#!/usr/bin/env python3
"""Lock and score the frozen ACEBench prompt-specialization A/B runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path
from typing import Any


ARMS = ("specialized", "generic")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


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


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    by_run: dict[str, set[str]] = {}
    route_by_id: dict[str, str] = {}
    usage: dict[str, Any] = {}
    operational_failures: dict[str, list[str]] = {}
    locks: dict[str, str] = {}

    # Prediction locks for every arm are written before truth is read below.
    for arm in ARMS:
        for repeat in (1, 2, 3):
            run = f"{arm}_r{repeat}"
            run_dir = args.root / "runs" / run
            prediction_path = run_dir / "predictions.jsonl"
            receipt_path = run_dir / "run_receipt.json"
            receipt = read_json(receipt_path)
            rows = read_jsonl(prediction_path)
            if sha256_file(prediction_path) != receipt.get("predictions_sha256"):
                raise SystemExit(f"{run}: prediction hash mismatch")
            if len(rows) != 102:
                raise SystemExit(f"{run}: incomplete run")
            failed_ids = sorted(
                str(row["item_id"])
                for row in rows
                if row.get("operational_error") is not None
            )
            if int(receipt.get("operational_failures", -1)) != len(failed_ids):
                raise SystemExit(f"{run}: operational-failure count mismatch")
            if receipt.get("arm") != arm or receipt.get("dry_run"):
                raise SystemExit(f"{run}: wrong arm or dry-run artifact")
            by_run[run] = {str(row["item_id"]) for row in rows if row.get("candidate") is True}
            for row in rows:
                old = route_by_id.setdefault(str(row["item_id"]), str(row["route"]))
                if old != row["route"]:
                    raise SystemExit(f"{run}: route drift for {row['item_id']}")
            usage[run] = receipt["llm_usage"]
            operational_failures[run] = failed_ids
            lock = {
                "schema_version": 1,
                "status": "PREDICTIONS_LOCKED_BEFORE_DEV_LABEL_JOIN",
                "scope": "post-label development comparison; not blind evidence",
                "run": run,
                "arm": arm,
                "prediction_count": len(by_run[run]),
                "predictions_sha256": sha256_file(prediction_path),
                "runner_receipt_sha256": sha256_file(receipt_path),
            }
            lock_path = run_dir / "prediction_lock.json"
            if lock_path.exists():
                raise SystemExit(f"refusing to overwrite prediction lock: {lock_path}")
            lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            locks[run] = sha256_file(lock_path)

    input_rows = read_jsonl(args.input)
    truth_rows = read_jsonl(args.truth)
    all_ids = {str(row["id"]) for row in input_rows}
    truth = {str(row["id"]): int(row["is_issue"]) for row in truth_rows}
    positive = {item_id for item_id, label in truth.items() if label == 1}
    if len(all_ids) != 102 or set(truth) != all_ids or len(positive) != 51:
        raise SystemExit("unexpected ACEBench truth shape")

    results: dict[str, Any] = {}
    candidates: dict[str, set[str]] = {}
    for run, predicted in by_run.items():
        candidates[run] = predicted
        overall = metrics(predicted, positive, all_ids)
        by_route: dict[str, Any] = {}
        for route in ("default", "agent", "special"):
            route_ids = {item_id for item_id in all_ids if route_by_id[item_id] == route}
            if route_ids:
                by_route[route] = metrics(predicted & route_ids, positive & route_ids, route_ids)
            else:
                by_route[route] = {"items": 0, "not_estimable": True}
        results[run] = {
            "overall": overall,
            "by_route": by_route,
            "llm_usage": usage[run],
            "operational_failure_count": len(operational_failures[run]),
            "operational_failure_ids": operational_failures[run],
            "prediction_lock_sha256": locks[run],
        }

    summary: dict[str, Any] = {}
    for arm in ARMS:
        arm_runs = [f"{arm}_r{i}" for i in (1, 2, 3)]
        arm_rows = [results[run]["overall"] for run in arm_runs]
        summary[arm] = {
            "median_candidates": median([row["candidates"] for row in arm_rows]),
            "median_tp": median([row["confusion_matrix"]["tp"] for row in arm_rows]),
            "median_fp": median([row["confusion_matrix"]["fp"] for row in arm_rows]),
            "median_precision": median([row["metrics"]["precision"] for row in arm_rows]),
            "median_recall": median([row["metrics"]["recall"] for row in arm_rows]),
            "median_f1": median([row["metrics"]["f1"] for row in arm_rows]),
            "median_operational_failures": median([
                results[run]["operational_failure_count"] for run in arm_runs
            ]),
            "total_operational_failures": sum(
                results[run]["operational_failure_count"] for run in arm_runs
            ),
            "pairwise_candidate_jaccard": {
                f"r{left}_r{right}": jaccard(candidates[f"{arm}_r{left}"], candidates[f"{arm}_r{right}"])
                for left, right in combinations((1, 2, 3), 2)
            },
        }

    s_tp = summary["specialized"]["median_tp"]
    g_tp = summary["generic"]["median_tp"]
    s_f1 = summary["specialized"]["median_f1"]
    g_f1 = summary["generic"]["median_f1"]
    pair_directions = [
        results[f"specialized_r{i}"]["overall"]["confusion_matrix"]["tp"]
        - results[f"generic_r{i}"]["overall"]["confusion_matrix"]["tp"]
        for i in (1, 2, 3)
    ]
    advantaged = "specialized" if s_tp > g_tp else "generic" if g_tp > s_tp else "tie"
    consistent = all(value > 0 for value in pair_directions) or all(value < 0 for value in pair_directions)
    f1_drop = 0.0
    if advantaged == "specialized":
        f1_drop = max(0.0, g_f1 - s_f1)
        operational_failure_increase = (
            summary["specialized"]["median_operational_failures"]
            > summary["generic"]["median_operational_failures"]
        )
    elif advantaged == "generic":
        f1_drop = max(0.0, s_f1 - g_f1)
        operational_failure_increase = (
            summary["generic"]["median_operational_failures"]
            > summary["specialized"]["median_operational_failures"]
        )
    else:
        operational_failure_increase = False

    output = {
        "schema_version": 1,
        "status": "POST_LABEL_DEV_PROMPT_SPECIALIZATION_AB_SCORED_AFTER_SIX_LOCKS",
        "scope_warning": "ACEBench labels were already known; development comparison only",
        "runs": results,
        "summary": summary,
        "comparison": {
            "median_tp_difference_specialized_minus_generic": s_tp - g_tp,
            "paired_tp_differences_specialized_minus_generic": pair_directions,
            "advantaged_arm": advantaged,
            "direction_consistent_across_paired_repeats": consistent,
            "predeclared_meaningful_gate_passed": (
                abs(s_tp - g_tp) >= 5
                and consistent
                and f1_drop <= 0.02
                and not operational_failure_increase
            ),
            "advantaged_arm_operational_failure_increase": operational_failure_increase,
            "agentsuite_reported_reference": {"precision": 0.865, "recall": 0.882, "f1": 0.874},
        },
        "truth_sha256": sha256_file(args.truth),
        "input_sha256": sha256_file(args.input),
    }
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite scoring output: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "comparison": output["comparison"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
