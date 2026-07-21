import json
from pathlib import Path

from benchcore.schema import BenchmarkItem
from benchcore.methods import ContractConsistencyChecker
from benchcore.loader import explicit_mapping_provenance
from benchcore.workspace_invariants import (
    WorkspaceArtifactInvariantChecker,
    collect_workspace_invariant_issues,
    workspace_artifact_manifest,
)


def make_item(input_path: Path, **overrides) -> BenchmarkItem:
    rubric = "Was report.md created?"
    raw = {
        "task": "Read source.txt and create report.md.",
        "rubrics": [rubric],
        "rubric_types": ["Basic Evaluation"],
        "output_files": ["report.md"],
        "input_files": [str(input_path)],
        "data_manifest": [{
            "filename": "source.txt",
            "stored_relpath": f"data/{input_path.name}",
        }],
        "file_dep_graph": [{"from": "source.txt", "to": "report.md"}],
        "workspace_inventory_complete": True,
        "workspace_inventory": ["source.txt", "report.md"],
    }
    raw.update(overrides.pop("raw", {}))
    metadata = dict(overrides.pop("metadata", {}) or {})
    metadata["_mapping_provenance"] = explicit_mapping_provenance(
        adapter_id="test_workspacebench_fixture",
        adapter_version="1",
        raw=raw,
        field_bindings={
            "task": "task",
            "context": ["data_manifest", "file_dep_graph"],
            "output_contract": "output_files",
            "evaluator": "rubrics",
        },
    )
    return BenchmarkItem(
        item_id="workspacebench-1",
        raw=raw,
        task="Read source.txt and create report.md.",
        context={
            "data_manifest": raw["data_manifest"],
            "file_dep_graph": raw["file_dep_graph"],
            "workspace_inventory_complete": raw["workspace_inventory_complete"],
            "workspace_inventory": raw["workspace_inventory"],
        },
        output_contract={"type": "workspace_files", "required_files": ["report.md"]},
        evaluator={
            "type": "workspacebench_rubric",
            "rubrics": [rubric],
            "rubric_types": ["Basic Evaluation"],
        },
        metadata=metadata,
        **overrides,
    )


def test_clean_workspace_artifacts_have_no_invariant_issue(tmp_path: Path):
    source = tmp_path / "0123456789abcdef_source.txt"
    source.write_text("facts", encoding="utf-8")

    assert collect_workspace_invariant_issues(
        make_item(source), allowed_roots=[tmp_path],
    ) == []


def test_scalar_contract_checker_skips_workspace_rubric_artifacts(tmp_path: Path):
    source = tmp_path / "0123456789abcdef_source.txt"
    source.write_text("facts", encoding="utf-8")
    item = make_item(source)
    item.output_contract["required_files"] = ["report.json"]
    item.evaluator["rubrics"] = ["Does report.json contain total 42?"]

    assert list(ContractConsistencyChecker().check(item)) == []


def test_manifest_and_dependency_graph_breaks_are_confirmed(tmp_path: Path):
    source = tmp_path / "0123456789abcdef_source.txt"
    source.write_text("facts", encoding="utf-8")
    item = make_item(source)
    item.context["data_manifest"] = [{
        "filename": "missing.csv", "stored_relpath": "data/missing.csv",
    }]
    item.context["file_dep_graph"] = [{"from": "missing.csv", "to": "ghost.md"}]

    issues = collect_workspace_invariant_issues(item, allowed_roots=[tmp_path])
    assert [issue.defect_type for issue in issues] == [
        "artifact_data_gap", "artifact_data_gap",
    ]
    assert all(not issue.review_only for issue in issues)


def test_distinct_bytes_with_one_logical_input_name_are_confirmed(tmp_path: Path):
    first = tmp_path / "0123456789abcdef_first.xlsx"
    second = tmp_path / "fedcba9876543210_second.xlsx"
    first.write_bytes(b"first workbook bytes")
    second.write_bytes(b"second workbook bytes")
    item = make_item(first, raw={
        "input_files": [str(first), str(second)],
        "data_manifest": [
            {"filename": "table.xlsx", "stored_relpath": f"data/{first.name}"},
            {"filename": "table.xlsx", "stored_relpath": f"data/{second.name}"},
        ],
        "file_dep_graph": [{"from": "table.xlsx", "to": "report.md"}],
    })
    item.context["data_manifest"] = item.raw["data_manifest"]

    violations = list(
        WorkspaceArtifactInvariantChecker(allowed_roots=[tmp_path]).check(item)
    )
    collision = next(
        row for row in violations if row.defect_type == "ambiguous_input_filename"
    )
    assert collision.evidence_tier == "confirmed"
    rows = collision.evidence["ambiguous_input_filenames"]
    assert rows[0]["logical_filename"] == "table.xlsx"
    assert len({entry["content_sha256"] for entry in rows[0]["entries"]}) == 2


def test_same_bytes_with_one_logical_input_name_is_not_a_collision(tmp_path: Path):
    first = tmp_path / "0123456789abcdef_first.xlsx"
    second = tmp_path / "fedcba9876543210_second.xlsx"
    first.write_bytes(b"identical workbook bytes")
    second.write_bytes(b"identical workbook bytes")
    item = make_item(first, raw={
        "input_files": [str(first), str(second)],
        "data_manifest": [
            {"filename": "table.xlsx", "stored_relpath": f"data/{first.name}"},
            {"filename": "table.xlsx", "stored_relpath": f"data/{second.name}"},
        ],
    })
    item.context["data_manifest"] = item.raw["data_manifest"]

    assert not any(
        issue.defect_type == "ambiguous_input_filename"
        for issue in collect_workspace_invariant_issues(item, allowed_roots=[tmp_path])
    )


def test_task_local_manifest_does_not_prove_workspace_graph_is_dangling(tmp_path: Path):
    source = tmp_path / "0123456789abcdef_source.txt"
    source.write_text("facts", encoding="utf-8")
    item = make_item(source)
    item.context.pop("workspace_inventory_complete")
    item.context.pop("workspace_inventory")
    item.raw.pop("workspace_inventory_complete")
    item.raw.pop("workspace_inventory")
    item.context["file_dep_graph"] = [
        {"from": "file_from_large_role_workspace.xlsx", "to": "report.md"},
    ]

    issues = collect_workspace_invariant_issues(item, allowed_roots=[tmp_path])

    assert not any("dependency-graph" in issue.message for issue in issues)


def test_duplicate_metadata_views_must_agree(tmp_path: Path):
    source = tmp_path / "0123456789abcdef_source.txt"
    source.write_text("facts", encoding="utf-8")
    item = make_item(source)
    item.raw["output_files"] = json.dumps(["wrong.md"])
    item.raw["rubrics"] = json.dumps(["Wrong rubric"])
    item.evaluator["rubric_types"] = ["Basic Evaluation", "Extra"]

    issues = collect_workspace_invariant_issues(item, allowed_roots=[tmp_path])
    assert {issue.defect_type for issue in issues} == {
        "output_evaluator_contract_mismatch", "schema_drift",
    }
    assert len(issues) == 3


def test_task_package_reference_generator_requires_actor_visibility_replay(tmp_path: Path):
    generator = tmp_path / "generate_report.py"
    generator.write_text(
        "from pathlib import Path\nPath('../output_cc/report.md').write_text('answer')\n",
        encoding="utf-8",
    )
    item = make_item(generator, raw={
        "data_manifest": [{
            "filename": "generate_report.py",
            "stored_relpath": "data/generate_report.py",
        }],
        "file_dep_graph": [{"from": "generate_report.py", "to": "report.md"}],
    })

    violations = list(
        WorkspaceArtifactInvariantChecker(allowed_roots=[tmp_path]).check(item)
    )
    leak = next(row for row in violations if row.defect_type == "solution_leak")
    assert leak.review_only
    assert leak.evidence["evidence_level"] == "task_package_static_execution_intent"
    assert not leak.evidence["visibility"]["visibility_verified"]


def test_integrity_manifest_records_hashes_and_coverage(tmp_path: Path):
    source = tmp_path / "0123456789abcdef_source.txt"
    source.write_text("facts", encoding="utf-8")

    result = workspace_artifact_manifest(
        [make_item(source)], allowed_roots=[tmp_path],
    )

    assert result["summary"]["byte_coverage"] == 1.0
    assert result["summary"]["materialized_files"] == 1
    assert len(result["files"][0]["sha256"]) == 64


def test_absolute_path_outside_allowed_root_is_blocked(tmp_path: Path):
    package = tmp_path / "package"
    package.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("must not be read", encoding="utf-8")
    item = make_item(outside)

    issues = collect_workspace_invariant_issues(item, package)

    blocked = next(
        issue for issue in issues
        if issue.evidence.get("evidence_level") == "path_policy_block"
    )
    assert blocked.review_only
    assert blocked.evidence["blocked_paths"][0]["resolved"] == str(outside.resolve())


def test_symlink_escape_is_blocked_after_realpath_resolution(tmp_path: Path):
    package = tmp_path / "package"
    package.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("must not be read", encoding="utf-8")
    link = package / "source.txt"
    link.symlink_to(outside)
    item = make_item(link)

    issues = collect_workspace_invariant_issues(item, package)

    assert any(
        issue.evidence.get("evidence_level") == "path_policy_block"
        for issue in issues
    )
