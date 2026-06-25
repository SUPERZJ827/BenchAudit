from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .loader import load_rows


def nested_get(row: dict[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


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
        "false_positive_items": sorted(confirmed_predictions - truth_items),
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
        "## Metrics",
        "",
        "| Mode | Predictions | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("confirmed", "candidate"):
        m = comparison[name]
        lines.append(
            f"| {name} | {m['prediction_items']} | {m['true_positive']} | "
            f"{m['false_positive']} | {m['false_negative']} | "
            f"{m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} |"
        )
    for title, key in (
        ("False Positives", "false_positive_items"),
        ("False Negatives", "false_negative_items"),
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
