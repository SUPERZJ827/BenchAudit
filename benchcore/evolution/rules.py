"""Trusted interpreter for model-proposed declarative checker rules."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..checkers import Checker, _violation
from ..coverage import AuditAbstained, AuditEligibility
from ..schema import BenchmarkItem, Violation
from .models import Predicate, RuleSpec, canonical_json, canonical_sha256


MAX_OPERAND_BYTES = 65_536
MAX_COLLECTION_ITEMS = 1_000
MAX_VALUE_DEPTH = 10

_MISSING = object()
_UNRESOLVED = object()


@dataclass(frozen=True)
class RuleOutcome:
    status: str
    matched: bool | None
    condition_results: tuple[dict[str, Any], ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "matched": self.matched,
            "condition_results": [dict(row) for row in self.condition_results],
            "reason": self.reason,
        }


def evaluate_rule(spec: RuleSpec, item: BenchmarkItem) -> RuleOutcome:
    results = [_evaluate_predicate(condition, item) for condition in spec.conditions]
    values = [row["result"] for row in results]
    unresolved = any(value is None for value in values)
    if spec.match == "all":
        if any(value is False for value in values):
            return RuleOutcome(
                "no_match",
                False,
                tuple(results),
                "at least one required predicate is false",
            )
        if unresolved:
            return RuleOutcome(
                "abstained",
                None,
                tuple(results),
                "one or more required predicates could not be evaluated safely",
            )
        return RuleOutcome("matched", True, tuple(results), "all predicates are true")
    if any(value is True for value in values):
        return RuleOutcome("matched", True, tuple(results), "at least one predicate is true")
    if unresolved:
        return RuleOutcome(
            "abstained",
            None,
            tuple(results),
            "no predicate matched and at least one could not be evaluated safely",
        )
    return RuleOutcome("no_match", False, tuple(results), "all predicates are false")


class DeclarativeRuleChecker(Checker):
    """Adapter exposing a validated RuleSpec through the normal audit ledger."""

    def __init__(self, spec: RuleSpec, *, registry_receipt: str | None = None) -> None:
        self.spec = spec
        self.registry_receipt = registry_receipt
        self.name = f"learned_rule:{spec.rule_id}:v{spec.version}"

    def audit_eligibility(
        self,
        item: BenchmarkItem,
        root: Path | None = None,
    ) -> AuditEligibility:
        return AuditEligibility.applicable(
            "validated declarative rule is defined over canonical/raw item fields"
        )

    def check(
        self,
        item: BenchmarkItem,
        root: Path | None = None,
    ) -> Iterable[Violation]:
        outcome = evaluate_rule(self.spec, item)
        if outcome.status == "abstained":
            raise AuditAbstained(
                outcome.reason,
                details={
                    "rule_id": self.spec.rule_id,
                    "rule_version": self.spec.version,
                    "rule_sha256": self.spec.sha256,
                    "condition_results": list(outcome.condition_results),
                },
            )
        if not outcome.matched:
            return
        evidence = {
            "evidence_level": "learned_declarative_predicate",
            "proof_schema_version": "1.0",
            "rule_schema_version": self.spec.schema_version,
            "rule_id": self.spec.rule_id,
            "rule_version": self.spec.version,
            "rule_sha256": self.spec.sha256,
            "rule_complexity": self.spec.complexity,
            "condition_results": list(outcome.condition_results),
            "registry_receipt": self.registry_receipt,
            # Generated predicates never grant themselves objective authority.
            "automatic_confirmation_authority": False,
        }
        yield _violation(
            item,
            self.spec.defect_type,
            self.spec.confidence,
            self.spec.message,
            evidence,
            review_only=True,
            repair=self.spec.repair or None,
            method="learned_declarative_rule",
        )


def _evaluate_predicate(
    predicate: Predicate,
    item: BenchmarkItem,
) -> dict[str, Any]:
    left = _resolve_operand(predicate.left.source, predicate.left.path, item)
    left = _apply_transforms(left, predicate.left.transforms)
    if predicate.right_operand is not None:
        right = _resolve_operand(
            predicate.right_operand.source,
            predicate.right_operand.path,
            item,
        )
        right = _apply_transforms(right, predicate.right_operand.transforms)
    elif predicate.has_right_literal:
        right = predicate.right_literal
    else:
        right = None
    result = _compare(predicate.operator, left, right)
    return {
        "operator": predicate.operator,
        "left": _evidence_value(left),
        "right": _evidence_value(right) if predicate.operator not in {
            "is_missing",
            "is_present",
            "is_empty",
            "is_nonempty",
            "has_duplicates",
        } else None,
        "result": result,
    }


def _resolve_operand(
    source: str,
    path: tuple[str, ...],
    item: BenchmarkItem,
) -> Any:
    if source == "raw":
        value: Any = item.raw
    else:
        value = {
            "task": item.task,
            "context": item.context,
            "choices": item.choices,
            "gold": item.gold,
            "aliases": item.aliases,
            "output_contract": item.output_contract,
            "evaluator": item.evaluator,
            "metadata": item.metadata,
        }
    for segment in path:
        if isinstance(value, Mapping) and segment in value:
            value = value[segment]
        else:
            return _MISSING
    return value if _value_within_budget(value) else _UNRESOLVED


def _apply_transforms(value: Any, transforms: tuple[str, ...]) -> Any:
    if value is _MISSING or value is _UNRESOLVED:
        return value
    current = value
    for transform in transforms:
        try:
            if transform == "parse_jsonish":
                if isinstance(current, str):
                    current = json.loads(current)
            elif transform == "strip":
                if not isinstance(current, str):
                    return _UNRESOLVED
                current = current.strip()
            elif transform == "casefold":
                if not isinstance(current, str):
                    return _UNRESOLVED
                current = current.casefold()
            elif transform == "normalize_space":
                if not isinstance(current, str):
                    return _UNRESOLVED
                current = " ".join(current.split())
            elif transform == "length":
                if not isinstance(current, (str, list, tuple, dict, set, frozenset)):
                    return _UNRESOLVED
                current = len(current)
            elif transform == "unique_count":
                if not isinstance(current, (list, tuple)):
                    return _UNRESOLVED
                current = len({_stable_member(child) for child in current})
            elif transform == "as_set":
                if not isinstance(current, (list, tuple, set, frozenset)):
                    return _UNRESOLVED
                current = frozenset(_stable_member(child) for child in current)
            else:  # RuleSpec validation makes this unreachable.
                return _UNRESOLVED
        except (TypeError, ValueError, json.JSONDecodeError, OverflowError):
            return _UNRESOLVED
        if not _value_within_budget(current):
            return _UNRESOLVED
    return current


def _compare(operator: str, left: Any, right: Any) -> bool | None:
    if operator == "is_missing":
        return _is_missing_value(left)
    if operator == "is_present":
        return left is not _UNRESOLVED and not _is_missing_value(left)
    if left is _UNRESOLVED or right is _UNRESOLVED:
        return None
    if operator == "is_empty":
        return False if left is _MISSING else _safe_empty(left)
    if operator == "is_nonempty":
        empty = False if left is _MISSING else _safe_empty(left)
        return None if empty is None else not empty
    if operator == "has_duplicates":
        if left is _MISSING:
            return False
        if not isinstance(left, (list, tuple)):
            return None
        return len(left) != len({_stable_member(child) for child in left})
    if left is _MISSING or right is _MISSING:
        return False
    try:
        if operator == "eq":
            return _safe_equal(left, right)
        if operator == "ne":
            return not _safe_equal(left, right)
        if operator == "contains":
            return _safe_contains(left, right)
        if operator == "not_contains":
            contained = _safe_contains(left, right)
            return None if contained is None else not contained
        if operator in {"lt", "le", "gt", "ge"}:
            if (
                not isinstance(left, (int, float))
                or isinstance(left, bool)
                or not isinstance(right, (int, float))
                or isinstance(right, bool)
                or not math.isfinite(float(left))
                or not math.isfinite(float(right))
            ):
                return None
            return {
                "lt": left < right,
                "le": left <= right,
                "gt": left > right,
                "ge": left >= right,
            }[operator]
        left_set = _coerce_set(left)
        right_set = _coerce_set(right)
        if left_set is None or right_set is None:
            return None
        if operator == "subset":
            return left_set <= right_set
        if operator == "not_subset":
            return not left_set <= right_set
        if operator == "intersects":
            return bool(left_set & right_set)
        if operator == "disjoint":
            return left_set.isdisjoint(right_set)
    except (TypeError, ValueError, OverflowError):
        return None
    return None


def _is_missing_value(value: Any) -> bool:
    return value is _MISSING or value is None or value == "" or value == [] or value == {}


def _safe_empty(value: Any) -> bool | None:
    if value is None:
        return True
    if isinstance(value, (str, list, tuple, dict, set, frozenset)):
        return len(value) == 0
    return None


def _safe_equal(left: Any, right: Any) -> bool:
    if isinstance(left, frozenset) or isinstance(right, frozenset):
        return left == right
    return canonical_json(left) == canonical_json(right)


def _safe_contains(container: Any, member: Any) -> bool | None:
    if isinstance(container, str) and isinstance(member, str):
        return member in container
    if isinstance(container, Mapping):
        return member in container
    if isinstance(container, (list, tuple, set, frozenset)):
        needle = _stable_member(member)
        return needle in {_stable_member(child) for child in container}
    return None


def _coerce_set(value: Any) -> frozenset[str] | None:
    if isinstance(value, frozenset):
        return value
    if not isinstance(value, (list, tuple, set)):
        return None
    return frozenset(_stable_member(child) for child in value)


def _stable_member(value: Any) -> str:
    return canonical_json(value)


def _value_within_budget(value: Any, *, depth: int = 0) -> bool:
    if depth > MAX_VALUE_DEPTH:
        return False
    if isinstance(value, str):
        return len(value.encode("utf-8", errors="replace")) <= MAX_OPERAND_BYTES
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, (list, tuple, set, frozenset)):
        return len(value) <= MAX_COLLECTION_ITEMS and all(
            _value_within_budget(child, depth=depth + 1) for child in value
        )
    if isinstance(value, Mapping):
        return len(value) <= MAX_COLLECTION_ITEMS and all(
            isinstance(key, str)
            and _value_within_budget(child, depth=depth + 1)
            for key, child in value.items()
        )
    return False


def _evidence_value(value: Any) -> dict[str, Any]:
    if value is _MISSING:
        return {"status": "missing"}
    if value is _UNRESOLVED:
        return {"status": "unresolved"}
    try:
        text = canonical_json(value)
    except (TypeError, ValueError, OverflowError):
        return {"status": "unresolved"}
    return {
        "status": "observed",
        "sha256": canonical_sha256(value),
        "preview": text[:500],
        "truncated": len(text) > 500,
    }
