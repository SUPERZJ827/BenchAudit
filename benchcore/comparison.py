from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from .loader import load_rows


_IGNORED_DEFECTS = {"llm_audit_failure", "auditor_contradiction"}
_STRONG_METHODS = {
    "llm_gold_audit",
    "llm_quantity_consistency",
    "executable_evidence",
    "executable_evidence_replay",
    "evaluator_replay",
    "differential_testing",
    "metamorphic_testing",
}
_STRONG_DEFECTS = {
    "wrong_gold_answer",
    "invalid_choice_gold",
    "missing_oracle",
    "duplicate_choices",
    "duplicate_item_id",
    "conflicting_duplicate_oracle",
    "evaluator_mismatch",
    "metamorphic_inconsistency",
}
_WEAK_REVIEW_DEFECTS = {
    "ambiguous_goal",
    "bad_options_clarity",
    "context_version_mismatch_risk",
    "missing_accepted_alternatives",
    "missing_condition",
    "missing_output_contract",
    "source_reference_missing",
    "temporal_scope_missing",
}


def nested_get(row: dict[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _substantive_violations(violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        v
        for v in violations
        if v.get("defect_scope", "substantive") == "substantive"
        and v.get("defect_type") not in _IGNORED_DEFECTS
    ]


def candidate_tier(violations: list[dict[str, Any]]) -> str:
    """Classify an item as priority or exploratory from its evidence strength."""
    substantive = _substantive_violations(violations)
    if not substantive:
        return "exploratory"
    if any(not v.get("review_only", False) for v in substantive):
        return "priority"

    methods = {
        v.get("detection_method", "").split("+")[0]
        for v in substantive
        if v.get("detection_method")
    }
    has_strong_signal = any(
        (
            v.get("detection_method", "").split("+")[0] in _STRONG_METHODS
            or v.get("defect_type") in _STRONG_DEFECTS
        )
        and v.get("detection_method") != "llm_quantity_consistency_nonmaterial"
        and float(v.get("confidence", 0.0) or 0.0) >= 0.6
        for v in substantive
    )
    has_corroboration = len(methods) >= 2 or any(
        v.get("evidence", {}).get("llm_corroborated_by") for v in substantive
    )
    only_weak_signals = all(v.get("defect_type") in _WEAK_REVIEW_DEFECTS for v in substantive)

    if has_strong_signal or (has_corroboration and not only_weak_signals):
        return "priority"
    return "exploratory"


def compute_item_risk_score(violations: list[dict[str, Any]]) -> float:
    """Compute a risk score [0, 1] for ranking candidates by review priority.

    Priority evidence is ranked above exploratory heuristics. Within a tier,
    confidence, independent-method corroboration, and strong oracle/execution
    evidence determine review order.
    """
    relevant = [
        v for v in violations
        if v.get("defect_scope") != "operational"
        and v.get("defect_type") not in _IGNORED_DEFECTS
    ]
    if not relevant:
        return 0.0

    substantive = [v for v in relevant if v.get("defect_scope", "substantive") == "substantive"]

    if not substantive:
        return 0.07  # presentation-only signal: low but non-zero

    confirmed = [v for v in substantive if not v.get("review_only", False)]
    tier = candidate_tier(substantive)
    score = 0.72 if confirmed else (0.52 if tier == "priority" else 0.12)
    max_confidence = max(float(v.get("confidence", 0.0) or 0.0) for v in substantive)
    score += 0.12 * max_confidence

    llm_methods = {
        v["detection_method"].split("+")[0]
        for v in substantive
        if v.get("detection_method", "").startswith("llm_")
    }
    score += min(0.12, 0.06 * (len(llm_methods) - 1)) if len(llm_methods) > 1 else 0.0

    strong_evidence = any(
        v.get("detection_method", "").split("+")[0] in _STRONG_METHODS
        or v.get("defect_type") in _STRONG_DEFECTS
        for v in substantive
    )
    if strong_evidence:
        score += 0.10

    has_contradiction = any(v.get("defect_type") == "auditor_contradiction" for v in violations)

    llm_subs = [v for v in substantive if v.get("detection_method", "").startswith("llm_")]
    all_needs_expert = bool(llm_subs) and all(
        v.get("evidence", {}).get("llm_result", {}).get("needs_expert", False)
        for v in llm_subs
    )

    if has_contradiction:
        score -= 0.08
    if all_needs_expert:
        score -= 0.08

    return max(0.0, min(1.0, score))


def _primary_defect_type(violations: list[dict[str, Any]]) -> str | None:
    """Return the single most representative substantive defect type for an item."""
    severity_rank = {"critical": 4, "major": 3, "minor": 2, "review": 1}
    candidates = [
        v for v in violations
        if v.get("defect_scope", "substantive") == "substantive"
        and v.get("defect_type") not in ("llm_audit_failure", "auditor_contradiction")
    ]
    if not candidates:
        return None
    confirmed = [v for v in candidates if not v.get("review_only", False)]
    pool = confirmed if confirmed else candidates
    return max(pool, key=lambda v: severity_rank.get(v.get("severity", "review"), 1))["defect_type"]


def compare_report(
    input_path: Path,
    report_path: Path,
    truth_field: str,
    clean_values: set[str],
    offset: int = 0,
    limit: int | None = None,
    id_field: str = "id",
    include_methods: set[str] | None = None,
    include_defects: set[str] | None = None,
    include_scopes: set[str] | None = None,
    rows_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = rows_override if rows_override is not None else load_rows(input_path)
    if rows_override is None:
        rows = rows[max(offset, 0) :]
        if limit is not None:
            rows = rows[: max(limit, 0)]
    report = json.loads(report_path.read_text(encoding="utf-8"))

    truth_by_item: dict[str, str] = {}
    for idx, row in enumerate(rows):
        item_id = str(nested_get(row, id_field) or row.get("item_id") or f"item-{offset + idx}")
        label = nested_get(row, truth_field)
        label_text = "missing" if label is None else str(label)
        truth_by_item[item_id] = label_text

    truth_items = {
        item_id for item_id, label in truth_by_item.items() if label.lower() not in clean_values
    }

    # --- All violations from report, grouped by item ---
    all_violations_by_item: dict[str, list[dict[str, Any]]] = {}
    for v in report.get("violations", []):
        all_violations_by_item.setdefault(v["item_id"], []).append(v)

    # --- Selected violations (for main metrics) ---
    selected_violations = [
        v
        for v in report.get("violations", [])
        if v.get("defect_type") != "llm_audit_failure"
        if v.get("defect_scope", "substantive") != "operational"
        if (not include_methods or v.get("detection_method") in include_methods)
        and (not include_defects or v.get("defect_type") in include_defects)
        and (not include_scopes or v.get("defect_scope", "substantive") in include_scopes)
    ]
    confirmed_predictions = {
        v["item_id"] for v in selected_violations if not v.get("review_only", False)
    }
    review_predictions = {
        v["item_id"] for v in selected_violations if v.get("review_only", False)
    }
    candidate_predictions = confirmed_predictions | review_predictions

    exploratory_predictions = {
        item_id
        for item_id in candidate_predictions
        if candidate_tier(
            [v for v in selected_violations if v["item_id"] == item_id]
        )
        == "exploratory"
    }
    priority_predictions = candidate_predictions - exploratory_predictions

    # --- Substantive-only metrics (exclude presentation scope) ---
    subst_violations = [
        v for v in report.get("violations", [])
        if v.get("defect_type") != "llm_audit_failure"
        if v.get("defect_scope", "substantive") not in ("operational", "presentation")
        if (not include_methods or v.get("detection_method") in include_methods)
        and (not include_defects or v.get("defect_type") in include_defects)
    ]
    subst_confirmed = {v["item_id"] for v in subst_violations if not v.get("review_only", False)}
    subst_candidate = subst_confirmed | {
        v["item_id"] for v in subst_violations if v.get("review_only", False)
    }

    # --- Risk scores and review budget ---
    risk_scores: dict[str, float] = {
        item_id: compute_item_risk_score(all_violations_by_item.get(item_id, []))
        for item_id in candidate_predictions
    }
    sorted_candidates = sorted(
        risk_scores.items(),
        key=lambda x: (
            0 if x[0] in priority_predictions else 1,
            -x[1],
            x[0],
        ),
    )
    total_items = len(rows)
    review_budget: dict[int, dict[str, Any]] = {}
    for pct in (5, 10, 20):
        budget = max(1, math.ceil(total_items * pct / 100))
        reviewed = {item_id for item_id, _ in sorted_candidates[:budget]}
        tp = reviewed & truth_items
        recall = len(tp) / len(truth_items) if truth_items else 0.0
        review_budget[pct] = {
            "budget_items": budget,
            "reviewed_candidates": len(reviewed & candidate_predictions),
            "true_positive": len(tp),
            "recall": recall,
        }

    # --- Per-truth-type recall ---
    truth_labels = sorted(
        {lbl for lbl in truth_by_item.values() if lbl.lower() not in clean_values}
    )
    per_type: dict[str, dict[str, Any]] = {}
    for label in truth_labels:
        label_items = {iid for iid, lbl in truth_by_item.items() if lbl == label}
        cand_tp = label_items & candidate_predictions
        conf_tp = label_items & confirmed_predictions

        # Predicted defect types for TP items
        predicted_type_counts: Counter[str] = Counter()
        for iid in cand_tp:
            ptype = _primary_defect_type(all_violations_by_item.get(iid, []))
            if ptype:
                predicted_type_counts[ptype] += 1

        per_type[label] = {
            "truth_count": len(label_items),
            "candidate_tp": len(cand_tp),
            "confirmed_tp": len(conf_tp),
            "candidate_recall": len(cand_tp) / len(label_items) if label_items else 0.0,
            "confirmed_recall": len(conf_tp) / len(label_items) if label_items else 0.0,
            "top_predicted_types": dict(predicted_type_counts.most_common()),
            "missed_items": sorted(label_items - candidate_predictions),
        }

    # --- False-positive defect breakdown ---
    fp_type_counts: Counter[str] = Counter()
    for item_id in confirmed_predictions - truth_items:
        ptype = _primary_defect_type(all_violations_by_item.get(item_id, []))
        if ptype:
            fp_type_counts[ptype] += 1

    return {
        "input_path": str(input_path),
        "report_path": str(report_path),
        "truth_field": truth_field,
        "clean_values": sorted(clean_values),
        "include_methods": sorted(include_methods or []),
        "include_defects": sorted(include_defects or []),
        "include_scopes": sorted(include_scopes or []),
        "items": len(rows),
        "truth_items": len(truth_items),
        "truth_distribution": dict(Counter(truth_by_item.values())),
        "confirmed": metrics(confirmed_predictions, truth_items),
        "candidate": metrics(candidate_predictions, truth_items),
        "priority_candidate": metrics(priority_predictions, truth_items),
        "exploratory_candidate": metrics(exploratory_predictions, truth_items),
        "substantive_only": {
            "confirmed": metrics(subst_confirmed, truth_items),
            "candidate": metrics(subst_candidate, truth_items),
        },
        "per_type": per_type,
        "false_positive_defect_breakdown": dict(fp_type_counts.most_common()),
        "review_budget": review_budget,
        "candidate_risk_scores": dict(sorted_candidates),
        "candidate_ranking": [
            {
                "item_id": item_id,
                "tier": "priority" if item_id in priority_predictions else "exploratory",
                "risk_score": score,
            }
            for item_id, score in sorted_candidates
        ],
        "false_positive_items": sorted(confirmed_predictions - truth_items),
        "candidate_false_positive_items": sorted(candidate_predictions - truth_items),
        "priority_false_positive_items": sorted(priority_predictions - truth_items),
        "exploratory_false_positive_items": sorted(exploratory_predictions - truth_items),
        "false_negative_items": sorted(truth_items - confirmed_predictions),
        "candidate_missed_items": sorted(truth_items - candidate_predictions),
        "truth_labels": {
            item_id: truth_by_item[item_id]
            for item_id in sorted(truth_items | confirmed_predictions | review_predictions)
        },
    }


def metrics(predictions: set[str], truth: set[str]) -> dict[str, Any]:
    tp = predictions & truth
    fp = predictions - truth
    fn = truth - predictions
    precision = len(tp) / len(predictions) if predictions else 0.0
    recall = len(tp) / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "prediction_items": len(predictions),
        "true_positive": len(tp),
        "false_positive": len(fp),
        "false_negative": len(fn),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def write_comparison_markdown(path: Path, comparison: dict[str, Any]) -> None:
    lines = [
        "# Supervised Benchmark Audit Comparison",
        "",
        f"- Items: `{comparison['items']}`",
        f"- Truth defect items: `{comparison['truth_items']}`",
        f"- Truth field: `{comparison['truth_field']}`",
        "",
        "## Overall Metrics",
        "",
        "| Mode | Predictions | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("confirmed", "candidate", "priority_candidate", "exploratory_candidate"):
        m = comparison.get(name)
        if not m:
            continue
        label = name.replace("_", " ")
        lines.append(
            f"| {label} | {m['prediction_items']} | {m['true_positive']} | "
            f"{m['false_positive']} | {m['false_negative']} | "
            f"{m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} |"
        )

    # Substantive-only metrics
    subst = comparison.get("substantive_only", {})
    if subst:
        lines.extend([
            "",
            "## Substantive-Only Metrics",
            "",
            "_Excludes `presentation` scope violations (presentation defects reported separately)._",
            "",
            "| Mode | Predictions | TP | FP | FN | Precision | Recall | F1 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for name in ("confirmed", "candidate"):
            m = subst.get(name, {})
            if m:
                lines.append(
                    f"| {name} | {m['prediction_items']} | {m['true_positive']} | "
                    f"{m['false_positive']} | {m['false_negative']} | "
                    f"{m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} |"
                )

    # Per-type recall
    per_type = comparison.get("per_type", {})
    if per_type:
        lines.extend([
            "",
            "## Per-Type Candidate Recall",
            "",
            "| Truth Label | Count | Cand TP | Cand Recall | Conf TP | Conf Recall | Top Predicted Types |",
            "|---|---:|---:|---:|---:|---:|---|",
        ])
        for label, stats in sorted(per_type.items()):
            top = ", ".join(
                f"{t}({n})" for t, n in list(stats["top_predicted_types"].items())[:3]
            )
            lines.append(
                f"| `{label}` | {stats['truth_count']} | {stats['candidate_tp']} | "
                f"{stats['candidate_recall']:.3f} | {stats['confirmed_tp']} | "
                f"{stats['confirmed_recall']:.3f} | {top or '—'} |"
            )

    # Review budget
    review_budget = comparison.get("review_budget", {})
    if review_budget:
        lines.extend([
            "",
            "## Review Budget (Recall@Top-N%)",
            "",
            "| Budget % | Items Reviewed | Candidates in Budget | TP | Recall |",
            "|---:|---:|---:|---:|---:|",
        ])
        for pct in sorted(int(k) for k in review_budget):
            rb = review_budget[pct]
            lines.append(
                f"| {pct}% | {rb['budget_items']} | {rb['reviewed_candidates']} | "
                f"{rb['true_positive']} | {rb['recall']:.3f} |"
            )

    # False positive defect breakdown
    fp_breakdown = comparison.get("false_positive_defect_breakdown", {})
    if fp_breakdown:
        lines.extend([
            "",
            "## False Positive Defect Breakdown (Confirmed FPs)",
            "",
        ])
        for dtype, count in fp_breakdown.items():
            lines.append(f"- `{dtype}`: {count}")

    for title, key in (
        ("False Positives (Confirmed)", "false_positive_items"),
        ("False Negatives (Confirmed)", "false_negative_items"),
        ("Candidate Misses", "candidate_missed_items"),
    ):
        lines.extend(["", f"## {title}", ""])
        values = comparison[key]
        if not values:
            lines.append("- None")
        else:
            for item_id in values:
                label = comparison["truth_labels"].get(item_id, "ok")
                lines.append(f"- `{item_id}`: truth=`{label}`")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
