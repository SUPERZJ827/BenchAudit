"""Single declared source of truth for every audit decision threshold.

Every constant that changes which items are flagged, or at which tier, lives
here.  Nothing else in ``benchcore`` may define such a constant inline.

The point is not tidiness.  A blind-holdout claim of the form "the decision
thresholds were frozen before the labels were read" is only checkable if the
thresholds are enumerable and hashable.  ``implementation_metadata`` hashes
every source file, so it changes on unrelated edits and cannot serve as that
evidence.  ``decision_policy_snapshot`` records exactly the decision surface
and nothing else.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


POLICY_SCHEMA_VERSION = "benchaudit-decision-policy-v1"

# --- comparison / tier assignment -------------------------------------------

IGNORED_DEFECTS = frozenset({"llm_audit_failure", "auditor_contradiction"})

STRONG_METHODS = frozenset({
    "llm_gold_audit",
    "llm_event_state",
    "llm_quantity_consistency",
    "executable_evidence",
    "executable_evidence_replay",
    "evaluator_replay",
    "differential_testing",
    "metamorphic_testing",
})

STRONG_DEFECTS = frozenset({
    "wrong_gold_answer",
    "invalid_choice_gold",
    "missing_oracle",
    "duplicate_choices",
    "duplicate_item_id",
    "conflicting_duplicate_oracle",
    "evaluator_mismatch",
    "metamorphic_inconsistency",
})

WEAK_REVIEW_DEFECTS = frozenset({
    "ambiguous_goal",
    "bad_options_clarity",
    "context_version_mismatch_risk",
    "missing_accepted_alternatives",
    "missing_condition",
    "missing_output_contract",
    "source_reference_missing",
    "temporal_scope_missing",
})

# Methods excluded from the strong-signal path even when their defect type is
# strong: they explicitly declare the finding does not change the answer.
NONMATERIAL_METHODS = frozenset({
    "llm_quantity_consistency_nonmaterial",
    "llm_event_state_nonmaterial",
})

# Minimum per-violation confidence for a finding to count as a strong signal.
STRONG_SIGNAL_MIN_CONFIDENCE = 0.6

# Distinct detection methods needed to treat a finding as corroborated.
CORROBORATION_MIN_METHODS = 2

# --- LLM auditor cascade gates ----------------------------------------------

# Below this, a blind solve is treated as risky and the cascade continues.
BLIND_SOLVE_MIN_CONFIDENCE = 0.85

# Below this, an option-evidence entry is treated as independently uncertain.
OPTION_EVIDENCE_MIN_CONFIDENCE = 0.8


# --- cascade ablation ---------------------------------------------------------
#
# The auditor embeds the blind solve's answer into later prompts and gates
# later calls on its confidence.  Provider nondeterminism at temperature 0
# therefore fans out into different downstream calls, which is the proposed
# mechanism behind finding-level irreproducibility.  These modes exist to test
# that mechanism causally; "full" is the unmodified pipeline.
#
#   full                 embed the whole blind solve, honour the gates
#   normalized           embed only decision fields, honour the gates
#   ungated              embed the whole blind solve, always continue
#   normalized_ungated   both interventions
CASCADE_MODES = ("full", "normalized", "ungated", "normalized_ungated")
DEFAULT_CASCADE_MODE = "full"

# Fields of a blind solve that downstream gates or auditors actually decide on.
# Everything else is prose and is dropped under a normalized cascade.
BLIND_SOLVE_DECISION_FIELDS = (
    "solution_status",
    "derived_answers",
    "valid_answers",
    "needs_expert",
    "assumption_risk",
)

# Under a normalized cascade the raw float is replaced by its side of the gate,
# so that 0.86 and 0.87 cannot produce two different downstream prompts.
CONFIDENCE_BUCKET_FIELD = "confidence_band"


# --- clarity multi-label ------------------------------------------------------
#
# The clarity auditor used to return one mutually exclusive status, so a task
# with several problems could only report one of them and the others were
# structurally suppressed.  It now returns a confidence-ranked list.  Scoring
# still uses the primary (top-ranked) entry only: "any label hits" inflates
# recall mechanically with the number of labels emitted, while the primary is
# immune to label count.
MAX_CLARITY_LABELS = 3

# Deterministic tie-break when two labels report the same confidence.  Without
# a fixed order the primary label -- and therefore the score -- would depend on
# dict iteration order.
CLARITY_LABEL_TIE_BREAK = (
    "answer_changing_ambiguity",
    "missing_context",
    "missing_condition",
)

# --- runtime-supplied thresholds --------------------------------------------

DEFAULT_LLM_CONFIRM_THRESHOLD = 0.75
DEFAULT_LLM_REVIEW_THRESHOLD = 0.45


def decision_policy(
    *,
    llm_confirm_threshold: float | None = None,
    llm_review_threshold: float | None = None,
    cascade_mode: str | None = None,
) -> dict[str, Any]:
    """Return the complete decision surface actually in force for a run."""

    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "ignored_defects": sorted(IGNORED_DEFECTS),
        "strong_methods": sorted(STRONG_METHODS),
        "strong_defects": sorted(STRONG_DEFECTS),
        "weak_review_defects": sorted(WEAK_REVIEW_DEFECTS),
        "nonmaterial_methods": sorted(NONMATERIAL_METHODS),
        "strong_signal_min_confidence": STRONG_SIGNAL_MIN_CONFIDENCE,
        "corroboration_min_methods": CORROBORATION_MIN_METHODS,
        "blind_solve_min_confidence": BLIND_SOLVE_MIN_CONFIDENCE,
        "option_evidence_min_confidence": OPTION_EVIDENCE_MIN_CONFIDENCE,
        "llm_confirm_threshold": (
            DEFAULT_LLM_CONFIRM_THRESHOLD
            if llm_confirm_threshold is None
            else float(llm_confirm_threshold)
        ),
        "llm_review_threshold": (
            DEFAULT_LLM_REVIEW_THRESHOLD
            if llm_review_threshold is None
            else float(llm_review_threshold)
        ),
        "cascade_mode": _validated_cascade_mode(cascade_mode),
        "blind_solve_decision_fields": list(BLIND_SOLVE_DECISION_FIELDS),
        "max_clarity_labels": MAX_CLARITY_LABELS,
        "clarity_label_tie_break": list(CLARITY_LABEL_TIE_BREAK),
    }


def _validated_cascade_mode(mode: str | None) -> str:
    resolved = DEFAULT_CASCADE_MODE if mode is None else str(mode)
    if resolved not in CASCADE_MODES:
        raise ValueError(
            f"unknown cascade mode {resolved!r}; expected one of {CASCADE_MODES}"
        )
    return resolved


def decision_policy_sha256(policy: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = decision_policy(**kwargs) if policy is None else policy
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decision_policy_snapshot(**kwargs: Any) -> dict[str, Any]:
    """Policy plus its hash, for embedding in run metadata."""

    policy = decision_policy(**kwargs)
    return {"policy": policy, "sha256": decision_policy_sha256(policy)}
