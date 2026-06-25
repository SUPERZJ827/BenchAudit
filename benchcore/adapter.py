from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .loader import build_items
from .schema import BenchmarkItem, FieldMapping


def canonicalize_item(item: BenchmarkItem, mapping: FieldMapping) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "task": item.task,
        "context": item.context,
        "choices": item.choices,
        "gold": item.gold,
        "aliases": item.aliases,
        "output_contract": item.output_contract,
        "evaluator": item.evaluator,
        "metadata": item.metadata,
        "artifact_coverage": artifact_coverage(item),
        "source_fields": asdict(mapping),
        "raw": item.raw,
    }


def artifact_coverage(item: BenchmarkItem) -> dict[str, bool]:
    return {
        "task_specification": bool(item.task),
        "context_attachment": bool(item.context),
        "expected_output": bool(item.output_contract or item.choices),
        "oracle_ground_truth": item.gold not in (None, ""),
        "evaluator": bool(item.evaluator or item.choices),
    }


def canonicalize_rows(rows: list[dict[str, Any]], mapping: FieldMapping) -> list[dict[str, Any]]:
    return [canonicalize_item(item, mapping) for item in build_items(rows, mapping)]


def write_canonical_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

