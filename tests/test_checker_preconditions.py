"""A checker declares what it needs; the audit does not guess from a name.

`OracleChecker` audits a scalar reference answer.  A benchmark scored by
running tests or applying a rubric has no scalar answer to audit, and calling
that absence `missing_oracle` is a false finding about every one of its rows.

That was previously handled outside the checker: a name-based detector scored
field names to guess "workspacebench", and a central policy switched this one
check off for the two families it knew.  A benchmark it did not recognise --
which is every benchmark but three -- got the false findings anyway.

The precondition belongs to the checker, stated against the profile derived
from the benchmark's own rows, and its outcome is recorded in the coverage
ledger rather than silently dropped.
"""

from __future__ import annotations

from benchcore.checkers import OracleChecker
from benchcore.evaluators import ITEM_SCORING_KEY
from benchcore.schema import BenchmarkItem


def _item(comparison: str | None) -> BenchmarkItem:
    metadata = {} if comparison is None else {ITEM_SCORING_KEY: {"comparison": comparison}}
    return BenchmarkItem(
        item_id="x",
        raw={},
        task="Refactor the module and make the suite pass",
        gold=None,
        metadata=metadata,
    )


def test_a_test_executed_benchmark_is_not_audited_for_a_scalar_answer():
    eligibility = OracleChecker().audit_eligibility(_item("test_execution"))
    assert eligibility.eligible is False
    assert "scalar" in eligibility.reason


def test_a_rubric_graded_benchmark_is_not_audited_for_a_scalar_answer():
    assert OracleChecker().audit_eligibility(_item("rubric_graded")).eligible is False


def test_a_state_checked_benchmark_is_not_audited_for_a_scalar_answer():
    assert OracleChecker().audit_eligibility(_item("state_check")).eligible is False


def test_a_scalar_answer_benchmark_is_still_audited():
    assert OracleChecker().audit_eligibility(_item("exact_match")).eligible is not False


def test_without_a_profile_the_precondition_is_not_asserted():
    """No profile means no verdict on the shape -- not a licence to assume one."""
    assert OracleChecker().audit_eligibility(_item(None)).eligible is not False


def test_the_skip_reaches_the_ledger_rather_than_vanishing():
    from benchcore.auditor import audit_items_with_ledger

    result = audit_items_with_ledger(
        [_item("rubric_graded")], checkers=[OracleChecker()]
    )
    entries = [e for e in result.ledger if e.checker == "oracle_ground_truth"]
    assert len(entries) == 1
    assert entries[0].status == "ineligible"
    assert entries[0].attempted is False
    assert not [v for v in result.violations if v.defect_type == "missing_oracle"]


def _swe_item(**raw) -> BenchmarkItem:
    return BenchmarkItem(item_id="s", raw=raw, task="Fix the crash", gold="g")


def test_leak_detection_is_inapplicable_without_a_patch_to_leak():
    """No gold patch means nothing this checker could find, which is not the
    same as looking and finding nothing."""

    from benchcore.swe_leak import SolutionLeakChecker

    eligibility = SolutionLeakChecker().audit_eligibility(_swe_item())
    assert eligibility.eligible is False
    assert "patch" in eligibility.reason


def test_leak_detection_applies_when_a_patch_is_present():
    from benchcore.swe_leak import SolutionLeakChecker

    item = _swe_item(patch="--- a/x.py\n+++ b/x.py\n+    return 1\n")
    assert SolutionLeakChecker().audit_eligibility(item).eligible is True


# --- what the rows themselves show, when nothing has been profiled -----------

def test_a_benchmark_where_no_record_carries_a_gold_is_not_gold_scored():
    """Observable without a model and without knowing the benchmark's name.

    零 gold across every record is the benchmark's design; a gold missing from
    some records while others have one is a data defect and still reported.
    """

    from benchcore.evaluators import ITEM_GOLD_COVERAGE_KEY

    item = BenchmarkItem(
        item_id="t", raw={}, task="Create /app/result.txt", gold=None,
        evaluator={"type": "some_verifier"},
        metadata={ITEM_GOLD_COVERAGE_KEY: False},
    )
    assert OracleChecker().audit_eligibility(item).eligible is False


def test_a_benchmark_where_some_records_carry_a_gold_still_reports_the_gaps():
    from benchcore.evaluators import ITEM_GOLD_COVERAGE_KEY

    item = BenchmarkItem(
        item_id="t", raw={}, task="Q", gold=None,
        metadata={ITEM_GOLD_COVERAGE_KEY: True},
    )
    assert OracleChecker().audit_eligibility(item).eligible is not False


def test_a_profile_outranks_the_observation():
    """The profile read the rows deliberately; coverage is a fallback."""

    from benchcore.evaluators import ITEM_GOLD_COVERAGE_KEY

    item = BenchmarkItem(
        item_id="t", raw={}, task="Q", gold=None,
        metadata={ITEM_SCORING_KEY: {"comparison": "exact_match"},
                  ITEM_GOLD_COVERAGE_KEY: False},
    )
    assert OracleChecker().audit_eligibility(item).eligible is not False
