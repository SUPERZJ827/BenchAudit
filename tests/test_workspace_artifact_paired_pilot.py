from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_workspace_artifact_paired_pilot.py"
SPEC = importlib.util.spec_from_file_location("workspace_artifact_paired_pilot", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
pilot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pilot
SPEC.loader.exec_module(pilot)


def _row(index: int, passed: bool = True) -> dict[str, object]:
    return {
        "index": index,
        "passed": passed,
        "confidence": 0.9,
        "evidence": f"evidence-{index}",
    }


def test_load_reusable_judge_result_rejects_error_and_accepts_complete_result(
    tmp_path: Path,
) -> None:
    unit = tmp_path / "unit"
    result_dir = unit / "rubrics_judge--~anthropic"
    result_dir.mkdir(parents=True)
    (unit / "metadata.json").write_text(
        json.dumps({"rubrics": ["first", "second"]}), encoding="utf-8"
    )
    result_path = result_dir / "claude-sonnet-latest.json"
    result_path.write_text(json.dumps({
        "judge": {
            "model": "~anthropic/claude-sonnet-latest",
            "error": "HTTP 402",
        },
        "summary": {"total": 2, "passed": 0, "failed": 2},
        "rubrics": [],
    }), encoding="utf-8")
    record = {
        "task_id": 7,
        "condition": "baseline",
        "unit_id": "opaque",
        "unit_path": str(unit),
    }
    assert pilot._load_reusable_judge_result(
        record, judge_model="~anthropic/claude-sonnet-latest"
    ) is None

    result_path.write_text(json.dumps({
        "judge": {
            "model": "~anthropic/claude-sonnet-latest",
            "error": None,
            "usage": {"total_tokens": 12},
        },
        "summary": {"total": 2, "passed": 1, "failed": 1},
        "rubrics": [
            {"index": 0, "passed": True},
            {"index": 1, "passed": False},
        ],
    }), encoding="utf-8")
    reused = pilot._load_reusable_judge_result(
        record, judge_model="~anthropic/claude-sonnet-latest"
    )
    assert reused is not None
    assert reused["valid"] is True
    assert reused["reused"] is True
    assert reused["summary"]["passed"] == 1


def test_normalize_rubric_rows_accepts_equivalent_keyed_layouts() -> None:
    nested = {"rubrics": {"1": _row(1, False), "0": _row(0)}}
    top_level = {"0": {"passed": True, "confidence": 0.8, "evidence": "x"}}

    assert pilot._normalize_rubric_rows(nested) == [_row(1, False), _row(0)]
    assert pilot._normalize_rubric_rows(top_level) == [
        {"index": 0, "passed": True, "confidence": 0.8, "evidence": "x"}
    ]


def test_pair_rows_requires_complete_original_indices() -> None:
    valid = {"A": {"rubrics": [_row(1), _row(0)]}}
    missing = {"A": {"rubrics": [_row(0)]}}

    assert [row["index"] for row in pilot._pair_rows(valid, "A", 2)] == [0, 1]
    assert pilot._pair_rows(missing, "A", 2) is None


def test_recover_final_message_output_is_explicit_contained_and_type_compatible(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    generated = workspace / "different_name.pdf"
    generated.write_bytes(b"%PDF-1.4\n")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4\n")
    message = tmp_path / "last.txt"
    message.write_text(str(generated) + "\n" + str(outside) + "\n", encoding="utf-8")

    recovered = pilot._recover_final_message_outputs(
        workspace,
        message,
        ["expected_name.pdf", "expected.xlsx"],
        {"expected_name.pdf": [], "expected.xlsx": []},
    )

    assert recovered["expected_name.pdf"] == ["different_name.pdf"]
    assert recovered["expected.xlsx"] == []


def test_recover_final_message_does_not_guess_ambiguous_compatible_files(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first = workspace / "one.pdf"
    second = workspace / "two.pdf"
    first.write_bytes(b"%PDF-1.4\n")
    second.write_bytes(b"%PDF-1.4\n")
    message = tmp_path / "last.txt"
    message.write_text(f"{first}\n{second}\n", encoding="utf-8")

    recovered = pilot._recover_final_message_outputs(
        workspace, message, ["expected.pdf"], {"expected.pdf": []},
    )

    assert recovered["expected.pdf"] == []


def test_score_rejects_failed_or_malformed_units() -> None:
    assert pilot._score({"valid": False, "summary": {"passed": 1, "total": 2}}) is None
    assert pilot._score({"valid": True, "summary": {"passed": 1, "total": 0}}) is None
    assert pilot._score({"valid": True, "summary": {"passed": 1, "total": 2}}) == 0.5


def test_protocol_hash_excludes_its_own_field() -> None:
    payload = {"task_ids": [2, 3], "protocol_sha256": ""}
    expected = pilot._canonical_sha256({"task_ids": [2, 3]})
    payload["protocol_sha256"] = expected

    assert payload["protocol_sha256"] == pilot._canonical_sha256(
        {key: value for key, value in payload.items() if key != "protocol_sha256"}
    )
