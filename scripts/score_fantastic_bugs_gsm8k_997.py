#!/usr/bin/env python3
"""Score locked Fantastic Bugs GSM8K-997 predictions against sealed truth."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchcore.comparison import compute_item_risk_score


EXPECTED = {
    "truth": "9592a7d9677766255e4f34d3508b952498a0287157c3bb99df81512f7f30806b",
    "static": "a52ab2ff36c8f1b9cf6a302bbd3a788a6dd3bd3a835c6d8f5e7662c6449508c1",
    "response": "c443afba1c6181ef7a2edf014fe2db8113f605200fb43cb161739261be7c80ad",
    "run1": "6673f506fcf5b03737818ac386e949bc911d9410cd9ee690ec42c20dc962bddb",
    "run2": "2466a8a789307bbe734868a57b312a0c1ebe3a54cbb9feac3d712fab354bc16e",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path, expected: str) -> Any:
    actual = sha256_file(path)
    if actual != expected:
        raise SystemExit(f"hash mismatch for {path}: expected {expected}, got {actual}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path, expected: str) -> list[dict[str, Any]]:
    actual = sha256_file(path)
    if actual != expected:
        raise SystemExit(f"hash mismatch for {path}: expected {expected}, got {actual}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def eligible_finding(row: dict[str, Any]) -> bool:
    return (
        row.get("defect_scope", "substantive") not in {"presentation", "operational"}
        and row.get("defect_type") != "llm_audit_failure"
    )


def is_llm(row: dict[str, Any]) -> bool:
    return str(row.get("detection_method", "")).startswith("llm_")


def findings_by_item(report: dict[str, Any], mode: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report.get("violations", []):
        if not eligible_finding(row):
            continue
        if mode == "llm" and not is_llm(row):
            continue
        if mode == "static" and is_llm(row):
            continue
        result[str(row["item_id"])].append(row)
    return dict(result)


def metrics(predictions: set[str], truth: set[str]) -> dict[str, Any]:
    tp = predictions & truth
    fp = predictions - truth
    fn = truth - predictions
    precision = len(tp) / len(predictions) if predictions else 0.0
    recall = len(tp) / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "candidates": len(predictions),
        "tp": len(tp),
        "fp": len(fp),
        "fn": len(fn),
        "precision": precision,
        "recall_sensitivity": recall,
        "f1": f1,
        "tp_items": sorted(tp),
    }


def ranked_metrics(ranking: list[str], truth: set[str], *, k: int = 50) -> dict[str, Any]:
    if len(ranking) < k:
        return {
            "identifiable": False,
            "reason": f"only {len(ranking)} scored candidates, fewer than k={k}",
        }
    top = ranking[:k]
    tp = set(top) & truth
    return {
        "identifiable": True,
        "k": k,
        "tp": len(tp),
        "precision_at_k": len(tp) / k,
        "sensitivity_at_k": len(tp) / len(truth),
        "top_k_items": top,
        "top_k_tp_items": sorted(tp),
    }


def average_percentiles(values: dict[str, float]) -> dict[str, float]:
    if len(values) <= 1:
        return {key: 0.0 for key in values}
    groups: dict[float, list[str]] = defaultdict(list)
    for key, value in values.items():
        if not math.isfinite(value):
            raise ValueError(f"nonfinite score for {key}")
        groups[value].append(key)
    out: dict[str, float] = {}
    before = 0
    denominator = len(values) - 1
    for value in sorted(groups):
        members = groups[value]
        percentile = (before + (len(members) - 1) / 2) / denominator
        for key in members:
            out[key] = percentile
        before += len(members)
    return out


def jaccard(left: set[Any], right: set[Any]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()

    truth_rows = load_jsonl(root / "materialized/sealed_truth.jsonl", EXPECTED["truth"])
    truth = {row["id"] for row in truth_rows if row["platinum_label"] == "invalid"}
    all_ids = {row["id"] for row in truth_rows}
    if len(all_ids) != 997 or len(truth) != 88:
        raise SystemExit(f"unexpected truth shape: {len(all_ids)} items / {len(truth)} invalid")
    static_report = load_json(root / "predictions/benchaudit_static.json", EXPECTED["static"])
    response = load_json(
        root / "predictions/fantastic_bugs_official_baseline.json", EXPECTED["response"]
    )
    run1 = load_json(root / "complete_run1/report.json", EXPECTED["run1"])
    run2 = load_json(root / "complete_run2/report.json", EXPECTED["run2"])
    if run1["methods_run"] != run2["methods_run"]:
        raise SystemExit("run methods differ")

    static_map = findings_by_item(static_report, "static")
    static_candidates = set(static_map)
    response_rows = response["items"]
    if {row["item_id"] for row in response_rows} != all_ids:
        raise SystemExit("response baseline ID set differs from truth")
    response_candidates = {
        row["item_id"] for row in response_rows if int(row["majority_vote"]) == 0
    }
    response_ranking = [row["item_id"] for row in response_rows]

    methods: dict[str, dict[str, Any]] = {}
    static_ranking = [
        item_id
        for item_id, _ in sorted(
            ((item_id, compute_item_risk_score(rows)) for item_id, rows in static_map.items()),
            key=lambda pair: (-pair[1], pair[0]),
        )
    ]
    methods["static"] = {
        "candidate_metrics": metrics(static_candidates, truth),
        "top50": ranked_metrics(static_ranking, truth),
    }
    methods["response_baseline"] = {
        "candidate_metrics": metrics(response_candidates, truth),
        "top50": ranked_metrics(response_ranking, truth),
    }

    run_components: dict[str, dict[str, set[str]]] = {}
    for run_name, report in (("run1", run1), ("run2", run2)):
        llm_map = findings_by_item(report, "llm")
        audit_map = findings_by_item(report, "all")
        llm_candidates = set(llm_map)
        audit_candidates = set(audit_map)
        llm_ranking = [
            item_id
            for item_id, _ in sorted(
                ((item_id, compute_item_risk_score(rows)) for item_id, rows in llm_map.items()),
                key=lambda pair: (-pair[1], pair[0]),
            )
        ]
        methods[f"semantic_{run_name}"] = {
            "candidate_metrics": metrics(llm_candidates, truth),
            "top50": ranked_metrics(llm_ranking, truth),
        }

        audit_scores = {
            item_id: compute_item_risk_score(audit_map.get(item_id, [])) for item_id in all_ids
        }
        response_scores = {row["item_id"]: -float(row["gr_mean"]) for row in response_rows}
        audit_pct = average_percentiles(audit_scores)
        response_pct = average_percentiles(response_scores)
        combined_scores = {
            item_id: 0.5 * audit_pct[item_id] + 0.5 * response_pct[item_id]
            for item_id in all_ids
        }
        combined_ranking = [
            item_id
            for item_id, _ in sorted(
                combined_scores.items(), key=lambda pair: (-pair[1], pair[0])
            )
        ]
        combined_candidates = audit_candidates | response_candidates
        methods[f"combined_{run_name}"] = {
            "candidate_metrics": metrics(combined_candidates, truth),
            "top50": ranked_metrics(combined_ranking, truth),
        }
        run_components[run_name] = {
            "static": static_candidates,
            "semantic": llm_candidates,
            "response_baseline": response_candidates,
            "combined": combined_candidates,
        }

    for run_name, components in run_components.items():
        for name, predictions in components.items():
            others = set().union(*(value for key, value in components.items() if key != name))
            unique = predictions & truth - others
            methods[
                name if name in {"static", "response_baseline"} else f"{name}_{run_name}"
            ].setdefault("strict_unique_tp", {})[run_name] = {
                "count": len(unique), "items": sorted(unique)
            }

        semantic_tp = components["semantic"] & truth
        response_tp = components["response_baseline"] & truth
        methods[f"semantic_{run_name}"]["incremental_tp_vs_response"] = {
            "count": len(semantic_tp - response_tp),
            "items": sorted(semantic_tp - response_tp),
        }
        methods["response_baseline"].setdefault("incremental_tp_vs_semantic", {})[
            run_name
        ] = {
            "count": len(response_tp - semantic_tp),
            "items": sorted(response_tp - semantic_tp),
        }
        combined_tp = components["combined"] & truth
        methods[f"combined_{run_name}"]["incremental_tp_from_union"] = {
            "beyond_response": len(combined_tp - response_tp),
            "beyond_semantic": len(combined_tp - semantic_tp),
        }

    llm1 = findings_by_item(run1, "llm")
    llm2 = findings_by_item(run2, "llm")
    finding1 = {
        (item, str(row["detection_method"]), str(row["defect_type"]))
        for item, rows in llm1.items() for row in rows
    }
    finding2 = {
        (item, str(row["detection_method"]), str(row["defect_type"]))
        for item, rows in llm2.items() for row in rows
    }

    # Current published DeepSeek v4-flash conservative all-cache-miss price:
    # CNY 1/M input tokens and CNY 2/M output tokens.  Provider usage is exact
    # for the two complete runs.  The abandoned preflight did not retain usage,
    # so it is estimated from the two complete runs' mean cost per attempt.
    usage = {}
    complete_cost = 0.0
    complete_attempts = 0
    for run_name, report in (("run1", run1), ("run2", run2)):
        llm = report["run_metadata"]["llm"]
        cost = llm["prompt_tokens"] / 1_000_000 + 2 * llm["completion_tokens"] / 1_000_000
        usage[run_name] = {
            "api_attempts": llm["api_attempts"],
            "api_failures": llm["api_failures"],
            "prompt_tokens": llm["prompt_tokens"],
            "completion_tokens": llm["completion_tokens"],
            "total_tokens": llm["total_tokens"],
            "cost_cny_all_input_cache_miss": cost,
        }
        complete_cost += cost
        complete_attempts += llm["api_attempts"]
    failed_attempts = 6887
    failed_estimate = failed_attempts * complete_cost / complete_attempts

    result = {
        "schema_version": 1,
        "status": "SCORED_AFTER_PREDICTION_LOCK",
        "truth": {"items": 997, "invalid": 88, "valid": 909},
        "methods": methods,
        "stability": {
            "semantic_item_jaccard": jaccard(set(llm1), set(llm2)),
            "semantic_finding_jaccard": jaccard(finding1, finding2),
            "run1_semantic_items": len(llm1),
            "run2_semantic_items": len(llm2),
            "run1_finding_keys": len(finding1),
            "run2_finding_keys": len(finding2),
        },
        "cost": {
            "pricing": "CNY 1/M input cache-miss + CNY 2/M output",
            "complete_runs": usage,
            "complete_runs_cost_cny": complete_cost,
            "abandoned_capacity_preflight_api_attempts": failed_attempts,
            "abandoned_capacity_preflight_cost_cny_estimated": failed_estimate,
            "total_cost_cny_estimated": complete_cost + failed_estimate,
            "failed_preflight_cost_limitation": (
                "provider usage was not retained because no report was produced; estimate uses "
                "the two complete runs' mean all-cache-miss cost per API attempt"
            ),
        },
        "inputs": {key: value for key, value in EXPECTED.items()},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "methods": {
            name: {
                "candidate": value["candidate_metrics"],
                "top50": value["top50"],
            }
            for name, value in methods.items()
        },
        "stability": result["stability"],
        "cost": result["cost"],
        "output_sha256": sha256_file(args.out),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
