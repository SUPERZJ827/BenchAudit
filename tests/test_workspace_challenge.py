import copy
import json
from pathlib import Path

import pytest

from benchcore.workspace_challenge import (
    CONTRACT_FILENAME_CONFLICT,
    DANGLING_DEPENDENCY,
    WORKSPACE_CHALLENGE_OPERATORS,
    audit_workspace_challenge,
    build_workspace_challenge,
    rows_contain_provenance,
    score_workspace_challenge,
    wilson_interval,
)


def workspace_row(input_path: Path) -> dict:
    rubrics = ["Was report.md created?"]
    rubric_types = ["Basic Evaluation"]
    outputs = ["report.md"]
    second_input = input_path.with_name("fedcba9876543210_second.txt")
    second_input.write_text("other facts", encoding="utf-8")
    manifest = [
        {"filename": "source.txt", "stored_relpath": f"data/{input_path.name}"},
        {"filename": "second.txt", "stored_relpath": f"data/{second_input.name}"},
    ]
    graph = [{"from": "source.txt", "to": "report.md"}]
    return {
        "item_id": "workspacebench-1",
        "absolute_id": 1,
        "task": "Read source.txt and create report.md.",
        "context": {
            "output_files": outputs,
            "data_manifest": manifest,
            "file_dep_graph": graph,
        },
        "output_contract": {
            "type": "workspace_files",
            "required_files": outputs,
        },
        "evaluator": {
            "type": "workspacebench_rubric",
            "rubrics": rubrics,
            "rubric_types": rubric_types,
        },
        "input_files": [str(input_path), str(second_input)],
        # Official Workspace exports retain these raw JSON-string views.
        "rubrics": json.dumps(rubrics),
        "rubric_types": json.dumps(rubric_types),
        "output_files": json.dumps(outputs),
        "data_manifest": json.dumps(manifest),
        "file_dep_graph": json.dumps(graph),
    }


def test_challenge_is_deterministic_and_keeps_provenance_sidecar_only(tmp_path: Path):
    source_file = tmp_path / "0123456789abcdef_source.txt"
    source_file.write_text("facts", encoding="utf-8")
    source = workspace_row(source_file)
    untouched = copy.deepcopy(source)

    first = build_workspace_challenge([source], seed=17, allowed_roots=[tmp_path])
    second = build_workspace_challenge([source], seed=17, allowed_roots=[tmp_path])

    assert source == untouched
    assert len(first.clean_rows) == 1
    assert len(first.mutant_rows) == len(WORKSPACE_CHALLENGE_OPERATORS) == 6
    assert len(first.provenance) == 6
    assert first.clean_rows == second.clean_rows
    assert first.mutant_rows == second.mutant_rows
    assert first.manifest() == second.manifest()
    assert not rows_contain_provenance(first.clean_rows)
    assert not rows_contain_provenance(first.mutant_rows)
    assert all("_injected_defect" not in row for row in first.mutant_rows)
    assert all(provenance.operator not in provenance.mutant_item_id for provenance in first.provenance)
    assert {row.operator for row in first.provenance} == set(WORKSPACE_CHALLENGE_OPERATORS)


def test_content_collision_mutation_requires_explicit_safe_attachment_roots(tmp_path: Path):
    source_file = tmp_path / "0123456789abcdef_source.txt"
    source_file.write_text("facts", encoding="utf-8")

    challenge = build_workspace_challenge([workspace_row(source_file)], seed=19)

    assert len(challenge.provenance) == len(WORKSPACE_CHALLENGE_OPERATORS) - 1
    assert any(
        row["operator"] == "manifest_filename_content_collision"
        and "trusted roots" in row["reason"]
        for row in challenge.skipped
    )


def test_all_objective_mutations_are_exactly_detected(tmp_path: Path):
    source_file = tmp_path / "0123456789abcdef_source.txt"
    source_file.write_text("facts", encoding="utf-8")
    challenge = build_workspace_challenge(
        [workspace_row(source_file)], seed=23, allowed_roots=[tmp_path],
    )

    result = audit_workspace_challenge(challenge, root=tmp_path)
    score = result["score"]

    assert result["clean"]["violation_count"] == 0
    assert result["mutant"]["violation_count"] == 6
    assert score["pairs"] == 6
    assert score["exact_detected"] == 6
    assert score["exact_recall"] == 1.0
    assert score["paired_discriminated"] == 6
    assert score["paired_discrimination"] == 1.0
    assert score["clean_expected_alarm_pairs"] == 0
    assert score["clean_alarm_items"] == 0
    assert score["extra_alarm_count"] == 0
    assert score["duplicate_alarm_count"] == 0
    assert all(row["exact_recall"] == 1.0 for row in score["per_operator"].values())


def test_atomic_delta_is_not_masked_by_a_preexisting_invariant_issue(tmp_path: Path):
    source_file = tmp_path / "0123456789abcdef_source.txt"
    source_file.write_text("facts", encoding="utf-8")
    source = workspace_row(source_file)
    source["rubrics"] = json.dumps(["Pre-existing divergent raw rubric"])
    challenge = build_workspace_challenge(
        [source], operators=[DANGLING_DEPENDENCY], seed=29, allowed_roots=[tmp_path],
    )

    score = audit_workspace_challenge(challenge, root=tmp_path)["score"]

    assert score["clean_alarm_items"] == 1
    assert score["exact_recall"] == 1.0
    assert score["paired_discrimination"] == 1.0
    assert score["extra_alarm_count"] == 0


def test_score_reports_extra_and_duplicate_delta_alarms(tmp_path: Path):
    source_file = tmp_path / "0123456789abcdef_source.txt"
    source_file.write_text("facts", encoding="utf-8")
    challenge = build_workspace_challenge(
        [workspace_row(source_file)],
        operators=[CONTRACT_FILENAME_CONFLICT], allowed_roots=[tmp_path],
        seed=31,
    )
    result = audit_workspace_challenge(challenge, root=tmp_path)
    mutant = list(result["mutant"]["violations"])
    mutant.append(copy.deepcopy(mutant[0]))
    mutant.append({
        "item_id": challenge.provenance[0].mutant_item_id,
        "defect_type": "inaccessible_attachment",
        "message": "unrelated alarm",
        "evidence": {"missing_paths": ["ghost.txt"]},
    })

    score = score_workspace_challenge(
        challenge.provenance,
        result["clean"]["violations"],
        mutant,
    )

    assert score["exact_recall"] == 1.0
    assert score["duplicate_alarm_count"] == 1
    assert score["extra_alarm_count"] == 2


def test_wilson_interval_handles_boundary_counts():
    low, high = wilson_interval(0, 20)
    assert low == 0.0
    assert high == pytest.approx(0.161125, abs=1e-6)
    low, high = wilson_interval(42, 42)
    assert low == pytest.approx(0.916201, abs=1e-6)
    assert high == 1.0
    with pytest.raises(ValueError):
        wilson_interval(2, 1)
