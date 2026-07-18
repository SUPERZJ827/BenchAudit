#!/usr/bin/env python3
"""Turn a DS-1000 execution-audit output directory into a triaged review queue.

The execution audit emits `underconstrained_evaluator_risk` whenever the harness
accepts an output that differs from the reference. Most of those are tasks that
legitimately admit many outputs (any order / random / find one of ...), where the
lenient harness is correct. This script applies the task-uniqueness classifier to
every flagged item and orders the queue so genuine over-leniency suspects
(`priority`) surface above the self-declared multi-solution tasks (`by_design`),
with the deciding task phrase shown for one-glance human triage.

It reads the per-item JSONs an audit run already wrote (no re-run, no LLM), so it
works on any existing out-dir. Consumes, rather than re-derives, the audit signal.

Usage: ds1000_review_queue.py --audit-dir reports/ds1000_exec_pilot200
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.task_uniqueness import classify_task_multiplicity, triage_rank

DS1000 = Path.home() / (".cache/huggingface/hub/datasets--xlangai--DS-1000/"
                        "snapshots/4416080ac5cb80bdf7576aefb8f9a0b4d5426a44/test.jsonl")
# Evaluator-soundness signals worth a human's time; llm_audit_failure (no signal)
# and output_format_overstrict_risk (DS-1000's intended surface constraints) are
# excluded from the actionable queue.
ACTIONABLE = {"underconstrained_evaluator_risk", "overstrict_evaluator",
              "evaluator_mutation_survived", "gold_rejected_by_evaluator"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-dir", required=True)
    ap.add_argument("--dataset", default=str(DS1000))
    ap.add_argument("--out", default=None, help="default: <audit-dir>/review_queue.md")
    args = ap.parse_args()

    prompts = {r["metadata"]["problem_id"]: r["prompt"]
               for r in (json.loads(l) for l in Path(args.dataset).read_text().splitlines())}
    audit_dir = Path(args.audit_dir)

    rows = []
    for f in sorted(audit_dir.glob("*.json")):
        if f.name in {"summary.json", "run_manifest.json"}:
            continue
        s = json.loads(f.read_text()).get("summary", {})
        pid = s.get("problem_id")
        hits = [v for v in (s.get("violations") or []) if v.get("defect_type") in ACTIONABLE]
        if not hits or pid not in prompts:
            continue
        mult = classify_task_multiplicity(prompts[pid])
        phrase = mult.signals[0].phrase if mult.signals else ""
        rows.append({
            "pid": pid, "library": s.get("library"),
            "defects": sorted({v["defect_type"] for v in hits}),
            "triage": mult.triage, "confidence": mult.confidence, "phrase": phrase,
            "message": hits[0].get("message", ""),
        })

    rows.sort(key=lambda r: (triage_rank(r["triage"]), r["pid"]))
    n = {t: sum(1 for r in rows if r["triage"] == t)
         for t in ("priority", "ambiguous", "by_design")}

    L = ["# DS-1000 执行审计 — 分诊后的人工复核队列\n",
         f"> 源:`{audit_dir}`;共 **{len(rows)}** 个待复核信号。"
         "按任务唯一性分诊排序:**priority**(无多解标记,真嫌疑,优先看)"
         " > **ambiguous**(弱多解如随机)> **by_design**(任务自己声明多解,大概率非缺陷)。\n",
         f"> 分布:priority **{n['priority']}** / ambiguous {n['ambiguous']} / by_design {n['by_design']}。"
         "全部 review 级,无自动确认。\n",
         "\n| # | id | 库 | 分诊 | 缺陷类型 | 任务多解证据 |",
         "|---:|---:|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        badge = {"priority": "🔴 priority", "ambiguous": "🟡 ambiguous",
                 "by_design": "⚪ by_design"}[r["triage"]]
        phrase = f"`{r['phrase']}`" if r["phrase"] else "(无——输出应唯一)"
        L.append(f"| {i} | {r['pid']} | {r['library']} | {badge} | "
                 f"{', '.join(r['defects'])} | {phrase} |")
    L += ["\n## 怎么用\n",
          "- 🔴 **priority**:任务应有唯一输出、评测器却接受了不同输出 → 最可能是真过宽,优先人工确认。",
          "- ⚪ **by_design**:任务 prompt 明确声明多解(见证据短语),存活变异是预期的,可快速跳过。",
          "- 🟡 **ambiguous**:仅匹配到弱标记(如'random'),需看一眼确认是输出随机还是输入设置。"]

    out = Path(args.out) if args.out else audit_dir / "review_queue.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"{len(rows)} signals -> priority={n['priority']} ambiguous={n['ambiguous']} "
          f"by_design={n['by_design']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
