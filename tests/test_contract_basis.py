"""Where a contract decision came from must be visible in the run.

The comparison used to judge answers has three possible sources: a profile
derived from the benchmark's rows, a label our adapter wrote from a
hand-maintained table, or a guess from the shape of the gold. They disagree --
gold "1500" is compared numerically with no label and exactly with one saying
exact_match -- so which was used changes what counts as correct.

Recording the basis does not change any decision. It makes it answerable
afterwards which runs rested on evidence and which rested on a label we wrote,
a question no existing artifact can answer.
"""

from __future__ import annotations

from benchcore.evaluators import CONTRACT_BASIS_GUESS, CONTRACT_BASIS_LABEL, CONTRACT_BASIS_PROFILE, answer_contract


def test_a_profile_verdict_is_recorded_as_the_basis():
    contract = answer_contract("1500", None, {"type": "exact_match"},
                               scoring={"comparison": "numeric_tolerance"})
    assert contract["basis"] == CONTRACT_BASIS_PROFILE


def test_an_adapter_label_is_recorded_as_the_basis():
    contract = answer_contract("1500", None, {"type": "exact_match"})
    assert contract["basis"] == CONTRACT_BASIS_LABEL


def test_inference_from_the_gold_alone_is_recorded_as_a_guess():
    """No profile and no label: the comparison comes from the gold's shape."""
    assert answer_contract("1500", None, None)["basis"] == CONTRACT_BASIS_GUESS
    assert answer_contract("Paris", None, None)["basis"] == CONTRACT_BASIS_GUESS


def test_choices_present_is_not_a_guess():
    """A listed option set is something the benchmark shipped."""
    contract = answer_contract("A", ["A", "B"], None)
    assert contract["basis"] != CONTRACT_BASIS_GUESS


def test_a_profile_agreeing_that_the_answer_is_a_choice_is_the_basis():
    """Comparing choices by their position is stricter than anything a profile
    can name, so the option set keeps deciding how -- but a profile that
    independently read these rows as multiple choice is why, and recording the
    label instead understates what the run rested on."""
    contract = answer_contract("A", ["A", "B"], None,
                               scoring={"comparison": "exact_match"})
    assert contract["kind"] == "choice"
    assert contract["basis"] == CONTRACT_BASIS_PROFILE


def test_an_unprofiled_option_set_is_still_the_adapter_label():
    contract = answer_contract("A", ["A", "B"], None)
    assert contract["basis"] == CONTRACT_BASIS_LABEL


def test_recording_the_basis_changes_no_decision():
    for gold, choices, evaluator, scoring in (
        ("1500", None, {"type": "exact_match"}, None),
        ("1500", None, None, None),
        ("A", ["A", "B"], None, None),
        ("1500", None, {"type": "exact_match"}, {"comparison": "numeric_tolerance"}),
    ):
        contract = answer_contract(gold, choices, evaluator, scoring=scoring)
        assert contract["kind"]
        assert contract["cardinality"]


# --- surfacing it in a run ----------------------------------------------------

def test_a_run_can_report_how_its_contracts_were_decided():
    """Which basis carried a run is the question this exists to answer."""
    from benchcore.evaluators import contract_basis_census
    from benchcore.schema import BenchmarkItem

    items = [
        BenchmarkItem(item_id="a", raw={}, task="q", gold="1500"),
        BenchmarkItem(item_id="b", raw={}, task="q", gold="1500",
                      evaluator={"type": "exact_match"}),
        BenchmarkItem(item_id="c", raw={}, task="q", gold="1500",
                      metadata={"_scoring": {"comparison": "numeric_tolerance"}}),
    ]
    census = contract_basis_census(items)
    assert census == {CONTRACT_BASIS_GUESS: 1, CONTRACT_BASIS_LABEL: 1,
                      CONTRACT_BASIS_PROFILE: 1}


def test_an_empty_run_reports_nothing():
    from benchcore.evaluators import contract_basis_census

    assert contract_basis_census([]) == {}
