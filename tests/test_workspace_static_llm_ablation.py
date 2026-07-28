from pathlib import Path

import pytest

from scripts.run_workspace_static_llm_ablation import (
    NEGATIVE_REVIEW_LABEL,
    POSITIVE_REVIEW_LABEL,
    UNCERTAIN_REVIEW_LABEL,
    _assert_review_only,
    binary_metrics,
    estimate_grounding_call_structure,
    materialize_input_view,
    parse_item_ids_file,
    parse_objective_output_reference,
    parse_objective_task_placeholder_reference,
    parse_reviewed_reference,
    render_output_candidate_appendix,
    run_rules,
)
from scripts.analyze_workspace_grounding_dual_holdout import decision_sets
from benchcore.schema import BenchmarkItem, Violation


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
            "| `workspacebench-3` | — | `placeholder_leak` | task leak |",
            "| `workspacebench-4` | 1 | `placeholder_leak` | rubric leak |",
        ]),
        encoding="utf-8",
    )
    assert parse_objective_output_reference(path) == {"workspacebench-1"}
    assert parse_objective_task_placeholder_reference(path) == {
        "workspacebench-3"
    }


def test_parse_item_ids_file_accepts_frozen_manifest_and_rejects_duplicates(
    tmp_path: Path,
):
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"item_ids":["workspacebench-2","workspacebench-1"]}',
        encoding="utf-8",
    )
    assert parse_item_ids_file(path) == [
        "workspacebench-2", "workspacebench-1",
    ]

    path.write_text(
        '{"item_ids":["workspacebench-1","workspacebench-1"]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate item id"):
        parse_item_ids_file(path)


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


def test_dual_holdout_decision_sets_recover_each_router_and_union():
    rows = {
        "item-1": {
            "decisions": [
                {
                    "rubric_index": 0,
                    "label": "unsupported",
                    "scanner": {
                        "label": "unsupported",
                        "triage_selected": True,
                        "triage_selected_views": [
                            "hidden_constraint", "support_challenge",
                        ],
                    },
                },
                {
                    "rubric_index": 1,
                    "label": "supported",
                    "scanner": {
                        "label": "unsupported",
                        "triage_selected": True,
                        "triage_selected_views": ["support_challenge"],
                    },
                },
                {
                    "rubric_index": 2,
                    "label": "uncertain",
                    "scanner": {
                        "label": "uncertain",
                        "triage_selected": False,
                        "triage_selected_views": [],
                    },
                },
            ],
        },
    }

    result = decision_sets(rows)

    assert result["routed_hidden_constraint"] == {("item-1", 0)}
    assert result["routed_support_challenge"] == {
        ("item-1", 0), ("item-1", 1),
    }
    assert result["routed_union"] == {("item-1", 0), ("item-1", 1)}
    assert result["final_unsupported"] == {("item-1", 0)}


def test_cost_structure_estimate_uses_shared_scan_and_candidate_only_verification():
    rows = {
        "item-1": {
            "decisions": [
                {
                    "label": "unsupported",
                    "scanner": {"label": "unsupported"},
                    "verifier": {"label": "unsupported"},
                },
                {
                    "label": "supported",
                    "scanner": {"label": "unsupported"},
                    "verifier": {"label": "supported"},
                },
                {
                    "label": "supported",
                    "scanner": {"label": "supported"},
                    "verifier": None,
                },
            ],
        },
        "item-2": {
            "decisions": [
                {
                    "label": "uncertain",
                    "scanner": {"label": "uncertain"},
                    "verifier": None,
                },
            ],
        },
    }

    result = estimate_grounding_call_structure(rows)

    assert result["legacy"]["logical_calls"] == 6
    assert result["two_stage_conservative"]["shared_triage_calls"] == 2
    assert result["two_stage_conservative"]["isolated_verifier_calls"] == 2
    assert result["two_stage_conservative"]["logical_calls"] == 4
    assert result["two_stage_conservative"]["relative_call_reduction"] == pytest.approx(
        1 / 3,
    )
    assert result["two_stage_final_candidate_floor"]["logical_calls"] == 3


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


def test_rules_arm_includes_same_objective_grounding_resolver_as_assisted_arm(
    tmp_path: Path,
):
    source = tmp_path / "source.txt"
    source.write_text("ordinary source", encoding="utf-8")
    rubric = (
        'Does the primary requested artifact use the exact title "Wrong Title"?'
    )
    item = BenchmarkItem(
        item_id="workspacebench-1",
        raw={"input_files": [str(source)], "rubrics": [rubric]},
        task=(
            'Use the exact title "Required Title" for the primary requested '
            "artifact."
        ),
        context={},
        output_contract={
            "type": "workspace_files",
            "required_files": ["report.md"],
        },
        evaluator={"type": "workspacebench_rubric", "rubrics": [rubric]},
    )

    result = run_rules([item], [tmp_path])

    candidates = [
        row for row in result["workspace_invariant_findings"]
        if row.get("source") == "deterministic_objective_grounding_resolver"
    ]
    assert len(candidates) == 1
    assert candidates[0]["item_id"] == item.item_id
    assert candidates[0]["evidence"]["rubric_index"] == 0
    assert candidates[0]["evidence"]["objective_certificate"]["label"] == (
        "unsupported"
    )


def test_output_candidate_appendix_does_not_call_unlabeled_difference_false_positive():
    item = BenchmarkItem(
        item_id="workspacebench-1",
        raw={},
        task="Save the result as expected.md.",
        output_contract={
            "type": "workspace_files",
            "required_files": ["published.md"],
        },
    )
    report = render_output_candidate_appendix(
        items=[item],
        rules={
            "output_filename_findings": [{
                "item_id": item.item_id,
                "type": "file_name_conflict",
                "detail": "expected.md vs published.md",
            }],
        },
        task_rows={item.item_id: {"findings": [], "observation": {}}},
        output_positive_items=set(),
    )

    assert "否（待复核差异）" in report
    assert "假阳性" not in report
    assert "published.md" in report
