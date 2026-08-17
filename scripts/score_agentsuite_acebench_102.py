#!/usr/bin/env python3
"""Score a hash-locked ACEBench-102 prediction report against sealed truth."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_METHODS = [
    "task_specification",
    "context_attachment",
    "expected_output",
    "oracle_ground_truth",
    "evaluator",
    "workspace_artifact_invariants",
    "solution_leak",
    "cross_artifact_consistency",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def eligible_finding(row: dict[str, Any]) -> bool:
    return (
        row.get("detection_method") == "llm_cross_artifact_consistency"
        and row.get("defect_scope", "substantive") not in {"presentation", "operational"}
        and row.get("defect_type") != "llm_audit_failure"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    lock = load_json(root / "prediction_lock.json")
    report_path = root / "predictions/report.json"
    truth_path = root / "materialized/sealed_truth.jsonl"
    audit_path = root / "materialized/audit_input.jsonl"
    expected_hashes = {
        report_path: lock["prediction_report_sha256"],
        truth_path: lock["sealed_truth_sha256"],
        audit_path: lock["audit_input_sha256"],
    }
    for path, expected in expected_hashes.items():
        actual = sha256_file(path)
        if actual != expected:
            raise SystemExit(f"hash mismatch for {path}: expected {expected}, got {actual}")

    report = load_json(report_path)
    if report.get("methods_run") != EXPECTED_METHODS:
        raise SystemExit(f"methods_run mismatch: {report.get('methods_run')!r}")
    truth_rows = load_jsonl(truth_path)
    audit_rows = load_jsonl(audit_path)
    truth_by_id = {str(row["id"]): int(row["is_issue"]) for row in truth_rows}
    audit_ids = {str(row["id"]) for row in audit_rows}
    if len(truth_by_id) != 102 or set(truth_by_id) != audit_ids:
        raise SystemExit("truth and audit input must contain the same 102 unique IDs")
    if sum(truth_by_id.values()) != 51:
        raise SystemExit("expected exactly 51 positive labels")

    predicted = {
        str(row["item_id"])
        for row in report.get("violations", [])
        if eligible_finding(row)
    }
    if not predicted <= audit_ids:
        raise SystemExit("prediction report contains IDs outside the frozen audit input")
    if len(predicted) != int(lock["prediction_only_counts"]["candidates"]):
        raise SystemExit("candidate count differs from prediction lock")
    positive = {item_id for item_id, label in truth_by_id.items() if label == 1}
    negative = audit_ids - positive
    tp = len(predicted & positive)
    fp = len(predicted & negative)
    fn = len(positive - predicted)
    tn = len(negative - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(audit_ids)

    result = {
        "schema_version": 1,
        "status": "SCORED_AFTER_PREDICTION_LOCK",
        "scope": {
            "dataset": "AgentSuite ACEBench public balanced human-alignment subset",
            "items": 102,
            "positive": 51,
            "negative": 51,
            "warning": "balanced-subset precision is not natural-prevalence precision",
            "comparison_type": "cross-method transfer on COBA-selected cases, not a neutral system ranking",
        },
        "predictions": len(predicted),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "metrics": {
            "precision": precision,
            "recall": recall,
            "specificity": specificity,
            "f1": f1,
            "accuracy": accuracy,
            "balanced_accuracy": (recall + specificity) / 2,
        },
        "published_agentsuite_reference": {
            "precision": 0.865,
            "recall": 0.882,
            "f1": 0.874,
            "note": "paper-reported ACEBench human-alignment result; different model and benchmark-specific prompt",
        },
        "locked_inputs": {
            "prediction_report_sha256": lock["prediction_report_sha256"],
            "sealed_truth_sha256": lock["sealed_truth_sha256"],
            "audit_input_sha256": lock["audit_input_sha256"],
        },
        "llm_usage": lock["llm_usage"],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
