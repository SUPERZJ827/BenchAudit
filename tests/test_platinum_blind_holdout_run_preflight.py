from __future__ import annotations

import inspect
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from benchcore.cli import collect_run_metadata
from scripts import preflight_platinum_blind_holdout_run as preflight
from scripts.preflight_platinum_holdout_availability import row_identity


def source_row(item_id: str, *, strategy: str = "math") -> dict:
    return {
        "id": item_id,
        "cleaning_status": "revised",
        "platinum_prompt": "truth-bearing corrected prompt must not be read",
        "platinum_prompt_no_cot": f"Question for {item_id}",
        "platinum_target": ["corrected-secret"],
        "original_target": ["7", "7.0"],
        "platinum_parsing_strategy": strategy,
        "input": f"source identity {item_id}",
        "target": "7",
    }


def test_run_config_is_explicit_and_frozen() -> None:
    config = preflight.verify_run_config()
    assert config["model"] == "deepseek-v4-flash"
    assert config["thinking"] == "disabled"
    assert config["n_votes"] == 1
    assert config["max_api_attempts"] == 7176


def test_current_method_registry_exactly_matches_v2() -> None:
    assert preflight.current_method_registry() == preflight.EXPECTED_METHODS
    assert len(preflight.EXPECTED_METHODS) == 18
    assert "choice_encoding_contract" not in preflight.EXPECTED_METHODS


def test_evaluator_mapping_has_five_paths_and_unknown_fails() -> None:
    for strategy in (
        "math", "text", "squad", "bbh_multiple_choice", "multiple_choice"
    ):
        evaluator, contract = preflight.evaluator_for(strategy)
        assert evaluator["type"]
        assert contract["type"]
    with pytest.raises(preflight.PreflightError, match="unknown platinum parsing strategy"):
        preflight.evaluator_for("new-unfrozen-strategy")


def test_materializer_excludes_truth_columns_at_parquet_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = "multiarith"
    data_root = tmp_path / "data"
    parquet = data_root / "platinum-bench" / config / "test-00000-of-00001.parquet"
    parquet.parent.mkdir(parents=True)
    sources = [source_row("a"), source_row("b")]
    pq.write_table(pa.Table.from_pylist(sources), parquet)
    opaque = [row_identity(config, row) for row in sources]
    manifest = {
        "dataset_revision": preflight.DATASET_REVISION,
        "truth_unsealed": False,
        "truth_fields_emitted": False,
        "items": [{"config": config, "opaque_id": value, "layer": "secret"} for value in opaque],
        "counts": {"secret": {"positive": 2}},
    }
    availability = {
        "config_aggregates": [{
            "config": config,
            "artifact": {"sha256": preflight.sha256_file(parquet), "bytes": parquet.stat().st_size},
        }],
    }
    monkeypatch.setattr(preflight, "EXPECTED_ITEMS", 2)
    monkeypatch.setattr(preflight, "verify_frozen_inputs", lambda: (manifest, availability))
    rows, isolation = preflight.materialize_rows(data_root)
    assert len(rows) == 2
    assert isolation["forbidden_source_columns_read"] == []
    assert not (preflight.FORBIDDEN_SOURCE_COLUMNS & set(isolation["source_projection_by_config"][config]))
    for row in rows:
        assert set(row) == preflight.ALLOWED_ROW_KEYS
        assert row["metadata"] == {"platinum_config": config}
        serialized = json.dumps(row)
        assert "revised" not in serialized
        assert "corrected-secret" not in serialized
        assert "secret" not in serialized


def test_empty_target_and_unknown_strategy_are_reachable_fail_closed() -> None:
    with pytest.raises(preflight.PreflightError, match="empty original_target"):
        preflight.normalized_targets([])
    with pytest.raises(preflight.PreflightError):
        preflight.evaluator_for("unknown")


def test_dry_count_script_has_no_network_or_llm_client_path() -> None:
    source = inspect.getsource(preflight)
    for forbidden in ("import requests", "import urllib", "import socket", "LLMClient("):
        assert forbidden not in source


def test_worker_count_is_bound_into_run_metadata() -> None:
    metadata = collect_run_metadata(
        run_started=time.monotonic(),
        started_at=datetime.now(timezone.utc),
        primary_client=None,
        workers=8,
    )
    assert metadata["workers"] == 8
    with pytest.raises(ValueError, match="workers must be a positive integer"):
        collect_run_metadata(
            run_started=time.monotonic(),
            started_at=datetime.now(timezone.utc),
            primary_client=None,
            workers=0,
        )


def test_call_bounds_are_the_frozen_six_to_eight_per_item() -> None:
    row = {
        "id": "opaque",
        "task": "What is 2 + 2?",
        "gold": "4",
        "aliases": [],
        "choices": None,
        "output_contract": {"type": "number", "format": "single numeric answer"},
        "evaluator": {"type": "numeric_exact_match"},
        "metadata": {"platinum_config": "multiarith"},
    }
    budget = preflight.prompt_budget([row])
    assert budget["six_call_minimum_prompt_chars_per_item"]["sum"] > 0
    assert budget["eight_call_historical_max_response_proxy_prompt_chars_per_item"]["sum"] > budget["six_call_minimum_prompt_chars_per_item"]["sum"]

