from scripts.analyze_workspace_a_double_prime_internal import (
    SELECTED_RULE_IDS,
    evaluate_internal,
)


def _evaluate(*, hits=6, candidates=118, unknown=None, escape=0):
    positives = {("item", index) for index in range(7)}
    a_prime = {("base", index) for index in range(candidates - hits)}
    r2c = {("item", 0)} if hits else set()
    r2d = {("item", index) for index in range(1, hits)}
    old_a = {("old", index) for index in range(118)}
    return evaluate_internal(
        a_prime_candidates=a_prime,
        old_a_candidates=old_a,
        rule_sets={
            "R2a": {("forbidden", 1)},
            "R2b": {("forbidden", 2)},
            "R2c": r2c,
            "R2d": r2d,
        },
        family_positives=positives,
        reviewed_labels={},
        expected_items={"item"},
        rubric_count=204,
        router_calls=10,
        review_ceiling_escape=escape,
        operational_unknown_tasks=unknown or [],
    )


def test_internal_gate_passes_only_frozen_r2c_r2d_point():
    result = _evaluate()

    assert tuple(result["selected_rule_ids"]) == SELECTED_RULE_IDS
    assert result["counts"]["candidates"] == 118
    assert result["counts"]["family_hits"] == 6
    assert result["decision"] == "PASS"


def test_internal_gate_does_not_consume_r2a_or_r2b():
    result = _evaluate()

    assert result["counts"]["rule_union_triggers"] == 6
    assert ("forbidden", 1) not in {
        ("item", index) for index in range(7)
    }
    assert set(result["rule_trigger_counts"]) == {"R2c", "R2d"}


def test_internal_gate_fails_below_six_family_hits():
    result = _evaluate(hits=5, candidates=117)

    assert result["gate"]["family_hits_at_least_6_of_7"] is False
    assert result["decision"] == "FAIL"


def test_internal_gate_fails_closed_on_unknown_or_ceiling_escape():
    assert _evaluate(unknown=["item"])["decision"] == "FAIL"
    assert _evaluate(escape=1)["decision"] == "FAIL"
