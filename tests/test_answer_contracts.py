import unittest

from benchcore.checkers import EvaluatorChecker
from benchcore.evaluators import answer_variants, evaluate_answer
from benchcore.llm_auditor import compact_value, presentation_violations
from benchcore.schema import BenchmarkItem


class AnswerContractTest(unittest.TestCase):
    def test_set_answer_is_order_insensitive(self) -> None:
        evaluator = {"type": "denotation_set_match"}
        gold = ["Honda Motor", "SC Tottori", "Ehime FC"]

        self.assertTrue(evaluate_answer(["Ehime FC", "Honda Motor", "SC Tottori"], gold, None, evaluator))
        self.assertTrue(evaluate_answer("Honda Motor, SC Tottori, Ehime FC", gold, None, evaluator))
        self.assertFalse(evaluate_answer("Honda Motor", gold, None, evaluator))

    def test_set_members_are_not_treated_as_aliases(self) -> None:
        item = BenchmarkItem(
            item_id="set",
            raw={},
            task="List the top 3 teams.",
            gold=["Honda Motor", "SC Tottori", "Ehime FC"],
            aliases=["Honda Motor", "SC Tottori", "Ehime FC"],
            evaluator={"type": "denotation_set_match"},
            output_contract={"type": "answer_set"},
        )

        violations = list(EvaluatorChecker().check(item))
        self.assertNotIn("overstrict_evaluator", {v.defect_type for v in violations})

    def test_explanatory_text_variants_require_contract_support(self) -> None:
        strict = answer_variants("Ottawa", evaluator={"type": "normalized_exact_match"})
        free_form = answer_variants(
            "Ottawa",
            evaluator={"type": "normalized_exact_match"},
            output_contract={"format": "answer extraction from free-form sentence"},
        )

        self.assertNotIn("answer_prefix", {name for name, _ in strict})
        self.assertIn("answer_prefix", {name for name, _ in free_form})

    def test_transport_truncation_is_not_presentation_corruption(self) -> None:
        compacted = compact_value({"table": "x" * 5000}, 100)
        self.assertTrue(compacted["__benchcore_payload_truncated__"])
        item = BenchmarkItem(
            item_id="table",
            raw={},
            task="Answer from the table.",
            context={"table": "x" * 5000},
            gold="x",
        )
        result = {
            "issues": [
                {
                    "artifact": "context_attachment",
                    "location": "table",
                    "issue_type": "truncation",
                    "raw_text": "...[truncated]",
                    "interpreted_text": "full table",
                    "confidence": 0.99,
                    "rationale": "The preview is truncated and should include the full table.",
                }
            ]
        }

        self.assertEqual(list(presentation_violations(item, result, 0.45)), [])


if __name__ == "__main__":
    unittest.main()
