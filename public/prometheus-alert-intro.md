---
title: Prometheus のアラートをちゃんと理解したい人のための入門：for と rate() の範囲を間違えると、鳴りすぎるか一度も鳴らない
tags:
  - prometheus
  - SRE
  - 監視
  - devops
  - 初心者
private: true
updated_at: '2026-11-10T13:30:53+09:00'
id: 46fd258b7351820e6ee6
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

Prometheus のアラートルール（alerting rules）の書き方を確かめる小さな道具（[promrule-lint](https://github.com/OTA-EITA/promrule-lint)）を作っていたとき、試しに [awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts) に当ててみました。

スターが 8,000 以上あり、README に「copy-paste YAML」と書かれている、よく使われているアラート集です。

1,162 本のアラートのうち、255 本は 1 回の揺れで鳴る書き方で、98 本は今の Prometheus の初期設定では一度も鳴らない書き方でした。障害のときに読む手順書（runbook）へのリンクは、1,162 本のどれにもありませんでした。

アラート集が悪いという話ではありません。アラートルールは数行の YAML ですが、その数行のそれぞれに「鳴らない」「鳴りすぎる」「鳴っても何をすればいいか分からない」の落とし穴があり、コピペしただけではそれが見えない、という話です。この記事では、その 3 つを `promtool` で実際に再現しながら説明します。

## この記事で触れること

- アラートルールの各行が何を決めているか
- `for` を書かないと、1 回の揺れで呼び出されること
- `rate()` の範囲が短いと、アラートが永遠に鳴らないこと
- 手順書のないアラートが、なぜ夜中に困るか
- 自分のルールを `promtool test rules` で確かめる方法

## この記事で触れないこと

- Alertmanager の通知先の振り分けや抑制（inhibit）の設定
- SLO とエラーバジェットにもとづくアラート（burn rate）
- Grafana のアラート機能
- しきい値（何 % で鳴らすか）の決め方

## そもそもアラートとは何か

ダッシュボードは人が見に行くもので、アラートは人を呼び出すものです。夜中でも休日でも、鳴れば誰かが起きてパソコンを開きます。

Google の SRE 本の監視の章には、呼び出しについてこう書かれています。

> Every page should be actionable.
> Every page response should require intelligence. If a page merely merits a robotic response, it shouldn't be a page.

呼び出しには、すぐに人が考えて手を動かす必要があるものだけを使う、ということです。この記事の 3 つの落とし穴は、どれもこの原則から外れる方向に働きます。

## アラートルールの読み方

awesome-prometheus-alerts にあるルールを 1 本見てみます。

```yaml
- alert: CiliumAgentHighDeniedRate
  expr: 'sum(rate(cilium_drop_count_total{reason="Policy denied"}[1m])) by (pod) > 0'
  for: 10m
  labels:
    severity: info
  annotations:
    summary: Cilium agent high denied rate (instance {{ $labels.instance }})
    description: "Cilium agent {{ $labels.pod }} is dropping packets due to policy denial. ..."
```

| 行 | 決めていること |
|---|---|
| `expr` | 何を見て、どうなったら異常とするか |
| `for` | 異常がどれだけ続いたら鳴らすか |
| `labels.severity` | どのくらい急ぎか。Alertmanager で、呼び出すか、チャットに流すだけかを分けるのに使う |
| `annotations` | 鳴ったときに人が読む文章。手順書へのリンクもここに書く |

このあと出てくる落とし穴は、`for` と、`expr` の中の `[1m]` と、`annotations` の 3 か所です。

## 試した条件

- 2026 年 11 月 5 日、macOS、Prometheus 3.15.1 の `promtool`（Homebrew）
- awesome-prometheus-alerts の `dist/rules`（コミット 736370e、2026 年 10 月 23 日）
- promrule-lint v0.1.0、取り込み間隔は Prometheus の初期値の 1 分として検査

`promtool test rules` は、時系列のデータを手で書いて、アラートが鳴るかどうかを確かめられる Prometheus 付属の機能です。本物の Prometheus を立てなくても、同じ評価のしかたで結果が分かります。

試したルールはこれです。

```yaml:rules.yml
groups:
  - name: demo
    interval: 1m
    rules:
      - alert: ErrorsShortWindow
        expr: rate(errors_total[1m]) > 0
      - alert: ErrorsLongWindow
        expr: rate(errors_total[5m]) > 0
      - alert: CpuNoFor
        expr: cpu_percent > 90
      - alert: CpuFor5m
        expr: cpu_percent > 90
        for: 5m
```

## 落とし穴 1：`for` がないと、1 回の揺れで鳴る

`for` は「異常な状態がこの時間ずっと続いたら鳴らす」という指定です。書かないか `for: 0m` にすると、評価した 1 回でも条件を満たせばすぐに鳴ります。

CPU 使用率が 1 回だけ 95% に跳ねて、すぐに 10% に戻るデータで試しました。

```yaml:test.yml（抜粋）
input_series:
  - series: 'cpu_percent{instance="web-1"}'
    values: '10 10 10 95 10 10 10 10 10 10'
alert_rule_test:
  # 1 回跳ねただけで、for のないアラートは鳴る
  - eval_time: 3m
    alertname: CpuNoFor
    exp_alerts: [{exp_labels: {instance: web-1}}]
  # for: 5m なら鳴らない
  - {eval_time: 3m, alertname: CpuFor5m, exp_alerts: []}
  - {eval_time: 8m, alertname: CpuFor5m, exp_alerts: []}
```

```console
$ promtool test rules test.yml
  SUCCESS
```

`for` のないほうは、跳ねた 3 分の時点で鳴りました。`for: 5m` のほうは、跳ねたあとすぐに戻ったので一度も鳴りません。

1 回だけの取り込みの失敗、GC の一瞬の停止、デプロイ中の数秒の揺れでも呼び出されるのが `for` のないアラートです。何度か起こされて、開いてみると何も起きていない、を繰り返すと、人はアラートを信じなくなります。本当の障害のときに見るのが遅れるのは、こういうときです。

ただし、`for` がないほうが正しいアラートもあります。たとえば「SSL 証明書の期限が切れた」は一瞬の揺れではなく状態なので、待つ意味がありません。awesome-prometheus-alerts の `BlackboxSslCertificateExpired` も `for: 0m` です。`for` を書かないなら、それが状態を見ているアラートかどうかを一度考える、というのが大事だと思います。

## 落とし穴 2：`rate()` の範囲が短いと、永遠に鳴らない

こちらのほうが怖い落とし穴です。鳴りすぎるアラートは少なくとも気づけますが、鳴らないアラートは、障害が起きて初めて鳴らなかったことに気づきます。

`rate(errors_total[1m])` は「直近 1 分のデータから、1 秒あたりの増え方を出す」という意味です。増え方を出すには、範囲の中にデータが 2 つ以上必要です。

Prometheus は、取り込み（scrape）のたびに 1 つデータを保存します。初期値の 1 分おきの取り込みで `[1m]` の範囲を見ると、範囲の中にデータが 1 つしか入りません。Prometheus 3 からは範囲の左端を含まなくなったので、なおさらです。移行ガイドにはこう書かれています。

> Lookback and range selectors are now left-open and right-closed (previously left-closed and right-closed)

> In Prometheus V3, however, such a subquery will only return one point, which is insufficient for a rate or increase calculation, resulting in No Data returned.

毎分 6 件ずつ確実にエラーが増えているデータで試しました。

```yaml:test.yml（抜粋）
input_series:
  # 1 分おきに取り込まれるカウンター。毎分 6 件ずつエラーが増える
  - series: 'errors_total{job="api"}'
    values: '0+6x15'
promql_expr_test:
  # 範囲が 1 分だと、取り込みが 1 分おきなので値が返らない
  - expr: rate(errors_total[1m])
    eval_time: 10m
    exp_samples: []
  # 範囲が 5 分なら 1 秒あたり 0.1 件 (毎分 6 件) が出る
  - expr: rate(errors_total[5m])
    eval_time: 10m
    exp_samples:
      - labels: '{job="api"}'
        value: 0.1
alert_rule_test:
  # エラーは毎分増えているのに、範囲 1 分のアラートは鳴らない
  - {eval_time: 10m, alertname: ErrorsShortWindow, exp_alerts: []}
  - eval_time: 10m
    alertname: ErrorsLongWindow
    exp_alerts: [{exp_labels: {job: api}}]
```

```console
$ promtool test rules test.yml
  SUCCESS
```

`[1m]` のほうは値そのものが返らず、アラートも鳴りませんでした。1 分、2 分、5 分、8 分、12 分、15 分の時点でも試しましたが、どれも値は空でした。エラーは毎分ずっと増えているのに、です。`[5m]` にすると、毎分 6 件、つまり 1 秒あたり 0.1 件が正しく出て、アラートも鳴りました。

`promtool check rules` は書き方の誤りを見るだけなので、このルールは問題なく通ります。エラーも警告も出ないまま、鳴らないアラートが本番に入ります。

この「範囲は取り込み間隔の 2〜4 倍以上にする」という話自体は、Grafana のドキュメントや Prometheus のメーリングリストでも以前から言われています（参考に載せています）。

awesome-prometheus-alerts の 98 本は、`[1m]` の範囲で `rate`・`increase`・`delta` を使っているもので、1 分おきの取り込みのまま入れると、上と同じことになります。

15 秒おきや 30 秒おきに取り込んでいる環境なら、範囲の中にデータが 2 つ以上入るので動きます。つまり、ルールが正しいかどうかは、ルールのファイルだけを見ても決まりません。自分の環境の取り込み間隔と組み合わせて初めて決まります。

## 落とし穴 3：鳴っても、何をすればいいか分からない

夜中の 3 時に起こされて、アラートの名前と「VALUE = 0.42」だけが届いたとします。それが何の数字で、どこを見て、何をすれば止まるのかが分からなければ、調べるところから始めることになります。

Prometheus の公式ドキュメントのアラートの章には、こう書かれています。

> Alerts should link to relevant consoles and make it easy to figure out which component is at fault.

多くのチームでは、`annotations` に `runbook_url` を書いて、鳴ったときの手順書へのリンクを付けています。

awesome-prometheus-alerts の 1,162 本には、`summary` と `description` はありますが、`runbook_url` は 1 本もありません。アラート集は、どのチームでも使える形で配っている以上、それぞれのチームの手順書へのリンクを持てないのは当然です。だからこそ、コピペしたあとに自分で足す必要があります。

手順書に書くことは、長くなくてかまいません。

- このアラートが鳴ると、利用者には何が起きているか
- 最初に見るダッシュボードとログ
- よくある原因と、その戻し方
- 誰にエスカレーションするか

書けないアラートは、そもそも呼び出す必要がないアラートかもしれません。

## 人気のアラート集に当ててみた結果

awesome-prometheus-alerts の `dist/rules`（112 ファイル）を promrule-lint で検査した結果です。

```console
$ npx github:OTA-EITA/promrule-lint --fail-on none dist/rules
…
112 file(s), 1515 finding(s): 98 high, 255 medium, 1162 low
```

| 指摘 | 本数 | 意味 |
|---|---|---|
| `for` がない（`for: 0m`） | 255 / 1,162 | 1 回の評価で鳴る。状態を見るアラートなら問題ない |
| `rate` などの範囲が `[1m]` | 98 / 1,162 | 1 分おきの取り込みでは値が返らず、鳴らない |
| `runbook_url` がない | 1,162 / 1,162 | 鳴ったときの手順書へのリンクがない |

繰り返しになりますが、これはアラート集の欠陥というより、「そのまま入れれば監視が完成する」ものではないことを示す数字だと思います。どれも、自分の環境の取り込み間隔、許せる揺れ、自分たちの手順書と組み合わせて初めて正しくなる部分です。

## 自分のルールを確かめる

ルールを足したり変えたりしたときは、`promtool test rules` で「鳴ってほしいときに鳴り、鳴ってほしくないときに鳴らない」ことを確かめておくと安心です。

この記事で使った [rules.yml と test.yml](https://github.com/OTA-EITA/qiita-articles/tree/main/samples/prometheus-alert-intro) は GitHub に置いています。2 つを同じフォルダに置いて `promtool test rules test.yml` を実行すれば、同じ結果になります。テストのデータは自分の環境の取り込み間隔に合わせて書きます。1 分おきに取り込んでいるなら `interval: 1m` です。

あわせて、CI でルールの書き方の落とし穴を機械的に見るようにしています。

```yaml:.github/workflows/rules.yml
  promrule-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          persist-credentials: false
      # 実際はタグかコミットで固定する（npx github:OTA-EITA/promrule-lint#v0.1.0 など）
      - run: npx github:OTA-EITA/promrule-lint --scrape-interval 30s rules/
```

`--scrape-interval` には、自分の環境の取り込み間隔を渡します。道具は何でもよくて、大事なのは「ルールが正しいかどうかは、取り込み間隔と一緒に見ないと分からない」ことです。

## 総まとめ

| 行 | 落とし穴 | 起きること | 確かめ方 |
|---|---|---|---|
| `for` | 書かない | 1 回の揺れで呼び出される | 揺れのデータで `promtool test rules` |
| `expr` の範囲 | 取り込み間隔の 2 倍より短い | 値が返らず、永遠に鳴らない | 取り込み間隔に合わせたデータで `promtool test rules` |
| `annotations` | 手順書がない | 鳴っても、何をすればいいか分からない | `runbook_url` があるかを CI で見る |

アラートは、鳴らすためではなく、鳴ったときに人が正しく動けるようにするためのものです。人気のアラート集は、何を見ればいいかを知る出発点としてとても便利です。そのうえで、`for`、範囲、手順書の 3 か所だけは、自分の環境に合わせて書き直してから使うのがよさそうです。

## 参考

- [Monitoring Distributed Systems（Site Reliability Engineering, Rob Ewaschuk）](https://sre.google/sre-book/monitoring-distributed-systems/)
- [Alerting（Prometheus のドキュメント）](https://prometheus.io/docs/practices/alerting/)
- [Migration guide（Prometheus 3.0 の変更点）](https://prometheus.io/docs/prometheus/latest/migration/)
- [Unit testing for rules（promtool test rules）](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
- [Troubleshoot Prometheus data source issues（Grafana のドキュメント）](https://grafana.com/docs/grafana/latest/datasources/prometheus/troubleshooting)
- [1 minute scrape, [1m] == no data ([90s] has data)（prometheus-users）](https://groups.google.com/g/prometheus-users/c/DV_Jbyh-zTM/m/ypRMQPTZBwAJ)
- [samber/awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts)
- [OTA-EITA/promrule-lint](https://github.com/OTA-EITA/promrule-lint)
