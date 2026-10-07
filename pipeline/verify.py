"""Stage 3 — Verify (independent model + code).

Claude Haiku re-labels a declared, seeded random sample of completed records WITHOUT seeing
the enricher's labels (it gets only the review text and the rubric). Code compares the two
and writes a disagreement report; enricher labels are never overwritten.

Also runs the planted-error test for free: a test copy of the sample gets one deliberately
wrong label, and code checks that the verifier's independent labels flag it.

    python pipeline/verify.py --run full --csv spotify_reviews_18months.csv --sample 1000
"""

import argparse
import csv
import hashlib
import json

from common import OUT, TOPICS, csv_rows, read_jsonl, append_jsonl
from enrich import SCHEMA, SYSTEM, user_message, validate
from llm import LLMError, haiku_json

SEED = "verify-v1"
VERIFY_CONFIG = "claude-haiku-4-5+enrich_v1+s1+nothink"


def pick_sample(records, n):
    """Deterministic: lowest SHA-256(seed:id) among completed originals (not cache copies)."""
    pool = [r for r in records if r["status"] == "completed" and not r.get("cache_source_id")]
    pool.sort(key=lambda r: hashlib.sha256(f"{SEED}:{r['review_id']}".encode()).hexdigest())
    return pool[:n]


def compare(enr, ver):
    diffs = [f for f, a, b in (("topic", enr["topic"], ver["topic"]), ("intent", enr["intent"], ver["intent"]),
                                ("severity", enr["severity"], ver["sev"])) if a != b]
    return diffs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="enrichment run to verify (outputs/runs/<run>)")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--sample", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=50)
    args = ap.parse_args()

    d = OUT / "runs" / args.run
    vd = d / "verify"
    vd.mkdir(exist_ok=True)
    f_pred, calls = vd / "verifier_predictions.jsonl", d / "calls.jsonl"
    texts = {r["review_id"]: r["review_text"] for r in csv_rows(args.csv)}
    recs = {r["review_id"]: r for r in read_jsonl(d / "records.jsonl")}
    sample = pick_sample(recs.values(), args.sample)
    (vd / "sample_ids.json").write_text(json.dumps({"seed": SEED, "n": len(sample),
                                                    "ids": [r["review_id"] for r in sample]}) + "\n")
    # resume/cache: reuse saved verifier predictions only if made under the same verifier config
    done = {p["review_id"]: p for p in read_jsonl(f_pred) if p.get("verify_config") == VERIFY_CONFIG}
    todo = [r["review_id"] for r in sample if r["review_id"] not in done]
    print(f"sample={len(sample)} already_verified={len(done)} todo={len(todo)}", flush=True)

    for i in range(0, len(todo), args.batch):
        ids = todo[i:i + args.batch]
        try:
            out = haiku_json(SYSTEM, user_message([texts[x] for x in ids]), SCHEMA, role="verify",
                             log_path=calls, review_ids=ids, label_config=VERIFY_CONFIG, run_id=args.run)
        except LLMError as e:
            print("verify call failed:", e)
            continue
        by_n = {it.get("n"): it for it in out.get("r", []) if isinstance(it, dict)}
        for n, rid in enumerate(ids, 1):
            it = by_n.get(n)
            ok = it is not None and validate(it, texts[rid]) in (None, "quote_not_in_text")
            row = {"review_id": rid, "verify_config": VERIFY_CONFIG, "valid": ok, **({k: it[k] for k in ("topic", "intent", "sev", "sent")} if ok else {})}
            append_jsonl(f_pred, row)
            done[rid] = row
        print(f"verified {len(done)}/{len(sample)}", flush=True)

    # Compare (code only)
    rows, agree = [], {"topic": 0, "intent": 0, "severity": 0}
    valid = [r for r in sample if done.get(r["review_id"], {}).get("valid")]
    for r in valid:
        v = done[r["review_id"]]
        diffs = compare(r, v)
        for f in agree:
            agree[f] += f not in diffs
        if diffs:
            rows.append({"review_id": r["review_id"], "text": texts[r["review_id"]][:300], "fields": ",".join(diffs),
                         "enricher": f"{r['topic']}/{r['intent']}/{r['severity']}",
                         "verifier": f"{v['topic']}/{v['intent']}/{v['sev']}"})
    n = len(valid) or 1
    report = {"enrich_run": args.run, "sample_seed": SEED, "sample_size": len(sample), "verifier_valid": len(valid),
              "verifier_model": "claude-haiku-4-5 (no thinking)", "verifier_saw_enricher_labels": False,
              "agreement": {f: round(c / n, 3) for f, c in agree.items()},
              "disagreements": len(rows)}

    # Planted-error test on a separate test copy (no extra model calls)
    if valid:
        target = valid[0]
        planted = dict(target)
        v = done[target["review_id"]]
        planted["topic"] = next(t for t in TOPICS if t not in (target["topic"], v["topic"]))
        flagged = "topic" in compare(planted, v)
        report["planted_error_test"] = {"review_id": target["review_id"], "original_topic": target["topic"],
                                        "planted_topic": planted["topic"], "verifier_topic": v["topic"],
                                        "detected": flagged, "note": "test copy only; real records untouched"}
    (vd / "verify_report.json").write_text(json.dumps(report, indent=2) + "\n")
    with (vd / "disagreements.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["review_id", "fields", "enricher", "verifier", "text"])
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
