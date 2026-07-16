import json
from pathlib import Path

import pytest

from scripts.run_workspace_grounding_experiment import (
    WORKSPACE_DATASET_REVISION,
    build_experiment_items,
    confusion_metrics,
    experiment_signature,
    read_existing,
)


def weak_row(task="任务", label="有依据"):
    return {
        "task_id": "1",
        "language": "cn",
        "task": task,
        "output_files": json.dumps(["report.md"], ensure_ascii=False),
        "rubric_index": "0",
        "rubric": "是否创建 report.md？",
        "rubric_type": "基础评估",
        "basis_label": label,
        "confidence": "0.9",
    }


def test_metrics_do_not_turn_operationally_missing_rows_into_uncertain():
    truth = {
        ("1", 0): weak_row(),
        ("2", 0): {**weak_row(), "task_id": "2", "basis_label": "无依据"},
    }
    predictions = [{
        "task_id": "1", "rubric_index": 0, "label": "supported",
        "split": "analysis",
    }]

    metrics = confusion_metrics(truth, predictions)

    assert metrics["rows"] == 1
    assert metrics["expected_rows"] == 2
    assert metrics["coverage"] == 0.5
    assert metrics["operational_missing_rows"] == 1
    assert metrics["unresolved_rate"] == 0.0


def test_resume_ignores_operational_failures_and_other_signatures(tmp_path: Path):
    path = tmp_path / "rows.jsonl"
    rows = [
        {"task_id": "1", "rubric_index": 0, "run_signature": "x", "label": "supported"},
        {
            "task_id": "1", "rubric_index": 1, "run_signature": "x", "label": "uncertain",
            "scanner": {"operational_failure": True},
        },
        {"task_id": "1", "rubric_index": 2, "run_signature": "y", "label": "supported"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    existing = read_existing(path, "x")

    assert set(existing) == {("1", 0)}


def test_signature_changes_with_workspace_or_provider(tmp_path: Path):
    dataset = tmp_path / "data.jsonl"
    dataset.write_text("{}\n", encoding="utf-8")
    common = dict(
        dataset_path=dataset,
        workspace_snapshot_sha256="a" * 64,
        model="model",
        base_url="https://one.invalid",
        temperature=0.0,
        max_tokens=1000,
        dry_run=False,
        verify=True,
        min_confidence=0.55,
        batch_size=1,
    )

    first = experiment_signature(**common)
    second = experiment_signature(**{**common, "workspace_snapshot_sha256": "b" * 64})
    third = experiment_signature(**{**common, "base_url": "https://two.invalid"})

    assert len({first, second, third}) == 3


def test_alignment_gate_rejects_cross_language_or_task_mix(tmp_path: Path):
    input_file = tmp_path / "source.txt"
    input_file.write_text("facts", encoding="utf-8")
    row = {
        "absolute_id": 1,
        "item_id": "workspacebench-1",
        "language": "cn",
        "task": "错误任务",
        "output_files": ["report.md"],
        "rubrics": ["是否创建 report.md？"],
        "rubric_types": ["基础评估"],
        "input_files": [str(input_file)],
        "context": {"data_manifest": [], "file_dep_graph": []},
        "output_contract": {"type": "workspace_files", "required_files": ["report.md"]},
        "evaluator": {
            "type": "workspacebench_rubric",
            "rubrics": ["是否创建 report.md？"],
            "rubric_types": ["基础评估"],
        },
        "metadata": {
            "absolute_id": 1,
            "language": "cn",
            "source_revision": WORKSPACE_DATASET_REVISION,
        },
    }
    dataset = tmp_path / "rows.jsonl"
    dataset.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="alignment gate failed"):
        build_experiment_items(dataset, [weak_row(task="正确任务")])
