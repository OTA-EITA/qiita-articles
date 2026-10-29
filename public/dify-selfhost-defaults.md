---
title: Dify を .env.example のままセルフホストすると何が残るか。1.17.1 を実際に起動して確かめた
tags:
  - Dify
  - Docker
  - Security
  - SRE
  - Go
private: true
updated_at: '2026-10-30T00:29:27+09:00'
id: 2ada1ea993e5911efae2
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

## きっかけ

Dify を Docker Compose でセルフホストする手順は、[公式の README](https://github.com/langgenius/dify/blob/1.17.1/README.md) では次の3行です。

```sh
cd dify/docker
cp .env.example .env
docker compose up -d
```

この手順のままだと、`.env` の中身は `.env.example` と同じです。検証用に立てたものをそのまま使い続けると、既定の鍵やパスワードも残ります。

そこで、Dify 1.17.1 の `.env.example` と `docker-compose.yaml` に、どんな既定値が入っているかをソースで1つずつ確かめました。さらに、既定のままのスタックを GitHub Actions のランナー上で実際に起動して、その既定値で本当に通るかを確認しました。

点検に使った CLI と検証用のワークフローは [OTA-EITA/dify-selfhost-audit](https://github.com/OTA-EITA/dify-selfhost-audit) に置いてあります。

### 既にある記事との違い

Qiita には、Dify のセルフホストの構築手順や、VPS への公開手順の記事はあります。一方で、既定の鍵やパスワードが何で、それを変えないと何が起きるかを、ソースと実際に起動した結果で確かめた記事は見つけられませんでした。この記事はそこを扱います。

## 結論

- 既定のままでホストの外に開いているのは、nginx の 80/443 と plugin_daemon のデバッグ用ポート 5003 だけです。DB、Redis、サンドボックス、Weaviate はコンテナのネットワークの内側にいます。
- `INIT_PASSWORD` が空だと、初期設定の画面にパスワードの確認がありません。管理者を作る前に 80 番が外から見えていれば、誰でも管理者になれます。
- ssrf_proxy は、メタデータのアドレスと内部のサービスへの通信をすべて 403 で止めました。
- ただし、**コード実行ノードのコードは ssrf_proxy を通らずに、api と plugin_daemon へ直接つながりました**。プロキシは環境変数で指定されているだけで、ネットワークとしては同じところにいるからです。
- そのため、api や plugin_daemon の内部向けの鍵が既定値のままなのは「内側に入られたら」だけの話ではありません。ワークフローを編集できる人のコードが、そこまで届きます。DB と Redis はサンドボックスと別のネットワークにいるので、構成上はサンドボックスから直接は届きません（ここは試していません）。
- Weaviate の匿名アクセスは `.env.example` で有効になりますが、admin list による認可が効いていて、キーなしでは読めも書けもしませんでした。

## 対象と前提

- Dify 1.17.1（コミット `8387590a`）
- dify-sandbox 0.2.15、dify-plugin-daemon 0.6.10
- 公式の `docker/.env.example` を `.env` にコピーしただけの状態

![Dify 1.17.1 の既定構成。80/443 と 5003 がホストの全インターフェースに公開され、sandbox は api や plugin_daemon と同じ ssrf_proxy_network にいる](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/dify-selfhost-defaults/network.png)

古いバージョンでは既定値が違います。たとえば `SECRET_KEY` は、1.14.0 までは `.env.example` に固定の値が書かれていました。1.14.1 から空になり、空のときは API が鍵を生成してストレージに保存します。

## 既定のまま残るもの

`.env.example` をそのまま使ったときに、点検ツールが出す指摘は次の 17 件です。

![dify-selfhost-audit を Dify 1.17.1 の .env.example と docker-compose.yaml に対して実行した結果。17 件、HIGH 0、MEDIUM 12](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/dify-selfhost-defaults/audit-output.png)

HIGH は 0 件です。DB、Redis、サンドボックスなどはホストにポートを公開していないので、鍵が既定のままでも外から直接は叩けません。

ただし例外が2つあります。1つは `INIT_PASSWORD` が空のまま 80 番を外に開けている場合で、管理者を作る前なら誰でも管理者になれます。もう1つは、プラグインのデバッグ用ポート 5003 が全インターフェースに公開されていることです。

残りの MEDIUM のほとんどは「ソースに書いてある値がそのまま鍵になっている」ものです。コンテナのネットワークに入れた相手、たとえば悪意のあるプラグインには、鍵がないのと同じです。

以下、重要なものから順に見ていきます。

### INIT_PASSWORD が空だと、最初に開いた人が管理者になる

`INIT_PASSWORD` が空のとき、`/install` を最初に開いた人が管理者アカウントを作れます。起動してから自分が管理者を作るまでの間に、ほかの人が先に開けば、その人が管理者です。

起動直後に確かめると、`GET /console/api/setup` は `not_started`（管理者がまだいない）で、`GET /console/api/init` は `finished` でした。`finished` は「パスワードの確認は済んでいる」という意味で、空のときは確認の段階そのものがありません。

`INIT_PASSWORD` を設定して api を作り直すと、`/console/api/init` は `not_started` に変わり、`/install` の前に `/init` の画面でそのパスワードの入力を求められます。

### サンドボックスの API キーは `dify-sandbox`

コード実行ノードが使うサンドボックスは、`X-Api-Key` ヘッダーでだけ認証しています。既定のキーは `dify-sandbox` で、Dify の `.env.example` にも、サンドボックス側の [conf/config.yaml](https://github.com/langgenius/dify-sandbox/blob/0.2.15/conf/config.yaml#L4) にも書かれています。

サンドボックスは外に公開されていないので、ホストの外から直接は呼べません。ただし、同じネットワークにいるコンテナからは呼べます。plugin_daemon もそのひとつで、ここではサードパーティのプラグインが動きます。

実際に api コンテナから呼ぶと、`X-Api-Key: dify-sandbox` で 200、誤ったキーとキーなしでは 401 でした。plugin_daemon のコンテナから既定のキーで呼んでも 200 です。

### DB と Redis のパスワードは `difyai123456`

PostgreSQL と Redis のパスワードは、どちらも `difyai123456` です。ベクトルストアを切り替えたときに使う pgvector、Qdrant、OceanBase なども、compose のフォールバックが同じ値です（`--all-profiles` で検出します）。

どちらもホストにポートは公開されていないので、外から直接はつながりません。問題になるのは、コンテナのネットワークの内側に入られたときです。

### plugin_daemon の鍵とデバッグ用ポート

plugin_daemon の `SERVER_KEY` と、api との間で使う `PLUGIN_DIFY_INNER_API_KEY` は、どちらも `.env.example` に書かれた固定の値です。

また、プラグインのリモートデバッグ用ポート 5003 が、compose でホストの全インターフェースに公開されています。ファイアウォールで閉じていなければ、外から TCP で接続できます。

ただ、つないだだけではプラグインを登録できません。最初のハンドシェイクで、コンソールで発行するデバッグ用のキーを求められ、合わなければ切断されます（[runtime_intialization_handlers.go L26-35](https://github.com/langgenius/dify-plugin-daemon/blob/0.6.10/internal/core/debugging_runtime/runtime_intialization_handlers.go#L26-L35)）。すぐに悪用できるわけではありませんが、プラグインを開発しない本番で外に開けておく理由はありません。

検証では公開先を 127.0.0.1 に付け替えているので、127.0.0.1:5003 には接続でき、ランナーの別のアドレスからは閉じていました。付け替えない compose のままなら、すべてのインターフェースで待ち受けます。

### Weaviate の匿名アクセスは有効になるが、実際には何もできない

ここは少しややこしいところです。compose のフォールバックでは `AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED` は `false` です。ところが `.env.example` には `WEAVIATE_AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true` と書かれています。手順どおり `.env.example` をコピーすると、匿名アクセスが有効になります。

最初はこれを問題として扱っていました。ところが Weaviate 側のソースを読むと、admin list による認可が有効なときは、admin list と読み取り専用のリストに入っていないユーザーはすべての操作を拒否されます。匿名のリクエストも同じです（[adminlist/authorizer.go L44-70](https://github.com/weaviate/weaviate/blob/v1.39.2/usecases/auth/authorization/adminlist/authorizer.go#L44-L70)）。`.env.example` では admin list が有効で、入っているのは `hello@dify.ai` だけです。

実際に、既定のキーで1件書き込んでから、キーなしで読み書きしてみました。読み込みも書き込みも 403 です。キーなしの `GET /v1/schema` は 200 を返しましたが、中身は空でした。一覧は見てよいものだけに絞って返すので、200 でも読めているわけではありません。最初にこの 200 だけを見て「読める」と思いかけたので、一覧の API だけで判断しないほうがよいです。

つまり既定のままなら、匿名アクセスの設定は効いていません。ただ、ソースを読む限り、admin list を無効にするとキーなしで読み書きできる状態になります（ここは試していません）。`false` にしておくのが安全です。点検ツールでは、admin list が無効のとき、または `anonymous` がリストに入っているときだけ指摘するようにしました。

### ssrf_proxy は内部への通信を止めるが、サンドボックスのコードは別

Dify は、HTTP リクエストノードやツールから外へ出る通信を、Squid の ssrf_proxy に通します。1.17.1 の既定では、プライベートアドレスやメタデータのアドレスへの通信は拒否されます。

api コンテナから ssrf_proxy を経由して試すと、`169.254.169.254`、`api:5001`、`sandbox:8194`、`plugin_daemon:5002`、`weaviate:8080`、プロキシ自身の `127.0.0.1:3128` はすべて 403 でした。対照として試した `https://example.com/` は 200 で、外へは出られます。

問題はサンドボックスの中のコードです。Dify のコード実行ノードは、サンドボックスに必ず `enable_network: True` を付けて頼みます（[code_executor.py L89](https://github.com/langgenius/dify/blob/1.17.1/api/core/helper/code_executor/code_executor.py#L89)）。サンドボックスには `HTTP_PROXY=http://ssrf_proxy:3128` が渡されますが、これは環境変数です。コードの側でプロキシを使わない設定にすれば、そのまま直接つなげます。

同じ条件で、サンドボックスに次の Python を実行させました。

```python
import urllib.request

def probe(url, use_env_proxy):
    handlers = [] if use_env_proxy else [urllib.request.ProxyHandler({})]
    try:
        r = urllib.request.build_opener(*handlers).open(url, timeout=5)
        return str(r.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except Exception as e:
        return type(e).__name__

print("direct_api=" + probe("http://api:5001/health", False))
print("direct_daemon=" + probe("http://plugin_daemon:5002/", False))
print("proxy_metadata=" + probe("http://169.254.169.254/", True))
```

結果は `direct_api=200 direct_daemon=404 proxy_metadata=403` でした。プロキシを通したメタデータへの通信は止まりますが、プロキシを使わずに api と plugin_daemon へは届きます。plugin_daemon の 404 は、HTTP のサーバーが応答したという意味です。

ssrf_proxy_network は `internal: true` なので、ここからインターネットへは直接出られません。外へ出る道がプロキシだけなのは確かです。ただ、同じネットワークにいるサービスへは、プロキシを通らずに届きます。試したのは api と plugin_daemon ですが、worker も同じネットワークにいます。

compose のコメントを読むと、エージェント用の `local_sandbox` については「api へ直接の経路がない」ように、わざわざ別のネットワークに分けてあります。コード実行用の `sandbox` はそうなっていません。

今回は、届くことまでを確かめました。届いた先の api や plugin_daemon の内部向け API に、既定の鍵で入れるかどうかまでは試していません。ただ、内部向けの鍵が `.env.example` に書かれた値のままだと、届いた先で守るものが既定値だけになります。

## 何をどう確かめたか

### 静的な点検

`dify-selfhost-audit` は、`.env` と `docker-compose.yaml` を読むだけの Go の CLI です。Docker にもネットワークにも触りません。

```sh
go install github.com/OTA-EITA/dify-selfhost-audit/cmd/dify-selfhost-audit@latest
cd dify/docker
dify-selfhost-audit
```

変数の展開は Compose と同じ規則（`${VAR:-default}`、`${VAR-default}`、入れ子、`$$`）で行います。各コンテナの環境変数は、`env_file` と `environment` を重ねて求めます。指摘には、根拠になる 1.17.1 のソースの行へのリンクを付けました。

`--fail-on medium` で CI を止められます。出力は表のほか、JSON と SARIF も選べます。

### 実際に起動しての確認

静的な点検だけでは、「既定のキーで本当に通るか」はわかりません。そこで、既定のスタックを GitHub Actions のランナー上で起動して確かめました。手元のマシンで上流のイメージとコードを動かしたくなかったので、使い捨てのランナーにしています。

- 公開ポートは、override ファイルですべて 127.0.0.1 に付け替えてから起動
- 付け替えたことを `docker compose config` で確認してから `up -d`
- 終わったら `docker compose down -v`
- メタデータのアドレスへのリクエストは、ステータスコードだけを記録

| 対象 | 確かめたこと | 結果 |
|---|---|---|
| 公開ポート | nginx の 80 を 127.0.0.1 で | 200 |
| | plugin_daemon の 5003 を 127.0.0.1 で | 接続できる |
| | 5003 をランナーの別のアドレスで | 閉じている |
| サンドボックス | キー `dify-sandbox` | **200** |
| | 誤ったキー / キーなし | 401 / 401 |
| | plugin_daemon から既定のキーで | **200** |
| Weaviate | 既定のキーで1件書き込み | 200 |
| | キーなしで読む / 書く | 403 / 403 |
| | キーなしで `GET /v1/schema` | 200（クラスは 0 件） |
| ssrf_proxy 経由 | `169.254.169.254`（メタデータ） | 403 |
| | api / sandbox / plugin_daemon / weaviate / プロキシ自身 | すべて 403 |
| | `https://example.com/`（対照） | 200 |
| サンドボックス内のコード | `api:5001` へ直接 | **200** |
| | `plugin_daemon:5002` へ直接 | **404（応答あり）** |
| | メタデータへプロキシ経由 | 403 |
| 初期設定 | `INIT_PASSWORD` が空で `/console/api/init` | **`finished`（パスワードの確認なし）** |
| | `INIT_PASSWORD` を設定して `/console/api/init` | `not_started` |

太字は、既定値のまま通ったもの、またはプロキシを通らずに届いたものです。

ワークフローは `workflow_dispatch` だけで動き、push や PR では動きません。起動から片付けまで、1回あたり 7〜8 分でした。

## 本番で変えるもの

優先度の高い順です。鍵は compose のコメントにあるとおり `openssl rand -base64 42` などで作ります。

1. `INIT_PASSWORD` を設定する。管理者を作り終えるまで、80/443 を外に出さない
2. 公開先を絞る。`EXPOSE_PLUGIN_DEBUGGING_PORT=127.0.0.1:5003` のように書けば、5003 は手元からしかつながらない。プラグインを開発しないなら公開自体をやめる
3. 内側の鍵を作り直す。対になっている変数は同じ値にそろえる
   - `SANDBOX_API_KEY` と `CODE_EXECUTION_API_KEY`
   - `PLUGIN_DAEMON_KEY`、`PLUGIN_DIFY_INNER_API_KEY`
   - `DB_PASSWORD`
   - `REDIS_PASSWORD` と、`CELERY_BROKER_URL` の中のパスワード
   - `WEAVIATE_API_KEY` と `WEAVIATE_AUTHENTICATION_APIKEY_ALLOWED_KEYS`
   - `DIFY_AGENT_SERVER_SECRET_KEY`、`DIFY_AGENT_API_TOKEN`
4. `CONSOLE_CORS_ALLOW_ORIGINS` を自分のドメインにする
5. `WEAVIATE_AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=false` にしておく
6. コード実行ノードを使える人を絞る。サンドボックスのコードが内側へ直接届くことを前提に、ワークフローの編集権限を考える

鍵を変えたあとは、`dify-selfhost-audit --fail-on medium` を CI に入れておくと、`.env` を差し替えたときに既定値へ戻っていないかを確かめられます。

## まとめ

Dify の既定構成は、外から直接触れる場所は少なく、ssrf_proxy もきちんと働いていました。一方で、`.env.example` の鍵とパスワードはソースに書かれた値で、コード実行ノードのコードはプロキシを通らずに内側のサービスへ届きます。

既定値のまま動かしているなら、まず `INIT_PASSWORD` と公開ポート、次に内側の鍵、の順で見直すのがよいと思います。点検ツールと検証のワークフローは [OTA-EITA/dify-selfhost-audit](https://github.com/OTA-EITA/dify-selfhost-audit) に置いてあります。

## 参考

- [langgenius/dify 1.17.1 docker/.env.example](https://github.com/langgenius/dify/blob/1.17.1/docker/.env.example)
- [langgenius/dify 1.17.1 docker/docker-compose.yaml](https://github.com/langgenius/dify/blob/1.17.1/docker/docker-compose.yaml)
- [langgenius/dify-sandbox 0.2.15](https://github.com/langgenius/dify-sandbox/tree/0.2.15)
- [langgenius/dify-plugin-daemon 0.6.10](https://github.com/langgenius/dify-plugin-daemon/tree/0.6.10)
- [weaviate/weaviate v1.39.2 adminlist/authorizer.go](https://github.com/weaviate/weaviate/blob/v1.39.2/usecases/auth/authorization/adminlist/authorizer.go)
- [OTA-EITA/dify-selfhost-audit](https://github.com/OTA-EITA/dify-selfhost-audit)
