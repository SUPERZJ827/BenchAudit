from pathlib import Path

from benchcore.package_scan import ArtifactKind, add_canonical_item_artifacts, scan_benchmark_package
from benchcore.schema import BenchmarkItem


def test_package_scanner_classifies_core_artifacts_and_ignores_build_dirs(tmp_path: Path):
    (tmp_path / "tasks.jsonl").write_text('{"id":"1","question":"q"}\n', encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (tmp_path / "gold_patch.diff").write_text("+fixed\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_feature.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    ignored = tmp_path / ".git"
    ignored.mkdir()
    (ignored / "secret").write_text("ignored", encoding="utf-8")

    package = scan_benchmark_package(tmp_path)

    kinds = {artifact.kind for artifact in package.artifacts}
    paths = {artifact.relative_path for artifact in package.artifacts}
    assert ArtifactKind.TASK_SPECIFICATION in kinds
    assert ArtifactKind.ENVIRONMENT in kinds
    assert ArtifactKind.ORACLE in kinds
    assert ArtifactKind.EVALUATOR in kinds
    assert ".git/secret" not in paths
    assert package.scan_metadata["files_scanned"] == 4
    assert any(edge.relation == "evaluates" for edge in package.edges)


def test_package_scanner_is_deterministic(tmp_path: Path):
    path = tmp_path / "questions.csv"
    path.write_text("id,question\n1,hello\n", encoding="utf-8")

    first = scan_benchmark_package(tmp_path).to_dict()
    second = scan_benchmark_package(tmp_path).to_dict()

    assert first == second


def test_identical_files_keep_distinct_artifact_identity(tmp_path: Path):
    (tmp_path / "task_a.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "task_b.jsonl").write_text("{}\n", encoding="utf-8")

    package = scan_benchmark_package(tmp_path)

    assert len({artifact.artifact_id for artifact in package.artifacts}) == 2
    assert len({artifact.sha256 for artifact in package.artifacts}) == 1


def test_scanner_does_not_follow_symlinks_outside_package(tmp_path: Path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "external.txt").symlink_to(outside)
    nested = tmp_path / "linked-dir"
    nested.symlink_to(tmp_path.parent, target_is_directory=True)

    package = scan_benchmark_package(tmp_path)

    assert package.artifacts == []


def test_oversized_artifact_remains_in_inventory_without_hashing(tmp_path: Path):
    path = tmp_path / "tasks.jsonl"
    path.write_text("0123456789", encoding="utf-8")

    package = scan_benchmark_package(tmp_path, max_file_bytes=5)

    assert len(package.artifacts) == 1
    assert package.artifacts[0].sha256 == ""
    assert "unhashed_oversized" in package.artifacts[0].roles
    assert package.scan_metadata["files_skipped_large"] == 1


def test_canonical_fields_add_virtual_artifacts_without_duplicates(tmp_path: Path):
    source = tmp_path / "data.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    package = scan_benchmark_package(source)
    items = [BenchmarkItem(
        item_id="1",
        raw={},
        task="Question",
        context={"table": "x"},
        gold="A",
        evaluator={"type": "exact"},
    )]

    add_canonical_item_artifacts(package, items)
    add_canonical_item_artifacts(package, items)

    virtual_kinds = [
        artifact.kind for artifact in package.artifacts
        if artifact.relative_path.startswith("@canonical/")
    ]
    assert len(virtual_kinds) == len(set(virtual_kinds))
    assert ArtifactKind.ORACLE in package.kinds()
    assert ArtifactKind.EVALUATOR in package.kinds()
