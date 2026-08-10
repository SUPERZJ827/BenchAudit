from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import json

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_all_external_experiments.py"
SPEC = importlib.util.spec_from_file_location("analyze_all_external_experiments", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


@pytest.fixture(scope="module")
def integration_results():
    modora = ROOT / "data" / "MoDora"
    collection = Path("/data/expdata/BenchAudit")
    if not all((modora / filename).is_file() for filename in mod.MODORA_FILES.values()):
        pytest.skip("external MoDora inputs are not tracked in git")
    if not (collection / "FILE_MANIFEST.csv").is_file():
        pytest.skip("external SQLBench/DBCode collection is unavailable")
    return {
        "modora": mod.analyze_modora(modora),
        "modora_defects": mod.load_modora_defect_receipt(
            ROOT / "reports" / "modora_defect_mining_20260810" / "receipt.json",
            mod.MODORA_DEFECT_RECEIPT_SHA256,
        ),
        "sql_dialect": mod.analyze_sql_dialect(
            collection / "SQLBench/SQL_Dialect_Translation/scores/sqlglot_syntax_validation"
        ),
        "llama": mod.analyze_llama(
            collection / "SQLBench/Llama3.1_SQL_Dialect_Translation/different_model_outputs"
        ),
        "portuguese": mod.analyze_portuguese(
            collection / "SQLBench/PortugueseSpider/scores"
        ),
        "dbcode": mod.analyze_dbcode(collection / "DBCode"),
        "integrity": mod.verify_collection(collection),
    }


def test_canonical_hash_is_order_independent_for_mapping_keys():
    assert mod.canonical_hash({"a": 1, "b": [2]}) == mod.canonical_hash(
        {"b": [2], "a": 1}
    )


def test_csv_bool_fails_closed():
    assert mod.csv_bool("true", "true") is True
    assert mod.csv_bool("false", "true") is False
    assert mod.csv_bool("", "false") is None
    with pytest.raises(ValueError):
        mod.csv_bool("maybe", "true")


def test_modora_defect_receipt_is_hash_bound_and_fails_closed(tmp_path):
    receipt = {
        "schema_version": "modora-defect-mining-receipt-v2",
        "rule_version": "modora-defect-mining-v2",
        "anchors": {"constructive": True},
        "input_sha256": mod.MODORA_SHA256,
        "summary": {
            "hard_record_inconsistency_items": 11,
            "invisible_gold_items": 4,
            "fact_convergence_hypothesis_items": 6,
        },
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    expected = mod.sha256_file(path)
    loaded = mod.load_modora_defect_receipt(path, expected)
    assert loaded["summary"] == {
        "fact_convergence_hypothesis_items": 6,
        "hard_record_inconsistency_items": 11,
        "invisible_gold_items": 4,
    }
    path.write_text(json.dumps({**receipt, "tampered": True}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        mod.load_modora_defect_receipt(path, expected)
    with pytest.raises(RuntimeError, match="missing"):
        mod.load_modora_defect_receipt(tmp_path / "missing.json", expected)


def test_cross_report_findings_are_derived_from_inputs():
    assert "11 条相同" in mod.render_modora_defect_finding(
        {
            "hard_record_inconsistency_items": 11,
            "invisible_gold_items": 4,
            "fact_convergence_hypothesis_items": 6,
        }
    )
    assert "4 条 U+200B" in mod.render_modora_defect_finding(
        {
            "hard_record_inconsistency_items": 11,
            "invisible_gold_items": 4,
            "fact_convergence_hypothesis_items": 6,
        }
    )
    assert "6 条需原 PDF" in mod.render_modora_defect_finding(
        {
            "hard_record_inconsistency_items": 11,
            "invisible_gold_items": 4,
            "fact_convergence_hypothesis_items": 6,
        }
    )
    finding = mod.render_sqlite_code_agent_finding(
        {"sqlite_code_agent_scored": 7, "sqlite_code_agent_pass": 2}
    )
    assert "7 条已评分任务" in finding
    assert "2/7 PASS" in finding
    assert "attempt-level" in finding


def test_portuguese_score_parser_keeps_metric_contracts_separate(tmp_path):
    path = tmp_path / "spider_eval_exec_example.txt"
    path.write_text(
        "Exec  OK easy pred: a\n---\nExec Fail hard pred: b\nnoise\n",
        encoding="utf-8",
    )
    row = mod.parse_portuguese_score(path, tmp_path)
    assert row["metric"] == "exec"
    assert row["records"] == 2
    assert row["ok"] == 1
    assert row["fail"] == 1
    assert row["rate"] == "0.500000000000"


def test_llama_task_key_does_not_use_completion_id():
    row = {"id": "dataset", "norm": "n", "clickhouse": "sql", "result": {"id": "x"}}
    assert mod.llama_task_key(row) == ("dataset", "n", "sql")


def test_real_data_anchors(integration_results):
    anchors = mod.validate_anchors(integration_results)
    assert anchors
    assert all(anchors.values()), anchors


def test_sql_model_matrix_is_complete(integration_results):
    summary = integration_results["sql_dialect"]["summary"]
    assert summary["records"] == summary["models"] * summary["tasks"]
    assert sum(summary["models_valid_distribution"].values()) == summary["tasks"]


def test_portuguese_pairs_have_equal_coverage_and_lower_exec(integration_results):
    pairs = integration_results["portuguese"]["pair_rows"]
    assert len(pairs) == 19
    assert all(row["same_coverage_count"] for row in pairs)
    assert all(float(row["exec_minus_match"]) < 0 for row in pairs)
    means = integration_results["portuguese"]["summary"][
        "mbart_match_mean_by_eval_language"
    ]
    assert means["en"] > means["fr"] > means["pt"]


def test_dbcode_full_pass_implies_function_pass_in_retained_sqlite(integration_results):
    summary = integration_results["dbcode"]["summary"]
    assert summary["sqlite_direct_full_pass_func_fail"] == 0
    assert summary["sqlite_direct_func_pass_full_fail"] == 60


def test_findings_make_dbcode_denominators_and_llama_uniques_explicit(
    integration_results,
):
    findings = mod.render_findings(integration_results)
    context = {
        (row["database"], row["model"], row["metric"]): row
        for row in integration_results["dbcode"]["context_rows"]
    }
    qwen = context[("postgresql", "Qwen3-Coder-480B-A35B-Instruct", "full")]
    summary = integration_results["dbcode"]["summary"]
    sqlite_total = sum(
        summary[key]
        for key in (
            "sqlite_direct_full_func_both_fail",
            "sqlite_direct_func_pass_full_fail",
            "sqlite_direct_both_pass",
            "sqlite_direct_full_pass_func_fail",
        )
    )
    single_file_unique = integration_results["llama"]["summary"][
        "task_occurrence_distribution"
    ][1]
    assert (
        f"共同且两侧均有分数的 {qwen['scored_pairs']} 条任务" in findings
    )
    assert f"合计 {sqlite_total} 条完整/function 双评分记录" in findings
    assert f"只有 {single_file_unique} 个任务是单文件独有" in findings
