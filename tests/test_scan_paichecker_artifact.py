import json
from pathlib import Path

from scripts.scan_paichecker_artifact import (
    inspect_candidate_file,
    stage0_decision,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_single_unlabeled_example_is_not_research_dataset(tmp_path):
    path = tmp_path / "example.jsonl"
    _write_jsonl(
        path,
        [
            {
                "instance_id": "repo__project-1",
                "problem_statement": "secret issue body",
                "pr_description": "secret PR body",
                "patch": "secret patch",
                "test_patch": "secret test",
            }
        ],
    )
    result = inspect_candidate_file(path)
    assert result["record_count"] == 1
    assert result["label_fields"] == []
    assert result["qualifies_as_labeled_research_data"] is False
    assert "secret issue body" not in json.dumps(result)


def test_labeled_records_with_source_evidence_pass_stage0(tmp_path):
    path = tmp_path / "annotations.jsonl"
    _write_jsonl(
        path,
        [
            {
                "instance_id": "a-1",
                "label": "SC",
                "problem_statement": "x",
                "pr_description": "y",
            },
            {
                "instance_id": "a-2",
                "label": "No Misalignment",
                "problem_statement": "x",
                "pr_description": "y",
            },
        ],
    )
    candidate = inspect_candidate_file(path)
    decision, reason = stage0_decision([candidate])
    assert candidate["qualifies_as_labeled_research_data"] is True
    assert decision == "PASS_STAGE_0"
    assert reason == "labeled_source_evidence_available"


def test_labels_without_required_evidence_fail_closed(tmp_path):
    path = tmp_path / "labels.jsonl"
    _write_jsonl(
        path,
        [
            {"instance_id": "a-1", "label": "SC"},
            {"instance_id": "a-2", "label": "No Misalignment"},
        ],
    )
    candidate = inspect_candidate_file(path)
    decision, reason = stage0_decision([candidate])
    assert decision == "NOT_IDENTIFIABLE_DATA"
    assert reason == "labels_cannot_be_linked_to_required_source_evidence"


def test_no_labeled_dataset_fails_closed():
    decision, reason = stage0_decision(
        [
            {
                "record_count": 1,
                "field_names": ["instance_id", "test_patch"],
                "qualifies_as_labeled_research_data": False,
            }
        ]
    )
    assert decision == "NOT_IDENTIFIABLE_DATA"
    assert reason == "official_repository_contains_no_labeled_research_dataset"
