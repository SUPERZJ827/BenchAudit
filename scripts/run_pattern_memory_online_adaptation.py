"""Exploratory prequential routing study for confirmed non-code defects.

This script deliberately keeps benchmark rows and defect labels in separate
objects.  A policy selects probes from structural applicability and historical
state only.  Rewards are revealed *after* all probes for the current item have
been selected, which makes target feedback usable without leaking future
target outcomes.

The study is exploratory: both labelled targets informed development, and the
previously unseen JobBench holdout has no independent defect annotations.
Memory-derived evidence therefore remains review-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import noncode_pattern_corpus as noncode


PROTOCOL_ID = "pattern-memory-noncode-online-exploratory-v1"
POLICIES = (
    "A_frozen_generic",
    "R_random_static",
    "R_random_per_item",
    "D_source_memory",
    "H_online_ucb1",
    "I_memory_seeded_ucb1",
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _confirmed_label(label: Any) -> bool:
    return str(label or "").startswith("已确认")


def load_workspace_confirmed(
    path: Path,
) -> dict[str, frozenset[str]]:
    """Load only independently confirmed, one-to-one probe labels.

    WorkspaceBench ``output_files`` are intentionally not treated as a gold
    deliverable contract.  Consequently, task/contract and rubric/contract
    filename annotations are excluded here even when an older report called
    them confirmed.  ``placeholder_leak`` is the only current family with a
    direct, contract-independent mapping to the frozen probes.
    """

    rows = json.loads(path.read_text(encoding="utf-8"))
    labels: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if (
            _confirmed_label(row.get("label"))
            and row.get("family") == "placeholder_leak"
        ):
            labels[str(row["item"])].add("placeholder_leak")
    return {
        item_id: frozenset(families)
        for item_id, families in labels.items()
    }


def _gdpval_family(violation: Mapping[str, Any]) -> str:
    defect_type = str(violation.get("defect_type") or "")
    message = str(violation.get("message") or "")
    if defect_type == "rubric_reference_contract_mismatch":
        return "rubric_reference_filename"
    if "Task spreadsheet-column" in message:
        return "task_rubric_column_difference"
    if "Rubric spreadsheet-column" in message:
        return "rubric_column_conflict"
    if "task output format" in message:
        return "task_output_format"
    if "task filename" in message:
        return "task_output_filename"
    if "rubric filename" in message:
        return "rubric_output_filename"
    raise ValueError(
        "confirmed GDPval violation has no frozen probe-family mapping: "
        f"{defect_type}: {message}"
    )


def load_gdpval_confirmed(
    path: Path,
) -> dict[str, frozenset[str]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    labels: dict[str, set[str]] = defaultdict(set)
    for violation in report.get("violations", []):
        if violation.get("evidence_tier") != "confirmed":
            continue
        labels[str(violation["item_id"])].add(
            _gdpval_family(violation)
        )
    return {
        item_id: frozenset(families)
        for item_id, families in labels.items()
    }


def validate_label_applicability(
    corpus: Sequence[Mapping[str, Any]],
    labels: Mapping[str, frozenset[str]],
) -> None:
    by_id = {str(row["task_id"]): set(row["applicable"]) for row in corpus}
    missing_items = sorted(set(labels) - set(by_id))
    if missing_items:
        raise ValueError(f"labels refer to absent items: {missing_items}")
    invalid = {
        item_id: sorted(set(families) - by_id[item_id])
        for item_id, families in labels.items()
        if set(families) - by_id[item_id]
    }
    if invalid:
        raise ValueError(f"confirmed labels are not probe-applicable: {invalid}")


def source_statistics(
    corpus: Sequence[Mapping[str, Any]],
    labels: Mapping[str, frozenset[str]],
) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for family in noncode.PROBE_FAMILIES:
        eligible = sum(
            family in set(row["applicable"]) for row in corpus
        )
        findings = sum(
            family in labels.get(str(row["task_id"]), frozenset())
            for row in corpus
        )
        result[family] = {
            "eligible_tasks": eligible,
            "confirmed_findings": findings,
            "confirmed_yield": findings / eligible if eligible else 0.0,
        }
    return result


def source_order(
    stats: Mapping[str, Mapping[str, float | int]],
) -> list[str]:
    return sorted(
        noncode.PROBE_FAMILIES,
        key=lambda family: (
            -float(stats[family]["confirmed_yield"]),
            -int(stats[family]["confirmed_findings"]),
            noncode.PROBE_FAMILIES.index(family),
        ),
    )


def _ucb_selection(
    applicable: Sequence[str],
    *,
    budget: int,
    successes: Mapping[str, float],
    counts: Mapping[str, float],
    total_updates: int,
    exploration_constant: float,
    rng: random.Random,
) -> list[str]:
    scored = []
    log_term = math.log(max(total_updates, 1) + len(noncode.PROBE_FAMILIES))
    for family in applicable:
        count = max(float(counts.get(family, 0.0)), 1e-12)
        mean = float(successes.get(family, 0.0)) / count
        bonus = exploration_constant * math.sqrt(log_term / count)
        scored.append((mean + bonus, rng.random(), family))
    scored.sort(reverse=True)
    return [family for _, _, family in scored[:budget]]


def run_policy(
    corpus: Sequence[Mapping[str, Any]],
    labels: Mapping[str, frozenset[str]],
    source_stats: Mapping[str, Mapping[str, float | int]],
    *,
    policy: str,
    budget: int,
    exploration_constant: float,
    seed: int,
) -> dict[str, Any]:
    if policy not in POLICIES:
        raise ValueError(f"unsupported policy: {policy}")
    rng = random.Random(seed)
    rows = list(corpus)
    rng.shuffle(rows)
    generic_order = list(noncode.PROBE_FAMILIES)
    random_order = list(noncode.PROBE_FAMILIES)
    rng.shuffle(random_order)
    memory_order = source_order(source_stats)

    # One neutral pseudo-observation per family regularizes UCB and ensures the
    # source-seeded arm changes prior mean, not whether a family is explored.
    counts = {family: 1.0 for family in noncode.PROBE_FAMILIES}
    successes = {family: 0.0 for family in noncode.PROBE_FAMILIES}
    if policy == "I_memory_seeded_ucb1":
        for family in noncode.PROBE_FAMILIES:
            successes[family] = float(
                source_stats[family]["confirmed_yield"]
            )

    probes = 0
    findings = 0
    detected_items: set[str] = set()
    late_probes = 0
    late_findings = 0
    selection_digest_rows = []
    midpoint = len(rows) // 2

    for index, row in enumerate(rows):
        item_id = str(row["task_id"])
        applicable = [
            family
            for family in noncode.PROBE_FAMILIES
            if family in set(row["applicable"])
        ]
        actual_budget = min(budget, len(applicable))
        if policy == "A_frozen_generic":
            selected = [
                family for family in generic_order if family in applicable
            ][:actual_budget]
        elif policy == "R_random_static":
            selected = [
                family for family in random_order if family in applicable
            ][:actual_budget]
        elif policy == "R_random_per_item":
            selected = list(applicable)
            rng.shuffle(selected)
            selected = selected[:actual_budget]
        elif policy == "D_source_memory":
            selected = [
                family for family in memory_order if family in applicable
            ][:actual_budget]
        else:
            selected = _ucb_selection(
                applicable,
                budget=actual_budget,
                successes=successes,
                counts=counts,
                total_updates=probes + len(noncode.PROBE_FAMILIES),
                exploration_constant=exploration_constant,
                rng=rng,
            )

        # The policy has committed to every probe for this item before rewards
        # become visible.  This prevents within-item or future-label leakage.
        item_labels = labels.get(item_id, frozenset())
        rewards = {
            family: int(family in item_labels) for family in selected
        }
        item_findings = sum(rewards.values())
        probes += len(selected)
        findings += item_findings
        if item_findings:
            detected_items.add(item_id)
        if index >= midpoint:
            late_probes += len(selected)
            late_findings += item_findings
        if policy in {"H_online_ucb1", "I_memory_seeded_ucb1"}:
            for family, reward in rewards.items():
                counts[family] += 1.0
                successes[family] += float(reward)
        selection_digest_rows.append({
            "position": index,
            "selected": selected,
        })

    labelled_items = set(labels)
    return {
        "probes": probes,
        "confirmed_findings": findings,
        "confirmed_finding_yield": findings / probes if probes else 0.0,
        "confirmed_labelled_items": len(labelled_items),
        "detected_confirmed_items": len(detected_items),
        "confirmed_task_recall": (
            len(detected_items) / len(labelled_items)
            if labelled_items else 0.0
        ),
        "late_half_confirmed_finding_yield": (
            late_findings / late_probes if late_probes else 0.0
        ),
        # No item IDs or outcomes are retained in the digest payload.
        "selection_sha256": hashlib.sha256(
            canonical_json(selection_digest_rows).encode("utf-8")
        ).hexdigest(),
    }


def percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = min(int(quantile * len(ordered)), len(ordered) - 1)
    return ordered[position]


def aggregate_runs(
    runs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    metrics = (
        "confirmed_finding_yield",
        "confirmed_task_recall",
        "late_half_confirmed_finding_yield",
    )
    result: dict[str, Any] = {
        "runs": len(runs),
        "probe_count_min": min(int(row["probes"]) for row in runs),
        "probe_count_max": max(int(row["probes"]) for row in runs),
    }
    for metric in metrics:
        values = [float(row[metric]) for row in runs]
        result[metric] = {
            "mean": sum(values) / len(values),
            "p05": percentile(values, 0.05),
            "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95),
        }
    return result


def paired_summary(
    arm: Sequence[Mapping[str, Any]],
    baseline: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    result = {}
    for metric in (
        "confirmed_finding_yield",
        "confirmed_task_recall",
        "late_half_confirmed_finding_yield",
    ):
        differences = [
            float(left[metric]) - float(right[metric])
            for left, right in zip(arm, baseline)
        ]
        result[metric] = {
            "mean_difference": sum(differences) / len(differences),
            # This is the central interval across randomized item orders, not
            # a confidence interval over a hypothetical benchmark population.
            "central_90_interval": [
                percentile(differences, 0.05),
                percentile(differences, 0.95),
            ],
            "probability_positive": (
                sum(value > 0 for value in differences) / len(differences)
            ),
            "probability_negative": (
                sum(value < 0 for value in differences) / len(differences)
            ),
        }
    return result


def evaluate_direction(
    source_name: str,
    target_name: str,
    source_corpus: Sequence[Mapping[str, Any]],
    source_labels: Mapping[str, frozenset[str]],
    target_corpus: Sequence[Mapping[str, Any]],
    target_labels: Mapping[str, frozenset[str]],
    *,
    budgets: Sequence[int],
    permutations: int,
    exploration_constant: float,
    sensitivity_constants: Sequence[float],
    seed: int,
) -> dict[str, Any]:
    stats = source_statistics(source_corpus, source_labels)
    result: dict[str, Any] = {
        "source": source_name,
        "target": target_name,
        "source_family_statistics": stats,
        "source_target_confirmed_family_overlap": sorted(
            {
                family
                for families in source_labels.values()
                for family in families
            }
            & {
                family
                for families in target_labels.values()
                for family in families
            }
        ),
        "budgets": {},
    }
    for budget in budgets:
        policy_runs: dict[str, list[dict[str, Any]]] = {
            policy: [] for policy in POLICIES
        }
        for permutation in range(permutations):
            trial_seed = seed + permutation
            for policy in POLICIES:
                policy_runs[policy].append(run_policy(
                    target_corpus,
                    target_labels,
                    stats,
                    policy=policy,
                    budget=budget,
                    exploration_constant=exploration_constant,
                    seed=trial_seed,
                ))
        expected_probes = {
            row["probes"]
            for runs in policy_runs.values()
            for row in runs
        }
        if len(expected_probes) != 1:
            raise RuntimeError(
                f"equal-budget invariant failed for {source_name} -> "
                f"{target_name}, budget={budget}: {expected_probes}"
            )
        random_baseline = policy_runs["R_random_per_item"]
        result["budgets"][str(budget)] = {
            "metrics": {
                policy: aggregate_runs(runs)
                for policy, runs in policy_runs.items()
            },
            "paired_minus_random_per_item": {
                policy: paired_summary(runs, random_baseline)
                for policy, runs in policy_runs.items()
                if policy != "R_random_per_item"
            },
        }

    # Every constant is reported; this is a sensitivity analysis, not a
    # hyperparameter-selection procedure.
    sensitivity: dict[str, Any] = {}
    for constant in sensitivity_constants:
        constant_rows = {}
        for budget in budgets:
            runs = [
                run_policy(
                    target_corpus,
                    target_labels,
                    stats,
                    policy="H_online_ucb1",
                    budget=budget,
                    exploration_constant=float(constant),
                    seed=seed + permutation,
                )
                for permutation in range(permutations)
            ]
            constant_rows[str(budget)] = aggregate_runs(runs)
        sensitivity[str(constant)] = constant_rows
    result["ucb_constant_sensitivity"] = sensitivity
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--workspace-evidence", type=Path, required=True)
    parser.add_argument("--gdpval", type=Path, required=True)
    parser.add_argument("--gdpval-evidence", type=Path, required=True)
    parser.add_argument("--jobbench", type=Path, required=True)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(
            "experiments/pattern_memory/"
            "noncode_online_adaptation_exploratory_v1.json"
        ),
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("protocol ID mismatch")
    paths = {
        "workspacebench": args.workspace,
        "gdpval": args.gdpval,
        "jobbench": args.jobbench,
    }
    evidence_paths = {
        "workspacebench": args.workspace_evidence,
        "gdpval": args.gdpval_evidence,
    }
    for dataset, path in paths.items():
        digest = noncode.sha256_path(path)
        expected = protocol["benchmarks"][dataset]["data_sha256"]
        if digest != expected:
            raise ValueError(
                f"{dataset} data SHA-256 mismatch: {digest} != {expected}"
            )
    for dataset, path in evidence_paths.items():
        digest = noncode.sha256_path(path)
        expected = protocol["benchmarks"][dataset]["evidence_sha256"]
        if digest != expected:
            raise ValueError(
                f"{dataset} evidence SHA-256 mismatch: {digest} != {expected}"
            )

    workspace = noncode.build_corpus(
        "workspacebench", noncode.load_workspace(args.workspace),
    )
    gdpval = noncode.build_corpus(
        "gdpval", noncode.load_gdpval(args.gdpval),
    )
    workspace_labels = load_workspace_confirmed(args.workspace_evidence)
    gdpval_labels = load_gdpval_confirmed(args.gdpval_evidence)
    validate_label_applicability(workspace, workspace_labels)
    validate_label_applicability(gdpval, gdpval_labels)

    controls = protocol["controls"]
    common = {
        "budgets": protocol["budgets_per_item"],
        "permutations": controls["item_order_permutations"],
        "exploration_constant": controls["ucb_exploration_constant"],
        "sensitivity_constants": controls["sensitivity_constants"],
    }
    directions = [
        evaluate_direction(
            "gdpval",
            "workspacebench",
            gdpval,
            gdpval_labels,
            workspace,
            workspace_labels,
            seed=controls["seed"],
            **common,
        ),
        evaluate_direction(
            "workspacebench",
            "gdpval",
            workspace,
            workspace_labels,
            gdpval,
            gdpval_labels,
            seed=controls["seed"] + 100_000,
            **common,
        ),
    ]
    result = {
        "schema_version": "benchcore-pattern-memory-online-exploratory-v1",
        "protocol": protocol,
        "label_summary": {
            "workspacebench": {
                "confirmed_items": len(workspace_labels),
                "confirmed_findings": sum(map(len, workspace_labels.values())),
                "family_counts": dict(sorted(Counter(
                    family
                    for families in workspace_labels.values()
                    for family in families
                ).items())),
            },
            "gdpval": {
                "confirmed_items": len(gdpval_labels),
                "confirmed_findings": sum(map(len, gdpval_labels.values())),
                "family_counts": dict(sorted(Counter(
                    family
                    for families in gdpval_labels.values()
                    for family in families
                ).items())),
            },
            "jobbench": {
                "confirmed_items": None,
                "confirmed_findings": None,
                "status": "not_independently_annotated",
            },
        },
        "directions": directions,
        "selection_uses_current_or_future_target_outcomes": False,
        "selection_uses_target_text_values": False,
        "promotion_ceiling": "review",
        "generalization_claim_allowed": False,
    }
    result["stable_summary_sha256"] = hashlib.sha256(
        canonical_json(result).encode("utf-8")
    ).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "label_summary": result["label_summary"],
        "directions": [
            {
                "source": row["source"],
                "target": row["target"],
                "source_target_confirmed_family_overlap": (
                    row["source_target_confirmed_family_overlap"]
                ),
                "budget_3": row["budgets"].get("3"),
            }
            for row in directions
        ],
        "stable_summary_sha256": result["stable_summary_sha256"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
