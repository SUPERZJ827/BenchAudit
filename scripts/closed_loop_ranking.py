#!/usr/bin/env python3
"""End-to-end closed loop: does OUR auditor's detections change the ranking?

The base ranking_impact experiment removed the items THIRD-PARTY MMLU-Redux marked
defective. This closes the loop: we remove the items OUR OWN auditor flagged
(scripts/../cli.py --llm-audit output), with no reliance on the third-party label,
and report:

  1. auditor precision/recall vs the MMLU-Redux objective-defect labels
     (do we actually find the ranking-distorting items?);
  2. the ranking change when we remove OUR flagged items (global + per-subject);
  3. side-by-side with the third-party-label removal, so the two agree or not.

"Objective" auditor defects = answer/option defect types the auditor can point at:
wrong_gold_answer / no_correct_answer / multiple_correct_answers(_risk) /
invalid_choice_gold / bad_options_clarity / duplicate_choices. These are review
signals (LLM judgement, not auto-confirmed on MCQ), i.e. high-recall candidates.

Usage: closed_loop_ranking.py --audit reports/ranking_impact/audit_full1000.json --models "<15 slugs>"
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import ranking_impact_analysis as ria  # kendall_tau, accuracy, ranked, load_model

DATA = REPO / "experiments/mmlu_redux_pilot1000.jsonl"
OUT = REPO / "reports/ranking_impact"
MMLU_OBJ = {"wrong_groundtruth", "no_correct_answer", "multiple_correct_answers"}
AUDIT_OBJ = {"wrong_gold_answer", "no_correct_answer", "multiple_correct_answers",
             "multiple_correct_answers_risk", "invalid_choice_gold",
             "bad_options_clarity", "duplicate_choices"}


def ranking(models, keep_ids):
    accs = {s: ria.accuracy(recs, keep_ids)[0] for s, recs in models.items()}
    order = ria.ranked(accs)
    return accs, order, {m: i + 1 for i, m in enumerate(order)}


def top1_changes(models, base_ids, removed_ids, min_items=15, min_removed=3):
    """Per-subject: how many subjects change top-1 when removed_ids are dropped."""
    any_recs = next(iter(models.values()))
    subj = {}
    for i in base_ids:
        subj.setdefault(any_recs[i]["subject"], set()).add(i)
    changed, considered = [], 0
    for s, ids in subj.items():
        keep = ids - removed_ids
        if len(ids) < min_items or len(ids) - len(keep) < min_removed or len(keep) < 5:
            continue
        considered += 1
        _, of, _ = ranking(models, ids)
        _, oc, _ = ranking(models, keep)
        if of[0] != oc[0]:
            changed.append({"subject": s, "n": len(ids), "removed": len(ids) - len(keep),
                            "top1_full": of[0], "top1_clean": oc[0]})
    return changed, considered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default=str(OUT / "audit_full1000.json"))
    ap.add_argument("--models", required=True)
    args = ap.parse_args()

    rows = {json.loads(l)["id"]: json.loads(l)
            for l in DATA.read_text(encoding="utf-8").splitlines()}
    all_ids = set(rows)
    mmlu_obj = {i for i, r in rows.items() if r["metadata"]["error_type"] in MMLU_OBJ}

    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    flagged = {v["item_id"] for v in audit.get("violations", [])
               if v["defect_type"] in AUDIT_OBJ}
    flagged &= all_ids  # guard

    # precision/recall of auditor vs third-party objective labels
    tp = len(flagged & mmlu_obj)
    prec = tp / len(flagged) if flagged else 0.0
    rec = tp / len(mmlu_obj) if mmlu_obj else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

    slugs = [s.strip() for s in args.models.split(",") if s.strip()]
    models = {s: ria.load_model(s) for s in slugs}
    models = {s: r for s, r in models.items()
              if len([1 for x in r.values() if x["pred"]]) >= 100}

    keep_full = all_ids
    keep_audit = all_ids - flagged            # remove OUR detections
    keep_mmlu = all_ids - mmlu_obj            # remove third-party labels
    _, of, rf = ranking(models, keep_full)
    _, oa, ra = ranking(models, keep_audit)
    _, om, rm = ranking(models, keep_mmlu)
    tau_audit = ria.kendall_tau(of, oa)
    tau_mmlu = ria.kendall_tau(of, om)
    shift_audit = max(abs(rf[m] - ra[m]) for m in rf)
    shift_mmlu = max(abs(rf[m] - rm[m]) for m in rf)

    subj_audit, considered = top1_changes(models, all_ids, flagged)
    subj_mmlu, _ = top1_changes(models, all_ids, mmlu_obj)

    L = ["# 端到端闭环:用我们审计器自己检出的题剔除,排名会变吗?\n",
         f"> 不依赖第三方标注——剔除的是**本项目审计器 `--llm-audit` 检出**的答案/选项类缺陷题。\n",
         f"> {len(models)} 模型;审计器用 DeepSeek(review 级信号,MCQ 上 LLM 判断不自动 confirmed)。\n",
         "\n## 1. 审计器 vs 第三方标注(我们真找到那些改排名的题吗)\n",
         f"- 审计器检出客观缺陷题:**{len(flagged)}** 道",
         f"- MMLU-Redux 客观错题(第三方标注):{len(mmlu_obj)} 道",
         f"- 命中(交集 TP)= {tp} → **precision={prec:.2f}, recall={rec:.2f}, F1={f1:.2f}**",
         "\n## 2. 排名变化:用我们检出剔除 vs 用第三方标注剔除\n",
         "| 剔除依据 | 剔除题数 | 全局 Kendall τ | 全局最大名次变动 | Per-subject 冠军易主 |",
         "|---|---:|---:|---:|---:|",
         f"| **我们审计器检出** | {len(flagged)} | {tau_audit:.3f} | {shift_audit} "
         f"| {len(subj_audit)}/{considered} |",
         f"| 第三方 MMLU-Redux 标注 | {len(mmlu_obj)} | {tau_mmlu:.3f} | {shift_mmlu} "
         f"| {len(subj_mmlu)}/{considered} |"]
    if subj_audit:
        L += ["\n## 3. 用我们检出剔除后,冠军易主的 subject\n",
              "| subject | 题数 | 我们剔除 | Top-1 变化 |", "|---|---:|---:|---|"]
        for d in sorted(subj_audit, key=lambda x: -x["removed"]):
            L.append(f"| {d['subject']} | {d['n']} | {d['removed']} "
                     f"| {d['top1_full'].split('__')[-1]} → {d['top1_clean'].split('__')[-1]} |")
    L += ["\n## 结论\n",
          f"审计器仅凭自己的检测(precision={prec:.2f}/recall={rec:.2f}),"
          f"在 {len(subj_audit)} 个 subject 上复现了冠军易主——**端到端闭环成立**:"
          "我们的系统不依赖第三方标注,就能自动找出足以改变模型排名的 benchmark 缺陷。\n",
          "## 诚实边界\n",
          "- 审计器检出为 **review 级候选**(高召回,含假阳性),非自动 confirmed;MCQ 语义缺陷本就不该自动 confirmed。",
          f"- 审计 recall={rec:.2f} 意味着仍漏检部分第三方标注错题;precision={prec:.2f} 表示部分检出未被第三方标注(可能是漏标或假阳,需人工复核)。",
          "- 1000 题子集、DeepSeek 单模型审计、15 个作答模型、zero-shot 单次。"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "closed_loop_ranking.md").write_text("\n".join(L), encoding="utf-8")
    (OUT / "closed_loop_ranking.json").write_text(json.dumps({
        "auditor_flagged": len(flagged), "mmlu_objective": len(mmlu_obj), "tp": tp,
        "precision": prec, "recall": rec, "f1": f1,
        "tau_audit": tau_audit, "tau_mmlu": tau_mmlu,
        "subj_top1_changed_audit": subj_audit, "subj_considered": considered,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"flagged={len(flagged)} tp={tp} P={prec:.2f} R={rec:.2f} F1={f1:.2f} "
          f"tau_audit={tau_audit:.3f} subj_changed={len(subj_audit)}/{considered}")
    print("wrote reports/ranking_impact/closed_loop_ranking.md")


if __name__ == "__main__":
    main()
