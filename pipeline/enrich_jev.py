"""Stage 2 — Enrich with Jev (TypeSafe System One), the low-cost primary enricher.

Cost design:
  * batching: up to 50 reviews per request; the rubric is sent ONCE per request in `state`
    and each per-review question only names its options (Jev bills input tokens only)
  * caching: exact duplicate texts are labeled once and reused via cache_source_id
  * queue + parallel workers: bounded concurrency under Jev's rate limits
  * durable progress: results appended after every completed batch; rerun resumes
Code owns validation, one retry for failed reviews, quarantine, spend cap and logs.
Evidence quotes are chosen by Jev from the review's own sentences (always exact
substrings); entities come from a documented keyword lexicon (deterministic).

    python pipeline/enrich_jev.py golden_50_to_label.csv --run jev_golden50 --max-usd 0.05
    python pipeline/enrich_jev.py spotify_reviews_18months.csv --run full --max-usd 8 --workers 8
    python pipeline/enrich_jev.py checkpoint_500.csv --run x --dry-run
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone

from common import OUT, PROMPTS, ROOT, TOPICS, INTENTS, append_jsonl, csv_rows, read_jsonl, row_sha

CFG = json.loads((PROMPTS / (os.environ.get("JEV_PROMPT", "jev_v3") + ".json")).read_text(encoding="utf-8"))
JEV_MODEL = "jev-1.13.0"  # pinned version, not the moving alias
LABEL_CONFIG = f"{JEV_MODEL}+{CFG['version']}+s1"
PRICE_PER_MTOK = 0.042  # input only; output tokens are free
MAX_SENTENCES = 8

# Deterministic entity lexicon: canonical name -> regex (case-insensitive)
LEXICON = {
    "ads": r"\bad(s|vert\w*)?\b|\badds\b|commercial", "shuffle": r"shuffl", "skip": r"\bskip",
    "premium": r"prem[ie]um|prenium", "offline": r"off ?line", "download": r"download",
    "playlist": r"play ?list", "podcast": r"podcast", "lyrics": r"lyric", "search": r"\bsearch",
    "recommendations": r"recommend|suggest", "login": r"log ?in|sign ?in|logged out|log out",
    "password": r"password", "account": r"\baccount", "update": r"\bupdat", "crash": r"crash",
    "queue": r"\bqueue", "price": r"\bprice|expensive|\bcost", "subscription": r"subscri",
    "refund": r"refund", "payment": r"payment|charged|\bcharge", "family plan": r"family",
    "student plan": r"student", "home screen": r"home ?screen|homepage|home page",
    "widget": r"widget", "bluetooth": r"bluetooth", "android auto": r"android auto|\bcar\b",
    "audiobooks": r"audiobook", "radio": r"\bradio", "equalizer": r"equali[sz]er", "dj": r"\bdj\b",
    "sleep timer": r"sleep timer", "notifications": r"notification", "connect": r"spotify connect|chromecast",
    "customer support": r"customer (service|support)|\bsupport\b", "storage": r"storage|\bspace\b|cache",
    "battery": r"batter", "audio quality": r"sound quality|audio quality|\bquality",
}
LEX = {k: re.compile(v, re.I) for k, v in LEXICON.items()}
SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def entities(text):
    return [k for k, rx in LEX.items() if rx.search(text)]


def sentences(text):
    """Exact substrings of text, in order, each with at least 2 letters."""
    out = []
    for m in SENT_RE.finditer(text):
        s = m.group().strip()
        if len(re.findall(r"\w", s)) >= 2:
            out.append(s)
    return out


def code_quote(text, topic):
    """Deterministic evidence: whole text if one sentence; else first sentence matching the topic's
    keyword rules, else first sentence naming a product term, else the first sentence."""
    from group import RX  # same documented keyword rules used for grouping
    ss = sentences(text)
    if len(ss) <= 1:
        return ss[0] if ss else text.strip()
    for _, rx in RX.get(topic, []):
        if rx.pattern == ".":
            continue
        for s in ss:
            if rx.search(s):
                return s
    for s in ss:
        if any(r.search(s) for r in LEX.values()):
            return s
    return ss[0]


def build_request(texts):
    """One state with the rubric once + up to 50 reviews; 4-5 questions per review."""
    from typesafe_sdk import Choice, Score
    q, sents = {}, {}
    reviews = {}
    for i, t in enumerate(texts, 1):
        rid = f"r{i}"
        reviews[rid] = t
        q[f"{rid}_topic"] = Choice(instructions=CFG["questions"]["topic"].format(rid=rid),
                                   criteria={k: None for k in TOPICS})
        q[f"{rid}_intent"] = Choice(instructions=CFG["questions"]["intent"].format(rid=rid),
                                    criteria={k: None for k in INTENTS})
        q[f"{rid}_sev"] = Choice(instructions=CFG["questions"]["severity"].format(rid=rid),
                                 criteria={k: None for k in "12345"})
        q[f"{rid}_sent"] = Score(instructions=CFG["questions"]["sentiment"].format(rid=rid),
                                 criteria=CFG["sentiment_levels"])
        ss = sentences(t)[:MAX_SENTENCES]
        if len(ss) >= 2 and CFG.get("evidence_mode") != "code":
            sents[rid] = ss
            q[f"{rid}_ev"] = Choice(instructions=CFG["questions"]["evidence"].format(rid=rid),
                                    criteria={f"s{j}": s for j, s in enumerate(ss, 1)})
    state = {"rubric": CFG["rubric"], "reviews": reviews}
    return state, q, sents


def parse(answers, i, text, sents):
    """Turn Jev answers for review i into our record fields (or raise KeyError/ValueError)."""
    rid = f"r{i}"
    top, inte, sev, sen = (answers[f"{rid}_{k}"] for k in ("topic", "intent", "sev", "sent"))
    if rid in sents:
        quote = sents[rid][int(answers[f"{rid}_ev"].choice[1:]) - 1]
    else:
        quote = code_quote(text, top.choice)
    conf = {"topic": round(top.confidence, 3), "intent": round(inte.confidence, 3), "severity": round(sev.confidence, 3)}
    nr = conf["topic"] < 0.5 or conf["intent"] < 0.5 or conf["severity"] < 0.4
    return {"topic": top.choice, "intent": inte.choice, "sev": int(sev.choice),
            "sent": round(max(-1.0, min(1.0, sen.score / 2 - 1)), 3), "ent": entities(text),
            "quote": quote, "nr": nr}, conf


def validate(item, text):
    if item["topic"] not in TOPICS or item["intent"] not in INTENTS:
        return "bad_label"
    if not 1 <= item["sev"] <= 5 or not -1 <= item["sent"] <= 1:
        return "bad_range"
    if not item["quote"].strip() or item["quote"] not in text:
        return "quote_not_in_text"
    return None


def to_record(rid, row, item, conf=None, cache_source=None):
    rec = {"review_id": rid, "source_sha256": row_sha(row), "status": "completed",
           "topic": item["topic"], "intent": item["intent"], "sentiment": float(item["sent"]),
           "severity": item["sev"], "entities": item["ent"], "evidence_quote": item["quote"],
           "needs_review": item["nr"], "label_config": LABEL_CONFIG}
    if conf:
        rec["confidence"] = conf
    if cache_source:
        rec["cache_source_id"] = cache_source
    return rec


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


async def main_async(args):
    d = OUT / "runs" / args.run
    d.mkdir(parents=True, exist_ok=True)
    f_rec, f_q, f_calls = d / "records.jsonl", d / "quarantine.jsonl", d / "calls.jsonl"
    rows = {r["review_id"]: r for r in csv_rows(args.csv)}
    done = {r["review_id"]: r for r in read_jsonl(f_rec)}
    quarantined = {r["review_id"] for r in read_jsonl(f_q)}
    prior = read_jsonl(f_calls)
    spent = sum(c.get("cost_usd") or 0 for c in prior if c["role"] == "enrich")
    phase = "resume" if any(c["role"] == "enrich" for c in prior) else "initial"

    for rid, r in rows.items():
        if not r["review_text"].strip() and rid not in quarantined:
            append_jsonl(f_q, {"review_id": rid, "source_sha256": row_sha(r), "status": "quarantined",
                               "reason": "empty_review_text", "attempts": 0})
            quarantined.add(rid)

    origin = {}
    for rid, rec in done.items():
        if not rec.get("cache_source_id") and rec["label_config"] == LABEL_CONFIG:
            origin.setdefault(rows[rid]["review_text"], rid)

    def fill_cache():
        n = 0
        for rid, r in rows.items():
            if rid in done or rid in quarantined:
                continue
            src = origin.get(r["review_text"])
            if src:
                b = done[src]
                item = {"topic": b["topic"], "intent": b["intent"], "sent": b["sentiment"], "sev": b["severity"],
                        "ent": b["entities"], "quote": b["evidence_quote"], "nr": b["needs_review"]}
                rec = to_record(rid, r, item, cache_source=src)
                append_jsonl(f_rec, rec)
                done[rid] = rec
                n += 1
        return n

    fill_cache()
    todo, seen = [], set()
    for rid, r in rows.items():
        t = r["review_text"]
        if rid in done or rid in quarantined or t in seen or t in origin:
            continue
        seen.add(t)
        todo.append(rid)
    batches = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    print(f"rows={len(rows)} done={len(done)} quarantined={len(quarantined)} distinct_todo={len(todo)} "
          f"batches={len(batches)} phase={phase} spent=${spent:.4f}", flush=True)

    if args.dry_run:
        tok = sum(len(json.dumps(build_request([rows[i]["review_text"] for i in b])[0], ensure_ascii=False)) / 3.5
                  + sum(130 + (60 if len(sentences(rows[i]["review_text"])) >= 2 else 0) for i in b) for b in batches)
        print(json.dumps({"estimated_input_tokens": int(tok), "estimated_cost_usd": round(tok * PRICE_PER_MTOK / 1e6, 2),
                          "note": "character-based estimate; measure with a small paid run"}, indent=2))
        return

    load_env()
    from typesafe_sdk import (AsyncTypeSafeClient, TypeSafeAuthenticationError, TypeSafeError,
                              TypeSafePermissionDeniedError)
    client = AsyncTypeSafeClient(model=JEV_MODEL)
    sem = asyncio.Semaphore(args.workers)
    stop = {"flag": False, "batches": 0, "api_errors": 0}
    ledger = {"reserved": 0.0}  # shared spend ledger: spent + in-flight reservations must stay under the cap

    def reserve_estimate(ids):
        """Worst-case cost of one request, reserved before dispatch (2x the character-based estimate)."""
        state, q, _ = build_request([rows[i]["review_text"] for i in ids])
        return 2 * (len(json.dumps(state, ensure_ascii=False)) / 3.5 + 190 * len(ids)) * PRICE_PER_MTOK / 1e6

    async def guarded_call(ids, attempt):
        est = reserve_estimate(ids)
        if spent + ledger["reserved"] + est > args.max_usd:
            stop["flag"] = True
            return None
        ledger["reserved"] += est
        try:
            async with sem:
                return await call(ids, attempt)
        finally:
            ledger["reserved"] -= est
    started = time.time()

    async def call(ids, attempt):
        nonlocal spent
        texts = [rows[i]["review_text"] for i in ids]
        state, questions, sents = build_request(texts)
        call = {"request_id": f"jev-{uuid.uuid4()}", "role": "enrich", "review_ids": ids, "model": JEV_MODEL,
                "phase": phase, "label_config": LABEL_CONFIG, "attempt": attempt, "backend": "typesafe",
                "started_at": now()}
        t0 = time.time()
        try:
            resp = await client.system_one(state=state, questions=questions)
        except TypeSafeError as e:
            call.update(outcome="failed", error=f"{type(e).__name__}: {str(e)[:200]}", input_tokens=0,
                        output_tokens=0, cost_usd=0.0, elapsed_s=round(time.time() - t0, 2))
            append_jsonl(f_calls, call)
            # Account/credit/auth problems or repeated API errors: stop cleanly, leave reviews pending
            # (they were never labeled, so they must not be quarantined as bad output).
            status = getattr(e, "status_code", None)
            stop["api_errors"] += 1
            if status in (401, 402, 403) or isinstance(e, (TypeSafeAuthenticationError, TypeSafePermissionDeniedError)) \
                    or stop["api_errors"] >= 5:
                stop["flag"] = True
                print(f"stopping: {type(e).__name__} (status {status}); saved work kept, rerun to resume", flush=True)
            return {}, {i: "API_ERROR" for i in ids}
        c = resp.usage.input_tokens * PRICE_PER_MTOK / 1e6
        spent += c
        good, bad = {}, {}
        for n, rid in enumerate(ids, 1):
            try:
                item, conf = parse(resp.answers, n, rows[rid]["review_text"], sents)
                err = validate(item, rows[rid]["review_text"])
            except (KeyError, ValueError, AttributeError, IndexError) as e:
                err, conf = "missing_or_malformed_answer:" + type(e).__name__, None
            if err:
                bad[rid] = err
            else:
                good[rid] = (item, conf)
        call.update(outcome="succeeded" if good else "failed", served_by=resp.model,
                    input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens,
                    cost_usd=round(c, 8), valid=len(good), invalid=len(bad), elapsed_s=round(time.time() - t0, 2))
        append_jsonl(f_calls, call)
        return good, bad

    def save(good):
        for rid, (item, conf) in good.items():
            rec = to_record(rid, rows[rid], item, conf)
            append_jsonl(f_rec, rec)
            done[rid] = rec
            origin.setdefault(rows[rid]["review_text"], rid)

    async def worker(queue):
        while True:
            ids = await queue.get()
            try:
                if stop["flag"]:
                    continue
                res = await guarded_call(ids, 1)
                if res is None:
                    print("spend cap reached (spent + reserved); progress saved", flush=True)
                    continue
                good, bad = res
                save(good)
                if any(v == "API_ERROR" for v in bad.values()):
                    continue  # call never succeeded: leave these reviews pending for a later rerun
                if bad:  # one retry, failed reviews only
                    res2 = await guarded_call(list(bad), 2)
                    good2, bad2 = res2 if res2 is not None else ({}, {i: "spend_cap_before_retry" for i in bad})
                    save(good2)
                    for rid, reason in bad2.items():
                        if reason == "API_ERROR":
                            continue  # retry call failed at the API: keep pending, not quarantined
                        append_jsonl(f_q, {"review_id": rid, "source_sha256": row_sha(rows[rid]),
                                           "status": "quarantined", "reason": f"{bad[rid]}|retry:{reason}",
                                           "attempts": 2})
                        quarantined.add(rid)
                stop["batches"] += 1
                if stop["batches"] % 25 == 0 or stop["batches"] == len(batches):
                    print(f"batches {stop['batches']}/{len(batches)} completed={len(done)} "
                          f"quarantined={len(quarantined)} spent=${spent:.4f} {time.time() - started:.0f}s", flush=True)
                if args.stop_after and stop["batches"] >= args.stop_after:
                    stop["flag"] = True
            finally:
                queue.task_done()

    def snapshot(tag):
        (d / f"checkpoint_{phase}_{int(time.time())}.json").write_text(json.dumps({"completed_ids": sorted(done)}) + "\n")
        print(f"checkpoint saved ({tag}): {len(done)} completed", flush=True)

    queue = asyncio.Queue()
    for b in batches:
        queue.put_nowait(b)
    workers = [asyncio.create_task(worker(queue)) for _ in range(args.workers)]
    try:
        await queue.join()
    except asyncio.CancelledError:  # Ctrl+C: completed batches are already on disk; record the checkpoint
        stop["flag"] = True
        snapshot("interrupted")
        print("interrupted: rerun the same command to resume", flush=True)
        raise
    for w in workers:
        w.cancel()
    await client.close() if hasattr(client, "close") else None

    reused = fill_cache()
    summary = {"run": args.run, "input": args.csv, "label_config": LABEL_CONFIG, "rows": len(rows),
               "completed": len(done), "quarantined": len(quarantined),
               "pending": len(rows) - len(done) - len(quarantined), "cache_reused_this_session": reused,
               "total_spent_usd": round(spent, 6), "spend_cap_usd": args.max_usd, "workers": args.workers,
               "elapsed_s_this_session": round(time.time() - started, 1), "stopped_early": stop["flag"],
               "finished_at": now()}
    (d / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    snapshot("end of session")
    print(json.dumps(summary, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--run", required=True)
    ap.add_argument("--batch", type=int, default=50, help="reviews per request (contract max 50)")
    ap.add_argument("--workers", type=int, default=4, help="concurrent requests")
    ap.add_argument("--max-usd", type=float, default=0.10, help="stop launching batches past this spend")
    ap.add_argument("--stop-after", type=int, default=0, help="stop after N batches (interruption demo)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.batch <= 50:
        raise SystemExit("--batch must be 1..50")
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        sys.exit(130)  # progress and checkpoint already saved; rerun the same command to resume


if __name__ == "__main__":
    main()
