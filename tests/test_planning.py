from pathlib import Path

from benchcore.package_scan import add_canonical_item_artifacts, scan_benchmark_package
from benchcore.coverage import AuditLedgerEntry
from benchcore.planning import (
    apply_family_policy,
    build_audit_plan,
    detect_benchmark_family,
    plan_for_executed_methods,
)
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
    assert checks["evaluator_replay"].status == "selected"
    assert checks["evaluator_replay"].evidence_level == "deterministic_replay"
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


def test_execution_evaluator_requires_llm_and_real_execution_capabilities(tmp_path: Path):
    source = tmp_path / "opaque.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    package = scan_benchmark_package(source)
    item = BenchmarkItem(
        item_id="exec-1",
        raw={},
        task="Sort a list.",
        gold="result = sorted(data)",
        evaluator={"code_context": "def test_execution(solution): pass"},
    )
    add_canonical_item_artifacts(package, [item])

    unavailable = {
        check.name: check
        for check in build_audit_plan(
            package,
            items=[item],
            available_llm=False,
            available_execution=False,
        ).checks
    }
    llm_only = {
        check.name: check
        for check in build_audit_plan(
            package,
            items=[item],
            available_llm=True,
            available_execution=False,
        ).checks
    }
    available = {
        check.name: check
        for check in build_audit_plan(
            package,
            items=[item],
            available_llm=True,
            available_execution=True,
        ).checks
    }

    assert unavailable["execution_evaluator_audit"].status == "skipped"
    assert "LLM capability" in unavailable["execution_evaluator_audit"].reason
    assert llm_only["execution_evaluator_audit"].status == "skipped"
    assert "safe execution" in llm_only["execution_evaluator_audit"].reason
    assert available["execution_evaluator_audit"].status == "selected"


def test_executed_method_status_is_derived_from_coverage_ledger(tmp_path: Path):
    source = tmp_path / "questions.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    package = scan_benchmark_package(source)
    plan = build_audit_plan(package)
    rows = [
        AuditLedgerEntry(
            item_id="a", checker="task_specification",
            status="completed_no_finding", reason="done",
            lifecycle=["planned", "eligible", "attempted", "completed_no_finding"],
            eligible=True, attempted=True, completed=True,
        ),
        AuditLedgerEntry(
            item_id="b", checker="task_specification",
            status="operational_failed", reason="boom",
            lifecycle=["planned", "eligible", "attempted", "operational_failed"],
            eligible=True, attempted=True, completed=False,
        ),
    ]

    result = plan_for_executed_methods(
        package, ["task_specification"], base_plan=plan, audit_ledger=rows,
    )
    task = next(check for check in result.checks if check.name == "task_specification")

    assert task.status == "partial"
    assert "1/2" in task.reason


def test_instantiated_checker_without_ledger_is_not_reported_executed(tmp_path: Path):
    source = tmp_path / "questions.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    package = scan_benchmark_package(source)

    result = plan_for_executed_methods(package, ["task_specification"], audit_ledger=[])
    task = next(check for check in result.checks if check.name == "task_specification")

    assert task.status == "failed"
