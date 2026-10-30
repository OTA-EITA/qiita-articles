---
title: Laravel 13 の APP_DEBUG=true は Cookie・本文・SQL を伏せずに出す。本番に残りやすい 4 つの設定を動かして確かめた
tags:
  - Laravel
  - PHP
  - Security
  - SRE
  - CORS
private: true
updated_at: '2026-10-30T21:45:22+09:00'
id: b2340a58e926db2458a2
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

新しく作った Laravel 13 のアプリで、本番に残りやすい 4 つの設定を変えながら動かして確かめました。

- `APP_DEBUG=true` の 500 のエラーページには、**Cookie・Authorization を含むリクエストヘッダー、password を含む本文、値を埋め込んだ SQL** が伏せずに出ます。
- `config/cors.php` で `allowed_origins` を `['*']` のまま `supports_credentials` を `true` にすると、**どのオリジンから来ても、そのオリジンを cookie 付きで許可**します。
- `trustProxies(at: '*')` にすると、**どのクライアントからでも** `X-Forwarded-For`・`-Host`・`-Proto` を信じます。
- Telescope は `APP_ENV=local` のとき、**ログインしていなくても**ダッシュボードを開けます。

どれも開発中は困らない 1 行の設定なので、本番に残りやすいところです。本番の `.env` を作る人、またはレビューする人向けに、動かした結果と本番で確認する値をまとめました。

`composer create-project laravel/laravel` で作った直後の `.env` は `APP_ENV=local`、`APP_DEBUG=true`、`LOG_LEVEL=debug` という開発用の値です。PHP 全般の本番のエラー表示については [本番のエラー表示で情報を漏らさない7設定](https://qiita.com/jiis-sasaki/items/fb459dcedeefe41621a6) が php.ini・nginx・Apache・WordPress の設定をまとめているので、この記事は Laravel 13 に絞って、実際に動かした結果を扱います。同じ設定を `.env` や `config/*.php` から見つける CLI と検証のワークフローは [OTA-EITA/laravel-prod-guard](https://github.com/OTA-EITA/laravel-prod-guard) に置いてあります。

## 対象と前提

- laravel/laravel v13.11.0（skeleton）、laravel/framework 13.38.0、laravel/telescope 5.26.0、fruitcake/php-cors v1.4.0
- PHP 8.4、`php artisan serve`
- 2026 年 10 月 29 日に、GitHub Actions の ubuntu-24.04 ランナー（使い捨て）で確認

リクエストに入れた Cookie・トークン・パスワードの値は、検証用に作った目印の文字列です。

## 本番の env で確認すること

先に、確かめた結果から決めた本番の値を載せます。理由は後ろの節にあります。

| 設定 | 本番の値 |
|---|---|
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` |
| `APP_KEY` | `php artisan key:generate --show` で作った値。`.env.example` には書かない |
| `SESSION_SECURE_COOKIE` | `true`（HTTPS で配信している場合） |
| `LOG_LEVEL` | `info` 以上 |
| `config/cors.php` | credentials を使うなら `allowed_origins` に自分のフロントエンドのオリジンだけを書く |
| `trustProxies` | ロードバランサーのアドレスを書く。`*` にするなら、アプリに直接つながる経路をふさぐ |

## APP_DEBUG=true は、ヘッダー・本文・SQL を伏せずに出す

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

ソースを読むと、そのとおりの作りです（[Exception.php L213-293](https://github.com/laravel/framework/blob/v13.38.0/src/Illuminate/Foundation/Exceptions/Renderer/Exception.php#L213-L293)）。

- ヘッダーは `$request->headers->all()` をそのまま並べる
- 本文は `$request->all()` をそのまま JSON にする
- SQL は、バインド値を `?` に埋め込んで表示する

伏せる処理はありません。このエラーページは Laravel 11 の途中で framework に入ったものです（[#51261](https://github.com/laravel/framework/pull/51261)、2024 年 5 月 27 日にマージ）。

`APP_DEBUG=false` にして同じリクエストを送ると、500 のページにはどの目印も出ませんでした。

### 何が問題になるのか

見えるのは、そのリクエストを送った本人の Cookie やパスワードです。他人のセッションが見えるわけではありません。問題になるのは次のようなものです。

- **内部の情報**: スタックトレース、コードの断片、サーバー上のパス、テーブル名と SQL。攻撃の下調べにそのまま使えます。
- **途中で足されたヘッダー**: ロードバランサーや API ゲートウェイが、内部向けの認証トークンやユーザー ID をヘッダーに足してアプリに渡している構成があります。クライアントは本来それを見られませんが、エラーページには並びます。
- **SQL に入る他人のデータ**: 例外の前に、ほかのユーザーのデータを条件に入れた SQL を流していれば、その値も出ます。

## credentials を有効にした CORS は、どのオリジンも cookie 付きで許可する

Laravel 13 の skeleton には `config/cors.php` がなく、framework の既定値が使われます。既定は `allowed_origins` が `['*']`、`supports_credentials` が `false` です（[config/cors.php L22-32](https://github.com/laravel/framework/blob/v13.38.0/config/cors.php#L22-L32)）。

`php artisan config:publish cors` で `config/cors.php` を出し、`supports_credentials` だけを `true` に書き換えて、`api/*` の下のルートに次のリクエストを送りました。

```sh
curl -s -o /dev/null -D - -H 'Origin: https://evil.example' http://127.0.0.1:8000/api/lab
```

| 設定 | Access-Control-Allow-Origin | Access-Control-Allow-Credentials |
|---|---|---|
| 既定 | `*` | なし |
| `allowed_origins ['*']` + `supports_credentials true` | `https://evil.example` | `true` |

ブラウザは `*` と credentials の組み合わせを受け付けません。そのため、`supports_credentials` を `true` にしたとき、Laravel が使っている fruitcake/php-cors は、**送られてきた Origin をそのまま返します**（[CorsService.php L204-219](https://github.com/fruitcake/php-cors/blob/v1.4.0/src/CorsService.php#L204-L219)）。CORS としては、どのオリジンにも cookie 付きのレスポンスを読ませる設定です。

実際に cookie が付くかは、cookie の `SameSite` で決まります。Laravel のセッション cookie は既定で `SameSite=Lax` なので、仕様どおりなら、まったく別のサイトからの `fetch` には付きません。同じサイトの別オリジン（ほかのサブドメインなど）からのリクエストや、`SESSION_SAME_SITE=none` にしている場合は付きます。ここはブラウザでは試していません。

SPA のために「とりあえず credentials を有効にする」と、ここに当たります。

## trustProxies('*') だと、クライアントが IP とホストを名乗れる

Laravel 11 以降は、`bootstrap/app.php` で信頼するプロキシを決めます。

```php
->withMiddleware(function (Middleware $middleware): void {
    $middleware->trustProxies(at: '*');
})
```

アプリが認識するクライアントの情報を返すルートを足して、`X-Forwarded-*` を付けて呼びました。

```php
Route::get('/lab/client', fn (Illuminate\Http\Request $r) => [
    'ip' => $r->ip(), 'secure' => $r->isSecure(), 'host' => $r->getHost(),
]);
```

```sh
curl -s -H 'X-Forwarded-For: 203.0.113.9' -H 'X-Forwarded-Host: evil.example' \
  -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/lab/client
```

| 設定 | `$request->ip()` | `isSecure()` | `getHost()` |
|---|---|---|---|
| 既定（何も書かない） | `127.0.0.1` | false | `127.0.0.1` |
| `trustProxies(at: '*')` | `203.0.113.9` | true | `evil.example` |

`*` を指定すると、信頼するプロキシが `0.0.0.0/0` と `::/0`、つまりすべてのアドレスになります（[TrustProxies.php L84-86、L121-124](https://github.com/laravel/framework/blob/v13.38.0/src/Illuminate/Http/Middleware/TrustProxies.php#L84-L124)）。ロードバランサーの後ろにしか置かないなら問題ありません。ただ、アプリのポートに直接つなげる経路が残っていると、クライアントが IP アドレスとホスト名を自由に名乗れます。レート制限や監査ログの IP、メールのリンクに使う URL が、その値になります。

## APP_ENV=local の Telescope は、ログインなしで開ける

Telescope のダッシュボードは、`APP_ENV` が `local` のときは認可のゲートを通りません（[TelescopeApplicationServiceProvider.php L29-32](https://github.com/laravel/telescope/blob/v5.26.0/src/TelescopeApplicationServiceProvider.php#L29-L32)）。

| APP_ENV | ログインせずに `/telescope` |
|---|---|
| `local` | 200 |
| `production` | 403 |

Telescope は、リクエストのヘッダーや本文、SQL、ジョブ、例外を記録して一覧で見せるツールです。`APP_ENV=local` のまま公開すると、**ほかのユーザーのリクエストも含めて**誰でも見られます。本人のデータに限られる APP_DEBUG のエラーページより、影響が大きいです。

Telescope は、`Authorization` と `php-auth-pw` のヘッダー、`password`・`password_confirmation` のパラメーターを既定で伏せます。一方、`Cookie` ヘッダーは伏せる対象に入っていません（[Telescope.php L83-96](https://github.com/laravel/telescope/blob/v5.26.0/src/Telescope.php#L83-L96)）。記録されたリクエストから、ほかのユーザーのセッション cookie が見えることになります。エラーページは何も伏せず、Telescope は一部を伏せる、という違いもありました。

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

見ている項目は全部で 17 個で、`--list-checks` で一覧が出ます。ここまでの 4 つのほかに、次のようなものを見ます。

- `APP_KEY` が空・長さ違い、または `.env.example` に書かれている
- `.env` が git で追跡されている
- Debugbar・Clockwork・Ignition が `require-dev` ではなく `require` にある
- セッション cookie の `Secure`・`HttpOnly`・`SameSite=None`
- `APP_URL` が http
- `public/` の下の `.env`、`.git`、`phpinfo()` を呼ぶファイル
- DB のパスワードが空、またはよくある値

各項目には、根拠になる Laravel 13 のソースの行へのリンクを付けました。

## 確かめていないこと

- Telescope に記録されたほかのユーザーの cookie で、実際になりすませるか
- CORS の設定で、ブラウザから実際に cookie が付くか。`SameSite` の話はソースと仕様から書いています
- Horizon。ソースでは Telescope と同じく `local` のとき認可を通りません（[Horizon.php L81-86](https://github.com/laravel/horizon/blob/v5.50.1/src/Horizon.php#L81-L86)）が、動かしてはいません
- `php artisan serve` 以外の、nginx や PHP-FPM の前段がある構成

## 参考

- [laravel/laravel v13.11.0 .env.example](https://github.com/laravel/laravel/blob/v13.11.0/.env.example)
- [laravel/framework v13.38.0 Exceptions/Renderer/Exception.php](https://github.com/laravel/framework/blob/v13.38.0/src/Illuminate/Foundation/Exceptions/Renderer/Exception.php)
- [laravel/framework #51261 Improves errors](https://github.com/laravel/framework/pull/51261)
- [fruitcake/php-cors v1.4.0 CorsService.php](https://github.com/fruitcake/php-cors/blob/v1.4.0/src/CorsService.php)
- [laravel/telescope v5.26.0 TelescopeApplicationServiceProvider.php](https://github.com/laravel/telescope/blob/v5.26.0/src/TelescopeApplicationServiceProvider.php)
- [laravel/horizon v5.50.1 Horizon.php](https://github.com/laravel/horizon/blob/v5.50.1/src/Horizon.php)
- [OTA-EITA/laravel-prod-guard](https://github.com/OTA-EITA/laravel-prod-guard)
