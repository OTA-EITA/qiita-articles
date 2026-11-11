---
title: Node.js 11月のセキュリティリリース（26.x・24.x・22.x）。自分の版の確かめ方と上げ方
tags:
  - Node.js
  - JavaScript
  - Security
  - npm
  - 脆弱性
private: false
updated_at: ''
id: null
organization_url_name: null
slide: false
---

Node.js の 26.x・24.x・22.x に、セキュリティリリースが出ました。直った脆弱性は 16 件で、深刻度は HIGH が 7 件、MEDIUM が 6 件、LOW が 3 件です。

| 系列 | 修正版 |
|---|---|
| 26.x | v26.13.1 |
| 24.x | v24.22.3 |
| 22.x | v22.23.5 |

内容は、公式のセキュリティリリース（[Wednesday, November 11, 2026 Security Releases](https://nodejs.org/en/blog/vulnerability/november-2026-security-releases)）の原文で確かめました。

**要点**

- HIGH の 7 件は、すべて HTTP/2・HTTPS・TLS のサーバー側です。そのうち 3 件は 24.x と 26.x だけが対象です
- 公開の直後は、GitHub Actions の `actions/setup-node` と Homebrew には、まだ修正版が来ていませんでした（2026-11-12 7:50 時点）。`check-latest: true` を付けても、古い版が入りました。版を明示すると、修正版が入りました
- サポートが終わった版には、修正版が出ません。20.x は 2026-04-30 にサポートが終わっています（[Node.js のリリース予定表](https://github.com/nodejs/Release/blob/main/schedule.json)）

## 直った脆弱性

内容は、原文の見出しと説明の要約です。

| CVE | 深刻度 | 内容 | 対象の系列 |
|---|---|---|---|
| CVE-2026-123863 | HIGH | HTTP/2 のセッションを閉じる処理の検査（assertion）で、認証なしのクライアントがサーバーを落とせる。TLS でも平文でも起きる | 24.x、26.x |
| CVE-2026-123864 | HIGH | HTTPS で、長さ 0 の TLS の書き込みが HTTP の解析処理に入り直し、認証なしのクライアントが、ほかの接続のメモリ（TLS の秘密鍵や、ほかの利用者のリクエストを含む）を読める | 22.x、24.x、26.x |
| CVE-2026-123865 | HIGH | HTTP/2 で、接続を閉じている途中にプロトコルエラーを起こされると、セッションが片付かず、メモリとファイル記述子が漏れ続ける | 22.x、24.x、26.x |
| CVE-2026-123866 | HIGH | HTTP/2 のストリームを閉じる処理の解放後使用（use-after-free）で、解放済みの応答のメモリ（ほかの接続の応答を含む）が相手に送られる | 22.x、24.x、26.x |
| CVE-2026-126051 | HIGH | TLS サーバーが `SNICallback`・`OCSPRequest`・`newSession`・`resumeSession`、または `server.addContext()` を使っていると、ハンドシェイク中の処理で、認証なしの攻撃者がプロセスを落とせる | 24.x、26.x |
| CVE-2026-123872 | HIGH | TLS 1.2 の再ネゴシエーションで servername を変えられ、ホスト名ごとに違うクライアント証明書の方針を回避できる | 22.x、24.x、26.x |
| CVE-2026-123874 | HIGH | HTTP/2 の `respondWithFile()` などでファイルを返すとき、書き込み待ちのストリームをリセットされると、解放後使用でサーバーのメモリが壊される | 24.x、26.x |
| CVE-2026-123828 | MEDIUM | HTTP/2 の `altsvc()` に、`:authority` ヘッダーのような攻撃者が決められる値を渡すと、1 バイトのヒープバッファオーバーフローが起きる | 24.x、26.x |
| CVE-2026-123867 | MEDIUM | `server.addContext()` で、ホスト名にクライアント証明書の CA だけを指定し、サーバー証明書を指定しないと、既定の CA に戻ってしまい、ホストごとの相互 TLS の認可を回避できる | 22.x、24.x、26.x |
| CVE-2026-123868 | MEDIUM | HTTP/2 で、読まれていないストリームにたまる受信データが、セッションのメモリ上限（`maxSessionMemory`）に数えられず、認証なしのクライアントがメモリを使い切らせる | 24.x、26.x |
| CVE-2026-123871 | MEDIUM | `ERR_PROXY_INVALID_CONFIG` のエラーメッセージに、プロキシの認証情報が出る | 22.x、24.x、26.x |
| CVE-2026-123877 | MEDIUM | `https.Agent` で、`ca` を省いたリクエストと `ca: []` のリクエストが同じ TLS セッションを使い回し、証明書の検証を回避できる | 22.x、24.x、26.x |
| CVE-2026-123875 | MEDIUM | HTTP/2 の `respondWithFile()` などのダウンロードを 1 つ取り消されると、NULL 参照でサーバーが落ちる | 22.x、24.x、26.x |
| CVE-2026-123829 | LOW | Permission Model で、再帰モードの `fs.watch()` が、読む許可のない子孫のファイル名を渡してしまう（macOS と Windows） | 22.x、24.x、26.x |
| CVE-2026-123862 | LOW | zlib で、`params()` の処理中に `destroy()` されると、捕捉できない例外でプロセスが落ちる | 22.x、24.x、26.x |
| CVE-2026-106071 | LOW | Permission Model で、ワイルドカードの `--allow-fs-read`・`--allow-fs-write` が、含まないはずのパスにも一致する | 22.x、24.x、26.x |

このほか、依存ライブラリの更新として、undici（24.x、26.x）と sqlite（22.x、24.x）が入っています。

## 自分の版を確かめる

```console
$ node -v
v24.22.1
```

これは筆者の手元の版で、修正前です。各系列の最新のセキュリティ版は、公式の配布一覧（`https://nodejs.org/dist/index.json`）の `security` で分かります。

```console
$ curl -s https://nodejs.org/dist/index.json \
  | jq -r '[.[] | select(.security)] | group_by(.version | split(".")[0]) | map(max_by(.date)) | .[]
           | select(.version | test("^v(22|24|26)\\.")) | "\(.version) \(.date)"'
v22.23.5 2026-11-11
v24.22.3 2026-11-10
v26.13.1 2026-11-10
```

自分の版が、ここに出る版より古ければ、上げる必要があります。

CI やコンテナで使っている版も見てください。

```console
# Dockerfile のベースイメージ
$ grep -n '^FROM node' Dockerfile

# GitHub Actions
$ grep -rn 'node-version' .github/workflows/
```

## 上げ方

修正版がどこから手に入るかは、経路ごとに違いました。2026-11-12 7:48〜7:50 に確かめた結果です。

| 経路 | 修正版 |
|---|---|
| 公式の配布物（nodejs.org/dist） | 3 系列とも、あり |
| Docker Hub の公式イメージ（`node:24.22.3` など） | 3 系列とも、あり |
| `actions/setup-node` が先に見る一覧（actions/node-versions） | まだない |
| Homebrew の `node@24` | まだない（24.22.2 のまま） |

### GitHub Actions の場合

公開の直後に、`ubuntu-latest` で `actions/setup-node@v7` を 3 通りの指定で動かしました。

| 指定 | 入った版 |
|---|---|
| `node-version: 24` | v24.22.2 |
| `node-version: 24` と `check-latest: true` | v24.22.2 |
| `node-version: 24.22.3` | v24.22.3 |

`check-latest: true` を付けても、修正前の v24.22.2 が入りました。版を明示した場合は、ログに `Not found in manifest. Falling back to download directly from Node` と出て、公式の配布物から v24.22.3 が入りました。

setup-node は、まず actions/node-versions から取り、そこにない版は、公式の配布物から直接ダウンロードします（[setup-node の説明](https://github.com/actions/setup-node/blob/main/docs/advanced-usage.md#check-latest-version)）。公開の直後は、一覧に載るまで、修正版の番号を明示するのが確実です。

```yaml
- uses: actions/setup-node@v7
  with:
    node-version: 24.22.3
```

### Docker の場合

公式イメージには、修正版のタグがありました。ベースイメージのタグを修正版に上げて、イメージを作り直します。`node:24` のような版を固定しないタグでも、手元に残っている古いイメージが使われることがあるので、`--pull` を付けて作り直してください。

```console
$ docker build --pull -t myapp .
```

### Homebrew の場合

確かめた時点では、`node@24` はまだ 24.22.2 でした。上げる前に、修正版が来ているかを確かめてください。

```console
$ brew update
$ brew info node@24   # 修正版が来ているかを確かめる
$ brew upgrade node@24
```

### nvm を使っている場合

nvm の README の書き方です。筆者の手元には nvm がないので、実行はしていません。

```console
$ nvm install --reinstall-packages-from=current 24
$ nvm alias default 24
$ node -v
```

## 出典

- Node.js、[Wednesday, November 11, 2026 Security Releases](https://nodejs.org/en/blog/vulnerability/november-2026-security-releases)
- Node.js、[配布一覧（dist/index.json）](https://nodejs.org/dist/index.json)
- Node.js、[リリース予定表（nodejs/Release の schedule.json）](https://github.com/nodejs/Release/blob/main/schedule.json)
- actions/setup-node、[Check latest version](https://github.com/actions/setup-node/blob/main/docs/advanced-usage.md#check-latest-version)
- nvm、[README](https://github.com/nvm-sh/nvm/blob/master/README.md)
