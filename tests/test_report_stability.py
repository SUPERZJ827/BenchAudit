from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from benchcore.report import (
    REPORT_SCHEMA_VERSION,
    STABLE_PAYLOAD_SCHEMA_VERSION,
    build_report,
    stable_payload_sha256,
    write_json_report,
)
from benchcore.schema import BenchmarkItem, FieldMapping, Violation


def _item() -> BenchmarkItem:
    return BenchmarkItem(
        item_id="stable-row",
        row_uid="source-row-00000000",
        source_row_index=0,
        source_row_sha256="a" * 64,
        task="Return the declared answer.",
        raw={"id": "stable-row", "task": "Return the declared answer."},
    )


def _violation() -> Violation:
    return Violation(
        item_id="stable-row",
        row_uid="source-row-00000000",
        source_row_sha256="a" * 64,
        defect_type="fixture_review_signal",
        artifact="task",
        mechanism="fixture",
        message="Frozen fixture finding.",
        severity="review",
        confidence=0.8,
        detection_method="fixture_checker",
        evidence={"fixture": True},
        evidence_tier="review",
        review_only=True,
    )


def _build(tmp_path: Path, *, elapsed: float, started: str) -> dict:
    source = tmp_path / "source.jsonl"
    source.write_text('{"id":"stable-row"}\n', encoding="utf-8")
    return build_report(
        str(source),
        [_item()],
        [_violation()],
        FieldMapping(item_id="id", task="task"),
        methods_run=["fixture_checker"],
        run_metadata={
            "started_at_utc": started,
            "finished_at_utc": started,
            "elapsed_seconds": elapsed,
            "pid": int(elapsed * 1000),
            "temporary_path": f"/tmp/run-{elapsed}",
        },
    )


def test_stable_payload_hash_excludes_volatile_run_metadata(tmp_path: Path) -> None:
    first = _build(tmp_path, elapsed=1.25, started="2026-08-02T00:00:00+00:00")
    second = _build(tmp_path, elapsed=9.75, started="2026-08-02T01:00:00+00:00")

    assert first["schema_version"] == REPORT_SCHEMA_VERSION
    assert first["stable_payload_schema_version"] == STABLE_PAYLOAD_SCHEMA_VERSION
    assert first["stable_payload_sha256"] == second["stable_payload_sha256"]
    assert json.dumps(first, sort_keys=True) != json.dumps(second, sort_keys=True)


def test_stable_payload_hash_changes_with_semantic_finding(tmp_path: Path) -> None:
    report = _build(tmp_path, elapsed=1.0, started="2026-08-02T00:00:00+00:00")
    original = report["stable_payload_sha256"]
    report["violations"][0]["message"] = "Changed semantic finding."

    assert stable_payload_sha256(report) != original


def test_report_metadata_does_not_change_violation_payload(tmp_path: Path) -> None:
    violation = _violation()
    source = tmp_path / "source.jsonl"
    source.write_text('{"id":"stable-row"}\n', encoding="utf-8")
    report = build_report(
        str(source),
        [_item()],
        [violation],
        FieldMapping(item_id="id", task="task"),
        run_metadata={"elapsed_seconds": 3.0},
    )

    assert report["violations"] == [asdict(violation)]
    assert report["summary"]["violation_count"] == 1
    assert report["summary"]["review_signal_count"] == 1
    assert report["summary"]["confirmed_count"] == 0


def test_json_writer_refreshes_hash_after_semantic_change(tmp_path: Path) -> None:
    report = _build(tmp_path, elapsed=1.0, started="2026-08-02T00:00:00+00:00")
    old_hash = report["stable_payload_sha256"]
    report["methods_run"].append("second_checker")
    output = tmp_path / "report.json"

    write_json_report(output, report)
    written = json.loads(output.read_text(encoding="utf-8"))

    assert written["stable_payload_sha256"] != old_hash
    assert written["stable_payload_sha256"] == stable_payload_sha256(written)
