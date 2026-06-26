#!/usr/bin/env python3
"""Create a human triage workbook from a BenchCore report and source JSONL."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()

    rows = load_jsonl_by_id(args.source)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for violation in report.get("violations", []):
        by_item[str(violation["item_id"])].append(violation)

    lines = build_workbook(args.title, args.source, args.report, rows, by_item)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(by_item)} triage cases to {args.out}")
    return 0


def load_jsonl_by_id(path: Path) -> dict[str, dict[str, Any]]:
    rows = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            rows[str(row.get("id"))] = row
    return rows


def build_workbook(
    title: str,
    source: Path,
    report_path: Path,
    rows: dict[str, dict[str, Any]],
    by_item: dict[str, list[dict[str, Any]]],
) -> list[str]:
    lines = [
        f"# {title}",
        "",
        "这个文件是人工审核工作表，不是机器审计报告。",
        "",
        "## 审核目标",
        "",
        "对每个候选 item，请判断三件事：",
        "",
        "1. 系统指出的问题是否真实存在。",
        "2. 如果真实存在，系统给出的 defect type / artifact 是否基本正确。",
        "3. 这个问题是否会影响答案、评分或数据质量。",
        "",
        "建议填写的人工标签：",
        "",
        "- `true_defect`: 系统发现的是实际 benchmark 缺陷。",
        "- `label_clean_but_real_quality_issue`: 不一定影响答案，但确实是数据质量问题。",
        "- `false_positive`: 系统误报。",
        "- `uncertain`: 需要更多背景或专家判断。",
        "",
        "建议同时记录：",
        "",
        "- `category_correct`: yes / partial / no",
        "- `artifact_correct`: yes / partial / no",
        "- `notes`: 简短原因",
        "",
        "## 来源",
        "",
        f"- Source: `{source}`",
        f"- Report: `{report_path}`",
        f"- Candidate items: `{len(by_item)}`",
        "",
        "## Cases",
        "",
    ]
    for index, item_id in enumerate(sorted(by_item), 1):
        row = rows.get(item_id, {})
        violations = by_item[item_id]
        lines.extend(render_case(index, item_id, row, violations))
    return lines


def render_case(
    index: int,
    item_id: str,
    row: dict[str, Any],
    violations: list[dict[str, Any]],
) -> list[str]:
    lines = [
        f"### {index}. `{item_id}`",
        "",
        "**人工审核填写**",
        "",
        "- human_label: `TODO`",
        "- category_correct: `TODO`",
        "- artifact_correct: `TODO`",
        "- notes: `TODO`",
        "",
        "**原始题目**",
        "",
        block(row.get("question") or row.get("task") or ""),
        "",
    ]
    if row.get("context"):
        lines.extend(["**Context**", "", block(row["context"]), ""])
    if row.get("table"):
        table = str(row["table"])
        if len(table) > 1200:
            lines.extend(
                [
                    "<details>",
                    "<summary>完整表格 markdown</summary>",
                    "",
                    block(table),
                    "",
                    "</details>",
                    "",
                ]
            )
        else:
            lines.extend(["**表格**", "", block(table), ""])
    lines.extend(
        [
            "**Gold / Accepted Output**",
            "",
            f"- gold: `{inline_json(row.get('gold'))}`",
            f"- aliases: `{inline_json(row.get('aliases'))}`",
            f"- output_contract: `{inline_json(row.get('output_contract'))}`",
            f"- evaluator: `{inline_json(row.get('evaluator'))}`",
            "",
        ]
    )
    metadata = row.get("metadata")
    if metadata:
        lines.extend(["**Metadata**", "", block(metadata), ""])
    lines.extend(["**系统发现**", ""])
    for violation in violations:
        mark = "review" if violation.get("review_only") else "confirmed"
        lines.append(
            "- "
            f"`{violation.get('defect_type')}` / "
            f"`{violation.get('artifact')}` / "
            f"`{violation.get('detection_method')}` / "
            f"`{violation.get('severity')}` / {mark} / "
            f"confidence={float(violation.get('confidence', 0.0)):.2f}"
        )
        lines.append(f"  - message: {violation.get('message')}")
        if violation.get("suggested_repair"):
            lines.append(f"  - suggested_repair: {violation.get('suggested_repair')}")
        evidence = violation.get("evidence")
        if evidence:
            lines.append("  - evidence:")
            lines.append(indent_block(evidence, spaces=4))
    lines.extend(
        [
            "",
            "**审核提示**",
            "",
            "- 先看原题、gold、context/table 是否足以支持答案。",
            "- 再看系统发现是否指出了真实问题。",
            "- 如果只是表达不自然但不影响理解和评分，通常标 `false_positive` 或 `label_clean_but_real_quality_issue`。",
            "- 如果问题类别对但 artifact 错了，`category_correct=partial` 或 `artifact_correct=no`。",
            "",
        ]
    )
    return lines


def block(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def indent_block(value: Any, spaces: int) -> str:
    prefix = " " * spaces
    text = block(value)
    return "\n".join(prefix + line for line in text.splitlines())


def inline_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


if __name__ == "__main__":
    raise SystemExit(main())
