"""Generic weak/strong-oracle differential confirmation.

This module proves one deliberately narrow fact: the same candidate is
accepted by a declared weak oracle and rejected by a declared stronger oracle.
It does not infer human intent and it does not treat timeouts as rejections.

Confirmation requires an explicit typed contract, a passing canonical control,
completed observations on both sides, and an independently verified execution
transcript.  Benchmark-specific data loading and execution adapters stay
outside this module.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .checkers import Checker, _violation
from .coverage import AuditEligibility
from .execution_attestation import (
    ExecutionTranscriptAttester,
    ExecutionTranscriptVerifier,
    request_execution_attestation,
    verify_execution_attestation,
)
from .schema import BenchmarkItem, Violation


DIFFERENTIAL_ORACLE_CONTRACT_VERSION = (
    "benchcore-differential-oracle-contract-v1"
)
DIFFERENTIAL_ORACLE_PROOF_VERSION = "benchcore-differential-oracle-proof-v1"
_RELATION = "declared_strict_test_extension"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _manifest_sha256(value: Sequence[Mapping[str, Any]]) -> str:
    encoded = json.dumps(
        list(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return _sha256_text(encoded)


@dataclass(frozen=True)
class OracleObservation:
    """Typed outcome; a timeout/error is never a semantic rejection."""

    status: str
    accepted: bool | None
    detail: str | None = None

    @classmethod
    def completed(cls, accepted: bool, detail: str | None = None) -> "OracleObservation":
        return cls("completed", bool(accepted), detail)

    @classmethod
    def timeout(cls, detail: str | None = None) -> "OracleObservation":
        return cls("timeout", None, detail)

    @classmethod
    def error(cls, detail: str | None = None) -> "OracleObservation":
        return cls("error", None, detail)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DifferentialCandidate:
    candidate_id: str
    source: str
    family: str
    transformation_index: int

    def to_evidence(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_source_sha256": _sha256_text(self.source),
            "family": self.family,
            "transformation_index": self.transformation_index,
        }


class DifferentialOracleEvaluator(Protocol):
    """Execution adapter supplied by a benchmark loader or external runner."""

    identity: str
    oracle_identities: tuple[str, str]

    def evaluate(
        self,
        item: BenchmarkItem,
        candidate: str,
        oracle_identity: str,
    ) -> OracleObservation: ...


def build_differential_report(
    *,
    canonical_source: str,
    evaluator_identity: str,
    contract: Mapping[str, Any],
    canonical_weak: OracleObservation,
    canonical_strong: OracleObservation,
    rows: Sequence[Mapping[str, Any]],
    execution_driver_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the exact attested payload from typed runner observations."""
    normalized_rows = [dict(row) for row in rows]
    return {
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reference_code_sha256": _sha256_text(canonical_source),
        "code_context_sha256": _sha256_text(evaluator_identity),
        "gold": canonical_weak.to_dict(),
        "instrumented_gold": canonical_strong.to_dict(),
        "gold_verdicts": {
            "weak": canonical_weak.accepted,
            "strong": canonical_strong.accepted,
        },
        "gold_instrumentation_consistent": (
            canonical_weak.status == "completed"
            and canonical_strong.status == "completed"
            and canonical_weak.accepted is True
            and canonical_strong.accepted is True
        ),
        "input_materialization_complete": True,
        "observed_cases": [{
            "relation": contract.get("relation"),
            "weak_oracle_identity": contract.get("weak_oracle_identity"),
            "strong_oracle_identity": contract.get("strong_oracle_identity"),
            "source_revision": contract.get("source_revision"),
            "candidate_manifest_sha256": contract.get(
                "candidate_manifest_sha256"
            ),
            "execution_driver_sha256": execution_driver_sha256,
        }],
        "probes": normalized_rows,
        "probe_failures": [
            row for row in normalized_rows
            if row["weak"]["status"] != "completed"
            or row["strong"]["status"] != "completed"
        ],
    }


def validated_contract(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    contract = dict(value)
    required = (
        "schema_version",
        "relation",
        "evaluator_identity",
        "weak_oracle_identity",
        "strong_oracle_identity",
        "source_revision",
        "candidate_manifest_sha256",
    )
    if any(not isinstance(contract.get(key), str) or not contract[key] for key in required):
        return None
    if contract["schema_version"] != DIFFERENTIAL_ORACLE_CONTRACT_VERSION:
        return None
    if contract["relation"] != _RELATION:
        return None
    if contract["weak_oracle_identity"] == contract["strong_oracle_identity"]:
        return None
    if contract.get("canonical_must_pass_both") is not True:
        return None
    manifest = contract.get("candidate_manifest")
    if (
        not isinstance(manifest, list)
        or not manifest
        or not all(isinstance(row, dict) for row in manifest)
        or contract["candidate_manifest_sha256"] != _manifest_sha256(manifest)
    ):
        return None
    return contract


class DifferentialOracleAuditChecker(Checker):
    """Execute a frozen candidate set against a generic weak/strong pair."""

    name = "differential_oracle_audit"

    def __init__(
        self,
        evaluator: DifferentialOracleEvaluator,
        candidates: Sequence[DifferentialCandidate],
        *,
        transcript_attester: ExecutionTranscriptAttester | None = None,
        transcript_verifier: ExecutionTranscriptVerifier | None = None,
    ) -> None:
        self.evaluator = evaluator
        self.candidates = tuple(candidates)
        self.transcript_attester = transcript_attester
        self.transcript_verifier = transcript_verifier

    def _contract(self, item: BenchmarkItem) -> dict[str, Any] | None:
        evaluator = item.evaluator if isinstance(item.evaluator, dict) else {}
        contract = validated_contract(evaluator.get("differential_oracle_contract"))
        if contract is None:
            return None
        if contract["evaluator_identity"] != getattr(self.evaluator, "identity", None):
            return None
        expected = (
            contract["weak_oracle_identity"],
            contract["strong_oracle_identity"],
        )
        if expected != getattr(self.evaluator, "oracle_identities", None):
            return None
        if contract["candidate_manifest"] != [
            candidate.to_evidence() for candidate in self.candidates
        ]:
            return None
        return contract

    def audit_eligibility(
        self,
        item: BenchmarkItem,
        root: Path | None = None,
    ) -> AuditEligibility:
        del root
        if not isinstance(item.gold, str) or not item.gold:
            return AuditEligibility.not_applicable(
                "differential replay requires canonical candidate source"
            )
        if self._contract(item) is None:
            return AuditEligibility.not_applicable(
                "differential replay requires a typed weak/strong-oracle contract"
            )
        if not self.candidates:
            return AuditEligibility.not_applicable(
                "differential replay requires at least one frozen candidate"
            )
        return AuditEligibility.applicable(
            "typed weak/strong-oracle contract and frozen candidates are available"
        )

    @staticmethod
    def _observe(
        evaluator: DifferentialOracleEvaluator,
        item: BenchmarkItem,
        candidate: str,
        oracle_identity: str,
    ) -> OracleObservation:
        try:
            value = evaluator.evaluate(item, candidate, oracle_identity)
        except TimeoutError as exc:
            return OracleObservation.timeout(type(exc).__name__)
        except Exception as exc:
            return OracleObservation.error(type(exc).__name__)
        if not isinstance(value, OracleObservation):
            return OracleObservation.error("invalid evaluator observation")
        if value.status == "completed" and not isinstance(value.accepted, bool):
            return OracleObservation.error("completed outcome lacks boolean verdict")
        if value.status not in {"completed", "timeout", "error"}:
            return OracleObservation.error("unsupported outcome status")
        return value

    def check(
        self,
        item: BenchmarkItem,
        root: Path | None = None,
    ) -> Iterable[Violation]:
        del root
        contract = self._contract(item)
        if contract is None or not isinstance(item.gold, str) or not item.gold:
            return
        weak_id = contract["weak_oracle_identity"]
        strong_id = contract["strong_oracle_identity"]
        canonical_weak = self._observe(self.evaluator, item, item.gold, weak_id)
        canonical_strong = self._observe(self.evaluator, item, item.gold, strong_id)

        rows: list[dict[str, Any]] = []
        for candidate in self.candidates:
            rows.append({
                "candidate": candidate.to_evidence(),
                "weak": self._observe(
                    self.evaluator, item, candidate.source, weak_id,
                ).to_dict(),
                "strong": self._observe(
                    self.evaluator, item, candidate.source, strong_id,
                ).to_dict(),
            })

        report = build_differential_report(
            canonical_source=item.gold,
            evaluator_identity=self.evaluator.identity,
            contract=contract,
            canonical_weak=canonical_weak,
            canonical_strong=canonical_strong,
            rows=rows,
            execution_driver_sha256=getattr(
                self.evaluator, "execution_driver_sha256", None,
            ),
        )
        attestation = request_execution_attestation(
            report, self.transcript_attester,
        )
        trust = verify_execution_attestation(
            report, attestation, self.transcript_verifier,
        )
        trust_evidence = trust.as_evidence()
        item.metadata["_differential_oracle_report"] = {
            "schema_version": "benchcore-differential-oracle-report-v1",
            "contract": contract,
            "canonical_weak": canonical_weak.to_dict(),
            "canonical_strong": canonical_strong.to_dict(),
            "probes": rows,
            **trust_evidence,
        }

        canonical_ok = (
            canonical_weak.status == "completed"
            and canonical_weak.accepted is True
            and canonical_strong.status == "completed"
            and canonical_strong.accepted is True
        )
        if not canonical_ok:
            return

        attested = trust.verified is True
        common = {
            "contract": contract,
            "evaluator": item.evaluator,
            "evaluator_identity": self.evaluator.identity,
            "baseline_weak": canonical_weak.to_dict(),
            "baseline_strong": canonical_strong.to_dict(),
            "original_answer_sha256": _sha256_text(item.gold),
            "driver_sha256": report["driver_sha256"],
            "reference_code_sha256": report["reference_code_sha256"],
            "code_context_sha256": report["code_context_sha256"],
            **trust_evidence,
        }
        for row in rows:
            weak = row["weak"]
            strong = row["strong"]
            if not (
                weak["status"] == "completed"
                and weak["accepted"] is True
                and strong["status"] == "completed"
                and strong["accepted"] is False
            ):
                continue
            yield _violation(
                item,
                "evaluator_mutation_survived",
                0.99 if attested else 0.72,
                (
                    "The declared weak oracle accepts a candidate that the "
                    "declared stronger oracle rejects."
                ),
                {
                    **common,
                    "candidate": row["candidate"],
                    "weak_observation": weak,
                    "strong_observation": strong,
                    "evidence_level": "executed_differential_oracle_replay",
                    "proof_schema_version": "1.0",
                },
                severity="major" if attested else "review",
                review_only=not attested,
                repair=(
                    "Add a distinguishing weak-oracle test or align the declared "
                    "weak and strong oracle contracts."
                ),
                method="execution_differential_oracle",
                artifact="evaluator",
            )


def replay_differential_oracle_proof(
    violation: Violation,
    item: BenchmarkItem | None,
) -> bool:
    """Rebind a finding to the live item; attestation is checked by promotion."""
    if item is None or not isinstance(item.gold, str) or not item.gold:
        return False
    evidence = violation.evidence
    evaluator = item.evaluator if isinstance(item.evaluator, dict) else {}
    contract = validated_contract(evaluator.get("differential_oracle_contract"))
    candidate = evidence.get("candidate")
    weak = evidence.get("weak_observation")
    strong = evidence.get("strong_observation")
    baseline_weak = evidence.get("baseline_weak")
    baseline_strong = evidence.get("baseline_strong")
    identity = contract.get("evaluator_identity") if contract else None
    return bool(
        contract is not None
        and isinstance(candidate, dict)
        and isinstance(weak, dict)
        and isinstance(strong, dict)
        and isinstance(baseline_weak, dict)
        and isinstance(baseline_strong, dict)
        and evidence.get("evaluator") == evaluator
        and evidence.get("contract") == contract
        and evidence.get("evaluator_identity") == identity
        and evidence.get("original_answer_sha256") == _sha256_text(item.gold)
        and evidence.get("reference_code_sha256") == _sha256_text(item.gold)
        and evidence.get("code_context_sha256") == _sha256_text(identity)
        and evidence.get("driver_sha256")
        == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        and candidate.get("candidate_id")
        and candidate.get("family")
        and isinstance(candidate.get("transformation_index"), int)
        and candidate in contract["candidate_manifest"]
        and baseline_weak.get("status") == "completed"
        and baseline_weak.get("accepted") is True
        and baseline_strong.get("status") == "completed"
        and baseline_strong.get("accepted") is True
        and weak.get("status") == "completed"
        and weak.get("accepted") is True
        and strong.get("status") == "completed"
        and strong.get("accepted") is False
    )
