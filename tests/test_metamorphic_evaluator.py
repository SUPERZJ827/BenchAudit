from __future__ import annotations

from decimal import Decimal

from benchcore.auditor import audit_items
from benchcore.execution_attestation import ATTESTATION_PROTOCOL
from benchcore.loader import explicit_mapping_provenance
from benchcore.metamorphic_evaluator import (
    EvaluatorObservation,
    MetamorphicEvaluatorAuditChecker,
    generate_mcq_permutation,
    generate_semantics_preserving_variants,
)
from benchcore.promotion import enforce_promotion_policy
from benchcore.schema import BenchmarkItem


class DeterministicAttester:
    def attest(self, payload_sha256):
        return {
            "protocol": ATTESTATION_PROTOCOL,
            "payload_sha256": payload_sha256,
            "signature": "verified-outside-harness",
        }


class AcceptingIndependentVerifier:
    def verify(self, attestation, payload_sha256):
        return (
            attestation.get("payload_sha256") == payload_sha256
            and attestation.get("signature") == "verified-outside-harness"
        )


class NumericValueEvaluator:
    identity = "fixture:numeric-value-evaluator:v1"

    def __init__(self, *, exact_lexeme: bool = False, reject_all: bool = False):
        self.exact_lexeme = exact_lexeme
        self.reject_all = reject_all

    def evaluate(self, item, answer):
        if self.reject_all:
            accepted = False
        elif self.exact_lexeme:
            accepted = answer == str(item.gold)
        else:
            accepted = Decimal(answer.strip()) == Decimal(str(item.gold).strip())
        return EvaluatorObservation.completed(accepted)


class CanonicalMCQEvaluator:
    identity = "fixture:canonical-mcq-evaluator:v1"

    def evaluate(self, item, answer):
        return EvaluatorObservation.completed(answer == item.gold)


class FixedFirstPositionEvaluator:
    identity = "fixture:fixed-first-position:v1"

    def evaluate(self, item, answer):
        del item
        return EvaluatorObservation.completed(answer == "A")


def numeric_item(item_id: str, gold: str) -> BenchmarkItem:
    evaluator = {
        "metamorphic_contract": {
            "schema_version": "benchcore-metamorphic-contract-v1",
            "semantic_profile": "numeric_value",
            "evaluator_identity": "fixture:numeric-value-evaluator:v1",
        }
    }
    raw = {"id": item_id, "answer": gold, "evaluator": evaluator}
    item = BenchmarkItem(
        item_id=item_id,
        raw=raw,
        task="Return the numeric value.",
        gold=gold,
        evaluator=evaluator,
    )
    item.metadata["_mapping_provenance"] = explicit_mapping_provenance(
        adapter_id="test_metamorphic_numeric",
        adapter_version="1",
        raw=raw,
        field_bindings={
            "item_id": "id",
            "gold": "answer",
            "evaluator": "evaluator",
        },
    )
    return item


def mcq_item(
    item_id: str,
    *,
    evaluator_identity: str = "fixture:canonical-mcq-evaluator:v1",
) -> BenchmarkItem:
    evaluator = {
        "metamorphic_contract": {
            "schema_version": "benchcore-metamorphic-contract-v1",
            "semantic_profile": "mcq_choice",
            "evaluator_identity": evaluator_identity,
            "choice_labels": ["A", "B", "C", "D"],
        }
    }
    raw = {
        "id": item_id,
        "question": "Which value is first?",
        "options": ["alpha", "beta", "gamma", "delta"],
        "answer": "A",
        "evaluator": evaluator,
    }
    item = BenchmarkItem(
        item_id=item_id,
        raw=raw,
        task=raw["question"],
        choices=list(raw["options"]),
        gold=raw["answer"],
        evaluator=evaluator,
    )
    item.metadata["_mapping_provenance"] = explicit_mapping_provenance(
        adapter_id="test_metamorphic_mcq",
        adapter_version="1",
        raw=raw,
        field_bindings={
            "item_id": "id",
            "task": "question",
            "choices": "options",
            "gold": "answer",
            "evaluator": "evaluator",
        },
    )
    return item


def test_numeric_variants_are_decimal_equal_and_carry_rationales():
    variants = generate_semantics_preserving_variants(
        "0.5",
        {"schema_version": "benchcore-metamorphic-contract-v1",
         "semantic_profile": "numeric_value",
         "evaluator_identity": "fixture:numeric-value-evaluator:v1"},
    )

    assert variants
    assert {variant.transformed for variant in variants} >= {".5", "0.50"}
    assert all(variant.semantics_preserving_rationale for variant in variants)
    assert all(Decimal(variant.transformed.strip()) == Decimal("0.5") for variant in variants)
    assert all(variant.semantics_proof["verified"] is True for variant in variants)


def test_python_variants_preserve_ast_and_never_change_indentation():
    source = "def f(x):\n    return x + 1\n"
    variants = generate_semantics_preserving_variants(
        source,
        {"schema_version": "benchcore-metamorphic-contract-v1",
         "semantic_profile": "python_ast",
         "evaluator_identity": "fixture:python:v1"},
    )

    assert variants
    assert all(variant.transformation_id != "generic_whitespace" for variant in variants)
    assert all(variant.semantics_proof["kind"] == "python_ast_equivalence" for variant in variants)
    assert all(variant.semantics_proof["verified"] is True for variant in variants)
    assert all("    return x + 1" in variant.transformed for variant in variants)


def test_sql_layout_variants_preserve_original_bytes_without_rewriting_tokens():
    source = "SELECT '/* literal */' AS value;"
    variants = generate_semantics_preserving_variants(
        source,
        {"schema_version": "benchcore-metamorphic-contract-v1",
         "semantic_profile": "sql_layout",
         "evaluator_identity": "fixture:sql:v1"},
    )

    assert {
        variant.transformation_id for variant in variants
    } == {
        "sql_leading_whitespace",
        "sql_trailing_whitespace",
        "sql_leading_plain_comment",
    }
    assert all(source in variant.transformed for variant in variants)
    assert all(
        variant.semantics_proof["kind"] == "declared_sql_layout_equivalence"
        for variant in variants
    )
    assert all(
        variant.semantics_proof["original_bytes_preserved"] is True
        for variant in variants
    )


def test_mcq_permutation_moves_gold_with_the_same_selected_choice():
    item = mcq_item("permutation-proof")
    variant = generate_mcq_permutation(
        item, item.evaluator["metamorphic_contract"],
    )

    assert variant is not None
    assert variant.permutation == (3, 2, 1, 0)
    assert variant.original_gold_label == "A"
    assert variant.permuted_gold_label == "D"
    assert variant.original_choices[0] == variant.permuted_choices[3] == "alpha"
    assert variant.to_evidence()["semantics_proof"] == {
        "schema_version": "benchcore-metamorphic-proof-v1",
        "kind": "mcq_synchronized_permutation",
        "selected_choice_preserved": True,
        "verified": True,
    }


def test_mcq_permutation_requires_an_explicit_label_namespace():
    item = mcq_item("missing-label-contract")
    contract = dict(item.evaluator["metamorphic_contract"])
    contract.pop("choice_labels")

    assert generate_mcq_permutation(item, contract) is None


def test_one_hundred_clean_mcq_evaluators_produce_zero_findings():
    checker = MetamorphicEvaluatorAuditChecker(CanonicalMCQEvaluator())
    items = [mcq_item(f"clean-mcq-{index}") for index in range(100)]

    findings = audit_items(items, checkers=[checker], workers=8)

    assert findings == []


def test_mcq_position_dependency_is_review_without_attestation():
    item = mcq_item(
        "position-review",
        evaluator_identity="fixture:fixed-first-position:v1",
    )
    checker = MetamorphicEvaluatorAuditChecker(FixedFirstPositionEvaluator())

    findings = audit_items([item], checkers=[checker])

    assert [finding.defect_type for finding in findings] == [
        "metamorphic_inconsistency"
    ]
    assert findings[0].evidence["evidence_level"] == (
        "executed_mcq_permutation_replay"
    )
    assert findings[0].evidence_tier == "review"
    assert findings[0].review_only is True


def test_attested_mcq_position_dependency_is_confirmed():
    item = mcq_item(
        "position-confirmed",
        evaluator_identity="fixture:fixed-first-position:v1",
    )
    checker = MetamorphicEvaluatorAuditChecker(
        FixedFirstPositionEvaluator(),
        transcript_attester=DeterministicAttester(),
        transcript_verifier=AcceptingIndependentVerifier(),
    )

    findings = audit_items([item], checkers=[checker])

    assert [finding.evidence_tier for finding in findings] == ["confirmed"]
    assert findings[0].proof_kind == "isolated_execution"


def test_tampered_mcq_permutation_payload_loses_confirmation():
    item = mcq_item(
        "position-tampered",
        evaluator_identity="fixture:fixed-first-position:v1",
    )
    checker = MetamorphicEvaluatorAuditChecker(
        FixedFirstPositionEvaluator(),
        transcript_attester=DeterministicAttester(),
        transcript_verifier=AcceptingIndependentVerifier(),
    )
    finding = audit_items([item], checkers=[checker])[0]
    assert finding.evidence_tier == "confirmed"

    finding.evidence["variant"]["permutation"] = [0, 1, 2, 3]
    enforce_promotion_policy(finding, item)

    assert finding.evidence_tier == "review"


def test_free_text_has_no_confirmable_variant_without_explicit_trim_contract():
    assert generate_semantics_preserving_variants(
        "answer",
        {"schema_version": "benchcore-metamorphic-contract-v1",
         "semantic_profile": "free_text",
         "evaluator_identity": "fixture:text:v1"},
    ) == ()


def test_one_hundred_valid_evaluators_produce_zero_findings():
    checker = MetamorphicEvaluatorAuditChecker(NumericValueEvaluator())
    items = [
        numeric_item(f"clean-{index}", f"{index}.5")
        for index in range(100)
    ]

    findings = audit_items(items, checkers=[checker], workers=8)

    assert findings == []


def test_format_flip_is_review_without_independent_attestation():
    item = numeric_item("overstrict-review", "0.5")
    checker = MetamorphicEvaluatorAuditChecker(
        NumericValueEvaluator(exact_lexeme=True),
    )

    findings = audit_items([item], checkers=[checker])

    assert {finding.defect_type for finding in findings} == {
        "metamorphic_inconsistency"
    }
    assert findings[0].evidence_tier == "review"
    assert findings[0].review_only is True


def test_attested_format_flip_is_confirmed_after_semantics_replay():
    item = numeric_item("overstrict-confirmed", "0.5")
    checker = MetamorphicEvaluatorAuditChecker(
        NumericValueEvaluator(exact_lexeme=True),
        transcript_attester=DeterministicAttester(),
        transcript_verifier=AcceptingIndependentVerifier(),
    )

    findings = audit_items([item], checkers=[checker])

    assert {finding.defect_type for finding in findings} == {
        "metamorphic_inconsistency"
    }
    assert findings[0].evidence_tier == "confirmed"
    assert findings[0].proof_kind == "isolated_execution"
    assert findings[0].review_only is False


def test_tampered_semantics_payload_loses_confirmation():
    item = numeric_item("tampered-proof", "0.5")
    checker = MetamorphicEvaluatorAuditChecker(
        NumericValueEvaluator(exact_lexeme=True),
        transcript_attester=DeterministicAttester(),
        transcript_verifier=AcceptingIndependentVerifier(),
    )
    finding = audit_items([item], checkers=[checker])[0]
    assert finding.evidence_tier == "confirmed"

    finding.evidence["variant"]["transformed_sha256"] = "0" * 64
    enforce_promotion_policy(finding, item)

    assert finding.evidence_tier == "review"


def test_attested_gold_rejection_is_confirmed():
    item = numeric_item("gold-rejected", "12.5")
    checker = MetamorphicEvaluatorAuditChecker(
        NumericValueEvaluator(reject_all=True),
        transcript_attester=DeterministicAttester(),
        transcript_verifier=AcceptingIndependentVerifier(),
    )

    findings = audit_items([item], checkers=[checker])

    assert [finding.defect_type for finding in findings] == [
        "gold_rejected_by_evaluator"
    ]
    assert findings[0].evidence_tier == "confirmed"


def test_timeout_is_indeterminate_not_a_semantic_failure():
    class TimeoutEvaluator:
        identity = "fixture:timeout:v1"

        def evaluate(self, item, answer):
            return EvaluatorObservation.timeout("fixture timeout")

    item = numeric_item("timeout", "1.5")
    item.evaluator["metamorphic_contract"]["evaluator_identity"] = (
        "fixture:timeout:v1"
    )
    item.raw["evaluator"]["metamorphic_contract"]["evaluator_identity"] = (
        "fixture:timeout:v1"
    )
    item.metadata["_mapping_provenance"] = explicit_mapping_provenance(
        adapter_id="test_metamorphic_timeout",
        adapter_version="1",
        raw=item.raw,
        field_bindings={
            "item_id": "id",
            "gold": "answer",
            "evaluator": "evaluator",
        },
    )
    findings = audit_items(
        [item],
        checkers=[MetamorphicEvaluatorAuditChecker(TimeoutEvaluator())],
    )

    assert findings == []
    report = item.metadata["_metamorphic_evaluator_report"]
    assert report["status"] == "indeterminate"
    assert report["baseline"]["status"] == "timeout"
