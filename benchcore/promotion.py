"""Fail-closed evidence promotion for benchmark audit findings.

Confidence is not proof.  In particular, an LLM vote can prioritize review but
cannot turn a semantic judgement into an objectively confirmed benchmark bug.
This module is the single authority that maps observations to evidence tiers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .schema import BenchmarkItem, Violation


EVIDENCE_TIERS = frozenset({"confirmed", "review", "unknown"})

PROOF_SCHEMA_VERSION = "1.0"

SEMANTIC_OR_MODEL_METHODS = frozenset({
    "grounded_rubric_consistency",
    "rubric_output_contract_consistency",
    "rubric_coverage",
    "workspace_rubric_grounding",
    "value_recompute",
    "code_exec_verifier",
    "differential_solver",
})

MAPPING_SENSITIVE_ARTIFACTS = {
    "task_specification": "task",
    "context_attachment": "context",
    "oracle_ground_truth": "gold",
    "expected_output": "output_contract",
    "evaluator": "evaluator",
}


@dataclass(frozen=True)
class PromotionDecision:
    tier: str
    proof_kind: str
    reason: str


ProofValidator = Callable[[Violation, BenchmarkItem | None], bool]


def _schema_valid(violation: Violation, item: BenchmarkItem | None) -> bool:
    return violation.evidence.get("proof_schema_version") == PROOF_SCHEMA_VERSION


def _sha256(value: Any) -> bool:
    text = str(value or "").casefold()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _commit(value: Any) -> bool:
    text = str(value or "").casefold()
    return len(text) == 40 and all(char in "0123456789abcdef" for char in text)


def _task_absent(violation: Violation, item: BenchmarkItem | None) -> bool:
    return bool(item is not None and not str(item.task or "").strip())


def _invalid_choice_gold(violation: Violation, item: BenchmarkItem | None) -> bool:
    if item is None or not item.choices:
        return False
    from .evaluators import choice_label_to_index

    return choice_label_to_index(item.gold, item.choices) is None


def _arithmetic_replay(violation: Violation, item: BenchmarkItem | None) -> bool:
    evidence = violation.evidence
    if item is None:
        return False
    from .checkers import _extract_simple_arithmetic_value
    from .evaluators import parse_number

    replayed = _extract_simple_arithmetic_value(str(item.task or ""))
    gold_number = parse_number(item.gold)
    return bool(
        str(item.task or "").strip()
        and replayed is not None
        and gold_number is not None
        and abs(replayed - gold_number) > 1e-9
        and evidence.get("gold") == item.gold
        and evidence.get("task") == item.task
        and isinstance(evidence.get("computed_value"), (int, float))
        and abs(float(evidence["computed_value"]) - replayed) <= 1e-12
        and evidence.get("safe_expression_replayed") is True
    )


def _declared_evaluator_replay(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    evidence = violation.evidence
    if item is None or evidence.get("gold") != item.gold:
        return False
    from .evaluators import evaluate_answer

    if violation.defect_type == "gold_rejected_by_evaluator":
        return bool(
            evidence.get("evaluator") == item.evaluator
            and evidence.get("choices") == item.choices
            and not evaluate_answer(
                item.gold, item.gold, item.choices, item.evaluator,
            )
        )
    if violation.defect_type == "overstrict_evaluator":
        aliases = evidence.get("aliases_rejected")
        return bool(
            isinstance(aliases, list)
            and aliases
            and all(alias in item.aliases for alias in aliases)
            and evidence.get("evaluator") == item.evaluator
            and all(
                not evaluate_answer(alias, item.gold, item.choices, item.evaluator)
                for alias in aliases
            )
        )
    return False


def _contract_replay(violation: Violation, item: BenchmarkItem | None) -> bool:
    evidence = violation.evidence
    if item is None:
        return False
    from .evaluators import infer_evaluator_type, normalize_text
    from .methods import _is_scalar_answer_contract

    if not _is_scalar_answer_contract(item):
        return False
    contract = normalize_text(item.output_contract)
    kind = infer_evaluator_type(item.gold, item.choices, item.evaluator)
    mismatch = bool(
        (
            item.choices
            and contract
            and any(token in contract for token in ("numeric", "number", "free text"))
        )
        or (
            "json" in contract
            and kind in {"exact", "normalized_exact", "numeric", "choice"}
        )
        or (
            any(token in contract for token in ("numeric", "number"))
            and kind == "choice"
        )
    )
    return bool(
        mismatch
        and evidence.get("output_contract") == item.output_contract
        and evidence.get("evaluator") == item.evaluator
        and evidence.get("inferred_evaluator") == kind
    )


def _workspace_manifest_replay(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    rows = violation.evidence.get("unresolved_manifest_entries")
    return bool(
        isinstance(rows, list) and rows
        and _workspace_live_replay_matches(
            violation, item, ("unresolved_manifest_entries",)
        )
    )


def _workspace_dependency_replay(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    rows = violation.evidence.get("dangling_edges")
    return bool(
        isinstance(rows, list)
        and rows
        and violation.evidence.get("workspace_inventory_complete") is True
        and _workspace_live_replay_matches(
            violation, item, ("dangling_edges", "workspace_inventory_complete")
        )
    )


def _workspace_metadata_contract(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    evidence = violation.evidence
    valid = bool(
        isinstance(evidence.get("raw_output_files"), list)
        and isinstance(evidence.get("contract_required_files"), list)
        and evidence["raw_output_files"] != evidence["contract_required_files"]
    )
    return valid and _workspace_live_replay_matches(
        violation, item, ("raw_output_files", "contract_required_files")
    )


def _workspace_metadata_evaluator(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    evidence = violation.evidence
    if "raw_rubric_count" in evidence:
        return bool(
            isinstance(evidence.get("raw_rubric_count"), int)
            and isinstance(evidence.get("evaluator_rubric_count"), int)
            and _sha256(evidence.get("raw_rubrics_sha256"))
            and _sha256(evidence.get("evaluator_rubrics_sha256"))
            and evidence["raw_rubrics_sha256"]
            != evidence["evaluator_rubrics_sha256"]
            and _workspace_live_replay_matches(
                violation,
                item,
                (
                    "raw_rubric_count", "evaluator_rubric_count",
                    "raw_rubrics_sha256", "evaluator_rubrics_sha256",
                ),
            )
        )
    return bool(
        isinstance(evidence.get("rubric_count"), int)
        and isinstance(evidence.get("rubric_type_count"), int)
        and evidence["rubric_count"] != evidence["rubric_type_count"]
        and _workspace_live_replay_matches(
            violation, item, ("rubric_count", "rubric_type_count")
        )
    )


def _workspace_live_replay_matches(
    violation: Violation,
    item: BenchmarkItem | None,
    keys: tuple[str, ...],
) -> bool:
    """Recompute an invariant from the live canonical item and pinned files.

    Promotion must not trust a payload merely because it has the expected
    shape.  The import is deliberately local to avoid the checker/promotion
    module cycle during startup.
    """

    if item is None:
        return False
    from .workspace_invariants import collect_workspace_invariant_issues

    trusted_roots = getattr(item, "_workspace_replay_allowed_roots", None)
    if trusted_roots is None:
        trusted_roots = ()
    if not isinstance(trusted_roots, tuple) or not all(
        hasattr(path, "resolve") for path in trusted_roots
    ):
        return False
    if (
        violation.evidence.get("evidence_level") == "filesystem_manifest_replay"
        and not trusted_roots
    ):
        return False

    # Promotion replay never needs to parse file contents; the solution-leak
    # scanner is a separate review-only path and is disabled here.
    for issue in collect_workspace_invariant_issues(
        item,
        allowed_roots=trusted_roots,
        include_solution_leak_scan=False,
    ):
        if issue.defect_type != violation.defect_type:
            continue
        if issue.evidence.get("evidence_level") != violation.evidence.get(
            "evidence_level"
        ):
            continue
        if all(issue.evidence.get(key) == violation.evidence.get(key) for key in keys):
            return True
    return False


def _workspace_visibility_replay(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    evidence = violation.evidence
    visibility = evidence.get("visibility")
    return bool(
        isinstance(visibility, dict)
        and all(
            visibility.get(key) is True
            for key in (
                "task_package_present", "agent_visible",
                "evaluator_visible", "visibility_verified",
            )
        )
        and _sha256(evidence.get("task_package_sha256"))
        and _sha256(evidence.get("archive_central_directory_sha256"))
        and _sha256(evidence.get("visibility_transcript_sha256"))
        and _commit(evidence.get("archive_revision"))
        and _commit(evidence.get("runner_commit"))
        and bool(evidence.get("archive_member"))
        and evidence.get("online_reverified") is True
    )


def _execution_gold_replay(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    evidence = violation.evidence
    harness = evidence.get("harness")
    return bool(
        isinstance(harness, dict)
        and (harness.get("pass") is False or harness.get("string_pass") is False)
        and all(
            _sha256(evidence.get(key))
            for key in (
                "driver_sha256", "reference_code_sha256", "code_context_sha256",
            )
        )
        and _execution_attestation_valid(evidence)
    )


def _execution_equivalent_replay(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    evidence = violation.evidence
    harness = evidence.get("harness")
    return bool(
        isinstance(harness, dict)
        and harness.get("pass") is False
        and evidence.get("assumption_satisfied") is True
        and evidence.get("same_inputs_replayed") is True
        and evidence.get("gold_instrumentation_consistent") is True
        and _sha256(evidence.get("probe_code_sha256"))
        and all(
            _sha256(evidence.get(key))
            for key in (
                "driver_sha256", "reference_code_sha256", "code_context_sha256",
            )
        )
        and _execution_attestation_valid(evidence)
    )


def _execution_mutant_replay(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    evidence = violation.evidence
    harness = evidence.get("harness")
    diff_case = evidence.get("diff_case")
    return bool(
        isinstance(harness, dict)
        and harness.get("pass") is True
        and harness.get("string_pass", True) is True
        and isinstance(diff_case, dict)
        and diff_case.get("loose_differs") is True
        and evidence.get("assumption_satisfied") is True
        and evidence.get("same_inputs_replayed") is True
        and evidence.get("gold_instrumentation_consistent") is True
        and _sha256(evidence.get("probe_code_sha256"))
        and all(
            _sha256(evidence.get(key))
            for key in (
                "driver_sha256", "reference_code_sha256", "code_context_sha256",
            )
        )
        and _execution_attestation_valid(evidence)
    )


def _execution_attestation_valid(evidence: dict[str, Any]) -> bool:
    """Prevent a benchmark-supplied trust-domain string from enabling proof.

    The checker sets this only after a configured external verifier accepts the
    exact canonical transcript.  Promotion repeats the structural checks so a
    stale/manual report cannot bypass that boundary.
    """
    attestation = evidence.get("execution_attestation")
    return bool(
        evidence.get("adjudicator_trust_domain") == "separate_process_v1"
        and evidence.get("execution_attestation_verified") is True
        and _sha256(evidence.get("execution_transcript_sha256"))
        and isinstance(attestation, dict)
        and attestation.get("protocol") == "benchaudit-execution-attestation-v1"
        and attestation.get("payload_sha256")
        == evidence.get("execution_transcript_sha256")
    )


def _dataset_duplicate_id(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    evidence = violation.evidence
    return bool(
        str(evidence.get("item_id") or "") == violation.item_id
        and isinstance(evidence.get("count"), int)
        and evidence["count"] > 1
        and isinstance(evidence.get("target_row_uids"), list)
        and len(evidence["target_row_uids"]) == evidence["count"]
        and len(set(evidence["target_row_uids"])) == evidence["count"]
        and violation.row_uid in evidence["target_row_uids"]
    )


def _dataset_conflicting_oracle(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    evidence = violation.evidence
    return bool(
        isinstance(evidence.get("item_ids"), list)
        and len(evidence["item_ids"]) > 1
        and isinstance(evidence.get("gold_values"), list)
        and len(evidence["gold_values"]) > 1
        and isinstance(evidence.get("target_row_uids"), list)
        and len(evidence["target_row_uids"]) > 1
        and len(set(evidence["target_row_uids"])) == len(evidence["target_row_uids"])
        and violation.row_uid in evidence["target_row_uids"]
    )


def _dataset_duplicate_id_live(
    violation: Violation,
    items: list[BenchmarkItem],
) -> bool:
    evidence = violation.evidence
    group = [item for item in items if item.item_id == violation.item_id]
    expected_uids = [item.row_uid for item in group]
    return bool(
        len(group) > 1
        and all(uid is not None for uid in expected_uids)
        and evidence.get("item_id") == violation.item_id
        and evidence.get("count") == len(group)
        and evidence.get("target_row_uids") == expected_uids
        and violation.row_uid in expected_uids
    )


def _dataset_conflicting_oracle_live(
    violation: Violation,
    items: list[BenchmarkItem],
) -> bool:
    from .methods import _item_signature, _stable_value

    if violation.row_uid is None:
        return False
    source = next(
        (item for item in items if item.row_uid == violation.row_uid),
        None,
    )
    if source is None:
        return False
    signature = _item_signature(source)
    group = [item for item in items if _item_signature(item) == signature]
    expected_uids = [item.row_uid for item in group]
    expected_golds = sorted({_stable_value(item.gold) for item in group})
    return bool(
        len(group) > 1
        and len(expected_golds) > 1
        and all(uid is not None for uid in expected_uids)
        and violation.item_id == source.item_id
        and violation.evidence.get("item_ids") == [item.item_id for item in group]
        and violation.evidence.get("target_row_uids") == expected_uids
        and violation.evidence.get("gold_values") == expected_golds
    )


def _executable_expression_replay(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    if item is None:
        return False
    evidence = violation.evidence
    from .methods import (
        _answers_equivalent,
        _find_executable_checks,
        _find_final_marked_value,
        _numeric_equivalent,
        _safe_eval_expr,
    )

    source_path = evidence.get("source_path")
    source_checks = next(
        (
            checks
            for candidate_path, checks in _find_executable_checks(item.raw)
            if candidate_path == source_path
        ),
        None,
    )
    if not isinstance(source_checks, list):
        return False
    if violation.defect_type == "invalid_executable_evidence":
        claimed = evidence.get("check")
        if not isinstance(claimed, dict) or claimed not in source_checks:
            return False
        if claimed.get("kind") != "python_expr":
            return False
        computed = _safe_eval_expr(claimed.get("expr"))
        return bool(
            computed is not None
            and evidence.get("computed") == computed
            and not _numeric_equivalent(computed, claimed.get("expected"))
        )

    replayed_checks: list[dict[str, Any]] = []
    for index, check in enumerate(source_checks):
        if not isinstance(check, dict) or check.get("kind") != "python_expr":
            continue
        computed = _safe_eval_expr(check.get("expr"))
        if computed is None:
            continue
        replayed_checks.append({
            "index": index,
            "expr": check.get("expr"),
            "expected": check.get("expected"),
            "computed": computed,
            "matches": _numeric_equivalent(computed, check.get("expected")),
        })
    final_marked = _find_final_marked_value(item.raw, str(source_path or ""))
    return bool(
        replayed_checks
        and final_marked is not None
        and evidence.get("gold") == item.gold
        and evidence.get("final_evidence_answer") == final_marked
        and evidence.get("checks") == replayed_checks
        and not _answers_equivalent(final_marked, item.gold)
    )


def _gdpval_objective_replay(
    violation: Violation,
    item: BenchmarkItem | None,
) -> bool:
    """Recompute a GDPval objective fact from the complete live source row."""

    from .gdpval_objective import replay_record_fact

    return replay_record_fact(violation, item)


def _gdpval_workbook_replay(
    violation: Violation,
    item: BenchmarkItem | None,
) -> bool:
    """Re-read pinned XLSX bytes and reproduce a column-contract mismatch."""

    from .gdpval_objective import replay_workbook_fact

    return replay_workbook_fact(violation, item)


# Confirmation is granted to one exact proof tuple, never to a checker name as
# a whole.  This prevents a newly added heuristic in an otherwise objective
# checker from silently inheriting confirmation authority.
OBJECTIVE_PROOF_VALIDATORS: dict[
    tuple[str, str, str], ProofValidator
] = {
    ("static_rule", "canonical_task_absence", "missing_task"): _task_absent,
    ("static_rule", "choice_gold_domain_replay", "invalid_choice_gold"): _invalid_choice_gold,
    ("static_rule", "safe_arithmetic_replay", "wrong_gold_answer"): _arithmetic_replay,
    ("static_rule", "declared_alias_replay", "overstrict_evaluator"): _declared_evaluator_replay,
    ("evaluator_replay", "declared_evaluator_replay", "gold_rejected_by_evaluator"): _declared_evaluator_replay,
    ("cross_artifact_consistency", "answer_contract_static_consistency", "output_evaluator_contract_mismatch"): _contract_replay,
    ("workspace_artifact_invariants", "filesystem_manifest_replay", "artifact_data_gap"): _workspace_manifest_replay,
    ("workspace_artifact_invariants", "dependency_graph_replay", "artifact_data_gap"): _workspace_dependency_replay,
    ("workspace_artifact_invariants", "metadata_contract_replay", "output_evaluator_contract_mismatch"): _workspace_metadata_contract,
    ("workspace_artifact_invariants", "metadata_evaluator_replay", "schema_drift"): _workspace_metadata_evaluator,
    # Actor visibility is necessary but not sufficient to prove a solution
    # leak.  Until an isolated replay binds generator output to the hidden
    # oracle/rubric, this tuple intentionally has no confirmation authority.
    ("executable_evidence_replay", "safe_expression_replay", "invalid_executable_evidence"): _executable_expression_replay,
    ("executable_evidence_replay", "safe_expression_replay", "executable_evidence_gold_conflict"): _executable_expression_replay,
    ("gdpval_objective", "gdpval_rubric_representation_replay", "rubric_representation_mismatch"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_record_schema_replay", "gdpval_schema_mismatch"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_artifact_manifest_replay", "artifact_reference_manifest_mismatch"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_rubric_identifier_replay", "duplicate_rubric_item_id"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_rubric_column_replay", "rubric_internal_contradiction"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_task_deliverable_filename_replay", "task_artifact_contract_mismatch"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_task_deliverable_format_replay", "task_artifact_contract_mismatch"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_rubric_deliverable_filename_replay", "rubric_artifact_contract_mismatch"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_rubric_deliverable_format_replay", "rubric_artifact_contract_mismatch"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_task_reference_filename_replay", "rubric_reference_contract_mismatch"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_rubric_reference_filename_replay", "rubric_reference_contract_mismatch"): _gdpval_objective_replay,
    ("gdpval_objective", "gdpval_task_workbook_header_replay", "task_artifact_contract_mismatch"): _gdpval_workbook_replay,
    ("gdpval_objective", "gdpval_rubric_workbook_header_replay", "rubric_artifact_contract_mismatch"): _gdpval_workbook_replay,
}


DATASET_PROOF_VALIDATORS: dict[
    tuple[str, str, str], Callable[[Violation, list[BenchmarkItem]], bool]
] = {
    (
        "dataset_duplicate_scan",
        "dataset_identifier_collision",
        "duplicate_item_id",
    ): _dataset_duplicate_id_live,
    (
        "dataset_duplicate_scan",
        "canonical_record_oracle_conflict",
        "conflicting_duplicate_oracle",
    ): _dataset_conflicting_oracle_live,
}


# These payloads describe observations made by an execution driver, but the
# current report has no independently verifiable adjudicator transcript.  A
# caller-controlled trust-domain string and well-shaped hashes are not proof.
DISABLED_UNATTESTED_PROOFS = frozenset({
    ("execution_replay", "executed_harness", "gold_rejected_by_evaluator"),
    (
        "execution_differential",
        "executed_differential_confirmed",
        "overstrict_evaluator",
    ),
    (
        "execution_kill_matrix",
        "executed_kill_matrix_confirmed",
        "evaluator_mutation_survived",
    ),
})


PROOF_FIELD_DEPENDENCIES: dict[tuple[str, str, str], tuple[str, ...]] = {
    ("static_rule", "canonical_task_absence", "missing_task"): ("task",),
    ("static_rule", "choice_gold_domain_replay", "invalid_choice_gold"): ("choices", "gold"),
    ("static_rule", "safe_arithmetic_replay", "wrong_gold_answer"): ("task", "gold"),
    ("static_rule", "declared_alias_replay", "overstrict_evaluator"): ("gold", "aliases", "evaluator"),
    ("evaluator_replay", "declared_evaluator_replay", "gold_rejected_by_evaluator"): ("gold", "evaluator"),
    ("cross_artifact_consistency", "answer_contract_static_consistency", "output_evaluator_contract_mismatch"): ("output_contract", "evaluator"),
    ("workspace_artifact_invariants", "filesystem_manifest_replay", "artifact_data_gap"): ("context",),
    ("workspace_artifact_invariants", "dependency_graph_replay", "artifact_data_gap"): ("context", "output_contract"),
    ("workspace_artifact_invariants", "metadata_contract_replay", "output_evaluator_contract_mismatch"): ("output_contract", "evaluator"),
    ("workspace_artifact_invariants", "metadata_evaluator_replay", "schema_drift"): ("evaluator",),
    ("workspace_artifact_invariants", "workspace_runner_visibility_replay", "solution_leak"): ("context", "evaluator"),
    ("execution_replay", "executed_harness", "gold_rejected_by_evaluator"): ("gold", "evaluator"),
    ("execution_differential", "executed_differential_confirmed", "overstrict_evaluator"): ("gold", "evaluator"),
    ("execution_kill_matrix", "executed_kill_matrix_confirmed", "evaluator_mutation_survived"): ("gold", "evaluator"),
    ("dataset_duplicate_scan", "dataset_identifier_collision", "duplicate_item_id"): ("item_id",),
    ("dataset_duplicate_scan", "canonical_record_oracle_conflict", "conflicting_duplicate_oracle"): ("task", "gold"),
    ("executable_evidence_replay", "safe_expression_replay", "invalid_executable_evidence"): ("task",),
    ("executable_evidence_replay", "safe_expression_replay", "executable_evidence_gold_conflict"): ("task", "gold"),
    ("gdpval_objective", "gdpval_rubric_representation_replay", "rubric_representation_mismatch"): ("evaluator",),
    ("gdpval_objective", "gdpval_record_schema_replay", "gdpval_schema_mismatch"): (),
    ("gdpval_objective", "gdpval_artifact_manifest_replay", "artifact_reference_manifest_mismatch"): ("context",),
    ("gdpval_objective", "gdpval_rubric_identifier_replay", "duplicate_rubric_item_id"): ("evaluator",),
    ("gdpval_objective", "gdpval_rubric_column_replay", "rubric_internal_contradiction"): ("evaluator",),
    ("gdpval_objective", "gdpval_task_deliverable_filename_replay", "task_artifact_contract_mismatch"): ("task", "gold"),
    ("gdpval_objective", "gdpval_task_deliverable_format_replay", "task_artifact_contract_mismatch"): ("task", "gold"),
    ("gdpval_objective", "gdpval_rubric_deliverable_filename_replay", "rubric_artifact_contract_mismatch"): ("evaluator", "gold"),
    ("gdpval_objective", "gdpval_rubric_deliverable_format_replay", "rubric_artifact_contract_mismatch"): ("evaluator", "gold"),
    ("gdpval_objective", "gdpval_task_reference_filename_replay", "rubric_reference_contract_mismatch"): ("task", "context"),
    ("gdpval_objective", "gdpval_rubric_reference_filename_replay", "rubric_reference_contract_mismatch"): ("evaluator", "context"),
    ("gdpval_objective", "gdpval_task_workbook_header_replay", "task_artifact_contract_mismatch"): ("task", "context", "gold"),
    ("gdpval_objective", "gdpval_rubric_workbook_header_replay", "rubric_artifact_contract_mismatch"): ("evaluator", "context", "gold"),
}


def _method_is_model_based(method: str, evidence: dict[str, Any]) -> bool:
    normalized = method.casefold()
    level = str(evidence.get("evidence_level") or "").casefold()
    return (
        "llm" in normalized
        or normalized in SEMANTIC_OR_MODEL_METHODS
        or level.startswith("llm_")
        or "llm_result" in evidence
        or "llm_results" in evidence
        or "votes" in evidence
    )


def _proof_kind(violation: Violation) -> str:
    method = violation.detection_method.casefold()
    level = str(violation.evidence.get("evidence_level") or "").casefold()
    if _method_is_model_based(method, violation.evidence):
        return "model_judgment"
    if method.startswith("execution_") or level.startswith("executed_"):
        return "isolated_execution"
    if level == "workspace_runner_visibility_replay":
        return "actor_visibility_replay"
    if "replay" in method or "replay" in level:
        return "deterministic_replay"
    if method == "workspace_artifact_invariants" and (
        "visible_file" in level or "runner_visibility_replay" in level
    ):
        return "artifact_content_hash"
    if method in {"static_rule", "cross_artifact_consistency"}:
        return "deterministic_rule"
    if method == "dataset_duplicate_scan":
        return "dataset_identity_scan"
    return "unclassified"


def _mapping_is_trusted(
    item: BenchmarkItem | None,
    artifact: str,
    dependencies: tuple[str, ...] | None = None,
) -> tuple[bool, str]:
    if item is None:
        return True, "no mapping provenance attached"
    fields_to_check = dependencies or (
        (MAPPING_SENSITIVE_ARTIFACTS[artifact],)
        if artifact in MAPPING_SENSITIVE_ARTIFACTS else ()
    )
    if not fields_to_check:
        return True, "artifact is not mapping-sensitive"
    provenance = item.metadata.get("_mapping_provenance")
    if not isinstance(provenance, dict):
        # Programmatically constructed canonical items are treated as explicit;
        # inferred loaders always attach provenance below.
        return True, "canonical item has no inferred-mapping marker"
    if provenance.get("source") == "explicit":
        return True, "user supplied an explicit field mapping"
    fields = provenance.get("fields")
    for field in fields_to_check:
        state = fields.get(field) if isinstance(fields, dict) else None
        if not isinstance(state, dict):
            return False, f"inferred mapping has no provenance for {field}"
        if state.get("row_status") != "resolved":
            return False, f"inferred {field} mapping row_status={state.get('row_status')}"
        if state.get("mapping_status") == "ambiguous":
            return False, f"inferred {field} mapping has conflicting candidate fields"
    return True, "selected inferred field is present and non-conflicting for this row"


def decide_promotion(
    violation: Violation,
    item: BenchmarkItem | None = None,
    items: list[BenchmarkItem] | None = None,
) -> PromotionDecision:
    proof = _proof_kind(violation)
    level = str(violation.evidence.get("evidence_level") or "")
    proof_key = (violation.detection_method, level, violation.defect_type)
    mapping_ok, mapping_reason = _mapping_is_trusted(
        item, violation.artifact, PROOF_FIELD_DEPENDENCIES.get(proof_key),
    )
    if not mapping_ok:
        return PromotionDecision(
            "unknown", "adapter_inference",
            "Finding may be caused by incomplete/ambiguous automatic field mapping: "
            + mapping_reason,
        )
    if violation.defect_scope == "operational":
        return PromotionDecision(
            "unknown", proof,
            "Operational failure describes audit coverage, not a benchmark defect.",
        )
    if _method_is_model_based(violation.detection_method, violation.evidence):
        return PromotionDecision(
            "review", "model_judgment",
            "Semantic/model judgements can prioritize review but cannot self-confirm.",
        )
    if violation.review_only and not bool(
        getattr(violation, "_pending_dataset_replay", False)
    ):
        return PromotionDecision(
            "review", proof,
            "The originating checker explicitly withheld automatic confirmation.",
        )
    dataset_validator = DATASET_PROOF_VALIDATORS.get(proof_key)
    if dataset_validator is not None:
        dataset_replay_succeeded = False
        if items is not None and _schema_valid(violation, item):
            try:
                dataset_replay_succeeded = bool(
                    dataset_validator(violation, items)
                )
            except Exception:
                dataset_replay_succeeded = False
        if dataset_replay_succeeded:
            return PromotionDecision(
                "confirmed",
                proof,
                "Finding passed an independent replay against the complete live dataset.",
            )
        return PromotionDecision(
            "review",
            proof,
            "Dataset proof was not replayed against matching complete live records.",
        )
    if proof_key in DISABLED_UNATTESTED_PROOFS and not _execution_attestation_valid(
        violation.evidence
    ):
        return PromotionDecision(
            "review",
            proof,
            "Execution payload lacks an independently verifiable adjudicator transcript.",
        )
    validator = OBJECTIVE_PROOF_VALIDATORS.get(proof_key)
    replay_succeeded = False
    if validator is not None and _schema_valid(violation, item):
        try:
            replay_succeeded = bool(validator(violation, item))
        except Exception:
            # Promotion is a fail-closed trust boundary.  A vanished cache,
            # parser rejection, or replay bug must never abort the complete
            # audit or preserve a confirmation claim.
            replay_succeeded = False
    if replay_succeeded:
        return PromotionDecision(
            "confirmed", proof,
            "Finding passed its exact versioned deterministic/execution proof validator.",
        )
    if validator is not None:
        return PromotionDecision(
            "review", proof,
            "The proof tuple is registered, but its versioned evidence payload failed validation.",
        )
    return PromotionDecision(
        "review", proof,
        "Method/evidence/defect proof tuple is not registered for automatic confirmation (fail-closed).",
    )


def enforce_promotion_policy(
    violation: Violation,
    item: BenchmarkItem | None = None,
    items: list[BenchmarkItem] | None = None,
) -> Violation:
    originating_review_only = bool(violation.review_only) and not bool(
        getattr(violation, "_pending_dataset_replay", False)
    )
    decision = decide_promotion(violation, item, items)
    if decision.tier not in EVIDENCE_TIERS:  # defensive invariant
        raise ValueError(f"invalid evidence tier: {decision.tier}")
    violation.evidence_tier = decision.tier
    violation.proof_kind = decision.proof_kind
    violation.promotion_reason = decision.reason
    violation.review_only = decision.tier != "confirmed"
    proof_key = (
        violation.detection_method,
        str(violation.evidence.get("evidence_level") or ""),
        violation.defect_type,
    )
    if (
        proof_key in DATASET_PROOF_VALIDATORS
        and items is None
        and not originating_review_only
    ):
        setattr(violation, "_pending_dataset_replay", True)
    elif items is not None and hasattr(violation, "_pending_dataset_replay"):
        delattr(violation, "_pending_dataset_replay")
    return violation


def enforce_all(
    violations: list[Violation],
    items: list[BenchmarkItem] | None = None,
) -> list[Violation]:
    all_items = list(items or [])
    by_row_uid = {
        item.row_uid: item for item in all_items if item.row_uid is not None
    }
    by_id_groups: dict[str, list[BenchmarkItem]] = {}
    for item in all_items:
        by_id_groups.setdefault(item.item_id, []).append(item)
    # item_id fallback is safe only when it is unique.  A duplicated benchmark
    # ID must never make promotion select an arbitrary last record.
    unique_by_id = {
        item_id: group[0]
        for item_id, group in by_id_groups.items()
        if len(group) == 1
    }
    return [
        enforce_promotion_policy(
            row,
            by_row_uid.get(row.row_uid) if row.row_uid is not None
            else unique_by_id.get(row.item_id),
            all_items,
        )
        for row in violations
    ]
