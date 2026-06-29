"""Probe real token usage for cost estimation.

Makes a few real API calls with the actual auditor system prompts and real
MMLU items, reading the `usage` field from the raw response. Used to turn the
paper's parametric cost estimate into measured tokens. Cost: a handful of calls.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from benchcore.llm_auditor import (
    BLIND_SOLVER_SYSTEM_PROMPT,
    QUESTION_SYSTEM_PROMPT,
    OPTION_SYSTEM_PROMPT,
)
from benchcore.llm_client import LLMClient, load_llm_config

REPO = Path(__file__).resolve().parent.parent
INPUT = REPO / "experiments" / "mmlu_redux_pilot1000.jsonl"

# DeepSeek-V4-Flash pricing (RMB per 1M tokens)
PRICE_IN_MISS = 1.0
PRICE_OUT = 2.0


def user_payload(raw: dict, blind: bool = False) -> str:
    payload = {
        "item_id": raw["id"],
        "task": raw["question"],
        "context": None,
        "metadata_without_verified_labels": {"subject": raw.get("metadata", {}).get("subject")},
    }
    if not blind:
        payload.update({
            "choices": raw["choices"],
            "gold": raw["gold"],
            "evaluator": raw.get("evaluator"),
        })
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> None:
    cfg = load_llm_config(str(REPO / "configs" / "llm_deepseek.json"))
    client = LLMClient(cfg)
    import os
    api_key = os.environ[cfg.api_key_env]

    items = [json.loads(l) for l in INPUT.open(encoding="utf-8")][:3]
    specs = [
        ("blind_solver", BLIND_SOLVER_SYSTEM_PROMPT, True),
        ("question_clarity", QUESTION_SYSTEM_PROMPT, False),
        ("option_set", OPTION_SYSTEM_PROMPT, False),
    ]
    rows = []
    for name, sysprompt, blind in specs:
        for raw in items:
            body = {
                "model": cfg.model,
                "messages": [
                    {"role": "system", "content": sysprompt},
                    {"role": "user", "content": user_payload(raw, blind)},
                ],
                "temperature": 0.0,
                "max_tokens": cfg.max_tokens,
                "response_format": {"type": "json_object"},
            }
            resp = client._post_chat_completions(body, api_key)
            u = resp.get("usage", {})
            rows.append({
                "auditor": name,
                "prompt_tokens": u.get("prompt_tokens"),
                "completion_tokens": u.get("completion_tokens"),
                "cached": u.get("prompt_cache_hit_tokens"),
            })
            print(json.dumps(rows[-1]), flush=True)

    pin = statistics.mean(r["prompt_tokens"] for r in rows)
    pout = statistics.mean(r["completion_tokens"] for r in rows)
    cost_call = pin * PRICE_IN_MISS / 1e6 + pout * PRICE_OUT / 1e6
    print("\n=== averages ===")
    print(f"prompt_tokens (input):     {pin:.0f}")
    print(f"completion_tokens (output):{pout:.0f}")
    print(f"cost/call (no cache):      {cost_call:.5f} RMB  (= {cost_call/7.2:.6f} USD)")
    print(f"1000-item MMLU (5.94/item):{5940*cost_call:.2f} RMB  (= {5940*cost_call/7.2:.2f} USD)")


if __name__ == "__main__":
    main()
