from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .field_mapping import infer_mapping, mapping_from_dict
from .schema import BenchmarkItem, FieldMapping


def load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows = []
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc
                if not isinstance(row, dict):
                    raise ValueError(f"JSONL line {line_no} is not an object")
                rows.append(row)
        return rows
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("data", "items", "examples", "rows"):
                if isinstance(data.get(key), list):
                    return [x for x in data[key] if isinstance(x, dict)]
            return [data]
        raise ValueError("JSON input must be an object or a list of objects")
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    raise ValueError(f"Unsupported input format: {suffix}. Use .jsonl, .json, or .csv")


def load_mapping(path: Path | None, rows: list[dict[str, Any]]) -> FieldMapping:
    if path is None:
        return infer_mapping(rows)
    return mapping_from_dict(json.loads(path.read_text(encoding="utf-8")))


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return [value]
    return [value]


def _get(row: dict[str, Any], key: str | None) -> Any:
    if not key:
        return None
    return row.get(key)


def build_items(rows: list[dict[str, Any]], mapping: FieldMapping) -> list[BenchmarkItem]:
    items = []
    for idx, row in enumerate(rows):
        item_id = str(_get(row, mapping.item_id) or f"item-{idx}")
        context = {key: row.get(key) for key in mapping.context if key in row}
        metadata: dict[str, Any] = {}
        raw_metadata = row.get("metadata")
        if isinstance(raw_metadata, dict):
            metadata.update(raw_metadata)
        for key in mapping.metadata:
            if key not in row or key == "metadata":
                continue
            metadata[key] = row.get(key)
        items.append(
            BenchmarkItem(
                item_id=item_id,
                raw=row,
                task=_get(row, mapping.task),
                context=context,
                choices=_as_list(_get(row, mapping.choices)) or None,
                gold=_get(row, mapping.gold),
                aliases=_as_list(_get(row, mapping.aliases)),
                output_contract=_get(row, mapping.output_contract),
                evaluator=_get(row, mapping.evaluator),
                metadata=metadata,
            )
        )
    return items
