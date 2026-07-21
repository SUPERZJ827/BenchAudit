from benchcore.checkers import (
    OracleChecker,
    TaskSpecChecker,
    _extract_simple_arithmetic_value,
)
from benchcore.schema import BenchmarkItem


def test_task_spec_checker_can_disable_keyword_ambiguity_only():
    item = BenchmarkItem(
        item_id="workspace-current",
        raw={},
        task=(
            "Use the attached PDF. The current version is complete; "
            "create a backup report."
        ),
        context={},
    )

    default_types = [v.defect_type for v in TaskSpecChecker().check(item)]
    workspace_types = [
        v.defect_type for v in TaskSpecChecker(check_ambiguity=False).check(item)
    ]

    assert "missing_context" in default_types
    assert "ambiguous_goal" in default_types
    assert workspace_types == ["missing_context"]


def test_arithmetic_extractor_rejects_truncated_natural_language():
    """A numeric prefix is not the task's arithmetic expression.

    The extractor used to stop at the first non-arithmetic character and
    evaluate the surviving fragment, so ``What is 15 percent of 200?`` yielded
    15.0.  Promotion replays the same function, so a correct gold of 30 was
    published as a confirmed ``wrong_gold_answer``.
    """

    for task in (
        "What is 15 percent of 200?",
        "Compute 100 minus 37.",
        "What is 2 to the power of 10?",
        "What is 12 divided by 4 plus 3?",
        "Calculate 8 apples plus 7 oranges. How many pieces of fruit?",
        "What is 5 more than 20?",
    ):
        assert _extract_simple_arithmetic_value(task) is None, task


def test_arithmetic_extractor_still_evaluates_whole_expression_tasks():
    assert _extract_simple_arithmetic_value("What is 3 + 4?") == 7.0
    assert _extract_simple_arithmetic_value("Calculate (2+3)*4") == 20.0
    assert _extract_simple_arithmetic_value("compute 10 / 4") == 2.5


def test_arithmetic_extractor_does_not_span_lines():
    assert _extract_simple_arithmetic_value("What is 3 + 4?\nAlso 99 + 1.") is None
    assert _extract_simple_arithmetic_value("What is 9 ** 999999?") is None


def test_arithmetic_proof_language_rejects_non_solve_contexts():
    for task in (
        'The example says "What is 2 + 2?"',
        "Find the error in: What is 2 + 2?",
        "What is 2 + 2? Explain your reasoning.",
        "What is 2 + 2 meters?",
    ):
        assert _extract_simple_arithmetic_value(task) is None


def test_correct_arithmetic_gold_is_not_reported_as_wrong():
    """The end-to-end guarantee: correct items yield no confirmed defect."""

    for task, gold in (
        ("What is 15 percent of 200?", "30"),
        ("Compute 100 minus 37.", "63"),
        ("What is 2 to the power of 10?", "1024"),
        ("What is 12 divided by 4 plus 3?", "6"),
    ):
        item = BenchmarkItem(item_id="q", raw={}, task=task, gold=gold)
        findings = [
            violation for violation in OracleChecker().check(item)
            if violation.defect_type == "wrong_gold_answer"
        ]
        assert findings == [], (task, [f.evidence_tier for f in findings])


def test_arithmetic_confirmation_requires_complete_scalar_gold():
    item = BenchmarkItem(
        item_id="verbose-gold",
        raw={},
        task="What is 2 + 2?",
        gold="Question 2 has answer 4",
    )

    findings = [
        violation for violation in OracleChecker().check(item)
        if violation.defect_type == "wrong_gold_answer"
    ]

    assert findings == []


def test_arithmetic_proof_language_abstains_on_representation_conventions():
    for gold in ("1/3", "one third", "0.5 meters", "1,2"):
        item = BenchmarkItem(
            item_id="representation",
            raw={},
            task="What is 1 / 2?",
            gold=gold,
        )
        findings = [
            violation for violation in OracleChecker().check(item)
            if violation.defect_type == "wrong_gold_answer"
        ]
        assert findings == [], gold
