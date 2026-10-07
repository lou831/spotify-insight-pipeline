"""Claude Haiku calls for the verify / group / memo roles.

Runs through the Claude Code CLI in headless mode on the user's Claude Pro plan
(billing_mode="subscription"): there is no metered per-call charge we can observe, so cost
is logged as unknown and an API-equivalent estimate is recorded next to it.
No tools, no MCP servers, no user settings, thinking off, our own system prompt only.
"""

import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone

from common import append_jsonl, cost_usd

HAIKU = "claude-haiku-4-5"
CLI = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


class LLMError(Exception):
    pass


def haiku_json(system, user, schema, *, role, log_path, review_ids=(), phase="initial", label_config="",
               run_id="", timeout=600):
    """One bounded Haiku call returning parsed JSON; every attempt is appended to log_path."""
    cmd = [CLI, "-p", "--model", "haiku", "--output-format", "json", "--system-prompt", system,
           "--json-schema", json.dumps(schema), "--tools", "", "--strict-mcp-config",
           "--setting-sources", "", "--no-session-persistence"]
    env = {**os.environ, "MAX_THINKING_TOKENS": "0"}
    call = {"request_id": f"local-{uuid.uuid4()}", "run_id": run_id, "role": role, "review_ids": list(review_ids),
            "model": HAIKU, "phase": phase, "label_config": label_config, "backend": "claude-code-cli",
            "billing_mode": "subscription", "effort": "no-thinking",
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=timeout,
                              cwd=os.path.expanduser("~"), env=env)
        out = json.loads(proc.stdout)
        if out.get("is_error"):
            raise LLMError(str(out.get("result", ""))[:200])
        data = out.get("structured_output")
        if data is None:
            data = json.loads(out.get("result", ""))
    except (ValueError, subprocess.TimeoutExpired, LLMError) as e:
        call.update(outcome="failed", error=f"{type(e).__name__}: {str(e)[:200]}", input_tokens=0, output_tokens=0,
                    cost_usd=None, elapsed_s=round(time.time() - t0, 2))
        append_jsonl(log_path, call)
        raise LLMError(call["error"])
    u = out.get("usage", {})
    tin = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
    tout = u.get("output_tokens", 0)
    call.update(request_id="cli-" + out.get("session_id", call["request_id"]), outcome="succeeded",
                served_by=next(iter(out.get("modelUsage") or {}), HAIKU), input_tokens=tin, output_tokens=tout,
                cost_usd=None, api_equivalent_usd=round(cost_usd(HAIKU, tin, tout), 6),
                elapsed_s=round(time.time() - t0, 2))
    append_jsonl(log_path, call)
    return data
