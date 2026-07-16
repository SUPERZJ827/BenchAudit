"""Trusted interpreter for :mod:`benchcore.adaptation.models`."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from ..schema import FieldMapping
from .models import AdapterSpec, AdapterValidationError, CORE_TARGETS
from .profile import build_schema_profile, validate_spec_against_profile


_MISSING = object()


@dataclass(frozen=True)
class AdaptationResult:
    rows: tuple[dict[str, Any], ...]
    source_schema_fingerprint: str
    adapter_sha256: str
    total_rows: int
    complete_rows: int
    abstained_rows: int
    binding_coverage: dict[str, float]
    errors: tuple[dict[str, Any], ...]

    @property
    def complete_rate(self) -> float:
        return self.complete_rows / self.total_rows if self.total_rows else 0.0

    def to_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        result = {
            "source_schema_fingerprint": self.source_schema_fingerprint,
            "adapter_sha256": self.adapter_sha256,
            "total_rows": self.total_rows,
            "complete_rows": self.complete_rows,
            "abstained_rows": self.abstained_rows,
            "complete_rate": self.complete_rate,
            "binding_coverage": dict(self.binding_coverage),
            "errors": list(self.errors),
        }
        if include_rows:
            result["rows"] = list(self.rows)
        return result


def adapt_rows(
    rows: list[dict[str, Any]],
    spec: AdapterSpec,
    *,
    strict_fingerprint: bool = True,
    strict_rows: bool = False,
) -> AdaptationResult:
    """Apply a validated adapter without evaluating generated Python.

    A row that misses a required field is recorded as an abstention.  Callers
    deciding to audit automatically should set ``strict_rows=True``; evaluation
    code may keep partial rows to measure coverage explicitly.
    """

    profile = build_schema_profile(rows, max_examples_per_path=0)
    observed_fingerprint = profile.fingerprint
    if strict_fingerprint and observed_fingerprint != spec.schema_fingerprint:
        raise AdapterValidationError(
            "adapter schema fingerprint mismatch; refusing silent schema drift "
            f"(expected {spec.schema_fingerprint}, observed {observed_fingerprint})"
        )
    validate_spec_against_profile(spec, profile)

    output: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    resolved = {binding.target: 0 for binding in spec.bindings}
    complete = 0
    for row_index, source_row in enumerate(rows):
        adapted: dict[str, Any] = {}
        row_errors: list[str] = []
        for binding in spec.bindings:
            if binding.path is not None:
                value = _resolve_exact(source_row, binding.path)
                source_description = ".".join(binding.path)
            elif binding.template is not None:
                raw_value = _resolve_exact(source_row, binding.template.path)
                if raw_value is _MISSING or raw_value in (None, ""):
                    value = _MISSING
                else:
                    raw_value = _apply_transforms(
                        copy.deepcopy(raw_value),
                        binding.template.transforms,
                        family=spec.family,
                    )
                    if isinstance(raw_value, (dict, list, tuple)):
                        raise TypeError("template value must be scalar")
                    value = binding.template.format.replace("{value}", str(raw_value))
                source_description = ".".join(binding.template.path)
            else:
                value, construction_errors = _construct_object(
                    source_row,
                    binding.object_fields,
                    family=spec.family,
                )
                row_errors.extend(
                    f"target {binding.target!r}: {message}"
                    for message in construction_errors
                )
                source_description = "<constructed object>"
            if value is _MISSING or value in (None, ""):
                if binding.required:
                    row_errors.append(
                        f"required target {binding.target!r} is missing at "
                        f"{source_description!r}"
                    )
                continue
            try:
                transformed = _apply_transforms(
                    copy.deepcopy(value),
                    binding.transforms,
                    family=spec.family,
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                row_errors.append(
                    f"target {binding.target!r}: {type(exc).__name__}: {exc}"
                )
                continue
            adapted[binding.target] = transformed
            resolved[binding.target] += 1
        output.append(adapted)
        if row_errors:
            errors.append({"row_index": row_index, "reasons": row_errors})
        else:
            complete += 1

    if strict_rows and errors:
        preview = errors[:5]
        raise AdapterValidationError(
            f"adapter abstained on {len(errors)}/{len(rows)} rows: {preview}"
        )
    total = len(rows)
    return AdaptationResult(
        rows=tuple(output),
        source_schema_fingerprint=observed_fingerprint,
        adapter_sha256=spec.sha256,
        total_rows=total,
        complete_rows=complete,
        abstained_rows=len(errors),
        binding_coverage={
            target: count / total if total else 0.0
            for target, count in sorted(resolved.items())
        },
        errors=tuple(errors),
    )


def mapping_for_adapted_rows(spec: AdapterSpec) -> FieldMapping:
    targets = spec.targets
    metadata = ["metadata"] if "metadata" in targets else []
    return FieldMapping(
        item_id="item_id" if "item_id" in targets else None,
        task="task",
        context=["context"] if "context" in targets else [],
        choices="choices" if "choices" in targets else None,
        gold="gold" if "gold" in targets else None,
        aliases="aliases" if "aliases" in targets else None,
        output_contract=(
            "output_contract" if "output_contract" in targets else None
        ),
        evaluator="evaluator" if "evaluator" in targets else None,
        metadata=metadata,
        diagnostics={
            "source": "generated_adapter",
            "adapter_id": spec.adapter_id,
            "adapter_version": spec.version,
            "adapter_sha256": spec.sha256,
            "schema_fingerprint": spec.schema_fingerprint,
            "registered_targets": sorted(targets & CORE_TARGETS),
            "extension_targets": sorted(targets - CORE_TARGETS),
        },
    )


def _resolve_exact(row: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = row
    for segment in path:
        if not isinstance(current, dict) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


def _apply_transforms(
    value: Any,
    transforms: tuple[str, ...],
    *,
    family: str,
) -> Any:
    current = value
    for transform in transforms:
        if transform == "parse_jsonish":
            if isinstance(current, str):
                current = json.loads(current)
        elif transform == "strip":
            if not isinstance(current, str):
                raise TypeError("strip requires a string")
            current = current.strip()
        elif transform == "stringify":
            current = str(current)
        elif transform == "as_list":
            if current is None or current == "":
                current = []
            elif isinstance(current, tuple):
                current = list(current)
            elif not isinstance(current, list):
                current = [current]
        elif transform == "as_context":
            if isinstance(current, dict):
                current = current
            elif isinstance(current, list):
                current = {"attachments": current}
            else:
                current = {"source": current}
        elif transform == "as_metadata":
            current = current if isinstance(current, dict) else {"source": current}
        elif transform == "as_evaluator":
            if not isinstance(current, dict):
                rubrics = current if isinstance(current, list) else [current]
                current = {
                    "type": (
                        "workspacebench_rubric"
                        if family == "workspacebench"
                        else "generated_adapter_evaluator"
                    ),
                    "rubrics": rubrics,
                }
        else:  # pragma: no cover - model validation makes this unreachable
            raise AdapterValidationError(f"unsupported transform: {transform}")
    return current


def _construct_object(
    row: dict[str, Any],
    fields: tuple[Any, ...],
    *,
    family: str,
) -> tuple[dict[str, Any], list[str]]:
    result: dict[str, Any] = {}
    errors: list[str] = []
    for field in fields:
        if field.has_literal:
            result[field.key] = copy.deepcopy(field.literal)
            continue
        value = _resolve_exact(row, field.path)
        if value is _MISSING or value in (None, ""):
            if field.required:
                errors.append(
                    f"required object field {field.key!r} is missing at "
                    f"{'.'.join(field.path)!r}"
                )
            continue
        try:
            result[field.key] = _apply_transforms(
                copy.deepcopy(value),
                field.transforms,
                family=family,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(
                f"object field {field.key!r}: {type(exc).__name__}: {exc}"
            )
    return result, errors
