"""Non-activated core for V2/V3 OS-visible trusted adjudication.

The module captures raw subprocess bytes, derives the frozen non-adaptive
policy from independently verified facts, and binds complete observations to
an internal HMAC attestation.  It deliberately has no CLI, checker, producer,
or promotion integration.  The production manifest registry is empty until a
separate activation review approves exact runtime and APPS manifests.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import collections
import math
import os
from dataclasses import dataclass
from pathlib import Path
import selectors
import signal
import subprocess
import time
from typing import Any, Mapping, Protocol


TRUSTED_ADJUDICATOR_PROTOCOL = "benchaudit-trusted-adjudicator-os-visible-v3"
SIGNATURE_SCHEME = "hmac-sha256-internal-integrity-v1"
NON_ADAPTIVE_MODEL = "non_adaptive_pre_cutoff"
TRUST_DOMAIN = "trusted_os_capture_supervisor_v3"
V3_PROTOCOL_COMMIT = "388d2e389720b30328a4b9d3267a1afb220c9474"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hex(value: str, length: int) -> bool:
    return len(value) == length and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class ComparisonResult:
    accepted: bool | None
    reason: str


def _apps_stdin_compare(actual: bytes, expected: bytes) -> ComparisonResult:
    """Frozen APPS comparator; raw hashes are bound before strict decoding."""

    try:
        actual_text = actual.decode("utf-8", errors="strict")
        expected_text = expected.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return ComparisonResult(None, "non_utf8_output_or_expectation")
    if actual_text.strip() == expected_text.strip():
        return ComparisonResult(True, "trimmed_exact")
    actual_lines = [line.strip() for line in actual_text.strip().splitlines() if line.strip()]
    expected_lines = [line.strip() for line in expected_text.strip().splitlines() if line.strip()]
    if actual_lines == expected_lines:
        return ComparisonResult(True, "normalized_lines")
    actual_tokens = actual_text.split()
    expected_tokens = expected_text.split()
    if len(actual_tokens) == len(expected_tokens):
        try:
            if all(
                math.isclose(float(left), float(right), rel_tol=1e-5, abs_tol=1e-6)
                for left, right in zip(actual_tokens, expected_tokens)
            ):
                return ComparisonResult(True, "numeric_tokens")
        except (TypeError, ValueError, OverflowError):
            pass
        if collections.Counter(actual_tokens) == collections.Counter(expected_tokens):
            return ComparisonResult(True, "token_multiset")
    return ComparisonResult(False, "output_mismatch")


_COMPARISON_CONTRACTS = {
    "apps-stdin-comparator-v1": _apps_stdin_compare,
}


@dataclass(frozen=True)
class HarnessProvenanceClaim:
    canonical_remote: str
    harness_revision_commit: str
    benchmark_cutoff_commit: str
    harness_content_sha256: str
    cutoff_binding_receipt_sha256: str
    cutoff_binding_benchaudit_commit: str


@dataclass(frozen=True)
class HarnessProvenanceVerification:
    verified: bool
    reason: str
    trust_domain: str
    canonical_remote_verified: bool
    verified_remote: str
    harness_revision_commit: str
    benchmark_cutoff_commit: str
    harness_content_sha256: str
    harness_is_ancestor_of_cutoff: bool
    cutoff_is_ancestor_of_harness: bool
    cutoff_binding_receipt_sha256: str
    cutoff_binding_benchaudit_commit: str
    cutoff_binding_is_ancestor_of_protocol: bool
    receipt_records_outcomes_uninspected: bool


class HarnessProvenanceVerifier(Protocol):
    def verify(
        self, claim: HarnessProvenanceClaim,
    ) -> HarnessProvenanceVerification: ...


@dataclass(frozen=True)
class AdversaryModelDecision:
    model: str | None
    confirmation_eligible: bool
    reason: str
    relation: str


def derive_adversary_model(
    claim: HarnessProvenanceClaim,
    verification: HarnessProvenanceVerification,
) -> AdversaryModelDecision:
    """Derive authority from verified bindings, never a caller model label."""

    bindings = (
        verification.verified is True
        and verification.trust_domain == "canonical_git_and_benchaudit_history_v1"
        and verification.canonical_remote_verified is True
        and verification.verified_remote == claim.canonical_remote
        and verification.harness_revision_commit == claim.harness_revision_commit
        and verification.benchmark_cutoff_commit == claim.benchmark_cutoff_commit
        and verification.harness_content_sha256 == claim.harness_content_sha256
        and verification.cutoff_binding_receipt_sha256
        == claim.cutoff_binding_receipt_sha256
        and verification.cutoff_binding_benchaudit_commit
        == claim.cutoff_binding_benchaudit_commit
        and verification.cutoff_binding_is_ancestor_of_protocol is True
        and verification.receipt_records_outcomes_uninspected is True
    )
    if not bindings:
        return AdversaryModelDecision(
            None, False, "provenance bindings are absent or unverifiable", "unverifiable"
        )
    equal = claim.harness_revision_commit == claim.benchmark_cutoff_commit
    if equal:
        if not (
            verification.harness_is_ancestor_of_cutoff
            and verification.cutoff_is_ancestor_of_harness
        ):
            return AdversaryModelDecision(
                None, False, "equal commits require bidirectional ancestry", "invalid"
            )
        relation = "equal_tautological_ancestry"
    else:
        if not verification.harness_is_ancestor_of_cutoff:
            return AdversaryModelDecision(
                None, False, "harness revision is not ancestral to cutoff", "post_or_unrelated"
            )
        if verification.cutoff_is_ancestor_of_harness:
            return AdversaryModelDecision(
                None, False, "distinct commits cannot have bidirectional ancestry", "invalid"
            )
        relation = "strict_ancestor"
    return AdversaryModelDecision(
        NON_ADAPTIVE_MODEL,
        True,
        "derived from canonical revision/content and pre-protocol BenchAudit binding",
        relation,
    )


@dataclass(frozen=True)
class TrustedExecutionManifest:
    manifest_id: str
    item_id: str
    candidate_id: str
    oracle_id: str
    comparison_contract_id: str
    expected_stdout: bytes
    argv: tuple[str, ...]
    cwd: str | None
    environment: tuple[tuple[str, str], ...]
    stdin_sha256: str
    runtime_identity: str
    runtime_confirmation_eligible: bool
    timeout_seconds: float
    max_stdout_bytes: int
    max_stderr_bytes: int
    provenance: HarnessProvenanceClaim

    def __post_init__(self) -> None:
        if not self.manifest_id or not self.item_id or not self.candidate_id or not self.oracle_id:
            raise ValueError("manifest, item, candidate, and oracle IDs are required")
        if self.comparison_contract_id not in _COMPARISON_CONTRACTS:
            raise ValueError("comparison contract is not code-owned")
        if not self.argv or not all(isinstance(value, str) and value for value in self.argv):
            raise ValueError("manifest argv must contain nonempty strings")
        if not _hex(self.stdin_sha256, 64):
            raise ValueError("manifest stdin SHA-256 is malformed")
        if self.timeout_seconds <= 0:
            raise ValueError("manifest timeout must be positive")
        if self.max_stdout_bytes <= 0 or self.max_stderr_bytes <= 0:
            raise ValueError("manifest output bounds must be positive")


# Empty by design.  Adding an entry is an activation-sensitive code change.
_CODE_OWNED_MANIFESTS: dict[str, TrustedExecutionManifest] = {}


@dataclass(frozen=True)
class SupervisorRequest:
    manifest_id: str
    stdin: bytes
    session_nonce: str
    claimed_adversary_model: str | None = None


@dataclass(frozen=True)
class RawProcessCapture:
    stdout: bytes
    stderr: bytes
    exit_code: int | None
    timed_out: bool
    stdout_overflow: bool
    stderr_overflow: bool
    stdout_eof: bool
    stderr_eof: bool

    @property
    def complete(self) -> bool:
        return (
            not self.timed_out
            and not self.stdout_overflow
            and not self.stderr_overflow
            and self.stdout_eof
            and self.stderr_eof
            and self.exit_code is not None
        )

    def stable_observation(self) -> dict[str, Any]:
        return {
            "stdout_sha256": _sha256(self.stdout),
            "stdout_bytes": len(self.stdout),
            "stderr_sha256": _sha256(self.stderr),
            "stderr_bytes": len(self.stderr),
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "stdout_overflow": self.stdout_overflow,
            "stderr_overflow": self.stderr_overflow,
            "stdout_eof": self.stdout_eof,
            "stderr_eof": self.stderr_eof,
            "complete": self.complete,
        }


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            # The leader may already have exited while a descendant still
            # owns an inherited pipe.  The process group remains the capture
            # boundary and must still be terminated to obtain honest EOF.
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


def capture_raw_process(
    argv: tuple[str, ...],
    *,
    stdin: bytes,
    cwd: Path | None,
    environment: Mapping[str, str],
    timeout_seconds: float,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
) -> RawProcessCapture:
    """Capture raw stdout/stderr with hard byte and wall-clock bounds."""

    process = subprocess.Popen(
        list(argv),
        cwd=str(cwd) if cwd is not None else None,
        env=dict(environment),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=(os.name == "posix"),
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    for stream in (process.stdin, process.stdout, process.stderr):
        os.set_blocking(stream.fileno(), False)
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    if stdin:
        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
    else:
        process.stdin.close()

    pending = memoryview(stdin)
    stdout = bytearray()
    stderr = bytearray()
    stdout_eof = False
    stderr_eof = False
    stdout_overflow = False
    stderr_overflow = False
    timed_out = False
    deadline = time.monotonic() + timeout_seconds
    try:
        while not (stdout_eof and stderr_eof and process.poll() is not None):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _kill_group(process)
                break
            events = selector.select(timeout=min(remaining, 0.05))
            for key, _ in events:
                stream = key.fileobj
                kind = key.data
                if kind == "stdin":
                    try:
                        written = os.write(stream.fileno(), pending[:65536])
                    except BrokenPipeError:
                        written = len(pending)
                    pending = pending[written:]
                    if not pending:
                        selector.unregister(stream)
                        stream.close()
                    continue
                try:
                    chunk = os.read(stream.fileno(), 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    if kind == "stdout":
                        stdout_eof = True
                    else:
                        stderr_eof = True
                    continue
                target = stdout if kind == "stdout" else stderr
                limit = max_stdout_bytes if kind == "stdout" else max_stderr_bytes
                remaining_bytes = max(limit - len(target), 0)
                target.extend(chunk[:remaining_bytes])
                if len(chunk) > remaining_bytes:
                    if kind == "stdout":
                        stdout_overflow = True
                    else:
                        stderr_overflow = True
                    _kill_group(process)
            if stdout_overflow or stderr_overflow:
                break
    finally:
        if timed_out or stdout_overflow or stderr_overflow:
            _kill_group(process)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            _kill_group(process)
            process.wait(timeout=1)
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
    return RawProcessCapture(
        stdout=bytes(stdout),
        stderr=bytes(stderr),
        exit_code=None if timed_out else process.returncode,
        timed_out=timed_out,
        stdout_overflow=stdout_overflow,
        stderr_overflow=stderr_overflow,
        stdout_eof=stdout_eof,
        stderr_eof=stderr_eof,
    )


@dataclass(frozen=True)
class SupervisorTranscript:
    manifest_id: str
    item_id: str
    candidate_id: str
    oracle_id: str
    comparison_contract_id: str
    expected_stdout_sha256: str
    session_nonce: str
    stdin_sha256: str
    runtime_identity: str
    observation: dict[str, Any]
    comparison_accepted: bool | None
    comparison_reason: str
    adversary_model: str | None
    adversary_relation: str
    provenance_reason: str
    v3_protocol_commit: str = V3_PROTOCOL_COMMIT

    def payload(self) -> dict[str, Any]:
        return {
            "protocol": TRUSTED_ADJUDICATOR_PROTOCOL,
            "manifest_id": self.manifest_id,
            "item_id": self.item_id,
            "candidate_id": self.candidate_id,
            "oracle_id": self.oracle_id,
            "comparison_contract_id": self.comparison_contract_id,
            "expected_stdout_sha256": self.expected_stdout_sha256,
            "session_nonce": self.session_nonce,
            "stdin_sha256": self.stdin_sha256,
            "runtime_identity": self.runtime_identity,
            "observation": self.observation,
            "comparison_accepted": self.comparison_accepted,
            "comparison_reason": self.comparison_reason,
            "adversary_model": self.adversary_model,
            "adversary_relation": self.adversary_relation,
            "provenance_reason": self.provenance_reason,
            "v3_protocol_commit": self.v3_protocol_commit,
        }

    @property
    def payload_sha256(self) -> str:
        return _sha256(_canonical_bytes(self.payload()))


@dataclass(frozen=True)
class SupervisorAttestation:
    protocol: str
    signature_scheme: str
    key_id: str
    payload_sha256: str
    signature: str

    def as_dict(self) -> dict[str, str]:
        return {
            "protocol": self.protocol,
            "signature_scheme": self.signature_scheme,
            "key_id": self.key_id,
            "payload_sha256": self.payload_sha256,
            "signature": self.signature,
        }


class _InternalHmacSigner:
    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("trusted adjudicator key must contain at least 32 bytes")
        self.__key = bytes(key)
        self.key_id = _sha256(self.__key)

    def attest(self, transcript: SupervisorTranscript) -> SupervisorAttestation:
        payload_sha256 = transcript.payload_sha256
        signature = hmac.new(
            self.__key, payload_sha256.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return SupervisorAttestation(
            TRUSTED_ADJUDICATOR_PROTOCOL,
            SIGNATURE_SCHEME,
            self.key_id,
            payload_sha256,
            signature,
        )


def verify_supervisor_attestation(
    transcript: SupervisorTranscript,
    attestation: SupervisorAttestation,
    *,
    verification_key: bytes,
) -> bool:
    if len(verification_key) < 32:
        return False
    if (
        attestation.protocol != TRUSTED_ADJUDICATOR_PROTOCOL
        or attestation.signature_scheme != SIGNATURE_SCHEME
        or attestation.key_id != _sha256(verification_key)
        or attestation.payload_sha256 != transcript.payload_sha256
        or not _hex(attestation.signature, 64)
    ):
        return False
    expected = hmac.new(
        verification_key,
        transcript.payload_sha256.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, attestation.signature)


@dataclass(frozen=True)
class SupervisorResult:
    transcript: SupervisorTranscript
    attestation: SupervisorAttestation
    capture: RawProcessCapture
    comparison: ComparisonResult
    confirmation_eligible: bool
    reason: str


class TrustedCaptureSupervisor:
    """TCB-owned executor; the caller selects only a code-owned manifest ID."""

    def __init__(self, *, signing_key: bytes, provenance_verifier: HarnessProvenanceVerifier):
        self.__signer = _InternalHmacSigner(signing_key)
        self.__provenance_verifier = provenance_verifier

    def execute(self, request: SupervisorRequest) -> SupervisorResult:
        manifest = _CODE_OWNED_MANIFESTS.get(request.manifest_id)
        if manifest is None:
            raise ValueError("unknown or non-code-owned trusted execution manifest")
        if _sha256(request.stdin) != manifest.stdin_sha256:
            raise ValueError("stdin does not match the code-owned manifest")
        if not request.session_nonce or len(request.session_nonce) < 16:
            raise ValueError("session nonce is absent or too short")
        verification = self.__provenance_verifier.verify(manifest.provenance)
        adversary = derive_adversary_model(manifest.provenance, verification)
        cwd = Path(manifest.cwd).resolve() if manifest.cwd is not None else None
        capture = capture_raw_process(
            manifest.argv,
            stdin=request.stdin,
            cwd=cwd,
            environment=dict(manifest.environment),
            timeout_seconds=manifest.timeout_seconds,
            max_stdout_bytes=manifest.max_stdout_bytes,
            max_stderr_bytes=manifest.max_stderr_bytes,
        )
        if not capture.complete:
            comparison = ComparisonResult(None, "capture_incomplete")
        elif capture.exit_code != 0:
            comparison = ComparisonResult(None, "process_nonzero_exit")
        else:
            comparison = _COMPARISON_CONTRACTS[manifest.comparison_contract_id](
                capture.stdout, manifest.expected_stdout
            )
        transcript = SupervisorTranscript(
            manifest_id=manifest.manifest_id,
            item_id=manifest.item_id,
            candidate_id=manifest.candidate_id,
            oracle_id=manifest.oracle_id,
            comparison_contract_id=manifest.comparison_contract_id,
            expected_stdout_sha256=_sha256(manifest.expected_stdout),
            session_nonce=request.session_nonce,
            stdin_sha256=manifest.stdin_sha256,
            runtime_identity=manifest.runtime_identity,
            observation=capture.stable_observation(),
            comparison_accepted=comparison.accepted,
            comparison_reason=comparison.reason,
            adversary_model=adversary.model,
            adversary_relation=adversary.relation,
            provenance_reason=adversary.reason,
        )
        attestation = self.__signer.attest(transcript)
        eligible = (
            capture.complete
            and manifest.runtime_confirmation_eligible
            and adversary.confirmation_eligible
            and comparison.accepted is not None
        )
        if not capture.complete:
            reason = "capture incomplete due timeout, overflow, missing EOF, or missing exit"
        elif not manifest.runtime_confirmation_eligible:
            reason = "runtime manifest is not confirmation eligible"
        elif not adversary.confirmation_eligible:
            reason = adversary.reason
        elif comparison.accepted is None:
            reason = comparison.reason
        else:
            reason = "complete attested and locally compared observation"
        return SupervisorResult(transcript, attestation, capture, comparison, eligible, reason)


@dataclass(frozen=True)
class DifferentialAdjudicationDecision:
    status: str
    confirmation_eligible: bool
    reason: str


def adjudicate_weak_strong_pair(
    canonical_weak: SupervisorResult,
    canonical_strong: SupervisorResult,
    candidate_weak: SupervisorResult,
    candidate_strong: SupervisorResult,
    *,
    verification_key: bytes,
) -> DifferentialAdjudicationDecision:
    """Apply the MR-4 direction after independently verifying four captures.

    This returns a proof candidate, never a BenchAudit ``Violation``.  Promotion
    remains disabled and outside this module.
    """

    values = (canonical_weak, canonical_strong, candidate_weak, candidate_strong)
    if not all(
        verify_supervisor_attestation(
            value.transcript, value.attestation, verification_key=verification_key
        )
        for value in values
    ):
        return DifferentialAdjudicationDecision("review", False, "attestation rejected")
    if not all(value.confirmation_eligible for value in values):
        return DifferentialAdjudicationDecision("review", False, "one or more observations are ineligible")
    transcripts = tuple(value.transcript for value in values)
    if len({value.session_nonce for value in transcripts}) != 4:
        return DifferentialAdjudicationDecision("review", False, "session nonce replay detected")
    if len({value.item_id for value in transcripts}) != 1:
        return DifferentialAdjudicationDecision("review", False, "cross-item transcript set")
    if canonical_weak.transcript.candidate_id != canonical_strong.transcript.candidate_id:
        return DifferentialAdjudicationDecision("review", False, "canonical identity mismatch")
    if candidate_weak.transcript.candidate_id != candidate_strong.transcript.candidate_id:
        return DifferentialAdjudicationDecision("review", False, "candidate identity mismatch")
    if canonical_weak.transcript.candidate_id == candidate_weak.transcript.candidate_id:
        return DifferentialAdjudicationDecision("review", False, "canonical and candidate identities collide")
    if (
        canonical_weak.transcript.oracle_id != candidate_weak.transcript.oracle_id
        or canonical_strong.transcript.oracle_id != candidate_strong.transcript.oracle_id
        or canonical_weak.transcript.oracle_id == canonical_strong.transcript.oracle_id
    ):
        return DifferentialAdjudicationDecision("review", False, "weak/strong oracle bindings mismatch")
    if len({value.comparison_contract_id for value in transcripts}) != 1:
        return DifferentialAdjudicationDecision("review", False, "comparison contracts differ")
    outcomes = tuple(value.comparison.accepted for value in values)
    if outcomes[:2] != (True, True):
        return DifferentialAdjudicationDecision("no_finding", False, "canonical control did not pass both oracles")
    if outcomes[2:] == (True, False):
        return DifferentialAdjudicationDecision(
            "confirmed_relative_coverage_gap_candidate",
            True,
            "canonical passed weak+strong while candidate passed weak and failed strong",
        )
    return DifferentialAdjudicationDecision("no_finding", False, "MR-4 direction not observed")


def production_manifest_ids() -> tuple[str, ...]:
    """Expose nonactivation state without allowing callers to extend it."""

    return tuple(sorted(_CODE_OWNED_MANIFESTS))
