"""The clarity auditor emits a ranked list; scoring uses only the primary.

A single mutually exclusive status structurally suppressed every defect but
one: a task that was both ambiguous and missing its context could report only
one of them. A ranked list removes that competition, but scoring on "any label
hits" would inflate recall with the number of labels emitted, so the primary
(top-confidence) label is what counts.
"""

from __future__ import annotations

from benchcore import decision_policy as dp
from benchcore.llm_auditor import clarity_defect_labels, primary_clarity_defect

AMBIG = "answer_changing_ambiguity"
CONTEXT = "missing_context"
CONDITION = "missing_condition"


def test_labels_are_ranked_by_confidence():
    result = {"clarity_defects": [
        {"defect": CONTEXT, "confidence": 0.6},
        {"defect": AMBIG, "confidence": 0.9},
    ]}
    assert [d for d, _ in clarity_defect_labels(result)] == [AMBIG, CONTEXT]
    assert primary_clarity_defect(result) == (AMBIG, 0.9)


def test_superseded_single_status_schema_still_parses():
    assert primary_clarity_defect({"clarity_status": CONTEXT, "confidence": 0.7}) == (CONTEXT, 0.7)


def test_clear_task_yields_no_label():
    assert primary_clarity_defect({"clarity_defects": []}) is None
    assert primary_clarity_defect({"clarity_status": "clear", "confidence": 0.9}) is None
    assert primary_clarity_defect({}) is None


def test_ties_are_broken_deterministically():
    forward = {"clarity_defects": [
        {"defect": CONTEXT, "confidence": 0.5}, {"defect": AMBIG, "confidence": 0.5}]}
    reverse = {"clarity_defects": [
        {"defect": AMBIG, "confidence": 0.5}, {"defect": CONTEXT, "confidence": 0.5}]}
    assert primary_clarity_defect(forward) == primary_clarity_defect(reverse)


def test_label_count_is_capped():
    result = {"clarity_defects": [
        {"defect": AMBIG, "confidence": 0.9},
        {"defect": CONTEXT, "confidence": 0.8},
        {"defect": CONDITION, "confidence": 0.7},
        {"defect": "not_a_real_defect", "confidence": 1.0},
    ]}
    assert len(clarity_defect_labels(result)) <= dp.MAX_CLARITY_LABELS


def test_duplicate_labels_cannot_buy_extra_slots():
    result = {"clarity_defects": [
        {"defect": CONTEXT, "confidence": 0.9},
        {"defect": CONTEXT, "confidence": 0.8},
    ]}
    assert clarity_defect_labels(result) == [(CONTEXT, 0.9)]


def test_unknown_labels_are_dropped():
    result = {"clarity_defects": [{"defect": "invented", "confidence": 0.99}]}
    assert primary_clarity_defect(result) is None


def test_malformed_payloads_fail_closed():
    for bad in ({"clarity_defects": "missing_context"}, {"clarity_defects": [None, 3]}):
        assert primary_clarity_defect(bad) is None


def test_cap_and_tie_break_are_in_the_policy_hash():
    base = dp.decision_policy()
    assert base["max_clarity_labels"] == dp.MAX_CLARITY_LABELS
    assert base["clarity_label_tie_break"] == list(dp.CLARITY_LABEL_TIE_BREAK)
