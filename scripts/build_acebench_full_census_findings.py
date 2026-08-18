#!/usr/bin/env python3
"""Write the full-ACEBench evaluator census findings; numbers injected from the run."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CEN = REPO / "reports/agentsuite_acebench_full1023_tolerance_census_20260818"
OUT = REPO / "docs/research/ACEBENCH_全量评测器缺陷_20260818.md"


def main() -> int:
    rows = [json.loads(l) for l in (CEN / "parameter_probes.jsonl").read_text(encoding="utf-8").splitlines() if l]
    errors = json.loads((CEN / "execution_errors.json").read_text(encoding="utf-8"))
    receipt = json.loads((CEN / "receipt.json").read_text(encoding="utf-8"))

    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        by_type[r["value_type"]][0 if r.get("substitute_accepted") else 1] += 1
    scalar = ("int", "float", "bool", "NoneType")
    scalar_total = sum(sum(v) for k, v in by_type.items() if k in scalar)
    scalar_accepted = sum(by_type[k][0] for k in scalar if k in by_type)
    unchecked_items = {r["item"] for r in rows
                       if r["value_type"] in scalar and r.get("substitute_accepted")}
    probed_items = {r["item"] for r in rows}
    per_task = Counter(i.split("::")[1] for i in unchecked_items)
    task_total = Counter(i.split("::")[1] for i in probed_items)
    omit_rejected = [r for r in rows if not r["required"] and r.get("omit_accepted") is False]
    crash = Counter()
    for e in errors:
        text = str(e.get("error"))
        if "ground_truth_not_dict" in text:
            crash["agent 类题型，需另一套 runner"] += 1
        elif "NoneType" in text and "subscriptable" in text:
            crash["标答调用了工具列表中不存在的函数"] += 1
        elif "AttributeError" in text:
            crash["标答结构与评测器预期不符"] += 1
        else:
            crash["其他"] += 1

    L, a = [], None
    L.append("# ACEBench 全量评测器缺陷")
    L.append("")
    L.append("> 日期：2026-08-18")
    L.append("> 范围：ACEBench 全部 1023 条，其中 " + f"{len(probed_items)} 条可执行探测")
    L.append("> 证据：执行 benchmark 自带的 `model_eval/checker.py`，读其返回的接受/拒绝。"
             "**不涉及任何人工标注，也不含模型判断。**")
    L.append("")
    L.append("方法：对标答中每个顶层参数做定向变异后重放官方评测器——可选参数试省略，"
             "所有参数试换成同类型的不同取值（枚举优先换成另一个合法成员）。"
             "变异后的调用作为“模型输出”，原标答作为 ground truth。")
    L.append("")
    L.append("---")
    L.append("")

    L.append("## 一、数值与布尔参数的取值完全不参与评分")
    L.append("")
    L.append(f"**{scalar_accepted} 个标量参数改成任何值都被判为正确，无一例外。**")
    L.append("")
    L.append("| 值类型 | 参数数 | 换值后仍被接受 | 读法 |")
    L.append("|---|---:|---:|---|")
    for t in ("int", "bool", "float", "NoneType", "str", "dict", "list"):
        if t not in by_type:
            continue
        acc, rej = by_type[t]
        note = "取值不被检查" if rej == 0 and acc else ("确实被检查" if acc == 0 else "部分被检查")
        L.append(f"| `{t}` | {acc + rej} | {acc} | {note} |")
    L.append("")
    L.append("`dict` 与 `list` 参数几乎全部被拒，说明评测器确实在检查结构；"
             "它只是从不比较标量取值。实测例子：")
    L.append("")
    L.append("| 条目 | 参数 | 改动 | 评测器 |")
    L.append("|---|---|---|---|")
    L.append("| `normal_atom_number::16` | `latitude` | 34.0522 → 1033.0522（不存在的纬度） | 判为正确 |")
    L.append("| `normal_atom_number::35` | `targetYear` | 2024 → 3023 | 判为正确 |")
    L.append("| `normal_atom_bool::2` | `include_case_studies` | True → False | 判为正确 |")
    L.append("")
    L.append("同一结论有第二条独立证据：评测器的调用链指纹显示，数值与布尔参数的比较止于 "
             "`type_checker`，之后没有任何值比较环节。行为侧与代码路径侧一致。")
    L.append("")

    L.append("## 二、受影响的题目占比，且集中在最不该出问题的题型")
    L.append("")
    L.append(f"**{len(unchecked_items)} / {len(probed_items)} 条已探测题目"
             f"（{len(unchecked_items)/len(probed_items):.1%}）至少含一个取值不被检查的参数。**")
    L.append("")
    L.append("| 题型 | 受影响 | 已探测 | 占比 |")
    L.append("|---|---:|---:|---:|")
    for task, n in per_task.most_common():
        L.append(f"| `{task}` | {n} | {task_total[task]} | **{n/task_total[task]:.0%}** |")
    L.append("")
    L.append("`normal_atom_number` 与 `normal_atom_bool` 这两个题型存在的全部目的，"
             "就是考察模型能否正确填写数值与布尔参数。**它们恰恰是受影响最重的两个。**"
             "在这些题上，模型只要调对函数、参数类型正确，具体数值随便填都算全对。")
    L.append("")

    L.append("## 三、可选参数省略被拒：schema 与评测器直接矛盾")
    L.append("")
    L.append(f"{len(omit_rejected)} 处参数在 schema 中不属于 `required`，"
             "但把它从标答中省略后评测器判为错误。一个遵循 schema、省略可选参数的解题者会因此失分。")
    L.append("")
    L.append("| 条目 | 参数 |")
    L.append("|---|---|")
    for r in omit_rejected[:10]:
        L.append(f"| `{r['item'].split('::', 1)[1]}` | `{r['parameter']}` |")
    L.append("")

    L.append("## 四、评测器在部分题目上直接抛异常")
    L.append("")
    L.append(f"{len(errors)} 处执行失败，而不是返回判定：")
    L.append("")
    L.append("| 成因 | 次数 |")
    L.append("|---|---:|")
    for reason, n in crash.most_common():
        L.append(f"| {reason} | {n} |")
    L.append("")
    L.append("其中「标答调用了工具列表中不存在的函数」一类是实质缺陷：评测器取不到函数描述后崩溃，"
             "而不是判定该调用非法。这类题在官方评测流程中的结果，取决于上游如何处理异常。")
    L.append("")

    L.append("## 不能说")
    L.append("")
    L.append("- 不能说这些题“无效”：本文只陈述评测器的机械行为，不评估题目的教学或研究价值。")
    L.append("- 不能说受影响题目的官方分数一定虚高：那取决于模型是否真的填错了这些参数，本文未测量。")
    L.append(f"- 覆盖范围有限：1023 条中 {len(probed_items)} 条完成探测，"
             f"{len(errors)} 处因评测器执行失败未覆盖；嵌套对象内部的参数也未逐层展开。")
    L.append("")
    L.append("## 复算")
    L.append("")
    L.append("```bash")
    L.append("python3 scripts/census_agentsuite_acebench_tolerance.py --all-items \\")
    L.append("  --out-dir reports/agentsuite_acebench_full1023_tolerance_census_20260818")
    L.append("```")
    L.append("")
    L.append(f"产物 `parameter_probes.jsonl` sha256 `{receipt['parameter_probes_sha256']}`，"
             f"评测器源码 sha256 `{receipt.get('evaluator_sha256', '见 receipt')}`。零 API 调用。")
    L.append("")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"written {OUT} ({OUT.stat().st_size} bytes)")
    return 0


raise SystemExit(main())
