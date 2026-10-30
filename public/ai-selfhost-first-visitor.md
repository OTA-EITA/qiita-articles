---
title: AI セルフホスト 5 製品を公式 compose で立てた直後、最初に来た人が管理者になれたのは n8n と Open WebUI だった
tags:
  - n8n
  - LLM
  - Docker
  - Security
  - SRE
private: true
updated_at: '2026-10-30T21:24:54+09:00'
id: 54cdd63922da7bd7531a
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

n8n・Open WebUI・LiteLLM・Langflow・Flowise を、公式の compose ファイルと `.env` の例のまま起動して確かめました。

| 製品（版） | 立てた直後 | 例のパスワード |
|---|---|---|
| n8n 2.44.5 | ログインなしで owner を作れる。2 人目は拒否 | Postgres が `changePassword` で入れる |
| Open WebUI 0.12.3 | 最初にサインアップした人が admin。2 人目は 403 | なし |
| LiteLLM 1.106.2 | マスターキーが空だと起動を拒否する | Postgres が `dbpassword9090` で入れる |
| Langflow 1.12.7 | 自動ログインは既定で無効（403） | Postgres が `langflow` で入れる |
| Flowise 3.1.4 | 公式の手順では起動しなかった（後述） | なし（SQLite） |

- n8n と Open WebUI は、管理者を作るまでの間なら、外から先に来た人が管理者になれます。「まだ誰もいない」ことも、ログインなしの API で分かります。
- LiteLLM と Langflow は、最近の版で安全な既定に変わっていました。ただし Langflow は、古い版のイメージや `LANGFLOW_AUTO_LOGIN=true` で、誰でもスーパーユーザーになります。
- データベースの例のパスワードは、3 製品で `.env` や compose に書かれたまま通りました。
- 5 つとも、公式の compose ファイルはアプリのポートをホストの全インターフェースに公開しています。

これらをセルフホストしていて、外に出す前に何を変えるか決めたい人向けです。

Intruder が 2026 年 3 月 27 日に公開した調査 [From enterprise chatbots to gooner caves: exposed AI infrastructure is rampant](https://www.intruder.io/research/from-enterprise-chatbots-to-gooner-caves-exposed-ai-infrastructure-is-rampant) は、インターネットに公開された AI 関連のサービスに、認証なしで使えるものが多いと報告しています。その中の "an alarming number of hosts appearing to be in a freshly installed setup, without any authentication"（入れたばかりの状態のまま、認証なしで公開されているホストが驚くほど多い）という一文を見て、公式の手順で立てた直後の内側がどうなっているかを確かめることにしました。外から見た数の話は、Intruder の調査を紹介した [【悲報】100万台のAIサービスをスキャンしたら「史上最悪のセキュリティ」だった件](https://qiita.com/emi_ndk/items/0aac69d8a962d2413d9d) に詳しく書かれています。点検に使った CLI と検証のワークフローは [OTA-EITA/ai-selfhost-audit](https://github.com/OTA-EITA/ai-selfhost-audit) に置いてあります。

## 対象と前提

- 各プロジェクトの公式の compose ファイルと `.env` の例を、次の版のまま使いました（2026 年 10 月 29 日時点で、公開から 7 日以上たっている最新の安定版）。
  - n8n: [n8n-hosting の withPostgres](https://github.com/n8n-io/n8n-hosting/tree/b690a87c814aed2f56981047fb617d22e488b861/docker-compose/withPostgres)（`.env` の `N8N_VERSION=2.44.5`）
  - Open WebUI: [v0.12.3 の docker-compose.yaml](https://github.com/open-webui/open-webui/blob/v0.12.3/docker-compose.yaml)
  - LiteLLM: [v1.106.2 の docker-compose.yml と .env.example](https://github.com/BerriAI/litellm/tree/v1.106.2)
  - Langflow: [v1.12.7 の docker_example](https://github.com/langflow-ai/langflow/blob/v1.12.7/docker_example/docker-compose.yml)
  - Flowise: [3.1.4 の docker/](https://github.com/FlowiseAI/Flowise/tree/flowise%403.1.4/docker)
- 起動したのは 2026 年 10 月 29 日、GitHub Actions の使い捨てのランナーです。外から届かないよう、公開ポートは override ファイルですべて 127.0.0.1 に付け替えています。付け替える前の compose が全インターフェースに公開していることは、`docker compose config` で確かめました。
- イメージが `latest` や `main` の製品は、上の版のタグに固定しました。

## 立てるときに変えること

先に、確かめた結果から決めた手順を載せます。理由は製品ごとの節にあります。

| 製品 | 外に出す前にやること |
|---|---|
| 共通 | 管理者を作るまではポートを `127.0.0.1:` で公開する。DB のポートは公開しない。例のパスワードを作り直す |
| n8n | 先に owner を作る（または `N8N_INSTANCE_OWNER_MANAGED_BY_ENV=true` で env から作る）。`N8N_ENCRYPTION_KEY` と `N8N_RUNNERS_AUTH_TOKEN` を生成する。2.45.5 以降にする |
| Open WebUI | `WEBUI_ADMIN_EMAIL` と `WEBUI_ADMIN_PASSWORD` を設定する。`WEBUI_SECRET_KEY` を生成する。`CORS_ALLOW_ORIGIN` を自分のオリジンにする |
| LiteLLM | `LITELLM_MASTER_KEY` と `LITELLM_SALT_KEY` を生成する。`DATABASE_URL` のパスワードを変える |
| Langflow | イメージを 1.10.3 以降に固定する。`LANGFLOW_AUTO_LOGIN` を `true` にしない |
| Flowise | 先に owner を登録する。`TRUST_PROXY` をプロキシのアドレスにする |

## n8n: ログインなしで owner を作れる

n8n は、最初に owner（管理者）を作るまでの間、owner を作る API を認証なしで受け付けます（[owner.controller.ts L25-29](https://github.com/n8n-io/n8n/blob/n8n@2.44.5/packages/cli/src/controllers/owner.controller.ts#L25-L29)、[ownership.service.ts L227-232](https://github.com/n8n-io/n8n/blob/n8n@2.44.5/packages/cli/src/services/ownership.service.ts#L227-L232)）。条件は「まだ owner がいないこと」だけです。

```sh
curl -s http://127.0.0.1:5678/rest/settings | jq .data.userManagement.showSetupOnFirstLoad
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:5678/rest/owner/setup \
  -H 'content-type: application/json' \
  -d '{"email":"lab-owner@example.com","firstName":"Lab","lastName":"Owner","password":"Lab-Owner-Passw0rd"}'
```

| 確かめたこと | 結果 |
|---|---|
| ログインなしで `GET /rest/settings` | `showSetupOnFirstLoad: true` |
| ログインなしで `POST /rest/owner/setup` | 200。送ったメールアドレスで owner ができた |
| もう一度 `POST /rest/owner/setup` | 400 `Instance owner already setup` |
| owner を作ったあと、ログインなしで `GET /rest/workflows` | 401 |

`/rest/settings` は誰でも読めるので、「この n8n にはまだ owner がいない」ことが外から分かります。owner を作ったあとは、ほかの API は 401 になりました。危ないのは、立ててから owner を作るまでの間です。

`.env` には、`POSTGRES_PASSWORD=changePassword` や `RUNNERS_AUTH_TOKEN=changeRunnerAuthToken` のような例の値が入っています。Postgres には実際に `changePassword` でログインできました。

なお、n8n の基本認証（`N8N_BASIC_AUTH_*`）は 2023 年 6 月の [#6362](https://github.com/n8n-io/n8n/pull/6362) で削除されています。今の n8n でこの変数を設定しても、何も変わりません。

## Open WebUI: 最初にサインアップした人が admin

Open WebUI は、最初に登録したユーザーを admin にして、そのあとのサインアップを止めます（[auths.py L811-827](https://github.com/open-webui/open-webui/blob/v0.12.3/backend/open_webui/routers/auths.py#L811-L827)）。

```sh
curl -s http://127.0.0.1:3000/api/config | jq .onboarding
curl -s -X POST http://127.0.0.1:3000/api/v1/auths/signup -H 'content-type: application/json' \
  -d '{"name":"first","email":"first@example.com","password":"Lab-First-Passw0rd"}' | jq .role
```

| 確かめたこと | 結果 |
|---|---|
| ログインなしで `GET /api/config` | `onboarding: true` |
| 最初の `POST /api/v1/auths/signup` | 200、`role: admin` |
| 2 人目の `POST /api/v1/auths/signup` | 403 |

n8n と同じで、`/api/config` から「まだ誰も登録していない」ことが分かります。`WEBUI_ADMIN_EMAIL` と `WEBUI_ADMIN_PASSWORD` を設定すると、起動時に admin が作られてサインアップも止まります（[env.py L804-806](https://github.com/open-webui/open-webui/blob/v0.12.3/backend/open_webui/env.py#L804-L806)）。

## LiteLLM: マスターキーがないと起動しない

LiteLLM は、マスターキーが未設定・空・`sk-1234` のときは起動を拒否します（[master_key_boot_check.py](https://github.com/BerriAI/litellm/blob/v1.106.2/litellm/proxy/auth/master_key_boot_check.py#L14-L22)）。公式の `.env.example` は `LITELLM_MASTER_KEY = ""` なので、そのまま起動すると次のように止まりました。

```text
LiteLLM proxy refused to start: the master key is empty.
```

マスターキーを設定して起動し直すと、`/health` と `/metrics` はキーなしでは 401 でした。安全側に倒した既定です。

一方、compose ファイルには `DATABASE_URL: "postgresql://llmproxy:dbpassword9090@db:5432/litellm"` が直接書かれていて、Postgres は `5432:5432` で全インターフェースに公開されています。実際に `dbpassword9090` でログインできました。Postgres にはキーのハッシュや、暗号化されたプロバイダーの認証情報が入ります。

`LITELLM_SALT_KEY` を設定しないと、その暗号化にもマスターキーが使われます（[encrypt_decrypt_utils.py L32-40](https://github.com/BerriAI/litellm/blob/v1.106.2/litellm/proxy/common_utils/encrypt_decrypt_utils.py#L32-L40)）。

## Langflow: 既定では安全、ただし 1.10.2 より前のイメージに注意

Langflow のコードの既定は今も `AUTO_LOGIN=True` です（[auth.py L96-104](https://github.com/langflow-ai/langflow/blob/v1.12.7/src/lfx/src/lfx/services/settings/auth.py#L96-L104)）。公式のイメージは 1.10.2 から `LANGFLOW_AUTO_LOGIN=false` を入れていて（[build_and_push.Dockerfile L234-235](https://github.com/langflow-ai/langflow/blob/v1.12.7/docker/build_and_push.Dockerfile#L234-L235)）、イメージで動かす限りは無効です。

| 確かめたこと | 結果 |
|---|---|
| 1.12.7 のイメージのまま `GET /api/v1/auto_login` | 403 |
| `LANGFLOW_AUTO_LOGIN=true` にして同じリクエスト | 200。スーパーユーザーのアクセストークンが返った |
| 例のパスワード `langflow` で Postgres にログイン | できた |

公式の `docker_example` はイメージが `langflowai/langflow:latest` なので、今 pull すれば安全な既定になります。古いタグに固定しているなら注意が必要です。2026 年 10 月 30 日の時点で、CISA の [悪用が確認された脆弱性のカタログ](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)（KEV）には Langflow の脆弱性が 6 件載っています。

| CVE | KEV に載った日 | 対象の版 |
|---|---|---|
| CVE-2025-3248 | 2025-05-05 | 1.3.0 未満 |
| CVE-2026-33017 | 2026-03-25 | 1.8.2 以前 |
| CVE-2025-34291 | 2026-05-21 | 1.6.9 以前 |
| CVE-2026-55255 | 2026-07-07 | 1.9.1 未満 |
| CVE-2026-0770 | 2026-07-21 | 1.7.3 以前 |
| CVE-2026-9198 | 2026-08-04 | 1.10.0 以前 |

対象の版は GitHub Advisory Database の記載です。KEV の 6 件を外すだけなら 1.10.1 以降で足りますが、自動ログインが既定で無効になるのは 1.10.2 から、MCP の stdio サーバーの設定からのコマンド実行（[GHSA-w794-rj3p-xv45](https://github.com/advisories/GHSA-w794-rj3p-xv45)、critical）が直ったのは 1.10.3 からです。固定するなら 1.10.3 以降にします。

## Flowise: 公式の手順では起動しなかった

Flowise も、最初に登録した人が owner になる作りです（[account.service.ts L178-197](https://github.com/FlowiseAI/Flowise/blob/flowise%403.1.4/packages/server/src/enterprise/services/account.service.ts#L178-L197)）。これを確かめるつもりでしたが、起動できませんでした。

1. 公式の compose と `.env.example` のままでは、ログのディレクトリを作るところで `mkdir ''` に失敗して落ちます。compose が全変数を `LOG_PATH=${LOG_PATH}` の形で渡すので、`.env.example` でコメントアウトされている変数が空文字になるためです（[#6030](https://github.com/FlowiseAI/Flowise/issues/6030)、修正の PR [#6031](https://github.com/FlowiseAI/Flowise/pull/6031) はまだ開いています）。
2. issue のとおりパスを `.env` に入れると先へ進みますが、3.1.4 のイメージ自体が依存パッケージのエラーで起動に失敗しました。これも既知の問題です（[#6688](https://github.com/FlowiseAI/Flowise/issues/6688)）。

そのため Flowise は、ソースを読んだ結果だけを点検ツールのルールにしています。なお Flowise の `FLOWISE_USERNAME` / `FLOWISE_PASSWORD` による基本認証は、ドキュメントで 3.0.1 から非推奨とされていて（[app-level.md](https://github.com/FlowiseAI/FlowiseDocs/blob/32d7f0cc7929bbd9e592cbc8e7a69bb82625f418/en/configuration/authorization/app-level.md#L11-L13)）、3.1.4 のソースにはもう参照がありません。設定しても効きません。

## 設定から見つける

ここまでのことは、compose ファイルと `.env` を読めば分かります。`ai-selfhost-audit` は、compose ファイルの `image` から製品を見分けて、製品ごとの設定とイメージの版を調べます。Docker にもネットワークにも触りません。

```sh
go install github.com/OTA-EITA/ai-selfhost-audit/cmd/ai-selfhost-audit@latest
cd your-compose-dir
ai-selfhost-audit
```

n8n の公式の compose ファイルに使うと、次のようになります。

```text
SEVERITY  ID      SERVICE   LOCATION               FINDING
HIGH      N8N010  n8n       docker-compose.yml:27  n8n version has an unpatched expression sandbox escape
MEDIUM    GEN007  n8n       .env:8                 Database password is an example from an official compose file
MEDIUM    GEN007  postgres  .env:4                 Database password is an example from an official compose file
MEDIUM    GEN007  postgres  .env:8                 Database password is an example from an official compose file
MEDIUM    N8N001  n8n       docker-compose.yml:27  First visitor can claim the n8n owner account
MEDIUM    N8N003  n8n       .env:10                Task runner auth token is an example value
MEDIUM    N8N008  n8n       docker-compose.yml:27  n8n SSRF protection is off
INFO      GEN002  n8n       docker-compose.yml:42  Application port published on all host interfaces

8 findings: 1 high, 6 medium, 0 low, 1 info
```

HIGH の N8N010 は、`.env` が指定している 2.44.5 に、まだ修正されていない式のサンドボックス脱出（[GHSA-gx3v-3x3v-f8r5](https://github.com/n8n-io/n8n/security/advisories/GHSA-gx3v-3x3v-f8r5)）があるという指摘です。2.44 系には修正版がなく、2.45.5 以降に上げる必要があります。

ルールは全部で 50 個です。製品ごとに、上で見た「最初の訪問者」「例の値」のほか、コード実行やファイルアクセスの制限を外す設定、既知の脆弱性がある版などを見ます。各ルールには、根拠になるソースの行や advisory へのリンクを付けました。

## 確かめていないこと

- Flowise の「最初に登録した人が owner」の挙動。上のとおり起動できなかったので、ソースを読んだだけです
- 公開されている「入れたばかり」のホストが、実際にこの時間差で残ったものかどうか。立ててから管理者を作るまでの間に外から見えていれば同じ状態になる、というところまでしか言えません
- 公式の compose 以外の立て方（Helm チャート、各社のマネージド版、ワンクリックのテンプレート）

## 参考

- [From enterprise chatbots to gooner caves: exposed AI infrastructure is rampant（Intruder）](https://www.intruder.io/research/from-enterprise-chatbots-to-gooner-caves-exposed-ai-infrastructure-is-rampant)
- [n8n-io/n8n-hosting withPostgres](https://github.com/n8n-io/n8n-hosting/tree/b690a87c814aed2f56981047fb617d22e488b861/docker-compose/withPostgres)
- [open-webui/open-webui v0.12.3](https://github.com/open-webui/open-webui/tree/v0.12.3)
- [BerriAI/litellm v1.106.2](https://github.com/BerriAI/litellm/tree/v1.106.2)
- [langflow-ai/langflow v1.12.7](https://github.com/langflow-ai/langflow/tree/v1.12.7)
- [FlowiseAI/Flowise 3.1.4](https://github.com/FlowiseAI/Flowise/tree/flowise%403.1.4)、[#6030](https://github.com/FlowiseAI/Flowise/issues/6030)、[#6688](https://github.com/FlowiseAI/Flowise/issues/6688)
- [CISA Known Exploited Vulnerabilities Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
- [GitHub Advisory Database: Langflow](https://github.com/advisories?query=langflow)
- [OTA-EITA/ai-selfhost-audit](https://github.com/OTA-EITA/ai-selfhost-audit)
