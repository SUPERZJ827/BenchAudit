from benchcore.execution_attestation import (
    ATTESTATION_PROTOCOL,
    SEPARATE_PROCESS_DOMAIN,
    canonical_transcript_payload,
    transcript_sha256,
    request_execution_attestation,
    verify_execution_attestation,
)


def _report():
    return {
        "driver_sha256": "a" * 64,
        "reference_code_sha256": "b" * 64,
        "code_context_sha256": "c" * 64,
        "gold": {"pass": True},
        "instrumented_gold": {"pass": True},
        "gold_verdicts": {"official": True},
        "gold_instrumentation_consistent": True,
        "input_materialization_complete": True,
        "observed_cases": [],
        "probes": [],
        "probe_failures": [],
    }


class AcceptingIndependentVerifier:
    def __init__(self):
        self.calls = []

    def verify(self, attestation, payload_sha256):
        self.calls.append((attestation, payload_sha256))
        return attestation.get("signature") == "verified-outside-harness"


class DeterministicAttester:
    def attest(self, payload_sha256):
        return {
            "protocol": ATTESTATION_PROTOCOL,
            "payload_sha256": payload_sha256,
            "signature": "verified-outside-harness",
        }


def test_transcript_hash_is_canonical_and_excludes_runtime_noise():
    report = _report()
    first = transcript_sha256(report)
    report["run"] = {"elapsed_seconds": 999, "cwd": "/untrusted/path"}
    assert transcript_sha256(report) == first
    assert canonical_transcript_payload(report)["protocol"] == ATTESTATION_PROTOCOL


def test_attestation_fails_closed_without_independent_verifier():
    report = _report()
    result = verify_execution_attestation(
        report,
        {
            "protocol": ATTESTATION_PROTOCOL,
            "payload_sha256": transcript_sha256(report),
            "signature": "claimed-by-harness",
        },
        None,
    )
    assert result.verified is False
    assert result.trust_domain != SEPARATE_PROCESS_DOMAIN


def test_attestation_requires_exact_payload_and_external_acceptance():
    report = _report()
    verifier = AcceptingIndependentVerifier()
    bad = verify_execution_attestation(
        report,
        {
            "protocol": ATTESTATION_PROTOCOL,
            "payload_sha256": "0" * 64,
            "signature": "verified-outside-harness",
        },
        verifier,
    )
    assert bad.verified is False
    assert verifier.calls == []

    attestation = {
        "protocol": ATTESTATION_PROTOCOL,
        "payload_sha256": transcript_sha256(report),
        "signature": "verified-outside-harness",
    }
    good = verify_execution_attestation(report, attestation, verifier)
    assert good.verified is True
    assert good.trust_domain == SEPARATE_PROCESS_DOMAIN
    assert good.as_evidence()["execution_attestation"] == attestation


def test_separate_attester_output_is_still_checked_by_verifier():
    report = _report()
    attestation = request_execution_attestation(report, DeterministicAttester())
    result = verify_execution_attestation(
        report, attestation, AcceptingIndependentVerifier(),
    )
    assert result.verified is True
