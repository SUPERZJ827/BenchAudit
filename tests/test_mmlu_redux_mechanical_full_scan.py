from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from scripts import scan_mmlu_redux_mechanical_full as scan


def row(
    item_id: str = "fixture-1",
    *,
    choices: list[str] | None = None,
    gold: object = "A",
    label: str = "ok",
    include_gold: bool = True,
) -> dict:
    value = {
        "id": item_id,
        "question": "Synthetic question",
        "choices": choices or ["alpha", "beta", "gamma", "delta"],
        "evaluator": {"type": "multiple_choice"},
        "metadata": {"subject": "synthetic", "error_type": label},
    }
    if include_gold:
        value["gold"] = gold
    return value


def common(item_id: str = "fixture-1", *, label: str = "ok") -> dict:
    return {
        "item_id": item_id,
        "subject": "synthetic",
        "redux_error_type": label,
        "redux_label_class": scan.label_class(label),
        "partition": "development_1087",
        "rule_input_fields_sha256": "0" * 64,
    }


def tiers(value: list[dict]) -> set[str]:
    return {finding["tier"] for finding in value}


def test_r1_byte_identical_hits_all_cumulative_tiers() -> None:
    value = row(choices=["same", "same", "other", "last"])
    assert tiers(scan.r1_findings(value, common())) == {"T1", "T2", "T3"}


def test_r1_nfkc_case_and_whitespace_difference_is_t2_only() -> None:
    value = row(choices=["Ａ  B", "a\tb", "other", "last"])
    assert tiers(scan.r1_findings(value, common())) == {"T2", "T3"}


def test_r1_boundary_punctuation_difference_is_t3_only() -> None:
    value = row(choices=["(Answer)", "answer!", "other", "last"])
    assert tiers(scan.r1_findings(value, common())) == {"T3"}


def test_r1_normalized_empty_values_do_not_create_duplicate() -> None:
    value = row(choices=["!!!", "???", "other", "last"])
    assert scan.r1_findings(value, common()) == []


@pytest.mark.parametrize("gold", ["A", " b ", "c", "D"])
def test_r2_valid_labels_map_uniquely(gold: str) -> None:
    assert scan.r2_finding(row(gold=gold), common()) is None


@pytest.mark.parametrize(
    ("value", "include_gold", "expected"),
    [
        (None, False, "gold_missing"),
        (None, True, "gold_non_string"),
        ("", True, "gold_empty"),
        ("E", True, "gold_outside_choice_domain"),
    ],
)
def test_r2_invalid_gold_is_deterministically_classified(
    value: object, include_gold: bool, expected: str
) -> None:
    finding = scan.r2_finding(row(gold=value, include_gold=include_gold), common())
    assert finding is not None
    assert finding["evidence"]["reason"] == expected


def test_r2_gold_pointing_to_empty_choice_triggers() -> None:
    finding = scan.r2_finding(
        row(choices=["alpha", " \t", "gamma", "delta"], gold="B"), common()
    )
    assert finding is not None
    assert finding["evidence"]["reason"] == "gold_points_to_empty_choice"
    assert finding["implicated_indices"] == [1]


def test_r3_empty_and_unicode_whitespace_choices_trigger() -> None:
    finding = scan.r3_finding(
        row(choices=["", "\u2003", "gamma", "delta"]), common()
    )
    assert finding is not None
    assert finding["implicated_indices"] == [0, 1]


def test_clean_item_triggers_no_rule() -> None:
    value = row()
    assert scan.r1_findings(value, common()) == []
    assert scan.r2_finding(value, common()) is None
    assert scan.r3_finding(value, common()) is None


def test_item_sets_preserve_overlap_without_inflating_union() -> None:
    findings = [
        {"item_id": "a", "rule": "R1_duplicate_choices", "tier": "T3"},
        {"item_id": "a", "rule": "R2_unresolvable_declared_gold", "tier": None},
        {"item_id": "b", "rule": "R3_empty_choice", "tier": None},
    ]
    sets = scan.item_sets(findings)
    union = sets["R1_T3"] | sets["R2"] | sets["R3"]
    assert union == {"a", "b"}


def test_expert_is_a_separate_label_class() -> None:
    assert scan.label_class("ok") == "ok"
    assert scan.label_class("expert") == "expert_abstention"
    assert scan.label_class("wrong_groundtruth") == "explicit_defect"


def test_schema_failures_are_not_coerced_or_skipped() -> None:
    seen: set[str] = set()
    scan.validate_row(row(include_gold=False), 1, seen)
    with pytest.raises(scan.ScanError, match="choice_not_string"):
        scan.validate_row(row("bad", choices=["a", "b", "c", 4]), 2, seen)
    with pytest.raises(scan.ScanError, match="duplicate_id"):
        scan.validate_row(row(), 3, seen)
    with pytest.raises(scan.ScanError, match="unknown_redux_label"):
        scan.validate_row(row("unknown", label="new_label"), 4, seen)


def test_synthetic_stable_outputs_are_byte_identical() -> None:
    known = row(
        scan.KNOWN_POSITIVE,
        choices=["alpha", "beta", "same", "same"],
        label="ok",
    )
    clean = row("unused-clean", label="expert")
    rows = [known, clean]
    used = {scan.KNOWN_POSITIVE}
    unused = {"unused-clean"}
    first_findings = scan.scan_rows(rows, used, unused)
    second_findings = scan.scan_rows(rows, used, unused)
    first_summary = scan.summarize(rows, first_findings, used, unused)
    second_summary = scan.summarize(rows, second_findings, used, unused)
    first_findings_bytes = b"".join(scan.stable_bytes(value) for value in first_findings)
    second_findings_bytes = b"".join(scan.stable_bytes(value) for value in second_findings)
    assert first_findings_bytes == second_findings_bytes
    assert scan.build_report(first_summary, first_findings) == scan.build_report(
        second_summary, second_findings
    )


def test_incomplete_scan_publishes_only_raw_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail():
        raise scan.ScanError("fixture failure")

    monkeypatch.setattr(scan, "load_bindings", fail)
    output = tmp_path / "failed"
    with pytest.raises(scan.ScanError, match="fixture failure"):
        scan.run(output)
    assert {path.name for path in output.iterdir()} == {"raw_run.json"}
    raw = json.loads((output / "raw_run.json").read_text(encoding="utf-8"))
    assert raw["outcome"] == "SCAN_INCOMPLETE"


def test_scanner_has_no_llm_api_network_or_production_import_path() -> None:
    source = inspect.getsource(scan)
    forbidden = (
        "import requests",
        "import urllib",
        "import socket",
        "llm_client",
        "LLMClient(",
        "os.environ",
        "from benchcore",
        "import benchcore",
    )
    for fragment in forbidden:
        assert fragment not in source


@pytest.mark.skipif(not scan.DATASET.is_file(), reason="frozen dataset artifact is external to Git")
def test_frozen_known_positive_control_matches_all_r1_tiers() -> None:
    rows, used, unused = scan.load_bindings()
    by_id = {value["id"]: value for value in rows}
    assert scan.KNOWN_POSITIVE in used
    assert scan.KNOWN_POSITIVE not in unused
    findings = scan.r1_findings(by_id[scan.KNOWN_POSITIVE], common(scan.KNOWN_POSITIVE))
    assert tiers(findings) == {"T1", "T2", "T3"}


def test_committed_outputs_are_self_consistent_when_present() -> None:
    output = scan.ROOT / "reports/mmlu_redux_mechanical_scan_20260803"
    receipt_path = output / "receipt.json"
    if not receipt_path.is_file():
        pytest.skip("full-scan result has not been published yet")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["outcome"] == "SCAN_COMPLETE"
    assert scan.sha256_file(output / "findings.jsonl") == receipt["outputs"]["findings_sha256"]
    assert scan.sha256_file(output / "REPORT.md") == receipt["outputs"]["report_sha256"]
    assert receipt["execution"]["production_activation"] is False
