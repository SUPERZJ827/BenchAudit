"""Regression tests for the claim proved by oracle-integrity evidence."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from benchcore.auditor import audit_items
from benchcore.checkers import OracleChecker, _violation
from benchcore.methods import DuplicateConflictChecker, _stable_value
from benchcore.oracle_text import (
    DUPLICATE_ORACLE_COMPARISON_CONTRACT,
    duplicate_oracle_comparison_value,
)
from benchcore.promotion import enforce_all
from benchcore.schema import BenchmarkItem


ROOT = Path(__file__).resolve().parents[1]


def _duplicates(first_gold, second_gold):
    return [
        BenchmarkItem(
            item_id="q895",
            raw={},
            task="Which crochet thread is specified?",
            gold=first_gold,
            row_uid="row-895",
        ),
        BenchmarkItem(
            item_id="q896",
            raw={},
            task="Which crochet thread is specified?",
            gold=second_gold,
            row_uid="row-896",
        ),
    ]


def _duplicate_findings(items):
    return audit_items(
        items,
        checkers=[],
        dataset_checkers=[DuplicateConflictChecker()],
    )


@pytest.mark.parametrize(
    ("first_gold", "second_gold"),
    [
        (["Size 10 crochet thread"], ["Size 10 crochet thread."]),
        ("Paris", "paris"),
        ("3.5", "3.50"),
        ("0.5", ".5"),
        (3.5, "3.500"),
    ],
)
def test_standing_equivalence_interpretation_stays_review(
    first_gold, second_gold,
):
    items = _duplicates(first_gold, second_gold)

    findings = _duplicate_findings(items)

    conflict = next(
        finding
        for finding in findings
        if finding.defect_type == "conflicting_duplicate_oracle"
    )
    assert conflict.evidence_tier == "review"
    assert conflict.review_only is True
    assert conflict.severity == "review"
    assert conflict.evidence["evidence_level"] == (
        "canonical_record_oracle_surface_difference"
    )
    assert len(conflict.evidence["gold_values"]) == 2
    assert len(conflict.evidence["comparison_values"]) == 1
    assert "surface formatting" in conflict.message


@pytest.mark.parametrize(
    ("first_gold", "second_gold"),
    [
        ("-5", "5"),
        ('42" x 50"', "42 x 50 mm"),
        ("80%", "-80%"),
        ("1.5", "15"),
        ("3.5", "35"),
    ],
)
def test_answer_bearing_symbols_remain_confirmable_conflicts(
    first_gold, second_gold,
):
    findings = _duplicate_findings(_duplicates(first_gold, second_gold))

    conflict = next(
        finding
        for finding in findings
        if finding.defect_type == "conflicting_duplicate_oracle"
    )
    assert conflict.evidence_tier == "confirmed"
    assert conflict.review_only is False
    assert conflict.evidence["evidence_level"] == (
        "canonical_record_oracle_conflict"
    )
    assert len(conflict.evidence["comparison_values"]) == 2


def test_forged_conflict_payload_cannot_promote_surface_only_live_values():
    items = _duplicates(
        ["Size 10 crochet thread"], ["Size 10 crochet thread."],
    )
    comparison_values = sorted({
        duplicate_oracle_comparison_value(item.gold) for item in items
    })
    finding = _violation(
        items[0],
        "conflicting_duplicate_oracle",
        "forged semantic conflict",
        {
            "item_ids": [item.item_id for item in items],
            "target_row_uids": [item.row_uid for item in items],
            "gold_values": sorted({_stable_value(item.gold) for item in items}),
            "comparison_values": comparison_values,
            "comparison_contract": DUPLICATE_ORACLE_COMPARISON_CONTRACT,
            "evidence_level": "canonical_record_oracle_conflict",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="dataset_duplicate_scan",
    )

    enforce_all([finding], items)

    assert finding.evidence_tier == "review"
    assert "complete live records" in finding.promotion_reason


def test_zero_width_gold_is_confirmed_by_live_replay():
    item = BenchmarkItem(
        item_id="q1048",
        raw={},
        task="Describe the weather.",
        gold=["\u200bUnsettled\u200b"],
        row_uid="row-1048",
    )

    findings = list(OracleChecker().check(item))

    finding = next(
        row
        for row in findings
        if row.defect_type == "unexpected_invisible_or_control_gold"
    )
    assert finding.evidence_tier == "confirmed"
    assert finding.review_only is False
    assert [
        (row["path"], row["position"], row["codepoint"], row["category"])
        for row in finding.evidence["unexpected_characters"]
    ] == [
        ("$[0]", 0, "U+200B", "Cf"),
        ("$[0]", 10, "U+200B", "Cf"),
    ]


def test_forged_invisible_character_payload_fails_closed():
    item = BenchmarkItem(
        item_id="q853",
        raw={},
        task="Question",
        gold="\u200banswer",
        row_uid="row-853",
    )
    finding = _violation(
        item,
        "unexpected_invisible_or_control_gold",
        "forged position",
        {
            "gold": item.gold,
            "unexpected_characters": [{
                "path": "$", "position": 1, "codepoint": "U+200B",
                "unicode_name": "ZERO WIDTH SPACE", "category": "Cf",
            }],
            "character_integrity_contract": "unicode-cf-cc-except-tab-newline-cr-v1",
            "evidence_level": "oracle_unicode_integrity_replay",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="static_rule",
    )

    assert finding.evidence_tier == "review"
    assert "failed validation" in finding.promotion_reason


def test_visible_unicode_and_allowed_layout_controls_are_not_flagged():
    item = BenchmarkItem(
        item_id="clean",
        raw={},
        task="Question",
        gold="José Medina\t—\nline two\r",
        row_uid="row-clean",
    )

    findings = list(OracleChecker().check(item))

    assert not [
        finding
        for finding in findings
        if finding.defect_type == "unexpected_invisible_or_control_gold"
    ]


def test_real_cli_preserves_review_and_confirmed_boundaries(tmp_path):
    output = tmp_path / "audit.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "benchcore.cli",
            "audit",
            str(ROOT / "tests/fixtures/oracle_proof_semantics.jsonl"),
            "--out",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))

    duplicate = next(
        finding
        for finding in report["violations"]
        if finding["defect_type"] == "conflicting_duplicate_oracle"
    )
    invisible = next(
        finding
        for finding in report["violations"]
        if finding["defect_type"] == "unexpected_invisible_or_control_gold"
    )
    assert duplicate["evidence_tier"] == "review"
    assert duplicate["evidence"]["evidence_level"] == (
        "canonical_record_oracle_surface_difference"
    )
    assert invisible["item_id"] == "q1048"
    assert invisible["evidence_tier"] == "confirmed"
