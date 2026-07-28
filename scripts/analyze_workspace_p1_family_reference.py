#!/usr/bin/env python3
"""Score P1 family-conditioned routing after authorized unblinding."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from scripts.validate_workspace_p0_annotations import read_jsonl


GROUNDING = "workspace_rubric_grounding"


def _index(
    rows: list[dict[str, Any]], *, name: str,
) -> dict[str, dict[str, Any]]:
    indexed = {str(row.get("blind_id") or ""): row for row in rows}
    if "" in indexed or len(indexed) != len(rows):
        raise ValueError(f"{name} contains empty or duplicate blind ids")
    return indexed


def _route_metrics(
    rows: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    positives = [row for row in rows if predicate(row)]
    result: dict[str, Any] = {"denominator": len(positives)}
    for label, field in (
        ("hidden_constraint", "routed_hidden_constraint"),
        ("support_challenge", "routed_support_challenge"),
        ("union", "routed_union"),
    ):
        hits = [row for row in positives if row[field]]
        misses = [row for row in positives if not row[field]]
        result[label] = {
            "hits": len(hits),
            "recall": len(hits) / len(positives) if positives else 1.0,
            "misses": [{
                "item_id": row["item_id"],
                "rubric_index": row["rubric_index"],
            } for row in misses],
        }
    return result


def summarize(
    mapping_rows: list[dict[str, Any]],
    annotation_rows: list[dict[str, Any]],
    *,
    p0_mapping_rows: list[dict[str, Any]] | None = None,
    p0_annotation_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    mapping = _index(mapping_rows, name="P1 mapping")
    annotations = _index(annotation_rows, name="P1 annotations")
    if set(mapping) != set(annotations):
        raise ValueError("P1 mapping and annotation coverage differs")
    joined = [
        {**mapping[blind_id], **annotations[blind_id]}
        for blind_id in sorted(mapping)
    ]

    primary = _route_metrics(
        joined,
        lambda row: (
            row["is_grounding_defect"] == "yes"
            and row["primary_family"] == GROUNDING
        ),
    )
    acceptable = _route_metrics(
        joined,
        lambda row: (
            row["is_grounding_defect"] == "yes"
            and (
                row["primary_family"] == GROUNDING
                or GROUNDING in row["acceptable_families"]
            )
        ),
    )
    mixed = _route_metrics(joined, lambda row: True)

    result: dict[str, Any] = {
        "rows": len(joined),
        "independent_verdict": dict(sorted(Counter(
            row["is_grounding_defect"] for row in joined
        ).items())),
        "grounding_class": dict(sorted(Counter(
            row["grounding_class"] for row in joined
        ).items())),
        "primary_family_all": dict(sorted(Counter(
            row["primary_family"] for row in joined
        ).items())),
        "primary_family_yes_only": dict(sorted(Counter(
            row["primary_family"] for row in joined
            if row["is_grounding_defect"] == "yes"
        ).items())),
        "routing": {
            "old_mixed_reference": mixed,
            "primary_grounding": primary,
            "acceptable_grounding": acceptable,
        },
        "excluded_from_positive_denominator": [{
            "item_id": row["item_id"],
            "rubric_index": row["rubric_index"],
            "verdict": row["is_grounding_defect"],
            "grounding_class": row["grounding_class"],
            "primary_family": row["primary_family"],
        } for row in joined if row["is_grounding_defect"] != "yes"],
    }

    if p0_mapping_rows is not None and p0_annotation_rows is not None:
        p0_mapping = _index(p0_mapping_rows, name="P0 mapping")
        p0_annotations = _index(p0_annotation_rows, name="P0 annotations")
        p0_by_key = {
            (row["item_id"], row["rubric_index"]):
            p0_annotations[blind_id]
            for blind_id, row in p0_mapping.items()
        }
        p1_by_key = {
            (row["item_id"], row["rubric_index"]):
            annotations[blind_id]
            for blind_id, row in mapping.items()
        }
        overlap = sorted(set(p0_by_key) & set(p1_by_key))
        fields = (
            "is_grounding_defect",
            "grounding_class",
            "primary_family",
            "evaluation_objectivity",
            "satisfaction_checkability",
        )
        result["p0_repeat_consistency"] = {
            "overlap": len(overlap),
            "fields": {
                field: {
                    "agree": sum(
                        p0_by_key[key][field] == p1_by_key[key][field]
                        for key in overlap
                    ),
                    "rate": (
                        sum(
                            p0_by_key[key][field] == p1_by_key[key][field]
                            for key in overlap
                        ) / len(overlap)
                        if overlap else 1.0
                    ),
                }
                for field in fields
            },
            "disagreements": [{
                "item_id": key[0],
                "rubric_index": key[1],
                "fields": {
                    field: {
                        "p0": p0_by_key[key][field],
                        "p1": p1_by_key[key][field],
                    }
                    for field in fields
                    if p0_by_key[key][field] != p1_by_key[key][field]
                },
            } for key in overlap if any(
                p0_by_key[key][field] != p1_by_key[key][field]
                for field in fields
            )],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--p0-mapping", type=Path)
    parser.add_argument("--p0-annotations", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))["rows"]
    p0_mapping = (
        json.loads(args.p0_mapping.read_text(encoding="utf-8"))["rows"]
        if args.p0_mapping else None
    )
    result = summarize(
        mapping,
        read_jsonl(args.annotations),
        p0_mapping_rows=p0_mapping,
        p0_annotation_rows=(
            read_jsonl(args.p0_annotations) if args.p0_annotations else None
        ),
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
