"""Stage 5 — Rank (code only, no model calls). Reproducible baseline from the contract:

    complaint_count = members; severity_sum = sum(severity); mean = sum/count (6 dp, half-up)
    priority_score = severity_sum; order by -score, then issue_id ascending.

    python pipeline/rank.py --run full          # from the run folder
    python pipeline/rank.py --from-grading      # from the published grading/ files; compares with grading/ranking.csv
"""

import argparse
import csv
import gzip
import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from common import OUT, ROOT, read_jsonl


def mean_str(total, n):
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run")
    ap.add_argument("--from-grading", action="store_true", help="use grading/records.jsonl.gz + grading/membership.csv")
    args = ap.parse_args()
    if args.from_grading:
        g = ROOT / "grading"
        with gzip.open(g / "records.jsonl.gz", "rt", encoding="utf-8") as f:
            recs = [json.loads(line) for line in f if line.strip()]
        mem_path, d = g / "membership.csv", OUT / "rerank_from_grading"
        d.mkdir(parents=True, exist_ok=True)
    elif args.run:
        d = OUT / "runs" / args.run
        recs, mem_path = read_jsonl(d / "records.jsonl"), d / "membership.csv"
    else:
        ap.error("give --run NAME or --from-grading")
    sev = {r["review_id"]: r["severity"] for r in recs if r["status"] == "completed"}
    members = defaultdict(set)
    with mem_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            members[row["issue_id"]].add(row["review_id"])  # a set: each review counted once per issue
    rows = []
    for iid, ids in members.items():
        s = sum(sev[r] for r in ids)
        rows.append({"issue_id": iid, "complaint_count": len(ids), "severity_sum": s,
                     "mean_severity": mean_str(s, len(ids)), "priority_score": s})
    rows.sort(key=lambda r: (-r["priority_score"], r["issue_id"]))
    with (d / "ranking.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity",
                                          "priority_score"], lineterminator="\n")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"rank": i, **r})
    print(json.dumps([{"rank": i, **r} for i, r in enumerate(rows[:5], 1)], indent=1))
    if args.from_grading:
        same = (d / "ranking.csv").read_bytes() == (ROOT / "grading" / "ranking.csv").read_bytes()
        print(f"regenerated {d / 'ranking.csv'} with 0 model calls; identical to grading/ranking.csv: {same}")


if __name__ == "__main__":
    main()
