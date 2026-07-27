from __future__ import annotations

import hashlib
import json

from benchcore.differential_oracle import (
    DIFFERENTIAL_ORACLE_CONTRACT_VERSION,
    DifferentialCandidate,
    DifferentialOracleAuditChecker,
    OracleObservation,
)
from benchcore.execution_attestation import ATTESTATION_PROTOCOL
from benchcore.loader import explicit_mapping_provenance
from benchcore.promotion import decide_promotion
from benchcore.schema import BenchmarkItem


class DeterministicAttester:
    def attest(self, payload_sha256):
        return {
            "protocol": ATTESTATION_PROTOCOL,
            "payload_sha256": payload_sha256,
            "signature": "observed-by-separate-runner",
        }


class IndependentVerifier:
    def verify(self, attestation, payload_sha256):
        return (
            attestation.get("payload_sha256") == payload_sha256
            and attestation.get("signature") == "observed-by-separate-runner"
        )


class FixtureOraclePair:
    identity = "fixture:oracle-pair:v1"
    oracle_identities = ("fixture:weak:v1", "fixture:strong:v1")

    def __init__(self, outcomes=None):
        self.outcomes = outcomes or {}

    def evaluate(self, item, candidate, oracle_identity):
        del item
        return self.outcomes.get(
            (candidate, oracle_identity),
            OracleObservation.completed(True),
        )


def item() -> BenchmarkItem:
    manifest = [candidate().to_evidence()]
    manifest_sha256 = hashlib.sha256(json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    contract = {
        "schema_version": DIFFERENTIAL_ORACLE_CONTRACT_VERSION,
        "relation": "declared_strict_test_extension",
        "evaluator_identity": FixtureOraclePair.identity,
        "weak_oracle_identity": FixtureOraclePair.oracle_identities[0],
        "strong_oracle_identity": FixtureOraclePair.oracle_identities[1],
        "source_revision": "fixture-revision-1",
        "canonical_must_pass_both": True,
        "candidate_manifest": manifest,
        "candidate_manifest_sha256": manifest_sha256,
    }
    evaluator = {"differential_oracle_contract": contract}
    raw = {"id": "q1", "canonical": "def f(): return 1", "evaluator": evaluator}
    value = BenchmarkItem(
        item_id="q1",
        raw=raw,
        task="Return one.",
        gold=raw["canonical"],
        evaluator=evaluator,
    )
    value.metadata["_mapping_provenance"] = explicit_mapping_provenance(
        adapter_id="test_differential_oracle",
        adapter_version="1",
        raw=raw,
        field_bindings={
            "item_id": "id",
            "gold": "canonical",
            "evaluator": "evaluator",
        },
    )
    return value


def candidate() -> DifferentialCandidate:
    return DifferentialCandidate(
        candidate_id="numeric_constant:0",
        source="def f(): return 2",
        family="numeric_constant",
        transformation_index=0,
    )


def checker(outcomes=None, *, attested=True):
    return DifferentialOracleAuditChecker(
        FixtureOraclePair(outcomes),
        [candidate()],
        transcript_attester=DeterministicAttester() if attested else None,
        transcript_verifier=IndependentVerifier() if attested else None,
    )


def witness_outcomes():
    return {
        (candidate().source, FixtureOraclePair.oracle_identities[0]):
            OracleObservation.completed(True),
        (candidate().source, FixtureOraclePair.oracle_identities[1]):
            OracleObservation.completed(False, "AssertionError"),
    }


def test_attested_weak_pass_strong_fail_is_confirmed():
    findings = list(checker(witness_outcomes()).check(item()))
    assert len(findings) == 1
    assert findings[0].defect_type == "evaluator_mutation_survived"
    assert findings[0].evidence_tier == "confirmed"
    assert findings[0].proof_kind == "isolated_execution"


def test_same_witness_without_attestation_is_review_only():
    findings = list(checker(witness_outcomes(), attested=False).check(item()))
    assert len(findings) == 1
    assert findings[0].evidence_tier == "review"
    assert findings[0].review_only is True


def test_timeout_is_indeterminate_not_rejection():
    outcomes = witness_outcomes()
    outcomes[(candidate().source, FixtureOraclePair.oracle_identities[1])] = (
        OracleObservation.timeout("ProbeTimeout")
    )
    assert list(checker(outcomes).check(item())) == []


def test_swapped_direction_is_not_underconstrained_finding():
    outcomes = {
        (candidate().source, FixtureOraclePair.oracle_identities[0]):
            OracleObservation.completed(False),
        (candidate().source, FixtureOraclePair.oracle_identities[1]):
            OracleObservation.completed(True),
    }
    assert list(checker(outcomes).check(item())) == []


def test_canonical_failure_invalidates_all_candidate_verdicts():
    value = item()
    outcomes = witness_outcomes()
    outcomes[(value.gold, FixtureOraclePair.oracle_identities[1])] = (
        OracleObservation.completed(False)
    )
    assert list(checker(outcomes).check(value)) == []


def test_identical_oracle_contract_is_rejected():
    value = item()
    contract = value.evaluator["differential_oracle_contract"]
    contract["strong_oracle_identity"] = contract["weak_oracle_identity"]
    assert list(checker(witness_outcomes()).check(value)) == []


def test_promotion_replay_rejects_tampered_candidate_hash():
    value = item()
    finding = list(checker(witness_outcomes()).check(value))[0]
    finding.evidence["candidate"]["candidate_source_sha256"] = "0" * 64
    decision = decide_promotion(finding, value)
    assert decision.tier == "review"
