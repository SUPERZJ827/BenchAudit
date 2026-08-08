"""How a benchmark decides correctness comes from the data, not from our label.

`answer_contract` chose its comparison by grepping `item.evaluator` for
substrings -- "numeric", "alias", "exact". That string is one our own adapter
wrote from a hand-maintained table, so the chain reads: we invent a label, we
grep the label we invented, and we compare answers by what the grep found.
Nothing the benchmark shipped enters the decision, which is how a comparison
named `..._with_aliases` was used to prove a benchmark rejects its own aliases.

A profile derived from the benchmark's own rows answers the same question with
evidence, so when one is available it decides.
"""

from __future__ import annotations

from benchcore.evaluators import answer_contract, evaluate_answer


def test_a_profile_verdict_decides_the_comparison():
    contract = answer_contract("1500", None, {"type": "exact_match"},
                               scoring={"comparison": "numeric_tolerance"})
    assert contract["kind"] == "numeric"


def test_the_label_still_decides_when_no_profile_exists():
    """Audits that predate profiling must behave exactly as before."""
    assert answer_contract("1500", None, {"type": "exact_match"})["kind"] == "exact"
    assert answer_contract("1500", None, {"type": "numeric_exact_match"})["kind"] == "numeric"


def test_several_accepted_answers_are_alternatives_not_a_set():
    """"Any of these will do" is the opposite of "all of these are required",
    and this test previously asked for the latter."""
    contract = answer_contract(["a", "b"], None, None,
                               scoring={"comparison": "any_of_accepted"})
    assert contract["cardinality"] == "alternatives"


def test_an_unrecognised_verdict_falls_back_rather_than_deciding():
    contract = answer_contract("1500", None, {"type": "numeric_exact_match"},
                               scoring={"comparison": "invented_comparison"})
    assert contract["kind"] == "numeric"


def test_a_profile_changes_what_counts_as_correct():
    """The point of the change: the same pair is judged by the benchmark's
    behaviour rather than by a label we wrote."""
    assert evaluate_answer("1,500", "1500", None, {"type": "exact_match"}) is False
    assert evaluate_answer(
        "1,500", "1500", None, {"type": "exact_match"},
        scoring={"comparison": "numeric_tolerance"},
    ) is True


# --- reaching the checkers ----------------------------------------------------

def test_an_item_carries_the_profile_verdict_to_the_checkers():
    """The verdict has to travel with the item; the checkers see nothing else."""
    from benchcore.evaluators import item_scoring
    from benchcore.schema import BenchmarkItem

    item = BenchmarkItem(item_id="x", raw={}, task="q", gold="1500")
    assert item_scoring(item) is None

    item.metadata["_scoring"] = {"comparison": "numeric_tolerance"}
    assert item_scoring(item) == {"comparison": "numeric_tolerance"}


def test_an_item_without_metadata_is_handled():
    from benchcore.evaluators import item_scoring

    assert item_scoring(None) is None
    assert item_scoring(object()) is None
