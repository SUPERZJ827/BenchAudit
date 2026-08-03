"""A declared alias list is not evidence that the evaluator is overstrict.

SQuAD-style benchmarks ship several annotator answers and an evaluator that
says it accepts any of them.  Comparing an alias against only the first entry
reports a defect that exists solely in the adapter, and because the comparison
is deterministic that false finding was promoted to `confirmed`.
"""

from __future__ import annotations

from benchcore.evaluators import evaluate_answer, evaluator_accepts_aliases

ALIAS_AWARE = {"type": "normalized_exact_match_with_aliases"}
EXACT_ONLY = {"type": "exact_match"}
GOLD = "complexity classes"
ALIAS = "some complexity classes"


def test_declaration_detection():
    assert evaluator_accepts_aliases(ALIAS_AWARE)
    assert not evaluator_accepts_aliases(EXACT_ONLY)
    assert not evaluator_accepts_aliases(None)


def test_alias_aware_evaluator_accepts_a_declared_alias():
    assert evaluate_answer(ALIAS, GOLD, None, ALIAS_AWARE, aliases=[ALIAS])


def test_exact_evaluator_still_rejects_declared_aliases():
    """This is the genuine defect class and must keep firing."""
    assert not evaluate_answer(ALIAS, GOLD, None, EXACT_ONLY, aliases=[ALIAS])


def test_unrelated_answer_is_rejected_even_with_alias_support():
    assert not evaluate_answer("something else", GOLD, None, ALIAS_AWARE, aliases=[ALIAS])


def test_gold_itself_is_unaffected():
    assert evaluate_answer(GOLD, GOLD, None, ALIAS_AWARE, aliases=[ALIAS])
    assert evaluate_answer(GOLD, GOLD, None, EXACT_ONLY)


def test_omitting_aliases_preserves_previous_behaviour():
    """Existing callers pass no aliases and must be unaffected."""
    assert not evaluate_answer(ALIAS, GOLD, None, ALIAS_AWARE)


def test_numeric_alias_uses_the_same_comparison_kind():
    numeric = {"type": "numeric_exact_match_with_aliases"}
    assert evaluate_answer("3.0", "4", None, numeric, aliases=["3"])
    assert not evaluate_answer("5", "4", None, numeric, aliases=["3"])
