"""Deterministic verifier routing for previously unseen benchmark schemas.

This is deliberately a *routing* layer, not an LLM deciding what counts as a
proof.  It inspects only canonical fields and selects the strongest verifier
family that is plausibly applicable.  If the required verifier is unavailable,
the route says so and semantic agents remain review-only.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .schema import BenchmarkItem


@dataclass(frozen=True)
class VerifierRoute:
    item_id: str
    route: str
    confirmation_boundary: str
    status: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def route_verifier(item: BenchmarkItem) -> VerifierRoute:
    """Choose a conservative evidence route from structured item signals."""
    raw = item.raw if isinstance(item.raw, dict) else {}
    evaluator = item.evaluator if isinstance(item.evaluator, dict) else {}
    raw_keys = {str(key).casefold() for key in raw}
    task = str(item.task or "")
    contract = str(item.output_contract or "")

    if (
        {"rubrics", "rubric_types", "file_dep_graph", "tested_capabilities"}
        & raw_keys
        or "workspace" in contract.casefold()
        or any(key in evaluator for key in ("rubrics", "rubric_types", "output_files"))
    ):
        return VerifierRoute(
            item.item_id,
            "workspace_objective_certificate_then_grounded_review",
            "Only a production-visible deterministic certificate may confirm; "
            "citation/agent judgments remain review-only.",
            "available",
            "Workspace/rubric structure detected from canonical fields.",
        )
    if isinstance(evaluator.get("code_context"), str) and str(item.gold or "").strip():
        return VerifierRoute(
            item.item_id,
            "executable_harness_with_external_transcript_attestation",
            "A separate attester and verifier must bind the exact execution "
            "transcript before promotion; otherwise review-only.",
            "requires_external_attestation",
            "Reference code and executable evaluator context are both present.",
        )
    table_signals = ("table", "dataframe", "spreadsheet", "csv", "row", "column")
    if any(token in (task + " " + contract).casefold() for token in table_signals):
        return VerifierRoute(
            item.item_id,
            "table_recomputation_and_constraint_check",
            "Recomputed values/constraints can confirm only when all source "
            "cells and transformation assumptions are pinned.",
            "available_if_structured_inputs_present",
            "Table-like task language detected; route avoids free-form answer voting.",
        )
    math_signals = (
        r"\b(prove|theorem|lemma|integral|derivative|equation|inequality)\b",
        r"[=≤≥≠∫∑√]",
    )
    if any(re.search(pattern, task, flags=re.I) for pattern in math_signals):
        return VerifierRoute(
            item.item_id,
            "symbolic_or_formal_math_verifier",
            "Symbolic replay/SMT/Lean must establish the claimed statement; "
            "agent agreement alone is review-only.",
            "adapter_required",
            "Math/formal-language signal detected but no universal formal adapter is assumed.",
        )
    return VerifierRoute(
        item.item_id,
        "multi_agent_grounded_review",
        "No objective verifier is inferred; preserve all semantic findings at review tier.",
        "review_only",
        "No sufficiently specific deterministic verifier route was inferred.",
    )


def route_verifiers(items: Iterable[BenchmarkItem], limit: int = 100) -> list[VerifierRoute]:
    """Route a bounded deterministic sample without calling a model."""
    return [route_verifier(item) for _, item in zip(range(limit), items)]
