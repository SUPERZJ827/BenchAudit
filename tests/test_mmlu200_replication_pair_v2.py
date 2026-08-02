from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/run_mmlu200_replication_pair_v2_20260802.py"
SPEC = importlib.util.spec_from_file_location("mmlu200_pair_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_v2_method_set_is_exact_complete_18() -> None:
    assert len(MODULE.EXPECTED_METHODS) == 18
    assert MODULE.EXPECTED_METHODS[12:15] == [
        "llm_gold_audit",
        "llm_question_clarity",
        "llm_option_set",
    ]
    assert "llm_presentation_integrity" not in MODULE.EXPECTED_METHODS
    assert "llm_quantity_consistency" not in MODULE.EXPECTED_METHODS
    assert "llm_event_state" not in MODULE.EXPECTED_METHODS


def test_v2_audit_command_freezes_auditors_workers_and_cache(tmp_path: Path) -> None:
    command = MODULE.audit_command(
        data=tmp_path / "data.jsonl",
        manifest=tmp_path / "manifest.json",
        config=tmp_path / "config.json",
        cache=tmp_path / "cache.jsonl",
        report_path=tmp_path / "report.json",
        report_md=tmp_path / "report.md",
    )
    auditors_index = command.index("--llm-auditors")
    workers_index = command.index("--workers")
    cache_index = command.index("--llm-cache")
    assert command[auditors_index + 1] == "gold,question,option"
    assert command[workers_index + 1] == "8"
    assert command[cache_index + 1] == str(tmp_path / "cache.jsonl")
    assert "--allow-remote-data-egress" in command


def test_v2_overrides_v1_validation_limits_without_changing_source() -> None:
    assert MODULE.BASE.MAX_API_ATTEMPTS == 1600
    assert MODULE.BASE.MAX_RUN_TOKENS == 4_000_000
    assert MODULE.BASE.EXPECTED_METHODS == MODULE.EXPECTED_METHODS


def test_v2_compare_command_freezes_truth_definition(tmp_path: Path) -> None:
    command = MODULE.compare_command(
        data=tmp_path / "data.jsonl",
        manifest=tmp_path / "manifest.json",
        report_path=tmp_path / "report.json",
        comparison_path=tmp_path / "comparison.json",
        comparison_md=tmp_path / "comparison.md",
    )
    truth_index = command.index("--truth-field")
    clean_index = command.index("--clean-value")
    assert command[truth_index + 1] == "metadata.error_type"
    assert command[clean_index + 1] == "ok"
