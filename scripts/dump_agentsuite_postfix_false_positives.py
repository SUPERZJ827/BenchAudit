#!/usr/bin/env python3
"""Dump full evidence for the eight false positives of the post-fix six runs."""
import json, re
from collections import defaultdict
from pathlib import Path

REPO = Path("/home/zhoujun/llmdata/after623")
P = REPO / "reports/agentsuite_acebench_102_deepseek_postfix_20260818"
MAT = REPO / "reports/agentsuite_acebench_102_solver_role_dev_20260816/materialized/audit_input.jsonl"
TRUTH = REPO / "reports/agentsuite_acebench_102_v2_20260816/materialized/sealed_truth.jsonl"
MUT = REPO / "reports/agentsuite_acebench_evaluator_mutation_20260817/report.json"
CONS = REPO / "reports/agentsuite_acebench_consequence_probe_20260817/probe_results.json"
OUT = REPO / "docs/research/ACEBENCH_修复后八条假阳核验_20260818.md"

VERDICT = {
    "normal_single_turn_single_function::59": ("标注疏漏", "题面自身存在日期矛盾，标答把越界数据纳入分析范围。"),
    "normal_single_turn_single_function::91": ("标注疏漏", "标答编造无来源标识符，并锁定一个从材料推不出的年份；官方 evaluator 拒绝任何等价替代写法。"),
    "normal_multi_turn_user_switch::11_1": ("标注疏漏", "用户明确请求的功能工具无法表达，标答改填了用户从未表态的选项。"),
    "normal_single_turn_parallel_function::1": ("标注疏漏", "标答把账户余额当成存款金额；省略该参数会被 evaluator 拒绝。"),
    "normal_preference::34": ("标注疏漏", "profile 记录了两项饮食偏好，标答只保留一项，而该字段无 enum 限制、本可同时表达。"),
    "normal_atom_bool::33": ("标注疏漏", "标答填入用户从未提及的三个开关，且与用户给出的数据方向相反；这三个参数的取值 evaluator 根本不检查。"),
    "normal_atom_object_deep::38": ("我们误报", "此条经过两次更正，最终判定的理由与最初记录的都不同。`sameDay.penalty` 在 schema 中是**必填**字段，解题者没有不填的选项；用户明确说 R789/R321/R654『same-day cancellation is not allowed』，使 `0` 成为唯一站得住的填法；变异探针进一步显示 evaluator 根本不检查该字段（`10 → 1009` 仍被接受），填什么都不影响任何解题者的得分。需要澄清的是，用户那句『5 days advance notice without penalty』复述的是 schema 中 `daysInAdvance` 的定义（『Minimum number of days in advance required to cancel without penalty』），并不是在陈述 same-day 罚金——所以我们原判词『该值无来源』本身没说错，错的是把『无来源』直接当成了缺陷。正确判据应为：无来源的值只有在**没有唯一站得住的填法**时才构成缺陷。"),
    "normal_multi_turn_user_adjust::37_2": ("我们误报", "比较操作本身对称，且前文先出现 Alice。模型自己在同一跑里也写了『reference is otherwise aligned』，属低置信度犹豫。"),
}
ORDER = list(VERDICT)


def load_jsonl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l]


def main():
    items = {r["id"]: r for r in load_jsonl(MAT)}
    truth = {r["id"]: int(r["is_issue"]) for r in load_jsonl(TRUTH)}
    mut = {v["item_id"]: v for v in json.loads(MUT.read_text(encoding="utf-8"))["violations"]}
    cons = defaultdict(list)
    for r in json.loads(CONS.read_text(encoding="utf-8"))["results"]:
        cons["agentsuite-ace::" + r["item"]].append(r)

    findings = defaultdict(list)
    for i in range(1, 7):
        for v in json.loads((P / f"run_r{i}/report.json").read_text(encoding="utf-8"))["violations"]:
            if (v.get("detection_method") == "llm_cross_artifact_consistency"
                    and v.get("defect_scope", "substantive") not in {"presentation", "operational"}
                    and v.get("defect_type") != "llm_audit_failure"):
                findings[v["item_id"]].append((f"r{i}", v))

    L = []
    a = L.append
    a("# ACEBench 修复后六跑的八条假阳：逐条核验")
    a("")
    a("> 日期：2026-08-18")
    a("> 口径：修复输入表示缺陷后的 DeepSeek V4 Flash + thinking 六跑并集（TP=49 / FP=8 / FN=2）")
    a("> 用途：供人工判断这八条究竟是标注疏漏还是我们误报")
    a("")
    a("“假阳”在此仅指被 AgentSuite 人工标签标为 `is_issue=0`。全部题面、标答与判词由冻结产物注入，未改写。")
    a("")
    a("## 结论速览")
    a("")
    a("| 条目 | 六跑票数 | 我的判定 |")
    a("|---|---:|---|")
    for s in ORDER:
        n = len({r for r, _ in findings.get("agentsuite-ace::" + s, [])})
        a(f"| `{s}` | {n}/6 | **{VERDICT[s][0]}** |")
    a("")
    a("---")
    a("")
    for s in ORDER:
        iid = "agentsuite-ace::" + s
        it = items[iid]
        rows = findings.get(iid, [])
        runs = sorted({r for r, _ in rows})
        confs = [float(v["confidence"]) for _, v in rows if v.get("confidence") is not None]
        kind, why = VERDICT[s]
        a(f"## `{s}`")
        a("")
        a(f"- 人工标签：`is_issue = {truth[iid]}`（非缺陷）")
        a(f"- 六跑报出：**{len(runs)}/6**"
          + (f"，置信度 {min(confs):.2f}–{max(confs):.2f}" if confs else ""))
        a(f"- **我的判定：{kind}**")
        a("")
        a(f"> {why}")
        a("")
        if iid in mut:
            a("### 机械证据：evaluator 不检查这些参数的取值")
            a("")
            a("| 参数 | 变异 | 原值 → 变异值 | evaluator |")
            a("|---|---|---|---|")
            for e in mut[iid]["evidence"]["unscored_parameters"]:
                a(f"| `{e['parameter_path']}` | {e['mutation']} | `{e['original_value']}` → `{e['mutated_value']}` | **接受** |")
            a("")
        if iid in cons:
            a("### 机械证据：evaluator 对合理替代解的反应")
            a("")
            a("| 探测 | evaluator |")
            a("|---|---|")
            for r in cons[iid]:
                a(f"| {r['probe']} | **{'接受' if r['evaluator_accepts'] else '拒绝'}** |")
            a("")
        a("### 完整题面")
        a("")
        a("```text")
        a(str(it.get("task") or "(无)"))
        a("```")
        a("")
        if it.get("time"):
            a(f"当前时间字段：`{it['time']}`")
            a("")
        a("### 标答")
        a("")
        a("```json")
        a(json.dumps(it.get("reference_solution"), ensure_ascii=False, indent=2))
        a("```")
        a("")
        names = {re.sub(r"_\d+$", "", str(n)) for n in (it.get("reference_solution") or {})}
        schemas = []
        for e in it.get("available_functions") or []:
            b = e.get("function") if isinstance(e.get("function"), dict) else e
            if str(b.get("name", "")) in names:
                schemas.append(e)
        a("<details><summary>被调用函数的完整 schema</summary>")
        a("")
        a("```json")
        a(json.dumps(schemas, ensure_ascii=False, indent=2))
        a("```")
        a("")
        a("</details>")
        a("")
        a("### 六跑判词（去重）")
        a("")
        seen = set()
        for run, v in rows:
            key = (v.get("message") or "")[:80]
            if key in seen:
                continue
            seen.add(key)
            a(f"**[{run}] `{v.get('defect_type')}` conf={v.get('confidence')}**")
            a("")
            a(f"> {v.get('message')}")
            a("")
        a("---")
        a("")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"written {OUT} ({OUT.stat().st_size} bytes, {len(L)} lines)")


main()
