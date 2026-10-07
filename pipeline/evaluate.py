"""Compare a run's model labels with your golden hand labels (code only, no model calls).

    python pipeline/evaluate.py --run golden50

Writes evals/<run>_eval.json (summary + confusion tables) and evals/<run>_disagreements.csv.
Missing or quarantined predictions count as wrong.
"""

import argparse
import csv
import json
from collections import Counter

from common import OUT, ROOT, read_jsonl

GOLD = ROOT / "evals" / "golden_50_labeled.csv"
SENT_TOL = 0.3  # predeclared: sentiment within ±0.3 counts as agreement


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args()
    gold = list(csv.DictReader(GOLD.open(encoding="utf-8")))
    pred = {r["review_id"]: r for r in read_jsonl(OUT / "runs" / args.run / "records.jsonl")}

    n = len(gold)
    hits = Counter()
    sev_err, sent_err = [], []
    conf = {"topic": Counter(), "intent": Counter()}
    rows = []
    for g in gold:
        p = pred.get(g["review_id"])
        row = {"review_id": g["review_id"], "gold_topic": g["topic"], "gold_intent": g["intent"], "gold_severity": g["severity"]}
        if not p:
            hits["missing"] += 1
            rows.append({**row, "pred_topic": "MISSING", "pred_intent": "", "pred_severity": "", "fields_wrong": "all"})
            continue
        wrong = []
        for f in ("topic", "intent"):
            conf[f][(g[f], p[f])] += 1
            if p[f] == g[f]:
                hits[f] += 1
            else:
                wrong.append(f)
        gs = int(g["severity"])
        sev_err.append(abs(p["severity"] - gs))
        if p["severity"] == gs:
            hits["severity"] += 1
        else:
            wrong.append("severity")
        se = abs(p["sentiment"] - float(g["sentiment"]))
        sent_err.append(se)
        hits["sentiment_within_tol"] += se <= SENT_TOL
        hits["needs_review"] += str(p["needs_review"]).upper() == g["needs_review"].upper()
        rows.append({**row, "pred_topic": p["topic"], "pred_intent": p["intent"], "pred_severity": p["severity"],
                     "pred_quote": p["evidence_quote"], "gold_quote": g["evidence_quote"], "fields_wrong": ",".join(wrong),
                     "your_verdict(ai_wrong/i_was_wrong/ambiguous)": "", "why": ""})

    def table(counter):
        labels = sorted({a for a, _ in counter} | {b for _, b in counter})
        return {"rows=gold, cols=pred": labels, "matrix": [[counter[(a, b)] for b in labels] for a in labels]}

    summary = {
        "run": args.run, "cases": n, "missing_or_quarantined": hits["missing"],
        "topic_agreement": round(hits["topic"] / n, 3), "intent_agreement": round(hits["intent"] / n, 3),
        "severity_exact": round(hits["severity"] / n, 3),
        "severity_mae": round(sum(sev_err) / len(sev_err), 3) if sev_err else None,
        "sentiment_mae": round(sum(sent_err) / len(sent_err), 3) if sent_err else None,
        f"sentiment_within_{SENT_TOL}": round(hits["sentiment_within_tol"] / n, 3),
        "needs_review_agreement": round(hits["needs_review"] / n, 3),
        "gold_marked_ambiguous": sum(g["needs_review"].upper() == "TRUE" for g in gold),
        "confusion_topic": table(conf["topic"]), "confusion_intent": table(conf["intent"]),
    }
    (ROOT / "evals" / f"{args.run}_eval.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (ROOT / "evals" / f"{args.run}_disagreements.csv").open("w", encoding="utf-8", newline="") as f:
        dis = [r for r in rows if r["fields_wrong"]]
        if dis:
            w = csv.DictWriter(f, fieldnames=list(max(dis, key=len).keys()))
            w.writeheader()
            w.writerows(dis)
    print(json.dumps({k: v for k, v in summary.items() if not k.startswith("confusion")}, indent=2))


if __name__ == "__main__":
    main()
