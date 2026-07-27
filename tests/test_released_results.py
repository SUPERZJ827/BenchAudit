from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchcore.released_results import (
    ReleasedResultMapping,
    ReleasedResultSource,
    adapt_released_results,
    analyze_released_results,
)
from benchcore.auditor import audit_items
from benchcore.checkers import TaskSpecChecker
from benchcore.field_mapping import mapping_from_dict
from benchcore.loader import build_items
from benchcore.promotion import enforce_promotion_policy
from benchcore.trace_bundle import analyze_trace_bundle


class ReleasedResultAdapterTest(unittest.TestCase):
    def test_common_jsonl_fields_are_inferred_and_joined_by_item_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "model-a.jsonl"
            second = root / "model-b.jsonl"
            first.write_text(
                "\n".join(
                    [
                        json.dumps({
                            "questionId": 2,
                            "question": "second",
                            "answer": "B",
                            "prediction": "same answer",
                            "judge": "T",
                        }),
                        json.dumps({
                            "questionId": 1,
                            "question": "first",
                            "answer": "A",
                            "prediction": "same answer",
                            "judge": "F",
                        }),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            second.write_text(
                "\n".join(
                    [
                        json.dumps({
                            "questionId": 1,
                            "question": "first",
                            "answer": "A",
                            "prediction": "same answer",
                            "judge": "T",
                        }),
                        json.dumps({
                            "questionId": 2,
                            "question": "second",
                            "answer": "B",
                            "prediction": "different",
                            "judge": "F",
                        }),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            bundle = adapt_released_results(
                [
                    ReleasedResultSource(first, system_id="model-a"),
                    ReleasedResultSource(second, system_id="model-b"),
                ],
                benchmark_id="fixture",
            )

        self.assertEqual(bundle.item_ids, ["1", "2"])
        self.assertEqual(bundle.system_ids, ["model-a", "model-b"])
        self.assertEqual(len(bundle.runs), 4)
        trace_result = analyze_trace_bundle(bundle)
        mismatch = next(
            candidate
            for candidate in trace_result["candidates"]
            if candidate["defect_type"]
            == "output_equivalent_evaluation_mismatch"
        )
        self.assertEqual(mismatch["item_ids"], ["1"])
        self.assertTrue(mismatch["review_only"])
        self.assertFalse(mismatch["confirmation_eligible"])

    def test_ambiguous_item_fields_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ambiguous.jsonl"
            path.write_text(
                json.dumps({
                    "id": "a",
                    "item_id": "b",
                    "prediction": "x",
                    "answer": "x",
                    "judge": "T",
                })
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "ambiguous item_id"):
                adapt_released_results(
                    [ReleasedResultSource(path)],
                    benchmark_id="fixture",
                )

    def test_dict_of_records_can_use_top_level_key_as_item_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dbcode.json"
            path.write_text(
                json.dumps({
                    "substr": {
                        "response": {"Answer": "implementation"},
                        "origin_code": "reference implementation",
                        "is_success": False,
                        "is_success_func": True,
                    }
                }),
                encoding="utf-8",
            )
            mapping = ReleasedResultMapping(
                item_id="__key__",
                prediction="response",
                reference="origin_code",
                evaluations=(
                    ("full_harness", "is_success"),
                    ("function_tests", "is_success_func"),
                ),
                reference_contract="code",
            )
            bundle = adapt_released_results(
                [
                    ReleasedResultSource(
                        path,
                        system_id="model-a",
                        mapping=mapping,
                    )
                ],
                benchmark_id="dbcode",
            )

        self.assertEqual(bundle.item_ids, ["substr"])
        run = bundle.runs[0]
        self.assertEqual(run.outcome.status, "unknown")
        self.assertIsNone(run.outcome.correct)
        self.assertEqual(
            [(row.evaluator_id, row.verdict) for row in run.evaluations],
            [("full_harness", "fail"), ("function_tests", "pass")],
        )
        result = analyze_trace_bundle(bundle)
        self.assertIn(
            "evaluator_verdict_disagreement",
            {candidate["defect_type"] for candidate in result["candidates"]},
        )

    def test_duplicate_item_system_rows_become_explicit_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repeats.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps({
                        "item_id": "q1",
                        "prediction": value,
                        "reference": "gold",
                        "correct": correct,
                    })
                    for value, correct in (("a", True), ("b", False))
                )
                + "\n",
                encoding="utf-8",
            )
            bundle = adapt_released_results(
                [ReleasedResultSource(path, system_id="model")],
                benchmark_id="fixture",
            )

        self.assertEqual([run.attempt for run in bundle.runs], [0, 1])

    def test_run_identity_is_stable_when_source_is_relocated(self) -> None:
        payload = (
            json.dumps({
                "item_id": "q1",
                "prediction": "answer",
                "reference": "gold",
                "correct": True,
            })
            + "\n"
        )
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = Path(first_tmp) / "result.jsonl"
            second = Path(second_tmp) / "result.jsonl"
            first.write_text(payload, encoding="utf-8")
            second.write_text(payload, encoding="utf-8")
            first_bundle = adapt_released_results(
                [ReleasedResultSource(first, system_id="model")],
                benchmark_id="fixture",
            )
            second_bundle = adapt_released_results(
                [ReleasedResultSource(second, system_id="model")],
                benchmark_id="fixture",
            )

        self.assertEqual(
            [run.run_id for run in first_bundle.runs],
            [run.run_id for run in second_bundle.runs],
        )

    def test_missing_prediction_is_not_a_comparable_output_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.jsonl"
            path.write_text(
                json.dumps({
                    "item_id": "q1",
                    "prediction": None,
                    "reference": "gold",
                    "correct": False,
                })
                + "\n",
                encoding="utf-8",
            )
            bundle = adapt_released_results(
                [ReleasedResultSource(path, system_id="model")],
                benchmark_id="fixture",
            )

        self.assertEqual(bundle.runs[0].artifacts, ())


class ReleasedResultAuditTest(unittest.TestCase):
    def _adapt(
        self,
        documents: list[tuple[str, list[dict]]],
        *,
        mapping: ReleasedResultMapping,
    ):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        sources = []
        for system_id, rows in documents:
            path = root / f"{system_id}.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            sources.append(
                ReleasedResultSource(path, system_id=system_id, mapping=mapping)
            )
        return adapt_released_results(sources, benchmark_id="fixture")

    def test_sql_diagnostic_references_are_one_dataset_level_candidate(self) -> None:
        mapping = ReleasedResultMapping(
            item_id="item_id",
            prediction="prediction",
            reference="reference",
            evaluations=(("syntax", "valid"),),
            reference_contract="sql",
        )
        bundle = self._adapt(
            [
                (
                    "model-a",
                    [
                        {
                            "item_id": "q1",
                            "prediction": "SELECT 1",
                            "reference": (
                                "Invalid expression / Unexpected token. "
                                "Line 1, Col: 3.\n  SELECT"
                            ),
                            "valid": True,
                        },
                        {
                            "item_id": "q2",
                            "prediction": "SELECT 2",
                            "reference": "Expecting ). Line 1, Col: 7.\n SELECT",
                            "valid": False,
                        },
                        {
                            "item_id": "q3",
                            "prediction": "SELECT 'Invalid expression'",
                            "reference": "SELECT 'Invalid expression'",
                            "valid": True,
                        },
                    ],
                )
            ],
            mapping=mapping,
        )
        result = analyze_released_results(bundle)

        diagnostic = next(
            candidate
            for candidate in result["candidates"]
            if candidate["defect_type"] == "reference_diagnostic_payload"
        )
        self.assertEqual(diagnostic["item_ids"], ["q1", "q2"])
        self.assertEqual(diagnostic["evidence"]["affected_items"], 2)
        self.assertEqual(
            len([
                candidate
                for candidate in result["candidates"]
                if candidate["defect_type"] == "reference_diagnostic_payload"
            ]),
            1,
        )
        self.assertTrue(diagnostic["review_only"])
        self.assertFalse(diagnostic["confirmation_eligible"])

    def test_reference_version_drift_is_grouped_across_systems(self) -> None:
        mapping = ReleasedResultMapping(
            item_id="item_id",
            prediction="prediction",
            reference="reference",
            evaluations=(("judge", "judge"),),
        )
        bundle = self._adapt(
            [
                (
                    "old-run",
                    [{
                        "item_id": "q1",
                        "prediction": "new",
                        "reference": "old",
                        "judge": "F",
                    }],
                ),
                (
                    "new-run",
                    [{
                        "item_id": "q1",
                        "prediction": "new",
                        "reference": "new",
                        "judge": "T",
                    }],
                ),
            ],
            mapping=mapping,
        )
        result = analyze_released_results(bundle)
        drift = next(
            candidate
            for candidate in result["candidates"]
            if candidate["defect_type"] == "reference_version_disagreement"
        )
        self.assertEqual(drift["item_ids"], ["q1"])
        self.assertEqual(drift["evidence"]["affected_items"], 1)
        self.assertEqual(drift["evidence"]["reference_versions"], 2)

    def test_published_reference_failures_are_dataset_level_review(self) -> None:
        mapping = ReleasedResultMapping(
            item_id="item_id",
            prediction="prediction",
            reference="reference",
            evaluations=(("prediction_syntax", "valid"),),
            reference_evaluations=(("reference_syntax", "reference_valid"),),
            reference_contract="sql",
        )
        bundle = self._adapt(
            [
                (
                    "model",
                    [
                        {
                            "item_id": "q1",
                            "prediction": "SELECT 1",
                            "reference": "SELECT (",
                            "valid": True,
                            "reference_valid": False,
                        },
                        {
                            "item_id": "q2",
                            "prediction": "SELECT 2",
                            "reference": "SELECT 2",
                            "valid": True,
                            "reference_valid": True,
                        },
                    ],
                )
            ],
            mapping=mapping,
        )
        result = analyze_released_results(bundle)
        candidate = next(
            row
            for row in result["candidates"]
            if row["defect_type"] == "published_reference_evaluator_failure"
        )
        self.assertEqual(candidate["item_ids"], ["q1"])
        self.assertEqual(candidate["evidence"]["affected_items"], 1)
        self.assertTrue(candidate["review_only"])

    def test_all_released_result_candidates_are_review_only(self) -> None:
        mapping = ReleasedResultMapping(
            item_id="item_id",
            prediction="prediction",
            reference="reference",
            evaluations=(("syntax", "valid"),),
            reference_contract="sql",
        )
        bundle = self._adapt(
            [
                (
                    "model",
                    [{
                        "item_id": "q1",
                        "prediction": "SELECT 1",
                        "reference": "Traceback (most recent call last):\nboom",
                        "valid": False,
                    }],
                )
            ],
            mapping=mapping,
        )
        result = analyze_released_results(bundle)
        self.assertEqual(result["promotion_ceiling"], "review")
        self.assertFalse(result["confirmation_eligible"])
        self.assertGreater(result["candidate_count"], 0)
        for candidate in result["candidates"]:
            self.assertEqual(candidate["evidence_tier"], "review")
            self.assertTrue(candidate["review_only"])
            self.assertFalse(candidate["confirmation_eligible"])

    def test_central_promotion_caps_released_result_provenance(self) -> None:
        mapping = mapping_from_dict({"item_id": "id", "task": "question"})
        item = build_items([{"id": "one"}], mapping)[0]
        finding = audit_items([item], checkers=[TaskSpecChecker()])[0]
        self.assertEqual(finding.evidence_tier, "confirmed")

        finding.evidence["released_result_source_sha256"] = "a" * 64
        enforce_promotion_policy(finding, item)
        self.assertEqual(finding.evidence_tier, "review")
        self.assertEqual(finding.proof_kind, "historical_result_observation")
        self.assertTrue(finding.review_only)


if __name__ == "__main__":
    unittest.main()
