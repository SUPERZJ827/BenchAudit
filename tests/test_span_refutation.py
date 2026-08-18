from __future__ import annotations

from benchcore.span_refutation import (
    REFUTED,
    UNREFUTED,
    UNRESOLVED,
    normalize,
    span_occurs,
    value_in_span,
    verify,
)

MATERIAL = "user: Please analyse the Technology sector over the last month."


def test_a_real_quote_carrying_the_value_refutes_the_claim() -> None:
    outcome, _ = verify(MATERIAL, {"grounding_kind": "verbatim",
                                   "span": "the Technology sector", "value": "Technology"})
    assert outcome == REFUTED


def test_an_invented_quote_leaves_the_claim_standing() -> None:
    outcome, reason = verify(MATERIAL, {"grounding_kind": "verbatim",
                                        "span": "the user asked for Summary output",
                                        "value": "Summary"})
    assert outcome == UNREFUTED
    assert "does not occur" in reason


def test_a_real_quote_that_does_not_carry_the_value_resolves_nothing() -> None:
    outcome, reason = verify(MATERIAL, {"grounding_kind": "verbatim",
                                        "span": "over the last month", "value": "Summary"})
    assert outcome == UNRESOLVED
    assert "does not carry the value" in reason


def test_declining_to_ground_leaves_the_claim_standing() -> None:
    assert verify(MATERIAL, {"grounding_kind": "none", "value": "Summary"})[0] == UNREFUTED


def test_a_derivation_blocks_confirmation_without_granting_refutation() -> None:
    outcome, _ = verify(MATERIAL, {"grounding_kind": "derived",
                                   "derivation": "not allowed implies no penalty", "value": 0})
    assert outcome == UNRESOLVED


def test_quoting_tolerates_case_whitespace_and_curly_quotes() -> None:
    assert span_occurs("The  user said “Last Month” here", 'the user said "last month" here')
    assert normalize("  A   B ") == "a b"


def test_a_boolean_value_is_never_required_to_appear_in_its_span() -> None:
    assert value_in_span("include the age breakdown", False)


def test_an_unknown_grounding_kind_resolves_nothing() -> None:
    assert verify(MATERIAL, {"grounding_kind": "guessed", "value": "x"})[0] == UNRESOLVED
