"""Deterministic A-double-prime routing over cached Workspace A-prime rows.

The rules in this module never establish a benchmark defect.  They inspect a
model-produced *rejection* and look for mechanically observable constraint
residue between the rubric and actor-visible sources.  Every emitted
observation is review-only and is consumed only by the offline experiment
driver.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


SPEC_VERSION = "workspace-grounding-a-double-prime-residue-v1-20260729"
APPLICABLE_REASONS = frozenset({
    "task_supported",
    "input_supported",
    "output_contract_supported",
    "general_quality",
})
R2B_EXTRA_REASONS = frozenset({"mechanically_derivable"})
POSITIVE_SUPPORT_REASONS = frozenset({
    "task_supported",
    "input_supported",
    "output_contract_supported",
})

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_COUNT_HEADS = (
    "charts?|sections?|suggestions?|categories?|slides?|pages?|items?|rows?|"
    "columns?|files?|recommendations?|points?|parts?|chapters?|headings?|"
    "records?|months?|figures?|panels?|metrics?|risk points?"
)
_COUNT_RE = re.compile(
    rf"\b(?:(?P<quantifier>exactly|at\s+least|at\s+most|no\s+fewer\s+than|"
    rf"no\s+more\s+than|minimum\s+of|maximum\s+of)\s+)?"
    rf"(?P<count>\d{{1,5}}|{'|'.join(_NUMBER_WORDS)})\s+"
    rf"(?:(?:specific|named|major|first-level|distinct|total|visual|"
    rf"improvement|actionable|concrete|bar|pie|donut|line|scatter|stacked|"
    rf"gantt|heatmap|radar|area|bubble|waterfall|timeline|histogram)\s+)*"
    rf"(?P<head>{_COUNT_HEADS})\b",
    re.IGNORECASE,
)
_ALL_RE = re.compile(
    rf"\b(?P<quantifier>all|every|each)\s+"
    rf"(?:(?:specified|named|input|visible|required)\s+)*"
    rf"(?P<head>{_COUNT_HEADS})\b",
    re.IGNORECASE,
)
_ORDER_PATTERNS = (
    re.compile(
        r"\b(?P<relation>first|last)\s+"
        r"(?P<object>slide|page|section|row|column|panel|part|chapter)\b"
        r"(?P<middle>.{0,100}?)\b(?:from|with|is|be|come\s+from|contain)\s+"
        r"(?P<anchor>[A-Za-z0-9][A-Za-z0-9 _./-]{0,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<object>[A-Za-z0-9][A-Za-z0-9 _./-]{0,80}?)\s+"
        r"(?P<relation>before|after)\s+"
        r"(?P<anchor>[A-Za-z0-9][A-Za-z0-9 _./-]{0,80})",
        re.IGNORECASE,
    ),
)
_ORDER_CUE_RE = re.compile(
    r"\b(first|last|before|after)\b|第一个|最后一个|之前|之后",
    re.IGNORECASE,
)
_DELEGATION_RE = re.compile(
    r"\b(?:include|cover|extract|summari[sz]e|process|use|preserve)\s+"
    r"(?:all|every|each)\b|\b(?:all|every|each)\b.{0,60}"
    r"\b(?:must|shall|should|include|cover|appear)\b",
    re.IGNORECASE,
)
_STRUCTURE_HEAD_RE = re.compile(
    r"\b(sections?|categories?|parts?|chapters?|slides?|headings?|"
    r"suggestions?|recommendations?)\b",
    re.IGNORECASE,
)
_LIST_INTRO_RE = re.compile(
    r"\b(?:include|includes|including|contain|contains|cover|covering|"
    r"divided\s+into|consist(?:s|ing)?\s+of|sections?\s+for)\b",
    re.IGNORECASE,
)
_NP_HEADS = frozenset({
    "chart",
    "graph",
    "plot",
    "diagram",
    "dashboard",
    "report",
    "table",
    "visualization",
})
_CONTENT_MODIFIERS = frozenset({
    "bar",
    "pie",
    "donut",
    "line",
    "scatter",
    "stacked",
    "gantt",
    "heatmap",
    "radar",
    "area",
    "bubble",
    "waterfall",
    "timeline",
    "histogram",
})
_NP_STOP_WORDS = frozenset({
    "a",
    "an",
    "the",
    "this",
    "that",
    "was",
    "were",
    "is",
    "are",
    "be",
    "been",
    "being",
    "create",
    "created",
    "generate",
    "generated",
    "include",
    "includes",
    "with",
    "of",
    "and",
    "or",
})
_NP_POST_HEAD_WORDS = frozenset({
    "generated",
    "created",
    "inserted",
    "rendered",
    "shown",
    "displayed",
    "based",
    "with",
    "for",
    "from",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
})


@dataclass(frozen=True)
class TextSpan:
    text: str
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QuantityAtom:
    quantifier: str
    count: int | None
    object_head: str
    closed_members: tuple[str, ...]
    span: TextSpan

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class DerivationCertificate:
    derivation_id: str
    object_head: str
    count: int | None
    closed_members: tuple[str, ...] = ()
    premise_spans: tuple[str, ...] = ()
    proof_basis: str = ""
    version: str = "v1"

    def covers(self, atom: QuantityAtom) -> bool:
        if singular(self.object_head) != singular(atom.object_head):
            return False
        if self.count is not None and self.count != atom.count:
            return False
        return not self.closed_members or set(map(normalize_text, self.closed_members)) >= {
            normalize_text(value) for value in atom.closed_members
        }


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    reason: str
    rubric_spans: tuple[TextSpan, ...]
    support_spans: tuple[TextSpan, ...] = ()
    evidence_roles: tuple[str, ...] = ()
    details: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "reason": self.reason,
            "rubric_spans": [row.to_dict() for row in self.rubric_spans],
            "support_spans": [row.to_dict() for row in self.support_spans],
            "evidence_roles": list(self.evidence_roles),
            "details": dict(self.details or {}),
        }


@dataclass(frozen=True)
class ResidueObservation:
    candidate_id: str
    item_id: str
    rubric_index: int
    rule_ids: tuple[str, ...]
    hits: tuple[RuleHit, ...]
    review_only: bool = True
    confirmation_eligible: bool = False
    spec_version: str = SPEC_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "item_id": self.item_id,
            "rubric_index": self.rubric_index,
            "rule_ids": list(self.rule_ids),
            "hits": [row.to_dict() for row in self.hits],
            "review_only": self.review_only,
            "confirmation_eligible": self.confirmation_eligible,
            "spec_version": self.spec_version,
        }


def normalize_text(value: str) -> str:
    """NFKC/casefold text while making punctuation differences non-decisive."""

    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = "".join(
        char if char.isalnum() or char in {"_", "-", "/"} else " "
        for char in value
    )
    return " ".join(value.split())


def normalized_contains(source: str, needle: str) -> bool:
    normalized_needle = normalize_text(needle)
    return bool(normalized_needle and normalized_needle in normalize_text(source))


def singular(value: str) -> str:
    value = normalize_text(value)
    if value.endswith("ies") and len(value) > 3:
        return value[:-3] + "y"
    if value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value


def _number(value: str) -> int:
    normalized = value.casefold()
    return int(normalized) if normalized.isdigit() else _NUMBER_WORDS[normalized]


def _clean_member(value: str) -> str:
    value = value.strip(" \t\r\n,;:.?!")
    value = re.sub(r"^(?:and|or)\s+", "", value, flags=re.I)
    return value.strip()


def _closed_members_after(text: str, start: int) -> tuple[str, ...]:
    tail = text[start:start + 500]
    tail = re.split(r"[?.;\n]", tail, maxsplit=1)[0]
    if ":" in tail:
        tail = tail.split(":", 1)[1]
    elif _LIST_INTRO_RE.search(tail):
        tail = _LIST_INTRO_RE.split(tail, maxsplit=1)[1]
    else:
        return ()
    values = [
        _clean_member(value)
        for value in re.split(r",|\band\b", tail, flags=re.I)
    ]
    values = [
        value
        for value in values
        if 1 < len(value) and len(value.split()) <= 12
    ]
    return tuple(dict.fromkeys(values)) if len(values) >= 2 else ()


def extract_quantity_atoms(text: str) -> tuple[QuantityAtom, ...]:
    atoms: list[QuantityAtom] = []
    for pattern in (_COUNT_RE, _ALL_RE):
        for match in pattern.finditer(text):
            count_value = match.groupdict().get("count")
            quantifier = " ".join(
                str(match.groupdict().get("quantifier") or "exact").split()
            ).casefold()
            head = singular(match.group("head"))
            members = _closed_members_after(text, match.end())
            atoms.append(QuantityAtom(
                quantifier=quantifier,
                count=_number(count_value) if count_value else None,
                object_head=head,
                closed_members=members,
                span=TextSpan(match.group(0), match.start(), match.end()),
            ))
    # A named closed list is a countable obligation even when the prose omits
    # an explicit numeral ("sections for Alpha, Beta, and Gamma").
    for head_match in _STRUCTURE_HEAD_RE.finditer(text):
        members = _closed_members_after(text, head_match.start())
        if len(members) < 2:
            continue
        head = singular(head_match.group(1))
        if any(
            atom.object_head == head
            and atom.span.start <= head_match.start() <= atom.span.end
            for atom in atoms
        ):
            continue
        atoms.append(QuantityAtom(
            quantifier="exact",
            count=len(members),
            object_head=head,
            closed_members=members,
            span=TextSpan(
                text[head_match.start():min(len(text), head_match.start() + 500)],
                head_match.start(),
                min(len(text), head_match.start() + 500),
            ),
        ))
    return tuple(sorted(
        atoms,
        key=lambda atom: (
            atom.span.start,
            atom.span.end,
            atom.object_head,
            atom.count if atom.count is not None else -1,
        ),
    ))


def _quantifier_entails(source: QuantityAtom, target: QuantityAtom) -> bool:
    if singular(source.object_head) != singular(target.object_head):
        return False
    if target.closed_members:
        source_members = {normalize_text(value) for value in source.closed_members}
        if not {normalize_text(value) for value in target.closed_members} <= source_members:
            return False
    if target.count is None:
        return source.quantifier in {"all", "every", "each"}
    if source.count is None:
        return False
    source_q = source.quantifier
    target_q = target.quantifier
    if target_q in {"at least", "no fewer than", "minimum of"}:
        return (
            source.count >= target.count
            and source_q not in {"at most", "no more than", "maximum of"}
        )
    if target_q in {"at most", "no more than", "maximum of"}:
        return (
            source.count <= target.count
            and source_q not in {"at least", "no fewer than", "minimum of"}
        )
    return source.count == target.count and source_q in {"exact", "exactly"}


def _same_head_atoms(
    atom: QuantityAtom,
    source_atoms: Iterable[QuantityAtom],
) -> tuple[QuantityAtom, ...]:
    return tuple(
        source
        for source in source_atoms
        if singular(source.object_head) == singular(atom.object_head)
    )


def default_derivation_certificates(task: str) -> tuple[DerivationCertificate, ...]:
    """Return the deliberately tiny, versioned v1 certificate registry."""

    certificates: list[DerivationCertificate] = []
    if re.search(r"\b(?:full|entire)\s+(?:calendar\s+)?year\b|全年", task, re.I):
        certificates.append(DerivationCertificate(
            derivation_id="calendar_year_to_month_count_v1",
            object_head="month",
            count=12,
            premise_spans=("full year",),
            proof_basis="closed_calendar_definition",
        ))
    return tuple(certificates)


def _source_texts(
    *,
    task: str,
    output_contract: Any,
    input_inventory: str,
    input_text: str,
) -> dict[str, str]:
    return {
        "task": task or "",
        "output_contract": json.dumps(
            output_contract, ensure_ascii=False, sort_keys=True, default=str,
        ),
        "input_inventory": input_inventory or "",
        "input": input_text or "",
        "intrinsic": "",
        "none": "",
    }


def positive_support_diagnostic(
    route: Mapping[str, Any],
    source_texts: Mapping[str, str],
) -> dict[str, Any] | None:
    reason_code = str(route.get("reason_code") or "")
    if reason_code not in POSITIVE_SUPPORT_REASONS:
        return None
    source = str(route.get("evidence_source") or "none")
    quote = str(route.get("evidence_quote") or "")
    if not quote:
        status = "invalid"
        diagnostic_reason = "empty_quote"
    elif not source_texts.get(source):
        status = "unknown"
        diagnostic_reason = "declared_source_text_unavailable"
    elif normalized_contains(source_texts[source], quote):
        status = "valid"
        diagnostic_reason = "normalized_source_substring"
    else:
        status = "invalid"
        diagnostic_reason = "quote_not_in_declared_source"
    return {
        "diagnostic": "positive_support_without_valid_quote",
        "status": status,
        "reason_code": reason_code,
        "evidence_source": source,
        "evidence_quote": quote,
        "reason": diagnostic_reason,
        "candidate": False,
    }


def _route_r2a(
    rubric: str,
    normative_text: str,
    route: Mapping[str, Any],
) -> RuleHit | None:
    if str(route.get("reason_code") or "") not in APPLICABLE_REASONS:
        return None
    if not _ORDER_CUE_RE.search(rubric):
        return None
    matches = [
        match
        for pattern in _ORDER_PATTERNS
        for match in pattern.finditer(rubric)
    ]
    if len(matches) != 1:
        return None
    match = matches[0]
    relation = match.group("relation")
    anchor = _clean_member(match.group("anchor"))
    anchor = re.split(r"\b(?:and|but|while)\b", anchor, maxsplit=1, flags=re.I)[0]
    if not anchor or len(anchor.split()) > 10:
        return None
    if (
        normalize_text(relation) in normalize_text(normative_text)
        and normalized_contains(normative_text, anchor)
    ):
        return None
    return RuleHit(
        rule_id="R2a",
        reason="unsupported_order_or_position",
        rubric_spans=(TextSpan(match.group(0), match.start(), match.end()),),
        evidence_roles=("task", "output_contract"),
        details={
            "relation": normalize_text(relation),
            "anchor": anchor,
        },
    )


def _route_r2b(
    rubric: str,
    task: str,
    output_contract_text: str,
    input_inventory: str,
    input_text: str,
    route: Mapping[str, Any],
    certificates: Iterable[DerivationCertificate],
) -> tuple[RuleHit, ...]:
    reason_code = str(route.get("reason_code") or "")
    if reason_code not in (APPLICABLE_REASONS | R2B_EXTRA_REASONS):
        return ()
    rubric_atoms = extract_quantity_atoms(rubric)
    if not rubric_atoms:
        return ()
    normative_atoms = extract_quantity_atoms(
        f"{task}\n{output_contract_text}",
    )
    descriptive_atoms = extract_quantity_atoms(
        f"{input_inventory}\n{input_text}\n"
        f"{route.get('evidence_quote') or ''}"
    )
    delegated = bool(_DELEGATION_RE.search(task))
    certificate_rows = tuple(certificates)
    hits: list[RuleHit] = []
    for atom in rubric_atoms:
        same_normative = _same_head_atoms(atom, normative_atoms)
        if any(_quantifier_entails(source, atom) for source in same_normative):
            continue
        if any(certificate.covers(atom) for certificate in certificate_rows):
            continue
        if delegated and _same_head_atoms(atom, descriptive_atoms):
            continue
        source = str(route.get("evidence_source") or "")
        same_descriptive = _same_head_atoms(atom, descriptive_atoms)
        if (
            not same_descriptive
            and source in {"input", "input_inventory"}
            and atom.count is not None
        ):
            quote = str(route.get("evidence_quote") or "")
            members = tuple(
                dict.fromkeys(
                    value
                    for value in (
                        _clean_member(part)
                        for part in re.split(r",|\band\b", quote, flags=re.I)
                    )
                    if len(value) > 1
                )
            )
            if len(members) >= atom.count:
                same_descriptive = (QuantityAtom(
                    quantifier="exact",
                    count=len(members),
                    object_head=atom.object_head,
                    closed_members=members,
                    span=TextSpan(quote, 0, len(quote)),
                ),)
        if same_descriptive and source in {"input", "input_inventory"}:
            reason = "descriptive_input_not_normative_obligation"
            role = source
        else:
            reason = "unsupported_quantity_without_source"
            role = "none" if not same_normative else "conflicting_normative_value"
        hits.append(RuleHit(
            rule_id="R2b",
            reason=reason,
            rubric_spans=(atom.span,),
            evidence_roles=(role,),
            details={
                "atom": atom.to_dict(),
                "conflicting_normative_atoms": [
                    row.to_dict() for row in same_normative
                ],
                "descriptive_atoms": [
                    row.to_dict() for row in same_descriptive
                ],
                "derivation_certificate": None,
            },
        ))
    return tuple(hits)


def _word_tokens_with_offsets(text: str) -> list[tuple[str, int, int]]:
    return [
        (match.group(0), match.start(), match.end())
        for match in re.finditer(r"[A-Za-z][A-Za-z-]*", text)
    ]


def extract_noun_phrases(text: str) -> tuple[dict[str, Any], ...]:
    """Parse a deliberately restricted English modifier/head grammar."""

    tokens = _word_tokens_with_offsets(text)
    phrases: list[dict[str, Any]] = []
    for index, (token, start, end) in enumerate(tokens):
        head = token.casefold()
        if head not in _NP_HEADS:
            continue
        if index + 1 < len(tokens):
            next_token, next_start, _ = tokens[index + 1]
            between = text[end:next_start]
            if (
                not re.search(r"[,;:.?!]", between)
                and next_token.casefold() not in _NP_POST_HEAD_WORDS
            ):
                # In "chart title", chart is a modifier of title, not the head.
                continue
        left = tokens[max(0, index - 4):index]
        # Do not cross coarse punctuation or clause boundaries.
        phrase_start = start
        modifiers: list[str] = []
        for candidate, candidate_start, candidate_end in reversed(left):
            between = text[candidate_end:phrase_start]
            if re.search(r"[,;:.?!]|\b(?:and|or|but)\b", between, re.I):
                break
            normalized = candidate.casefold()
            if normalized in _NP_STOP_WORDS:
                break
            modifiers.insert(0, normalized)
            phrase_start = candidate_start
        content = tuple(
            value for value in modifiers if value in _CONTENT_MODIFIERS
        )
        phrases.append({
            "head": head,
            "modifiers": tuple(modifiers),
            "content_modifiers": content,
            "span": TextSpan(text[phrase_start:end], phrase_start, end),
        })
    return tuple(phrases)


def _route_r2c(
    rubric: str,
    normative_text: str,
    route: Mapping[str, Any],
) -> RuleHit | None:
    if str(route.get("reason_code") or "") not in APPLICABLE_REASONS:
        return None
    rubric_phrases = [
        phrase for phrase in extract_noun_phrases(rubric)
        if phrase["content_modifiers"]
    ]
    support_phrases = extract_noun_phrases(normative_text)
    candidates: list[tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]] = []
    for rubric_phrase in rubric_phrases:
        same_head = [
            phrase for phrase in support_phrases
            if phrase["head"] == rubric_phrase["head"]
        ]
        if len(same_head) != 1:
            continue
        support = same_head[0]
        residual = tuple(
            value
            for value in rubric_phrase["content_modifiers"]
            if value not in support["modifiers"]
        )
        if residual:
            candidates.append((rubric_phrase, support, residual))
    if len(candidates) != 1:
        return None
    rubric_phrase, support, residual = candidates[0]
    return RuleHit(
        rule_id="R2c",
        reason="unsupported_subtype_modifier",
        rubric_spans=(rubric_phrase["span"],),
        support_spans=(support["span"],),
        evidence_roles=("task", "output_contract"),
        details={
            "rubric_head": rubric_phrase["head"],
            "support_head": support["head"],
            "rubric_modifiers": list(rubric_phrase["modifiers"]),
            "support_modifiers": list(support["modifiers"]),
            "residual_modifiers": list(residual),
        },
    )


def _named_structure(rubric: str) -> tuple[str, tuple[str, ...], TextSpan] | None:
    head_match = _STRUCTURE_HEAD_RE.search(rubric)
    if not head_match:
        return None
    members = _closed_members_after(rubric, head_match.start())
    if len(members) < 2:
        return None
    end = min(len(rubric), head_match.start() + 500)
    return (
        singular(head_match.group(1)),
        members,
        TextSpan(rubric[head_match.start():end], head_match.start(), end),
    )


def _route_r2d(
    rubric: str,
    normative_text: str,
    route: Mapping[str, Any],
) -> RuleHit | None:
    if str(route.get("reason_code") or "") not in APPLICABLE_REASONS:
        return None
    parsed = _named_structure(rubric)
    if parsed is None:
        return None
    head, members, span = parsed
    if all(normalized_contains(normative_text, member) for member in members):
        return None
    if _DELEGATION_RE.search(normative_text) and re.search(
        rf"\b{re.escape(head)}s?\b", normative_text, re.I,
    ):
        return None
    unsupported = tuple(
        member for member in members
        if not normalized_contains(normative_text, member)
    )
    return RuleHit(
        rule_id="R2d",
        reason="unsupported_named_structure",
        rubric_spans=(span,),
        evidence_roles=("task", "output_contract"),
        details={
            "governing_head": head,
            "members": list(members),
            "unsupported_members": list(unsupported),
        },
    )


def route_constraint_residue(
    *,
    item_id: str,
    rubric_index: int,
    rubric: str,
    route: Mapping[str, Any],
    task: str,
    output_contract: Any,
    input_inventory: str = "",
    input_text: str = "",
    derivation_certificates: Iterable[DerivationCertificate] | None = None,
) -> tuple[ResidueObservation | None, dict[str, Any] | None]:
    """Apply H1 and R2a--R2d without consulting labels or item-specific rules."""

    source_texts = _source_texts(
        task=task,
        output_contract=output_contract,
        input_inventory=input_inventory,
        input_text=input_text,
    )
    h1 = positive_support_diagnostic(route, source_texts)
    if str(route.get("action") or "") != "do_not_route":
        return None, h1
    normative_text = f"{task}\n{source_texts['output_contract']}"
    certificates = (
        tuple(derivation_certificates)
        if derivation_certificates is not None
        else default_derivation_certificates(task)
    )
    hits: list[RuleHit] = []
    r2a = _route_r2a(rubric, normative_text, route)
    if r2a is not None:
        hits.append(r2a)
    hits.extend(_route_r2b(
        rubric,
        task,
        source_texts["output_contract"],
        input_inventory,
        input_text,
        route,
        certificates,
    ))
    r2c = _route_r2c(rubric, normative_text, route)
    if r2c is not None:
        hits.append(r2c)
    r2d = _route_r2d(rubric, normative_text, route)
    if r2d is not None:
        hits.append(r2d)
    if not hits:
        return None, h1
    hits = sorted(hits, key=lambda row: (row.rule_id, row.reason))
    rule_ids = tuple(sorted({row.rule_id for row in hits}))
    stable_payload = {
        "item_id": item_id,
        "rubric_index": rubric_index,
        "rule_ids": rule_ids,
        "hits": [row.to_dict() for row in hits],
        "spec_version": SPEC_VERSION,
    }
    candidate_id = hashlib.sha256(json.dumps(
        stable_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")).hexdigest()
    return ResidueObservation(
        candidate_id=candidate_id,
        item_id=item_id,
        rubric_index=rubric_index,
        rule_ids=rule_ids,
        hits=tuple(hits),
    ), h1
