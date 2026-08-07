"""What kind of benchmark this is comes from its rows, not from a name list.

detect_benchmark_family scores three particular benchmarks by their field and
file names, so anything outside that list is "generic" -- SVAMP, MMLU and
Platinum all are. The verdict is not cosmetic: it disables the scalar-gold
checker, adds workspace-specific ones, and selects which learned rules load.
Disabling a checker is a silent outcome, because an audit that reports nothing
reads the same whether the data was clean or never examined.

The profile already describes shape from the rows themselves, so where it
speaks it decides.
"""

from __future__ import annotations

from benchcore.benchmark_profile import BenchmarkProfile
from benchcore.planning import family_from_profile


def _profile(**kw) -> BenchmarkProfile:
    base = dict(fingerprint="f", field_names=(), task_shape="other",
                answer_cardinality="single", modality="text",
                scoring={"comparison": "other"})
    base.update(kw)
    return BenchmarkProfile(**base)


def test_producing_artifacts_graded_by_criteria_is_the_agent_family():
    profile = _profile(task_shape="artifact_production",
                       scoring={"comparison": "rubric_graded"})
    assert family_from_profile(profile) == "workspacebench"


def test_acting_and_being_graded_on_the_end_state_is_the_agent_family():
    profile = _profile(task_shape="multi_turn_task",
                       scoring={"comparison": "state_check"})
    assert family_from_profile(profile) == "terminalbench"


def test_code_graded_by_running_tests_is_the_code_family():
    profile = _profile(task_shape="code_generation",
                       scoring={"comparison": "test_execution"})
    assert family_from_profile(profile) == "swebench"


def test_a_question_with_a_reference_answer_is_generic():
    """The scalar-gold checker must stay enabled for these."""
    for shape, comparison in (("open_ended_qa", "exact_match"),
                              ("multiple_choice", "exact_match"),
                              ("open_ended_qa", "any_of_accepted")):
        assert family_from_profile(_profile(task_shape=shape,
                                            scoring={"comparison": comparison})) == "generic"


def test_no_profile_yields_no_verdict():
    """Without a profile the existing detector must still decide."""
    assert family_from_profile(None) is None


def test_an_unclassifiable_shape_yields_no_verdict():
    """Abstaining leaves the existing detector in charge rather than forcing
    a benchmark into a family that disables its checkers."""
    assert family_from_profile(_profile()) is None
