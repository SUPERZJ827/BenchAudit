"""Cross-domain counterexample validation for benchmark evaluators.

LLMs may propose a mutation, but this module never treats the proposal itself
as proof.  It records the expected relation between a baseline and a minimally
changed variant, validates replay evidence, and applies a family-specific
promotion boundary:

* code and exact-answer evaluators use pass/fail differential observations;
* tables use pinned-source recomputation;
* rubric/workspace evaluators use blinded, order-balanced paired scores; and
* open-ended tasks reuse paired statistics but always remain review-only.

The important common unit is a *counterexample*: a certified intervention plus
an evaluator behavior that violates an explicit expected relation.  A clean
pair is evidence only about that intervention, never proof that the entire
benchmark item is defect-free.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

from .evaluators import (
    CHOICE_LABELS,
    answer_contract,
    answer_values,
    answer_variants,
    choice_label_to_index,
    evaluate_answer,
    parse_number,
    parse_ratio_value,
)
from .execution_attestation import (
    ATTESTATION_PROTOCOL,
    SEPARATE_PROCESS_DOMAIN,
    AttestationStatus,
)
from .schema import BenchmarkItem


OBJECTIVE_FAMILIES = frozenset({"code", "exact_answer", "table", "formal_math"})
SCORED_FAMILIES = frozenset({"rubric", "workspace", "open_ended"})
ALL_FAMILIES = OBJECTIVE_FAMILIES | SCORED_FAMILIES

EQUIVALENT_SHOULD_PASS = "equivalent_should_pass"
INVALID_SHOULD_FAIL = "invalid_should_fail"
DEGRADATION_SHOULD_LOWER = "degradation_should_lower"
IMPROVEMENT_SHOULD_NOT_LOWER = "improvement_should_not_lower"
EQUIVALENT_SHOULD_PRESERVE = "equivalent_should_preserve"
GAMING_SHOULD_NOT_RAISE = "gaming_should_not_raise"
CRITERION_LOCALITY = "criterion_locality"

OBJECTIVE_RELATIONS = frozenset({EQUIVALENT_SHOULD_PASS, INVALID_SHOULD_FAIL})
SCORED_RELATIONS = frozenset({
    DEGRADATION_SHOULD_LOWER,
    IMPROVEMENT_SHOULD_NOT_LOWER,
    EQUIVALENT_SHOULD_PRESERVE,
    GAMING_SHOULD_NOT_RAISE,
    CRITERION_LOCALITY,
})


@dataclass(frozen=True)
class VerificationCapability:
    """One applicable verifier family and the evidence it still needs."""

    family: str
    verifier: str
    priority: int
    automatic_confirmation_possible: bool
    required_evidence: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObjectivePairObservation:
    """Pass/fail behavior for one objective evaluator intervention."""

    pair_id: str
    family: str
    relation: str
    baseline_accepted: bool
    variant_accepted: bool
    relation_certified: bool
    official_evaluator: bool
    transcript_attested: bool
    independent_adjudicator: bool
    execution_transcript_sha256: str
    baseline_sha256: str
    variant_sha256: str
    mutation_operator: str
    mutation_origin: str = "deterministic"
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TableRecomputeObservation:
    """Declared and independently recomputed values from pinned table inputs."""

    item_id: str
    declared_value: float
    recomputed_value: float
    absolute_tolerance: float
    relative_tolerance: float
    source_cells_pinned: bool
    formula_pinned: bool
    transcript_attested: bool
    independent_adjudicator: bool
    official_value_sha256: str
    recompute_transcript_sha256: str
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredPairSpec:
    """Sidecar-only expectation for a rubric/open-ended A/B intervention."""

    pair_id: str
    family: str
    relation: str
    mutation_operator: str
    construction: str
    baseline_sha256: str
    variant_sha256: str
    changed_paths: tuple[str, ...]
    rubric_quote: str
    target_criterion: str | None = None
    expected_min_delta: float = 0.10
    invariance_tolerance: float = 0.03
    explicit_requirement: bool = True
    provenance_hidden: bool = True
    official_evaluator: bool = True
    grader_kind: str = "llm"


@dataclass(frozen=True)
class ScoredPairTrial:
    """One blinded replay. Scores are canonicalized to baseline/variant sides."""

    seed: int
    presented_order: str
    evaluator_id: str
    baseline_score: float
    variant_score: float
    score_max: float = 1.0
    baseline_criteria: Mapping[str, float] = field(default_factory=dict)
    variant_criteria: Mapping[str, float] = field(default_factory=dict)
    criterion_score_max: Mapping[str, float] = field(default_factory=dict)
    transcript_sha256: str = ""
    transcript_attested: bool = False


@dataclass(frozen=True)
class CounterexamplePolicy:
    min_trials: int = 6
    min_violation_rate: float = 0.80
    alpha: float = 0.05
    null_violation_probability: float = 0.50
    require_order_balance: bool = True


@dataclass(frozen=True)
class CounterexampleDecision:
    pair_id: str
    family: str
    status: str
    evidence_tier: str
    proof_kind: str
    confidence: float
    reason: str
    metrics: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExactAnswerPair:
    pair_id: str
    relation: str
    transformation: str
    value: Any
    certificate_sha256: str


def verification_capabilities(item: BenchmarkItem) -> list[VerificationCapability]:
    """Return every applicable verifier route, strongest first.

    Routes are intentionally non-exclusive.  A table question with a scalar
    gold answer benefits from both source recomputation and answer-contract
    mutation; selecting only one would discard useful evidence.
    """

    raw = item.raw if isinstance(item.raw, dict) else {}
    context = item.context if isinstance(item.context, dict) else {}
    evaluator = item.evaluator if isinstance(item.evaluator, dict) else {}
    task_contract = f"{item.task or ''} {item.output_contract or ''}".casefold()
    raw_keys = {str(key).casefold() for key in raw}
    context_keys = {str(key).casefold() for key in context}
    evaluator_type = str(evaluator.get("type") or "").casefold()
    contract_type = (
        str(item.output_contract.get("type") or "").casefold()
        if isinstance(item.output_contract, dict)
        else str(item.output_contract or "").casefold()
    )
    routes: list[VerificationCapability] = []

    workspace = bool(
        {"rubrics", "rubric_types", "file_dep_graph", "tested_capabilities"} & raw_keys
        or "workspace" in task_contract
        or any(key in evaluator for key in ("rubrics", "rubric_types", "output_files"))
    )
    if workspace:
        routes.append(VerificationCapability(
            "workspace",
            "blinded_rubric_counterfactual_replay",
            10,
            False,
            (
                "single-variable mutation certificate",
                "official per-rubric score vectors",
                "order-balanced repeated transcripts",
            ),
            "Workspace/rubric artifacts support sensitivity, invariance, locality, and anti-gaming pairs.",
        ))

    code_context = evaluator.get("code_context")
    code_signals = {
        "test_patch", "fail_to_pass", "pass_to_pass", "tests", "harness", "task_toml",
    } & (raw_keys | context_keys)
    code_detected = bool(
        isinstance(code_context, str)
        or code_signals
        or evaluator_type in {"terminal_bench_verifier", "swebench_tests", "pytest", "unit_tests"}
        or contract_type in {"terminal_task", "git_patch", "code_patch"}
    )
    if code_detected:
        routes.append(VerificationCapability(
            "code",
            "sandboxed_differential_execution",
            20,
            True,
            (
                "certified equivalent or invalid implementation",
                "official harness verdict",
                "independently attested execution transcript",
            ),
            "Executable harness/test signals are present.",
        ))

    table_tokens = ("table", "dataframe", "spreadsheet", "csv", "row", "column", "cell")
    explicit_table = bool(
        {"table", "tables", "spreadsheet", "csv", "dataframe"} & context_keys
        or any(token in contract_type or token in evaluator_type for token in table_tokens)
        or workspace
    )
    if any(token in task_contract for token in table_tokens) and (not code_detected or explicit_table):
        routes.append(VerificationCapability(
            "table",
            "pinned_source_recomputation",
            30,
            True,
            (
                "pinned source cells",
                "pinned formula or transformation",
                "independently attested recompute transcript",
            ),
            "Table-like language supports value and constraint recomputation.",
        ))

    math_tokens = (" prove ", " theorem ", " lemma ", " integral ", " derivative ", " equation ")
    padded = f" {task_contract} "
    formal_signal = any(token in padded for token in math_tokens) or any(
        token in task_contract for token in ("≤", "≥", "∫", "∑", "√")
    )
    explicit_formal = any(
        token in contract_type or token in evaluator_type
        for token in ("lean", "formal", "proof", "smt", "symbolic")
    )
    if formal_signal and (not code_detected and not workspace or explicit_formal):
        routes.append(VerificationCapability(
            "formal_math",
            "symbolic_smt_or_formal_replay",
            40,
            True,
            ("formalized statement", "solver proof transcript", "kernel or solver identity"),
            "The task contains formal mathematical signals.",
        ))

    scalar_gold = bool(
        item.gold not in (None, "", [], {})
        and contract_type not in {
            "workspace", "workspace_files", "artifact_files", "terminal_task",
            "git_patch", "code_patch",
        }
        and evaluator_type not in {
            "workspacebench_rubric", "agent_as_a_judge", "rubric_judge",
            "terminal_bench_verifier", "swebench_tests",
        }
    )
    if scalar_gold:
        routes.append(VerificationCapability(
            "exact_answer",
            "answer_contract_metamorphic_and_mutation_replay",
            50,
            True,
            ("declared answer contract", "equivalent and invalid answer certificates"),
            "A gold answer is available for deterministic contract probes.",
        ))

    if not routes:
        routes.append(VerificationCapability(
            "open_ended",
            "blinded_multi_judge_counterfactual_review",
            100,
            False,
            (
                "single-variable mutation certificate",
                "order-balanced repeated judge transcripts",
            ),
            "No objective verifier is available; only conservative paired review is possible.",
        ))
    return sorted(routes, key=lambda route: (route.priority, route.family))


def adjudicate_objective_pair(
    observation: ObjectivePairObservation,
    attestation_status: AttestationStatus | None = None,
) -> CounterexampleDecision:
    """Adjudicate a code/exact/table/formal pass/fail differential."""

    errors = _validate_objective_observation(observation)
    if errors:
        return _invalid_decision(observation.pair_id, observation.family, errors)

    violated = (
        observation.baseline_accepted
        and (
            observation.relation == EQUIVALENT_SHOULD_PASS
            and not observation.variant_accepted
            or observation.relation == INVALID_SHOULD_FAIL
            and observation.variant_accepted
        )
    )
    if not observation.baseline_accepted:
        return CounterexampleDecision(
            observation.pair_id,
            observation.family,
            "baseline_failed",
            "unknown",
            "unusable_counterexample",
            0.0,
            "The evaluator rejected the baseline, so the differential cannot isolate the mutation.",
            evidence=dict(observation.evidence),
        )
    if not violated:
        return CounterexampleDecision(
            observation.pair_id,
            observation.family,
            "expected_behavior",
            "unknown",
            "counterexample_not_observed",
            1.0,
            "The evaluator behaved consistently with this certified intervention.",
            metrics={"baseline_accepted": True, "variant_accepted": observation.variant_accepted},
            evidence=dict(observation.evidence),
        )

    trusted_attestation = _attestation_matches(
        attestation_status, observation.execution_transcript_sha256,
    )
    objective_proof = all((
        observation.relation_certified,
        observation.official_evaluator,
        trusted_attestation,
        observation.independent_adjudicator,
    ))
    return CounterexampleDecision(
        observation.pair_id,
        observation.family,
        "defect_observed",
        "confirmed" if objective_proof else "review",
        (
            "attested_objective_counterexample"
            if objective_proof
            else "unattested_or_semantic_counterexample"
        ),
        1.0 if objective_proof else 0.72,
        (
            "The official evaluator violates a certified pass/fail relation."
            if objective_proof
            else "A differential was observed, but at least one proof precondition is not objective."
        ),
        metrics={
            "baseline_accepted": observation.baseline_accepted,
            "variant_accepted": observation.variant_accepted,
            "relation": observation.relation,
        },
        evidence={
            **dict(observation.evidence),
            "baseline_sha256": observation.baseline_sha256,
            "variant_sha256": observation.variant_sha256,
            "mutation_operator": observation.mutation_operator,
            "mutation_origin": observation.mutation_origin,
            "execution_transcript_sha256": observation.execution_transcript_sha256,
            "trusted_attestation": (
                attestation_status.as_evidence() if attestation_status is not None else None
            ),
            "proof_preconditions": {
                "relation_certified": observation.relation_certified,
                "official_evaluator": observation.official_evaluator,
                "claimed_transcript_attested": observation.transcript_attested,
                "trusted_attestation_verified": trusted_attestation,
                "independent_adjudicator": observation.independent_adjudicator,
            },
        },
    )


def adjudicate_table_recompute(
    observation: TableRecomputeObservation,
    attestation_status: AttestationStatus | None = None,
) -> CounterexampleDecision:
    """Compare a declared table value with an independently replayed value."""

    errors: list[str] = []
    for name, value in (
        ("declared_value", observation.declared_value),
        ("recomputed_value", observation.recomputed_value),
        ("absolute_tolerance", observation.absolute_tolerance),
        ("relative_tolerance", observation.relative_tolerance),
    ):
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            errors.append(f"{name} must be finite")
    if observation.absolute_tolerance < 0 or observation.relative_tolerance < 0:
        errors.append("tolerances must be non-negative")
    if not _is_sha256(observation.official_value_sha256):
        errors.append("official_value_sha256 is invalid")
    if not _is_sha256(observation.recompute_transcript_sha256):
        errors.append("recompute_transcript_sha256 is invalid")
    if errors:
        return _invalid_decision(observation.item_id, "table", errors)

    tolerance = max(
        float(observation.absolute_tolerance),
        float(observation.relative_tolerance)
        * max(1.0, abs(float(observation.declared_value)), abs(float(observation.recomputed_value))),
    )
    delta = abs(float(observation.declared_value) - float(observation.recomputed_value))
    mismatch = delta > tolerance
    trusted_attestation = _attestation_matches(
        attestation_status, observation.recompute_transcript_sha256,
    )
    proof_ready = all((
        observation.source_cells_pinned,
        observation.formula_pinned,
        trusted_attestation,
        observation.independent_adjudicator,
    ))
    if not mismatch:
        return CounterexampleDecision(
            observation.item_id,
            "table",
            "expected_behavior",
            "unknown",
            "recompute_agreement",
            1.0,
            "The declared value agrees with the pinned-source recomputation within tolerance.",
            metrics={"absolute_delta": delta, "effective_tolerance": tolerance},
            evidence=dict(observation.evidence),
        )
    return CounterexampleDecision(
        observation.item_id,
        "table",
        "defect_observed",
        "confirmed" if proof_ready else "review",
        "attested_table_recompute" if proof_ready else "incomplete_table_recompute",
        1.0 if proof_ready else 0.72,
        (
            "The declared value disagrees with an independently attested pinned-source recomputation."
            if proof_ready
            else "A value mismatch was observed, but source/formula/transcript provenance is incomplete."
        ),
        metrics={"absolute_delta": delta, "effective_tolerance": tolerance},
        evidence={
            **dict(observation.evidence),
            "declared_value": observation.declared_value,
            "recomputed_value": observation.recomputed_value,
            "trusted_attestation": (
                attestation_status.as_evidence() if attestation_status is not None else None
            ),
            "proof_preconditions": {
                "source_cells_pinned": observation.source_cells_pinned,
                "formula_pinned": observation.formula_pinned,
                "claimed_transcript_attested": observation.transcript_attested,
                "trusted_attestation_verified": trusted_attestation,
                "independent_adjudicator": observation.independent_adjudicator,
            },
        },
    )


def adjudicate_scored_pair(
    spec: ScoredPairSpec,
    trials: Sequence[ScoredPairTrial],
    policy: CounterexamplePolicy | None = None,
    *,
    verified_transcript_hashes: frozenset[str] = frozenset(),
) -> CounterexampleDecision:
    """Test a rubric/open-ended expected relation with repeated blinded scores."""

    policy = policy or CounterexamplePolicy()
    errors = _validate_scored_inputs(spec, trials, policy)
    if errors:
        return _invalid_decision(spec.pair_id, spec.family, errors)

    deltas = [_scored_delta(spec, trial) for trial in trials]
    margins = [_scored_violation_margin(spec, trial) for trial in trials]
    violations = [margin > 0.0 for margin in margins]
    violation_count = sum(violations)
    violation_rate = violation_count / len(trials)
    p_value = binomial_upper_tail(
        violation_count,
        len(trials),
        policy.null_violation_probability,
    )
    mean_delta = fmean(deltas)
    mean_margin = fmean(margins)
    observed = bool(
        violation_rate >= policy.min_violation_rate
        and p_value <= policy.alpha
        and mean_margin > 0.0
    )
    metrics = {
        "trials": len(trials),
        "violations": violation_count,
        "violation_rate": violation_rate,
        "binomial_upper_tail_p": p_value,
        "mean_normalized_delta": mean_delta,
        "mean_violation_margin": mean_margin,
        "min_normalized_delta": min(deltas),
        "max_normalized_delta": max(deltas),
        "evaluated_score_scope": spec.target_criterion or "total",
        "orders": {
            "AB": sum(trial.presented_order == "AB" for trial in trials),
            "BA": sum(trial.presented_order == "BA" for trial in trials),
        },
        "claimed_attested_transcripts": sum(trial.transcript_attested for trial in trials),
        "trusted_verified_transcripts": sum(
            trial.transcript_sha256 in verified_transcript_hashes for trial in trials
        ),
    }
    evidence = {
        "relation": spec.relation,
        "mutation_operator": spec.mutation_operator,
        "construction": spec.construction,
        "baseline_sha256": spec.baseline_sha256,
        "variant_sha256": spec.variant_sha256,
        "changed_paths": list(spec.changed_paths),
        "rubric_quote": spec.rubric_quote,
        "target_criterion": spec.target_criterion,
        "transcript_sha256": [trial.transcript_sha256 for trial in trials],
        "evaluator_ids": sorted({trial.evaluator_id for trial in trials}),
    }
    if not observed:
        return CounterexampleDecision(
            spec.pair_id,
            spec.family,
            "expected_behavior",
            "unknown",
            "paired_counterexample_not_observed",
            1.0 - min(1.0, p_value),
            "The repeated paired scores do not establish a stable violation of the expected relation.",
            metrics=metrics,
            evidence=evidence,
        )

    deterministic_proof = all((
        spec.family in {"rubric", "workspace"},
        spec.construction == "deterministic",
        spec.explicit_requirement,
        spec.provenance_hidden,
        spec.official_evaluator,
        spec.grader_kind == "deterministic",
        all(trial.transcript_sha256 in verified_transcript_hashes for trial in trials),
    ))
    # An LLM grader can establish a stable behavior of that grader, but not the
    # semantic truth of the rubric.  Open-ended tasks are never auto-promoted.
    tier = "confirmed" if deterministic_proof else "review"
    proof_kind = (
        "attested_deterministic_evaluator_behavior"
        if deterministic_proof
        else "repeated_blind_paired_evaluator_behavior"
    )
    return CounterexampleDecision(
        spec.pair_id,
        spec.family,
        "defect_observed",
        tier,
        proof_kind,
        _paired_confidence(violation_rate, p_value, tier),
        (
            "The deterministic official evaluator reproducibly violates an explicit paired relation."
            if deterministic_proof
            else "The paired effect is stable, but semantic or LLM-grader uncertainty requires review."
        ),
        metrics=metrics,
        evidence=evidence,
    )


def build_exact_answer_pairs(item: BenchmarkItem) -> list[ExactAnswerPair]:
    """Create deterministic equivalent and intentionally invalid answer pairs."""

    if item.gold in (None, "", [], {}):
        return []
    candidates: list[tuple[str, str, Any]] = []
    for name, value in _equivalent_answer_variants(item):
        candidates.append((EQUIVALENT_SHOULD_PASS, name, value))
    candidates.extend(
        (INVALID_SHOULD_FAIL, name, value)
        for name, value in _invalid_answer_variants(item)
    )

    seen: set[str] = set()
    pairs: list[ExactAnswerPair] = []
    gold_key = _canonical_sha256(item.gold)
    for relation, name, value in candidates:
        payload = {
            "item_id": item.item_id,
            "relation": relation,
            "transformation": name,
            "value": value,
            "gold": item.gold,
            "evaluator": item.evaluator,
            "output_contract": item.output_contract,
        }
        digest = _canonical_sha256(payload)
        value_key = _canonical_sha256({"relation": relation, "value": value})
        if _canonical_sha256(value) == gold_key:
            continue
        if value_key in seen:
            continue
        seen.add(value_key)
        pairs.append(ExactAnswerPair(
            pair_id=f"{item.item_id}:{digest[:16]}",
            relation=relation,
            transformation=name,
            value=value,
            certificate_sha256=digest,
        ))
    return pairs


def replay_exact_answer_pairs(item: BenchmarkItem) -> list[CounterexampleDecision]:
    """Replay deterministic answer probes against BenchAudit's declared model.

    This models the declared evaluator contract; it does not claim to have run
    arbitrary benchmark-owned code, so observed defects intentionally remain
    review-only unless another layer binds them to the official evaluator.
    """

    baseline = evaluate_answer(item.gold, item.gold, item.choices, item.evaluator)
    decisions: list[CounterexampleDecision] = []
    for pair in build_exact_answer_pairs(item):
        accepted = evaluate_answer(pair.value, item.gold, item.choices, item.evaluator)
        observation = ObjectivePairObservation(
            pair_id=pair.pair_id,
            family="exact_answer",
            relation=pair.relation,
            baseline_accepted=baseline,
            variant_accepted=accepted,
            relation_certified=True,
            official_evaluator=False,
            transcript_attested=True,
            independent_adjudicator=True,
            execution_transcript_sha256=_canonical_sha256({
                "item_id": item.item_id,
                "pair_id": pair.pair_id,
                "baseline_accepted": baseline,
                "variant_accepted": accepted,
            }),
            baseline_sha256=_canonical_sha256(item.gold),
            variant_sha256=_canonical_sha256(pair.value),
            mutation_operator=pair.transformation,
            evidence={
                "certificate_sha256": pair.certificate_sha256,
                "evaluator": item.evaluator,
                "output_contract": item.output_contract,
            },
        )
        decisions.append(adjudicate_objective_pair(observation))
    return decisions


def binomial_upper_tail(successes: int, trials: int, probability: float) -> float:
    """Exact P(X >= successes) for X ~ Binomial(trials, probability)."""

    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("successes must satisfy 0 <= successes <= trials")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    return sum(
        math.comb(trials, count)
        * probability**count
        * (1.0 - probability) ** (trials - count)
        for count in range(successes, trials + 1)
    )


def _validate_objective_observation(observation: ObjectivePairObservation) -> list[str]:
    errors: list[str] = []
    if observation.family not in OBJECTIVE_FAMILIES:
        errors.append(f"unsupported objective family: {observation.family}")
    if observation.relation not in OBJECTIVE_RELATIONS:
        errors.append(f"unsupported objective relation: {observation.relation}")
    if not observation.pair_id:
        errors.append("pair_id is required")
    if not observation.mutation_operator:
        errors.append("mutation_operator is required")
    if not _is_sha256(observation.baseline_sha256):
        errors.append("baseline_sha256 is invalid")
    if not _is_sha256(observation.variant_sha256):
        errors.append("variant_sha256 is invalid")
    if observation.baseline_sha256 == observation.variant_sha256:
        errors.append("baseline and variant hashes must differ")
    if not _is_sha256(observation.execution_transcript_sha256):
        errors.append("execution_transcript_sha256 is invalid")
    return errors


def _validate_scored_inputs(
    spec: ScoredPairSpec,
    trials: Sequence[ScoredPairTrial],
    policy: CounterexamplePolicy,
) -> list[str]:
    errors: list[str] = []
    if spec.family not in SCORED_FAMILIES:
        errors.append(f"unsupported scored family: {spec.family}")
    if spec.relation not in SCORED_RELATIONS:
        errors.append(f"unsupported scored relation: {spec.relation}")
    if not spec.pair_id:
        errors.append("pair_id is required")
    if not spec.mutation_operator:
        errors.append("mutation_operator is required")
    if spec.construction not in {"deterministic", "llm", "hybrid"}:
        errors.append("construction must be deterministic, llm, or hybrid")
    if not _is_sha256(spec.baseline_sha256) or not _is_sha256(spec.variant_sha256):
        errors.append("baseline and variant SHA-256 values are required")
    elif spec.baseline_sha256 == spec.variant_sha256:
        errors.append("baseline and variant hashes must differ")
    if not spec.changed_paths:
        errors.append("changed_paths must identify the controlled intervention")
    if not spec.rubric_quote.strip():
        errors.append("rubric_quote is required")
    if spec.expected_min_delta < 0 or spec.invariance_tolerance < 0:
        errors.append("delta thresholds must be non-negative")
    if spec.relation == CRITERION_LOCALITY and not spec.target_criterion:
        errors.append("criterion_locality requires target_criterion")
    if policy.min_trials <= 0:
        errors.append("min_trials must be positive")
    if not 0.5 <= policy.min_violation_rate <= 1.0:
        errors.append("min_violation_rate must be in [0.5, 1]")
    if not 0.0 < policy.alpha < 1.0:
        errors.append("alpha must be in (0, 1)")
    if len(trials) < policy.min_trials:
        errors.append(f"at least {policy.min_trials} trials are required")
    if len({trial.seed for trial in trials}) != len(trials):
        errors.append("trial seeds must be unique")
    orders = {trial.presented_order for trial in trials}
    if not orders <= {"AB", "BA"}:
        errors.append("presented_order must be AB or BA")
    if policy.require_order_balance and not {"AB", "BA"} <= orders:
        errors.append("both AB and BA presentation orders are required")
    for index, trial in enumerate(trials):
        if not trial.evaluator_id:
            errors.append(f"trial {index} evaluator_id is required")
        if (
            not isinstance(trial.score_max, (int, float))
            or not math.isfinite(float(trial.score_max))
            or trial.score_max <= 0
        ):
            errors.append(f"trial {index} score_max must be positive and finite")
            continue
        for name, score in (
            ("baseline_score", trial.baseline_score),
            ("variant_score", trial.variant_score),
        ):
            if not isinstance(score, (int, float)) or not math.isfinite(float(score)):
                errors.append(f"trial {index} {name} must be finite")
            elif not 0.0 <= float(score) <= float(trial.score_max):
                errors.append(f"trial {index} {name} is outside [0, score_max]")
        if not _is_sha256(trial.transcript_sha256):
            errors.append(f"trial {index} transcript_sha256 is invalid")
        if spec.target_criterion is not None:
            baseline_keys = set(trial.baseline_criteria)
            variant_keys = set(trial.variant_criteria)
            if baseline_keys != variant_keys or spec.target_criterion not in baseline_keys:
                errors.append(
                    f"trial {index} criterion vectors must have identical keys including target_criterion"
                )
            for key, score in [
                *trial.baseline_criteria.items(), *trial.variant_criteria.items(),
            ]:
                criterion_max = trial.criterion_score_max.get(key, trial.score_max)
                if (
                    not isinstance(criterion_max, (int, float))
                    or not math.isfinite(float(criterion_max))
                    or criterion_max <= 0
                ):
                    errors.append(f"trial {index} criterion {key!r} maximum must be positive and finite")
                    continue
                if not isinstance(score, (int, float)) or not math.isfinite(float(score)):
                    errors.append(f"trial {index} criterion {key!r} must be finite")
                elif not 0.0 <= float(score) <= float(criterion_max):
                    errors.append(f"trial {index} criterion {key!r} is outside score range")
    return errors


def _scored_violation_margin(spec: ScoredPairSpec, trial: ScoredPairTrial) -> float:
    delta = _scored_delta(spec, trial)
    if spec.relation == DEGRADATION_SHOULD_LOWER:
        return delta + spec.expected_min_delta
    if spec.relation == IMPROVEMENT_SHOULD_NOT_LOWER:
        return -delta - spec.invariance_tolerance
    if spec.relation == EQUIVALENT_SHOULD_PRESERVE:
        return abs(delta) - spec.invariance_tolerance
    if spec.relation == GAMING_SHOULD_NOT_RAISE:
        return delta - spec.invariance_tolerance
    if spec.relation == CRITERION_LOCALITY:
        off_target = [
            abs(
                float(trial.variant_criteria[key])
                - float(trial.baseline_criteria[key])
            ) / float(trial.criterion_score_max.get(key, trial.score_max))
            for key in trial.baseline_criteria
            if key != spec.target_criterion
        ]
        return (max(off_target) if off_target else 0.0) - spec.invariance_tolerance
    raise ValueError(f"unsupported relation: {spec.relation}")


def _scored_delta(spec: ScoredPairSpec, trial: ScoredPairTrial) -> float:
    if spec.target_criterion is not None and spec.relation != CRITERION_LOCALITY:
        baseline = float(trial.baseline_criteria[spec.target_criterion])
        variant = float(trial.variant_criteria[spec.target_criterion])
        scale = float(
            trial.criterion_score_max.get(spec.target_criterion, trial.score_max)
        )
    else:
        baseline = float(trial.baseline_score)
        variant = float(trial.variant_score)
        scale = float(trial.score_max)
    return (variant - baseline) / scale


def _invalid_answer_variants(item: BenchmarkItem) -> list[tuple[str, Any]]:
    contract = answer_contract(item.gold, item.choices, item.evaluator, item.output_contract)
    if item.choices:
        gold_index = choice_label_to_index(item.gold, item.choices)
        return [
            (f"non_gold_choice_{index}", CHOICE_LABELS[index])
            for index in range(min(len(item.choices), len(CHOICE_LABELS)))
            if index != gold_index
        ]
    if contract["cardinality"] == "set":
        values = answer_values(item.gold)
        return [("drop_set_member", values[:-1])] if len(values) > 1 else []
    if contract["kind"] == "ratio":
        ratio = parse_ratio_value(item.gold)
        return [("ratio_plus_one", ratio + 1.0)] if ratio is not None else []
    number = parse_number(item.gold)
    if number is not None:
        return [
            ("numeric_plus_one", number + 1.0),
            ("numeric_negated", -number if number != 0 else 1.0),
        ]
    return [
        ("empty_answer", ""),
        ("unrelated_sentinel", "__BENCHCORE_INTENTIONALLY_WRONG__"),
    ]


def _equivalent_answer_variants(item: BenchmarkItem) -> list[tuple[str, Any]]:
    variants = answer_variants(
        item.gold, item.choices, item.evaluator, item.output_contract,
    )
    contract = answer_contract(
        item.gold, item.choices, item.evaluator, item.output_contract,
    )
    if contract["kind"] == "numeric" and contract["cardinality"] == "single":
        number = parse_number(item.gold)
        if number is not None:
            variants.append((
                "numeric_decimal_equivalent",
                f"{int(number)}.0" if float(number).is_integer() else f"{number}0",
            ))
    if contract["kind"] == "ratio" and contract["cardinality"] == "single":
        text = str(item.gold).strip()
        if ":" in text:
            variants.append(("ratio_fraction_equivalent", text.replace(":", "/", 1)))
        ratio = parse_ratio_value(item.gold)
        if ratio is not None:
            variants.append(("ratio_decimal_equivalent", str(ratio)))
    if contract["kind"] == "normalized_exact" and contract["cardinality"] == "single":
        variants.append(("surrounding_whitespace", f"  {item.gold}  "))
    return variants


def _paired_confidence(violation_rate: float, p_value: float, tier: str) -> float:
    base = 0.70 + 0.20 * violation_rate + 0.10 * (1.0 - min(1.0, p_value / 0.05))
    return min(1.0 if tier == "confirmed" else 0.94, base)


def _attestation_matches(
    status: AttestationStatus | None,
    transcript_sha256: str,
) -> bool:
    if status is None or not isinstance(status.attestation, dict):
        return False
    return bool(
        status.verified is True
        and status.trust_domain == SEPARATE_PROCESS_DOMAIN
        and status.payload_sha256 == transcript_sha256
        and status.attestation.get("protocol") == ATTESTATION_PROTOCOL
        and status.attestation.get("payload_sha256") == transcript_sha256
    )


def _invalid_decision(pair_id: str, family: str, errors: Iterable[str]) -> CounterexampleDecision:
    values = tuple(dict.fromkeys(str(error) for error in errors))
    return CounterexampleDecision(
        pair_id,
        family,
        "invalid_evidence",
        "unknown",
        "schema_or_provenance_failure",
        0.0,
        "; ".join(values),
        evidence={"validation_errors": list(values)},
    )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "").casefold()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)
