"""Bounded train/dev/one-shot-holdout evolution controller."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .corpus import validate_corpus
from .evaluation import CandidateEvaluation, GatePolicy, evaluate_candidate
from .models import CorpusExample, RuleSpec, canonical_sha256, corpus_sha256
from .synthesis import RuleSynthesizer


@dataclass(frozen=True)
class EvolutionRun:
    schema_version: str
    run_id: str
    started_at_utc: str
    finished_at_utc: str
    corpus_sha256: str
    policy: dict[str, Any]
    budget: dict[str, int]
    rounds: tuple[dict[str, Any], ...]
    selected_rule: dict[str, Any] | None
    final_evaluation: CandidateEvaluation | None
    status: str
    stop_reason: str
    holdout_attempts: int
    lineage_closed: bool

    def to_dict(self, *, include_example_details: bool = False) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "corpus_sha256": self.corpus_sha256,
            "policy": self.policy,
            "budget": self.budget,
            "rounds": list(self.rounds),
            "selected_rule": self.selected_rule,
            "final_evaluation": (
                self.final_evaluation.to_dict(
                    include_example_details=include_example_details
                )
                if self.final_evaluation is not None
                else None
            ),
            "status": self.status,
            "stop_reason": self.stop_reason,
            "holdout_attempts": self.holdout_attempts,
            "lineage_closed": self.lineage_closed,
            "semantics": {
                "accepted": (
                    "eligible for automatic activation as a review-only declarative checker"
                ),
                "lineage_closed": (
                    "holdout feedback must not be used to resynthesize this lineage"
                ),
                "not_rsi": (
                    "the controller evolves bounded checker rules; it does not modify its trusted gates"
                ),
            },
        }


class EvolutionController:
    """Iterate on dev feedback, then consume a sealed holdout exactly once."""

    def __init__(
        self,
        synthesizer: RuleSynthesizer,
        *,
        policy: GatePolicy | None = None,
        max_rounds: int = 3,
        max_candidates_per_round: int = 6,
        max_total_candidates: int = 12,
    ) -> None:
        if not 1 <= max_rounds <= 10:
            raise ValueError("max_rounds must be between 1 and 10")
        if not 1 <= max_candidates_per_round <= 20:
            raise ValueError("max_candidates_per_round must be between 1 and 20")
        if not 1 <= max_total_candidates <= 50:
            raise ValueError("max_total_candidates must be between 1 and 50")
        self.synthesizer = synthesizer
        self.policy = policy or GatePolicy()
        self.max_rounds = max_rounds
        self.max_candidates_per_round = max_candidates_per_round
        self.max_total_candidates = max_total_candidates

    def run(self, examples: list[CorpusExample]) -> EvolutionRun:
        validate_corpus(examples)
        started = datetime.now(timezone.utc)
        corpus_digest = corpus_sha256(examples)
        run_id = canonical_sha256({
            "corpus_sha256": corpus_digest,
            "policy": self.policy.to_dict(),
            "started_at_utc": started.isoformat(),
        })[:24]
        train = [example for example in examples if example.split == "train"]
        feedback: list[dict[str, Any]] = []
        seen: set[str] = set()
        rounds: list[dict[str, Any]] = []
        selected: RuleSpec | None = None
        total_candidates = 0
        stop_reason = "round_budget_exhausted"

        for round_index in range(1, self.max_rounds + 1):
            remaining = self.max_total_candidates - total_candidates
            if remaining <= 0:
                stop_reason = "candidate_budget_exhausted"
                break
            requested = min(self.max_candidates_per_round, remaining)
            try:
                proposed = self.synthesizer.propose(
                    train,
                    feedback=feedback,
                    max_candidates=requested,
                )
            except Exception as exc:  # noqa: BLE001 - synthesis is untrusted
                error = f"{type(exc).__name__}: {exc}"[:1_000]
                rounds.append({
                    "round": round_index,
                    "status": "synthesis_failed",
                    "error": error,
                    "candidates": [],
                })
                # Schema failures are useful bounded feedback.  They never
                # reveal dev/holdout data and may be corrected in the next
                # iteration, subject to the hard round/call budget.
                feedback.append({
                    "round": round_index,
                    "synthesis_schema_error": error,
                })
                stop_reason = "synthesis_failed"
                continue
            new_rules = [rule for rule in proposed if rule.sha256 not in seen]
            for rule in new_rules:
                seen.add(rule.sha256)
            if not new_rules:
                rounds.append({
                    "round": round_index,
                    "status": "cycle_detected",
                    "candidates": [],
                })
                stop_reason = "candidate_cycle_detected"
                break
            evaluations: list[tuple[RuleSpec, CandidateEvaluation]] = []
            for rule in new_rules[:remaining]:
                evaluation = evaluate_candidate(
                    rule,
                    examples,
                    self.policy,
                    consume_holdout=False,
                )
                evaluations.append((rule, evaluation))
                total_candidates += 1
            ranked = sorted(evaluations, key=_development_rank, reverse=True)
            rounds.append({
                "round": round_index,
                "status": "development_evaluated",
                "candidates": [
                    evaluation.to_dict(include_example_details=False)
                    for _, evaluation in ranked
                ],
            })
            passing = [pair for pair in ranked if pair[1].dev_passed]
            if passing:
                selected = passing[0][0]
                stop_reason = "development_gate_passed"
                break
            best = ranked[0][1]
            feedback.append({
                "round": round_index,
                "rule_sha256": best.rule_sha256,
                "train_recall": best.train.recall,
                "dev_recall": best.dev.recall,
                "dev_false_positive_rate": best.dev.false_positive_rate,
                "dev_abstention_rate": best.dev.abstention_rate,
                "dev_paired_discrimination": best.dev.paired_discrimination,
                "gate_reasons": list(best.reasons),
            })

        final: CandidateEvaluation | None = None
        holdout_attempts = 0
        if selected is not None:
            # This is the only call in the controller that can read holdout.
            holdout_attempts = 1
            final = evaluate_candidate(
                selected,
                examples,
                self.policy,
                consume_holdout=True,
            )
            if final.accepted:
                status = "accepted"
                stop_reason = "all_gates_passed"
            else:
                status = "quarantined"
                stop_reason = "sealed_holdout_gate_failed"
        else:
            status = "no_candidate"
        finished = datetime.now(timezone.utc)
        return EvolutionRun(
            schema_version="benchcore-evolution-run-v1",
            run_id=run_id,
            started_at_utc=started.isoformat(),
            finished_at_utc=finished.isoformat(),
            corpus_sha256=corpus_digest,
            policy=self.policy.to_dict(),
            budget={
                "max_rounds": self.max_rounds,
                "max_candidates_per_round": self.max_candidates_per_round,
                "max_total_candidates": self.max_total_candidates,
                "actual_candidates": total_candidates,
            },
            rounds=tuple(rounds),
            selected_rule=selected.to_dict() if selected is not None else None,
            final_evaluation=final,
            status=status,
            stop_reason=stop_reason,
            holdout_attempts=holdout_attempts,
            lineage_closed=bool(final and final.lineage_closed),
        )


def _development_rank(pair: tuple[RuleSpec, CandidateEvaluation]) -> tuple[float, ...]:
    spec, evaluation = pair
    return (
        1.0 if evaluation.dev_passed else 0.0,
        evaluation.dev.paired_discrimination,
        evaluation.dev.recall,
        -evaluation.dev.false_positive_rate,
        -evaluation.dev.abstention_rate,
        evaluation.dev.precision,
        -float(spec.complexity),
    )
