---
title: Laravel 13 の APP_DEBUG=true のエラーページは何を見せるか。CORS・プロキシ・Telescope と合わせて動かして確かめた
tags:
  - Laravel
  - PHP
  - Security
  - SRE
  - CORS
private: true
updated_at: '2026-10-30T12:30:54+09:00'
id: b2340a58e926db2458a2
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

## きっかけ

`composer create-project laravel/laravel` で作った直後の `.env` は、開発用の値です。

```ini
APP_ENV=local
APP_DEBUG=true
LOG_LEVEL=debug
```

開発ではこれで正しいのですが、この `.env` をもとに本番の設定を作ると、どこかが残ることがあります。`APP_DEBUG=true` が危ないことはよく知られています。では、Laravel 13 で実際に何が見えるのかを、きちんと確かめたことはありませんでした。

そこで、新しく作った Laravel 13 のアプリを GitHub Actions のランナー上で動かして、`APP_DEBUG`、CORS、信頼するプロキシ、Telescope の設定を変えながら、何が起きるかを確かめました。あわせて、同じ設定を `.env` や `config/*.php` から見つける CLI も作りました。

- 点検ツールと検証のワークフロー: [OTA-EITA/laravel-prod-guard](https://github.com/OTA-EITA/laravel-prod-guard)

### 既にある記事との違い

PHP 全般の本番のエラー表示については、[本番のエラー表示で情報を漏らさない7設定](https://qiita.com/jiis-sasaki/items/fb459dcedeefe41621a6) が php.ini・nginx・Apache・WordPress の設定をまとめています。この記事は Laravel 13 に絞って、設定を変えたアプリを実際に動かした結果を扱います。

## 結論

- `APP_DEBUG=true` のエラーページには、**送られてきたリクエストヘッダー（Cookie・Authorization を含む）、リクエスト本文（password を含む）、値を埋め込んだ SQL** が、伏せられずにそのまま出ます。
- ただし、見えるのはそのリクエストを送った本人のデータです。問題になるのは、コードの断片・SQL・サーバー上のパスといった内部の情報と、**途中のプロキシや API ゲートウェイが足したヘッダー**です。
- `config/cors.php` で `allowed_origins` を `['*']` のまま `supports_credentials` を `true` にすると、**どのオリジンから来ても、そのオリジンを cookie 付きで許可**します。
- `trustProxies(at: '*')` にすると、`X-Forwarded-For`・`-Host`・`-Proto` を**どのクライアントからでも**信じます。
- Telescope は `APP_ENV=local` のとき、**ログインしていなくても**ダッシュボードを開けます。

## 対象と前提

- laravel/laravel v13.11.0（skeleton）、laravel/framework 13.38.0、laravel/telescope 5.26.0
- PHP 8.4、`php artisan serve`
- GitHub Actions の ubuntu-24.04 ランナー（使い捨て）

リクエストに入れた Cookie・トークン・パスワードの値は、検証用に作った目印の文字列です。

## APP_DEBUG=true のエラーページ

途中で例外を投げるルートを1つ足し、そこに Cookie・Authorization ヘッダー・パスワードを付けて POST しました。ルートの中では、バインド値つきの SQL を1本だけ流しています。

```php
Route::post('/lab/fail', function () {
    DB::select('select ? as probe', ['bound-value-7d1c']);
    throw new RuntimeException('lab failure');
});
```

```sh
curl -X POST http://127.0.0.1:8000/lab/fail \
  -H "Cookie: laravel_session=cookie-secret-5e2a" \
  -H "Authorization: Bearer token-secret-91fb" \
  --data-urlencode "email=lab@example.com" --data-urlencode "password=pass-secret-c3d8"
```

`APP_ENV=production`、`APP_DEBUG=true` で返ってきた 500 のページの一部です。

![Laravel 13 のエラーページ。Queries にバインド値を埋め込んだ SQL、Headers に Cookie と Authorization、Body に password がそのまま出ている](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/laravel-prod-settings/debug-page.png)

ソースを読むと、そのとおりの作りです（[Exception.php L213-293](https://github.com/laravel/framework/blob/v13.39.0/src/Illuminate/Foundation/Exceptions/Renderer/Exception.php#L213-L293)）。

- ヘッダーは `$request->headers->all()` をそのまま並べる
- 本文は `$request->all()` をそのまま JSON にする
- SQL は、バインド値を `?` に埋め込んで表示する

伏せる処理はありません。このエラーページは Laravel 11 の途中（[#51261](https://github.com/laravel/framework/pull/51261)、2024 年 5 月）から framework に入ったものです。

`APP_DEBUG=false` にして同じリクエストを送ると、500 のページにはどの目印も出ませんでした。

### 何が問題になるのか

見えるのは、そのリクエストを送った本人の Cookie やパスワードです。他人のセッションが見えるわけではありません。問題になるのは次のようなものです。

- **内部の情報**: スタックトレース、コードの断片、サーバー上のパス、テーブル名と SQL。攻撃の下調べにそのまま使えます。
- **途中で足されたヘッダー**: ロードバランサーや API ゲートウェイが、内部向けの認証トークンやユーザー ID をヘッダーに足してアプリに渡している構成があります。クライアントは本来それを見られませんが、エラーページには並びます。
- **SQL に入る他人のデータ**: 例外の前に、ほかのユーザーのデータを条件に入れた SQL を流していれば、その値も出ます。

## CORS で任意のオリジンを cookie 付きで許可する

Laravel 13 の skeleton には `config/cors.php` がなく、framework の既定値が使われます。既定は `allowed_origins` が `['*']`、`supports_credentials` が `false` です（[config/cors.php L22-32](https://github.com/laravel/framework/blob/v13.39.0/config/cors.php#L22-L32)）。

`Origin: https://evil.example` を付けて `api/*` にリクエストすると、次のとおりでした。

| 設定 | Access-Control-Allow-Origin | Access-Control-Allow-Credentials |
|---|---|---|
| 既定 | `*` | なし |
| `allowed_origins ['*']` + `supports_credentials true` | `https://evil.example` | `true` |

ブラウザは `*` と credentials の組み合わせを受け付けません。そのため、`supports_credentials` を `true` にしたとき、Laravel が使っている fruitcake/php-cors は、**送られてきた Origin をそのまま返します**（[CorsService.php L204-219](https://github.com/fruitcake/php-cors/blob/v1.4.0/src/CorsService.php#L204-L219)）。CORS としては、どのオリジンにも cookie 付きのレスポンスを読ませる設定です。

実際に cookie が付くかは、cookie の `SameSite` で決まります。Laravel のセッション cookie は既定で `SameSite=Lax` なので、まったく別のサイトからの `fetch` には付きません。一方、同じサイトの別オリジン（ほかのサブドメインなど）からのリクエストには付きます。`SESSION_SAME_SITE=none` にしていれば、別のサイトからでも付きます。

SPA のために「とりあえず credentials を有効にする」と、ここに当たります。`allowed_origins` に自分のフロントエンドのオリジンだけを書いてください。

## trustProxies(at: '*')

Laravel 11 以降は、`bootstrap/app.php` で信頼するプロキシを決めます。

```php
->withMiddleware(function (Middleware $middleware): void {
    $middleware->trustProxies(at: '*');
})
```

`X-Forwarded-For: 203.0.113.9`、`X-Forwarded-Host: evil.example`、`X-Forwarded-Proto: https` を付けて、アプリが認識するクライアントの情報を返すルートを呼びました。

| 設定 | `$request->ip()` | `isSecure()` | `getHost()` |
|---|---|---|---|
| 既定（何も書かない） | `127.0.0.1` | false | `127.0.0.1` |
| `trustProxies(at: '*')` | `203.0.113.9` | true | `evil.example` |

`*` を指定すると、信頼するプロキシが `0.0.0.0/0` と `::/0`、つまりすべてのアドレスになります（[TrustProxies.php L84-86、L121-124](https://github.com/laravel/framework/blob/v13.39.0/src/Illuminate/Http/Middleware/TrustProxies.php#L84-L124)）。ロードバランサーの後ろにしか置かないなら問題ありません。ただ、アプリのポートに直接つなげる経路が残っていると、クライアントが IP アドレスとホスト名を自由に名乗れます。レート制限や監査ログの IP、メールのリンクに使う URL が、その値になります。

## Telescope と APP_ENV=local

Telescope のダッシュボードは、`APP_ENV` が `local` のときは認可のゲートを通りません（[TelescopeApplicationServiceProvider.php L29-32](https://github.com/laravel/telescope/blob/v5.26.0/src/TelescopeApplicationServiceProvider.php#L29-L32)）。Horizon も同じです。

| APP_ENV | ログインせずに `/telescope` |
|---|---|
| `local` | 200 |
| `production` | 403 |

Telescope は、リクエストのヘッダーや本文、SQL、ジョブ、例外を記録して一覧で見せるツールです。`APP_ENV=local` のまま公開すると、**ほかのユーザーのリクエストも含めて**誰でも見られます。本人のデータに限られる APP_DEBUG のエラーページより、影響が大きいです。

Telescope は、`Authorization` ヘッダーと `password`・`password_confirmation` を既定で伏せます。一方、`Cookie` ヘッダーは伏せる対象に入っていません（[Telescope.php L83-96](https://github.com/laravel/telescope/blob/v5.26.0/src/Telescope.php#L83-L96)）。記録されたリクエストから、ほかのユーザーのセッション cookie が見えることになります。その cookie で実際になりすませるかまでは、今回は試していません。

エラーページは何も伏せず、Telescope は一部を伏せる、という違いもありました。

## 設定から見つける

ここまでの設定は、どれもファイルを読めば分かります。`laravel-prod-guard` は、`.env`、`.env.example`、`composer.json`、`config/*.php`、`bootstrap/app.php`、`public/` を読むだけで、アプリのコードは実行しません。

```sh
git clone https://github.com/OTA-EITA/laravel-prod-guard.git
php laravel-prod-guard/bin/laravel-prod-guard path/to/app --env path/to/app/.env.production --fail-on medium
```

実行時の依存はないので、clone したディレクトリの `bin/laravel-prod-guard` をそのまま PHP 8.2 以上で動かせます。

新しく作ったアプリにそのまま使うと、次のようになります。

```text
HIGH   LPG001  .env:4  APP_DEBUG is true
MEDIUM LPG002  .env:2  APP_ENV is "local"
MEDIUM LPG009  config/session.php:172  SESSION_SECURE_COOKIE is not set
LOW    LPG012  .env:21  LOG_LEVEL is debug

1 app(s), 4 finding(s): 1 high, 2 medium, 1 low
```

開発用の `.env` としてはどれも正しい値です。本番用の env ファイルを `--env` で渡して、これが残っていないかを CI で確かめる使い方を想定しています。

設定の値は、env ファイル → アプリが公開した `config/*.php` に書かれた既定値 → framework の既定値、の順に決めます。`config/*.php` は PHP として実行せず、`'key' => env('NAME', default)` の形を読み取ります。

ほかに見ているもの（全 17 項目）:

- `APP_KEY` が空・長さ違い、または `.env.example` に書かれている
- `.env` が git で追跡されている
- Debugbar・Clockwork・Ignition が `require-dev` ではなく `require` にある
- セッション cookie の `Secure`・`HttpOnly`・`SameSite=None`
- `APP_URL` が http
- `public/` の下の `.env`、`.git`、`phpinfo()` を呼ぶファイル
- DB のパスワードが空、またはよくある値

各項目には、根拠になる Laravel 13 のソースの行へのリンクを付けました。

## 本番の env で確認すること

| 設定 | 本番の値 |
|---|---|
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` |
| `APP_KEY` | `php artisan key:generate --show` で作った値。`.env.example` には書かない |
| `SESSION_SECURE_COOKIE` | `true`（HTTPS で配信している場合） |
| `LOG_LEVEL` | `info` 以上 |
| `config/cors.php` | credentials を使うなら `allowed_origins` を列挙する |
| `trustProxies` | ロードバランサーのアドレスを書く。`*` にするなら、アプリに直接つながる経路をふさぐ |

## まとめ

`APP_DEBUG=true` のエラーページは、Laravel 13 ではヘッダー・本文・SQL を伏せずに出します。見えるのは送った本人のデータですが、内部の情報や途中で足されたヘッダーも一緒に出ます。CORS の credentials、`trustProxies('*')`、`APP_ENV=local` の Telescope は、どれも 1 行の設定で、開発中は困らないぶん本番に残りやすいところです。

本番の env ファイルを CI で点検しておくと、こうした値が残ったまま出ていくのを防げます。

## 参考

- [laravel/laravel v13.11.0 .env.example](https://github.com/laravel/laravel/blob/v13.11.0/.env.example)
- [laravel/framework v13.39.0 Exceptions/Renderer/Exception.php](https://github.com/laravel/framework/blob/v13.39.0/src/Illuminate/Foundation/Exceptions/Renderer/Exception.php)
- [laravel/framework #51261 Improves errors](https://github.com/laravel/framework/pull/51261)
- [fruitcake/php-cors v1.4.0 CorsService.php](https://github.com/fruitcake/php-cors/blob/v1.4.0/src/CorsService.php)
- [laravel/telescope v5.26.0 TelescopeApplicationServiceProvider.php](https://github.com/laravel/telescope/blob/v5.26.0/src/TelescopeApplicationServiceProvider.php)
- [OTA-EITA/laravel-prod-guard](https://github.com/OTA-EITA/laravel-prod-guard)
