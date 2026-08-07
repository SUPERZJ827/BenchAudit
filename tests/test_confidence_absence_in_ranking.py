"""Absence of a confidence is not a confidence of zero.

Both ranking gates read the field with an ``or 0.0`` fallback, which was
harmless while every finding carried a number.  Once deterministic detectors
stopped inventing one, that fallback would score exactly the findings we trust
most as the weakest thing in the report -- an `invalid_choice_gold` proven by
replay would fail a gate written to filter unsupported model claims.
"""

from __future__ import annotations

from benchcore.comparison import candidate_tier, compute_item_risk_score


def _finding(**overrides):
    base = {
        "defect_type": "invalid_choice_gold",
        "detection_method": "static_rule",
        "defect_scope": "substantive",
        "review_only": True,
        "confidence": None,
        "evidence": {},
    }
    base.update(overrides)
    return base


def test_a_deterministic_finding_still_counts_as_a_strong_signal():
    """`invalid_choice_gold` is in STRONG_DEFECTS; it has no score to threshold."""
    assert candidate_tier([_finding()]) == "priority"


def test_a_model_claim_below_the_gate_is_still_filtered():
    """The gate must keep working for what it was written for."""
    weak = _finding(detection_method="llm_gold_audit", confidence=0.2)
    assert candidate_tier([weak]) == "exploratory"


def test_a_missing_score_does_not_rank_below_a_reported_zero():
    deterministic = compute_item_risk_score([_finding()])
    reported_zero = compute_item_risk_score(
        [_finding(detection_method="llm_gold_audit", confidence=0.0)]
    )
    assert deterministic >= reported_zero
