from __future__ import annotations

from benchcore.llm_auditor import (
    AnswerMultiplicityLLMAuditor,
    GoldLLMAuditor,
    OptionSetLLMAuditor,
    QuestionClarityLLMAuditor,
)
from benchcore.llm_client import LLMClient, LLMConfig
from benchcore.schema import BenchmarkItem


def client() -> LLMClient:
    return LLMClient(LLMConfig(model="x", base_url="https://example.invalid", dry_run=True))


def structured_item() -> BenchmarkItem:
    # A function-calling item: a task, but no scalar gold, aliases or choices.
    return BenchmarkItem(item_id="i", raw={"reference_solution": {"Tool": {"a": 1}}},
                         task="call the tool", context={})


def test_gold_auditor_declares_itself_inapplicable_without_a_scalar_gold() -> None:
    # The gate used to live only in check(), which returned no findings and let
    # the ledger record "examined and found nothing".
    verdict = GoldLLMAuditor(client()).audit_eligibility(structured_item())
    assert not verdict.eligible
    assert "gold" in verdict.reason


def test_answer_multiplicity_needs_at_least_two_declared_answers() -> None:
    assert not AnswerMultiplicityLLMAuditor(client()).audit_eligibility(structured_item()).eligible
    both = BenchmarkItem(item_id="i", raw={}, task="q", gold="4", aliases=["four"], context={})
    assert AnswerMultiplicityLLMAuditor(client()).audit_eligibility(both).eligible


def test_option_set_needs_a_choice_set() -> None:
    assert not OptionSetLLMAuditor(client()).audit_eligibility(structured_item()).eligible
    mcq = BenchmarkItem(item_id="i", raw={}, task="q", choices=["a", "b"], context={})
    assert OptionSetLLMAuditor(client()).audit_eligibility(mcq).eligible


def test_the_shared_precondition_is_the_task_text() -> None:
    assert QuestionClarityLLMAuditor(client()).audit_eligibility(structured_item()).eligible
    blank = BenchmarkItem(item_id="i", raw={}, task="", context={})
    assert not QuestionClarityLLMAuditor(client()).audit_eligibility(blank).eligible


def test_a_scalar_gold_item_remains_eligible_for_the_gold_auditor() -> None:
    scalar = BenchmarkItem(item_id="i", raw={}, task="q", gold="42", context={})
    assert GoldLLMAuditor(client()).audit_eligibility(scalar).eligible
