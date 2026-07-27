"""Type-scoped metamorphic relations for evaluator consistency auditing.

The module deliberately separates three claims:

* a deterministic transformer proves that two answer representations have the
  same meaning under an explicit semantic profile;
* an evaluator executes both representations and reports verdicts;
* an independent attestation service binds the verdict-bearing transcript.

Only the conjunction can become confirmed.  LLM-generated transformations and
untyped whitespace edits are intentionally outside this module.
"""
from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from .checkers import Checker, _violation
from .coverage import AuditEligibility
from .execution_attestation import (
    ExecutionTranscriptAttester,
    ExecutionTranscriptVerifier,
    request_execution_attestation,
    verify_execution_attestation,
)
from .schema import BenchmarkItem, Violation


METAMORPHIC_CONTRACT_VERSION = "benchcore-metamorphic-contract-v1"
METAMORPHIC_PROOF_VERSION = "benchcore-metamorphic-proof-v1"
SUPPORTED_SEMANTIC_PROFILES = frozenset({
    "numeric_value",
    "python_ast",
    "sql_layout",
    "trim_insensitive_text",
})


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_decimal(value: str) -> str | None:
    try:
        parsed = Decimal(value.strip())
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    normalized = parsed.normalize()
    if normalized == 0:
        normalized = Decimal(0)
    return format(normalized, "f")


def _python_ast_digest(value: str) -> str | None:
    try:
        tree = ast.parse(value)
    except (SyntaxError, ValueError, TypeError):
        return None
    material = ast.dump(tree, annotate_fields=True, include_attributes=False)
    return _sha256_text(material)


@dataclass(frozen=True)
class MetamorphicVariant:
    relation_id: str
    transformation_id: str
    original: str
    transformed: str
    semantic_profile: str
    semantics_preserving_rationale: str
    semantics_proof: dict[str, Any]

    def to_evidence(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("original")
        value.pop("transformed")
        value["original_sha256"] = _sha256_text(self.original)
        value["transformed_sha256"] = _sha256_text(self.transformed)
        return value


@dataclass(frozen=True)
class EvaluatorObservation:
    status: str
    accepted: bool | None
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"completed", "timeout", "error"}:
            raise ValueError(f"unsupported evaluator observation status: {self.status}")
        if self.status == "completed" and not isinstance(self.accepted, bool):
            raise ValueError("completed evaluator observation requires a boolean verdict")
        if self.status != "completed" and self.accepted is not None:
            raise ValueError("non-completed evaluator observation cannot carry a verdict")

    @classmethod
    def completed(
        cls, accepted: bool, detail: Mapping[str, Any] | None = None,
    ) -> "EvaluatorObservation":
        return cls("completed", bool(accepted), dict(detail or {}))

    @classmethod
    def timeout(cls, reason: str) -> "EvaluatorObservation":
        return cls("timeout", None, {"reason": str(reason)})

    @classmethod
    def error(cls, reason: str) -> "EvaluatorObservation":
        return cls("error", None, {"reason": str(reason)})

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "accepted": self.accepted,
            "detail": dict(self.detail),
        }


class MetamorphicEvaluator(Protocol):
    identity: str

    def evaluate(
        self, item: BenchmarkItem, answer: str,
    ) -> EvaluatorObservation: ...


def _validated_contract(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if value.get("schema_version") != METAMORPHIC_CONTRACT_VERSION:
        return None
    profile = value.get("semantic_profile")
    identity = value.get("evaluator_identity")
    if (
        profile not in SUPPORTED_SEMANTIC_PROFILES
        or not isinstance(identity, str)
        or not identity.strip()
    ):
        return None
    return dict(value)


def _numeric_variants(answer: str) -> list[MetamorphicVariant]:
    canonical = _canonical_decimal(answer)
    if canonical is None:
        return []
    stripped = answer.strip()
    candidates: list[tuple[str, str, str]] = []
    if "." in stripped:
        candidates.append((
            "numeric_trailing_zero",
            stripped + "0",
            "Appending a fractional trailing zero preserves the exact Decimal value.",
        ))
    else:
        candidates.append((
            "numeric_explicit_fraction",
            stripped + ".0",
            "Adding a zero fractional part preserves the exact Decimal value.",
        ))
    unsigned = stripped[1:] if stripped.startswith(("+", "-")) else stripped
    sign = stripped[:1] if stripped.startswith(("+", "-")) else ""
    if unsigned.startswith("0.") and len(unsigned) > 2:
        candidates.append((
            "numeric_omitted_leading_zero",
            sign + unsigned[1:],
            "Omitting the optional leading zero preserves the exact Decimal value.",
        ))
    candidates.append((
        "numeric_trailing_space",
        stripped + " ",
        "Trailing ASCII space is outside the numeric token and does not change its Decimal value.",
    ))

    variants: list[MetamorphicVariant] = []
    seen = {answer}
    for transformation_id, transformed, rationale in candidates:
        if transformed in seen or _canonical_decimal(transformed) != canonical:
            continue
        seen.add(transformed)
        variants.append(MetamorphicVariant(
            relation_id="evaluator_format_invariance",
            transformation_id=transformation_id,
            original=answer,
            transformed=transformed,
            semantic_profile="numeric_value",
            semantics_preserving_rationale=rationale,
            semantics_proof={
                "schema_version": METAMORPHIC_PROOF_VERSION,
                "kind": "decimal_value_equivalence",
                "canonical_value": canonical,
                "verified": True,
            },
        ))
    return variants


def _python_variants(answer: str) -> list[MetamorphicVariant]:
    original_digest = _python_ast_digest(answer)
    if original_digest is None:
        return []
    candidates = [
        (
            "python_terminal_newline",
            answer.rstrip("\n") + "\n",
            "A terminal newline does not change the parsed Python AST.",
        ),
        (
            "python_trailing_comment",
            answer.rstrip("\n")
            + "\n# BenchAudit semantics-preserving trailing comment\n",
            "A trailing comment is discarded by the Python parser and leaves the AST unchanged.",
        ),
    ]
    variants: list[MetamorphicVariant] = []
    seen = {answer}
    for transformation_id, transformed, rationale in candidates:
        transformed_digest = _python_ast_digest(transformed)
        if (
            transformed in seen
            or transformed_digest is None
            or transformed_digest != original_digest
        ):
            continue
        seen.add(transformed)
        variants.append(MetamorphicVariant(
            relation_id="evaluator_format_invariance",
            transformation_id=transformation_id,
            original=answer,
            transformed=transformed,
            semantic_profile="python_ast",
            semantics_preserving_rationale=rationale,
            semantics_proof={
                "schema_version": METAMORPHIC_PROOF_VERSION,
                "kind": "python_ast_equivalence",
                "ast_sha256": original_digest,
                "verified": True,
            },
        ))
    return variants


def _trim_variants(answer: str) -> list[MetamorphicVariant]:
    candidates = [
        ("declared_leading_space", " " + answer),
        ("declared_trailing_space", answer + " "),
    ]
    variants = []
    for transformation_id, transformed in candidates:
        variants.append(MetamorphicVariant(
            relation_id="evaluator_format_invariance",
            transformation_id=transformation_id,
            original=answer,
            transformed=transformed,
            semantic_profile="trim_insensitive_text",
            semantics_preserving_rationale=(
                "The explicit trim-insensitive contract declares leading and "
                "trailing ASCII whitespace semantically irrelevant."
            ),
            semantics_proof={
                "schema_version": METAMORPHIC_PROOF_VERSION,
                "kind": "declared_trim_equivalence",
                "trimmed_sha256": _sha256_text(answer.strip()),
                "verified": transformed.strip() == answer.strip(),
            },
        ))
    return variants


def _sql_layout_variants(answer: str) -> list[MetamorphicVariant]:
    """Apply SQL-token-external layout edits under an explicit SQL contract.

    The original SQL bytes are never rewritten. The fixed block comment is
    deliberately not an optimizer-hint comment (``/*+ ... */``). This profile
    is opt-in because only an adapter can establish that the answer is SQL.
    """
    if not answer.strip():
        return []
    candidates = [
        (
            "sql_leading_whitespace",
            "  \n" + answer,
            "Leading whitespace precedes the first SQL token and leaves the SQL program unchanged.",
        ),
        (
            "sql_trailing_whitespace",
            answer + "\n  ",
            "Trailing whitespace follows the final SQL token and leaves the SQL program unchanged.",
        ),
        (
            "sql_leading_plain_comment",
            "/* BenchAudit semantics-preserving layout probe */\n" + answer,
            (
                "A fixed non-hint block comment before the first SQL token is "
                "lexically ignored and leaves the SQL program unchanged."
            ),
        ),
    ]
    return [
        MetamorphicVariant(
            relation_id="evaluator_format_invariance",
            transformation_id=transformation_id,
            original=answer,
            transformed=transformed,
            semantic_profile="sql_layout",
            semantics_preserving_rationale=rationale,
            semantics_proof={
                "schema_version": METAMORPHIC_PROOF_VERSION,
                "kind": "declared_sql_layout_equivalence",
                "original_sha256": _sha256_text(answer),
                "original_bytes_preserved": True,
                "verified": True,
            },
        )
        for transformation_id, transformed, rationale in candidates
    ]


def generate_semantics_preserving_variants(
    answer: str, contract: Mapping[str, Any],
) -> tuple[MetamorphicVariant, ...]:
    """Generate only transformations with a locally replayable proof."""
    validated = _validated_contract(dict(contract))
    if validated is None or not isinstance(answer, str):
        return ()
    profile = validated["semantic_profile"]
    if profile == "numeric_value":
        variants = _numeric_variants(answer)
    elif profile == "python_ast":
        variants = _python_variants(answer)
    elif profile == "sql_layout":
        variants = _sql_layout_variants(answer)
    elif profile == "trim_insensitive_text":
        variants = _trim_variants(answer)
    else:
        variants = []
    return tuple(variant for variant in variants if variant.semantics_proof["verified"] is True)


def replay_semantics_proof(
    original: str,
    variant_evidence: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> bool:
    """Rebuild the declared transformation instead of trusting its proof flag."""
    transformed_sha = variant_evidence.get("transformed_sha256")
    transformation_id = variant_evidence.get("transformation_id")
    if not isinstance(transformed_sha, str) or not isinstance(transformation_id, str):
        return False
    for variant in generate_semantics_preserving_variants(original, contract):
        if (
            variant.transformation_id == transformation_id
            and _sha256_text(variant.transformed) == transformed_sha
            and variant.to_evidence() == dict(variant_evidence)
        ):
            return True
    return False


class MetamorphicEvaluatorAuditChecker(Checker):
    """Run deterministic MRs against an injected executable evaluator adapter."""

    name = "metamorphic_evaluator_audit"

    def __init__(
        self,
        evaluator: MetamorphicEvaluator,
        *,
        transcript_attester: ExecutionTranscriptAttester | None = None,
        transcript_verifier: ExecutionTranscriptVerifier | None = None,
    ) -> None:
        self.evaluator = evaluator
        self.transcript_attester = transcript_attester
        self.transcript_verifier = transcript_verifier

    def _contract(self, item: BenchmarkItem) -> dict[str, Any] | None:
        evaluator = item.evaluator if isinstance(item.evaluator, dict) else {}
        contract = _validated_contract(evaluator.get("metamorphic_contract"))
        if (
            contract is None
            or contract["evaluator_identity"] != getattr(self.evaluator, "identity", None)
        ):
            return None
        return contract

    def audit_eligibility(
        self, item: BenchmarkItem, root: Path | None = None,
    ) -> AuditEligibility:
        if not isinstance(item.gold, str) or not item.gold:
            return AuditEligibility.not_applicable(
                "metamorphic replay requires a non-empty string gold answer"
            )
        if self._contract(item) is None:
            return AuditEligibility.not_applicable(
                "metamorphic replay requires a supported contract bound to the evaluator identity"
            )
        return AuditEligibility.applicable(
            "typed metamorphic contract and evaluator adapter are available"
        )

    @staticmethod
    def _observe(
        evaluator: MetamorphicEvaluator,
        item: BenchmarkItem,
        answer: str,
    ) -> EvaluatorObservation:
        try:
            value = evaluator.evaluate(item, answer)
        except Exception as exc:
            return EvaluatorObservation.error(type(exc).__name__)
        if not isinstance(value, EvaluatorObservation):
            return EvaluatorObservation.error("evaluator returned an invalid observation")
        return value

    def check(
        self, item: BenchmarkItem, root: Path | None = None,
    ) -> Iterable[Violation]:
        contract = self._contract(item)
        if contract is None or not isinstance(item.gold, str) or not item.gold:
            return
        variants = generate_semantics_preserving_variants(item.gold, contract)
        baseline = self._observe(self.evaluator, item, item.gold)
        observations: list[tuple[MetamorphicVariant, EvaluatorObservation]] = []
        if baseline.status == "completed":
            observations = [
                (variant, self._observe(self.evaluator, item, variant.transformed))
                for variant in variants
            ]

        report = {
            "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "reference_code_sha256": _sha256_text(item.gold),
            "code_context_sha256": _sha256_text(self.evaluator.identity),
            "gold": baseline.to_dict(),
            "instrumented_gold": baseline.to_dict(),
            "gold_verdicts": {"official": baseline.accepted},
            "gold_instrumentation_consistent": True,
            "input_materialization_complete": True,
            "observed_cases": [],
            "probes": [
                {
                    "relation": variant.to_evidence(),
                    "observation": observation.to_dict(),
                }
                for variant, observation in observations
            ],
            "probe_failures": [
                {
                    "relation": variant.to_evidence(),
                    "observation": observation.to_dict(),
                }
                for variant, observation in observations
                if observation.status != "completed"
            ],
        }
        attestation = request_execution_attestation(
            report, self.transcript_attester,
        )
        trust = verify_execution_attestation(
            report, attestation, self.transcript_verifier,
        )
        trust_evidence = trust.as_evidence()
        item.metadata["_metamorphic_evaluator_report"] = {
            "schema_version": "benchcore-metamorphic-report-v1",
            "status": (
                "completed" if baseline.status == "completed" else "indeterminate"
            ),
            "semantic_profile": contract["semantic_profile"],
            "evaluator_identity": self.evaluator.identity,
            "baseline": baseline.to_dict(),
            "variants": report["probes"],
            **trust_evidence,
        }
        if baseline.status != "completed":
            return

        common_evidence = {
            "contract": contract,
            "evaluator": item.evaluator,
            "evaluator_identity": self.evaluator.identity,
            "original_answer_sha256": _sha256_text(item.gold),
            "driver_sha256": report["driver_sha256"],
            "reference_code_sha256": report["reference_code_sha256"],
            "code_context_sha256": report["code_context_sha256"],
            **trust_evidence,
        }
        attested = trust.verified is True
        if baseline.accepted is False:
            yield _violation(
                item,
                "gold_rejected_by_evaluator",
                0.99 if attested else 0.72,
                "The executable evaluator rejects the benchmark's own gold answer.",
                {
                    **common_evidence,
                    "baseline": baseline.to_dict(),
                    "evidence_level": "executed_metamorphic_gold_replay",
                    "proof_schema_version": "1.0",
                },
                severity="critical" if attested else "review",
                review_only=not attested,
                repair="Fix the gold answer, evaluator, or their declared contract.",
                method="execution_metamorphic",
                artifact="evaluator",
            )

        for variant, observation in observations:
            if (
                observation.status != "completed"
                or observation.accepted == baseline.accepted
            ):
                continue
            yield _violation(
                item,
                "metamorphic_inconsistency",
                0.99 if attested else 0.7,
                "A locally proven semantics-preserving representation changes the evaluator verdict.",
                {
                    **common_evidence,
                    "baseline": baseline.to_dict(),
                    "variant_observation": observation.to_dict(),
                    "variant": variant.to_evidence(),
                    "verdict_direction": (
                        "pass_to_fail" if baseline.accepted else "fail_to_pass"
                    ),
                    "evidence_level": "executed_metamorphic_invariance_replay",
                    "proof_schema_version": "1.0",
                },
                severity="major" if attested else "review",
                review_only=not attested,
                repair=(
                    "Evaluate the answer's declared semantic value instead of "
                    "its incidental representation."
                ),
                method="execution_metamorphic",
                artifact="evaluator",
            )
