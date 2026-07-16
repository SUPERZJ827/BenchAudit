"""Independent conformance gates for generated benchmark adapters."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from .apply import AdaptationResult, adapt_rows
from .models import AdapterSpec, CORE_TARGETS, allowed_targets, canonical_json


FAMILY_REQUIRED_TARGETS: dict[str, frozenset[str]] = {
    "generic": frozenset({"task"}),
    "workspacebench": frozenset({
        "item_id", "task", "context", "output_contract", "evaluator",
    }),
    "swebench": frozenset({"item_id", "task", "repo", "base_commit", "patch"}),
    "terminalbench": frozenset({"item_id", "task", "environment", "tests"}),
}


@dataclass(frozen=True)
class AdapterGatePolicy:
    schema_version: str = "benchcore-adapter-gate-v1"
    min_rows: int = 20
    min_complete_rate: float = 1.0
    min_required_binding_coverage: float = 1.0
    min_task_text_rate: float = 0.99
    min_item_id_unique_rate: float = 0.99
    min_reference_field_accuracy: float = 0.99
    min_reference_row_accuracy: float = 0.99
    min_reference_field_wilson_lower: float = 0.95
    required_targets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.required_targets, list):
            object.__setattr__(self, "required_targets", tuple(self.required_targets))
        if (
            not isinstance(self.required_targets, tuple)
            or any(not isinstance(value, str) for value in self.required_targets)
            or len(self.required_targets) != len(set(self.required_targets))
        ):
            raise ValueError("required_targets must be a unique string sequence")
        globally_allowed = set().union(*(
            allowed_targets(family)
            for family in ("generic", "workspacebench", "swebench", "terminalbench")
        ))
        unknown = set(self.required_targets) - globally_allowed
        if unknown:
            raise ValueError(f"required_targets contains unknown targets: {sorted(unknown)}")
        if not isinstance(self.min_rows, int) or isinstance(self.min_rows, bool):
            raise ValueError("min_rows must be an integer")
        if self.min_rows < 1:
            raise ValueError("min_rows must be positive")
        for name in (
            "min_complete_rate",
            "min_required_binding_coverage",
            "min_task_text_rate",
            "min_item_id_unique_rate",
            "min_reference_field_accuracy",
            "min_reference_row_accuracy",
            "min_reference_field_wilson_lower",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} must be numeric")
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between zero and one")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReferenceMetrics:
    rows: int
    expected_targets: tuple[str, ...]
    mapped_targets: tuple[str, ...]
    target_coverage: float
    compared_fields: int
    equal_fields: int
    equal_rows: int
    field_accuracy: float
    row_accuracy: float
    field_accuracy_wilson95: tuple[float | None, float | None]
    per_target: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdapterEvaluation:
    schema_version: str
    adapter: dict[str, Any]
    adapter_sha256: str
    policy: dict[str, Any]
    adaptation: dict[str, Any]
    reference: ReferenceMetrics | None
    structural_passed: bool
    accepted: bool
    evidence_tier: str
    activation_mode: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter": self.adapter,
            "adapter_sha256": self.adapter_sha256,
            "policy": self.policy,
            "adaptation": self.adaptation,
            "reference": self.reference.to_dict() if self.reference else None,
            "structural_passed": self.structural_passed,
            "accepted": self.accepted,
            "evidence_tier": self.evidence_tier,
            "activation_mode": self.activation_mode,
            "reasons": list(self.reasons),
            "semantics": {
                "active_shadow": (
                    "structurally conformant but semantic field identity is not "
                    "independently proven"
                ),
                "active_verified": (
                    "structurally conformant and equivalent across the complete "
                    "external reference target manifest"
                ),
            },
        }


def evaluate_adapter(
    spec: AdapterSpec,
    rows: list[dict[str, Any]],
    *,
    references: list[dict[str, Any]] | None = None,
    policy: AdapterGatePolicy | None = None,
) -> AdapterEvaluation:
    """Evaluate a candidate; references must be an external sidecar.

    Without references the adapter may pass only as ``active_shadow``.  This is
    intentional: schema/type invariants cannot prove that an opaque text field
    is semantically the benchmark task rather than a rationale or distractor.
    """

    policy = policy or AdapterGatePolicy()
    adaptation = adapt_rows(
        rows,
        spec,
        strict_fingerprint=True,
        strict_rows=False,
    )
    reasons = _structural_reasons(spec, adaptation, policy)
    adapted_rows = list(adaptation.rows)
    reasons.extend(_semantic_shape_reasons(spec, adapted_rows, policy))
    structural_passed = not reasons

    reference_metrics: ReferenceMetrics | None = None
    if references is not None:
        contract_reasons = _reference_contract_reasons(spec, adapted_rows, references)
        reasons.extend(contract_reasons)
        if not contract_reasons:
            try:
                reference_metrics = compare_references(
                    spec,
                    adapted_rows,
                    references,
                )
            except Exception as exc:  # noqa: BLE001 - reference fails closed
                reasons.append(
                    "reference comparison failed closed: "
                    f"{type(exc).__name__}: {exc}"
                )
        if (
            reference_metrics is not None
            and reference_metrics.field_accuracy < policy.min_reference_field_accuracy
        ):
            reasons.append(
                "reference field accuracy "
                f"{reference_metrics.field_accuracy:.6f} is below "
                f"{policy.min_reference_field_accuracy:.6f}"
            )
        if (
            reference_metrics is not None
            and reference_metrics.row_accuracy < policy.min_reference_row_accuracy
        ):
            reasons.append(
                "reference row accuracy "
                f"{reference_metrics.row_accuracy:.6f} is below "
                f"{policy.min_reference_row_accuracy:.6f}"
            )
        lower = (
            reference_metrics.field_accuracy_wilson95[0]
            if reference_metrics is not None
            else None
        )
        if (
            reference_metrics is not None
            and (lower is None or lower < policy.min_reference_field_wilson_lower)
        ):
            reasons.append(
                "reference field-accuracy Wilson lower bound "
                f"{lower!r} is below {policy.min_reference_field_wilson_lower:.6f}"
            )

    accepted = not reasons
    if references is None:
        evidence_tier = "structural_only"
        activation_mode = "active_shadow" if accepted else "quarantined"
    else:
        evidence_tier = "reference_equivalent" if accepted else "reference_failed"
        activation_mode = "active_verified" if accepted else "quarantined"
    return AdapterEvaluation(
        schema_version="benchcore-adapter-evaluation-v1",
        adapter=spec.to_dict(),
        adapter_sha256=spec.sha256,
        policy=policy.to_dict(),
        adaptation=adaptation.to_dict(include_rows=False),
        reference=reference_metrics,
        structural_passed=structural_passed,
        accepted=accepted,
        evidence_tier=evidence_tier,
        activation_mode=activation_mode,
        reasons=tuple(reasons),
    )


def compare_references(
    spec: AdapterSpec,
    adapted_rows: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> ReferenceMetrics:
    contract_reasons = _reference_contract_reasons(spec, adapted_rows, references)
    if contract_reasons:
        raise ValueError("; ".join(contract_reasons))
    targets = sorted(references[0])
    compared = equal = equal_rows = 0
    target_counts = {
        target: {"compared": 0, "equal": 0, "accuracy": 0.0}
        for target in targets
    }
    for adapted, reference in zip(adapted_rows, references, strict=True):
        row_equal = True
        row_compared = 0
        for target in targets:
            # Absence in a sidecar is not treated as a convenient negative;
            # every generated target must be independently specified.
            if target not in reference:
                value_equal = False
            else:
                value_equal = canonical_json(adapted.get(target)) == canonical_json(
                    reference[target]
                )
            compared += 1
            row_compared += 1
            target_counts[target]["compared"] += 1
            if value_equal:
                equal += 1
                target_counts[target]["equal"] += 1
            else:
                row_equal = False
        if row_compared and row_equal:
            equal_rows += 1
    for counts in target_counts.values():
        counts["accuracy"] = _rate(counts["equal"], counts["compared"])
    return ReferenceMetrics(
        rows=len(adapted_rows),
        expected_targets=tuple(targets),
        mapped_targets=tuple(sorted(spec.targets)),
        target_coverage=_rate(len(spec.targets & set(targets)), len(targets)),
        compared_fields=compared,
        equal_fields=equal,
        equal_rows=equal_rows,
        field_accuracy=_rate(equal, compared),
        row_accuracy=_rate(equal_rows, len(adapted_rows)),
        field_accuracy_wilson95=wilson_interval(equal, compared),
        per_target=target_counts,
    )


def _reference_contract_reasons(
    spec: AdapterSpec,
    adapted_rows: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> list[str]:
    """Require a complete, stable canonical target manifest in the sidecar."""

    reasons: list[str] = []
    if len(adapted_rows) != len(references):
        return [
            "reference row count must equal source row count; positional "
            "truncation or implicit joins are forbidden"
        ]
    if not references:
        return ["external reference sidecar must contain at least one row"]
    invalid_rows = [
        index for index, row in enumerate(references) if not isinstance(row, dict)
    ]
    if invalid_rows:
        return [
            "each external reference row must be an object; invalid rows: "
            + ", ".join(str(index) for index in invalid_rows[:10])
        ]

    expected = set(references[0])
    registered = allowed_targets(spec.family)
    unknown = expected - registered
    if unknown:
        reasons.append(
            "reference sidecar contains unregistered targets: "
            + ", ".join(sorted(unknown))
        )
    inconsistent = [
        index for index, row in enumerate(references)
        if set(row) != expected
    ]
    if inconsistent:
        reasons.append(
            "reference target manifest differs across rows: "
            + ", ".join(str(index) for index in inconsistent[:10])
        )
    missing = expected - spec.targets
    if missing:
        reasons.append(
            "adapter omits targets declared by the external reference: "
            + ", ".join(sorted(missing))
        )
    unreferenced = spec.targets - expected
    if unreferenced:
        reasons.append(
            "adapter declares targets absent from the external reference: "
            + ", ".join(sorted(unreferenced))
        )
    return reasons


def _structural_reasons(
    spec: AdapterSpec,
    result: AdaptationResult,
    policy: AdapterGatePolicy,
) -> list[str]:
    reasons: list[str] = []
    required_targets = FAMILY_REQUIRED_TARGETS.get(
        spec.family,
        FAMILY_REQUIRED_TARGETS["generic"],
    ) | frozenset(policy.required_targets)
    invalid_policy_targets = required_targets - allowed_targets(spec.family)
    if invalid_policy_targets:
        reasons.append(
            "gate policy requires targets unavailable for this family: "
            + ", ".join(sorted(invalid_policy_targets))
        )
    missing_targets = required_targets - spec.targets
    if missing_targets:
        reasons.append(
            "adapter is missing family-required targets: "
            + ", ".join(sorted(missing_targets))
        )
    if result.total_rows < policy.min_rows:
        reasons.append(
            f"row count {result.total_rows} is below minimum {policy.min_rows}"
        )
    if result.complete_rate < policy.min_complete_rate:
        reasons.append(
            f"complete rate {result.complete_rate:.6f} is below "
            f"{policy.min_complete_rate:.6f}"
        )
    for binding in spec.bindings:
        if not binding.required:
            continue
        coverage = result.binding_coverage.get(binding.target, 0.0)
        if coverage < policy.min_required_binding_coverage:
            reasons.append(
                f"required target {binding.target!r} coverage {coverage:.6f} "
                f"is below {policy.min_required_binding_coverage:.6f}"
            )
    return reasons


def _semantic_shape_reasons(
    spec: AdapterSpec,
    rows: list[dict[str, Any]],
    policy: AdapterGatePolicy,
) -> list[str]:
    reasons: list[str] = []
    tasks = [row.get("task") for row in rows]
    task_text = sum(isinstance(value, str) and bool(value.strip()) for value in tasks)
    task_rate = _rate(task_text, len(rows))
    if task_rate < policy.min_task_text_rate:
        reasons.append(
            f"task text rate {task_rate:.6f} is below {policy.min_task_text_rate:.6f}"
        )
    if "item_id" in spec.targets:
        values = [row.get("item_id") for row in rows]
        usable = [
            canonical_json(value)
            for value in values
            if value not in (None, "", [], {})
        ]
        unique_rate = _rate(len(set(usable)), len(rows))
        if unique_rate < policy.min_item_id_unique_rate:
            reasons.append(
                f"item_id unique rate {unique_rate:.6f} is below "
                f"{policy.min_item_id_unique_rate:.6f}"
            )
    for target in (spec.targets & CORE_TARGETS) - {"task", "item_id"}:
        invalid = sum(not _target_type_compatible(target, row.get(target)) for row in rows)
        if invalid:
            reasons.append(
                f"target {target!r} has {invalid}/{len(rows)} type-incompatible values"
            )
    if spec.family == "workspacebench":
        evaluator_valid = sum(
            isinstance(row.get("evaluator"), dict)
            and isinstance(row["evaluator"].get("rubrics"), list)
            and bool(row["evaluator"]["rubrics"])
            for row in rows
        )
        if _rate(evaluator_valid, len(rows)) < 0.99:
            reasons.append(
                "Workspace evaluator must contain a non-empty rubrics list on at "
                "least 99% of rows"
            )
        contract_valid = sum(
            isinstance(row.get("output_contract"), dict)
            and isinstance(row["output_contract"].get("required_files"), list)
            for row in rows
        )
        if _rate(contract_valid, len(rows)) < 0.99:
            reasons.append(
                "Workspace output_contract must contain required_files list on at "
                "least 99% of rows"
            )
        if "metadata" in spec.targets:
            required_metadata_keys = {"absolute_id", "language", "persona", "task_diff"}
            metadata_valid = sum(
                isinstance(row.get("metadata"), dict)
                and required_metadata_keys <= set(row["metadata"])
                for row in rows
            )
            if _rate(metadata_valid, len(rows)) < 0.99:
                reasons.append(
                    "Workspace metadata must expose canonical keys absolute_id, "
                    "language, persona, and task_diff on at least 99% of rows"
                )
        item_ids = [row.get("item_id") for row in rows]
        canonical_id_rate = _rate(
            sum(
                isinstance(value, str) and value.startswith("workspacebench-")
                for value in item_ids
            ),
            len(rows),
        )
        if canonical_id_rate < 0.99:
            reasons.append(
                "Workspace item_id must use the canonical workspacebench- prefix "
                "on at least 99% of rows"
            )
        consistency_failures: Counter[str] = Counter()
        for row in rows:
            consistency_failures.update(_workspace_consistency_failures(row))
        for failure, count in sorted(consistency_failures.items()):
            if _rate(count, len(rows)) > 0.01:
                reasons.append(
                    f"Workspace consistency failure on {count}/{len(rows)} rows: "
                    f"{failure}"
                )
    return reasons


def _workspace_components_consistent(row: dict[str, Any]) -> bool:
    """Ground composite fields in independently mapped typed extensions."""

    return not _workspace_consistency_failures(row)


def _workspace_consistency_failures(row: dict[str, Any]) -> tuple[str, ...]:
    failures: list[str] = []

    context = row.get("context")
    evaluator = row.get("evaluator")
    contract = row.get("output_contract")
    if not isinstance(context, dict) or not isinstance(evaluator, dict) or not isinstance(contract, dict):
        return ("context/evaluator/output_contract must all be objects",)
    comparisons = (
        (context, "data_manifest", row, "data_manifest"),
        (context, "file_dep_graph", row, "file_dep_graph"),
        (context, "input_files", row, "input_files"),
        (evaluator, "rubrics", row, "rubrics"),
        (evaluator, "rubric_types", row, "rubric_types"),
        (contract, "required_files", row, "output_files"),
    )
    for left, left_key, right, right_key in comparisons:
        # If an extension is deliberately absent from a smaller Workspace
        # profile, the family minimum can still run.  Once either side is
        # mapped, however, both sides must be present and equal.
        if right_key not in right:
            continue
        if left_key not in left:
            failures.append(f"{left_key} is absent from its canonical composite")
            continue
        if canonical_json(_parse_jsonish(left[left_key])) != canonical_json(
            _parse_jsonish(right[right_key])
        ):
            failures.append(
                f"canonical composite {left_key} does not equal extension {right_key}"
            )
    shapes = {
        "rubrics": lambda value: isinstance(value, list) and all(isinstance(x, str) for x in value),
        "rubric_types": lambda value: isinstance(value, list) and all(isinstance(x, str) for x in value),
        "output_files": lambda value: isinstance(value, list) and all(isinstance(x, str) for x in value),
        "input_files": lambda value: isinstance(value, list) and all(isinstance(x, str) for x in value),
        "data_manifest": lambda value: isinstance(value, list) and all(isinstance(x, dict) for x in value),
        "file_dep_graph": lambda value: isinstance(value, list) and all(isinstance(x, dict) for x in value),
        "tested_capabilities": lambda value: isinstance(value, list) and all(isinstance(x, str) for x in value),
    }
    for target, predicate in shapes.items():
        if target in row and not predicate(_parse_jsonish(row[target])):
            failures.append(f"extension {target} has an incompatible structural type")
    return tuple(sorted(set(failures)))


def _parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _target_type_compatible(target: str, value: Any) -> bool:
    if value is None:
        return True
    if target in {"context", "metadata", "evaluator"}:
        return isinstance(value, dict)
    if target in {"choices", "aliases"}:
        return isinstance(value, list)
    return True


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def wilson_interval(
    successes: int,
    total: int,
    *,
    z: float = 1.959963984540054,
) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)
