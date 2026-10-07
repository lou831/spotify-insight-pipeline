# Class 7 check-in — Spotify Insight Pipeline

Status as of 2026-10-04. Cost so far: **$0** (all model calls ran on a Claude Pro plan via the Claude Code CLI in headless mode).

## 1. Labels and rubric
- 8 common topics, intent precedence and the 1–5 severity scale from `GRADING_CONTRACT.md`, used unchanged.
- Model instructions: [prompts/enrich_v1.md](prompts/enrich_v1.md), with 10 worked examples taken only from `checkpoint_500.csv` (none from the golden set).
- Hand-labeled golden 50: [evals/golden_50_labeled.csv](evals/golden_50_labeled.csv) (notes on 8 hard cases). The labels were locked *before* any model run on these reviews: [evals/golden_lock.json](evals/golden_lock.json).

## 2. Pipeline so far
| Stage | Owner | File | Status |
|---|---|---|---|
| Ingest + profile all 660,622 rows | code | `pipeline/ingest.py` → `outputs/ingestion.json` | ✅ matches manifest (13 empty texts, 159,701 missing versions, 0 duplicate IDs, 484,189 distinct texts) |
| Enrich | model (Haiku 4.5) + code | `pipeline/enrich.py` | ✅ golden 50 + 500 checkpoint |
| Evaluate vs. golden | code | `pipeline/evaluate.py` | ✅ |
| Cost projection | code | `pipeline/project_cost.py` | ✅ |
| Verify, group, rank, memo | — | — | after Class 7 |

How code controls the model:
- At most 50 reviews per call. Reviews are numbered 1–50 in the request, and code maps the numbers back to review IDs, which saves output tokens.
- Exact-text deduplication with `cache_source_id`, so repeated texts are labeled once.
- Every returned item is validated in code: allowed labels, value ranges, IDs, and an exact-substring check on the quote.
- One retry, for the failed items only. Items that still fail go to quarantine with a reason.
- Results are saved after every batch. Resume skips IDs that are already done. There is a spend cap and a stop-after flag.

## 3. Golden-set results (n = 50, label_config `claude-haiku-4-5+enrich_v1+s1+nothink`)
| Metric | Thinking OFF (chosen) | Thinking ON |
|---|---|---|
| Topic agreement | 66% | 66% |
| Intent agreement | 82% | 84% |
| Severity exact / mean abs. error | 70% / 0.29 | 76% / 0.25 |
| Sentiment within ±0.3 (predeclared) / MAE | 58% / 0.32 | 66% / 0.30 |
| needs_review agreement | 84% | 94% |
| Output tokens for 49 reviews | 2,929 | 16,172 |
| Time | 25 s | 190 s |
| Quarantined | 1 | 1 |

Missing and quarantined reviews count as wrong.

**Choice:** thinking off. Accuracy drops slightly, but output tokens fall 5.5× and the run is 7× faster, which is what makes a large run feasible. Full detail: [evals/golden50_eval.json](evals/golden50_eval.json) and [evals/golden50_disagreements.csv](evals/golden50_disagreements.csv).

The most common topic confusion is **other ↔ usability**, plus **other ↔ catalog**: general complaints versus ad and recommendation complaints.

### Inspected disagreements (10 of 27, human verdicts)
Source: [evals/golden50_disagreements_review.xlsx](evals/golden50_disagreements_review.xlsx). Verdicts: **AI wrong 4 · I was wrong 5 · ambiguous 1**. The golden labels were *not* changed after this review.

| Review (excerpt) | Mine → AI | Verdict | Why |
|---|---|---|---|
| "Staff must be full of… Banning conservative music…" | catalog/complaint/2 → other/unclear/1 | AI wrong | Complains about songs being removed, a catalog issue, not a bare slogan |
| "Update: I reached out to Spotify Support… able to get the app working" | support/praise → playback/praise | AI wrong | First specific praised feature is customer support |
| "What is happening with Spotify?? …trying to play a song…" | access → playback | AI wrong | I read it as the app not opening |
| "Too expensive and the free version is pretty much unusable with constant ads" | severity 2 → 3 | AI wrong | Ads are part of the free tier, an annoyance rather than lost function |
| "Very good but wen I play my song it o ly plays a little bit then it st[ops]" | usability/2 → playback/3 | I was wrong | It's a playback failure, and the function is degraded |
| "I LOVE that I was able to put in only a few songs… Spotify g[enerates]" | other → catalog | I was wrong | Praises recommendations, a specific feature |
| "Nice app, very less advertising" | other → usability | I was wrong | Ads belong to usability |
| "Very poor updates as we cannot playback the songs…" | severity 4 → 3 | I was wrong | I judged it less severe than a core item failing |
| "paying for subscribing but unable to play in offline mode really?" | severity 2 → 3 | I was wrong | Offline is a restricted function, so 3 |
| "This update very bad for everyone. old Spotify. we all want." | other → usability | Ambiguous | No specific defect is named |

**Patterns:**
- (a) My labels drifted toward `other` when a specific feature was named. Three of my five errors were this, and the topic rules say to prefer the first specific feature.
- (b) The AI misses context-dependent topics, such as support praise and content removal.
- (c) Severity disagreements are all off by one, between 2/3 and 3/4.

**Next prompt revision** (to be tuned on dev data only, not the golden set):
- Add an example of support praise.
- Clarify "songs removed or banned" as `catalog`.

## 4. 500-review development run
- 500 rows: **499 completed, 1 quarantined, 0 pending**. 16 calls, 0 failed calls, 4.2% retry overhead, 9 exact-duplicate reuses.
- **Interruption/resume demo:** stopped after 3 batches with 161 completed. The rerun used `phase=resume` and labeled the remaining 329 distinct texts. **0 already-completed IDs were re-sent.** Snapshots: `outputs/runs/dev500/checkpoint_initial_*.json` and `checkpoint_resume_*.json`.
- Label mix:
  - **Topic:** other 287, usability 65, billing 53, playback 48, catalog 27, access 10, downloads 7, support 2
  - **Intent:** praise 222, complaint 207, cancellation 28, unclear 24, request 18
  - **Severity:** 1 → 262, 2 → 124, 3 → 80, 4 → 33. No 5s.

### Inspected failures (both quarantined because `quote_not_in_text`, twice)
1. **Golden:** a review with **embedded line breaks** ("…saved ⏎albums/artists…"). The model's quote dropped the line break, so the exact-substring check failed. Fix idea: allow the model to quote within a single line.
2. **Dev:** "GET PRENIUM ITS WORTH…" — the model likely **auto-corrected the typo** in its quote. This is evidence that the check matters: a fluent quote is not always an exact one.

## 5. Measured cost and runtime ([evals/cost_projection_dev500.json](evals/cost_projection_dev500.json))
Measured per distinct text: about 107 input and 68 output tokens, 0.52 s.

Each projected row includes:
- enrichment of the distinct texts
- **retries**, at the measured 4.2% overhead
- **verification** of a declared random sample (1,000 reviews for 10K, 2,000 for the full run)
- about 30 group and memo calls (an assumption: about 3k tokens in and 1k out each)

| Scope | Calls | Tokens (in / out) | API-equivalent cost (standard / Batch API) | Cost on Pro plan | Sequential time |
|---|---|---|---|---|---|
| 500 dev (measured) | 16 | 51K / 33K | $0.21 | $0 | 3 min |
| 10,000 sample | 219 | 1.10M / 0.67M | $4.46 / $2.23 | $0 | ~1.4 h |
| Full 660,622 (484,189 distinct) | 9,754 | 51.9M / 33.1M | $217 / $109 | $0, but limited by Pro usage caps | ~71 h |

**Spending limit (declared before scaling): $0.**
- All model calls run on the Claude Pro plan, which cannot incur per-token charges.
- If the API backend is ever used, `enrich.py --backend api` stops at `--max-usd`, which defaults to $1. Any increase would be declared here before the run.
- Throughput is limited by Pro usage windows, not money.

## 6. Questions for the instructor
1. The course website says the 10,000-review sample is the default model run, while the Word brief and `GRADING_CONTRACT.md` require all 660,609 nonempty reviews. Which applies?
2. If the full run is required: are course API credits available? A full run is about 9,700 calls, which exceeds what Pro usage limits allow in a reasonable time.
3. Is running the model through Claude Code headless mode on a Pro plan acceptable evidence? Calls are logged with session IDs and token usage.
