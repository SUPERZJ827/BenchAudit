from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_modora_static_cross_execution.py"
SPEC = importlib.util.spec_from_file_location(
    "analyze_modora_static_cross_execution", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def test_phi_handles_perfect_inverse_and_undefined_vectors():
    assert mod.phi([0, 1, 0, 1], [0, 1, 0, 1]) == pytest.approx(1.0)
    assert mod.phi([0, 1, 0, 1], [1, 0, 1, 0]) == pytest.approx(-1.0)
    assert mod.phi([1, 1], [0, 1]) is None


def test_target_ids_expands_dataset_findings():
    from benchcore.schema import Violation

    finding = Violation(
        item_id="895",
        artifact="oracle",
        mechanism="x",
        defect_type="conflicting_duplicate_oracle",
        severity="major",
        confidence=None,
        message="x",
        evidence={"target_row_uids": ["modora:895", "modora:896"]},
    )
    assert mod.target_ids(finding) == [895, 896]


def test_contingency_is_exhaustive_and_mutually_exclusive():
    rows = [
        {
            "questionId": 1,
            "static_intrinsic": True,
            "static_any_compatible": True,
            "cross_execution_hit": True,
            "mining_layer_hit": True,
        },
        {
            "questionId": 2,
            "static_intrinsic": False,
            "static_any_compatible": False,
            "cross_execution_hit": True,
            "mining_layer_hit": True,
        },
        {
            "questionId": 3,
            "static_intrinsic": True,
            "static_any_compatible": True,
            "cross_execution_hit": False,
            "mining_layer_hit": False,
        },
        {
            "questionId": 4,
            "static_intrinsic": False,
            "static_any_compatible": False,
            "cross_execution_hit": False,
            "mining_layer_hit": False,
        },
    ]
    result = mod.contingency_rows(rows)
    primary = {
        row["cell"]: row["count"]
        for row in result
        if row["comparison"] == "static_intrinsic_x_cross_execution"
    }
    assert primary == {"A": 1, "B": 1, "C": 1, "D": 1}


def test_frozen_receipt_hash_mismatch_fails_closed(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="receipt hash mismatch"):
        mod.verify_frozen_inputs(ROOT, receipt)


@pytest.mark.skipif(
    not (ROOT / "data/MoDora/resmodora.jsonl").is_file()
    or not (ROOT / "reports/modora_defect_mining_20260810/receipt.json").is_file(),
    reason="external MoDora inputs and report receipt are not tracked in git",
)
def test_real_data_analysis_anchors():
    miner = mod.load_module(
        ROOT / "scripts/mine_modora_defects.py", "test_frozen_mine_modora"
    )
    loaded = miner.load_data(ROOT / "data/MoDora")
    result = miner.analyze(loaded)
    items = mod.build_items(miner, loaded)
    static = mod.run_static(items)
    channels = mod.build_item_channels(result, static)
    contingency = mod.contingency_rows(channels)
    pairs, _ = mod.method_correlations(miner, loaded)
    anchors = mod.validate_anchors(static, channels, contingency, pairs)
    assert all(anchors.values()), anchors
    findings = mod.render_findings(static, channels, contingency, pairs)
    assert "A（两层都报）=0；B（跨执行独有）=15" in findings
    assert "`confirmed`" in findings
    assert "89 条全错且预测发散" in findings
