from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from .checkers import DEFAULT_CHECKERS, Checker, _violation
from .methods import DatasetChecker
from .schema import BenchmarkItem, Violation


def audit_items(
    items: list[BenchmarkItem],
    root: Path | None = None,
    checkers: list[Checker] | None = None,
    dataset_checkers: list[DatasetChecker] | None = None,
    progress_callback: Callable[[int, int, BenchmarkItem], None] | None = None,
    workers: int = 1,
) -> list[Violation]:
    active = checkers or DEFAULT_CHECKERS
    violations: list[Violation] = []
    total = len(items)

    def check_item(item: BenchmarkItem) -> list[Violation]:
        found = []
        for checker in active:
            found.extend(list(checker.check(item, root=root)))
        return found

    if workers <= 1:
        for completed, item in enumerate(items, 1):
            violations.extend(check_item(item))
            if progress_callback is not None:
                progress_callback(completed, total, item)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(check_item, item): item for item in items}
            for completed, future in enumerate(as_completed(futures), 1):
                item = futures[future]
                violations.extend(future.result())
                if progress_callback is not None:
                    progress_callback(completed, total, item)
    for checker in dataset_checkers or []:
        violations.extend(list(checker.check(items)))
    return fuse_llm_evidence(violations, items)


def fuse_llm_evidence(
    violations: list[Violation],
    items: list[BenchmarkItem],
) -> list[Violation]:
    items_by_id = {item.item_id: item for item in items}
    by_item: dict[str, list[Violation]] = {}
    added_violations: list[Violation] = []
    for violation in violations:
        by_item.setdefault(violation.item_id, []).append(violation)

    for item_id, item_violations in by_item.items():
        item = items_by_id.get(item_id)
        observations = (
            item.metadata.get("_llm_observations", {})
            if item is not None
            else {}
        )
        llm_methods = {
            violation.detection_method.split("+", 1)[0]
            for violation in item_violations
            if violation.detection_method.startswith("llm_")
            and violation.defect_type != "llm_audit_failure"
        }
        non_llm_defects = {
            violation.defect_type
            for violation in item_violations
            if not violation.detection_method.startswith("llm_")
        }
        corroborated = len(llm_methods) >= 2
        contradictions = observation_contradictions(observations)
        for violation in item_violations:
            if not violation.detection_method.startswith("llm_"):
                continue
            if violation.defect_type == "llm_audit_failure":
                continue
            base_method = violation.detection_method.split("+", 1)[0]
            relevant_contradictions = [
                contradiction["reason"]
                for contradiction in contradictions
                if base_method in contradiction["affected_methods"]
            ]
            if relevant_contradictions:
                violation.review_only = True
                violation.severity = "review"
                violation.evidence["auditor_contradictions"] = relevant_contradictions
                continue
            result = violation.evidence.get("llm_result", {})
            if (
                violation.detection_method == "llm_question_clarity"
                and violation.defect_type in non_llm_defects
            ):
                violation.review_only = False
                violation.severity = "major"
                violation.evidence["corroborated_by_non_llm"] = True
                continue
            if bool(result.get("needs_expert", False)):
                violation.review_only = True
                violation.severity = "review"
                continue
            if corroborated:
                violation.evidence["llm_corroborated_by"] = sorted(llm_methods)
        if contradictions and item is not None:
            added_violations.append(
                _violation(
                    item,
                    "auditor_contradiction",
                    1.0,
                    "LLM auditors produced mutually inconsistent conclusions.",
                    {
                        "reasons": [
                            contradiction["reason"]
                            for contradiction in contradictions
                        ],
                        "affected_methods": sorted(
                            {
                                method
                                for contradiction in contradictions
                                for method in contradiction["affected_methods"]
                            }
                        ),
                        "observations": observations,
                    },
                    severity="review",
                    review_only=True,
                    repair="Resolve the auditor disagreement before confirming a benchmark defect.",
                    method="llm_evidence_fusion",
                    scope="operational",
                )
            )
    violations.extend(added_violations)
    return violations


def observation_contradictions(observations: dict) -> list[dict]:
    contradictions = []
    gold = observations.get("llm_gold_audit", {})
    option = observations.get("llm_option_set", {})

    gold_answers = {
        str(value).strip().upper()
        for value in gold.get("correct_answers", [])
        if value not in (None, "")
    }
    option_best = set()
    for entry in option.get("option_statuses", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("best_answer_status") in {"best", "acceptable"}:
            label = entry.get("label")
            if label:
                option_best.add(str(label).strip().upper())

    if gold_answers and option_best and gold_answers.isdisjoint(option_best):
        contradictions.append(
            {
                "reason": (
                    f"gold correct_answers={sorted(gold_answers)} conflicts with "
                    f"option best_answers={sorted(option_best)}"
                ),
                "affected_methods": {"llm_gold_audit", "llm_option_set"},
            }
        )

    option_defect = option.get("defect_type")
    best_cardinality = option.get(
        "best_answer_cardinality",
        option.get("cardinality"),
    )
    if option_defect == "multiple_correct_answers" and best_cardinality == "exactly_one":
        contradictions.append(
            {
                "reason": (
                    "option defect says multiple_correct_answers but cardinality is exactly_one"
                ),
                "affected_methods": {"llm_option_set"},
            }
        )
    if option_defect == "no_correct_answer" and best_cardinality == "exactly_one":
        contradictions.append(
            {
                "reason": (
                    "option defect says no_correct_answer but cardinality is exactly_one"
                ),
                "affected_methods": {"llm_option_set"},
            }
        )

    declared_gold = str(observations.get("_declared_gold", "")).strip().upper()
    if (
        gold.get("gold_status") == "contradicted"
        and declared_gold
        and declared_gold in option_best
    ):
        contradictions.append(
            {
                "reason": (
                    "gold auditor contradicts the declared gold while option auditor "
                    "still marks it as best"
                ),
                "affected_methods": {"llm_gold_audit", "llm_option_set"},
            }
        )
    return contradictions
