#!/usr/bin/env python3
"""Analyze semantic findings only inside the official baseline's negative pool.

This is a post-result addendum, not a preregistered primary endpoint.  It reads
only hash-pinned prediction and truth artifacts from the completed GSM8K-997
experiment and makes no API calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchcore.comparison import compute_item_risk_score
from scripts import score_fantastic_bugs_gsm8k_997 as primary


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_residual(ranking: list[str], residual_truth: set[str]) -> dict[str, float | int]:
    candidate_metrics = primary.metrics(set(ranking), residual_truth)
    top50 = primary.ranked_metrics(ranking, residual_truth, k=50)
    return {
        "semantic_candidates": len(ranking),
        "tp": candidate_metrics["tp"],
        "fp": candidate_metrics["fp"],
        "fn": candidate_metrics["fn"],
        "precision": candidate_metrics["precision"],
        "recall_of_response_baseline_misses": candidate_metrics["recall_sensitivity"],
        "top50_tp": top50["tp"],
        "precision_at_50": top50["precision_at_k"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()

    truth_rows = primary.load_jsonl(
        root / "materialized/sealed_truth.jsonl", primary.EXPECTED["truth"]
    )
    truth = {row["id"] for row in truth_rows if row["platinum_label"] == "invalid"}
    response = primary.load_json(
        root / "predictions/fantastic_bugs_official_baseline.json",
        primary.EXPECTED["response"],
    )
    all_ids = {row["item_id"] for row in response["items"]}
    response_candidates = {
        row["item_id"] for row in response["items"] if int(row["majority_vote"]) == 0
    }
    residual_pool = all_ids - response_candidates
    residual_truth = truth - response_candidates

    runs = {}
    for run_name in ("run1", "run2"):
        report = primary.load_json(
            root / f"complete_{run_name}/report.json", primary.EXPECTED[run_name]
        )
        semantic = primary.findings_by_item(report, "llm")
        ranking = [
            item_id
            for item_id, _ in sorted(
                (
                    (item_id, compute_item_risk_score(rows))
                    for item_id, rows in semantic.items()
                    if item_id in residual_pool
                ),
                key=lambda pair: (-pair[1], pair[0]),
            )
        ]
        runs[run_name] = summarize_residual(ranking, residual_truth)

    result = {
        "schema_version": 1,
        "status": "POST_RESULT_RESIDUAL_POOL_ADDENDUM",
        "preregistered_primary_endpoint": False,
        "api_calls_made": 0,
        "pool": {
            "definition": "items where official majority_vote != 0",
            "items": len(residual_pool),
            "invalid": len(residual_truth),
        },
        "semantic_ranking": (
            "existing locked semantic candidates in residual pool, ordered by "
            "BenchAudit item risk descending and item_id ascending"
        ),
        "runs": runs,
        "inputs": dict(primary.EXPECTED),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"result": result, "output_sha256": sha256_file(args.out)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
