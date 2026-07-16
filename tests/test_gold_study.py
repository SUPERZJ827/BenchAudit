import json
from pathlib import Path

import pytest

from benchcore.gold_study import build_gold_study, write_gold_study_jsonl


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_gold_study_includes_flagged_and_unflagged_controls(tmp_path: Path):
    source = tmp_path / "items.jsonl"
    write_jsonl(source, [
        {"item_id": f"wb-{i}", "task": f"task {i}", "context": [], "evaluator": {"rubrics": [f"r{i}"]}}
        for i in range(1, 7)
    ])
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "field_mapping": {
            "item_id": "item_id", "task": "task", "context": ["context"],
            "evaluator": "evaluator", "metadata": [],
        },
        "violations": [
            {"item_id": "wb-1", "row_uid": "source-row-00000000", "defect_type": "artifact_data_gap"},
            {"item_id": "wb-2", "row_uid": "source-row-00000001", "defect_type": "task_rubric_mismatch"},
            {"item_id": "wb-3", "row_uid": "source-row-00000002", "defect_type": "task_rubric_mismatch"},
        ],
    }), encoding="utf-8")
    investigation = tmp_path / "investigation.json"
    investigation.write_text(json.dumps({"investigations": [
        {"item_id": "wb-1", "row_uid": "source-row-00000000", "verdict": "likely_true", "issue_category": "data_gap"},
        {"item_id": "wb-2", "row_uid": "source-row-00000001", "verdict": "false_positive", "issue_category": "task_rubric_mismatch"},
        {"item_id": "wb-3", "row_uid": "source-row-00000002", "verdict": "uncertain", "issue_category": "over_strict_rubric"},
    ]}), encoding="utf-8")

    study = build_gold_study(
        input_path=source,
        report_path=report,
        investigation_path=investigation,
        flagged_size=3,
        unflagged_size=2,
        seed=7,
    )

    records = study["records"]
    assert len(records) == 5
    assert {row["sampling_group"] for row in records} == {"flagged", "unflagged_control"}
    assert sum(row["sampling_group"] == "unflagged_control" for row in records) == 2
    assert {row["sampling_stratum"] for row in records if row["sampling_group"] == "flagged"} == {
        "likely_true:data_gap",
        "false_positive:task_rubric_mismatch",
        "uncertain:over_strict_rubric",
    }

    out = tmp_path / "study.jsonl"
    write_gold_study_jsonl(out, study)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert "_manifest" in json.loads(lines[0])
    assert json.loads(lines[1])["human_label"] == "TODO"


def test_gold_study_samples_duplicate_ids_as_distinct_source_rows(tmp_path: Path):
    source = tmp_path / "duplicates.jsonl"
    write_jsonl(source, [
        {"item_id": "dup", "task": "first task"},
        {"item_id": "dup", "task": "second task"},
    ])
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "field_mapping": {"item_id": "item_id", "task": "task"},
        "violations": [{
            "item_id": "dup",
            "row_uid": "source-row-00000000",
            "defect_type": "wrong_gold_answer",
        }],
    }), encoding="utf-8")

    study = build_gold_study(
        input_path=source,
        report_path=report,
        investigation_path=None,
        flagged_size=1,
        unflagged_size=1,
        seed=3,
    )

    assert {row["row_uid"] for row in study["records"]} == {
        "source-row-00000000", "source-row-00000001",
    }
    by_uid = {row["row_uid"]: row for row in study["records"]}
    assert by_uid["source-row-00000000"]["task"] == "first task"
    assert by_uid["source-row-00000000"]["sampling_group"] == "flagged"
    assert by_uid["source-row-00000001"]["task"] == "second task"
    assert by_uid["source-row-00000001"]["sampling_group"] == "unflagged_control"


def test_gold_study_rejects_ambiguous_legacy_duplicate_finding(tmp_path: Path):
    source = tmp_path / "duplicates.jsonl"
    write_jsonl(source, [
        {"item_id": "dup", "task": "first task"},
        {"item_id": "dup", "task": "second task"},
    ])
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "field_mapping": {"item_id": "item_id", "task": "task"},
        "violations": [{
            "item_id": "dup", "defect_type": "wrong_gold_answer",
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="must carry a valid row_uid"):
        build_gold_study(
            input_path=source,
            report_path=report,
            investigation_path=None,
            flagged_size=1,
            unflagged_size=1,
            seed=3,
        )


def test_gold_study_rejects_unique_legacy_finding_without_row_uid(tmp_path: Path):
    source = tmp_path / "unique.jsonl"
    write_jsonl(source, [{"item_id": "one", "task": "task"}])
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "field_mapping": {"item_id": "item_id", "task": "task"},
        "violations": [{"item_id": "one", "defect_type": "wrong_gold_answer"}],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="must carry a valid row_uid"):
        build_gold_study(
            input_path=source,
            report_path=report,
            investigation_path=None,
            flagged_size=1,
            unflagged_size=0,
            seed=3,
        )


def test_gold_study_expands_valid_dataset_target_rows(tmp_path: Path):
    source = tmp_path / "duplicates.jsonl"
    write_jsonl(source, [
        {"item_id": "dup", "task": "same task"},
        {"item_id": "dup", "task": "same task"},
    ])
    target_uids = ["source-row-00000000", "source-row-00000001"]
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "field_mapping": {"item_id": "item_id", "task": "task"},
        "violations": [{
            "item_id": "dup",
            "row_uid": target_uids[0],
            "defect_type": "duplicate_item_id",
            "evidence": {"target_row_uids": target_uids},
        }],
    }), encoding="utf-8")

    study = build_gold_study(
        input_path=source,
        report_path=report,
        investigation_path=None,
        flagged_size=2,
        unflagged_size=0,
        seed=3,
    )

    assert {row["row_uid"] for row in study["records"]} == set(target_uids)
    assert all(row["sampling_group"] == "flagged" for row in study["records"])
