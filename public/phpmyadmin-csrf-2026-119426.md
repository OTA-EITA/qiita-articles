---
title: >-
  phpMyAdmin 5.2.3 の CSRF（CVE-2026-119426）を手元で確かめた。5.2 系にはまだ修正版がなく「5.2.4
  に上げよ」は誤り
tags:
  - phpMyadmin
  - Security
  - csrf
  - PHP
  - 脆弱性
private: false
updated_at: '2026-11-05T12:34:29+09:00'
id: 16fbf2683b2677e88af9
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

2026 年 10 月 30 日に、phpMyAdmin 5.2.3 以前の脆弱性が 7 件公開されました。この記事では、その中で一番深刻な CSRF（CVE-2026-119426、CVSS 7.7）を取り上げます。

CVE の記録、5.2.3 の実際のソース、修正コミット、保守ブランチの今の状態を一次情報で確かめました。原因になっているコードの動きは、公式リリースの 5.2.3 に同梱されたクラスをそのまま呼び出して、手元で再現しています。phpMyAdmin を社内やサーバーに置いて使っている人に向けた記事です。

確認したのは 2026 年 11 月 5 日です。状況は変わるので、使う前に出典のリンク先を見てください。

## 結論

- 原因は、CSRF トークンが合わなかったときに `$_POST` などのスーパーグローバルは空にするのに、先に作ってあった PSR-7 のリクエストオブジェクトを空にし忘れていたことです。コントローラは後者から `sql_query` を読むので、攻撃者が仕込んだ SQL が生き残ります
- `http` 認証と `config` 認証だと、資格情報がリクエストに自動で付くため、別サイトからの POST でも認証が通ります。唯一の守りだった CSRF トークンが効かないので、被害者の権限で任意の SQL が走ります
- **2026 年 11 月 5 日時点で、5.2 系の修正版は出ていません。** 最新リリースは 2025 年 10 月の 5.2.3 のままです。「5.2.4 に上げればよい」と書いている記事がありますが、5.2.4 は存在しません
- 修正は開発ブランチ（新しいミドルウェア構成）にだけ入っています。5.2 系の保守ブランチ（QA_5_2）は 11 月 3 日時点でもまだ脆弱なコードのままです
- つまり今は、更新ではなく運用側の緩和でしのぐしかありません。`http`・`config` 認証を避けて cookie 認証にする、phpMyAdmin を信頼できる範囲の外に出さない、といった対策になります

## 2026 年 11 月 5 日時点の状況

| 項目 | 内容 | 出典 |
| --- | --- | --- |
| 公開日 | 2026-10-30 | [NVD の記録][nvd] |
| 原因 | CSRF トークン不一致後の後始末がスーパーグローバルにしか効かず、PSR-7 リクエストに `sql_query` が残る | [5.2.3 のソース][common523] |
| 深刻度 | CVSS 4.0 で 7.7（High） | [NVD の記録][nvd] |
| 影響範囲 | 5.2.3 以前のすべて。`http`・`config` 認証のとき | [vulncheck の記録][vulncheck] |
| 攻撃対象 | `/sql`・`/database/sql` に `sql_query` を送る非 AJAX の POST | [vulncheck の記録][vulncheck] |
| 修正版 | なし。最新リリースは 5.2.3（2025-10-08） | [リリース一覧][releases] |
| 修正コミット | 2026-10-26 にマージ（PR #20569）。開発ブランチのミドルウェアを直すもの | [修正コミット][fix] |
| 5.2 保守ブランチ | QA_5_2 は 2026-11-03 時点でも未修正 | [QA_5_2 のソース][commonqa52] |

同じ日に公開された 7 件は次のとおりです。この記事では 1 番目を扱います。

| CVE | 種別 | CVSS 4.0 | 概要 |
| --- | --- | --- | --- |
| CVE-2026-119426 | CSRF | 7.7 | 非 AJAX の POST でトークン検査を回避し、任意の SQL を実行 |
| CVE-2026-119561 | 認証回避 | 7.6 | WebAuthn のアサーション署名を検証していない |
| CVE-2026-119428 | SSRF | 6.3 | `setup/validate.php` が未認証で外向きの接続を起こせる |
| CVE-2026-119429 | 再認証漏れ | 5.3 | 二要素認証を再認証なしで外せる |
| CVE-2026-119563 | 蓄積型 XSS | 5.1 | テーブル名の HTML がエスケープされずに表示される |
| CVE-2026-119427 | SQL インジェクション | 2.3 | Designer の `saveSetting()` |
| CVE-2026-119562 | SQL インジェクション | 2.3 | `central-columns` の列情報 |

## 原因

phpMyAdmin 5.2.3 の `Common::run()` は、まず最初にリクエストを作ります。

```php
// libraries/classes/Common.php（抜粋）
$request = ServerRequestFactory::createFromGlobals();
```

このとき同梱の Slim の実装は、メソッドが POST で `Content-Type` がフォーム形式（`application/x-www-form-urlencoded` か `multipart/form-data`）のときに、`$_POST` の中身をリクエストの本文として取り込みます。

```php
// vendor/slim/psr7/src/Factory/ServerRequestFactory.php（抜粋）
$contentTypesWithParsedBodies = ['application/x-www-form-urlencoded', 'multipart/form-data'];
if ($method === 'POST' && in_array($parsedContentType, $contentTypesWithParsedBodies)) {
    return $request->withParsedBody($_POST);
}
```

ブラウザが普通の `<form>` を POST すると `application/x-www-form-urlencoded` になります。別サイトに置いた攻撃者のフォームも同じです。つまりこの時点で、攻撃者が送った `sql_query` がリクエストの本文に入ります。

そのあと、CSRF トークンの検査が走ります。

```php
// libraries/classes/Common.php（抜粋）
self::checkTokenRequestParam();
```

トークンが合わないときの後始末がこれです。

```php
// libraries/classes/Common.php の checkTokenRequestParam()（抜粋）
$allowList = ['ajax_request'];
Sanitize::removeRequestVars($allowList);
```

その `removeRequestVars()` が消すのは、スーパーグローバルだけです。

```php
// libraries/classes/Sanitize.php の removeRequestVars()（抜粋）
foreach ($keys as $key) {
    if (! in_array($key, $allowList)) {
        unset($_REQUEST[$key], $_GET[$key], $_POST[$key]);
        continue;
    }
    // ...
}
```

ここで `$_POST['sql_query']` は消えます。ところが、さっき作った `$request` は PSR-7 の不変オブジェクトで、本文を自分の中に抱えています。`$_POST` を消しても `$request` の本文は変わりません。

そして、この後でコントローラが読むのは `$request` の方です。

```php
// libraries/classes/Common.php（抜粋）
$sql_query = '';
if ($request->isPost()) {
    $sql_query = $request->getParsedBodyParam('sql_query', '');
}
```

`getParsedBodyParam()` は、`$_POST` ではなくリクエストが抱えている本文を返します。

```php
// libraries/classes/Http/ServerRequest.php（抜粋）
public function getParsedBodyParam(string $param, $default = null)
{
    $postParams = $this->getParsedBody();
    if (is_array($postParams) && isset($postParams[$param])) {
        return $postParams[$param];
    }
    // ...
    return $default;
}
```

CSRF の後始末がスーパーグローバルにしか効かず、コントローラは消されていない PSR-7 側から値を読む。ここがズレていて、攻撃者の SQL が生き残ります。

### なぜ http・config 認証だけなのか

上のズレは認証方式に関係なく起きます。それでも影響するのが `http` と `config` だけなのは、別サイトからの POST が認証を通れるかどうかが、認証方式ごとに違うからです。5.2.3 のソースで確かめました。

- **http 認証**: 資格情報は HTTP の `Authorization` ヘッダから来ます。`readCredentials()` は `PHP_AUTH_USER` などを読むだけで、トークンは見ません。Basic 認証のヘッダはクッキーではないので、別サイトからの POST でもブラウザが再送します。そのまま認証が通ります
- **config 認証**: ユーザーとパスワードはサーバー側の設定に書いてあります。`readCredentials()` が拒むのは `token_provided && token_mismatch` のときだけです（[ソース][authcfg]）。攻撃者はトークンを付けないので `token_provided` は false になり、この条件は成立しません。認証は通ります

```php
// libraries/classes/Plugins/Auth/AuthenticationConfig.php の readCredentials()（抜粋）
if ($GLOBALS['token_provided'] && $GLOBALS['token_mismatch']) {
    return false;
}
```

- **cookie 認証**: 資格情報は暗号化されてクッキーに入ります。そのクッキーの `SameSite` は既定で `Strict` です（[ソース][samesite]）。別サイトからの POST ではブラウザがこのクッキーを送らないので、資格情報が復号できず、認証が通りません。だから同じ手は効きません

```php
// libraries/classes/Config/Settings.php の setCookieSameSite()（抜粋）
if (! isset($settings['CookieSameSite']) || ! in_array($settings['CookieSameSite'], ['Lax', 'None'], true)) {
    return 'Strict';
}
```

cookie 認証でも、`CookieSameSite` を `None` に変えているとクッキーが送られてしまい、同じ経路が開きます。既定の `Strict`、または `Lax` のままにしておくのが大事です。

## 手元で確かめる

公式リリースの 5.2.3 に同梱されている本物のクラスを呼び出して、値が生き残ることを確かめます。自分のマシンの中だけで動かし、ネットワークにも外部のサーバーにも触れません。

```php
<?php
require __DIR__ . '/vendor/autoload.php';

use PhpMyAdmin\Http\Factory\ServerRequestFactory;
use PhpMyAdmin\Common;

// 別サイトのフォームから届いた POST を模す。攻撃者は本物のトークンを
// 知らないので、トークンは付けない。
$_SERVER['REQUEST_METHOD'] = 'POST';
$_SERVER['CONTENT_TYPE']   = 'application/x-www-form-urlencoded';
$_POST = [
    'db'        => 'poc',
    'sql_query' => 'DROP DATABASE victim_data',  // 攻撃者が選んだ SQL
];
$_REQUEST = $_POST;
$_SESSION[' PMA_token '] = 'REAL-SECRET-TOKEN-xyz'; // サーバー側の本物

$request = ServerRequestFactory::createFromGlobals();

echo '前: $_POST       = ' . var_export($_POST['sql_query'] ?? null, true) . "\n";
echo '前: $request     = ' . var_export($request->getParsedBodyParam('sql_query', null), true) . "\n";

global $token_provided, $token_mismatch;
Common::checkTokenRequestParam(); // CSRF トークンの検査

echo 'token_provided = ' . var_export($token_provided, true)
   . '  token_mismatch = ' . var_export($token_mismatch, true) . "\n";
// config 認証が弾くのは (token_provided && token_mismatch) のときだけ
echo 'config 認証なら弾く? ' . (($token_provided && $token_mismatch) ? 'yes' : 'NO') . "\n";

echo '後: $_POST       = ' . var_export($_POST['sql_query'] ?? null, true) . "\n";
echo '後: $request     = ' . var_export($request->getParsedBodyParam('sql_query', null), true) . "\n";

$sql = $request->isPost() ? $request->getParsedBodyParam('sql_query', '') : '';
echo 'コントローラが受け取る値 = ' . var_export($sql, true) . "\n";
```

PHP 8.5.12 で動かした結果です。

```text
前: $_POST       = 'DROP DATABASE victim_data'
前: $request     = 'DROP DATABASE victim_data'
token_provided = false  token_mismatch = true
config 認証なら弾く? NO
後: $_POST       = NULL
後: $request     = 'DROP DATABASE victim_data'
コントローラが受け取る値 = 'DROP DATABASE victim_data'
```

トークンを付けていないので `token_provided` は false、`token_mismatch` は true です。この組み合わせだと、後で見るように config 認証は弾きません。そして CSRF の後始末で `$_POST` は空になっていますが、`$request` からは攻撃者の SQL がそのまま取れます。コントローラはこちらを読むので、トークンがなくても値が渡ります。

ここで確かめたのは「CSRF の後始末をすり抜けて値が残る」という原因の部分です。最後に実際に SQL がデータベースへ流れるところまでは、CVE と調査報告が任意 SQL の実行としています。全体を通した実行は手元では試していません。

## 修正

2026 年 10 月 26 日にマージされた修正（PR #20569）は、開発ブランチの新しいミドルウェアに入っています。トークンが合わないとき、スーパーグローバルに加えて PSR-7 のリクエストも空にし、ルートをホームに戻します。

```php
// src/Http/Middleware/TokenRequestParamChecking.php（修正後の抜粋）
$_REQUEST = $_POST = $_GET = $_COOKIE = [];
$request = $request->withParsedBody([])
    ->withQueryParams([])
    ->withCookieParams([])
    ->withAttribute('route', '/');
```

同じ入力に、この後始末を当てた結果です。

```text
route attribute          = '/'
controller sees sql_query = ''
>>> fixed: attacker SQL dropped, request routed home
```

リクエストの本文が空になり、ルートもホームに戻るので、コントローラには何も渡りません。

## 今できること

修正版のリリースがまだないので、更新では閉じられません。運用側で次のような対策になります。

- `http` 認証・`config` 認証を使っているなら、cookie 認証に変える。CVE が影響の条件として挙げているのはこの 2 つの認証です
- cookie 認証なら、`CookieSameSite` を既定の `Strict`（または `Lax`）のままにする。`None` にするとクロスサイトの POST でクッキーが送られ、同じ経路が開きます
- phpMyAdmin を公開の場所に置かない。社内からだけ届くようにする、VPN の内側に置く、接続元の IP を絞る
- 使っていないなら止める。常時立ち上げておかず、必要なときだけ動かす
- リバースプロキシや WAF の前段で、`/sql`・`/database/sql` への素の POST を見張る。ただし根本ではないので補助として

5.2 系の保守ブランチに修正が入って、5.2.4 などの修正版が出たら、そちらへの更新が本筋です。公開は出典のリリース一覧で確認できます。

## まとめ

CVE-2026-119426 は、CSRF トークンの後始末がスーパーグローバルにしか効かず、コントローラが読む PSR-7 のリクエストには攻撃者の値が残る、というズレが原因でした。スーパーグローバルから PSR-7 への移行の途中で、片方だけ消す形になっていたところです。手元で本物のクラスを呼ぶと、トークン検査の後も値が生き残ることが確かめられました。

今の時点で 5.2 系の修正版はありません。「5.2.4 に上げる」という対策は、まだ取れません。それまでは認証方式と公開範囲で守るのが現実的です。

[nvd]: https://nvd.nist.gov/vuln/detail/CVE-2026-119426
[vulncheck]: https://www.vulncheck.com/advisories/phpmyadmin-through-5.2.3-csrf-token-bypass-via-non-ajax-post-to-sql
[common523]: https://github.com/phpmyadmin/phpmyadmin/blob/RELEASE_5_2_3/libraries/classes/Common.php#L476-L511
[commonqa52]: https://github.com/phpmyadmin/phpmyadmin/blob/QA_5_2/libraries/classes/Common.php#L476-L511
[authcfg]: https://github.com/phpmyadmin/phpmyadmin/blob/RELEASE_5_2_3/libraries/classes/Plugins/Auth/AuthenticationConfig.php#L59
[samesite]: https://github.com/phpmyadmin/phpmyadmin/blob/RELEASE_5_2_3/libraries/classes/Config/Settings.php#L2267-L2274
[fix]: https://github.com/phpmyadmin/phpmyadmin/commit/910322373f14ed4601c85234858f630f127569ef
[releases]: https://github.com/phpmyadmin/phpmyadmin/releases
