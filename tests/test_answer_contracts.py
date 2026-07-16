import unittest

from benchcore.checkers import EvaluatorChecker, OutputContractChecker
from benchcore.evaluators import answer_variants, evaluate_answer
from benchcore.llm_auditor import compact_value, presentation_violations
from benchcore.methods import MetamorphicAnswerChecker
from benchcore.schema import BenchmarkItem
from scripts.prepare_pilot_datasets import normalize_asdiv_answer, ratio_aliases


class AnswerContractTest(unittest.TestCase):
    def test_agent_output_contract_without_evaluator_is_structural_gap(self) -> None:
        item = BenchmarkItem(
            item_id="agent",
            raw={},
            task="Create report.md.",
            output_contract={"type": "workspace_files", "required_files": ["report.md"]},
            gold=None,
            evaluator=None,
        )

        violations = list(EvaluatorChecker().check(item))

        missing = [v for v in violations if v.defect_type == "missing_evaluator"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].severity, "major")
        # Absence in one canonical row is a strong structural candidate, but
        # without a complete package/runner proof an external evaluator may
        # still exist.  The central promotion policy therefore keeps it review.
        self.assertTrue(missing[0].review_only)
        self.assertEqual(missing[0].evidence_tier, "review")
        self.assertTrue(missing[0].evidence["agent_style_contract"])

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

    def test_asdiv_semicolon_answer_remains_single_compound_response(self) -> None:
        gold = normalize_asdiv_answer("24 (degrees); 120 (degrees); 36 (degrees)")

        self.assertEqual(gold, "24; 120; 36")
        self.assertTrue(
            evaluate_answer(
                "24; 120; 36",
                gold,
                None,
                {"type": "normalized_exact_match"},
            )
        )
        self.assertTrue(
            evaluate_answer(
                "24 (degrees); 120 (degrees); 36 (degrees)",
                gold,
                None,
                {"type": "compound_normalized_exact_match"},
            )
        )
        self.assertFalse(
            evaluate_answer(
                "24",
                gold,
                None,
                {"type": "compound_normalized_exact_match"},
            )
        )

    def test_asdiv_ratio_answer_preserves_structure(self) -> None:
        gold = normalize_asdiv_answer("7:50")

        self.assertEqual(gold, "7:50")
        self.assertEqual(ratio_aliases(gold), ["7/50", "0.14"])
        self.assertTrue(evaluate_answer("7:50", gold, None, {"type": "ratio_or_normalized_exact"}))
        self.assertTrue(evaluate_answer("7/50", gold, None, {"type": "ratio_or_normalized_exact"}))
        self.assertTrue(evaluate_answer("0.14", gold, None, {"type": "ratio_or_normalized_exact"}))
        self.assertFalse(evaluate_answer("7", gold, None, {"type": "ratio_or_normalized_exact"}))

    def test_numeric_metamorphic_variants_preserve_decimal_value(self) -> None:
        item = BenchmarkItem(
            item_id="money",
            raw={},
            task="If each ball costs $1.54, how much must Kyoko pay for three balls?",
            gold="4.62",
            evaluator={"type": "numeric_or_normalized_exact"},
            output_contract={"type": "number", "format": "single answer"},
        )

        violations = list(MetamorphicAnswerChecker().check(item))

        self.assertEqual(violations, [])
        self.assertTrue(evaluate_answer("4.620", "4.62", None, {"type": "numeric_or_normalized_exact"}))
        self.assertFalse(evaluate_answer("4.6", "4.62", None, {"type": "numeric_or_normalized_exact"}))

    def test_unit_requested_by_question_allows_bare_numeric_gold(self) -> None:
        item = BenchmarkItem(
            item_id="minutes",
            raw={},
            task="An industrial machine made 12 shirts. It can make 2 shirts a minute. How many minutes was the machine working?",
            gold="6",
            evaluator={"type": "numeric_or_normalized_exact"},
            output_contract={"type": "number", "format": "single answer"},
        )

        violations = list(OutputContractChecker().check(item))

        self.assertNotIn("missing_accepted_alternatives", {v.defect_type for v in violations})


if __name__ == "__main__":
    unittest.main()
