from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from .comparison import nested_get


def build_sample(
    rows: list[dict[str, Any]],
    source_path: Path,
    size: int,
    seed: int,
    stratify_fields: list[str],
    id_field: str = "id",
    label_field: str | None = None,
    clean_values: set[str] | None = None,
    defect_fraction: float | None = None,
    excluded_indices: set[int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    excluded_indices = excluded_indices or set()
    candidates = [
        (index, row)
        for index, row in enumerate(rows)
        if index not in excluded_indices
    ]
    target_size = min(max(size, 0), len(candidates))
    rng = random.Random(seed)

    if label_field and defect_fraction is not None:
        clean_values = {value.lower() for value in (clean_values or {"ok"})}
        clean = []
        defect = []
        for entry in candidates:
            label = _label(entry[1], label_field)
            (clean if label.lower() in clean_values else defect).append(entry)
        defect_target = min(len(defect), round(target_size * defect_fraction))
        clean_target = min(len(clean), target_size - defect_target)
        remaining = target_size - defect_target - clean_target
        if remaining:
            extra_defect = min(remaining, len(defect) - defect_target)
            defect_target += extra_defect
            remaining -= extra_defect
            clean_target += min(remaining, len(clean) - clean_target)
        selected = _balanced_sample(defect, defect_target, stratify_fields, rng)
        selected += _balanced_sample(clean, clean_target, stratify_fields, rng)
    else:
        selected = _balanced_sample(candidates, target_size, stratify_fields, rng)

    rng.shuffle(selected)
    records = [row for _, row in selected]
    selected_entries = []
    for index, row in selected:
        selected_entries.append(
            {
                "source_index": index,
                "item_id": str(nested_get(row, id_field) or f"item-{index}"),
                "stratum": {
                    field: _stable_label(nested_get(row, field))
                    for field in stratify_fields
                },
                "label": _label(row, label_field) if label_field else None,
            }
        )

    manifest = {
        "manifest_version": 1,
        "source_path": str(source_path.resolve()),
        "source_sha256": file_sha256(source_path),
        "source_items": len(rows),
        "sample_items": len(records),
        "seed": seed,
        "id_field": id_field,
        "stratify_fields": stratify_fields,
        "label_field": label_field,
        "clean_values": sorted(clean_values or []),
        "defect_fraction": defect_fraction,
        "excluded_source_indices": len(excluded_indices),
        "sample_label_distribution": dict(
            Counter(entry["label"] for entry in selected_entries if entry["label"] is not None)
        ),
        "sample_stratum_distribution": dict(
            Counter(_stratum_key(entry["stratum"]) for entry in selected_entries)
        ),
        "selected": selected_entries,
    }
    return records, manifest


def load_rows_from_manifest(
    rows: list[dict[str, Any]],
    source_path: Path,
    manifest_path: Path,
    verify_hash: bool = True,
) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if verify_hash:
        expected = manifest.get("source_sha256")
        actual = file_sha256(source_path)
        if expected and expected != actual:
            raise ValueError(
                f"Manifest source hash mismatch: expected {expected}, got {actual}"
            )
    selected = manifest.get("selected", [])
    result = []
    for entry in selected:
        index = int(entry["source_index"])
        if index < 0 or index >= len(rows):
            raise ValueError(f"Manifest source index out of range: {index}")
        result.append(rows[index])
    return result


def manifest_indices(paths: list[Path]) -> set[int]:
    indices: set[int] = set()
    for path in paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        indices.update(int(entry["source_index"]) for entry in manifest.get("selected", []))
    return indices


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _balanced_sample(
    entries: list[tuple[int, dict[str, Any]]],
    target: int,
    stratify_fields: list[str],
    rng: random.Random,
) -> list[tuple[int, dict[str, Any]]]:
    if target <= 0 or not entries:
        return []
    if not stratify_fields:
        shuffled = list(entries)
        rng.shuffle(shuffled)
        return shuffled[:target]

    groups: dict[tuple[str, ...], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for entry in entries:
        key = tuple(_stable_label(nested_get(entry[1], field)) for field in stratify_fields)
        groups[key].append(entry)
    queues = {}
    for key, values in groups.items():
        rng.shuffle(values)
        queues[key] = deque(values)

    keys = list(queues)
    rng.shuffle(keys)
    selected = []
    while len(selected) < target:
        progressed = False
        for key in keys:
            queue = queues[key]
            if not queue:
                continue
            selected.append(queue.popleft())
            progressed = True
            if len(selected) >= target:
                break
        if not progressed:
            break
    return selected


def _label(row: dict[str, Any], field: str | None) -> str:
    if not field:
        return "missing"
    return _stable_label(nested_get(row, field))


def _stable_label(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _stratum_key(stratum: dict[str, str]) -> str:
    if not stratum:
        return "all"
    return " | ".join(f"{key}={value}" for key, value in sorted(stratum.items()))

