"""A confidence is a model's self-reported belief, or it is nothing.

The deterministic detectors carried hand-picked numbers -- 0.65 for an
overstrict evaluator, 0.85 for a missing context -- that no measurement
produced and that no decision consumed.  Severity was set explicitly at every
one of those call sites, so the number only ever reached the report, where it
reads as a calibrated score and is not one.

The LLM auditors are different: their confidence comes from the model and does
gate review-versus-confirm, so it stays.
"""

from __future__ import annotations

from benchcore.checkers import EvaluatorChecker
from benchcore.schema import BenchmarkItem


def _overstrict_item() -> BenchmarkItem:
    """Gold "1500" under an exact evaluator: rejects the "1500.0" variant."""
    return BenchmarkItem(
        item_id="x",
        raw={},
        task="A question whose answer is 1500",
        gold="1500",
        evaluator={"type": "exact_match"},
    )


def test_a_deterministic_finding_reports_no_confidence():
    findings = list(EvaluatorChecker().check(_overstrict_item()))
    assert findings, "the overstrict-evaluator rule should still fire"
    for finding in findings:
        assert finding.confidence is None, (
            f"{finding.defect_type} still carries a hand-written {finding.confidence}"
        )


def test_dropping_the_number_does_not_drop_the_finding():
    """Severity was always set explicitly, so nothing about the verdict moves."""
    findings = list(EvaluatorChecker().check(_overstrict_item()))
    overstrict = [f for f in findings if f.defect_type == "output_format_overstrict_risk"]
    assert len(overstrict) == 1
    assert overstrict[0].severity == "review"
    assert overstrict[0].review_only is True


def test_a_model_reported_confidence_survives():
    """The half that means something must keep meaning it."""

    from benchcore.llm_auditor import question_violations

    item = BenchmarkItem(item_id="q", raw={}, task="Question", choices=["one", "two"])
    result = {
        "clarity_defects": [{"defect": "answer_changing_ambiguity", "confidence": 0.62}],
        "needs_expert": False,
        "alternative_interpretations": [
            {"interpretation": "one", "answer": "A"},
            {"interpretation": "two", "answer": "B"},
        ],
    }
    findings = list(question_violations(item, result, 0.75, 0.45))
    assert findings, "the clarity auditor should still report"
    assert findings[0].confidence == 0.62


# --- consumers ---------------------------------------------------------------

def test_a_confidence_filter_does_not_silently_drop_what_has_no_confidence():
    """`float(None)` raising into a 0.0 fallback would hide every static finding.

    A deterministic finding is not a low-confidence finding.  ``--min-confidence``
    selects among self-reported scores; a record without one is out of its scope
    and must survive.
    """

    from benchcore.investigator import select_violations

    violations = [
        {"defect_type": "d", "detection_method": "static_rule", "confidence": None},
        {"defect_type": "d", "detection_method": "llm_gold_audit", "confidence": 0.4},
        {"defect_type": "d", "detection_method": "llm_gold_audit", "confidence": 0.95},
    ]
    kept = select_violations(
        violations,
        include_defects=None,
        include_methods=None,
        min_confidence=0.9,
        offset=0,
        limit=None,
    )
    assert [v["confidence"] for v in kept] == [None, 0.95]


def test_a_report_states_no_confidence_rather_than_inventing_one(tmp_path):
    """Rendered through the real report path, not a hand-built fixture."""

    from benchcore.field_mapping import FieldMapping
    from benchcore.report import build_report, write_markdown_report

    item = _overstrict_item()
    findings = list(EvaluatorChecker().check(item))
    report = build_report(
        "fixture.jsonl",
        [item],
        findings,
        FieldMapping(item_id="id", task="task"),
        methods_run=["evaluator"],
    )
    path = tmp_path / "r.md"
    write_markdown_report(path, report)
    text = path.read_text(encoding="utf-8")

    assert "output_format_overstrict_risk" in text
    assert "confidence=0.00" not in text, "a missing score must not render as zero"
    assert "confidence=" not in text, "a deterministic finding has no score to print"


def test_a_synthesised_rule_keeps_the_confidence_its_proposer_wrote():
    """A learned rule's score comes from the model that proposed the rule.

    `RuleSpec.from_dict` parses it out of the rule JSON the synthesiser
    returns, so it belongs with the model-reported half, not with the literals.
    """

    from benchcore.auditor import audit_items_with_ledger
    from benchcore.evolution import DeclarativeRuleChecker, RuleSpec
    from benchcore.loader import build_items, load_mapping

    spec = RuleSpec.from_dict({
        "schema_version": "benchcore-declarative-rule-v1",
        "rule_id": "rubric_type_count_mismatch",
        "version": 1,
        "family": "generic",
        "defect_type": "schema_drift",
        "description": "Rubric and rubric-type list lengths differ.",
        "message": "Rubric and rubric-type cardinalities differ.",
        "repair": "Provide exactly one type for every rubric.",
        "conditions": [{
            "left": {"source": "raw", "path": ["rubrics"],
                     "transforms": ["parse_jsonish", "length"]},
            "operator": "ne",
            "right": {"operand": {"source": "raw", "path": ["rubric_types"],
                                  "transforms": ["parse_jsonish", "length"]}},
        }],
        "match": "all",
        "confidence": 0.85,
    })
    rows = [{"item_id": "v", "task": "x", "rubrics": ["a"], "rubric_types": []}]
    items = build_items(rows, load_mapping(None, rows))
    result = audit_items_with_ledger(
        items,
        checkers=[DeclarativeRuleChecker(spec, registry_receipt="r")],
        dataset_checkers=[],
    )
    assert [v.confidence for v in result.violations] == [0.85]
