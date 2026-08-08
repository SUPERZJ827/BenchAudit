"""Loose normalization removes formatting, not the answer.

It is the SQuAD recipe -- lowercase, drop punctuation, drop articles, squeeze
whitespace -- which is right for text spans and wrong for numbers, because two
of the characters it drops carry value rather than format.  A minus sign and a
decimal point are not the trailing period on "Paris.".

The clearest damage is not in comparison but in bookkeeping: a question whose
options are ['-19', '-10', '19', '10'] normalizes to two identical pairs, and
resolving an answer to an option then lands on whichever collided first.
"""

from __future__ import annotations

from benchcore.evaluators import choice_label_to_index, normalize_loose


def test_a_negative_number_is_not_its_own_opposite():
    assert normalize_loose("-5") != normalize_loose("5")


def test_a_decimal_point_is_not_dropped():
    assert normalize_loose("0.46") == "0.46"


def test_a_hyphen_between_digits_survives():
    assert normalize_loose("3-4") != normalize_loose("34")


def test_a_trailing_period_is_still_formatting():
    assert normalize_loose("Paris.") == "paris"


def test_a_hyphen_between_letters_is_still_formatting():
    """The letter-hyphen class must read exactly as it does today."""
    assert normalize_loose("e-mail") == "email"
    assert normalize_loose("state-of-the-art") == "stateoftheart"
    assert normalize_loose("mid-1990s") == "mid1990s"


def test_articles_and_whitespace_are_still_dropped():
    assert normalize_loose("  The  Answer  ") == "answer"


def test_signed_options_resolve_to_themselves():
    """Real item: four options collapsing to two under the old recipe."""
    options = ["-19", "-10", "19", "10"]
    assert [choice_label_to_index(option, options) for option in options] == [0, 1, 2, 3]
