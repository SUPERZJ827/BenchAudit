from __future__ import annotations

from dataclasses import replace
from typing import Any

from benchcore.external_evidence import (
    EXTERNAL_EVIDENCE_POLICY_VERSION,
    EXTERNAL_EVIDENCE_TRUST_DOMAIN,
    GIT_RELATION_PROOF_KIND,
    ExternalEvidenceReceipt,
    ExternalEvidenceVerification,
    derive_allowed_uses,
    evaluate_external_evidence,
    receipt_payload_sha256,
)
from benchcore.field_mapping import mapping_from_dict
from benchcore.loader import build_items
from benchcore.promotion import decide_promotion
from benchcore.schema import BenchmarkItem, Violation


OFFICIAL_REMOTE = "https://github.com/example/benchmark.git"
SOURCE_COMMIT = "a" * 40
CUTOFF_COMMIT = "b" * 40
CONTENT_SHA256 = "c" * 64


def _receipt(
    *,
    role: str = "normative",
    source_commit: str = SOURCE_COMMIT,
    cutoff_commit: str = CUTOFF_COMMIT,
    content_sha256: str = CONTENT_SHA256,
    policy_version: str = EXTERNAL_EVIDENCE_POLICY_VERSION,
    remote_url: str = OFFICIAL_REMOTE,
    include_relation_proof: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "receipt_version": "1",
        "policy_version": policy_version,
        "source_role": role,
        "source_remote_url": remote_url,
        "cutoff_remote_url": remote_url,
        "source_commit": source_commit,
        "cutoff_commit": cutoff_commit,
        "source_path": "README.md",
        "content_sha256": content_sha256,
    }
    if include_relation_proof:
        value["relation_proof"] = {
            "kind": GIT_RELATION_PROOF_KIND,
            "remote_url": remote_url,
            "source_commit": source_commit,
            "cutoff_commit": cutoff_commit,
            "source_path": "README.md",
            "content_sha256": content_sha256,
        }
    if extra:
        value.update(extra)
    return value


def _verification(
    receipt: ExternalEvidenceReceipt,
    *,
    source_is_ancestor: bool = True,
    cutoff_is_ancestor: bool = False,
    source_tree_content_sha256: str | None = None,
    cutoff_tree_content_sha256: str | None = None,
    verified_remote_url: str = OFFICIAL_REMOTE,
    official_remote_verified: bool = True,
) -> ExternalEvidenceVerification:
    relation_is_pre = source_is_ancestor
    return ExternalEvidenceVerification(
        verified=True,
        reason="fixture independently replayed",
        trust_domain=EXTERNAL_EVIDENCE_TRUST_DOMAIN,
        receipt_payload_sha256=receipt_payload_sha256(receipt),
        verified_remote_url=verified_remote_url,
        official_remote_verified=official_remote_verified,
        role_binding_verified=True,
        verified_source_role=receipt.source_role,
        source_commit=receipt.source_commit,
        cutoff_commit=receipt.cutoff_commit,
        source_path=receipt.source_path,
        source_tree_content_sha256=(
            source_tree_content_sha256 or receipt.content_sha256
        ),
        cutoff_tree_content_sha256=(
            cutoff_tree_content_sha256
            if cutoff_tree_content_sha256 is not None
            else receipt.content_sha256 if relation_is_pre else None
        ),
        source_is_ancestor_of_cutoff=source_is_ancestor,
        cutoff_is_ancestor_of_source=cutoff_is_ancestor,
    )


class _StaticVerifier:
    def __init__(
        self,
        verification: ExternalEvidenceVerification
        | dict[str, ExternalEvidenceVerification],
    ) -> None:
        self.verification = verification

    def verify(
        self,
        receipt: ExternalEvidenceReceipt,
    ) -> ExternalEvidenceVerification:
        if isinstance(self.verification, dict):
            return self.verification[receipt.content_sha256]
        return self.verification


def _parsed_receipt(**kwargs: Any) -> ExternalEvidenceReceipt:
    return ExternalEvidenceReceipt.from_mapping(_receipt(**kwargs))


def _verifier_for(value: dict[str, Any], **kwargs: Any) -> _StaticVerifier:
    receipt = ExternalEvidenceReceipt.from_mapping(value)
    return _StaticVerifier(_verification(receipt, **kwargs))


def _missing_task_finding(
    external_receipts: list[dict[str, Any]] | None,
) -> tuple[Violation, BenchmarkItem]:
    evidence: dict[str, Any] = {
        "evidence_level": "canonical_task_absence",
        "proof_schema_version": "1.0",
    }
    if external_receipts is not None:
        evidence["external_evidence_receipts"] = external_receipts
    item = build_items(
        [{"id": "item-1"}],
        mapping_from_dict({"item_id": "id", "task": "question"}),
    )[0]
    return (
        Violation(
            item_id="item-1",
            artifact="task_specification",
            mechanism="omission",
            defect_type="missing_task",
            severity="critical",
            confidence=1.0,
            message="Task specification is missing.",
            detection_method="static_rule",
            evidence=evidence,
        ),
        item,
    )


def test_normative_pre_cutoff_receipt_allows_all_uses() -> None:
    receipt = _parsed_receipt()

    assert derive_allowed_uses(receipt, _verification(receipt)) == {
        "routing", "detection", "confirmation", "validation",
    }


def test_post_cutoff_correction_is_validation_only_for_substantive_work() -> None:
    receipt = _parsed_receipt(
        role="post_cutoff_correction",
        source_commit="d" * 40,
    )

    allowed = derive_allowed_uses(
        receipt,
        _verification(
            receipt,
            source_is_ancestor=False,
            cutoff_is_ancestor=True,
        ),
    )

    assert allowed == {"routing", "validation"}
    assert "detection" not in allowed
    assert "confirmation" not in allowed


def test_unrelated_git_history_is_unverifiable_and_allows_nothing() -> None:
    receipt = _parsed_receipt()

    allowed = derive_allowed_uses(
        receipt,
        _verification(
            receipt,
            source_is_ancestor=False,
            cutoff_is_ancestor=False,
        ),
    )

    assert allowed == frozenset()


def test_caller_supplied_allowed_uses_cannot_forge_confirmation() -> None:
    value = _receipt(
        role="post_cutoff_correction",
        source_commit="d" * 40,
        extra={"allowed_uses": ["confirmation"]},
    )
    receipt = ExternalEvidenceReceipt.from_mapping(value)

    allowed = derive_allowed_uses(
        receipt,
        _verification(
            receipt,
            source_is_ancestor=False,
            cutoff_is_ancestor=True,
        ),
    )

    assert allowed == {"routing", "validation"}


def test_absent_independent_verifier_is_unverifiable_and_allows_nothing() -> None:
    decision = evaluate_external_evidence([_receipt()], None)

    assert decision.present is True
    assert decision.allowed_uses == frozenset()


def test_correct_ancestry_with_wrong_cutoff_blob_hash_is_rejected() -> None:
    receipt = _parsed_receipt()
    verification = _verification(
        receipt,
        cutoff_tree_content_sha256="d" * 64,
    )

    assert derive_allowed_uses(receipt, verification) == frozenset()


def test_absent_relation_proof_is_rejected() -> None:
    receipt = _parsed_receipt(include_relation_proof=False)

    assert derive_allowed_uses(receipt, _verification(receipt)) == frozenset()


def test_unknown_receipt_or_active_policy_version_is_rejected() -> None:
    receipt = _parsed_receipt(policy_version="future-policy")
    assert derive_allowed_uses(receipt, _verification(receipt)) == frozenset()

    current = _parsed_receipt()
    assert derive_allowed_uses(
        current,
        _verification(current),
        active_policy_version="future-policy",
    ) == frozenset()


def test_cached_old_policy_decision_is_ignored_and_rederived() -> None:
    value = _receipt(
        role="post_cutoff_correction",
        source_commit="d" * 40,
        extra={
            "cached_allowed_uses": [
                "routing", "detection", "confirmation", "validation",
            ],
            "cached_policy_version": "obsolete",
        },
    )
    receipt = ExternalEvidenceReceipt.from_mapping(value)

    allowed = derive_allowed_uses(
        receipt,
        _verification(
            receipt,
            source_is_ancestor=False,
            cutoff_is_ancestor=True,
        ),
    )

    assert allowed == {"routing", "validation"}


def test_verification_against_a_different_remote_is_rejected() -> None:
    receipt = _parsed_receipt()
    verification = _verification(
        receipt,
        verified_remote_url="https://github.com/attacker/fork.git",
    )

    assert derive_allowed_uses(receipt, verification) == frozenset()


def test_receipt_payload_hash_binding_rejects_forged_verification() -> None:
    receipt = _parsed_receipt()
    verification = replace(
        _verification(receipt),
        receipt_payload_sha256="0" * 64,
    )

    assert derive_allowed_uses(receipt, verification) == frozenset()


def test_multiple_receipts_use_the_intersection_of_capabilities() -> None:
    normative_value = _receipt(content_sha256="c" * 64)
    metadata_value = _receipt(
        role="contemporaneous_metadata",
        content_sha256="d" * 64,
    )
    normative = ExternalEvidenceReceipt.from_mapping(normative_value)
    metadata = ExternalEvidenceReceipt.from_mapping(metadata_value)
    verifier = _StaticVerifier({
        normative.content_sha256: _verification(normative),
        metadata.content_sha256: _verification(metadata),
    })

    decision = evaluate_external_evidence(
        [normative_value, metadata_value],
        verifier,
    )

    assert decision.allowed_uses == {"routing", "detection", "validation"}


def test_validation_only_external_receipt_blocks_detection_in_promotion() -> None:
    value = _receipt(
        role="post_cutoff_correction",
        source_commit="d" * 40,
    )
    finding, item = _missing_task_finding([value])

    decision = decide_promotion(
        finding,
        item,
        external_evidence_verifier=_verifier_for(
            value,
            source_is_ancestor=False,
            cutoff_is_ancestor=True,
        ),
    )

    assert decision.tier == "unknown"
    assert decision.proof_kind == "external_evidence_provenance"


def test_metadata_external_receipt_caps_objective_proof_at_review() -> None:
    value = _receipt(role="contemporaneous_metadata")
    finding, item = _missing_task_finding([value])

    decision = decide_promotion(
        finding,
        item,
        external_evidence_verifier=_verifier_for(value),
    )

    assert decision.tier == "review"
    assert decision.proof_kind == "external_evidence_provenance"


def test_normative_external_receipt_does_not_self_confirm_unregistered_proof() -> None:
    value = _receipt()
    finding, item = _missing_task_finding([value])
    finding.defect_type = "wrong_gold_answer"
    finding.evidence["evidence_level"] = "unregistered_external_claim"

    decision = decide_promotion(
        finding,
        item,
        external_evidence_verifier=_verifier_for(value),
    )

    assert decision.tier == "review"
    assert decision.proof_kind != "external_evidence_provenance"


def test_normative_external_receipt_can_reach_existing_objective_validator() -> None:
    value = _receipt()
    finding, item = _missing_task_finding([value])

    decision = decide_promotion(
        finding,
        item,
        external_evidence_verifier=_verifier_for(value),
    )

    assert decision.tier == "confirmed"


def test_external_receipt_without_verifier_fails_closed_in_promotion() -> None:
    finding, item = _missing_task_finding([_receipt()])

    decision = decide_promotion(finding, item)

    assert decision.tier == "unknown"
    assert decision.proof_kind == "external_evidence_provenance"


def test_findings_without_external_receipts_keep_existing_behavior() -> None:
    finding, item = _missing_task_finding(None)

    decision = decide_promotion(finding, item)

    assert decision.tier == "confirmed"
