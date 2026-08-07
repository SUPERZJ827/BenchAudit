"""Rubrics and scalar-answer shape are read from roles, not from field names.

A rubric is not a WorkspaceBench idea.  GDPval ships one, MT-Bench ships one,
and any benchmark graded against written criteria ships one -- under whatever
name its authors chose.  Guessing at four English spellings finds the ones that
happen to match and silently finds nothing for the rest, so every rubric check
quietly does nothing on a benchmark that calls the field something else.

The profile already decides which field holds the rubric, for every benchmark,
from its own rows.  That verdict was computed and thrown away.
"""

from __future__ import annotations

from benchcore.artifact_consistency import extract_rubrics
from benchcore.benchmark_profile import ITEM_ROLES_KEY
from benchcore.schema import BenchmarkItem


def test_a_rubric_is_found_under_a_name_no_heuristic_would_guess():
    item = BenchmarkItem(
        item_id="x", raw={"scoring_checklist": ["States the total.", "Cites a source."]},
        task="Write the summary",
        metadata={ITEM_ROLES_KEY: {"rubric": "scoring_checklist"}},
    )
    assert extract_rubrics(item) == ["States the total.", "Cites a source."]


def test_a_conventional_name_still_works_without_a_profile():
    """No profile means falling back to the ordinary English words for it."""
    item = BenchmarkItem(item_id="x", raw={"rubrics": ["Mentions the date."]}, task="t")
    assert extract_rubrics(item) == ["Mentions the date."]


def test_a_bound_role_beats_a_conventionally_named_field():
    item = BenchmarkItem(
        item_id="x",
        raw={"rubrics": ["stale copy"], "criteria_v2": ["the live one"]},
        task="t",
        metadata={ITEM_ROLES_KEY: {"rubric": "criteria_v2"}},
    )
    assert extract_rubrics(item) == ["the live one"]


def test_a_role_naming_an_absent_field_falls_back_rather_than_finding_nothing():
    item = BenchmarkItem(
        item_id="x", raw={"rubrics": ["present"]}, task="t",
        metadata={ITEM_ROLES_KEY: {"rubric": "gone_in_this_revision"}},
    )
    assert extract_rubrics(item) == ["present"]


# --- the same question, asked once ------------------------------------------

def test_contract_consistency_reads_the_profile_not_three_evaluator_names():
    """`_is_scalar_answer_contract` listed `workspacebench_rubric`,
    `agent_as_a_judge` and `rubric_judge`, so a rubric-graded benchmark using a
    fourth name got a scalar answer contract fabricated for it.  The profiled
    scoring answers the same question for any benchmark."""

    from benchcore.evaluators import ITEM_SCORING_KEY
    from benchcore.methods import ContractConsistencyChecker

    item = BenchmarkItem(
        item_id="x", raw={}, task="Produce the report", gold="see rubric",
        evaluator={"type": "criteria_panel_v3"},
        metadata={ITEM_SCORING_KEY: {"comparison": "rubric_graded"}},
    )
    assert ContractConsistencyChecker().audit_eligibility(item).eligible is False


def test_a_scalar_benchmark_is_still_checked():
    from benchcore.evaluators import ITEM_SCORING_KEY
    from benchcore.methods import ContractConsistencyChecker

    item = BenchmarkItem(
        item_id="x", raw={}, task="Q", gold="42",
        evaluator={"type": "exact_match"},
        metadata={ITEM_SCORING_KEY: {"comparison": "exact_match"}},
    )
    assert ContractConsistencyChecker().audit_eligibility(item).eligible is True
