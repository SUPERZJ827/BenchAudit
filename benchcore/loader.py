from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .field_mapping import infer_mapping, mapping_from_dict
from .schema import BenchmarkItem, FieldMapping


MAPPING_RECEIPT_VERSION = "1"
_CANONICAL_MAPPING_FIELDS = (
    "item_id",
    "task",
    "context",
    "choices",
    "gold",
    "aliases",
    "output_contract",
    "evaluator",
)


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _schema_shape(value: Any) -> Any:
    """Return a value-free, deterministic description of a JSON-like value."""

    if isinstance(value, dict):
        return {
            "type": "object",
            "fields": {
                str(key): _schema_shape(child)
                for key, child in sorted(value.items(), key=lambda pair: str(pair[0]))
            },
        }
    if isinstance(value, (list, tuple)):
        element_shapes = {
            json.dumps(
                _schema_shape(child), sort_keys=True, separators=(",", ":"), default=str,
            )
            for child in value
        }
        return {
            "type": "array",
            "elements": [json.loads(shape) for shape in sorted(element_shapes)],
        }
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, (int, float)):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    return {"type": type(value).__name__}


def record_schema_sha256(row: dict[str, Any]) -> str:
    """Bind a mapping receipt to the structure of the live source record."""

    return _stable_sha256(_schema_shape(row))


def mapping_bindings_sha256(bindings: dict[str, Any]) -> str:
    """Bind a receipt to exact source-to-canonical field declarations."""

    return _stable_sha256(bindings)


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


def _as_choices(value: Any) -> list[Any] | dict[Any, Any] | None:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return _as_list(value) or None


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
    selected_schema = {
        **selected,
        "context": list(mapping.context),
        "metadata": list(mapping.metadata),
    }
    schema_fingerprint = str(
        diagnostics.get("schema_fingerprint")
        or hashlib.sha256(
            json.dumps(
                selected_schema,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    )
    binding_sha256 = mapping_bindings_sha256(selected_schema)
    if source == "generated_adapter":
        activation_mode = str(diagnostics.get("activation_mode") or "unverified")
        trust_domain = (
            "adapter_registry_verified_v1"
            if activation_mode == "active_verified"
            else "adapter_shadow_v1"
        )
    elif source == "explicit":
        activation_mode = "host_explicit"
        trust_domain = "user_explicit_mapping_v1"
    else:
        activation_mode = "inferred"
        trust_domain = "inferred_mapping_v1"
    return {
        "receipt_version": MAPPING_RECEIPT_VERSION,
        "source": source,
        "trust_domain": trust_domain,
        "activation_mode": activation_mode,
        "adapter_id": str(
            diagnostics.get("adapter_id")
            or ("user_field_mapping" if source == "explicit" else "automatic_field_inference")
        ),
        "adapter_version": str(diagnostics.get("adapter_version") or "1"),
        "schema_fingerprint": schema_fingerprint,
        "adapter_sha256": diagnostics.get("adapter_sha256"),
        "adapter_family": diagnostics.get("adapter_family"),
        "adapter_registry_root": diagnostics.get("adapter_registry_root"),
        "receipt_id": diagnostics.get("receipt_id"),
        "mapping_bindings": selected_schema,
        "mapping_bindings_sha256": binding_sha256,
        "record_schema_sha256": record_schema_sha256(row),
        "semantic_contracts": dict(diagnostics.get("semantic_contracts") or {}),
        "fields": fields,
    }


def explicit_mapping_provenance(
    *,
    adapter_id: str,
    adapter_version: str,
    raw: dict[str, Any],
    field_bindings: dict[str, Any],
) -> dict[str, Any]:
    """Issue a host-code receipt for a programmatic canonical adapter.

    Unlike the old API, callers cannot supply their own fingerprint.  The
    receipt is derived from the live source record and exact field bindings.
    AI-generated adapters do not use this authority: they must travel through
    the adapter registry and are capped unless its independent receipt is
    ``active_verified``.
    """

    if not isinstance(raw, dict):
        raise TypeError("explicit mapping provenance raw must be an object")
    if not isinstance(field_bindings, dict) or not field_bindings:
        raise ValueError("explicit mapping provenance requires field_bindings")
    unknown = sorted(set(field_bindings) - set(_CANONICAL_MAPPING_FIELDS))
    if unknown:
        raise ValueError("unknown canonical field binding(s): " + ", ".join(unknown))
    values = {
        "adapter_id": str(adapter_id).strip(),
        "adapter_version": str(adapter_version).strip(),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ValueError(
            "explicit mapping provenance requires non-empty " + ", ".join(missing)
        )
    normalized_bindings = {
        str(field): value for field, value in sorted(field_bindings.items())
    }
    fields: dict[str, Any] = {}
    for field in _CANONICAL_MAPPING_FIELDS:
        binding = normalized_bindings.get(field)
        alternatives = (
            list(binding) if isinstance(binding, (list, tuple)) else [binding]
        )
        resolved = [
            path for path in alternatives
            if isinstance(path, str)
            and _get(raw, path) not in (None, "", [], {})
        ]
        fields[field] = {
            "selected": binding,
            "resolved_key": resolved[0] if resolved else None,
            "row_status": "resolved" if resolved else "unresolved",
            "mapping_status": "host_explicit",
        }
    binding_sha256 = mapping_bindings_sha256(normalized_bindings)
    return {
        "receipt_version": MAPPING_RECEIPT_VERSION,
        "source": "explicit",
        "trust_domain": "host_programmatic_mapping_v1",
        "activation_mode": "host_explicit",
        **values,
        # Compatibility name retained for report consumers; it is now computed
        # rather than a caller-controlled trust assertion.
        "schema_fingerprint": binding_sha256,
        "mapping_bindings": normalized_bindings,
        "mapping_bindings_sha256": binding_sha256,
        "record_schema_sha256": record_schema_sha256(raw),
        "fields": fields,
    }


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
                choices=_as_choices(choices),
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
