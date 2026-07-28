#!/usr/bin/env python3
"""Analyze Workspace P0 independent review after protocol-authorized unblinding."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scripts.compare_workspace_p0_annotations import compare_annotations
from scripts.validate_workspace_p0_annotations import read_jsonl


FOCUS_UNSUPPORTED = "focus_b_only_unsupported"
FOCUS_MISSED = "focus_missed_reviewed_positive"


def _counter(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row[field]) for row in rows).items()))


def _index(
    rows: list[dict[str, Any]], *, name: str,
) -> dict[str, dict[str, Any]]:
    result = {str(row.get("blind_id") or ""): row for row in rows}
    if "" in result or len(result) != len(rows):
        raise ValueError(f"{name} contains empty or duplicate blind ids")
    return result


def summarize(
    mapping_rows: list[dict[str, Any]],
    independent_rows: list[dict[str, Any]],
    evidence_review_rows: list[dict[str, Any]],
    *,
    incremental_dual_calls: int = 206,
) -> dict[str, Any]:
    mapping = _index(mapping_rows, name="mapping")
    independent = _index(independent_rows, name="independent review")
    evidence_review = _index(
        evidence_review_rows, name="evidence review",
    )
    if set(mapping) != set(independent) or set(mapping) != set(evidence_review):
        raise ValueError("mapping and annotation blind-id coverage differs")

    joined = []
    for blind_id in sorted(mapping):
        joined.append({
            **mapping[blind_id],
            "independent_verdict": independent[blind_id][
                "is_grounding_defect"
            ],
            "independent_class": independent[blind_id]["grounding_class"],
            "independent_primary_family": independent[blind_id][
                "primary_family"
            ],
            "independent_acceptable_families": independent[blind_id][
                "acceptable_families"
            ],
            "independent_confidence": independent[blind_id]["confidence"],
            "evidence_review_verdict": evidence_review[blind_id][
                "is_grounding_defect"
            ],
        })

    by_stratum: dict[str, Any] = {}
    for stratum in sorted({row["source_stratum"] for row in joined}):
        rows = [row for row in joined if row["source_stratum"] == stratum]
        consensus = Counter()
        for row in rows:
            first = row["independent_verdict"]
            second = row["evidence_review_verdict"]
            consensus[first if first == second else "conflict"] += 1
        by_stratum[stratum] = {
            "rows": len(rows),
            "independent_verdict": _counter(rows, "independent_verdict"),
            "independent_class": _counter(rows, "independent_class"),
            "independent_primary_family": _counter(
                rows, "independent_primary_family",
            ),
            "cross_review_consensus": dict(sorted(consensus.items())),
        }

    focus = [row for row in joined if row["source_stratum"] == FOCUS_UNSUPPORTED]
    focus_counts = Counter(row["independent_verdict"] for row in focus)
    decisive = focus_counts["yes"] + focus_counts["no"]
    agreed_positive = sum(
        row["independent_verdict"] == "yes"
        and row["evidence_review_verdict"] == "yes"
        for row in focus
    )
    focus_grounding_positive = sum(
        row["independent_verdict"] == "yes"
        and row["independent_primary_family"] == "workspace_rubric_grounding"
        for row in focus
    )

    missed = [row for row in joined if row["source_stratum"] == FOCUS_MISSED]
    missed_grounding_positive = sum(
        row["independent_verdict"] == "yes"
        and (
            row["independent_primary_family"] == "workspace_rubric_grounding"
            or "workspace_rubric_grounding"
            in row["independent_acceptable_families"]
        )
        for row in missed
    )

    comparison = compare_annotations(
        evidence_review_rows, independent_rows,
    )
    return {
        "rows": len(joined),
        "by_stratum": by_stratum,
        "b_only_final_unsupported": {
            "rows": len(focus),
            "independent_yes": focus_counts["yes"],
            "independent_no": focus_counts["no"],
            "independent_uncertain": focus_counts["uncertain"],
            "independent_positive_rate_all": (
                focus_counts["yes"] / len(focus) if focus else None
            ),
            "independent_positive_rate_decisive": (
                focus_counts["yes"] / decisive if decisive else None
            ),
            "independent_grounding_family_positive": focus_grounding_positive,
            "cross_review_agreed_positive": agreed_positive,
            "incremental_dual_calls": incremental_dual_calls,
            "calls_per_independent_positive": (
                incremental_dual_calls / focus_counts["yes"]
                if focus_counts["yes"] else None
            ),
            "calls_per_cross_review_agreed_positive": (
                incremental_dual_calls / agreed_positive
                if agreed_positive else None
            ),
        },
        "previously_missed_reviewed_positive": {
            "rows": len(missed),
            "independent_verdict": _counter(
                missed, "independent_verdict",
            ),
            "independent_primary_family": _counter(
                missed, "independent_primary_family",
            ),
            "eligible_as_grounding_positive": missed_grounding_positive,
            "case_details": [{
                "blind_id": row["blind_id"],
                "item_id": row["item_id"],
                "rubric_index": row["rubric_index"],
                "independent_verdict": row["independent_verdict"],
                "independent_class": row["independent_class"],
                "independent_primary_family": row[
                    "independent_primary_family"
                ],
            } for row in missed],
        },
        "cross_review_agreement": {
            "verdict_agreement": comparison["field_agreement"][
                "is_grounding_defect"
            ],
            "grounding_class_agreement": comparison["field_agreement"][
                "grounding_class"
            ],
            "objectivity_agreement": comparison["field_agreement"][
                "evaluation_objectivity"
            ],
            "checkability_agreement": comparison["field_agreement"][
                "satisfaction_checkability"
            ],
            "primary_family_agreement": comparison["field_agreement"][
                "primary_family"
            ],
            "verdict_cohens_kappa": comparison[
                "grounding_defect_cohens_kappa"
            ],
            "verdict_confusion": comparison[
                "grounding_defect_confusion"
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--evidence-review", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--incremental-dual-calls", type=int, default=206)
    args = parser.parse_args()
    mapping_document = json.loads(args.mapping.read_text(encoding="utf-8"))
    result = summarize(
        mapping_document["rows"],
        read_jsonl(args.independent),
        read_jsonl(args.evidence_review),
        incremental_dual_calls=args.incremental_dual_calls,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
