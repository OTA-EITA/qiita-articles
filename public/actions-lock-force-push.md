---
title: actions.lock を試した。タグの force push は防げたが、別リポジトリの再利用ワークフローと --relock は素通りした
tags:
  - GitHubActions
  - Security
  - SRE
  - サプライチェーン攻撃
  - CI
private: false
updated_at: '2026-10-31T18:57:41+09:00'
id: 56e1a736dc61a6863326
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

2026 年 10 月 28 日に GA になった GitHub Actions のロックファイル（`actions.lock`）を、自分で用意したアクションのタグを実際に force push して試しました。

- ロックしたワークフローは、タグを別のコミットに動かされても、**ロックしたコミットのまま動きました**。アクションの中で使っているアクションも同じです。
- タグを、ロックしたコミットから辿れない履歴に付け替えられると、**ワークフローはエラーで止まり**、どちらのコードも動きませんでした。
- 一方で、次の 3 つは素通りしました。
  - **ロックファイルに載っていない新しいワークフロー**は、警告なしで動かされた先のコミットを実行した
  - **別のリポジトリの再利用ワークフロー**（`jobs.<id>.uses`）は、ロック済みのワークフローから呼んでも、動かされた先を実行した
  - **`gh actions-lock --relock`** は「タグが動いた」と警告を出したうえで、動かされた先のコミットにロックを進め、終了コード 0 で終わった

`actions.lock` を入れようとしている人と、入れたあとの更新や CI での確認の手順を決めたい人向けです。試した手順、結果、入れるときにやることをまとめました。

`actions.lock` の紹介と導入手順は [GitHub Actions で checkout@v7 のようなバージョン指定を書くのはやめよう！時代は actions.lock！](https://zenn.dev/progate/articles/24b1140180300c) に分かりやすくまとまっています。この記事は、その先の「実際に攻撃されたときに何が起きるか」を確かめたものです。

## 対象と前提

- `gh actions-lock` 拡張 v0.4.0、ロックファイルの形式 v0.0.3
- 2026 年 10 月 31 日、GitHub.com の Free プラン、`ubuntu-24.04` のランナー
- `gh actions-lock` は手元では動かさず、使い捨てのランナーの上で動かしました
- 試したリポジトリは公開しているので、実行のログもそのまま見られます
  - アクションの側（タグを force push する）: [OTA-EITA/actions-lock-lab-action](https://github.com/OTA-EITA/actions-lock-lab-action)
  - 使う側（ロックファイルを置く）: [OTA-EITA/actions-lock-lab](https://github.com/OTA-EITA/actions-lock-lab)

背景には、2026 年 3 月 19 日に `aquasecurity/trivy-action` の 77 個のバージョンのタグのうち 76 個が、認証情報を盗むコードに force push で書き換えられた事件があります（[GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)）。タグで指定していたワークフローは、約 12 時間、書き換えられたコードを動かしていました。

## 試したこと

アクションの側は、`OUTER_MARKER` を出す composite アクションです。中で同じリポジトリの `inner@v1` を呼び、こちらは `INNER_MARKER` を出します。どのコミットが動いたかは、この 2 つの値で分かります。

```yaml:action.yml
runs:
  using: composite
  steps:
    - shell: bash
      run: echo "OUTER_MARKER=A"
    - uses: OTA-EITA/actions-lock-lab-action/inner@v1
```

使う側は、ただこのアクションを呼ぶだけのワークフローです。

```yaml:.github/workflows/use-action.yml
on: workflow_dispatch
permissions: {}
jobs:
  run:
    runs-on: ubuntu-24.04
    steps:
      - uses: OTA-EITA/actions-lock-lab-action@v1
```

手順は次のとおりです。

1. 版 A（`289fb71`）に `v1` のタグを付ける
2. 使う側で `gh actions-lock` を実行し、できたロックファイルを commit する
3. 版 B（`875663c`、A の上に積んだコミット）を作り、`v1` を force push で B に動かす
4. ワークフローを動かし、どのコミットが動いたかを見る

ロックファイルはこうなりました（一部）。

```yaml:.github/workflows/actions.lock
version: 'v0.0.3'
workflows:
    '.github/workflows/use-action.yml':
        - 'ota-eita/actions-lock-lab-action@v1'
dependencies:
    'ota-eita/actions-lock-lab-action@v1':
        ref: 'v1'
        commit: 'sha1-289fb71b6ad20503e1a75480232a9ea0277cd855'
```

## 結果

| # | 試したこと | 動いたコミット | 結果 |
|---|---|---|---|
| E2 | `v1` を B に動かして、ロック済みのワークフローを実行 | **A** | 守られた。中の `inner@v1` も A |
| E2 | 同じリポジトリの再利用ワークフロー（`./.github/workflows/…`）経由 | **A** | 守られた |
| E9 | `v1` を A から辿れない別の履歴 C に動かして実行 | なし | **エラーで止まった** |
| E3 | ロックファイルにない新しいワークフローで `@v1` を使う | **B** | **素通り。警告もなし** |
| E8 | 別リポジトリの再利用ワークフロー `…/remote.yml@v2` を、`v2` を動かしてから呼ぶ | **B** | **素通り。ロックファイルにも載らない** |
| E4 | ロック済みのワークフローに、ロックしていないアクションを足す | なし | 起動できない（422） |
| E5 | `gh actions-lock --verify` | — | E3 と E4 を検出して終了コード 1。タグが動いたことは報告しない |
| E6 | `gh actions-lock`（通常の再生成） | — | 既存の行は A のまま。タグが動いたことは報告しない |
| E7 | `gh actions-lock --relock` | — | **「タグが動いた」と警告したうえで B に進め、終了コード 0** |

### タグを動かされても、ロックしたコミットが動いた（E2）

`v1` が B を指している状態でロック済みのワークフローを動かすと、ログの最初にこう出て、A がダウンロードされました。

```text
Using locked action versions from the workflow's lockfile
Download action repository 'OTA-EITA/actions-lock-lab-action@v1' (SHA:289fb71b6ad20503e1a75480232a9ea0277cd855)
OUTER_MARKER=A
INNER_MARKER=A
```

中で呼んでいる `inner@v1` は、ロックファイルに別の行として載っていませんが、A のコミットのものが動きました。同じリポジトリの再利用ワークフローを経由しても同じです。

### 辿れない履歴に付け替えられると、止まった（E9）

攻撃者は、元のコミットの上に積むとは限りません。`v1` を A と無関係の履歴 C に付け替えると、ロック済みのワークフローは次のエラーで止まりました。

```text
##[error]Lockfile pin 289fb71b6ad20503e1a75480232a9ea0277cd855 for `ota-eita/actions-lock-lab-action` does not match ref `v1`. Ensure the pinned commit exists on the expected branch or tag.
```

[ドキュメント](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles)には、ロックしたコミットは記録したタグやブランチから辿れる必要があり、辿れなくなったものは実行時に拒否されると書かれています。そのとおりの動きで、攻撃者のコードも元のコードも動かずに止まります。安全側ですが、上流がまっとうな理由で履歴を書き換えたときも、同じように止まります。

### 新しいワークフローは、ロックし直すまで守られない（E3）

ロックファイルを作ったあとに、同じ `@v1` を使うワークフローを 1 本足しました。ロックし直さずに動かすと、警告もなく B が動きました。

```text
Download action repository 'OTA-EITA/actions-lock-lab-action@v1' (SHA:875663c7885e676528d7f888745932fec4d63a0e)
OUTER_MARKER=B
```

ロックファイルは「載っているワークフロー」にだけ効きます。ドキュメントにも、ワークフローは 1 本ずつでもまとめてでも onboard できる、とあります。載っていないワークフローは、これまでどおりタグで解決されます。

### 別リポジトリの再利用ワークフローは、ロックの外（E8）

別リポジトリの再利用ワークフローを `jobs.<id>.uses` で呼ぶワークフローをロックすると、そのワークフローの行は空（`[]`）になり、警告も出ませんでした。`v2` を動かしてから実行すると、動かされた先がそのまま動きました。

```text
Uses: OTA-EITA/actions-lock-lab-action/.github/workflows/remote.yml@refs/tags/v2 (6e74cf98180d2b9bba393e9fc1fb4493c5f9f040)
REMOTE_MARKER=B
```

ドキュメントにも、ロックファイルは再利用ワークフローの呼び出しを固定しないので、フルのコミット SHA で固定する、と書かれています。

### --relock は、動いたタグに警告を出しつつ進める（E7）

ロックを更新するための `--relock` を、`v1` が B に動いた状態で実行しました。

```text
warning ref-moved .github/workflows/use-action.yml ref v1 now resolves to 875663c7885e, lockfile pins 289fb71b6ad2
```

警告は出ますが、ロックファイルの `v1` は B（`875663c`）に書き換わり、終了コードは 0 でした。README には「動いたピンを受け入れる」ための `--accept-moved` というフラグがありますが、付けなくても進みました。

更新を CI で定期的に回していると、タグを書き換えられた直後の `--relock` で、攻撃者のコミットをそのまま取り込むことになります。通常の再生成（E6）と `--verify`（E5）は、タグが動いたことを報告しませんでした。

### ロックしていないアクションを足すと、起動できない（E4）

ロック済みのワークフローに `actions/setup-node@v6` を足して、ロックし直さずに動かそうとすると、起動の時点で弾かれました。

```text
HTTP 422: Invalid Argument - failed to parse workflow: Invalid dependency lockfile ".github/workflows/actions.lock": workflow ".github/workflows/use-action.yml" references actions not present in the lockfile: actions/setup-node@v6
```

ほかのロック済みのワークフローは、この間も普通に動きました。

### そのほかに分かったこと

- `gh actions-lock` は、ロックファイルを作るだけでなく、ワークフローも書き換えます。`actions/checkout@v7` は `@v7.0.1` に、`actions/upload-artifact@v7` は `@v7.0.2` に変わりました。`v1` のように semver でないタグは書き換えず、「完全な semver の参照を使う」よう info で勧めてきます。
- `container:` のイメージ（`alpine:3`）はロックされず、「digest で固定していない」と warning が出ます。

## 入れるときにやること

- **PR で `gh actions-lock --verify` を動かす**。ロックファイルに載っていないワークフロー（E3）と、載っていないアクション（E4）を、マージ前に止められます
- **`--relock` の出力の `ref-moved` を確かめてから commit する**。動いたタグは、上流のリリースノートやタグの履歴で、まっとうな更新か確かめます（E7）
- **別リポジトリの再利用ワークフローはコミット SHA で固定する**。ロックファイルでは守られません（E8）
- **コンテナのイメージは digest で固定する**
- **ワークフローを足したらロックし直す**。`--verify` を CI に入れておけば、忘れても止まります

## 確かめていないこと

- Dependabot がアクションを更新するときに、タグが動いていたらどうなるか。Changelog には、Dependabot がロックファイルの行も同じ PR で作り直すとあります
- Docker のアクション（`docker://` や Dockerfile のアクション）
- プライベートリポジトリのアクションと、GitHub Enterprise Server（`gh actions-lock` は対応していません）
- ブランチ（`@main` など）で指定したアクションのロック

## 参考

- [GitHub Actions workflow lockfiles are generally available（GitHub Changelog, 2026-10-28）](https://github.blog/changelog/2026-10-28-github-actions-workflow-lockfiles-are-generally-available/)
- [Workflow dependency lockfiles（GitHub Docs）](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles)
- [github/gh-actions-lock](https://github.com/github/gh-actions-lock)
- [GHSA-69fq-xp46-6x23: Trivy ecosystem supply chain was briefly compromised](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)
- [GitHub Actions で checkout@v7 のようなバージョン指定を書くのはやめよう！時代は actions.lock！（Zenn）](https://zenn.dev/progate/articles/24b1140180300c)
- [OTA-EITA/actions-lock-lab](https://github.com/OTA-EITA/actions-lock-lab)、[OTA-EITA/actions-lock-lab-action](https://github.com/OTA-EITA/actions-lock-lab-action)
