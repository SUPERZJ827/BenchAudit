from __future__ import annotations

import ast
import json
import math
import operator
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .checkers import Checker, _violation
from .evaluators import (
    CHOICE_LABELS,
    answer_variants,
    choice_label_to_index,
    evaluate_answer,
    infer_evaluator_type,
    normalize_text,
    parse_number,
)
from .schema import BenchmarkItem, Violation


class EvaluatorReplayChecker(Checker):
    """Replay gold and declared aliases against the declared evaluator contract."""

    name = "evaluator_replay"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if item.gold in (None, "") or item.evaluator in (None, "", [], {}):
            return []
        if not evaluate_answer(item.gold, item.gold, item.choices, item.evaluator):
            yield _violation(
                item,
                "gold_rejected_by_evaluator",
                0.98,
                "Declared evaluator contract rejects the benchmark's own gold answer.",
                {
                    "gold": item.gold,
                    "choices": item.choices,
                    "evaluator": item.evaluator,
                    "evidence_level": "declared_evaluator_replay",
                },
                repair="Fix the gold representation or evaluator parsing contract.",
                method="evaluator_replay",
            )


class MetamorphicAnswerChecker(Checker):
    """Check answer transformations that should preserve correctness."""

    name = "metamorphic_answer"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if item.gold in (None, ""):
            return []
        kind = infer_evaluator_type(item.gold, item.choices, item.evaluator)
        expected_variants = _semantics_preserving_variants(item, kind)
        rejected = []
        for description, variant in expected_variants:
            if not evaluate_answer(variant, item.gold, item.choices, item.evaluator):
                rejected.append({"transformation": description, "variant": variant})
        if rejected:
            yield _violation(
                item,
                "metamorphic_inconsistency",
                0.72 if item.evaluator else 0.5,
                "Semantics-preserving answer transformations change the evaluation result.",
                {
                    "gold": item.gold,
                    "evaluator": item.evaluator,
                    "rejected_transformations": rejected,
                    "evidence_level": "declared_evaluator_model",
                },
                severity="review",
                review_only=True,
                repair="Normalize equivalent answer forms or explicitly document strict formatting requirements.",
                method="metamorphic_testing",
            )


class EvaluatorMutationChecker(Checker):
    """Inject clearly wrong answers and verify that the evaluator rejects them."""

    name = "evaluator_mutation"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if item.gold in (None, ""):
            return []
        accepted = []
        for mutation_name, mutation in _wrong_answer_mutations(item):
            if evaluate_answer(mutation, item.gold, item.choices, item.evaluator):
                accepted.append({"mutation": mutation_name, "value": mutation})
        if accepted:
            yield _violation(
                item,
                "evaluator_mutation_survived",
                0.6,
                "The modeled evaluator accepts one or more intentionally wrong answer mutations.",
                {
                    "gold": item.gold,
                    "evaluator": item.evaluator,
                    "surviving_mutations": accepted,
                    "evidence_level": "declared_evaluator_model",
                },
                severity="review",
                review_only=True,
                repair="Strengthen answer parsing or evaluator checks, then replay adversarial wrong answers.",
                method="mutation_testing",
            )


class ContractConsistencyChecker(Checker):
    """Check static consistency between output contract, choices, gold, and evaluator."""

    name = "contract_consistency"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        contract = normalize_text(item.output_contract)
        kind = infer_evaluator_type(item.gold, item.choices, item.evaluator)
        mismatch = None
        if item.choices and contract and any(token in contract for token in ("numeric", "number", "free text")):
            mismatch = "Choices are present, but output contract describes a non-choice answer."
        elif "json" in contract and kind in {"exact", "normalized_exact", "numeric", "choice"}:
            mismatch = f"Output contract requires JSON, but evaluator is modeled as {kind}."
        elif any(token in contract for token in ("numeric", "number")) and kind == "choice":
            mismatch = "Output contract requires numeric output, but evaluator is modeled as choice matching."
        if mismatch:
            yield _violation(
                item,
                "output_evaluator_contract_mismatch",
                0.85,
                mismatch,
                {
                    "output_contract": item.output_contract,
                    "evaluator": item.evaluator,
                    "inferred_evaluator": kind,
                },
                repair="Align the output contract, gold representation, and evaluator type.",
                method="cross_artifact_consistency",
            )


class TaskIntegrityChecker(Checker):
    """Deterministic checks for temporal, source, instruction, and rendering integrity."""

    name = "task_integrity"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        task = str(item.task or "")
        combined_choices = " ".join(str(choice) for choice in (item.choices or []))
        combined = f"{task}\n{combined_choices}"

        temporal_match = re.search(
            r"\b(as of now|latest|most recent)\b|"
            r"\bcurrent\s+(?:president|prime minister|leader|dalai lama|ceo|"
            r"version|release|population|rate|status|law|policy)\b",
            task,
            re.I,
        )
        has_explicit_year = bool(re.search(r"\b(?:19|20)\d{2}\b", task))
        has_temporal_metadata = any(
            key.lower() in {"date", "as_of", "timestamp", "release_date", "version"}
            for key in item.metadata
        )
        if temporal_match and not has_explicit_year and not has_temporal_metadata:
            yield _violation(
                item,
                "temporal_scope_missing",
                0.82,
                "Time-sensitive wording lacks an explicit reference date or version.",
                {
                    "matched_phrase": temporal_match.group(0),
                    "task_excerpt": task[:300],
                },
                severity="review",
                review_only=True,
                repair="Add an explicit as-of date or replace relative time wording with a stable reference.",
                method="task_integrity_rule",
            )

        source_match = re.search(
            r"\b(recent|new|latest|a|the)\s+"
            r"(research|study|report|survey|comparison)\b",
            task,
            re.I,
        )
        source_named = bool(
            re.search(r"\b(?:19|20)\d{2}\b|https?://|doi:|according to [A-Z][A-Za-z'-]+", task)
        )
        if source_match and not source_named and not item.context:
            yield _violation(
                item,
                "source_reference_missing",
                0.8,
                "The task depends on an unnamed study/report and provides no source context.",
                {"matched_phrase": source_match.group(0), "task_excerpt": task[:300]},
                severity="review",
                review_only=True,
                repair="Identify the study/report, publication date, or source artifact.",
                method="task_integrity_rule",
            )

        instruction_signals = []
        if re.search(r"\bserving\s*[-–—]\s*year terms\b", task, re.I):
            instruction_signals.append("missing_term_length_blank")
        if re.search(r"\bhas members each serving\s*[-–—]?\s*year terms\b", task, re.I):
            instruction_signals.append("missing_member_count_blank")
        if re.search(r"\b(?:select|identify|choose)\s*$", task.strip(), re.I):
            instruction_signals.append("truncated_command")
        if instruction_signals:
            yield _violation(
                item,
                "incomplete_task_instruction",
                0.9,
                "The task appears to contain a missing blank or truncated instruction.",
                {"signals": instruction_signals, "task_excerpt": task[:300]},
                severity="review",
                review_only=True,
                repair="Restore the missing blank, command, or original task instruction.",
                method="task_integrity_rule",
            )

        presentation_signals = []
        if re.search(r"(?:â|ï¿½|�|Ã[A-Za-z])", combined):
            presentation_signals.append("encoding_corruption")
        if re.search(
            r"\b\d{1,2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
            combined,
            re.I,
        ):
            presentation_signals.append("spreadsheet_date_conversion")
        if re.search(r"\b(?:10\^|10\s*\*)\s*$", combined):
            presentation_signals.append("truncated_exponent")
        if presentation_signals:
            yield _violation(
                item,
                "presentation_corruption",
                0.92,
                "Visible encoding or formatting corruption was detected.",
                {"signals": presentation_signals, "text_excerpt": combined[:400]},
                severity="review",
                review_only=True,
                repair="Restore the original text/choice formatting and prevent lossy conversion.",
                method="task_integrity_rule",
                scope="presentation",
            )


class ExecutableEvidenceChecker(Checker):
    """Validate safe arithmetic evidence embedded in a benchmark record."""

    name = "executable_evidence"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        checks = _find_executable_checks(item.raw)
        for source_path, evidence_checks in checks:
            results = []
            for index, check in enumerate(evidence_checks):
                if not isinstance(check, dict) or check.get("kind") != "python_expr":
                    continue
                expr = check.get("expr")
                expected = check.get("expected")
                computed = _safe_eval_expr(expr)
                if computed is None:
                    continue
                matches = _numeric_equivalent(computed, expected)
                results.append(
                    {
                        "index": index,
                        "expr": expr,
                        "expected": expected,
                        "computed": computed,
                        "matches": matches,
                    }
                )
                if not matches:
                    yield _violation(
                        item,
                        "invalid_executable_evidence",
                        0.99,
                        "Executable evidence does not reproduce its declared expected value.",
                        {
                            "source_path": source_path,
                            "check": check,
                            "computed": computed,
                        },
                        repair="Correct or regenerate the executable evidence.",
                        method="executable_evidence_replay",
                    )

            if not results:
                continue
            final_marked = _find_final_marked_value(item.raw, source_path)
            if final_marked is not None and not _answers_equivalent(final_marked, item.gold):
                yield _violation(
                    item,
                    "executable_evidence_gold_conflict",
                    0.98,
                    "Final answer associated with executable evidence disagrees with the gold answer.",
                    {
                        "source_path": source_path,
                        "gold": item.gold,
                        "final_evidence_answer": final_marked,
                        "checks": results,
                    },
                    repair="Review the gold answer and executable reasoning chain.",
                    method="executable_evidence_replay",
                )


class DifferentialCandidateChecker(Checker):
    """Compare independent candidate/solver answers already attached to an item."""

    name = "differential_candidate"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        candidates = _find_candidate_answers(item.raw)
        disagreements = []
        for source_path, answer, confidence in candidates:
            if answer in (None, "") or _answers_equivalent(answer, item.gold):
                continue
            disagreements.append(
                {
                    "source_path": source_path,
                    "candidate_answer": answer,
                    "confidence": confidence,
                }
            )
        if disagreements:
            max_confidence = max((x["confidence"] or 0.5) for x in disagreements)
            yield _violation(
                item,
                "solver_gold_disagreement",
                min(0.95, max(0.5, max_confidence)),
                "One or more independent candidate solver outputs disagree with the gold answer.",
                {"gold": item.gold, "disagreements": disagreements},
                severity="review",
                review_only=True,
                repair="Replay or independently verify the candidate solution before changing the gold.",
                method="differential_solver",
            )


class DatasetChecker:
    name = "dataset_checker"

    def check(self, items: list[BenchmarkItem]) -> Iterable[Violation]:
        raise NotImplementedError


class DuplicateConflictChecker(DatasetChecker):
    name = "duplicate_conflict"

    def check(self, items: list[BenchmarkItem]) -> Iterable[Violation]:
        by_id: dict[str, list[BenchmarkItem]] = defaultdict(list)
        by_signature: dict[str, list[BenchmarkItem]] = defaultdict(list)
        for item in items:
            by_id[item.item_id].append(item)
            by_signature[_item_signature(item)].append(item)

        for item_id, group in by_id.items():
            if len(group) <= 1:
                continue
            yield _violation(
                group[0],
                "duplicate_item_id",
                1.0,
                "Multiple records share the same item identifier.",
                {"item_id": item_id, "count": len(group)},
                repair="Assign stable unique identifiers or remove duplicate records.",
                method="dataset_duplicate_scan",
            )

        for group in by_signature.values():
            if len(group) <= 1:
                continue
            golds = {_stable_value(item.gold) for item in group}
            ids = [item.item_id for item in group]
            if len(golds) > 1:
                yield _violation(
                    group[0],
                    "conflicting_duplicate_oracle",
                    0.99,
                    "Equivalent task records declare conflicting gold answers.",
                    {"item_ids": ids, "gold_values": sorted(golds)},
                    repair="Reconcile the conflicting gold answers or separate genuinely different task contexts.",
                    method="dataset_duplicate_scan",
                )
            else:
                yield _violation(
                    group[0],
                    "duplicate_task",
                    0.9,
                    "Equivalent task records appear multiple times in the benchmark.",
                    {"item_ids": ids, "gold": group[0].gold},
                    severity="review",
                    review_only=True,
                    repair="Deduplicate the benchmark or document intentional repeated measurements.",
                    method="dataset_duplicate_scan",
                )


class SchemaDriftChecker(DatasetChecker):
    name = "schema_drift"

    def check(self, items: list[BenchmarkItem]) -> Iterable[Violation]:
        if len(items) < 5:
            return []
        patterns = Counter(_coverage_pattern(item) for item in items)
        dominant, dominant_count = patterns.most_common(1)[0]
        minority = len(items) - dominant_count
        if minority == 0:
            return []
        ratio = minority / len(items)
        if ratio < 0.02:
            return []
        example_ids = [
            item.item_id for item in items if _coverage_pattern(item) != dominant
        ][:20]
        yield _violation(
            items[0],
            "schema_drift",
            min(0.95, 0.5 + ratio),
            "Core artifact availability differs across records in the same benchmark sample.",
            {
                "dominant_pattern": dominant,
                "pattern_distribution": {str(k): v for k, v in patterns.items()},
                "minority_example_ids": example_ids,
            },
            severity="review",
            review_only=True,
            repair="Inspect whether mixed task families require separate mappings or missing artifact repair.",
            method="dataset_schema_profile",
        )


DEFAULT_METHOD_CHECKERS: list[Checker] = [
    TaskIntegrityChecker(),
    ContractConsistencyChecker(),
    EvaluatorReplayChecker(),
    MetamorphicAnswerChecker(),
    EvaluatorMutationChecker(),
    ExecutableEvidenceChecker(),
    DifferentialCandidateChecker(),
]

DEFAULT_DATASET_CHECKERS: list[DatasetChecker] = [
    DuplicateConflictChecker(),
    SchemaDriftChecker(),
]


def _semantics_preserving_variants(item: BenchmarkItem, kind: str) -> list[tuple[str, Any]]:
    variants = []
    if kind == "choice" and item.choices:
        idx = choice_label_to_index(item.gold, item.choices)
        if idx is not None:
            variants.extend(
                [
                    ("choice_text", item.choices[idx]),
                    ("choice_label_period", f"{CHOICE_LABELS[idx]}."),
                    ("choice_label_lowercase", CHOICE_LABELS[idx].lower()),
                ]
            )
    elif kind == "numeric":
        number = parse_number(item.gold)
        if number is not None:
            variants.append(("numeric_decimal", f"{number:.1f}"))
            if float(number).is_integer():
                variants.append(("numeric_leading_zeros", f"{int(number):03d}"))
    elif kind == "normalized_exact":
        text = str(item.gold)
        variants.extend(
            [
                ("surrounding_whitespace", f"  {text}  "),
                ("case_change", text.swapcase()),
            ]
        )
    variants.extend((f"declared_alias:{idx}", alias) for idx, alias in enumerate(item.aliases))
    return _deduplicate_variants(variants)


def _wrong_answer_mutations(item: BenchmarkItem) -> list[tuple[str, Any]]:
    if item.choices:
        gold_idx = choice_label_to_index(item.gold, item.choices)
        return [
            (f"non_gold_choice_{idx}", CHOICE_LABELS[idx])
            for idx in range(len(item.choices))
            if idx != gold_idx
        ]
    number = parse_number(item.gold)
    if number is not None:
        return [
            ("numeric_plus_one", number + 1),
            ("numeric_negated", -number if number != 0 else 1),
        ]
    gold_text = str(item.gold)
    return [
        ("unrelated_sentinel", "__BENCHCORE_INTENTIONALLY_WRONG__"),
        ("empty_answer", ""),
        ("gold_plus_contradiction", f"{gold_text} OR __BENCHCORE_INTENTIONALLY_WRONG__"),
    ]


def _deduplicate_variants(values: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    seen = set()
    result = []
    for name, value in values:
        key = _stable_value(value)
        if key in seen:
            continue
        seen.add(key)
        result.append((name, value))
    return result


def _item_signature(item: BenchmarkItem) -> str:
    payload = {
        "task": _normalize_task(item.task),
        "context": item.context,
        "choices": item.choices,
        "output_contract": item.output_contract,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _normalize_task(value: Any) -> str:
    text = normalize_text(value)
    return re.sub(r"\s+", " ", text).strip()


def _stable_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _coverage_pattern(item: BenchmarkItem) -> tuple[bool, bool, bool, bool, bool]:
    return (
        bool(item.task),
        bool(item.context),
        bool(item.output_contract or item.choices),
        item.gold not in (None, ""),
        bool(item.evaluator or item.choices),
    )


_SAFE_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_SAFE_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_SAFE_CALLS = {
    "abs": abs,
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
    "min": min,
    "max": max,
}


def _safe_eval_expr(expr: Any) -> float | int | None:
    if not isinstance(expr, str) or len(expr) > 500:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def visit(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BINOPS:
            return _SAFE_BINOPS[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_UNARY:
            return _SAFE_UNARY[type(node.op)](visit(node.operand))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _SAFE_CALLS
            and not node.keywords
        ):
            return _SAFE_CALLS[node.func.id](*(visit(arg) for arg in node.args))
        raise ValueError("unsupported expression")

    try:
        value = visit(tree)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    return value


def _find_executable_checks(value: Any, path: str = "") -> list[tuple[str, list[Any]]]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in {"executable_checks", "execution_checks", "oracle_checks"} and isinstance(child, list):
                found.append((child_path, child))
            else:
                found.extend(_find_executable_checks(child, child_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            found.extend(_find_executable_checks(child, f"{path}[{idx}]"))
    return found


def _find_final_marked_value(raw: dict[str, Any], source_path: str) -> Any:
    if source_path.endswith("executable_checks"):
        if source_path.endswith("platinum_executable_checks"):
            return None
        metadata = raw.get("metadata", {})
        if isinstance(metadata, dict):
            return metadata.get("original_final_answer")
        return raw.get("final_answer")
    return None


def _find_candidate_answers(value: Any, path: str = "") -> list[tuple[str, Any, float | None]]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in {"math_solution_verification", "solver_result", "candidate_solution"} and isinstance(child, dict):
                answer = child.get("final_answer", child.get("answer"))
                confidence = child.get("confidence")
                try:
                    confidence = float(confidence) if confidence is not None else None
                except (TypeError, ValueError):
                    confidence = None
                found.append((child_path, answer, confidence))
            found.extend(_find_candidate_answers(child, child_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            found.extend(_find_candidate_answers(child, f"{path}[{idx}]"))
    return found


def _numeric_equivalent(left: Any, right: Any) -> bool:
    left_num = parse_number(left)
    right_num = parse_number(right)
    if left_num is None or right_num is None:
        return str(left).strip() == str(right).strip()
    tolerance = max(1e-9, 1e-6 * max(1.0, abs(left_num), abs(right_num)))
    return abs(left_num - right_num) <= tolerance


def _answers_equivalent(left: Any, right: Any) -> bool:
    if _numeric_equivalent(left, right):
        return True
    return normalize_text(left) == normalize_text(right)
