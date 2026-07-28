from scripts.analyze_workspace_a_prime import analyze
from scripts.run_workspace_static_llm_ablation import (
    NEGATIVE_REVIEW_LABEL,
    POSITIVE_REVIEW_LABEL,
)


def _decision(index, *, views, route=None):
    scanner = {
        "triage_selected_views": views,
        "triage_view_count": 1,
    }
    if route is not None:
        scanner["structured_route"] = route
    return {
        "rubric_index": index,
        "scanner": scanner,
        "verifier": None,
    }


def _route(confidence, selected=True, reason="unsupported_exact_constraint"):
    return {
        "action": "route" if selected else "do_not_route",
        "reason_code": reason,
        "evidence_source": "none",
        "confidence": confidence,
        "policy_selected_before_threshold": selected,
        "policy_override": "",
    }


def test_a_prime_analysis_builds_frozen_pareto_and_cost():
    structured = {
        "item-1": {
            "decisions": [
                _decision(0, views=["structured_a_prime"], route=_route(0.95)),
                _decision(1, views=["structured_a_prime"], route=_route(0.75)),
                _decision(
                    2,
                    views=[],
                    route=_route(0.99, False, "general_quality"),
                ),
                _decision(
                    3,
                    views=[],
                    route=_route(0.4),
                ),
            ],
            "findings": [],
        },
    }
    baseline = {
        "item-1": {
            "decisions": [
                _decision(0, views=["hidden_constraint"]),
                _decision(1, views=["hidden_constraint"]),
                _decision(2, views=["hidden_constraint"]),
                _decision(3, views=["hidden_constraint"]),
            ],
        },
    }
    reviewed = {
        ("item-1", 0): POSITIVE_REVIEW_LABEL,
        ("item-1", 1): POSITIVE_REVIEW_LABEL,
        ("item-1", 2): NEGATIVE_REVIEW_LABEL,
    }

    result = analyze(
        structured_rows=structured,
        baseline_rows=baseline,
        expected_items={"item-1"},
        reviewed_labels=reviewed,
        family_positives_all={("item-1", 0), ("item-1", 1)},
    )

    by_threshold = {row["threshold"]: row for row in result["thresholds"]}
    assert by_threshold[0.5]["family_grounding"]["recall"] == 1.0
    assert by_threshold[0.5]["candidate_rate"] == 0.5
    assert by_threshold[0.8]["family_grounding"]["recall"] == 0.5
    assert result["baseline_a"]["logical_calls"] == 5
    assert result["decomposition"]["reason_counts_all"] == {
        "general_quality": 1,
        "unsupported_exact_constraint": 3,
    }
    assert result["operational_unknown_tasks"] == []


def test_a_prime_analysis_marks_missing_structured_row_operational_unknown():
    structured = {
        "item-1": {
            "decisions": [{
                "rubric_index": 0,
                "scanner": {
                    "triage_selected_views": [],
                    "triage_view_count": 1,
                },
                "verifier": None,
            }],
            "findings": [],
        },
    }
    baseline = {
        "item-1": {
            "decisions": [_decision(0, views=["hidden_constraint"])],
        },
    }

    result = analyze(
        structured_rows=structured,
        baseline_rows=baseline,
        expected_items={"item-1"},
        reviewed_labels={},
        family_positives_all=set(),
    )

    assert result["operational_unknown_tasks"] == ["item-1"]
    assert not result["calibration_go"]
