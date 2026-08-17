#!/usr/bin/env python3
"""Score the locked five-run Fantastic Bugs GSM8K-997 stability study."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchcore.comparison import compute_item_risk_score


OLD_ROOT = REPO_ROOT / "reports/fantastic_bugs_gsm8k_997_20260813"
NEW_ROOT = REPO_ROOT / "reports/fantastic_bugs_gsm8k_997_n5_20260816"
TRUTH_SHA256 = "9592a7d9677766255e4f34d3508b952498a0287157c3bb99df81512f7f30806b"
OLD_REPORT_HASHES = {
    1: "6673f506fcf5b03737818ac386e949bc911d9410cd9ee690ec42c20dc962bddb",
    2: "2466a8a789307bbe734868a57b312a0c1ebe3a54cbb9feac3d712fab354bc16e",
}
OLD_LOCK_SHA256 = "6f8f790289357f95acf436d8e5ac6947aa2a51f5eb03360ef9469c3b15019339"


class ScoringError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ScoringError(f"expected JSON object: {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def eligible_semantic(row: dict[str, Any]) -> bool:
    return (
        str(row.get("detection_method", "")).startswith("llm_")
        and row.get("defect_scope", "substantive") not in {"presentation", "operational"}
        and row.get("defect_type") != "llm_audit_failure"
    )


def semantic_map(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report.get("violations", []):
        if eligible_semantic(row):
            result[str(row["item_id"])].append(row)
    return dict(result)


def semantic_finding_keys(
    mapping: dict[str, list[dict[str, Any]]]
) -> set[tuple[str, str, str]]:
    return {
        (item_id, str(row["detection_method"]), str(row["defect_type"]))
        for item_id, rows in mapping.items()
        for row in rows
    }


def jaccard(left: set[Any], right: set[Any]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        rank = (cursor + end - 1) / 2 + 1
        for position in range(cursor, end):
            ranks[order[position]] = rank
        cursor = end
    return ranks


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or not left:
        raise ValueError("Pearson inputs must have equal nonzero length")
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_ss = sum((x - left_mean) ** 2 for x in left)
    right_ss = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_ss * right_ss)
    return numerator / denominator if denominator else None


def spearman_tie_aware(left: list[float], right: list[float]) -> float | None:
    return pearson(average_ranks(left), average_ranks(right))


def kendall_tau_b(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or not left:
        raise ValueError("Kendall inputs must have equal nonzero length")
    concordant = discordant = tie_left = tie_right = 0
    for first, second in itertools.combinations(range(len(left)), 2):
        dx = (left[first] > left[second]) - (left[first] < left[second])
        dy = (right[first] > right[second]) - (right[first] < right[second])
        if dx == 0 and dy == 0:
            continue
        if dx == 0:
            tie_left += 1
        elif dy == 0:
            tie_right += 1
        elif dx == dy:
            concordant += 1
        else:
            discordant += 1
    denominator = math.sqrt(
        (concordant + discordant + tie_left)
        * (concordant + discordant + tie_right)
    )
    return (concordant - discordant) / denominator if denominator else None


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0:
        raise ValueError("Wilson total must be positive")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    half = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return [center - half, center + half]


def distribution(values: list[float]) -> dict[str, float]:
    median = statistics.median(values)
    return {
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "median": median,
        "mean": statistics.fmean(values),
        "sample_sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "median_absolute_deviation": statistics.median(
            [abs(value - median) for value in values]
        ),
    }


def pairwise_values(rows: Iterable[dict[str, Any]], field: str) -> list[float]:
    return [float(row[field]) for row in rows]


def verify_prediction_lock(lock_path: Path, freeze_receipt_path: Path) -> dict[int, Path]:
    lock = load_json(lock_path)
    if lock.get("status") != "PREDICTIONS_LOCKED_BEFORE_N5_SCORING":
        raise ScoringError("supplemental prediction lock has the wrong status")
    old_lock = lock.get("old_prediction_lock", {})
    if old_lock.get("sha256") != OLD_LOCK_SHA256:
        raise ScoringError("old prediction lock binding mismatch")
    if sha256_file(OLD_ROOT / "final_prediction_lock.json") != OLD_LOCK_SHA256:
        raise ScoringError("old prediction lock bytes changed")
    freeze_binding = lock.get("freeze_receipt", {})
    if freeze_binding.get("sha256") != sha256_file(freeze_receipt_path):
        raise ScoringError("freeze receipt binding mismatch")

    paths: dict[int, Path] = {}
    rows = lock.get("new_runs", [])
    if [row.get("run") for row in rows] != [3, 4, 5]:
        raise ScoringError("prediction lock must contain Runs 3, 4, and 5 exactly")
    for row in rows:
        run_number = int(row["run"])
        report_path = NEW_ROOT / f"complete_run{run_number}/report.json"
        cache_path = NEW_ROOT / f"complete_run{run_number}/cache.jsonl"
        if sha256_file(report_path) != row.get("report_sha256"):
            raise ScoringError(f"Run {run_number} report changed after locking")
        if sha256_file(cache_path) != row.get("cache_sha256"):
            raise ScoringError(f"Run {run_number} cache changed after locking")
        paths[run_number] = report_path
    return paths


def summarize_run(
    report: dict[str, Any], all_ids: list[str], truth: set[str], run_number: int
) -> dict[str, Any]:
    mapping = semantic_map(report)
    candidate_set = set(mapping)
    scores = {
        item_id: compute_item_risk_score(mapping.get(item_id, [])) for item_id in all_ids
    }
    ranking = sorted(all_ids, key=lambda item_id: (-scores[item_id], item_id))
    top50 = ranking[:50]
    top50_tp = set(top50) & truth
    llm = report["run_metadata"]["llm"]
    return {
        "run": run_number,
        "candidate_items": sorted(candidate_set),
        "candidate_count": len(candidate_set),
        "finding_keys": sorted(semantic_finding_keys(mapping)),
        "finding_key_count": len(semantic_finding_keys(mapping)),
        "scores": scores,
        "top50_items": top50,
        "top50_tp_items": sorted(top50_tp),
        "top50_tp": len(top50_tp),
        "precision_at_50": len(top50_tp) / 50,
        "conditional_wilson_95": wilson_interval(len(top50_tp), 50),
        "operational_affected_items": int(
            report.get("summary", {}).get("operational_affected_items", 0)
        ),
        "api_attempts": int(llm["api_attempts"]),
        "prompt_tokens": int(llm["prompt_tokens"]),
        "completion_tokens": int(llm["completion_tokens"]),
        "total_tokens": int(llm["total_tokens"]),
        "provider_model_field": llm.get("model"),
        "started_at_utc": report["run_metadata"].get("started_at_utc"),
        "finished_at_utc": report["run_metadata"].get("finished_at_utc"),
    }


def prospective_decision(new_runs: list[dict[str, Any]]) -> dict[str, Any]:
    counts = [int(row["top50_tp"]) for row in new_runs]
    count_range = max(counts) - min(counts)
    if count_range >= 3:
        status = "REPLICATION_SUPPORTS_MATERIAL_TOP50_VARIABILITY"
    else:
        status = "NO_BROAD_STABILITY_CLAIM_FROM_THIS_PILOT"
    return {
        "status": status,
        "rule_frozen_before_run3": (
            "support requires a prospective Run3-Run5 Top-50 TP range of at least "
            "3 items (6 percentage points); otherwise Fantastic Bugs alone is not "
            "used for a broad stability headline"
        ),
        "run3_run5_top50_tp_range": count_range,
        "run3_run5_p_at_50_range": count_range / 50,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prediction-lock", type=Path, default=NEW_ROOT / "supplemental_prediction_lock.json"
    )
    parser.add_argument(
        "--freeze-receipt", type=Path, default=NEW_ROOT / "freeze_receipt.json"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    new_paths = verify_prediction_lock(
        args.prediction_lock.resolve(), args.freeze_receipt.resolve()
    )
    truth_path = OLD_ROOT / "materialized/sealed_truth.jsonl"
    if sha256_file(truth_path) != TRUTH_SHA256:
        raise ScoringError("sealed truth changed")
    truth_rows = load_jsonl(truth_path)
    all_ids = sorted(str(row["id"]) for row in truth_rows)
    truth = {str(row["id"]) for row in truth_rows if row["platinum_label"] == "invalid"}
    if len(all_ids) != 997 or len(set(all_ids)) != 997 or len(truth) != 88:
        raise ScoringError("unexpected truth shape")

    reports: dict[int, dict[str, Any]] = {}
    for run_number, expected in OLD_REPORT_HASHES.items():
        path = OLD_ROOT / f"complete_run{run_number}/report.json"
        if sha256_file(path) != expected:
            raise ScoringError(f"old Run {run_number} report changed")
        reports[run_number] = load_json(path)
    for run_number, path in new_paths.items():
        reports[run_number] = load_json(path)

    methods = [reports[n].get("methods_run") for n in range(1, 6)]
    if any(value != methods[0] for value in methods[1:]):
        raise ScoringError("methods_run differs across the five runs")

    runs = [summarize_run(reports[n], all_ids, truth, n) for n in range(1, 6)]
    pairwise: list[dict[str, Any]] = []
    for left_number, right_number in itertools.combinations(range(1, 6), 2):
        left = runs[left_number - 1]
        right = runs[right_number - 1]
        left_scores = [float(left["scores"][item_id]) for item_id in all_ids]
        right_scores = [float(right["scores"][item_id]) for item_id in all_ids]
        pairwise.append(
            {
                "left_run": left_number,
                "right_run": right_number,
                "candidate_item_jaccard": jaccard(
                    set(left["candidate_items"]), set(right["candidate_items"])
                ),
                "finding_key_jaccard": jaccard(
                    {tuple(row) for row in left["finding_keys"]},
                    {tuple(row) for row in right["finding_keys"]},
                ),
                "top50_item_jaccard": jaccard(
                    set(left["top50_items"]), set(right["top50_items"])
                ),
                "top50_true_positive_jaccard": jaccard(
                    set(left["top50_tp_items"]), set(right["top50_tp_items"])
                ),
                "risk_score_spearman_tie_aware": spearman_tie_aware(
                    left_scores, right_scores
                ),
                "risk_score_kendall_tau_b": kendall_tau_b(left_scores, right_scores),
                "absolute_top50_tp_difference": abs(
                    int(left["top50_tp"]) - int(right["top50_tp"])
                ),
            }
        )

    compact_runs = [
        {key: value for key, value in row.items() if key not in {"scores", "finding_keys"}}
        for row in runs
    ]
    top50_values = [float(row["precision_at_50"]) for row in runs]
    result = {
        "schema_version": "fantastic-bugs-gsm997-n5-stability-v1",
        "status": "SCORED_AFTER_SUPPLEMENTAL_PREDICTION_LOCK",
        "interpretation_scope": (
            "end-to-end operational reproducibility of the pinned public model alias; "
            "not pure sampling variance unless the provider revision is independently pinned"
        ),
        "truth": {"items": 997, "invalid": 88, "valid": 909},
        "runs": compact_runs,
        "p_at_50_distribution": distribution(top50_values),
        "top50_tp_count_distribution": distribution(
            [float(row["top50_tp"]) for row in runs]
        ),
        "pairwise": pairwise,
        "pairwise_descriptive_distributions": {
            field: distribution(pairwise_values(pairwise, field))
            for field in (
                "candidate_item_jaccard",
                "finding_key_jaccard",
                "top50_item_jaccard",
                "top50_true_positive_jaccard",
                "risk_score_spearman_tie_aware",
                "risk_score_kendall_tau_b",
                "absolute_top50_tp_difference",
            )
        },
        "prospective_run3_run5_decision": prospective_decision(runs[2:]),
        "statistical_boundary": (
            "The ten pairwise comparisons share runs and are descriptive, not ten "
            "independent observations. Per-run Wilson intervals are conditional Top-50 "
            "binomial intervals and do not estimate across-run variability."
        ),
        "bindings": {
            "prediction_lock_sha256": sha256_file(args.prediction_lock.resolve()),
            "freeze_receipt_sha256": sha256_file(args.freeze_receipt.resolve()),
            "truth_sha256": TRUTH_SHA256,
            "old_report_sha256": OLD_REPORT_HASHES,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "p_at_50": [row["precision_at_50"] for row in compact_runs],
                "decision": result["prospective_run3_run5_decision"],
                "output_sha256": sha256_file(args.out),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScoringError as exc:
        raise SystemExit(f"FAIL_CLOSED: {exc}") from exc
