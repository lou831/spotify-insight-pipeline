"""Build the standardized grading/ folder from a finished run (code only, no model calls).

    python pipeline/export.py --run full
    python check_submission.py check --reference local-reference.json --submission grading --out self-check.json
"""

import argparse
import csv
import gzip
import json
import shutil

from common import OUT, ROOT, read_jsonl
from check_submission import VERSION


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=str(ROOT / "grading"))
    args = ap.parse_args()
    d, g = OUT / "runs" / args.run, __import__("pathlib").Path(args.out)
    g.mkdir(exist_ok=True)
    (g / "run.json").write_text(json.dumps({
        "version": VERSION, "analysis_count": 660622,
        "analysis_sha256": "1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6",
        "classification_input_fields": ["review_text"], "allow_multi_issue": False}) + "\n")
    shutil.copy(OUT / "ingestion.json", g / "ingestion.json")

    final = {}
    for r in read_jsonl(d / "quarantine.jsonl"):
        final[r["review_id"]] = {k: r[k] for k in ("review_id", "source_sha256", "status", "reason")}
    for r in read_jsonl(d / "records.jsonl"):
        final[r["review_id"]] = r  # a later completion supersedes an earlier quarantine
    with gzip.open(g / "records.jsonl.gz", "wt", encoding="utf-8") as f:
        for r in final.values():
            if not r["review_id"].startswith("SYNTHETIC"):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with gzip.open(g / "calls.jsonl.gz", "wt", encoding="utf-8") as f:
        for c in read_jsonl(d / "calls.jsonl"):
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    for name in ("membership.csv", "ranking.csv", "claims.csv"):
        shutil.copy(d / name, g / name)
    cps = sorted(d.glob("checkpoint_*.json"), key=lambda p: int(p.stem.rsplit("_", 1)[1]))
    initial = [p for p in cps if "_initial_" in p.name]
    shutil.copy(initial[0] if initial else cps[0], g / "checkpoint_before.json")
    shutil.copy(cps[-1], g / "checkpoint_after.json")
    status = {}
    for r in final.values():
        status[r["status"]] = status.get(r["status"], 0) + 1
    print(f"grading/ written: {len(final)} records {status}")


if __name__ == "__main__":
    main()
