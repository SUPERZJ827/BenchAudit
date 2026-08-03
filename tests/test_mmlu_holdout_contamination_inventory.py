import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

import scripts.inventory_mmlu_holdout_contamination as inventory


def _dataset(path: Path, count: int = 5700, *, duplicate: bool = False) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for index in range(count):
            item = 0 if duplicate and index == count - 1 else index
            # The invalid suffix proves the extractor does not decode the complete row.
            handle.write(f'{{"id":"mmlu-redux-subject-{item}","question":INVALID}}\n')


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def _init_repo(path: Path) -> None:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def test_selective_dataset_extraction_does_not_decode_rows(tmp_path):
    path = tmp_path / "dataset.jsonl"
    _dataset(path)
    ids = inventory.extract_universe_ids(path)
    assert len(ids) == 5700
    assert ids[0] == "mmlu-redux-subject-0"


def test_duplicate_and_malformed_dataset_ids_fail_closed(tmp_path):
    duplicate = tmp_path / "duplicate.jsonl"
    _dataset(duplicate, duplicate=True)
    with pytest.raises(inventory.InventoryError, match="duplicate dataset id"):
        inventory.extract_universe_ids(duplicate)
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"question":"x","id":"mmlu-redux-subject-0"}\n')
    with pytest.raises(inventory.InventoryError, match="does not begin"):
        inventory.extract_universe_ids(malformed)


def test_exact_ids_found_without_context_and_lookalikes_ignored():
    universe = {"mmlu-redux-subject-1", "mmlu-redux-subject-2"}
    data = (
        b"secret-before mmlu-redux-subject-1 secret-after "
        b"mmlu-redux-subject-999 mmlu-redux-subject-2-extra"
    )
    assert inventory.scan_bytes(data, universe) == {"mmlu-redux-subject-1"}


def test_all_refs_and_deleted_historical_blob_are_scanned(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo)
    path = repo / "artifact.txt"
    path.write_text("mmlu-redux-subject-4")
    _git(repo, "add", "artifact.txt")
    _git(repo, "commit", "-qm", "add")
    first = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "historical", first)
    path.unlink()
    _git(repo, "add", "-u")
    _git(repo, "commit", "-qm", "delete")
    monkeypatch.chdir(repo)
    records, sources, refs = inventory.scan_git_history({"mmlu-redux-subject-4"})
    assert records
    assert "mmlu-redux-subject-4" in sources
    assert "refs/heads/historical" in {row["name"] for row in refs}


def test_working_tree_scans_hidden_untracked_and_does_not_follow_symlink(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    hidden = root / ".hidden"
    hidden.write_text("mmlu-redux-subject-5")
    target = tmp_path / "outside"
    target.write_text("mmlu-redux-subject-6")
    (root / "link").symlink_to(target)
    records, sources, caches, unsupported = inventory.scan_working_tree(
        root, tmp_path / "output", {"mmlu-redux-subject-5", "mmlu-redux-subject-6"}
    )
    assert {row["path"] for row in records} == {".hidden"}
    assert set(sources) == {"mmlu-redux-subject-5"}
    assert caches == [] and unsupported == []


def test_zip_members_are_scanned_and_corrupt_zip_fails(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    archive = root / "items.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("inside.txt", "mmlu-redux-subject-7")
    records, sources, _, unsupported = inventory.scan_working_tree(
        root, tmp_path / "output", {"mmlu-redux-subject-7"}
    )
    assert records[0]["disposition"] == "zip_scanned"
    assert sources["mmlu-redux-subject-7"] == ["items.zip!inside.txt"]
    assert unsupported == []
    archive.unlink()
    (root / "bad.zip").write_bytes(b"not a zip")
    with pytest.raises(inventory.InventoryError, match="corrupt ZIP"):
        inventory.scan_working_tree(root, tmp_path / "output", set())


def test_unsupported_compression_prevents_complete_scan(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "archive.gz").write_bytes(b"gzip-ish")
    records, _, _, unsupported = inventory.scan_working_tree(
        root, tmp_path / "output", set()
    )
    assert records[0]["disposition"] == "unsupported"
    assert unsupported == ["archive.gz"]


def test_digest_only_cache_is_opaque_and_response_not_returned(tmp_path):
    cache = tmp_path / "cache.jsonl"
    response = {"private": "must-not-appear"}
    cache.write_text(json.dumps({"key": "a" * 64, "response": response}) + "\n")
    result = inventory.cache_shape(cache)
    assert result == {
        "entries": 1,
        "distinct_keys": 1,
        "key_length_histogram": {"64": 1},
    }
    assert "private" not in json.dumps(result)


def test_full_inventory_is_deterministic_and_reports_zero_api(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo)
    protocol = repo / "protocol.md"
    protocol.write_text("frozen")
    artifact = repo / "artifact.txt"
    artifact.write_text("mmlu-redux-subject-9")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    dataset = tmp_path / "dataset.jsonl"
    _dataset(dataset)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(inventory, "PROTOCOL", Path("protocol.md"))
    monkeypatch.setattr(inventory, "EXPECTED_DATASET_SHA256", inventory.sha256_file(dataset))

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    for output in (out1, out2):
        inventory.run(argparse.Namespace(repo_root=str(repo), dataset=str(dataset), out=str(output)))
    assert (out1 / "inventory.json").read_bytes() == (out2 / "inventory.json").read_bytes()
    assert (out1 / "REPORT.md").read_bytes() == (out2 / "REPORT.md").read_bytes()
    receipt = json.loads((out1 / "receipt.json").read_text())
    result = json.loads((out1 / "inventory.json").read_text())
    assert receipt["api_attempts"] == receipt["network_attempts"] == 0
    assert receipt["dataset_rows_json_decoded"] is False
    assert result["counts"]["universe_ids"] == 5700
    assert result["counts"]["exposed_ids"] == 1
    assert result["counts"]["candidate_ids"] == 5699
    assert not (set(row["item_id"] for row in result["exposures"]) & set(result["candidate_ids"]))
    assert hashlib.sha256((out1 / "inventory.json").read_bytes()).hexdigest() == receipt[
        "outputs"
    ]["inventory_sha256"]
