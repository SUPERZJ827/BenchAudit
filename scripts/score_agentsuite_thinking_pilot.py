#!/usr/bin/env python3
"""Lock one thinking-enabled ACEBench report, then score it against dev truth."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def candidate_ids(report: dict[str, Any]) -> set[str]:
    return {
        str(row["item_id"])
        for row in report.get("violations", [])
        if row.get("detection_method") == "llm_cross_artifact_consistency"
        and row.get("defect_scope", "substantive") not in {"presentation", "operational"}
        and row.get("defect_type") != "llm_audit_failure"
    }


def metrics(predicted: set[str], positive: set[str], all_ids: set[str]) -> dict[str, Any]:
    tp, fp = len(predicted & positive), len(predicted - positive)
    fn, tn = len(positive - predicted), len((all_ids - positive) - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "candidates": len(predicted),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "metrics": {"precision": precision, "recall": recall, "f1": f1},
        "tp_ids": sorted(predicted & positive),
        "fp_ids": sorted(predicted - positive),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    report = load_json(args.report)
    llm = report.get("run_metadata", {}).get("llm", {})
    if llm.get("model") != "deepseek-v4-flash" or llm.get("thinking") != "enabled":
        raise SystemExit("report is not the frozen thinking-enabled model arm")
    if int(llm.get("cache_entries", -1)) != 102 or int(llm.get("invalid_responses", -1)) != 0:
        raise SystemExit("expected 102 complete cache entries and zero invalid responses")
    if int(llm.get("api_attempts", -1)) + int(llm.get("cache_hits", -1)) != 102:
        raise SystemExit("expected api_attempts + cache_hits to equal 102")
    predicted = candidate_ids(report)
    lock = {
        "schema_version": 1,
        "status": "THINKING_PILOT_PREDICTIONS_LOCKED_BEFORE_DEV_LABEL_JOIN",
        "scope_warning": "ACEBench labels already known; development pilot only",
        "report_sha256": sha256_file(args.report),
        "input_sha256": sha256_file(args.input),
        "config_sha256": sha256_file(args.config),
        "prediction_only_counts": {"candidates": len(predicted)},
        "llm_usage": llm,
        "usage_accounting_complete": int(llm.get("cache_hits", 0)) == 0,
    }
    if args.lock.exists():
        raise SystemExit(f"refusing to overwrite lock: {args.lock}")
    args.lock.parent.mkdir(parents=True, exist_ok=True)
    args.lock.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    all_ids = {str(row["id"]) for row in load_jsonl(args.input)}
    truth = {str(row["id"]): int(row["is_issue"]) for row in load_jsonl(args.truth)}
    positive = {item_id for item_id, label in truth.items() if label == 1}
    if len(all_ids) != 102 or set(truth) != all_ids or len(positive) != 51:
        raise SystemExit("unexpected ACEBench-102 truth shape")
    scored = metrics(predicted, positive, all_ids)
    tp = scored["confusion_matrix"]["tp"]
    fp = scored["confusion_matrix"]["fp"]
    f1 = scored["metrics"]["f1"]
    if tp >= 35 and f1 > 0.6818181818181819:
        outcome = "LARGE_GAIN_OBSERVED_REPEAT_REQUIRED"
    elif tp <= 30:
        outcome = "NO_GAIN_STOP_THINKING_ARM"
    else:
        outcome = "INCONCLUSIVE_WITHIN_EXISTING_VARIATION"
    result = {
        "schema_version": 1,
        "status": "THINKING_PILOT_SCORED_AFTER_PREDICTION_LOCK",
        "scope_warning": "single known-label development run; not a final A/B estimate",
        "disabled_a1_reference": {
            "runs": 2,
            "each": {"tp": 30, "fp": 7, "fn": 21, "precision": 0.8108108108108109, "recall": 0.5882352941176471, "f1": 0.6818181818181819},
        },
        "thinking_enabled": scored,
        "predeclared_outcome": outcome,
        "large_gain_gate": "TP >= 35 and F1 > disabled A1; if passed, run two more repeats",
        "prediction_lock_sha256": sha256_file(args.lock),
        "truth_sha256": sha256_file(args.truth),
        "llm_usage": llm,
        "usage_accounting_complete": int(llm.get("cache_hits", 0)) == 0,
    }
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite result: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
