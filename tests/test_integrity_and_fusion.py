import unittest

from benchcore.auditor import fuse_llm_evidence
from benchcore.checkers import _violation
from benchcore.llm_auditor import (
    EvidenceGoldLLMAuditor,
    build_user_prompt,
    option_match_evidence,
    option_applicability_violations,
    option_violations,
    presentation_violations,
    question_violations,
)
from benchcore.methods import TaskIntegrityChecker
from benchcore.schema import BenchmarkItem


class FakeLLMClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat_json(self, system, user):
        self.calls.append((system, user))
        return self.responses.pop(0)


class IntegrityAndFusionTest(unittest.TestCase):
    def test_temporal_and_source_integrity(self) -> None:
        item = BenchmarkItem(
            item_id="temporal",
            raw={},
            task="In the latest research, what is the current population?",
            gold="9",
        )
        violations = list(TaskIntegrityChecker().check(item))
        defects = {violation.defect_type for violation in violations}
        self.assertIn("temporal_scope_missing", defects)
        self.assertIn("source_reference_missing", defects)

    def test_story_relative_time_is_not_external_temporal_scope(self) -> None:
        item = BenchmarkItem(
            item_id="story-time",
            raw={},
            task=(
                "A machine made 12 shirts yesterday and has 5 shirts right now. "
                "How many shirts are there altogether?"
            ),
        )
        violations = list(TaskIntegrityChecker().check(item))
        self.assertNotIn(
            "temporal_scope_missing",
            {violation.defect_type for violation in violations},
        )

    def test_presentation_corruption(self) -> None:
        item = BenchmarkItem(
            item_id="corrupt",
            raw={},
            task="Choose the age group.",
            choices=["0-4", "14-May", "15-49"],
            gold="C",
        )
        violations = list(TaskIntegrityChecker().check(item))
        finding = next(v for v in violations if v.defect_type == "presentation_corruption")
        self.assertEqual(finding.defect_scope, "presentation")
        self.assertTrue(finding.review_only)

    def test_option_literal_vs_best_output(self) -> None:
        item = BenchmarkItem(
            item_id="options",
            raw={},
            task="Which option is true?",
            choices=["A", "B"],
            gold="A",
        )
        result = {
            "option_statuses": [
                {
                    "label": "A",
                    "literal_truth": "true",
                    "best_answer_status": "acceptable",
                    "clarity": "clear",
                },
                {
                    "label": "B",
                    "literal_truth": "true",
                    "best_answer_status": "acceptable",
                    "clarity": "clear",
                },
            ],
            "literal_cardinality": "multiple",
            "best_answer_cardinality": "multiple",
            "defect_type": "none",
            "confidence": 0.9,
            "needs_expert": False,
        }
        violations = list(option_violations(item, result, 0.75, 0.45))
        self.assertEqual(violations[0].defect_type, "multiple_correct_answers")

    def test_question_clarity_is_review_without_external_evidence(self) -> None:
        item = BenchmarkItem(
            item_id="clarity",
            raw={},
            task="An underspecified question",
            gold="A",
        )
        result = {
            "clarity_status": "missing_condition",
            "confidence": 0.95,
            "needs_expert": False,
            "alternative_interpretations": [
                {"interpretation": "one", "answer": "A"},
                {"interpretation": "two", "answer": "B"},
            ],
        }
        violations = list(question_violations(item, result, 0.75, 0.45))
        self.assertTrue(violations[0].review_only)
        self.assertEqual(violations[0].severity, "review")

    def test_auditor_contradiction_demotes_findings(self) -> None:
        item = BenchmarkItem(
            item_id="conflict",
            raw={},
            task="Question",
            choices=["one", "two"],
            gold="A",
            metadata={
                "_llm_observations": {
                    "_declared_gold": "A",
                    "llm_gold_audit": {
                        "gold_status": "contradicted",
                        "correct_answers": ["B"],
                    },
                    "llm_option_set": {
                        "defect_type": "none",
                        "best_answer_cardinality": "exactly_one",
                        "option_statuses": [
                            {
                                "label": "A",
                                "best_answer_status": "best",
                            }
                        ],
                    },
                }
            },
        )
        violation = _violation(
            item,
            "wrong_gold_answer",
            0.9,
            "conflict",
            method="llm_gold_audit",
        )
        fused = fuse_llm_evidence([violation], [item])
        self.assertTrue(violation.review_only)
        self.assertEqual(violation.severity, "review")
        self.assertTrue(any(v.defect_type == "auditor_contradiction" for v in fused))

    def test_option_internal_contradiction_does_not_demote_gold(self) -> None:
        item = BenchmarkItem(
            item_id="option-conflict",
            raw={},
            task="Question",
            choices=["one", "two"],
            gold="A",
            metadata={
                "_llm_observations": {
                    "_declared_gold": "A",
                    "llm_gold_audit": {
                        "gold_status": "contradicted",
                        "correct_answers": ["B"],
                    },
                    "llm_option_set": {
                        "defect_type": "no_correct_answer",
                        "best_answer_cardinality": "exactly_one",
                        "option_statuses": [
                            {
                                "label": "B",
                                "best_answer_status": "best",
                            }
                        ],
                    },
                }
            },
        )
        gold_violation = _violation(
            item,
            "wrong_gold_answer",
            0.9,
            "gold finding",
            method="llm_gold_audit",
        )
        option_violation = _violation(
            item,
            "no_correct_answer",
            0.9,
            "option finding",
            method="llm_option_set",
        )

        fuse_llm_evidence([gold_violation, option_violation], [item])

        self.assertFalse(gold_violation.review_only)
        self.assertTrue(option_violation.review_only)

    def test_llm_observations_are_not_reinjected_into_prompts(self) -> None:
        item = BenchmarkItem(
            item_id="stable-prompt",
            raw={},
            task="Question",
            gold="A",
            metadata={
                "subject": "test",
                "_llm_observations": {
                    "llm_gold_audit": {"gold_status": "supported"},
                },
            },
        )

        prompt = build_user_prompt(item)

        self.assertIn('"subject": "test"', prompt)
        self.assertNotIn("_llm_observations", prompt)
        self.assertNotIn("gold_status", prompt)

    def test_evidence_gold_cascade_runs_challenger_for_safe_blind_solution(self) -> None:
        client = FakeLLMClient(
            [
                {
                    "solution_status": "solved",
                    "derived_answers": ["2"],
                    "confidence": 0.95,
                    "needs_expert": False,
                    "required_assumptions": [],
                },
                {
                    "matches": [
                        {"label": "A", "relation": "equivalent", "confidence": 0.95},
                        {"label": "B", "relation": "not_equivalent", "confidence": 0.95},
                    ],
                    "needs_expert": False,
                },
                {
                    "option_assessments": [
                        {"label": "A", "status": "acceptable", "confidence": 0.95},
                        {"label": "B", "status": "not_acceptable", "confidence": 0.95},
                    ],
                    "question_mode": "identity",
                    "needs_expert": False,
                },
            ]
        )
        item = BenchmarkItem(
            item_id="safe",
            raw={},
            task="What is 1 + 1?",
            choices=["2", "3"],
            gold="A",
        )

        violations = list(EvidenceGoldLLMAuditor(client, mode="cascade").check(item))

        self.assertEqual(violations, [])
        self.assertEqual(len(client.calls), 3)
        self.assertNotIn('"gold"', client.calls[0][1])

    def test_evidence_gold_cascade_adds_defender_on_challenge(self) -> None:
        client = FakeLLMClient(
            [
                {
                    "solution_status": "solved",
                    "derived_answers": ["two"],
                    "confidence": 0.95,
                    "needs_expert": False,
                    "required_assumptions": [],
                },
                {
                    "matches": [
                        {"label": "A", "relation": "not_equivalent", "confidence": 0.95},
                        {"label": "B", "relation": "equivalent", "confidence": 0.95},
                    ],
                    "needs_expert": False,
                },
                {
                    "option_assessments": [
                        {"label": "A", "status": "not_acceptable", "confidence": 0.95},
                        {"label": "B", "status": "acceptable", "confidence": 0.95},
                    ],
                    "question_mode": "identity",
                    "needs_expert": False,
                },
                {
                    "gold_validity": "invalid",
                    "defect_type": "wrong_gold_answer",
                    "alternative_answers": ["B"],
                    "confidence": 0.9,
                    "needs_expert": False,
                },
                {
                    "gold_support": "supported",
                    "confidence": 0.9,
                    "needs_expert": False,
                    "assumptions_required": [],
                },
            ]
        )
        item = BenchmarkItem(
            item_id="challenge",
            raw={},
            task="Question",
            choices=["one", "two"],
            gold="A",
        )

        violations = list(EvidenceGoldLLMAuditor(client, mode="cascade").check(item))

        self.assertEqual(len(client.calls), 5)
        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].review_only)

    def test_evidence_gold_full_confirms_three_way_wrong_gold(self) -> None:
        client = FakeLLMClient(
            [
                {
                    "solution_status": "solved",
                    "derived_answers": ["2"],
                    "confidence": 0.9,
                    "needs_expert": False,
                    "assumption_risk": "conventional",
                    "required_assumptions": ["Standard arithmetic notation"],
                },
                {
                    "matches": [
                        {"label": "A", "relation": "not_equivalent", "confidence": 0.9},
                        {"label": "B", "relation": "equivalent", "confidence": 0.9},
                    ],
                    "needs_expert": False,
                },
                {
                    "option_assessments": [
                        {"label": "A", "status": "not_acceptable", "confidence": 0.9},
                        {"label": "B", "status": "acceptable", "confidence": 0.9},
                    ],
                    "question_mode": "identity",
                    "needs_expert": False,
                },
                {
                    "gold_validity": "invalid",
                    "defect_type": "wrong_gold_answer",
                    "alternative_answers": ["B"],
                    "confidence": 0.9,
                    "needs_expert": False,
                },
                {
                    "gold_support": "unsupported",
                    "confidence": 0.9,
                    "needs_expert": False,
                    "assumptions_required": ["An invalid nonstandard convention"],
                },
            ]
        )
        item = BenchmarkItem(
            item_id="wrong",
            raw={},
            task="What is 1 + 1?",
            choices=["3", "2"],
            gold="A",
        )

        violations = list(EvidenceGoldLLMAuditor(client, mode="full").check(item))

        self.assertEqual(len(client.calls), 5)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "wrong_gold_answer")
        self.assertFalse(violations[0].review_only)
        result = violations[0].evidence["llm_result"]
        self.assertEqual(result["evidence_votes"], ["wrong_gold_answer"] * 3)
        self.assertEqual(result["evidence_agreement"], 1.0)
        self.assertAlmostEqual(result["confidence"], 0.9)

    def test_external_source_evidence_stays_in_review(self) -> None:
        client = FakeLLMClient(
            [
                {
                    "solution_status": "solved",
                    "derived_answers": ["a source-specific answer"],
                    "confidence": 1.0,
                    "needs_expert": False,
                    "required_assumptions": [],
                    "claims": [
                        {
                            "claim": "A source-specific fact",
                            "evidence_type": "external_source",
                            "support": "Not attached",
                        }
                    ],
                },
                {
                    "matches": [
                        {"label": "A", "relation": "not_equivalent", "confidence": 1.0},
                        {"label": "B", "relation": "equivalent", "confidence": 1.0},
                    ],
                    "needs_expert": False,
                },
                {
                    "option_assessments": [
                        {"label": "A", "status": "not_acceptable", "confidence": 1.0},
                        {"label": "B", "status": "acceptable", "confidence": 1.0},
                    ],
                    "question_mode": "identity",
                    "needs_expert": False,
                },
                {
                    "gold_validity": "invalid",
                    "defect_type": "wrong_gold_answer",
                    "alternative_answers": ["B"],
                    "confidence": 1.0,
                    "needs_expert": False,
                },
                {
                    "gold_support": "unsupported",
                    "confidence": 1.0,
                    "needs_expert": False,
                    "assumptions_required": [],
                },
            ]
        )
        item = BenchmarkItem(
            item_id="source-dependent",
            raw={},
            task="According to a source, which answer is right?",
            choices=["one", "two"],
            gold="A",
        )

        violations = list(EvidenceGoldLLMAuditor(client, mode="full").check(item))

        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].review_only)
        self.assertTrue(violations[0].evidence["llm_result"]["needs_expert"])

    def test_general_knowledge_mislabeled_as_external_can_be_confirmed(self) -> None:
        client = FakeLLMClient(
            [
                {
                    "solution_status": "solved",
                    "derived_answers": ["the stable textbook answer"],
                    "confidence": 0.95,
                    "needs_expert": False,
                    "assumption_risk": "none",
                    "required_assumptions": [],
                    "claims": [
                        {
                            "claim": "A stable textbook fact",
                            "evidence_type": "external_source",
                            "support": "General domain knowledge",
                        }
                    ],
                },
                {
                    "matches": [
                        {"label": "A", "relation": "not_equivalent", "confidence": 0.95},
                        {"label": "B", "relation": "equivalent", "confidence": 0.95},
                    ],
                    "needs_expert": False,
                },
                {
                    "option_assessments": [
                        {"label": "A", "status": "not_acceptable", "confidence": 0.95},
                        {"label": "B", "status": "acceptable", "confidence": 0.95},
                    ],
                    "question_mode": "identity",
                    "needs_expert": False,
                },
                {
                    "gold_validity": "invalid",
                    "defect_type": "wrong_gold_answer",
                    "alternative_answers": ["B"],
                    "confidence": 0.95,
                    "needs_expert": False,
                    "counterclaims": [],
                },
                {
                    "gold_support": "unsupported",
                    "confidence": 0.95,
                    "needs_expert": False,
                    "assumptions_required": [],
                    "claims": [],
                },
            ]
        )
        item = BenchmarkItem(
            item_id="general-knowledge",
            raw={},
            task="Which anatomical structure performs this function?",
            choices=["one", "two"],
            gold="A",
        )

        violations = list(EvidenceGoldLLMAuditor(client, mode="cascade").check(item))

        self.assertEqual(len(violations), 1)
        self.assertFalse(violations[0].review_only)

    def test_answer_option_matching_uses_equivalence_not_weak_implication(self) -> None:
        item = BenchmarkItem(
            item_id="algebra",
            raw={},
            task="What structure is formed?",
            choices=["commutative semigroup", "Abelian group"],
            gold="B",
        )
        blind = {
            "solution_status": "solved",
            "derived_answers": ["Abelian group"],
            "confidence": 0.95,
            "needs_expert": False,
        }
        matcher = {
            "matches": [
                {
                    "label": "A",
                    "relation": "not_equivalent",
                    "confidence": 0.95,
                },
                {
                    "label": "B",
                    "relation": "equivalent",
                    "confidence": 0.95,
                },
            ],
            "needs_expert": False,
        }

        evidence = option_match_evidence(item, blind, matcher)

        self.assertEqual(evidence["solution_status"], "solved")
        self.assertEqual(evidence["valid_answers"], ["B"])

    def test_independent_option_applicability_finds_non_equivalent_second_answer(self) -> None:
        item = BenchmarkItem(
            item_id="primes",
            raw={},
            task="Which number is prime?",
            choices=["2", "3", "4"],
            gold="A",
        )
        blind = {
            "solution_status": "solved",
            "derived_answers": ["2"],
            "confidence": 0.95,
            "needs_expert": False,
        }
        matcher = {
            "matches": [
                {"label": "A", "relation": "equivalent", "confidence": 0.95},
                {"label": "B", "relation": "not_equivalent", "confidence": 0.95},
                {"label": "C", "relation": "not_equivalent", "confidence": 0.95},
            ],
            "needs_expert": False,
        }
        applicability = {
            "option_assessments": [
                {"label": "A", "status": "acceptable", "confidence": 1.0},
                {"label": "B", "status": "acceptable", "confidence": 1.0},
                {"label": "C", "status": "not_acceptable", "confidence": 1.0},
            ],
            "question_mode": "property",
            "needs_expert": False,
        }

        evidence = option_match_evidence(item, blind, matcher, applicability)

        self.assertEqual(evidence["solution_status"], "multiple")
        self.assertEqual(evidence["valid_answers"], ["A", "B"])
        self.assertEqual(evidence["equivalent_answers"], ["A"])
        self.assertEqual(
            evidence["independently_acceptable_answers"],
            ["A", "B"],
        )

    def test_missing_independent_option_assessment_is_uncertain(self) -> None:
        item = BenchmarkItem(
            item_id="missing-assessment",
            raw={},
            task="Which option is correct?",
            choices=["one", "two", "three"],
            gold="A",
        )
        evidence = option_match_evidence(
            item,
            {
                "solution_status": "solved",
                "derived_answers": ["one"],
                "confidence": 1.0,
            },
            {
                "matches": [
                    {"label": "A", "relation": "equivalent", "confidence": 1.0}
                ]
            },
            {
                "option_assessments": [
                    {"label": "A", "status": "acceptable", "confidence": 1.0},
                    {"label": "B", "status": "not_acceptable", "confidence": 1.0},
                ]
            },
        )

        self.assertEqual(evidence["solution_status"], "uncertain")
        self.assertEqual(evidence["missing_option_assessments"], ["C"])

    def test_low_confidence_option_rejection_is_uncertain(self) -> None:
        item = BenchmarkItem(
            item_id="dc",
            raw={},
            task="In dc, charges flow",
            choices=["steadily in one direction", "in one direction"],
            gold="B",
        )
        evidence = option_match_evidence(
            item,
            {
                "solution_status": "solved",
                "derived_answers": ["in one direction"],
                "confidence": 1.0,
            },
            {
                "matches": [
                    {"label": "A", "relation": "not_equivalent", "confidence": 0.9},
                    {"label": "B", "relation": "equivalent", "confidence": 1.0},
                ]
            },
            {
                "option_assessments": [
                    {"label": "A", "status": "not_acceptable", "confidence": 0.7},
                    {"label": "B", "status": "acceptable", "confidence": 1.0},
                ]
            },
        )

        self.assertEqual(evidence["solution_status"], "uncertain")
        self.assertEqual(evidence["uncertain_answers"], ["A"])

    def test_applicability_multiple_signal_survives_later_disagreement(self) -> None:
        item = BenchmarkItem(
            item_id="multiple-signal",
            raw={},
            task="Which number is prime?",
            choices=["2", "3", "4"],
            gold="A",
        )
        evidence = {
            "solution_status": "multiple",
            "valid_answers": ["A", "B"],
            "uncertain_answers": [],
            "confidence": 0.95,
            "option_applicability": {
                "option_assessments": [
                    {"label": "A", "status": "acceptable", "confidence": 0.95},
                    {"label": "B", "status": "acceptable", "confidence": 0.90},
                    {"label": "C", "status": "not_acceptable", "confidence": 0.95},
                ]
            },
        }

        violations = list(option_applicability_violations(item, evidence))

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "multiple_correct_answers")
        self.assertTrue(violations[0].review_only)
        self.assertEqual(
            violations[0].detection_method,
            "llm_option_applicability",
        )

        # Gate: empty option_assessments prevents an unsubstantiated violation.
        empty_evidence = {**evidence, "option_applicability": {"option_assessments": []}}
        self.assertEqual(list(option_applicability_violations(item, empty_evidence)), [])

    def test_presentation_auditor_reports_silent_math_repair(self) -> None:
        item = BenchmarkItem(
            item_id="lost-exponent",
            raw={},
            task="How far is the star?",
            choices=["1.5 x 1017 meters"],
            gold="A",
        )
        result = {
            "issues": [
                {
                    "artifact": "choices",
                    "location": "choice A",
                    "issue_type": "lost_math_markup",
                    "raw_text": "1.5 x 1017 meters",
                    "interpreted_text": "1.5 × 10^17 meters",
                    "repair_operations": ["inserted exponent marker ^"],
                    "confidence": 0.98,
                    "rationale": "The exponent marker is missing.",
                }
            ],
            "confidence": 0.98,
        }

        violations = list(presentation_violations(item, result, 0.45))

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "presentation_corruption")
        self.assertEqual(violations[0].defect_scope, "presentation")
        self.assertEqual(violations[0].artifact, "expected_output")

    def test_presentation_auditor_ignores_explicit_numeric_representation(self) -> None:
        item = BenchmarkItem(
            item_id="numeric-format",
            raw={},
            task="What is the profit margin?",
            choices=["40.00%", "10.00%", "4.00%", "0.025"],
            gold="D",
        )

        violations = list(
            presentation_violations(
                item,
                {"issues": [], "confidence": 0.95},
                0.45,
            )
        )

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
