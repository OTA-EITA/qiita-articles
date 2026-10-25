# kinesis-poison-pill

Qiita 記事「壊れた決済イベント 1 件で、後ろの不正な決済はどうなるのか。Kinesis + Lambda のリトライ設定を LocalStack で比べた」の再現コードです。
LocalStack 上で、1 シャードの Kinesis に架空の決済イベントを流し、途中に壊れたイベント（JSON として読めない 1 件）と、その直後に不正な決済を 1 件入れます。Lambda のイベントソースマッピング（ESM）の設定ごとに、不正な決済が検知されるまでの時間や、取りこぼし・重複を記録します。

データはすべて架空です（`pay-000123`、`card-TEST-0007`、`shop-DEMO-03` のような ID のみ）。

## 必要なもの

- Docker（Lambda の実行に Docker ソケットを使います）
- Python 3.10 以上と boto3（図を描くなら matplotlib も）

## 注意

- `localstack/localstack:4.14.0` は、認証トークンなしで起動できる最後のコミュニティ版イメージです（2026-02-26 公開）。2026.03.0 以降はトークン（無料の Hobby プランは非商用・アカウント登録が必要）が要ります。4.14.0 にはもうセキュリティ修正が入らないので、ポートは 127.0.0.1 にだけ公開しています。
- AWS アカウントは使いません。`run.py` は `AWS_PROFILE` を消し、ダミーの認証情報（`test` / `test`）で `http://127.0.0.1:4566` にだけ接続します。
- LocalStack 4.14.0 では `BisectBatchOnFunctionError` が実装されていません（設定はできますが、分割されません）。リトライの間隔も AWS とは別物です。

## 使い方

```bash
docker compose up -d
python -m venv .venv && .venv/bin/pip install boto3

.venv/bin/python run.py default --drain 210   # 既定の設定（約 6 分）
.venv/bin/python run.py retry2                # MaximumRetryAttempts=2 + 失敗時の送信先 SQS
.venv/bin/python run.py bisect                # retry2 + BisectBatchOnFunctionError
.venv/bin/python run.py partial               # retry2 + ReportBatchItemFailures（壊れたイベントで処理を止める）
.venv/bin/python run.py partial_all           # retry2 + ReportBatchItemFailures（残りを処理してから報告する）

.venv/bin/python analyze.py                   # results/*.json を集計
.venv/bin/pip install matplotlib && .venv/bin/python plot.py   # figures/ に記事の図を出力

docker compose down
# LocalStack が起動した Lambda 用のコンテナが残ることがあるので消す
docker ps -aq --filter name=kinesis-poison-pill-localstack-lambda | xargs -r docker rm -f
```

各シナリオは新しいストリーム・関数・キューを作るので、続けて実行しても互いに影響しません。

`results/` には、記事を書いたときの実行結果（2026-10-25、各シナリオ 1 回ずつ）をそのまま置いています。
