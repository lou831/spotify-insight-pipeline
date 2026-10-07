"""Stage 1 — Ingest (code only, no model calls).

Reads the whole CSV with a real CSV parser, writes the deterministic grader profile
plus a richer human-readable report.

    python pipeline/ingest.py spotify_reviews_18months.csv
"""

import argparse
import json
from collections import Counter

from common import OUT, csv_rows, sha
from check_submission import profile, write_json


def text_stats(path):
    lengths, texts = [], Counter()
    empty_ids = []
    for row in csv_rows(path):
        t = row["review_text"]
        if not t.strip():
            empty_ids.append(row["review_id"])
            continue
        lengths.append(len(t))
        texts[t] += 1
    lengths.sort()
    pct = lambda p: lengths[min(len(lengths) - 1, int(len(lengths) * p))]
    return {
        "nonempty_texts": len(lengths),
        "distinct_nonempty_texts": len(texts),
        "exact_duplicate_rows_reusable": len(lengths) - len(texts),
        "text_length_chars": {"min": lengths[0], "p10": pct(.10), "median": pct(.5), "mean": round(sum(lengths) / len(lengths), 2),
                              "p90": pct(.90), "p99": pct(.99), "max": lengths[-1]},
        "total_chars_distinct": sum(len(t) for t in texts),
        "most_common_texts": texts.most_common(15),
        "empty_review_ids": empty_ids,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default=str(OUT), help="output folder (default outputs/)")
    args = ap.parse_args()
    out = __import__("pathlib").Path(args.out)

    prof = profile(args.csv)  # identical to `check_submission.py profile`
    write_json(out / "ingestion.json", prof)
    report = {"input_path": args.csv, "file_sha256": prof["file_sha256"], "profile": prof, "text": text_stats(args.csv)}
    write_json(out / "ingestion_report.json", report)
    write_json(out / "data_manifest.json", {"input_path": args.csv, "file_sha256": sha(args.csv),
                                            "records": prof["counts"]["records"]})
    c = prof["counts"]
    t = report["text"]
    print(json.dumps({**c, "first": prof["first_review"], "last": prof["last_review"],
                      "distinct_nonempty_texts": t["distinct_nonempty_texts"],
                      "median_chars": t["text_length_chars"]["median"]}, indent=2))


if __name__ == "__main__":
    main()
