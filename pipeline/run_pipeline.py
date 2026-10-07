"""Orchestrator: run all six stages on any input CSV, in order, with saved handoffs.

    1 prepare  (code)          ingest.py profile only for the full file; dedup/cache inside stage 2
    2 classify (Jev + code)    enrich_jev.py   -> records.jsonl, quarantine.jsonl, calls.jsonl
    3 verify   (Haiku + code)  verify.py       -> verify/verify_report.json, disagreements.csv
    4 group    (code + Haiku)  group.py        -> membership.csv, issues.json
    5 rank     (code)          rank.py         -> ranking.csv
    6 memo     (Haiku + code)  memo.py         -> claims.csv, memo.md, memo_check.json

Each stage is a separate process reading the previous stage's saved files, so any stage can
be rerun alone; rank/group/memo reruns make no model calls when their inputs are unchanged.
Stage start/stop, wall time and exit status go to outputs/runs/<run>/run_log.jsonl.

    python pipeline/run_pipeline.py cost_100.csv --run pilot100 --verify-sample 10 --max-usd 0.05 --workers 1
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone

from common import OUT, ROOT, append_jsonl

PY = sys.executable
P = ROOT / "pipeline"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--run", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--max-usd", type=float, default=0.10, help="Jev spend cap for this invocation")
    ap.add_argument("--verify-sample", type=int, default=1000)
    ap.add_argument("--stop-after", type=int, default=0, help="enrichment interruption demo")
    ap.add_argument("--stages", default="prepare,classify,verify,group,rank,memo")
    args = ap.parse_args()
    run_dir = OUT / "runs" / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "run_log.jsonl"

    cmds = {
        "prepare": [PY, P / "ingest.py", args.csv, "--out", run_dir / "prepare"],
        "classify": [PY, P / "enrich_jev.py", args.csv, "--run", args.run, "--workers", str(args.workers),
                     "--max-usd", str(args.max_usd)] + (["--stop-after", str(args.stop_after)] if args.stop_after else []),
        "verify": [PY, P / "verify.py", "--run", args.run, "--csv", args.csv, "--sample", str(args.verify_sample)],
        "group": [PY, P / "group.py", "--run", args.run, "--csv", args.csv],
        "rank": [PY, P / "rank.py", "--run", args.run],
        "memo": [PY, P / "memo.py", "--run", args.run],
    }
    t_all = time.time()
    for stage in args.stages.split(","):
        t0 = time.time()
        append_jsonl(log, {"stage": stage, "event": "start", "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        print(f"=== {stage} ===", flush=True)
        proc = subprocess.Popen([str(c) for c in cmds[stage]], cwd=ROOT)
        while True:
            try:
                rc = proc.wait()
                break
            except KeyboardInterrupt:  # Ctrl+C also reaches the stage; let it save its checkpoint first
                print("interrupt received; waiting for the stage to save its progress...", flush=True)
        append_jsonl(log, {"stage": stage, "event": "stop", "exit_code": rc, "wall_s": round(time.time() - t0, 2),
                           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        if rc in (130, -2):
            print(f"stage {stage} interrupted; saved work is kept. Run the same command again to resume.")
            sys.exit(130)
        if rc != 0:
            print(f"stage {stage} failed (exit {rc}); stopping. Fix and rerun; saved work is kept.")
            sys.exit(rc)
    print(f"pipeline finished in {time.time() - t_all:.1f}s")


if __name__ == "__main__":
    main()
