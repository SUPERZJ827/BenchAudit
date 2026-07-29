from scripts.recompute_workspace_a_double_prime_internal_p1 import (
    summarize_family_reference,
)


def test_family_reference_summary_uses_requested_denominator():
    positives = {("item", 1), ("item", 2)}
    result = summarize_family_reference(
        positives=positives,
        old_a_candidates={("item", 1), ("other", 9)},
        a_prime_candidates={("item", 2)},
        a_double_prime_candidates={("item", 1), ("item", 2)},
    )

    assert result["positives"] == 2
    assert result["methods"]["old_a"]["hits"] == 1
    assert result["methods"]["a_prime"]["hits"] == 1
    assert result["methods"]["a_double_prime"]["hits"] == 2


def test_disjoint_reference_changes_hits_without_changing_predictions():
    p0 = {("item", 1)}
    p1 = {("item", 2)}
    predictions = {("item", 2)}

    p0_result = summarize_family_reference(
        positives=p0,
        old_a_candidates=predictions,
        a_prime_candidates=predictions,
        a_double_prime_candidates=predictions,
    )
    p1_result = summarize_family_reference(
        positives=p1,
        old_a_candidates=predictions,
        a_prime_candidates=predictions,
        a_double_prime_candidates=predictions,
    )

    assert p0_result["methods"]["old_a"]["hits"] == 0
    assert p1_result["methods"]["old_a"]["hits"] == 1
