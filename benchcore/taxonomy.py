from __future__ import annotations

from dataclasses import dataclass


CORE_ARTIFACTS = (
    "task_specification",
    "context_attachment",
    "expected_output",
    "oracle_ground_truth",
    "evaluator",
)


SEVERITY_ORDER = {
    "critical": 4,
    "major": 3,
    "minor": 2,
    "review": 1,
}


@dataclass(frozen=True)
class DefectInfo:
    artifact: str
    mechanism: str
    defect_type: str
    default_severity: str
    description: str


DEFECTS: dict[str, DefectInfo] = {
    "missing_task": DefectInfo(
        "task_specification",
        "missing",
        "missing_task",
        "critical",
        "Task description/question/instruction is missing.",
    ),
    "ambiguous_goal": DefectInfo(
        "task_specification",
        "ambiguous",
        "ambiguous_goal",
        "major",
        "Task goal has multiple plausible interpretations.",
    ),
    "missing_condition": DefectInfo(
        "task_specification",
        "missing",
        "missing_condition",
        "major",
        "Task appears to require answer-changing information that is not specified.",
    ),
    "missing_context": DefectInfo(
        "context_attachment",
        "missing",
        "missing_context",
        "major",
        "Task references external context that is not present.",
    ),
    "artifact_data_gap": DefectInfo(
        "context_attachment",
        "missing",
        "artifact_data_gap",
        "major",
        "Task, rubric, evaluator, or reference requires data absent from the provided artifacts.",
    ),
    "inaccessible_attachment": DefectInfo(
        "context_attachment",
        "unavailable",
        "inaccessible_attachment",
        "major",
        "Referenced attachment path is missing or unreadable.",
    ),
    "context_version_mismatch_risk": DefectInfo(
        "context_attachment",
        "stale",
        "context_version_mismatch_risk",
        "review",
        "Context appears version-sensitive but no version/provenance is available.",
    ),
    "missing_output_contract": DefectInfo(
        "expected_output",
        "missing",
        "missing_output_contract",
        "minor",
        "Expected output format or answer contract is missing.",
    ),
    "output_format_overstrict_risk": DefectInfo(
        "expected_output",
        "overstrict",
        "output_format_overstrict_risk",
        "review",
        "Evaluator may reject format-preserving answer variants.",
    ),
    "missing_accepted_alternatives": DefectInfo(
        "expected_output",
        "missing",
        "missing_accepted_alternatives",
        "review",
        "Task likely needs accepted aliases or semantically equivalent alternatives.",
    ),
    "missing_oracle": DefectInfo(
        "oracle_ground_truth",
        "missing",
        "missing_oracle",
        "critical",
        "Gold answer/reference oracle is missing.",
    ),
    "wrong_gold_answer": DefectInfo(
        "oracle_ground_truth",
        "incorrect",
        "wrong_gold_answer",
        "critical",
        "Executable or independently derived evidence disagrees with the gold answer.",
    ),
    "invalid_choice_gold": DefectInfo(
        "oracle_ground_truth",
        "incorrect",
        "invalid_choice_gold",
        "critical",
        "Gold choice cannot be mapped to the available choices.",
    ),
    "duplicate_choices": DefectInfo(
        "oracle_ground_truth",
        "ambiguous",
        "duplicate_choices",
        "major",
        "Multiple answer choices normalize to the same content.",
    ),
    "bad_options_clarity": DefectInfo(
        "expected_output",
        "ambiguous",
        "bad_options_clarity",
        "review",
        "One or more answer choices are unclear, uninterpretable, or answer-changingly overlapping.",
    ),
    "multiple_correct_answers": DefectInfo(
        "oracle_ground_truth",
        "ambiguous",
        "multiple_correct_answers",
        "major",
        "Multiple answers appear correct under the task specification.",
    ),
    "multiple_correct_answers_risk": DefectInfo(
        "oracle_ground_truth",
        "ambiguous",
        "multiple_correct_answers_risk",
        "review",
        "Single-answer task may have multiple acceptable answers.",
    ),
    "no_correct_answer": DefectInfo(
        "oracle_ground_truth",
        "incorrect",
        "no_correct_answer",
        "major",
        "No provided answer appears correct under the task specification.",
    ),
    "missing_evaluator": DefectInfo(
        "evaluator",
        "missing",
        "missing_evaluator",
        "major",
        "Evaluator/test/rubric is missing or cannot be inferred.",
    ),
    "overstrict_evaluator": DefectInfo(
        "evaluator",
        "overstrict",
        "overstrict_evaluator",
        "major",
        "Evaluator rejects format-preserving or declared accepted answer variants.",
    ),
    "underconstrained_evaluator_risk": DefectInfo(
        "evaluator",
        "underconstrained",
        "underconstrained_evaluator_risk",
        "review",
        "Evaluator appears too weak to distinguish task success from superficial output.",
    ),
    "gold_rejected_by_evaluator": DefectInfo(
        "evaluator",
        "incorrect",
        "gold_rejected_by_evaluator",
        "critical",
        "The declared evaluator rejects the benchmark's own gold answer.",
    ),
    "evaluator_mutation_survived": DefectInfo(
        "evaluator",
        "underconstrained",
        "evaluator_mutation_survived",
        "major",
        "An intentionally wrong answer mutation is accepted by the evaluator.",
    ),
    "metamorphic_inconsistency": DefectInfo(
        "evaluator",
        "inconsistent",
        "metamorphic_inconsistency",
        "major",
        "A semantics-preserving answer transformation changes the evaluation result.",
    ),
    "output_evaluator_contract_mismatch": DefectInfo(
        "evaluator",
        "inconsistent",
        "output_evaluator_contract_mismatch",
        "major",
        "The output contract and evaluator/rubric requirements are inconsistent.",
    ),
    "task_rubric_mismatch": DefectInfo(
        "evaluator",
        "inconsistent",
        "task_rubric_mismatch",
        "major",
        "Rubric or evaluator checks requirements not supported by the task specification.",
    ),
    "rubric_target_error": DefectInfo(
        "evaluator",
        "incorrect",
        "rubric_target_error",
        "review",
        "Rubric asserts a target value not reproduced by an independent recompute from the inputs.",
    ),
    "reference_task_mismatch": DefectInfo(
        "oracle_ground_truth",
        "inconsistent",
        "reference_task_mismatch",
        "major",
        "Reference solution or gold artifact appears misaligned with the task specification.",
    ),
    "duplicate_item_id": DefectInfo(
        "task_specification",
        "inconsistent",
        "duplicate_item_id",
        "critical",
        "Multiple benchmark records use the same item identifier.",
    ),
    "duplicate_task": DefectInfo(
        "task_specification",
        "leaky",
        "duplicate_task",
        "review",
        "Multiple benchmark records contain the same normalized task.",
    ),
    "solution_leak": DefectInfo(
        "task_specification",
        "leaky",
        "solution_leak",
        "major",
        "The visible task statement directly exposes solution or repair content.",
    ),
    "hints_only_solution_leak": DefectInfo(
        "context_attachment",
        "leaky",
        "hints_only_solution_leak",
        "review",
        "Solution or repair content appears only in non-visible hints or comments.",
    ),
    "conflicting_duplicate_oracle": DefectInfo(
        "oracle_ground_truth",
        "inconsistent",
        "conflicting_duplicate_oracle",
        "critical",
        "Duplicate task records declare different gold answers.",
    ),
    "schema_drift": DefectInfo(
        "task_specification",
        "inconsistent",
        "schema_drift",
        "review",
        "Records in the same benchmark expose inconsistent core artifact fields.",
    ),
    "invalid_executable_evidence": DefectInfo(
        "oracle_ground_truth",
        "incorrect",
        "invalid_executable_evidence",
        "critical",
        "Declared executable evidence does not reproduce its expected value.",
    ),
    "executable_evidence_gold_conflict": DefectInfo(
        "oracle_ground_truth",
        "inconsistent",
        "executable_evidence_gold_conflict",
        "critical",
        "Final executable evidence disagrees with the gold answer.",
    ),
    "solver_gold_disagreement": DefectInfo(
        "oracle_ground_truth",
        "inconsistent",
        "solver_gold_disagreement",
        "review",
        "An independent candidate solver answer disagrees with the gold answer.",
    ),
    "llm_audit_failure": DefectInfo(
        "evaluator",
        "unavailable",
        "llm_audit_failure",
        "review",
        "An LLM audit method failed and produced no usable result.",
    ),
    "temporal_scope_missing": DefectInfo(
        "task_specification",
        "missing",
        "temporal_scope_missing",
        "review",
        "A time-sensitive task lacks a stable reference date or version.",
    ),
    "source_reference_missing": DefectInfo(
        "context_attachment",
        "missing",
        "source_reference_missing",
        "review",
        "A source-dependent task does not identify the referenced study, text, or authority.",
    ),
    "incomplete_task_instruction": DefectInfo(
        "task_specification",
        "missing",
        "incomplete_task_instruction",
        "review",
        "The task appears to have lost an instruction, blank, or required question component.",
    ),
    "presentation_corruption": DefectInfo(
        "expected_output",
        "incorrect",
        "presentation_corruption",
        "review",
        "OCR, encoding, date conversion, or formatting corruption is visible in the task or choices.",
    ),
    "auditor_contradiction": DefectInfo(
        "evaluator",
        "inconsistent",
        "auditor_contradiction",
        "review",
        "Independent audit dimensions produced mutually inconsistent conclusions.",
    ),
}
