"""Minimal structural corpus adapters for non-code routing experiments.

The adapters expose field/capability presence only.  They intentionally do
not compute findings, read defect labels, or treat WorkspaceBench
``output_files`` as a trusted deliverable contract.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd


PROBE_FAMILIES = (
    "placeholder_leak",
    "duplicate_rubric_criterion",
    "rubric_column_conflict",
    "task_rubric_column_difference",
    "task_rubric_output_filename_conflict",
    "task_output_filename",
    "task_output_format",
    "rubric_output_filename",
    "rubric_output_format",
    "task_reference_filename",
    "rubric_reference_filename",
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [value]
        return parsed if isinstance(parsed, list) else [parsed]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _rubric_count(value: Any) -> int:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return 0
    if isinstance(value, Mapping):
        value = value.get("rubrics", [])
    return len(value) if isinstance(value, list) else 0


def load_workspace(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            manifest = parse_list(raw.get("data_manifest"))
            rows.append({
                "task_id": str(
                    raw.get("item_id") or raw.get("absolute_id")
                ),
                "has_task": bool(str(raw.get("task") or "").strip()),
                "rubric_count": len(parse_list(raw.get("rubrics"))),
                "has_references": any(
                    isinstance(entry, Mapping) and entry.get("filename")
                    for entry in manifest
                ),
                # User-established boundary: WorkspaceBench output_files are
                # not a gold deliverable manifest; scoring is rubric-driven.
                "has_trusted_deliverables": False,
            })
    return rows


def load_gdpval(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_parquet(path)
    rows = []
    for raw in frame.to_dict(orient="records"):
        rows.append({
            "task_id": str(raw["task_id"]),
            "has_task": bool(str(raw.get("prompt") or "").strip()),
            "rubric_count": _rubric_count(raw.get("rubric_json")),
            "has_references": bool(parse_list(raw.get("reference_files"))),
            "has_trusted_deliverables": bool(
                parse_list(raw.get("deliverable_files"))
            ),
        })
    return rows


def applicability(row: Mapping[str, Any]) -> tuple[str, ...]:
    has_task = bool(row.get("has_task"))
    rubric_count = int(row.get("rubric_count") or 0)
    has_rubrics = rubric_count > 0
    has_references = bool(row.get("has_references"))
    has_deliverables = bool(row.get("has_trusted_deliverables"))
    result = set()
    if has_rubrics:
        result.add("placeholder_leak")
    if rubric_count >= 2:
        result.add("duplicate_rubric_criterion")
    if has_task and has_rubrics:
        result.update({
            "rubric_column_conflict",
            "task_rubric_column_difference",
            "task_rubric_output_filename_conflict",
        })
    if has_task and has_deliverables:
        result.update({"task_output_filename", "task_output_format"})
    if has_rubrics and has_deliverables:
        result.update({"rubric_output_filename", "rubric_output_format"})
    if has_task and has_references:
        result.add("task_reference_filename")
    if has_rubrics and has_references:
        result.add("rubric_reference_filename")
    return tuple(
        family for family in PROBE_FAMILIES if family in result
    )


def build_corpus(
    dataset: str,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "dataset": dataset,
            "task_id": str(row["task_id"]),
            "applicable": applicability(row),
        }
        for row in rows
    ]
