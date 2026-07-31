"""Fail-closed provenance policy for externally acquired evidence.

The policy function in this module is deliberately file/network independent.
Git graph traversal, remote trust, tree reads, and manifest-role verification
belong to a separately configured verifier.  A receipt cannot authorize
itself by embedding booleans or a caller-chosen ``allowed_uses`` field.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Protocol


EXTERNAL_EVIDENCE_RECEIPT_VERSION = "1"
EXTERNAL_EVIDENCE_POLICY_VERSION = "external-evidence-policy-v1"
EXTERNAL_EVIDENCE_TRUST_DOMAIN = "independent_git_provenance_v1"
GIT_RELATION_PROOF_KIND = "git_graph_and_tree_blob_v1"

EVIDENCE_USES = frozenset({
    "routing", "detection", "confirmation", "validation",
})
SOURCE_ROLES = frozenset({
    "normative",
    "contemporaneous_metadata",
    "post_cutoff_correction",
    "search_lead",
})

_ROLE_CAPABILITIES = {
    "normative": EVIDENCE_USES,
    "contemporaneous_metadata": frozenset({
        "routing", "detection", "validation",
    }),
    "post_cutoff_correction": frozenset({"routing", "validation"}),
    "search_lead": frozenset({"routing"}),
}
_RELATION_CAPABILITIES = {
    "pre_cutoff": EVIDENCE_USES,
    "post_cutoff": frozenset({"routing", "validation"}),
    "unverifiable": frozenset(),
}


def _hex_digest(value: Any, lengths: tuple[int, ...]) -> bool:
    text = str(value or "").casefold()
    return len(text) in lengths and all(char in "0123456789abcdef" for char in text)


def _safe_relative_path(value: Any) -> bool:
    text = str(value or "")
    if not text or text.startswith(("/", "\\")):
        return False
    return all(part not in {"", ".", ".."} for part in text.replace("\\", "/").split("/"))


def normalize_remote_url(value: Any) -> str:
    """Apply only representation-safe normalization.

    SSH/HTTPS remotes are intentionally not treated as equivalent: the trusted
    verifier must pin one canonical official remote rather than broaden trust.
    """

    text = str(value or "").strip().rstrip("/")
    return text[:-4] if text.endswith(".git") else text


@dataclass(frozen=True)
class GitRelationProofClaim:
    kind: str
    remote_url: str
    source_commit: str
    cutoff_commit: str
    source_path: str
    content_sha256: str

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any] | None,
    ) -> GitRelationProofClaim | None:
        if not isinstance(value, Mapping):
            return None
        return cls(
            kind=str(value.get("kind") or ""),
            remote_url=str(value.get("remote_url") or ""),
            source_commit=str(value.get("source_commit") or ""),
            cutoff_commit=str(value.get("cutoff_commit") or ""),
            source_path=str(value.get("source_path") or ""),
            content_sha256=str(value.get("content_sha256") or ""),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "remote_url": self.remote_url,
            "source_commit": self.source_commit,
            "cutoff_commit": self.cutoff_commit,
            "source_path": self.source_path,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class ExternalEvidenceReceipt:
    receipt_version: str
    policy_version: str
    source_role: str
    source_remote_url: str
    cutoff_remote_url: str
    source_commit: str
    cutoff_commit: str
    source_path: str
    content_sha256: str
    relation_proof: GitRelationProofClaim | None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ExternalEvidenceReceipt:
        if not isinstance(value, Mapping):
            raise ValueError("external evidence receipt must be an object")
        # Unknown fields, including caller-supplied allowed_uses, are ignored.
        return cls(
            receipt_version=str(value.get("receipt_version") or ""),
            policy_version=str(value.get("policy_version") or ""),
            source_role=str(value.get("source_role") or ""),
            source_remote_url=str(value.get("source_remote_url") or ""),
            cutoff_remote_url=str(value.get("cutoff_remote_url") or ""),
            source_commit=str(value.get("source_commit") or ""),
            cutoff_commit=str(value.get("cutoff_commit") or ""),
            source_path=str(value.get("source_path") or ""),
            content_sha256=str(value.get("content_sha256") or ""),
            relation_proof=GitRelationProofClaim.from_mapping(
                value.get("relation_proof")
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "receipt_version": self.receipt_version,
            "policy_version": self.policy_version,
            "source_role": self.source_role,
            "source_remote_url": self.source_remote_url,
            "cutoff_remote_url": self.cutoff_remote_url,
            "source_commit": self.source_commit,
            "cutoff_commit": self.cutoff_commit,
            "source_path": self.source_path,
            "content_sha256": self.content_sha256,
            "relation_proof": (
                self.relation_proof.as_dict()
                if self.relation_proof is not None else None
            ),
        }


def receipt_payload_sha256(receipt: ExternalEvidenceReceipt) -> str:
    encoded = json.dumps(
        receipt.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ExternalEvidenceVerification:
    """Facts produced by a verifier outside the evidence producer's trust domain."""

    verified: bool
    reason: str
    trust_domain: str
    receipt_payload_sha256: str
    verified_remote_url: str
    official_remote_verified: bool
    role_binding_verified: bool
    verified_source_role: str
    source_commit: str
    cutoff_commit: str
    source_path: str
    source_tree_content_sha256: str
    cutoff_tree_content_sha256: str | None
    source_is_ancestor_of_cutoff: bool
    cutoff_is_ancestor_of_source: bool


class ExternalEvidenceVerifier(Protocol):
    """Independent authority for Git graph, blob, remote, and role replay."""

    def verify(
        self, receipt: ExternalEvidenceReceipt,
    ) -> ExternalEvidenceVerification: ...


@dataclass(frozen=True)
class ExternalEvidencePolicyDecision:
    allowed_uses: frozenset[str]
    reason: str


def _derived_relation(
    verification: ExternalEvidenceVerification,
) -> str:
    # Equality makes both ancestry predicates true; it is still pre-cutoff.
    if verification.source_is_ancestor_of_cutoff:
        return "pre_cutoff"
    if verification.cutoff_is_ancestor_of_source:
        return "post_cutoff"
    return "unverifiable"


def _bindings_valid(
    receipt: ExternalEvidenceReceipt,
    verification: ExternalEvidenceVerification,
    *,
    active_policy_version: str,
) -> tuple[bool, str]:
    if active_policy_version != EXTERNAL_EVIDENCE_POLICY_VERSION:
        return False, "active external-evidence policy version is unknown"
    if receipt.receipt_version != EXTERNAL_EVIDENCE_RECEIPT_VERSION:
        return False, "external-evidence receipt version is unsupported"
    if receipt.policy_version != EXTERNAL_EVIDENCE_POLICY_VERSION:
        return False, "receipt declares an unknown external-evidence policy"
    if receipt.source_role not in SOURCE_ROLES:
        return False, "external-evidence source role is unsupported"
    if not _hex_digest(receipt.source_commit, (40, 64)):
        return False, "source commit is malformed"
    if not _hex_digest(receipt.cutoff_commit, (40, 64)):
        return False, "cutoff commit is malformed"
    if not _hex_digest(receipt.content_sha256, (64,)):
        return False, "content SHA-256 is malformed"
    if not _safe_relative_path(receipt.source_path):
        return False, "source path is unsafe or absent"
    source_remote = normalize_remote_url(receipt.source_remote_url)
    cutoff_remote = normalize_remote_url(receipt.cutoff_remote_url)
    if not source_remote or source_remote != cutoff_remote:
        return False, "source and cutoff remotes are not the same pinned remote"

    proof = receipt.relation_proof
    if proof is None:
        return False, "relation proof is absent"
    if proof.kind != GIT_RELATION_PROOF_KIND:
        return False, "relation proof kind is unsupported"
    if (
        normalize_remote_url(proof.remote_url) != source_remote
        or proof.source_commit != receipt.source_commit
        or proof.cutoff_commit != receipt.cutoff_commit
        or proof.source_path != receipt.source_path
        or proof.content_sha256 != receipt.content_sha256
    ):
        return False, "relation proof does not bind the exact receipt"

    if verification.verified is not True:
        return False, "independent provenance verifier rejected the receipt"
    if verification.trust_domain != EXTERNAL_EVIDENCE_TRUST_DOMAIN:
        return False, "verification did not come from the pinned trust domain"
    if verification.receipt_payload_sha256 != receipt_payload_sha256(receipt):
        return False, "verification is not bound to this exact receipt"
    if verification.official_remote_verified is not True:
        return False, "official remote was not independently verified"
    if normalize_remote_url(verification.verified_remote_url) != source_remote:
        return False, "verification used a different remote"
    if verification.role_binding_verified is not True:
        return False, "manifest source-role binding was not verified"
    if verification.verified_source_role != receipt.source_role:
        return False, "verified source role differs from the receipt"
    if (
        verification.source_commit != receipt.source_commit
        or verification.cutoff_commit != receipt.cutoff_commit
        or verification.source_path != receipt.source_path
    ):
        return False, "verification references different Git objects or path"
    if (
        verification.source_is_ancestor_of_cutoff
        and verification.cutoff_is_ancestor_of_source
        and receipt.source_commit != receipt.cutoff_commit
    ):
        return False, "bidirectional ancestry requires identical commits"
    if verification.source_tree_content_sha256 != receipt.content_sha256:
        return False, "source tree content hash differs from the receipt"
    relation = _derived_relation(verification)
    if relation == "pre_cutoff":
        if verification.cutoff_tree_content_sha256 != receipt.content_sha256:
            return False, "cutoff tree content hash differs from the receipt"
    elif relation == "post_cutoff":
        if verification.cutoff_tree_content_sha256 is not None:
            return False, "post-cutoff verification must not supply an unused cutoff blob hash"
    return True, relation


def derive_allowed_uses(
    receipt: ExternalEvidenceReceipt,
    verification: ExternalEvidenceVerification,
    *,
    active_policy_version: str = EXTERNAL_EVIDENCE_POLICY_VERSION,
) -> frozenset[str]:
    """Derive capabilities without filesystem, network, or cached permissions."""

    valid, relation_or_reason = _bindings_valid(
        receipt,
        verification,
        active_policy_version=active_policy_version,
    )
    if not valid:
        return frozenset()
    return frozenset(
        _ROLE_CAPABILITIES[receipt.source_role]
        & _RELATION_CAPABILITIES[relation_or_reason]
    )


def evaluate_external_evidence(
    receipt_values: Any,
    verifier: ExternalEvidenceVerifier | None,
    *,
    active_policy_version: str = EXTERNAL_EVIDENCE_POLICY_VERSION,
) -> ExternalEvidencePolicyDecision:
    """Verify all declared receipts and intersect their allowed capabilities."""

    if not isinstance(receipt_values, list) or not receipt_values:
        return ExternalEvidencePolicyDecision(
            frozenset(),
            "external evidence receipts are absent or not a non-empty list",
        )
    if verifier is None:
        return ExternalEvidencePolicyDecision(
            frozenset(),
            "no independent external-evidence verifier is configured",
        )

    aggregate = EVIDENCE_USES
    for index, value in enumerate(receipt_values):
        try:
            receipt = ExternalEvidenceReceipt.from_mapping(value)
            verification = verifier.verify(receipt)
        except Exception:
            return ExternalEvidencePolicyDecision(
                frozenset(),
                f"external evidence receipt {index} failed verification",
            )
        allowed = derive_allowed_uses(
            receipt,
            verification,
            active_policy_version=active_policy_version,
        )
        if not allowed:
            return ExternalEvidencePolicyDecision(
                frozenset(),
                f"external evidence receipt {index} is unverifiable or disallowed",
            )
        aggregate = frozenset(aggregate & allowed)
    return ExternalEvidencePolicyDecision(
        frozenset(aggregate),
        "external evidence uses were independently re-derived under the active policy",
    )
