"""Detect reference parameters whose value the benchmark's own evaluator ignores.

``EvaluatorMutationChecker`` mutates a scalar gold answer and replays BenchCore's
*declared* evaluator model. This checker answers a different question for
benchmarks whose reference is a structured call: it corrupts one parameter value
at a time and replays the benchmark's *own* evaluator code. A corrupted value the
evaluator still accepts is proof that the parameter is not scored, so any item
that claims to test it does not.

The evaluator invocation is injected, because running it is benchmark specific;
this module stays free of any one benchmark's layout.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

from .checkers import Checker, _violation
from .coverage import AuditEligibility
from .schema import BenchmarkItem, Violation

# (accepted, evaluator_detail) for a candidate solver answer against the item.
EvaluatorReplay = Callable[[BenchmarkItem, dict[str, Any]], tuple[bool, Any]]

MUTATION_SENTINEL = "BENCHCORE_MUTATED_VALUE"
NUMERIC_OFFSET = 999


def _enum_alternative(spec: Any, value: Any) -> Any | None:
    if not isinstance(spec, dict) or not isinstance(spec.get("enum"), list):
        return None
    for candidate in spec["enum"]:
        if candidate != value:
            return candidate
    return None


def corrupt(value: Any, spec: Any = None) -> tuple[str, Any] | None:
    """A same-typed value the item's own wording could never justify."""
    if isinstance(value, bool):
        return "boolean_negated", not value
    if isinstance(value, (int, float)):
        return "numeric_offset", value + NUMERIC_OFFSET
    if isinstance(value, str):
        alternative = _enum_alternative(spec, value)
        if alternative is not None:
            return "enum_swapped", alternative
        return "string_replaced", MUTATION_SENTINEL
    return None


def _property_spec(spec: Any, key: str) -> Any:
    if not isinstance(spec, dict):
        return None
    properties = spec.get("properties")
    return properties.get(key) if isinstance(properties, dict) else None


def scalar_positions(value: Any, spec: Any = None, path: str = "") -> list[tuple[str, Any, Any]]:
    """Every scalar leaf as (json path, value, declared schema for that leaf)."""
    if isinstance(value, dict):
        found: list[tuple[str, Any, Any]] = []
        for key, child in value.items():
            found.extend(scalar_positions(child, _property_spec(spec, key), f"{path}.{key}"))
        return found
    if isinstance(value, list):
        items_spec = spec.get("items") if isinstance(spec, dict) else None
        found = []
        for index, child in enumerate(value):
            found.extend(scalar_positions(child, items_spec, f"{path}[{index}]"))
        return found
    if isinstance(value, (str, int, float, bool)):
        return [(path, value, spec)]
    return []


def replace_at(payload: Any, path: list[str | int], new_value: Any) -> Any:
    """Copy ``payload`` with the leaf at ``path`` replaced."""
    if not path:
        return new_value
    head, rest = path[0], path[1:]
    if isinstance(head, int):
        copied = list(payload)
        copied[head] = replace_at(copied[head], rest, new_value)
        return copied
    copied = dict(payload)
    copied[head] = replace_at(copied[head], rest, new_value)
    return copied


def parse_path(path: str) -> list[str | int]:
    parts: list[str | int] = []
    for chunk in path.lstrip(".").split("."):
        name, _, indexes = chunk.partition("[")
        if name:
            parts.append(name)
        for index in indexes.rstrip("]").split("][") if indexes else []:
            parts.append(int(index))
    return parts


class ReferenceEvaluatorMutationChecker(Checker):
    """Report reference parameters the benchmark's evaluator does not score."""

    name = "reference_evaluator_mutation"

    def __init__(self, replay: EvaluatorReplay, *, evaluator_sha256: str) -> None:
        self.replay = replay
        self.evaluator_sha256 = evaluator_sha256

    def _reference(self, item: BenchmarkItem) -> dict[str, Any] | None:
        value = item.raw.get("reference_solution") if isinstance(item.raw, dict) else None
        return value if isinstance(value, dict) else None

    def _schema_index(self, item: BenchmarkItem) -> dict[str, Any]:
        index: dict[str, Any] = {}
        for value in item.context.values():
            if not isinstance(value, list):
                continue
            for entry in value:
                body = entry.get("function") if isinstance(entry, dict) and isinstance(
                    entry.get("function"), dict) else entry
                if isinstance(body, dict) and body.get("name"):
                    index.setdefault(str(body["name"]), body.get("parameters"))
        return index

    def audit_eligibility(self, item: BenchmarkItem, root: Path | None = None) -> AuditEligibility:
        if self._reference(item) is None:
            return AuditEligibility.not_applicable("no structured reference_solution")
        return AuditEligibility.applicable("structured reference can be mutated per parameter")

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        reference = self._reference(item)
        if reference is None:
            return
        accepted, detail = self.replay(item, reference)
        if not accepted:
            # The reference does not pass its own evaluator; that is a different
            # defect, reported elsewhere, and it makes mutation results
            # uninterpretable here.
            return
        schemas = self._schema_index(item)
        unscored: list[dict[str, Any]] = []
        for call_name, arguments in reference.items():
            if not isinstance(arguments, dict):
                continue
            spec = schemas.get(str(call_name).rstrip("_0123456789")) or schemas.get(str(call_name))
            for path, value, leaf_spec in scalar_positions(arguments, spec):
                mutation = corrupt(value, leaf_spec)
                if mutation is None:
                    continue
                kind, mutated = mutation
                variant = dict(reference)
                variant[call_name] = replace_at(arguments, parse_path(path), mutated)
                survived, verdict = self.replay(item, variant)
                if survived:
                    unscored.append({
                        "parameter_path": f"{call_name}{path}",
                        "mutation": kind,
                        "original_value": value,
                        "mutated_value": mutated,
                        "evaluator_accepted_mutation": True,
                        "evaluator_detail": verdict,
                    })
        if not unscored:
            return
        yield _violation(
            item,
            "evaluator_mutation_survived",
            "The benchmark's own evaluator accepts corrupted values for "
            f"{len(unscored)} reference parameter(s), so those parameters are not scored.",
            {
                "proof_schema_version": "reference-evaluator-mutation-v1",
                "unscored_parameters": unscored,
                "baseline_reference_accepted": True,
                "baseline_evaluator_detail": detail,
                "evaluator_sha256": self.evaluator_sha256,
            },
            severity="major",
            method="reference_evaluator_mutation",
        )
