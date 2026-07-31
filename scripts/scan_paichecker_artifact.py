#!/usr/bin/env python3
"""Aggregate-only Stage 0 scanner for the public PAIChecker artifact."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


DATA_SUFFIXES = {".csv", ".json", ".jsonl", ".parquet"}
LABEL_FIELDS = {
    "label",
    "labels",
    "binary_label",
    "fine_grained_label",
    "classifications",
    "misalignment_label",
}
EVIDENCE_FIELD_GROUPS = {
    "instance_id": {"instance_id"},
    "issue_body": {"problem_statement", "issue_body", "issue_description"},
    "issue_discussion": {"hints_text", "issue_comments", "issue_discussion"},
    "pr_description": {"pr_description", "pull_request_description"},
    "production_patch": {"patch", "production_patch"},
    "test_patch": {"test_patch"},
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def _schema_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = sorted({key for row in rows for key in row})
    label_fields = sorted(set(fields) & LABEL_FIELDS)
    evidence_presence = {
        group: bool(set(fields) & aliases)
        for group, aliases in EVIDENCE_FIELD_GROUPS.items()
    }
    return {
        "record_count": len(rows),
        "field_names": fields,
        "label_fields": label_fields,
        "evidence_field_presence": evidence_presence,
        "qualifies_as_labeled_research_data": (
            len(rows) >= 2
            and evidence_presence["instance_id"]
            and bool(label_fields)
        ),
    }


def inspect_candidate_file(path: Path) -> dict[str, Any]:
    """Return aggregate schema metadata without serializing record values."""
    result: dict[str, Any] = {
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "format": path.suffix.lower().lstrip("."),
        "parse_status": "unsupported",
    }
    rows: list[dict[str, Any]] = []
    try:
        if path.suffix.lower() == ".jsonl":
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError("JSONL record is not an object")
                    rows.append(value)
        elif path.suffix.lower() == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
            values = value if isinstance(value, list) else [value]
            if not all(isinstance(row, dict) for row in values):
                raise ValueError("JSON top level is not an object or object list")
            rows = list(values)
        elif path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                rows = [dict(row) for row in csv.DictReader(handle)]
        elif path.suffix.lower() == ".parquet":
            result["parse_status"] = "not_parsed_no_optional_dependency"
            return result
        result.update(_schema_summary(rows))
        result["parse_status"] = "parsed"
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        result["parse_status"] = "parse_error"
        result["error_type"] = type(exc).__name__
    return result


def stage0_decision(candidate_files: list[dict[str, Any]]) -> tuple[str, str]:
    labeled = [
        item
        for item in candidate_files
        if item.get("qualifies_as_labeled_research_data") is True
    ]
    if not labeled:
        return (
            "NOT_IDENTIFIABLE_DATA",
            "official_repository_contains_no_labeled_research_dataset",
        )
    required_for_any_group = [
        item
        for item in labeled
        if (
            item["evidence_field_presence"]["pr_description"]
            or (
                item["evidence_field_presence"]["issue_body"]
                and item["evidence_field_presence"]["test_patch"]
            )
        )
    ]
    if not required_for_any_group:
        return (
            "NOT_IDENTIFIABLE_DATA",
            "labels_cannot_be_linked_to_required_source_evidence",
        )
    return "PASS_STAGE_0", "labeled_source_evidence_available"


def scan_repo(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    tracked = [
        Path(item)
        for item in _git(repo, "ls-files", "-z").split("\0")
        if item
    ]
    files = []
    candidates = []
    for relative in sorted(tracked, key=lambda item: item.as_posix()):
        absolute = repo / relative
        metadata = {
            "path": relative.as_posix(),
            "size_bytes": absolute.stat().st_size,
            "sha256": _sha256(absolute),
        }
        files.append(metadata)
        if relative.suffix.lower() in DATA_SUFFIXES:
            candidate = {"path": relative.as_posix()}
            candidate.update(inspect_candidate_file(absolute))
            candidates.append(candidate)
    decision, reason = stage0_decision(candidates)
    return {
        "protocol": "paichecker_public_data_stage0_v1",
        "repository": {
            "remote_url": _git(repo, "remote", "get-url", "origin"),
            "commit_sha": _git(repo, "rev-parse", "HEAD"),
            "commit_timestamp": _git(repo, "show", "-s", "--format=%cI", "HEAD"),
            "tracked_file_count": len(files),
            "files": files,
        },
        "candidate_data_files": candidates,
        "labeled_research_dataset_count": sum(
            item.get("qualifies_as_labeled_research_data") is True
            for item in candidates
        ),
        "api_or_llm_calls": 0,
        "decision": decision,
        "decision_reason": reason,
        "stage1_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    receipt = scan_repo(args.repo)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "decision": receipt["decision"],
                "reason": receipt["decision_reason"],
                "tracked_files": receipt["repository"]["tracked_file_count"],
                "candidate_data_files": len(receipt["candidate_data_files"]),
                "labeled_datasets": receipt["labeled_research_dataset_count"],
                "api_or_llm_calls": receipt["api_or_llm_calls"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
