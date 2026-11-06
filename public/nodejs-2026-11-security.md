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
- サポートが終わった版（20.x 以前）には修正版が出ません。上の系列に移る必要があります
- 【HIGH の件の要約を 1〜2 行】

## 直った脆弱性

| CVE | 深刻度 | 内容 | 対象の系列 |
| --- | --- | --- | --- |
| 【公開後に記入】 | | | |

## 自分の版を確かめる

```console
$ node -v
```

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
$ nvm install 24 --reinstall-packages-from=current
$ nvm alias default 24
$ node -v
```

### Homebrew の場合

```console
$ brew update && brew upgrade node@24
```

### Docker の場合

ベースイメージのタグを修正版に上げて、イメージを作り直します。`node:24` のような版を固定しないタグでも、手元に残っている古いイメージが使われることがあるので、`--pull` を付けて作り直してください。

```console
$ docker build --pull -t myapp .
```

### GitHub Actions の場合

`actions/setup-node` に `check-latest: true` を付けると、キャッシュではなく最新のパッチ版を取りに行きます。

```yaml
- uses: actions/setup-node@v5
  with:
    node-version: 24
    check-latest: true
```

## 出典

- Node.js の 11 月のセキュリティリリース: https://nodejs.org/en/blog/vulnerability/november-2026-security-releases
- Node.js のリリース一覧: https://nodejs.org/en/about/previous-releases
