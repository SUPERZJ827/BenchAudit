#!/usr/bin/env python3
"""Analyze A-prime routing on the frozen Workspace development partitions."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.run_workspace_static_llm_ablation import (  # noqa: E402
    NEGATIVE_REVIEW_LABEL,
    POSITIVE_REVIEW_LABEL,
    _read_completed_items,
    binary_metrics,
    parse_reviewed_reference,
)

Key = tuple[str, int]
GROUNDING = "workspace_rubric_grounding"
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def family_positive_keys(
    mapping_path: Path,
    annotations_path: Path,
) -> set[Key]:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))["rows"]
    annotations = {
        row["blind_id"]: row for row in read_jsonl(annotations_path)
    }
    if {row["blind_id"] for row in mapping} != set(annotations):
        raise ValueError("family mapping and annotations coverage differs")
    result = set()
    for row in mapping:
        annotation = annotations[row["blind_id"]]
        if (
            annotation["is_grounding_defect"] == "yes"
            and (
                annotation["primary_family"] == GROUNDING
                or GROUNDING in annotation["acceptable_families"]
            )
        ):
            result.add((row["item_id"], int(row["rubric_index"])))
    return result


def _baseline_a_candidates(
    rows: dict[str, dict[str, Any]],
) -> set[Key]:
    result: set[Key] = set()
    for item_id, row in rows.items():
        for decision in row.get("decisions", []):
            if not isinstance(decision, dict):
                continue
            index = decision.get("rubric_index")
            scanner = decision.get("scanner")
            if (
                isinstance(index, int)
                and isinstance(scanner, dict)
                and "hidden_constraint"
                in (scanner.get("triage_selected_views") or [])
            ):
                result.add((item_id, index))
    return result


def _structured_routes(
    rows: dict[str, dict[str, Any]],
) -> tuple[dict[Key, dict[str, Any]], set[str], int]:
    routes: dict[Key, dict[str, Any]] = {}
    operational_unknown: set[str] = set()
    rubric_count = 0
    for item_id, row in rows.items():
        for decision in row.get("decisions", []):
            if not isinstance(decision, dict):
                continue
            rubric_count += 1
            index = decision.get("rubric_index")
            scanner = decision.get("scanner")
            if not isinstance(index, int) or not isinstance(scanner, dict):
                operational_unknown.add(item_id)
                continue
            if scanner.get("objective_resolver_short_circuit") is True:
                continue
            route = scanner.get("structured_route")
            if not isinstance(route, dict):
                operational_unknown.add(item_id)
                continue
            routes[(item_id, index)] = route
        if any(
            isinstance(finding, dict)
            and finding.get("defect_scope") == "operational"
            for finding in row.get("findings", [])
        ):
            operational_unknown.add(item_id)
    return routes, operational_unknown, rubric_count


def _candidate_set(
    routes: dict[Key, dict[str, Any]],
    threshold: float,
) -> set[Key]:
    return {
        key
        for key, route in routes.items()
        if route.get("policy_selected_before_threshold") is True
        and float(route.get("confidence") or 0.0) >= threshold
    }


def _task_hits(candidates: set[Key], positives: set[Key]) -> int:
    positive_tasks = {item_id for item_id, _ in positives}
    hit_tasks = {item_id for item_id, _ in candidates & positives}
    return len(hit_tasks & positive_tasks)


def _task_router_calls(rows: dict[str, dict[str, Any]]) -> int:
    """Count task-level semantic router calls, independent of view count."""

    return sum(
        any(
            isinstance(decision, dict)
            and isinstance(decision.get("scanner"), dict)
            and int(
                decision["scanner"].get("triage_view_count") or 0
            ) > 0
            for decision in row.get("decisions", [])
        )
        for row in rows.values()
    )


def analyze(
    *,
    structured_rows: dict[str, dict[str, Any]],
    baseline_rows: dict[str, dict[str, Any]],
    expected_items: set[str],
    reviewed_labels: dict[Key, str],
    family_positives_all: set[Key],
    selected_threshold: float | None = None,
) -> dict[str, Any]:
    if set(structured_rows) != expected_items:
        raise ValueError("structured result coverage differs from partition")
    if not expected_items <= set(baseline_rows):
        raise ValueError("baseline is missing partition items")
    baseline_rows = {
        item_id: baseline_rows[item_id] for item_id in expected_items
    }
    routes, operational_unknown, rubric_count = _structured_routes(
        structured_rows,
    )
    family_positives = {
        key for key in family_positives_all if key[0] in expected_items
    }
    reviewed_universe = {
        key
        for key, label in reviewed_labels.items()
        if key[0] in expected_items
        and label in {POSITIVE_REVIEW_LABEL, NEGATIVE_REVIEW_LABEL}
    }
    reviewed_positives = {
        key
        for key, label in reviewed_labels.items()
        if key[0] in expected_items and label == POSITIVE_REVIEW_LABEL
    }
    baseline_candidates = _baseline_a_candidates(baseline_rows)
    baseline_router_calls = _task_router_calls(baseline_rows)
    baseline_logical_calls = baseline_router_calls + len(baseline_candidates)
    reason_counts_all = Counter(
        str(route.get("reason_code") or "") for route in routes.values()
    )
    action_counts = Counter(
        str(route.get("action") or "") for route in routes.values()
    )
    source_counts = Counter(
        str(route.get("evidence_source") or "") for route in routes.values()
    )
    deterministic_overrides = Counter(
        str(route.get("policy_override") or "")
        for route in routes.values()
        if str(route.get("policy_override") or "").startswith(
            "deterministic_rejection:"
        )
    )
    threshold_rows: list[dict[str, Any]] = []
    for threshold in THRESHOLDS:
        candidates = _candidate_set(routes, threshold)
        router_calls = _task_router_calls(structured_rows)
        logical_calls = router_calls + len(candidates)
        family_hits = len(candidates & family_positives)
        family_recall = (
            family_hits / len(family_positives)
            if family_positives else 1.0
        )
        reviewed = binary_metrics(
            candidates, reviewed_positives, reviewed_universe,
        )
        threshold_rows.append({
            "threshold": threshold,
            "candidates": len(candidates),
            "candidate_rate": (
                len(candidates) / rubric_count if rubric_count else 0.0
            ),
            "family_grounding": {
                "hits": family_hits,
                "positives": len(family_positives),
                "recall": family_recall,
                "misses": sorted(family_positives - candidates),
            },
            "reviewed": reviewed,
            "router_calls": router_calls,
            "counterfactual_verifier_calls": len(candidates),
            "logical_calls": logical_calls,
            "logical_call_reduction_vs_a": (
                1.0 - logical_calls / baseline_logical_calls
                if baseline_logical_calls else 0.0
            ),
            "logical_calls_per_reviewed_positive_rubric_hit": (
                logical_calls / reviewed["tp"] if reviewed["tp"] else None
            ),
            "reviewed_positive_task_hits": _task_hits(
                candidates, reviewed_positives,
            ),
            "reason_counts": dict(sorted(Counter(
                str(routes[key].get("reason_code") or "")
                for key in candidates
            ).items())),
        })
    passing = [
        row
        for row in threshold_rows
        if (
            row["family_grounding"]["recall"] >= 0.90
            and row["candidate_rate"] <= 0.40
            and not operational_unknown
        )
    ]
    chosen = (
        sorted(
            passing,
            key=lambda row: (
                row["candidate_rate"],
                -row["family_grounding"]["recall"],
                -row["threshold"],
            ),
        )[0]
        if passing else None
    )
    if selected_threshold is not None:
        matches = [
            row for row in threshold_rows
            if row["threshold"] == selected_threshold
        ]
        if not matches:
            raise ValueError("selected threshold is outside frozen threshold set")
        chosen = matches[0]
    baseline_family_hits = len(baseline_candidates & family_positives)
    return {
        "counts": {
            "tasks": len(expected_items),
            "rubrics": rubric_count,
            "structured_rows": len(routes),
            "family_grounding_positives": len(family_positives),
            "reviewed_universe": len(reviewed_universe),
            "reviewed_positives": len(reviewed_positives),
        },
        "baseline_a": {
            "candidates": len(baseline_candidates),
            "candidate_rate": (
                len(baseline_candidates) / rubric_count
                if rubric_count else 0.0
            ),
            "router_calls": baseline_router_calls,
            "logical_calls": baseline_logical_calls,
            "family_grounding_hits": baseline_family_hits,
            "family_grounding_recall": (
                baseline_family_hits / len(family_positives)
                if family_positives else 1.0
            ),
        },
        "decomposition": {
            "reason_counts_all": dict(sorted(reason_counts_all.items())),
            "action_counts": dict(sorted(action_counts.items())),
            "evidence_source_counts": dict(sorted(source_counts.items())),
            "deterministic_overrides": dict(
                sorted(deterministic_overrides.items())
            ),
            "legacy_reason_observability": (
                "unavailable: the original A schema stored indices only"
            ),
        },
        "operational_unknown_tasks": sorted(operational_unknown),
        "thresholds": threshold_rows,
        "chosen_working_point": chosen,
        "calibration_go": chosen is not None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structured-results", type=Path, required=True)
    parser.add_argument("--baseline-results", type=Path, required=True)
    parser.add_argument("--partition-manifest", type=Path, required=True)
    parser.add_argument("--reviewed-reference", type=Path, required=True)
    parser.add_argument("--family-mapping", type=Path, required=True)
    parser.add_argument("--family-annotations", type=Path, required=True)
    parser.add_argument("--selected-threshold", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(
        args.partition_manifest.read_text(encoding="utf-8")
    )
    result = analyze(
        structured_rows=_read_completed_items(args.structured_results),
        baseline_rows=_read_completed_items(args.baseline_results),
        expected_items={str(value) for value in manifest["item_ids"]},
        reviewed_labels=parse_reviewed_reference(args.reviewed_reference),
        family_positives_all=family_positive_keys(
            args.family_mapping, args.family_annotations,
        ),
        selected_threshold=args.selected_threshold,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
