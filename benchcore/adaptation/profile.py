"""Deterministic schema profiling without using labels or row identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import AdapterSpec, AdapterValidationError, canonical_sha256


PROFILE_SCHEMA_VERSION = "benchcore-schema-profile-v1"
MAX_PROFILE_DEPTH = 10
MAX_PROFILE_PATHS = 512
MAX_EXAMPLE_STRING_CHARS = 160


@dataclass(frozen=True)
class PathProfile:
    path: tuple[str, ...]
    present: int
    types: tuple[str, ...]
    list_element_types: tuple[str, ...]
    examples: tuple[Any, ...]

    def to_dict(self, *, include_examples: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "path": list(self.path),
            "present": self.present,
            "types": list(self.types),
            "list_element_types": list(self.list_element_types),
        }
        if include_examples:
            result["examples"] = list(self.examples)
        return result


@dataclass(frozen=True)
class SchemaProfile:
    row_count: int
    paths: tuple[PathProfile, ...]
    schema_version: str = PROFILE_SCHEMA_VERSION

    @property
    def fingerprint(self) -> str:
        # Values, row order, row count and presence counts are excluded.  The
        # digest represents the observable structural contract, not a dataset
        # content hash and not a train/holdout membership signal.
        payload = {
            "schema_version": self.schema_version,
            "paths": [
                {
                    "path": list(path.path),
                    "types": list(path.types),
                    "list_element_types": list(path.list_element_types),
                }
                for path in self.paths
            ],
        }
        return canonical_sha256(payload)

    def to_dict(self, *, include_examples: bool = True) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "row_count": self.row_count,
            "schema_fingerprint": self.fingerprint,
            "paths": [
                path.to_dict(include_examples=include_examples)
                for path in self.paths
            ],
        }


def build_schema_profile(
    rows: list[dict[str, Any]],
    *,
    max_examples_per_path: int = 2,
) -> SchemaProfile:
    if not isinstance(rows, list) or not rows:
        raise AdapterValidationError("schema profiling requires at least one row")
    if any(not isinstance(row, dict) for row in rows):
        raise AdapterValidationError("every profiled row must be an object")
    if not 0 <= max_examples_per_path <= 5:
        raise ValueError("max_examples_per_path must be between zero and five")

    states: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        observed_in_row: set[tuple[str, ...]] = set()
        _walk(row, (), states, observed_in_row, max_examples_per_path)
        for path in observed_in_row:
            states[path]["present"] += 1
    if len(states) > MAX_PROFILE_PATHS:
        raise AdapterValidationError(
            f"schema exposes {len(states)} paths; maximum is {MAX_PROFILE_PATHS}"
        )
    profiles = tuple(
        PathProfile(
            path=path,
            present=int(state["present"]),
            types=tuple(sorted(state["types"])),
            list_element_types=tuple(sorted(state["list_element_types"])),
            examples=tuple(state["examples"]),
        )
        for path, state in sorted(states.items())
    )
    return SchemaProfile(row_count=len(rows), paths=profiles)


def schema_fingerprint(rows: list[dict[str, Any]]) -> str:
    return build_schema_profile(rows, max_examples_per_path=0).fingerprint


def validate_spec_against_profile(
    spec: AdapterSpec,
    profile: SchemaProfile,
) -> None:
    """Statically type-check every generated source and transform chain."""

    observed = {path.path: set(path.types) for path in profile.paths}
    expected_types = {
        "task": {"string"},
        "context": {"object"},
        "choices": {"array"},
        "aliases": {"array"},
        "evaluator": {"object"},
        "metadata": {"object"},
    }
    for binding in spec.bindings:
        if binding.path is not None:
            source_types = _source_types(binding.path, observed)
            output_types = _transform_types(source_types, binding.transforms)
        elif binding.template is not None:
            source_types = _source_types(binding.template.path, observed)
            output_types = _transform_types(source_types, binding.template.transforms)
            if output_types & {"array", "object"}:
                raise AdapterValidationError(
                    f"template target {binding.target!r} may receive non-scalar types "
                    f"{sorted(output_types)}"
                )
            output_types = {"string"}
        else:
            for field in binding.object_fields:
                if field.path is None:
                    continue
                source_types = _source_types(field.path, observed)
                _transform_types(source_types, field.transforms)
            output_types = {"object"}
        expected = expected_types.get(binding.target)
        if expected is not None and not output_types <= expected:
            raise AdapterValidationError(
                f"target {binding.target!r} expects {sorted(expected)} but the "
                f"declared chain may produce {sorted(output_types)}"
            )


def _source_types(
    path: tuple[str, ...],
    observed: dict[tuple[str, ...], set[str]],
) -> set[str]:
    types = observed.get(path)
    if not types:
        raise AdapterValidationError(
            f"adapter source path {'.'.join(path)!r} is absent from schema profile"
        )
    unsupported = {value for value in types if value.startswith("non_json:")}
    if unsupported:
        raise AdapterValidationError(
            f"adapter source path {'.'.join(path)!r} has non-JSON types "
            f"{sorted(unsupported)}"
        )
    return set(types)


def _transform_types(
    source_types: set[str],
    transforms: tuple[str, ...],
) -> set[str]:
    current = set(source_types)
    all_json = {"null", "boolean", "integer", "number", "string", "array", "object"}
    for transform in transforms:
        if transform == "parse_jsonish":
            # Non-string JSON values pass through; strings may decode to any
            # JSON type and are validated against every row at runtime.
            current = (current - {"string"}) | (all_json if "string" in current else set())
        elif transform == "strip":
            if current != {"string"}:
                raise AdapterValidationError(
                    f"strip requires only strings, observed {sorted(current)}"
                )
            current = {"string"}
        elif transform == "stringify":
            current = {"string"}
        elif transform == "as_list":
            current = {"array"}
        elif transform in {"as_context", "as_metadata", "as_evaluator"}:
            current = {"object"}
        else:  # pragma: no cover - AdapterSpec validation rejects it first
            raise AdapterValidationError(f"unsupported transform {transform!r}")
    return current


def _walk(
    value: Mapping[str, Any],
    prefix: tuple[str, ...],
    states: dict[tuple[str, ...], dict[str, Any]],
    observed: set[tuple[str, ...]],
    max_examples: int,
) -> None:
    if len(prefix) >= MAX_PROFILE_DEPTH:
        return
    for raw_key, child in value.items():
        if not isinstance(raw_key, str):
            raise AdapterValidationError("object field names must be strings")
        path = (*prefix, raw_key)
        state = states.setdefault(path, {
            "present": 0,
            "types": set(),
            "list_element_types": set(),
            "examples": [],
        })
        observed.add(path)
        state["types"].add(_json_type(child))
        if isinstance(child, list):
            state["list_element_types"].update(_json_type(entry) for entry in child)
        if len(state["examples"]) < max_examples:
            example = _bounded_example(child)
            if example not in state["examples"]:
                state["examples"].append(example)
        if isinstance(child, dict):
            _walk(child, path, states, observed, max_examples)


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return f"non_json:{type(value).__name__}"


def _bounded_example(value: Any, *, depth: int = 0) -> Any:
    if depth >= 3:
        return f"<{_json_type(value)}>"
    if isinstance(value, str):
        return value[:MAX_EXAMPLE_STRING_CHARS]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [_bounded_example(entry, depth=depth + 1) for entry in value[:3]]
    if isinstance(value, dict):
        return {
            str(key): _bounded_example(child, depth=depth + 1)
            for key, child in list(value.items())[:8]
        }
    return f"<{type(value).__name__}>"
