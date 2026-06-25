import unittest

from benchcore.llm_auditor import quantity_consistency_violations
from benchcore.schema import BenchmarkItem


class QuantityConsistencyTest(unittest.TestCase):
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
        self.assertFalse(violations[0].review_only)
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
