from __future__ import annotations

import inspect
import json

import pytest

from scripts import analyze_mmlu_response_pattern_baseline as baseline


def source_row(item_id: str, label: str = "ok", *, subject: str = "fixture") -> dict:
    return {
        "id": item_id,
        "gold": "A",
        "metadata": {"error_type": label, "subject": subject},
    }


def matrices_for(item_id: str, predictions: list[object]) -> dict:
    assert len(predictions) == 15
    return {
        f"model-{index:02d}.jsonl": {item_id: {"pred": prediction}}
        for index, prediction in enumerate(predictions)
    }


def test_eight_same_non_gold_votes_trigger_primary() -> None:
    source = {"item": source_row("item")}
    matrices = matrices_for("item", ["B"] * 8 + ["A"] * 7)
    score = baseline.score_items(source, matrices)[0]
    assert score["max_same_non_gold_count"] == 8
    assert score["maximizing_non_gold_labels"] == ["B"]


def test_votes_for_different_alternatives_are_not_summed() -> None:
    source = {"item": source_row("item")}
    matrices = matrices_for("item", ["B"] * 4 + ["C"] * 4 + ["D"] * 3 + ["A"] * 4)
    score = baseline.score_items(source, matrices)[0]
    assert score["max_same_non_gold_count"] == 4
    assert score["maximizing_non_gold_labels"] == ["B", "C"]


def test_invalid_predictions_abstain_and_gold_votes_do_not_score() -> None:
    source = {"item": source_row("item")}
    matrices = matrices_for(
        "item", [None, "None", "", " E ", 4, "A", "a", " A "] + ["B"] * 7
    )
    score = baseline.score_items(source, matrices)[0]
    assert score["abstention_count"] == 5
    assert score["gold_vote_count"] == 3
    assert score["max_same_non_gold_count"] == 7


def test_endpoint_definitions_keep_expert_as_abstention_in_strict_endpoint() -> None:
    labels = [
        "ok", "expert", "wrong_groundtruth", "bad_question_clarity",
        "multiple_correct_answers", "no_correct_answer", "bad_options_clarity",
    ]
    source = {f"i{index}": source_row(f"i{index}", label) for index, label in enumerate(labels)}
    endpoints = baseline.endpoint_sets(source)
    assert len(endpoints["legacy_non_ok_including_expert"]["positive"]) == 6
    assert len(endpoints["strict_explicit_defect"]["positive"]) == 5
    assert endpoints["strict_explicit_defect"]["excluded"] == {"i1"}
    assert len(endpoints["gold_related"]["positive"]) == 3
    assert endpoints["wrong_groundtruth_only"]["positive"] == {"i2"}


def test_classification_metrics_and_undefined_ratios() -> None:
    endpoint = {"positive": {"p"}, "negative": {"n"}, "excluded": set()}
    values = baseline.classification_metrics({"p"}, endpoint)
    assert (values["tp"], values["fp"], values["fn"], values["tn"]) == (1, 0, 0, 1)
    assert values["precision"] == values["recall"] == values["f1"] == 1.0
    no_positive = {"positive": set(), "negative": {"n"}, "excluded": set()}
    empty = baseline.classification_metrics(set(), no_positive)
    assert empty["precision"] is None
    assert empty["recall"] is None
    assert empty["f1"] is None


def test_oracle_threshold_tie_breaks_toward_larger_k() -> None:
    rows = {
        "1": {"f1": 0.5},
        "2": {"f1": 0.7},
        "3": {"f1": 0.7},
        "4": {"f1": None},
    }
    assert baseline.oracle_threshold(rows) == 3


def test_synthetic_scoring_is_byte_deterministic() -> None:
    source = {"item": source_row("item")}
    matrices = matrices_for("item", ["B"] * 8 + ["A"] * 7)
    first = baseline.score_items(source, matrices)
    second = baseline.score_items(source, matrices)
    assert baseline.stable_bytes(first) == baseline.stable_bytes(second)


def test_scanner_has_no_network_llm_or_production_import_path() -> None:
    source = inspect.getsource(baseline)
    for fragment in (
        "import requests", "import urllib", "import socket", "llm_client",
        "LLMClient(", "os.environ", "from benchcore", "import benchcore",
    ):
        assert fragment not in source


@pytest.mark.skipif(
    not baseline.SOURCE.is_file() or not baseline.AUDIT_REPORT.is_file(),
    reason="frozen source/report artifacts are external to Git",
)
def test_frozen_bindings_and_benchcore_legacy_confusion_reproduce() -> None:
    source, matrices, report = baseline.verify_bindings()
    assert len(source) == 1000
    assert len(matrices) == 15
    endpoint = baseline.endpoint_sets(source)["legacy_non_ok_including_expert"]
    metrics = baseline.classification_metrics(
        baseline.bench_candidates(report, set(source)), endpoint
    )
    assert {key: metrics[key] for key in ("tp", "fp", "fn", "tn")} == {
        "tp": 206, "fp": 86, "fn": 164, "tn": 544,
    }


def test_committed_outputs_are_bound_when_present() -> None:
    output = baseline.ROOT / "reports/mmlu_response_pattern_baseline_20260803"
    receipt_path = output / "receipt.json"
    if not receipt_path.is_file():
        pytest.skip("response-pattern outputs have not been published yet")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["outcome"] == "BASELINE_COMPLETE"
    assert baseline.sha256_file(output / "scores.jsonl") == receipt["outputs"]["scores_sha256"]
    assert baseline.sha256_file(output / "metrics.json") == receipt["outputs"]["metrics_sha256"]
    assert baseline.sha256_file(output / "REPORT.md") == receipt["outputs"]["report_sha256"]
    assert receipt["execution"]["incremental_api_attempts"] == 0
    assert receipt["execution"]["production_activation"] is False


def test_post_result_interpretation_is_hash_bound_and_metric_exact() -> None:
    output = baseline.ROOT / "reports/mmlu_response_pattern_baseline_20260803"
    interpretation_path = output / "interpretation.json"
    if not interpretation_path.is_file():
        pytest.skip("response-pattern interpretation has not been published yet")
    interpretation = json.loads(interpretation_path.read_text(encoding="utf-8"))
    metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    bound = interpretation["bound_outputs"]
    assert baseline.sha256_file(output / "scores.jsonl") == bound["scores_sha256"]
    assert baseline.sha256_file(output / "metrics.json") == bound["metrics_sha256"]
    assert baseline.sha256_file(output / "REPORT.md") == bound["report_sha256"]
    assert baseline.sha256_file(output / "receipt.json") == bound["stable_receipt_sha256"]

    strict_bench = metrics["benchcore"]["endpoints"]["strict_explicit_defect"]
    strict_response = metrics["response_pattern"]["endpoints"]["strict_explicit_defect"]
    assert interpretation["broad_strict_endpoint"]["benchcore"]["f1"] == strict_bench["f1"]
    assert interpretation["broad_strict_endpoint"]["response_pattern_k8"]["f1"] == (
        strict_response["thresholds"]["8"]["f1"]
    )
    assert interpretation["broad_strict_endpoint"]["response_pattern_post_hoc_oracle"]["f1"] == (
        strict_response["post_hoc_oracle_upper_bound"]["metrics"]["f1"]
    )
    assert interpretation["claim_boundary"]["historical_response_generation_cost_zero"] is False
