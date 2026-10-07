"""Project tokens, API-equivalent cost and runtime from a measured run (code only).

    python pipeline/project_cost.py --run dev500
"""

import argparse
import json

from common import MODEL, OUT, ROOT, cost_usd, read_jsonl

# distinct nonempty texts that need a model call (exact duplicates reuse saved labels)
TARGETS = {"analysis_10000": 8448, "full_660622": 484189}
VERIFY_SAMPLE = {"analysis_10000": 1000, "full_660622": 2000}  # declared independent re-label sample
OTHER_STAGES_CALLS = 30  # group naming + memo sections: bounded aggregate inputs, ~3k in / 1k out each (assumption)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args()
    d = OUT / "runs" / args.run
    calls = [c for c in read_jsonl(d / "calls.jsonl") if c["role"] == "enrich"]
    recs = read_jsonl(d / "records.jsonl")
    sent = sum(len(c["review_ids"]) for c in calls)  # includes retries
    first = sum(len(c["review_ids"]) for c in calls if c["attempt"] == 1)
    tin = sum(c["input_tokens"] for c in calls)
    tout = sum(c["output_tokens"] for c in calls)
    secs = sum(c.get("elapsed_s", 0) for c in calls)
    per = {"input_tokens": tin / first, "output_tokens": tout / first, "seconds": secs / first,
           "retry_overhead": round(sent / first - 1, 4)}
    proj = {}
    for name, n in TARGETS.items():
        v = VERIFY_SAMPLE[name]
        i = per["input_tokens"] * (n + v) + OTHER_STAGES_CALLS * 3000
        o = per["output_tokens"] * (n + v) + OTHER_STAGES_CALLS * 1000
        proj[name] = {"includes": f"enrich {n} distinct texts + retries (measured) + verify {v} + ~{OTHER_STAGES_CALLS} group/memo calls","distinct_texts": n, "model_calls": -(-n // 50) + -(-v // 50) + OTHER_STAGES_CALLS, "input_tokens": int(i), "output_tokens": int(o),
                      "api_cost_usd_standard": round(cost_usd(MODEL, i, o), 2),
                      "api_cost_usd_batch": round(cost_usd(MODEL, i, o, batch=True), 2),
                      "pro_plan_cost_usd": 0.0, "spending_limit_usd": 0.0,
                      "sequential_hours": round(per["seconds"] * (n + v) / 3600, 1)}
    out = {"measured_on": args.run, "model": MODEL, "calls": len(calls), "distinct_texts_labeled": first,
           "records_completed": len(recs), "measured_input_tokens": tin, "measured_output_tokens": tout,
           "measured_api_equivalent_usd": round(cost_usd(MODEL, tin, tout), 4),
           "per_distinct_text": {k: round(v, 3) for k, v in per.items()}, "projections": proj,
           "notes": ["Pro plan: no per-token charge, but usage limits per 5-hour window cap throughput.",
                     "Verification, grouping and memo stages are extra (verify a ~1-2k sample, not everything).",
                     "API-equivalent prices: Haiku 4.5 list $1/$5 per MTok; Batch API halves them."]}
    path = ROOT / "evals" / f"cost_projection_{args.run}.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
