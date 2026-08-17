#!/usr/bin/env python3
"""Dump complete, unabridged evidence for a list of ACEBench-102 items."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

REPO = Path("/home/zhoujun/llmdata/after623")
AGENTSUITE = Path("/home/zhoujun/llmdata/AgentSuite-main")
MAT = REPO / "reports/agentsuite_acebench_102_solver_role_dev_20260816/materialized/audit_input.jsonl"
TRUTH = REPO / "reports/agentsuite_acebench_102_v2_20260816/materialized/sealed_truth.jsonl"
PILOT = REPO / "reports/agentsuite_acebench_102_deepseek_thinking_pilot_20260816"
KSCAN = REPO / "reports/agentsuite_acebench_102_thinking_k_scan_20260817"
SPLIT = REPO / "reports/agentsuite_acebench_102_devtest_split_20260817"

FALSE_POSITIVES = [
    "normal_single_turn_single_function::91",
    "normal_atom_bool::33",
    "normal_single_turn_parallel_function::1",
    "normal_multi_turn_user_switch::11_1",
    "normal_single_turn_single_function::59",
    "normal_preference::34",
    "normal_atom_object_deep::38",
]
CONTROLS = [
    "normal_single_turn_single_function::9",
    "normal_atom_enum::22",
]

RUNS = [
    ("R1", PILOT / "run/report.json"),
    ("R2", PILOT / "run_r2/report.json"),
    ("R3", PILOT / "run_r3/report.json"),
    ("R4", KSCAN / "run_r4/report.json"),
    ("R5", KSCAN / "run_r5/report.json"),
]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def called_function_names(reference: dict) -> list[str]:
    return [re.sub(r"_\d+$", "", str(name)) for name in reference]


def schema_for(item: dict, names: list[str]) -> list[dict]:
    out = []
    for entry in item.get("available_functions") or []:
        body = entry.get("function") if isinstance(entry.get("function"), dict) else entry
        if str(body.get("name", "")) in names:
            out.append(entry)
    return out


def fenced(value, lang: str = "json") -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return f"```{lang}\n{text}\n```"


def main() -> int:
    items = {row["id"]: row for row in load_jsonl(MAT)}
    truth = {row["id"]: int(row["is_issue"]) for row in load_jsonl(TRUTH)}
    dev = set(json.loads((SPLIT / "dev_ids.json").read_text(encoding="utf-8")))

    human = {
        (r["task_name"], r["task_id"]): r
        for r in csv.DictReader(
            (AGENTSUITE / "pipeline/human_labelled_ground_truth/ACEBench.csv").open(encoding="utf-8")
        )
    }
    issues: dict[str, list[dict]] = {}
    for r in csv.DictReader((AGENTSUITE / "ACEBench/acebench_issues.csv").open(encoding="utf-8")):
        issues.setdefault(r["task_id"], []).append(r)

    findings: dict[str, list[tuple[str, dict]]] = {}
    for name, path in RUNS:
        report = json.loads(path.read_text(encoding="utf-8"))
        for v in report["violations"]:
            if (
                v.get("detection_method") == "llm_cross_artifact_consistency"
                and v.get("defect_scope", "substantive") not in {"presentation", "operational"}
                and v.get("defect_type") != "llm_audit_failure"
            ):
                findings.setdefault(v["item_id"], []).append((name, v))

    lines: list[str] = []
    add = lines.append
    add("# ACEBench-102 争议条目完整证据卷")
    add("")
    add("> 日期：2026-08-17")
    add("> 用途：供人工判读，判断这些条目的人工标注是否存在不一致")
    add("> 内容：7 条被 BenchAudit 五跑全部或多次报出、但人工标为 non-issue 的条目，")
    add("> 外加 2 条机制相同但人工标为 issue 的对照条目。全部字段未截断。")
    add("")
    add("原始来源：")
    add("")
    add("- 题面/工具/reference：`AgentSuite-main/ACEBench`，经 `scripts/prepare_agentsuite_acebench_102.py` 规范化")
    add("- 人工标签：`AgentSuite-main/pipeline/human_labelled_ground_truth/ACEBench.csv`（只有 `is_issue`，`issue_type` 全部为空）")
    add("- 官方问题理由：`AgentSuite-main/ACEBench/acebench_issues.csv`（102 条中多数 non-issue 无对应记录）")
    add("")
    add("---")
    add("")

    for section, group in (("第一部分：争议条目（人工标为 non-issue）", FALSE_POSITIVES),
                           ("第二部分：对照条目（人工标为 issue）", CONTROLS)):
        add(f"# {section}")
        add("")
        for short in group:
            task_name, task_id = short.split("::")
            item_id = f"agentsuite-ace::{short}"
            item = items[item_id]
            label = truth[item_id]
            half = "dev" if item_id in dev else "test"
            add(f"## `{short}`")
            add("")
            add(f"- **人工标签 `is_issue` = {label}**（{'缺陷' if label else '非缺陷'}）")
            add(f"- dev/test 切分归属：{half}")
            hm = human.get((task_name, task_id))
            add(f"- `ACEBench.csv` 记录：{json.dumps(hm, ensure_ascii=False) if hm else '未找到'}")
            rows = issues.get(f"{task_name}_{task_id}", []) + issues.get(task_id, [])
            if rows:
                for r in rows:
                    add(f"- `acebench_issues.csv` 记录：`detection={r['detection']}` "
                        f"`source={r['source']}` `gt_confirmed={r['gt_confirmed']}` `resolution={r['resolution']}`")
                    add("")
                    add(f"  > **官方 issue_reason**：{r['issue_reason']}")
                    add("")
                    if r.get("resolution_detail"):
                        add(f"  > **resolution_detail**：{r['resolution_detail']}")
                        add("")
            else:
                add("- `acebench_issues.csv` 记录：**无**（该条从未进入 COBA 的候选清单）")
            add("")
            add("### 完整题面")
            add("")
            add(fenced(item.get("task") or "(无)", "text"))
            add("")
            for field in ("time", "profile", "initial_config", "involved_classes", "milestones"):
                if item.get(field) not in (None, "", [], {}):
                    add(f"### 上下文字段 `{field}`")
                    add("")
                    add(fenced(item[field]))
                    add("")
            add("### Reference / Ground Truth（完整）")
            add("")
            add(fenced(item.get("reference_solution")))
            add("")
            names = called_function_names(item.get("reference_solution") or {})
            add(f"### 被调用函数的完整 schema（{', '.join(names)}）")
            add("")
            add(fenced(schema_for(item, names)))
            add("")
            add(f"### BenchAudit 五跑判词（该条被 {len({n for n, _ in findings.get(item_id, [])})}/5 跑报出）")
            add("")
            for name, v in findings.get(item_id, []):
                add(f"**[{name}] `{v.get('defect_type')}` conf={v.get('confidence')}**")
                add("")
                add(f"> {v.get('message')}")
                add("")
            if item_id not in findings:
                add("（未被任何一跑报出）")
                add("")
            add("---")
            add("")

    out = REPO / "docs/research/ACEBench_102_争议条目完整证据卷_20260817.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {out}  ({len(lines)} lines, {out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
