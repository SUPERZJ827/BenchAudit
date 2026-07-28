from pathlib import Path

import pytest

from scripts.run_workspace_static_llm_ablation import (
    NEGATIVE_REVIEW_LABEL,
    POSITIVE_REVIEW_LABEL,
    UNCERTAIN_REVIEW_LABEL,
    _assert_review_only,
    binary_metrics,
    materialize_input_view,
    parse_objective_output_reference,
    parse_reviewed_reference,
)
from benchcore.schema import Violation


def test_parse_reviewed_reference_keeps_only_rubric_labels(tmp_path: Path):
    path = tmp_path / "reviewed.md"
    path.write_text(
        "\n".join([
            "| `workspacebench-1` | 2 | **较可信真问题** | 0 | 0 | x | c | e | r |",
            "| `workspacebench-2` | 3 | **较可信非问题** | 0 | 0 | x | c | e | r |",
            "| `workspacebench-3` | 4 | **证据不足/分歧** | 0 | 0 | x | c | e | r |",
            "| `workspacebench-4` | — | **已确认** | 0 | 0 | x | c | e | r |",
        ]),
        encoding="utf-8",
    )
    assert parse_reviewed_reference(path) == {
        ("workspacebench-1", 2): POSITIVE_REVIEW_LABEL,
        ("workspacebench-2", 3): NEGATIVE_REVIEW_LABEL,
        ("workspacebench-3", 4): UNCERTAIN_REVIEW_LABEL,
    }


def test_parse_objective_output_reference_uses_exact_family(tmp_path: Path):
    path = tmp_path / "objective.md"
    path.write_text(
        "\n".join([
            "| `workspacebench-1` | — | `task_vs_contract_filename` | mismatch |",
            "| `workspacebench-2` | 3 | `rubric_vs_contract_filename` | mismatch |",
        ]),
        encoding="utf-8",
    )
    assert parse_objective_output_reference(path) == {"workspacebench-1"}


def test_binary_metrics_do_not_count_predictions_outside_reference_universe():
    metrics = binary_metrics(
        {"a", "b", "unlabeled"},
        {"a", "c"},
        {"a", "b", "c", "d"},
    )
    assert metrics == {
        "tp": 1,
        "fp": 1,
        "fn": 1,
        "tn": 1,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "predicted": 2,
        "positives": 2,
        "universe": 4,
    }


def test_review_only_safety_assertion_rejects_confirmed():
    review = Violation(
        item_id="x",
        artifact="evaluator",
        mechanism="inconsistent",
        defect_type="task_rubric_mismatch",
        severity="review",
        confidence=0.8,
        review_only=True,
        evidence_tier="review",
        proof_kind="model_judgment",
        message="candidate",
    )
    _assert_review_only([review])
    review.evidence_tier = "confirmed"
    with pytest.raises(AssertionError):
        _assert_review_only([review])


def test_review_only_safety_allows_operational_unknown_but_not_substantive_unknown():
    operational = Violation(
        item_id="x",
        artifact="auditor",
        mechanism="operational",
        defect_type="llm_audit_failure",
        severity="review",
        confidence=0.0,
        review_only=True,
        evidence_tier="unknown",
        proof_kind="unclassified",
        defect_scope="operational",
        message="API response failed validation",
    )
    _assert_review_only([operational])
    operational.defect_scope = "substantive"
    with pytest.raises(AssertionError):
        _assert_review_only([operational])


def test_materialized_input_view_turns_symlink_into_regular_file(tmp_path: Path):
    source = tmp_path / "blob"
    source.write_bytes(b"frozen workspace input")
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    declared = snapshot / "0123456789abcdef_input.txt"
    declared.symlink_to(source)
    rows = [{
        "item_id": "workspacebench-1",
        "input_files": [str(declared)],
        "task": "Summarize input.txt",
    }]

    staged, receipt = materialize_input_view(rows, tmp_path / "view")

    staged_path = Path(staged[0]["input_files"][0])
    assert staged_path.name == declared.name
    assert staged_path.is_file()
    assert not staged_path.is_symlink()
    assert staged_path.read_bytes() == source.read_bytes()
    assert rows[0]["input_files"] == [str(declared)]
    assert receipt["files"] == 1
    assert receipt["source_symlinks"] == 1
    assert receipt["hardlinked"] + receipt["copied"] == 1


def test_materialized_input_view_rejects_distinct_same_basename(tmp_path: Path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "input.txt").write_text("left", encoding="utf-8")
    (right / "input.txt").write_text("right", encoding="utf-8")
    rows = [{
        "item_id": "workspacebench-1",
        "input_files": [
            str(left / "input.txt"),
            str(right / "input.txt"),
        ],
    }]

    with pytest.raises(ValueError, match="share staged basename"):
        materialize_input_view(rows, tmp_path / "view")
