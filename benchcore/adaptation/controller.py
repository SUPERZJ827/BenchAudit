"""Budgeted adapter synthesis with trusted feedback and one-shot reference use."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .evaluation import (
    FAMILY_REQUIRED_TARGETS,
    AdapterEvaluation,
    AdapterGatePolicy,
    evaluate_adapter,
)
from .models import AdapterSpec, canonical_sha256
from .profile import SchemaProfile
from .synthesis import AdapterSynthesizer


@dataclass(frozen=True)
class AdapterRun:
    schema_version: str
    run_id: str
    started_at_utc: str
    finished_at_utc: str
    source_schema_fingerprint: str
    source_content_sha256: str
    family: str
    policy: dict[str, Any]
    budget: dict[str, int]
    rounds: tuple[dict[str, Any], ...]
    selected_adapter: dict[str, Any] | None
    final_evaluation: AdapterEvaluation | None
    status: str
    stop_reason: str
    reference_attempts: int
    lineage_closed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "source_schema_fingerprint": self.source_schema_fingerprint,
            "source_content_sha256": self.source_content_sha256,
            "family": self.family,
            "policy": self.policy,
            "budget": self.budget,
            "rounds": list(self.rounds),
            "selected_adapter": self.selected_adapter,
            "final_evaluation": (
                self.final_evaluation.to_dict()
                if self.final_evaluation is not None
                else None
            ),
            "status": self.status,
            "stop_reason": self.stop_reason,
            "reference_attempts": self.reference_attempts,
            "lineage_closed": self.lineage_closed,
            "semantics": {
                "not_rsi": (
                    "this controller synthesizes typed adapters; it cannot modify "
                    "its interpreter, gates, registry verification, or executor"
                ),
                "reference_attempts": (
                    "external reference feedback is consumed at most once and is "
                    "never returned to synthesis"
                ),
            },
        }


class AdapterController:
    def __init__(
        self,
        synthesizer: AdapterSynthesizer,
        *,
        policy: AdapterGatePolicy | None = None,
        max_rounds: int = 3,
        max_candidates_per_round: int = 4,
        max_total_candidates: int = 8,
    ) -> None:
        if not 1 <= max_rounds <= 8:
            raise ValueError("max_rounds must be between one and eight")
        if not 1 <= max_candidates_per_round <= 10:
            raise ValueError("max_candidates_per_round must be between one and ten")
        if not 1 <= max_total_candidates <= 24:
            raise ValueError("max_total_candidates must be between one and 24")
        self.synthesizer = synthesizer
        self.policy = policy or AdapterGatePolicy()
        self.max_rounds = max_rounds
        self.max_candidates_per_round = max_candidates_per_round
        self.max_total_candidates = max_total_candidates

    def run(
        self,
        rows: list[dict[str, Any]],
        profile: SchemaProfile,
        *,
        family: str,
        references: list[dict[str, Any]] | None = None,
    ) -> AdapterRun:
        started = datetime.now(timezone.utc)
        run_id = canonical_sha256({
            "source_schema_fingerprint": profile.fingerprint,
            "family": family,
            "policy": self.policy.to_dict(),
            "started_at_utc": started.isoformat(),
        })[:24]
        rounds: list[dict[str, Any]] = []
        required_targets = sorted(
            FAMILY_REQUIRED_TARGETS.get(
                family,
                FAMILY_REQUIRED_TARGETS["generic"],
            ) | frozenset(self.policy.required_targets)
        )
        feedback: list[dict[str, Any]] = [{
            "trusted_contract": {
                "family": family,
                "required_targets": required_targets,
            },
        }]
        seen: set[str] = set()
        selected: AdapterSpec | None = None
        actual_candidates = 0
        synthesis_failed_rounds = 0
        stop_reason = "round_budget_exhausted"

        for round_index in range(1, self.max_rounds + 1):
            remaining = self.max_total_candidates - actual_candidates
            if remaining <= 0:
                stop_reason = "candidate_budget_exhausted"
                break
            requested = min(self.max_candidates_per_round, remaining)
            feedback_used = list(feedback[-6:])
            try:
                proposed = self.synthesizer.propose(
                    profile,
                    family=family,
                    feedback=feedback,
                    max_candidates=requested,
                )
            except Exception as exc:  # noqa: BLE001 - proposer is untrusted
                synthesis_failed_rounds += 1
                error = f"{type(exc).__name__}: {exc}"[:1_000]
                rounds.append({
                    "round": round_index,
                    "status": "synthesis_failed",
                    "error": error,
                    "feedback_used": feedback_used,
                    "candidates": [],
                })
                feedback.append({
                    "round": round_index,
                    "trusted_schema_error": error,
                })
                stop_reason = "synthesis_failed"
                continue
            candidates = [spec for spec in proposed if spec.sha256 not in seen]
            for spec in candidates:
                seen.add(spec.sha256)
            if not candidates:
                rounds.append({
                    "round": round_index,
                    "status": "cycle_detected",
                    "feedback_used": feedback_used,
                    "candidates": [],
                })
                stop_reason = "candidate_cycle_detected"
                break

            evaluated: list[tuple[AdapterSpec, AdapterEvaluation]] = []
            for spec in candidates[:remaining]:
                try:
                    evaluation = evaluate_adapter(
                        spec,
                        rows,
                        policy=self.policy,
                        references=None,
                    )
                except Exception as exc:  # noqa: BLE001 - candidate fails closed
                    evaluation = None
                    error = f"{type(exc).__name__}: {exc}"[:1_000]
                else:
                    error = None
                    evaluated.append((spec, evaluation))
                actual_candidates += 1
                if evaluation is None:
                    feedback.append({
                        "round": round_index,
                        "adapter_sha256": spec.sha256,
                        "trusted_evaluation_error": error,
                    })
            ranked = sorted(evaluated, key=_rank, reverse=True)
            rounds.append({
                "round": round_index,
                "status": "development_evaluated",
                "feedback_used": feedback_used,
                "candidates": [evaluation.to_dict() for _, evaluation in ranked],
            })
            passing = [pair for pair in ranked if pair[1].accepted]
            if passing:
                selected = passing[0][0]
                stop_reason = "structural_gate_passed"
                break
            if ranked:
                best = ranked[0][1]
                feedback.append({
                    "round": round_index,
                    "adapter_sha256": best.adapter_sha256,
                    "complete_rate": best.adaptation.get("complete_rate"),
                    "binding_coverage": best.adaptation.get("binding_coverage"),
                    "gate_reasons": list(best.reasons),
                })
        else:
            if selected is None:
                stop_reason = "round_budget_exhausted"

        final: AdapterEvaluation | None = None
        reference_attempts = 0
        if selected is not None:
            if references is not None:
                reference_attempts = 1
            final = evaluate_adapter(
                selected,
                rows,
                references=references,
                policy=self.policy,
            )
            if final.accepted:
                status = final.activation_mode
                stop_reason = "all_available_gates_passed"
            else:
                status = "quarantined"
                stop_reason = "sealed_reference_gate_failed"
        else:
            status = "no_candidate"
        finished = datetime.now(timezone.utc)
        return AdapterRun(
            schema_version="benchcore-adapter-run-v1",
            run_id=run_id,
            started_at_utc=started.isoformat(),
            finished_at_utc=finished.isoformat(),
            source_schema_fingerprint=profile.fingerprint,
            source_content_sha256=canonical_sha256(rows),
            family=family,
            policy=self.policy.to_dict(),
            budget={
                "max_rounds": self.max_rounds,
                "max_candidates_per_round": self.max_candidates_per_round,
                "max_total_candidates": self.max_total_candidates,
                "actual_candidates": actual_candidates,
                "schema_valid_candidates": actual_candidates,
                "synthesis_failed_rounds": synthesis_failed_rounds,
                "actual_synthesis_rounds": len(rounds),
            },
            rounds=tuple(rounds),
            selected_adapter=(selected.to_dict() if selected is not None else None),
            final_evaluation=final,
            status=status,
            stop_reason=stop_reason,
            reference_attempts=reference_attempts,
            lineage_closed=references is not None and final is not None,
        )


def _rank(pair: tuple[AdapterSpec, AdapterEvaluation]) -> tuple[float, ...]:
    spec, evaluation = pair
    coverage = evaluation.adaptation.get("binding_coverage", {})
    mean_coverage = (
        sum(float(value) for value in coverage.values()) / len(coverage)
        if coverage else 0.0
    )
    return (
        1.0 if evaluation.accepted else 0.0,
        1.0 if evaluation.structural_passed else 0.0,
        float(evaluation.adaptation.get("complete_rate") or 0.0),
        mean_coverage,
        -float(len(spec.bindings)),
    )
