"""Fail-closed boundary for independently attested execution transcripts.

An execution container protects the host, but does not by itself make the
container's JSON output trustworthy: the benchmark harness may control code
that runs beside the serializer.  This module deliberately does *not* invent a
local signature scheme.  A deployment must supply an independent verifier
(for example an attestation service bound to a separate runner/identity).

Without that verifier every execution observation remains in the shared,
untrusted-driver trust domain.  This is a safety property, not a missing
default convenience feature.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


ATTESTATION_PROTOCOL = "benchaudit-execution-attestation-v1"
SHARED_UNTRUSTED_DOMAIN = "shared_untrusted_driver"
SEPARATE_PROCESS_DOMAIN = "separate_process_v1"


def canonical_transcript_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the minimal immutable observation that an external service signs.

    The payload avoids local paths, raw probe source, and timing fields.  It
    nevertheless binds the three code identities and every verdict-bearing
    field.  The caller hashes this canonical structure before sending it to an
    external verifier.
    """
    return {
        "protocol": ATTESTATION_PROTOCOL,
        "driver_sha256": str(report.get("driver_sha256") or ""),
        "reference_code_sha256": str(report.get("reference_code_sha256") or ""),
        "code_context_sha256": str(report.get("code_context_sha256") or ""),
        "gold": report.get("gold"),
        "instrumented_gold": report.get("instrumented_gold"),
        "gold_verdicts": report.get("gold_verdicts"),
        "gold_instrumentation_consistent": report.get(
            "gold_instrumentation_consistent"
        ),
        "input_materialization_complete": report.get("input_materialization_complete"),
        "observed_cases": report.get("observed_cases"),
        "probes": report.get("probes"),
        "probe_failures": report.get("probe_failures"),
    }


def transcript_sha256(report: Mapping[str, Any]) -> str:
    payload = canonical_transcript_payload(report)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ExecutionTranscriptVerifier(Protocol):
    """Verifier owned by a trust domain distinct from the target harness.

    Implementations are expected to verify an attester identity/signature and
    independently bind ``payload_sha256`` to a runner-produced transcript.
    Returning ``True`` is intentionally the *only* way to cross the promotion
    boundary; a value embedded in benchmark data is never enough by itself.
    """

    def verify(self, attestation: Mapping[str, Any], payload_sha256: str) -> bool: ...


class ExecutionTranscriptAttester(Protocol):
    """Remote/separate-domain component that signs a completed transcript hash.

    It must be backed by the runner's own trusted observation, not merely sign
    a hash submitted by the benchmark process.  The verifier remains a second
    independent boundary and can reject an attester's response.
    """

    def attest(self, payload_sha256: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class AttestationStatus:
    trust_domain: str
    payload_sha256: str
    verified: bool
    reason: str
    attestation: dict[str, Any] | None = None

    def as_evidence(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "adjudicator_trust_domain": self.trust_domain,
            "execution_transcript_sha256": self.payload_sha256,
            "execution_attestation_verified": self.verified,
            "execution_attestation_reason": self.reason,
        }
        if self.attestation is not None:
            # Keep only public, structured attestation metadata.  The verifier
            # owns any secret material and must never return it here.
            value["execution_attestation"] = self.attestation
        return value


def verify_execution_attestation(
    report: Mapping[str, Any],
    attestation: Mapping[str, Any] | None,
    verifier: ExecutionTranscriptVerifier | None,
) -> AttestationStatus:
    """Validate an external attestation, failing closed on every ambiguity."""
    payload_sha = transcript_sha256(report)
    if verifier is None:
        return AttestationStatus(
            SHARED_UNTRUSTED_DOMAIN, payload_sha, False,
            "no independent transcript verifier configured",
        )
    if not isinstance(attestation, Mapping):
        return AttestationStatus(
            SHARED_UNTRUSTED_DOMAIN, payload_sha, False,
            "runner did not provide an attestation object",
        )
    public = dict(attestation)
    if public.get("protocol") != ATTESTATION_PROTOCOL:
        return AttestationStatus(
            SHARED_UNTRUSTED_DOMAIN, payload_sha, False,
            "attestation protocol mismatch", public,
        )
    if public.get("payload_sha256") != payload_sha:
        return AttestationStatus(
            SHARED_UNTRUSTED_DOMAIN, payload_sha, False,
            "attestation payload hash does not match this transcript", public,
        )
    try:
        verified = verifier.verify(public, payload_sha)
    except Exception:
        verified = False
    if verified is not True:
        return AttestationStatus(
            SHARED_UNTRUSTED_DOMAIN, payload_sha, False,
            "independent verifier rejected attestation", public,
        )
    return AttestationStatus(
        SEPARATE_PROCESS_DOMAIN, payload_sha, True,
        "independent verifier accepted attestation", public,
    )


def request_execution_attestation(
    report: Mapping[str, Any], attester: ExecutionTranscriptAttester | None,
) -> Mapping[str, Any] | None:
    """Ask a separate attester for a statement bound to this transcript hash.

    A failed/unavailable attester simply yields no proof; callers must keep the
    observation at review tier.  This deliberately catches all transport and
    implementation errors rather than allowing audit availability to become a
    semantic finding.
    """
    if attester is None:
        return None
    try:
        value = attester.attest(transcript_sha256(report))
    except Exception:
        return None
    return dict(value) if isinstance(value, Mapping) else None
