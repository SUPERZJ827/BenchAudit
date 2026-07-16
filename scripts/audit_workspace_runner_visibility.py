#!/usr/bin/env python3
"""Prove reference-generator visibility in a pinned Workspace-Bench runner view."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchcore.loader import build_items, load_mapping, load_rows
from benchcore.workspace_invariants import collect_workspace_invariant_issues
from benchcore.zip_range import HTTPRangeReader, read_zip_entry, read_zip_index
from benchcore.workspace_visibility import SCHEMA_VERSION


WORKSPACE_REPO = "Workspace-Bench/Workspace-Bench-Workspaces"
WORKSPACE_REVISION = "e245d63bfa20cfdb708cd8e78145ffb087155857"
WORKSPACE_ARCHIVE = "filesys_cn.zip"
WORKSPACE_ARCHIVE_BYTES = 18_861_940_415
WORKSPACE_ARCHIVE_LFS_SHA256 = (
    "4d04f93233664b159620dee07b17c35cc4984a220c12b5d3e3db759146b82bee"
)
RUNNER_COMMIT = "268643b92bb6d417064236ccc2b4999fdd63d240"
ROLE_PREFIX = {
    "Product Manager": "ProductManager_Workdir/",
    "Backend Developer": "BackendDeveloper_Workdir/",
    "Researcher": "Research_Workdir/",
    "Operations Manager": "OperationsManager_Workdir/",
    "Logistics Manager": "LogisticsManager_Workdir/",
}
RUNNER_FILES = (
    "evaluation/src/filesys_utils.py",
    "evaluation/src/agent_runner.py",
    "evaluation/src/agent_as_a_judge.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", default="datasets/workspacebench/lite_cn_100_pinned.jsonl",
    )
    parser.add_argument(
        "--out", default="reports/workspace_runner_visibility_20260714/report.json",
    )
    parser.add_argument(
        "--md", default="reports/workspace_runner_visibility_20260714/report.md",
    )
    return parser.parse_args()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def runner_provenance() -> dict[str, Any]:
    rows = []
    contents: dict[str, str] = {}
    for path in RUNNER_FILES:
        url = (
            f"https://raw.githubusercontent.com/OpenDataBox/Workspace-Bench/"
            f"{RUNNER_COMMIT}/{path}"
        )
        payload = fetch(url)
        text = payload.decode("utf-8")
        contents[path] = text
        rows.append({"path": path, "url": url, "sha256": sha256(payload)})
    checks = {
        "raw_workspace_copied_to_standard": (
            "shutil.copytree(raw_path, standard_path)" in contents[RUNNER_FILES[0]]
        ),
        "standard_workspace_copied_to_agent_case": (
            "_copytree_fast(standard_work_dir, work_dir)" in contents[RUNNER_FILES[1]]
        ),
        "task_data_exposed_in_judge_view": (
            "_symlink_or_copy(inputs_dir, dst)" in contents[RUNNER_FILES[2]]
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"pinned runner visibility markers changed: {checks}")
    return {"commit": RUNNER_COMMIT, "files": rows, "verified_semantics": checks}


def main() -> int:
    args = parse_args()
    dataset_path = (REPO / args.dataset).resolve()
    rows = load_rows(dataset_path)
    items = build_items(rows, load_mapping(None, rows))
    suspects = []
    for item in items:
        for issue in collect_workspace_invariant_issues(item):
            if issue.defect_type != "solution_leak":
                continue
            for file_row in issue.evidence.get("files", []):
                suspects.append({
                    "item_id": item.item_id,
                    "absolute_id": item.metadata.get("absolute_id"),
                    "persona": item.raw.get("persona") or item.metadata.get("persona"),
                    "task_package_path": file_row["path"],
                    "task_package_sha256": file_row["sha256"],
                    "matched": file_row.get("matched"),
                    "excerpt": file_row.get("excerpt"),
                })

    archive_url = (
        f"https://huggingface.co/datasets/{WORKSPACE_REPO}/resolve/"
        f"{WORKSPACE_REVISION}/{WORKSPACE_ARCHIVE}"
    )
    reader = HTTPRangeReader(archive_url, timeout=120)
    if reader.size != WORKSPACE_ARCHIVE_BYTES:
        raise RuntimeError(
            f"archive size changed: expected {WORKSPACE_ARCHIVE_BYTES}, got {reader.size}"
        )
    index = read_zip_index(reader)
    matches = []
    for suspect in suspects:
        role = ROLE_PREFIX.get(str(suspect["persona"]))
        basename = Path(str(suspect["task_package_path"])).name.casefold()
        candidates = [
            entry for entry in index.entries
            if (not role or entry.name.startswith(role))
            and Path(entry.name).name.casefold() == basename
        ]
        candidate_rows = []
        for entry in candidates:
            payload = read_zip_entry(reader, entry, max_uncompressed_bytes=2_000_000)
            digest = sha256(payload)
            candidate_rows.append({
                "archive_member": entry.name,
                "sha256": digest,
                "crc32": f"{entry.crc32:08x}",
                "compressed_bytes": entry.compressed_size,
                "uncompressed_bytes": entry.uncompressed_size,
                "byte_identical_to_task_package": (
                    digest == suspect["task_package_sha256"]
                ),
            })
        exact = [row for row in candidate_rows if row["byte_identical_to_task_package"]]
        matches.append({
            **suspect,
            "archive_candidates": candidate_rows,
            "exact_agent_workspace_matches": exact,
            "visibility": {
                "task_package_present": True,
                "agent_visible": bool(exact),
                "evaluator_visible": True,
                "visibility_verified": bool(exact),
            },
            "status": "confirmed" if exact else "review",
        })

    runner = runner_provenance()
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(dataset_path),
            "sha256": sha256(dataset_path.read_bytes()),
            "items": len(items),
        },
        "archive": {
            "repo": WORKSPACE_REPO,
            "revision": WORKSPACE_REVISION,
            "filename": WORKSPACE_ARCHIVE,
            "bytes": reader.size,
            "declared_lfs_sha256": WORKSPACE_ARCHIVE_LFS_SHA256,
            "central_directory_offset": index.central_directory_offset,
            "central_directory_bytes": index.central_directory_size,
            "central_directory_sha256": index.central_directory_sha256,
            "entries": len(index.entries),
            "range_only": True,
        },
        "runner": runner,
        "summary": {
            "suspect_reference_generators": len(matches),
            "confirmed_agent_visible": sum(
                int(row["visibility"]["agent_visible"]) for row in matches
            ),
            "confirmed_evaluator_visible": sum(
                int(row["visibility"]["evaluator_visible"]) for row in matches
            ),
        },
        "findings": matches,
    }
    out = (REPO / args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = (REPO / args.md).resolve()
    md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Workspace-Bench runner 可见性复核",
        "",
        f"- 固定工作区 revision：`{WORKSPACE_REVISION}`",
        f"- 归档：`{WORKSPACE_ARCHIVE}`（{reader.size:,} bytes，{len(index.entries):,} entries）",
        f"- 只读取中央目录与候选成员：`true`",
        f"- 可疑生成器：`{len(matches)}`",
        f"- 确认 Agent 可见：`{report['summary']['confirmed_agent_visible']}`",
        f"- 确认 Judge 可见：`{report['summary']['confirmed_evaluator_visible']}`",
        "",
        "## Findings",
        "",
    ]
    for row in matches:
        exact = row["exact_agent_workspace_matches"]
        lines.extend([
            f"### `{row['item_id']}`",
            "",
            f"- 状态：`{row['status']}`",
            f"- Task package SHA-256：`{row['task_package_sha256']}`",
            f"- Agent member：`{exact[0]['archive_member'] if exact else 'not proven'}`",
            f"- 三层可见性：`{json.dumps(row['visibility'], ensure_ascii=False)}`",
            "",
        ])
    md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if all(row["status"] == "confirmed" for row in matches) else 2


if __name__ == "__main__":
    raise SystemExit(main())
