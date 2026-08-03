from __future__ import annotations

import inspect

import pytest

from scripts import verify_mmlu_redux_ok_mechanical as verifier


def row(*, choices=None, gold="A", aliases=None, evaluator=None):
    return {
        "choices": choices,
        "gold": gold,
        "aliases": [] if aliases is None else aliases,
        "evaluator": {"type": "multiple_choice"} if evaluator is None else evaluator,
    }


def test_duplicate_rule_has_all_three_reachable_statuses() -> None:
    assert verifier.duplicate_rule(
        row(choices=["same", "Same", "other"]), {"multiple_correct_answers"}
    )["status"] == "mechanically_confirmed"
    assert verifier.duplicate_rule(
        row(choices=["one", "two"]), {"multiple_correct_answers"}
    )["status"] == "mechanically_not_triggered"
    assert verifier.duplicate_rule(
        row(choices=["same", "same"]), {"wrong_gold_answer"}
    )["status"] == "not_applicable"


def test_duplicate_rule_does_not_treat_near_match_as_exact() -> None:
    result = verifier.duplicate_rule(
        row(choices=["New York", "New York City"]), {"duplicate_choices"}
    )
    assert result["status"] == "mechanically_not_triggered"


def test_gold_domain_rule_has_all_three_reachable_statuses() -> None:
    assert verifier.gold_domain_rule(
        row(choices=["x", "y"], gold="C"), {"wrong_gold_answer"}
    )["status"] == "mechanically_confirmed"
    assert verifier.gold_domain_rule(
        row(choices=["x", "y"], gold="A"), {"wrong_gold_answer"}
    )["status"] == "mechanically_not_triggered"
    assert verifier.gold_domain_rule(
        row(choices=["x", "y"], gold="C"), {"ambiguous_goal"}
    )["status"] == "not_applicable"


def test_gold_text_and_alias_can_map_to_choice_domain() -> None:
    assert verifier.gold_domain_rule(
        row(choices=["alpha", "beta"], gold="beta"), {"no_correct_answer"}
    )["status"] == "mechanically_not_triggered"
    assert verifier.gold_domain_rule(
        row(choices=["alpha", "beta"], gold="unknown", aliases=["B"]),
        {"no_correct_answer"},
    )["status"] == "mechanically_not_triggered"


def test_gold_domain_unknown_contract_abstains() -> None:
    result = verifier.gold_domain_rule(
        row(choices=["x", "y"], gold="C", evaluator={"type": "free_text"}),
        {"wrong_gold_answer"},
    )
    assert result == {"status": "not_applicable", "reason": "contract_not_explicit_single_choice"}


@pytest.mark.skipif(not verifier.SOURCE.is_file(), reason="frozen dataset artifact is external to Git")
def test_frozen_population_and_four_pool_counts_recompute() -> None:
    rows, report = verifier.load_frozen()
    result = verifier.pools(rows, report)
    assert {name: len(values) for name, values in result.items()} == {
        "d": 86,
        "p_agree": 196,
        "p_missed": 142,
        "n_agree": 544,
        "expert_review": 10,
        "expert_no_review": 22,
    }
    assert not (result["expert_review"] & result["p_agree"])
    assert not (result["expert_no_review"] & result["p_missed"])


@pytest.mark.skipif(not verifier.SOURCE.is_file(), reason="frozen dataset artifact is external to Git")
def test_all_86_items_run_both_rules_and_only_confirmed_route_out() -> None:
    rows, report = verifier.load_frozen()
    result = verifier.verify_all(rows, report)
    assert result["items_inspected"] == 86
    assert result["all_d_items_ran_both_rules"] is True
    assert len(result["item_results"]) == 86
    for item in result["item_results"]:
        assert set(item["rules"]) == {"M-DUP-V1", "M-GOLD-DOMAIN-V1"}
        if item["route"] == "mechanical_confirmed":
            assert item["mechanically_confirmed_rules"]
        else:
            assert item["route"] == "blind_adjudication"
            assert not item["mechanically_confirmed_rules"]


def test_verifier_has_no_network_or_llm_path() -> None:
    source = inspect.getsource(verifier)
    for forbidden in ("import requests", "import urllib", "import socket", "LLMClient("):
        assert forbidden not in source
