from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import sys

import pytest

import benchcore.trusted_adjudicator as adjudicator
from benchcore.trusted_adjudicator import (
    HarnessProvenanceClaim,
    HarnessProvenanceVerification,
    SupervisorRequest,
    TrustedCaptureSupervisor,
    TrustedExecutionManifest,
    capture_raw_process,
    adjudicate_weak_strong_pair,
    derive_adversary_model,
    production_manifest_ids,
    verify_supervisor_attestation,
)


KEY = b"phase-2a-fixture-key-material-32-bytes!!"


def _claim(*, strict: bool = False) -> HarnessProvenanceClaim:
    source = "1" * 40 if strict else "2" * 40
    return HarnessProvenanceClaim(
        canonical_remote="https://huggingface.co/datasets/codeparrot/apps",
        harness_revision_commit=source,
        benchmark_cutoff_commit="2" * 40,
        harness_content_sha256="3" * 64,
        cutoff_binding_receipt_sha256="4" * 64,
        cutoff_binding_benchaudit_commit="5" * 40,
    )


def _verification(claim: HarnessProvenanceClaim) -> HarnessProvenanceVerification:
    equal = claim.harness_revision_commit == claim.benchmark_cutoff_commit
    return HarnessProvenanceVerification(
        verified=True,
        reason="fixture",
        trust_domain="canonical_git_and_benchaudit_history_v1",
        canonical_remote_verified=True,
        verified_remote=claim.canonical_remote,
        harness_revision_commit=claim.harness_revision_commit,
        benchmark_cutoff_commit=claim.benchmark_cutoff_commit,
        harness_content_sha256=claim.harness_content_sha256,
        harness_is_ancestor_of_cutoff=True,
        cutoff_is_ancestor_of_harness=equal,
        cutoff_binding_receipt_sha256=claim.cutoff_binding_receipt_sha256,
        cutoff_binding_benchaudit_commit=claim.cutoff_binding_benchaudit_commit,
        cutoff_binding_is_ancestor_of_protocol=True,
        receipt_records_outcomes_uninspected=True,
    )


class StaticVerifier:
    def __init__(self, value: HarnessProvenanceVerification):
        self.value = value

    def verify(self, claim):
        del claim
        return self.value


def _manifest(
    source: str,
    stdin: bytes = b"input\n",
    *,
    eligible: bool = True,
    manifest_id: str = "fixture-v1",
    candidate_id: str = "candidate:0",
    oracle_id: str = "weak",
    expected_stdout: bytes = b"input\n",
):
    claim = _claim()
    return TrustedExecutionManifest(
        manifest_id=manifest_id,
        item_id="fixture/item",
        candidate_id=candidate_id,
        oracle_id=oracle_id,
        comparison_contract_id="apps-stdin-comparator-v1",
        expected_stdout=expected_stdout,
        argv=(sys.executable, "-I", "-c", source),
        cwd=None,
        environment=(("PATH", os.environ.get("PATH", "")),),
        stdin_sha256=hashlib.sha256(stdin).hexdigest(),
        runtime_identity="fixture-runtime-sha256:" + "6" * 64,
        runtime_confirmation_eligible=eligible,
        timeout_seconds=1.0,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
        provenance=claim,
    )


def _execute(
    monkeypatch,
    manifest,
    stdin=b"input\n",
    verifier=None,
    nonce="fixture-session-0001",
):
    monkeypatch.setitem(adjudicator._CODE_OWNED_MANIFESTS, manifest.manifest_id, manifest)
    verifier = verifier or StaticVerifier(_verification(manifest.provenance))
    return TrustedCaptureSupervisor(
        signing_key=KEY,
        provenance_verifier=verifier,
    ).execute(SupervisorRequest(
        manifest_id=manifest.manifest_id,
        stdin=stdin,
        session_nonce=nonce,
        claimed_adversary_model="caller_claim_is_ignored",
    ))


def test_equal_and_strict_ancestor_models_are_derived_from_verified_facts():
    equal = _claim()
    equal_decision = derive_adversary_model(equal, _verification(equal))
    assert equal_decision.confirmation_eligible is True
    assert equal_decision.relation == "equal_tautological_ancestry"

    strict = _claim(strict=True)
    strict_decision = derive_adversary_model(strict, _verification(strict))
    assert strict_decision.confirmation_eligible is True
    assert strict_decision.relation == "strict_ancestor"


def test_equal_commit_without_benchaudit_cutoff_binding_is_review_only():
    claim = _claim()
    verification = replace(
        _verification(claim),
        cutoff_binding_is_ancestor_of_protocol=False,
    )
    decision = derive_adversary_model(claim, verification)
    assert decision.confirmation_eligible is False
    assert decision.model is None


def test_distinct_bidirectional_ancestry_is_rejected():
    claim = _claim(strict=True)
    verification = replace(
        _verification(claim),
        cutoff_is_ancestor_of_harness=True,
    )
    assert derive_adversary_model(claim, verification).relation == "invalid"


def test_raw_capture_preserves_non_utf8_and_separates_stderr():
    source = "import os; os.write(1, b'\\xffout'); os.write(2, b'err\\xfe')"
    capture = capture_raw_process(
        (sys.executable, "-I", "-c", source),
        stdin=b"",
        cwd=None,
        environment={"PATH": os.environ.get("PATH", "")},
        timeout_seconds=1,
        max_stdout_bytes=100,
        max_stderr_bytes=100,
    )
    assert capture.complete is True
    assert capture.stdout == b"\xffout"
    assert capture.stderr == b"err\xfe"


def test_timeout_and_partial_output_never_become_complete():
    source = "import os,time; os.write(1,b'partial'); time.sleep(5)"
    capture = capture_raw_process(
        (sys.executable, "-I", "-c", source),
        stdin=b"",
        cwd=None,
        environment={"PATH": os.environ.get("PATH", "")},
        timeout_seconds=0.05,
        max_stdout_bytes=100,
        max_stderr_bytes=100,
    )
    assert capture.stdout == b"partial"
    assert capture.timed_out is True
    assert capture.complete is False


def test_descendant_retaining_stdout_cannot_create_complete_observation():
    source = (
        "import subprocess,sys; "
        "subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(5)']); "
        "print('leader-exited')"
    )
    capture = capture_raw_process(
        (sys.executable, "-I", "-c", source),
        stdin=b"",
        cwd=None,
        environment={"PATH": os.environ.get("PATH", "")},
        timeout_seconds=0.1,
        max_stdout_bytes=100,
        max_stderr_bytes=100,
    )
    assert capture.stdout == b"leader-exited\n"
    assert capture.timed_out is True
    assert capture.complete is False


def test_output_overflow_is_bounded_and_incomplete():
    capture = capture_raw_process(
        (sys.executable, "-I", "-c", "import os; os.write(1,b'x'*10000)"),
        stdin=b"",
        cwd=None,
        environment={"PATH": os.environ.get("PATH", "")},
        timeout_seconds=1,
        max_stdout_bytes=64,
        max_stderr_bytes=64,
    )
    assert len(capture.stdout) == 64
    assert capture.stdout_overflow is True
    assert capture.complete is False


def test_supervisor_ignores_caller_model_and_signs_its_own_capture(monkeypatch):
    manifest = _manifest("import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data)")
    result = _execute(monkeypatch, manifest)
    assert result.capture.stdout == b"input\n"
    assert result.comparison.accepted is True
    assert result.transcript.adversary_model == adjudicator.NON_ADAPTIVE_MODEL
    assert "caller_claim" not in str(result.transcript.payload())
    assert result.confirmation_eligible is True
    assert verify_supervisor_attestation(
        result.transcript, result.attestation, verification_key=KEY
    )
    assert "key" not in result.attestation.as_dict()


def test_attestation_rejects_wrong_key_and_cross_item_replay(monkeypatch):
    result = _execute(monkeypatch, _manifest("print('ok')"))
    assert not verify_supervisor_attestation(
        result.transcript, result.attestation, verification_key=b"z" * 32
    )
    changed = replace(result.transcript, item_id="other/item")
    assert not verify_supervisor_attestation(
        changed, result.attestation, verification_key=KEY
    )


def test_incomplete_capture_and_unpinned_runtime_are_review_only(monkeypatch):
    timeout = replace(_manifest("import time; time.sleep(5)"), timeout_seconds=0.05)
    assert _execute(monkeypatch, timeout).confirmation_eligible is False

    unpinned = _manifest("print('ok')", eligible=False)
    assert _execute(monkeypatch, unpinned).confirmation_eligible is False


@pytest.mark.parametrize(
    ("source", "expected", "accepted"),
    [
        ("print(' 4 ')", b"4\n", True),
        ("print(1/3)", b"0.333333\n", True),
        ("print('b a b')", b"a b b\n", True),
        ("print('wrong')", b"right\n", False),
    ],
)
def test_code_owned_apps_comparator_runs_after_capture(
    monkeypatch, source, expected, accepted,
):
    manifest = _manifest(source, stdin=b"", expected_stdout=expected)
    result = _execute(monkeypatch, manifest, stdin=b"")
    assert result.comparison.accepted is accepted
    assert result.confirmation_eligible is True


def test_non_utf8_comparison_abstains(monkeypatch):
    manifest = _manifest(
        "import os; os.write(1,b'\\xff')",
        stdin=b"",
        expected_stdout=b"value",
    )
    result = _execute(monkeypatch, manifest, stdin=b"")
    assert result.comparison.accepted is None
    assert result.confirmation_eligible is False


def test_unverifiable_provenance_is_review_only(monkeypatch):
    manifest = _manifest("print('ok')")
    bad = replace(_verification(manifest.provenance), verified=False)
    result = _execute(monkeypatch, manifest, verifier=StaticVerifier(bad))
    assert result.confirmation_eligible is False
    assert result.transcript.adversary_model is None


def test_manifest_and_stdin_are_fail_closed(monkeypatch):
    supervisor = TrustedCaptureSupervisor(
        signing_key=KEY,
        provenance_verifier=StaticVerifier(_verification(_claim())),
    )
    with pytest.raises(ValueError, match="unknown or non-code-owned"):
        supervisor.execute(SupervisorRequest("missing", b"", "fixture-session-0001"))

    manifest = _manifest("print('ok')")
    monkeypatch.setitem(adjudicator._CODE_OWNED_MANIFESTS, manifest.manifest_id, manifest)
    with pytest.raises(ValueError, match="stdin does not match"):
        supervisor.execute(SupervisorRequest(manifest.manifest_id, b"wrong", "fixture-session-0001"))


def test_stable_transcript_excludes_elapsed_time(monkeypatch):
    manifest = _manifest("print('stable')")
    first = _execute(monkeypatch, manifest)
    second = _execute(monkeypatch, manifest)
    assert first.transcript.payload_sha256 == second.transcript.payload_sha256
    changed_nonce = replace(second.transcript, session_nonce="fixture-session-0002")
    assert changed_nonce.payload_sha256 != first.transcript.payload_sha256


def _four_results(monkeypatch, *, candidate_strong_source="print('bad')"):
    common = {"stdin": b"", "expected_stdout": b"ok\n"}
    return (
        _execute(monkeypatch, _manifest(
            "print('ok')", manifest_id="cw", candidate_id="canonical",
            oracle_id="weak", **common,
        ), stdin=b"", nonce="session-canonical-weak"),
        _execute(monkeypatch, _manifest(
            "print('ok')", manifest_id="cs", candidate_id="canonical",
            oracle_id="strong", **common,
        ), stdin=b"", nonce="session-canonical-strong"),
        _execute(monkeypatch, _manifest(
            "print('ok')", manifest_id="mw", candidate_id="mutant",
            oracle_id="weak", **common,
        ), stdin=b"", nonce="session-mutant-weak"),
        _execute(monkeypatch, _manifest(
            candidate_strong_source, manifest_id="ms", candidate_id="mutant",
            oracle_id="strong", **common,
        ), stdin=b"", nonce="session-mutant-strong"),
    )


def test_weak_pass_strong_fail_is_the_only_confirmable_direction(monkeypatch):
    values = _four_results(monkeypatch)
    decision = adjudicate_weak_strong_pair(*values, verification_key=KEY)
    assert decision.status == "confirmed_relative_coverage_gap_candidate"
    assert decision.confirmation_eligible is True

    all_pass = _four_results(monkeypatch, candidate_strong_source="print('ok')")
    assert adjudicate_weak_strong_pair(
        *all_pass, verification_key=KEY
    ).status == "no_finding"


def test_differential_rejects_nonce_replay_and_attestation_tamper(monkeypatch):
    values = list(_four_results(monkeypatch))
    values[3] = replace(
        values[3],
        transcript=replace(
            values[3].transcript,
            session_nonce=values[2].transcript.session_nonce,
        ),
    )
    assert adjudicate_weak_strong_pair(
        *values, verification_key=KEY
    ).status == "review"

    untampered = list(_four_results(monkeypatch))
    untampered[3] = replace(
        untampered[3],
        transcript=replace(untampered[3].transcript, item_id="other/item"),
    )
    assert adjudicate_weak_strong_pair(
        *untampered, verification_key=KEY
    ).status == "review"


def test_production_registry_and_integration_remain_inactive():
    assert production_manifest_ids() == ()
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "benchcore/cli.py",
        "benchcore/promotion.py",
        "benchcore/evaluator_execution.py",
    ):
        assert "trusted_adjudicator" not in (root / relative).read_text(encoding="utf-8")
    promotion = (root / "benchcore/promotion.py").read_text(encoding="utf-8")
    assert "DISABLED_UNATTESTED_PROOFS" in promotion
