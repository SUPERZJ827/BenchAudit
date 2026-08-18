#!/usr/bin/env python3
"""Inventory which BenchCore capabilities are inert on ACEBench, and why.

The coverage ledger of a real run already records per-method status; this pulls
it together with the declared artifact requirements so the reason each silent
capability is silent is visible in one place.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "reports/agentsuite_acebench_102_deepseek_postfix_20260818/run_r1/report.json"
OUT = REPO / "docs/research/ACEBENCH_能力覆盖盘点_哪些检查被静默关闭_20260818.md"

# Why each silent capability is silent, and what a structured-call version would need.
WHY = {
    "oracle_ground_truth": ("ORACLE 构件判定为不存在", "标答在 `reference_solution`，未进入 `gold` 槽位"),
    "evaluator_replay": ("requires_all {ORACLE, EVALUATOR}", "同上；这是“标答能否通过自己的评测器”那条检查"),
    "execution_evaluator_audit": ("requires_all {ORACLE, EVALUATOR}", "同上；执行差分审计"),
    "metamorphic_answer": ("requires_any {ORACLE, EVALUATOR}", "变形测试针对标量答案设计，逐条判定不适用"),
    "evaluator_mutation": ("requires_any {EVALUATOR}", "实现要求 `item.gold` 非空，逐条判定不适用"),
    "executable_evidence": ("requires_any {ORACLE, TASK_SPECIFICATION}", "需要可执行表达式，逐条判定不适用"),
    "differential_candidate": ("requires_any {ORACLE, TASK_SPECIFICATION}", "需要候选答案集合"),
    "solution_leak": ("requires_all {TASK_SPECIFICATION, ORACLE}", "泄漏检查以标量答案出现在题面为判据"),
    "contract_consistency": ("requires_all {TASK_SPECIFICATION, EVALUATOR}", "逐条判定不适用"),
    "workspace_artifact_invariants": ("requires_all {TASK_SPECIFICATION, EVALUATOR}", "ACEBench 无工作区文件"),
    "trace_failure_cluster": ("requires_any {TRACE}", "**我们没有把模型轨迹作为输入**；COBA 的 pipeline 正是吃这个"),
    "environment_replay": ("requires_all {ENVIRONMENT, EVALUATOR}", "未提供 environment_initial_state"),
}

# Capabilities that never entered this run because no CLI flag enabled them.
NOT_ENABLED = {
    "llm_answer_multiplicity": "需 `--llm-audit`。且实现要求 benchmark 已声明 ≥2 个可接受答案（`gold`+`aliases`），"
                               "检查的是“已声明的多解彼此矛盾”，与“客观上存在多解但未声明”方向相反",
    "llm_question_clarity": "需 `--llm-audit`。payload 主动移除 `gold`/`aliases`/`evaluator`，只读题面，看不到 schema 约束",
    "llm_gold_audit": "需 `--llm-audit`，且面向标量 gold",
    "llm_quantity_consistency": "需 `--llm-audit`，面向数值型答案",
    "llm_option_set": "需 `--llm-audit`，面向选择题选项集",
    "value_recompute": "需 `--value-recompute-audit`，面向表格型输入",
    "reference_schema_validation": "需 `--reference-schema-audit`；本轮主线未启用（单独运行过，3 触发 / 3 TP / 0 FP）",
    "reference_evaluator_mutation": "2026-08-17 新建，尚未接入 CLI，只能由脚本调用",
}


def main() -> int:
    report = json.loads(RUN.read_text(encoding="utf-8"))
    plan = report["audit_plan"]["checks"]
    cov = report["summary"]["audit_coverage"]

    executed = [c for c in plan if c["status"] == "executed"]
    partial = [c for c in plan if c["status"] == "partial"]
    silent = [c for c in plan if c["status"] in {"ineligible", "unsupported"}]

    L, a = [], None
    L.append("# ACEBench 上哪些检查被静默关闭了")
    L.append("")
    L.append("> 日期：2026-08-18")
    L.append("> 依据：`reports/agentsuite_acebench_102_deepseek_postfix_20260818/run_r1/report.json` 的覆盖账本与审计计划")
    L.append("> 性质：对现有实现的盘点，不是新实验")
    L.append("")
    L.append("## 结论先行")
    L.append("")
    L.append(f"这一轮计划了 {len(plan)} 项能力，其中 **{len(executed)} 项执行、{len(partial)} 项部分执行、"
             f"{len(silent)} 项在全部 102 条上未产生任何判定**。整次审计的实质产出几乎全部来自一个方法：`cross_artifact_consistency`。")
    L.append("")
    L.append(f"逐行账本：`completed_no_finding={cov['status_distribution'].get('completed_no_finding')}`、"
             f"`finding={cov['status_distribution'].get('finding')}`、"
             f"`ineligible={cov['status_distribution'].get('ineligible')}`。"
             "即约一半的检查行在进入检查器之前就被判为不适用。")
    L.append("")
    L.append("**共同根因只有一个**：ACEBench 的标答被物化进 `reference_solution` 这个原始字段，"
             "而不是 `gold` 槽位，因此 `ArtifactKind.ORACLE` 判定为不存在，所有以 ORACLE 为前提的能力集体失效。")
    L.append("")
    L.append("这个映射当初是**有意为之**（见 V2 对齐协议）：ACEBench 的标答是结构化函数调用，"
             "放进标量 `gold` 会让通用答案合同检查把函数参数里的数字误当成数值答案。"
             "当时避免了一类假阳，代价是关掉了一整片能力，而这个代价直到现在才被清点。")
    L.append("")

    L.append("## 一、计划内但全程沉默的能力")
    L.append("")
    L.append("| 能力 | 状态 | 声明的构件要求 | 为什么在 ACEBench 上沉默 |")
    L.append("|---|---|---|---|")
    for c in silent:
        req, why = WHY.get(c["name"], ("—", c.get("reason", "")))
        L.append(f"| `{c['name']}` | {c['status']} | {req} | {why} |")
    L.append("")

    L.append("## 二、连计划都没进入的能力（配置未启用）")
    L.append("")
    L.append("| 能力 | 为什么没跑 |")
    L.append("|---|---|")
    for name, why in NOT_ENABLED.items():
        L.append(f"| `{name}` | {why} |")
    L.append("")

    L.append("## 三、这解释了三件此前分开发生的事")
    L.append("")
    L.append("1. **evaluator 轴长期零产出。**taxonomy 在 `evaluator` 构件下有 17 个缺陷类型，"
             "但在 2026-08-17 之前，34 份历史报告里 `overstrict_evaluator` 和 `gold_rejected_by_evaluator` 各 0 条。"
             "原因不是没有能力，而是 `evaluator_replay`/`evaluator_mutation` 都被 ORACLE 前提挡住了。"
             "直到新建 `reference_evaluator_mutation`（绕开 `gold`，直接吃 `reference_solution`）才第一次产出 20 条。")
    L.append("2. **存在性/唯一性检查看起来“不存在”。**`llm_answer_multiplicity` 实际存在，"
             "但它要求 benchmark 自己声明了 ≥2 个可接受答案；ACEBench 没有 `aliases`，函数体一次都没进入。"
             "而且它检查的是“已声明的多解互相矛盾”，与我们需要的“客观多解但未声明”方向相反。")
    L.append("3. **我们有轨迹能力却没用。**`trace_failure_cluster` 声明 `requires_any {TRACE}`，"
             "因为我们不把模型轨迹作为输入而全程 unsupported。COBA 的 pipeline 恰恰以轨迹为必需输入。"
             "这不是我们缺能力，是我们没有供给它所需的构件。")
    L.append("")

    L.append("## 四、可以怎么补")
    L.append("")
    L.append("按代价从低到高：")
    L.append("")
    L.append("| 做法 | 代价 | 风险 |")
    L.append("|---|---|---|")
    L.append("| 把已验证的 `reference_schema_validation` 与 `reference_evaluator_mutation` 接入 CLI 主线 | 低 | 会改变源码指纹，历史跑不可直接并列 |")
    L.append("| 为结构化调用补一个 ORACLE 适配层，让 ORACLE 前提的能力重新可用 | 中 | 正是当初要避免的假阳来源，须逐个检查器验证 |")
    L.append("| 把轨迹作为**可选**构件供给 `trace_failure_cluster` | 中 | 轨迹免费可得；但不得让它变成必需输入，否则丢掉“无需模型跑过”的结构性优势 |")
    L.append("| 为结构化调用实现存在性/唯一性检查 | 高 | 目前仅剩的 2 条漏检属于此类 |")
    L.append("")
    L.append("## 不能说")
    L.append("")
    L.append("- 不能说这些能力“坏了”：它们在各自适用的 benchmark 上有产出，这里只是不适用。")
    L.append("- 不能说补上它们就一定提升 F1：本盘点只说明能力被关闭，没有测量任何一项打开后的效果。")
    L.append("- 本盘点基于单次运行的审计计划；换配置（例如加 `--llm-audit`）会得到不同的计划。")
    L.append("")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"written {OUT} ({OUT.stat().st_size} bytes)")
    print(f"executed={len(executed)} partial={len(partial)} silent={len(silent)}")
    return 0


raise SystemExit(main())
