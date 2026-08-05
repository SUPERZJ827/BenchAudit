"""A profiled shape can call for checkers the caller did not request.

Every rule adds; none removes. A wrong "this benchmark needs X" costs a few
review-tier candidates, while a wrong "this benchmark does not need X" is
silent: the audit reports nothing and nobody can tell whether that means clean
or unexamined.

What each addition was called for is recorded, because two audits are
comparable only when they enabled the same checkers -- an earlier pair of runs
was rendered incomparable by an unrecorded difference of exactly this kind.
"""

from __future__ import annotations

from benchcore.benchmark_profile import BenchmarkProfile
from benchcore.cli import PROFILE_CHECKER_RULES, checkers_called_for


def _profile(**overrides) -> BenchmarkProfile:
    base = dict(
        fingerprint="x", field_names=(), task_shape="other",
        answer_cardinality="single", modality="text", scoring={"comparison": "other"},
    )
    base.update(overrides)
    return BenchmarkProfile(**base)


def test_several_accepted_answers_call_for_the_multiplicity_auditor():
    profile = _profile(task_shape="open_ended_qa",
                       scoring={"comparison": "any_of_accepted"})
    assert checkers_called_for(profile) == [
        {"checker": "llm:multiplicity", "because": "scoring.comparison=any_of_accepted"}
    ]


def test_rubric_grading_calls_for_the_contract_checks():
    profile = _profile(scoring={"comparison": "rubric_graded"})
    assert [entry["checker"] for entry in checkers_called_for(profile)] == [
        "artifact_contract"
    ]


def test_two_dimensions_calling_for_one_checker_add_it_once():
    profile = _profile(task_shape="artifact_production",
                       scoring={"comparison": "rubric_graded"})
    called = checkers_called_for(profile)
    assert [entry["checker"] for entry in called] == ["artifact_contract"]


def test_a_shape_matching_no_rule_adds_nothing():
    assert checkers_called_for(_profile()) == []


def test_no_profile_adds_nothing():
    """Without a profile an audit must behave exactly as before."""
    assert checkers_called_for(None) == []


def test_every_addition_names_the_dimension_that_called_for_it():
    profile = _profile(task_shape="multiple_choice")
    for entry in checkers_called_for(profile):
        dimension, _, value = entry["because"].partition("=")
        assert dimension and value


def test_no_rule_ever_removes_a_checker():
    """The rule table is add-only by construction; keep it that way."""
    for dimension, value, checker in PROFILE_CHECKER_RULES:
        assert dimension and value and checker
        assert not checker.startswith("-")


def test_missing_scoring_block_does_not_crash_the_lookup():
    assert checkers_called_for(_profile(scoring={})) == []
    assert checkers_called_for(_profile(scoring=None)) == []
