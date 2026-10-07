# Cost and runtime calculator (100-review pilot)

Specification: [../COST_CALCULATOR.md](../COST_CALCULATOR.md). Report: [report.md](report.md).

## Offline replay (default, no API key, no model calls)

```bash
.venv/bin/python cost/calculator.py
```

Recomputes every cost from saved usage ([pilot_calls.jsonl](pilot_calls.jsonl)) and editable rates ([rates.csv](rates.csv)), writes [usage.csv](usage.csv) and [report.md](report.md). Projection inputs are in [assumptions.json](assumptions.json). Changing rates or assumptions never changes the measured pilot rows; doubling all API rates doubles the metered API subtotal (tested), while local-compute (unknown) and measured times stay the same.

## Paid pilot (explicit)

```bash
.venv/bin/python cost/calculator.py pilot --confirm
```

Runs the whole pipeline on `cost_100.csv` (checksum checked against `manifest.json`) twice: **cold** (empty result cache, 1 worker, verify sample 10) and **warm** (same settings, saved results). Saves [pilot_runs.json](pilot_runs.json), [pilot_calls.jsonl](pilot_calls.jsonl), [pilot_records.jsonl](pilot_records.jsonl), [pilot_outputs/](pilot_outputs/), then replays.

## Files

| File | Contents |
|---|---|
| `rates.csv` | provider, model, billing item, unit, USD per million units, billing mode, dated source link |
| `usage.csv` | one row per call × billing item, mapped to its rate (metered vs. subscription vs. unknown) |
| `pilot_calls.jsonl` | every attempt with run ID, request ID, role, model, settings, tokens, timing, outcome |
| `pilot_runs.json` | cold/warm wall clock, per-stage seconds, workers, batch size, verify sample, spend cap |
| `pilot_records.jsonl` | one result per pilot ID with original row hash and common labels |
| `report.md` | measured dashboard + projections (base, conservative, no-reuse) and budget check |
| `archive_*` | earlier pilot attempts kept for honesty (a warm-run bug, a memo-check failure, a superseded run), each with a NOTE |

## Billing modes

- **metered_api** — Jev (`jev-1.13.0`): $0.042 per million input tokens, output free.
- **subscription** — Claude Haiku 4.5 called through Claude Code on a Claude Pro plan. No per-call charge is observable, so it is reported as **unknown** with an API-equivalent estimate at Anthropic list prices ($1 / $5 per million tokens). Subscription access is not evidence that calls are free.
- **local_compute** — code stages on a laptop; not measured, reported as unknown.

## Measured results and decision

- Cold pilot: 34.9 s end to end, metered $0.001168 (100 rows), 0 failures, 0 retries. Warm: 0 new calls, 1.0 s, $0.
- Refreshed at 500 and 10,000 reviews: 278.2 / 278.7 / 278.5 Jev tokens per distinct text ([../evals/cost_refresh.json](../evals/cost_refresh.json)).
- Full-run projection: **$5.66** base, $7.43 conservative, $7.72 without exact-text reuse. Chosen: budget $10, full-run cap $7.50, 4 workers, fallback fraction 0%.
- **Actual full run: $5.71** (9,684 requests, 0 failed), 7.5 minutes of classification. Reconcile with the TypeSafe usage dashboard if needed.
