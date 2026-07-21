from __future__ import annotations

import time

import pytest

from benchcore.auditor import audit_items, audit_items_with_ledger
from benchcore.checkers import Checker, _violation
from benchcore.coverage import (
    AuditEligibility,
    AuditSecurityBlocked,
    AuditUnsupported,
    summarize_coverage,
)
from benchcore.methods import DatasetChecker, DuplicateConflictChecker
from benchcore.loader import explicit_mapping_provenance
from benchcore.report import build_report, write_markdown_report
from benchcore.schema import BenchmarkItem, FieldMapping


def _item(item_id: str, task: str = "A stable task") -> BenchmarkItem:
    raw = {"id": item_id, "task": task}
    return BenchmarkItem(
        item_id=item_id,
        raw=raw,
        task=task,
        metadata={"_mapping_provenance": explicit_mapping_provenance(
            adapter_id="test_audit_coverage_fixture",
            adapter_version="1",
            raw=raw,
            field_bindings={"item_id": "id", "task": "task"},
        )},
    )


class EmptyLegacyChecker(Checker):
    name = "empty_legacy"

    def check(self, item, root=None):
        return []


class ExplicitEmptyChecker(EmptyLegacyChecker):
    name = "explicit_empty"

    def audit_eligibility(self, item, root=None):
        return AuditEligibility.applicable("task text is present")


class FindingChecker(Checker):
    name = "finding_checker"

    def audit_eligibility(self, item, root=None):
        return AuditEligibility.applicable("all synthetic rows are supported")

    def check(self, item, root=None):
        return [
            _violation(
                item,
                "missing_task",
                1.0,
                "synthetic finding",
                method="static_rule",
            )
        ]


class ExplodingChecker(Checker):
    name = "exploding_checker"

    def audit_eligibility(self, item, root=None):
        return AuditEligibility.applicable("synthetic failure path")

    def check(self, item, root=None):
        raise RuntimeError(f"provider failed for {item.item_id}")


def test_empty_return_is_not_reported_as_clean() -> None:
    result = audit_items_with_ledger(
        [_item("row-1")],
        checkers=[EmptyLegacyChecker()],
    )

    assert result.violations == []
    entry = result.ledger[0]
    assert entry.status == "completed_no_finding"
    assert entry.eligible is None
    assert entry.attempted is True
    assert entry.completed is True
    assert entry.coverage_unknown is True
    assert "not evidence that the item is clean" in entry.reason
    assert entry.lifecycle == ["planned", "attempted", "completed_no_finding"]


def test_explicit_eligibility_closes_no_finding_coverage() -> None:
    result = audit_items_with_ledger(
        [_item("row-1")],
        checkers=[ExplicitEmptyChecker()],
    )

    entry = result.ledger[0]
    assert entry.status == "completed_no_finding"
    assert entry.eligible is True
    assert entry.coverage_unknown is False
    assert entry.lifecycle == [
        "planned",
        "eligible",
        "attempted",
        "completed_no_finding",
    ]


def test_finding_and_exception_have_distinct_coverage_states() -> None:
    result = audit_items_with_ledger(
        [_item("row-1")],
        checkers=[FindingChecker(), ExplodingChecker()],
    )

    assert len(result.violations) == 1
    by_checker = {entry.checker: entry for entry in result.ledger}
    finding = by_checker["finding_checker"]
    failure = by_checker["exploding_checker"]
    assert finding.status == "finding"
    assert finding.completed is True
    assert finding.finding_count == 1
    assert finding.substantive_finding_count == 1
    assert failure.status == "operational_failed"
    assert failure.completed is False
    assert failure.attempted is True
    assert failure.details["exception_type"] == "RuntimeError"
    assert "row-1" in failure.reason


class OneRowDatasetChecker(DatasetChecker):
    name = "one_row_dataset"

    def check(self, items):
        yield _violation(
            items[0],
            "duplicate_task",
            0.9,
            "synthetic dataset finding",
            method="dataset_duplicate_scan",
        )


class CrossRowFindingChecker:
    name = "cross_row_finding"

    def check(self, item, root=None):
        finding = _violation(
            item,
            "duplicate_task",
            0.9,
            "stale worker-local finding",
            review_only=True,
            method="dataset_duplicate_scan",
        )
        finding.row_uid = "some-other-row"
        yield finding


def test_item_checker_cannot_emit_a_stale_cross_row_finding() -> None:
    result = audit_items_with_ledger(
        [_item("row-1")],
        checkers=[CrossRowFindingChecker()],
    )

    assert result.violations == []
    assert result.ledger[0].status == "operational_failed"
    assert result.ledger[0].details["exception_type"] == "ValueError"


class UnknownDatasetTargetChecker(DatasetChecker):
    name = "unknown_dataset_target"

    def check(self, items):
        yield _violation(
            items[0],
            "duplicate_task",
            0.9,
            "finding targets a non-existent row",
            {"target_row_uids": ["not-a-live-row"]},
            review_only=True,
            method="dataset_duplicate_scan",
        )


def test_dataset_checker_cannot_target_unknown_row_uid() -> None:
    result = audit_items_with_ledger(
        [_item("row-1"), _item("row-2")],
        checkers=[],
        dataset_checkers=[UnknownDatasetTargetChecker()],
    )

    assert result.violations == []
    assert all(entry.status == "operational_failed" for entry in result.ledger)


def test_dataset_checker_is_projected_to_every_item_without_clean_claims() -> None:
    items = [_item("row-1"), _item("row-2")]
    result = audit_items_with_ledger(
        items,
        checkers=[],
        dataset_checkers=[OneRowDatasetChecker()],
    )

    assert len(result.violations) == 1
    assert [(entry.item_id, entry.checker_scope) for entry in result.ledger] == [
        ("row-1", "dataset"),
        ("row-2", "dataset"),
    ]
    first, second = result.ledger
    assert first.status == "finding"
    assert first.eligible is True
    assert second.status == "completed_no_finding"
    assert second.eligible is None
    assert second.coverage_unknown is True


def test_duplicate_item_ids_use_unique_row_identity_for_evidence_and_ledger() -> None:
    items = [_item("dup", "same"), _item("dup", "different")]

    result = audit_items_with_ledger(
        items, checkers=[], dataset_checkers=[DuplicateConflictChecker()],
    )

    duplicate = next(
        row for row in result.violations if row.defect_type == "duplicate_item_id"
    )
    assert duplicate.evidence_tier == "confirmed"
    assert len(set(duplicate.evidence["target_row_uids"])) == 2
    assert duplicate.row_uid in duplicate.evidence["target_row_uids"]
    assert len({entry.row_uid for entry in result.ledger}) == 2
    assert all(entry.status == "finding" for entry in result.ledger)
    assert all(entry.finding_count == 1 for entry in result.ledger)


def test_dataset_finding_does_not_broadcast_across_duplicate_item_id() -> None:
    items = [_item("dup", "first"), _item("dup", "second")]

    result = audit_items_with_ledger(
        items, checkers=[], dataset_checkers=[OneRowDatasetChecker()],
    )

    assert [entry.status for entry in result.ledger] == [
        "finding", "completed_no_finding",
    ]
    assert result.violations[0].row_uid == items[0].row_uid


def test_compatibility_api_remains_fail_fast() -> None:
    with pytest.raises(RuntimeError, match="provider failed"):
        audit_items([_item("row-1")], checkers=[ExplodingChecker()])


class MixedConcurrentChecker(Checker):
    name = "mixed_concurrent"

    def audit_eligibility(self, item, root=None):
        if item.item_id.endswith("u"):
            raise AuditUnsupported("required evaluator is absent")
        return AuditEligibility.applicable("synthetic item is supported")

    def check(self, item, root=None):
        # Force futures to complete in a different order from the input.  The
        # ledger must remain item-aligned without shared mutable collector state.
        number = int(item.item_id.split("-")[1][:-1])
        time.sleep((7 - number % 7) * 0.0002)
        if item.item_id.endswith("e"):
            raise ValueError(f"boom:{item.item_id}")
        if item.item_id.endswith("s"):
            raise AuditSecurityBlocked("sandbox policy denied the input")
        if item.item_id.endswith("f"):
            return FindingChecker().check(item)
        return []


def test_parallel_ledger_is_thread_safe_item_aligned_and_deterministic() -> None:
    suffixes = ("n", "f", "e", "s", "u")
    items = [_item(f"row-{index}{suffixes[index % len(suffixes)]}") for index in range(80)]

    result = audit_items_with_ledger(
        items,
        checkers=[MixedConcurrentChecker()],
        workers=8,
    )

    assert [entry.item_id for entry in result.ledger] == [item.item_id for item in items]
    assert len({(entry.item_id, entry.checker) for entry in result.ledger}) == len(items)
    expected = {
        "n": "completed_no_finding",
        "f": "finding",
        "e": "operational_failed",
        "s": "security_blocked",
        "u": "unsupported",
    }
    assert all(entry.status == expected[entry.item_id[-1]] for entry in result.ledger)
    assert len(result.violations) == 16


def test_report_serializes_and_summarizes_coverage_ledger(tmp_path) -> None:
    item = _item("row-1")
    result = audit_items_with_ledger(
        [item],
        checkers=[FindingChecker(), EmptyLegacyChecker(), ExplodingChecker()],
    )
    report = build_report(
        "fixture.jsonl",
        [item],
        result.violations,
        FieldMapping(item_id="id", task="task"),
        methods_run=["finding_checker", "empty_legacy", "exploding_checker"],
        audit_ledger=result.ledger,
    )

    coverage = report["summary"]["audit_coverage"]
    assert coverage["planned"] == 3
    assert coverage["eligible"] == 2
    assert coverage["attempted"] == 3
    assert coverage["completed"] == 2
    assert coverage["unknown"] == 2
    assert coverage["operational_failed"] == 1
    assert coverage["completed_no_finding"] == 1
    assert report["coverage_ledger"][1]["coverage_unknown"] is True
    assert summarize_coverage(result.ledger) == coverage

    markdown_path = tmp_path / "report.md"
    write_markdown_report(markdown_path, report)
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "## Item × Checker Coverage Ledger" in markdown
    assert "It is not a clean-benchmark verdict" in markdown
    assert "Operational failures: `1`" in markdown
    assert "`row-1` × `exploding_checker`: `operational_failed`" in markdown
