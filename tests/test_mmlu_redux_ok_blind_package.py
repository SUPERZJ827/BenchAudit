from __future__ import annotations

import inspect
import json
from pathlib import Path

from scripts import build_mmlu_redux_ok_blind_package as builder


def frozen_inputs():
    rows = []
    report = {"violations": []}
    selected = {
        "d": {f"d-{index:03d}" for index in range(86)},
        "p_agree": {f"pa-{index:03d}" for index in range(196)},
        "p_missed": {f"pm-{index:03d}" for index in range(142)},
        "n_agree": {f"n-{index:03d}" for index in range(544)},
        "expert_review": {f"er-{index:03d}" for index in range(10)},
        "expert_no_review": {f"en-{index:03d}" for index in range(22)},
    }
    labels = {
        **{item_id: "ok" for item_id in selected["d"] | selected["n_agree"]},
        **{item_id: "wrong_groundtruth" for item_id in selected["p_agree"] | selected["p_missed"]},
        **{item_id: "expert" for item_id in selected["expert_review"] | selected["expert_no_review"]},
    }
    reviewed = selected["d"] | selected["p_agree"] | selected["expert_review"]
    for index, (item_id, label) in enumerate(sorted(labels.items())):
        rows.append({
            "id": item_id,
            "question": f"Synthetic question {index}",
            "choices": ["alpha", "beta", "gamma", "delta"],
            "gold": "A",
            "evaluator": {"type": "multiple_choice"},
            "metadata": {"error_type": label, "subject": f"subject-{index % 12:02d}"},
        })
        if item_id in reviewed:
            report["violations"].append({
                "item_id": item_id,
                "defect_scope": "substantive",
                "evidence_tier": "review",
                "detection_method": "fixture_method",
                "defect_type": "wrong_gold_answer",
                "artifact": "oracle_ground_truth",
            })
    mechanical = {
        "mechanically_confirmed_item_ids": ["d-000"],
    }
    return rows, report, mechanical, selected


def test_four_frozen_pools_exclude_expert_and_have_expected_sizes() -> None:
    _rows, _report, _mechanical, selected = frozen_inputs()
    assert {name: len(selected[name]) for name in (
        "d", "p_agree", "p_missed", "n_agree", "expert_review", "expert_no_review"
    )} == {
        "d": 86, "p_agree": 196, "p_missed": 142, "n_agree": 544,
        "expert_review": 10, "expert_no_review": 22,
    }
    assert not (selected["p_agree"] & selected["expert_review"])
    assert not (selected["p_missed"] & selected["expert_no_review"])


def test_fixed_salt_is_byte_deterministic_and_new_salt_reblinds() -> None:
    rows, report, mechanical, selected = frozen_inputs()
    first = builder.build(rows, report, mechanical, selected, b"a" * 32)
    second = builder.build(rows, report, mechanical, selected, b"a" * 32)
    changed = builder.build(rows, report, mechanical, selected, b"b" * 32)
    assert builder.stable_bytes(first[0]) == builder.stable_bytes(second[0])
    assert builder.stable_bytes(first[1]) == builder.stable_bytes(second[1])
    assert {row["blind_id"] for row in first[0]} != {row["blind_id"] for row in changed[0]}
    assert first[2]["source_pool_counts"] == changed[2]["source_pool_counts"]


def test_package_is_205_uniform_rows_with_no_class_keys() -> None:
    rows, report, mechanical, selected = frozen_inputs()
    public, mapping, receipt = builder.build(rows, report, mechanical, selected, b"c" * 32)
    assert receipt["outcome"] == "PASS_BLIND_PACKAGE_205"
    assert len(public) == 205
    assert len(mapping["items"]) == 205
    assert receipt["blind_semantic_d_count"] == 85
    assert receipt["control_counts"] == {"p_agree": 40, "p_missed": 40, "n_agree": 40}
    assert {tuple(sorted(row)) for row in public} == {tuple(sorted(builder.PUBLIC_KEYS))}
    serialized = b"".join(builder.stable_bytes(row) for row in public).decode().lower()
    for forbidden in builder.FORBIDDEN_PUBLIC_FRAGMENTS:
        assert f'"{forbidden}"' not in serialized


def test_control_arms_are_disjoint_and_subject_quota_receipts_sum() -> None:
    rows, report, mechanical, selected = frozen_inputs()
    _public, mapping, receipt = builder.build(rows, report, mechanical, selected, b"d" * 32)
    by_arm = {}
    for item in mapping["items"]:
        by_arm.setdefault(item["arm"], set()).add(item["item_id"])
    assert {arm: len(ids) for arm, ids in by_arm.items()} == {
        "d": 85, "p_agree": 40, "p_missed": 40, "n_agree": 40,
    }
    arms = list(by_arm.values())
    assert sum(len(ids) for ids in arms) == len(set().union(*arms))
    for quota in receipt["quota_receipts"].values():
        assert sum(quota["actual_subject_quotas"].values()) == 40


def test_builder_has_no_network_or_llm_path() -> None:
    source = inspect.getsource(builder)
    for forbidden in ("import requests", "import urllib", "import socket", "LLMClient("):
        assert forbidden not in source


def test_committed_public_package_and_receipt_are_self_consistent() -> None:
    package = builder.ROOT / "reports/mmlu_redux_ok_blind_package_20260803/package.jsonl"
    receipt_path = builder.ROOT / "reports/mmlu_redux_ok_blind_package_20260803/receipt.json"
    public = [json.loads(line) for line in package.read_text(encoding="utf-8").splitlines() if line]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert len(public) == receipt["public_rows"] == 205
    assert len({row["blind_id"] for row in public}) == 205
    assert {tuple(sorted(row)) for row in public} == {tuple(sorted(builder.PUBLIC_KEYS))}
    assert builder.sha256_file(package) == receipt["public_package_sha256"]
    assert receipt["sealed_mapping_path_emitted"] is False
    assert receipt["adjudication_performed"] is False
