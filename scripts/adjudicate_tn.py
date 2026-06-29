#!/usr/bin/env python3
"""Calibration check for the FP adjudication.

Samples TRUE NEGATIVES (MMLU-Redux=ok AND not flagged by BenchAudit) and runs
the same blind GPT-5.5 judge. A low defect rate here means the judge is
conservative, so the high defect rate on BenchAudit's FPs is a real signal
rather than the judge calling everything defective.
"""
from __future__ import annotations

import collections, json, random, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config
from scripts.adjudicate_fps import JUDGE_PROMPT, user_prompt

random.seed(20260629)
items = {json.loads(l)["id"]: json.loads(l) for l in
         (REPO / "experiments/mmlu_redux_pilot1000.jsonl").open(encoding="utf-8")}
defects = {i for i, d in items.items() if d.get("metadata", {}).get("error_type", "ok") != "ok"}
rep = json.loads((REPO / "reports/mmlu_holistic_v3_fixes_report.json").read_text())
flagged = {v["item_id"] for v in rep.get("violations", [])
           if v.get("defect_scope", "substantive") == "substantive"}
# true negatives: clean label AND not flagged by BenchAudit
tn = [i for i in items if i not in defects and i not in flagged]
random.shuffle(tn)
sample = tn[:40]

cfg = load_llm_config(str(REPO / "configs/llm_openrouter_gpt55.json"))
cfg.cache_path = "reports/fp_adjudication_cache.jsonl"
client = LLMClient(cfg)

def judge(i):
    try:
        return i, client.chat_json(JUDGE_PROMPT, user_prompt(items[i]))
    except Exception as e:
        return i, {"verdict": "error", "reason": str(e)}

results, t0 = {}, time.time()
with ThreadPoolExecutor(max_workers=8) as pool:
    futs = [pool.submit(judge, i) for i in sample]
    for n, f in enumerate(as_completed(futs), 1):
        i, r = f.result(); results[i] = r
        if n % 10 == 0:
            print(f"  {n}/{len(sample)} ({time.time()-t0:.0f}s)", flush=True)

tally = collections.Counter(r.get("verdict") for r in results.values())
nd = tally.get("defect", 0)
print("\n=== GPT-5.5 on TRUE NEGATIVES (clean + unflagged) ===")
print("sample:", len(results), "| tally:", dict(tally))
print(f"judge false-alarm rate on clean items: {nd/len(results):.1%}")
print(f"(compare: defect rate on BenchAudit FPs was 25.0%)")
(REPO / "reports/tn_calibration_20260629.json").write_text(
    json.dumps({"sample": len(results), "tally": dict(tally), "results": results}, indent=2, ensure_ascii=False))
print("wrote reports/tn_calibration_20260629.json")
