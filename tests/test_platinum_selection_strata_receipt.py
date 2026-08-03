from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import derive_platinum_selection_strata_receipt as strata


@pytest.fixture
def source() -> dict:
    return json.loads(strata.INPUT.read_text())


def test_real_aggregate_supports_frozen_quotas(source: dict) -> None:
    result = strata.derive(source)
    assert result["outcome"] == "PASS_SELECTION_STRATA_AVAILABLE"
    assert result["layer_status_counts"]["A_arithmetic"]["revised"] == 3
    assert result["layer_status_counts"]["A_arithmetic"]["rejected"] == 22
    assert result["layer_status_counts"]["B_text_qa"]["revised"] == 310
    assert result["layer_status_counts"]["B_text_qa"]["rejected"] == 199
    assert all(row["passed"] for row in result["layer_b_quota_gates"].values())


def test_vqa_is_positive_only(source: dict) -> None:
    counts = strata.derive(source)["layer_status_counts"]["X_out_of_modality"]
    assert (counts["positive"], counts["negative"]) == (242, 0)


def test_insufficient_revised_quota_fails(source: dict) -> None:
    mutant = copy.deepcopy(source)
    row = next(row for row in mutant["config_aggregates"] if row["config"] == "drop")
    moved = row["status_counts"]["revised"] - 39
    row["status_counts"]["revised"] = 39
    row["status_counts"]["consensus"] += moved
    result = strata.derive(mutant)
    assert result["outcome"] == "INSUFFICIENT_REVISED_QUOTA"


def test_unknown_or_duplicate_config_fails(source: dict) -> None:
    mutant = copy.deepcopy(source)
    mutant["config_aggregates"].append(copy.deepcopy(mutant["config_aggregates"][0]))
    with pytest.raises(strata.StrataError, match="CONFIG_SCOPE_MISMATCH"):
        strata.derive(mutant)


def test_stable_output_contains_no_item_mapping(tmp_path: Path) -> None:
    strata.run(strata.INPUT, tmp_path)
    result = json.loads((tmp_path / "receipt.json").read_text())
    assert result["item_ids_emitted"] is False
    assert result["item_label_mapping_emitted"] is False
    assert result["dataset_files_opened"] == 0
