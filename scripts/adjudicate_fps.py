#!/usr/bin/env python3
"""Independent adjudication of BenchAudit candidate false positives (Mode B).

Takes items BenchAudit flagged but MMLU-Redux labels "ok", and asks an
INDEPENDENT model (GPT-5.5 via OpenRouter, a different family from the
DeepSeek-V4 auditors) to BLINDLY judge whether each item truly has a quality
defect. The judge never sees BenchAudit's verdict, so agreement is genuine
independent corroboration that a "false positive" is actually a real defect the
annotators missed. Conservative prompt: difficulty/uncertainty is not a defect.
"""
from __future__ import annotations

import collections
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

JUDGE_PROMPT = """You are a strict, conservative benchmark quality reviewer.
You are given a multiple-choice question with its OFFICIAL gold answer.
Decide INDEPENDENTLY whether the item has a genuine quality defect that would
unfairly penalize a competent solver. Solve it yourself first, then judge.

Defect = one of:
- wrong_gold: the official gold answer is factually/logically incorrect.
- multiple_correct: two or more options are equally defensible as the best answer.
- no_correct: no option is a defensible answer.
- unanswerable: the question is ambiguous/underspecified so that different valid
  readings give different answers, or required context is missing.

Be conservative. The default is "clean". Do NOT flag merely because the question
is hard, niche, or you are unsure. Only flag a defect you can justify concretely.
For specialized professional/domain facts you cannot verify, answer "uncertain".

Return ONLY JSON:
{
  "verdict": "defect" | "clean" | "uncertain",
  "defect_type": "wrong_gold" | "multiple_correct" | "no_correct" | "unanswerable" | "none",
  "confidence": 0.0,
  "reason": "one or two sentences"
}"""


def user_prompt(it: dict) -> str:
    lines = [f"Question: {it.get('question','')}"]
    labels = "ABCDE"
    for j, c in enumerate(it.get("choices") or []):
        mark = "  <-- official gold" if labels[j] == str(it.get("gold")) else ""
        lines.append(f"  {labels[j]}) {c}{mark}")
    return "\n".join(lines)


def main() -> None:
    random.seed(20260629)
    items = {json.loads(l)["id"]: json.loads(l) for l in
             (REPO / "experiments/mmlu_redux_pilot1000.jsonl").open(encoding="utf-8")}
    defects = {i for i, d in items.items() if d.get("metadata", {}).get("error_type", "ok") != "ok"}
    rep = json.loads((REPO / "reports/mmlu_holistic_v3_fixes_report.json").read_text())
    byitem = collections.defaultdict(list)
    for v in rep.get("violations", []):
        if v.get("defect_scope", "substantive") != "substantive":
            continue
        byitem[v["item_id"]].append(v.get("defect_type"))
    fps = [i for i in byitem if i not in defects]

    # stratified sample ~40 across BenchAudit's primary defect type
    by_type = collections.defaultdict(list)
    for i in fps:
        by_type[byitem[i][0]].append(i)
    target, sample = 40, []
    for t, ids in by_type.items():
        random.shuffle(ids)
        sample += ids[: max(1, round(target * len(ids) / len(fps)))]
    sample = sample[:target]

    cfg = load_llm_config(str(REPO / "configs/llm_openrouter_gpt55.json"))
    cfg.cache_path = "reports/fp_adjudication_cache.jsonl"
    client = LLMClient(cfg)

    def judge(i):
        try:
            r = client.chat_json(JUDGE_PROMPT, user_prompt(items[i]))
        except Exception as e:
            return i, {"verdict": "error", "reason": str(e)}
        return i, r

    results = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(judge, i) for i in sample]
        for n, f in enumerate(as_completed(futs), 1):
            i, r = f.result(); results[i] = r
            if n % 10 == 0:
                print(f"  {n}/{len(sample)} ({time.time()-t0:.0f}s)", flush=True)

    tally = collections.Counter(r.get("verdict") for r in results.values())
    print("\n=== Independent GPT-5.5 verdicts on BenchAudit FPs ===")
    print("sample size:", len(results), "| tally:", dict(tally))
    n_def = tally.get("defect", 0)
    n_clean = tally.get("clean", 0)
    n_unc = tally.get("uncertain", 0)
    print(f"real-defect rate (defect / sample): {n_def/len(results):.1%}")
    print(f"  -> at least {n_def} of {len(results)} BenchAudit 'false positives' are independently judged REAL defects")

    # markdown for human eyeball
    md = ["# BenchAudit FP independent adjudication (GPT-5.5, blind)\n",
          f"Sample: {len(results)} candidate FPs (BenchAudit flagged, MMLU-Redux=ok)\n",
          f"Verdicts: {dict(tally)} | real-defect rate {n_def/len(results):.1%}\n"]
    for i, r in results.items():
        it = items[i]
        md.append(f"\n## {i}  (subject={it['metadata'].get('subject')})")
        md.append(f"- BenchAudit flagged: **{byitem[i]}**")
        md.append(f"- GPT-5.5 verdict: **{r.get('verdict')}** / {r.get('defect_type')} (conf {r.get('confidence')})")
        md.append(f"- GPT-5.5 reason: {r.get('reason')}")
        md.append(f"- Q: {it.get('question','')[:200]}")
        for j, c in enumerate(it.get("choices") or []):
            g = " <-gold" if "ABCDE"[j] == str(it.get("gold")) else ""
            md.append(f"    {'ABCDE'[j]}) {str(c)[:90]}{g}")
    (REPO / "reports/fp_adjudication_20260629.md").write_text("\n".join(md), encoding="utf-8")
    (REPO / "reports/fp_adjudication_20260629.json").write_text(
        json.dumps({"sample": len(results), "tally": dict(tally), "results": results}, indent=2, ensure_ascii=False))
    print("wrote reports/fp_adjudication_20260629.{md,json}")


if __name__ == "__main__":
    main()
