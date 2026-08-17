#!/usr/bin/env python3
"""Lock and score the minimal innocent-explanation ACEBench experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


METHOD = "llm_cross_artifact_consistency"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def predicted_ids(report: dict[str, Any]) -> set[str]:
    return {
        str(row["item_id"])
        for row in report.get("violations", [])
        if row.get("detection_method") == METHOD
        and row.get("defect_scope", "substantive") not in {"presentation", "operational"}
        and row.get("defect_type") != "llm_audit_failure"
    }


def metric_row(predicted: set[str], positive: set[str], all_ids: set[str]) -> dict[str, Any]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--historical-root", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    reports = {
        "baseline_r1": args.historical_root / "runs/a1_r1/report.json",
        "baseline_r2": args.historical_root / "runs/a1_r2/report.json",
        "baseline_r3": args.root / "runs/baseline_r3/report.json",
        "innocent_r1": args.root / "runs/innocent_r1/report.json",
        "innocent_r2": args.root / "runs/innocent_r2/report.json",
        "innocent_r3": args.root / "runs/innocent_r3/report.json",
    }
    existing_locks = {
        "baseline_r1": args.historical_root / "runs/a1_r1/prediction_lock.json",
        "baseline_r2": args.historical_root / "runs/a1_r2/prediction_lock.json",
    }

    # Lock every newly generated prediction before opening truth.
    locks: dict[str, dict[str, Any]] = {}
    for run, report_path in reports.items():
        report = load_json(report_path)
        predictions = predicted_ids(report)
        if run in existing_locks:
            lock_path = existing_locks[run]
            lock = load_json(lock_path)
            if sha256_file(report_path) != lock["prediction_report_sha256"]:
                raise SystemExit(f"{run}: historical report no longer matches its lock")
        else:
            run_dir = report_path.parent
            receipt_path = run_dir / "run_receipt.json"
            receipt = load_json(receipt_path)
            if sha256_file(report_path) != receipt["report_sha256"]:
                raise SystemExit(f"{run}: report no longer matches its runner receipt")
            lock = {
                "schema_version": 1,
                "status": "PREDICTIONS_LOCKED_BEFORE_DEV_LABEL_JOIN",
                "scope_warning": "labels were already known; this is a development diagnostic",
                "run": run,
                "arm": receipt["arm"],
                "prediction_report_sha256": sha256_file(report_path),
                "runner_receipt_sha256": sha256_file(receipt_path),
                "prompt_sha256": receipt["prompt_sha256"],
                "prediction_only_counts": {"candidates": len(predictions)},
            }
            lock_path = run_dir / "prediction_lock.json"
            if lock_path.exists():
                raise SystemExit(f"refusing to overwrite lock: {lock_path}")
            lock_path.write_text(
                json.dumps(lock, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        locks[run] = {**lock, "lock_path": str(lock_path)}

    truth_rows = load_jsonl(args.truth)
    input_rows = load_jsonl(args.input)
    all_ids = {str(row["id"]) for row in input_rows}
    truth = {str(row["id"]): int(row["is_issue"]) for row in truth_rows}
    if len(all_ids) != 102 or set(truth) != all_ids or sum(truth.values()) != 51:
        raise SystemExit("expected the frozen 102-item, 51/51 ACEBench development subset")
    positive = {item_id for item_id, label in truth.items() if label == 1}

    scored: dict[str, Any] = {}
    for run, report_path in reports.items():
        report = load_json(report_path)
        scored[run] = {
            **metric_row(predicted_ids(report), positive, all_ids),
            "report_sha256": sha256_file(report_path),
            "prediction_lock_sha256": sha256_file(Path(locks[run]["lock_path"])),
            "llm_usage": report.get("run_metadata", {}).get("llm", {}),
        }

    baseline_runs = [scored[f"baseline_r{i}"] for i in (1, 2, 3)]
    treatment_runs = [scored[f"innocent_r{i}"] for i in (1, 2, 3)]
    summary: dict[str, Any] = {}
    for name, rows in (("baseline", baseline_runs), ("innocent", treatment_runs)):
        summary[name] = {
            "median_tp": median([row["confusion_matrix"]["tp"] for row in rows]),
            "median_fp": median([row["confusion_matrix"]["fp"] for row in rows]),
            "median_precision": median([row["metrics"]["precision"] for row in rows]),
            "median_recall": median([row["metrics"]["recall"] for row in rows]),
            "median_f1": median([row["metrics"]["f1"] for row in rows]),
        }
    tp_delta = summary["innocent"]["median_tp"] - summary["baseline"]["median_tp"]
    precision_delta = summary["innocent"]["median_precision"] - summary["baseline"]["median_precision"]
    f1_delta = summary["innocent"]["median_f1"] - summary["baseline"]["median_f1"]
    if tp_delta >= 5 and precision_delta >= 0 and f1_delta >= 0:
        verdict = "CLEAR_WIN"
    elif tp_delta >= 5:
        verdict = "RECALL_GAIN_WITH_PRECISION_OR_F1_TRADEOFF"
    else:
        verdict = "NO_DISCERNIBLE_TP_GAIN_UNDER_PREDECLARED_GATE"

    result = {
        "schema_version": 1,
        "status": "POST_LABEL_DEV_AB_SCORED_AFTER_NEW_RUN_LOCKS",
        "scope": {
            "items": 102,
            "positive": 51,
            "negative": 51,
            "development_only": True,
            "warning": "labels and two historical baseline results were known before treatment runs",
        },
        "truth_sha256": sha256_file(args.truth),
        "runs": scored,
        "summary": summary,
        "predeclared_decision": {
            "median_tp_delta": tp_delta,
            "median_precision_delta": precision_delta,
            "median_f1_delta": f1_delta,
            "meaningful_tp_gate": 5,
            "verdict": verdict,
        },
    }
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite scoring output: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["predeclared_decision"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
