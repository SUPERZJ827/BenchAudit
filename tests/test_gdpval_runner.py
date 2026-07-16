from __future__ import annotations

import hashlib
import stat
from pathlib import Path

import pytest

from scripts.run_gdpval_objective_audit import _code_provenance, _snapshot_input


def test_source_snapshot_is_content_addressed_regular_and_read_only(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.parquet"
    source.write_bytes(b"synthetic parquet bytes")
    output = tmp_path / "report"
    output.mkdir()

    snapshot, digest, size = _snapshot_input(source, output)

    assert digest == hashlib.sha256(source.read_bytes()).hexdigest()
    assert size == source.stat().st_size
    assert snapshot.name == f"source-{digest}.parquet"
    assert snapshot.read_bytes() == source.read_bytes()
    assert stat.S_ISREG(snapshot.lstat().st_mode)
    assert stat.S_IMODE(snapshot.stat().st_mode) == 0o400


def test_source_snapshot_rejects_preexisting_symlink_even_with_same_bytes(
    tmp_path: Path,
) -> None:
    payload = b"same digest is not enough when the pathname is a symlink"
    source = tmp_path / "input.parquet"
    source.write_bytes(payload)
    output = tmp_path / "report"
    output.mkdir()
    digest = hashlib.sha256(payload).hexdigest()
    attacker_target = tmp_path / "attacker-controlled.parquet"
    attacker_target.write_bytes(payload)
    (output / f"source-{digest}.parquet").symlink_to(attacker_target)

    with pytest.raises(OSError):
        _snapshot_input(source, output)


def test_code_provenance_binds_runner_and_core_proof_files() -> None:
    provenance = _code_provenance()

    assert provenance["schema_version"] == "gdpval-objective-code-manifest-v1"
    assert len(provenance["sha256"]) == 64
    assert "scripts/run_gdpval_objective_audit.py" in provenance["files"]
    assert "benchcore/promotion.py" in provenance["files"]
    assert all(
        len(value["sha256"]) == 64 and value["size_bytes"] > 0
        for value in provenance["files"].values()
    )
