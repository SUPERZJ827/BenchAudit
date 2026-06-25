import unittest

from benchcore.llm_auditor import event_state_violations
from benchcore.schema import BenchmarkItem


class EventStateTest(unittest.TestCase):
    def test_removal_exceeding_inventory_is_programmatically_detected(self) -> None:
        item = BenchmarkItem(item_id="bus", raw={}, task="36 riders; 68 got off.", gold="24")
        result = {
            "state_models": [
                {
                    "entity": "children on bus",
                    "initial_value": 36,
                    "events": [
                        {"operation": "remove", "amount": 68, "stage": 1}
                    ],
                    "stated_final_value": 12,
                    "required_limit": None,
                    "material_to_answer": True,
                    "confidence": 0.99,
                }
            ],
            "role_conflicts": [],
            "confidence": 0.99,
        }
        violations = list(event_state_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertFalse(violations[0].review_only)
        findings = violations[0].evidence["llm_result"]["programmatic_event_state_findings"]
        self.assertEqual(findings[0]["finding_type"], "removal_exceeds_available")

    def test_negative_inferred_initial_state_is_detected(self) -> None:
        item = BenchmarkItem(item_id="caps", raw={}, task="Found 39, now has 16.", gold="2")
        result = {
            "state_models": [
                {
                    "entity": "bottle caps",
                    "initial_value": None,
                    "events": [{"operation": "add", "amount": 39, "stage": 1}],
                    "stated_final_value": 16,
                    "required_limit": None,
                    "material_to_answer": False,
                    "confidence": 1.0,
                }
            ],
            "role_conflicts": [],
            "confidence": 1.0,
        }
        violations = list(event_state_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].review_only)
        self.assertEqual(violations[0].detection_method, "llm_event_state_nonmaterial")

    def test_recipe_amount_exceeding_requirement_is_detected(self) -> None:
        item = BenchmarkItem(item_id="recipe", raw={}, task="Needs 6 cups; added 12.", gold="2")
        result = {
            "state_models": [
                {
                    "entity": "flour added",
                    "initial_value": 0,
                    "events": [{"operation": "add", "amount": 12, "stage": 1}],
                    "stated_final_value": 12,
                    "required_limit": 6,
                    "material_to_answer": False,
                    "confidence": 1.0,
                }
            ],
            "role_conflicts": [],
            "confidence": 1.0,
        }
        violations = list(event_state_violations(item, result, 0.75, 0.45))
        findings = violations[0].evidence["llm_result"]["programmatic_event_state_findings"]
        self.assertEqual(findings[0]["finding_type"], "state_exceeds_required_limit")

    def test_profit_price_role_conflict_is_detected(self) -> None:
        item = BenchmarkItem(item_id="shop", raw={}, task="Makes $10 off it. What does it cost?", gold="10")
        result = {
            "state_models": [],
            "role_conflicts": [
                {
                    "stated_role": "profit",
                    "queried_role": "price",
                    "same_quantity_justified": False,
                    "material_to_answer": True,
                    "confidence": 0.95,
                    "evidence": "Profit is not necessarily customer price.",
                }
            ],
            "confidence": 0.95,
        }
        violations = list(event_state_violations(item, result, 0.75, 0.45))
        self.assertEqual(len(violations), 1)
        self.assertFalse(violations[0].review_only)

    def test_valid_state_model_has_no_violation(self) -> None:
        item = BenchmarkItem(item_id="valid", raw={}, task="Had 9, ate 3, has 6.", gold="6")
        result = {
            "state_models": [
                {
                    "entity": "cookies",
                    "initial_value": 9,
                    "events": [{"operation": "remove", "amount": 3, "stage": 1}],
                    "stated_final_value": 6,
                    "required_limit": None,
                    "material_to_answer": True,
                    "confidence": 1.0,
                }
            ],
            "role_conflicts": [],
            "confidence": 1.0,
        }
        self.assertEqual(list(event_state_violations(item, result, 0.75, 0.45)), [])

    def test_unknown_event_amount_can_be_inferred_from_final_state(self) -> None:
        item = BenchmarkItem(
            item_id="unknown-add",
            raw={},
            task="Had 2 children, some got on, then there were 10.",
            gold="8",
        )
        result = {
            "state_models": [
                {
                    "entity": "children",
                    "initial_value": 2,
                    "events": [
                        {"operation": "add", "amount": None, "stage": 1},
                        {"operation": "set", "amount": 10, "stage": 2},
                    ],
                    "stated_final_value": 10,
                    "required_limit": None,
                    "material_to_answer": True,
                    "confidence": 1.0,
                }
            ],
            "role_conflicts": [],
            "confidence": 1.0,
        }
        self.assertEqual(list(event_state_violations(item, result, 0.75, 0.45)), [])

    def test_unknown_event_embedded_in_final_state_evidence_is_not_mismatch(self) -> None:
        item = BenchmarkItem(
            item_id="implicit-delete",
            raw={},
            task="Had 21, added 89, after deleting some had 24.",
            gold="3",
        )
        result = {
            "state_models": [
                {
                    "entity": "apps",
                    "initial_value": 21,
                    "events": [
                        {"operation": "add", "amount": 89, "stage": 1},
                        {
                            "operation": "set",
                            "amount": 24,
                            "stage": 2,
                            "evidence": "after deleting some he had 24 left",
                        },
                    ],
                    "stated_final_value": 24,
                    "required_limit": None,
                    "material_to_answer": True,
                    "confidence": 1.0,
                }
            ],
            "role_conflicts": [],
            "confidence": 1.0,
        }
        self.assertEqual(list(event_state_violations(item, result, 0.75, 0.45)), [])


if __name__ == "__main__":
    unittest.main()
