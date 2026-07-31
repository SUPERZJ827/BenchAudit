from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from benchcore.external_evidence import ExternalEvidenceReceipt
from scripts import external_evidence_git_verifier as verifier
from scripts import run_external_evidence_git_verifier_v2 as runner


REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_FIXTURE = (
    REPO_ROOT / "docs" / "experiments"
    / "apps_external_evidence_positive_fixture_20260731.json"
)


def _receipt_value() -> dict[str, object]:
    return json.loads(APPS_FIXTURE.read_text(encoding="utf-8"))[
        "external_evidence_receipt"
    ]


def _failure_code(callable_) -> str:
    with pytest.raises(verifier.VerificationFailure) as exc:
        callable_()
    return exc.value.reason_code


def test_code_allowlisted_manifest_loads_and_binds_one_normative_path() -> None:
    manifest, digest = verifier.load_trusted_manifest()

    assert digest == verifier.TRUSTED_MANIFEST_PAYLOAD_SHA256
    assert manifest.manifest_id == "apps-normative-cutoff-v1"
    assert manifest.normative_paths == ("README.md",)


def test_modified_manifest_payload_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = json.loads(verifier.TRUSTED_MANIFEST_PATH.read_text(encoding="utf-8"))
    value["payload"]["manifests"][0]["normative_paths"].append("apps.py")
    modified = tmp_path / "manifest.json"
    modified.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(verifier, "TRUSTED_MANIFEST_PATH", modified)

    assert _failure_code(verifier.load_trusted_manifest) == "manifest_self_hash_mismatch"


def test_caller_cannot_replace_manifest_with_self_consistent_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = json.loads(verifier.TRUSTED_MANIFEST_PATH.read_text(encoding="utf-8"))
    value["payload"]["manifests"][0]["normative_paths"].append("apps.py")
    value["payload_sha256"] = hashlib.sha256(
        verifier._canonical_bytes(value["payload"])
    ).hexdigest()
    modified = tmp_path / "manifest.json"
    modified.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(verifier, "TRUSTED_MANIFEST_PATH", modified)

    assert _failure_code(verifier.load_trusted_manifest) == "manifest_not_code_allowlisted"


@pytest.mark.parametrize(
    "url",
    [
        "http://huggingface.co/datasets/codeparrot/apps",
        "https://user@huggingface.co/datasets/codeparrot/apps",
        "https://huggingface.co:8443/datasets/codeparrot/apps",
        "https://huggingface.co/datasets/codeparrot/apps?q=1",
        "https://huggingface.co/datasets/codeparrot/apps#fragment",
        "ssh://git@huggingface.co/datasets/codeparrot/apps",
    ],
)
def test_huggingface_url_attacks_are_rejected_before_fetch(url: str) -> None:
    assert _failure_code(
        lambda: verifier.validate_canonical_remote(url, "huggingface_dataset")
    ) in {"remote_url_rejected", "hf_dataset_url_rejected"}


def test_unknown_host_kind_has_no_generic_git_fallback() -> None:
    assert _failure_code(
        lambda: verifier.validate_canonical_remote(
            "https://example.com/owner/repo", "generic_git"
        )
    ) == "unknown_host_kind"


def test_github_and_huggingface_use_distinct_handlers() -> None:
    assert verifier.validate_canonical_remote(
        "https://github.com/owner/repo.git", "github"
    ) == verifier.HOST_HANDLER_GITHUB
    assert verifier.validate_canonical_remote(
        "https://huggingface.co/datasets/owner/repo", "huggingface_dataset"
    ) == verifier.HOST_HANDLER_HF_DATASET


def test_receipt_matches_frozen_manifest_before_network() -> None:
    manifest, _ = verifier.load_trusted_manifest()
    receipt = ExternalEvidenceReceipt.from_mapping(_receipt_value())

    assert verifier.validate_receipt_against_manifest(receipt, manifest) == (
        verifier.HOST_HANDLER_HF_DATASET
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("source_remote_url", "https://huggingface.co/datasets/attacker/apps", "source_remote_mismatch"),
        ("cutoff_commit", "0" * 40, "cutoff_commit_mismatch"),
        ("source_role", "contemporaneous_metadata", "role_path_not_allowlisted"),
        ("source_path", "apps.py", "role_path_not_allowlisted"),
    ],
)
def test_remote_cutoff_role_and_path_mismatches_fail_before_fetch(
    field: str, value: str, reason: str,
) -> None:
    manifest, _ = verifier.load_trusted_manifest()
    receipt_value = _receipt_value()
    receipt_value[field] = value
    receipt = ExternalEvidenceReceipt.from_mapping(receipt_value)

    assert _failure_code(
        lambda: verifier.validate_receipt_against_manifest(receipt, manifest)
    ) == reason


def _make_bare_fixture(tmp_path: Path, content: bytes) -> tuple[Path, str]:
    work = tmp_path / "work"
    bare = tmp_path / "objects.git"
    work.mkdir()
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.email", "test@example.invalid"], check=True)
    (work / "README.md").write_bytes(content)
    subprocess.run(["git", "-C", str(work), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "fixture"], check=True)
    commit = subprocess.check_output(["git", "-C", str(work), "rev-parse", "HEAD"]).decode().strip()
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
    return bare, commit


def test_blob_reader_hashes_content_bytes_without_git_object_header(tmp_path: Path) -> None:
    content = b"line one\nline two\n"
    bare, commit = _make_bare_fixture(tmp_path, content)
    observations: list[verifier.CommandObservation] = []
    home = tmp_path / "home"
    home.mkdir()

    _, observed = verifier._blob(
        bare,
        commit,
        "README.md",
        env=verifier._git_env(home),
        observations=observations,
    )

    assert observed == content
    assert hashlib.sha256(observed).hexdigest() == hashlib.sha256(content).hexdigest()
    assert not (tmp_path / "checkout").exists()


def test_lfs_pointer_blob_is_unverifiable(tmp_path: Path) -> None:
    content = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"0" * 64 + b"\nsize 1\n"
    )
    bare, commit = _make_bare_fixture(tmp_path, content)
    observations: list[verifier.CommandObservation] = []
    home = tmp_path / "home"
    home.mkdir()

    assert _failure_code(
        lambda: verifier._blob(
            bare,
            commit,
            "README.md",
            env=verifier._git_env(home),
            observations=observations,
        )
    ) == "lfs_pointer_unverifiable"


def test_alternate_object_store_is_rejected(tmp_path: Path) -> None:
    bare, _ = _make_bare_fixture(tmp_path, b"README\n")
    alternates = bare / "objects" / "info" / "alternates"
    alternates.write_text("/attacker/objects\n", encoding="utf-8")
    observations: list[verifier.CommandObservation] = []
    home = tmp_path / "home"
    home.mkdir()

    assert _failure_code(
        lambda: verifier._assert_absent_object_overrides(
            bare, verifier._git_env(home), observations
        )
    ) == "alternates_present"


def test_verifier_is_standalone_and_phase_2a_remains_unactivated() -> None:
    benchcore = REPO_ROOT / "benchcore"
    script_path = REPO_ROOT / "scripts" / "external_evidence_git_verifier.py"
    assert script_path.exists()
    for path in benchcore.rglob("*.py"):
        if path.name == "external_evidence.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "ExternalEvidenceVerification(" not in text
        if path.name not in {"promotion.py"}:
            assert '"external_evidence_receipts"' not in text


def test_execution_boundary_is_digest_pinned_and_requires_two_replays(
    tmp_path: Path,
) -> None:
    assert "@sha256:" in runner.PINNED_IMAGE
    assert runner.ALLOWED_AUTHORITY == "huggingface.co:443"
    with pytest.raises(runner.BoundaryFailure, match="exactly two"):
        runner.run_replays(APPS_FIXTURE, tmp_path / "out", 1)


def test_container_security_profile_is_read_only_non_root_and_capability_free() -> None:
    arguments = runner._container_security_args()

    assert "--read-only" in arguments
    assert arguments[arguments.index("--user") + 1] == "65534:65534"
    assert arguments[arguments.index("--cap-drop") + 1] == "ALL"
    assert arguments[arguments.index("--security-opt") + 1] == (
        "no-new-privileges:true"
    )
    assert "--tmpfs" in arguments


def test_runner_mounts_an_execution_bundle_not_the_worktree() -> None:
    source = (
        REPO_ROOT / "scripts" / "run_external_evidence_git_verifier_v2.py"
    ).read_text(encoding="utf-8")

    assert 'src={bundle},dst=/workspace,readonly' in source
    assert 'src={REPO_ROOT},dst=/workspace' not in source
