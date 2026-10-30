---
title: 壊れた決済イベント 1 件で、後ろの不正な決済はどうなるのか。Kinesis + Lambda のリトライ設定を LocalStack で比べた
tags:
  - AWS
  - Kinesis
  - lambda
  - SRE
  - LocalStack
private: false
updated_at: '2026-10-30T21:29:57+09:00'
id: ed173fb261c971c2d4c7
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

Kinesis Data Streams と Lambda で決済の不正検知を組んだとき、壊れたイベントが 1 件入ると、すぐ後ろの不正な決済はどうなるのか。LocalStack でリトライの設定を 5 通り試した結論は次の 3 つです。

- 既定の設定では、そのシャードの判定が止まった。後ろの不正な決済は、観測した 286 秒の間、判定されなかった
- `MaximumRetryAttempts` を設定すると止まらなくなるが、壊れたイベントと同じバッチにいた不正な決済も一緒に捨てられた
- すぐに検知できたのは、壊れたイベントを飛ばして残りを判定し、最後に `ReportBatchItemFailures` で報告する書き方だけ。その場合も同じ決済が 3 回判定された

Kinesis と Lambda でストリーム処理を作る人や運用する人、特に SRE として「何を設定し、何を監視していれば気づけるか」を決めたい人に向けて書いています。持ち帰れるものは「やること」のチェック表にまとめました。

自分は Kinesis を本番で運用したことはありません。AWS のアカウントは使わず、LocalStack で再現しました。決済データはすべて架空のものです。

設定ごとの挙動そのものは、クラスメソッドの quiver さんが実際の AWS で確認した記事がすでにあります（最後に載せています）。この記事では、少し違うところを見ます。

- 壊れたイベントの「すぐ後ろ」にいた不正な決済は、いつ判定されるのか。そもそも判定されるのか
- 同じ決済が何回判定されるのか（不正アラートが何回飛ぶのか）
- SRE として、何を監視していれば気づけるのか

## 何が起きるのか

Lambda のドキュメントには、Kinesis のシャードについてこう書かれています。

> Lambda processes records in each shard in order. It stops processing additional records in a shard if your function returns an error.

関数がエラーを返すと、そのシャードの後続のレコードは処理されません。そして、何回リトライするかを決める `MaximumRetryAttempts` の既定値は無制限です。

> The default value is infinite (-1). When set to infinite (-1), failed records are retried until the record expires.

レコードの保持期間は、既定で 24 時間、最大で 365 日です（2026 年 10 月現在）。つまり既定の設定のままだと、JSON として読めないイベントが 1 件入っただけで、そのシャードの決済はレコードの期限が切れるまで判定されません。Lambda のドキュメントにも「既定の設定では、1 件の悪いレコードが最大 1 週間シャードを止めうる」と書かれています（保持期間の既定は 24 時間なので、保持期間を延ばしている場合の話だと思います）。

## 試した環境

- 2026 年 10 月 25 日、macOS、Docker Desktop
- LocalStack 4.14.0（`localstack/localstack:4.14.0`）、Lambda のランタイムは `python3.12`
- Kinesis のストリームは 1 シャード。イベントソースマッピングは `BatchSize` などを既定のままにして、`StartingPosition` だけ `TRIM_HORIZON` にしました

LocalStack は、2026 年 3 月 23 日の 2026.03.0 から、起動に認証トークンが必要になりました。トークンなしで起動できるコミュニティ版は 4.14.0（2026 年 2 月 26 日公開）が最後です。新しい版を無料で使うには、非商用向けの Hobby プラン（アカウント登録が必要）になります（2026 年 10 月現在）。4.14.0 にはもうセキュリティ修正が入らないので、今回はポートを `127.0.0.1` にだけ公開して、検証が終わったらコンテナを消しています。

```yaml:compose.yaml
services:
  localstack:
    image: localstack/localstack:4.14.0
    ports:
      - "127.0.0.1:4566:4566"
    environment:
      - SERVICES=kinesis,lambda,sqs,iam,logs,sts
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

### 流したデータ

0.2 秒ごとに 1 件、90 秒間、架空の決済イベントを入れました。20 秒の時点で、途中で切れた JSON（壊れたイベント）を 1 件入れ、その直後に不正な決済を 1 件入れています。

```json
{"payment_id": "pay-000090", "card_id": "card-TEST-0040", "merchant_id": "shop-DEMO-06",
 "amount": 480000, "card_country": "JP", "ip_country": "XX"}
```

```text
{"payment_id": "pay-POISON", "amount":
```

Lambda は、金額が 30 万円以上か、カードの国と IP の国が違えば「不正の疑い」とするだけの単純なものです。壊れたイベントは `json.loads` で例外になり、そのまま関数のエラーになります。

```python:handler.py（抜粋）
    for record in records:
        k = record["kinesis"]
        raw = base64.b64decode(k["data"])
        try:
            payment = json.loads(raw)
            reasons = score(payment)
        except Exception as e:  # malformed event = poison pill
            print(json.dumps({"kind": "poison", ...}))  # 時刻などをログに出す
            ...
            raise

        print(json.dumps({"kind": "scored", ...}))  # 判定した時刻と結果をログに出す
```

### 測り方

LocalStack 4.14.0 は、イベントソースマッピングの CloudWatch メトリクス（`IteratorAge` など）を出しません。`IteratorAge` は、ストリームがレコードを受け取ってから Lambda に渡すまでの時間で、処理がどれだけ遅れているかの目安になる値です。そこで、Lambda が 1 件判定するたびに時刻をログに出し、送った時刻と突き合わせて次の値を自分で計算しました。

- 不正な決済が、送ってから何秒で判定されたか（判定されなかったか）
- 同じ決済が何回判定されたか
- その時点で「判定も破棄もされずに残っている、いちばん古いレコード」が何秒待っているか。`IteratorAge` に近い値として使っています

各シナリオ 1 回ずつの結果です。コードと実行結果の JSON は [GitHub に置きました](https://github.com/OTA-EITA/qiita-articles/tree/main/samples/kinesis-poison-pill)。シナリオごとのイベントソースマッピングの設定は [run.py の `SCENARIOS`](https://github.com/OTA-EITA/qiita-articles/blob/main/samples/kinesis-poison-pill/run.py#L34-L40) に、作成している箇所は [`create_event_source_mapping` の呼び出し](https://github.com/OTA-EITA/qiita-articles/blob/main/samples/kinesis-poison-pill/run.py#L94-L102) にあります。

## 結果

試したのは次の 5 つです。2 番目以降は、すべて `MaximumRetryAttempts=2` と、失敗時の送信先（on-failure destination）に SQS を設定しています。「＋」は、2 番目の設定にそれを足したものです。

| 設定 | 不正な決済 | 判定されなかった決済 | 2 回以上判定された決済 |
|---|---|---|---|
| 既定 | 286 秒の観測中、判定されず | 308 件 | 4 件（各 15 回） |
| `MaximumRetryAttempts=2` | 判定されず SQS へ | 1 件（不正な決済） | 4 件（各 3 回） |
| ＋`BisectBatchOnFunctionError` | 同上（LocalStack では分割されない） | 1 件 | 4 件（各 3 回） |
| ＋`ReportBatchItemFailures`（壊れた所で止める） | 判定されず SQS へ | 1 件 | なし |
| ＋`ReportBatchItemFailures`（残りを処理してから報告） | 0.07 秒で検知、アラート 3 回 | なし | 1 件（不正な決済が 3 回） |

壊れたイベントを含むバッチが、呼び出しのたびにどう扱われたかを並べると、こうなりました。

![壊れたイベントを含むバッチの扱われ方](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/kinesis-poison-pill/poison-batch.png)

そして、残っているいちばん古いレコードの待ち時間です。

![未処理で残っている最も古いレコードの待ち時間](https://raw.githubusercontent.com/OTA-EITA/qiita-articles/main/images/kinesis-poison-pill/oldest-pending-age.png)

下の拡大図のギザギザは、LocalStack がシャードを 1 秒ごとに読みにいくことによるものです。

### 既定の設定：不正な決済は判定されないまま

20 秒で壊れたイベントが届いてから、同じバッチを 15 回失敗し続けたところで観測を打ち切りました（286 秒）。その間、不正な決済を含む後ろの 308 件は 1 件も判定されていません。待ち時間は時間に比例して伸びるだけで、自然には戻りません。

もう一つ見落としやすいのが、同じバッチの中で壊れたイベントより前にあった 4 件です。リトライのたびに先頭から判定し直すので、この 4 件は 15 回ずつ判定されました。判定のたびに何かを書き込んだり通知したりする処理なら、15 回分の副作用が出ます。

リトライの間隔は、0.3 秒、1.0 秒、1.2 秒…と伸びて、最後は 1 分前後になりました。これは LocalStack 自身の待ち方（ソースコードを見ると、0.5 秒から 1.5 倍ずつ、上限 60 秒）で、AWS の間隔とは違います。AWS での間隔は、quiver さんの記事に実測があります。

### MaximumRetryAttempts=2：止まらなくなるが、不正な決済ごと捨てられる

最初の試行と 2 回のリトライ（`approximateInvokeCount` は 3）で諦め、壊れたイベントから 2 秒ほどで処理が先に進みました。待ち時間のグラフも、すぐに元に戻っています。

ただし、捨てられたのは壊れたイベント 1 件ではなく、それを含むバッチ全体（6 件）でした。その中に、すぐ後ろにいた不正な決済も入っています。SQS に届いたのは次のようなメッセージで、決済の中身は入っていません。

```json:SQS に届いたメッセージ（実物）
{
  "requestContext": {
    "requestId": "1611d034-e152-4ae5-ba31-eacdb4833f58",
    "functionArn": "arn:aws:lambda:ap-northeast-1:000000000000:function:retry2-d09b55",
    "condition": "RetryAttemptsExhausted",
    "approximateInvokeCount": 3
  },
  "responseContext": {
    "statusCode": 200,
    "executedVersion": "$LATEST",
    "functionError": "Unhandled"
  },
  "KinesisBatchInfo": {
    "approximateArrivalOfFirstRecord": "2026-10-25T12:14:08.140Z",
    "approximateArrivalOfLastRecord": "2026-10-25T12:14:09.051Z",
    "batchSize": 6,
    "endSequenceNumber": "49679596257919839594449880635047489392422372888138481666",
    "shardId": "shardId-000000000000",
    "startSequenceNumber": "49679596257919839594449880635041444763324299673545474050",
    "streamArn": "arn:aws:kinesis:ap-northeast-1:000000000000:stream/retry2-d09b55"
  },
  "timestamp": "2026-10-25T12:14:10.529Z",
  "version": "1.0"
}
```

これは AWS の仕様どおりで、SQS や SNS の送信先にはメタデータしか送られず、中身はシーケンス番号を使ってストリームから取り直す必要があります。ドキュメントには、期限が切れて失われる前に取り出すように、と書かれています。S3 を送信先にした場合だけ、元のレコードも一緒に送られます。

つまり、このままだと不正な決済は「判定されないまま、シーケンス番号の範囲として SQS に置かれている」状態になります。誰かが SQS を見て、保持期間内にストリームから取り直して判定し直さない限り、検知されません。

なお、バッチの大きさはそのときの流量で決まります。今回は 1 秒に 5 件程度だったので 6 件でしたが、流量が多ければ、最大で `BatchSize`（既定 100）件がまとめて捨てられることになります。

### BisectBatchOnFunctionError：LocalStack では確かめられなかった

AWS では、失敗したバッチを半分に分けてリトライし、悪いレコードを絞り込む設定です。分割はリトライの回数を消費しない、とドキュメントにあります。うまく働けば、不正な決済は壊れたイベントと別のバッチに分かれて判定されるはずです。

ところが LocalStack 4.14.0 では、設定は受け付けるものの、動きは上の `MaximumRetryAttempts=2` とまったく同じでした。LocalStack のドキュメントでも、ストリームでの `BisectBatchOnFunctionError` は「未実装」となっていて、ソースコードにも同じコメントがあります。ここは実機で確かめる必要があります（quiver さんの記事で、AWS 上で分割される様子が確認されています）。

### ReportBatchItemFailures（壊れた所で止めて報告）：重複はなくなるが、やはり捨てられる

`ReportBatchItemFailures` を有効にすると、関数は「どのレコードから失敗したか」を返せます。AWS のドキュメントにあるサンプルコードは、言語によって書き方が違いますが、JavaScript や Java などは失敗したレコードを見つけた時点でそのシーケンス番号を返して終わる書き方です。まずそのとおりにしました。

前の 4 件は成功扱いになり、リトライは壊れたイベントから始まります。そのため、重複して判定される決済はなくなりました。

一方で、リトライされるバッチは「壊れたイベントと不正な決済」の 2 件で、毎回壊れたイベントで止まるので、不正な決済には一度も届きません。3 回目で諦めたとき、この 2 件の範囲がまとめて SQS に送られました。不正な決済が判定されないことは変わりません。

### ReportBatchItemFailures（残りを処理してから報告）：検知はすぐ、ただしアラートは 3 回

最後に、壊れたイベントを飛ばして残りの判定を続け、最後に壊れたイベントだけを報告する書き方にしました。

```python
except Exception:
    failures.append({"itemIdentifier": k["sequenceNumber"]})
    continue
...
return {"batchItemFailures": failures}
```

不正な決済は、送ってから 0.07 秒で検知されました。今回の 5 つの中で、すぐに検知できたのはこれだけです。

ただ、Lambda は報告されたレコード以降を全部リトライします。ドキュメントにも「最も小さいシーケンス番号をチェックポイントにして、そこから全部リトライする」と書かれています。そのため、不正な決済はリトライのたびに判定し直され、不正アラートが 3 回出ました。さらに、最後に SQS に送られた範囲にも不正な決済が含まれていたので、SQS から取り直して判定し直す仕組みを作ると、4 回目のアラートが出ることになります。

## やること

今回の結果から、自分ならこうするだろう、と思ったことをまとめます。設定でできるのは「止まらないようにする」ところまでで、何を捨てたかを拾い直したり、アラートを 1 回にまとめたりするのはアプリと運用の仕事です。

| 区分 | やること | 理由（今回の結果） |
|---|---|---|
| 設定 | `MaximumRetryAttempts` を有限の値にする | 既定の無制限では、シャードの判定が止まり続けた |
| 設定 | 失敗時の送信先を設定する。中身ごと残したいなら S3 | SQS と SNS には、シーケンス番号の範囲しか届かない |
| アプリ | 何度リトライしても直らないエラーは、関数の中で捕まえて退避し、成功扱いにする | 関数のエラーにすると、同じバッチの後ろの決済が巻き添えで捨てられた |
| アプリ | `ReportBatchItemFailures` を使うなら、壊れた所で止めず、残りを処理してから報告する | 壊れた所で止めると、後ろの不正な決済に一度も届かなかった |
| アプリ | アラートを `payment_id` などで冪等にする | すぐ検知できた書き方でも、同じ決済が 3 回判定された |
| 監視 | `IteratorAge` のアラームを、検知に許される遅れからしきい値を決めて置く | 既定の設定で詰まったときは、これが伸び続ける |
| 監視 | 失敗時の送信先と、`DroppedEventCount` などのメトリクスも監視する | `MaximumRetryAttempts` を設定すると `IteratorAge` はすぐ戻り、捨てられても鳴らない |
| 監視 | 送信先に届いたら、保持期間内にストリームから取り直す手順を決めておく | 中身はストリームにしか残っていない |

### 壊れたデータは関数のエラーにしない

JSON が読めない、必須の項目がないといった「何度リトライしても直らない」エラーは、関数の中で捕まえて、中身ごと別のキューなどに退避し、そのレコードは成功扱いにします。リトライが役に立つのは、下流の API が一時的に落ちているような場合だけなので、そういうエラーだけを関数のエラーとして返します。こうしておけば、壊れたデータで後ろの決済が巻き添えになることはありません。

そのうえで、`MaximumRetryAttempts` と失敗時の送信先は保険として設定しておきます。

### アラートは冪等にする

上の最後のパターンのように、正しく作っても同じ決済は複数回判定されます。Lambda のドキュメントでも、イベントソースマッピングは「少なくとも 1 回」の処理で、重複が起こりうるので冪等にするよう強く勧めています。`payment_id` をキーにして「この決済のアラートはもう出したか」を DynamoDB の条件付き書き込みなどで確認してから通知する、といった形です。Powertools for AWS Lambda の Idempotency ユーティリティも使えます。

### IteratorAge だけでは足りない

既定の設定で詰まったときは、`IteratorAge` が伸び続けるので気づけます。Kinesis 側の `GetRecords.IteratorAgeMilliseconds` について、Kinesis のドキュメントは、保持期間の 50% を超えるとレコードの期限切れでデータを失うおそれがあるとして、Maximum の統計でアラームを設定するよう勧めています。ただ、不正検知のように数秒で判定したい処理なら、しきい値は保持期間ではなく、検知に許される遅れ（数十秒〜数分）から決めるべきだと思います。

一方で、`MaximumRetryAttempts` を設定した場合は、上のグラフのとおり待ち時間は 2 秒ほどで元に戻ります。不正な決済が捨てられていても、`IteratorAge` のアラームは鳴りません。

### 捨てられた側を見る

そこで、失敗時の送信先も監視します。

- SQS に送っているなら、そのキューの `ApproximateNumberOfMessagesVisible` が 0 より大きくなったら通知する。不正検知では 1 件でも人が見るべきだと思います
- イベントソースマッピングのメトリクス（`MetricsConfig` で `EventCount` を有効にしたとき）の `OnFailureDestinationDeliveredEventCount` と `DroppedEventCount`
- 送信先への配送に失敗したときの `DestinationDeliveryFailures`

### DroppedEventCount の死角

`DroppedEventCount` には注意が必要です。ドキュメントによると、これは `MaximumRecordAgeInSeconds` や `MaximumRetryAttempts` を超えて捨てたレコードの数で、ストリームの保持期間切れで失われたレコードは含まれません。

> Importantly, this doesn't include the number of records that expire due to exceeding your event source's retention settings.

つまり、既定の設定のまま 24 時間詰まって、壊れたイベントも後ろの決済もまとめて期限切れになった場合、`DroppedEventCount` には現れません。その状況に気づけるのは `IteratorAge` だけです。設定を変えていないシステムほど、`IteratorAge` のアラームが唯一の頼りになります。

### SQS に届いたら時間との勝負

SQS に届くのはシーケンス番号の範囲だけで、中身はストリームから取り直す必要があります。取り直せるのは保持期間内だけなので、既定の 24 時間なら、夜中に届いた通知を翌日の夕方に見ても間に合わないかもしれません。Yan Cui さんの記事では、SNS 経由で別の Lambda を挟み、届いた時点で中身を取ってきて付け足す方法が紹介されています。S3 を送信先にすれば中身ごと残るので、それも選択肢です。

## 確かめていないこと

今回の数字は、あくまで LocalStack 4.14.0 というエミュレーターで、各シナリオ 1 回ずつ試した結果です。分かっている AWS との違いと、確かめられていないことを書いておきます。

- `BisectBatchOnFunctionError` は実装されていません。設定は通りますが、バッチは分割されません。AWS で不正な決済が別のバッチに分かれて判定されるかは、実機で同じ測り方をしないと分かりません
- イベントソースマッピングの CloudWatch メトリクスは出ません。`IteratorAge` に当たる値は、ログの時刻から自分で計算しました。上の監視の話は、AWS のドキュメントを読んで考えたもので、実際にアラームが鳴るところは見ていません
- リトライの間隔は LocalStack 独自のものです（0.5 秒から 1.5 倍ずつ、ばらつき ±50%、上限 60 秒）
- LocalStack は、最初に読んだバッチをそのまま覚えておいてリトライします。AWS がリトライのときにレコードを読み直してバッチの範囲が変わるのかどうかは、確かめられていません。そのため、SQS に送られる範囲（今回の 6 件や 2 件）は、AWS では違う可能性があります
- `ParallelizationFactor` も未実装なので、今回は試していません

逆に、`MaximumRetryAttempts` で 3 回目に諦めること、SQS に届くメッセージの形（`condition` が `RetryAttemptsExhausted`、`KinesisBatchInfo` にシーケンス番号の範囲）、`ReportBatchItemFailures` で報告したレコードからリトライされることは、ドキュメントに書かれている挙動と一致していました。

## 参考

- [KinesisデータストリームをLambdaで処理する時のエラー制御方法をまとめてみた（DevelopersIO、quiver さん）](https://dev.classmethod.jp/articles/how-to-handle-kinesis-data-stream-errors/)：AWS 上で、リトライ回数・バイセクト・部分バッチレスポンスの挙動とリトライ間隔を確認している記事
- [The one mistake everyone makes when using Kinesis with Lambda（Yan Cui）](https://theburningmonk.com/2023/12/the-one-mistake-everyone-makes-when-using-kinesis-with-lambda/)：失敗時の送信先に中身が入らない問題と、その補い方
- [Optimizing batch processing with custom checkpoints in AWS Lambda（AWS Compute Blog）](https://aws.amazon.com/blogs/compute/optimizing-batch-processing-with-custom-checkpoints-in-aws-lambda/)
- [Lambdaトリガー「Kinesis」にある再試行(Retry attempts) パラメタ が「-1」の場合どういう挙動をするか（@wagasa2 さん）](https://qiita.com/wagasa2/items/fcbccfbd62a1e312a576)
- [Lambdaのイベントソース処理のリトライ設計値をまとめる(Streams/SQS編)（@neruneruo さん）](https://qiita.com/neruneruo/items/367de78995536890d648)
- [Kinesis Data Streamsを使う前に知っておきたかったこと（Zenn）](https://zenn.dev/aminevsky/articles/2f0a7ebcc0359b)
- [Using Lambda to process records from Amazon Kinesis Data Streams](https://docs.aws.amazon.com/lambda/latest/dg/with-kinesis.html)
- [Retain discarded batch records for a Kinesis Data Streams event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/kinesis-on-failure-destination.html)
- [Configuring partial batch response with Kinesis Data Streams and Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-kinesis-batchfailurereporting.html)
- [CreateEventSourceMapping（API リファレンス）](https://docs.aws.amazon.com/lambda/latest/api/API_CreateEventSourceMapping.html)
- [Types of metrics for Lambda functions（IteratorAge、DroppedEventCount など）](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics-types.html)
- [Monitor the Amazon Kinesis Data Streams service with Amazon CloudWatch](https://docs.aws.amazon.com/streams/latest/dev/monitoring-with-cloudwatch.html)
- [Change the data retention period（Kinesis Data Streams）](https://docs.aws.amazon.com/streams/latest/dev/kinesis-extended-retention.html)
- [Idempotency（Powertools for AWS Lambda (Python)）](https://docs.aws.amazon.com/powertools/python/latest/utilities/idempotency/)
- [LocalStack: Lambda（イベントソースマッピングの対応状況）](https://docs.localstack.cloud/aws/services/lambda/)
- [LocalStack for AWS Is Moving to a Single Image. Here are Your Next Steps（LocalStack Blog）](https://blog.localstack.cloud/localstack-single-image-next-steps/)
