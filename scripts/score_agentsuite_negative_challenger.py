#!/usr/bin/env python3
"""Lock and score three ACEBench negative-challenger runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


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


def challenger_ids_at_threshold(rows: list[dict[str, Any]], threshold: float) -> set[str]:
    selected: set[str] = set()
    for row in rows:
        result = row.get("result")
        if not isinstance(result, dict) or row.get("operational_error") is not None:
            continue
        if str(result.get("status", "uncertain")).strip() != "defect":
            continue
        if result.get("material") is not True:
            continue
        try:
            confidence = float(result.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        required = (
            "defect_type",
            "reference_target",
            "contradiction",
            "task_or_policy_evidence",
            "reference_evidence",
        )
        if confidence < threshold:
            continue
        if any(not str(result.get(key) or "").strip() for key in required):
            continue
        if str(result.get("defect_type")).strip() == "none":
            continue
        selected.add(str(row["item_id"]))
    return selected


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
        raise SystemExit("baseline report no longer matches its historical prediction lock")
    base = baseline_ids(baseline_report)
    if len(base) != 37:
        raise SystemExit(f"expected 37 frozen baseline candidates, got {len(base)}")

    locks: dict[str, dict[str, Any]] = {}
    challenger_by_run: dict[str, dict[float, set[str]]] = {}
    for repeat in (1, 2, 3):
        run = f"challenger_r{repeat}"
        run_dir = args.root / "runs" / run
        prediction_path = run_dir / "predictions.jsonl"
        receipt_path = run_dir / "run_receipt.json"
        receipt = load_json(receipt_path)
        if sha256_file(prediction_path) != receipt["predictions_sha256"]:
            raise SystemExit(f"{run}: predictions no longer match runner receipt")
        rows = load_jsonl(prediction_path)
        if len(rows) != 65 or receipt["operational_failures"] != 0:
            raise SystemExit(f"{run}: expected 65 complete challenger rows")
        challenger_by_threshold = {
            threshold: challenger_ids_at_threshold(rows, threshold)
            for threshold in THRESHOLDS
        }
        for threshold, challenger in challenger_by_threshold.items():
            if challenger & base:
                raise SystemExit(
                    f"{run}@{threshold}: challenger escaped frozen negative route"
                )
        lock = {
            "schema_version": 1,
            "status": "PREDICTIONS_LOCKED_BEFORE_DEV_LABEL_JOIN",
            "scope_warning": "labels were already known; development optimization only",
            "run": run,
            "predictions_sha256": sha256_file(prediction_path),
            "runner_receipt_sha256": sha256_file(receipt_path),
            "baseline_report_sha256": sha256_file(args.baseline_report),
            "prediction_only_counts": {
                "baseline": len(base),
                "challenger_unique_by_threshold": {
                    str(threshold): len(challenger_by_threshold[threshold])
                    for threshold in THRESHOLDS
                },
                "union_by_threshold": {
                    str(threshold): len(base | challenger_by_threshold[threshold])
                    for threshold in THRESHOLDS
                },
            },
        }
        lock_path = run_dir / "prediction_lock.json"
        if lock_path.exists():
            raise SystemExit(f"refusing to overwrite lock: {lock_path}")
        lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        locks[run] = lock
        challenger_by_run[run] = challenger_by_threshold

    input_rows = load_jsonl(args.input)
    truth_rows = load_jsonl(args.truth)
    all_ids = {str(row["id"]) for row in input_rows}
    truth = {str(row["id"]): int(row["is_issue"]) for row in truth_rows}
    positive = {item_id for item_id, value in truth.items() if value == 1}
    if len(all_ids) != 102 or set(truth) != all_ids or len(positive) != 51:
        raise SystemExit("unexpected ACEBench 102 truth shape")

    base_metrics = metrics(base, positive, all_ids)
    runs: dict[str, Any] = {}
    for run, challenger_by_threshold in challenger_by_run.items():
        runs[run] = {
            "by_threshold": {
                str(threshold): {
                    "challenger_only": metrics(
                        challenger_by_threshold[threshold], positive, all_ids
                    ),
                    "fixed_union": metrics(
                        base | challenger_by_threshold[threshold], positive, all_ids
                    ),
                }
                for threshold in THRESHOLDS
            },
            "prediction_lock_sha256": sha256_file(args.root / "runs" / run / "prediction_lock.json"),
            "llm_usage": load_json(args.root / "runs" / run / "run_receipt.json")["llm_usage"],
        }

    summary_by_threshold: dict[str, Any] = {}
    decisions_by_threshold: dict[str, Any] = {}
    for threshold in THRESHOLDS:
        key = str(threshold)
        unions = [
            runs[f"challenger_r{i}"]["by_threshold"][key]["fixed_union"]
            for i in (1, 2, 3)
        ]
        summary = {
            "median_tp": median([row["confusion_matrix"]["tp"] for row in unions]),
            "median_fp": median([row["confusion_matrix"]["fp"] for row in unions]),
            "median_precision": median([row["metrics"]["precision"] for row in unions]),
            "median_recall": median([row["metrics"]["recall"] for row in unions]),
            "median_f1": median([row["metrics"]["f1"] for row in unions]),
        }
        tp_delta = summary["median_tp"] - base_metrics["confusion_matrix"]["tp"]
        summary_by_threshold[key] = summary
        decisions_by_threshold[key] = {
            "median_tp_delta_vs_baseline": tp_delta,
            "development_gain_gate_passed": (
                tp_delta >= 5 and summary["median_f1"] > base_metrics["metrics"]["f1"]
            ),
            "exceeds_reported_agentsuite_all_three_metrics": (
                summary["median_precision"] > 0.865
                and summary["median_recall"] > 0.882
                and summary["median_f1"] > 0.874
            ),
        }
    best_threshold = max(
        THRESHOLDS,
        key=lambda value: (summary_by_threshold[str(value)]["median_f1"], value),
    )
    result = {
        "schema_version": 1,
        "status": "POST_LABEL_DEV_CHALLENGER_SCORED_AFTER_THREE_LOCKS",
        "scope_warning": "same ACEBench labels used for iterative development; not generalization evidence",
        "baseline": base_metrics,
        "runs": runs,
        "union_median_by_threshold": summary_by_threshold,
        "decision": {
            "primary_benchguard_style_threshold": 0.8,
            "by_threshold": decisions_by_threshold,
            "development_best_threshold_by_median_f1": best_threshold,
            "confidence_semantics": (
                "self-reported ranking/acceptance signal only; every LLM-only "
                "finding remains review regardless of threshold"
            ),
            "agentsuite_reference": {"precision": 0.865, "recall": 0.882, "f1": 0.874},
        },
        "truth_sha256": sha256_file(args.truth),
    }
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite scoring output: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "union_median_by_threshold": summary_by_threshold,
        "decision": result["decision"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
