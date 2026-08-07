"""Two clarity heuristics only make sense on a question.

`ambiguous_goal` and `context_version_mismatch_risk` fire on wording like
"latest", "current", or "as of" when the record carries no version metadata.
That reasoning holds for a question whose answer moves with time.  It does not
hold for an instruction to produce something: "refactor to the current API" and
"use the latest release" are ordinary phrasing in a task specification, and
flagging them reports a defect on every such row.

Both were previously switched off from outside, by a name-based detector that
recognised two agent benchmarks and called everything else generic.  The
condition is a property of the task's shape, which the profile reads from the
benchmark's own rows.
"""

from __future__ import annotations

from benchcore.benchmark_profile import ITEM_TASK_SHAPE_KEY
from benchcore.checkers import ContextChecker, TaskSpecChecker
from benchcore.schema import BenchmarkItem


def _item(shape: str | None, task: str) -> BenchmarkItem:
    metadata = {} if shape is None else {ITEM_TASK_SHAPE_KEY: shape}
    return BenchmarkItem(item_id="x", raw={}, task=task, gold="g", metadata=metadata)


AMBIGUOUS = "Update the module to the latest API and keep the current behaviour"
VERSIONED = "Refactor as of the current release"


def _defects(checker, item):
    return {v.defect_type for v in checker.check(item)}


def test_an_instruction_is_not_flagged_for_time_sensitive_wording():
    item = _item("artifact_production", AMBIGUOUS)
    assert "ambiguous_goal" not in _defects(TaskSpecChecker(), item)


def test_a_multi_turn_task_is_not_flagged_either():
    item = _item("multi_turn_task", AMBIGUOUS)
    assert "ambiguous_goal" not in _defects(TaskSpecChecker(), item)


def test_a_question_is_still_flagged():
    item = _item("open_ended_qa", AMBIGUOUS)
    assert "ambiguous_goal" in _defects(TaskSpecChecker(), item)


def test_an_unprofiled_benchmark_keeps_the_existing_behaviour():
    """No profile is no verdict; the heuristic runs as it always did."""
    assert "ambiguous_goal" in _defects(TaskSpecChecker(), _item(None, AMBIGUOUS))


def test_version_risk_follows_the_same_rule():
    instruction = _item("artifact_production", VERSIONED)
    question = _item("open_ended_qa", VERSIONED)
    assert "context_version_mismatch_risk" not in _defects(ContextChecker(), instruction)
    assert "context_version_mismatch_risk" in _defects(ContextChecker(), question)
