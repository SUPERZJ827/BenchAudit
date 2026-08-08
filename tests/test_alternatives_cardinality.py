"""Several acceptable wordings is not the same shape as an answer with parts.

A benchmark that records ``["5", "five", "5.0"]`` is saying any one of these
will do.  A benchmark whose answer is a set of table cells is saying all of
them are required.  Both arrive as a list of strings, and the vocabulary had
one slot for them, so "any of these" was scored as "all of these": answering
correctly failed and reciting every wording passed.

The profile tells them apart.  ``any_of_accepted`` is only asserted when some
record actually carries more than one value, so where it is stated the list is
alternatives; where nothing states it, a multi-valued gold stays a set whose
values are all required.
"""

from __future__ import annotations

from benchcore.evaluators import answer_contract, answer_variants, evaluate_answer

ALTERNATIVES = {"comparison": "any_of_accepted"}
WORDINGS = ["5", "five", "5.0"]


def test_the_contract_separates_alternatives_from_a_set():
    contract = answer_contract(WORDINGS, None, None, scoring=ALTERNATIVES)
    assert contract["cardinality"] == "alternatives"


def test_any_one_recorded_wording_is_accepted():
    for wording in WORDINGS:
        assert evaluate_answer(wording, WORDINGS, None, None, scoring=ALTERNATIVES) is True


def test_reciting_every_wording_is_not_an_answer():
    assert evaluate_answer("5, five, 5.0", WORDINGS, None, None, scoring=ALTERNATIVES) is False


def test_a_wording_that_was_not_recorded_is_rejected():
    assert evaluate_answer("seven", WORDINGS, None, None, scoring=ALTERNATIVES) is False


def test_a_multi_valued_gold_nothing_ruled_on_still_requires_every_value():
    """A denotation set -- several table cells -- is the other reading, and
    stays the default where no profile settled the question."""
    cells = ["Paris", "Lyon"]
    assert evaluate_answer("Paris", cells, None, None) is False
    assert evaluate_answer("Paris, Lyon", cells, None, None) is True


def test_no_set_variant_is_generated_for_alternatives():
    """Joining every wording into one string is a wrong answer, not a
    rephrasing, so offering it as semantics-preserving reports the evaluator
    for rejecting something it should reject."""
    descriptions = [
        description
        for description, _ in answer_variants(WORDINGS, None, None, scoring=ALTERNATIVES)
    ]
    assert "set_comma_joined" not in descriptions
    assert "set_reordered" not in descriptions


def test_a_set_still_gets_its_variants():
    descriptions = [
        description for description, _ in answer_variants(["Paris", "Lyon"], None, None)
    ]
    assert "set_comma_joined" in descriptions
