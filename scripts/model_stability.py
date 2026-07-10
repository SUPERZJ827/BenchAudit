#!/usr/bin/env python3
"""Stability + capability probe for the rubric-audit false-positive problem.

Discovery during the first ablation: the cheap auditor (deepseek-v4-flash) is NOT
reproducible even at temperature=0 -- the same task+rubrics gave different verdicts
(task_type flips deterministic<->subjective, n_high 0..9) across separate runs.

So we measure two things on a small HUMAN-LABELED set, for a LOW and a HIGH model:
  (1) STABILITY: run each task K times (no cache, interleaved so calls are spaced
      apart in time) and report the spread of (task_type, n_high).
  (2) CORRECTNESS: does the modal verdict match the human ground truth?

Calls are interleaved low/high per repetition so the fast low-model calls are
spaced ~one high-model latency apart, exposing cross-window variance.
"""
from __future__ import annotations

import importlib.util, json, sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

_a = importlib.util.spec_from_file_location("abl", REPO / "scripts" / "model_ablation_fp.py")
abl = importlib.util.module_from_spec(_a); _a.loader.exec_module(abl)
GT, audit, load_tasks = abl.GT, abl.audit, abl.load_tasks

K = 4  # repetitions per (task, model)
MODELS = [("low", "deepseek-v4-flash", "configs/llm_deepseek.json"),
          ("high", "gpt-5.5", "configs/llm_openrouter_gpt55.json")]


def main():
    tasks = load_tasks()
    print(f"加载 {len(tasks)} 个人工标注任务: {sorted(tasks)}; K={K} 次/模型", flush=True)
    clients = {}
    for tag, _m, cfg in MODELS:
        c = load_llm_config(str(REPO / cfg)); c.cache_path = None  # NO cache: every call is fresh
        clients[tag] = LLMClient(c)

    res = {tid: {tag: [] for tag, _, _ in MODELS} for tid in tasks}
    for k in range(1, K + 1):
        for tid in sorted(tasks):
            t = tasks[tid]
            for tag, model, _ in MODELS:  # interleave low/high so low calls are spaced apart
                a = audit(clients[tag], t["task"], t["rubrics"])
                highs = [it for it in a["issues"] if it.get("severity") == "high"]
                res[tid][tag].append({"task_type": a["task_type"], "n_high": len(highs),
                                      "err": a.get("error")})
                print(f"  k={k} id={tid} [{tag}] type={a['task_type']} n_high={len(highs)}"
                      f"{' ERR' if a.get('error') else ''}", flush=True)

    (REPO / "reports/model_stability.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(tasks, res)
    print("\nwrote reports/model_stability.json and 模型对比_假阳性归因.md")


def summarize(runs):
    types = Counter(r["task_type"] for r in runs)
    nhs = [r["n_high"] for r in runs]
    type_set = list(types)
    modal_type = types.most_common(1)[0][0]
    reproducible = len(set((r["task_type"], r["n_high"]) for r in runs)) == 1
    return {"types": dict(types), "type_set": type_set, "modal_type": modal_type,
            "nh_min": min(nhs), "nh_max": max(nhs), "nh_list": nhs,
            "reproducible": reproducible}


def write_md(tasks, res):
    L = []
    L.append("# 模型对照 + 复现性：rubric 审计的假阳性，到底是模型菜还是方法不稳？\n")
    L.append("> **背景**：低端模型(deepseek-v4-flash)在全量扫描里报出大量疑点。本实验问两件事：")
    L.append("> 1. **复现性**——同一任务、同一 prompt、temperature=0，重复跑 K 次，结论稳不稳？")
    L.append("> 2. **能力**——换强模型(gpt-5.5)，是更准、还是只是不一样？\n")
    L.append(f"> 设置：{len(tasks)} 个**人工已核实**的任务，每个任务每个模型**无缓存重复跑 {K} 次**，"
             "low/high 交替调用使快模型的相邻两次间隔约一个强模型延迟（暴露跨时间窗的漂移）。\n")
    L.append("> ⚠️ 小规模归因实验，目的是解开混淆变量、定下一步方向，**非**大规模评测。\n")

    # ---- headline: reproducibility ----
    L.append("## 1. 复现性：同一输入、temp=0，重复跑的结果\n")
    L.append("| 任务 | 人工金标 | 低模型 task_type(K次) | 低模型 n_high(K次) | 低稳? | 强模型 task_type(K次) | 强模型 n_high(K次) | 强稳? |")
    L.append("|---|---|---|---|:--:|---|---|:--:|")
    lo_sum, hi_sum = {}, {}
    for tid, gt in GT.items():
        ls, hs = summarize(res[tid]["low"]), summarize(res[tid]["high"])
        lo_sum[tid], hi_sum[tid] = ls, hs
        gmark = {"TRUE": "✅真问题", "FALSE": "❌应判干净", "BORDERLINE": "⚠️边界"}[gt["label"]]
        L.append(f"| {tid} | {gmark} | {'/'.join(ls['type_set'])} | {ls['nh_list']} | "
                 f"{'稳' if ls['reproducible'] else '**漂**'} | {'/'.join(hs['type_set'])} | "
                 f"{hs['nh_list']} | {'稳' if hs['reproducible'] else '**漂**'} |")
    lo_unstable = sum(1 for tid in GT if not lo_sum[tid]['reproducible'])
    hi_unstable = sum(1 for tid in GT if not hi_sum[tid]['reproducible'])
    L.append("")
    L.append(f"> **复现性小结**：低模型 {lo_unstable}/{len(GT)} 个任务跑不稳（K 次结果不一致），"
             f"强模型 {hi_unstable}/{len(GT)} 个。`n_high` 列直接看每次报了几条 high。\n")

    # ---- correctness on modal verdict ----
    L.append("## 2. 正确性：用「多次中的众数判断」对金标\n")
    L.append("> flagged = 众数 n_high>0（该任务被判有问题）。TRUE 应 flagged，FALSE 应不 flagged。\n")
    L.append("| 模型 | 真问题召回(应flag) | 误报(不该flag却flag) | task_type 众数判对 |")
    L.append("|---|---|---|---|")
    for tag, sums in (("低 deepseek-v4-flash", lo_sum), ("强 gpt-5.5", hi_sum)):
        tp = fp = tc = 0; tp_d = fp_d = ""
        for tid, gt in GT.items():
            s = sums[tid]
            modal_nh = Counter(r["n_high"] for r in res[tid]["low" if "deepseek" in tag else "high"]).most_common(1)[0][0]
            flagged = modal_nh > 0
            if s["modal_type"] == gt["true_type"]:
                tc += 1
            if gt["label"] == "TRUE" and flagged: tp += 1; tp_d += f"{tid} "
            if gt["label"] == "FALSE" and flagged: fp += 1; fp_d += f"{tid} "
        n_true = sum(1 for g in GT.values() if g["label"] == "TRUE")
        n_false = sum(1 for g in GT.values() if g["label"] == "FALSE")
        L.append(f"| {tag} | {tp}/{n_true} ({tp_d.strip() or '-'}) | {fp}/{n_false} "
                 f"({fp_d.strip() or '无'}) | {tc}/{len(GT)} |")
    L.append("")

    # ---- the 287 anecdote, made concrete from data ----
    L.append("## 3. 最直观的一例：任务 287（确定性数据任务，理想应判『干净』）\n")
    s287l = lo_sum[287]
    L.append(f"- 低模型 {K} 次：task_type ∈ {{{', '.join(s287l['type_set'])}}}，n_high = {s287l['nh_list']}")
    L.append(f"- 加上之前几次独立运行，287 在低模型上出现过：deterministic/0、subjective/2、subjective/9、（原始扫描）subjective/14")
    L.append("- **同一道题、同一 prompt、temp=0，结论从『0 个问题』到『14 个问题』来回跳** —— 这不是模型菜，是**不可复现**。\n")

    # ---- how to read ----
    L.append("## 4. 怎么读这张结果（决定下一步）\n")
    L.append("- 若**低模型漂、强模型稳** → 花钱买的是**稳定性**而非单纯准确率：初筛后用强模型复核能去抖。")
    L.append("- 若**两个模型都漂** → 假阳性的根子是**方法**：单次 LLM 判断不可作数，必须改成"
             "「多次投票取众数 + 确定性门控 + 验证-门控」，再贵的模型也不能单跑一次就采信。")
    L.append("- 若**强模型把 278/287 都稳定判 deterministic/0、把 35/244 稳定判有问题** → 说明"
             "**task_type 分类是总开关**：先把『确定性 vs 主观』判稳，假阳性自然塌掉。\n")
    L.append("> 原始逐次结果：`reports/model_stability.json`")
    (REPO / "模型对比_假阳性归因.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
