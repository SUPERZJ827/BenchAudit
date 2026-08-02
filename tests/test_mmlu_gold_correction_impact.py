import json
from pathlib import Path

import numpy as np
import pytest

from scripts.analyze_mmlu_gold_correction_impact import (
    InputIntegrityError,
    Panel,
    analyze_panel,
    build_receipt,
    load_frozen_panel,
    percentile_interval,
    sha256_file,
    stable_json_bytes,
    stratified_bootstrap_indices,
    verify_sha,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _fixture(tmp_path: Path, *, n: int = 1000):
    dataset = tmp_path / "dataset.jsonl"
    pilot = tmp_path / "pilot.jsonl"
    answers = tmp_path / "answers"
    answers.mkdir()
    dataset_rows = []
    pilot_rows = []
    for i in range(n):
        gold = "A"
        verified = "B" if i == 0 else (None if i == 1 else "A")
        meta = {"subject": f"s{i % 2}"}
        if verified is not None:
            meta["verified_gold"] = verified
        dataset_rows.append({"id": f"i{i}", "gold": gold, "metadata": meta})
        pilot_rows.append({"id": f"i{i}", "gold": gold, "metadata": {"subject": f"s{i % 2}"}})
    _write_jsonl(dataset, dataset_rows)
    _write_jsonl(pilot, pilot_rows)
    for model in range(15):
        rows = []
        for i in range(n):
            pred = "B" if i == 0 and model == 0 else "A"
            rows.append(
                {
                    "id": f"i{i}",
                    "pred": pred,
                    "gold": "A",
                    "correct": pred == "A",
                    "subject": f"s{i % 2}",
                }
            )
        _write_jsonl(answers / f"m{model:02}.jsonl", rows)
    return dataset, pilot, answers


def test_changed_and_missing_verified_gold_scoring(tmp_path):
    dataset, pilot, answers = _fixture(tmp_path)
    panel, _ = load_frozen_panel(dataset, pilot, answers, enforce_frozen_hashes=False)
    assert panel.changed_gold.sum() == 1
    assert panel.old_correct[0, 0] == 0
    assert panel.new_correct[0, 0] == 1
    assert panel.old_correct[1, 0] == panel.new_correct[1, 0] == 1


def test_duplicate_id_fails_closed(tmp_path):
    dataset, pilot, answers = _fixture(tmp_path)
    with pilot.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "i0", "gold": "A", "metadata": {"subject": "s0"}}) + "\n")
    with pytest.raises(InputIntegrityError, match="duplicate id"):
        load_frozen_panel(dataset, pilot, answers, enforce_frozen_hashes=False)


def test_mismatched_id_set_fails_closed(tmp_path):
    dataset, pilot, answers = _fixture(tmp_path)
    rows = [json.loads(line) for line in (answers / "m00.jsonl").read_text().splitlines()]
    _write_jsonl(answers / "m00.jsonl", rows[:-1])
    with pytest.raises(InputIntegrityError, match="ID set mismatch"):
        load_frozen_panel(dataset, pilot, answers, enforce_frozen_hashes=False)


def test_incorrect_archived_correct_flag_fails_closed(tmp_path):
    dataset, pilot, answers = _fixture(tmp_path)
    path = answers / "m00.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[2]["correct"] = False
    _write_jsonl(path, rows)
    with pytest.raises(InputIntegrityError, match="incorrect archived correct flag"):
        load_frozen_panel(dataset, pilot, answers, enforce_frozen_hashes=False)


def test_pair_categories_include_expand_contract_and_flip():
    # Four items, three models. Original counts: A=4, B=3, C=1.
    # Corrected counts: A=2, B=4, C=1. A/B flips; B/C expands.
    panel = Panel(
        item_ids=("i0", "i1", "i2", "i3"),
        subjects=("s", "s", "s", "s"),
        models=("a", "b", "c"),
        old_correct=np.array([[1, 1, 1], [1, 1, 0], [1, 1, 0], [1, 0, 0]], dtype=np.int8),
        new_correct=np.array([[1, 1, 1], [1, 1, 0], [0, 1, 0], [0, 1, 0]], dtype=np.int8),
        changed_gold=np.array([0, 0, 1, 1], dtype=np.bool_),
    )
    result = analyze_panel(panel, replicates=20, seed=7)
    assert result["pairwise_summary"]["rank_flipped"] == 1
    assert result["pairwise_summary"]["expanded"] >= 1
    assert result["pairwise_summary"]["contracted_including_flips"] >= 1


def test_tie_order_is_deterministic_and_relative_is_none():
    values = np.array([[1, 1], [0, 0]], dtype=np.int8)
    panel = Panel(
        item_ids=("i0", "i1"),
        subjects=("s", "s"),
        models=("z", "a"),
        old_correct=values,
        new_correct=values,
        changed_gold=np.array([0, 0], dtype=np.bool_),
    )
    result = analyze_panel(panel, replicates=10, seed=3)
    assert result["ranking"]["old_order"] == ["a", "z"]
    assert result["pairs"][0]["original_tie"] is True
    assert result["pairs"][0]["relative_gap_change"] is None


def test_bootstrap_indices_are_subject_stratified_and_deterministic():
    subjects = ("a", "a", "b", "b", "b")
    first = list(stratified_bootstrap_indices(subjects, 3, 9))
    second = list(stratified_bootstrap_indices(subjects, 3, 9))
    assert all(np.array_equal(a, b) for a, b in zip(first, second))
    for indices in first:
        assert sum(subjects[i] == "a" for i in indices) == 2
        assert sum(subjects[i] == "b" for i in indices) == 3


def test_analysis_is_byte_deterministic():
    panel = Panel(
        item_ids=("i0", "i1", "i2"),
        subjects=("a", "a", "b"),
        models=("m0", "m1"),
        old_correct=np.array([[1, 0], [1, 1], [0, 0]], dtype=np.int8),
        new_correct=np.array([[1, 1], [1, 0], [0, 0]], dtype=np.int8),
        changed_gold=np.array([1, 1, 0], dtype=np.bool_),
    )
    one = stable_json_bytes(analyze_panel(panel, replicates=25, seed=11))
    two = stable_json_bytes(analyze_panel(panel, replicates=25, seed=11))
    assert one == two


def test_undefined_bootstrap_interval_is_explicit():
    assert percentile_interval(np.array([np.nan, np.nan])) == [None, None]


def test_receipt_reports_zero_api_and_unchanged_inputs():
    values = np.zeros((1000, 15), dtype=np.int8)
    panel = Panel(
        item_ids=tuple(f"i{i}" for i in range(1000)),
        subjects=("s",) * 1000,
        models=tuple(f"m{i}" for i in range(15)),
        old_correct=values,
        new_correct=values,
        changed_gold=np.zeros(1000, dtype=np.bool_),
    )
    receipt = build_receipt(
        panel=panel,
        observed_hashes={"input": "abc"},
        before={"input": "abc"},
        after={"input": "abc"},
        analysis_bytes=b"analysis",
        report_bytes=b"report",
        code_sha256="c" * 64,
        protocol_sha256="p" * 64,
        commit="deadbeef",
    )
    assert receipt["api_attempts"] == 0
    assert receipt["network_attempts"] == 0
    assert receipt["input_bytes_unchanged"] is True
    assert all(receipt["integrity_gates"].values())


def test_hash_mismatch_fails_closed(tmp_path):
    path = tmp_path / "x"
    path.write_bytes(b"content")
    with pytest.raises(InputIntegrityError, match="SHA-256 mismatch"):
        verify_sha(path, "0" * 64)
    assert sha256_file(path) != "0" * 64
