

def test_parse_number_rejects_a_structured_reference() -> None:
    from benchcore.evaluators import parse_number

    # A structured call is not a numeric answer. Stringifying it and taking the
    # first digits turned a date inside a function argument into the answer 2023.
    assert parse_number({"cultural_experience_finder": {"date": "2023-01-02"}}) is None
    assert parse_number({"tool": {"nested": {"assessmentDate": "2022-06"}}}) is None


def test_parse_number_still_reads_scalars() -> None:
    from benchcore.evaluators import parse_number

    assert parse_number("42") == 42.0
    assert parse_number("约 3.5") == 3.5
    assert parse_number(7) == 7.0
    assert parse_number(None) is None


def test_structured_reference_is_not_typed_as_a_numeric_answer() -> None:
    from benchcore.evaluators import infer_evaluator_type

    assert infer_evaluator_type({"tool": {"date": "2023-01-02"}}, None, None) != "numeric"
