"""Kinesis consumer that scores synthetic payment events.

Every record is logged as one JSON line so that the measurement script can
reconstruct when each payment was scored (and how many times).

MODE=raise   : a malformed record raises, so the whole batch fails (default behaviour)
MODE=partial : stop at the malformed record and report it via batchItemFailures
               (the pattern in the AWS sample code)
MODE=partial_all : keep scoring the rest of the batch, then report the malformed record
"""

import base64
import json
import os
import time

MODE = os.environ.get("MODE", "raise")
AMOUNT_LIMIT = 300_000  # JPY. Anything at or above this is flagged.


def score(payment):
    reasons = []
    if payment["amount"] >= AMOUNT_LIMIT:
        reasons.append("amount")
    if payment["card_country"] != payment["ip_country"]:
        reasons.append("country_mismatch")
    return reasons


def handler(event, context):
    records = event["Records"]
    failures = []
    invoked_at = time.time()
    print(json.dumps({
        "kind": "invoke",
        "request_id": context.aws_request_id,
        "batch_size": len(records),
        "first_seq": records[0]["kinesis"]["sequenceNumber"],
        "t": invoked_at,
    }))

    for record in records:
        k = record["kinesis"]
        raw = base64.b64decode(k["data"])
        try:
            payment = json.loads(raw)
            reasons = score(payment)
        except Exception as e:  # malformed event = poison pill
            print(json.dumps({
                "kind": "poison",
                "request_id": context.aws_request_id,
                "seq": k["sequenceNumber"],
                "arrival": k["approximateArrivalTimestamp"],
                "t": time.time(),
                "error": type(e).__name__,
            }))
            if MODE == "partial":
                return {"batchItemFailures": [{"itemIdentifier": k["sequenceNumber"]}]}
            if MODE == "partial_all":
                failures.append({"itemIdentifier": k["sequenceNumber"]})
                continue
            raise

        print(json.dumps({
            "kind": "scored",
            "request_id": context.aws_request_id,
            "seq": k["sequenceNumber"],
            "payment_id": payment["payment_id"],
            "arrival": k["approximateArrivalTimestamp"],
            "t": time.time(),
            "fraud": bool(reasons),
            "reasons": reasons,
        }))

    return {"batchItemFailures": failures}
