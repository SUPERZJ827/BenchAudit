"""Deterministic verifier routing for previously unseen benchmark schemas.

This is deliberately a *routing* layer, not an LLM deciding what counts as a
proof.  It inspects only canonical fields and selects the strongest verifier
family that is plausibly applicable.  If the required verifier is unavailable,
the route says so and semantic agents remain review-only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .counterexample_validation import verification_capabilities
from .schema import BenchmarkItem


@dataclass(frozen=True)
class VerifierRoute:
    item_id: str
    route: str
    confirmation_boundary: str
    status: str
    reason: str
    secondary_routes: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def route_verifier(item: BenchmarkItem) -> VerifierRoute:
    """Choose a conservative evidence route from structured item signals."""
    capabilities = verification_capabilities(item)
    primary = capabilities[0]
    secondary = tuple(route.verifier for route in capabilities[1:])

    if primary.family == "workspace":
        return VerifierRoute(
            item.item_id,
            "workspace_objective_certificate_then_grounded_review",
            "Only a production-visible deterministic certificate may confirm; "
            "citation/agent judgments remain review-only.",
            "available",
            "Workspace/rubric structure detected from canonical fields.",
            secondary,
            primary.required_evidence,
        )
    if primary.family == "code":
        return VerifierRoute(
            item.item_id,
            "executable_harness_with_external_transcript_attestation",
            "A separate attester and verifier must bind the exact execution "
            "transcript before promotion; otherwise review-only.",
            "requires_external_attestation",
            primary.reason,
            secondary,
            primary.required_evidence,
        )
    if primary.family == "table":
        return VerifierRoute(
            item.item_id,
            "table_recomputation_and_constraint_check",
            "Recomputed values/constraints can confirm only when all source "
            "cells and transformation assumptions are pinned.",
            "available_if_structured_inputs_present",
            primary.reason,
            secondary,
            primary.required_evidence,
        )
    if primary.family == "formal_math":
        return VerifierRoute(
            item.item_id,
            "symbolic_or_formal_math_verifier",
            "Symbolic replay/SMT/Lean must establish the claimed statement; "
            "agent agreement alone is review-only.",
            "adapter_required",
            primary.reason,
            secondary,
            primary.required_evidence,
        )
    if primary.family == "exact_answer":
        return VerifierRoute(
            item.item_id,
            "answer_contract_counterexample_replay",
            "Modeled answer-contract probes remain review until bound to the official evaluator; "
            "official deterministic replay may confirm.",
            "available",
            primary.reason,
            secondary,
            primary.required_evidence,
        )
    return VerifierRoute(
        item.item_id,
        "multi_agent_grounded_review",
        "No objective verifier is inferred; preserve all semantic findings at review tier.",
        "review_only",
        primary.reason,
        secondary,
        primary.required_evidence,
    )


def route_verifiers(items: Iterable[BenchmarkItem], limit: int = 100) -> list[VerifierRoute]:
    """Route a bounded deterministic sample without calling a model."""
    return [route_verifier(item) for _, item in zip(range(limit), items)]
