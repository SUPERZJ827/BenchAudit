"""Fail-closed evidence promotion for benchmark audit findings.

Confidence is not proof.  In particular, an LLM vote can prioritize review but
cannot turn a semantic judgement into an objectively confirmed benchmark bug.
This module is the single authority that maps observations to evidence tiers.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
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
DatasetProofValidator = Callable[[Violation, list[BenchmarkItem]], bool]


@dataclass(frozen=True)
class ProofSpec:
    """Confirmation authority and its explicit proof obligations."""

    validator: Callable[..., bool]
    scope: str
    evidence_basis: str
    prerequisites: tuple[str, ...]
    field_dependencies: tuple[str, ...]


def _schema_valid(violation: Violation, item: BenchmarkItem | None) -> bool:
    return violation.evidence.get("proof_schema_version") == PROOF_SCHEMA_VERSION


def _sha256(value: Any) -> bool:
    text = str(value or "").casefold()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _commit(value: Any) -> bool:
    text = str(value or "").casefold()
    return len(text) == 40 and all(char in "0123456789abcdef" for char in text)


def _registry_receipt_matches(
    registry_root: str,
    family: str,
    schema_fingerprint: str,
    adapter_id: str,
    adapter_version: str,
    adapter_sha256: str,
    receipt_id: str,
) -> bool:
    """Revalidate a generated adapter against its external trust authority."""

    try:
        from .adaptation.registry import AdapterRegistry

        spec, receipt = AdapterRegistry(Path(registry_root)).resolve(
            family=family,
            schema_fingerprint=schema_fingerprint,
            allow_shadow=False,
        )
    except Exception:
        return False
    return bool(
        receipt.get("activation_mode") == "active_verified"
        and str(receipt.get("receipt_id") or "") == receipt_id
        and spec.adapter_id == adapter_id
        and spec.version == adapter_version
        and spec.sha256 == adapter_sha256
        and spec.schema_fingerprint == schema_fingerprint
        and spec.family == family
    )


def _task_absent(violation: Violation, item: BenchmarkItem | None) -> bool:
    return bool(item is not None and not str(item.task or "").strip())


def _invalid_choice_gold_with_declared_labels(
    violation: Violation,
    item: BenchmarkItem | None,
    *,
    source: str,
) -> bool:
    if item is None or not item.choices:
        return False
    from .evaluators import (
        answer_values,
        choice_gold_is_mappable,
        choice_values,
        declared_choice_labels,
        normalize_text,
    )

    contract = item.evaluator if source == "evaluator" else item.output_contract
    labels = declared_choice_labels(contract, len(choice_values(item.choices)))
    normalized_labels = {normalize_text(label) for label in labels or ()}
    outside_declared_namespace = bool(labels) and any(
        normalize_text(value) not in normalized_labels for value in answer_values(item.gold)
    )
    return bool(
        labels
        and violation.evidence.get("choice_contract_source") == source
        and violation.evidence.get("declared_choice_labels") == list(labels)
        and not choice_gold_is_mappable(item.gold, item.choices)
        and outside_declared_namespace
        and violation.evidence.get("gold") == item.gold
        and violation.evidence.get("choices") == item.choices
    )


def _invalid_choice_gold_evaluator_labels(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    return _invalid_choice_gold_with_declared_labels(
        violation, item, source="evaluator",
    )


def _invalid_choice_gold_output_labels(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    return _invalid_choice_gold_with_declared_labels(
        violation, item, source="output_contract",
    )


def _declared_label_family_outlier(gold: Any, labels: tuple[str, ...]) -> bool:
    """Whether gold clearly uses the declared label family but is out of range."""

    from .evaluators import answer_values, normalize_text

    normalized_labels = [normalize_text(label) for label in labels]
    values = [normalize_text(value) for value in answer_values(gold)]
    if not values:
        return False
    if all(re.fullmatch(r"[a-z]", label) for label in normalized_labels):
        return all(
            re.fullmatch(r"[a-z]", value) is not None
            and value not in normalized_labels
            for value in values
        )
    if all(re.fullmatch(r"[+-]?\d+", label) for label in normalized_labels):
        return all(
            re.fullmatch(r"[+-]?\d+", value) is not None
            and value not in normalized_labels
            for value in values
        )
    return False


def _invalid_choice_gold_declared_labels_dataset(
    violation: Violation,
    items: list[BenchmarkItem],
) -> bool:
    """Adjudicate explicit-label violations without enumerating alphabets."""

    from collections import Counter
    from .evaluators import (
        answer_values,
        characterize_unknown_choice_encoding,
        choice_gold_is_mappable,
        choice_values,
        declared_choice_labels,
        normalize_text,
    )

    source = next(
        (
            item for item in items
            if violation.row_uid is not None and item.row_uid == violation.row_uid
        ),
        None,
    )
    if source is None:
        candidates = [item for item in items if item.item_id == violation.item_id]
        source = candidates[0] if len(candidates) == 1 else None
    if source is None or not source.choices:
        return False
    contract_source = str(violation.evidence.get("choice_contract_source") or "")
    contract = (
        source.evaluator if contract_source == "evaluator"
        else source.output_contract if contract_source == "output_contract"
        else None
    )
    labels = declared_choice_labels(contract, len(choice_values(source.choices)))
    if labels is None:
        return False
    item_validator = (
        _invalid_choice_gold_evaluator_labels
        if contract_source == "evaluator"
        else _invalid_choice_gold_output_labels
    )
    if not item_validator(violation, source):
        return False
    if _declared_label_family_outlier(source.gold, labels):
        violation.evidence["choice_encoding_replay"] = {
            "decision": "declared_label_family_outlier",
            "semantic_permutation_verified": True,
        }
        return True

    signature = _choice_namespace_signature(source)
    group = [
        item for item in items
        if item.choices
        and len(choice_values(item.choices)) == len(choice_values(source.choices))
        and _choice_namespace_signature(item) == signature
    ]
    if len(group) - 1 < DECLARED_CHOICE_NAMESPACE_MIN_PEERS:
        return False
    golds = [item.gold for item in group]
    profile = characterize_unknown_choice_encoding(golds, len(labels))
    scalar_tokens = []
    for item in group:
        values = answer_values(item.gold)
        if len(values) != 1:
            scalar_tokens = []
            break
        scalar_tokens.append(normalize_text(values[0]))
    counts = Counter(scalar_tokens)
    top = counts.most_common(len(labels))
    dominant_tokens = {token for token, _ in top}
    dominant_coverage = (
        sum(count for _, count in top) / len(group) if group else 0.0
    )
    source_values = answer_values(source.gold)
    source_token = normalize_text(source_values[0]) if len(source_values) == 1 else ""
    dominant_unknown_encoding = bool(
        len(top) == len(labels)
        and dominant_coverage >= 0.95
        and source_token in dominant_tokens
    )
    violation.evidence["choice_encoding_replay"] = {
        **profile,
        "dominant_tokens": sorted(dominant_tokens),
        "dominant_coverage": dominant_coverage,
        "source_in_dominant_namespace": dominant_unknown_encoding,
        "systematic_permutation_limitation": (
            "Structure cannot determine whether a coherent token-to-choice permutation is semantically shifted."
        ),
    }
    if profile["coherent"] or dominant_unknown_encoding:
        return False
    if source_token and dominant_coverage >= 0.95 and source_token not in dominant_tokens:
        return True
    # A declared label contract plus a sufficiently large, non-cardinality-
    # compatible collection is objective evidence of invalid storage values.
    return not any(choice_gold_is_mappable(item.gold, item.choices) for item in group)


CHOICE_NAMESPACE_MIN_PEERS = 100
# With 100/100 supporting peers, the 95% Wilson lower bound is about 0.963.
# A 0.98 threshold would therefore be mathematically unreachable at the stated
# minimum sample size and would silently disable this confirmation path.
CHOICE_NAMESPACE_MIN_WILSON_LOWER = 0.95
DECLARED_CHOICE_NAMESPACE_MIN_PEERS = 20
# 20/20 supporting peers yield a 95% Wilson lower bound of about 0.839.
DECLARED_CHOICE_NAMESPACE_MIN_WILSON_LOWER = 0.80


def _choice_namespace_signature(item: BenchmarkItem) -> str:
    """Group only rows that share a schema and declared mapping context."""

    provenance = item.metadata.get("_mapping_provenance")
    fields = provenance.get("fields", {}) if isinstance(provenance, dict) else {}

    def selected(name: str) -> Any:
        state = fields.get(name, {}) if isinstance(fields, dict) else {}
        if not isinstance(state, dict):
            return None
        return state.get("resolved_key") or state.get("selected")

    payload = {
        "raw_keys": sorted(str(key) for key in item.raw),
        "mapping_source": provenance.get("source") if isinstance(provenance, dict) else None,
        "choices_field": selected("choices"),
        "gold_field": selected("gold"),
        "evaluator": item.evaluator,
        "output_contract": item.output_contract,
        "schema_fingerprint": (
            provenance.get("schema_fingerprint")
            if isinstance(provenance, dict) else None
        ),
        "adapter_id": (
            provenance.get("adapter_id") if isinstance(provenance, dict) else None
        ),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    proportion = successes / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    centre = proportion + z2 / (2.0 * total)
    margin = z * math.sqrt(
        (proportion * (1.0 - proportion) + z2 / (4.0 * total)) / total
    )
    return max(0.0, (centre - margin) / denominator)


def _invalid_choice_gold_dataset(
    violation: Violation,
    items: list[BenchmarkItem],
) -> bool:
    """Confirm an inferred MCQ namespace from homogeneous peer records.

    The target row is excluded from the estimate: an alleged defect must never
    help establish the semantic precondition used to confirm itself.
    """

    from .evaluators import choice_gold_is_mappable

    source = next(
        (
            item for item in items
            if violation.row_uid is not None and item.row_uid == violation.row_uid
        ),
        None,
    )
    if source is None:
        candidates = [item for item in items if item.item_id == violation.item_id]
        source = candidates[0] if len(candidates) == 1 else None
    if source is None or not source.choices:
        return False
    if choice_gold_is_mappable(source.gold, source.choices):
        return False
    if (
        violation.evidence.get("gold") != source.gold
        or violation.evidence.get("choices") != source.choices
    ):
        return False

    signature = _choice_namespace_signature(source)
    peers = [
        item for item in items
        if item is not source
        and item.choices
        and item.gold not in (None, "")
        and _choice_namespace_signature(item) == signature
    ]
    successes = sum(
        choice_gold_is_mappable(item.gold, item.choices) for item in peers
    )
    declared_contract = str(violation.evidence.get("evidence_level") or "").startswith(
        "declared_choice_"
    )
    minimum_peers = (
        DECLARED_CHOICE_NAMESPACE_MIN_PEERS
        if declared_contract else CHOICE_NAMESPACE_MIN_PEERS
    )
    minimum_lower = (
        DECLARED_CHOICE_NAMESPACE_MIN_WILSON_LOWER
        if declared_contract else CHOICE_NAMESPACE_MIN_WILSON_LOWER
    )
    lower = _wilson_lower_bound(successes, len(peers))
    stats = {
        "group_signature": signature,
        "leave_one_out": True,
        "peer_records": len(peers),
        "mappable_peer_records": successes,
        "observed_rate": successes / len(peers) if peers else 0.0,
        "wilson_lower_95": lower,
        "contract_declared": declared_contract,
        "minimum_peer_records": minimum_peers,
        "minimum_wilson_lower_95": minimum_lower,
    }
    violation.evidence["choice_namespace_replay"] = stats
    return bool(
        len(peers) >= minimum_peers
        and lower >= minimum_lower
    )


def _arithmetic_replay(violation: Violation, item: BenchmarkItem | None) -> bool:
    evidence = violation.evidence
    if item is None:
        return False
    from .checkers import (
        ARITHMETIC_PROOF_LANGUAGE,
        _extract_simple_arithmetic_value,
        _parse_arithmetic_proof_gold,
    )

    replayed = _extract_simple_arithmetic_value(str(item.task or ""))
    gold_number = _parse_arithmetic_proof_gold(item.gold)
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
        and evidence.get("arithmetic_proof_language") == ARITHMETIC_PROOF_LANGUAGE
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


def _workspace_filename_collision_replay(
    violation: Violation, item: BenchmarkItem | None,
) -> bool:
    rows = violation.evidence.get("ambiguous_input_filenames")
    return bool(
        isinstance(rows, list) and rows
        and _workspace_live_replay_matches(
            violation, item, ("ambiguous_input_filenames",)
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
    ("static_rule", "safe_arithmetic_replay", "wrong_gold_answer"): _arithmetic_replay,
    ("static_rule", "declared_alias_replay", "overstrict_evaluator"): _declared_evaluator_replay,
    ("evaluator_replay", "declared_evaluator_replay", "gold_rejected_by_evaluator"): _declared_evaluator_replay,
    ("cross_artifact_consistency", "answer_contract_static_consistency", "output_evaluator_contract_mismatch"): _contract_replay,
    ("workspace_artifact_invariants", "filesystem_manifest_replay", "artifact_data_gap"): _workspace_manifest_replay,
    ("workspace_artifact_invariants", "dependency_graph_replay", "artifact_data_gap"): _workspace_dependency_replay,
    ("workspace_artifact_invariants", "manifest_filename_collision_replay", "ambiguous_input_filename"): _workspace_filename_collision_replay,
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
    tuple[str, str, str], DatasetProofValidator
] = {
    (
        "static_rule",
        "inferred_choice_namespace_replay",
        "invalid_choice_gold",
    ): _invalid_choice_gold_dataset,
    (
        "static_rule",
        "declared_choice_evaluator_namespace_replay",
        "invalid_choice_gold",
    ): _invalid_choice_gold_dataset,
    (
        "static_rule",
        "declared_choice_output_namespace_replay",
        "invalid_choice_gold",
    ): _invalid_choice_gold_dataset,
    (
        "static_rule",
        "explicit_choice_evaluator_labels_replay",
        "invalid_choice_gold",
    ): _invalid_choice_gold_declared_labels_dataset,
    (
        "static_rule",
        "explicit_choice_output_labels_replay",
        "invalid_choice_gold",
    ): _invalid_choice_gold_declared_labels_dataset,
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
    (
        "static_rule",
        "explicit_choice_evaluator_labels_replay",
        "invalid_choice_gold",
    ): ("choices", "gold", "evaluator"),
    (
        "static_rule",
        "explicit_choice_output_labels_replay",
        "invalid_choice_gold",
    ): ("choices", "gold", "output_contract"),
    (
        "static_rule",
        "declared_choice_evaluator_namespace_replay",
        "invalid_choice_gold",
    ): ("choices", "gold", "evaluator"),
    (
        "static_rule",
        "declared_choice_output_namespace_replay",
        "invalid_choice_gold",
    ): ("choices", "gold", "output_contract"),
    (
        "static_rule",
        "inferred_choice_namespace_replay",
        "invalid_choice_gold",
    ): ("choices", "gold"),
    ("static_rule", "safe_arithmetic_replay", "wrong_gold_answer"): ("task", "gold"),
    ("static_rule", "declared_alias_replay", "overstrict_evaluator"): ("gold", "aliases", "evaluator"),
    ("evaluator_replay", "declared_evaluator_replay", "gold_rejected_by_evaluator"): ("gold", "evaluator"),
    ("cross_artifact_consistency", "answer_contract_static_consistency", "output_evaluator_contract_mismatch"): ("output_contract", "evaluator"),
    ("workspace_artifact_invariants", "filesystem_manifest_replay", "artifact_data_gap"): ("context",),
    ("workspace_artifact_invariants", "dependency_graph_replay", "artifact_data_gap"): ("context", "output_contract"),
    ("workspace_artifact_invariants", "manifest_filename_collision_replay", "ambiguous_input_filename"): ("context",),
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


_INDEPENDENT_ITEM_PROOFS = frozenset({
    key for key in OBJECTIVE_PROOF_VALIDATORS
    if key[0] in {"workspace_artifact_invariants", "gdpval_objective"}
    or key[0] == "executable_evidence_replay"
})
_HEURISTIC_REPLAY_PROOFS = frozenset({
    (
        "cross_artifact_consistency",
        "answer_contract_static_consistency",
        "output_evaluator_contract_mismatch",
    ),
})


def _build_proof_specs() -> dict[tuple[str, str, str], ProofSpec]:
    specs: dict[tuple[str, str, str], ProofSpec] = {}
    for key, validator in OBJECTIVE_PROOF_VALIDATORS.items():
        if key in _HEURISTIC_REPLAY_PROOFS:
            basis = "same_heuristic_replay"
        elif key in _INDEPENDENT_ITEM_PROOFS:
            basis = "independent_source_replay"
        else:
            basis = "decidable_predicate"
        prerequisites = ["versioned_proof_schema", "trusted_field_mapping"]
        if key[1] in {
            "explicit_choice_evaluator_labels_replay",
            "explicit_choice_output_labels_replay",
        }:
            prerequisites.extend((
                "declared_choice_answer_contract",
                "explicit_choice_label_namespace",
            ))
        specs[key] = ProofSpec(
            validator=validator,
            scope="item",
            evidence_basis=basis,
            prerequisites=tuple(prerequisites),
            field_dependencies=PROOF_FIELD_DEPENDENCIES.get(key, ()),
        )
    for key, validator in DATASET_PROOF_VALIDATORS.items():
        prerequisites = [
            "versioned_proof_schema",
            "trusted_field_mapping",
            "complete_live_record_set",
        ]
        if key[1] in {
            "inferred_choice_namespace_replay",
            "declared_choice_evaluator_namespace_replay",
            "declared_choice_output_namespace_replay",
            "explicit_choice_evaluator_labels_replay",
            "explicit_choice_output_labels_replay",
        }:
            prerequisites.extend((
                "homogeneous_schema_group",
                "leave_one_out_namespace_support",
                "minimum_peer_sample",
                "wilson_confidence_lower_bound",
            ))
        specs[key] = ProofSpec(
            validator=validator,
            scope="dataset",
            evidence_basis="independent_source_replay",
            prerequisites=tuple(prerequisites),
            field_dependencies=PROOF_FIELD_DEPENDENCIES.get(key, ()),
        )
    return specs


PROOF_SPECS = _build_proof_specs()


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
        return False, "live canonical item is unavailable for mapping replay"
    fields_to_check = dependencies or (
        (MAPPING_SENSITIVE_ARTIFACTS[artifact],)
        if artifact in MAPPING_SENSITIVE_ARTIFACTS else ()
    )
    if not fields_to_check:
        return True, "artifact is not mapping-sensitive"
    provenance = item.metadata.get("_mapping_provenance")
    if not isinstance(provenance, dict):
        return False, "canonical item has no mapping provenance"

    # A receipt is a trust statement by a particular authority, not merely a
    # self-consistent bundle of hashes.  In particular, a generated adapter may
    # not promote itself by writing a correct fingerprint into its own output.
    source = str(provenance.get("source") or "")
    trust_domain = str(provenance.get("trust_domain") or "")
    activation_mode = str(provenance.get("activation_mode") or "")
    if source == "explicit":
        required = ("adapter_id", "adapter_version", "schema_fingerprint")
        missing = [key for key in required if not str(provenance.get(key) or "").strip()]
        if missing:
            return False, "explicit mapping receipt is missing " + ", ".join(missing)
    if str(provenance.get("receipt_version") or "") != "1":
        return False, "mapping receipt version is absent or unsupported"
    if source == "generated_adapter":
        registry_root = str(provenance.get("adapter_registry_root") or "")
        family = str(provenance.get("adapter_family") or "")
        adapter_id = str(provenance.get("adapter_id") or "")
        adapter_version = str(provenance.get("adapter_version") or "")
        adapter_sha256 = str(provenance.get("adapter_sha256") or "")
        schema_fingerprint = str(provenance.get("schema_fingerprint") or "")
        receipt_id = str(provenance.get("receipt_id") or "")
        if (
            trust_domain != "adapter_registry_verified_v1"
            or activation_mode != "active_verified"
            or not receipt_id
            or not _sha256(adapter_sha256)
            or not _sha256(schema_fingerprint)
            or not registry_root
            or not family
        ):
            return False, "generated adapter lacks an independently verified registry receipt"
        if not _registry_receipt_matches(
            registry_root,
            family,
            schema_fingerprint,
            adapter_id,
            adapter_version,
            adapter_sha256,
            receipt_id,
        ):
            return False, "generated adapter receipt did not replay against its registry authority"
    elif source == "explicit":
        if trust_domain not in {
            "user_explicit_mapping_v1",
            "host_programmatic_mapping_v1",
        }:
            return False, "explicit mapping receipt was not issued by a host authority"
        if not _sha256(provenance.get("schema_fingerprint")):
            return False, "explicit mapping schema fingerprint is malformed"
    elif source == "inferred":
        if trust_domain != "inferred_mapping_v1":
            return False, "inferred mapping receipt has an invalid trust domain"
    else:
        return False, f"mapping receipt has unsupported source={source!r}"

    bindings = provenance.get("mapping_bindings")
    if not isinstance(bindings, dict):
        return False, "mapping receipt has no exact field bindings"
    from .loader import mapping_bindings_sha256, record_schema_sha256

    if provenance.get("mapping_bindings_sha256") != mapping_bindings_sha256(bindings):
        return False, "mapping receipt field bindings do not match their commitment"
    if provenance.get("record_schema_sha256") != record_schema_sha256(item.raw):
        return False, "mapping receipt does not match the live record schema"

    fields = provenance.get("fields")
    for field in fields_to_check:
        state = fields.get(field) if isinstance(fields, dict) else None
        if not isinstance(state, dict):
            return False, f"mapping receipt has no field provenance for {field}"
        if state.get("row_status") != "resolved":
            # A host-explicit mapping can prove that a required source field is
            # absent; that absence is exactly what missing-field validators
            # inspect.  Inference cannot make the same semantic claim safely.
            if source == "explicit" and state.get("selected"):
                continue
            return False, f"{field} mapping row_status={state.get('row_status')}"
        if state.get("mapping_status") == "ambiguous":
            return False, f"{field} mapping has conflicting candidate fields"
    return True, "mapping authority, commitments, and dependent fields replayed"


def decide_promotion(
    violation: Violation,
    item: BenchmarkItem | None = None,
    items: list[BenchmarkItem] | None = None,
) -> PromotionDecision:
    proof = _proof_kind(violation)
    level = str(violation.evidence.get("evidence_level") or "")
    proof_key = (violation.detection_method, level, violation.defect_type)
    proof_spec = PROOF_SPECS.get(proof_key)

    def mapping_failure() -> PromotionDecision | None:
        mapping_ok, mapping_reason = _mapping_is_trusted(
            item,
            violation.artifact,
            proof_spec.field_dependencies if proof_spec is not None else None,
        )
        if mapping_ok:
            return None
        return PromotionDecision(
            "unknown", "adapter_inference",
            "Finding may be caused by incomplete/ambiguous field mapping: "
            + mapping_reason,
        )
    if violation.defect_scope == "operational":
        return PromotionDecision(
            "unknown", proof,
            "Operational failure describes audit coverage, not a benchmark defect.",
        )
    provenance = item.metadata.get("_mapping_provenance") if item is not None else None
    if isinstance(provenance, dict):
        if (failure := mapping_failure()) is not None:
            return failure
    if _method_is_model_based(violation.detection_method, violation.evidence):
        return PromotionDecision(
            "review", "model_judgment",
            "Semantic/model judgements can prioritize review but cannot self-confirm.",
        )
    if bool(getattr(violation, "_originating_review_only", violation.review_only)) and not bool(
        getattr(violation, "_pending_dataset_replay", False)
    ):
        return PromotionDecision(
            "review", proof,
            "The originating checker explicitly withheld automatic confirmation.",
        )
    if (
        proof_spec is not None
        and proof_spec.evidence_basis == "same_heuristic_replay"
    ):
        return PromotionDecision(
            "review",
            proof,
            "The registered replay repeats the detector's heuristic assumptions; "
            "it may prioritize review but cannot independently confirm a defect.",
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
            if (failure := mapping_failure()) is not None:
                return failure
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
        if (failure := mapping_failure()) is not None:
            return failure
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
    if not hasattr(violation, "_originating_review_only"):
        setattr(violation, "_originating_review_only", bool(violation.review_only))
    originating_review_only = bool(
        getattr(violation, "_originating_review_only")
    ) and not bool(
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
