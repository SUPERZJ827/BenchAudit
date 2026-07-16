"""Validated replay evidence for Workspace-Bench actor visibility.

The static detector can prove that a task package contains suspicious generator
code, but package presence alone does not prove that the benchmark runner shows
it to the agent.  This module consumes the bounded, pinned replay transcript
produced by ``scripts/audit_workspace_runner_visibility.py`` and validates every
hash/semantic gate before the static candidate may be promoted.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .zip_range import HTTPRangeReader, read_zip_entry, read_zip_index


SCHEMA_VERSION = "workspace-runner-visibility-v1"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text.casefold())


def _is_commit(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 40 and all(char in "0123456789abcdef" for char in text.casefold())


@dataclass(frozen=True)
class RunnerVisibilityProof:
    item_id: str
    task_package_sha256: str
    archive_member: str
    archive_revision: str
    archive_central_directory_sha256: str
    runner_commit: str
    transcript_sha256: str
    online_reverified: bool

    def to_evidence(self) -> dict[str, Any]:
        return {
            "evidence_level": (
                "workspace_runner_visibility_replay"
                if self.online_reverified
                else "workspace_runner_visibility_transcript"
            ),
            "proof_schema_version": "1.0",
            "online_reverified": self.online_reverified,
            "visibility": {
                "task_package_present": True,
                "agent_visible": True,
                "evaluator_visible": True,
                "visibility_verified": True,
            },
            "task_package_sha256": self.task_package_sha256,
            "archive_member": self.archive_member,
            "archive_revision": self.archive_revision,
            "archive_central_directory_sha256": self.archive_central_directory_sha256,
            "runner_commit": self.runner_commit,
            "visibility_transcript_sha256": self.transcript_sha256,
        }


class WorkspaceRunnerVisibilityIndex:
    """Immutable lookup of fail-closed, byte-bound actor-visibility proofs."""

    def __init__(
        self,
        proofs: dict[tuple[str, str], RunnerVisibilityProof],
        *,
        transcript_sha256: str,
        dataset_sha256: str,
    ) -> None:
        self._proofs = dict(proofs)
        self.transcript_sha256 = transcript_sha256
        self.dataset_sha256 = dataset_sha256

    @classmethod
    def load(
        cls,
        report_path: Path,
        *,
        dataset_path: Path,
        online_reverify: bool = False,
        remote_timeout: float = 120.0,
    ) -> "WorkspaceRunnerVisibilityIndex":
        payload = report_path.read_bytes()
        transcript_sha = _sha256_bytes(payload)
        try:
            report = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid Workspace visibility JSON: {report_path}") from exc
        if not isinstance(report, dict):
            raise ValueError("Workspace visibility transcript must be a JSON object")
        if report.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                "unsupported Workspace visibility transcript schema: "
                f"{report.get('schema_version')!r}"
            )

        dataset = report.get("dataset")
        if not isinstance(dataset, dict) or not _is_sha256(dataset.get("sha256")):
            raise ValueError("visibility transcript has no valid dataset SHA-256")
        actual_dataset_sha = _sha256_bytes(dataset_path.read_bytes())
        declared_dataset_sha = str(dataset["sha256"]).casefold()
        if actual_dataset_sha != declared_dataset_sha:
            raise ValueError(
                "visibility transcript belongs to a different dataset: "
                f"expected {actual_dataset_sha}, got {declared_dataset_sha}"
            )

        archive = report.get("archive")
        runner = report.get("runner")
        if not isinstance(archive, dict) or not isinstance(runner, dict):
            raise ValueError("visibility transcript lacks archive/runner provenance")
        if not archive.get("range_only"):
            raise ValueError("visibility transcript is not marked as a bounded range replay")
        if not _is_commit(archive.get("revision")):
            raise ValueError("visibility transcript has an invalid archive revision")
        if not _is_sha256(archive.get("central_directory_sha256")):
            raise ValueError("visibility transcript has no central-directory hash")
        if int(archive.get("entries") or 0) <= 0:
            raise ValueError("visibility transcript has an empty archive index")
        if not _is_commit(runner.get("commit")):
            raise ValueError("visibility transcript has an invalid runner commit")
        semantics = runner.get("verified_semantics")
        required_semantics = {
            "raw_workspace_copied_to_standard",
            "standard_workspace_copied_to_agent_case",
            "task_data_exposed_in_judge_view",
        }
        if not isinstance(semantics, dict) or not all(
            semantics.get(name) is True for name in required_semantics
        ):
            raise ValueError("runner actor-view semantics were not all verified")
        runner_files = runner.get("files")
        if not isinstance(runner_files, list) or not runner_files:
            raise ValueError("visibility transcript has no hashed runner source files")
        if any(
            not isinstance(row, dict) or not _is_sha256(row.get("sha256"))
            for row in runner_files
        ):
            raise ValueError("visibility transcript contains an unhashed runner file")

        findings = report.get("findings")
        if not isinstance(findings, list):
            raise ValueError("visibility transcript findings must be a list")
        online_keys = (
            _online_reverify_report(
                report,
                dataset_path=dataset_path,
                timeout=remote_timeout,
            )
            if online_reverify
            else set()
        )
        proofs: dict[tuple[str, str], RunnerVisibilityProof] = {}
        for row in findings:
            if not isinstance(row, dict) or row.get("status") != "confirmed":
                continue
            visibility = row.get("visibility")
            if not isinstance(visibility, dict) or not all(
                visibility.get(name) is True
                for name in (
                    "task_package_present",
                    "agent_visible",
                    "evaluator_visible",
                    "visibility_verified",
                )
            ):
                continue
            item_id = str(row.get("item_id") or "")
            digest = str(row.get("task_package_sha256") or "").casefold()
            if not item_id or not _is_sha256(digest):
                raise ValueError("confirmed visibility finding lacks an item/hash key")
            exact = row.get("exact_agent_workspace_matches")
            if not isinstance(exact, list):
                raise ValueError("confirmed visibility finding lacks exact archive matches")
            exact_rows = [
                match for match in exact
                if isinstance(match, dict)
                and match.get("byte_identical_to_task_package") is True
                and str(match.get("sha256") or "").casefold() == digest
                and str(match.get("archive_member") or "")
            ]
            if not exact_rows:
                raise ValueError(
                    f"confirmed visibility finding {item_id} has no byte-identical member"
                )
            key = (item_id, digest)
            if key in proofs:
                raise ValueError(f"duplicate Workspace visibility proof: {key}")
            proofs[key] = RunnerVisibilityProof(
                item_id=item_id,
                task_package_sha256=digest,
                archive_member=str(exact_rows[0]["archive_member"]),
                archive_revision=str(archive["revision"]),
                archive_central_directory_sha256=str(
                    archive["central_directory_sha256"]
                ).casefold(),
                runner_commit=str(runner["commit"]),
                transcript_sha256=transcript_sha,
                online_reverified=key in online_keys,
            )
        return cls(
            proofs,
            transcript_sha256=transcript_sha,
            dataset_sha256=declared_dataset_sha,
        )

    def find(self, item_id: str, task_package_sha256: str) -> RunnerVisibilityProof | None:
        return self._proofs.get((str(item_id), str(task_package_sha256).casefold()))

    def __len__(self) -> int:
        return len(self._proofs)


def _fetch(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def _dataset_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        value = json.loads(text)
        rows = value if isinstance(value, list) else []
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("visibility dataset must contain only JSON object rows")
    return rows


def _online_reverify_report(
    report: dict[str, Any],
    *,
    dataset_path: Path,
    timeout: float,
) -> set[tuple[str, str]]:
    """Rebuild every trust-bearing edge from authoritative pinned bytes.

    A transcript hash only detects accidental local edits; it is not a
    signature.  Confirmation therefore requires re-fetching the pinned runner
    sources and the exact ZIP member, plus hashing the task-package file that
    the pinned dataset actually declares for that item.
    """

    if timeout <= 0:
        raise ValueError("remote visibility verification timeout must be positive")
    archive = report["archive"]
    runner = report["runner"]
    if archive.get("repo") != "Workspace-Bench/Workspace-Bench-Workspaces":
        raise ValueError("visibility archive is not the authoritative Workspace-Bench repo")
    revision = str(archive["revision"])
    filename = str(archive.get("filename") or "")
    if not filename or "/" in filename or "\\" in filename:
        raise ValueError("visibility archive filename is invalid")

    contents: dict[str, str] = {}
    expected_runner_base = (
        "https://raw.githubusercontent.com/OpenDataBox/Workspace-Bench/"
        f"{runner['commit']}/"
    )
    for row in runner["files"]:
        path = str(row.get("path") or "")
        expected_url = expected_runner_base + path
        if row.get("url") != expected_url:
            raise ValueError("runner source URL is not bound to its declared commit/path")
        payload = _fetch(expected_url, min(timeout, 60.0))
        if _sha256_bytes(payload) != str(row["sha256"]).casefold():
            raise ValueError(f"pinned runner source hash changed: {path}")
        contents[path] = payload.decode("utf-8")
    semantic_markers = {
        "evaluation/src/filesys_utils.py": "shutil.copytree(raw_path, standard_path)",
        "evaluation/src/agent_runner.py": "_copytree_fast(standard_work_dir, work_dir)",
        "evaluation/src/agent_as_a_judge.py": "_symlink_or_copy(inputs_dir, dst)",
    }
    if any(marker not in contents.get(path, "") for path, marker in semantic_markers.items()):
        raise ValueError("pinned runner source no longer proves the declared actor-view semantics")

    archive_url = (
        "https://huggingface.co/datasets/"
        f"{archive['repo']}/resolve/{revision}/{filename}"
    )
    reader = HTTPRangeReader(archive_url, timeout=timeout)
    if reader.size != int(archive.get("bytes") or 0):
        raise ValueError("remote Workspace archive size differs from transcript")
    index = read_zip_index(reader)
    if (
        index.central_directory_sha256
        != str(archive["central_directory_sha256"]).casefold()
        or len(index.entries) != int(archive.get("entries") or 0)
    ):
        raise ValueError("remote Workspace ZIP index differs from transcript")
    entries = {entry.name: entry for entry in index.entries}

    dataset_by_id = {
        str(row.get("item_id") or ""): row for row in _dataset_rows(dataset_path)
    }
    verified: set[tuple[str, str]] = set()
    for row in report["findings"]:
        if not isinstance(row, dict) or row.get("status") != "confirmed":
            continue
        item_id = str(row.get("item_id") or "")
        digest = str(row.get("task_package_sha256") or "").casefold()
        dataset_row = dataset_by_id.get(item_id)
        declared_inputs = (
            dataset_row.get("input_files") if isinstance(dataset_row, dict) else None
        )
        task_path = Path(str(row.get("task_package_path") or "")).expanduser()
        if (
            not isinstance(declared_inputs, list)
            or str(task_path) not in {str(value) for value in declared_inputs}
            or not task_path.is_file()
            or _sha256_bytes(task_path.read_bytes()) != digest
        ):
            raise ValueError(f"task-package proof is not bound to dataset row {item_id}")
        matches = row.get("exact_agent_workspace_matches")
        if not isinstance(matches, list) or not matches:
            raise ValueError(f"visibility finding {item_id} has no exact archive member")
        match = matches[0]
        member_name = str(match.get("archive_member") or "")
        entry = entries.get(member_name)
        if entry is None:
            raise ValueError(f"remote Workspace archive lacks member {member_name!r}")
        member = read_zip_entry(reader, entry, max_uncompressed_bytes=2_000_000)
        if _sha256_bytes(member) != digest:
            raise ValueError(f"remote archive member no longer matches task package {item_id}")
        verified.add((item_id, digest))
    return verified
