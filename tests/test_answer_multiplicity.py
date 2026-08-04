"""A benchmark that declares several accepted answers is stating a fact.

Which fact is not deterministic: the answers may be several wordings of one
answer, or genuinely different answers.  Normalization settles "1705" against
"12 may 1705" and fails on a sentence-long extraction span against a two-word
one, so the classification is a model judgement and is capped at review.

Separately, a solver answer must be compared against everything the benchmark
declared acceptable.  Comparing against the entry our adapter happened to put
first reports a defect whenever the solver picked a different declared answer.
"""

from __future__ import annotations

from benchcore.llm_auditor import (
    accepted_answer_set,
    answer_multiplicity_violations,
    answers_are_interchangeable,
    declared_accepted_answers,
    defect_from_blind,
    normalize_answer,
)
from benchcore.schema import BenchmarkItem


def _item(gold="2 million", aliases=("ca 2 million",), metadata=None):
    return BenchmarkItem(
        item_id="x", raw={}, task="how many?", gold=gold,
        aliases=list(aliases), metadata=dict(metadata or {}),
    )


def test_declared_answers_preserve_order_and_deduplicate():
    item = _item(gold="a", aliases=["a", "b"])
    assert declared_accepted_answers(item) == ["a", "b"]


def test_single_answer_item_is_not_examined():
    assert len(declared_accepted_answers(_item(gold="a", aliases=[]))) < 2


def test_solver_answer_matching_an_alias_is_not_a_wrong_gold():
    item = _item()
    blind = {"solution_status": "solved", "valid_answers": ["ca 2 million"]}
    answers = {normalize_answer(item, "ca 2 million")}
    gold = normalize_answer(item, item.gold)
    assert defect_from_blind(item, blind, answers, gold) == ""


def test_unrelated_solver_answer_still_reports():
    item = _item()
    blind = {"solution_status": "solved", "valid_answers": ["seventeen"]}
    answers = {normalize_answer(item, "seventeen")}
    gold = normalize_answer(item, item.gold)
    assert defect_from_blind(item, blind, answers, gold) == "wrong_gold_answer"


def test_accepted_set_covers_gold_and_aliases():
    assert accepted_answer_set(_item()) == {"2 million", "ca 2 million"}


def test_unexamined_item_reports_no_verdict():
    """Absent a verdict the declared set is honoured as-is."""
    assert answers_are_interchangeable(_item()) is None


def test_verdicts_are_read_back():
    same = _item(metadata={"_answer_multiplicity": {"relationship": "same_answer"}})
    diff = _item(metadata={"_answer_multiplicity": {"relationship": "different_answers"}})
    unsure = _item(metadata={"_answer_multiplicity": {"relationship": "uncertain"}})
    assert answers_are_interchangeable(same) is True
    assert answers_are_interchangeable(diff) is False
    assert answers_are_interchangeable(unsure) is None


def test_only_materially_different_answers_are_reported():
    item = _item()
    same = {"relationship": "same_answer", "confidence": 0.9}
    diff = {"relationship": "different_answers", "confidence": 0.9}
    assert list(answer_multiplicity_violations(item, same, 0.75, 0.45)) == []
    assert len(list(answer_multiplicity_violations(item, diff, 0.75, 0.45))) == 1


def test_low_confidence_is_withheld():
    item = _item()
    weak = {"relationship": "different_answers", "confidence": 0.1}
    assert list(answer_multiplicity_violations(item, weak, 0.75, 0.45)) == []


def test_multiplicity_findings_never_exceed_review():
    item = _item()
    result = {"relationship": "different_answers", "confidence": 0.99}
    for violation in answer_multiplicity_violations(item, result, 0.75, 0.45):
        assert violation.review_only is True
