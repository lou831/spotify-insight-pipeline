# Cost and runtime calculator — 100-review pilot

Generated offline 2026-10-07T04:42:53+00:00 from `pilot_calls.jsonl`, `pilot_runs.json`, `rates.csv`, `assumptions.json`. No API key or model call used.

Input `cost_100.csv` sha256 `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e` (matches manifest.json). 100 IDs.

## Rates (editable: `rates.csv`)

| provider | model | item | USD / 1M units | billing mode | checked | source |
|---|---|---|---|---|---|---|
| typesafe | jev-1.13.0 | input_tokens | 0.042 | metered_api | 2026-10-06 | https://docs.typesafe.ai/models |
| typesafe | jev-1.13.0 | output_tokens | 0.0 | metered_api | 2026-10-06 | https://docs.typesafe.ai/models |
| anthropic | claude-haiku-4-5 | input_tokens | 1.0 | subscription | 2026-10-06 | https://platform.claude.com/docs/en/about-claude/pricing |
| anthropic | claude-haiku-4-5 | output_tokens | 5.0 | subscription | 2026-10-06 | https://platform.claude.com/docs/en/about-claude/pricing |
| local | laptop | compute_seconds |  | local_compute | 2026-10-06 |  |

Billing modes: **metered_api** = real per-token charge; **subscription** = Claude Pro plan via Claude Code, no metered charge observable, reported as *unknown* with an API-equivalent estimate; **local_compute** = laptop time, cost not measured (*unknown*).

## Measured pilot runs

### COLD run `pilot_cold_20261007T044217Z`

Wall clock **34.86 s** (end to end) · workers 1 · batch 50 · verify sample 10 · Jev spend cap $0.05

| stage | wall s | calls | failed | retries | input tok | output tok | metered API $ | subscription (API-equiv $) | model / effort |
|---|---|---|---|---|---|---|---|---|---|
| prepare | 0.08 | 0 | 0 | 0 | 0 | 0 | 0.000000 | — | code only (local compute: unknown) |
| classify | 1.07 | 2 | 0 | 0 | 27,821 | 20,481 | 0.001168 | — | jev-1.13.0 / n/a (classifier) |
| verify | 8.32 | 1 | 0 | 0 | 2,481 | 807 | 0.000000 | unknown (0.006516) | claude-haiku-4-5-20251001 / no-thinking |
| group | 10.63 | 1 | 0 | 0 | 3,218 | 907 | 0.000000 | unknown (0.007753) | claude-haiku-4-5-20251001 / no-thinking |
| rank | 0.09 | 0 | 0 | 0 | 0 | 0 | 0.000000 | — | code only (local compute: unknown) |
| memo | 14.58 | 1 | 0 | 0 | 4,010 | 1,012 | 0.000000 | unknown (0.009070) | claude-haiku-4-5-20251001 / no-thinking |

**Metered API total: $0.001168** · cost per 1,000 input rows $0.011685 · per completed record $0.00001168 · local compute: unknown

### WARM run `pilot_warm_20261007T044252Z`

Wall clock **0.99 s** (end to end) · workers 1 · batch 50 · verify sample 10 · Jev spend cap $0.05

| stage | wall s | calls | failed | retries | input tok | output tok | metered API $ | subscription (API-equiv $) | model / effort |
|---|---|---|---|---|---|---|---|---|---|
| prepare | 0.09 | 0 | 0 | 0 | 0 | 0 | 0.000000 | — | code only (local compute: unknown) |
| classify | 0.41 | 0 | 0 | 0 | 0 | 0 | 0.000000 | — | code only (local compute: unknown) |
| verify | 0.09 | 0 | 0 | 0 | 0 | 0 | 0.000000 | — | code only (local compute: unknown) |
| group | 0.1 | 0 | 0 | 0 | 0 | 0 | 0.000000 | — | code only (local compute: unknown) |
| rank | 0.08 | 0 | 0 | 0 | 0 | 0 | 0.000000 | — | code only (local compute: unknown) |
| memo | 0.1 | 0 | 0 | 0 | 0 | 0 | 0.000000 | — | code only (local compute: unknown) |

**Metered API total: $0.000000** · cost per 1,000 input rows $0.000000 · per completed record $0.00000000 · local compute: unknown

### Pilot outcomes

Completed 100 · quarantined 0 · exact-text cache hits 0 · unique texts 100

**Warm rerun: 0 new enrichment calls**, incremental metered cost $0.000000, wall 0.99 s.

## Projections (editable: `assumptions.json`)

Measured per distinct text (cold run): 278.2 Jev input tokens incl. retries (retry rate 0.0%); verifier 248 in / 81 out tokens and 0.82 s per review; group/memo 3614 in / 960 out tokens and 12.5 s per call. Fixed overhead (group + memo, 3 calls, prepare) is added once. Fallback fraction: 0% (No stronger-model fallback: reviews that fail validation twice are quarantined, not escalated.)

| scope | scenario | texts classified | Jev requests | Jev metered $ | Haiku (subscription) API-equiv $ | est. wall time | within budget? |
|---|---|---|---|---|---|---|---|
| analysis_10000 | base | 8,448 | 169 | 0.10 | unknown (≈0.68) | 0.24 h | yes |
| analysis_10000 | conservative | 8,448 | 178 | 0.13 | unknown (≈0.85) | 0.24 h | yes |
| analysis_10000 | base, no reuse | 10,000 | 200 | 0.12 | unknown (≈0.68) | 0.24 h | yes |
| full_660622 | base | 484,189 | 9,684 | 5.66 | unknown (≈1.33) | 0.60 h | yes |
| full_660622 | conservative | 484,189 | 10,169 | 7.43 | unknown (≈1.66) | 0.74 h | yes |
| full_660622 | base, no reuse | 660,609 | 13,213 | 7.72 | unknown (≈1.33) | 0.65 h | yes |

Budget: $10.0 metered API spend (Jev). Enrichment workers 8 (efficiency 0.8 base / 0.4 conservative), capped by 80 req/s. Haiku runs on a subscription: its charge is reported as unknown, never as zero. Projections are estimates; measured pilot rows above do not change when assumptions or rates change.

