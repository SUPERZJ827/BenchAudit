"""Independent metrics and acceptance gates for generated rules."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .corpus import build_corpus_items
from .models import CorpusExample, RuleSpec
from .rules import evaluate_rule


@dataclass(frozen=True)
class GatePolicy:
    schema_version: str = "benchcore-evolution-gate-v1"
    min_train_positives: int = 4
    min_train_negatives: int = 4
    min_dev_positives: int = 10
    min_dev_negatives: int = 10
    min_holdout_positives: int = 20
    min_holdout_negatives: int = 20
    min_dev_recall: float = 0.90
    min_holdout_recall: float = 0.90
    min_dev_paired_discrimination: float = 0.90
    min_holdout_paired_discrimination: float = 0.90
    max_dev_false_positive_rate: float = 0.02
    max_holdout_false_positive_rate: float = 0.02
    max_dev_abstention_rate: float = 0.0
    max_holdout_abstention_rate: float = 0.0
    min_dev_recall_wilson_lower: float = 0.80
    min_holdout_recall_wilson_lower: float = 0.90
    max_dev_false_positive_wilson_upper: float = 0.10
    max_holdout_false_positive_wilson_upper: float = 0.05
    max_rule_complexity: int = 24

    def __post_init__(self) -> None:
        for name in (
            "min_train_positives",
            "min_train_negatives",
            "min_dev_positives",
            "min_dev_negatives",
            "min_holdout_positives",
            "min_holdout_negatives",
            "max_rule_complexity",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in (
            "min_dev_recall",
            "min_holdout_recall",
            "min_dev_paired_discrimination",
            "min_holdout_paired_discrimination",
            "max_dev_false_positive_rate",
            "max_holdout_false_positive_rate",
            "max_dev_abstention_rate",
            "max_holdout_abstention_rate",
            "min_dev_recall_wilson_lower",
            "min_holdout_recall_wilson_lower",
            "max_dev_false_positive_wilson_upper",
            "max_holdout_false_positive_wilson_upper",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between zero and one")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplitMetrics:
    split: str
    total: int
    positives: int
    negatives: int
    true_positives: int
    false_negatives: int
    false_positives: int
    true_negatives: int
    abstained: int
    recall: float
    precision: float
    false_positive_rate: float
    abstention_rate: float
    paired_groups: int
    paired_discriminated: int
    paired_discrimination: float
    recall_wilson95: tuple[float | None, float | None]
    false_positive_rate_wilson95: tuple[float | None, float | None]
    per_example: tuple[dict[str, Any], ...]

    def to_dict(self, *, include_examples: bool = True) -> dict[str, Any]:
        result = asdict(self)
        if not include_examples:
            result.pop("per_example", None)
        return result


@dataclass(frozen=True)
class CandidateEvaluation:
    rule: dict[str, Any]
    rule_sha256: str
    policy: dict[str, Any]
    train: SplitMetrics
    dev: SplitMetrics
    holdout: SplitMetrics | None
    dev_passed: bool
    accepted: bool
    holdout_consumed: bool
    lineage_closed: bool
    reasons: tuple[str, ...]

    def to_dict(self, *, include_example_details: bool = False) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "rule_sha256": self.rule_sha256,
            "policy": self.policy,
            "train": self.train.to_dict(include_examples=include_example_details),
            "dev": self.dev.to_dict(include_examples=include_example_details),
            "holdout": (
                self.holdout.to_dict(include_examples=include_example_details)
                if self.holdout is not None
                else None
            ),
            "dev_passed": self.dev_passed,
            "accepted": self.accepted,
            "holdout_consumed": self.holdout_consumed,
            "lineage_closed": self.lineage_closed,
            "reasons": list(self.reasons),
        }


def evaluate_candidate(
    spec: RuleSpec,
    examples: list[CorpusExample],
    policy: GatePolicy,
    *,
    consume_holdout: bool,
) -> CandidateEvaluation:
    train = evaluate_split(spec, examples, "train")
    dev = evaluate_split(spec, examples, "dev")
    reasons = _development_gate_reasons(spec, train, dev, policy)
    dev_passed = not reasons
    holdout: SplitMetrics | None = None
    if consume_holdout:
        holdout = evaluate_split(spec, examples, "holdout")
        reasons.extend(_holdout_gate_reasons(holdout, policy))
    accepted = bool(consume_holdout and dev_passed and not reasons)
    return CandidateEvaluation(
        rule=spec.to_dict(),
        rule_sha256=spec.sha256,
        policy=policy.to_dict(),
        train=train,
        dev=dev,
        holdout=holdout,
        dev_passed=dev_passed,
        accepted=accepted,
        holdout_consumed=consume_holdout,
        # A holdout result must never be fed back into the same synthesis
        # lineage.  Pass or fail, that lineage is closed after one look.
        lineage_closed=consume_holdout,
        reasons=tuple(reasons),
    )


def evaluate_split(
    spec: RuleSpec,
    examples: list[CorpusExample],
    split: str,
) -> SplitMetrics:
    selected = [example for example in examples if example.split == split]
    items = build_corpus_items(selected)
    rows: list[dict[str, Any]] = []
    for example, item in zip(selected, items, strict=True):
        expected = spec.defect_type in example.expected_defect_types
        try:
            outcome = evaluate_rule(spec, item)
            predicted = outcome.matched
            status = outcome.status
        except Exception as exc:  # noqa: BLE001 - gate must fail closed
            predicted = None
            status = "abstained"
            outcome = None
            error = f"{type(exc).__name__}: {exc}"[:500]
        else:
            error = None
        rows.append({
            "example_id": example.example_id,
            "source_group": example.source_group,
            "expected": expected,
            "predicted": predicted,
            "status": status,
            "error": error,
        })
    positives = sum(bool(row["expected"]) for row in rows)
    negatives = len(rows) - positives
    tp = sum(row["expected"] and row["predicted"] is True for row in rows)
    fn = positives - tp
    fp = sum(not row["expected"] and row["predicted"] is True for row in rows)
    tn = sum(not row["expected"] and row["predicted"] is False for row in rows)
    abstained = sum(row["predicted"] is None for row in rows)
    paired_groups, paired_discriminated = _paired_metrics(rows)
    return SplitMetrics(
        split=split,
        total=len(rows),
        positives=positives,
        negatives=negatives,
        true_positives=tp,
        false_negatives=fn,
        false_positives=fp,
        true_negatives=tn,
        abstained=abstained,
        recall=_rate(tp, positives),
        precision=_rate(tp, tp + fp),
        false_positive_rate=_rate(fp, negatives),
        abstention_rate=_rate(abstained, len(rows)),
        paired_groups=paired_groups,
        paired_discriminated=paired_discriminated,
        paired_discrimination=_rate(paired_discriminated, paired_groups),
        recall_wilson95=wilson_interval(tp, positives),
        false_positive_rate_wilson95=wilson_interval(fp, negatives),
        per_example=tuple(rows),
    )


def _paired_metrics(rows: Iterable[dict[str, Any]]) -> tuple[int, int]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["source_group"]), []).append(row)
    eligible = [
        group
        for group in groups.values()
        if any(row["expected"] for row in group)
        and any(not row["expected"] for row in group)
    ]
    passed = sum(
        all(
            row["predicted"] is (True if row["expected"] else False)
            for row in group
        )
        for group in eligible
    )
    return len(eligible), passed


def _development_gate_reasons(
    spec: RuleSpec,
    train: SplitMetrics,
    dev: SplitMetrics,
    policy: GatePolicy,
) -> list[str]:
    reasons: list[str] = []
    if spec.complexity > policy.max_rule_complexity:
        reasons.append(
            f"rule complexity {spec.complexity} exceeds {policy.max_rule_complexity}"
        )
    for metric, minimum, label in (
        (train.positives, policy.min_train_positives, "train positives"),
        (train.negatives, policy.min_train_negatives, "train negatives"),
        (dev.positives, policy.min_dev_positives, "dev positives"),
        (dev.negatives, policy.min_dev_negatives, "dev negatives"),
    ):
        if metric < minimum:
            reasons.append(f"{label} {metric} is below minimum {minimum}")
    if dev.recall < policy.min_dev_recall:
        reasons.append(
            f"dev recall {dev.recall:.6f} is below {policy.min_dev_recall:.6f}"
        )
    if dev.false_positive_rate > policy.max_dev_false_positive_rate:
        reasons.append(
            "dev false-positive rate "
            f"{dev.false_positive_rate:.6f} exceeds "
            f"{policy.max_dev_false_positive_rate:.6f}"
        )
    if dev.abstention_rate > policy.max_dev_abstention_rate:
        reasons.append(
            f"dev abstention {dev.abstention_rate:.6f} exceeds "
            f"{policy.max_dev_abstention_rate:.6f}"
        )
    if dev.paired_discrimination < policy.min_dev_paired_discrimination:
        reasons.append(
            f"dev paired discrimination {dev.paired_discrimination:.6f} is below "
            f"{policy.min_dev_paired_discrimination:.6f}"
        )
    dev_recall_lower = dev.recall_wilson95[0]
    if dev_recall_lower is None or dev_recall_lower < policy.min_dev_recall_wilson_lower:
        reasons.append(
            f"dev recall Wilson lower {dev_recall_lower} is below "
            f"{policy.min_dev_recall_wilson_lower:.6f}"
        )
    dev_fp_upper = dev.false_positive_rate_wilson95[1]
    if (
        dev_fp_upper is None
        or dev_fp_upper > policy.max_dev_false_positive_wilson_upper
    ):
        reasons.append(
            f"dev false-positive Wilson upper {dev_fp_upper} exceeds "
            f"{policy.max_dev_false_positive_wilson_upper:.6f}"
        )
    return reasons


def _holdout_gate_reasons(
    holdout: SplitMetrics,
    policy: GatePolicy,
) -> list[str]:
    reasons: list[str] = []
    if holdout.positives < policy.min_holdout_positives:
        reasons.append(
            f"holdout positives {holdout.positives} is below minimum "
            f"{policy.min_holdout_positives}"
        )
    if holdout.negatives < policy.min_holdout_negatives:
        reasons.append(
            f"holdout negatives {holdout.negatives} is below minimum "
            f"{policy.min_holdout_negatives}"
        )
    if holdout.recall < policy.min_holdout_recall:
        reasons.append(
            f"holdout recall {holdout.recall:.6f} is below "
            f"{policy.min_holdout_recall:.6f}"
        )
    if holdout.false_positive_rate > policy.max_holdout_false_positive_rate:
        reasons.append(
            f"holdout false-positive rate {holdout.false_positive_rate:.6f} exceeds "
            f"{policy.max_holdout_false_positive_rate:.6f}"
        )
    if holdout.abstention_rate > policy.max_holdout_abstention_rate:
        reasons.append(
            f"holdout abstention {holdout.abstention_rate:.6f} exceeds "
            f"{policy.max_holdout_abstention_rate:.6f}"
        )
    if holdout.paired_discrimination < policy.min_holdout_paired_discrimination:
        reasons.append(
            "holdout paired discrimination "
            f"{holdout.paired_discrimination:.6f} is below "
            f"{policy.min_holdout_paired_discrimination:.6f}"
        )
    recall_lower = holdout.recall_wilson95[0]
    if (
        recall_lower is None
        or recall_lower < policy.min_holdout_recall_wilson_lower
    ):
        reasons.append(
            f"holdout recall Wilson lower {recall_lower} is below "
            f"{policy.min_holdout_recall_wilson_lower:.6f}"
        )
    fp_upper = holdout.false_positive_rate_wilson95[1]
    if (
        fp_upper is None
        or fp_upper > policy.max_holdout_false_positive_wilson_upper
    ):
        reasons.append(
            f"holdout false-positive Wilson upper {fp_upper} exceeds "
            f"{policy.max_holdout_false_positive_wilson_upper:.6f}"
        )
    return reasons


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def wilson_interval(
    successes: int,
    total: int,
    z: float = 1.959963984540054,
) -> tuple[float | None, float | None]:
    if total == 0:
        return None, None
    if successes < 0 or successes > total:
        raise ValueError("successes must be within total")
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        (p * (1 - p) + z * z / (4 * total)) / total
    ) / denominator
    lower = 0.0 if successes == 0 else max(0.0, center - margin)
    upper = 1.0 if successes == total else min(1.0, center + margin)
    return lower, upper
