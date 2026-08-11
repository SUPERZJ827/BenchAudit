from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/replay_modora_static_cross_execution_v2.py"
SPEC = importlib.util.spec_from_file_location(
    "replay_modora_static_cross_execution_v2", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def _row(question_id: int, static: bool, external: bool):
    return {
        "questionId": question_id,
        "static_intrinsic": static,
        "static_any_compatible": static,
        "cross_execution_hit": external,
        "mining_layer_hit": external,
    }


def test_coverage_migration_keeps_comparisons_separate():
    old = [_row(question_id, False, question_id == 1) for question_id in range(1, 1066)]
    new = [_row(question_id, question_id == 1, question_id == 1) for question_id in range(1, 1066)]

    migrations = mod.build_coverage_migrations(old, new)

    changed = [row for row in migrations if row["changed"]]
    assert len(changed) == 4
    assert {row["transition"] for row in changed} == {"B->A"}
    by_comparison = mod.transition_counts_by_comparison(migrations)
    assert all(counts["B->A"] == 1 for counts in by_comparison.values())


def test_evidence_migration_distinguishes_tier_change_from_new_finding():
    old = [{
        "questionId": "895",
        "defect_type": "conflicting_duplicate_oracle",
        "source_finding_item_id": "895",
        "evidence_tier": "confirmed",
        "review_only": "False",
        "severity": "critical",
    }]
    new = [
        {
            "questionId": 895,
            "defect_type": "conflicting_duplicate_oracle",
            "source_finding_item_id": "895",
            "evidence_tier": "review",
            "review_only": True,
            "severity": "review",
        },
        {
            "questionId": 853,
            "defect_type": "unexpected_invisible_or_control_gold",
            "source_finding_item_id": "853",
            "evidence_tier": "confirmed",
            "review_only": False,
            "severity": "major",
        },
    ]

    migrations = mod.build_evidence_migrations(old, new)

    changed = [row for row in migrations if row["changed"]]
    assert len(changed) == 2
    q895 = next(row for row in changed if row["questionId"] == 895)
    q853 = next(row for row in changed if row["questionId"] == 853)
    assert (q895["v1_evidence_tier"], q895["v2_evidence_tier"]) == (
        "confirmed",
        "review",
    )
    assert q853["v1_present"] is False and q853["v2_present"] is True


def test_v1_receipt_hash_mismatch_fails_closed(tmp_path: Path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="receipt hash mismatch"):
        mod.verify_v1_outputs(receipt)


def test_product_refusal_requires_every_method_file(tmp_path: Path):
    class Miner:
        METHOD_FILES = {"a": "a.jsonl", "b": "b.jsonl"}

    result = '{"prediction":"x","judge":true,"answer":"x"}\n'
    (tmp_path / "a.jsonl").write_text(result, encoding="utf-8")
    (tmp_path / "b.jsonl").write_text(result, encoding="utf-8")

    refusals = mod.verify_product_refusal(Miner, tmp_path)

    assert len(refusals) == 2
    assert all(row["refused"] for row in refusals)


def test_product_refusal_fails_if_one_file_has_an_explicit_contract(tmp_path: Path):
    class Miner:
        METHOD_FILES = {"a": "a.jsonl"}

    row = '{"prediction":"x","judge":true,"answer":"x","evaluator":"exact"}\n'
    (tmp_path / "a.jsonl").write_text(row, encoding="utf-8")

    with pytest.raises(RuntimeError, match="did not refuse"):
        mod.verify_product_refusal(Miner, tmp_path)


@pytest.mark.skipif(
    not (ROOT / "data/MoDora/resmodora.jsonl").is_file()
    or not (ROOT / "reports/modora_defect_mining_20260810/receipt.json").is_file()
    or not (
        ROOT
        / "reports/modora_static_cross_execution_complementarity_20260810/receipt.json"
    ).is_file(),
    reason="external MoDora inputs and V1 report receipts are not tracked in git",
)
def test_real_v2_replay_anchors(tmp_path: Path):
    miner = mod.load_module(
        ROOT / "scripts/mine_modora_defects.py", "test_v2_frozen_miner"
    )
    old = mod.load_module(
        ROOT / "scripts/analyze_modora_static_cross_execution.py",
        "test_v1_frozen_complementarity",
    )
    refusals = mod.verify_product_refusal(miner, ROOT / "data/MoDora")
    loaded = miner.load_data(ROOT / "data/MoDora")
    mining = miner.analyze(loaded)
    static = mod.run_static_v2(old, old.build_items(miner, loaded))
    channels = old.build_item_channels(mining, static)
    contingency = old.contingency_rows(channels)
    v1_dir = ROOT / "reports/modora_static_cross_execution_complementarity_20260810"
    coverage = mod.build_coverage_migrations(
        mod.read_csv(v1_dir / "item_channels.csv"), channels
    )
    evidence = mod.build_evidence_migrations(
        mod.read_csv(v1_dir / "static_findings.csv"), static["finding_rows"]
    )

    anchors = mod.validate_anchors(
        refusals, static, channels, contingency, coverage, evidence
    )

    assert all(anchors.values()), anchors
