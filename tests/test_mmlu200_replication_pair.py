from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/run_mmlu200_replication_pair_20260802.py"
SPEC = importlib.util.spec_from_file_location("mmlu200_pair", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _violation(item: str, method: str, defect: str, scope: str = "substantive") -> dict:
    return {
        "item_id": item,
        "detection_method": method,
        "defect_type": defect,
        "defect_scope": scope,
        "evidence_tier": "review",
    }


def test_jaccard_empty_and_nonempty() -> None:
    assert MODULE.jaccard(set(), set()) == 1.0
    assert MODULE.jaccard({"a"}, set()) == 0.0
    assert MODULE.jaccard({"a", "b"}, {"b", "c"}) == 1 / 3


def test_finding_identity_excludes_presentation() -> None:
    report = {
        "violations": [
            _violation("one", "method_a", "wrong_gold"),
            _violation("one", "method_a", "typo", "presentation"),
        ]
    }
    assert MODULE.item_set(report) == {"one"}
    assert MODULE.finding_set(report) == {("one", "method_a", "wrong_gold")}


def test_per_method_jaccard_preserves_method_boundary() -> None:
    left = {("one", "a", "x"), ("two", "b", "y")}
    right = {("one", "a", "x"), ("three", "b", "y")}
    assert MODULE.per_method_jaccard(left, right) == {"a": 1.0, "b": 0.0}


def test_validate_run_rejects_method_worker_cache_and_operational_drift(tmp_path: Path) -> None:
    report = {
        "methods_run": ["wrong"],
        "run_metadata": {
            "workers": 1,
            "llm": {
                "model": "deepseek-v4-flash",
                "temperature": 0.0,
                "configured_votes": 1,
                "thinking": "disabled",
                "max_tokens": 5000,
                "proxy_url": "http://127.0.0.1:17890",
                "cache_hits": 1,
                "cache_path": str(tmp_path / "wrong.jsonl"),
                "api_attempts": 2,
                "total_tokens": 10,
            },
        },
        "summary": {"audit_coverage": {"operational_failed": 6, "attempted": 100}},
        "violations": [],
    }
    failures, diagnostics = MODULE.validate_run(
        report, expected_cache_path=tmp_path / "expected.jsonl"
    )
    assert "methods_run_mismatch" in failures
    assert "workers_mismatch" in failures
    assert "cache_hits_nonzero" in failures
    assert "cache_path_mismatch" in failures
    assert "operational_failure_rate_exceeded" in failures
    assert diagnostics["operational_failure_rate"] == 0.06


def test_validate_run_accepts_frozen_shape(tmp_path: Path) -> None:
    cache = tmp_path / "cache.jsonl"
    report = {
        "methods_run": MODULE.EXPECTED_METHODS,
        "run_metadata": {
            "workers": 8,
            "llm": {
                "model": "deepseek-v4-flash",
                "temperature": 0.0,
                "configured_votes": 1,
                "thinking": "disabled",
                "max_tokens": 5000,
                "proxy_url": "http://127.0.0.1:17890",
                "cache_hits": 0,
                "cache_entries": 10,
                "cache_path": str(cache),
                "api_attempts": 10,
                "total_tokens": 100,
            },
        },
        "summary": {"audit_coverage": {"operational_failed": 1, "attempted": 100}},
        "violations": [],
    }
    failures, diagnostics = MODULE.validate_run(report, expected_cache_path=cache)
    assert failures == []
    assert diagnostics["operational_failure_rate"] == 0.01


def test_pair_summary_uses_preregistered_thresholds() -> None:
    reports = [
        {"violations": [_violation("one", "a", "x")]},
        {"violations": [_violation("one", "a", "x")]},
    ]
    comparisons = [
        {"substantive_only": {"candidate": {"f1": 0.70}}},
        {"substantive_only": {"candidate": {"f1": 0.71}}},
    ]
    summary = MODULE.build_pair_summary(reports, comparisons, [{}, {}])
    assert summary["metrics"]["item_jaccard"] == 1.0
    assert summary["metrics"]["violation_jaccard"] == 1.0
    assert summary["interpretation"] == "SUPPORTS_MMLU_MORE_STABLE_FOR_THIS_PAIR"
