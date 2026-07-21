"""Public fail-closed fixtures for structurally unfamiliar benchmarks.

These are behavior-level safety tests, not copies of the frozen red-team set.
Clean but unfamiliar schemas must not acquire an automatic ``confirmed`` bug;
the paired positive controls prevent a trivial global evidence downgrade.
"""

import pytest

from benchcore.auditor import audit_items
from benchcore.checkers import OracleChecker
from benchcore.field_mapping import infer_mapping, mapping_from_dict
from benchcore.loader import build_items


@pytest.mark.parametrize(
    "rows",
    [
        # Natural-language inference: label and sentence pair are not MCQ fields.
        [{
            "uid": "nli-1",
            "premise": "A person is running.",
            "hypothesis": "Someone is moving.",
            "label": "entailment",
        }],
        # Summarization: a reference is an open text target, not a choice label.
        [{
            "id": "summ-1",
            "article": "The council approved the proposal after a public vote.",
            "instruction": "Summarize the article in one sentence.",
            "reference": "The council approved the proposal.",
            "metric": "rouge",
        }],
        # Code generation: tests describe an evaluator rather than a gold answer.
        [{
            "task_id": "code-1",
            "prompt": "Implement add(a, b).",
            "tests": ["assert add(2, 3) == 5"],
        }],
        # Tabular QA: table context and a scalar answer are ordinary valid fields.
        [{
            "question_id": "table-1",
            "question": "What is the value in row B?",
            "table": {"name": ["A", "B"], "value": [2, 4]},
            "answer": "4",
        }],
        # Retrieval/ranking: candidates and target live in different namespaces.
        [{
            "id": f"rank-{index}",
            "query": "capital of France",
            "candidates": ["doc-a", "doc-b", "doc-c"],
            "target": "document-17",
        } for index in range(5)],
        # Multilingual MCQ with a valid explicit label.
        [{
            "id": "zh-mcq-1",
            "question": "法国的首都是？",
            "options": ["巴黎", "伦敦", "罗马"],
            "correct_answer": "A",
        }],
        # Multi-answer gold is not safely reduced to a scalar choice label.
        [{
            "id": "multi-1",
            "question": "Select all prime numbers.",
            "choices": ["2", "3", "4"],
            "gold": ["A", "B"],
            "answer_type": "multiple_select",
        }],
        # A dict-valued candidate pool is not automatically a choice list.
        [{
            "id": "dict-choice-1",
            "query": "Find the relevant record.",
            "candidates": {"left": "record-a", "right": "record-b"},
            "target": "record-a",
        }],
    ],
)
def test_clean_unfamiliar_schema_has_zero_confirmed_findings(rows):
    items = build_items(rows, infer_mapping(rows))

    findings = audit_items(items)

    assert [finding for finding in findings if finding.evidence_tier == "confirmed"] == []


def test_positive_control_strict_arithmetic_remains_confirmed():
    rows = [{
        "id": "bad-math",
        "question": "What is (2 + 2) * 3?",
        "answer": "11",
    }]
    mapping = mapping_from_dict({
        "item_id": "id", "task": "question", "gold": "answer",
    })

    findings = audit_items(build_items(rows, mapping), checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].defect_type == "wrong_gold_answer"
    assert findings[0].evidence_tier == "confirmed"


def test_positive_control_declared_choice_contract_remains_confirmed():
    rows = [{
        "id": "bad-choice",
        "question": "Pick one.",
        "choices": ["alpha", "beta"],
        "answer": "C",
        "output_contract": {"type": "multiple_choice", "labels": ["A", "B"]},
    }]
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "output_contract": "output_contract",
    })

    findings = audit_items(build_items(rows, mapping), checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].defect_type == "invalid_choice_gold"
    assert findings[0].evidence_tier == "confirmed"
