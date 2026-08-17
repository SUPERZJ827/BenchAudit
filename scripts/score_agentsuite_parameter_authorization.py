#!/usr/bin/env python3
"""Lock and score three independent parameter-authorization runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.run_agentsuite_parameter_authorization import (
    LEGITIMATE_SOURCES,
    SOURCE_STATES,
    parameter_candidate,
)


THRESHOLDS = (0.45, 0.60, 0.70, 0.80)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def baseline_ids(report: dict[str, Any]) -> set[str]:
    return {
        str(row["item_id"])
        for row in report.get("violations", [])
        if row.get("detection_method") == "llm_cross_artifact_consistency"
        and row.get("defect_scope", "substantive") not in {"presentation", "operational"}
        and row.get("defect_type") != "llm_audit_failure"
    }


def ids_at_threshold(rows: list[dict[str, Any]], threshold: float) -> set[str]:
    return {
        str(row["item_id"])
        for row in rows
        if row.get("operational_error") is None
        and isinstance(row.get("result"), dict)
        and parameter_candidate(row["result"], threshold)
    }


def metrics(predicted: set[str], positive: set[str], all_ids: set[str]) -> dict[str, Any]:
    tp_ids = predicted & positive
    fp_ids = predicted - positive
    fn_ids = positive - predicted
    tn_ids = (all_ids - positive) - predicted
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


def median(values: list[float]) -> float:
    values = sorted(values)
    return values[len(values) // 2]


def jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left | right else 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--baseline-report", required=True, type=Path)
    parser.add_argument("--baseline-lock", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    baseline_report = load_json(args.baseline_report)
    baseline_lock = load_json(args.baseline_lock)
    if sha256_file(args.baseline_report) != baseline_lock["prediction_report_sha256"]:
        raise SystemExit("baseline report no longer matches historical prediction lock")
    base = baseline_ids(baseline_report)
    if len(base) != 37:
        raise SystemExit(f"expected 37 baseline candidates, got {len(base)}")

    rows_by_run: dict[str, list[dict[str, Any]]] = {}
    ids_by_run: dict[str, dict[float, set[str]]] = {}
    for repeat in (1, 2, 3):
        run = f"parameter_r{repeat}"
        run_dir = args.root / "runs" / run
        prediction_path = run_dir / "predictions.jsonl"
        receipt_path = run_dir / "run_receipt.json"
        receipt = load_json(receipt_path)
        if sha256_file(prediction_path) != receipt["predictions_sha256"]:
            raise SystemExit(f"{run}: predictions do not match runner receipt")
        rows = load_jsonl(prediction_path)
        if len(rows) != 65 or receipt["operational_failures"] != 0:
            raise SystemExit(f"{run}: expected 65 complete rows")
        by_threshold = {threshold: ids_at_threshold(rows, threshold) for threshold in THRESHOLDS}
        for threshold, selected in by_threshold.items():
            if selected & base:
                raise SystemExit(f"{run}@{threshold}: escaped frozen negative route")
        lock = {
            "schema_version": 1,
            "status": "PREDICTIONS_LOCKED_BEFORE_DEV_LABEL_JOIN",
            "scope_warning": "labels were already known; development optimization only",
            "run": run,
            "predictions_sha256": sha256_file(prediction_path),
            "runner_receipt_sha256": sha256_file(receipt_path),
            "baseline_report_sha256": sha256_file(args.baseline_report),
            "prediction_only_counts": {
                str(threshold): len(by_threshold[threshold]) for threshold in THRESHOLDS
            },
        }
        lock_path = run_dir / "prediction_lock.json"
        if lock_path.exists():
            raise SystemExit(f"refusing to overwrite lock: {lock_path}")
        lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rows_by_run[run] = rows
        ids_by_run[run] = by_threshold

    all_ids = {str(row["id"]) for row in load_jsonl(args.input)}
    truth = {str(row["id"]): int(row["is_issue"]) for row in load_jsonl(args.truth)}
    positive = {item_id for item_id, value in truth.items() if value == 1}
    if len(all_ids) != 102 or set(truth) != all_ids or len(positive) != 51:
        raise SystemExit("unexpected ACEBench-102 truth shape")

    base_metrics = metrics(base, positive, all_ids)
    runs: dict[str, Any] = {}
    for run in rows_by_run:
        runs[run] = {
            "by_threshold": {
                str(threshold): {
                    "parameter_only": metrics(ids_by_run[run][threshold], positive, all_ids),
                    "fixed_union": metrics(base | ids_by_run[run][threshold], positive, all_ids),
                }
                for threshold in THRESHOLDS
            },
            "source_status_counts": {
                state: sum(
                    1
                    for row in rows_by_run[run]
                    for parameter in row["result"]["parameters"]
                    if parameter.get("source_status") == state
                )
                for state in SOURCE_STATES
            },
            "prediction_lock_sha256": sha256_file(args.root / "runs" / run / "prediction_lock.json"),
            "llm_usage": load_json(args.root / "runs" / run / "run_receipt.json")["llm_usage"],
        }

    summary: dict[str, Any] = {}
    decision: dict[str, Any] = {}
    for threshold in THRESHOLDS:
        key = str(threshold)
        parameter_sets = [ids_by_run[f"parameter_r{i}"][threshold] for i in (1, 2, 3)]
        parameter_rows = [
            runs[f"parameter_r{i}"]["by_threshold"][key]["parameter_only"]
            for i in (1, 2, 3)
        ]
        union_rows = [
            runs[f"parameter_r{i}"]["by_threshold"][key]["fixed_union"]
            for i in (1, 2, 3)
        ]
        median_new_tp = median([row["confusion_matrix"]["tp"] for row in parameter_rows])
        median_new_fp = median([row["confusion_matrix"]["fp"] for row in parameter_rows])
        median_union_f1 = median([row["metrics"]["f1"] for row in union_rows])
        if median_new_tp >= 6 and median_new_fp <= 2 and median_union_f1 > base_metrics["metrics"]["f1"]:
            outcome = "SUPPORTED_BUILD_NEXT_CHECKER"
        elif median_new_tp <= 3:
            outcome = "STOP_SPLIT_CHECKER_EXPANSION"
        else:
            outcome = "INCONCLUSIVE_DO_NOT_EXPAND"
        summary[key] = {
            "median_new_tp": median_new_tp,
            "median_new_fp": median_new_fp,
            "median_union_tp": median([row["confusion_matrix"]["tp"] for row in union_rows]),
            "median_union_fp": median([row["confusion_matrix"]["fp"] for row in union_rows]),
            "median_union_precision": median([row["metrics"]["precision"] for row in union_rows]),
            "median_union_recall": median([row["metrics"]["recall"] for row in union_rows]),
            "median_union_f1": median_union_f1,
            "candidate_jaccard": {
                "r1_r2": jaccard(parameter_sets[0], parameter_sets[1]),
                "r1_r3": jaccard(parameter_sets[0], parameter_sets[2]),
                "r2_r3": jaccard(parameter_sets[1], parameter_sets[2]),
            },
        }
        decision[key] = {
            "predeclared_outcome": outcome,
            "gate": "median new TP >=6; median new FP <=2; union median F1 > A1 baseline",
        }

    result = {
        "schema_version": 1,
        "status": "POST_LABEL_DEV_PARAMETER_AUTHORIZATION_SCORED_AFTER_THREE_LOCKS",
        "scope_warning": "same ACEBench labels used for iterative development; not generalization evidence",
        "baseline": base_metrics,
        "runs": runs,
        "summary_by_threshold": summary,
        "decision_by_threshold": decision,
        "primary_threshold": 0.60,
        "truth_sha256": sha256_file(args.truth),
        "evidence_tier": "review_only",
        "provenance_rule": {
            "legitimate_sources": sorted(LEGITIMATE_SOURCES),
            "ungrounded_requires_all_excluded": True,
        },
    }
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite scoring output: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "baseline": base_metrics,
        "summary_by_threshold": summary,
        "decision_by_threshold": decision,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
