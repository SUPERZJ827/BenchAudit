#!/usr/bin/env python3
"""Fast static audit of the whole Workspace-Bench (no agent, no solving).

Loads every task + its rubrics from the HuggingFace dataset and runs the
semantic auditor (task<->rubric: over-constrained / brittle / unverifiable,
gated by task type) on each. Produces a ranked list of the most suspicious
tasks for human review. These are CANDIDATES -- the auditor over-flags, so
treat as a triage queue, not confirmed defects.
"""
from __future__ import annotations

import collections, json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

PROMPT = """You audit the QUALITY of a benchmark task's grading rubrics (you do NOT solve it).

FIRST decide the task type:
- DETERMINISTIC: unique computable/extractable answer. A rubric stating an expected
  value is NORMAL -- do NOT flag it as over_constrained/answer_leakage.
- SUBJECTIVE/OPEN: asks for judgement/analysis/recommendations. Pinning one specific
  answer/score/structure IS over_constrained/answer_leakage.

Then flag rubrics that are defective as grading criteria:
- over_constrained: open task pinned to one author answer/score/structure.
- answer_leakage: rubric states a conclusion the agent should derive.
- unverifiable: vague/subjective ("reasonable","no fabrication") -> inconsistent grading.
- brittle: exact filename/sheet-name/threshold a correct answer could fail on, not
  required by the task.
Be conservative; only flag real issues.
Return ONLY JSON: {"task_type":"deterministic|subjective","issues":[{"rubric_index":<int>,
"defect_type":"...","severity":"high|medium|low","reason":"short"}]}

TASK: {task}

RUBRICS:
{rubrics}"""


def main():
    ds_name = sys.argv[1] if len(sys.argv) > 1 else "Workspace-Bench/Workspace-Bench-Lite"
    split = sys.argv[2] if len(sys.argv) > 2 else "lite"
    from datasets import load_dataset
    ds = load_dataset(ds_name, split=split)
    print(f"加载 {len(ds)} 个任务", flush=True)

    cfg = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
    cfg.cache_path = "reports/scan_hf_cache.jsonl"
    client = LLMClient(cfg)

    def audit(i):
        r = ds[i]
        rubrics = r["rubrics"] if isinstance(r["rubrics"], list) else json.loads(r["rubrics"])
        rub = "\n".join(f"{j}: {x}" for j, x in enumerate(rubrics))
        try:
            res = client.chat_json(PROMPT.replace("{task}", str(r["task"])[:1500]).replace("{rubrics}", rub[:4000]), "audit")
        except Exception as e:
            res = {"issues": [], "error": str(e)}
        highs = [it for it in res.get("issues", []) if it.get("severity") == "high"]
        return {"id": r["absolute_id"], "persona": r.get("persona"), "task": str(r["task"])[:80],
                "task_type": res.get("task_type"), "n_rubrics": len(rubrics),
                "n_high": len(highs), "n_issues": len(res.get("issues", [])),
                "issues": res.get("issues", [])}

    rows = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = [pool.submit(audit, i) for i in range(len(ds))]
        for n, f in enumerate(as_completed(futs), 1):
            rows.append(f.result())
            if n % 20 == 0:
                print(f"  {n}/{len(ds)}", flush=True)

    rows.sort(key=lambda r: -r["n_high"])
    typ = collections.Counter(it.get("defect_type") for r in rows for it in r["issues"] if it.get("severity") == "high")
    flagged = [r for r in rows if r["n_high"] > 0]
    print(f"\n=== 扫描完成:{len(ds)} 任务,{len(flagged)} 个有 high 级疑点 ===")
    print(f"high 级问题类型分布: {dict(typ)}\n")
    print("最可疑的 15 个任务(按 high 数排序):")
    for r in rows[:15]:
        print(f"  id={r['id']:>4} high={r['n_high']} [{r['task_type']}] {r['persona']}: {r['task'][:54]}")
    out = REPO / "reports/scan_hf_tasks_20260630.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out.name}  (含每条疑点明细)")


if __name__ == "__main__":
    main()
