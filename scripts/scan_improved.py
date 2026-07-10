#!/usr/bin/env python3
"""Discovery scan with the higher-precision detectors (B1 existence + B2 recompute
consensus). Runs only the two OBJECTIVE detectors -- the ones that yield confirmable
(B1) or reproducible-mismatch (B2) findings -- over a batch of tasks, and collects the
findings for human review. B4/B5 (subjective, candidate-only, noisy) are skipped on
purpose: this scan is about surfacing a SHORT, HIGH-QUALITY candidate list, not volume.

Every B2 finding is still a human-review candidate (recompute code is LLM-written);
every B1 finding means a data dimension the rubric needs is absent from the inputs.

Run:  /home/zhoujun/llmdata/.venv/bin/python scripts/scan_improved.py 3 35 38 ...
"""
from __future__ import annotations

import importlib.util, json, sys, traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

_a = importlib.util.spec_from_file_location("aa", REPO / "scripts" / "auditor_agent.py")
A = importlib.util.module_from_spec(_a); _a.loader.exec_module(A)

DEFAULT_IDS = [3, 35, 38, 54, 55, 72, 75, 78, 79, 83, 85, 87]


def main():
    ids = [int(x) for x in sys.argv[1:]] or DEFAULT_IDS
    single = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek.json")))
    vote_b1 = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek_vote5.json")))
    out = []
    for aid in ids:
        try:
            item = A.load_hf_item(aid)
        except Exception as e:
            print(f"id={aid}: LOAD FAILED {e}", flush=True); continue
        if not item["inputs"]:
            print(f"id={aid}: no input files -> skip", flush=True); continue
        try:
            b1 = A.evaluate("B1", A.exec_B1(item, single, vote_b1))
            b2 = A.evaluate("B2", A.exec_B2(item, vote_b1))
        except Exception:
            print(f"id={aid}: DETECTOR ERROR\n{traceback.format_exc()[-400:]}", flush=True); continue
        finds = [{"detector": "B1", **f} for f in b1] + [{"detector": "B2", **f} for f in b2]
        print(f"id={aid}: {len(item['rubrics'])} rubrics, {len(item['inputs'])} inputs -> "
              f"{sum(f['detector']=='B1' for f in finds)} B1(确认) + "
              f"{sum(f['detector']=='B2' for f in finds)} B2(共识候选)", flush=True)
        for f in finds:
            print(f"   [{f['detector']}/{f['status']}] {f['rubric'][:60]}", flush=True)
            print(f"        └ {f.get('evidence','')[:100]}", flush=True)
        if finds:
            out.append({"id": aid, "task": item["task"][:200], "findings": finds})
    Path(REPO / "reports/scan_improved.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    nb1 = sum(f["detector"] == "B1" for o in out for f in o["findings"])
    nb2 = sum(f["detector"] == "B2" for o in out for f in o["findings"])
    print(f"\n=== {len(ids)} tasks scanned | {nb1} B1 confirmed + {nb2} B2 consensus-candidates "
          f"across {len(out)} tasks | wrote reports/scan_improved.json ===", flush=True)


if __name__ == "__main__":
    main()
