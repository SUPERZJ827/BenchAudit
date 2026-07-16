import hashlib
import json
from pathlib import Path

import pytest

from benchcore.workspace_invariants import WorkspaceArtifactInvariantChecker
from benchcore.workspace_visibility import (
    SCHEMA_VERSION,
    WorkspaceRunnerVisibilityIndex,
)
from tests.test_workspace_invariants import make_item


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _visibility_report(dataset: Path, generator: Path) -> dict:
    digest = _sha(generator.read_bytes())
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset": {"sha256": _sha(dataset.read_bytes())},
        "archive": {
            "revision": "a" * 40,
            "central_directory_sha256": "b" * 64,
            "entries": 10,
            "range_only": True,
        },
        "runner": {
            "commit": "c" * 40,
            "files": [{"path": "runner.py", "sha256": "d" * 64}],
            "verified_semantics": {
                "raw_workspace_copied_to_standard": True,
                "standard_workspace_copied_to_agent_case": True,
                "task_data_exposed_in_judge_view": True,
            },
        },
        "findings": [{
            "item_id": "workspacebench-1",
            "status": "confirmed",
            "task_package_sha256": digest,
            "visibility": {
                "task_package_present": True,
                "agent_visible": True,
                "evaluator_visible": True,
                "visibility_verified": True,
            },
            "exact_agent_workspace_matches": [{
                "archive_member": "Role_Workdir/project/data/generate_report.py",
                "sha256": digest,
                "byte_identical_to_task_package": True,
            }],
        }],
    }


def test_online_reverified_visibility_still_needs_oracle_output_binding(
    tmp_path: Path, monkeypatch,
):
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"id":1}\n', encoding="utf-8")
    generator = tmp_path / "generate_report.py"
    generator.write_text(
        "from pathlib import Path\nPath('../output_cc/report.md').write_text('gold')\n",
        encoding="utf-8",
    )
    report = tmp_path / "visibility.json"
    report.write_text(
        json.dumps(_visibility_report(dataset, generator)), encoding="utf-8",
    )

    digest = _sha(generator.read_bytes())
    monkeypatch.setattr(
        "benchcore.workspace_visibility._online_reverify_report",
        lambda *args, **kwargs: {("workspacebench-1", digest)},
    )
    index = WorkspaceRunnerVisibilityIndex.load(
        report, dataset_path=dataset, online_reverify=True,
    )
    findings = list(
        WorkspaceArtifactInvariantChecker(
            allowed_roots=[tmp_path], visibility_index=index,
        ).check(
            make_item(generator),
        )
    )
    leak = next(row for row in findings if row.defect_type == "solution_leak")

    assert leak.evidence_tier == "review"
    assert leak.review_only
    assert leak.proof_kind == "actor_visibility_replay"
    assert leak.evidence["visibility"]["agent_visible"] is True
    assert leak.evidence["visibility_transcript_sha256"] == index.transcript_sha256
    assert leak.evidence["online_reverified"] is True


def test_self_consistent_transcript_without_online_replay_stays_review(tmp_path: Path):
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"id":1}\n', encoding="utf-8")
    generator = tmp_path / "generate_report.py"
    generator.write_text("output_cc", encoding="utf-8")
    report = tmp_path / "visibility.json"
    report.write_text(
        json.dumps(_visibility_report(dataset, generator)), encoding="utf-8",
    )

    index = WorkspaceRunnerVisibilityIndex.load(report, dataset_path=dataset)
    leak = next(
        row
        for row in WorkspaceArtifactInvariantChecker(
            allowed_roots=[tmp_path], visibility_index=index,
        ).check(
            make_item(generator),
        )
        if row.defect_type == "solution_leak"
    )

    assert leak.evidence_tier == "review"
    assert leak.review_only
    assert leak.evidence["online_reverified"] is False


def test_visibility_transcript_is_bound_to_exact_dataset_bytes(tmp_path: Path):
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"id":1}\n', encoding="utf-8")
    generator = tmp_path / "generate_report.py"
    generator.write_text("output_cc", encoding="utf-8")
    report = tmp_path / "visibility.json"
    report.write_text(
        json.dumps(_visibility_report(dataset, generator)), encoding="utf-8",
    )
    dataset.write_text('{"id":2}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="different dataset"):
        WorkspaceRunnerVisibilityIndex.load(report, dataset_path=dataset)


def test_visibility_transcript_rejects_unverified_runner_semantics(tmp_path: Path):
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"id":1}\n', encoding="utf-8")
    generator = tmp_path / "generate_report.py"
    generator.write_text("output_cc", encoding="utf-8")
    value = _visibility_report(dataset, generator)
    value["runner"]["verified_semantics"]["standard_workspace_copied_to_agent_case"] = False
    report = tmp_path / "visibility.json"
    report.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="semantics"):
        WorkspaceRunnerVisibilityIndex.load(report, dataset_path=dataset)
