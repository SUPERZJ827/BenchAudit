"""Versioned, non-executable DSL for benchmark adapters."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


ADAPTER_SCHEMA_VERSION = "benchcore-adapter-v1"
MAX_BINDINGS = 40
MAX_PATH_DEPTH = 10
MAX_TRANSFORMS = 4
MAX_NAME_CHARS = 64

CORE_TARGETS = frozenset({
    "item_id",
    "task",
    "context",
    "choices",
    "gold",
    "aliases",
    "output_contract",
    "evaluator",
    "metadata",
})

# These are normalized raw fields consumed by trusted family checkers.  Adding
# a new target is a reviewed change to the trusted control plane; a generated
# adapter cannot invent an executable checker or arbitrary destination.
FAMILY_EXTENSION_TARGETS: dict[str, frozenset[str]] = {
    "generic": frozenset(),
    "workspacebench": frozenset({
        "rubrics",
        "rubric_types",
        "output_files",
        "input_files",
        "data_manifest",
        "file_dep_graph",
        "tested_capabilities",
    }),
    "swebench": frozenset({
        "repo",
        "base_commit",
        "patch",
        "test_patch",
        "fail_to_pass",
        "pass_to_pass",
    }),
    "terminalbench": frozenset({
        "commands",
        "environment",
        "tests",
    }),
}
ALLOWED_FAMILIES = frozenset(FAMILY_EXTENSION_TARGETS)
ALLOWED_TRANSFORMS = frozenset({
    "parse_jsonish",
    "strip",
    "stringify",
    "as_list",
    "as_context",
    "as_evaluator",
    "as_metadata",
})

# Labels, split membership, generated-code carriers, and provenance may never
# be used as schema signals.  This prevents a mutation sidecar from becoming a
# shortcut for an apparently perfect adapter.
# These names are reserved by BenchAudit's mutation/evolution fixtures.  Common
# benchmark fields such as ``label``, ``reference`` and ``split`` are *not*
# globally forbidden: they are legitimate data in many public benchmarks.
# Sidecar labels are kept physically separate, and role-sensitive names below
# are allowed only for semantically compatible destinations.
FORBIDDEN_PATH_SEGMENTS = frozenset({
    "expected_label",
    "mutation_id",
    "operator",
    "adapter_answer",
    "reference_row",
    "canonical_reference",
    "_injected_defect",
    "_mutation_provenance",
    "_challenge_provenance",
})
ROLE_SENSITIVE_PATHS: dict[str, frozenset[str]] = {
    "label": frozenset({"gold"}),
    "reference": frozenset({"gold", "evaluator"}),
    "expected": frozenset({"gold", "output_contract"}),
}

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{2,63}\Z")
_PATH_SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_. -]{0,95}\Z")


class AdapterValidationError(ValueError):
    """A generated adapter violated the trusted, non-executable schema."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def allowed_targets(family: str) -> frozenset[str]:
    if family not in FAMILY_EXTENSION_TARGETS:
        raise AdapterValidationError(f"unsupported adapter family: {family!r}")
    return CORE_TARGETS | FAMILY_EXTENSION_TARGETS[family]


def _strict_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    where: str,
) -> None:
    optional = optional or set()
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing:
        raise AdapterValidationError(f"{where} is missing keys: {sorted(missing)}")
    if extra:
        raise AdapterValidationError(f"{where} has unknown keys: {sorted(extra)}")


def _path_from_json(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_PATH_DEPTH:
        raise AdapterValidationError(
            f"binding.path must contain 1..{MAX_PATH_DEPTH} string segments"
        )
    result: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not _PATH_SEGMENT.fullmatch(value):
            raise AdapterValidationError(f"invalid binding path segment: {value!r}")
        segment = value.strip()
        lowered = segment.casefold()
        if (
            lowered in FORBIDDEN_PATH_SEGMENTS
            or "__" in lowered
            or lowered.endswith("_provenance")
        ):
            raise AdapterValidationError(
                f"adapter cannot read reserved sidecar/provenance path {segment!r}"
            )
        result.append(segment)
    return tuple(result)


def _validate_path_role(path: tuple[str, ...], *, target: str) -> None:
    leaf = path[-1].casefold()
    allowed = ROLE_SENSITIVE_PATHS.get(leaf)
    if allowed is not None and target not in allowed:
        raise AdapterValidationError(
            f"source field {path[-1]!r} may only populate {sorted(allowed)}, "
            f"not {target!r}"
        )


def _validate_literal(value: Any, *, depth: int = 0) -> None:
    if depth > 5:
        raise AdapterValidationError("adapter literal nesting exceeds five levels")
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if len(value) > 1_000:
            raise AdapterValidationError("adapter literal string is too long")
        return
    if isinstance(value, list):
        if len(value) > 64:
            raise AdapterValidationError("adapter literal list is too large")
        for child in value:
            _validate_literal(child, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 64 or any(not isinstance(key, str) for key in value):
            raise AdapterValidationError("adapter literal object is invalid")
        for child in value.values():
            _validate_literal(child, depth=depth + 1)
        return
    raise AdapterValidationError("adapter literals must be JSON values")


@dataclass(frozen=True)
class ObjectFieldSpec:
    key: str
    path: tuple[str, ...] | None = None
    literal: Any = None
    has_literal: bool = False
    transforms: tuple[str, ...] = ()
    required: bool = False

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        target: str,
    ) -> "ObjectFieldSpec":
        if not isinstance(value, Mapping):
            raise AdapterValidationError("binding.object entry must be an object")
        _strict_keys(
            value,
            required={"key"},
            optional={"path", "literal", "transforms", "required"},
            where="binding.object entry",
        )
        key = value["key"]
        if (
            not isinstance(key, str)
            or not key
            or len(key) > MAX_NAME_CHARS
            or key.startswith("_")
        ):
            raise AdapterValidationError("object field key is invalid")
        has_path = "path" in value
        has_literal = "literal" in value
        if has_path == has_literal:
            raise AdapterValidationError(
                "object field must contain exactly one of path or literal"
            )
        path = _path_from_json(value["path"]) if has_path else None
        if path is not None:
            _validate_path_role(path, target=target)
        literal = value.get("literal")
        if has_literal:
            _validate_literal(literal)
        raw_transforms = value.get("transforms", [])
        transforms = _parse_transforms(raw_transforms)
        if has_literal and transforms:
            raise AdapterValidationError("literal object fields cannot use transforms")
        required = value.get("required", False)
        if not isinstance(required, bool):
            raise AdapterValidationError("object field required must be boolean")
        return cls(
            key=key,
            path=path,
            literal=literal,
            has_literal=has_literal,
            transforms=transforms,
            required=required,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "key": self.key,
            "transforms": list(self.transforms),
            "required": self.required,
        }
        if self.path is not None:
            result["path"] = list(self.path)
        else:
            result["literal"] = self.literal
        return result


def _parse_transforms(raw_transforms: Any) -> tuple[str, ...]:
    if (
        not isinstance(raw_transforms, list)
        or len(raw_transforms) > MAX_TRANSFORMS
        or any(not isinstance(item, str) for item in raw_transforms)
    ):
        raise AdapterValidationError(
            f"transforms must contain at most {MAX_TRANSFORMS} strings"
        )
    transforms = tuple(raw_transforms)
    unknown = set(transforms) - ALLOWED_TRANSFORMS
    if unknown:
        raise AdapterValidationError(f"unsupported transforms: {sorted(unknown)}")
    if len(transforms) != len(set(transforms)):
        raise AdapterValidationError("transforms must not repeat")
    return transforms


@dataclass(frozen=True)
class TemplateSpec:
    format: str
    path: tuple[str, ...]
    transforms: tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        target: str,
    ) -> "TemplateSpec":
        if not isinstance(value, Mapping):
            raise AdapterValidationError("binding.template must be an object")
        _strict_keys(
            value,
            required={"format", "path"},
            optional={"transforms"},
            where="binding.template",
        )
        format_string = value["format"]
        if (
            not isinstance(format_string, str)
            or not 1 <= len(format_string) <= 200
            or format_string.count("{value}") != 1
            or format_string.replace("{value}", "").find("{") >= 0
            or format_string.replace("{value}", "").find("}") >= 0
        ):
            raise AdapterValidationError(
                "template format must contain exactly one {value} placeholder "
                "and no other braces"
            )
        path = _path_from_json(value["path"])
        _validate_path_role(path, target=target)
        transforms = _parse_transforms(value.get("transforms", []))
        if any(transform in {"as_context", "as_metadata", "as_evaluator"} for transform in transforms):
            raise AdapterValidationError("template value transforms must remain scalar")
        return cls(format=format_string, path=path, transforms=transforms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "path": list(self.path),
            "transforms": list(self.transforms),
        }


@dataclass(frozen=True)
class BindingSpec:
    target: str
    path: tuple[str, ...] | None = None
    object_fields: tuple[ObjectFieldSpec, ...] = ()
    template: TemplateSpec | None = None
    transforms: tuple[str, ...] = ()
    required: bool = False

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        family: str,
    ) -> "BindingSpec":
        if not isinstance(value, Mapping):
            raise AdapterValidationError("binding must be an object")
        _strict_keys(
            value,
            required={"target"},
            optional={"path", "object", "template", "transforms", "required"},
            where="binding",
        )
        target = str(value["target"])
        if target not in allowed_targets(family):
            raise AdapterValidationError(
                f"target {target!r} is not registered for family {family!r}"
            )
        has_path = "path" in value
        has_object = "object" in value
        has_template = "template" in value
        if sum((has_path, has_object, has_template)) != 1:
            raise AdapterValidationError(
                "binding must contain exactly one of path, object, or template"
            )
        path = _path_from_json(value["path"]) if has_path else None
        if path is not None:
            _validate_path_role(path, target=target)
        raw_object = value.get("object", [])
        if has_object and (
            not isinstance(raw_object, list)
            or not 1 <= len(raw_object) <= 32
        ):
            raise AdapterValidationError(
                "binding.object must contain 1..32 object-field entries"
            )
        object_fields = tuple(
            ObjectFieldSpec.from_dict(raw, target=target) for raw in raw_object
        )
        object_keys = [field.key for field in object_fields]
        if len(object_keys) != len(set(object_keys)):
            raise AdapterValidationError("binding.object keys must be unique")
        template = (
            TemplateSpec.from_dict(value["template"], target=target)
            if has_template else None
        )
        transforms = _parse_transforms(value.get("transforms", []))
        if (object_fields or template is not None) and transforms:
            raise AdapterValidationError(
                "constructed objects cannot use a second top-level transform chain"
            )
        required = value.get("required", False)
        if not isinstance(required, bool):
            raise AdapterValidationError("binding.required must be boolean")
        return cls(
            target=target,
            path=path,
            object_fields=object_fields,
            template=template,
            transforms=transforms,
            required=required,
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "target": self.target,
            "transforms": list(self.transforms),
            "required": self.required,
        }
        if self.path is not None:
            result["path"] = list(self.path)
        elif self.template is not None:
            result["template"] = self.template.to_dict()
        else:
            result["object"] = [field.to_dict() for field in self.object_fields]
        return result


@dataclass(frozen=True)
class AdapterSpec:
    adapter_id: str
    version: int
    family: str
    schema_fingerprint: str
    description: str
    bindings: tuple[BindingSpec, ...]
    schema_version: str = ADAPTER_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AdapterSpec":
        if not isinstance(value, Mapping):
            raise AdapterValidationError("adapter must be an object")
        _strict_keys(
            value,
            required={
                "schema_version",
                "adapter_id",
                "version",
                "family",
                "schema_fingerprint",
                "description",
                "bindings",
            },
            where="adapter",
        )
        if value["schema_version"] != ADAPTER_SCHEMA_VERSION:
            raise AdapterValidationError(
                f"unsupported adapter schema version: {value['schema_version']!r}"
            )
        adapter_id = value["adapter_id"]
        if not isinstance(adapter_id, str) or not _IDENTIFIER.fullmatch(adapter_id):
            raise AdapterValidationError(
                "adapter_id must match [a-z][a-z0-9_]{2,63}"
            )
        version = value["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise AdapterValidationError("adapter.version must be a positive integer")
        family = value["family"]
        if not isinstance(family, str) or family not in ALLOWED_FAMILIES:
            raise AdapterValidationError(f"unsupported adapter family: {family!r}")
        fingerprint = value["schema_fingerprint"]
        if (
            not isinstance(fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        ):
            raise AdapterValidationError(
                "schema_fingerprint must be a lowercase SHA-256 digest"
            )
        description = value["description"]
        if (
            not isinstance(description, str)
            or not description.strip()
            or len(description) > 1_000
        ):
            raise AdapterValidationError(
                "adapter.description must contain 1..1000 characters"
            )
        raw_bindings = value["bindings"]
        if (
            not isinstance(raw_bindings, list)
            or not 1 <= len(raw_bindings) <= MAX_BINDINGS
        ):
            raise AdapterValidationError(
                f"adapter.bindings must contain 1..{MAX_BINDINGS} entries"
            )
        bindings = tuple(
            BindingSpec.from_dict(raw, family=family) for raw in raw_bindings
        )
        targets = [binding.target for binding in bindings]
        if len(targets) != len(set(targets)):
            raise AdapterValidationError(
                "each canonical/extension target may have exactly one binding"
            )
        if "task" not in targets:
            raise AdapterValidationError("adapter must bind the canonical task field")
        if not next(binding for binding in bindings if binding.target == "task").required:
            raise AdapterValidationError("the task binding must be required")
        for binding in bindings:
            _validate_transform_target(binding)
        return cls(
            adapter_id=adapter_id,
            version=version,
            family=family,
            schema_fingerprint=fingerprint,
            description=description.strip(),
            bindings=bindings,
        )

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @property
    def targets(self) -> frozenset[str]:
        return frozenset(binding.target for binding in self.bindings)

    def binding_for(self, target: str) -> BindingSpec | None:
        return next(
            (binding for binding in self.bindings if binding.target == target),
            None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "version": self.version,
            "family": self.family,
            "schema_fingerprint": self.schema_fingerprint,
            "description": self.description,
            "bindings": [binding.to_dict() for binding in self.bindings],
        }


def _validate_transform_target(binding: BindingSpec) -> None:
    transforms = set(binding.transforms)
    if "as_context" in transforms and binding.target != "context":
        raise AdapterValidationError("as_context is only valid for context")
    if "as_metadata" in transforms and binding.target != "metadata":
        raise AdapterValidationError("as_metadata is only valid for metadata")
    if "as_evaluator" in transforms and binding.target != "evaluator":
        raise AdapterValidationError("as_evaluator is only valid for evaluator")
    if "as_context" in transforms and "as_metadata" in transforms:
        raise AdapterValidationError("context and metadata transforms cannot be combined")
    if "stringify" in transforms and (
        {"as_context", "as_metadata", "as_evaluator"} & transforms
    ):
        raise AdapterValidationError(
            "stringify cannot be combined with object wrapper transforms"
        )
    if binding.object_fields and binding.target not in {
        "context", "metadata", "evaluator", "output_contract"
    }:
        raise AdapterValidationError(
            f"object construction is not allowed for target {binding.target!r}"
        )
