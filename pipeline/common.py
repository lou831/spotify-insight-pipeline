"""Shared constants and helpers. Reuses the course checker's CSV reader and row hash
so our source_sha256 values match the grader byte for byte."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from check_submission import csv_rows, row_sha, sha, FIELDS, TOPICS, INTENTS  # noqa: E402,F401

OUT = ROOT / "outputs"
PROMPTS = ROOT / "prompts"

# Cheapest Claude model; swap only if golden-set evaluation shows it is not good enough.
MODEL = "claude-haiku-4-5"
PROMPT_VERSION = "enrich_v1"
SCHEMA_VERSION = "s1"
LABEL_CONFIG = f"{MODEL}+{PROMPT_VERSION}+{SCHEMA_VERSION}+nothink"

# USD per million tokens (Anthropic list price, checked 2026-10-03). Batch API halves these.
PRICES = {"claude-haiku-4-5": (1.00, 5.00), "claude-sonnet-5-5": (2.00, 10.00)}

BATCH_SIZE = 50  # contract maximum per enrichment request


def cost_usd(model, input_tokens, output_tokens, batch=False):
    p_in, p_out = PRICES[model]
    c = (input_tokens * p_in + output_tokens * p_out) / 1_000_000
    return c / 2 if batch else c


def append_jsonl(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    for i, line in enumerate(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            if i == len(lines) - 1:  # a line cut off by an interruption: ignore it, the work stays pending
                print(f"note: ignoring truncated last line in {path.name}")
                continue
            raise
    return out
