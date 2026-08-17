"""Deterministic validation of structured reference calls against tool schemas."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .checkers import Checker, _violation
from .coverage import AuditEligibility
from .schema import BenchmarkItem, Violation


def _function_name(schema: Any) -> str:
    if not isinstance(schema, dict):
        return ""
    if schema.get("name") not in (None, ""):
        return str(schema["name"])
    nested = schema.get("function")
    if isinstance(nested, dict) and nested.get("name") not in (None, ""):
        return str(nested["name"])
    return ""


def _function_parameters(schema: dict[str, Any]) -> dict[str, Any] | None:
    body = schema.get("function") if isinstance(schema.get("function"), dict) else schema
    parameters = body.get("parameters") if isinstance(body, dict) else None
    return parameters if isinstance(parameters, dict) else None


def _reference_calls(item: BenchmarkItem) -> dict[str, Any] | None:
    value = item.raw.get("reference_solution") if isinstance(item.raw, dict) else None
    return value if isinstance(value, dict) else None


def _schema_index(item: BenchmarkItem) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for value in item.context.values():
        if not isinstance(value, list):
            continue
        for entry in value:
            name = _function_name(entry)
            if name and isinstance(entry, dict):
                index.setdefault(name, entry)
    return index


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _validate_value(value: Any, schema: dict[str, Any], path: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    expected = schema.get("type")
    expected_types = (
        [expected]
        if isinstance(expected, str)
        else [entry for entry in expected if isinstance(entry, str)]
        if isinstance(expected, list)
        else []
    )
    if expected_types and not any(_json_type_matches(value, kind) for kind in expected_types):
        return [{
            "path": path,
            "kind": "type_mismatch",
            "expected": expected_types,
            "actual": type(value).__name__,
            "value": value,
        }]
    if isinstance(schema.get("enum"), list) and value not in schema["enum"]:
        issues.append({
            "path": path,
            "kind": "enum_mismatch",
            "value": value,
            "allowed": schema["enum"],
        })
    if isinstance(value, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            required = schema.get("required") if isinstance(schema.get("required"), list) else []
            for key in required:
                if key not in value:
                    issues.append({"path": f"{path}.{key}", "kind": "missing_required"})
            additional = schema.get("additionalProperties", True)
            for key, child in value.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    issues.extend(_validate_value(child, child_schema, f"{path}.{key}"))
                elif additional is False:
                    issues.append({
                        "path": f"{path}.{key}",
                        "kind": "unknown_property",
                        "value": child,
                    })
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            issues.extend(_validate_value(child, schema["items"], f"{path}[{index}]"))
    return issues


def reference_schema_issues(item: BenchmarkItem) -> list[dict[str, Any]]:
    calls = _reference_calls(item)
    if calls is None:
        return []
    schemas = _schema_index(item)
    issues: list[dict[str, Any]] = []
    for raw_name, arguments in calls.items():
        name = re.sub(r"_\d+$", "", str(raw_name))
        schema = schemas.get(str(raw_name)) or schemas.get(name)
        if schema is None:
            issues.append({"path": str(raw_name), "kind": "missing_function_schema"})
            continue
        parameters = _function_parameters(schema)
        if parameters is None:
            issues.append({"path": str(raw_name), "kind": "missing_parameters_schema"})
            continue
        issues.extend(_validate_value(arguments, parameters, str(raw_name)))
    return issues


def _schema_snapshot_sha256(item: BenchmarkItem) -> str:
    payload = json.dumps(
        _schema_index(item), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ReferenceSchemaChecker(Checker):
    """Check only claims mechanically entailed by JSON-style tool schemas."""

    name = "reference_schema_validation"

    def audit_eligibility(self, item: BenchmarkItem, root: Path | None = None) -> AuditEligibility:
        if _reference_calls(item) is None:
            return AuditEligibility.not_applicable("no structured reference_solution")
        if not _schema_index(item):
            return AuditEligibility.not_applicable("no named function schemas in canonical context")
        return AuditEligibility.applicable(
            "structured reference and named function schemas are both present"
        )

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        issues = reference_schema_issues(item)
        if not issues:
            return []
        yield _violation(
            item,
            "reference_schema_mismatch",
            "Structured reference call violates the declared function schema.",
            {
                "proof_schema_version": "reference-schema-validation-v1",
                "issues": issues,
                "reference_solution": _reference_calls(item),
                "schema_snapshot_sha256": _schema_snapshot_sha256(item),
            },
            severity="review",
            review_only=True,
            method="reference_schema_validation",
        )
