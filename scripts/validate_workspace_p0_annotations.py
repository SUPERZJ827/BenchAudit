#!/usr/bin/env python3
"""Validate a Workspace P0 adjudication file against the frozen blind ids."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ENUMS = {
    "grounding_class": {
        "hidden_exact_constraint",
        "intrinsic_validity",
        "general_quality",
        "task_or_input_derived",
        "task_contract_conflict",
        "insufficient_evidence",
    },
    "is_grounding_defect": {"yes", "no", "uncertain"},
    "evaluation_objectivity": {"objective", "subjective", "mixed", "uncertain"},
    "satisfaction_checkability": {
        "static", "artifact_execution", "llm_judge", "human_review", "mixed",
        "uncertain",
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1,
    ):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: row must be an object")
        rows.append(row)
    return rows


def validate_annotations(
    template_rows: list[dict[str, Any]],
    annotation_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = [str(row.get("blind_id") or "") for row in template_rows]
    actual = [str(row.get("blind_id") or "") for row in annotation_rows]
    if len(expected) != len(set(expected)):
        raise ValueError("template contains duplicate or empty blind ids")
    if len(actual) != len(set(actual)):
        raise ValueError("annotations contain duplicate or empty blind ids")
    if set(expected) != set(actual):
        raise ValueError("annotation blind-id coverage differs from template")
    for row in annotation_rows:
        blind_id = row["blind_id"]
        for field, allowed in ENUMS.items():
            if row.get(field) not in allowed:
                raise ValueError(
                    f"{blind_id}: invalid {field}: {row.get(field)!r}"
                )
        confidence = row.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            raise ValueError(f"{blind_id}: confidence must be in [0,1]")
        if not str(row.get("primary_family") or "").strip():
            raise ValueError(f"{blind_id}: primary_family is required")
        families = row.get("acceptable_families")
        if not isinstance(families, list) or not all(
            isinstance(value, str) and value.strip() for value in families
        ):
            raise ValueError(f"{blind_id}: acceptable_families must be strings")
        if not str(row.get("root_cause_summary") or "").strip():
            raise ValueError(f"{blind_id}: root_cause_summary is required")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"{blind_id}: non-empty evidence is required")
        for evidence_row in evidence:
            if not isinstance(evidence_row, dict):
                raise ValueError(f"{blind_id}: evidence rows must be objects")
            if evidence_row.get("relation") not in {
                "supports", "contradicts", "insufficient",
            }:
                raise ValueError(f"{blind_id}: invalid evidence relation")
            if not str(evidence_row.get("source") or "").strip():
                raise ValueError(f"{blind_id}: evidence source is required")
            if not str(evidence_row.get("quote") or "").strip():
                raise ValueError(f"{blind_id}: evidence quote is required")
    return {
        "rows": len(annotation_rows),
        "grounding_class_counts": {
            value: sum(
                row["grounding_class"] == value for row in annotation_rows
            )
            for value in sorted(ENUMS["grounding_class"])
        },
        "grounding_defect_counts": {
            value: sum(
                row["is_grounding_defect"] == value for row in annotation_rows
            )
            for value in sorted(ENUMS["is_grounding_defect"])
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    args = parser.parse_args()
    summary = validate_annotations(
        read_jsonl(args.template),
        read_jsonl(args.annotations),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
