from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

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
            return _require_object_rows(data, source="JSON root list")
        if isinstance(data, dict):
            for key in ("data", "items", "examples", "rows"):
                if isinstance(data.get(key), list):
                    return _require_object_rows(
                        data[key], source=f"JSON wrapper field {key!r}",
                    )
            return [data]
        raise ValueError("JSON input must be an object or a list of objects")
    if suffix in {".csv", ".tsv"}:
        with path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f, delimiter="\t" if suffix == ".tsv" else ","))
    if suffix == ".parquet":
        try:
            import pyarrow.parquet as parquet
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise ValueError(
                "Parquet input requires the optional 'pyarrow' dependency"
            ) from exc
        return _require_object_rows(
            parquet.read_table(path).to_pylist(), source="Parquet table",
        )
    raise ValueError(
        f"Unsupported input format: {suffix}. "
        "Use .jsonl, .json, .csv, .tsv, or .parquet"
    )


def _require_object_rows(values: list[Any], *, source: str) -> list[dict[str, Any]]:
    invalid = [index for index, value in enumerate(values) if not isinstance(value, dict)]
    if invalid:
        preview = ", ".join(str(index) for index in invalid[:10])
        suffix = "..." if len(invalid) > 10 else ""
        raise ValueError(
            f"{source} contains non-object row(s) at index {preview}{suffix}; "
            "rows are never silently discarded"
        )
    return list(values)


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
    if key in row:
        return row.get(key)
    actual = next((name for name in row if name.casefold() == key.casefold()), None)
    if actual is not None:
        return row.get(actual)
    current: Any = row
    for component in key.split("."):
        if not isinstance(current, dict):
            return None
        actual = next(
            (name for name in current if name.casefold() == component.casefold()),
            None,
        )
        if actual is None:
            return None
        current = current.get(actual)
    return current


def _mapped_value(
    row: dict[str, Any], mapping: FieldMapping, field: str,
) -> tuple[str | None, Any, bool]:
    primary = getattr(mapping, field)
    value = _get(row, primary)
    if primary and value not in (None, "", [], {}):
        return primary, value, False
    diagnostics = mapping.diagnostics if isinstance(mapping.diagnostics, dict) else {}
    if diagnostics.get("source") != "inferred":
        return primary, value, False
    state = diagnostics.get("fields", {}).get(field, {})
    candidates = state.get("candidates", []) if isinstance(state, dict) else []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = candidate.get("selected_actual") or candidate.get("candidate")
        if not isinstance(key, str) or key == primary:
            continue
        candidate_value = _get(row, key)
        if candidate_value not in (None, "", [], {}):
            return key, candidate_value, True
    return primary, value, False


def _mapping_provenance_for_row(
    row: dict[str, Any], mapping: FieldMapping,
) -> dict[str, Any]:
    diagnostics = mapping.diagnostics if isinstance(mapping.diagnostics, dict) else {}
    source = str(diagnostics.get("source") or "explicit")
    global_fields = diagnostics.get("fields") if isinstance(diagnostics.get("fields"), dict) else {}
    selected = {
        "item_id": mapping.item_id,
        "task": mapping.task,
        "choices": mapping.choices,
        "gold": mapping.gold,
        "aliases": mapping.aliases,
        "output_contract": mapping.output_contract,
        "evaluator": mapping.evaluator,
    }
    fields: dict[str, Any] = {}
    for name, key in selected.items():
        resolved_key, value, fallback_used = _mapped_value(row, mapping, name)
        global_state = global_fields.get(name) if isinstance(global_fields, dict) else None
        fields[name] = {
            "selected": key,
            "resolved_key": resolved_key,
            "fallback_used": fallback_used,
            "row_status": "resolved" if key and value not in (None, "", [], {}) else "unresolved",
            "mapping_status": (
                global_state.get("status", source)
                if isinstance(global_state, dict) else source
            ),
            "coverage": (
                global_state.get("coverage")
                if isinstance(global_state, dict) else None
            ),
        }
    context_values = [(key, _get(row, key)) for key in mapping.context]
    fields["context"] = {
        "selected": list(mapping.context),
        "resolved_keys": [
            key for key, value in context_values
            if value not in (None, "", [], {})
        ],
        "row_status": (
            "resolved" if any(
                value not in (None, "", [], {}) for _, value in context_values
            )
            else "unresolved"
        ),
        "mapping_status": source,
    }
    return {"source": source, "fields": fields}


def build_items(
    rows: list[dict[str, Any]],
    mapping: FieldMapping,
    *,
    source_indices: Sequence[int] | None = None,
) -> list[BenchmarkItem]:
    if source_indices is None:
        source_indices = range(len(rows))
    if len(source_indices) != len(rows):
        raise ValueError("source_indices length must equal rows length")
    normalized_indices = [int(value) for value in source_indices]
    if any(value < 0 for value in normalized_indices):
        raise ValueError("source_indices must be non-negative")
    if len(set(normalized_indices)) != len(normalized_indices):
        raise ValueError("source_indices must be unique")
    items = []
    for row, source_index in zip(rows, normalized_indices):
        _, item_id_value, _ = _mapped_value(row, mapping, "item_id")
        item_id = str(item_id_value or f"item-{source_index}")
        context = {
            key: value for key in mapping.context
            if (value := _get(row, key)) not in (None, "", [], {})
        }
        metadata: dict[str, Any] = {}
        raw_metadata = _get(row, "metadata")
        if isinstance(raw_metadata, dict):
            metadata.update(raw_metadata)
        for key in mapping.metadata:
            value = _get(row, key)
            if value in (None, "", [], {}) or key.casefold() == "metadata":
                continue
            metadata[key] = value
        metadata["_mapping_provenance"] = _mapping_provenance_for_row(row, mapping)
        _, task, _ = _mapped_value(row, mapping, "task")
        _, choices, _ = _mapped_value(row, mapping, "choices")
        _, gold, _ = _mapped_value(row, mapping, "gold")
        _, aliases, _ = _mapped_value(row, mapping, "aliases")
        _, output_contract, _ = _mapped_value(row, mapping, "output_contract")
        _, evaluator, _ = _mapped_value(row, mapping, "evaluator")
        items.append(
            BenchmarkItem(
                item_id=item_id,
                raw=row,
                task=task,
                context=context,
                choices=_as_list(choices) or None,
                gold=gold,
                aliases=_as_list(aliases),
                output_contract=output_contract,
                evaluator=evaluator,
                metadata=metadata,
                row_uid=f"source-row-{source_index:08d}",
                source_row_index=source_index,
                source_row_sha256=hashlib.sha256(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ).encode("utf-8")
                ).hexdigest(),
            )
        )
    return items
