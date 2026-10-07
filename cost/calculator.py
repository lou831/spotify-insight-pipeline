"""100-review cost and runtime calculator (see COST_CALCULATOR.md).

DEFAULT = offline replay: recomputes every cost from saved usage + editable rates.
No API key, no network, no model calls.

    python cost/calculator.py                 # offline replay -> cost/usage.csv, cost/report.md
    python cost/calculator.py pilot --confirm # PAID: cold run (empty cache, 1 worker) then warm run

Edit cost/rates.csv (prices) or cost/assumptions.json (projection inputs) and replay again.
Measured pilot numbers never change when rates or projections change.
"""

import csv
import json
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

C = Path(__file__).resolve().parent
ROOT = C.parent
RUN = "pilot100"
PILOT_CSV = ROOT / "cost_100.csv"
PILOT_SHA = "c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e"  # manifest.json
STAGE_OF_ROLE = {"enrich": "classify", "verify": "verify", "group": "group", "memo": "memo"}


def jl(path):
    p = Path(path)
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ----------------------------------------------------------------- paid pilot (explicit only)
def pilot():
    if "--confirm" not in sys.argv:
        sys.exit("Paid pilot not started. Re-run with: python cost/calculator.py pilot --confirm")
    if sha(PILOT_CSV) != PILOT_SHA:
        sys.exit("cost_100.csv checksum does not match manifest.json")
    run_dir = ROOT / "outputs" / "runs" / RUN
    shutil.rmtree(run_dir, ignore_errors=True)  # cold = empty result cache for this experiment
    runs = json.loads((C / "pilot_runs.json").read_text()) if (C / "pilot_runs.json").exists() else []
    for phase in ("cold", "warm"):
        calls_before = len(jl(run_dir / "calls.jsonl"))
        log_before = len(jl(run_dir / "run_log.jsonl"))
        run_id = f"pilot_{phase}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        t0 = time.time()
        rc = subprocess.run([sys.executable, str(ROOT / "pipeline" / "run_pipeline.py"), str(PILOT_CSV), "--run", RUN,
                             "--workers", "1", "--verify-sample", "10", "--max-usd", "0.05"], cwd=ROOT).returncode
        wall = round(time.time() - t0, 2)
        new_calls = jl(run_dir / "calls.jsonl")[calls_before:]
        for c in new_calls:
            c["run_id"] = run_id
            with (C / "pilot_calls.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        stages = {e["stage"]: e["wall_s"] for e in jl(run_dir / "run_log.jsonl")[log_before:] if e["event"] == "stop"}
        runs.append({"run_id": run_id, "phase": phase, "exit_code": rc, "wall_s": wall, "stage_wall_s": stages,
                     "workers": 1, "batch_size": 50, "verify_sample": 10, "jev_spend_cap_usd": 0.05,
                     "input_sha256": PILOT_SHA, "new_calls_by_role": dict(_count(new_calls)),
                     "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        (C / "pilot_runs.json").write_text(json.dumps(runs, indent=2) + "\n")
        if rc != 0:
            sys.exit(f"{phase} run failed (exit {rc}); see outputs/runs/{RUN}/run_log.jsonl")
    recs = {r["review_id"]: r for r in jl(run_dir / "records.jsonl")}
    for q in jl(run_dir / "quarantine.jsonl"):
        recs.setdefault(q["review_id"], q)
    (C / "pilot_records.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs.values()))
    for f in ("verify/verify_report.json", "membership.csv", "issues.json", "ranking.csv", "claims.csv", "memo.md"):
        if (run_dir / f).exists():
            (C / "pilot_outputs").mkdir(exist_ok=True)
            shutil.copy(run_dir / f, C / "pilot_outputs" / Path(f).name)
    replay()


def _count(calls):
    out = defaultdict(int)
    for c in calls:
        out[c["role"]] += 1
    return out


# ----------------------------------------------------------------- offline replay (default)
def load_rates():
    rates = {}
    with (C / "rates.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p = r["price_usd_per_million_units"]
            rates[(r["model"], r["billing_item"])] = {"per_unit": float(p) / 1_000_000 if p != "" else None,
                                                      "mode": r["billing_mode"], "source": r["source_url"],
                                                      "checked": r["checked_date"], "provider": r["provider"]}
    return rates


def item_costs(call, rates):
    """(metered_usd or None if unknown, api_equivalent_usd) for one call."""
    metered, equiv, unknown = 0.0, 0.0, False
    for item, units in (("input_tokens", call.get("input_tokens", 0)), ("output_tokens", call.get("output_tokens", 0))):
        r = rates.get((call["model"], item))
        if not r or r["per_unit"] is None:
            unknown = True
            continue
        c = units * r["per_unit"]
        equiv += c
        if r["mode"] == "metered_api":
            metered += c
        else:
            unknown = True
    return (None if unknown and metered == 0 else metered), equiv, unknown


def replay():
    rates, A = load_rates(), json.loads((C / "assumptions.json").read_text())
    calls, runs, recs = jl(C / "pilot_calls.jsonl"), (json.loads((C / "pilot_runs.json").read_text())
                                                       if (C / "pilot_runs.json").exists() else []), jl(C / "pilot_records.jsonl")
    if not runs:
        print("No pilot measured yet. Run: python cost/calculator.py pilot --confirm  (paid, ~$0.001)")
        return
    # usage.csv: one row per call x billing item, mapped to its rate
    with (C / "usage.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["run_id", "request_id", "stage", "role", "attempt", "outcome", "provider", "model", "billing_item",
                    "units", "usd_per_unit", "billing_mode", "metered_usd", "api_equivalent_usd"])
        for c in calls:
            for item in ("input_tokens", "output_tokens"):
                r = rates.get((c["model"], item), {})
                u = c.get(item, 0)
                cost = u * r["per_unit"] if r.get("per_unit") is not None else None
                w.writerow([c["run_id"], c["request_id"], STAGE_OF_ROLE.get(c["role"], c["role"]), c["role"],
                            c.get("attempt", 1), c["outcome"], r.get("provider", "?"), c["model"], item, u,
                            r.get("per_unit"), r.get("mode", "unknown"),
                            "" if cost is None or r.get("mode") != "metered_api" else f"{cost:.10f}",
                            "" if cost is None else f"{cost:.10f}"])

    L = ["# Cost and runtime calculator — 100-review pilot", "",
         f"Generated offline {datetime.now(timezone.utc).isoformat(timespec='seconds')} from "
         "`pilot_calls.jsonl`, `pilot_runs.json`, `rates.csv`, `assumptions.json`. No API key or model call used.", "",
         f"Input `cost_100.csv` sha256 `{PILOT_SHA}` (matches manifest.json). 100 IDs.", "",
         "## Rates (editable: `rates.csv`)", "", "| provider | model | item | USD / 1M units | billing mode | checked | source |",
         "|---|---|---|---|---|---|---|"]
    for (m, item), r in rates.items():
        L.append(f"| {r['provider']} | {m} | {item} | {'' if r['per_unit'] is None else round(r['per_unit'] * 1e6, 6)} | "
                 f"{r['mode']} | {r['checked']} | {r['source']} |")
    L += ["", "Billing modes: **metered_api** = real per-token charge; **subscription** = Claude Pro plan via Claude Code, "
              "no metered charge observable, reported as *unknown* with an API-equivalent estimate; **local_compute** = laptop "
              "time, cost not measured (*unknown*).", "", "## Measured pilot runs", ""]
    by_run = defaultdict(list)
    for c in calls:
        by_run[c["run_id"]].append(c)
    measured = {}
    for run in runs:
        cs = by_run.get(run["run_id"], [])
        st = defaultdict(lambda: {"calls": 0, "failed": 0, "retries": 0, "in": 0, "out": 0, "metered": 0.0,
                                  "equiv": 0.0, "unknown": False, "models": set()})
        for c in cs:
            s = st[STAGE_OF_ROLE[c["role"]]]
            s["calls"] += 1
            s["failed"] += c["outcome"] == "failed"
            s["retries"] += c.get("attempt", 1) > 1
            s["in"] += c.get("input_tokens", 0)
            s["out"] += c.get("output_tokens", 0)
            m, e, unk = item_costs(c, rates)
            s["metered"] += m or 0.0
            s["equiv"] += e
            s["unknown"] |= unk
            s["models"].add(c.get("served_by") or c["model"])
        metered = sum(s["metered"] for s in st.values())
        measured[run["phase"]] = {"stages": st, "metered": metered, "run": run}
        done = sum(r.get("status") == "completed" for r in recs)
        L += [f"### {run['phase'].upper()} run `{run['run_id']}`", "",
              f"Wall clock **{run['wall_s']} s** (end to end) · workers {run['workers']} · batch {run['batch_size']} · "
              f"verify sample {run['verify_sample']} · Jev spend cap ${run['jev_spend_cap_usd']}", "",
              "| stage | wall s | calls | failed | retries | input tok | output tok | metered API $ | subscription (API-equiv $) | model / effort |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for stage in ("prepare", "classify", "verify", "group", "rank", "memo"):
            s = st.get(stage)
            wall = run["stage_wall_s"].get(stage, "")
            if s:
                sub = f"unknown ({s['equiv']:.6f})" if s["unknown"] else "—"
                eff = "no-thinking" if any("haiku" in x for x in s["models"]) else "n/a (classifier)"
                L.append(f"| {stage} | {wall} | {s['calls']} | {s['failed']} | {s['retries']} | {s['in']:,} | {s['out']:,} | "
                         f"{s['metered']:.6f} | {sub} | {', '.join(sorted(s['models']))} / {eff} |")
            else:
                L.append(f"| {stage} | {wall} | 0 | 0 | 0 | 0 | 0 | 0.000000 | — | code only (local compute: unknown) |")
        L += ["", f"**Metered API total: ${metered:.6f}** · cost per 1,000 input rows ${metered * 10:.6f} · "
                  f"per completed record ${metered / max(done, 1):.8f} · local compute: unknown", ""]
    recs_ok = [r for r in recs if r.get("status") == "completed"]
    L += ["### Pilot outcomes", "",
          f"Completed {len(recs_ok)} · quarantined {sum(r.get('status') == 'quarantined' for r in recs)} · "
          f"exact-text cache hits {sum(1 for r in recs_ok if r.get('cache_source_id'))} · "
          f"unique texts {100 - sum(1 for r in recs_ok if r.get('cache_source_id'))}", ""]
    warm = measured.get("warm")
    if warm:
        n_enrich = warm["stages"].get("classify", {"calls": 0})["calls"]
        L += [f"**Warm rerun: {n_enrich} new enrichment calls**, incremental metered cost ${warm['metered']:.6f}, "
              f"wall {warm['run']['wall_s']} s.", ""]

    # ------------------------------------------------------------- projections
    cold = measured.get("cold")
    ccalls = by_run.get(cold["run"]["run_id"], []) if cold else []
    enr = [c for c in ccalls if c["role"] == "enrich"]
    first_ids = sum(len(c["review_ids"]) for c in enr if c.get("attempt", 1) == 1) or 1
    retried = sum(len(c["review_ids"]) for c in enr if c.get("attempt", 1) > 1)
    jev_tok = sum(c.get("input_tokens", 0) for c in enr) / first_ids  # includes measured retries
    jev_rate = rates[("jev-1.13.0", "input_tokens")]["per_unit"]
    enr_req_s = (sum(c.get("elapsed_s", 0) for c in enr) / max(len(enr), 1))
    ver = [c for c in ccalls if c["role"] == "verify" and c["outcome"] == "succeeded"]
    ver_n = sum(len(c["review_ids"]) for c in ver) or 1
    v_in, v_out = sum(c["input_tokens"] for c in ver) / ver_n, sum(c["output_tokens"] for c in ver) / ver_n
    v_s = sum(c.get("elapsed_s", 0) for c in ver) / ver_n
    fixed = [c for c in ccalls if c["role"] in ("group", "memo") and c["outcome"] == "succeeded"]
    f_in = sum(c["input_tokens"] for c in fixed) / max(len(fixed), 1)
    f_out = sum(c["output_tokens"] for c in fixed) / max(len(fixed), 1)
    f_s = sum(c.get("elapsed_s", 0) for c in fixed) / max(len(fixed), 1)
    h_in, h_out = rates[("claude-haiku-4-5", "input_tokens")]["per_unit"], rates[("claude-haiku-4-5", "output_tokens")]["per_unit"]
    n_fixed = sum(A["fixed_calls"].values())
    retry_base = retried / first_ids
    L += ["## Projections (editable: `assumptions.json`)", "",
          f"Measured per distinct text (cold run): {jev_tok:.1f} Jev input tokens incl. retries "
          f"(retry rate {retry_base:.1%}); verifier {v_in:.0f} in / {v_out:.0f} out tokens and {v_s:.2f} s per review; "
          f"group/memo {f_in:.0f} in / {f_out:.0f} out tokens and {f_s:.1f} s per call. Fixed overhead (group + memo, "
          f"{n_fixed} calls, prepare) is added once. Fallback fraction: {A['max_fallback_fraction']:.0%} ({A['fallback_note']})", "",
          "| scope | scenario | texts classified | Jev requests | Jev metered $ | Haiku (subscription) API-equiv $ | est. wall time | within budget? |",
          "|---|---|---|---|---|---|---|---|"]
    for scope, rows, distinct, nonempty in (("analysis_10000", A["sample_10k_rows"], A["sample_10k_distinct"], A["sample_10k_rows"]),
                                            ("full_660622", A["full_rows"], A["full_distinct_nonempty"], A["full_nonempty"])):
        vs = A["verify_sample"][scope]
        for scen, reuse in (("base", True), ("conservative", True), ("base, no reuse", False)):
            cons = scen == "conservative"
            n = distinct if reuse else nonempty
            retry = max(retry_base * 3, A["retry_rate_conservative_min"]) if cons else retry_base
            infl = A["token_inflation_conservative"] if cons else 1.0
            tok = jev_tok / (1 + retry_base) * (1 + retry) * infl * n
            jev_usd = tok * jev_rate
            reqs = int((n / 50 + 0.999) * (1 + retry))
            eff = A["parallel_efficiency_conservative" if cons else "parallel_efficiency_base"]
            rate_floor = reqs / A["jev_requests_per_second_limit"]
            enrich_s = max(reqs * enr_req_s / (A["enrich_workers"] * eff), rate_floor)
            haiku_equiv = (vs * (v_in * h_in + v_out * h_out) + n_fixed * (f_in * h_in + f_out * h_out)) * infl
            total_s = A["prepare_seconds_full_measured"] * rows / A["full_rows"] + enrich_s + vs * v_s + n_fixed * f_s
            ok = "yes" if jev_usd <= A["budget_usd"] else f"**NO: exceeds ${A['budget_usd']} budget**"
            L.append(f"| {scope} | {scen} | {n:,} | {reqs:,} | {jev_usd:.2f} | unknown (≈{haiku_equiv:.2f}) | "
                     f"{total_s / 3600:.2f} h | {ok} |")
    L += ["", f"Budget: ${A['budget_usd']} metered API spend (Jev). Enrichment workers {A['enrich_workers']} "
              f"(efficiency {A['parallel_efficiency_base']} base / {A['parallel_efficiency_conservative']} conservative), "
              f"capped by {A['jev_requests_per_second_limit']} req/s. Haiku runs on a subscription: its charge is reported "
              "as unknown, never as zero. Projections are estimates; measured pilot rows above do not change when "
              "assumptions or rates change.", ""]
    (C / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    pilot() if len(sys.argv) > 1 and sys.argv[1] == "pilot" else replay()
