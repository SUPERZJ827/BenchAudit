"""Run a frozen cross-domain counterexample protocol self-test.

This is an implementation/invariant test, not a real-benchmark accuracy claim.
Every injected and clean control is specified before adjudication, and results
are reported separately by family and evidence tier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchcore.counterexample_validation import (
    DEGRADATION_SHOULD_LOWER,
    EQUIVALENT_SHOULD_PASS,
    EQUIVALENT_SHOULD_PRESERVE,
    GAMING_SHOULD_NOT_RAISE,
    INVALID_SHOULD_FAIL,
    ObjectivePairObservation,
    ScoredPairSpec,
    ScoredPairTrial,
    TableRecomputeObservation,
    adjudicate_objective_pair,
    adjudicate_scored_pair,
    adjudicate_table_recompute,
)
from benchcore.execution_attestation import (
    ATTESTATION_PROTOCOL,
    SEPARATE_PROCESS_DOMAIN,
    AttestationStatus,
)


SEED = 20260721


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--md")
    return parser.parse_args()


def run_experiment() -> dict[str, Any]:
    cases: list[tuple[str, bool, Any]] = []
    cases.extend(_objective_cases())
    cases.extend(_table_cases())
    cases.extend(_scored_cases())
    details = []
    by_family: dict[str, dict[str, int]] = defaultdict(
        lambda: {"injected": 0, "detected": 0, "controls": 0, "false_alarms": 0}
    )
    for case_id, expected_alarm, decision in cases:
        alarm = decision.status == "defect_observed"
        row = {
            "case_id": case_id,
            "expected_alarm": expected_alarm,
            "observed_alarm": alarm,
            "correct": alarm == expected_alarm,
            "decision": decision.to_dict(),
        }
        details.append(row)
        counts = by_family[decision.family]
        if expected_alarm:
            counts["injected"] += 1
            counts["detected"] += int(alarm)
        else:
            counts["controls"] += 1
            counts["false_alarms"] += int(alarm)
    injected = sum(row["expected_alarm"] for row in details)
    detected = sum(row["expected_alarm"] and row["observed_alarm"] for row in details)
    controls = len(details) - injected
    false_alarms = sum(not row["expected_alarm"] and row["observed_alarm"] for row in details)
    return {
        "schema_version": "counterexample-injection-selftest-v1",
        "seed": SEED,
        "claim_boundary": (
            "Protocol implementation self-test only; does not estimate precision or recall "
            "on natural benchmark defects."
        ),
        "summary": {
            "cases": len(details),
            "injected": injected,
            "detected": detected,
            "injected_recall": detected / injected if injected else 0.0,
            "controls": controls,
            "false_alarms": false_alarms,
            "control_false_alarm_rate": false_alarms / controls if controls else 0.0,
            "confirmed_decisions": sum(
                row["decision"]["evidence_tier"] == "confirmed" for row in details
            ),
            "review_decisions": sum(
                row["decision"]["evidence_tier"] == "review" for row in details
            ),
        },
        "per_family": {
            family: {
                **counts,
                "injected_recall": counts["detected"] / counts["injected"]
                if counts["injected"] else 0.0,
                "control_false_alarm_rate": counts["false_alarms"] / counts["controls"]
                if counts["controls"] else 0.0,
            }
            for family, counts in sorted(by_family.items())
        },
        "details": details,
    }


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# Cross-domain counterexample protocol self-test",
        "",
        f"> {result['claim_boundary']}",
        "",
        f"- Injected detection: **{summary['detected']}/{summary['injected']}**",
        f"- Clean-control false alarms: **{summary['false_alarms']}/{summary['controls']}**",
        f"- Confirmed/review decisions: **{summary['confirmed_decisions']}/{summary['review_decisions']}**",
        "",
        "| Family | Injected | Detected | Controls | False alarms |",
        "|---|---:|---:|---:|---:|",
    ]
    for family, row in result["per_family"].items():
        lines.append(
            f"| {family} | {row['injected']} | {row['detected']} | "
            f"{row['controls']} | {row['false_alarms']} |"
        )
    return "\n".join(lines) + "\n"


def _objective_cases() -> list[tuple[str, bool, Any]]:
    rows = []
    for relation, bad_variant, label in (
        (EQUIVALENT_SHOULD_PASS, False, "overstrict"),
        (INVALID_SHOULD_FAIL, True, "understrict"),
    ):
        for expected_alarm, variant_accepted, suffix in (
            (True, bad_variant, "injected"),
            (False, not bad_variant, "control"),
        ):
            case_id = f"code-{label}-{suffix}"
            observation = ObjectivePairObservation(
                pair_id=case_id,
                family="code",
                relation=relation,
                baseline_accepted=True,
                variant_accepted=variant_accepted,
                relation_certified=True,
                official_evaluator=True,
                transcript_attested=True,
                independent_adjudicator=True,
                execution_transcript_sha256=_digest(case_id + "-transcript"),
                baseline_sha256=_digest(case_id + "-baseline"),
                variant_sha256=_digest(case_id + "-variant"),
                mutation_operator=label,
            )
            rows.append((
                case_id,
                expected_alarm,
                adjudicate_objective_pair(
                    observation,
                    _trusted_attestation(observation.execution_transcript_sha256),
                ),
            ))
    return rows


def _table_cases() -> list[tuple[str, bool, Any]]:
    rows = []
    for expected_alarm, recomputed, suffix in ((True, 90.0, "injected"), (False, 100.0, "control")):
        case_id = f"table-recompute-{suffix}"
        observation = TableRecomputeObservation(
            item_id=case_id,
            declared_value=100.0,
            recomputed_value=recomputed,
            absolute_tolerance=0.01,
            relative_tolerance=1e-6,
            source_cells_pinned=True,
            formula_pinned=True,
            transcript_attested=True,
            independent_adjudicator=True,
            official_value_sha256=_digest(case_id + "-official"),
            recompute_transcript_sha256=_digest(case_id + "-transcript"),
        )
        rows.append((
            case_id,
            expected_alarm,
            adjudicate_table_recompute(
                observation,
                _trusted_attestation(observation.recompute_transcript_sha256),
            ),
        ))
    return rows


def _scored_cases() -> list[tuple[str, bool, Any]]:
    rows = []
    configurations = (
        ("workspace", DEGRADATION_SHOULD_LOWER, 0.85, 0.85, 0.85, 0.55, "insensitivity"),
        ("workspace", EQUIVALENT_SHOULD_PRESERVE, 0.85, 0.55, 0.85, 0.85, "invariance"),
        ("workspace", GAMING_SHOULD_NOT_RAISE, 0.50, 0.80, 0.50, 0.50, "gaming"),
        ("open_ended", DEGRADATION_SHOULD_LOWER, 0.85, 0.85, 0.85, 0.55, "open-insensitivity"),
    )
    for family, relation, base, injected_variant, control_base, control_variant, label in configurations:
        for expected_alarm, baseline, variant, suffix in (
            (True, base, injected_variant, "injected"),
            (False, control_base, control_variant, "control"),
        ):
            case_id = f"{label}-{suffix}"
            spec = ScoredPairSpec(
                pair_id=case_id,
                family=family,
                relation=relation,
                mutation_operator=label,
                construction="deterministic",
                baseline_sha256=_digest(case_id + "-baseline"),
                variant_sha256=_digest(case_id + "-variant"),
                changed_paths=("artifact",),
                rubric_quote="Frozen explicit requirement for the self-test.",
                grader_kind="llm",
            )
            trial_rows = [
                ScoredPairTrial(
                    seed=SEED + index,
                    presented_order="AB" if index % 2 == 0 else "BA",
                    evaluator_id="frozen-judge",
                    baseline_score=baseline,
                    variant_score=variant,
                    transcript_sha256=_digest(f"{case_id}-trial-{index}"),
                    transcript_attested=True,
                )
                for index in range(10)
            ]
            rows.append((case_id, expected_alarm, adjudicate_scored_pair(spec, trial_rows)))
    return rows


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _trusted_attestation(payload_sha256: str) -> AttestationStatus:
    """Frozen test double; production callers must use their external verifier."""

    return AttestationStatus(
        trust_domain=SEPARATE_PROCESS_DOMAIN,
        payload_sha256=payload_sha256,
        verified=True,
        reason="frozen self-test verifier accepted",
        attestation={
            "protocol": ATTESTATION_PROTOCOL,
            "payload_sha256": payload_sha256,
        },
    )


def main() -> None:
    args = parse_args()
    result = run_experiment()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md:
        md = Path(args.md)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
