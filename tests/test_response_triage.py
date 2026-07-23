from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchcore.response_triage import (
    build_response_triage,
    load_response_matrix,
    write_response_triage_markdown,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


class ResponseMatrixLoadingTest(unittest.TestCase):
    def test_per_model_files_are_joined_by_id_not_row_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_jsonl(
                root / "model-a.jsonl",
                [
                    {"id": "q1", "correct": True},
                    {"id": "q2", "correct": False},
                ],
            )
            _write_jsonl(
                root / "model-b.jsonl",
                [
                    {"id": "q2", "correct": True},
                    {"id": "q1", "correct": False},
                ],
            )
            matrix = load_response_matrix([root])
        self.assertEqual(
            matrix.values,
            {
                "q1": {"model-a": True, "model-b": False},
                "q2": {"model-a": False, "model-b": True},
            },
        )

    def test_feature_document_wide_correctness_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.json"
            path.write_text(
                json.dumps(
                    {
                        "items": {
                            "q1": {"correct": {"m1": True, "m2": False}},
                            "q2": {"correct": {"m1": False, "m2": False}},
                        }
                    }
                ),
                encoding="utf-8",
            )
            matrix = load_response_matrix([path])
        self.assertEqual(matrix.item_ids, ["q1", "q2"])
        self.assertEqual(matrix.model_ids, ["m1", "m2"])

    def test_long_form_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "responses.jsonl"
            _write_jsonl(
                path,
                [
                    {"item_id": "q1", "model_id": "m1", "correct": 1},
                    {"item_id": "q1", "model_id": "m2", "correct": 0},
                ],
            )
            matrix = load_response_matrix([path])
        self.assertEqual(matrix.values["q1"], {"m1": True, "m2": False})

    def test_duplicate_item_model_pair_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "responses.jsonl"
            _write_jsonl(
                path,
                [
                    {"item_id": "q1", "model_id": "m1", "correct": True},
                    {"item_id": "q1", "model_id": "m1", "correct": True},
                ],
            )
            with self.assertRaisesRegex(ValueError, "duplicate response pair"):
                load_response_matrix([path])

    def test_string_correctness_is_rejected_instead_of_truthy_coercion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "responses.jsonl"
            _write_jsonl(
                path,
                [{"item_id": "q1", "model_id": "m1", "correct": "false"}],
            )
            with self.assertRaisesRegex(ValueError, "JSON boolean"):
                load_response_matrix([path])


class ResponseTriageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = type(
            "MatrixFixture",
            (),
            {
                "values": {
                    "q1": {"m1": False, "m2": False, "m3": False},
                    "q2": {"m1": True, "m2": True, "m3": True},
                    "q3": {"m1": True, "m2": False, "m3": True},
                    "q4": {"m1": False, "m2": True, "m3": True},
                },
                "sources": [],
                "item_ids": ["q1", "q2", "q3", "q4"],
                "model_ids": ["m1", "m2", "m3"],
                "validate": lambda fixture, minimum_models: (
                    None
                    if minimum_models <= 3
                    else (_ for _ in ()).throw(ValueError("below minimum"))
                ),
            },
        )()
        self.report = {
            "violations": [
                {
                    "item_id": "q2",
                    "defect_type": "wrong_gold_answer",
                    "defect_scope": "substantive",
                    "detection_method": "arithmetic_replay",
                    "confidence": 1.0,
                    "review_only": False,
                    "evidence": {},
                }
            ]
        }

    def test_fusion_is_always_review_only_even_with_confirmed_audit_input(self) -> None:
        result = build_response_triage(
            self.matrix,
            self.report,
            minimum_models=3,
            minimum_responses_per_item=3,
        )
        self.assertEqual(result["promotion_ceiling"], "review")
        self.assertFalse(result["confirmation_eligible"])
        self.assertEqual(len(result["items"]), 4)
        for row in result["items"]:
            self.assertTrue(row["review_only"])
            self.assertEqual(row["evidence_tier"], "review")
            self.assertFalse(row["confirmation_eligible"])

    def test_error_rate_and_wilson_interval_are_reported(self) -> None:
        result = build_response_triage(
            self.matrix,
            {"violations": []},
            minimum_models=3,
            minimum_responses_per_item=3,
        )
        by_id = {row["item_id"]: row for row in result["items"]}
        self.assertEqual(by_id["q1"]["error_rate"], 1.0)
        self.assertEqual(by_id["q2"]["error_rate"], 0.0)
        self.assertAlmostEqual(by_id["q3"]["error_rate"], 1 / 3)
        self.assertLess(by_id["q1"]["error_rate_ci95"][0], 1.0)
        self.assertGreater(by_id["q2"]["error_rate_ci95"][1], 0.0)

    def test_incomplete_item_does_not_receive_behavior_fusion(self) -> None:
        del self.matrix.values["q3"]["m3"]
        result = build_response_triage(
            self.matrix,
            self.report,
            minimum_models=3,
            minimum_responses_per_item=3,
            minimum_model_coverage=0.0,
        )
        q3 = next(row for row in result["items"] if row["item_id"] == "q3")
        self.assertFalse(q3["fusion_applied"])
        self.assertIsNone(q3["behavior_percentile"])
        self.assertEqual(q3["fused_score"], q3["audit_percentile"])

    def test_low_coverage_models_do_not_satisfy_panel_gate(self) -> None:
        del self.matrix.values["q3"]["m3"]
        del self.matrix.values["q4"]["m3"]
        with self.assertRaisesRegex(ValueError, "meet minimum_model_coverage"):
            build_response_triage(
                self.matrix,
                self.report,
                minimum_models=3,
                minimum_responses_per_item=2,
                minimum_model_coverage=0.8,
            )

    def test_duplicate_model_behavior_disables_fusion(self) -> None:
        for row in self.matrix.values.values():
            row["m2"] = row["m1"]
            row["m3"] = row["m1"]
        result = build_response_triage(
            self.matrix,
            self.report,
            minimum_models=3,
            minimum_responses_per_item=3,
        )
        self.assertFalse(result["quality"]["panel_behavior_eligible"])
        self.assertIn("fusion is disabled", result["quality"]["warnings"][0])
        self.assertTrue(all(not row["fusion_applied"] for row in result["items"]))

    def test_default_fusion_excludes_single_exploratory_audit_signal(self) -> None:
        weak_report = {
            "violations": [
                {
                    "item_id": "q2",
                    "defect_type": "missing_accepted_alternatives",
                    "defect_scope": "substantive",
                    "detection_method": "static_rule",
                    "confidence": 0.9,
                    "review_only": True,
                    "evidence": {},
                }
            ]
        }
        result = build_response_triage(
            self.matrix,
            weak_report,
            minimum_models=3,
            minimum_responses_per_item=3,
        )
        q2 = next(row for row in result["items"] if row["item_id"] == "q2")
        self.assertEqual(q2["audit_score"], 0.0)
        self.assertEqual(
            result["audit"]["items_excluded_from_fusion_as_exploratory"], 1
        )

        legacy = build_response_triage(
            self.matrix,
            weak_report,
            minimum_models=3,
            minimum_responses_per_item=3,
            audit_score_mode="risk",
        )
        legacy_q2 = next(
            row for row in legacy["items"] if row["item_id"] == "q2"
        )
        self.assertGreater(legacy_q2["audit_score"], 0.0)

    def test_panel_provenance_does_not_overclaim_independence(self) -> None:
        unspecified = build_response_triage(
            self.matrix,
            self.report,
            minimum_models=3,
            minimum_responses_per_item=3,
        )
        self.assertFalse(unspecified["panel_independence"]["claimed"])
        self.assertTrue(
            any(
                "provenance is unspecified" in warning
                for warning in unspecified["quality"]["warnings"]
            )
        )

        views = build_response_triage(
            self.matrix,
            self.report,
            minimum_models=3,
            minimum_responses_per_item=3,
            panel_kind="single-model-views",
        )
        self.assertFalse(views["panel_independence"]["claimed"])
        self.assertTrue(
            any(
                "correlated views" in warning
                for warning in views["quality"]["warnings"]
            )
        )

        models = build_response_triage(
            self.matrix,
            self.report,
            minimum_models=3,
            minimum_responses_per_item=3,
            panel_kind="independent-models",
        )
        self.assertTrue(models["panel_independence"]["claimed"])
        self.assertIn("caller-declared", models["panel_independence"]["basis"])

    def test_minimum_model_gate_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "below minimum"):
            build_response_triage(
                self.matrix,
                self.report,
                minimum_models=4,
                minimum_responses_per_item=3,
            )

    def test_markdown_states_observational_boundary(self) -> None:
        result = build_response_triage(
            self.matrix,
            self.report,
            minimum_models=3,
            minimum_responses_per_item=3,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "triage.md"
            write_response_triage_markdown(path, result, top_k=2)
            text = path.read_text(encoding="utf-8")
        self.assertIn("review-only", text)
        self.assertIn("difficulty rather than a benchmark defect", text)
        self.assertIn("Top 2", text)


if __name__ == "__main__":
    unittest.main()
