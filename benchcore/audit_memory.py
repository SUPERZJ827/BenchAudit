"""Leakage-resistant, review-only defect-pattern memory.

The memory stores reusable defect *mechanisms*, not task answers or historical
problem text.  Matching is performed only on explicit structural features
(schema shape, evaluator type, capabilities, and existing audit signals).
Concrete cases are retained solely as provenance and never enter ranking.

A pattern hit is a routing hint: it may prioritize a verifier or an LLM review,
but it is never evidence that the current benchmark is defective.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .schema import BenchmarkItem


MEMORY_SCHEMA_VERSION = "benchcore-defect-pattern-v1"
MEMORY_PROMOTION_CEILING = "review"
ACTIVE_PATTERN_STATUSES = frozenset({
    "paper_reported",
    "observed",
    "reproduced",
    "objective_confirmed",
})
INACTIVE_PATTERN_STATUSES = frozenset({"disputed", "deprecated"})
EVIDENCE_TIERS = frozenset({"paper_reported", "review", "confirmed"})
_STATUS_WEIGHT = {
    "paper_reported": 0.55,
    "observed": 0.65,
    "reproduced": 0.85,
    "objective_confirmed": 1.00,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def normalize_feature(value: Any, field_name: str = "feature") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    normalized = normalize_text(value)
    if len(normalized) > 256:
        raise ValueError(f"{field_name} exceeds 256 characters")
    return normalized


def _nonempty_text(value: Any, field_name: str, *, maximum: int = 8_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    text = value.strip()
    if len(text) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} characters")
    return text


def _optional_text(value: Any, field_name: str, *, maximum: int = 2_000) -> str | None:
    if value in (None, ""):
        return None
    return _nonempty_text(value, field_name, maximum=maximum)


def _feature_set(
    value: Any,
    field_name: str,
    *,
    required: bool = False,
    maximum: int = 128,
) -> frozenset[str]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    if len(value) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} entries")
    result = frozenset(
        normalize_feature(entry, f"{field_name}[{index}]")
        for index, entry in enumerate(value)
    )
    if required and not result:
        raise ValueError(f"{field_name} must contain at least one feature")
    return result


def _text_tuple(
    value: Any,
    field_name: str,
    *,
    required: bool = False,
    maximum: int = 32,
) -> tuple[str, ...]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    if len(value) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} entries")
    result: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(value):
        text = _nonempty_text(entry, f"{field_name}[{index}]", maximum=2_000)
        key = normalize_text(text)
        if key not in seen:
            result.append(text)
            seen.add(key)
    if required and not result:
        raise ValueError(f"{field_name} must contain at least one entry")
    return tuple(result)


@dataclass(frozen=True)
class PatternEvidenceCase:
    """A provenance pointer; case content is deliberately not searchable."""

    case_id: str
    source_type: str
    evidence_tier: str
    dataset: str | None = None
    dataset_family: str | None = None
    item_id: str | None = None
    uri: str | None = None
    content_sha256: str | None = None

    @classmethod
    def from_dict(cls, value: Any) -> "PatternEvidenceCase":
        if not isinstance(value, dict):
            raise ValueError("evidence case must be an object")
        required = {"case_id", "source_type", "evidence_tier"}
        optional = {
            "dataset",
            "dataset_family",
            "item_id",
            "uri",
            "content_sha256",
        }
        missing = required - set(value)
        unknown = set(value) - required - optional
        if missing:
            raise ValueError(f"evidence case is missing fields: {sorted(missing)}")
        if unknown:
            raise ValueError(f"unknown evidence case fields: {sorted(unknown)}")
        tier = _nonempty_text(
            value["evidence_tier"], "evidence_case.evidence_tier", maximum=64,
        )
        if tier not in EVIDENCE_TIERS:
            raise ValueError(f"unsupported evidence tier: {tier}")
        content_sha256 = _optional_text(
            value.get("content_sha256"),
            "evidence_case.content_sha256",
            maximum=64,
        )
        if (
            content_sha256 is not None
            and (
                len(content_sha256) != 64
                or any(character not in "0123456789abcdef" for character in content_sha256)
            )
        ):
            raise ValueError(
                "evidence_case.content_sha256 must be 64 lowercase hex characters"
            )
        dataset = _optional_text(value.get("dataset"), "evidence_case.dataset")
        item_id = _optional_text(value.get("item_id"), "evidence_case.item_id")
        uri = _optional_text(value.get("uri"), "evidence_case.uri", maximum=4_000)
        if uri is None and not (dataset and item_id):
            raise ValueError(
                "evidence case requires uri or both dataset and item_id"
            )
        return cls(
            case_id=_nonempty_text(
                value["case_id"], "evidence_case.case_id", maximum=256,
            ),
            source_type=_nonempty_text(
                value["source_type"], "evidence_case.source_type", maximum=128,
            ),
            evidence_tier=tier,
            dataset=dataset,
            dataset_family=_optional_text(
                value.get("dataset_family"), "evidence_case.dataset_family",
            ),
            item_id=item_id,
            uri=uri,
            content_sha256=content_sha256,
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "case_id": self.case_id,
            "source_type": self.source_type,
            "evidence_tier": self.evidence_tier,
            "dataset": self.dataset,
            "dataset_family": self.dataset_family,
            "item_id": self.item_id,
            "uri": self.uri,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class DefectPattern:
    pattern_id: str
    defect_family: str
    summary: str
    status: str
    required_features: frozenset[str]
    indicative_features: frozenset[str]
    counter_features: frozenset[str]
    verifier_steps: tuple[str, ...]
    evidence_cases: tuple[PatternEvidenceCase, ...]
    schema_version: str = MEMORY_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Any) -> "DefectPattern":
        if not isinstance(value, dict):
            raise ValueError("defect pattern must be an object")
        required = {
            "schema_version",
            "pattern_id",
            "defect_family",
            "summary",
            "status",
            "required_features",
            "indicative_features",
            "counter_features",
            "verifier_steps",
            "evidence_cases",
        }
        missing = required - set(value)
        unknown = set(value) - required
        if missing:
            raise ValueError(f"defect pattern is missing fields: {sorted(missing)}")
        if unknown:
            raise ValueError(f"unknown defect pattern fields: {sorted(unknown)}")
        version = value["schema_version"]
        if version != MEMORY_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported memory schema {version!r}; "
                f"expected {MEMORY_SCHEMA_VERSION!r}"
            )
        status = _nonempty_text(value["status"], "status", maximum=64)
        if status not in ACTIVE_PATTERN_STATUSES | INACTIVE_PATTERN_STATUSES:
            raise ValueError(f"unsupported pattern status: {status}")
        required_features = _feature_set(
            value["required_features"], "required_features", required=True,
        )
        indicative_features = _feature_set(
            value["indicative_features"], "indicative_features",
        )
        counter_features = _feature_set(
            value["counter_features"], "counter_features",
        )
        if (required_features | indicative_features) & counter_features:
            raise ValueError(
                "counter_features cannot overlap required/indicative features"
            )
        raw_cases = value["evidence_cases"]
        if not isinstance(raw_cases, list) or not 1 <= len(raw_cases) <= 64:
            raise ValueError("evidence_cases must contain 1..64 cases")
        cases = tuple(PatternEvidenceCase.from_dict(case) for case in raw_cases)
        case_ids = [case.case_id for case in cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evidence_cases contain duplicate case_id values")
        if status == "objective_confirmed" and not any(
            case.evidence_tier == "confirmed" for case in cases
        ):
            raise ValueError(
                "objective_confirmed pattern requires a confirmed evidence case"
            )
        return cls(
            schema_version=version,
            pattern_id=_nonempty_text(value["pattern_id"], "pattern_id", maximum=256),
            defect_family=_nonempty_text(
                value["defect_family"], "defect_family", maximum=256,
            ),
            summary=_nonempty_text(value["summary"], "summary"),
            status=status,
            required_features=required_features,
            indicative_features=indicative_features,
            counter_features=counter_features,
            verifier_steps=_text_tuple(
                value["verifier_steps"], "verifier_steps", required=True,
            ),
            evidence_cases=cases,
        )

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_PATTERN_STATUSES

    @property
    def trust_weight(self) -> float:
        return _STATUS_WEIGHT.get(self.status, 0.0)

    @property
    def content_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pattern_id": self.pattern_id,
            "defect_family": self.defect_family,
            "summary": self.summary,
            "status": self.status,
            "required_features": sorted(self.required_features),
            "indicative_features": sorted(self.indicative_features),
            "counter_features": sorted(self.counter_features),
            "verifier_steps": list(self.verifier_steps),
            "evidence_cases": [case.to_dict() for case in self.evidence_cases],
        }


class DefectPatternStore:
    def __init__(self, patterns: Iterable[DefectPattern]) -> None:
        ordered = sorted(patterns, key=lambda pattern: pattern.pattern_id)
        ids = [pattern.pattern_id for pattern in ordered]
        duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate pattern_id values: {duplicates}")
        self.patterns = tuple(ordered)
        self.sha256 = canonical_sha256(
            [pattern.to_dict() for pattern in self.patterns]
        )

    @classmethod
    def load_jsonl(cls, path: Path | str) -> "DefectPatternStore":
        source = Path(path)
        patterns: list[DefectPattern] = []
        with source.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    patterns.append(DefectPattern.from_dict(json.loads(line)))
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(
                        f"invalid defect-pattern memory at "
                        f"{source}:{line_number}: {exc}"
                    ) from exc
        if not patterns:
            raise ValueError(f"defect-pattern memory is empty: {source}")
        return cls(patterns)


@dataclass(frozen=True)
class PatternQuery:
    query_id: str
    features: frozenset[str]
    dataset: str | None = None
    dataset_family: str | None = None
    source_case_ids: frozenset[str] = frozenset()
    item_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PatternMatchPolicy:
    allow_same_dataset: bool = False
    allow_same_dataset_family: bool = False
    include_inactive: bool = False
    maximum_per_family: int = 2

    def __post_init__(self) -> None:
        if self.maximum_per_family < 1:
            raise ValueError("maximum_per_family must be >=1")


@dataclass(frozen=True)
class PatternHit:
    pattern: DefectPattern
    score: float
    matched_required_features: tuple[str, ...]
    matched_indicative_features: tuple[str, ...]
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "pattern_id": self.pattern.pattern_id,
            "pattern_sha256": self.pattern.content_sha256,
            "defect_family": self.pattern.defect_family,
            "status": self.pattern.status,
            "score": self.score,
            "matched_required_features": list(self.matched_required_features),
            "matched_indicative_features": list(self.matched_indicative_features),
            "evidence_case_ids": [
                case.case_id for case in self.pattern.evidence_cases
            ],
            "promotion_ceiling": MEMORY_PROMOTION_CEILING,
        }


class DefectPatternMatcher:
    """Exact structural matcher; historical case text is never inspected."""

    def __init__(self, store: DefectPatternStore) -> None:
        self.store = store

    def match(
        self,
        query: PatternQuery,
        *,
        top_k: int = 6,
        policy: PatternMatchPolicy | None = None,
    ) -> list[PatternHit]:
        if top_k < 1:
            raise ValueError("top_k must be >=1")
        policy = policy or PatternMatchPolicy()
        candidates: list[tuple[float, DefectPattern, tuple[str, ...]]] = []
        for pattern in self.store.patterns:
            if not policy.include_inactive and not pattern.is_active:
                continue
            if self._excluded(query, pattern, policy):
                continue
            if not pattern.required_features <= query.features:
                continue
            if pattern.counter_features & query.features:
                continue
            matched_indicative = tuple(sorted(
                pattern.indicative_features & query.features
            ))
            indicative_score = (
                len(matched_indicative) / len(pattern.indicative_features)
                if pattern.indicative_features
                else 0.0
            )
            score = 0.70 + 0.20 * indicative_score + 0.10 * pattern.trust_weight
            candidates.append((score, pattern, matched_indicative))
        candidates.sort(key=lambda row: (-row[0], row[1].pattern_id))

        selected: list[PatternHit] = []
        family_counts: Counter[str] = Counter()
        for score, pattern, matched_indicative in candidates:
            family = normalize_text(pattern.defect_family)
            if family_counts[family] >= policy.maximum_per_family:
                continue
            selected.append(PatternHit(
                pattern=pattern,
                score=score,
                matched_required_features=tuple(sorted(pattern.required_features)),
                matched_indicative_features=matched_indicative,
                rank=len(selected) + 1,
            ))
            family_counts[family] += 1
            if len(selected) >= top_k:
                break
        return selected

    @staticmethod
    def _excluded(
        query: PatternQuery,
        pattern: DefectPattern,
        policy: PatternMatchPolicy,
    ) -> bool:
        query_dataset = normalize_text(query.dataset or "")
        query_family = normalize_text(query.dataset_family or "")
        for case in pattern.evidence_cases:
            if case.case_id in query.source_case_ids:
                return True
            if case.item_id and case.item_id in query.item_ids:
                return True
            if (
                not policy.allow_same_dataset
                and query_dataset
                and normalize_text(case.dataset or "") == query_dataset
            ):
                return True
            if (
                not policy.allow_same_dataset_family
                and query_family
                and normalize_text(case.dataset_family or "") == query_family
            ):
                return True
        return False


def _shape_name(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__.casefold()


def _mapping_descriptor_features(prefix: str, value: Any) -> set[str]:
    features = {f"shape:{prefix}:{_shape_name(value)}"}
    if isinstance(value, Mapping):
        for key in ("type", "format", "mode", "language"):
            child = value.get(key)
            if isinstance(child, (str, int, float, bool)):
                features.add(normalize_feature(f"{prefix}:{key}:{child}"))
    return features


def query_from_item(
    item: BenchmarkItem,
    *,
    signals: Iterable[str] = (),
    extra_features: Iterable[str] = (),
    dataset: str | None = None,
    dataset_family: str | None = None,
) -> PatternQuery:
    """Build a query without task/context/choice/gold values or metadata labels."""

    features: set[str] = set()
    for name in (
        "task",
        "context",
        "choices",
        "gold",
        "aliases",
        "output_contract",
        "evaluator",
    ):
        value = getattr(item, name)
        if value not in (None, "", [], {}):
            features.add(f"field:{name}")
            features.add(f"shape:{name}:{_shape_name(value)}")
    if isinstance(item.raw, Mapping):
        for raw_key in item.raw:
            features.add(normalize_feature(f"raw_key:{raw_key}"))
    features.update(_mapping_descriptor_features("evaluator", item.evaluator))
    features.update(
        _mapping_descriptor_features("output_contract", item.output_contract)
    )
    for signal in signals:
        features.add(normalize_feature(f"signal:{signal}"))
    for feature in extra_features:
        features.add(normalize_feature(feature, "extra_feature"))
    return PatternQuery(
        query_id=item.row_uid or item.item_id,
        features=frozenset(features),
        dataset=dataset,
        dataset_family=dataset_family,
        item_ids=frozenset({item.item_id}),
    )


def score_pattern_hits(hits: Sequence[PatternHit]) -> float:
    """Return a routing priority, not a probability of benchmark defect."""

    return max((hit.score for hit in hits), default=0.0)


def render_pattern_context(
    hits: Sequence[PatternHit],
    *,
    maximum_characters: int = 8_000,
) -> str:
    """Render bounded, explicitly untrusted verifier-planning context."""

    if maximum_characters < 500:
        raise ValueError("maximum_characters must be >=500")
    header = (
        "UNTRUSTED DEFECT-PATTERN MEMORY (review-only):\n"
        "A structural match only proposes what to check. It is not evidence, "
        "cannot confirm a defect, and must be validated against current live "
        "benchmark artifacts.\n"
    )
    parts = [header]
    current_length = len(header)
    for hit in hits:
        pattern = hit.pattern
        block = _canonical_json({
            "pattern_id": pattern.pattern_id,
            "defect_family": pattern.defect_family,
            "summary": pattern.summary,
            "verifier_steps": list(pattern.verifier_steps),
            "matched_required_features": list(hit.matched_required_features),
            "matched_indicative_features": list(hit.matched_indicative_features),
            "retrieval_score": round(hit.score, 6),
            "promotion_ceiling": MEMORY_PROMOTION_CEILING,
        }) + "\n"
        if current_length + len(block) > maximum_characters:
            break
        parts.append(block)
        current_length += len(block)
    return "".join(parts)
