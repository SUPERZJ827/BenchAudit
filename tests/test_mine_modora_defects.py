from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mine_modora_defects.py"
DATA_DIR = ROOT / "data" / "MoDora"
SPEC = importlib.util.spec_from_file_location("mine_modora_defects", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


@pytest.fixture(scope="module")
def full_result():
    if not all((DATA_DIR / filename).is_file() for filename in mod.METHOD_FILES.values()):
        pytest.skip(
            "frozen MoDora result files are external inputs and are not tracked in git"
        )
    loaded = mod.load_data(DATA_DIR)
    return loaded, mod.analyze(loaded)


def test_e1_is_conservative_about_semantic_symbols():
    assert mod.e1("-5") != mod.e1("5")
    assert mod.e1('42" x 50"') != mod.e1("42 x 50 mm")
    assert mod.e1("José Medina") == mod.e1("  JOSÉ   MEDINA ")
    assert mod.e1("Unsettled") != mod.e1(
        "Unsettled with frequent rain and dull weather."
    )


def test_scalar_answer_is_canonicalized_to_list():
    assert mod.as_answer_list("002694") == ["002694"]
    assert mod.as_answer_list(["002694"]) == ["002694"]
    assert mod.answer_signature("002694") == mod.answer_signature(["002694"])


def test_blank_predictions_do_not_form_an_agreement_group():
    groups = mod.nonempty_e1_prediction_groups(
        {"a": "", "b": "  \t", "c": None, "d": "answer", "e": " ANSWER "}
    )
    assert groups == {"answer": ["d", "e"]}
    assert max(map(len, groups.values())) == 2


def test_all_blank_predictions_have_no_participating_group():
    groups = mod.nonempty_e1_prediction_groups({"a": "", "b": None, "c": "\n"})
    assert groups == {}
    assert max((len(methods) for methods in groups.values()), default=0) == 0


def test_invisible_character_detector_finds_zero_width_space():
    findings = mod.unexpected_invisible_characters("\u200bUnsettled\u200b")
    assert [finding["codepoint"] for finding in findings] == ["U+200B", "U+200B"]


def test_corrected_item_total_is_undefined_for_constant_item():
    assert mod.pearson([0.0] * 9, list(map(float, range(9)))) is None
    assert mod.pearson([1.0] * 9, list(map(float, range(9)))) is None


def test_frozen_input_and_metadata_conflicts(full_result):
    loaded, result = full_result
    assert loaded.ids == tuple(range(1, 1066))
    assert loaded.input_hashes == mod.EXPECTED_SHA256
    conflicts = result["metadata_conflicts"]
    q76 = [row for row in conflicts if row["questionId"] == 76]
    q181 = [row for row in conflicts if row["questionId"] == 181]
    assert any(row["field"] == "question" and row["semantic_difference_e1"] for row in q76)
    assert any(row["field"] == "answer" and row["semantic_difference_e1"] for row in q76)
    assert any(row["field"] == "question" and row["semantic_difference_e1"] for row in q181)
    assert result["canonical"][76]["question"] == "How many questions are shown in this page?"
    assert result["canonical"][76]["answer"] == ["5 questions"]


def test_empirical_anchor_counts(full_result):
    _, result = full_result
    summary = result["summary"]
    assert summary["correct_distribution"] == {
        str(key): value for key, value in mod.EXPECTED_CORRECT_DISTRIBUTION.items()
    }
    assert summary["all_wrong_items"] == 151
    assert summary["all_wrong_e1_buckets"] == {
        "divergent_1": 89,
        "shared_2_4": 55,
        "convergent_5_plus": 7,
    }
    assert summary["blank_prediction_rows_e1"] == 471
    assert summary["all_wrong_blank_prediction_rows_e1"] == 75
    assert summary["all_wrong_items_with_blank_prediction_e1"] == 62
    assert summary["all_wrong_nonempty_prediction_method_count_distribution"] == {
        "5": 1,
        "7": 10,
        "8": 51,
        "9": 89,
    }
    assert summary["all_wrong_participating_prediction_rows_e1"] == 1284
    assert summary["hard_record_inconsistency_items"] == 9
    assert summary["fact_convergence_hypothesis_items"] == 5
    assert summary["long_gold_convergence_items"] == 2
    assert summary["difficulty_inversion_items"] == 2
    assert summary["r_pb_undefined_items"] == 166


def test_q1060_is_hard_local_record_inconsistency(full_result):
    _, result = full_result
    rows = [row for row in result["hard_record_rows"] if row["questionId"] == 1060]
    assert len(rows) == 1
    assert rows[0]["evidence_level"] == "E0"
    assert "quest" in rows[0]["methods_judged_F"]
    assert "m3rag" in rows[0]["methods_judged_T"]
    triage = {row["questionId"]: row for row in result["triage_rows"]}
    assert triage[1060]["primary_verdict"] == "hard_record_inconsistency"


def test_q1048_invisible_gold_is_hard_but_convergence_is_not_fact_claim(full_result):
    _, result = full_result
    hard = [row for row in result["hard_artifact_rows"] if row["questionId"] == 1048]
    assert any(row["anomaly_type"] == "unexpected_invisible_or_control_gold" for row in hard)
    convergence = [row for row in result["convergence_rows"] if row["questionId"] == 1048]
    assert len(convergence) == 1
    assert convergence[0]["category"] == "long_gold_or_short_answer_convergence"
    triage = {row["questionId"]: row for row in result["triage_rows"]}
    assert triage[1048]["primary_verdict"] == "hard_artifact_anomaly"


def test_q110_is_not_promoted_as_fact_convergence(full_result):
    _, result = full_result
    rows = [row for row in result["convergence_rows"] if row["questionId"] == 110]
    assert len(rows) == 1
    assert rows[0]["category"] == "long_gold_or_short_answer_convergence"


def test_q994_unit_mismatch_is_review_only_not_hard(full_result):
    _, result = full_result
    assert not any(row["questionId"] == 994 for row in result["hard_record_rows"])
    assert not any(row["questionId"] == 994 for row in result["hard_artifact_rows"])
    relations = {
        row["relation_type"]
        for row in result["scoring_relation_rows"]
        if row["questionId"] == 994 and row["method"] == "udop"
    }
    assert "loose_normalization_only_containment_negative_control" in relations
    triage = {row["questionId"]: row for row in result["triage_rows"]}
    assert triage[994]["primary_verdict"] != "hard_record_inconsistency"
    assert triage[994]["primary_verdict"] != "hard_artifact_anomaly"


def test_q107_punctuation_only_conflict_is_review_not_hard(full_result):
    _, result = full_result
    assert not any(row["questionId"] == 107 for row in result["hard_record_rows"])
    assert any(
        row["questionId"] == 107
        and row["relation_type"] == "prediction_format_variant_conflicting_judge"
        for row in result["scoring_relation_rows"]
    )


def test_q895_q896_terminal_period_variant_is_not_hard(full_result):
    _, result = full_result
    assert not any(
        row["questionId"] in {895, 896} for row in result["hard_artifact_rows"]
    )
    relation_ids = {
        row["questionId"]
        for row in result["scoring_relation_rows"]
        if row["relation_type"] == "same_question_gold_terminal_punctuation_variant"
    }
    assert {895, 896}.issubset(relation_ids)


def test_primary_verdict_is_mutually_exclusive_and_complete(full_result):
    _, result = full_result
    triage = result["triage_rows"]
    allowed = {
        "hard_record_inconsistency",
        "hard_artifact_anomaly",
        "gold_or_item_hypothesis",
        "difficulty_inversion_hypothesis",
        "scoring_contract_hypothesis",
        "unresolved_all_wrong",
        "low_success_unresolved",
        "not_flagged",
    }
    assert len(triage) == 1065
    assert len({row["questionId"] for row in triage}) == 1065
    assert {row["primary_verdict"] for row in triage} <= allowed


def test_all_anchors_pass(full_result):
    _, result = full_result
    checks = mod.validate_anchors(result)
    assert checks
    assert all(checks.values()), checks


def test_findings_uses_live_counts_and_avoids_overclaim_phrases(full_result):
    _, result = full_result
    findings = mod.render_findings(result, mod.validate_anchors(result))
    assert "9 个可重放的同答案 T/F 冲突" in findings
    assert "3 个含不可见字符的 gold" in findings
    assert "q994 是固定负对照" in findings
    assert "V2 E1 保留单位符号" in findings
    for forbidden in ("真难", "gold 已错", "defect precision"):
        assert forbidden not in findings
