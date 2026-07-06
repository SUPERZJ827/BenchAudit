import json

from scripts.export_workspacebench_jsonl import parse_json_field, with_benchcore_fields


def test_parse_json_field_returns_default_on_bad_json():
    assert parse_json_field("", default=[]) == []
    assert parse_json_field("not json", default=["x"]) == ["x"]
    assert parse_json_field("[1, 2]", default=[]) == [1, 2]


def test_with_benchcore_fields_preserves_workspace_artifacts():
    row = {
        "absolute_id": 3,
        "language": "en",
        "persona": "Backend Developer",
        "task": "Create a dependency summary.",
        "task_diff": "medium",
        "output_files": json.dumps(["deps.md"]),
        "rubrics": json.dumps(["Was deps.md created?", "Does it list 43 dependencies?"]),
        "rubric_types": json.dumps(["Basic Evaluation", "Outcome Evaluation"]),
        "data_manifest": json.dumps(
            [{"filename": "dependency_item_1.md", "stored_relpath": "data/x.md"}]
        ),
        "file_dep_graph": json.dumps(
            [{"from": "dependency_item_1.md", "to": "deps.md"}]
        ),
        "tested_capabilities": json.dumps(["Task-Providing File Utilization"]),
    }

    out = with_benchcore_fields(row)

    assert out["item_id"] == "workspacebench-3"
    assert out["task"] == "Create a dependency summary."
    assert out["rubrics"] == ["Was deps.md created?", "Does it list 43 dependencies?"]
    assert out["output_contract"]["type"] == "workspace_files"
    assert out["output_contract"]["required_files"] == ["deps.md"]
    assert out["evaluator"]["type"] == "workspacebench_rubric"
    assert out["evaluator"]["rubric_types"] == [
        "Basic Evaluation",
        "Outcome Evaluation",
    ]
    assert out["context"]["data_manifest"][0]["filename"] == "dependency_item_1.md"
    assert out["context"]["file_dep_graph"][0]["to"] == "deps.md"
    assert out["metadata"]["absolute_id"] == 3
