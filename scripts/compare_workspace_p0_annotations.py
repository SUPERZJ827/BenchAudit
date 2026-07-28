#!/usr/bin/env python3
"""Compare two validated Workspace P0 annotation files without unblinding."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.validate_workspace_p0_annotations import read_jsonl

VERDICTS = ("yes", "no", "uncertain")
FIELDS = (
    "is_grounding_defect",
    "grounding_class",
    "evaluation_objectivity",
    "satisfaction_checkability",
    "primary_family",
)


def by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {str(row.get("blind_id") or ""): row for row in rows}
    if len(result) != len(rows) or "" in result:
        raise ValueError("annotation rows contain duplicate or empty blind ids")
    return result


def compare_annotations(
    first_rows: list[dict[str, Any]],
    second_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    first = by_id(first_rows)
    second = by_id(second_rows)
    if set(first) != set(second):
        raise ValueError("annotation files have different blind-id coverage")
    ids = sorted(first)
    confusion = {
        left: {
            right: sum(
                first[key]["is_grounding_defect"] == left
                and second[key]["is_grounding_defect"] == right
                for key in ids
            )
            for right in VERDICTS
        }
        for left in VERDICTS
    }
    n = len(ids)
    observed = (
        sum(confusion[label][label] for label in VERDICTS) / n if n else 1.0
    )
    expected = (
        sum(
            sum(confusion[label].values())
            * sum(confusion[left][label] for left in VERDICTS)
            for label in VERDICTS
        )
        / (n * n)
        if n else 1.0
    )
    kappa = (
        (observed - expected) / (1.0 - expected)
        if expected < 1.0
        else 1.0
    )
    disagreements = [
        {
            "blind_id": key,
            "first": {
                field: first[key].get(field)
                for field in FIELDS
            },
            "second": {
                field: second[key].get(field)
                for field in FIELDS
            },
        }
        for key in ids
        if any(first[key].get(field) != second[key].get(field) for field in FIELDS)
    ]
    return {
        "rows": n,
        "field_agreement": {
            field: {
                "count": sum(
                    first[key].get(field) == second[key].get(field)
                    for key in ids
                ),
                "rate": (
                    sum(
                        first[key].get(field) == second[key].get(field)
                        for key in ids
                    )
                    / n
                    if n else 1.0
                ),
            }
            for field in FIELDS
        },
        "grounding_defect_confusion": confusion,
        "grounding_defect_cohens_kappa": kappa,
        "disagreements": disagreements,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare_annotations(
        read_jsonl(args.first),
        read_jsonl(args.second),
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
