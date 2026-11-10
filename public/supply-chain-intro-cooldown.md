---
title: サプライチェーン攻撃をちゃんと理解したい人のための入門：「公開から7日待つ」設定は銀の弾丸ではない
tags:
  - Security
  - サプライチェーン攻撃
  - npm
  - GitHubActions
  - 初心者
private: true
updated_at: '2026-11-10T13:50:30+09:00'
id: 59fb9e0eb24eb3554be2
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

10 月に自分のリポジトリを見直したら、公開されてから 1 週間たっていない依存が 30〜50 個ずつ入っていました。そこで「公開されたばかりの版は入れない」設定を入れ、ついでに本当に止まるのかを npm・pnpm・Yarn・Bundler・GitHub Actions で試しました。結果は、止まる場面より止まらない場面のほうが多いくらいでした。

この記事は、その検証の前提になる「サプライチェーン攻撃とは何か」「なぜ 7 日待つと効くのか」「それでも防げないのはどこか」を、入門向けに 1 本にまとめ直したものです。細かい検証の手順はそれぞれの記事に書いたので、ここでは結果だけを使います。

## この記事で触れること

- サプライチェーン攻撃の仕組みと、実際に起きた 3 件
- なぜ「自分は有名なパッケージしか使っていない」では防げないのか
- 公開から N 日待つ設定（クールダウン）、lockfile、Actions の固定のそれぞれが何を防ぐか
- それぞれの対策が、実際に試すとどこで素通りしたか

## この記事で触れないこと

- 署名や SBOM、SLSA などの仕組みそのもの
- 社内レジストリやプロキシの運用
- タイポスクワッティング（名前の似た偽パッケージ）への対策
- 攻撃に使われたマルウェアの解析

## サプライチェーン攻撃とは

自分のコードではなく、自分のコードが取り込んでいる部品（ライブラリ、ビルドの道具、CI のアクション）に悪いコードを混ぜる攻撃です。

アプリを書く人が攻撃者の手元のコードを直接動かすことはまずありません。ですが `npm install` や CI のワークフローは、毎日のように他人が公開したコードを取ってきて、こちらの権限で実行しています。攻撃者はそこを狙います。

## 実際に起きた 3 件

### chalk と debug の乗っ取り（2025 年 9 月 8 日）

広く使われている `chalk` や `debug` などのメンテナーが、ソーシャルエンジニアリングで npm のアカウントを乗っ取られました。攻撃者はそのアカウントで、悪いコードを入れた新しい版を公開しました。Wiz によると、悪い版がダウンロードできたのは約 2 時間です。

### Shai-Hulud（2025 年 9 月）

インストール時に動いて開発者の認証情報（GitHub のトークンやクラウドの API キー）を盗み、盗んだ npm のトークンで別のパッケージにも自分を仕込んで公開する、自己増殖型のワームです。CISA の勧告では、500 以上のパッケージが汚染され、2025 年 9 月 16 日より前の安全な版に固定するよう求めています。

### trivy-action のタグ書き換え（2026 年 3 月 19 日）

脆弱性スキャナー Trivy の GitHub Actions、`aquasecurity/trivy-action` で、77 個あるバージョンのタグのうち 76 個が force push で書き換えられ、認証情報を盗むコードを指すようにされました。Trivy のアドバイザリによると、書き換えられた状態は約 12 時間続きました。`uses: aquasecurity/trivy-action@v0.xx` のようにタグで指定していたワークフローは、その間、何も変えていないのに攻撃者のコードを動かしていました。

## でも有名で信頼できるパッケージしか使っていないのでは？

3 件とも、使われたのは偽物ではなく本物のパッケージ、本物のアクションです。正規のアカウントから、正規の名前で、新しい版として出てきます。名前やスター数を見て選んでいても防げません。

## なぜ新しい版が勝手に入ってくるのか

ふだん書いている指定が、そういう作りになっているからです。

```json:package.json
"dependencies": {
  "debug": "^4.4.0"
}
```

`^4.4.0` は「4.x の中で一番新しいもの」という意味です。lockfile がない状態で `npm install` すると、その瞬間の最新版が選ばれます。直接の依存だけでなく、依存の依存も同じように解決されます。

GitHub Actions のタグも同じです。`@v1` のようなタグはあとから別のコミットに付け替えられるので、昨日と同じワークフローでも今日は違うコードが動くことがあります。

これはバグではなく、バグ修正やセキュリティ修正を自動で受け取れるようにするための仕組みです。便利さの裏返しで、上流で悪い版が出れば、それも自動で受け取ってしまいます。

## 対策 1：公開から N 日待つ（クールダウン）

3 件とも、悪い版が出回っていたのは数時間〜半日です。William Woodruff さんの分析では、調べた 10 件のサプライチェーン攻撃のうち 8 件で、悪い版を使えた期間が 1 週間未満でした（Andrew Nesbitt さんの記事で紹介されています）。

それなら、公開されてから数日たっていない版は選ばないようにすれば、多くの攻撃は見つかって消されたあとになります。これがクールダウンです。主なパッケージマネージャーには同じような設定があります。

| 道具 | 設定 | 例 |
|---|---|---|
| npm | `min-release-age` | `.npmrc` に `min-release-age=7`（日） |
| pnpm | `minimumReleaseAge` | `pnpm-workspace.yaml` に `minimumReleaseAge: 10080`（分）。pnpm 11 は設定しなくても 1 日待つ |
| Yarn | `npmMinimalAgeGate` | `.yarnrc.yml` に `npmMinimalAgeGate: 7d` |
| Bundler | `cooldown` | Gemfile の `source "https://rubygems.org", cooldown: 7`（日）。Bundler 4.0.13 から |
| Dependabot | `cooldown` | `dependabot.yml` に `cooldown: default-days: 7` |

## 対策 2：lockfile をコミットして、CI は lockfile どおりに入れる

lockfile（`package-lock.json`、`pnpm-lock.yaml`、`yarn.lock`、`Gemfile.lock`）には、依存の依存まで含めて「どの版を入れたか」が書かれます。これをコミットしておき、CI では `npm ci` のように lockfile どおりに入れるコマンドを使えば、CI が勝手に新しい版を取りに行くことはなくなります。

## 対策 3：Actions はタグではなくコミットで固定する

タグは付け替えられますが、コミットの SHA は変えられません。`uses:` をコミットの SHA で書くか、2026 年 10 月 28 日に GA になった `actions.lock`（ワークフローのロックファイル）を使えば、タグを書き換えられても前のコミットのまま動きます。

## ただし、どれも銀の弾丸ではない

ここからが実際に試した結果です。どの対策も、ある場面ではきちんと効きましたが、別の場面では何も言わずに素通りしました。

### lockfile に入ってしまった版は、クールダウンでは止まらない

クールダウンは「これから版を選ぶとき」の設定です。すでに lockfile に書かれている版には、ほとんどの道具で効きません。公開から 7 日待つ設定を入れたうえで、公開 3 日の版が入った lockfile を CI と同じコマンドで入れたところ、こうなりました。

| 道具 | lockfile なしで解決 | lockfile どおりに入れる |
|---|---|---|
| npm 12.2.1 | 古い版を選ぶ | 止まらない（`npm ci` が新しすぎる版を入れる） |
| pnpm 11.28.6 | 古い版を選ぶ | 止まる（`pnpm install --frozen-lockfile` が失敗する） |
| Yarn 4.18.1 | 古い版を選ぶ | 止まらない（`yarn install --immutable` が入れる） |
| Bundler 4.0.23 | 古い版を選ぶ | 止まらない（`bundle install` が入れ、`bundle update --all` でも残る） |

lockfile は、誰かが手元で一度 `npm install` したときの結果です。その人の環境にクールダウンの設定がなかった、あるいは Dependabot 以外の経路で更新された、というだけで新しすぎる版が lockfile に入り、そのまま CI を通ります。対策 1 と対策 2 は、組み合わせると穴が開くことがあるわけです。

pnpm 以外を使っているなら、lockfile に書かれた版の公開日を CI で確かめる仕組みを別に置くしかありません。やることは、lockfile の版ごとにレジストリの公開日を取って比べるだけです。

```bash
npm view typescript-eslint time --json | grep '"8.72.0"'
#   "8.72.0": "2026-10-19T17:08:09.147Z",
```

自分はこれを CI で回すために [lockfile-guard](https://github.com/OTA-EITA/lockfile-guard) という小さな道具を作って使っていますが、道具は何でもかまいません。

### actions.lock でも素通りする経路がある

`actions.lock` を入れたリポジトリで、自分で用意したアクションのタグを実際に force push してみました。ロックしたワークフローは、タグを動かされてもロックしたコミットのまま動きました。ここは期待どおりです。

一方で、次の 3 つは素通りしました。

- ロックファイルに載っていない新しいワークフローは、警告なしで書き換えられた先のコミットを動かした
- 別のリポジトリの再利用ワークフロー（`jobs.<id>.uses`）は、ロック済みのワークフローから呼んでも、書き換えられた先を動かした
- `gh actions-lock --relock` は「タグが動いた」と警告を出したうえで、書き換えられた先にロックを進め、成功として終わった

最後の 1 つは、更新のたびに機械的に `--relock` していると、攻撃されたタグをそのまま受け入れてしまうということです。

### CI が裏で入れている道具は、アプリの lockfile の外にある

アプリの依存をいくら固めても、CI のステップの中で `npm install -g` している道具は lockfile の外です。この記事を投稿している Qiita CLI の公式アクションも、2026 年 10 月に確認した時点では、CLI を `npm install -g` で入れていました。`-g` のインストールは lockfile を使わないので、CLI の依存は実行のたびにその時点の最新で解決されます。そこで入れた CLI に、次のステップで投稿用のトークンを渡して動かしていました。

自分の運用では、CLI を記事リポジトリの `package.json` と lockfile で固定し、`npm ci --ignore-scripts` で入れるワークフローを自分で書くことにしました。

### 7 日を超えて潜む攻撃は止まらない

8 件が 1 週間未満ということは、残りの 2 件は 1 週間を超えていたということです。気づかれないように長く潜むことを狙った攻撃には、待つ日数をどれだけ延ばしても限界があります。逆に、待つ日数を延ばすほど、本物のセキュリティ修正を受け取るのも遅れます。

## 結局どうすればいいか

1 つの対策で全部を防ごうとせず、それぞれが何を防いで、何を防がないかを知ったうえで重ねるのが現実的だと思います。

| 対策 | 防げるもの | 防げないもの |
|---|---|---|
| クールダウン | 新しく版を選ぶときに、出たばかりの悪い版を選ぶこと | lockfile にすでに入った版（pnpm 以外）、長く潜む攻撃 |
| lockfile と `npm ci` | CI が勝手に新しい版を取りに行くこと | lockfile を更新したときに入った悪い版、`-g` で入れる道具 |
| Actions の SHA 固定・`actions.lock` | タグの書き換え | ロックしていないワークフロー、別リポジトリの再利用ワークフロー、考えずに `--relock` すること |
| lockfile の公開日の検査（CI） | 設定のない環境で lockfile に入った新しすぎる版 | 公開から日数がたってから見つかる攻撃 |

自分のリポジトリでは、次のようにしています。

- パッケージマネージャーと Dependabot の両方にクールダウンを入れる
- lockfile をコミットし、CI は lockfile どおりに、インストールスクリプトを止めて入れる（`npm ci --ignore-scripts`）
- CI で lockfile の版の公開日を検査し、7 日未満のものがあれば止める
- Actions は SHA で固定し、ロックの更新は差分を人が見てから入れる
- CI のステップで入れる道具も、lockfile で固定する

便利さとのバランスは、プロジェクトごとに違うと思います。ただ、どの対策をどこまで入れるにしても、「入れたから大丈夫」ではなく「どこが素通りするか」を一度確かめておくと安心です。

## それぞれの検証の詳細

- [「公開から7日待つ」設定、lockfile に入った新しすぎる版は止まるのか npm・pnpm・Yarn で試した](https://qiita.com/Nekorock/items/d25fc8cb764c0e9325bc)
- [Bundler の cooldown は Gemfile.lock にある版には効かない](https://qiita.com/Nekorock/items/07b0d2ee27ddb1138d1d)
- [actions.lock を試した。タグの force push は防げたが、別リポジトリの再利用ワークフローと --relock は素通りした](https://qiita.com/Nekorock/items/56e1a736dc61a6863326)

## 参考

- [Widespread npm Supply Chain Attack（Wiz）](https://www.wiz.io/blog/widespread-npm-supply-chain-attack-breaking-down-impact-scope-across-debug-chalk)
- [Widespread Supply Chain Compromise Impacting npm Ecosystem（CISA, 2025-09-23）](https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem)
- [GHSA-69fq-xp46-6x23: Trivy ecosystem supply chain temporarily compromised](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)
- [Package managers need to cool down（Andrew Nesbitt）](https://nesbitt.io/2026/03/04/package-managers-need-to-cool-down)
- [GitHub Actions workflow lockfiles are generally available（GitHub Changelog, 2026-10-28）](https://github.blog/changelog/2026-10-28-github-actions-workflow-lockfiles-are-generally-available/)
- [サプライチェーン攻撃の40年 AI時代の依存を守る入門ガイド（Qiita）](https://qiita.com/kai_kou/items/debd8b05019aa41920f9)：攻撃の歴史を広く知りたい人向け
