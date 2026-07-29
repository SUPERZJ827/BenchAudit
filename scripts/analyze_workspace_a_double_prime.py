#!/usr/bin/env python3
"""Run the frozen, zero-API Workspace A-double-prime residue experiment."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchcore.workspace_constraint_residue import (  # noqa: E402
    APPLICABLE_REASONS,
    R2B_EXTRA_REASONS,
    ResidueObservation,
    route_constraint_residue,
)
from scripts.run_workspace_static_llm_ablation import (  # noqa: E402
    NEGATIVE_REVIEW_LABEL,
    POSITIVE_REVIEW_LABEL,
    binary_metrics,
    parse_reviewed_reference,
)


Key = tuple[str, int]
RULE_IDS = ("R2a", "R2b", "R2c", "R2d")
FROZEN_REPO_INPUTS = {
    "experiments/workspace_grounding/A_PRIME_DEV_PROTOCOL_20260729.md":
        "e7402f26bb46714687454ec368ee6e7e068a99a09a764a4f57a8708f618aabd4",
    "experiments/workspace_grounding/A_PRIME_CALIBRATION_20_20260729.json":
        "d17f47f5d74507878f63df16291952b8e33167f1941d20af64ce020f6bbe1d76",
    "experiments/workspace_grounding/A_PRIME_INTERNAL_VALIDATION_10_20260729.json":
        "8af94ea6a23663654bec21e115928f6a7d5b30b86d1912e6992e9a5d24325515",
    "experiments/workspace_grounding/A_PRIME_CALIBRATION_RESULTS_20260729.md":
        "ff22fd7069afaef524532c06bd20883d5e4d51d2eb337bee6af9b37cacc0fe17",
}
FROZEN_ARTIFACT_INPUTS = {
    (
        "reports/workspace_grounding_a_prime_calibration_20260729/"
        "grounding_item_structured_triage_items.jsonl"
    ): "689fad58c3947109b3547561681d3fa258ecbc7ded9ec94cfb7751d2ec061c1a",
    (
        "reports/workspace_grounding_a_prime_calibration_20260729/"
        "grounding_item_structured_triage_cache.jsonl"
    ): "53740726724c1a58e200245a3795ca243c2573ec49aa1ce838b1f7d7b39fc6e4",
    (
        "reports/workspace_grounding_a_prime_calibration_20260729/"
        "analysis.json"
    ): "fee5a065173851bb5597af5994e3beee9408bf40aaa0b9d62854d617d5434147",
    "datasets/workspacebench/full.jsonl":
        "2e3d8fd1f5a741b9e6b73ebab9ce23e26ce054527b4f3477de8fdd950aad9dbe",
}
REVIEWED_REFERENCE_SHA256 = (
    "fa8fbef8497ac2f8f39b21975e28dd88005a5d2541db07cbe162fb04558978cf"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_frozen_inputs(
    *,
    repo_root: Path,
    artifact_root: Path | None,
) -> dict[str, str]:
    if artifact_root is None:
        raise ValueError("--artifact-root is required")
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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _dataset_by_id(
    rows: Iterable[Mapping[str, Any]],
    expected_items: set[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in rows:
        item_id = str(value.get("item_id") or "")
        if item_id not in expected_items:
            continue
        if item_id in result:
            raise ValueError(f"duplicate source dataset item: {item_id}")
        result[item_id] = dict(value)
    if set(result) != expected_items:
        raise ValueError("source dataset does not cover the frozen calibration set")
    return result


def _items_by_id(
    rows: Iterable[Mapping[str, Any]],
    expected_items: set[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in rows:
        item_id = str(value.get("item_id") or "")
        if item_id not in expected_items:
            raise ValueError(f"unexpected A-prime item: {item_id}")
        if item_id in result:
            raise ValueError(f"duplicate A-prime item: {item_id}")
        result[item_id] = dict(value)
    if set(result) != expected_items:
        raise ValueError("A-prime results do not cover the frozen calibration set")
    return result


def _input_inventory(row: Mapping[str, Any]) -> str:
    value = row.get("data_manifest")
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value
        return json.dumps(
            parsed, ensure_ascii=False, sort_keys=True, default=str,
        )
    return json.dumps(value or [], ensure_ascii=False, sort_keys=True, default=str)


def _a_prime_candidates(
    items: Mapping[str, Mapping[str, Any]],
) -> tuple[set[Key], int, list[str]]:
    candidates: set[Key] = set()
    rubrics = 0
    unknown: set[str] = set()
    for item_id, row in items.items():
        for decision in row.get("decisions", []):
            rubrics += 1
            if not isinstance(decision, dict):
                unknown.add(item_id)
                continue
            index = decision.get("rubric_index")
            scanner = decision.get("scanner")
            route = scanner.get("structured_route") if isinstance(scanner, dict) else None
            if not isinstance(index, int) or not isinstance(route, dict):
                unknown.add(item_id)
                continue
            if (
                route.get("policy_selected_before_threshold") is True
                and float(route.get("confidence") or 0.0) >= 0.5
            ):
                candidates.add((item_id, index))
    return candidates, rubrics, sorted(unknown)


def _frozen_family_state(
    frozen_analysis: Mapping[str, Any],
) -> tuple[int, int, set[Key]]:
    thresholds = frozen_analysis.get("thresholds")
    if not isinstance(thresholds, list) or not thresholds:
        raise ValueError("frozen analysis has no threshold rows")
    row = next(
        (
            value for value in thresholds
            if isinstance(value, dict) and value.get("threshold") == 0.5
        ),
        None,
    )
    if row is None:
        raise ValueError("frozen analysis lacks the 0.5 A-prime working point")
    family = row.get("family_grounding") or {}
    misses = {
        (str(value[0]), int(value[1]))
        for value in family.get("misses", [])
        if isinstance(value, list) and len(value) == 2
    }
    positives = int(family.get("positives") or 0)
    hits = int(family.get("hits") or 0)
    if positives != hits + len(misses):
        raise ValueError("frozen family hit/miss accounting is inconsistent")
    return positives, hits, misses


def collect_residue_observations(
    *,
    items: Mapping[str, Mapping[str, Any]],
    dataset: Mapping[str, Mapping[str, Any]],
) -> tuple[
    list[ResidueObservation],
    list[dict[str, Any]],
    dict[str, Any],
    list[str],
]:
    observations: list[ResidueObservation] = []
    diagnostics: list[dict[str, Any]] = []
    unknown: set[str] = set()
    reason_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    for item_id in sorted(items):
        source = dataset[item_id]
        task = str(source.get("task") or "")
        output_contract = source.get("output_contract") or {}
        inventory = _input_inventory(source)
        source_rubrics = source.get("rubrics")
        if not isinstance(source_rubrics, list):
            unknown.add(item_id)
            continue
        for decision in items[item_id].get("decisions", []):
            if not isinstance(decision, dict):
                unknown.add(item_id)
                continue
            index = decision.get("rubric_index")
            scanner = decision.get("scanner")
            route = scanner.get("structured_route") if isinstance(scanner, dict) else None
            rubric = decision.get("rubric")
            if (
                not isinstance(index, int)
                or not isinstance(route, dict)
                or not isinstance(rubric, str)
                or index < 0
                or index >= len(source_rubrics)
                or str(source_rubrics[index]) != rubric
            ):
                unknown.add(item_id)
                continue
            action_counts[str(route.get("action") or "")] += 1
            reason_counts[str(route.get("reason_code") or "")] += 1
            source_counts[str(route.get("evidence_source") or "")] += 1
            observation, diagnostic = route_constraint_residue(
                item_id=item_id,
                rubric_index=index,
                rubric=rubric,
                route=route,
                task=task,
                output_contract=output_contract,
                input_inventory=inventory,
            )
            if observation is not None:
                observations.append(observation)
            if diagnostic is not None:
                diagnostics.append({
                    "item_id": item_id,
                    "rubric_index": index,
                    **diagnostic,
                })
    observations.sort(key=lambda row: (row.item_id, row.rubric_index))
    diagnostics.sort(key=lambda row: (row["item_id"], row["rubric_index"]))
    decomposition = {
        "reason_counts_all": dict(sorted(reason_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "evidence_source_counts": dict(sorted(source_counts.items())),
        "legacy_reason_observability": (
            "unavailable: the original A schema stored indices only"
        ),
    }
    return observations, diagnostics, decomposition, sorted(unknown)


def _reviewed_metrics(
    candidates: set[Key],
    reviewed_labels: Mapping[Key, str] | None,
    expected_items: set[str],
) -> dict[str, Any] | None:
    if reviewed_labels is None:
        return None
    universe = {
        key for key, value in reviewed_labels.items()
        if (
            key[0] in expected_items
            and value in {POSITIVE_REVIEW_LABEL, NEGATIVE_REVIEW_LABEL}
        )
    }
    positives = {
        key for key, value in reviewed_labels.items()
        if key[0] in expected_items and value == POSITIVE_REVIEW_LABEL
    }
    return binary_metrics(candidates, positives, universe)


def _rule_sets(
    observations: Iterable[ResidueObservation],
) -> dict[str, set[Key]]:
    result = {rule_id: set() for rule_id in RULE_IDS}
    for row in observations:
        key = (row.item_id, row.rubric_index)
        for rule_id in row.rule_ids:
            result[rule_id].add(key)
    return result


def rule_id_combinations() -> list[tuple[str, ...]]:
    return [
        tuple(rule_ids)
        for size in range(1, len(RULE_IDS) + 1)
        for rule_ids in itertools.combinations(RULE_IDS, size)
    ]


def choose_working_point(
    rows: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    passing = [row for row in rows if row.get("pass") is True]
    return (
        sorted(
            passing,
            key=lambda row: (
                int(row["candidates"]),
                -int(row["family_hits"]),
                len(row["rule_ids"]),
                tuple(row["rule_ids"]),
            ),
        )[0]
        if passing else None
    )


def analyze(
    *,
    items: Mapping[str, Mapping[str, Any]],
    dataset: Mapping[str, Mapping[str, Any]],
    frozen_analysis: Mapping[str, Any],
    reviewed_labels: Mapping[Key, str] | None = None,
) -> tuple[dict[str, Any], list[ResidueObservation], list[dict[str, Any]]]:
    baseline, rubric_count, baseline_unknown = _a_prime_candidates(items)
    if len(baseline) != 188 or rubric_count != 405:
        raise ValueError("A-prime baseline no longer matches frozen 188/405 counts")
    positives, baseline_hits, misses = _frozen_family_state(frozen_analysis)
    if (positives, baseline_hits, len(misses)) != (19, 12, 7):
        raise ValueError("frozen family accounting no longer matches 19/12/7")
    observations, diagnostics, decomposition, residue_unknown = (
        collect_residue_observations(items=items, dataset=dataset)
    )
    rule_sets = _rule_sets(observations)
    operational_unknown = sorted(set(baseline_unknown) | set(residue_unknown))
    review_ceiling_escape = sum(
        int(not row.review_only or row.confirmation_eligible)
        for row in observations
    )
    expected_items = set(items)

    def metrics(rule_ids: tuple[str, ...]) -> dict[str, Any]:
        rule_union = set().union(*(rule_sets[rule_id] for rule_id in rule_ids))
        additions = rule_union - baseline
        candidates = baseline | rule_union
        recovered = additions & misses
        family_hits = baseline_hits + len(recovered)
        return {
            "rule_ids": list(rule_ids),
            "raw_trigger_count": len(rule_union),
            "incremental_candidates": len(additions),
            "candidates": len(candidates),
            "candidate_rate": len(candidates) / rubric_count,
            "recovered_known_family_positives": len(recovered),
            "recovered_keys": sorted([list(key) for key in recovered]),
            "family_hits": family_hits,
            "family_positives": positives,
            "family_recall": family_hits / positives,
            "marginal_candidates_per_recovered_positive": (
                len(additions) / len(recovered) if recovered else None
            ),
            "reviewed": _reviewed_metrics(
                candidates, reviewed_labels, expected_items,
            ),
            "review_ceiling_escape": review_ceiling_escape,
            "operational_unknown": len(operational_unknown),
            "pass": (
                len(candidates) <= 211
                and family_hits >= 16
                and review_ceiling_escape == 0
                and not operational_unknown
            ),
        }

    single_rules = {
        rule_id: metrics((rule_id,)) for rule_id in RULE_IDS
    }
    combinations = [metrics(rule_ids) for rule_ids in rule_id_combinations()]
    chosen = choose_working_point(combinations)
    overlaps = {}
    for left, right in itertools.combinations(RULE_IDS, 2):
        overlaps[f"{left}&{right}"] = len(rule_sets[left] & rule_sets[right])
    reason_by_rule = {}
    route_by_key = {
        (item_id, int(decision["rubric_index"])): decision["scanner"][
            "structured_route"
        ]
        for item_id, row in items.items()
        for decision in row.get("decisions", [])
        if (
            isinstance(decision, dict)
            and isinstance(decision.get("rubric_index"), int)
            and isinstance(decision.get("scanner"), dict)
            and isinstance(
                decision["scanner"].get("structured_route"), dict,
            )
        )
    }
    for rule_id in RULE_IDS:
        reason_by_rule[rule_id] = dict(sorted(Counter(
            str(route_by_key[(item_id, index)].get("reason_code") or "")
            for item_id, index in rule_sets[rule_id]
            if (item_id, index) in route_by_key
        ).items()))
    result = {
        "protocol": "workspace-grounding-a-double-prime-residue-v1-20260729",
        "api_calls": 0,
        "counts": {
            "tasks": len(items),
            "rubrics": rubric_count,
            "a_prime_candidates": len(baseline),
            "observations": len(observations),
            "h1_diagnostics": len(diagnostics),
            "family_positives": positives,
            "a_prime_family_hits": baseline_hits,
        },
        "decomposition": decomposition,
        "h1": {
            "status_counts": dict(sorted(Counter(
                str(row["status"]) for row in diagnostics
            ).items())),
            "empty_quote_count": sum(
                int(row["reason"] == "empty_quote") for row in diagnostics
            ),
        },
        "single_rules": single_rules,
        "rule_intersections": overlaps,
        "triggered_a_prime_reason_codes": reason_by_rule,
        "combinations": combinations,
        "operational_unknown_tasks": operational_unknown,
        "review_ceiling_escape": review_ceiling_escape,
        "calibration_go": chosen is not None,
        "chosen_working_point": chosen,
        "decision": "PASS" if chosen is not None else "STOP",
        "known_family_misses_before_a_double_prime": sorted(
            [list(key) for key in misses]
        ),
    }
    return result, observations, diagnostics


def _load_reviewed_reference(path: Path | None) -> dict[Key, str] | None:
    if path is None:
        return None
    actual = sha256_file(path)
    if actual != REVIEWED_REFERENCE_SHA256:
        raise ValueError(f"reviewed reference hash mismatch: {actual}")
    return parse_reviewed_reference(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--reviewed-reference", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    frozen_hashes = verify_frozen_inputs(
        repo_root=REPO,
        artifact_root=args.artifact_root,
    )
    manifest = json.loads((
        REPO
        / "experiments/workspace_grounding/A_PRIME_CALIBRATION_20_20260729.json"
    ).read_text(encoding="utf-8"))
    expected_items = {str(value) for value in manifest["item_ids"]}
    report_root = (
        args.artifact_root
        / "reports/workspace_grounding_a_prime_calibration_20260729"
    )
    items = _items_by_id(
        read_jsonl(report_root / "grounding_item_structured_triage_items.jsonl"),
        expected_items,
    )
    dataset = _dataset_by_id(
        read_jsonl(args.artifact_root / "datasets/workspacebench/full.jsonl"),
        expected_items,
    )
    frozen_analysis = json.loads(
        (report_root / "analysis.json").read_text(encoding="utf-8")
    )
    result, observations, diagnostics = analyze(
        items=items,
        dataset=dataset,
        frozen_analysis=frozen_analysis,
        reviewed_labels=_load_reviewed_reference(args.reviewed_reference),
    )
    result["frozen_input_sha256"] = frozen_hashes
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "observations.jsonl").write_text(
        "".join(
            json.dumps(row.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
            for row in observations
        ),
        encoding="utf-8",
    )
    (args.output_dir / "h1_diagnostics.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in diagnostics
        ),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
