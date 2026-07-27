from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_sqlbench_metamorphic_pilot.py"


def _module():
    spec = importlib.util.spec_from_file_location("sqlbench_mr_pilot", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_manifest_is_path_sorted_and_content_bound(tmp_path):
    module = _module()
    (tmp_path / "b.json").write_text("b", encoding="utf-8")
    (tmp_path / "a.json").write_text("a", encoding="utf-8")

    rows, digest = module._source_manifest(
        [tmp_path / "a.json", tmp_path / "b.json"], tmp_path,
    )
    rows_again, digest_again = module._source_manifest(
        [tmp_path / "a.json", tmp_path / "b.json"], tmp_path,
    )

    assert [row["path"] for row in rows] == ["a.json", "b.json"]
    assert rows == rows_again
    assert digest == digest_again


def test_report_contract_is_explicitly_non_confirming():
    source = SCRIPT.read_text(encoding="utf-8")

    assert '"confirmation_eligible": False' in source
    assert '"evidence_tier": "diagnostic"' in source
    assert "official SQLBench correctness evaluator" in source
