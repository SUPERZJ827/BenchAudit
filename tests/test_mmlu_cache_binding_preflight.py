import json
from pathlib import Path

import pytest

from scripts.preflight_mmlu_cache_binding import (
    PreflightError,
    cache_keys,
    report_cache_path,
    upper_ids_from_mutation_manifest,
    upper_ids_from_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_cache_keys_require_unique_digest_rows(tmp_path):
    path = tmp_path / "cache.jsonl"
    _write_jsonl(path, [{"key": "a" * 64, "response": {}}])
    assert cache_keys(path) == {"a" * 64}
    _write_jsonl(
        path,
        [
            {"key": "a" * 64, "response": {}},
            {"key": "a" * 64, "response": {}},
        ],
    )
    with pytest.raises(PreflightError, match="duplicate cache key"):
        cache_keys(path)


def test_cache_row_shape_and_key_length_fail_closed(tmp_path):
    path = tmp_path / "cache.jsonl"
    _write_jsonl(path, [{"key": "short", "response": {}}])
    with pytest.raises(PreflightError, match="invalid cache key"):
        cache_keys(path)
    _write_jsonl(path, [{"key": "a" * 64, "response": {}, "prompt": "leak"}])
    with pytest.raises(PreflightError, match="row shape"):
        cache_keys(path)


def test_report_cache_path_is_mandatory():
    report = {"run_metadata": {"llm": {"cache_path": "reports/x.jsonl"}}}
    assert report_cache_path(report) == "reports/x.jsonl"
    with pytest.raises(PreflightError, match="does not bind"):
        report_cache_path({})


def test_coverage_ledger_binds_exact_audited_set():
    report = {
        "coverage_ledger": [
            {"item_id": "a", "checker": "one"},
            {"item_id": "a", "checker": "two"},
            {"item_id": "b", "checker": "one"},
        ],
        "source_identity": {"audited_rows": 2},
    }
    assert upper_ids_from_report(report) == {"a", "b"}
    report["source_identity"]["audited_rows"] = 3
    with pytest.raises(PreflightError, match="does not match"):
        upper_ids_from_report(report)


def test_mutation_manifest_binds_report_input_to_source_ids(tmp_path):
    root = tmp_path
    input_path = root / "mutated.jsonl"
    _write_jsonl(input_path, [{"id": "a_mut"}, {"id": "b_mut"}])
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "mutations": [
                    {"source_item_id": "a", "mutated_item_id": "a_mut"},
                    {"source_item_id": "b", "mutated_item_id": "b_mut"},
                ]
            }
        )
    )
    report = {"input_path": "mutated.jsonl"}
    assert upper_ids_from_mutation_manifest(manifest_path, report, root) == {"a", "b"}
    _write_jsonl(input_path, [{"id": "a_mut"}])
    with pytest.raises(PreflightError, match="does not bind"):
        upper_ids_from_mutation_manifest(manifest_path, report, root)
