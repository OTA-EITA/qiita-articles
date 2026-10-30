---
title: Claude Code の agent teams を tmux で分割表示してレビューさせたら、「読むだけ」の指示は守られなかった
tags:
  - tmux
  - ClaudeCode
  - AIエージェント
  - SRE
  - Security
private: false
updated_at: '2026-10-26T09:53:17+09:00'
id: 29d59923e2c52364c878
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

Claude Code の実験的な機能 agent teams を tmux の分割表示で動かし、自分のリポジトリを 3 人のチームメイトにレビューさせました。どれも 1 回ずつ試しただけの結果ですが、分かったことは次の 3 つです。

- 「読むだけ、コマンドは実行しない」とプロンプトで頼んでも、2 人が Bash を実行した。macOS では検索が Bash 経由になることと、チームメイトがリーダーの権限モードを引き継ぐことが理由
- シェルで export した環境変数のうち、`DISABLE_AUTOUPDATER` は分割表示のチームメイトに届かなかった
- リーダーで `/exit` してチームメイトを止めると、ペインもプロセスも残らなかった

インフラや SRE のリポジトリ、つまり認証情報やデプロイの仕組みが近くにあるリポジトリで agent teams を使おうとしている人に向けて書いています。設定の手順は分かりやすい記事がすでにあるので（最後に載せています）、ここでは実際に起きたことを書きます。

![agent teams を tmux で動かしている様子](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/claude-agent-teams-tmux/mid.png)

左がリーダー、右の 3 つがチームメイトです。どれも別々の Claude Code のプロセスとして動いています。

## 試した環境

- 2026 年 10 月 24 日、macOS、tmux 3.8
- Claude Code 2.1.287、モデルは Sonnet 5.5
- レビュー対象は、自分で作った Alertmanager の通知を Slack に振り分ける小さなサービス（TypeScript）
- どの結果も 1 回ずつ試したものです。同じ頼み方でも、毎回同じように動くとは限りません

agent teams は既定では無効です。環境変数で有効にして、tmux のセッションの中で `--teammate-mode tmux` を付けて起動しました。

```bash
tmux new -s team
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
claude --teammate-mode tmux
```

`--teammate-mode` は `claude --help` には出てこない実験的なフラグです。常に使うなら `~/.claude/settings.json` の `teammateMode` に書けます。なお、VS Code の統合ターミナルでは分割表示は使えないとドキュメントにあります。自分は普段 VS Code の拡張から Claude Code を使っているので、VS Code の外に tmux のセッションを作って試しました。

## 1 回目は、チームではなくサブエージェントで動いた

最初はこう頼みました。

> エージェントチームを作って、このリポジトリ（alert-router）を3人でレビューしてください。1人目はセキュリティ（入力の検証、Slack へのメッセージ注入、秘密情報の扱い）、2人目はテストの抜け、3人目は README と実装の食い違いを担当。ファイルは読むだけにして、編集やコマンドの実行はしないでください。最後に指摘を重要度順にまとめてください。

画面は分割されず、普通のサブエージェントが 3 つバックグラウンドで動いただけでした。セッションの記録を見ると、名前を付けずに `Agent` ツールを 3 回呼んでいます。ドキュメントによると、チームメイトとして起動するのは、agent teams が有効な状態で Claude が名前付きで `Agent` ツールを呼んだときです。

これはドキュメントにも「Claude がチームを作らずにサブエージェントを使うことがある。その場合はもう一度、agent team を明示的に頼む」と書かれていて、ほかの方の記事でも触れられています。「サブエージェントではなく、agent team としてチームメイトを 3 人起動して」と頼み直したところ、`security-reviewer`・`test-gap-reviewer`・`readme-drift-reviewer` という名前付きのチームメイトが起動し、ペインが 4 つに分かれました。

## 分かったこと 1：「読むだけ」の指示は守られなかった

始まってすぐ、2 人のチームメイトが自分からこう報告してきました。

- security-reviewer：「前のターンでBashのecho skipを実行してしまいましたが、副作用はなく、読み取り専用の指示には反していました。」
- test-gap-reviewer：「直前のファイル一覧取得にBashを使ってしまい、指示に反していました（変更や書き込みは行っていません）。」

どちらもファイルを変えてはいませんが、「コマンドは実行しない」という指示を破っています。原因を調べると、ドキュメントにこう書かれていました。

> On macOS, Linux, and WSL, Claude Code leaves Glob and Grep out of the default tool set, and Claude searches with `find` and `grep` through the Bash tool instead.

macOS では、ファイルを探す Glob と Grep が既定で外れていて、検索は Bash の `find` や `grep` で行う作りです。つまり「コマンドを実行しない」と言われると、ファイルを探す手段がありません。実際、1 回目のまとめには「3人とも Glob と Grep が使えず、ファイル名を推測して Read しただけです」と書かれていました。

もう 1 つの理由は権限です。チームメイトはリーダーの権限モードを引き継ぎます。今回のリーダーは auto モードだったので、Bash の実行はそのまま通りました。

プロンプトでお願いしても、それは強制ではありません。人間の運用でいえば「本番では触らないでね」と口頭で伝えるのと同じで、権限で絞っていないなら守られない前提で考えるべきでした。権限で絞る方法は、後の「使う前に決めておくこと」に書きました。

## 分かったこと 2：シェルで export した DISABLE_AUTOUPDATER は、チームメイトに届かなかった

テストの途中で、Claude Code が自動更新で新しい版を入れたことに気づきました。そこで 2 回目は `DISABLE_AUTOUPDATER=1` も export してから起動したのですが、チームメイトのペインには `Update installed` と出ていました。

![チームが作業を終えたところ](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/claude-agent-teams-tmux/end.png)

（左下の入力欄の文字は Claude Code が出す次の入力の候補で、自分が打ったものではありません）

各ペインの claude のプロセスの環境変数は `ps eww` で見られます。macOS なら、たとえば次のように 2 つの変数だけを取り出せます。

```bash
for pid in $(pgrep -x claude); do
  echo "== $(ps -o command= -p "$pid")"
  ps eww -o command= -p "$pid" | tr ' ' '\n' \
    | grep -E '^(CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS|DISABLE_AUTOUPDATER)='
done
```

リーダーを起動したシェルでは、2 つとも export しています。結果はこうでした。

| 変数 | リーダー | チームメイト 3 人 |
|---|---|---|
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | `1` | `1`（渡っている） |
| `DISABLE_AUTOUPDATER` | `1` | なし（渡っていない） |

`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` はチームメイトにも渡っていますが、同じシェルで export した `DISABLE_AUTOUPDATER` は渡っていません。分割表示のチームメイトは tmux の新しいペインで起動されるので、リーダーのシェルの環境はそのまま引き継がれないようです（Claude Code が必要なものだけ渡している、という動きに見えます）。確かめたのはこの 2 つの変数だけです。

自動更新くらいなら困りませんが、プロキシや社内の認証局（`NODE_EXTRA_CA_CERTS` など）をシェルの export で設定している環境だと、チームメイトだけ外に出られない、ということが起こりえます。

## 分かったこと 3：/exit でチームメイトを止めると、ペインもプロセスも残らなかった

リーダーで `/exit` すると、「バックグラウンドで作業が動いている」という確認が出て、チームメイトを止めて終わるか、バックグラウンドに回すかを選べました。止めて終わると、チームメイトのペインもプロセスも残りませんでした。

ドキュメントには、tmux のセッションが残ってしまった場合の片付け方（`tmux ls` と `tmux kill-session`）も載っています。今回は残りませんでしたが、途中でターミナルごと閉じた場合などには確認したほうがよさそうです。

## レビューの中身はどうだったか

レビュー自体はちゃんと役に立ちました。一番大きかった指摘は、実はチームではなく、1 回目にサブエージェントで動いたときのまとめに入っていたものです。

> flapping で通知が 10 分間抑止される（dedup.ts:17-20）。firing → resolved → firing の 2 回目の firing が、最初の firing の記録で抑止されます。

自分のサービスは、同じアラートを Slack に何度も流さないように、一定時間まとめる処理を入れていました。ところが、一度解決したアラートがすぐにまた発生すると（いわゆるフラッピング）、2 回目の発生の通知が捨てられていました。テストを書いて再現したところ、指摘どおり通知されていませんでした。障害対応の現場でいちばん困る種類の取りこぼしなので、すぐに直してリリースしました。

チームのほうでは、セキュリティ担当が「リリースは v* タグの push で起動するため、タグを打てる人なら誰でもイメージを公開できます」と指摘しました。3 人とも、最後に読めていないファイルや確認できていないことを自分で書いてくれたのは助かりました。

## 使う前に決めておくこと（未検証）

チームメイトは、リーダーと同じ権限を持った別のプロセスとして動きます。守ってほしいことはプロンプトで頼むのではなく、権限と設定で決めておく必要があります。以下はドキュメントを読んで考えたことで、今回は試していません。

- `--disallowedTools Bash` で Bash を外す。Bash を外すと Glob と Grep が戻ってくるので、ファイルを探す手段は残ります。ただし、分割表示のチームメイトにこのフラグ（と `--tools`）が引き継がれるのは v2.1.309 以降です。試したときの 2.1.287 は、それより前の版です
- リーダーを plan モードにしてからチームメイトを起動する。そのチームメイトは、計画ができるまで読み取り専用の plan モードで動きます。ただ、ドキュメントには、計画は届いた時点で自動で承認され、そのあと実装に移るとも書かれています。レビューだけさせたい場合に、これだけで足りるかは分かりません
- チーム全員に効かせたい環境変数は、シェルの export ではなく `settings.json` の `env` に書く。ドキュメントでは、チームメイトは普通のセッションと同じようにプロジェクトの設定を読み込むとされていますが、`env` がチームメイトのプロセスに渡るかは確かめていません

## 参考

- [Orchestrate teams of Claude Code sessions（Claude Code Docs）](https://code.claude.com/docs/en/agent-teams)
- [Tools reference: Glob tool behavior（Claude Code Docs）](https://code.claude.com/docs/en/tools-reference)
- [Claude Code Agent Teams で"AIチーム開発"を体験する — 1人で5人分のレビューを回す方法](https://qiita.com/dai_chi/items/dfc684a01afc85711fee)
- [Claude Codeのチームエージェント×tmuxで並列開発を爆速化する](https://zenn.dev/devken/articles/claude-code-team-tmux)
