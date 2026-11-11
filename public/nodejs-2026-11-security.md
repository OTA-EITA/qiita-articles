---
title: Node.js 11月のセキュリティリリース（26.x・24.x・22.x）。自分の版の確かめ方と上げ方
tags:
  - Node.js
  - JavaScript
  - Security
  - npm
  - 脆弱性
private: true
updated_at: ''
id: null
organization_url_name: null
slide: false
ignorePublish: true
---

<!-- 下書き: 2026-11-11 の公開後に、修正版の番号と CVE の表を一次情報（https://nodejs.org/en/blog/vulnerability/november-2026-security-releases）から埋める。埋めたら ignorePublish を false にする -->

2026 年 11 月 11 日に、Node.js 26.x・24.x・22.x のセキュリティリリースが出ました。最高の深刻度は HIGH です。

この記事では、影響と修正版を公式のセキュリティリリースで確かめたうえで、自分が使っている Node.js の版の確かめ方と、上げ方をまとめます。

## 結論

- 26.x・24.x・22.x はすべて対象です。修正版は 【26.x の版】・【24.x の版】・【22.x の版】 です
- サポートが終わった版には修正版が出ません。20.x は 2026-04-30 にサポートが終わっています（[Node.js のリリース予定表](https://github.com/nodejs/Release/blob/main/schedule.json)）。22.x 以降へ移る必要があります
- 【HIGH の件の要約を 1〜2 行】

## 直った脆弱性

| CVE | 深刻度 | 内容 | 対象の系列 |
| --- | --- | --- | --- |
| 【公開後に記入】 | | | |

## 自分の版を確かめる

```console
$ node -v
```

各系列の最新のセキュリティ版は、公式の配布一覧（`https://nodejs.org/dist/index.json`）の `security` で分かります。

```console
$ curl -s https://nodejs.org/dist/index.json \
  | jq -r '[.[] | select(.security)] | group_by(.version | split(".")[0]) | map(max_by(.date)) | .[]
           | select(.version | test("^v(22|24|26)\\.")) | "\(.version) \(.date)"'
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

### nvm を使っている場合

```console
$ nvm install --reinstall-packages-from=current 24
$ nvm alias default 24
$ node -v
```

### Homebrew の場合

```console
$ brew update
$ brew info node@24   # 修正版が来ているかを確かめる
$ brew upgrade node@24
```

### Docker の場合

ベースイメージのタグを修正版に上げて、イメージを作り直します。`node:24` のような版を固定しないタグでも、手元に残っている古いイメージが使われることがあるので、`--pull` を付けて作り直してください。

```console
$ docker build --pull -t myapp .
```

### GitHub Actions の場合

`actions/setup-node` に `check-latest: true` を付けると、ランナーにキャッシュされた版が最新かを確かめ、古ければ最新の版をダウンロードします（[setup-node の説明](https://github.com/actions/setup-node/blob/main/docs/advanced-usage.md#check-latest-version)）。既定は `false` で、キャッシュの版が使われます。

```yaml
- uses: actions/setup-node@v7
  with:
    node-version: 24
    check-latest: true
```

## 出典

- Node.js の 11 月のセキュリティリリース: https://nodejs.org/en/blog/vulnerability/november-2026-security-releases
- Node.js のリリース一覧: https://nodejs.org/en/about/previous-releases
