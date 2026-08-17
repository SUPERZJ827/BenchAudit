from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load_script("prepare_fantastic_bugs_gsm8k_997.py")
score = load_script("score_fantastic_bugs_gsm8k_997.py")
residual = load_script("analyze_fantastic_bugs_residual_semantic.py")


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("Reasoning. The answer is 1,250.", "1250"),
        ("Reasoning. The final answer is -3.5", "-3.5"),
        ("Reasoning. The answer is 25%.", "25%"),
    ],
)
def test_extract_gold_accepts_only_final_numeric_scalar(reference: str, expected: str) -> None:
    assert prepare.extract_gold(reference) == expected


@pytest.mark.parametrize(
    "reference",
    [
        "The answer is forty two.",
        "The answer is 42 apples.",
        "No final answer sentence",
    ],
)
def test_extract_gold_rejects_non_scalar_or_missing_answer(reference: str) -> None:
    with pytest.raises(ValueError):
        prepare.extract_gold(reference)


def test_stable_item_id_is_content_bound() -> None:
    first = prepare.stable_item_id("How many?")
    assert first == prepare.stable_item_id("How many?")
    assert first != prepare.stable_item_id("How many ?")
    assert first.startswith("fantastic-bugs-gsm-")


def test_candidate_metrics_use_invalid_items_as_positives() -> None:
    result = score.metrics({"a", "b", "c"}, {"b", "c", "d", "e"})
    assert result["candidates"] == 3
    assert result["tp"] == 2
    assert result["fp"] == 1
    assert result["fn"] == 2
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall_sensitivity"] == pytest.approx(1 / 2)


def test_precision_at_50_is_not_imputed_for_short_candidate_list() -> None:
    result = score.ranked_metrics(["a", "b"], {"a"}, k=50)
    assert result == {
        "identifiable": False,
        "reason": "only 2 scored candidates, fewer than k=50",
    }


def test_average_percentiles_use_average_rank_for_ties() -> None:
    assert score.average_percentiles({"a": 1.0, "b": 1.0, "c": 3.0}) == {
        "a": 0.25,
        "b": 0.25,
        "c": 1.0,
    }


def test_residual_summary_scores_only_the_locked_ranked_candidates() -> None:
    ranking = [f"item-{index}" for index in range(50)]
    truth = {"item-0", "item-49", "not-ranked"}
    result = residual.summarize_residual(ranking, truth)
    assert result["semantic_candidates"] == 50
    assert result["tp"] == 2
    assert result["fp"] == 48
    assert result["fn"] == 1
    assert result["top50_tp"] == 2
    assert result["precision_at_50"] == pytest.approx(0.04)
