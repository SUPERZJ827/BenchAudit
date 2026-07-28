"""Deterministic, review-routing-only detection of hidden exact constraints."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Iterable


_QUOTED_PATTERNS = (
    re.compile(r"`([^`\n]{2,180})`"),
    re.compile(r'"([^"\n]{2,180})"'),
    re.compile(r"“([^”\n]{2,180})”"),
    re.compile(r"‘([^’\n]{2,180})’"),
    re.compile(r"「([^」\n]{2,180})」"),
)
_FORCE_CUE = re.compile(
    r"\b(?:exact(?:ly)?|named|called|titled|must|shall|required|specific)\b"
    r"|精确|准确|必须|命名为|名为|标题为|列名|字段名",
    re.IGNORECASE,
)
_COLUMN_CUE = re.compile(
    r"\b(?:column|header|field|worksheet|sheet)\b|列名|字段名|表头|工作表",
    re.IGNORECASE,
)
_SECTION_CUE = re.compile(
    r"\b(?:section|chapter|slide|page|title|heading)\b|章节|小节|幻灯片|页面|标题",
    re.IGNORECASE,
)
_FILENAME_CUE = re.compile(
    r"\b(?:filename|file\s+(?:named|called)|(?:named|called)\s+file)\b"
    r"|文件名|文件命名为|命名文件",
    re.IGNORECASE,
)
_ORDER_CUE = re.compile(
    r"\b(?:order|ordering|sequence|first|last|before|after)\b|顺序|排序|首先|最后",
    re.IGNORECASE,
)
_LANGUAGE_CUE = re.compile(
    r"\b(?:language|english|chinese|bilingual)\b|语言|英文|中文|双语",
    re.IGNORECASE,
)
_EXACT_COUNT = re.compile(
    r"(?:exactly|must contain|requires?|总共|恰好|必须包含)\s*"
    r"(\d{1,5})\s*(?:rows?|columns?|sections?|slides?|pages?|items?|条|行|列|页)",
    re.IGNORECASE,
)
_FILE_LITERAL = re.compile(
    r"(?i)\.(?:txt|md|csv|json|xlsx?|docx?|pptx?|pdf|html?|zip)$"
)
_GENERIC_LITERALS = {
    "yes", "no", "true", "false", "output", "report", "table", "document",
}


def normalize_visible_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(value.split())


@dataclass(frozen=True)
class ExactConstraintRoute:
    rubric_index: int
    selected: bool
    reason_codes: tuple[str, ...]
    unmatched_literals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _literal_reason_codes(rubric: str, literal: str) -> set[str]:
    codes = {"quoted_literal", "literal_mismatch"}
    if _COLUMN_CUE.search(rubric):
        codes.add("column_header")
    if _SECTION_CUE.search(rubric):
        codes.add("section_name")
    if _FILENAME_CUE.search(rubric) or _FILE_LITERAL.search(literal.strip()):
        codes.add("filename")
    if _ORDER_CUE.search(rubric):
        codes.add("ordering")
    if _LANGUAGE_CUE.search(rubric):
        codes.add("language_requirement")
    return codes


def _quoted_literals(rubric: str) -> list[str]:
    literals = []
    for pattern in _QUOTED_PATTERNS:
        literals.extend(match.group(1).strip() for match in pattern.finditer(rubric))
    result = []
    seen = set()
    for literal in literals:
        normalized = normalize_visible_text(literal)
        if (
            not normalized
            or normalized in _GENERIC_LITERALS
            or normalized in seen
        ):
            continue
        seen.add(normalized)
        result.append(literal)
    return result


def route_exact_constraint(
    *,
    rubric_index: int,
    rubric: str,
    task: str,
    output_contract: Any,
    allowed_input_evidence: str,
) -> ExactConstraintRoute:
    visible = normalize_visible_text(
        "\n".join((
            task or "",
            json.dumps(output_contract, ensure_ascii=False, default=str),
            allowed_input_evidence or "",
        ))
    )
    reasons: set[str] = set()
    unmatched = []

    if _FORCE_CUE.search(rubric):
        for literal in _quoted_literals(rubric):
            if normalize_visible_text(literal) not in visible:
                unmatched.append(literal)
                reasons.update(_literal_reason_codes(rubric, literal))

    for match in _EXACT_COUNT.finditer(rubric):
        count = match.group(1)
        if not re.search(rf"(?<!\d){re.escape(count)}(?!\d)", visible):
            reasons.update(("exact_count", "literal_mismatch"))
            unmatched.append(count)

    if _ORDER_CUE.search(rubric) and _FORCE_CUE.search(rubric):
        normalized_rubric = normalize_visible_text(rubric)
        order_terms = [
            term for term in ("first", "last", "before", "after", "首先", "最后")
            if term in normalized_rubric and term not in visible
        ]
        if order_terms:
            reasons.add("ordering")
            unmatched.extend(order_terms)

    if _LANGUAGE_CUE.search(rubric) and _FORCE_CUE.search(rubric):
        normalized_rubric = normalize_visible_text(rubric)
        language_terms = [
            term for term in ("english", "chinese", "bilingual", "英文", "中文", "双语")
            if term in normalized_rubric and term not in visible
        ]
        if language_terms:
            reasons.add("language_requirement")
            unmatched.extend(language_terms)

    unique_unmatched = tuple(dict.fromkeys(unmatched))
    return ExactConstraintRoute(
        rubric_index=rubric_index,
        selected=bool(reasons),
        reason_codes=tuple(sorted(reasons)),
        unmatched_literals=unique_unmatched,
    )


def route_exact_constraints(
    entries: Iterable[tuple[int, str]],
    *,
    task: str,
    output_contract: Any,
    allowed_input_evidence: str,
) -> dict[int, ExactConstraintRoute]:
    return {
        index: route_exact_constraint(
            rubric_index=index,
            rubric=rubric,
            task=task,
            output_contract=output_contract,
            allowed_input_evidence=allowed_input_evidence,
        )
        for index, rubric in entries
    }
