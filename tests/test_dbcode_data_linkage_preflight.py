import csv
import json
from pathlib import Path

from scripts.preflight_dbcode_data_linkage import (
    parse_json_file,
    run,
    trace_identity,
)


def test_json_list_extracts_only_structural_presence(tmp_path: Path):
    path = tmp_path / "rows.json"
    path.write_text(json.dumps([{
        "item_id": "Secret-ID",
        "task": "SECRET TASK TEXT",
        "reference_code": "SECRET REFERENCE",
        "generated_code": "SECRET CANDIDATE",
        "model": "model-a",
    }]), encoding="utf-8")

    parsed = parse_json_file(path)

    assert len(parsed.records) == 1
    assert parsed.records[0].identity == "secret-id"
    assert parsed.records[0].has_task is True
    assert parsed.records[0].has_reference is True
    assert parsed.records[0].has_candidate is True
    assert "SECRET TASK TEXT" not in repr(parsed)
    assert "SECRET REFERENCE" not in repr(parsed)
    assert "SECRET CANDIDATE" not in repr(parsed)


def test_json_ambiguous_multiple_lists_fail_closed(tmp_path: Path):
    path = tmp_path / "rows.json"
    path.write_text(json.dumps({
        "left": [{"id": "one"}],
        "right": [{"id": "two"}],
    }), encoding="utf-8")

    parsed = parse_json_file(path)

    assert parsed.records == []
    assert parsed.reasons["record_container_not_identifiable"] == 1


def test_mapping_key_and_explicit_id_conflict_is_rejected(tmp_path: Path):
    path = tmp_path / "rows.json"
    path.write_text(json.dumps({
        "mapping-id": {"item_id": "different-id", "candidate": "code"},
    }), encoding="utf-8")

    parsed = parse_json_file(path)

    assert parsed.records == []
    assert parsed.identity_conflicts == 1


def test_trace_identity_requires_frozen_anchored_form(tmp_path: Path):
    before = tmp_path / "trajectory_abs_20260101_010203.json"
    before.touch()
    parent = tmp_path / "substr"
    parent.mkdir()
    after = parent / "agent_substr_20260101_010203_trajectory.json"
    after.touch()
    ambiguous = tmp_path / "agent_abs_20260101_010203_trajectory.json"
    ambiguous.touch()

    assert trace_identity(before) == ("abs", "filename_before_date")
    assert trace_identity(after) == ("substr", "parent_confirmed_after_date")
    assert trace_identity(ambiguous) == (None, "trace_identity_ambiguous")


def _write_family(root: Path, family: str, count: int) -> None:
    family_root = root / family
    candidates = family_root / "different_model_outputs"
    scores = family_root / "scores"
    traces = family_root / "logs_and_execution_traces"
    candidates.mkdir(parents=True)
    scores.mkdir()
    traces.mkdir()
    rows = [{
        "item_id": f"item_{index}",
        "task": f"secret task {index}",
        "reference_code": f"secret ref {index}",
        "generated_code": f"secret code {index}",
        "model": "model-a",
        "variant": "default",
    } for index in range(count)]
    (candidates / "results.json").write_text(
        json.dumps(rows), encoding="utf-8"
    )
    with (scores / "per_item_status.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["item_id", "status"])
        writer.writeheader()
        for index in range(count):
            writer.writerow({"item_id": f"item_{index}", "status": "passed"})
    (scores / "score_summary.csv").write_text("metric,value\nn,1\n")
    for index in range(count):
        (traces / f"trajectory_item_{index}_20260101_010203.json").touch()


def test_end_to_end_aggregate_gate_and_no_content_leak(tmp_path: Path):
    _write_family(tmp_path, "SQLite_Function_Code_Generation", 30)
    _write_family(tmp_path, "PostgreSQL_Function_Code_Generation", 2)
    (tmp_path / "HARNESS_AND_VARIANTS.md").write_text("metadata only")

    result = run(tmp_path)
    rendered = json.dumps(result, ensure_ascii=False)

    assert result["decision"] == "GO_WRITE_A1_PROTOCOL"
    sqlite = result["families"][0]
    assert sqlite["full_chain_count"] == 30
    assert all(sqlite["gate"].values())
    assert result["raw_content_emitted"] is False
    assert result["raw_item_ids_emitted"] is False
    assert "secret task" not in rendered
    assert "secret ref" not in rendered
    assert "secret code" not in rendered
    assert "item_0" not in rendered


def test_run_is_deterministic_for_same_tree(tmp_path: Path):
    _write_family(tmp_path, "SQLite_Function_Code_Generation", 3)
    _write_family(tmp_path, "PostgreSQL_Function_Code_Generation", 3)

    assert run(tmp_path) == run(tmp_path)
