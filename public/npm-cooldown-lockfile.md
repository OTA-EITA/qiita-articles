---
title: 「公開から7日待つ」設定、lockfile に入った新しすぎる版は止まるのか npm・pnpm・Yarn で試した
tags:
  - npm
  - pnpm
  - YARN
  - Security
  - サプライチェーン攻撃
private: false
updated_at: '2026-10-23T19:47:38+09:00'
id: d25fc8cb764c0e9325bc
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

## きっかけ

先日、自分の TypeScript のリポジトリをいくつか見直したら、公開されてから 1 週間たっていない依存が 30〜50 個ずつ入っていました。依存を足したタイミングで普通に `npm install` していただけなので、そうなるのは当たり前なのですが、去年の chalk / debug の乗っ取りや Shai-Hulud のことを考えると少し怖い状態です。

対策としてよく紹介されているのが「公開されたばかりの版は入れない」設定（クールダウン）です。npm・pnpm・Yarn のどれにも同じような設定があります。

ただ、npm の `min-release-age` は **lockfile がすでにあると効かない**ことが、すでに何人かの方に指摘されています（記事の最後に載せています）。では pnpm と Yarn はどうなのか。自分が探した範囲では、実際に動かして比べた記事が見つからなかったので、同じ条件で 3 つとも試してみました。

## 試した結果

![3つのパッケージマネージャーの結果](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/npm-cooldown/cmp.png)

新しく版を決めるときは 3 つとも設定どおり動きました。違いが出たのは lockfile どおりに入れるときで、止めてくれたのは pnpm だけでした。npm と Yarn は、lockfile に書いてある公開 3 日の版をエラーも警告もなく入れます。

## 試した条件

- 2026 年 10 月 23 日、macOS、Node.js 24.22.1
- 依存は `typescript-eslint@^8.70.0` だけのプロジェクト
- この時点で `typescript-eslint` の最新は 8.72.0（10 月 19 日公開）、その前が 8.71.2（10 月 12 日公開）

手順はどれも同じです。

1. クールダウンなしで `install` して、8.72.0 入りの lockfile を作る
2. 「公開から 7 日待つ」設定を入れる
3. `node_modules` を消して、CI と同じコマンド（`npm ci` / `pnpm install --frozen-lockfile` / `yarn install --immutable`）で入れ直す

あわせて、lockfile がない状態からの解決も試しています。

設定の書き方は、名前も単位もばらばらなので注意が必要です。npm は日、pnpm と Yarn は分で指定します（Yarn は `7d` のような書き方もできます）。

```ini:.npmrc
min-release-age=7
```

```yaml:pnpm-workspace.yaml
minimumReleaseAge: 10080
```

```yaml:.yarnrc.yml
npmMinimalAgeGate: 7d
```

npm は 11.10.0 から、pnpm は 10.16.0 から使えます。npm 11.9.0 で `npm config ls -l` を見ると、`min-release-age` 自体が出てきませんでした。

## 実際の出力

![CI と同じコマンドを実行した結果](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/npm-cooldown/ci-run.png)

pnpm だけが、lockfile の 95 件を公開日と照らし合わせて、引っかかった 13 件を全部出して失敗しました。エラーメッセージには「lockfile が古いか、誰かがポリシーを回避して作った lockfile をコミットした可能性がある。pnpm-lock.yaml の最近の変更を確認すること」という趣旨の説明まで付いています。

pnpm のドキュメントを見ると、`pnpm install` は読み込んだ lockfile の全エントリに `minimumReleaseAge` をかけ直すと書かれています。これを省略する `trustLockfile` という設定があり、既定は `false` です。外部の人が lockfile を編集できるなら `false` のままにしておくように、とも書かれていました。

### pnpm で少し気になったところ

失敗したあとに `node_modules` を見ると、8.72.0 はすでに配置されていました。チェックはパッケージの配置と並行して走っていて、最後に失敗する作りのようです。

そこで、`postinstall` を持つ esbuild で同じことを試しました。チェックに通る場合は `esbuild postinstall$ node install.js` が実行されますが、チェックに引っかかる場合は、配置はされても `postinstall` は実行されずに終わりました。Shai-Hulud のような `postinstall` で動くタイプは、ここで止まることになります。

それでも、ファイル自体は置かれます。後続のステップで実行されないよう、CI の該当ジョブはこの時点で落とす（終了コードを無視しない）のが前提です。

## npm と Yarn をどう補うか

npm と Yarn を使っている場合は、lockfile を自分で検査するしかありません。とはいえ、やることは単純です。lockfile に並んでいるパッケージの公開日をレジストリから取って比べるだけです。

```bash
npm view typescript-eslint time --json | grep '"8.72.0"'
#   "8.72.0": "2026-10-19T17:08:09.147Z",
```

（pnpm のエラーに出ていた時刻とは 1 分ほどずれていましたが、7 日の判定には影響しません）

自分は、これを CI で回すために [lockfile-guard](https://github.com/OTA-EITA/lockfile-guard) という小さなツールを作って使っています。上の npm の lockfile を検査すると、pnpm と同じ 13 件が出ました。

![lockfile-guard で同じ lockfile を検査した結果](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/npm-cooldown/guard.png)

GitHub Actions では、`npm ci` より前のジョブに置いています。

```yaml:.github/workflows/ci.yml
  lockfile-guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          persist-credentials: false
      - uses: OTA-EITA/lockfile-guard@v0.1.1 # 実際はコミット SHA で固定しています
        with:
          min-age: "7"
          fail-on: medium
```

ツールは何でもよくて、大事なのは「lockfile がコミットされた時点の版を CI で見る」ことです。手元の `.npmrc` や Dependabot の設定がどれだけ正しくても、設定の入っていない環境で一度でも lockfile が更新されると、その版がそのまま CI を通ります。

## そもそも何日待てばいいのか

参考までに、去年の 2 件を並べるとこうなります。

![悪意ある版が出回った期間と7日のクールダウン](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/npm-cooldown/attack-window.png)

- chalk / debug の乗っ取り（2025 年 9 月 8 日）：悪意ある版がダウンロードできたのは 13:16〜15:15 UTC 頃の約 2 時間
- Shai-Hulud（2025 年 9 月中旬）：`postinstall` で認証情報を盗み、盗んだトークンで別のパッケージにも自分を仕込むワーム。CISA によると 500 以上のパッケージが汚染され、9 月 16 日より前の版に固定するよう勧告が出ました

Andrew Nesbitt さんの記事では、調べられた 10 件のサプライチェーン攻撃のうち 8 件で、悪意ある版が使えた期間が 1 週間未満だったと紹介されています。7 日という数字は、このあたりが根拠になっています。pnpm 11 は何も設定しなくても 1 日（1440 分）待つようになっています。

## 自分のリポジトリでやったこと

最初に書いた 3 つのリポジトリは npm なので、次のようにしました。

- lockfile を消して、`npm install --before <7日前の日付>` で作り直す（lockfile を残したままだと、上の npm の結果と同じで古い解決がそのまま使われます）
- CI に lockfile の検査を足す
- Dependabot に `cooldown: default-days: 7` を設定する
- CI のインストールは `npm ci --ignore-scripts` にする

作り直しの途中で、使っていた ESLint 9 が非推奨になっていることにも気づいたので、ついでに 10 に上げました。

## CI が入れる道具も見落としていた（2026 年 10 月現在）

この記事を Qiita に自動で投稿する仕組みを作っているときにも、同じ種類の穴に気づきました。

Qiita CLI の公式手順どおり `npx qiita init` を実行すると、投稿用の GitHub Actions のワークフローが作られます。そこで使われている `increments/qiita-cli/actions/publish@v1` の中身を読むと、2026 年 10 月現在、次のように CLI を入れていました。

```yaml
- name: Install qiita-cli
  run: npm install -g @qiita/qiita-cli@v1.12.0
```

気になった点は 3 つです。

- 1.12.0 は 10 月 21 日に公開されたばかりで、確認した時点で公開から 2 日でした
- `npm install -g` は lockfile を使いません。Qiita CLI はパッケージに `npm-shrinkwrap.json` も含めていないので、依存（`chalk ^5.6.2`、`debug ^4.4.0` など）は実行のたびにその時点の版で解決されます。`debug ^4.4.0` は、去年乗っ取られた `debug@4.4.2` を含む範囲です（4.4.2 自体は今は削除されています）
- インストールスクリプトも止めていません

アプリの依存をいくら固めても、このステップはその外側で動きます。しかも、ここで入れた CLI は次のステップで Qiita のトークンを渡されて実行されます。

公式アクションが悪いというより、常に最新を入れる便利さとのトレードオフだと思います。ただ、自分の運用には合わないので、CLI を記事リポジトリの `package.json` と lockfile で 1.10.0（公開から 7 日以上たった版）に固定しました。そのうえで、`npm ci --ignore-scripts` で入れて投稿する同じ処理を、[自分でワークフローに書きました](https://github.com/OTA-EITA/qiita-articles/blob/main/.github/workflows/publish.yml)。

守る対象は、アプリの依存だけではありません。パイプラインが裏で入れている道具も含めて考える必要がある、というのが今回いちばんの学びでした。

## おわりに

npm も `min-release-age` で lockfile を見てくれればいいのに、とは思います。ただ、`npm ci` が「lockfile どおりに入れる」コマンドである以上、今の挙動も筋は通っています。

pnpm を使っているなら、設定を入れるだけで CI まで守られます。npm と Yarn の場合は、設定とは別に CI で lockfile を見る仕組みを用意しておくのがよさそうです。

## 参考

- [Minimum Release Age: npm, pnpm, Yarn, Bun and Deno Settings](https://www.devanshuverma.in/blog/minimum-release-age-package-managers-complete-guide)：各パッケージマネージャーの設定の一覧と、npm ci が lockfile の版をそのまま入れることの指摘
- [2026年春のOSS事故から学ぶ npm・pnpm・GitHub Actionsのサプライチェーン防御](https://zenn.dev/trknhr/articles/989086c7b8ecf0)
- [Package managers need to cool down（Andrew Nesbitt）](https://nesbitt.io/2026/03/04/package-managers-need-to-cool-down)
- [pnpm: Dependency resolution settings（minimumReleaseAge / trustLockfile）](https://pnpm.io/settings/dependency-resolution)
- [Widespread npm Supply Chain Attack（Wiz）](https://www.wiz.io/blog/widespread-npm-supply-chain-attack-breaking-down-impact-scope-across-debug-chalk)
- [Widespread Supply Chain Compromise Impacting npm Ecosystem（CISA）](https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem)
