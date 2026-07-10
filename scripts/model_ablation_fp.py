#!/usr/bin/env python3
"""Model-capability ablation for the rubric-audit false-positive problem.

Question: is the auditor's high false-positive rate a MODEL-CAPABILITY artifact
(a weak/cheap model over-flags) or fundamental to the task framing (even a strong
model over-flags)?

Method: run the IDENTICAL scan prompt (imported from scan_hf_tasks, not copied) on
a small set of HUMAN-LABELED tasks, with a LOW-capability model (deepseek-v4-flash)
and a HIGH-capability model (gpt-5.5). Compare each model's verdicts against the
human ground truth, and against each other on the same rubrics.

This is deliberately small (a handful of labeled tasks) and cheap -- it answers the
confound, it is not a large-scale eval.
"""
from __future__ import annotations

import collections, importlib.util, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

# import the EXACT prompt the big scan used, so model is the only variable
_spec = importlib.util.spec_from_file_location("scan", REPO / "scripts" / "scan_hf_tasks.py")
scan = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(scan)
PROMPT = scan.PROMPT

# Human-verified ground truth (from reports/高置信度问题清单 top-5 manual check).
# expected_type = what the task ACTUALLY is; label = is there a real rubric defect.
GT = {
    35:  {"true_type": "subjective",    "label": "TRUE",       "note": "真·过度约束：开放设计任务被钉死作者具体方案（如临时权限'不超过3天'）"},
    244: {"true_type": "subjective",    "label": "TRUE",       "note": "真·答案泄漏：任务要agent自己发现，rubric却写死结论（'评分标准严重失真'等）"},
    55:  {"true_type": "subjective",    "label": "BORDERLINE", "note": "边界：轻微结构过度规定，不如35/244硬"},
    278: {"true_type": "deterministic", "label": "FALSE",      "note": "误报：其实是确定性数据任务，value rubric正常，低模型误判成subjective"},
    287: {"true_type": "deterministic", "label": "FALSE",      "note": "误报：同上，确定性数据报告，被误标一堆answer_leakage"},
}

MODELS = [
    ("low",  "deepseek-v4-flash", "configs/llm_deepseek.json"),
    ("high", "gpt-5.5",           "configs/llm_openrouter_gpt55.json"),
]


def load_tasks():
    from datasets import load_dataset
    ds = load_dataset("Workspace-Bench/Workspace-Bench-Lite", split="lite")
    out = {}
    for i in range(len(ds)):
        r = ds[i]
        if r["absolute_id"] in GT:
            rubrics = r["rubrics"] if isinstance(r["rubrics"], list) else json.loads(r["rubrics"])
            out[r["absolute_id"]] = {"task": str(r["task"]), "rubrics": rubrics,
                                     "persona": r.get("persona")}
    return out


def audit(client, task, rubrics):
    rub = "\n".join(f"{j}: {x}" for j, x in enumerate(rubrics))
    user_filled = PROMPT.replace("{task}", str(task)[:1500]).replace("{rubrics}", rub[:4000])
    try:
        res = client.chat_json(user_filled, "audit")
    except Exception as e:
        return {"task_type": "ERROR", "issues": [], "error": str(e)}
    return {"task_type": res.get("task_type"), "issues": res.get("issues", [])}


def main():
    tasks = load_tasks()
    print(f"加载 {len(tasks)} 个人工标注任务: {sorted(tasks)}", flush=True)

    clients = {}
    for tag, _model, cfg_path in MODELS:
        cfg = load_llm_config(str(REPO / cfg_path))
        cfg.cache_path = f"reports/ablation_{tag}_cache.jsonl"
        clients[tag] = LLMClient(cfg)

    results = {}  # id -> {tag -> audit}
    for tid in sorted(tasks):
        t = tasks[tid]
        results[tid] = {"persona": t["persona"], "n_rubrics": len(t["rubrics"]),
                        "rubrics": t["rubrics"]}
        for tag, model, _ in MODELS:
            a = audit(clients[tag], t["task"], t["rubrics"])
            highs = [it for it in a["issues"] if it.get("severity") == "high"]
            results[tid][tag] = {"model": model, "task_type": a["task_type"],
                                 "n_high": len(highs), "n_issues": len(a["issues"]),
                                 "issues": a["issues"], "error": a.get("error")}
            print(f"  id={tid} [{tag}/{model}] type={a['task_type']} "
                  f"n_high={len(highs)}{' ERR='+a['error'] if a.get('error') else ''}", flush=True)

    out_json = REPO / "reports/model_ablation_fp.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(results)
    print(f"\nwrote {out_json.name} and 模型对比_假阳性归因.md")


def fp_tp(results, tag):
    """Score one model against ground truth. A task 'flagged' if n_high>0."""
    tp = fp = tn = fn = 0
    type_correct = 0
    for tid, gt in GT.items():
        m = results[tid][tag]
        flagged = m["n_high"] > 0
        if m["task_type"] == gt["true_type"]:
            type_correct += 1
        if gt["label"] == "TRUE":
            tp += flagged; fn += (not flagged)
        elif gt["label"] == "FALSE":
            fp += flagged; tn += (not flagged)
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "type_correct": type_correct}


def write_md(results):
    L = []
    L.append("# 模型能力对照：rubric 审计的假阳性是模型问题还是方法问题？\n")
    L.append("> **实验问题**：低端模型(deepseek-v4-flash)报出的大量假阳性，换成强模型(gpt-5.5)会不会消失？")
    L.append("> 同一套审计 prompt（与全量扫描完全一致，直接 import），只换模型，跑在一小批**人工已核实**的任务上。\n")
    L.append("> ⚠️ 这是**小规模归因实验**（5 个有金标的任务），目的是解开混淆变量、决定下一步该不该砸钱上强模型，**不是**大规模评测。\n")

    # summary table
    L.append("## 1. 总览：同样的任务，两个模型怎么判\n")
    L.append("| 任务 | 人工金标 | 低模型 task_type | 低模型 high数 | 强模型 task_type | 强模型 high数 |")
    L.append("|---|---|---|--:|---|--:|")
    for tid, gt in GT.items():
        lo, hi = results[tid]["low"], results[tid]["high"]
        gmark = {"TRUE": "✅真问题", "FALSE": "❌应判干净", "BORDERLINE": "⚠️边界"}[gt["label"]]
        L.append(f"| {tid} | {gmark} | {lo['task_type']} | {lo['n_high']} | {hi['task_type']} | {hi['n_high']} |")
    L.append("")

    # scoring
    lo_s, hi_s = fp_tp(results, "low"), fp_tp(results, "high")
    L.append("## 2. 对金标的命中（TRUE=该报、FALSE=不该报）\n")
    L.append("| 模型 | 真问题召回(TP/2) | 误报(FP/2) | task_type 判对(/5) |")
    L.append("|---|--:|--:|--:|")
    L.append(f"| 低 deepseek-v4-flash | {lo_s['tp']}/2 | {lo_s['fp']}/2 | {lo_s['type_correct']}/5 |")
    L.append(f"| 强 gpt-5.5 | {hi_s['tp']}/2 | {hi_s['fp']}/2 | {hi_s['type_correct']}/5 |")
    L.append("")
    L.append("> 关键看两列：**FP**（强模型能不能不误报 278/287）和 **task_type 判对**"
             "（278/287 是确定性任务，低模型误判成 subjective 才导致连锁误报）。\n")

    # rubric-level disagreement on the two FALSE tasks
    L.append("## 3. 逐条看分歧（以两个『应判干净』的误报任务为例）\n")
    L.append("> 这两个任务实际是确定性数据任务，理想情况下不该有 high 级缺陷。看两个模型在**同样的 rubric** 上谁在乱报。\n")
    for tid in (278, 287):
        gt = GT[tid]
        L.append(f"### 任务 {tid}（{gt['note']}）\n")
        lo, hi = results[tid]["low"], results[tid]["high"]
        L.append(f"- 低模型：task_type=`{lo['task_type']}`，标了 **{lo['n_high']}** 条 high")
        L.append(f"- 强模型：task_type=`{hi['task_type']}`，标了 **{hi['n_high']}** 条 high\n")
        lo_idx = {it.get("rubric_index"): it for it in lo["issues"] if it.get("severity") == "high"}
        hi_idx = {it.get("rubric_index"): it for it in hi["issues"] if it.get("severity") == "high"}
        only_lo = sorted(set(lo_idx) - set(hi_idx), key=lambda x: (x is None, x))
        rubrics = results[tid]["rubrics"]
        if only_lo:
            L.append("**低模型报、强模型没报的 rubric（前 5 条）**：\n")
            L.append("| rubric# | 低模型判的缺陷 | rubric 原文（截断） |")
            L.append("|--:|---|---|")
            for ri in only_lo[:5]:
                it = lo_idx[ri]
                txt = str(rubrics[ri])[:70].replace("|", "/").replace("\n", " ") if isinstance(ri, int) and ri < len(rubrics) else "?"
                L.append(f"| {ri} | {it.get('defect_type')} | {txt} |")
            L.append("")
        both = sorted(set(lo_idx) & set(hi_idx), key=lambda x: (x is None, x))
        L.append(f"两模型都报的: {len(both)} 条；仅低模型报的: {len(only_lo)} 条；仅强模型报的: {len(set(hi_idx)-set(lo_idx))} 条\n")

    L.append("## 4. 怎么读这张结果\n")
    L.append("- **若强模型 FP→0 且 task_type 全判对** → 假阳性主要是**模型能力**问题：换强模型/便宜地只在初筛后用强模型复核，就能压下来。")
    L.append("- **若强模型仍然误报 278/287** → 假阳性是**方法/任务框定**问题：再贵的模型也救不了，必须改判断方式（确定性门控 / 验证-门控审计器）。")
    L.append("- 中间情况（强模型好一些但没清零）→ 两者都有，给出**成本-可靠性权衡**：用强模型做第二道复核而非全量。\n")
    L.append("> 原始逐条结果：`reports/model_ablation_fp.json`")

    (REPO / "模型对比_假阳性归因.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
