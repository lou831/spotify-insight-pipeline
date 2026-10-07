"""Stage 2 — Enrich (model worker + code control).

Code owns: batching (<=50), exact-text dedup, validation, one retry, quarantine,
saving after every batch, resume, spend cap and logging. The model only reads text.

    # free: estimate tokens/cost, no API call
    python pipeline/enrich.py checkpoint_500.csv --run dev500 --dry-run
    # free on a Claude Pro/Max plan: calls the Claude Code CLI headlessly (default backend)
    python pipeline/enrich.py checkpoint_500.csv --run dev500
    # paid alternative: Anthropic API key in .env
    python pipeline/enrich.py checkpoint_500.csv --run dev500 --backend api --max-usd 1
    # interruption demo: stop after 3 batches, then rerun the same command to resume
    python pipeline/enrich.py checkpoint_500.csv --run dev500 --stop-after 3
"""

import argparse
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone

from common import (BATCH_SIZE, INTENTS, LABEL_CONFIG, MODEL, OUT, PROMPT_VERSION, PROMPTS, TOPICS,
                    append_jsonl, cost_usd, csv_rows, read_jsonl, row_sha)

SYSTEM = (PROMPTS / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")

SCHEMA = {
    "type": "object",
    "properties": {"r": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "n": {"type": "integer"},
            "topic": {"type": "string", "enum": list(TOPICS)},
            "intent": {"type": "string", "enum": list(INTENTS)},
            "sent": {"type": "number"},
            "sev": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
            "ent": {"type": "array", "items": {"type": "string"}},
            "quote": {"type": "string"},
            "nr": {"type": "boolean"},
        },
        "required": ["n", "topic", "intent", "sent", "sev", "ent", "quote", "nr"],
        "additionalProperties": False,
    }}},
    "required": ["r"],
    "additionalProperties": False,
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_env():
    env = OUT.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def user_message(texts):
    return "\n".join(f"[{i}] {t}" for i, t in enumerate(texts, 1))


def validate(item, text):
    """Return an error string, or None if the item is a valid label for `text`."""
    if item.get("topic") not in TOPICS:
        return "bad_topic"
    if item.get("intent") not in INTENTS:
        return "bad_intent"
    if type(item.get("sev")) is not int or not 1 <= item["sev"] <= 5:
        return "bad_severity"
    s = item.get("sent")
    if type(s) not in (int, float) or not -1 <= s <= 1:
        return "bad_sentiment"
    if not isinstance(item.get("ent"), list) or not all(isinstance(e, str) and e.strip() for e in item["ent"]):
        return "bad_entities"
    q = item.get("quote")
    if not isinstance(q, str) or not q.strip():
        return "empty_quote"
    if q not in text:
        return "quote_not_in_text"
    if type(item.get("nr")) is not bool:
        return "bad_needs_review"
    return None


def to_record(rid, row, item, cache_source=None):
    rec = {"review_id": rid, "source_sha256": row_sha(row), "status": "completed",
           "topic": item["topic"], "intent": item["intent"], "sentiment": float(item["sent"]),
           "severity": item["sev"], "entities": [e.strip() for e in item["ent"]],
           "evidence_quote": item["quote"], "needs_review": item["nr"], "label_config": LABEL_CONFIG}
    if cache_source:
        rec["cache_source_id"] = cache_source
    return rec


class CallError(Exception):
    pass


def call_api(client, texts):
    """Anthropic API (pay per token). Returns a uniform result dict."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=60 * len(texts) + 200,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_message(texts)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return {"text": text, "input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens,
            "request_id": resp._request_id, "stop_reason": resp.stop_reason, "model": MODEL, "billed": True}


CLI = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def call_cli(_client, texts):
    """Claude Code CLI in headless mode, billed to the user's Pro/Max plan (no API charge).
    No tools, no MCP servers, no user settings, our own system prompt only."""
    cmd = [CLI, "-p", "--model", "haiku", "--output-format", "json", "--system-prompt", SYSTEM,
           "--json-schema", json.dumps(SCHEMA), "--tools", "", "--strict-mcp-config",
           "--setting-sources", "", "--no-session-persistence"]
    env = {**os.environ, "MAX_THINKING_TOKENS": "0"}  # thinking off: ~4x fewer output tokens, same format
    proc = subprocess.run(cmd, input=user_message(texts), capture_output=True, text=True, timeout=600,
                          cwd=os.path.expanduser("~"), env=env)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        raise CallError(f"cli_exit_{proc.returncode}: {(proc.stderr or proc.stdout)[:200]}")
    if out.get("is_error"):
        raise CallError("cli_error: " + str(out.get("result", ""))[:200])
    so = out.get("structured_output")
    text = json.dumps(so) if so is not None else out.get("result", "")
    u = out.get("usage", {})
    models = list((out.get("modelUsage") or {}).keys())
    return {"text": text,
            "input_tokens": u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0), "request_id": "cli-" + out.get("session_id", str(uuid.uuid4())),
            "stop_reason": out.get("subtype"), "model": models[0] if models else MODEL, "billed": False,
            "api_equivalent_usd": out.get("total_cost_usd")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--run", required=True, help="run name; outputs go to outputs/runs/<run>/")
    ap.add_argument("--backend", choices=["cli", "api"], default="cli",
                    help="cli = Claude Code on your Pro plan (no charge); api = pay-per-token API key")
    ap.add_argument("--dry-run", action="store_true", help="estimate only, no API calls")
    ap.add_argument("--max-usd", type=float, default=1.0, help="stop before exceeding this spend")
    ap.add_argument("--stop-after", type=int, default=0, help="stop after N batches (interruption demo)")
    args = ap.parse_args()

    d = OUT / "runs" / args.run
    d.mkdir(parents=True, exist_ok=True)
    f_rec, f_q, f_calls = d / "records.jsonl", d / "quarantine.jsonl", d / "calls.jsonl"

    rows = {r["review_id"]: r for r in csv_rows(args.csv)}
    done = {r["review_id"]: r for r in read_jsonl(f_rec)}
    quarantined = {r["review_id"] for r in read_jsonl(f_q)}
    prior_calls = read_jsonl(f_calls)
    spent = sum(c.get("cost_usd") or 0 for c in prior_calls if c["role"] == "enrich")
    phase = "resume" if any(c["role"] == "enrich" for c in prior_calls) else "initial"

    # Empty texts: quarantine without a model call.
    for rid, r in rows.items():
        if not r["review_text"].strip() and rid not in quarantined:
            append_jsonl(f_q, {"review_id": rid, "source_sha256": row_sha(r), "status": "quarantined",
                               "reason": "empty_review_text", "attempts": 0})
            quarantined.add(rid)

    # Exact-text cache: the first completed ID for each text is the direct original.
    origin_by_text = {}
    for rid, rec in done.items():
        if not rec.get("cache_source_id") and rec["label_config"] == LABEL_CONFIG:
            origin_by_text.setdefault(rows[rid]["review_text"], rid)

    def fill_from_cache():
        n = 0
        for rid, r in rows.items():
            if rid in done or rid in quarantined:
                continue
            src = origin_by_text.get(r["review_text"])
            if src:
                base = done[src]
                item = {"topic": base["topic"], "intent": base["intent"], "sent": base["sentiment"], "sev": base["severity"],
                        "ent": base["entities"], "quote": base["evidence_quote"], "nr": base["needs_review"]}
                rec = to_record(rid, r, item, cache_source=src)
                append_jsonl(f_rec, rec)
                done[rid] = rec
                n += 1
        return n

    fill_from_cache()

    # Distinct texts still needing a model call, each represented by its first ID.
    todo, seen = [], set()
    for rid, r in rows.items():
        t = r["review_text"]
        if rid in done or rid in quarantined or t in seen or t in origin_by_text:
            continue
        seen.add(t)
        todo.append(rid)
    batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    print(f"rows={len(rows)} done={len(done)} quarantined={len(quarantined)} distinct_todo={len(todo)} "
          f"batches={len(batches)} phase={phase} spent_so_far=${spent:.4f}")

    if args.dry_run:
        sys_tok = len(SYSTEM) / 3.5
        in_tok = sum(sys_tok + len(user_message([rows[i]["review_text"] for i in b])) / 3.5 + 300 for b in batches)
        out_tok = len(todo) * 45 + 30 * len(batches)  # assumption: ~45 output tokens per review
        print(json.dumps({"estimated_input_tokens": int(in_tok), "estimated_output_tokens": int(out_tok),
                          "estimated_cost_usd_standard": round(cost_usd(MODEL, in_tok, out_tok), 4),
                          "estimated_cost_usd_batch_api": round(cost_usd(MODEL, in_tok, out_tok, batch=True), 4),
                          "note": "rough character-based estimate; replace with measured usage after a paid pilot"}, indent=2))
        return

    if args.backend == "api":
        load_env()
        import anthropic
        client, call_model, errors = anthropic.Anthropic(), call_api, (anthropic.APIError, CallError)
    else:
        client, call_model, errors = None, call_cli, (CallError, subprocess.TimeoutExpired)

    def run_batch(ids, attempt):
        """Call once; return (valid items by id, failed ids with reasons)."""
        nonlocal spent
        texts = [rows[i]["review_text"] for i in ids]
        call = {"request_id": f"local-{uuid.uuid4()}", "role": "enrich", "review_ids": ids, "model": MODEL,
                "phase": phase, "label_config": LABEL_CONFIG, "attempt": attempt, "started_at": now()}
        t0 = time.time()
        try:
            res = call_model(client, texts)
        except errors as e:
            call.update(outcome="failed", error=f"{type(e).__name__}: {str(e)[:200]}", input_tokens=0, output_tokens=0,
                        backend=args.backend, elapsed_s=round(time.time() - t0, 2))
            append_jsonl(f_calls, call)
            return {}, {i: "call_error:" + type(e).__name__ for i in ids}
        text = res["text"]
        c = cost_usd(MODEL, res["input_tokens"], res["output_tokens"]) if res["billed"] else 0.0
        spent += c
        call.update(request_id=res["request_id"] or call["request_id"], input_tokens=res["input_tokens"],
                    output_tokens=res["output_tokens"], cost_usd=round(c, 6), stop_reason=res["stop_reason"],
                    backend=args.backend, served_by=res["model"],
                    api_equivalent_usd=res.get("api_equivalent_usd", round(cost_usd(MODEL, res["input_tokens"], res["output_tokens"]), 6)),
                    elapsed_s=round(time.time() - t0, 2))
        good, bad = {}, {}
        try:
            items = json.loads(text)["r"]
        except (ValueError, KeyError, TypeError):
            items = []
        by_n = {}
        for it in items:
            n = it.get("n") if isinstance(it, dict) else None
            if type(n) is int and 1 <= n <= len(ids):
                by_n.setdefault(n, []).append(it)
        for n, rid in enumerate(ids, 1):
            got = by_n.get(n, [])
            if len(got) != 1:
                bad[rid] = "missing_id" if not got else "duplicate_id"
                continue
            err = validate(got[0], rows[rid]["review_text"])
            if err:
                bad[rid] = err
            else:
                good[rid] = got[0]
        extra = [n for n in by_n if not 1 <= n <= len(ids)]
        call.update(outcome="succeeded" if good else "failed", valid=len(good), invalid=len(bad), foreign_ids=len(extra))
        append_jsonl(f_calls, call)
        return good, bad

    def save(good):
        for rid, item in good.items():
            rec = to_record(rid, rows[rid], item)
            append_jsonl(f_rec, rec)
            done[rid] = rec
            origin_by_text.setdefault(rows[rid]["review_text"], rid)

    started = time.time()
    for bi, ids in enumerate(batches, 1):
        if spent >= args.max_usd:
            print(f"spend cap ${args.max_usd} reached; progress saved")
            break
        good, bad = run_batch(ids, attempt=1)
        save(good)
        if bad:  # one retry, only for the failed reviews
            good2, bad2 = run_batch(list(bad), attempt=2)
            save(good2)
            for rid, reason in bad2.items():
                append_jsonl(f_q, {"review_id": rid, "source_sha256": row_sha(rows[rid]), "status": "quarantined",
                                   "reason": f"{bad[rid]}|retry:{reason}", "attempts": 2})
                quarantined.add(rid)
        print(f"batch {bi}/{len(batches)} ok={len(done)} quarantined={len(quarantined)} spent=${spent:.4f}")
        if args.stop_after and bi >= args.stop_after:
            print("stopping early on request (interruption demo); rerun the same command to resume")
            break
    reused = fill_from_cache()
    summary = {"run": args.run, "input": args.csv, "label_config": LABEL_CONFIG, "rows": len(rows),
               "completed": len(done), "quarantined": len(quarantined),
               "pending": len(rows) - len(done) - len(quarantined), "cache_reused_this_session": reused,
               "total_spent_usd": round(spent, 6), "elapsed_s_this_session": round(time.time() - started, 1),
               "finished_at": now()}
    (d / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (d / f"checkpoint_{phase}_{int(time.time())}.json").write_text(
        json.dumps({"completed_ids": sorted(done)}, indent=0) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
