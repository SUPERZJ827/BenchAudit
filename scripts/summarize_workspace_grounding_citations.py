#!/usr/bin/env python3
"""Summarize the fail-closed citation gate for a Workspace grounding run.

This is intentionally a post-processor: it never calls an LLM and therefore
cannot change the scored protocol or consume additional API budget.  Rows from
older run signatures in an append-only decision file are ignored.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--json-out", required=True, type=Path)
    parser.add_argument("--md-out", required=True, type=Path)
    return parser.parse_args()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def summarize(decisions: Path, run_summary: Path) -> dict[str, Any]:
    summary = json.loads(run_summary.read_text(encoding="utf-8"))
    signature = str(summary.get("run", {}).get("signature") or "")
    if not signature:
        raise ValueError("summary has no run.signature")
    rows = [
        row for row in _read_jsonl(decisions)
        if row.get("run_signature") == signature
    ]
    expected = int(summary.get("run", {}).get("rubrics") or 0)
    identities = [
        (str(row.get("task_id") or row.get("item_id") or ""), int(row["rubric_index"]))
        for row in rows
    ]
    duplicates = len(identities) - len(set(identities))
    if len(rows) != expected or duplicates:
        raise ValueError(
            f"decision alignment failed: rows={len(rows)}, expected={expected}, "
            f"duplicate_keys={duplicates}"
        )

    gates: Counter[str] = Counter()
    validity: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    valid_support_rows = 0
    for row in rows:
        validation = row.get("citation_validation")
        if not isinstance(validation, dict):
            gates["missing_citation_validation"] += 1
            validity["missing"] += 1
        else:
            gates[str(validation.get("gate_reason") or "missing_gate_reason")] += 1
            validity[
                "valid" if validation.get("all_claimed_valid") is True else "invalid"
            ] += 1
            valid_support_rows += int(
                int(validation.get("valid_support_count") or 0) > 0
            )
        labels[str(row.get("label") or "missing")] += 1

    valid = validity["valid"]
    return {
        "schema_version": "workspace-grounding-citation-summary-v1",
        "source_decisions": str(decisions.resolve()),
        "source_summary": str(run_summary.resolve()),
        "run_signature": signature,
        "rows": len(rows),
        "tasks": len({key[0] for key in identities}),
        "duplicate_keys": duplicates,
        "citation_valid_rows": valid,
        "citation_invalid_rows": validity["invalid"],
        "citation_metadata_missing_rows": validity["missing"],
        "citation_valid_rate": valid / len(rows) if rows else 0.0,
        "rows_with_verified_positive_support": valid_support_rows,
        "gate_reason_distribution": dict(sorted(gates.items())),
        "post_gate_label_distribution": dict(sorted(labels.items())),
        "claim_boundary": (
            "This reports deterministic citation-source validation, not semantic "
            "accuracy and not defect precision/recall."
        ),
    }


def render_markdown(value: dict[str, Any]) -> str:
    gates = "\n".join(
        f"- `{name}`: {count}"
        for name, count in value["gate_reason_distribution"].items()
    )
    labels = "\n".join(
        f"- `{name}`: {count}"
        for name, count in value["post_gate_label_distribution"].items()
    )
    return f"""# Workspace grounding 引用闸门统计

- Run signature: `{value['run_signature']}`
- Rubrics: {value['rows']}（任务数 {value['tasks']}，重复键 {value['duplicate_keys']}）
- 引用全部通过: {value['citation_valid_rows']} / {value['rows']} ({value['citation_valid_rate']:.2%})
- 引用失败: {value['citation_invalid_rows']}
- 至少一个已核验正向支持引用: {value['rows_with_verified_positive_support']}

## Gate 原因

{gates}

## 闸门后标签

{labels}

## 结论边界

该统计只衡量引用能否在声明来源中被确定性复核，不衡量语义判断正确率，也不是 benchmark 缺陷的 precision/recall。
"""


def main() -> int:
    args = parse_args()
    value = summarize(args.decisions, args.summary)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_out.write_text(render_markdown(value), encoding="utf-8")
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
