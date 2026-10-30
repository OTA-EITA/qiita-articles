---
title: >-
  Claude Code で「Yes, and don't ask again」を選んだコマンドのパスワードは設定ファイルに残る。自分のマシンを調べたら 74
  件あった
tags:
  - ClaudeCode
  - Security
  - AIエージェント
  - MCP
  - SRE
private: true
updated_at: '2026-10-30T21:05:21+09:00'
id: 065e4b9c19785fd42d90
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

## きっかけ

Claude Code にデータベースを見てもらっていると、`PGPASSWORD='…' psql -h … -c '…'` のようなコマンドを何度も実行しようとします。毎回確認が出るのが面倒で、つい「Yes, and don't ask again」を選んでいました。

このとき、そのコマンドが許可ルールとして設定ファイルに保存されます。パスワードも含めて、そのままの文字列でです。頭では分かっていたつもりでしたが、実際にどれくらい残っているのかは見たことがありませんでした。

そこで、AI コーディングエージェントの設定ファイルを検査する [agent-config-audit](https://github.com/OTA-EITA/agent-config-audit) という小さなツールを作り（自作です）、2026 年 10 月 25 日に自分の作業用マシンを調べました。平文の秘密情報が 74 件見つかりました。

この記事では、なぜそうなるのかをドキュメントで確認した結果と、見つけたあとに何をしたか、次から入らないようにするために何をしたかを書きます。

## 似た指摘はすでにある

同じ問題は、すでに何度か指摘されています。

- Lakera の [Your AI Coding Assistant Just Shipped Your API Keys](https://web.archive.org/web/20260516182335/https://www.lakera.ai/blog/your-ai-coding-assistant-just-shipped-your-api-keys)（2026 年 4 月 22 日）は、npm に公開されたパッケージを監視して、約 46,500 件のうち 428 件に `.claude/settings.local.json` が入っており、そのうち 30 パッケージの 33 ファイルに認証情報が含まれていたと報告しています。仕組みの説明もこの記事と同じです（元の URL は 2026 年 10 月現在 404 になっているので、アーカイブを載せています）
- GitGuardian の [The State of Secrets Sprawl 2026](https://gitguardian.com/state-of-secrets-sprawl-report-2026) は、MCP の設定ファイルから重複を除いて 24,008 件の秘密情報が見つかり、その 14% が PostgreSQL の接続文字列だったとしています
- Hush Security の調査（[Help Net Security の記事](https://www.helpnetsecurity.com/2026/09/18/hush-security-mcp-credential-exposure-report/)）は、公開 GitHub の MCP 設定ファイル約 82,000 件を調べ、認証情報を書く欄の 12% に値が直接書かれていたこと、7,681 件の履歴を見たところ 243 件で「今のファイルからは消えているが過去のコミットには残っている」状態だったことを報告しています

どれも「公開された場所」を外から数えた調査です。この記事では逆に、ふだん使っている 1 台のマシンの中を見て、どのファイルにどれくらい溜まっていたか、どう片付けたかを書きます。

## 何が起きているのか

### 「Yes, and don't ask again」の保存先

Claude Code のドキュメントには次のように書かれています（[Configure permissions](https://code.claude.com/docs/en/permissions)、2026 年 10 月現在）。

> When you choose "Yes, and don't ask again" and the approval saves permanently, such as for a Bash command or a WebFetch domain, Claude Code saves the rule to `.claude/settings.local.json` at the root of the git repository

Bash コマンドの場合、この許可は「Permanently per repository and command」、つまりリポジトリごと・コマンドごとに無期限で残ります。ファイル編集の許可のようにセッション終了で消えるものとは違います。

```mermaid
flowchart TD
  CMD["Claude が実行したいコマンド<br/>PGPASSWORD='…' psql -h db …"]
  ASK{"許可の確認"}
  ONCE["Yes<br/>この 1 回だけ実行"]
  DONE["ルールとしては残らない"]
  RULE["Yes, and don't ask again"]
  FILE[".claude/settings.local.json の<br/>permissions.allow に<br/>パスワードごと保存"]
  SHARE["dotfiles に入れる<br/>同僚に設定を渡す<br/>settings.json に移して commit<br/>npm パッケージに同梱"]
  LEAK(["パスワードが手元の外に出る"])

  CMD --> ASK
  ASK --> ONCE --> DONE
  ASK --> RULE --> FILE --> SHARE --> LEAK
```

（「Yes」だけを選んだ場合も、会話の記録としてはコマンドが `~/.claude/projects/` に残ります。ただしこちらは既定で 30 日たつと消えます。[`cleanupPeriodDays`](https://code.claude.com/docs/en/settings-reference#cleanupperioddays) を参照してください。許可ルールには期限がありません）

### パスワードがルールに入ってしまう理由

`Bash(psql *)` のように前方一致のルールにしておけば、パスワードは入らないはずです。そうならないのは、許可ルールの照合が先頭の環境変数の代入を飛ばさないからです。ドキュメントにはこうあります。

> Claude Code also strips a leading assignment of certain known-safe environment variables, so `Bash(npm test *)` matches `NODE_ENV=test npm test`. An allow rule won't match past an assignment of any other variable.

`NODE_ENV` のような決まった変数は読み飛ばしてくれますが、`PGPASSWORD` や `DB_PASSWORD` は対象外です。そのため、`PGPASSWORD='…' psql …` を自動で許可するルールは、先頭の `PGPASSWORD='…'` まで含んだ形になります。`curl -H "Authorization: Bearer …"` のようにヘッダーに入っている場合も同じで、コマンドの文字列にトークンが含まれている以上、ルールにも残ります。

偽のパスワードを付けたコマンドを頼んでみると、確認の 2 番目の選択肢にパスワードがそのまま入っていました。

![Claude Code の確認で、2 番目の選択肢にパスワードを含むルールが出ている](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/claude-code-allow-rule-secrets/permission-prompt.png)

### settings.local.json は git に入らない。でも安全とは限らない

このファイルについて、ドキュメント（[Settings files and precedence](https://code.claude.com/docs/en/settings)）はこう説明しています。

> The first time Claude Code writes the file in a git repository that doesn't already ignore it, it adds `**/.claude/settings.local.json` to your global git excludes file, so the file stays out of your commits in every repository.

Claude Code が作ったファイルなら、グローバルの git excludes に入るのでコミットされません。自分で手で作った場合は `.gitignore` に自分で足す必要があります。

ただ、守られるのは「git にコミットされること」だけです。たとえば次のような経路は防げません。

- dotfiles のリポジトリに `.claude` ごとコピーする
- 「その設定ちょうだい」と言われて同僚に送る
- 便利なルールをチームの `.claude/settings.json` に移して commit する
- npm パッケージに `.claude/` ごと入れて公開する（上の Lakera の調査はこれです）
- 画面共有やデモ中にファイルを開く

設定ファイルは `settings.local.json` だけではありません。ドキュメントでは、優先度の高い順に「managed settings、コマンドライン、project local（`.claude/settings.local.json`）、shared project（`.claude/settings.json`）、user（`~/.claude/settings.json`）」とされています。さらに `~/.claude.json` には、アカウント情報や MCP サーバーの設定が入ります。今回、秘密情報はこのうち 4 種類のファイルから見つかりました。

なお、CLI で「don't ask again」を選んだときの保存先は local の 1 ファイルだけですが、ドキュメントによると VS Code 拡張では承認カードから保存先を選べて、チーム共有の `.claude/settings.json` にもできます（[同ページ](https://code.claude.com/docs/en/settings)の「In the VS Code extension the approval card lets you pick the destination file, including the project's shared file」）。

## 自分のマシンで見つかったもの

結果は次のとおりでした（値やプロジェクト名はここには書きません）。

| 場所 | 件数 | 中身 |
| --- | --- | --- |
| あるプロジェクトの `.claude/settings.local.json` | 27 | `DB_PASSWORD` / `PGPASSWORD` / トークンを含むコマンド |
| 別のプロジェクトの `.claude/settings.local.json` | 27 | 同上 |
| `~/.claude/settings.json`（ユーザー設定） | 13 | 同上 |
| 別のプロジェクトの `.claude/settings.local.json` | 3 | GitHub のトークン |
| 別のプロジェクトの `.claude/settings.local.json` | 2 | 秘密情報を含むコマンド |
| `~/.claude.json` | 1 | MCP サーバーの `env` に書いた API キー |
| あるプロジェクトの `.claude/settings.json` | 1 | URL に埋め込まれたパスワード |

合計 74 件、すべて重大度 high です。

ほとんどは、データベースに接続するコマンドを許可したときのものでした。ユーザー設定に 13 件入っていた経緯は追えていません。ユーザー設定はどのプロジェクトで Claude Code を起動しても読み込まれるファイルなので、パスワードの置き場所としてはいちばん範囲が広いところです。

いちばんまずかったのは最後の 1 件です。`.claude/settings.json` は共有するためのファイルなので git で管理されていて、プライベートリポジトリとはいえ push 済みでした。

## 同じことを手元で試す

自分の環境に向けて実行した出力は載せられないので、偽の値を入れたプロジェクトを作って同じツールをかけてみます。

```json:demo-app/.claude/settings.local.json
{
  "permissions": {
    "allow": [
      "Bash(npm test *)",
      "Bash(PGPASSWORD='example-not-real' psql -h localhost -p 5433 -U app -d app_dev -c *)",
      "Bash(DB_PASSWORD=fake-pass-1234 npm run migrate)",
      "Bash(curl -s -H \"Authorization: Bearer fake-token-abcdef123456\" https://api.example.com/v1/me)",
      "Bash(git status *)"
    ]
  }
}
```

ターミナルで見ると、偽の値がルールの中にそのまま入っているのが分かります。

![settings.local.json の許可ルールに偽のパスワードとトークンが入っている](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/claude-code-allow-rule-secrets/settings-local.png)

```json:demo-app/.mcp.json
{
  "mcpServers": {
    "search": {
      "command": "npx",
      "args": ["-y", "example-search-mcp@1.2.3"],
      "env": {
        "SEARCH_API_KEY": "fake-key-0123456789abcdef"
      }
    }
  }
}
```

```console
$ npx github:OTA-EITA/agent-config-audit .
.claude/settings.local.json:5  HIGH   AC001  settings: PGPASSWORD in a command hardcoded in a permission rule (exam…**** (16 chars))
.claude/settings.local.json:6  HIGH   AC001  settings: DB_PASSWORD in a command hardcoded in a permission rule (fake…**** (14 chars))
.mcp.json:7  HIGH   AC001  search: literal value in SEARCH_API_KEY hardcoded in env.SEARCH_API_KEY (fake…**** (25 chars))

2 file(s), 3 finding(s): 3 high, 0 medium, 0 low
```

実際に実行した画面です。終了コードは 1 になります。

![agent-config-audit の出力。値は先頭 4 文字と長さだけが出ている](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/claude-code-allow-rule-secrets/audit-output.png)

値は先頭 4 文字と長さだけを出して、残りは伏せています。ターミナルのログや CI の画面に秘密情報を出し直さないためです。

見てのとおり、`curl` の `Authorization: Bearer fake-token-…` は検出していません。このツールは GitHub や AWS などの決まった形式のトークンや、`PASSWORD=` のような書き方を見ています。形式のないトークンを全部拾おうとすると誤検知だらけになるので、取りこぼしはあります。

ツールを使わなくても、`jq` で怪しいルールの位置だけを出すことはできます。値そのものは表示しないようにしています。

```bash
PAT='(?i)pass(word|wd)?=|token|secret|api_?key|authorization|bearer'
find ~/.claude ~/src -path '*/.claude/settings*.json' -not -path '*/node_modules/*' 2>/dev/null |
while read -r f; do
  jq -r --arg f "$f" --arg re "$PAT" '(.permissions.allow // []) | to_entries[]
    | select(.value | test($re)) | "\($f)\tallow[\(.key)]"' "$f"
done
```

偽のプロジェクトに向けると、`curl` の行も含めて 3 件出ます。

```console
./demo-app/.claude/settings.local.json	allow[1]
./demo-app/.claude/settings.local.json	allow[2]
./demo-app/.claude/settings.local.json	allow[3]
```

`~/src` の部分は、リポジトリを置いているディレクトリに読み替えてください。`~/.claude.json` は `permissions` ではなく `mcpServers` の下に MCP の設定が入るので、これとは別に見る必要があります。

## 見つけたあとにやること

### 1. まずローテーション

平文で置いてあった値は、どこかにコピーされた前提で考えます。ファイルから消すことよりも、発行元でパスワードやトークンを変えることの方が先です。今回見つかったトークン類も、ローテーションが必要なものとして洗い出しました。

特に git で管理していた `.claude/settings.json` の 1 件は、ルールを消しても過去のコミットに残ります。上の Hush Security の調査で 243 件見つかっていたのも、まさにこの状態です。履歴を書き換えるより、パスワードを変えてしまう方が確実です。

### 2. 秘密情報を含むルールを消す

自分の環境では、6 つの設定ファイルから合計 73 件のルールを、バックアップを取ってから削除しました。件数が多いと手作業では漏れるので、`jq` を使うと楽です。

```bash
PAT='(?i)pass(word|wd)?=|token|secret|api_?key|authorization|bearer'
f=.claude/settings.local.json
cp -p "$f" "$f.bak"
jq --arg re "$PAT" '.permissions.allow |= map(select(test($re) | not))' "$f.bak" > "$f"
```

偽のプロジェクトで試すと、`npm test` と `git status` の 2 件だけが残り、`settings.local.json` についてのツールの検出も 0 件になりました（`.mcp.json` の 1 件はこの手順では消えないので残ります）。バックアップにはもちろん元の値が残っているので、動作を確認したら消します。

`~/.claude.json` の MCP の API キーは、今も使っているサーバーのものなので、その場では消していません。ローテーションと、次の項目のように環境変数を参照する形への切り替えが残っています。

### 3. 秘密情報をコマンドの外に出す

ルールを消しただけだと、次に Claude が同じコマンドを実行しようとしたとき、また同じ確認が出ます。そこで「Yes, and don't ask again」を選べば元に戻ります。コマンドの文字列にパスワードが入らないようにするのが本当の対策です。

PostgreSQL なら `~/.pgpass` が使えます。PostgreSQL のドキュメントでは、`PGPASSWORD` を使うこと自体が勧められていません（[Environment Variables](https://www.postgresql.org/docs/current/libpq-envars.html)）。

> Use of this environment variable is not recommended for security reasons, as some operating systems allow non-root users to see process environment variables via ps; instead consider using a password file

```text:~/.pgpass
# hostname:port:database:username:password
localhost:5433:app_dev:app:（パスワード）
```

Unix ではグループや他人が読める権限だとファイルが無視されるので、`chmod 0600 ~/.pgpass` にしておきます（[The Password File](https://www.postgresql.org/docs/current/libpq-pgpass.html)）。これでコマンドは `psql -h localhost -p 5433 -U app -d app_dev -c …` になり、許可ルールも `Bash(psql -h localhost -p 5433 *)` のようにパスワードを含まない形で書けます。

GitHub のトークンを `curl` のヘッダーに入れているなら、`gh auth login` でログインして `gh api` を使う形にできます。`gh` はトークンを OS の認証情報ストアに保存します（`gh auth login --help` に「stored securely in the system credential store」とあります。ストアが使えない環境ではファイルに平文で書くので、`gh auth status` で保存先を確認してください）。

MCP サーバーの設定は、値を直接書かずに環境変数を参照します。Claude Code の `.mcp.json` は `${VAR}` と `${VAR:-default}` の展開に対応していて、`command`・`args`・`env`・`url`・`headers` で使えます（[Connect Claude Code to tools via MCP](https://code.claude.com/docs/en/mcp)、2026 年 10 月現在）。

```json:.mcp.json
{
  "mcpServers": {
    "search": {
      "command": "npx",
      "args": ["-y", "example-search-mcp@1.2.3"],
      "env": {
        "SEARCH_API_KEY": "${SEARCH_API_KEY}"
      }
    }
  }
}
```

ひとつ注意があります。リモートの MCP サーバーの `url` と `headers` では、`ANTHROPIC_API_KEY`・`AWS_BEARER_TOKEN_BEDROCK`・`NPM_TOKEN` など一部の変数は、設定していても空として扱われます。リポジトリの `.mcp.json` が、Claude Code やクラウドの認証情報を外部のサーバーに送れないようにするためです。そうした値を渡したい場合は、自分で付けた別の名前の変数にコピーしてから参照するように、とドキュメントに書かれています。

## 次から入らないようにすること

- 「don't ask again」を選ぶ前に、コマンドに秘密情報が入っていないか見る。入っていたら「Yes」で 1 回だけ通して、あとで上の形に直します
- dotfiles や設定を人に渡す前に検査する。`npx github:OTA-EITA/agent-config-audit --home` で、`~/.claude/settings.json` や `~/.claude.json` も含めて見られます
- npm に公開するパッケージでは `npm pack --dry-run` で中身を確認する。`.npmignore` に `.claude/` を入れておくと安心です（Lakera の記事の対策と同じです）
- 共有する設定ファイルは CI で検査する

CI では、リポジトリにコミットされる `.claude/settings.json` や `.mcp.json` を見ます。GitHub Actions なら次のように書けます。

```yaml:.github/workflows/agent-config-audit.yml
name: agent-config-audit
on: [push, pull_request]
permissions:
  contents: read
jobs:
  audit:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v5
        with:
          persist-credentials: false
      - uses: OTA-EITA/agent-config-audit@6052e0bed5ca0f3f950c6a68e68443472a613d94 # v0.1.0
        id: audit
      - uses: github/codeql-action/upload-sarif@v4
        if: always()
        with:
          sarif_file: ${{ steps.audit.outputs.sarif-file }}
          category: agent-config-audit
```

検出結果は SARIF で GitHub の Code scanning に送ります。SARIF にも値は伏せた形でしか出ません。

ただし CI で見られるのは、コミットされたファイルだけです。`settings.local.json` やユーザー設定は CI からは見えないので、手元で定期的に実行するしかありません。

## おわりに

「Yes, and don't ask again」は、その場の 1 回の判断を、期限のないルールに変える操作です。コマンドの中身がそのまま保存されることを分かっていても、確認の画面でそこまで意識するのは難しいと感じました。

Claude Code に限らず、エージェントの設定ファイルは「設定」というより、実行したコマンドの記録に近いものになっています。`.env` と同じくらいの扱いで、たまに中を見ておくのがよさそうです。

## 参考

- [Configure permissions（Claude Code Docs）](https://code.claude.com/docs/en/permissions)
- [Settings files and precedence（Claude Code Docs）](https://code.claude.com/docs/en/settings)
- [Connect Claude Code to tools via MCP（Claude Code Docs）](https://code.claude.com/docs/en/mcp)
- [Your AI Coding Assistant Just Shipped Your API Keys（Lakera、アーカイブ）](https://web.archive.org/web/20260516182335/https://www.lakera.ai/blog/your-ai-coding-assistant-just-shipped-your-api-keys)
- [The State of Secrets Sprawl 2026（GitGuardian）](https://gitguardian.com/state-of-secrets-sprawl-report-2026)
- [Hardcoded MCP credentials found in public GitHub files（Help Net Security）](https://www.helpnetsecurity.com/2026/09/18/hush-security-mcp-credential-exposure-report/)
- [PostgreSQL: Environment Variables](https://www.postgresql.org/docs/current/libpq-envars.html) / [The Password File](https://www.postgresql.org/docs/current/libpq-pgpass.html)
- [agent-config-audit](https://github.com/OTA-EITA/agent-config-audit)（筆者が作ったツールです）
