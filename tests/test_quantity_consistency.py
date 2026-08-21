import unittest

from benchcore.llm_auditor import (
    quantity_consistency_violations,
    quantity_response_consistency,
)
from benchcore.schema import BenchmarkItem


class QuantityConsistencyTest(unittest.TestCase):
    def test_known_internally_inconsistent_derived_claims_are_rejected(self) -> None:
        fixtures = [
            (
                "chal-162",
                "How many fishes disappeared?",
                ["15"],
                (
                    "Initial total is 7+12=19. After disappearance, 15 remain. "
                    "So disappeared = 19-15=4. The task asks for number of "
                    "fishes disappeared, which is 4."
                ),
                4.0,
            ),
            (
                "chal-599",
                "How many more marbles did Ed have than Doug then?",
                ["44"],
                (
                    "Ed had 45 and Doug had 35, then 24 after losing 11. "
                    "Difference is 21. All quantities are grounded."
                ),
                21.0,
            ),
            (
                "chal-687",
                "How much money did they make from selling the t-shirts?",
                ["4085"],
                (
                    "The shop makes $87 per shirt and sold 95 shirts. "
                    "Thus answer is 8265."
                ),
                8265.0,
            ),
            (
                "chal-934",
                "How many more storks than birds are sitting on the fence?",
                ["4"],
                (
                    "Initial storks=6 and final birds=2+3=5. Difference=6-5=1. "
                    "The question asks how many more storks, so answer is 1."
                ),
                1.0,
            ),
            (
                "chal-974",
                "How many more apps did he add than he deleted?",
                ["86"],
                (
                    "Deleted = 110 - 24 = 86. Added minus deleted is 89-86=3. "
                    "Wait, derived answer should be 3, not 86. "
                    "Correction: derived answer is 3."
                ),
                3.0,
            ),
        ]

        for name, task, derived, rationale, expected_rationale_value in fixtures:
            with self.subTest(name=name):
                item = BenchmarkItem(
                    item_id=name,
                    raw={},
                    task=task,
                    gold="999",
                )
                result = {
                    "solution_status": "solved",
                    "derived_answers": derived,
                    "checks": [],
                    "reference_issues": [],
                    "confidence": 1.0,
                    "rationale": rationale,
                }
                item.metadata["_llm_observations"] = {
                    "llm_quantity_consistency": result,
                }
                consistency = quantity_response_consistency(item, result)
                self.assertEqual(consistency["status"], "INCONSISTENT")
                self.assertEqual(
                    consistency["rationale_final_value"],
                    expected_rationale_value,
                )

                violations = list(
                    quantity_consistency_violations(item, result, 0.75, 0.45)
                )
                self.assertEqual(violations, [])
                observation = item.metadata["_llm_observations"][
                    "llm_quantity_consistency"
                ]
                self.assertEqual(
                    observation["response_consistency"]["status"],
                    "INCONSISTENT",
                )
                self.assertEqual(
                    observation["invalidated_claim_types"],
                    ["wrong_gold_answer"],
                )

    def test_inconsistent_derived_answer_preserves_independent_check_claim(self) -> None:
        item = BenchmarkItem(
            item_id="chal-513",
            raw={},
            task=(
                "David did 56 more push-ups than Zachary. David did 38 push-ups. "
                "How many push-ups did Zachary do?"
            ),
            gold="20",
        )
        result = {
            "solution_status": "solved",
            "derived_answers": ["132"],
            "checks": [
                {
                    "check_type": "state_transition",
                    "left_expression": "38 - 56",
                    "left_value": -18,
                    "relation": ">=",
                    "right_expression": "minimum feasible push-ups",
                    "right_value": 0,
                    "fully_grounded": True,
                    "material_to_answer": True,
                    "confidence": 1.0,
                    "evidence": "David did 56 more push-ups than Zachary and did 38.",
                }
            ],
            "reference_issues": [],
            "confidence": 1.0,
            "rationale": (
                "David did 56 more push-ups than Zachary and David did 38. "
                "Thus Zachary did 38 - 56 = -18 push-ups, which is impossible. "
                "The derived answer is 20, but the problem is internally inconsistent."
            ),
        }
        item.metadata["_llm_observations"] = {
            "llm_quantity_consistency": result,
        }

        consistency = quantity_response_consistency(item, result)
        self.assertEqual(consistency["status"], "INCONSISTENT")
        self.assertEqual(consistency["derived_value"], 132.0)
        self.assertEqual(consistency["rationale_final_value"], 20.0)

        violations = list(quantity_consistency_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "ambiguous_goal")
        self.assertEqual(violations[0].detection_method, "llm_quantity_consistency")
        self.assertNotEqual(violations[0].defect_scope, "operational")
        self.assertEqual(
            violations[0].evidence["llm_result"]["response_consistency"]["status"],
            "INCONSISTENT",
        )
        self.assertEqual(
            violations[0].evidence["llm_result"]["invalidated_claim_types"],
            ["wrong_gold_answer"],
        )
        observation = item.metadata["_llm_observations"]["llm_quantity_consistency"]
        self.assertEqual(observation["response_consistency"]["status"], "INCONSISTENT")
        self.assertEqual(
            observation["invalidated_claim_types"],
            ["wrong_gold_answer"],
        )

    def test_inconsistent_derived_answer_preserves_nonmaterial_reference_claim(self) -> None:
        item = BenchmarkItem(
            item_id="claim-scoped-reference",
            raw={},
            task="How many objects remain?",
            gold="3",
        )
        result = {
            "solution_status": "solved",
            "derived_answers": ["6"],
            "checks": [],
            "reference_issues": [
                {
                    "issue": "An irrelevant object's unit was parsed incorrectly.",
                    "material_to_answer": False,
                    "confidence": 1.0,
                }
            ],
            "confidence": 1.0,
            "rationale": "The final answer is 3.",
        }

        violations = list(quantity_consistency_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "ambiguous_goal")
        self.assertEqual(
            violations[0].detection_method,
            "llm_quantity_consistency_nonmaterial",
        )
        self.assertEqual(
            violations[0].evidence["llm_result"]["response_consistency"]["status"],
            "INCONSISTENT",
        )
        self.assertEqual(
            violations[0].evidence["llm_result"]["invalidated_claim_types"],
            ["wrong_gold_answer"],
        )

    def test_consistent_relation_error_still_reaches_gold_comparison(self) -> None:
        item = BenchmarkItem(
            item_id="consistent-but-wrong",
            raw={},
            task="How many more marbles did Ed have than Doug?",
            gold="21",
        )
        result = {
            "solution_status": "solved",
            "derived_answers": ["34"],
            "checks": [],
            "reference_issues": [],
            "confidence": 1.0,
            "rationale": (
                "The initial difference is irrelevant. "
                "The final difference is 45 - 11 = 34."
            ),
        }

        consistency = quantity_response_consistency(item, result)
        self.assertEqual(consistency["status"], "CONSISTENT")
        violations = list(quantity_consistency_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "wrong_gold_answer")
        self.assertEqual(violations[0].defect_scope, "substantive")

    def test_unidentifiable_rationale_preserves_existing_behavior(self) -> None:
        item = BenchmarkItem(
            item_id="unidentifiable",
            raw={},
            task="How many objects remain?",
            gold="3",
        )
        result = {
            "solution_status": "solved",
            "derived_answers": ["6"],
            "checks": [],
            "reference_issues": [],
            "confidence": 1.0,
            "rationale": "The quantities can be combined in the usual way.",
        }

        consistency = quantity_response_consistency(item, result)
        self.assertEqual(consistency["status"], "NOT_IDENTIFIABLE")
        violations = list(quantity_consistency_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "wrong_gold_answer")

    def test_invalid_arithmetic_claim_cannot_trigger_downgrade(self) -> None:
        item = BenchmarkItem(
            item_id="invalid-rationale-arithmetic",
            raw={},
            task="How many more bottles than apples are there?",
            gold="98",
        )
        result = {
            "solution_status": "solved",
            "derived_answers": ["44"],
            "checks": [],
            "reference_issues": [],
            "confidence": 1.0,
            "rationale": "Total bottles are 134. The final answer is 134 - 36 = 44.",
        }

        consistency = quantity_response_consistency(item, result)
        self.assertEqual(consistency["status"], "NOT_IDENTIFIABLE")
        violations = list(quantity_consistency_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "wrong_gold_answer")

    def test_non_solved_or_non_unique_answer_is_not_identifiable(self) -> None:
        item = BenchmarkItem(
            item_id="not-identifiable-precondition",
            raw={},
            task="How many objects remain?",
            gold="3",
        )
        fixtures = [
            {"solution_status": "ambiguous", "derived_answers": ["3"]},
            {"solution_status": "solved", "derived_answers": []},
            {"solution_status": "solved", "derived_answers": ["3", "4"]},
        ]
        for result in fixtures:
            with self.subTest(result=result):
                result = {
                    **result,
                    "rationale": "The final answer is 3.",
                    "checks": [],
                    "reference_issues": [],
                    "confidence": 1.0,
                }
                self.assertEqual(
                    quantity_response_consistency(item, result)["status"],
                    "NOT_IDENTIFIABLE",
                )

    def test_program_rechecks_violated_availability_constraint(self) -> None:
        item = BenchmarkItem(
            item_id="cookies",
            raw={},
            task="Paco had 17 cookies. He ate 14 and gave away 13.",
            gold="1",
        )
        result = {
            "solution_status": "contradictory",
            "derived_answers": [],
            "checks": [
                {
                    "check_type": "availability",
                    "left_value": 27,
                    "relation": "<=",
                    "right_value": 17,
                    "fully_grounded": True,
                    "material_to_answer": True,
                    "confidence": 0.98,
                }
            ],
            "reference_issues": [],
            "confidence": 0.98,
        }
        violations = list(quantity_consistency_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "ambiguous_goal")
        self.assertTrue(violations[0].review_only)
        self.assertEqual(violations[0].evidence_tier, "review")
        self.assertTrue(violations[0].evidence["llm_result"]["programmatic_violation"])

    def test_program_does_not_trust_a_satisfied_constraint_as_defect(self) -> None:
        item = BenchmarkItem(
            item_id="valid",
            raw={},
            task="Paco had 17 cookies and ate 4.",
            gold="13",
        )
        result = {
            "solution_status": "solved",
            "derived_answers": ["13"],
            "checks": [
                {
                    "check_type": "availability",
                    "left_value": 4,
                    "relation": "<=",
                    "right_value": 17,
                    "fully_grounded": True,
                    "material_to_answer": True,
                    "confidence": 0.99,
                }
            ],
            "reference_issues": [],
            "confidence": 0.99,
        }
        self.assertEqual(
            list(quantity_consistency_violations(item, result, 0.75, 0.45)),
            [],
        )

    def test_independent_numeric_answer_can_flag_gold_mismatch(self) -> None:
        item = BenchmarkItem(
            item_id="balloons",
            raw={},
            task="Jake brought 6 balloons and later bought 3. How many did he bring?",
            gold="9",
        )
        result = {
            "solution_status": "solved",
            "derived_answers": ["6"],
            "checks": [],
            "reference_issues": [],
            "confidence": 0.95,
        }
        violations = list(quantity_consistency_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "wrong_gold_answer")
        self.assertTrue(violations[0].review_only)

    def test_irrelevant_constraints_are_exploratory_and_ungrounded_are_ignored(self) -> None:
        item = BenchmarkItem(
            item_id="packages",
            raw={},
            task="Each package has 13 shirts. There are 39 shirts.",
            gold="3",
        )
        result = {
            "solution_status": "solved",
            "derived_answers": ["3"],
            "checks": [
                {
                    "left_value": 13,
                    "relation": "==",
                    "right_value": 39,
                    "fully_grounded": False,
                    "material_to_answer": True,
                    "confidence": 1.0,
                },
                {
                    "left_value": 36,
                    "relation": "<=",
                    "right_value": 9,
                    "fully_grounded": True,
                    "material_to_answer": False,
                    "confidence": 1.0,
                },
            ],
            "reference_issues": [],
            "confidence": 1.0,
        }
        violations = list(quantity_consistency_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].review_only)
        self.assertEqual(
            violations[0].detection_method,
            "llm_quantity_consistency_nonmaterial",
        )

    def test_nonmaterial_reference_issue_is_exploratory(self) -> None:
        item = BenchmarkItem(
            item_id="classrooms",
            raw={},
            task="There are 58 students and 87 classrooms. How many buses are needed?",
            gold="29",
        )
        result = {
            "solution_status": "solved",
            "derived_answers": ["29"],
            "checks": [],
            "reference_issues": [
                {
                    "issue_type": "semantic_role",
                    "material_to_answer": False,
                    "confidence": 1.0,
                    "evidence": "The classroom distribution is internally implausible.",
                }
            ],
            "confidence": 1.0,
        }
        violations = list(quantity_consistency_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].review_only)
        self.assertEqual(
            violations[0].detection_method,
            "llm_quantity_consistency_nonmaterial",
        )


if __name__ == "__main__":
    unittest.main()
