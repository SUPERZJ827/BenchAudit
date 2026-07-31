#!/usr/bin/env python3
"""Standalone Phase-2A Git verifier for external-evidence receipts.

This module is deliberately not imported by ``benchcore`` and is not wired to
any checker or CLI.  It verifies one code-allowlisted APPS manifest in a fresh
bare object database and emits raw and stable replay artifacts.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchcore.external_evidence import (  # noqa: E402
    EXTERNAL_EVIDENCE_POLICY_VERSION,
    EXTERNAL_EVIDENCE_TRUST_DOMAIN,
    ExternalEvidenceReceipt,
    ExternalEvidenceVerification,
    derive_allowed_uses,
    receipt_payload_sha256,
)


TRUSTED_MANIFEST_PATH = (
    REPO_ROOT / "configs" / "external_evidence_trusted_sources_v1.json"
)
TRUSTED_MANIFEST_PAYLOAD_SHA256 = "28a8501dce3194c767362db2bcdb1aeac3e977aa064c2cbba9521ddf481c9acc"
VERIFIER_POLICY_ID = "external-evidence-git-verifier-v2"
HOST_HANDLER_HF_DATASET = "huggingface-dataset-git-v1"
HOST_HANDLER_GITHUB = "github-git-v1"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class VerificationFailure(RuntimeError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class TrustedManifestEntry:
    manifest_id: str
    benchmark_id: str
    host_kind: str
    canonical_remote_url: str
    cutoff_commit: str
    normative_paths: tuple[str, ...]
    policy_version: str
    receipt_version: str


@dataclass(frozen=True)
class CommandObservation:
    argv: tuple[str, ...]
    returncode: int
    duration_ms: int
    stdout_sha256: str
    stderr: str


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def load_trusted_manifest() -> tuple[TrustedManifestEntry, str]:
    raw = json.loads(TRUSTED_MANIFEST_PATH.read_text(encoding="utf-8"))
    if raw.get("manifest_schema") != "benchaudit-external-evidence-trusted-sources-v1":
        raise VerificationFailure("manifest_schema_invalid", "trusted manifest schema is invalid")
    payload = raw.get("payload")
    if not isinstance(payload, Mapping):
        raise VerificationFailure("manifest_payload_invalid", "trusted manifest payload is absent")
    actual = _sha256_bytes(_canonical_bytes(payload))
    if raw.get("payload_sha256") != actual:
        raise VerificationFailure("manifest_self_hash_mismatch", "trusted manifest self-hash differs")
    if actual != TRUSTED_MANIFEST_PAYLOAD_SHA256:
        raise VerificationFailure("manifest_not_code_allowlisted", "trusted manifest is not code-allowlisted")
    values = payload.get("manifests")
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], Mapping):
        raise VerificationFailure("manifest_cardinality_invalid", "Phase 2A requires exactly one manifest")
    value = values[0]
    entry = TrustedManifestEntry(
        manifest_id=str(value.get("manifest_id") or ""),
        benchmark_id=str(value.get("benchmark_id") or ""),
        host_kind=str(value.get("host_kind") or ""),
        canonical_remote_url=str(value.get("canonical_remote_url") or ""),
        cutoff_commit=str(value.get("cutoff_commit") or ""),
        normative_paths=tuple(str(path) for path in value.get("normative_paths") or ()),
        policy_version=str(value.get("policy_version") or ""),
        receipt_version=str(value.get("receipt_version") or ""),
    )
    return entry, actual


def validate_canonical_remote(url: str, host_kind: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise VerificationFailure("remote_url_rejected", "remote URL violates the transport policy")
    parts = tuple(part for part in parsed.path.split("/") if part)
    if host_kind == "huggingface_dataset":
        if parsed.hostname != "huggingface.co" or len(parts) != 3 or parts[0] != "datasets":
            raise VerificationFailure("hf_dataset_url_rejected", "Hugging Face dataset URL is not canonical")
        if any(part in {".", ".."} for part in parts):
            raise VerificationFailure("hf_dataset_url_rejected", "Hugging Face path is unsafe")
        return HOST_HANDLER_HF_DATASET
    if host_kind == "github":
        if parsed.hostname != "github.com" or len(parts) != 2 or not parts[1].endswith(".git"):
            raise VerificationFailure("github_url_rejected", "GitHub URL is not canonical")
        return HOST_HANDLER_GITHUB
    raise VerificationFailure("unknown_host_kind", "unknown host kind has no Git fallback")


def validate_receipt_against_manifest(
    receipt: ExternalEvidenceReceipt,
    manifest: TrustedManifestEntry,
) -> str:
    handler = validate_canonical_remote(manifest.canonical_remote_url, manifest.host_kind)
    if receipt.source_remote_url.rstrip("/") != manifest.canonical_remote_url.rstrip("/"):
        raise VerificationFailure("source_remote_mismatch", "receipt source remote differs from manifest")
    if receipt.cutoff_remote_url.rstrip("/") != manifest.canonical_remote_url.rstrip("/"):
        raise VerificationFailure("cutoff_remote_mismatch", "receipt cutoff remote differs from manifest")
    if receipt.cutoff_commit != manifest.cutoff_commit:
        raise VerificationFailure("cutoff_commit_mismatch", "receipt cutoff differs from manifest")
    if receipt.source_role != "normative" or receipt.source_path not in manifest.normative_paths:
        raise VerificationFailure("role_path_not_allowlisted", "receipt role/path is not normative in manifest")
    if receipt.policy_version != manifest.policy_version or receipt.receipt_version != manifest.receipt_version:
        raise VerificationFailure("version_mismatch", "receipt versions differ from manifest")
    if not HEX40.fullmatch(receipt.source_commit) or not HEX40.fullmatch(receipt.cutoff_commit):
        raise VerificationFailure("commit_id_invalid", "Phase 2A accepts SHA-1 Git commit IDs only")
    return handler


def _git_env(home: Path) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "xdg"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
        "GIT_SSH_COMMAND": "/bin/false",
        "GIT_ALLOW_PROTOCOL": "https",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    for name in ("HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"):
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def _run(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path | None,
    observations: list[CommandObservation],
    check: bool = True,
) -> bytes:
    started = time.monotonic()
    proc = subprocess.run(
        list(argv),
        cwd=str(cwd) if cwd is not None else None,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    observations.append(CommandObservation(
        argv=tuple(argv),
        returncode=proc.returncode,
        duration_ms=round((time.monotonic() - started) * 1000),
        stdout_sha256=_sha256_bytes(proc.stdout),
        stderr=proc.stderr.decode("utf-8", errors="replace"),
    ))
    if check and proc.returncode != 0:
        raise VerificationFailure("git_command_failed", f"command failed: {argv[0]} {argv[1] if len(argv) > 1 else ''}")
    return proc.stdout


def _git(
    git_dir: Path,
    args: Sequence[str],
    *,
    env: Mapping[str, str],
    observations: list[CommandObservation],
    check: bool = True,
) -> bytes:
    return _run(
        ["git", f"--git-dir={git_dir}", *args],
        env=env,
        cwd=None,
        observations=observations,
        check=check,
    )


def _assert_absent_object_overrides(git_dir: Path, env: Mapping[str, str], observations: list[CommandObservation]) -> None:
    if (git_dir / "objects" / "info" / "alternates").exists():
        raise VerificationFailure("alternates_present", "alternate object store is present")
    if (git_dir / "info" / "grafts").exists():
        raise VerificationFailure("grafts_present", "grafts are present")
    replacements = _git(git_dir, ["for-each-ref", "--format=%(refname)", "refs/replace"], env=env, observations=observations)
    if replacements.strip():
        raise VerificationFailure("replacement_refs_present", "replacement refs are present")
    shallow = _git(git_dir, ["rev-parse", "--is-shallow-repository"], env=env, observations=observations)
    if shallow.strip() != b"false":
        raise VerificationFailure("shallow_repository", "object database is shallow")


def _is_ancestor(git_dir: Path, left: str, right: str, *, env: Mapping[str, str], observations: list[CommandObservation]) -> bool:
    _git(git_dir, ["merge-base", "--is-ancestor", left, right], env=env, observations=observations, check=False)
    result = observations[-1].returncode
    if result not in {0, 1}:
        raise VerificationFailure("ancestry_check_failed", "Git ancestry check failed")
    return result == 0


def _blob(
    git_dir: Path,
    commit: str,
    path: str,
    *,
    env: Mapping[str, str],
    observations: list[CommandObservation],
) -> tuple[str, bytes]:
    spec = f"{commit}:{path}"
    oid = _git(git_dir, ["rev-parse", "--verify", spec], env=env, observations=observations).decode().strip()
    if not HEX40.fullmatch(oid):
        raise VerificationFailure("blob_oid_invalid", "tree entry is not a SHA-1 object ID")
    object_type = _git(git_dir, ["cat-file", "-t", oid], env=env, observations=observations).strip()
    if object_type != b"blob":
        raise VerificationFailure("tree_entry_not_blob", "tree entry is not an ordinary Git blob")
    content = _git(git_dir, ["cat-file", "blob", oid], env=env, observations=observations)
    if content.startswith(LFS_POINTER_PREFIX):
        raise VerificationFailure("lfs_pointer_unverifiable", "Git LFS pointer is outside Phase 2A")
    return oid, content


def verifier_source_sha256() -> str:
    return _sha256_bytes(Path(__file__).read_bytes())


def verify_receipt(receipt_value: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], ExternalEvidenceVerification]:
    receipt = ExternalEvidenceReceipt.from_mapping(receipt_value)
    manifest, manifest_hash = load_trusted_manifest()
    handler = validate_receipt_against_manifest(receipt, manifest)
    observations: list[CommandObservation] = []
    created_at = time.time()
    temp_root = Path(tempfile.mkdtemp(prefix="benchaudit-git-verifier-"))
    git_dir = temp_root / "objects.git"
    home = temp_root / "home"
    home.mkdir(mode=0o700)
    env = _git_env(home)
    stable: dict[str, Any] = {}
    try:
        _run(["git", "init", "--bare", str(git_dir)], env=env, cwd=None, observations=observations)
        _git(git_dir, ["config", "remote.origin.url", manifest.canonical_remote_url], env=env, observations=observations)
        _git(git_dir, ["config", "http.followRedirects", "false"], env=env, observations=observations)
        _git(git_dir, ["config", "credential.helper", ""], env=env, observations=observations)
        _git(git_dir, ["config", "protocol.file.allow", "never"], env=env, observations=observations)
        _assert_absent_object_overrides(git_dir, env, observations)
        commits = sorted({receipt.source_commit, receipt.cutoff_commit})
        for commit in commits:
            _git(
                git_dir,
                [
                    "-c", "http.followRedirects=false",
                    "-c", "credential.helper=",
                    "-c", "protocol.file.allow=never",
                    "fetch", "--no-tags", "--no-write-fetch-head",
                    "--no-recurse-submodules", "origin", commit,
                ],
                env=env,
                observations=observations,
            )
        _assert_absent_object_overrides(git_dir, env, observations)
        _git(git_dir, ["fsck", "--full", "--strict", "--no-dangling"], env=env, observations=observations)
        for commit in commits:
            object_type = _git(git_dir, ["cat-file", "-t", commit], env=env, observations=observations).strip()
            if object_type != b"commit":
                raise VerificationFailure("commit_object_missing", "fetched object is not a commit")
        forward = _is_ancestor(git_dir, receipt.source_commit, receipt.cutoff_commit, env=env, observations=observations)
        reverse = _is_ancestor(git_dir, receipt.cutoff_commit, receipt.source_commit, env=env, observations=observations)
        source_blob, source_content = _blob(git_dir, receipt.source_commit, receipt.source_path, env=env, observations=observations)
        cutoff_blob, cutoff_content = _blob(git_dir, receipt.cutoff_commit, receipt.source_path, env=env, observations=observations)
        source_hash = _sha256_bytes(source_content)
        cutoff_hash = _sha256_bytes(cutoff_content)
        source_tree = _git(git_dir, ["rev-parse", f"{receipt.source_commit}^{{tree}}"], env=env, observations=observations).decode().strip()
        cutoff_tree = _git(git_dir, ["rev-parse", f"{receipt.cutoff_commit}^{{tree}}"], env=env, observations=observations).decode().strip()
        verified = ExternalEvidenceVerification(
            verified=True,
            reason="verified_by_fresh_remote_git_replay",
            trust_domain=EXTERNAL_EVIDENCE_TRUST_DOMAIN,
            receipt_payload_sha256=receipt_payload_sha256(receipt),
            verified_remote_url=manifest.canonical_remote_url,
            official_remote_verified=True,
            role_binding_verified=True,
            verified_source_role="normative",
            source_commit=receipt.source_commit,
            cutoff_commit=receipt.cutoff_commit,
            source_path=receipt.source_path,
            source_tree_content_sha256=source_hash,
            cutoff_tree_content_sha256=cutoff_hash,
            source_is_ancestor_of_cutoff=forward,
            cutoff_is_ancestor_of_source=reverse,
        )
        allowed = sorted(derive_allowed_uses(receipt, verified))
        if allowed != ["confirmation", "detection", "routing", "validation"]:
            raise VerificationFailure("policy_rejected_verification", "policy did not grant the expected normative uses")
        stable = {
            "receipt_payload_sha256": receipt_payload_sha256(receipt),
            "trusted_manifest_id": manifest.manifest_id,
            "trusted_manifest_payload_sha256": manifest_hash,
            "host_kind": manifest.host_kind,
            "canonical_remote": manifest.canonical_remote_url,
            "source_commit": receipt.source_commit,
            "cutoff_commit": receipt.cutoff_commit,
            "source_path": receipt.source_path,
            "fetched_source_object_id": receipt.source_commit,
            "fetched_cutoff_object_id": receipt.cutoff_commit,
            "source_tree_object_id": source_tree,
            "cutoff_tree_object_id": cutoff_tree,
            "source_is_ancestor_of_cutoff": forward,
            "cutoff_is_ancestor_of_source": reverse,
            "source_blob_id": source_blob,
            "cutoff_blob_id": cutoff_blob,
            "source_content_sha256": source_hash,
            "cutoff_content_sha256": cutoff_hash,
            "role_binding_verified": True,
            "verified_source_role": "normative",
            "host_handler_id": handler,
            "verifier_policy_id": VERIFIER_POLICY_ID,
            "verifier_source_sha256": verifier_source_sha256(),
            "verified": True,
            "derived_relation": "pre_cutoff" if forward else "post_cutoff" if reverse else "unverifiable",
            "reason_code": "verified_normative_git_blob",
            "security_controls": {
                "redirects_disabled": True,
                "alternates_absent": True,
                "grafts_absent": True,
                "replacement_refs_absent": True,
                "shallow_state_absent": True,
                "credentials_disabled": True,
                "checkout_absent": True,
            },
        }
        raw = {
            "raw_transcript_schema": "benchaudit-external-evidence-git-verifier-raw-v1",
            "created_at_epoch": created_at,
            "temporary_root": str(temp_root),
            "process_id": os.getpid(),
            "git_version": _run(["git", "--version"], env=env, cwd=None, observations=observations).decode().strip(),
            "commands": [asdict(observation) for observation in observations],
            "stable_summary": stable,
            "stable_summary_sha256": _sha256_bytes(_canonical_bytes(stable)),
        }
        return raw, stable, verified
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--raw-out", type=Path, required=True)
    parser.add_argument("--stable-out", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.receipt.read_text(encoding="utf-8"))
    if "external_evidence_receipt" in value:
        value = value["external_evidence_receipt"]
    try:
        raw, stable, _ = verify_receipt(value)
    except VerificationFailure as exc:
        failure = {
            "verified": False,
            "reason_code": exc.reason_code,
            "message": str(exc),
        }
        _write_json(args.raw_out, failure)
        _write_json(args.stable_out, failure)
        return 2
    _write_json(args.raw_out, raw)
    _write_json(args.stable_out, stable)
    print(json.dumps({
        "verified": True,
        "stable_summary_sha256": _sha256_bytes(_canonical_bytes(stable)),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
