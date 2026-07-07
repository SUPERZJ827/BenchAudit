from __future__ import annotations

import ast
import operator
import re
from pathlib import Path
from typing import Any, Iterable

from .evaluators import (
    answer_contract,
    answer_variants,
    choice_label_to_index,
    evaluate_answer,
    infer_evaluator_type,
    normalize_choice_for_duplicate,
    normalize_loose,
    parse_number,
)
from .schema import BenchmarkItem, Violation
from .taxonomy import DEFECTS


REFERENCE_PATTERNS = {
    "passage": re.compile(r"\b(passage|article|paragraph|text above|above text)\b", re.I),
    "figure": re.compile(r"\b(figure|diagram|chart|plot|screenshot)\b|\b(attached|shown|following)\s+image\b", re.I),
    "table": re.compile(r"\b(spreadsheet|csv|excel)\b|\b(table\s+(above|below|shown|provided|attached))\b", re.I),
    "file": re.compile(
        r"\b(attached|provided|following|uploaded)\s+(file|attachment|document|pdf)\b|"
        r"\baccording to\s+(the\s+)?(file|document|pdf)\b",
        re.I,
    ),
    "database": re.compile(
        r"\b(given|provided|attached|following)\s+(database|schema)\b|"
        r"\baccording to\s+(the\s+)?(database|schema)\b",
        re.I,
    ),
}

CONTEXT_ALIASES = {
    "figure": {"figure", "image", "images", "attachment", "attachments", "file", "files", "context"},
    "table": {"table", "tables", "spreadsheet", "csv", "excel", "attachment", "attachments", "file", "files", "context"},
    "file": {"file", "files", "attachment", "attachments", "document", "documents", "context"},
    "passage": {"passage", "article", "document", "documents", "context"},
    "database": {"database", "schema", "db_schema", "database_schema", "tables", "context"},
}

AMBIGUITY_PATTERNS = (
    re.compile(
        r"\b(latest|most recent)\b|"
        r"\bcurrent\s+(?:president|prime minister|leader|ceo|version|release|"
        r"population|rate|status|law|policy)\b",
        re.I,
    ),
    re.compile(r"\b(best|most appropriate|most likely|typically|usually)\b", re.I),
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _has_context(item: BenchmarkItem, name: str | None = None) -> bool:
    values = [v for v in item.context.values() if v not in (None, "", [], {})]
    if not values:
        return False
    if name is None:
        return True
    aliases = CONTEXT_ALIASES.get(name, {name})
    for key, value in item.context.items():
        key_lower = key.lower()
        if any(alias in key_lower for alias in aliases) and value not in (None, "", [], {}):
            return True
    return False


def _violation(
    item: BenchmarkItem,
    defect_type: str,
    confidence: float,
    message: str,
    evidence: dict[str, Any] | None = None,
    severity: str | None = None,
    review_only: bool | None = None,
    repair: str | None = None,
    method: str = "static_rule",
    scope: str = "substantive",
    artifact: str | None = None,
) -> Violation:
    info = DEFECTS[defect_type]
    chosen_severity = severity or info.default_severity
    return Violation(
        item_id=item.item_id,
        artifact=artifact or info.artifact,
        mechanism=info.mechanism,
        defect_type=info.defect_type,
        severity=chosen_severity,
        confidence=confidence,
        message=message,
        detection_method=method,
        defect_scope=scope,
        evidence=evidence or {},
        suggested_repair=repair,
        review_only=(chosen_severity == "review") if review_only is None else review_only,
    )


class Checker:
    name = "checker"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        raise NotImplementedError


class TaskSpecChecker(Checker):
    name = "task_specification"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        task = _text(item.task).strip()
        if not task:
            yield _violation(
                item,
                "missing_task",
                1.0,
                "Task specification is missing.",
                repair="Add a question, instruction, or problem statement.",
            )
            return
        for context_name, pattern in REFERENCE_PATTERNS.items():
            if (
                pattern.search(task)
                and not _has_context(item, context_name)
                and not _has_embedded_context(task, context_name)
            ):
                yield _violation(
                    item,
                    "missing_context",
                    0.85,
                    f"Task references {context_name}, but no matching context artifact was found.",
                    {"reference_type": context_name, "task_excerpt": task[:240]},
                    repair=f"Attach the referenced {context_name} or remove the reference.",
                )
        for pattern in AMBIGUITY_PATTERNS:
            if pattern.search(task) and not any(k in item.metadata for k in ("source", "version", "date", "domain")):
                yield _violation(
                    item,
                    "ambiguous_goal",
                    0.45,
                    "Task contains context-sensitive wording but lacks source/version/domain metadata.",
                    {"matched_pattern": pattern.pattern, "task_excerpt": task[:240]},
                    severity="review",
                    repair="Add explicit time, source, domain, jurisdiction, or intended convention when answer-changing.",
                )


class ContextChecker(Checker):
    name = "context_attachment"

    def __init__(self, *, check_version_risk: bool = True) -> None:
        self.check_version_risk = check_version_risk

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        for key, value in item.context.items():
            if value in (None, "", [], {}):
                continue
            candidates: list[Any] = value if isinstance(value, list) else [value]
            for candidate in candidates:
                if not isinstance(candidate, str):
                    continue
                if not _looks_like_path(candidate):
                    continue
                path = Path(candidate)
                if not path.is_absolute() and root is not None:
                    path = root / path
                if not path.exists():
                    yield _violation(
                        item,
                        "inaccessible_attachment",
                        0.95,
                        f"Referenced attachment does not exist: {candidate}",
                        {"field": key, "path": candidate},
                        repair="Fix the attachment path or include the missing artifact.",
                    )
        if not self.check_version_risk:
            return
        task = _text(item.task)
        if re.search(r"\b(as of|version|release|updated|latest|current)\b", task, re.I):
            has_version = any(k.lower() in {"version", "source", "date", "release"} for k in item.metadata)
            if not has_version:
                yield _violation(
                    item,
                    "context_version_mismatch_risk",
                    0.4,
                    "Task appears version-sensitive but no source/version metadata was found.",
                    {"task_excerpt": task[:240]},
                    severity="review",
                    repair="Record source, release, timestamp, or benchmark version metadata.",
                )


class OutputContractChecker(Checker):
    name = "expected_output"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if (
            item.output_contract in (None, "", [], {})
            and not item.choices
            and item.evaluator in (None, "", [], {})
        ):
            yield _violation(
                item,
                "missing_output_contract",
                0.55,
                "No explicit output format/answer contract was found.",
                severity="review",
                review_only=True,
                repair="Add expected output type, normalization, unit, or submission format.",
            )
        task = _text(item.task)
        gold_num = parse_number(item.gold)
        if (
            gold_num is not None
            and re.search(r"\b(about|approximately|approximate|estimate|roughly|nearest)\b", task, re.I)
            and infer_evaluator_type(item.gold, item.choices, item.evaluator) == "numeric"
            and not _is_discrete_count_approximation(task, gold_num)
        ):
            yield _violation(
                item,
                "output_format_overstrict_risk",
                0.8,
                "Task requests an approximate answer, but the evaluator requires exact numeric equality.",
                {
                    "gold": item.gold,
                    "task_excerpt": task[:240],
                    "evaluator": item.evaluator,
                    "output_contract": item.output_contract,
                },
                severity="review",
                review_only=True,
                repair="Define an approximation rule, rounding target, or numeric tolerance.",
                method="cross_artifact_consistency",
            )
        if gold_num is not None and re.search(r"\b(dollar|usd|yuan|rmb|percent|%|meter|mile|hour|minute|kg|pound)\b", task, re.I):
            if (
                not _question_requests_unit_answer(task)
                and not re.search(r"\b(dollar|usd|yuan|rmb|percent|%|meter|mile|hour|minute|kg|pound)\b", _text(item.output_contract), re.I)
            ):
                yield _violation(
                    item,
                    "missing_accepted_alternatives",
                    0.45,
                    "Numeric task mentions units, but the output contract does not state unit handling.",
                    {"gold": item.gold, "task_excerpt": task[:240]},
                    severity="review",
                    repair="Declare whether units are required, optional, or normalized by the evaluator.",
                )


class OracleChecker(Checker):
    name = "oracle_ground_truth"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if item.gold in (None, ""):
            yield _violation(
                item,
                "missing_oracle",
                1.0,
                "Gold answer/reference oracle is missing.",
                repair="Add gold answer, target state, reference solution, or accepted alternatives.",
            )
            return
        if item.choices:
            idx = choice_label_to_index(item.gold, item.choices)
            if idx is None:
                yield _violation(
                    item,
                    "invalid_choice_gold",
                    0.98,
                    "Gold choice cannot be mapped to the available answer choices.",
                    {"gold": item.gold, "choices": item.choices},
                    repair="Correct the gold label or the choice list.",
                )
            normalized = {}
            duplicates = []
            for pos, choice in enumerate(item.choices):
                norm = normalize_choice_for_duplicate(choice)
                if norm in normalized:
                    duplicates.append((normalized[norm], pos, choice))
                else:
                    normalized[norm] = pos
            if duplicates:
                yield _violation(
                    item,
                    "duplicate_choices",
                    0.75,
                    "Two or more choices normalize to the same text.",
                    {"duplicates": duplicates, "choices": item.choices},
                    severity="review",
                    repair="Deduplicate choices unless duplicates are intentional distractors that do not affect the gold answer.",
                )
        arithmetic_value = _extract_simple_arithmetic_value(_text(item.task))
        gold_num = parse_number(item.gold)
        if arithmetic_value is not None and gold_num is not None and abs(arithmetic_value - gold_num) > 1e-9:
            yield _violation(
                item,
                "wrong_gold_answer",
                0.95,
                "Simple executable arithmetic evidence disagrees with the gold answer.",
                {"gold": item.gold, "computed_value": arithmetic_value, "task": item.task},
                repair="Review and correct the gold answer or reference solution.",
            )


class EvaluatorChecker(Checker):
    name = "evaluator"

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        contract = answer_contract(item.gold, item.choices, item.evaluator, item.output_contract)
        inferred = (
            contract["cardinality"]
            if contract["cardinality"] in {"set", "compound"}
            else contract["kind"]
        )
        if item.evaluator in (None, "", [], {}) and item.gold not in (None, ""):
            severity = "minor" if inferred in {"choice", "numeric", "normalized_exact"} else "major"
            yield _violation(
                item,
                "missing_evaluator",
                0.5,
                f"No explicit evaluator was found; inferred evaluator type is {inferred}.",
                {"inferred_evaluator": inferred},
                severity=severity,
                review_only=severity == "minor",
                repair="Declare evaluator type, normalization, aliases, tests, or rubric.",
            )
        rejected = []
        for description, variant in answer_variants(
            item.gold,
            item.choices,
            item.evaluator,
            item.output_contract,
        ):
            if not evaluate_answer(variant, item.gold, item.choices, item.evaluator):
                rejected.append({"variant_description": description, "variant": variant})
        alias_rejected = []
        if contract["cardinality"] != "set":
            for alias in item.aliases:
                if not evaluate_answer(alias, item.gold, item.choices, item.evaluator):
                    alias_rejected.append(alias)
        if alias_rejected:
            yield _violation(
                item,
                "overstrict_evaluator",
                0.9,
                "Evaluator rejects declared accepted answer aliases.",
                {"aliases_rejected": alias_rejected, "gold": item.gold, "evaluator": item.evaluator},
                repair="Update evaluator normalization or accepted-alternative handling.",
            )
        elif rejected and inferred in {"exact"}:
            yield _violation(
                item,
                "output_format_overstrict_risk",
                0.65,
                "Exact evaluator rejects format-preserving variants of the gold answer.",
                {"rejected_variants": rejected[:5], "gold": item.gold, "evaluator": item.evaluator},
                severity="review",
                repair="Use normalized exact match, answer extraction, or accepted aliases.",
            )
        if item.evaluator in (None, "", [], {}) and item.output_contract in (None, "", [], {}) and not item.choices:
            yield _violation(
                item,
                "underconstrained_evaluator_risk",
                0.4,
                "No evaluator or output contract is available to determine task success.",
                {"gold": item.gold},
                severity="review",
                repair="Add tests, rubric, normalization rules, or executable oracle.",
            )


def _looks_like_path(value: str) -> bool:
    if "\n" in value or len(value) > 260:
        return False
    suffixes = (
        ".pdf",
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".txt",
        ".md",
        ".png",
        ".jpg",
        ".jpeg",
        ".xlsx",
        ".py",
        ".sql",
        ".zip",
    )
    return value.startswith(("./", "../", "/")) or value.lower().endswith(suffixes)


def _has_embedded_context(task: str, context_name: str) -> bool:
    if context_name == "passage":
        marker = re.search(
            r"(following information|following passage|passage below|text below)\s*[:.]?\s*",
            task,
            re.I,
        )
        if marker and len(task[marker.end() :].strip()) >= 100:
            return True
    if context_name == "table":
        marker = re.search(r"(table below|following table)\s*[:.]?\s*", task, re.I)
        if marker and len(task[marker.end() :].strip()) >= 40:
            return True
    return False


def _question_requests_unit_answer(task: str) -> bool:
    """Return true when the unit is already part of the answer request.

    In elementary word problems, a bare numeric gold is acceptable when the
    question asks "how many minutes", "how much money", "what is the area",
    etc. The evaluator may still normalize units, but missing unit text in the
    gold is not itself a useful review signal.
    """
    text = re.sub(r"\s+", " ", task.lower())
    unit = r"dollars?|usd|yuan|rmb|cents?|percent|%|meters?|miles?|hours?|minutes?|kilograms?|kg|pounds?"
    if re.search(rf"\bhow\s+(?:many|much)\b[^?.!]*\b(?:{unit})\b", text):
        return True
    if re.search(r"\bhow\s+much\s+(?:money|will\b[^?.!]*(?:pay|cost)|does\b[^?.!]*cost)\b", text):
        return True
    if re.search(r"\bhow\s+(?:long|far)\b", text):
        return True
    if re.search(r"\bwhat\s+is\b[^?.!]*\b(?:area|perimeter|volume|length|height|width|distance|time)\b", text):
        return True
    return False


def _is_discrete_count_approximation(task: str, gold_num: float) -> bool:
    if not float(gold_num).is_integer():
        return False
    text = re.sub(r"\s+", " ", task.lower())
    discrete_units = (
        "piles",
        "groups",
        "packages",
        "packs",
        "boxes",
        "bags",
        "buses",
        "cars",
        "trips",
        "loads",
        "teams",
    )
    unit_pattern = "|".join(discrete_units)
    return bool(re.search(rf"\bhow\s+many\b[^?.!]*\b(?:{unit_pattern})\b", text))


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


def _safe_eval_arithmetic(expr: str) -> float | None:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BINOPS:
            return float(_SAFE_BINOPS[type(node.op)](visit(node.left), visit(node.right)))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_UNARY:
            return float(_SAFE_UNARY[type(node.op)](visit(node.operand)))
        raise ValueError("unsafe expression")

    try:
        value = visit(tree)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    if abs(value) > 1e12:
        return None
    return value


def _extract_simple_arithmetic_value(task: str) -> float | None:
    patterns = [
        r"what is\s+([-+*/().\d\s]+)\??",
        r"calculate\s+([-+*/().\d\s]+)\??",
        r"compute\s+([-+*/().\d\s]+)\??",
    ]
    for pattern in patterns:
        match = re.search(pattern, task, re.I)
        if not match:
            continue
        expr = match.group(1).strip()
        if re.fullmatch(r"[-+*/().\d\s]+", expr):
            return _safe_eval_arithmetic(expr)
    return None


DEFAULT_CHECKERS: list[Checker] = [
    TaskSpecChecker(),
    ContextChecker(),
    OutputContractChecker(),
    OracleChecker(),
    EvaluatorChecker(),
]
