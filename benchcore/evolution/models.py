"""Versioned schemas for bounded checker evolution.

The rule language is intentionally small.  It has no imports, regular
expressions, attribute access, filesystem access, network access, or execution
primitive.  This makes automatic activation materially safer than importing a
model-generated Python module into the auditor process.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from ..taxonomy import DEFECTS, SEVERITY_ORDER


RULE_SCHEMA_VERSION = "benchcore-declarative-rule-v1"
CORPUS_SCHEMA_VERSION = "benchcore-evolution-corpus-v1"
MAX_RULE_CONDITIONS = 8
MAX_PATH_DEPTH = 8
MAX_TRANSFORMS = 4
MAX_LITERAL_BYTES = 16_384
MAX_TEXT_CHARS = 2_000

ALLOWED_SOURCES = frozenset({"raw", "canonical"})
ALLOWED_TRANSFORMS = frozenset({
    "parse_jsonish",
    "strip",
    "casefold",
    "normalize_space",
    "length",
    "unique_count",
    "as_set",
})
UNARY_OPERATORS = frozenset({
    "is_missing",
    "is_present",
    "is_empty",
    "is_nonempty",
    "has_duplicates",
})
BINARY_OPERATORS = frozenset({
    "eq",
    "ne",
    "contains",
    "not_contains",
    "lt",
    "le",
    "gt",
    "ge",
    "subset",
    "not_subset",
    "intersects",
    "disjoint",
})
ALLOWED_OPERATORS = UNARY_OPERATORS | BINARY_OPERATORS
ALLOWED_FAMILIES = frozenset({
    "generic",
    "workspacebench",
    "swebench",
    "terminalbench",
    "rubric",
    "code",
})

# Mutation labels and record identity are forbidden inputs.  This closes the
# easiest reward-hacking route in the legacy generic injection fixture, where
# the operator name is visible in ``item_id`` and ``_injected_defect``.
FORBIDDEN_PATH_SEGMENTS = frozenset({
    "id",
    "item_id",
    "absolute_id",
    "row_uid",
    "source_row_index",
    "source_row_sha256",
    "mutation_id",
    "operator",
    "expected_label",
    "label",
    "split",
    "source_group",
    "_injected_defect",
    "_workspace_challenge",
    "_workspace_semantic_challenge",
    "_challenge_provenance",
    "_mutation_provenance",
})
PROVENANCE_KEYS = frozenset(
    value for value in FORBIDDEN_PATH_SEGMENTS if value.startswith("_")
)

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{2,63}\Z")
_PATH_SEGMENT = re.compile(r"[A-Za-z0-9_. -]{1,96}\Z")


class RuleValidationError(ValueError):
    """A generated rule or evolution corpus violated the trusted schema."""


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
        raise RuleValidationError(f"{where} is missing keys: {sorted(missing)}")
    if extra:
        raise RuleValidationError(f"{where} has unknown keys: {sorted(extra)}")


def _validate_path(path: Any, *, source: str) -> tuple[str, ...]:
    if not isinstance(path, list) or not path or len(path) > MAX_PATH_DEPTH:
        raise RuleValidationError(
            f"operand.path must contain 1..{MAX_PATH_DEPTH} string segments"
        )
    result: list[str] = []
    for raw_segment in path:
        if not isinstance(raw_segment, str) or not _PATH_SEGMENT.fullmatch(raw_segment):
            raise RuleValidationError(f"invalid operand path segment: {raw_segment!r}")
        segment = raw_segment.strip()
        lowered = segment.casefold()
        if (
            lowered in FORBIDDEN_PATH_SEGMENTS
            or lowered.startswith("_")
            or lowered.endswith("_id")
        ):
            raise RuleValidationError(
                f"rules cannot inspect identity, split, or provenance path {segment!r}"
            )
        result.append(segment)
    if source == "canonical" and result[0] not in {
        "task",
        "context",
        "choices",
        "gold",
        "aliases",
        "output_contract",
        "evaluator",
        "metadata",
    }:
        raise RuleValidationError(
            f"unsupported canonical root {result[0]!r}"
        )
    return tuple(result)


def _validate_json_literal(value: Any, *, depth: int = 0) -> None:
    if depth > 6:
        raise RuleValidationError("rule literal nesting exceeds 6 levels")
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and len(value) > MAX_TEXT_CHARS:
            raise RuleValidationError("rule literal string is too long")
        return
    if isinstance(value, list):
        if len(value) > 256:
            raise RuleValidationError("rule literal list is too large")
        for child in value:
            _validate_json_literal(child, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 128 or any(not isinstance(key, str) for key in value):
            raise RuleValidationError("rule literal object is invalid or too large")
        for child in value.values():
            _validate_json_literal(child, depth=depth + 1)
        return
    raise RuleValidationError(
        f"rule literals must be JSON values, got {type(value).__name__}"
    )


@dataclass(frozen=True)
class Operand:
    source: str
    path: tuple[str, ...]
    transforms: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Operand":
        if not isinstance(value, Mapping):
            raise RuleValidationError("operand must be an object")
        _strict_keys(
            value,
            required={"source", "path"},
            optional={"transforms"},
            where="operand",
        )
        source = str(value["source"])
        if source not in ALLOWED_SOURCES:
            raise RuleValidationError(f"unsupported operand source: {source!r}")
        path = _validate_path(value["path"], source=source)
        raw_transforms = value.get("transforms", [])
        if (
            not isinstance(raw_transforms, list)
            or len(raw_transforms) > MAX_TRANSFORMS
            or any(not isinstance(item, str) for item in raw_transforms)
        ):
            raise RuleValidationError(
                f"operand.transforms must contain at most {MAX_TRANSFORMS} strings"
            )
        transforms = tuple(raw_transforms)
        unknown = set(transforms) - ALLOWED_TRANSFORMS
        if unknown:
            raise RuleValidationError(f"unsupported transforms: {sorted(unknown)}")
        if len(transforms) != len(set(transforms)):
            raise RuleValidationError("operand transforms must not repeat")
        return cls(source=source, path=path, transforms=transforms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "path": list(self.path),
            "transforms": list(self.transforms),
        }


@dataclass(frozen=True)
class Predicate:
    left: Operand
    operator: str
    right_operand: Operand | None = None
    right_literal: Any = None
    has_right_literal: bool = False

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Predicate":
        if not isinstance(value, Mapping):
            raise RuleValidationError("condition must be an object")
        _strict_keys(
            value,
            required={"left", "operator"},
            optional={"right"},
            where="condition",
        )
        left = Operand.from_dict(value["left"])
        operator = str(value["operator"])
        if operator not in ALLOWED_OPERATORS:
            raise RuleValidationError(f"unsupported condition operator: {operator!r}")
        right = value.get("right")
        if operator in UNARY_OPERATORS:
            if right is not None:
                raise RuleValidationError(f"unary operator {operator!r} cannot have right")
            return cls(left=left, operator=operator)
        if not isinstance(right, Mapping):
            raise RuleValidationError(f"binary operator {operator!r} requires right")
        _strict_keys(
            right,
            required=set(),
            optional={"operand", "literal"},
            where="condition.right",
        )
        if set(right) == {"operand"}:
            return cls(
                left=left,
                operator=operator,
                right_operand=Operand.from_dict(right["operand"]),
            )
        if set(right) == {"literal"}:
            literal = right["literal"]
            _validate_json_literal(literal)
            if len(canonical_json(literal).encode("utf-8")) > MAX_LITERAL_BYTES:
                raise RuleValidationError("rule literal exceeds byte limit")
            return cls(
                left=left,
                operator=operator,
                right_literal=literal,
                has_right_literal=True,
            )
        raise RuleValidationError(
            "condition.right must contain exactly one of operand or literal"
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "left": self.left.to_dict(),
            "operator": self.operator,
        }
        if self.right_operand is not None:
            result["right"] = {"operand": self.right_operand.to_dict()}
        elif self.has_right_literal:
            result["right"] = {"literal": self.right_literal}
        return result


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    version: int
    family: str
    defect_type: str
    description: str
    message: str
    repair: str
    conditions: tuple[Predicate, ...]
    match: str = "all"
    confidence: float = 0.8
    schema_version: str = RULE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RuleSpec":
        if not isinstance(value, Mapping):
            raise RuleValidationError("rule must be an object")
        _strict_keys(
            value,
            required={
                "schema_version",
                "rule_id",
                "version",
                "family",
                "defect_type",
                "description",
                "message",
                "repair",
                "conditions",
            },
            optional={"match", "confidence"},
            where="rule",
        )
        if value["schema_version"] != RULE_SCHEMA_VERSION:
            raise RuleValidationError(
                f"unsupported rule schema version: {value['schema_version']!r}"
            )
        rule_id = str(value["rule_id"])
        if not _IDENTIFIER.fullmatch(rule_id):
            raise RuleValidationError(
                "rule_id must match [a-z][a-z0-9_]{2,63}"
            )
        version = value["version"]
        if not isinstance(version, int) or isinstance(version, bool) or not 1 <= version <= 1_000_000:
            raise RuleValidationError("rule version must be a positive integer")
        family = str(value["family"])
        if family not in ALLOWED_FAMILIES:
            raise RuleValidationError(f"unsupported benchmark family: {family!r}")
        defect_type = str(value["defect_type"])
        if defect_type not in DEFECTS:
            raise RuleValidationError(
                f"generated rules may only use registered defect types: {defect_type!r}"
            )
        description = _bounded_text(value["description"], "description", 1_000)
        message = _bounded_text(value["message"], "message", 1_000)
        repair = _bounded_text(value["repair"], "repair", 1_000, allow_empty=True)
        raw_conditions = value["conditions"]
        if (
            not isinstance(raw_conditions, list)
            or not 1 <= len(raw_conditions) <= MAX_RULE_CONDITIONS
        ):
            raise RuleValidationError(
                f"rule must have 1..{MAX_RULE_CONDITIONS} conditions"
            )
        conditions = tuple(Predicate.from_dict(row) for row in raw_conditions)
        match = str(value.get("match", "all"))
        if match not in {"all", "any"}:
            raise RuleValidationError("rule.match must be all or any")
        confidence = value.get("confidence", 0.8)
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0.0 <= float(confidence) <= 0.95
        ):
            raise RuleValidationError("rule confidence must be between 0 and 0.95")
        return cls(
            rule_id=rule_id,
            version=version,
            family=family,
            defect_type=defect_type,
            description=description,
            message=message,
            repair=repair,
            conditions=conditions,
            match=match,
            confidence=float(confidence),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rule_id": self.rule_id,
            "version": self.version,
            "family": self.family,
            "defect_type": self.defect_type,
            "description": self.description,
            "message": self.message,
            "repair": self.repair,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "match": self.match,
            "confidence": self.confidence,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @property
    def complexity(self) -> int:
        return sum(
            1
            + len(condition.left.transforms)
            + (
                len(condition.right_operand.transforms)
                if condition.right_operand is not None
                else 0
            )
            for condition in self.conditions
        )


@dataclass(frozen=True)
class CorpusExample:
    example_id: str
    source_group: str
    split: str
    row: dict[str, Any]
    expected_defect_types: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CorpusExample":
        if not isinstance(value, Mapping):
            raise RuleValidationError("corpus example must be an object")
        _strict_keys(
            value,
            required={
                "example_id",
                "source_group",
                "split",
                "row",
                "expected_defect_types",
            },
            where="corpus example",
        )
        example_id = str(value["example_id"])
        source_group = str(value["source_group"])
        if not example_id or len(example_id) > 128:
            raise RuleValidationError("example_id is empty or too long")
        if not source_group or len(source_group) > 128:
            raise RuleValidationError("source_group is empty or too long")
        split = str(value["split"])
        if split not in {"train", "dev", "holdout"}:
            raise RuleValidationError("split must be train, dev, or holdout")
        row = value["row"]
        if not isinstance(row, dict):
            raise RuleValidationError("corpus example row must be an object")
        leaked = _find_provenance_keys(row)
        if leaked:
            raise RuleValidationError(
                f"visible corpus row contains sidecar provenance keys: {sorted(leaked)}"
            )
        raw_labels = value["expected_defect_types"]
        if not isinstance(raw_labels, list) or any(
            not isinstance(label, str) or label not in DEFECTS
            for label in raw_labels
        ):
            raise RuleValidationError(
                "expected_defect_types must contain registered defect type strings"
            )
        labels = tuple(dict.fromkeys(raw_labels))
        return cls(
            example_id=example_id,
            source_group=source_group,
            split=split,
            row=dict(row),
            expected_defect_types=labels,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "source_group": self.source_group,
            "split": self.split,
            "row": self.row,
            "expected_defect_types": list(self.expected_defect_types),
        }


def _find_provenance_keys(value: Any, *, depth: int = 0) -> set[str]:
    if depth > 12:
        raise RuleValidationError("corpus row nesting exceeds safety limit")
    if isinstance(value, dict):
        found = {
            str(key)
            for key in value
            if str(key).casefold() in PROVENANCE_KEYS
        }
        for child in value.values():
            found.update(_find_provenance_keys(child, depth=depth + 1))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for child in value:
            found.update(_find_provenance_keys(child, depth=depth + 1))
        return found
    return set()


def _bounded_text(
    value: Any,
    field: str,
    limit: int,
    *,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise RuleValidationError(f"rule {field} must be a string")
    text = value.strip()
    if not allow_empty and not text:
        raise RuleValidationError(f"rule {field} must not be empty")
    if len(text) > limit:
        raise RuleValidationError(f"rule {field} exceeds {limit} characters")
    return text


def defect_default_severity(defect_type: str) -> str:
    severity = DEFECTS[defect_type].default_severity
    if severity not in SEVERITY_ORDER:
        raise RuleValidationError(f"invalid taxonomy severity for {defect_type!r}")
    return severity


def corpus_sha256(examples: list[CorpusExample]) -> str:
    return canonical_sha256([example.to_dict() for example in examples])


def model_asdict(value: Any) -> dict[str, Any]:
    """Dataclass serializer kept here to make report schemas deterministic."""

    return asdict(value)
