import json
from pathlib import Path

import pytest

from benchcore.field_mapping import infer_mapping
from benchcore.loader import build_items, load_rows


def test_json_list_never_silently_discards_non_object_rows(tmp_path: Path):
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps([{"id": 1}, "bad", {"id": 2}]), encoding="utf-8")

    with pytest.raises(ValueError, match="never silently discarded"):
        load_rows(path)


def test_wrapped_json_never_silently_discards_non_object_rows(tmp_path: Path):
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps({"items": [{"id": 1}, 7]}), encoding="utf-8")

    with pytest.raises(ValueError, match="index 1"):
        load_rows(path)


def test_nested_paths_are_inferred_and_resolved_case_insensitively():
    rows = [{
        "Record": {"ID": "n-1"},
        "Input": {"Question": "What is 2+2?", "Context": "arithmetic"},
        "Output": {"Answer": "4"},
    }]

    mapping = infer_mapping(rows)
    item = build_items(rows, mapping)[0]

    assert mapping.item_id == "Record.ID"
    assert mapping.task == "Input.Question"
    assert mapping.gold == "Output.Answer"
    assert "Input.Context" in mapping.context
    assert item.item_id == "n-1"
    assert item.task == "What is 2+2?"
    assert item.gold == "4"
    assert item.context["Input.Context"] == "arithmetic"


def test_inferred_mapping_uses_per_row_fallback_for_complementary_fields():
    rows = [
        {"id": "a", "question": "q1", "answer": "x", "label": ""},
        {"id": "b", "question": "q2", "answer": "", "label": "y"},
    ]

    mapping = infer_mapping(rows)
    items = build_items(rows, mapping)

    assert mapping.gold == "answer"
    assert [item.gold for item in items] == ["x", "y"]
    provenance = items[1].metadata["_mapping_provenance"]["fields"]["gold"]
    assert provenance["resolved_key"] == "label"
    assert provenance["fallback_used"] is True
    assert provenance["row_status"] == "resolved"


def test_tsv_rows_are_supported(tmp_path: Path):
    path = tmp_path / "rows.tsv"
    path.write_text("id\tquestion\tanswer\n1\tQ\tA\n", encoding="utf-8")

    assert load_rows(path) == [{"id": "1", "question": "Q", "answer": "A"}]


def test_parquet_rows_are_supported(tmp_path: Path):
    pyarrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")
    path = tmp_path / "rows.parquet"
    parquet.write_table(
        pyarrow.table({"id": [1], "question": ["Q"], "answer": ["A"]}),
        path,
    )

    assert load_rows(path) == [{"id": 1, "question": "Q", "answer": "A"}]
