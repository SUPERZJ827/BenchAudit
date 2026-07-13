from dataclasses import asdict

from benchcore.defect_injection import inject_defects, score_injected_report
from benchcore.schema import FieldMapping


MAPPING = FieldMapping(
    item_id="id",
    task="question",
    context=["context"],
    choices="choices",
    gold="answer",
    evaluator="evaluator",
)


def test_injection_is_deterministic_and_does_not_mutate_source():
    source = [{
        "id": "q1",
        "question": "Pick one",
        "context": "Passage",
        "choices": ["A", "B", "C"],
        "answer": "A",
        "evaluator": {"type": "exact"},
    }]

    first = inject_defects(source, MAPPING, seed=7, mutations_per_item=4)
    second = inject_defects(source, MAPPING, seed=7, mutations_per_item=4)

    assert [result.row for result in first] == [result.row for result in second]
    assert source[0]["question"] == "Pick one"
    assert source[0]["choices"] == ["A", "B", "C"]
    assert len({result.provenance.mutation_id for result in first}) == len(first)
    assert all(result.provenance.before_sha256 != result.provenance.after_sha256 for result in first)


def test_duplicate_choice_injection_preserves_gold_and_records_provenance():
    source = [{
        "id": "q1", "question": "Pick", "choices": ["A", "B"], "answer": "A",
    }]

    result = inject_defects(
        source,
        MAPPING,
        seed=1,
        operators=["duplicate_choice"],
    )[0]

    assert result.row["choices"] == ["A", "A"]
    assert result.row["answer"] == "A"
    assert result.provenance.defect_type == "duplicate_choices"
    assert result.row["_injected_defect"]["operator"] == "duplicate_choice"


def test_score_injected_report_computes_exact_per_type_recall():
    source = [{"id": "q1", "question": "Pick", "choices": ["A", "B"], "answer": "A"}]
    results = inject_defects(
        source,
        MAPPING,
        seed=1,
        operators=["duplicate_choice", "remove_task"],
        mutations_per_item=2,
    )
    manifest = {"mutations": [asdict(result.provenance) for result in results]}
    duplicate = next(result for result in results if result.provenance.defect_type == "duplicate_choices")
    report = {"violations": [{
        "item_id": duplicate.provenance.mutated_item_id,
        "defect_type": "duplicate_choices",
    }]}

    score = score_injected_report(manifest, report)

    assert score["expected"] == 2
    assert score["detected"] == 1
    assert score["recall"] == 0.5
    assert score["per_defect_type"]["duplicate_choices"]["recall"] == 1.0
    assert len(score["misses"]) == 1


def test_wrong_gold_preserves_choice_label_representation():
    source = [{
        "id": "q1", "question": "Pick", "choices": ["red", "green", "blue"],
        "answer": "B",
    }]

    result = inject_defects(
        source,
        MAPPING,
        seed=3,
        operators=["wrong_gold"],
    )[0]

    assert result.row["answer"] in {"A", "C"}
    assert result.row["answer"] != "B"
