from __future__ import annotations

import copy
import subprocess
import sys

import pytest

from scripts import select_platinum_blind_holdout as selector


SOURCE_COUNTS = {
    "multiarith": {"consensus": 164, "verified": 3, "revised": 3, "rejected": 4},
    "singleop": {"consensus": 142, "verified": 8, "revised": 0, "rejected": 9},
    "singleq": {"consensus": 87, "verified": 13, "revised": 0, "rejected": 9},
    "drop": {"consensus": 27, "verified": 3, "revised": 179, "rejected": 41},
    "hotpotqa": {"consensus": 48, "verified": 45, "revised": 88, "rejected": 69},
    "squad": {"consensus": 69, "verified": 49, "revised": 43, "rejected": 89},
    "bbh_logical_deduction_three_objects": {"consensus": 159, "verified": 41, "revised": 0, "rejected": 0},
    "bbh_navigate": {"consensus": 118, "verified": 82, "revised": 0, "rejected": 0},
    "bbh_object_counting": {"consensus": 57, "verified": 133, "revised": 0, "rejected": 10},
    "winograd_wsc": {"consensus": 77, "verified": 118, "revised": 0, "rejected": 5},
}


def fixture_rows() -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for config, counts in SOURCE_COUNTS.items():
        rows = []
        for status, count in counts.items():
            for index in range(count):
                rows.append({
                    "opaque_id": f"{config}-{status}-{index:04d}",
                    "status": status,
                    "stratum": selector.stratum(status),
                })
        result[config] = rows
    return result


def test_frozen_hashes_and_strata_receipt_are_valid() -> None:
    availability, strata = selector.verify_frozen_inputs()
    assert availability["outcomes"]["detection_source"] == "PASS_DETECTION_HOLDOUT_SOURCE_AVAILABLE"
    assert strata["outcome"] == "PASS_SELECTION_STRATA_AVAILABLE"


def test_direct_cli_entrypoint_is_importable() -> None:
    completed = subprocess.run(
        [sys.executable, str(selector.Path(selector.__file__)), "--help"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--truth-out" in completed.stdout


def test_selection_exactly_matches_all_frozen_quotas() -> None:
    selected = selector.select(fixture_rows())
    selector.validate_selection(selected)
    assert len(selected) == 897
    assert selector.selection_counts(selected) == {
        "A_arithmetic": {"rows": 442, "revised": 3, "rejected": 22, "positive": 25, "negative": 417},
        "B_text_qa": {"rows": 300, "revised": 85, "rejected": 85, "positive": 170, "negative": 130},
        "C_reasoning_coreference": {"rows": 155, "revised": 0, "rejected": 15, "positive": 15, "negative": 140},
    }


def test_vqa_and_tabfact_are_out_of_selection_scope() -> None:
    selected = selector.select(fixture_rows())
    configs = {row["config"] for row in selected}
    assert "vqa" not in configs
    assert "tab_fact" not in configs


def test_seed_changes_samples_but_not_arithmetic_census() -> None:
    rows = fixture_rows()
    baseline = selector.select(rows, seed=selector.SEED)
    mutant = selector.select(rows, seed=selector.SEED + "-mutant")
    a0 = {r["opaque_id"] for r in baseline if r["layer"] == "A_arithmetic"}
    a1 = {r["opaque_id"] for r in mutant if r["layer"] == "A_arithmetic"}
    sampled0 = {r["opaque_id"] for r in baseline if r["layer"] != "A_arithmetic"}
    sampled1 = {r["opaque_id"] for r in mutant if r["layer"] != "A_arithmetic"}
    assert a0 == a1
    assert sampled0 != sampled1


def test_public_manifest_and_truth_cover_same_ids_without_truth_leak() -> None:
    public, truth = selector.build_artifacts(selector.select(fixture_rows()))
    public_ids = {row["opaque_id"] for row in public["items"]}
    truth_ids = {row["opaque_id"] for row in truth["items"]}
    assert public_ids == truth_ids
    assert public["sealed_truth_sha256"] == selector.hashlib.sha256(selector.stable_bytes(truth)).hexdigest()
    assert public["truth_fields_emitted"] is False
    for item in public["items"]:
        assert not (selector.FORBIDDEN_PUBLIC_KEYS & set(item))


def test_selection_and_artifacts_are_byte_deterministic() -> None:
    first = selector.build_artifacts(selector.select(fixture_rows()))
    second = selector.build_artifacts(selector.select(fixture_rows()))
    assert selector.stable_bytes(first[0]) == selector.stable_bytes(second[0])
    assert selector.stable_bytes(first[1]) == selector.stable_bytes(second[1])


def test_insufficient_layer_b_cell_fails_closed() -> None:
    rows = fixture_rows()
    rows["drop"] = [
        row for row in rows["drop"]
        if row["status"] != "rejected" or int(row["opaque_id"].rsplit("-", 1)[1]) < 29
    ]
    with pytest.raises(selector.SelectionError, match="insufficient drop/rejected"):
        selector.select(rows)


def test_validation_rejects_post_selection_mutation() -> None:
    selected = selector.select(fixture_rows())
    mutant = copy.deepcopy(selected[:-1])
    with pytest.raises(selector.SelectionError, match="selection size mismatch"):
        selector.validate_selection(mutant)
