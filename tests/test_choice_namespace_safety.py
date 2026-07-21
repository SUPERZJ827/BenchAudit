"""Safety and recall contracts for non-Latin/non-letter MCQ encodings."""

import pytest

from benchcore.auditor import audit_items
from benchcore.checkers import OracleChecker
from benchcore.field_mapping import infer_mapping, mapping_from_dict
from benchcore.loader import build_items
from benchcore.methods import ChoiceEncodingContractChecker


def _audit(rows, *, contract_field="output_contract"):
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        contract_field: contract_field,
    })
    return audit_items(build_items(rows, mapping), checkers=[OracleChecker()])


@pytest.mark.parametrize(
    "choices,golds",
    [
        (["红", "绿", "蓝", "黑"], list("甲乙丙丁") * 2),
        (["red", "green", "blue", "black"], [1, 2, 3, 4] * 2),
        (["red", "green", "blue", "black"], [["A", "B"], ["C"]] * 4),
    ],
)
def test_valid_alternative_choice_encodings_have_zero_confirmed(choices, golds):
    rows = [{
        "id": f"q-{index}",
        "question": "Select the answer.",
        "choices": choices,
        "answer": gold,
        "output_contract": {"type": "multiple_choice"},
    } for index, gold in enumerate(golds)]

    findings = _audit(rows)

    assert [finding for finding in findings if finding.evidence_tier == "confirmed"] == []
    assert [finding for finding in findings if finding.defect_type == "invalid_choice_gold"] == []


def test_dict_choices_preserve_labels_and_have_zero_confirmed():
    rows = [{
        "id": f"dict-{index}",
        "question": "Select the answer.",
        "choices": {"甲": "red", "乙": "green", "丙": "blue"},
        "answer": ("甲", "乙", "丙")[index % 3],
        "output_contract": {"type": "multiple_choice"},
    } for index in range(8)]
    mapping = infer_mapping(rows)
    items = build_items(rows, mapping)

    findings = audit_items(items, checkers=[OracleChecker()])

    assert isinstance(items[0].choices, dict)
    assert mapping.choices == "choices"
    assert findings == []


def test_generic_mcq_contract_cannot_confirm_single_unknown_namespace():
    rows = [{
        "id": "unknown-label",
        "question": "Select the answer.",
        "choices": ["red", "green"],
        "answer": "custom-left",
        "output_contract": {"type": "multiple_choice"},
    }]

    findings = _audit(rows)

    assert len(findings) == 1
    assert findings[0].defect_type == "invalid_choice_gold"
    assert findings[0].evidence_tier == "review"


def test_declared_mcq_contract_lowers_but_does_not_remove_peer_gate():
    rows = [{
        "id": f"good-{index}",
        "question": "Select the answer.",
        "choices": ["red", "green"],
        "answer": "A" if index % 2 == 0 else "B",
        "output_contract": {"type": "multiple_choice"},
    } for index in range(20)]
    rows.append({
        "id": "bad",
        "question": "Select the answer.",
        "choices": ["red", "green"],
        "answer": "C",
        "output_contract": {"type": "multiple_choice"},
    })

    findings = _audit(rows)

    assert len(findings) == 1
    assert findings[0].evidence_tier == "confirmed"
    replay = findings[0].evidence["choice_namespace_replay"]
    assert replay["contract_declared"] is True
    assert replay["minimum_peer_records"] == 20


def test_explicit_label_namespace_can_confirm_a_single_violation():
    rows = [{
        "id": "bad",
        "question": "Select the answer.",
        "choices": ["red", "green"],
        "answer": "C",
        "output_contract": {
            "type": "multiple_choice",
            "labels": ["A", "B"],
        },
    }]

    findings = _audit(rows)

    assert len(findings) == 1
    assert findings[0].evidence_tier == "confirmed"
    assert findings[0].evidence["declared_choice_labels"] == ["A", "B"]


def test_explicit_letter_format_reports_mappable_numeric_gold_once_at_dataset_scope():
    rows = [{
        "id": "bad-format",
        "question": "Select the answer.",
        "choices": ["red", "green", "blue", "black"],
        "answer": 3,
        "output_contract": {
            "type": "multiple_choice",
            "format": "single letter A/B/C/D",
        },
    }]

    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "output_contract": "output_contract",
    })
    items = build_items(rows, mapping)
    item_findings = audit_items(items, checkers=[OracleChecker()])
    findings = audit_items(
        items,
        checkers=[],
        dataset_checkers=[ChoiceEncodingContractChecker()],
    )

    assert item_findings == []
    assert len(findings) == 1
    assert findings[0].defect_type == "choice_encoding_contract_mismatch"
    assert findings[0].evidence_tier == "review"
    assert findings[0].evidence["declared_choice_labels"] == ["A", "B", "C", "D"]


@pytest.mark.parametrize(
    "gold",
    ["(C)", "C. Days become shorter."],
)
def test_decorated_declared_label_forms_are_semantically_mappable(gold):
    rows = [{
        "id": "decorated",
        "question": "What happens in winter?",
        "choices": [
            "Days become warmer.",
            "Days become wetter.",
            "Days become shorter.",
            "Days become brighter.",
        ],
        "answer": gold,
        "output_contract": {
            "type": "multiple_choice",
            "format": "single letter A/B/C/D",
        },
    }]

    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "output_contract": "output_contract",
    })
    items = build_items(rows, mapping)
    findings = audit_items(
        items,
        checkers=[OracleChecker()],
        dataset_checkers=[ChoiceEncodingContractChecker()],
    )

    assert findings == []


def test_option_text_storage_is_one_dataset_review_not_item_critical_spam():
    rows = [{
        "id": f"text-{index}",
        "question": "What happens in winter?",
        "choices": [
            "Days become warmer.",
            "Days become wetter.",
            "Days become shorter.",
            "Days become brighter.",
        ],
        "answer": "Days become shorter.",
        "output_contract": {
            "type": "multiple_choice",
            "format": "single letter A/B/C/D",
        },
    } for index in range(60)]
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "output_contract": "output_contract",
    })
    items = build_items(rows, mapping)

    item_findings = audit_items(items, checkers=[OracleChecker()])
    dataset_findings = audit_items(
        items,
        checkers=[],
        dataset_checkers=[ChoiceEncodingContractChecker()],
    )

    assert item_findings == []
    assert len(dataset_findings) == 1
    finding = dataset_findings[0]
    assert finding.evidence_tier == "review"
    assert finding.severity == "review"
    assert finding.evidence["affected_records"] == 60


@pytest.mark.parametrize(
    "alphabet,expected_reviews",
    [
        (["Ａ", "Ｂ", "Ｃ", "Ｄ"], 0),
        (["α", "β", "γ", "δ"], 1),
        (["①", "②", "③", "④"], 1),
        (["一", "二", "三", "四"], 1),
    ],
)
def test_unseen_bijective_label_alphabets_never_expand_to_item_confirmed(
    alphabet, expected_reviews,
):
    rows = [{
        "id": f"encoded-{index}",
        "question": "Select the answer.",
        "choices": ["red", "green", "blue", "black"],
        "answer": alphabet[index % 4],
        "output_contract": {
            "type": "multiple_choice",
            "format": "single letter A/B/C/D",
        },
    } for index in range(60)]
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "output_contract": "output_contract",
    })
    items = build_items(rows, mapping)

    findings = audit_items(
        items,
        checkers=[OracleChecker()],
        dataset_checkers=[ChoiceEncodingContractChecker()],
    )

    assert [finding for finding in findings if finding.evidence_tier == "confirmed"] == []
    assert len(findings) == expected_reviews
    if findings:
        assert findings[0].defect_type == "choice_encoding_contract_mismatch"
        assert findings[0].evidence["affected_records"] == 60


def test_one_outlier_from_unknown_bijective_encoding_is_exactly_one_confirmed():
    alphabet = ["α", "β", "γ", "δ"]
    rows = [{
        "id": f"encoded-{index}",
        "question": "Select the answer.",
        "choices": ["red", "green", "blue", "black"],
        "answer": alphabet[index % 4],
        "output_contract": {
            "type": "multiple_choice",
            "format": "single letter A/B/C/D",
        },
    } for index in range(60)]
    rows[0]["answer"] = "ε"
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "output_contract": "output_contract",
    })
    items = build_items(rows, mapping)

    findings = audit_items(
        items,
        checkers=[OracleChecker()],
        dataset_checkers=[ChoiceEncodingContractChecker()],
    )

    confirmed = [finding for finding in findings if finding.evidence_tier == "confirmed"]
    reviews = [finding for finding in findings if finding.evidence_tier == "review"]
    assert len(confirmed) == 1
    assert confirmed[0].item_id == "encoded-0"
    assert len(reviews) == 1
    assert reviews[0].defect_type == "choice_encoding_contract_mismatch"
    assert reviews[0].evidence["affected_records"] == 59


@pytest.mark.parametrize(
    "row_factory",
    [
        # A valid namespace need not be close to uniformly distributed.
        lambda index: {
            "choices": ["red", "green", "blue", "black"],
            "answer": (["α"] * 48 + ["β"] * 4 + ["γ"] * 4 + ["δ"] * 4)[index],
        },
        # Real MCQ suites can mix questions with different option counts.
        lambda index: {
            "choices": [f"option-{position}" for position in range(3 + index % 3)],
            "answer": ("α", "β", "γ", "δ", "ε")[index % (3 + index % 3)],
        },
        # A dataset can contain multiple internally consistent storage encodings.
        lambda index: {
            "choices": ["red", "green", "blue", "black"],
            "answer": (
                ("α", "β", "γ", "δ")[index % 4]
                if index < 30
                else ("①", "②", "③", "④")[index % 4]
            ),
        },
    ],
)
def test_irregular_unknown_choice_namespaces_remain_review_only(row_factory):
    rows = []
    for index in range(60):
        encoded = row_factory(index)
        rows.append({
            "id": f"irregular-{index}",
            "question": "Select the answer.",
            "output_contract": {
                "type": "multiple_choice",
                "format": "single letter A/B/C/D",
            },
            **encoded,
        })
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "output_contract": "output_contract",
    })

    findings = audit_items(
        build_items(rows, mapping),
        checkers=[OracleChecker()],
        dataset_checkers=[ChoiceEncodingContractChecker()],
    )

    assert [finding for finding in findings if finding.evidence_tier == "confirmed"] == []


def test_small_unknown_choice_namespace_remains_review_only():
    rows = [{
        "id": f"small-{index}",
        "question": "Select the answer.",
        "choices": ["red", "green", "blue", "black"],
        "answer": ("α", "β", "γ", "δ", "α")[index],
        "output_contract": {
            "type": "multiple_choice",
            "format": "single letter A/B/C/D",
        },
    } for index in range(5)]
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "output_contract": "output_contract",
    })

    findings = audit_items(
        build_items(rows, mapping),
        checkers=[OracleChecker()],
        dataset_checkers=[ChoiceEncodingContractChecker()],
    )

    assert [finding for finding in findings if finding.evidence_tier == "confirmed"] == []
