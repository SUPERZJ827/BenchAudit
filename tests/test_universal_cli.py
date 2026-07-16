import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch, sentinel

from benchcore.cli import main
from benchcore.gold_study import build_gold_study
from benchcore.investigator import investigate_audit_report


def test_plan_command_writes_machine_and_human_readable_outputs(tmp_path: Path):
    package = tmp_path / "benchmark"
    package.mkdir()
    (package / "tasks.jsonl").write_text('{"id":"1","question":"q"}\n', encoding="utf-8")
    output = tmp_path / "plan.json"
    markdown = tmp_path / "plan.md"

    exit_code = main(["plan", str(package), "--out", str(output), "--md", str(markdown)])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["benchmark_package"]["schema_version"] == "1.0"
    assert payload["audit_plan"]["artifact_coverage"]["task_specification"] == "present"
    assert "Benchmark Audit Plan" in markdown.read_text(encoding="utf-8")


def test_inject_defects_command_writes_provenance_manifest(tmp_path: Path):
    source = tmp_path / "questions.jsonl"
    source.write_text(
        json.dumps({
            "id": "q1", "question": "2+2?", "choices": ["3", "4"],
            "answer": "4", "evaluator": "exact",
        }) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "mutated.jsonl"
    manifest = tmp_path / "manifest.json"

    exit_code = main([
        "inject-defects", str(source), "--operator", "wrong_gold",
        "--out", str(output), "--manifest-out", str(manifest),
    ])

    assert exit_code == 0
    mutated = json.loads(output.read_text(encoding="utf-8").strip())
    provenance = json.loads(manifest.read_text(encoding="utf-8"))
    assert mutated["answer"] != "4"
    assert mutated["_injected_defect"]["defect_type"] == "wrong_gold_answer"
    assert provenance["mutated_items"] == 1


def test_audit_report_includes_package_and_coverage(tmp_path: Path):
    source = tmp_path / "questions.jsonl"
    source.write_text(
        json.dumps({
            "id": "q1", "question": "2+2?", "answer": "4",
            "output_format": "number", "evaluator": "exact",
        }) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "audit.json"

    exit_code = main([
        "audit", str(source), "--out", str(output), "--progress-every", "0",
    ])

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["benchmark_package"]["schema_version"] == "1.0"
    assert report["audit_plan"]["summary"]["executed"] > 0
    assert report["audit_plan"]["artifact_coverage"]["oracle_ground_truth"] == "present"


def test_codeexec_auditor_requires_an_explicit_execution_backend(tmp_path: Path):
    source = tmp_path / "table.jsonl"
    source.write_text(json.dumps({
        "item_id": "table-1",
        "task": "sum amount",
        "table": "| amount |\n|---|\n| 1 |\n| 2 |",
        "gold": "3",
    }) + "\n", encoding="utf-8")

    with unittest.TestCase().assertRaisesRegex(
        ValueError, "generated-code audits require --execution-container-image",
    ):
        main([
            "audit", str(source), "--llm-audit", "--llm-auditors", "codeexec",
            "--llm-dry-run", "--out", str(tmp_path / "blocked.json"),
        ])


def test_offset_row_uids_join_exact_rows_in_investigation_and_gold_study(
    tmp_path: Path,
):
    source = tmp_path / "offset.jsonl"
    source.write_text("\n".join(json.dumps(row) for row in [
        {"item_id": "skip", "task": "unselected row"},
        {"item_id": "dup", "task": "first selected duplicate"},
        {"item_id": "dup", "task": "second selected duplicate"},
        {"item_id": "tail", "task": "unselected tail"},
    ]) + "\n", encoding="utf-8")
    report_path = tmp_path / "offset-report.json"

    assert main([
        "audit", str(source), "--offset", "1", "--limit", "2",
        "--out", str(report_path), "--progress-every", "0",
    ]) == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    duplicate = next(
        row for row in report["violations"]
        if row["defect_type"] == "duplicate_item_id"
    )
    assert duplicate["row_uid"] == "source-row-00000001"
    assert duplicate["evidence"]["target_row_uids"] == [
        "source-row-00000001", "source-row-00000002",
    ]
    assert len(duplicate["source_row_sha256"]) == 64
    assert report["source_identity"]["row_uid_scheme"] == (
        "zero_based_original_source_index"
    )

    client = FakeCrossArtifactClient()
    investigation = investigate_audit_report(
        input_path=source,
        report_path=report_path,
        client=client,
        include_defects={"duplicate_item_id"},
        progress_every=0,
    )
    assert investigation["investigations"][0]["row_uid"] == (
        "source-row-00000001"
    )
    assert "first selected duplicate" in client.calls[0][1]
    assert "unselected row" not in client.calls[0][1]

    study = build_gold_study(
        input_path=source,
        report_path=report_path,
        investigation_path=None,
        flagged_size=2,
        unflagged_size=0,
        seed=9,
    )
    assert {row["row_uid"] for row in study["records"]} == {
        "source-row-00000001", "source-row-00000002",
    }


def test_manifest_reordering_preserves_original_source_row_uids(tmp_path: Path):
    source = tmp_path / "manifest-source.jsonl"
    source.write_text("\n".join(json.dumps(row) for row in [
        {"item_id": "zero", "task": "row zero"},
        {"item_id": "dup", "task": "original row one"},
        {"item_id": "two", "task": "row two"},
        {"item_id": "dup", "task": "original row three"},
    ]) + "\n", encoding="utf-8")
    manifest = tmp_path / "sample-manifest.json"
    manifest.write_text(json.dumps({
        "selected": [
            {"source_index": 3},
            {"source_index": 1},
        ],
    }), encoding="utf-8")
    report_path = tmp_path / "manifest-report.json"

    assert main([
        "audit", str(source), "--manifest", str(manifest),
        "--out", str(report_path), "--progress-every", "0",
    ]) == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    duplicate = next(
        row for row in report["violations"]
        if row["defect_type"] == "duplicate_item_id"
    )
    assert duplicate["row_uid"] == "source-row-00000003"
    assert duplicate["evidence"]["target_row_uids"] == [
        "source-row-00000003", "source-row-00000001",
    ]
    study = build_gold_study(
        input_path=source,
        report_path=report_path,
        investigation_path=None,
        flagged_size=2,
        unflagged_size=0,
        seed=9,
    )
    by_uid = {row["row_uid"]: row for row in study["records"]}
    assert by_uid["source-row-00000003"]["task"] == "original row three"
    assert by_uid["source-row-00000001"]["task"] == "original row one"


def test_score_injections_command_writes_recall(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.json"
    output = tmp_path / "score.json"
    manifest.write_text(json.dumps({"mutations": [{
        "mutated_item_id": "q1__mut",
        "defect_type": "missing_task",
        "operator": "remove_task",
    }]}), encoding="utf-8")
    report.write_text(json.dumps({"violations": [{
        "item_id": "q1__mut",
        "defect_type": "missing_task",
    }]}), encoding="utf-8")

    exit_code = main([
        "score-injections", "--manifest", str(manifest),
        "--report", str(report), "--out", str(output),
    ])

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["recall"] == 1.0


def test_auto_profile_detects_swebench_and_keeps_structural_checkers(tmp_path: Path):
    source = tmp_path / "opaque.jsonl"
    source.write_text(json.dumps({
        "instance_id": "repo__1",
        "problem_statement": "The parser fails on empty input.",
        "patch": "diff --git a/parser.py b/parser.py\n+return []",
        "test_patch": "def test_empty(): ...",
        "FAIL_TO_PASS": ["test_parser.py::test_empty"],
        "item_id": "repo__1",
        "task": "The parser fails on empty input.",
        "gold": "diff --git a/parser.py b/parser.py\n+return []",
        "output_contract": {"type": "git_patch"},
        "evaluator": {"type": "swebench_pytest"},
    }) + "\n", encoding="utf-8")
    output = tmp_path / "audit.json"

    exit_code = main([
        "audit", str(source), "--basic-only", "--out", str(output),
        "--progress-every", "0",
    ])

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["audit_plan"]["family"] == "swebench"
    assert "solution_leak" in report["methods_run"]
    assert "task_specification" in report["methods_run"]
    assert "evaluator" in report["methods_run"]


def test_auto_terminal_profile_does_not_require_scalar_gold(tmp_path: Path):
    source = tmp_path / "opaque.jsonl"
    source.write_text(json.dumps({
        "item_id": "terminal-1",
        "task": "Create /app/result.txt.",
        "raw": {"instruction": "Create /app/result.txt.", "task_toml": "[verifier]"},
        "output_contract": {"type": "terminal_task"},
        "evaluator": {"type": "terminal_bench_verifier"},
    }) + "\n", encoding="utf-8")
    output = tmp_path / "audit.json"

    assert main([
        "audit", str(source), "--basic-only", "--out", str(output),
        "--progress-every", "0",
    ]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["audit_plan"]["family"] == "terminalbench"
    assert "oracle_ground_truth" not in report["methods_run"]
    assert not any(v["defect_type"] == "missing_oracle" for v in report["violations"])


def test_plan_loads_record_semantics_and_canonical_artifacts(tmp_path: Path):
    source = tmp_path / "opaque.jsonl"
    source.write_text(json.dumps({
        "item_id": "workspace-1",
        "task": "Create the requested workspace files.",
        "rubrics": ["The report contains the requested result."],
        "rubric_types": ["content"],
        "file_dep_graph": {"report.md": []},
        "tested_capabilities": ["document_editing"],
        "evaluator": {"type": "workspacebench_rubric", "rubrics": []},
        "output_contract": {"type": "workspace_files", "required_files": ["report.md"]},
    }) + "\n", encoding="utf-8")
    output = tmp_path / "plan.json"

    assert main(["plan", str(source), "--out", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["audit_plan"]["family"] == "workspacebench"
    assert payload["audit_plan"]["artifact_coverage"]["evaluator_tests_rubric"] == "present"
    assert payload["audit_plan"]["artifact_coverage"]["expected_output"] == "present"


class FakeCrossArtifactClient:
    def __init__(self) -> None:
        self.calls = []

    def chat_json(self, system, user):
        self.calls.append((system, user))
        return {
            "status": "consistent",
            "missing_data": [],
            "task_ambiguities": [],
            "consistency_issues": [],
            "severity": "none",
            "confidence": 0.95,
            "summary": "Artifacts are consistent.",
        }

    def run_stats(self):
        return {"requests": len(self.calls)}


def _cross_artifact_source(root: Path) -> Path:
    source = root / "cross.jsonl"
    source.write_text(json.dumps({
        "item_id": "cross-1",
        "task": "Summarize the supplied evidence.",
        "context": {"table": "metric,value\nquality,12"},
        "rubrics": ["The summary reports the quality metric."],
        "output_contract": {"type": "text"},
    }) + "\n", encoding="utf-8")
    return source


def test_generic_cross_artifact_requires_remote_egress_consent(tmp_path: Path):
    source = _cross_artifact_source(tmp_path)
    with patch("benchcore.cli.build_llm_client") as build_client:
        with unittest.TestCase().assertRaisesRegex(ValueError, "allow-remote-data-egress"):
            main([
                "audit", str(source), "--profile", "generic",
                "--cross-artifact-audit", "--basic-only",
                "--out", str(tmp_path / "blocked.json"), "--progress-every", "0",
            ])
    build_client.assert_not_called()


def test_generic_cross_artifact_consent_records_outbound_manifest(tmp_path: Path):
    source = _cross_artifact_source(tmp_path)
    output = tmp_path / "allowed.json"
    client = FakeCrossArtifactClient()
    with patch("benchcore.cli.build_llm_client", return_value=client):
        assert main([
            "audit", str(source), "--profile", "generic",
            "--cross-artifact-audit", "--allow-remote-data-egress",
            "--basic-only", "--out", str(output), "--progress-every", "0",
        ]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    egress = report["run_metadata"]["remote_data_egress"]
    assert egress["authorized"] is True
    assert egress["network_egress_possible"] is True
    assert egress["attachment_content_in_scope"] is True
    assert "task" in egress["outbound_fields"]
    assert "attachment_content" in egress["outbound_fields"]
    assert egress["checkers"][0]["checker"] == "cross_artifact_consistency"
    assert client.calls


def _investigation_inputs(root: Path) -> tuple[Path, Path]:
    source = root / "investigate.jsonl"
    source.write_text(
        json.dumps({"item_id": "case-1", "task": "Inspect this case."}) + "\n",
        encoding="utf-8",
    )
    report = root / "audit.json"
    report.write_text(json.dumps({
        "field_mapping": {"item_id": "item_id", "task": "task"},
        "violations": [],
    }), encoding="utf-8")
    return source, report


def test_investigate_requires_remote_egress_consent_before_client_creation(
    tmp_path: Path,
):
    source, report = _investigation_inputs(tmp_path)
    with patch("benchcore.cli.build_llm_client") as build_client:
        with unittest.TestCase().assertRaisesRegex(
            ValueError, "allow-remote-data-egress",
        ):
            main([
                "investigate", str(source), "--report", str(report),
                "--out", str(tmp_path / "blocked.json"),
                "--no-evidence-verifier", "--progress-every", "0",
            ])
    build_client.assert_not_called()


def test_investigate_records_manifest_and_threads_trusted_roots(tmp_path: Path):
    source, source_report = _investigation_inputs(tmp_path)
    extra_root = tmp_path / "attachments"
    extra_root.mkdir()
    output = tmp_path / "investigation.json"
    client = FakeCrossArtifactClient()
    empty_report = {
        "summary": {
            "input_path": str(source),
            "source_report": str(source_report),
            "candidates_investigated": 0,
            "investigation_count": 0,
            "verdict_distribution": {},
            "issue_category_distribution": {},
            "defect_distribution": {},
            "likely_true_items": 0,
            "false_positive_items": 0,
            "uncertain_items": 0,
            "mean_agreement": 0.0,
            "evidence_verdict_distribution": {},
        },
        "investigations": [],
    }
    with (
        patch("benchcore.cli.build_llm_client", return_value=client),
        patch(
            "benchcore.cli.investigate_audit_report",
            return_value=empty_report,
        ) as investigate,
    ):
        assert main([
            "investigate", str(source), "--report", str(source_report),
            "--out", str(output), "--no-evidence-verifier",
            "--allow-input-root", str(extra_root),
            "--allow-remote-data-egress", "--progress-every", "0",
        ]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    egress = payload["run_metadata"]["remote_data_egress"]
    assert egress["authorized"] is True
    assert egress["network_egress_possible"] is True
    assert egress["attachment_content_in_scope"] is True
    assert egress["checkers"][0]["checker"] == "evidence_grounded_investigator"
    allowed_roots = investigate.call_args.kwargs["allowed_roots"]
    assert allowed_roots == [tmp_path.resolve(), extra_root.resolve()]


def test_deprecated_workspace_egress_flag_remains_compatible(
    tmp_path: Path,
    capsys,
):
    source = _cross_artifact_source(tmp_path)
    output = tmp_path / "legacy.json"
    with patch(
        "benchcore.cli.build_llm_client",
        return_value=FakeCrossArtifactClient(),
    ):
        assert main([
            "audit", str(source), "--profile", "generic",
            "--cross-artifact-audit", "--allow-workspace-data-egress",
            "--basic-only", "--out", str(output), "--progress-every", "0",
        ]) == 0

    assert "deprecated" in capsys.readouterr().err
    egress = json.loads(output.read_text(encoding="utf-8"))["run_metadata"][
        "remote_data_egress"
    ]
    assert egress["authorization_source"] == "deprecated_workspace_alias"


class ExecutionAuditCliTest(unittest.TestCase):
    def _source(self, root: Path) -> Path:
        source = root / "execution.jsonl"
        source.write_text(json.dumps({
            "item_id": "exec-1",
            "task": "Sort the list.",
            "gold": "result = sorted(data)",
            "evaluator": {"code_context": "def test_execution(solution): pass", "n_cases": 1},
        }) + "\n", encoding="utf-8")
        return source

    def test_help_documents_execution_safety_flags(self) -> None:
        output = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(output):
            main(["audit", "--help"])
        help_text = output.getvalue()
        self.assertIn("--execution-evaluator-audit", help_text)
        self.assertIn("--execution-container-image", help_text)
        self.assertIn("--allow-unsafe-local-execution", help_text)
        self.assertIn("--acknowledge-unsafe-local-execution", help_text)
        self.assertIn("NAME@sha256:<64 lowercase hex>", help_text)
        self.assertIn("--allow-remote-data-egress", help_text)

    def test_execution_audit_requires_a_container_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            with self.assertRaisesRegex(ValueError, "execution-container-image"):
                main([
                    "audit", str(source), "--execution-evaluator-audit",
                    "--llm-dry-run", "--out", str(root / "report.json"),
                    "--progress-every", "0",
                ])

    def test_value_recompute_requires_a_container_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            with self.assertRaisesRegex(ValueError, "execution-container-image"):
                main([
                    "audit", str(source), "--value-recompute-audit",
                    "--llm-dry-run", "--out", str(root / "report.json"),
                    "--progress-every", "0",
                ])

    def test_unsafe_local_execution_requires_both_opt_ins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            with self.assertRaisesRegex(ValueError, "requires both"):
                main([
                    "audit", str(source), "--execution-evaluator-audit",
                    "--allow-unsafe-local-execution", "--llm-dry-run",
                    "--out", str(root / "report.json"), "--progress-every", "0",
                ])

    def test_double_opt_in_wires_local_runner_and_records_backend(self) -> None:
        class FakeChecker:
            name = "execution_evaluator_audit"

            def check(self, item, root=None):
                return []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            report_path = root / "report.json"
            with (
                patch("benchcore.cli.LocalProcessRunner", return_value=sentinel.runner),
                patch(
                    "benchcore.cli.ExecutionEvaluatorAuditChecker",
                    return_value=FakeChecker(),
                ) as checker,
            ):
                result = main([
                    "audit", str(source), "--execution-evaluator-audit",
                    "--allow-unsafe-local-execution",
                    "--acknowledge-unsafe-local-execution",
                    "--llm-dry-run", "--out", str(report_path),
                    "--progress-every", "0",
                ])

            self.assertEqual(result, 0)
            self.assertIs(checker.call_args.kwargs["runner"], sentinel.runner)
            self.assertTrue(checker.call_args.kwargs["allow_unsafe_local"])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["run_metadata"]["execution"]["backend"], "unsafe_local")
            self.assertFalse(report["run_metadata"]["execution"]["confirmation_eligible"])
            self.assertEqual(report["run_metadata"]["execution"]["evidence_ceiling"], "review")
            self.assertIn("execution_evaluator_audit", report["methods_run"])

    def test_mutable_container_tag_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            with self.assertRaisesRegex(ValueError, "digest-pinned"):
                main([
                    "audit", str(source), "--execution-evaluator-audit",
                    "--execution-container-image", "benchcore-test:latest",
                    "--llm-dry-run", "--out", str(root / "report.json"),
                    "--progress-every", "0",
                ])

    def test_container_flag_wires_container_runner(self) -> None:
        class FakeChecker:
            name = "execution_evaluator_audit"

            def check(self, item, root=None):
                return []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            report_path = root / "report.json"
            with (
                patch("benchcore.cli.ContainerRunner", return_value=sentinel.runner) as runner,
                patch(
                    "benchcore.cli.ExecutionEvaluatorAuditChecker",
                    return_value=FakeChecker(),
                ) as checker,
            ):
                image = "benchcore-test@sha256:" + ("a" * 64)
                result = main([
                    "audit", str(source), "--execution-evaluator-audit",
                    "--execution-container-image", image,
                    "--llm-dry-run", "--out", str(report_path),
                    "--progress-every", "0",
                ])

            self.assertEqual(result, 0)
            runner.assert_called_once_with(image)
            self.assertIs(checker.call_args.kwargs["runner"], sentinel.runner)
            self.assertFalse(checker.call_args.kwargs["allow_unsafe_local"])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["run_metadata"]["execution"]["backend"], "container")
            self.assertTrue(report["run_metadata"]["execution"]["sandboxed"])
            self.assertTrue(report["run_metadata"]["execution"]["image_digest_pinned"])
            self.assertFalse(report["run_metadata"]["execution"]["evidence_integrity_proven"])
            self.assertEqual(
                report["run_metadata"]["execution"]["method_evidence_ceilings"][
                    "execution_evaluator_audit"
                ],
                "review_until_separate_adjudicator",
            )

    def test_value_recompute_uses_shared_container_backend_and_policy(self) -> None:
        class FakeChecker:
            name = "value_recompute"

            def check(self, item, root=None):
                return []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            report_path = root / "report.json"
            with (
                patch("benchcore.cli.ContainerRunner", return_value=sentinel.runner) as runner,
                patch(
                    "benchcore.cli.ValueRecomputeChecker",
                    return_value=FakeChecker(),
                ) as checker,
            ):
                image = "benchcore-value@sha256:" + ("b" * 64)
                result = main([
                    "audit", str(source), "--value-recompute-audit",
                    "--execution-container-image", image,
                    "--llm-dry-run", "--out", str(report_path),
                    "--progress-every", "0",
                ])

            self.assertEqual(result, 0)
            runner.assert_called_once_with(image)
            self.assertIs(checker.call_args.kwargs["runner"], sentinel.runner)
            policy = checker.call_args.kwargs["policy"]
            self.assertFalse(policy.network_enabled)
            self.assertFalse(policy.allow_local_process)
            self.assertEqual(policy.allowed_environment, frozenset())
            self.assertFalse(checker.call_args.kwargs["allow_unsafe_local"])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            execution = report["run_metadata"]["execution"]
            self.assertEqual(execution["methods"], ["value_recompute"])
            self.assertEqual(execution["workspace_mount"], "read_only")
            self.assertEqual(
                execution["method_evidence_ceilings"]["value_recompute"],
                "review",
            )
