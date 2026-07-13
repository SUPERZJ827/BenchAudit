from pathlib import Path

from benchcore.package_scan import scan_benchmark_package
from benchcore.planning import apply_family_policy, build_audit_plan, detect_benchmark_family
from benchcore.schema import BenchmarkItem


def test_planner_detects_swebench_and_explains_missing_execution(tmp_path: Path):
    (tmp_path / "problem_statement.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "gold_patch.diff").write_text("+ fix\n", encoding="utf-8")
    (tmp_path / "tests.py").write_text("assert True\n", encoding="utf-8")
    package = scan_benchmark_package(tmp_path)

    family, confidence, _ = detect_benchmark_family(package)
    plan = build_audit_plan(package, available_llm=False, available_execution=False)
    checks = {check.name: check for check in plan.checks}

    assert family == "swebench"
    assert confidence >= 0.8
    assert checks["solution_leak"].status == "selected"
    assert checks["evaluator_replay"].status == "skipped"
    assert "safe execution" in checks["evaluator_replay"].reason
    assert checks["llm_semantic_audit"].status == "skipped"


def test_planner_reports_missing_artifact_coverage(tmp_path: Path):
    (tmp_path / "questions.jsonl").write_text("{}\n", encoding="utf-8")

    plan = build_audit_plan(scan_benchmark_package(tmp_path))

    assert plan.artifact_coverage["task_specification"] == "present"
    assert plan.artifact_coverage["environment_initial_state"] == "missing"
    assert any(check.status == "unsupported" for check in plan.checks)


def test_family_detection_uses_record_semantics_not_only_filename(tmp_path: Path):
    source = tmp_path / "sample.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    package = scan_benchmark_package(source)
    item = BenchmarkItem(
        item_id="terminal-1",
        raw={"instruction": "fix it", "task_toml": "[verifier]"},
        task="Fix the repository.",
        output_contract={"type": "terminal_task"},
        evaluator={"type": "terminal_bench_verifier"},
    )

    family, confidence, reasons = detect_benchmark_family(package, [item])

    assert family == "terminalbench"
    assert confidence >= 0.9
    assert any("terminal-agent" in reason for reason in reasons)

    plan = apply_family_policy(build_audit_plan(package, items=[item]))
    oracle = next(check for check in plan.checks if check.name == "oracle_ground_truth")
    assert oracle.status == "skipped"
    assert "scalar gold" in oracle.reason
