from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchcore.cli import main
from benchcore.input_domain import (
    AUDIT_INPUT_DOMAIN_SCHEMA_VERSION,
    UnsupportedAuditInput,
    enforce_audit_input_domain,
    result_export_refusal,
)


def _result_row(**updates):
    row = {
        "questionId": "q1",
        "question": "What is shown?",
        "answer": ["blue"],
        "prediction": ["blue"],
        "judge": True,
    }
    row.update(updates)
    return row


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_exact_result_export_shape_has_stable_machine_diagnostic():
    refusal = result_export_refusal([_result_row(), _result_row(questionId="q2")])

    assert refusal is not None
    assert refusal.schema_version == AUDIT_INPUT_DOMAIN_SCHEMA_VERSION
    assert refusal.rows_checked == 2
    assert refusal.required_result_markers == ("judge", "prediction")
    assert "output_contract" in refusal.absent_contract_carriers


@pytest.mark.parametrize(
    "carrier",
    [
        "output_contract",
        "output_format",
        "choices",
        "options",
        "evaluator",
        "rubric",
        "rubrics",
    ],
)
def test_any_explicit_contract_carrier_prevents_refusal_even_when_empty(carrier):
    rows = [_result_row(**{carrier: None}), _result_row()]

    assert result_export_refusal(rows) is None


@pytest.mark.parametrize("missing", ["prediction", "judge"])
def test_both_result_markers_are_required_on_every_row(missing):
    incomplete = _result_row(questionId="q2")
    incomplete.pop(missing)

    assert result_export_refusal([_result_row(), incomplete]) is None


def test_markers_nested_in_metadata_do_not_trigger_refusal():
    row = {
        "question": "What is shown?",
        "answer": "blue",
        "metadata": {"prediction": "blue", "judge": True},
    }

    assert result_export_refusal([row]) is None


def test_key_comparison_is_case_insensitive_but_top_level_only():
    row = _result_row()
    row["Prediction"] = row.pop("prediction")
    row["Judge"] = row.pop("judge")

    refusal = result_export_refusal([row])

    assert refusal is not None


def test_empty_input_is_not_classified_as_a_result_export():
    assert result_export_refusal([]) is None


def test_cli_refuses_before_report_creation(tmp_path: Path):
    source = tmp_path / "results.jsonl"
    output = tmp_path / "audit.json"
    _write_jsonl(source, [_result_row(), _result_row(questionId="q2")])

    with pytest.raises(UnsupportedAuditInput, match="result-export-like schema"):
        main(["audit", str(source), "--out", str(output), "--progress-every", "0"])

    assert not output.exists()


def test_cli_does_not_overwrite_an_existing_report_on_refusal(tmp_path: Path):
    source = tmp_path / "results.jsonl"
    output = tmp_path / "audit.json"
    _write_jsonl(source, [_result_row()])
    output.write_bytes(b"pre-existing-report\n")

    with pytest.raises(UnsupportedAuditInput, match="No audit report was produced"):
        main(["audit", str(source), "--out", str(output), "--progress-every", "0"])

    assert output.read_bytes() == b"pre-existing-report\n"


def test_domain_refusal_precedes_execution_backend_validation(tmp_path: Path):
    source = tmp_path / "results.jsonl"
    output = tmp_path / "audit.json"
    _write_jsonl(source, [_result_row()])

    with pytest.raises(UnsupportedAuditInput, match="result-export-like schema"):
        main([
            "audit",
            str(source),
            "--execution-container-image",
            "not-a-digest",
            "--out",
            str(output),
        ])

    assert not output.exists()


def test_domain_refusal_precedes_profile_and_llm_configuration(tmp_path: Path):
    source = tmp_path / "results.jsonl"
    output = tmp_path / "audit.json"
    _write_jsonl(source, [_result_row()])

    with pytest.raises(UnsupportedAuditInput, match="result-export analysis workflow"):
        main([
            "audit",
            str(source),
            "--llm-config",
            str(tmp_path / "missing-config.json"),
            "--out",
            str(output),
        ])

    assert not output.exists()


def test_benchmark_with_prediction_and_judge_and_contract_is_audited(tmp_path: Path):
    source = tmp_path / "benchmark.jsonl"
    output = tmp_path / "audit.json"
    _write_jsonl(source, [_result_row(evaluator={"type": "exact_match"})])

    assert main([
        "audit",
        str(source),
        "--basic-only",
        "--no-benchmark-profile",
        "--out",
        str(output),
        "--progress-every",
        "0",
    ]) == 0
    assert output.exists()


def test_exception_exposes_the_frozen_diagnostic():
    with pytest.raises(UnsupportedAuditInput) as caught:
        enforce_audit_input_domain([_result_row()])

    assert caught.value.refusal.schema_version == AUDIT_INPUT_DOMAIN_SCHEMA_VERSION
    assert caught.value.refusal.rows_checked == 1
