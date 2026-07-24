from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchcore.cli import main
from benchcore.trace_bundle import (
    TRACE_SCHEMA_VERSION,
    analyze_trace_bundle,
    load_trace_bundle,
    trace_response_rows,
    write_trace_audit_markdown,
)


def _run(
    run_id: str,
    item_id: str,
    system_id: str,
    attempt: int,
    *,
    status: str = "passed",
    correct: bool | None = True,
    score: float | None = 1.0,
    reward: float | None = None,
    control_id: str | None = None,
    control_kind: str | None = None,
    events: list[dict] | None = None,
    artifacts: list[dict] | None = None,
    evaluations: list[dict] | None = None,
) -> dict:
    outcome = {"status": status, "correct": correct, "score": score}
    if reward is not None:
        outcome["reward"] = reward
    return {
        "run_id": run_id,
        "item_id": item_id,
        "system_id": system_id,
        "attempt": attempt,
        "control_id": control_id,
        "control_kind": control_kind,
        "outcome": outcome,
        "events": events or [],
        "artifacts": artifacts or [],
        "evaluations": evaluations or [],
        "metadata": {},
    }


def _document(runs: list[dict]) -> dict:
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "benchmark_id": "fixture-benchmark",
        "runs": runs,
    }


def _write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


class TraceBundleLoadingTest(unittest.TestCase):
    def test_bundle_is_sorted_by_identifiers_not_source_row_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traces.json"
            _write_json(
                path,
                _document(
                    [
                        _run("r2", "q2", "m1", 0),
                        _run("r1", "q1", "m1", 0),
                    ]
                ),
            )
            bundle = load_trace_bundle([path])
        self.assertEqual([run.run_id for run in bundle.runs], ["r1", "r2"])
        self.assertEqual(bundle.item_ids, ["q1", "q2"])
        self.assertEqual(bundle.system_ids, ["m1"])
        self.assertEqual(len(bundle.sources), 1)
        self.assertEqual(len(bundle.sources[0]["sha256"]), 64)

    def test_jsonl_rows_require_explicit_version_and_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traces.jsonl"
            rows = [
                {
                    "schema_version": TRACE_SCHEMA_VERSION,
                    "benchmark_id": "fixture-benchmark",
                    **_run("r1", "q1", "m1", 0),
                },
                {
                    "schema_version": TRACE_SCHEMA_VERSION,
                    "benchmark_id": "fixture-benchmark",
                    **_run("r2", "q2", "m1", 0),
                },
            ]
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            bundle = load_trace_bundle([path])
        self.assertEqual(len(bundle.runs), 2)

    def test_duplicate_run_id_is_rejected_across_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.json"
            second = Path(tmp) / "second.json"
            _write_json(first, _document([_run("r1", "q1", "m1", 0)]))
            _write_json(second, _document([_run("r1", "q2", "m1", 0)]))
            with self.assertRaisesRegex(ValueError, "duplicate run_id"):
                load_trace_bundle([first, second])

    def test_duplicate_item_system_attempt_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traces.json"
            _write_json(
                path,
                _document(
                    [
                        _run("r1", "q1", "m1", 0),
                        _run("r2", "q1", "m1", 0),
                    ]
                ),
            )
            with self.assertRaisesRegex(
                ValueError, r"duplicate \(item_id, system_id, attempt\)"
            ):
                load_trace_bundle([path])

    def test_unknown_fields_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traces.json"
            run = _run("r1", "q1", "m1", 0)
            run["succes"] = True
            _write_json(path, _document([run]))
            with self.assertRaisesRegex(ValueError, "unknown field"):
                load_trace_bundle([path])

    def test_row_level_identity_cannot_override_bundle_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traces.json"
            run = _run("r1", "q1", "m1", 0)
            run["benchmark_id"] = "different-benchmark"
            _write_json(path, _document([run]))
            with self.assertRaisesRegex(ValueError, "does not match file benchmark_id"):
                load_trace_bundle([path])

    def test_string_correctness_is_not_coerced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traces.json"
            run = _run("r1", "q1", "m1", 0)
            run["outcome"]["correct"] = "false"
            _write_json(path, _document([run]))
            with self.assertRaisesRegex(ValueError, "JSON boolean"):
                load_trace_bundle([path])

    def test_artifact_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traces.json"
            run = _run(
                "r1",
                "q1",
                "m1",
                0,
                artifacts=[
                    {
                        "artifact_id": "out",
                        "role": "output",
                        "path": "../secret.txt",
                    }
                ],
            )
            _write_json(path, _document([run]))
            with self.assertRaisesRegex(ValueError, "must not contain"):
                load_trace_bundle([path])

    def test_windows_absolute_artifact_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traces.json"
            run = _run(
                "r1",
                "q1",
                "m1",
                0,
                artifacts=[
                    {
                        "artifact_id": "out",
                        "role": "output",
                        "path": "C:\\private\\answer.txt",
                    }
                ],
            )
            _write_json(path, _document([run]))
            with self.assertRaisesRegex(ValueError, "must be relative"):
                load_trace_bundle([path])

    def test_event_sequences_must_be_monotonic_and_unique(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traces.json"
            run = _run(
                "r1",
                "q1",
                "m1",
                0,
                events=[
                    {"sequence": 1, "event_type": "tool"},
                    {"sequence": 0, "event_type": "tool"},
                ],
            )
            _write_json(path, _document([run]))
            with self.assertRaisesRegex(ValueError, "monotonically increasing"):
                load_trace_bundle([path])

    def test_normalized_document_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.json"
            normalized = Path(tmp) / "normalized.json"
            _write_json(source, _document([_run("r1", "q1", "m1", 0)]))
            first = load_trace_bundle([source])
            _write_json(normalized, first.to_document())
            second = load_trace_bundle([normalized])
        self.assertEqual(first.benchmark_id, second.benchmark_id)
        self.assertEqual(first.runs, second.runs)


class TraceBundleAnalysisTest(unittest.TestCase):
    def _load(self, runs: list[dict]):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "traces.json"
        _write_json(path, _document(runs))
        return load_trace_bundle([path])

    def test_consistency_candidates_are_review_only(self) -> None:
        digest_a = "a" * 64
        digest_b = "b" * 64
        bundle = self._load(
            [
                _run(
                    "r1",
                    "q1",
                    "m1",
                    0,
                    status="passed",
                    score=0.95,
                    control_id="same-q1",
                    control_kind="identical",
                    artifacts=[
                        {
                            "artifact_id": "out",
                            "role": "output",
                            "path": "answer.txt",
                            "sha256": digest_a,
                        }
                    ],
                ),
                _run(
                    "r2",
                    "q1",
                    "m1",
                    1,
                    status="failed",
                    correct=False,
                    score=0.40,
                    control_id="same-q1",
                    control_kind="identical",
                    artifacts=[
                        {
                            "artifact_id": "out",
                            "role": "output",
                            "path": "answer.txt",
                            "sha256": digest_b,
                        }
                    ],
                ),
                _run(
                    "r3",
                    "q2",
                    "m2",
                    0,
                    correct=False,
                    events=[
                        {
                            "sequence": 0,
                            "event_type": "process_exit",
                            "attributes": {"exit_code": 7},
                        }
                    ],
                ),
                _run(
                    "r4",
                    "q3",
                    "m3",
                    0,
                    status="failed",
                    correct=False,
                    score=0.0,
                    reward=0.99,
                    evaluations=[
                        {
                            "evaluator_id": "judge-a",
                            "rubric_id": "rubric-1",
                            "verdict": "pass",
                            "score": 1.0,
                        },
                        {
                            "evaluator_id": "judge-b",
                            "rubric_id": "rubric-1",
                            "verdict": "fail",
                            "score": 0.0,
                        },
                    ],
                ),
            ]
        )
        result = analyze_trace_bundle(bundle)
        defect_types = {row["defect_type"] for row in result["candidates"]}
        self.assertTrue(
            {
                "identical_control_mismatch",
                "pass_with_execution_error",
                "reward_verdict_mismatch",
                "evaluator_verdict_disagreement",
                "outcome_correctness_mismatch",
            }.issubset(defect_types)
        )
        identical = next(
            row
            for row in result["candidates"]
            if row["defect_type"] == "identical_control_mismatch"
        )
        self.assertEqual(
            identical["evidence"]["mismatch_modalities"],
            ["outcome", "score", "artifact"],
        )
        self.assertNotIn("repeated_outcome_disagreement", defect_types)
        self.assertNotIn("repeated_score_instability", defect_types)
        self.assertEqual(result["promotion_ceiling"], "review")
        self.assertFalse(result["confirmation_eligible"])
        for candidate in result["candidates"]:
            self.assertEqual(candidate["evidence_tier"], "review")
            self.assertTrue(candidate["review_only"])
            self.assertFalse(candidate["confirmation_eligible"])

    def test_infrastructure_cluster_is_dataset_level_review(self) -> None:
        bundle = self._load(
            [
                _run(
                    f"r{index}",
                    f"q{index}",
                    "m1",
                    0,
                    status="timeout" if index < 2 else "passed",
                    correct=None,
                    score=None,
                )
                for index in range(5)
            ]
        )
        result = analyze_trace_bundle(bundle)
        cluster = next(
            row
            for row in result["candidates"]
            if row["defect_type"] == "infrastructure_failure_cluster"
        )
        self.assertEqual(cluster["evidence"]["rate"], 0.4)
        self.assertEqual(len(cluster["item_ids"]), 2)

    def test_non_control_repeats_keep_generic_instability_candidates(self) -> None:
        bundle = self._load(
            [
                _run("r1", "q1", "m1", 0, status="passed", score=0.9),
                _run(
                    "r2",
                    "q1",
                    "m1",
                    1,
                    status="failed",
                    correct=False,
                    score=0.2,
                ),
            ]
        )
        result = analyze_trace_bundle(bundle)
        defect_types = {row["defect_type"] for row in result["candidates"]}
        self.assertIn("repeated_outcome_disagreement", defect_types)
        self.assertIn("repeated_score_instability", defect_types)

    def test_response_export_uses_aligned_attempt_columns(self) -> None:
        bundle = self._load(
            [
                _run("q1-a0", "q1", "m1", 0, correct=True),
                _run("q1-a1", "q1", "m1", 1, correct=False),
                _run("q2-a0", "q2", "m1", 0, correct=False),
                _run("q2-a1", "q2", "m1", 1, correct=True),
                _run("q1-m2", "q1", "m2", 0, correct=True),
            ]
        )
        rows = trace_response_rows(bundle)
        by_run = {row["source_run_id"]: row for row in rows}
        self.assertEqual(by_run["q1-a0"]["model_id"], "m1#attempt=0")
        self.assertEqual(by_run["q2-a0"]["model_id"], "m1#attempt=0")
        self.assertEqual(by_run["q1-a1"]["model_id"], "m1#attempt=1")
        self.assertEqual(by_run["q1-m2"]["model_id"], "m2")

    def test_markdown_explicitly_states_review_boundary(self) -> None:
        bundle = self._load([_run("r1", "q1", "m1", 0)])
        result = analyze_trace_bundle(bundle)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            write_trace_audit_markdown(path, result)
            text = path.read_text(encoding="utf-8")
        self.assertIn("review-only", text)
        self.assertIn("independent verifier", text)
        self.assertIn("Quality warnings", text)

    def test_cli_writes_all_requested_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "traces.json"
            _write_json(
                source,
                _document(
                    [
                        _run("r1", "q1", "m1", 0),
                        _run(
                            "r2",
                            "q1",
                            "m1",
                            1,
                            status="failed",
                            correct=False,
                            score=0.0,
                        ),
                    ]
                ),
            )
            exit_code = main(
                [
                    "triage-traces",
                    str(source),
                    "--out",
                    str(root / "audit.json"),
                    "--md",
                    str(root / "audit.md"),
                    "--normalized-out",
                    str(root / "normalized.json"),
                    "--responses-out",
                    str(root / "responses.jsonl"),
                ]
            )
            self.assertEqual(exit_code, 0)
            for name in (
                "audit.json",
                "audit.md",
                "normalized.json",
                "responses.jsonl",
            ):
                self.assertTrue((root / name).is_file(), name)
            normalized = load_trace_bundle([root / "normalized.json"])
            self.assertEqual(len(normalized.runs), 2)


if __name__ == "__main__":
    unittest.main()
