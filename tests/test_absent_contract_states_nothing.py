"""A contract that does not exist cannot fail to say something.

GSM8K carries no output-contract field at all, and 23 of the 28 findings
reported against 300 of its records said its output contract "does not state
unit handling".  The sentence is true only in the way that any statement about
a thing that is not there is true, and it crowds out the finding that would
actually be worth making.

Where no contract is recorded, its absence is the finding -- reported once by
the check that looks for it -- not an unbounded list of things it fails to say.
"""

from __future__ import annotations

from benchcore.checkers import OutputContractChecker
from benchcore.schema import BenchmarkItem

UNIT_TASK = "Tom earns 5 dollars an hour and works 3 hours. How much does he earn?"


def _item(**overrides) -> BenchmarkItem:
    fields = dict(
        item_id="1",
        task=UNIT_TASK,
        gold="15",
        raw={},
        metadata={},
    )
    fields.update(overrides)
    return BenchmarkItem(**fields)


def _types(item) -> list[str]:
    return [v.defect_type for v in OutputContractChecker().check(item)]


def test_an_absent_contract_is_not_read_as_omitting_units():
    assert "missing_accepted_alternatives" not in _types(_item(evaluator={"type": "numeric"}))


def test_a_present_contract_silent_on_units_is_still_reported():
    item = _item(
        evaluator={"type": "numeric"},
        output_contract={"type": "number", "format": "an integer"},
    )
    assert "missing_accepted_alternatives" in _types(item)


def test_a_contract_that_states_unit_handling_is_accepted():
    item = _item(
        evaluator={"type": "numeric"},
        output_contract={"type": "number", "format": "a dollar amount, no symbol"},
    )
    assert "missing_accepted_alternatives" not in _types(item)


def test_an_absent_contract_is_still_reported_absent():
    """The one finding worth making where nothing declares the answer format."""
    assert "missing_output_contract" in _types(_item())


def test_an_evaluator_alone_is_not_a_missing_contract():
    """GSM8K's shape: no contract field, but the evaluator declares the type."""
    assert "missing_output_contract" not in _types(_item(evaluator={"type": "numeric"}))
