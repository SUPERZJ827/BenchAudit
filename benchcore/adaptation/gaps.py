"""Typed component-gap analysis for unseen benchmark packages."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import AdapterSpec
from .profile import SchemaProfile


@dataclass(frozen=True)
class ComponentGap:
    component: str
    status: str
    required_targets: tuple[str, ...]
    resolved_targets: tuple[str, ...]
    resolution_channel: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GapAnalysis:
    family: str
    schema_fingerprint: str
    components: tuple[ComponentGap, ...]
    resolved: int
    unresolved: int
    requires_trusted_plugin: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "schema_fingerprint": self.schema_fingerprint,
            "components": [component.to_dict() for component in self.components],
            "summary": {
                "resolved": self.resolved,
                "unresolved": self.unresolved,
                "requires_trusted_plugin": self.requires_trusted_plugin,
            },
        }


_DECLARATIVE_REQUIREMENTS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "generic": (
        ("canonical_task", ("task",)),
    ),
    "workspacebench": (
        ("canonical_task", ("task",)),
        ("record_identity", ("item_id",)),
        ("evaluator_protocol", ("evaluator", "rubrics")),
        ("output_contract", ("output_contract", "output_files")),
        ("attachment_manifest", ("context", "data_manifest")),
        ("dependency_graph", ("file_dep_graph",)),
        ("materialized_inputs", ("input_files",)),
    ),
    "swebench": (
        ("canonical_task", ("task",)),
        ("repository_identity", ("repo", "base_commit")),
        ("reference_patch", ("patch",)),
        ("test_protocol", ("test_patch",)),
    ),
    "terminalbench": (
        ("canonical_task", ("task",)),
        ("environment_protocol", ("environment",)),
        ("command_protocol", ("commands",)),
        ("test_protocol", ("tests",)),
    ),
}

_PLUGIN_COMPONENTS = (
    "record_source_loader",
    "attachment_resolver",
    "candidate_materializer",
    "harness_result_parser",
    "trace_parser",
)


def analyze_component_gaps(
    profile: SchemaProfile,
    *,
    family: str,
    spec: AdapterSpec | None = None,
) -> GapAnalysis:
    """Describe what declarative adaptation solved and what still needs code.

    Plugin components are never marked resolved merely because similarly named
    fields exist: their correctness involves filesystem or execution behavior
    that this non-executable DSL intentionally cannot implement.
    """

    targets = spec.targets if spec is not None else frozenset()
    components: list[ComponentGap] = []
    for component, required in _DECLARATIVE_REQUIREMENTS.get(
        family,
        _DECLARATIVE_REQUIREMENTS["generic"],
    ):
        resolved_targets = tuple(target for target in required if target in targets)
        passed = len(resolved_targets) == len(required)
        components.append(ComponentGap(
            component=component,
            status="resolved" if passed else "unresolved",
            required_targets=required,
            resolved_targets=resolved_targets,
            resolution_channel="typed_adapter_dsl",
            reason=(
                "all registered typed outputs are provided"
                if passed
                else "missing typed outputs: "
                + ", ".join(target for target in required if target not in targets)
            ),
        ))
    for component in _PLUGIN_COMPONENTS:
        components.append(ComponentGap(
            component=component,
            status="requires_trusted_plugin",
            required_targets=(),
            resolved_targets=(),
            resolution_channel="sandboxed_reviewed_plugin",
            reason=(
                "filesystem/execution semantics cannot be supplied by a generated "
                "declarative field adapter"
            ),
        ))
    return GapAnalysis(
        family=family,
        schema_fingerprint=profile.fingerprint,
        components=tuple(components),
        resolved=sum(component.status == "resolved" for component in components),
        unresolved=sum(component.status == "unresolved" for component in components),
        requires_trusted_plugin=sum(
            component.status == "requires_trusted_plugin" for component in components
        ),
    )
