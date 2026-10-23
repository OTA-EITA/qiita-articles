---
title: npm の「公開から 7 日待つ」設定は lockfile にすでに入った版を止めない ── 検証と CI での塞ぎ方
tags:
  - npm
  - Security
  - Node.js
  - サプライチェーン攻撃
  - GitHubActions
private: true
updated_at: ''
id: null
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

## はじめに

npm のサプライチェーン攻撃への対策として、「公開されたばかりの版は入れない（クールダウン）」が広まっています。npm にも `min-release-age` という設定が入り、pnpm や Yarn にも同じ機能があります。

ただ、実際に試してみると **lockfile にすでに入っている新しい版は、この設定では止まりません**。CI でよく使う `npm ci` も、警告なしでそのまま入れます。

この記事では、その挙動を実際に確かめた結果と、CI で塞ぐ方法をまとめます。

![設定が効く場所・効かない場所](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/npm-cooldown/where.png)

## 結論

- `min-release-age`（や `--before`、Dependabot の `cooldown`）が効くのは、**新しく版を決めるとき**だけ
- lockfile どおりに入れる `npm ci` と、lockfile がある状態の `npm install` には効かない
- 誰かが一度でも新しすぎる版で lockfile を作ってコミットすると、以後の CI はそれをそのまま入れる
- なので、**lockfile 自体を CI で検査して止める**のが確実

## 背景：攻撃は公開から数時間〜数日のうちに起きる

2025 年 9 月には、npm で大きな事件が続けて起きました。

- **chalk / debug の乗っ取り（9 月 8 日）**：メンテナーのアカウントが乗っ取られ、週に何億回もダウンロードされるパッケージに悪意ある版が公開されました。出回っていたのは約 2 時間です。
- **Shai-Hulud（9 月 14〜18 日）**：`postinstall` で開発者の認証情報を盗み、そのトークンで別のパッケージにも自分を仕込む自己増殖型のワームです。500 以上の版が汚染されました。

![悪意ある版が出回った期間と 7 日のクールダウン](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/npm-cooldown/timeline.png)

どちらも、悪意ある版が出回ったのは公開から数時間〜数日の間です。公開から一定期間たった版しか入れなければ、この期間を避けられます。これがクールダウンの考え方です。

## npm の `min-release-age` を試す

npm 11.10.0 から `min-release-age`（単位は日）が使えます。プロジェクトの `.npmrc` に書いておけば、`npm install` のたびに効きます。

```ini:.npmrc
min-release-age=7
```

ちなみに pnpm は `minimumReleaseAge`（単位は分）、Yarn は `npmMinimalAgeGate`（単位は分）と、名前も単位もばらばらなので注意してください。

### 検証した環境

- Node.js 24.22.1 / npm 12.2.1（2026 年 10 月 23 日に実施）
- 依存は `typescript-eslint@^8.70.0` だけのプロジェクト
- この時点で `typescript-eslint` の最新は 8.72.0（公開から 3 日）、その前は 8.71.2

### 検証スクリプト

```bash:run.sh
#!/usr/bin/env bash
set -u
npm_() { npx -y npm@12.2.1 "$@" --ignore-scripts --no-audit --no-fund; }
ver() { node -p "require('$1').packages['node_modules/typescript-eslint'].version"; }

mkdir -p a b
pkg='{"name":"demo","version":"1.0.0","dependencies":{"typescript-eslint":"^8.70.0"}}'
echo "$pkg" > a/package.json; echo "$pkg" > b/package.json

echo "== 1. npm install（クールダウンなし）"
(cd a && npm_ install >/dev/null 2>&1 && echo "locked: $(ver ./package-lock.json)")

echo "== 2. lockfile がない状態で npm install --min-release-age=7"
(cd b && npm_ install --min-release-age=7 >/dev/null 2>&1 && echo "locked: $(ver ./package-lock.json)")

echo "== 3. 1 の lockfile で npm ci --min-release-age=7"
(cd a && rm -rf node_modules && npm_ ci --min-release-age=7 | tail -1 \
  && echo "installed: $(node -p "require('./node_modules/typescript-eslint/package.json').version")")

echo "== 4. 1 の lockfile があるまま npm install --min-release-age=7"
(cd a && npm_ install --min-release-age=7 | tail -1 && echo "locked: $(ver ./package-lock.json)")
```

### 結果

![検証結果](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/npm-cooldown/experiment.png)

| ケース | 入った版 | 判定 |
|---|---|---|
| 1. クールダウンなしで `npm install` | 8.72.0 | （比較用） |
| 2. lockfile なしで `npm install --min-release-age=7` | **8.71.2** | ✅ 公開 7 日以上の版が選ばれる |
| 3. 1 の lockfile で `npm ci --min-release-age=7` | **8.72.0** | ❌ 警告なしで入る |
| 4. 1 の lockfile があるまま `npm install --min-release-age=7` | **8.72.0** | ❌ lockfile はそのまま |

ケース 2 のとおり、版を新しく決めるときはきちんと効きます。一方、ケース 3 と 4 では、lockfile に書かれた公開 3 日の版がそのまま入りました。エラーも警告も出ません。

考えてみれば `npm ci` は「lockfile どおりに入れる」ためのコマンドなので、自然な挙動です。ただ、運用で困るのは次のような場面です。

- `.npmrc` を設定していない人や環境（設定前に作られたブランチ、ローカルのグローバル npm など）で lockfile が更新され、そのままマージされる
- CI では `npm ci` しか実行しないので、どこにも引っかからない

## 対策：CI で lockfile を検査する

lockfile は単なる JSON なので、中の各パッケージの公開日をレジストリに問い合わせれば、新しすぎる版を見つけられます。

これを CI で行うために、[lockfile-guard](https://github.com/OTA-EITA/lockfile-guard) というツールを作りました（自作です）。公開日のチェックのほかに、インストールスクリプトや、レジストリ以外からの取得、integrity の欠落、人気パッケージに似せた名前（タイポスクワット）も見ます。

上のケース 1 の lockfile を検査すると、こうなります。

![lockfile-guard の出力](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/npm-cooldown/guard.png)

`typescript-eslint` 本体だけでなく、一緒に更新された依存先の 12 件も出ています。終了コードが 1 になるので、CI ならここで止まります。

GitHub Actions ではこう書きます。結果は PR のアノテーションと Code scanning（SARIF）に出ます。

```yaml:.github/workflows/ci.yml
jobs:
  lockfile-guard:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v5
        with:
          persist-credentials: false
      - uses: OTA-EITA/lockfile-guard@v0.1.1 # 実運用ではコミット SHA で固定
        id: guard
        with:
          min-age: "7"
          fail-on: medium
      - uses: github/codeql-action/upload-sarif@v4
        if: always()
        with:
          sarif_file: ${{ steps.guard.outputs.sarif-file }}
          category: lockfile-guard
```

もちろん、自作ツールでなくても考え方は同じです。`npm view <パッケージ> time --json` で公開日は取れるので、lockfile の `packages` を回して比べるだけでも作れます。

## 新しく決めるときの対策も並べておく

lockfile の検査は「最後の砦」なので、版を決める時点の対策と組み合わせます。

### 手元：`.npmrc` と `--before`

`.npmrc` に `min-release-age=7` を書いておくのが一番手軽です。npm が古い環境では、日付を指定する `--before` でも同じことができます。

```bash
# 7 日前の時点で公開されていた版だけで lockfile を作り直す
rm -rf node_modules package-lock.json
npm install --before "$(date -v-7d +%Y-%m-%d)"   # macOS の date
```

**lockfile を消してから**実行するのがポイントです。lockfile が残っていると、ケース 4 と同じく古い解決結果がそのまま使われます。

### Dependabot：`cooldown`

Dependabot も公開直後の版を提案しないように設定できます。

```yaml:.github/dependabot.yml
version: 2
updates:
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: weekly
    cooldown:
      default-days: 7
    # メジャー更新は互換性を確かめて手で上げる
    ignore:
      - dependency-name: "*"
        update-types: ["version-update:semver-major"]
```

`cooldown` だけにしたところ、TypeScript 7 や @types/node 26 といったメジャー更新がまとめて提案され、CI が落ちました。メジャーは手で上げる運用にしたほうが扱いやすいです。

### おまけ：インストールスクリプトを動かさない

Shai-Hulud は `postinstall` で動きました。CI では `npm ci --ignore-scripts` にしておくと、万一入ってしまってもインストール時には実行されません。esbuild のようにスクリプトを持つパッケージでも、多くはこれで問題なく動きます。

## 自分のリポジトリで試したら

手元の TypeScript のリポジトリ 3 つで lockfile-guard を動かしたところ、どれも **公開 7 日未満の版が 30〜50 件** 入っていました。依存を足したタイミングで普通に `npm install` していただけです。あわせて、使っていた ESLint 9 が非推奨（サポート終了）になっていることも分かりました。

3 つとも、ESLint 10 に上げたうえで lockfile を作り直し、検出 0 件にしています。

## まとめ

- クールダウン（`min-release-age`、`--before`、Dependabot の `cooldown`）は、版を **新しく決めるとき** の対策
- lockfile にすでに入った版は `npm ci` でも素通りするので、**CI で lockfile を検査して止める**
- CI では `npm ci --ignore-scripts` も併用する

## 参考

- [Widespread npm Supply Chain Attack: Breaking Down Impact & Scope Across Debug, Chalk, and Beyond（Wiz）](https://www.wiz.io/blog/widespread-npm-supply-chain-attack-breaking-down-impact-scope-across-debug-chalk)
- [Shai-Hulud: The novel self-replicating worm infecting hundreds of npm packages（Sysdig）](https://sysdig.com/blog/shai-hulud-the-novel-self-replicating-worm-infecting-hundreds-of-npm-packages)
- [Package managers need to cool down（Andrew Nesbitt）](https://nesbitt.io/2026/03/04/package-managers-need-to-cool-down)
- [lockfile-guard](https://github.com/OTA-EITA/lockfile-guard)
