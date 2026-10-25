"""Summarise results/<scenario>.json produced by run.py."""

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def summarise(name):
    d = json.load(open(os.path.join(HERE, "results", f"{name}.json")))
    t0 = d["t0"]
    sent = d["sent"]
    ev = d["events"]
    fraud = next(s for s in sent if s["kind"] == "fraud")
    poison = next(s for s in sent if s["kind"] == "poison")
    scored = [e for e in ev if e["kind"] == "scored"]
    counts = Counter(e["payment_id"] for e in scored)
    first = {}
    for e in sorted(scored, key=lambda e: e["t"]):
        first.setdefault(e["payment_id"], e)
    payments = [s for s in sent if s["kind"] in ("good", "fraud")]
    never = [s["payment_id"] for s in payments if s["payment_id"] not in first]
    fraud_hit = first.get(fraud["payment_id"])
    after = [s for s in payments if s["t"] > poison["t"]]
    delays_after = [first[s["payment_id"]]["t"] - s["t"] for s in after if s["payment_id"] in first]
    return {
        "scenario": name,
        "esm": d["esm"],
        "sent_payments": len(payments),
        "invocations": sum(1 for e in ev if e["kind"] == "invoke"),
        "poison_attempts": sum(1 for e in ev if e["kind"] == "poison"),
        "fraud_detected_after_s": round(fraud_hit["t"] - fraud["t"], 2) if fraud_hit else None,
        "fraud_alerts": counts.get(fraud["payment_id"], 0),
        "never_scored": len(never),
        "never_scored_ids": never[:12],
        "scored_more_than_once": sum(1 for c in counts.values() if c > 1),
        "max_delay_after_poison_s": round(max(delays_after), 2) if delays_after else None,
        "dlq_messages": len(d["dlq"]),
        "dlq": [
            {
                "condition": m["requestContext"]["condition"],
                "approximateInvokeCount": m["requestContext"]["approximateInvokeCount"],
                "batchSize": m["KinesisBatchInfo"]["batchSize"],
            }
            for m in d["dlq"]
        ],
        "observed_s": round(max(e["t"] for e in ev) - t0, 1),
    }


if __name__ == "__main__":
    names = sys.argv[1:] or ["default", "retry2", "bisect", "partial", "partial_all"]
    for n in names:
        if os.path.exists(os.path.join(HERE, "results", f"{n}.json")):
            print(json.dumps(summarise(n), ensure_ascii=False))
