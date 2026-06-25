import unittest

from benchcore.comparison import candidate_tier, compute_item_risk_score


def _violation(
    defect_type: str,
    method: str,
    confidence: float,
    *,
    review_only: bool = True,
) -> dict:
    return {
        "item_id": "item-1",
        "defect_type": defect_type,
        "defect_scope": "substantive",
        "detection_method": method,
        "confidence": confidence,
        "review_only": review_only,
        "evidence": {},
    }


class ComparisonRankingTest(unittest.TestCase):
    def test_gold_audit_review_signal_is_priority(self) -> None:
        violations = [_violation("no_correct_answer", "llm_gold_audit", 0.667)]
        self.assertEqual(candidate_tier(violations), "priority")

    def test_weak_output_contract_heuristic_is_exploratory(self) -> None:
        violations = [_violation("missing_accepted_alternatives", "static_rule", 0.45)]
        self.assertEqual(candidate_tier(violations), "exploratory")

    def test_single_clarity_signal_is_exploratory(self) -> None:
        violations = [_violation("ambiguous_goal", "llm_question_clarity", 1.0)]
        self.assertEqual(candidate_tier(violations), "exploratory")

    def test_confirmed_signal_is_always_priority(self) -> None:
        violations = [
            _violation(
                "missing_accepted_alternatives",
                "static_rule",
                0.45,
                review_only=False,
            )
        ]
        self.assertEqual(candidate_tier(violations), "priority")

    def test_gold_signal_ranks_above_weak_static_signal(self) -> None:
        gold = [_violation("no_correct_answer", "llm_gold_audit", 0.667)]
        weak = [_violation("missing_accepted_alternatives", "static_rule", 0.45)]
        self.assertGreater(
            compute_item_risk_score(gold),
            compute_item_risk_score(weak),
        )


if __name__ == "__main__":
    unittest.main()
