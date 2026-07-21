import hashlib

import pytest

from benchcore.counterexample_validation import (
    CRITERION_LOCALITY,
    DEGRADATION_SHOULD_LOWER,
    EQUIVALENT_SHOULD_PASS,
    EQUIVALENT_SHOULD_PRESERVE,
    GAMING_SHOULD_NOT_RAISE,
    INVALID_SHOULD_FAIL,
    CounterexamplePolicy,
    ObjectivePairObservation,
    ScoredPairSpec,
    ScoredPairTrial,
    TableRecomputeObservation,
    adjudicate_objective_pair,
    adjudicate_scored_pair,
    adjudicate_table_recompute,
    binomial_upper_tail,
    build_exact_answer_pairs,
    replay_exact_answer_pairs,
    verification_capabilities,
)
from benchcore.schema import BenchmarkItem
from benchcore.execution_attestation import (
    ATTESTATION_PROTOCOL,
    SEPARATE_PROCESS_DOMAIN,
    AttestationStatus,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def objective(**overrides):
    values = {
        "pair_id": "pair-1",
        "family": "code",
        "relation": EQUIVALENT_SHOULD_PASS,
        "baseline_accepted": True,
        "variant_accepted": False,
        "relation_certified": True,
        "official_evaluator": True,
        "transcript_attested": True,
        "independent_adjudicator": True,
        "execution_transcript_sha256": digest("execution-transcript"),
        "baseline_sha256": digest("baseline"),
        "variant_sha256": digest("variant"),
        "mutation_operator": "equivalent_api",
    }
    values.update(overrides)
    return ObjectivePairObservation(**values)


def trusted_attestation(payload_sha256: str) -> AttestationStatus:
    return AttestationStatus(
        trust_domain=SEPARATE_PROCESS_DOMAIN,
        payload_sha256=payload_sha256,
        verified=True,
        reason="test verifier accepted",
        attestation={
            "protocol": ATTESTATION_PROTOCOL,
            "payload_sha256": payload_sha256,
        },
    )


def scored_spec(**overrides):
    values = {
        "pair_id": "rubric-pair",
        "family": "workspace",
        "relation": DEGRADATION_SHOULD_LOWER,
        "mutation_operator": "delete_required_section",
        "construction": "deterministic",
        "baseline_sha256": digest("complete"),
        "variant_sha256": digest("section removed"),
        "changed_paths": ("report.md#required-section",),
        "rubric_quote": "The report must contain the required section.",
        "expected_min_delta": 0.10,
        "invariance_tolerance": 0.03,
        "grader_kind": "llm",
    }
    values.update(overrides)
    return ScoredPairSpec(**values)


def trials(
    baseline: float,
    variant: float,
    *,
    count: int = 10,
    attested: bool = True,
    baseline_criteria=None,
    variant_criteria=None,
    criterion_score_max=None,
):
    return [
        ScoredPairTrial(
            seed=index,
            presented_order="AB" if index % 2 == 0 else "BA",
            evaluator_id="official-grader",
            baseline_score=baseline,
            variant_score=variant,
            baseline_criteria=baseline_criteria or {},
            variant_criteria=variant_criteria or {},
            criterion_score_max=criterion_score_max or {},
            transcript_sha256=digest(f"trial-{index}"),
            transcript_attested=attested,
        )
        for index in range(count)
    ]


def test_capabilities_are_multi_route_not_forced_single_family():
    item = BenchmarkItem(
        item_id="table-answer",
        raw={},
        task="Read the spreadsheet table and report the total column value.",
        gold="42",
        evaluator={"type": "numeric"},
    )

    routes = verification_capabilities(item)

    assert [route.family for route in routes] == ["table", "exact_answer"]


def test_workspace_and_code_routes_can_coexist():
    item = BenchmarkItem(
        item_id="workspace-code",
        raw={"rubrics": ["Tests pass"], "tests": ["pytest"]},
        task="Modify the repository and produce report.md.",
        evaluator={"rubrics": ["Tests pass"], "code_context": "def test(): pass"},
        output_contract={"type": "workspace_files"},
    )

    families = [route.family for route in verification_capabilities(item)]

    assert families == ["workspace", "code"]


def test_attested_equivalent_rejection_is_confirmed_for_code():
    observation = objective()
    decision = adjudicate_objective_pair(
        observation,
        trusted_attestation(observation.execution_transcript_sha256),
    )

    assert decision.status == "defect_observed"
    assert decision.evidence_tier == "confirmed"
    assert decision.proof_kind == "attested_objective_counterexample"


def test_llm_proposal_origin_does_not_block_objective_execution_proof():
    observation = objective(mutation_origin="llm")
    decision = adjudicate_objective_pair(
        observation,
        trusted_attestation(observation.execution_transcript_sha256),
    )

    assert decision.evidence_tier == "confirmed"
    assert decision.evidence["mutation_origin"] == "llm"


def test_shared_trust_domain_keeps_code_differential_at_review():
    decision = adjudicate_objective_pair(
        objective(independent_adjudicator=False)
    )

    assert decision.status == "defect_observed"
    assert decision.evidence_tier == "review"


def test_manifest_boolean_cannot_forge_execution_confirmation():
    observation = objective(transcript_attested=True)

    decision = adjudicate_objective_pair(observation)

    assert decision.evidence_tier == "review"
    assert decision.evidence["proof_preconditions"]["trusted_attestation_verified"] is False


def test_invalid_mutant_rejected_is_expected_behavior_not_clean_proof():
    decision = adjudicate_objective_pair(objective(
        relation=INVALID_SHOULD_FAIL,
        variant_accepted=False,
    ))

    assert decision.status == "expected_behavior"
    assert decision.evidence_tier == "unknown"


def test_objective_pair_rejects_forged_or_identical_hashes():
    decision = adjudicate_objective_pair(objective(
        baseline_sha256=digest("same"),
        variant_sha256=digest("same"),
    ))

    assert decision.status == "invalid_evidence"
    assert "must differ" in decision.reason


def test_table_mismatch_confirms_only_with_all_provenance_preconditions():
    observation = TableRecomputeObservation(
        item_id="sheet-1",
        declared_value=100.0,
        recomputed_value=90.0,
        absolute_tolerance=0.01,
        relative_tolerance=1e-6,
        source_cells_pinned=True,
        formula_pinned=True,
        transcript_attested=True,
        independent_adjudicator=True,
        official_value_sha256=digest("100"),
        recompute_transcript_sha256=digest("recompute"),
    )

    confirmed = adjudicate_table_recompute(
        observation,
        trusted_attestation(observation.recompute_transcript_sha256),
    )
    review = adjudicate_table_recompute(
        TableRecomputeObservation(**{
            **observation.__dict__,
            "source_cells_pinned": False,
        })
    )

    assert confirmed.evidence_tier == "confirmed"
    assert confirmed.metrics["absolute_delta"] == 10.0
    assert review.evidence_tier == "review"


def test_workspace_deleted_requirement_with_unchanged_scores_is_detected():
    decision = adjudicate_scored_pair(
        scored_spec(),
        trials(0.85, 0.85),
    )

    assert decision.status == "defect_observed"
    assert decision.evidence_tier == "review"
    assert decision.metrics["violation_rate"] == 1.0
    assert decision.metrics["binomial_upper_tail_p"] == pytest.approx(0.0009765625)


def test_targeted_rubric_sensitivity_uses_criterion_score_not_diluted_total():
    decision = adjudicate_scored_pair(
        scored_spec(target_criterion="required_section"),
        trials(
            0.80,
            0.75,
            baseline_criteria={"required_section": 9.0, "style": 7.0},
            variant_criteria={"required_section": 9.0, "style": 6.0},
            criterion_score_max={"required_section": 10.0, "style": 10.0},
        ),
    )

    assert decision.status == "defect_observed"
    assert decision.metrics["evaluated_score_scope"] == "required_section"
    assert decision.metrics["mean_normalized_delta"] == 0.0


def test_llm_grader_never_auto_confirms_even_with_deterministic_mutation():
    decision = adjudicate_scored_pair(
        scored_spec(grader_kind="llm"),
        trials(0.9, 0.9),
    )

    assert decision.evidence_tier == "review"
    assert decision.proof_kind == "repeated_blind_paired_evaluator_behavior"


def test_deterministic_official_rubric_evaluator_can_confirm_behavior():
    rows = trials(0.9, 0.9, attested=True)
    decision = adjudicate_scored_pair(
        scored_spec(grader_kind="deterministic"),
        rows,
        verified_transcript_hashes=frozenset(row.transcript_sha256 for row in rows),
    )

    assert decision.evidence_tier == "confirmed"
    assert decision.proof_kind == "attested_deterministic_evaluator_behavior"


def test_trial_boolean_cannot_forge_deterministic_grader_confirmation():
    decision = adjudicate_scored_pair(
        scored_spec(grader_kind="deterministic"),
        trials(0.9, 0.9, attested=True),
    )

    assert decision.status == "defect_observed"
    assert decision.evidence_tier == "review"


def test_open_ended_pair_always_remains_review():
    decision = adjudicate_scored_pair(
        scored_spec(family="open_ended", grader_kind="deterministic"),
        trials(0.9, 0.9),
    )

    assert decision.status == "defect_observed"
    assert decision.evidence_tier == "review"


def test_equivalent_format_score_instability_is_detected():
    decision = adjudicate_scored_pair(
        scored_spec(
            relation=EQUIVALENT_SHOULD_PRESERVE,
            mutation_operator="rename_internal_object_ids",
            expected_min_delta=0.0,
            invariance_tolerance=0.03,
        ),
        trials(0.9, 0.6),
    )

    assert decision.status == "defect_observed"
    assert decision.metrics["mean_normalized_delta"] == pytest.approx(-0.3)


def test_reward_hacking_score_increase_is_detected():
    decision = adjudicate_scored_pair(
        scored_spec(
            relation=GAMING_SHOULD_NOT_RAISE,
            mutation_operator="insert_unsupported_completion_claim",
            expected_min_delta=0.0,
        ),
        trials(0.4, 0.7),
    )

    assert decision.status == "defect_observed"


def test_criterion_locality_uses_off_target_score_vectors():
    spec = scored_spec(
        relation=CRITERION_LOCALITY,
        target_criterion="accuracy",
        mutation_operator="improve_accuracy_only",
    )
    decision = adjudicate_scored_pair(
        spec,
        trials(
            0.7,
            0.8,
            baseline_criteria={"accuracy": 0.5, "style": 0.9},
            variant_criteria={"accuracy": 0.8, "style": 0.5},
        ),
    )

    assert decision.status == "defect_observed"
    assert decision.metrics["violation_rate"] == 1.0


def test_scored_pair_requires_blind_order_balance_unique_seeds_and_hashes():
    rows = trials(0.8, 0.8, count=6)
    rows = [ScoredPairTrial(**{**row.__dict__, "presented_order": "AB"}) for row in rows]

    decision = adjudicate_scored_pair(scored_spec(), rows)

    assert decision.status == "invalid_evidence"
    assert "both AB and BA" in decision.reason


def test_exact_answer_pairs_cover_equivalent_and_invalid_numeric_forms():
    item = BenchmarkItem(
        item_id="numeric",
        raw={},
        task="What is 2 + 4?",
        gold="6",
        evaluator={"type": "numeric"},
        output_contract={"type": "number"},
    )

    pairs = build_exact_answer_pairs(item)
    decisions = replay_exact_answer_pairs(item)

    assert {pair.relation for pair in pairs} == {
        EQUIVALENT_SHOULD_PASS,
        INVALID_SHOULD_FAIL,
    }
    assert any(pair.transformation == "numeric_decimal_equivalent" for pair in pairs)
    assert all(decision.status == "expected_behavior" for decision in decisions)


def test_exact_answer_modeled_evaluator_defect_cannot_auto_confirm(monkeypatch):
    item = BenchmarkItem(
        item_id="strict",
        raw={},
        gold="6",
        evaluator={"type": "numeric"},
    )
    import benchcore.counterexample_validation as module

    original = module.evaluate_answer

    def reject_decimal(prediction, gold, choices, evaluator):
        if prediction == "6.0":
            return False
        return original(prediction, gold, choices, evaluator)

    monkeypatch.setattr(module, "evaluate_answer", reject_decimal)
    decisions = replay_exact_answer_pairs(item)

    defect = next(row for row in decisions if row.status == "defect_observed")
    assert defect.evidence_tier == "review"
    assert defect.evidence["proof_preconditions"]["official_evaluator"] is False


def test_binomial_upper_tail_is_exact():
    assert binomial_upper_tail(10, 10, 0.5) == pytest.approx(1 / 1024)
    assert binomial_upper_tail(0, 10, 0.5) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        binomial_upper_tail(11, 10, 0.5)
