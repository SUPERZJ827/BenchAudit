from __future__ import annotations

from scripts.preflight_apps_input_contract_v1 import classify_question


def question(input_text: str, *, body: str = "") -> str:
    return f"""Problem statement.
{body}
-----Input-----
{input_text}
-----Output-----
Print the answer.
"""


def test_single_integer_with_explicit_bounds_is_supported():
    assert classify_question(question(
        "The first line contains a single integer n. 1 <= n <= 100."
    )) == ("single_integer", "supported")


def test_fixed_integer_tuple_requires_bounds_for_every_value():
    assert classify_question(question(
        "The first line contains two integers n and m. "
        "1 <= n <= 10 and 0 <= m <= 20."
    )) == ("fixed_integer_tuple", "supported")
    schema, reason = classify_question(question(
        "The first line contains two integers n and m. 1 <= n <= 10."
    ))
    assert schema is None
    assert reason == "fixed_tuple_missing_bounds"


def test_counted_vector_with_indexed_element_bounds_is_supported():
    schema, reason = classify_question(question(
        "The first line contains a single integer n. 1 <= n <= 10.\n"
        "The second line contains n space-separated integers a_i. "
        "0 <= a_i <= 100."
    ))
    assert (schema, reason) == ("counted_integer_vector", "supported")


def test_multiple_test_cases_are_out_of_scope():
    schema, reason = classify_question(question(
        "The first line contains an integer t, the number of test cases. "
        "1 <= t <= 10."
    ))
    assert schema is None
    assert reason == "multiple_test_cases"


def test_hidden_full_question_domain_marker_blocks_certificate():
    schema, reason = classify_question(question(
        "The first line contains a single integer n. 1 <= n <= 100.",
        body="It is guaranteed that all values are distinct.",
    ))
    assert schema is None
    assert reason == "full_question_marker:guaranteed"


def test_parity_guarantee_outside_input_section_blocks_certificate():
    schema, reason = classify_question(question(
        "The first line contains a single integer n. 1 <= n <= 100.",
        body="The input number n is always even.",
    ))
    assert schema is None
    assert reason == "full_question_marker:parity_guarantee"
