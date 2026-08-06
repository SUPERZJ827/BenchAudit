"""A wording difference ends the audit of an item before the cascade runs.

The adversarial cascade exists to catch a solver that answered wrongly, not to
tell "2 million" from "2,000,000". Normalization settles punctuation and case
and nothing else, so those are unequal strings for one number, and of 66
measured items shipping several answers, 55 ship wordings of one answer.

Settling that with one question keeps the cascade for the disagreements it was
built for, and keeps its fan-out -- the main source of run-to-run instability
-- off the majority case.
"""

from __future__ import annotations

from benchcore import decision_policy as dp
from benchcore.llm_auditor import blind_answer_is_a_wording_difference
from benchcore.schema import BenchmarkItem


class _Client:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def chat_json(self, system, user):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _item(gold="2 million", aliases=()):
    return BenchmarkItem(
        item_id="x", raw={}, task="how many people?", gold=gold, aliases=list(aliases)
    )


BLIND = {"solution_status": "solved", "valid_answers": ["2,000,000"]}


def test_a_confident_same_answer_ends_the_audit():
    verdict = {"relation": "same_answer", "confidence": 0.9}
    assert blind_answer_is_a_wording_difference(_Client(verdict), _item(), BLIND, {})


def test_a_hesitant_same_answer_does_not():
    """Below the declared threshold the cascade runs as before."""
    weak = {"relation": "same_answer",
            "confidence": dp.ANSWER_EQUIVALENCE_MIN_CONFIDENCE - 0.01}
    assert not blind_answer_is_a_wording_difference(_Client(weak), _item(), BLIND, {})


def test_a_different_answer_does_not_end_the_audit():
    verdict = {"relation": "different_answer", "confidence": 0.99}
    assert not blind_answer_is_a_wording_difference(_Client(verdict), _item(), BLIND, {})


def test_uncertainty_does_not_end_the_audit():
    verdict = {"relation": "uncertain", "confidence": 0.99}
    assert not blind_answer_is_a_wording_difference(_Client(verdict), _item(), BLIND, {})


def test_an_invented_relation_does_not_end_the_audit():
    verdict = {"relation": "obviously_fine", "confidence": 0.99}
    assert not blind_answer_is_a_wording_difference(_Client(verdict), _item(), BLIND, {})


def test_a_provider_failure_does_not_end_the_audit():
    """Failing to ask must not be read as having asked and been reassured."""
    client = _Client(RuntimeError("boom"))
    observations: dict = {}
    assert not blind_answer_is_a_wording_difference(client, _item(), BLIND, observations)
    assert "audit_failure" in observations["llm_answer_equivalence"]


def test_nothing_to_compare_costs_no_call():
    client = _Client({"relation": "same_answer", "confidence": 0.99})
    empty = {"solution_status": "solved", "valid_answers": []}
    assert not blind_answer_is_a_wording_difference(client, _item(), empty, {})
    assert client.calls == 0


def test_the_verdict_is_recorded_either_way():
    observations: dict = {}
    verdict = {"relation": "same_answer", "confidence": 0.9}
    blind_answer_is_a_wording_difference(_Client(verdict), _item(), BLIND, observations)
    assert observations["llm_answer_equivalence"] == verdict


def test_the_threshold_is_part_of_the_policy_hash():
    base = dp.decision_policy()
    assert base["answer_equivalence_min_confidence"] == dp.ANSWER_EQUIVALENCE_MIN_CONFIDENCE
