from __future__ import annotations

import ast
import operator
import re
from pathlib import Path
from typing import Any, Iterable

from .evaluators import (
    item_scoring,
    answer_contract,
    CARDINALITY_ALTERNATIVES,
    MULTI_VALUE_CARDINALITIES,
    answer_variants,
    choice_label_to_index,
    evaluate_answer,
    infer_evaluator_type,
    normalize_choice_for_duplicate,
    parse_number,
    scores_a_scalar_answer,
    scoring_comparison,
    NON_SCALAR_COMPARISONS,
)
from .benchmark_profile import task_is_a_question
from .schema import BenchmarkItem, Violation
from .taxonomy import DEFECTS
from .promotion import enforce_promotion_policy
from .coverage import AuditEligibility


REFERENCE_PATTERNS = {
    "passage": re.compile(r"\b(passage|article|paragraph|text above|above text)\b", re.I),
    # A demonstrative is required, as for tables: "figure" is an ordinary
    # English word ("figure skating", "figure out", "a public figure") and a
    # bare match produced false findings on prose that referenced no artifact.
    "figure": re.compile(
        r"\b(figure|diagram|chart|plot|screenshot|image)\s+"
        r"(above|below|shown|provided|attached)\b|"
        r"\b(attached|provided|following|shown|uploaded)\s+"
        r"(figure|diagram|chart|plot|screenshot|image)\b|"
        r"\bin\s+(figure|diagram|chart)\s*\d",
        re.I,
    ),
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
    message: str,
    evidence: dict[str, Any] | None = None,
    *,
    # Keyword-only and absent by default: a detector that cannot name a model
    # as the source of a number has no confidence to report, and cannot supply
    # one by accident.
    confidence: float | None = None,
    severity: str | None = None,
    review_only: bool | None = None,
    repair: str | None = None,
    method: str = "static_rule",
    scope: str = "substantive",
    artifact: str | None = None,
) -> Violation:
    info = DEFECTS[defect_type]
    chosen_severity = severity or info.default_severity
    violation = Violation(
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
        row_uid=item.row_uid,
        source_row_sha256=item.source_row_sha256,
    )
    return enforce_promotion_policy(violation, item)


class Checker:
    name = "checker"

    def audit_eligibility(
        self,
        item: BenchmarkItem,
        root: Path | None = None,
    ) -> AuditEligibility:
        """Return explicit applicability when a checker can prove it.

        Existing checkers historically used an empty iterable for both
        inapplicability and a completed no-finding run.  The conservative
        compatibility default therefore keeps eligibility unknown while still
        allowing the check to run.  New checkers should override this method.
        """

        return AuditEligibility.unknown()

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        raise NotImplementedError


class TaskSpecChecker(Checker):
    name = "task_specification"

    def audit_eligibility(self, item, root=None) -> AuditEligibility:
        return AuditEligibility.applicable(
            "task presence and specification integrity are defined for every canonical item"
        )

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        task = _text(item.task).strip()
        if not task:
            yield _violation(
                item,
                "missing_task",
                "Task specification is missing.",
                {
                    "evidence_level": "canonical_task_absence",
                    "proof_schema_version": "1.0",
                },
                repair="Add a question, instruction, or problem statement.",
            )
            return
        # Only the declared-but-empty case is decided here.
        #
        # Whether prose *is* the referenced material or merely describes it
        # needs semantics, and "figure" is an ordinary English word; three
        # rounds of pattern work on one held-out benchmark went 244 -> 242 ->
        # 240 -> 137 false findings without converging.  That judgement now
        # belongs to the clarity auditor, which reports `missing_context` and no
        # longer has to win a single status slot to do so.
        #
        # A benchmark that declares a context field has stated the material is
        # a separate artifact, so an empty field is a checkable omission and
        # stays here.
        for context_name, pattern in REFERENCE_PATTERNS.items():
            if not pattern.search(task):
                continue
            # Material that cannot live in prose -- an image, an upload, a
            # database -- is missing whenever nothing is attached, which is a
            # factual observation.  Material that can be inline is left to the
            # clarity auditor: deciding whether prose *is* the passage or only
            # describes it needs semantics, and a key-name match cannot stand
            # in for that.
            if context_name in INLINE_CAPABLE_CONTEXT:
                continue
            source = locate_referenced_context(item, task, context_name)
            if source != "not_found":
                continue
            yield _violation(
                item,
                "missing_context",
                f"Task references {context_name}, but it is neither attached nor in the task text.",
                {
                    "reference_type": context_name,
                    "context_source": source,
                    "task_excerpt": task[:240],
                },
                repair=f"Attach the referenced {context_name} or remove the reference.",
            )
        # Time-sensitive wording only threatens an answer when the task asks
        # for one.  In an instruction, "the current release" specifies the work.
        if task_is_a_question(item) is False:
            return
        for pattern in AMBIGUITY_PATTERNS:
            if pattern.search(task) and not any(k in item.metadata for k in ("source", "version", "date", "domain")):
                yield _violation(
                    item,
                    "ambiguous_goal",
                    "Task contains context-sensitive wording but lacks source/version/domain metadata.",
                    {"matched_pattern": pattern.pattern, "task_excerpt": task[:240]},
                    severity="review",
                    repair="Add explicit time, source, domain, jurisdiction, or intended convention when answer-changing.",
                )


class ContextChecker(Checker):
    name = "context_attachment"

    def audit_eligibility(self, item, root=None) -> AuditEligibility:
        return AuditEligibility.applicable(
            "context attachment and version checks accept empty or populated context"
        )

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
                        f"Referenced attachment does not exist: {candidate}",
                        {"field": key, "path": candidate},
                        repair="Fix the attachment path or include the missing artifact.",
                    )
        if task_is_a_question(item) is False:
            return
        task = _text(item.task)
        if re.search(r"\b(as of|version|release|updated|latest|current)\b", task, re.I):
            has_version = any(k.lower() in {"version", "source", "date", "release"} for k in item.metadata)
            if not has_version:
                yield _violation(
                    item,
                    "context_version_mismatch_risk",
                    "Task appears version-sensitive but no source/version metadata was found.",
                    {"task_excerpt": task[:240]},
                    severity="review",
                    repair="Record source, release, timestamp, or benchmark version metadata.",
                )


class OutputContractChecker(Checker):
    name = "expected_output"

    def audit_eligibility(self, item, root=None) -> AuditEligibility:
        return AuditEligibility.applicable(
            "output-contract presence and consistency are defined for every canonical item"
        )

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if (
            item.output_contract in (None, "", [], {})
            and not item.choices
            and item.evaluator in (None, "", [], {})
        ):
            yield _violation(
                item,
                "missing_output_contract",
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
                    "Numeric task mentions units, but the output contract does not state unit handling.",
                    {"gold": item.gold, "task_excerpt": task[:240]},
                    severity="review",
                    repair="Declare whether units are required, optional, or normalized by the evaluator.",
                )


class OracleChecker(Checker):
    name = "oracle_ground_truth"

    def audit_eligibility(self, item, root=None) -> AuditEligibility:
        # This checker audits a scalar reference answer.  A benchmark scored by
        # running tests, applying a rubric, or inspecting an end state has none
        # by design, and reporting that absence would be a false finding on
        # every one of its rows.  Two things can establish that, and the ledger
        # should say which one did.
        if scoring_comparison(item_scoring(item)) in NON_SCALAR_COMPARISONS:
            return AuditEligibility.not_applicable(
                "the benchmark's profiled scoring judges no scalar answer, so "
                "there is no reference oracle for this checker to audit"
            )
        if scores_a_scalar_answer(item) is False:
            return AuditEligibility.not_applicable(
                "no record in this benchmark carries a gold, so it is not "
                "scored against reference answers"
            )
        return AuditEligibility.applicable(
            "oracle presence and basic validity are defined for every scalar-answer item profile"
        )

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if item.gold in (None, ""):
            yield _violation(
                item,
                "missing_oracle",
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
                    "Gold choice cannot be mapped to the available answer choices.",
                    {
                        "gold": item.gold,
                        "choices": item.choices,
                        "evidence_level": "choice_gold_domain_replay",
                        "proof_schema_version": "1.0",
                    },
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
                "Simple executable arithmetic evidence disagrees with the gold answer.",
                {
                    "gold": item.gold,
                    "computed_value": arithmetic_value,
                    "task": item.task,
                    "safe_expression_replayed": True,
                    "evidence_level": "safe_arithmetic_replay",
                    "proof_schema_version": "1.0",
                },
                repair="Review and correct the gold answer or reference solution.",
            )


class EvaluatorChecker(Checker):
    name = "evaluator"

    def audit_eligibility(self, item, root=None) -> AuditEligibility:
        return AuditEligibility.applicable(
            "evaluator presence and declared answer behavior are defined for every canonical item"
        )

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        contract = answer_contract(
            item.gold, item.choices, item.evaluator, item.output_contract,
            scoring=item_scoring(item),
        )
        inferred = (
            contract["cardinality"]
            if contract["cardinality"] in MULTI_VALUE_CARDINALITIES
            else contract["kind"]
        )
        evaluator_missing = item.evaluator in (None, "", [], {})
        has_gold = item.gold not in (None, "")
        has_output_contract = item.output_contract not in (None, "", [], {})
        if evaluator_missing and (has_gold or has_output_contract):
            # Agent benchmarks commonly have no scalar gold: tests/rubrics are
            # the oracle. A declared output contract without any evaluator is
            # therefore a structural scoring gap, not merely a generic review
            # risk. This also makes remove_evaluator mutations observable
            # without consulting synthetic provenance metadata.
            is_agent_contract = has_output_contract and not has_gold
            severity = (
                "major"
                if is_agent_contract
                else (
                    "minor"
                    if inferred in {"choice", "numeric", "normalized_exact",
                                    CARDINALITY_ALTERNATIVES}
                    else "major"
                )
            )
            yield _violation(
                item,
                "missing_evaluator",
                (
                    "An output contract is declared, but no evaluator/tests/rubric can determine success."
                    if is_agent_contract
                    else f"No explicit evaluator was found; inferred evaluator type is {inferred}."
                ),
                {
                    "inferred_evaluator": inferred,
                    "output_contract": item.output_contract,
                    "agent_style_contract": is_agent_contract,
                },
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
            item_scoring(item),
        ):
            if not evaluate_answer(variant, item.gold, item.choices, item.evaluator, scoring=item_scoring(item)):
                rejected.append({"variant_description": description, "variant": variant})
        alias_rejected = []
        if contract["cardinality"] != "set":
            for alias in item.aliases:
                if not evaluate_answer(
                    alias,
                    item.gold,
                    item.choices,
                    item.evaluator,
                    aliases=list(item.aliases),
                ):
                    alias_rejected.append(alias)
        if alias_rejected:
            yield _violation(
                item,
                "overstrict_evaluator",
                "Evaluator rejects declared accepted answer aliases.",
                {
                    "aliases_rejected": alias_rejected,
                    "gold": item.gold,
                    "evaluator": item.evaluator,
                    "evidence_level": "declared_alias_replay",
                    "proof_schema_version": "1.0",
                },
                repair="Update evaluator normalization or accepted-alternative handling.",
            )
        elif rejected and inferred in {"exact"}:
            yield _violation(
                item,
                "output_format_overstrict_risk",
                "Exact evaluator rejects format-preserving variants of the gold answer.",
                {"rejected_variants": rejected[:5], "gold": item.gold, "evaluator": item.evaluator},
                severity="review",
                repair="Use normalized exact match, answer extraction, or accepted aliases.",
            )
        if evaluator_missing and not has_output_contract and not item.choices:
            yield _violation(
                item,
                "underconstrained_evaluator_risk",
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


# Material that can legitimately live inside the task text.  A figure, an
# uploaded file or a database cannot, so for those the artifact check stands.
INLINE_CAPABLE_CONTEXT = {"passage": 100, "table": 40}

# Labels that introduce inline material.  Kept because an explicit label is
# stronger evidence than length alone -- but no longer the only signal, since
# a phrase list can never be complete: "Context:" was absent and produced 242
# false "missing context" findings on one held-out benchmark.
# A labelled material block is `<material word> [optional ordinal] <separator>`.
# The rule is structural rather than a phrase list: enumerating labels never
# converges -- "Context:" was missing and cost 244 false findings, then
# "Paragraph A:" was missing and cost 236 more.  The ordinal group covers
# "Paragraph A:", "Document 1:", "Passage II:", "Source (b):" in one rule.
#
# It still cannot cover unlabelled inline material, non-English labels, or
# blocks delimited only by rules such as "---".  That is the ceiling of a
# deterministic layer here, not a gap to be closed by another pattern.
_MATERIAL_WORDS = (
    "context|passage|paragraph|article|document|excerpt|snippet|text|table|source"
)
_MATERIAL_ORDINAL = r"(?:\s*(?:[a-z0-9]{1,3}|\([a-z0-9]{1,3}\)|\[[a-z0-9]{1,3}\]|#\d{1,3}))?"
_INLINE_CONTEXT_LABELS = re.compile(
    rf"\b(?:{_MATERIAL_WORDS})\b{_MATERIAL_ORDINAL}\s*[:\-\u2013\u2014]\s*"
    r"|\b(?:following information|following passage|passage below|text below|"
    r"table below|following table)\b\s*[:.\-]?\s*",
    re.I,
)


def _has_embedded_context(task: str, context_name: str) -> bool:
    """Is the referenced material present in the task itself, under a label?

    The task statement is the most basic context a benchmark can carry and many
    datasets ship nothing else, so this is checked before any attached
    artifact.  Only an explicit label counts.  An earlier version also accepted
    "enough text remains after removing the referencing sentence", but length
    is a bad proxy for presence: a task that merely *describes* a passage at
    length passed, hiding a genuine omission, while a short inline passage
    still failed.  Deciding whether prose *is* the material or merely talks
    about it needs semantics, which belongs to the LLM layer.
    """

    minimum = INLINE_CAPABLE_CONTEXT.get(context_name)
    if minimum is None:
        return False
    label = _INLINE_CONTEXT_LABELS.search(task)
    return bool(label and len(task[label.end():].strip()) >= minimum)



def locate_referenced_context(
    item: BenchmarkItem, task: str, context_name: str
) -> str:
    """Where the referenced material was found: task text, artifact, or nowhere.

    Whether an attached artifact is the *right* material cannot be decided
    without semantics, so any non-empty match counts as present.  Requiring the
    key name to correspond exactly would make this layer assert something it
    cannot determine -- the same mistake that produced the alias false
    positives.  A deterministic checker may claim "nothing is here"; it may not
    claim "the wrong thing is here".
    """

    if _has_embedded_context(task, context_name):
        return "task_text"
    if _has_context(item, context_name):
        return "attached_artifact"
    return "not_found"


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
