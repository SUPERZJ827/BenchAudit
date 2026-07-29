#!/usr/bin/env python3
"""Evaluate the frozen A-double-prime R2c+R2d point on internal10."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.analyze_workspace_a_double_prime import (  # noqa: E402
    Key,
    _a_prime_candidates,
    _dataset_by_id,
    _items_by_id,
    _reviewed_metrics,
    _rule_sets,
    collect_residue_observations,
    read_jsonl,
    sha256_file,
)
from scripts.analyze_workspace_a_prime import (  # noqa: E402
    _baseline_a_candidates,
    family_positive_keys,
)
from scripts.run_workspace_static_llm_ablation import (  # noqa: E402
    _read_completed_items,
    parse_reviewed_reference,
)


PROTOCOL = "workspace-grounding-a-double-prime-internal10-v1-20260729"
SELECTED_RULE_IDS = ("R2c", "R2d")
FROZEN_REPO_INPUTS = {
    "experiments/workspace_grounding/A_DOUBLE_PRIME_INTERNAL10_PROTOCOL_20260729.md":
        "5d9bf989dd560eeedc072329486124fb5537864219f3c62ee2982a33fc2f4e85",
    "experiments/workspace_grounding/A_PRIME_INTERNAL_VALIDATION_10_20260729.json":
        "8af94ea6a23663654bec21e115928f6a7d5b30b86d1912e6992e9a5d24325515",
    "configs/llm_deepseek_workspace_a_prime_internal_validation.json":
        "f6542eb4dd7c326f22c5fe109575258b8ba48f57a75493a66ddc0861948bad86",
    "benchcore/workspace_constraint_residue.py":
        "aa0f09461a0414466259d9f37e5512c9226c5918578f5b167159dc84411c0b34",
    "benchcore/workspace_grounding.py":
        "0f64ce1d7050b16f0596c2e4cae2772b380b6ebb6337dd983d1b4c9fa126592a",
    "scripts/run_workspace_static_llm_ablation.py":
        "e941aa57953a693d94d9be12844a66fa45c6aa6bc753dc01ca17cc972b3566e2",
}
FROZEN_ARTIFACT_INPUTS = {
    "datasets/workspacebench/full.jsonl":
        "2e3d8fd1f5a741b9e6b73ebab9ce23e26ce054527b4f3477de8fdd950aad9dbe",
    (
        "reports/workspace_grounding_dual_triage_holdout30_20260728/"
        "grounding_dual_triage_items.jsonl"
    ): "2562ca10533e8f1a0a87080eed306fcf19389039ed7172ac7f04c1c197f9a50e",
    "WorkspaceBench_full388_Codex证据化逐条标注_20260720.md":
        "fa8fbef8497ac2f8f39b21975e28dd88005a5d2541db07cbe162fb04558978cf",
    "reports/workspace_p0_blind_adjudication_20260728/SEALED_MAPPING.json":
        "18232ed0e0e65e9215dd51c857c34b560512d59be51d74b89b1c3efad4619ee9",
    (
        "reports/workspace_p0_blind_adjudication_20260728/"
        "GEMINI_3_1_PRO_INDEPENDENT_ANNOTATIONS.jsonl"
    ): "b091fae11b9ecbd2bffc826c4cf60615e15c39357b700abdf3c9510daa3b8e62",
}


def verify_frozen_inputs(
    *,
    repo_root: Path,
    artifact_root: Path,
) -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in FROZEN_REPO_INPUTS.items():
        path = repo_root / relative
        if not path.is_file():
            raise ValueError(f"frozen repo input is missing: {relative}")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                f"frozen repo input hash mismatch: {relative}: {actual}"
            )
        observed[f"repo:{relative}"] = actual
    for relative, expected in FROZEN_ARTIFACT_INPUTS.items():
        path = artifact_root / relative
        if not path.is_file():
            raise ValueError(f"frozen artifact input is missing: {relative}")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                f"frozen artifact input hash mismatch: {relative}: {actual}"
            )
        observed[f"artifact:{relative}"] = actual
    return dict(sorted(observed.items()))


def evaluate_internal(
    *,
    a_prime_candidates: set[Key],
    old_a_candidates: set[Key],
    rule_sets: Mapping[str, set[Key]],
    family_positives: set[Key],
    reviewed_labels: Mapping[Key, str],
    expected_items: set[str],
    rubric_count: int,
    router_calls: int,
    review_ceiling_escape: int,
    operational_unknown_tasks: list[str],
) -> dict[str, Any]:
    rule_union = set().union(
        *(rule_sets.get(rule_id, set()) for rule_id in SELECTED_RULE_IDS)
    )
    candidates = a_prime_candidates | rule_union
    family_hits = len(candidates & family_positives)
    logical_calls = router_calls + len(candidates)
    old_logical_calls = router_calls + len(old_a_candidates)
    reviewed = _reviewed_metrics(
        candidates, reviewed_labels, expected_items,
    )
    old_reviewed = _reviewed_metrics(
        old_a_candidates, reviewed_labels, expected_items,
    )
    gate = {
        "family_hits_at_least_6_of_7": (
            len(family_positives) == 7 and family_hits >= 6
        ),
        "candidate_count_at_most_118": len(candidates) <= 118,
        "candidate_rate_at_most_118_of_204": (
            rubric_count == 204 and len(candidates) / rubric_count <= 118 / 204
        ),
        "logical_calls_at_most_128": logical_calls <= 128,
        "review_ceiling_escape_zero": review_ceiling_escape == 0,
        "operational_unknown_zero": not operational_unknown_tasks,
        "fixed_working_point": tuple(SELECTED_RULE_IDS) == ("R2c", "R2d"),
    }
    return {
        "selected_rule_ids": list(SELECTED_RULE_IDS),
        "counts": {
            "tasks": len(expected_items),
            "rubrics": rubric_count,
            "a_prime_candidates": len(a_prime_candidates),
            "old_a_candidates": len(old_a_candidates),
            "rule_union_triggers": len(rule_union),
            "incremental_candidates_vs_a_prime": len(
                rule_union - a_prime_candidates
            ),
            "candidates": len(candidates),
            "family_positives": len(family_positives),
            "family_hits": family_hits,
        },
        "candidate_rate": (
            len(candidates) / rubric_count if rubric_count else 0.0
        ),
        "family_recall": (
            family_hits / len(family_positives)
            if family_positives else 0.0
        ),
        "logical_calls": logical_calls,
        "old_a_logical_calls": old_logical_calls,
        "logical_call_reduction_vs_old_a": (
            1.0 - logical_calls / old_logical_calls
            if old_logical_calls else 0.0
        ),
        "reviewed": reviewed,
        "old_a_reviewed": old_reviewed,
        "rule_trigger_counts": {
            rule_id: len(rule_sets.get(rule_id, set()))
            for rule_id in SELECTED_RULE_IDS
        },
        "rule_target_hits": {
            rule_id: len(rule_sets.get(rule_id, set()) & family_positives)
            for rule_id in SELECTED_RULE_IDS
        },
        "review_ceiling_escape": review_ceiling_escape,
        "operational_unknown_tasks": sorted(operational_unknown_tasks),
        "gate": gate,
        "decision": "PASS" if all(gate.values()) else "FAIL",
    }


def validate_runtime(
    *,
    provenance: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    grounding = runtime.get("grounding")
    llm = grounding.get("llm") if isinstance(grounding, dict) else None
    checks = {
        "manifest_hash_matches": provenance.get(
            "item_ids_manifest_sha256"
        ) == FROZEN_REPO_INPUTS[
            "experiments/workspace_grounding/"
            "A_PRIME_INTERNAL_VALIDATION_10_20260729.json"
        ],
        "dataset_hash_matches": provenance.get(
            "dataset_sha256"
        ) == FROZEN_ARTIFACT_INPUTS["datasets/workspacebench/full.jsonl"],
        "strategy_matches": (
            provenance.get("grounding_strategy")
            == "item-structured-triage"
        ),
        "routing_only": provenance.get("grounding_routing_only") is True,
        "raw_threshold_preserved": (
            float(provenance.get("structured_min_confidence") or 0.0) == 0.0
        ),
        "workers_at_most_4": int(provenance.get("workers") or 0) <= 4,
        "runtime_present": isinstance(grounding, dict) and isinstance(llm, dict),
        "api_attempts_at_most_10": (
            isinstance(llm, dict) and int(llm.get("api_attempts") or 0) <= 10
        ),
        "api_failures_zero": (
            isinstance(llm, dict) and int(llm.get("api_failures") or 0) == 0
        ),
        "api_successes_10": (
            isinstance(llm, dict) and int(llm.get("api_successes") or 0) == 10
        ),
        "total_tokens_at_most_200000": (
            isinstance(llm, dict)
            and int(llm.get("total_tokens") or 0) <= 200_000
        ),
        "verifier_disabled": (
            isinstance(grounding, dict)
            and grounding.get("verify_unsupported") is False
        ),
    }
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise ValueError(f"internal10 runtime contract failed: {failed}")
    return {
        "checks": checks,
        "api_attempts": int(llm.get("api_attempts") or 0),
        "api_successes": int(llm.get("api_successes") or 0),
        "api_failures": int(llm.get("api_failures") or 0),
        "prompt_tokens": int(llm.get("prompt_tokens") or 0),
        "completion_tokens": int(llm.get("completion_tokens") or 0),
        "total_tokens": int(llm.get("total_tokens") or 0),
    }


def analyze_internal(
    *,
    items: Mapping[str, Mapping[str, Any]],
    dataset: Mapping[str, Mapping[str, Any]],
    baseline_rows: Mapping[str, Mapping[str, Any]],
    family_positives: set[Key],
    reviewed_labels: Mapping[Key, str],
) -> tuple[dict[str, Any], list[Any], list[dict[str, Any]]]:
    expected_items = set(items)
    a_prime, rubric_count, baseline_unknown = _a_prime_candidates(items)
    old_a = _baseline_a_candidates(dict(baseline_rows))
    if (len(expected_items), rubric_count, len(old_a)) != (10, 204, 118):
        raise ValueError(
            "internal10 baseline no longer matches frozen 10/204/118"
        )
    if len(family_positives) != 7:
        raise ValueError("internal10 family universe no longer contains 7 rows")
    observations, diagnostics, decomposition, residue_unknown = (
        collect_residue_observations(items=items, dataset=dataset)
    )
    review_ceiling_escape = sum(
        int(not row.review_only or row.confirmation_eligible)
        for row in observations
    )
    result = evaluate_internal(
        a_prime_candidates=a_prime,
        old_a_candidates=old_a,
        rule_sets=_rule_sets(observations),
        family_positives=family_positives,
        reviewed_labels=reviewed_labels,
        expected_items=expected_items,
        rubric_count=rubric_count,
        router_calls=10,
        review_ceiling_escape=review_ceiling_escape,
        operational_unknown_tasks=sorted(
            set(baseline_unknown) | set(residue_unknown)
        ),
    )
    result.update({
        "protocol": PROTOCOL,
        "decomposition": decomposition,
        "h1": {
            "status_counts": {
                status: sum(
                    int(row.get("status") == status) for row in diagnostics
                )
                for status in ("valid", "invalid", "unknown")
            },
            "diagnostics": len(diagnostics),
        },
    })
    return result, observations, diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--a-prime-results-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    frozen_hashes = verify_frozen_inputs(
        repo_root=REPO,
        artifact_root=args.artifact_root,
    )
    if args.preflight_only:
        print(json.dumps(
            {"protocol": PROTOCOL, "frozen_input_sha256": frozen_hashes},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ))
        return
    if args.a_prime_results_dir is None or args.output_dir is None:
        raise ValueError(
            "--a-prime-results-dir and --output-dir are required after preflight"
        )

    manifest = json.loads((
        REPO
        / "experiments/workspace_grounding/"
        "A_PRIME_INTERNAL_VALIDATION_10_20260729.json"
    ).read_text(encoding="utf-8"))
    expected_items = {str(value) for value in manifest["item_ids"]}
    items_path = (
        args.a_prime_results_dir
        / "grounding_item_structured_triage_items.jsonl"
    )
    cache_path = (
        args.a_prime_results_dir
        / "grounding_item_structured_triage_cache.jsonl"
    )
    runtime_path = args.a_prime_results_dir / "runtime.json"
    provenance_path = args.a_prime_results_dir / "provenance.json"
    for path in (items_path, cache_path, runtime_path, provenance_path):
        if not path.is_file():
            raise ValueError(f"internal10 result is missing: {path}")

    items = _items_by_id(read_jsonl(items_path), expected_items)
    dataset = _dataset_by_id(
        read_jsonl(args.artifact_root / "datasets/workspacebench/full.jsonl"),
        expected_items,
    )
    baseline_all = _read_completed_items(
        args.artifact_root
        / "reports/workspace_grounding_dual_triage_holdout30_20260728/"
        "grounding_dual_triage_items.jsonl"
    )
    baseline_rows = {
        item_id: baseline_all[item_id] for item_id in expected_items
    }
    family_all = family_positive_keys(
        args.artifact_root
        / "reports/workspace_p0_blind_adjudication_20260728/"
        "SEALED_MAPPING.json",
        args.artifact_root
        / "reports/workspace_p0_blind_adjudication_20260728/"
        "GEMINI_3_1_PRO_INDEPENDENT_ANNOTATIONS.jsonl",
    )
    family_positives = {
        key for key in family_all if key[0] in expected_items
    }
    reviewed_labels = parse_reviewed_reference(
        args.artifact_root
        / "WorkspaceBench_full388_Codex证据化逐条标注_20260720.md"
    )
    result, observations, diagnostics = analyze_internal(
        items=items,
        dataset=dataset,
        baseline_rows=baseline_rows,
        family_positives=family_positives,
        reviewed_labels=reviewed_labels,
    )
    result["frozen_input_sha256"] = frozen_hashes
    result["runtime"] = validate_runtime(
        provenance=json.loads(provenance_path.read_text(encoding="utf-8")),
        runtime=json.loads(runtime_path.read_text(encoding="utf-8")),
    )
    result["raw_output_sha256"] = {
        path.name: sha256_file(path)
        for path in (items_path, cache_path, runtime_path, provenance_path)
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "a_double_prime_analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "a_double_prime_observations.jsonl").write_text(
        "".join(
            json.dumps(row.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
            for row in observations
        ),
        encoding="utf-8",
    )
    (args.output_dir / "a_double_prime_h1_diagnostics.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in diagnostics
        ),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
