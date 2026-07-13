import json
from pathlib import Path

from benchcore.cli import main


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
