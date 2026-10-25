"""Reproduce a poison pill blocking a Kinesis shard on LocalStack.

usage: python run.py <scenario> [--duration 90] [--poison-at 20] [--drain 60]

scenarios:
  default  ESM defaults (MaximumRetryAttempts=-1)
  retry2   MaximumRetryAttempts=2 + on-failure SQS destination
  bisect   retry2 + BisectBatchOnFunctionError
  partial      retry2 + ReportBatchItemFailures, function stops at the bad record
  partial_all  retry2 + ReportBatchItemFailures, function scores the rest, then reports

Talks only to LocalStack on 127.0.0.1:4566 with dummy credentials.
"""

import argparse
import io
import json
import os
import time
import uuid
import zipfile

import boto3

for k in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_SESSION_TOKEN"):
    os.environ.pop(k, None)
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"

ENDPOINT = "http://127.0.0.1:4566"
REGION = "ap-northeast-1"
HERE = os.path.dirname(os.path.abspath(__file__))

SCENARIOS = {
    "default": dict(mode="raise", esm={}),
    "retry2": dict(mode="raise", esm={"MaximumRetryAttempts": 2}, dlq=True),
    "bisect": dict(mode="raise", esm={"MaximumRetryAttempts": 2, "BisectBatchOnFunctionError": True}, dlq=True),
    "partial": dict(mode="partial", esm={"MaximumRetryAttempts": 2, "FunctionResponseTypes": ["ReportBatchItemFailures"]}, dlq=True),
    "partial_all": dict(mode="partial_all", esm={"MaximumRetryAttempts": 2, "FunctionResponseTypes": ["ReportBatchItemFailures"]}, dlq=True),
}


def client(name):
    return boto3.client(name, endpoint_url=ENDPOINT, region_name=REGION)


def lambda_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.write(os.path.join(HERE, "lambda", "handler.py"), "handler.py")
    return buf.getvalue()


def payment(i, fraud=False):
    # Synthetic data only. IDs are obviously fake.
    return {
        "payment_id": f"pay-{i:06d}",
        "card_id": f"card-TEST-{i % 50:04d}",
        "merchant_id": f"shop-DEMO-{i % 7:02d}",
        "amount": 480_000 if fraud else 1_000 + (i * 37) % 20_000,
        "card_country": "JP",
        "ip_country": "XX" if fraud else "JP",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=SCENARIOS)
    ap.add_argument("--duration", type=float, default=90)
    ap.add_argument("--poison-at", type=float, default=20)
    ap.add_argument("--interval", type=float, default=0.2)
    ap.add_argument("--drain", type=float, default=60)
    args = ap.parse_args()
    sc = SCENARIOS[args.scenario]
    run_id = f"{args.scenario}-{uuid.uuid4().hex[:6]}"

    kinesis, lam, sqs, logs = client("kinesis"), client("lambda"), client("sqs"), client("logs")

    kinesis.create_stream(StreamName=run_id, ShardCount=1)
    kinesis.get_waiter("stream_exists").wait(StreamName=run_id)
    stream_arn = kinesis.describe_stream_summary(StreamName=run_id)["StreamDescriptionSummary"]["StreamARN"]

    lam.create_function(
        FunctionName=run_id,
        Runtime="python3.12",
        Handler="handler.handler",
        Role="arn:aws:iam::000000000000:role/lambda-role",
        Code={"ZipFile": lambda_zip()},
        Timeout=30,
        Environment={"Variables": {"MODE": sc["mode"]}},
    )
    lam.get_waiter("function_active_v2").wait(FunctionName=run_id)

    esm_args = dict(sc["esm"])
    queue_url = None
    if sc.get("dlq"):
        queue_url = sqs.create_queue(QueueName=f"{run_id}-onfailure")["QueueUrl"]
        q_arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        esm_args["DestinationConfig"] = {"OnFailure": {"Destination": q_arn}}
    esm = lam.create_event_source_mapping(
        FunctionName=run_id, EventSourceArn=stream_arn, StartingPosition="TRIM_HORIZON", **esm_args
    )
    while lam.get_event_source_mapping(UUID=esm["UUID"])["State"] != "Enabled":
        time.sleep(1)
    print("esm:", json.dumps({k: v for k, v in lam.get_event_source_mapping(UUID=esm["UUID"]).items()
                              if k in ("BatchSize", "MaximumRetryAttempts", "MaximumRecordAgeInSeconds",
                                       "BisectBatchOnFunctionError", "FunctionResponseTypes",
                                       "DestinationConfig", "ParallelizationFactor")}))

    # Produce a steady stream. One malformed event at --poison-at, the fraudulent
    # payment right after it in the same shard (single shard, so same partition doesn't matter).
    sent = []
    t0 = time.time()
    i = 0
    poisoned = False
    while time.time() - t0 < args.duration:
        if not poisoned and time.time() - t0 >= args.poison_at:
            r = kinesis.put_record(StreamName=run_id, PartitionKey="p",
                                   Data=b'{"payment_id": "pay-POISON", "amount": ')
            sent.append({"kind": "poison", "seq": r["SequenceNumber"], "t": time.time()})
            i += 1
            p = payment(i, fraud=True)
            r = kinesis.put_record(StreamName=run_id, PartitionKey="p", Data=json.dumps(p).encode())
            sent.append({"kind": "fraud", "payment_id": p["payment_id"], "seq": r["SequenceNumber"], "t": time.time()})
            poisoned = True
        else:
            i += 1
            p = payment(i)
            r = kinesis.put_record(StreamName=run_id, PartitionKey="p", Data=json.dumps(p).encode())
            sent.append({"kind": "good", "payment_id": p["payment_id"], "seq": r["SequenceNumber"], "t": time.time()})
        time.sleep(args.interval)
    print(f"sent {len(sent)} records in {time.time() - t0:.1f}s, draining {args.drain}s")
    time.sleep(args.drain)

    # Collect what the function logged.
    group = f"/aws/lambda/{run_id}"
    events, token = [], None
    while True:
        kw = {"logGroupName": group}
        if token:
            kw["nextToken"] = token
        resp = logs.filter_log_events(**kw)
        for e in resp["events"]:
            msg = e["message"].strip()
            if msg.startswith("{"):
                events.append(json.loads(msg))
        token = resp.get("nextToken")
        if not token:
            break

    dlq = []
    if queue_url:
        while True:
            m = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1)
            if not m.get("Messages"):
                break
            for msg in m["Messages"]:
                dlq.append(json.loads(msg["Body"]))
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])

    lam.update_event_source_mapping(UUID=esm["UUID"], Enabled=False)

    out = {"scenario": args.scenario, "run_id": run_id, "t0": t0, "args": vars(args),
           "esm": esm_args, "sent": sent, "events": events, "dlq": dlq}
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    path = os.path.join(HERE, "results", f"{args.scenario}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print("wrote", path)


if __name__ == "__main__":
    main()
