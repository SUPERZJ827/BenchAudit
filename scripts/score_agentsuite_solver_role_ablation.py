#!/usr/bin/env python3
"""Lock and score the six ACEBench solver-role development-ablation runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


RUNS = tuple(f"{arm}_r{repeat}" for arm in ("a0", "a1", "a2") for repeat in (1, 2))
BASE_METHODS = [
    "task_specification",
    "context_attachment",
    "expected_output",
    "oracle_ground_truth",
    "evaluator",
    "workspace_artifact_invariants",
    "solution_leak",
    "cross_artifact_consistency",
]
ELIGIBLE_BY_ARM = {
    "a0": {"llm_cross_artifact_consistency"},
    "a1": {"llm_cross_artifact_consistency"},
    "a2": {
        "llm_cross_artifact_consistency",
        "llm_reference_value_provenance",
        "reference_schema_validation",
    },
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def predicted_ids(report: dict[str, Any], arm: str) -> set[str]:
    return {
        str(row["item_id"])
        for row in report.get("violations", [])
        if row.get("detection_method") in ELIGIBLE_BY_ARM[arm]
        and row.get("defect_scope", "substantive") not in {"presentation", "operational"}
        and row.get("defect_type") != "llm_audit_failure"
    }


def expected_methods(arm: str) -> list[str]:
    return BASE_METHODS + (["reference_schema_validation"] if arm == "a2" else [])


def lock_predictions(root: Path) -> dict[str, dict[str, Any]]:
    """Create all six locks without reading or opening the truth file."""
    audit_path = root / "materialized/audit_input.jsonl"
    mappings = {
        "a0": root / "materialized/mapping_a0.json",
        "a1": root / "materialized/mapping.json",
        "a2": root / "materialized/mapping.json",
    }
    locks: dict[str, dict[str, Any]] = {}
    for run in RUNS:
        arm = run.split("_", 1)[0]
        run_dir = root / "runs" / run
        report_path = run_dir / "report.json"
        report = load_json(report_path)
        if report.get("methods_run") != expected_methods(arm):
            raise SystemExit(f"{run}: methods_run mismatch: {report.get('methods_run')!r}")
        predictions = predicted_ids(report, arm)
        llm = report.get("run_metadata", {}).get("llm", {})
        if int(llm.get("api_attempts", -1)) > 110:
            raise SystemExit(f"{run}: API-attempt cap exceeded")
        lock = {
            "schema_version": 1,
            "status": "PREDICTIONS_LOCKED_BEFORE_DEV_LABEL_JOIN",
            "scope_warning": "labels were already known before method development; this lock prevents post-run edits only",
            "run": run,
            "arm": arm,
            "prediction_report_sha256": sha256_file(report_path),
            "audit_input_sha256": sha256_file(audit_path),
            "mapping_sha256": sha256_file(mappings[arm]),
            "methods_run": report["methods_run"],
            "eligible_detection_methods": sorted(ELIGIBLE_BY_ARM[arm]),
            "prediction_only_counts": {"candidates": len(predictions)},
            "llm_usage": llm,
            "implementation": report.get("run_metadata", {}).get("implementation", {}),
        }
        lock_path = run_dir / "prediction_lock.json"
        lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        locks[run] = lock
    return locks


def metrics(predicted: set[str], positive: set[str], all_ids: set[str]) -> dict[str, Any]:
    negative = all_ids - positive
    tp_ids = predicted & positive
    fp_ids = predicted & negative
    fn_ids = positive - predicted
    tn_ids = negative - predicted
    tp, fp, fn, tn = map(len, (tp_ids, fp_ids, fn_ids, tn_ids))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "candidates": len(predicted),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "metrics": {"precision": precision, "recall": recall, "f1": f1},
        "tp_ids": sorted(tp_ids),
        "fp_ids": sorted(fp_ids),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    locks = lock_predictions(root)

    # Truth is intentionally opened only after every prediction lock exists.
    truth_path = root / "materialized/sealed_truth.jsonl"
    audit_path = root / "materialized/audit_input.jsonl"
    truth_rows = load_jsonl(truth_path)
    audit_rows = load_jsonl(audit_path)
    all_ids = {str(row["id"]) for row in audit_rows}
    truth = {str(row["id"]): int(row["is_issue"]) for row in truth_rows}
    if len(all_ids) != 102 or set(truth) != all_ids or sum(truth.values()) != 51:
        raise SystemExit("expected the frozen 102-item, 51/51 ACEBench development subset")
    positive = {item_id for item_id, label in truth.items() if label == 1}

    scored: dict[str, Any] = {}
    predictions_by_run: dict[str, set[str]] = {}
    for run in RUNS:
        arm = run.split("_", 1)[0]
        run_dir = root / "runs" / run
        report_path = run_dir / "report.json"
        if sha256_file(report_path) != locks[run]["prediction_report_sha256"]:
            raise SystemExit(f"{run}: report changed after locking")
        report = load_json(report_path)
        predicted = predicted_ids(report, arm)
        predictions_by_run[run] = predicted
        scored[run] = {
            **metrics(predicted, positive, all_ids),
            "llm_usage": locks[run]["llm_usage"],
            "prediction_lock_sha256": sha256_file(run_dir / "prediction_lock.json"),
        }

    comparisons: dict[str, Any] = {}
    for arm in ("a1", "a2"):
        changes = []
        for repeat in (1, 2):
            run = f"{arm}_r{repeat}"
            base = f"a0_r{repeat}"
            arm_tp = set(scored[run]["tp_ids"])
            base_tp = set(scored[base]["tp_ids"])
            changes.append({
                "repeat": repeat,
                "tp_delta": len(arm_tp) - len(base_tp),
                "unique_tp_over_a0": sorted(arm_tp - base_tp),
                "lost_tp_vs_a0": sorted(base_tp - arm_tp),
            })
        comparisons[f"{arm}_vs_a0"] = {
            "repeats": changes,
            "predeclared_meaningful_tp_gate_passed": all(row["tp_delta"] >= 5 for row in changes),
        }

    result = {
        "schema_version": 1,
        "status": "POST_LABEL_DEV_ABLATION_SCORED_AFTER_SIX_LOCKS",
        "scope": {
            "dataset": "AgentSuite ACEBench public balanced human-alignment subset",
            "items": 102,
            "positive": 51,
            "negative": 51,
            "development_only": True,
            "warning": "not held-out evidence; labels informed the architecture changes",
        },
        "truth_sha256": sha256_file(truth_path),
        "runs": scored,
        "comparisons": comparisons,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
