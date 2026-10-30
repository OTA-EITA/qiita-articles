---
title: Dify 1.17.1 を .env.example のまま起動したら、コード実行ノードからプロキシを通らずに api へ届いた
tags:
  - Dify
  - Docker
  - Security
  - SRE
  - Go
private: true
updated_at: '2026-10-30T22:05:48+09:00'
id: 2ada1ea993e5911efae2
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

Dify 1.17.1 を、公式の手順どおり `.env.example` をコピーしただけの状態で起動して確かめました。

- 外に開いているのは nginx の 80/443 と、plugin_daemon のデバッグ用ポート 5003 だけでした。ssrf_proxy も、メタデータのアドレスと内部のサービスへの通信をすべて 403 で止めました。
- ただし、**コード実行ノードのコードは ssrf_proxy を通らずに、api と plugin_daemon へ直接届きました**。届いた先を守る鍵は `.env.example` に書かれた値のままです。
- `INIT_PASSWORD` が空だと、管理者を作る前に `/install` を開いた人が管理者になります。

Docker Compose で Dify をセルフホストしていて、本番に出す前に何を変えるか決めたい人向けに、確かめた結果と変える順番をまとめました。

公式の [README](https://github.com/langgenius/dify/blob/1.17.1/README.md) の手順は `cp .env.example .env` して `docker compose up -d` の3行で、検証用に立てたものをそのまま使い続けると既定の鍵やパスワードも残ります。Qiita には構築手順や VPS への公開手順の記事はありますが、既定値で何が通るのかを実際に起動して確かめた記事は見つけられなかったので、そこを扱います。点検に使った CLI と検証用のワークフローは [OTA-EITA/dify-selfhost-audit](https://github.com/OTA-EITA/dify-selfhost-audit) に置いてあります。

## 対象と前提

- Dify 1.17.1（コミット `8387590a`）
- dify-sandbox 0.2.15、dify-plugin-daemon 0.6.10、Weaviate 1.39.2（1.17.1 の compose が指している版）
- 公式の `docker/.env.example` を `.env` にコピーしただけの状態
- 2026 年 10 月 29 日に、GitHub Actions のランナー上で起動して確認

![Dify 1.17.1 の既定構成。80/443 と 5003 がホストの全インターフェースに公開され、sandbox は api や plugin_daemon と同じ ssrf_proxy_network にいる](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/dify-selfhost-defaults/network.png)

古いバージョンでは既定値が違います。たとえば `SECRET_KEY` は、1.14.0 までは `.env.example` に固定の値が書かれていました。1.14.1 から空になり、空のときは API が鍵を生成して、ストレージに `.dify_secret_key` として保存します（[api/configs/secret_key.py](https://github.com/langgenius/dify/blob/1.14.1/api/configs/secret_key.py)）。

## 確かめたこと

手元のマシンで上流のイメージとコードを動かしたくなかったので、使い捨ての GitHub Actions のランナーで起動しました。公開ポートは次の override ファイルで 127.0.0.1 に付け替え、`docker compose config` で付け替わったことを確かめてから `up -d` しています。終わったら `docker compose down -v` で片付けました。

```yaml:docker-compose.override.yaml
# !override は Docker Compose v2.24.4 以降
services:
  nginx:
    ports: !override
      - "127.0.0.1:80:80"
      - "127.0.0.1:443:443"
  plugin_daemon:
    ports: !override
      - "127.0.0.1:5003:5003"
```

内側のサービスへのリクエストは、api コンテナの中から curl で送りました。たとえばサンドボックスは次のように叩いています。

```sh
docker compose exec -T api curl -s -o /dev/null -w '%{http_code}' \
  -H 'X-Api-Key: dify-sandbox' -H 'Content-Type: application/json' \
  -d '{"language":"python3","code":"print(1)","preload":"","enable_network":true}' \
  http://sandbox:8194/v1/sandbox/run
```

結果は次のとおりです。太字は、既定値のまま通ったもの、またはプロキシを通らずに届いたものです。

| 対象 | 確かめたこと | 結果 |
|---|---|---|
| サンドボックス内のコード | `api:5001` へ直接 | **200** |
| | `plugin_daemon:5002` へ直接 | **404（応答あり）** |
| | メタデータへプロキシ経由 | 403 |
| ssrf_proxy 経由 | `169.254.169.254`（メタデータ） | 403 |
| | api / sandbox / plugin_daemon / weaviate / プロキシ自身 | すべて 403 |
| | `https://example.com/`（対照） | 200 |
| 初期設定 | `INIT_PASSWORD` が空で `/console/api/init` | **`finished`（パスワードの確認なし）** |
| | `INIT_PASSWORD` を設定して `/console/api/init` | `not_started` |
| サンドボックス | キー `dify-sandbox` | **200** |
| | 誤ったキー / キーなし | 401 / 401 |
| | plugin_daemon から既定のキーで | **200** |
| 公開ポート | nginx の 80 を 127.0.0.1 で | 200 |
| | plugin_daemon の 5003 を 127.0.0.1 で | 接続できる |
| | 5003 をランナーの別のアドレスで | 閉じている |
| Weaviate | 既定のキーで1件書き込み | 200 |
| | キーなしで読む / 書く | 403 / 403 |
| | キーなしで `GET /v1/schema` | 200（クラスは 0 件） |

ワークフローは `workflow_dispatch` だけで動き、push や PR では動きません。起動から片付けまで、1回あたり 7〜8 分でした。

## 分かったこと

影響の大きいものから順に並べます。

### コード実行ノードのコードは、ssrf_proxy を通らずに api と plugin_daemon へ届く

Dify は、HTTP リクエストノードやツールから外へ出る通信を、Squid の ssrf_proxy に通します。1.17.1 の既定では、プライベートアドレスやメタデータのアドレスへの通信は拒否され、上の表のとおり内部のサービスへの通信はすべて 403 でした。

問題はサンドボックスの中のコードです。Dify のコード実行ノードは、サンドボックスに必ず `enable_network: True` を付けて頼みます（[code_executor.py L89](https://github.com/langgenius/dify/blob/1.17.1/api/core/helper/code_executor/code_executor.py#L89)）。サンドボックスには `HTTP_PROXY=http://ssrf_proxy:3128` が渡されますが、これは環境変数です。コードの側でプロキシを使わない設定にすれば、そのまま直接つなげます。

サンドボックスに次の Python を実行させました。

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

そのため、api や plugin_daemon の内部向けの鍵が既定値のままなのは「内側に入られたら」だけの話ではありません。ワークフローを編集できる人のコードが、そこまで届きます。

### INIT_PASSWORD が空だと、最初に開いた人が管理者になる

`INIT_PASSWORD` が空のとき、`/install` を最初に開いた人が管理者アカウントを作れます。起動してから自分が管理者を作るまでの間に、ほかの人が先に開けば、その人が管理者です。

起動直後に確かめると、`GET /console/api/setup` は `not_started`（管理者がまだいない）で、`GET /console/api/init` は `finished` でした。`finished` は「パスワードの確認は済んでいる」という意味で、空のときは確認の段階そのものがありません。

`INIT_PASSWORD` を設定して api を作り直すと、`/console/api/init` は `not_started` に変わり、`/install` の前に `/init` の画面でそのパスワードの入力を求められます。

### サンドボックスの API キーは `dify-sandbox` のまま

サンドボックスは `X-Api-Key` ヘッダーでだけ認証しています。既定のキーは `dify-sandbox` で、Dify の `.env.example` にも、サンドボックス側の [conf/config.yaml](https://github.com/langgenius/dify-sandbox/blob/0.2.15/conf/config.yaml#L4) にも書かれています。

外には公開されていないので、ホストの外から直接は呼べません。ただし、同じネットワークにいるコンテナからは呼べ、api からも plugin_daemon からも既定のキーで 200 でした。plugin_daemon ではサードパーティのプラグインが動きます。

### plugin_daemon の鍵は固定値で、デバッグ用ポート 5003 は全インターフェースに開く

plugin_daemon の `SERVER_KEY` と、api との間で使う `PLUGIN_DIFY_INNER_API_KEY` は、どちらも `.env.example` に書かれた固定の値です。

また、プラグインのリモートデバッグ用ポート 5003 が、compose でホストの全インターフェースに公開されています。ファイアウォールで閉じていなければ、外から TCP で接続できます。検証では 127.0.0.1 に付け替えたので、ランナーの別のアドレスからは閉じていました。

つないだだけではプラグインを登録できません。最初のハンドシェイクで、コンソールで発行するデバッグ用のキーを求められ、合わなければ切断されます（[runtime_intialization_handlers.go L26-35](https://github.com/langgenius/dify-plugin-daemon/blob/0.6.10/internal/core/debugging_runtime/runtime_intialization_handlers.go#L26-L35)）。すぐに悪用できるわけではありませんが、プラグインを開発しない本番で外に開けておく理由はありません。

### DB と Redis のパスワードは `difyai123456` のまま

PostgreSQL と Redis のパスワードは、どちらも `difyai123456` です。ベクトルストアを切り替えたときに使う pgvector、Qdrant、OceanBase なども、compose のフォールバックが同じ値です。

どちらもホストにポートは公開されておらず、サンドボックスとも別のネットワークにいるので、構成上は外からもサンドボックスからも直接は届きません。問題になるのは、DB や Redis と同じネットワークにいるコンテナに入られたときです。

### Weaviate の匿名アクセスは有効になるが、admin list で止まる

compose のフォールバックでは `AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED` は `false` です。ところが `.env.example` には `WEAVIATE_AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true` と書かれているので、手順どおりコピーすると匿名アクセスが有効になります。

Weaviate のソースを読むと、admin list による認可が有効なときは、admin list と読み取り専用のリストに入っていないユーザーはすべての操作を拒否されます。匿名のリクエストも同じです（[adminlist/authorizer.go L44-70](https://github.com/weaviate/weaviate/blob/v1.39.2/usecases/auth/authorization/adminlist/authorizer.go#L44-L70)）。`.env.example` では admin list が有効で、入っているのは `hello@dify.ai` だけです。

実際、キーなしの読み込みも書き込みも 403 でした。キーなしの `GET /v1/schema` は 200 を返しましたが、中身は空です。一覧は見てよいものだけに絞って返すので、200 でも読めているわけではありません。最初にこの 200 だけを見て「読める」と思いかけたので、一覧の API だけで判断しないほうがよいです。

## 本番で変えるもの

優先度の高い順です。鍵は compose のコメントにあるとおり `openssl rand -base64 42` などで作ります。

1. `INIT_PASSWORD` を設定する。管理者を作り終えるまで、80/443 を外に出さない
2. コード実行ノードを使える人を絞る。サンドボックスのコードが内側へ直接届くことを前提に、ワークフローの編集権限を考える
3. 公開先を絞る。`EXPOSE_PLUGIN_DEBUGGING_PORT=127.0.0.1:5003` のように書けば、5003 は手元からしかつながらない。プラグインを開発しないなら公開自体をやめる
4. 内側の鍵を作り直す。対になっている変数は同じ値にそろえる
   - `SANDBOX_API_KEY` と `CODE_EXECUTION_API_KEY`
   - `PLUGIN_DAEMON_KEY`、`PLUGIN_DIFY_INNER_API_KEY`
   - `DB_PASSWORD`
   - `REDIS_PASSWORD` と、`CELERY_BROKER_URL` の中のパスワード
   - `WEAVIATE_API_KEY` と `WEAVIATE_AUTHENTICATION_APIKEY_ALLOWED_KEYS`
   - `DIFY_AGENT_SERVER_SECRET_KEY`、`DIFY_AGENT_API_TOKEN`
5. `CONSOLE_CORS_ALLOW_ORIGINS` を自分のドメインにする
6. `WEAVIATE_AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=false` にしておく

## 点検ツールで見つける

`dify-selfhost-audit` は、`.env` と `docker-compose.yaml` を読むだけの Go の CLI です。Docker にもネットワークにも触りません。

```sh
go install github.com/OTA-EITA/dify-selfhost-audit/cmd/dify-selfhost-audit@latest
cd dify/docker
dify-selfhost-audit
```

変数の展開は Compose と同じ規則（`${VAR:-default}`、`${VAR-default}`、入れ子、`$$`）で行います。各コンテナの環境変数は、`env_file` と `environment` を重ねて求めます。指摘には、根拠になる 1.17.1 のソースの行へのリンクを付けました。ベクトルストアのプロファイルまで見るときは `--all-profiles` を付けます。

`.env.example` をそのまま使ったときの指摘は次の 17 件で、HIGH は 0 件、MEDIUM は 12 件です。

| ID | 重要度 | 対象 |
|---|---|---|
| DSA004 | MEDIUM | `INIT_PASSWORD` が空 |
| DSA005 | MEDIUM | サンドボックスのキーが `dify-sandbox` |
| DSA007 | MEDIUM | plugin_daemon の `SERVER_KEY` が既定値 |
| DSA008 | MEDIUM | プラグイン用の内部 API キーが既定値 |
| DSA009 | MEDIUM | `DB_PASSWORD` が既定値 |
| DSA010 | MEDIUM | `REDIS_PASSWORD` が既定値 |
| DSA010 | MEDIUM | `CELERY_BROKER_URL` に既定の Redis パスワード |
| DSA011 | MEDIUM | Weaviate の API キーが既定値 |
| DSA014 | MEDIUM | `DIFY_AGENT_SERVER_SECRET_KEY` が既定値 |
| DSA015 | MEDIUM | `DIFY_AGENT_API_TOKEN` が既定値 |
| DSA018 | MEDIUM | `CONSOLE_CORS_ALLOW_ORIGINS` が `*` |
| DSA101 | MEDIUM | plugin_daemon の 5003 が全インターフェースに公開 |
| DSA019 | LOW | `WEB_API_CORS_ALLOW_ORIGINS` が `*` |
| DSA020 | LOW | nginx が HTTP のみ |
| DSA002 | INFO | `SECRET_KEY` が空（生成して保存される） |
| DSA101 | INFO | nginx の 80 が全インターフェースに公開 |
| DSA101 | INFO | nginx の 443 が全インターフェースに公開 |

HIGH が 0 件なのは、DB、Redis、サンドボックスなどがホストにポートを公開していないからです。MEDIUM のほとんどは「ソースに書いてある値がそのまま鍵になっている」もので、コンテナのネットワークに入れた相手、たとえば悪意のあるプラグインやコード実行ノードのコードには、鍵がないのと同じです。

出力は表のほか、`--format json` と `--format sarif` も選べます。`--fail-on medium` を CI に入れておくと、`.env` を差し替えたときに既定値へ戻っていないかを確かめられます。

## 確かめていないこと

- サンドボックスのコードから届いた api や plugin_daemon の内部向け API に、既定の鍵で実際に入れるか。届くことまでは確かめましたが、その先は試していません
- サンドボックスから worker へ届くか。同じネットワークにいることは compose で確かめましたが、通信は試していません
- DB と Redis にサンドボックスから届かないこと。別のネットワークにいるのは compose で確かめましたが、通信は試していません
- Weaviate で admin list を無効にしたときの挙動。ソースを読む限りキーなしで読み書きできる状態になりますが、試していません。点検ツールでは、admin list が無効のとき、または `anonymous` がリストに入っているときだけ指摘します
- 1.17.1 以外のバージョン

## 参考

- [langgenius/dify 1.17.1 docker/.env.example](https://github.com/langgenius/dify/blob/1.17.1/docker/.env.example)
- [langgenius/dify 1.17.1 docker/docker-compose.yaml](https://github.com/langgenius/dify/blob/1.17.1/docker/docker-compose.yaml)
- [langgenius/dify 1.14.1 api/configs/secret_key.py](https://github.com/langgenius/dify/blob/1.14.1/api/configs/secret_key.py)
- [langgenius/dify-sandbox 0.2.15](https://github.com/langgenius/dify-sandbox/tree/0.2.15)
- [langgenius/dify-plugin-daemon 0.6.10](https://github.com/langgenius/dify-plugin-daemon/tree/0.6.10)
- [weaviate/weaviate v1.39.2 adminlist/authorizer.go](https://github.com/weaviate/weaviate/blob/v1.39.2/usecases/auth/authorization/adminlist/authorizer.go)
- [OTA-EITA/dify-selfhost-audit](https://github.com/OTA-EITA/dify-selfhost-audit)
