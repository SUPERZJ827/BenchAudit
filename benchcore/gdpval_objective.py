"""Objective, replayable integrity checks for the public GDPval v2 records.

The GDPval benchmark contains professional, partly subjective tasks.  This
module deliberately audits only claims with a deterministic witness: rubric
serialization, artifact manifests, explicit filenames/file formats, and a
small grammar of spreadsheet-column contracts.  It never promotes an LLM vote
or a general judgement about professional quality.

All confirmation-capable findings carry a stable ``fact_signature``.  The
central promotion policy recomputes that signature from the live canonical row
instead of trusting the checker payload.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlparse

from .checkers import Checker, _violation
from .coverage import AuditEligibility, AuditUnsupported
from .methods import DatasetChecker
from .schema import BenchmarkItem, Violation


GDPVAL_PREDICATE_VERSION = "benchcore-gdpval-objective/1.0"
DEFAULT_GDPVAL_REVISION = "11e7900cdcac61bc4daf59e65feb238acda98fbf"
DETECTION_METHOD = "gdpval_objective"

GDPVAL_REQUIRED_FIELDS = frozenset({
    "task_id",
    "prompt",
    "reference_files",
    "reference_file_urls",
    "reference_file_hf_uris",
    "deliverable_files",
    "deliverable_file_urls",
    "deliverable_file_hf_uris",
    "rubric_pretty",
    "rubric_json",
})

_ARTIFACT_TRIPLETS = {
    "reference": (
        "reference_files",
        "reference_file_urls",
        "reference_file_hf_uris",
    ),
    "deliverable": (
        "deliverable_files",
        "deliverable_file_urls",
        "deliverable_file_hf_uris",
    ),
}

_FILE_EXTENSIONS = frozenset({
    ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".pdf", ".ppt", ".pptx",
    ".csv", ".txt", ".md", ".zip", ".png", ".jpg", ".jpeg", ".wav",
    ".mp3", ".mp4", ".ipynb", ".py", ".yaml", ".yml",
})


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_space(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _normalize_criterion(value: Any) -> str:
    return _normalize_space(value).casefold()


def _normalize_basename(value: Any) -> str:
    text = unquote(str(value or "").replace("\\", "/"))
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    path = parsed.path if parsed.scheme else text
    return unicodedata.normalize("NFKC", PurePosixPath(path).name).strip()


@dataclass(frozen=True)
class RubricEntry:
    score: float | int
    criterion: str
    rubric_item_id: str | None
    index: int
    raw: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "criterion": self.criterion,
            "rubric_item_id": self.rubric_item_id,
            "index": self.index,
        }


def parse_rubrics(value: Any) -> list[dict[str, Any]]:
    """Parse and structurally validate a GDPval ``rubric_json`` value.

    The public helper returns ordinary dictionaries so experiment scripts can
    serialize the result without importing internal dataclasses.  Unknown
    rubric keys are preserved; required structural keys are validated.
    """

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"rubric_json is invalid JSON: {exc}") from exc
    else:
        parsed = value
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("rubric_json must be a non-empty list")
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(parsed):
        if not isinstance(raw, dict):
            raise ValueError(f"rubric_json[{index}] must be an object")
        criterion = raw.get("criterion")
        score = raw.get("score")
        if not isinstance(criterion, str) or not criterion.strip():
            raise ValueError(f"rubric_json[{index}].criterion must be non-empty text")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError(f"rubric_json[{index}].score must be numeric")
        rubric_id = raw.get("rubric_item_id")
        if rubric_id is not None and not isinstance(rubric_id, str):
            raise ValueError(f"rubric_json[{index}].rubric_item_id must be text or null")
        result.append(dict(raw))
    return result


def _rubric_entries(value: Any) -> list[RubricEntry]:
    rows = parse_rubrics(value)
    return [
        RubricEntry(
            score=row["score"],
            criterion=_normalize_space(row["criterion"]),
            rubric_item_id=row.get("rubric_item_id"),
            index=index,
            raw=row,
        )
        for index, row in enumerate(rows)
    ]


_PRETTY_ITEM = re.compile(
    r"(?ms)^\s*\[\s*(\+-?\d+(?:\.\d+)?|-\d+(?:\.\d+)?)\s*\]\s*"
    r"(.*?)(?=^\s*\[\s*(?:\+-?\d+(?:\.\d+)?|-\d+(?:\.\d+)?)\s*\]|\Z)"
)


def parse_pretty_rubrics(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("rubric_pretty must be non-empty text")
    result: list[dict[str, Any]] = []
    for match in _PRETTY_ITEM.finditer(value):
        token = match.group(1)
        if token.startswith("+-"):
            number = -float(token[2:])
        else:
            number = float(token)
        score: float | int = int(number) if number.is_integer() else number
        criterion = _normalize_space(match.group(2))
        if not criterion:
            raise ValueError("rubric_pretty contains an empty criterion")
        result.append({"score": score, "criterion": criterion})
    if not result:
        raise ValueError("rubric_pretty contains no parseable rubric entries")
    return result


@dataclass(frozen=True)
class ObjectiveFact:
    defect_type: str
    evidence_level: str
    atom: Mapping[str, Any]
    message: str
    severity: str
    confidence: float
    repair: str
    confirmation_capable: bool = True

    @property
    def signature(self) -> str:
        return _sha256_json({
            "defect_type": self.defect_type,
            "evidence_level": self.evidence_level,
            "atom": self.atom,
            "predicate_version": GDPVAL_PREDICATE_VERSION,
        })

    def evidence(self, row: Mapping[str, Any], dataset_revision: str) -> dict[str, Any]:
        return {
            "proof_schema_version": "1.0",
            "evidence_level": self.evidence_level,
            "benchmark_family": "gdpval",
            "dataset_revision": dataset_revision,
            "predicate_version": GDPVAL_PREDICATE_VERSION,
            "replay_input_sha256": _sha256_json(row),
            "fact_signature": self.signature,
            "atom": dict(self.atom),
        }


def _representation_facts(row: Mapping[str, Any]) -> list[ObjectiveFact]:
    pretty_raw = row.get("rubric_pretty")
    json_raw = row.get("rubric_json")
    try:
        pretty = parse_pretty_rubrics(pretty_raw)
    except ValueError as exc:
        return [ObjectiveFact(
            "rubric_representation_mismatch",
            "gdpval_rubric_representation_replay",
            {
                "kind": "pretty_parse_error",
                "error_type": type(exc).__name__,
                "pretty_sha256": _sha256_text(str(pretty_raw or "")),
                "json_sha256": _sha256_text(str(json_raw or "")),
            },
            "The human-readable rubric representation cannot be parsed.",
            "major",
            1.0,
            "Regenerate rubric_pretty from the canonical structured rubric.",
        )]
    try:
        structured = _rubric_entries(json_raw)
    except ValueError as exc:
        return [ObjectiveFact(
            "rubric_representation_mismatch",
            "gdpval_rubric_representation_replay",
            {
                "kind": "json_parse_or_shape_error",
                "error_type": type(exc).__name__,
                "pretty_sha256": _sha256_text(str(pretty_raw or "")),
                "json_sha256": _sha256_text(str(json_raw or "")),
            },
            "The structured rubric representation cannot be parsed or has an invalid shape.",
            "major",
            1.0,
            "Repair rubric_json and regenerate its readable representation.",
        )]
    expected = [
        {"score": entry.score, "criterion": _normalize_space(entry.criterion)}
        for entry in structured
    ]
    if pretty == expected:
        return []
    mismatch_index = next(
        (
            index
            for index in range(max(len(pretty), len(expected)))
            if index >= len(pretty)
            or index >= len(expected)
            or pretty[index] != expected[index]
        ),
        None,
    )
    return [ObjectiveFact(
        "rubric_representation_mismatch",
        "gdpval_rubric_representation_replay",
        {
            "kind": "pretty_json_content_mismatch",
            "pretty_item_count": len(pretty),
            "json_item_count": len(expected),
            "first_mismatch_index": mismatch_index,
            "pretty_item": pretty[mismatch_index] if mismatch_index is not None and mismatch_index < len(pretty) else None,
            "json_item": expected[mismatch_index] if mismatch_index is not None and mismatch_index < len(expected) else None,
            "pretty_sha256": _sha256_json(pretty),
            "json_sha256": _sha256_json(expected),
        },
        "rubric_pretty and rubric_json disagree.",
        "major",
        1.0,
        "Choose one canonical rubric representation and regenerate the other.",
    )]


def _safe_relative_artifact_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return False
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    return not pure.is_absolute() and ".." not in pure.parts


def _schema_facts(row: Mapping[str, Any]) -> list[ObjectiveFact]:
    missing = sorted(GDPVAL_REQUIRED_FIELDS - set(row))
    invalid: dict[str, str] = {}
    if "task_id" in row and not dataset_uuid_is_valid(row.get("task_id")):
        invalid["task_id"] = "must be a canonical UUID"
    if "prompt" in row and (
        not isinstance(row.get("prompt"), str) or not row.get("prompt", "").strip()
    ):
        invalid["prompt"] = "must be non-empty text"
    for keys in _ARTIFACT_TRIPLETS.values():
        for key in keys:
            value = row.get(key)
            if key in row and (
                not isinstance(value, list)
                or any(not isinstance(entry, str) for entry in value)
            ):
                invalid[key] = "must be a list of strings"
    if "rubric_pretty" in row and not isinstance(row.get("rubric_pretty"), str):
        invalid["rubric_pretty"] = "must be text"
    if "rubric_json" in row and not isinstance(row.get("rubric_json"), (str, list)):
        invalid["rubric_json"] = "must be JSON text or a list"
    if not missing and not invalid:
        return []
    return [ObjectiveFact(
        "gdpval_schema_mismatch",
        "gdpval_record_schema_replay",
        {
            "kind": "gdpval_record_schema_mismatch",
            "missing_fields": missing,
            "invalid_fields": invalid,
            "observed_fields": sorted(str(key) for key in row),
        },
        "The record does not satisfy the explicit GDPval v2 row schema.",
        "major",
        1.0,
        "Restore the required GDPval fields and canonical field types before auditing content.",
    )]


def _https_manifest_reasons(
    value: Any,
    declared_path: str,
    dataset_revision: str,
) -> list[str]:
    reasons: list[str] = []
    try:
        parsed = urlparse(str(value or ""))
        port = parsed.port
    except ValueError:
        return ["malformed_https_url"]
    if (
        parsed.scheme != "https"
        or parsed.hostname != "huggingface.co"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        reasons.append("unexpected_https_url_origin")
    if parsed.query or parsed.fragment:
        reasons.append("unexpected_https_url_suffix")
    prefix = "/datasets/openai/gdpval/resolve/"
    decoded_path = unicodedata.normalize("NFKC", unquote(parsed.path))
    if not decoded_path.startswith(prefix):
        reasons.append("unexpected_https_dataset_path")
        return reasons
    remainder = decoded_path[len(prefix):]
    if "/" not in remainder:
        reasons.append("missing_https_revision_or_artifact_path")
        return reasons
    revision, artifact_path = remainder.split("/", 1)
    if revision not in {"main", dataset_revision}:
        reasons.append("unexpected_https_dataset_revision")
    if artifact_path != declared_path:
        reasons.append("https_artifact_path_disagreement")
    return reasons


def _hf_manifest_reasons(
    value: Any,
    declared_path: str,
    dataset_revision: str,
) -> list[str]:
    reasons: list[str] = []
    try:
        parsed = urlparse(str(value or ""))
    except ValueError:
        return ["malformed_hf_dataset_uri"]
    if parsed.scheme != "hf" or parsed.hostname != "datasets":
        reasons.append("invalid_hf_dataset_uri")
    if parsed.query or parsed.fragment:
        reasons.append("unexpected_hf_uri_suffix")
    decoded_path = unicodedata.normalize("NFKC", unquote(parsed.path)).lstrip("/")
    prefix = "openai/gdpval@"
    if not decoded_path.startswith(prefix):
        reasons.append("unexpected_hf_dataset_path")
        return reasons
    remainder = decoded_path[len(prefix):]
    if "/" not in remainder:
        reasons.append("missing_hf_revision_or_artifact_path")
        return reasons
    revision, artifact_path = remainder.split("/", 1)
    if revision not in {"main", dataset_revision}:
        reasons.append("unexpected_hf_dataset_revision")
    if artifact_path != declared_path:
        reasons.append("hf_artifact_path_disagreement")
    return reasons


def _manifest_facts(
    row: Mapping[str, Any],
    dataset_revision: str,
) -> list[ObjectiveFact]:
    facts: list[ObjectiveFact] = []
    for role, keys in _ARTIFACT_TRIPLETS.items():
        values = [row.get(key) for key in keys]
        valid_lists = all(isinstance(value, list) for value in values)
        lengths = [len(value) if isinstance(value, list) else None for value in values]
        mismatches: list[dict[str, Any]] = []
        if valid_lists and len(set(lengths)) == 1:
            for index, (path, url, hf_uri) in enumerate(zip(*values, strict=True)):
                path_name = _normalize_basename(path)
                url_name = _normalize_basename(url)
                hf_name = _normalize_basename(hf_uri)
                reasons: list[str] = []
                if not _safe_relative_artifact_path(path):
                    reasons.append("unsafe_or_invalid_relative_path")
                declared_path = str(path or "")
                reasons.extend(_https_manifest_reasons(
                    url, declared_path, dataset_revision,
                ))
                reasons.extend(_hf_manifest_reasons(
                    hf_uri, declared_path, dataset_revision,
                ))
                if not path_name or len({path_name, url_name, hf_name}) != 1:
                    reasons.append("basename_disagreement")
                if reasons:
                    mismatches.append({
                        "index": index,
                        "declared_path": declared_path,
                        "path_basename": path_name,
                        "url_basename": url_name,
                        "hf_uri_basename": hf_name,
                        "reasons": sorted(set(reasons)),
                    })
        if not valid_lists or len(set(lengths)) != 1 or mismatches:
            facts.append(ObjectiveFact(
                "artifact_reference_manifest_mismatch",
                "gdpval_artifact_manifest_replay",
                {
                    "kind": "artifact_triplet_mismatch",
                    "artifact_role": role,
                    "source_fields": list(keys),
                    "list_types_valid": valid_lists,
                    "lengths": lengths,
                    "mismatches": mismatches,
                },
                f"GDPval {role} artifact path/URL/URI declarations are inconsistent.",
                "major",
                1.0,
                "Repair the three parallel artifact lists from one canonical manifest.",
            ))
    return facts


def _rubric_structure_facts(row: Mapping[str, Any]) -> list[ObjectiveFact]:
    try:
        entries = _rubric_entries(row.get("rubric_json"))
    except ValueError:
        return []  # representation fact owns this root cause
    facts: list[ObjectiveFact] = []
    by_id: dict[str, list[RubricEntry]] = defaultdict(list)
    by_text: dict[str, list[RubricEntry]] = defaultdict(list)
    for entry in entries:
        if entry.rubric_item_id:
            by_id[entry.rubric_item_id].append(entry)
        by_text[_normalize_criterion(entry.criterion)].append(entry)
    for rubric_id, group in sorted(by_id.items()):
        if len(group) <= 1:
            continue
        facts.append(ObjectiveFact(
            "duplicate_rubric_item_id",
            "gdpval_rubric_identifier_replay",
            {
                "kind": "duplicate_rubric_item_id",
                "rubric_item_id": rubric_id,
                "indices": [entry.index for entry in group],
            },
            "Multiple rubric entries reuse the same rubric_item_id.",
            "major",
            1.0,
            "Assign every rubric entry a globally unique identifier.",
        ))
    for normalized, group in sorted(by_text.items()):
        if len(group) <= 1:
            continue
        facts.append(ObjectiveFact(
            "duplicate_rubric_criterion",
            "gdpval_duplicate_criterion_scan",
            {
                "kind": "duplicate_rubric_criterion",
                "criterion_sha256": _sha256_text(normalized),
                "indices": [entry.index for entry in group],
                "rubric_item_ids": [entry.rubric_item_id for entry in group],
                "scores": [entry.score for entry in group],
                "excerpt": group[0].criterion[:300],
            },
            "The rubric repeats the same normalized criterion.",
            "review",
            0.99,
            "Remove accidental duplicate scoring or document intentional repeated weighting.",
            confirmation_capable=False,
        ))
    return facts


def _scope_for_fragment(fragment: str, source: str) -> str:
    lowered = fragment.casefold()
    if "sample size calculation" in lowered:
        return "deliverable:sample_size_calculation"
    if any(token in lowered for token in ("first worksheet", "first tab", "selected sample")):
        return "deliverable:first_sheet"
    if any(token in lowered for token in ("population reference", "population sheet")):
        return "reference:population"
    quoted_sheet = re.search(
        r"(?:worksheet|sheet|tab)\s+[\"'‘’“”]([^\"'‘’“”]{1,60})[\"'‘’“”]|"
        r"[\"'‘’“”]([^\"'‘’“”]{1,60})[\"'‘’“”]\s+(?:worksheet|sheet|tab)",
        fragment,
        re.I,
    )
    if quoted_sheet:
        name = _normalize_criterion(quoted_sheet.group(1) or quoted_sheet.group(2))
        return f"deliverable:sheet:{name}"
    named_sheet = re.search(
        r"\b(?:on|in|within)\s+(?:the\s+)?([A-Za-z0-9_-]{1,40})\s+"
        r"(?:worksheet|sheet|tab)\b",
        fragment,
        re.I,
    )
    if named_sheet and named_sheet.group(1).casefold() not in {"first", "selected"}:
        return f"deliverable:sheet:{named_sheet.group(1).casefold()}"
    bare_sheet = re.search(
        r"\b([A-Za-z0-9_-]{1,40})\s+(?:worksheet|sheet|tab)\b",
        fragment,
        re.I,
    )
    if bare_sheet and bare_sheet.group(1).casefold() not in {
        "first", "selected", "population", "reference",
    }:
        return f"deliverable:sheet:{bare_sheet.group(1).casefold()}"
    if source == "task" and any(
        token in lowered for token in ("capture", "indicate sampled", "marked in column")
    ):
        return "deliverable:first_sheet"
    if source == "task" and "q2 and q3 data" in lowered:
        return "reference:population"
    return "unspecified"


def _claim(
    *,
    role: str,
    column: str,
    source: str,
    source_path: str,
    excerpt: str,
    scope: str,
    conditional: bool,
) -> dict[str, Any]:
    return {
        "role": role,
        "column": column.upper(),
        "source": source,
        "source_path": source_path,
        "scope": scope,
        "conditional": conditional,
        "excerpt": _normalize_space(excerpt)[:500],
        "excerpt_sha256": _sha256_text(_normalize_space(excerpt)),
    }


def _excel_column_token(value: str) -> str | None:
    """Normalize a real Excel column token without consuming prose.

    The surrounding patterns are case-insensitive, so a phrase such as
    ``variance column in both`` would otherwise invent column ``IN``.
    Lower-case single letters remain valid (``column j`` is common), while a
    multi-letter identifier must use conventional upper-case notation and
    fall inside Excel's XFD limit.
    """

    if not re.fullmatch(r"[A-Za-z]{1,3}", value):
        return None
    if len(value) > 1 and value != value.upper():
        return None
    normalized = value.upper()
    ordinal = 0
    for character in normalized:
        ordinal = ordinal * 26 + ord(character) - ord("A") + 1
    return normalized if ordinal <= 16_384 else None


def extract_column_claims(
    text: str,
    *,
    source: str,
    source_path: str,
) -> list[dict[str, Any]]:
    """Extract a deliberately small grammar of spreadsheet column roles."""

    if not isinstance(text, str) or not text.strip():
        return []
    fragments = [
        fragment.strip()
        for fragment in re.split(r"[\r\n]+|(?<=[.;])\s+(?=[A-Z0-9])", text)
        if fragment.strip()
    ]
    claims: list[dict[str, Any]] = []
    for fragment_index, fragment in enumerate(fragments):
        scope = _scope_for_fragment(fragment, source)
        conditional = bool(re.search(r"\b(?:if|unless|depending on|where)\b", fragment, re.I))
        path = f"{source_path}#fragment-{fragment_index}"
        used: set[tuple[str, str]] = set()

        pair_patterns = (
            re.compile(
                r"Q2(?:\s+\d{4})?\s+and\s+Q3(?:\s+\d{4})?[^.]{0,80}?"
                r"columns?\s+([A-Z]{1,3})\s+and\s+([A-Z]{1,3})",
                re.I,
            ),
            re.compile(
                r"columns?\s+([A-Z]{1,3})\s+and\s+([A-Z]{1,3})[^.]{0,100}?"
                r"Q2(?:\s+\d{4})?\s+and\s+Q3(?:\s+\d{4})?[^.]{0,30}?respectively",
                re.I,
            ),
        )
        for pattern in pair_patterns:
            match = pattern.search(fragment)
            if not match:
                continue
            pair = (
                _excel_column_token(match.group(1)),
                _excel_column_token(match.group(2)),
            )
            if None in pair:
                continue
            for role, column in (("q2", pair[0]), ("q3", pair[1])):
                assert column is not None
                claims.append(_claim(
                    role=role,
                    column=column,
                    source=source,
                    source_path=path,
                    excerpt=fragment,
                    scope=scope,
                    conditional=conditional,
                ))
                used.add((role, column))
            break

        role_patterns: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
            (
                "variance",
                (
                    re.compile(r"column\s+([A-Z]{1,3})[^.]{0,100}?(?:variance|quarter[\s‑–-]*on[\s‑–-]*quarter)", re.I),
                    re.compile(r"(?:variance|quarter[\s‑–-]*on[\s‑–-]*quarter)[^.]{0,100}?column\s+([A-Z]{1,3})", re.I),
                    re.compile(r"(?:absolute\s+)?variance\s*\|([A-Z]{1,3})\|", re.I),
                ),
            ),
            (
                "sample_flag",
                (
                    re.compile(r"column\s+([A-Z]{1,3})[^.]{0,100}?(?:sampled|sample\s+(?:flag|selected|selection))", re.I),
                    re.compile(r"(?:sampled|sample\s+(?:flag|selected|selection))[^.]{0,100}?column\s+([A-Z]{1,3})", re.I),
                    re.compile(r"sum\s+of\s+1s?\s+in\s+column\s+([A-Z]{1,3})", re.I),
                ),
            ),
        )
        for role, patterns in role_patterns:
            for pattern in patterns:
                for match in pattern.finditer(fragment):
                    column = _excel_column_token(match.group(1))
                    if column is None:
                        continue
                    if (role, column) in used:
                        continue
                    claims.append(_claim(
                        role=role,
                        column=column,
                        source=source,
                        source_path=path,
                        excerpt=fragment,
                        scope=scope,
                        conditional=conditional,
                    ))
                    used.add((role, column))
    unique = {
        _sha256_json(claim): claim
        for claim in claims
    }
    return [unique[key] for key in sorted(unique)]


def _column_facts(row: Mapping[str, Any]) -> list[ObjectiveFact]:
    task_claims, rubric_claims = _all_column_claims(row)
    if not rubric_claims:
        return []

    conflicts: list[dict[str, Any]] = []
    unconditional = [
        claim for claim in rubric_claims
        if not claim["conditional"] and claim.get("scope") != "unspecified"
    ]
    by_role: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_column: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for claim in unconditional:
        by_role[(claim["scope"], claim["role"])].append(claim)
        by_column[(claim["scope"], claim["column"])].append(claim)
    for (scope, role), group in sorted(by_role.items()):
        columns = sorted({claim["column"] for claim in group})
        if len(columns) > 1:
            conflicts.append({
                "kind": "one_role_multiple_columns",
                "scope": scope,
                "role": role,
                "columns": columns,
                "claims": sorted(group, key=lambda claim: (claim["column"], claim["source_path"])),
            })
    for (scope, column), group in sorted(by_column.items()):
        roles = sorted({claim["role"] for claim in group})
        if len(roles) > 1:
            conflicts.append({
                "kind": "one_column_multiple_roles",
                "scope": scope,
                "column": column,
                "roles": roles,
                "claims": sorted(group, key=lambda claim: (claim["role"], claim["source_path"])),
            })
    facts: list[ObjectiveFact] = []
    if conflicts:
        facts.append(ObjectiveFact(
            "rubric_internal_contradiction",
            "gdpval_rubric_column_replay",
            {
                "kind": "incompatible_column_role_claims",
                "conflicts": conflicts,
                "claim_count": len(rubric_claims),
            },
            "The rubric assigns incompatible semantic roles to spreadsheet columns in the same scope.",
            "review",
            0.98,
            "Resolve table/sheet identity, then reconcile every column reference with the workbook.",
            confirmation_capable=False,
        ))

    # Cross-source differences are useful review signals but are not
    # confirmation-capable until an immutable workbook replay chooses the
    # applicable scope and establishes the actual headers.
    task_by_role: dict[tuple[str, str], set[str]] = defaultdict(set)
    rubric_by_role: dict[tuple[str, str], set[str]] = defaultdict(set)
    for claim in task_claims:
        if not claim["conditional"]:
            task_by_role[(claim["scope"], claim["role"])].add(claim["column"])
    for claim in rubric_claims:
        if not claim["conditional"]:
            rubric_by_role[(claim["scope"], claim["role"])].add(claim["column"])
    mismatches = []
    for key in sorted(set(task_by_role) & set(rubric_by_role)):
        if task_by_role[key] != rubric_by_role[key]:
            mismatches.append({
                "scope": key[0],
                "role": key[1],
                "task_columns": sorted(task_by_role[key]),
                "rubric_columns": sorted(rubric_by_role[key]),
            })
    if mismatches:
        facts.append(ObjectiveFact(
            "task_rubric_mismatch",
            "gdpval_column_contract_candidate",
            {
                "kind": "task_rubric_column_difference",
                "mismatches": mismatches,
                "task_claims": task_claims,
                "rubric_claims": rubric_claims,
            },
            "Task and rubric column-role claims differ; workbook replay is required for adjudication.",
            "review",
            0.98,
            "Replay the claims against pinned reference and deliverable workbook headers.",
            confirmation_capable=False,
        ))
    return facts


def _all_column_claims(row: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return task and rubric claims without assigning them an evidence tier."""

    task_claims = extract_column_claims(
        str(row.get("prompt") or ""), source="task", source_path="prompt",
    )
    rubric_claims: list[dict[str, Any]] = []
    try:
        rubrics = _rubric_entries(row.get("rubric_json"))
    except ValueError:
        return task_claims, rubric_claims
    for entry in rubrics:
        claims = extract_column_claims(
            entry.criterion,
            source="rubric",
            source_path=f"rubric_json[{entry.index}].criterion",
        )
        for claim in claims:
            claim["rubric_item_id"] = entry.rubric_item_id
            claim["rubric_index"] = entry.index
        rubric_claims.extend(claims)
    return task_claims, rubric_claims


_QUOTED_FILENAME = re.compile(
    r"[\"'‘’“”]([^\"'‘’“”\r\n]{1,240}\.(?:docx?|xlsx?|xlsm|pdf|pptx?|csv|txt|md|zip|png|jpe?g|wav|mp3|mp4|ipynb|py|ya?ml))[\"'‘’“”]",
    re.I,
)

_OUTPUT_CUES = re.compile(
    r"\b(?:save(?:d)?|file\s*name|filename|deliverable|return|submit|attach|"
    r"label\s+the\s+final|titled|provided\s+as|create(?:d)?|compile)\b",
    re.I,
)
_REFERENCE_CUES = re.compile(
    r"\b(?:reference|source|attached|input)\s+"
    r"(?:sheet|file|document|workbook|spreadsheet|script|template)|"
    r"\b(?:copy\s+of|consistent\s+with|based\s+on|other\s+than|uses?)\s+(?:the\s+)?$",
    re.I,
)
_EXACT_FILENAME_CUES = re.compile(
    r"\b(?:file\s*name|filename)\b[^.]{0,80}\bexact(?:ly)?\b|"
    r"\bexact(?:ly)?\b[^.]{0,80}\b(?:file\s*name|filename)\b|"
    r"\bsave(?:d)?\s+(?:the\s+\w+\s+)?(?:exactly\s+)?as\b|"
    r"\blabel\s+the\s+final\b|\bfollowing\s+file\s*name\b",
    re.I,
)


def _extract_filename_claims(
    text: str,
    *,
    source: str,
    source_path: str,
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for match in _QUOTED_FILENAME.finditer(text or ""):
        start, end = match.span()
        context = text[max(0, start - 140):min(len(text), end + 80)]
        before = text[max(0, start - 140):start]
        immediate = before[-80:]
        reference_matches = list(_REFERENCE_CUES.finditer(immediate))
        output_matches = list(_OUTPUT_CUES.finditer(immediate))
        latest_reference = reference_matches[-1].start() if reference_matches else -1
        latest_output = output_matches[-1].start() if output_matches else -1
        if latest_reference > latest_output:
            role = "reference"
        elif _OUTPUT_CUES.search(context):
            role = "deliverable"
        else:
            continue
        name = _normalize_basename(match.group(1))
        if Path(name).suffix.casefold() not in _FILE_EXTENSIONS:
            continue
        claims.append({
            "kind": "exact_filename",
            "artifact_role": role,
            "basename": name,
            "source": source,
            "source_path": source_path,
            "raw_claim_span": {
                "start": match.start(1),
                "end": match.end(1),
            },
            "raw_claim_sha256": _sha256_text(match.group(1)),
            "match_policy": (
                "exact"
                if _EXACT_FILENAME_CUES.search(context)
                or re.search(r"\.[A-Za-z0-9]{1,8}\.[A-Za-z0-9]{1,8}$", name)
                else "named_reference_candidate"
            ),
            "excerpt": _normalize_space(context)[:400],
            "excerpt_sha256": _sha256_text(_normalize_space(context)),
        })
    return claims


_FORMAT_NAMES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (".docx", re.compile(r"\bWord\b(?:\s+(?:document|file))?|\.docx\b", re.I)),
    (".xlsx", re.compile(r"\bExcel\s+(?:workbook|file|spreadsheet)\b|\.xlsx\b", re.I)),
    (".pdf", re.compile(r"\bPDF\b(?:\s+(?:document|file))?|\.pdf\b", re.I)),
    # "PowerPoint slides/presentation" describes a visual form but does not
    # require a .pptx container; GDPval commonly publishes such decks as PDF.
    (".pptx", re.compile(r"\bPowerPoint\s+file\b|\.pptx\b", re.I)),
)

_OUTPUT_FORMAT_DESCRIPTORS: dict[str, str] = {
    ".docx": r"Word\s+(?:document|file)",
    ".xlsx": r"Excel\s+(?:workbook|file|spreadsheet)",
    ".pdf": r"PDF(?:\s+(?:document|file))?",
    ".pptx": r"(?:PowerPoint(?:\s+(?:presentation|file))?|slide\s+deck)",
}


def _is_strong_output_format_claim(text: str, extension: str) -> bool:
    """Require a syntactic link between a format and the requested output."""

    descriptor = _OUTPUT_FORMAT_DESCRIPTORS[extension]
    escaped_extension = re.escape(extension)
    value = rf"(?:{descriptor}|{escaped_extension}\b)"
    patterns = (
        # "Create/prepare ... a Word document".  Raw extensions are excluded
        # here so "Create a report using input.xlsx" cannot bind the input.
        rf"\b(?:create|prepare|produce|compile|draft|return)\b[^.\n]{{0,200}}"
        rf"(?:{descriptor})\b",
        rf"\b(?:output|deliverable|submission|final\s+(?:file|document|workbook))\b"
        rf"[^.\n]{{0,140}}{value}",
        rf"\b(?:save|saved|submit|submitted|provide|provided|deliver|delivered|"
        rf"export|exported|return|returned)\b[^.\n]{{0,100}}\bas\b"
        rf"[^.\n]{{0,40}}{value}",
        rf"{value}[^.\n]{{0,80}}\b(?:output|deliverable|submission|format)\b",
    )
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def _extract_output_formats(text: str, *, source: str, source_path: str) -> list[dict[str, Any]]:
    fragments = [
        fragment.strip()
        for fragment in re.split(r"[\r\n]+|(?<=[.!?])\s+", text or "")
        if fragment.strip()
    ]
    claims: list[dict[str, Any]] = []
    for index, fragment in enumerate(fragments):
        if not _OUTPUT_CUES.search(fragment):
            continue
        # URLs and quoted filenames commonly describe inputs.  Exact output
        # filenames are handled by the filename-claim grammar above.
        cleaned = re.sub(r"https?://\S+", " ", fragment)
        cleaned = _QUOTED_FILENAME.sub(" ", cleaned)
        formats = sorted({extension for extension, pattern in _FORMAT_NAMES if pattern.search(cleaned)})
        if len(formats) > 1:
            # Explicit final-export wording disambiguates intermediate authoring
            # formats (e.g. "PowerPoint presentation (as PDF)").
            final_pdf = re.search(
                r"(?:convert(?:ed)?\s+(?:it|them)?\s*to|as|final\s+)\s*(?:a\s+)?PDF\b",
                cleaned,
                re.I,
            )
            if final_pdf:
                formats = [".pdf"]
        if len(formats) != 1:
            continue
        strong_format = _is_strong_output_format_claim(cleaned, formats[0])
        claims.append({
            "kind": "output_format",
            "extension": formats[0],
            "confirmation_capable": strong_format,
            "source": source,
            "source_path": f"{source_path}#fragment-{index}",
            "excerpt": _normalize_space(fragment)[:400],
            "excerpt_sha256": _sha256_text(_normalize_space(fragment)),
        })
    return claims


def _contract_facts(row: Mapping[str, Any]) -> list[ObjectiveFact]:
    task = str(row.get("prompt") or "")
    try:
        rubrics = _rubric_entries(row.get("rubric_json"))
    except ValueError:
        return []
    task_names = _extract_filename_claims(task, source="task", source_path="prompt")
    task_formats = _extract_output_formats(task, source="task", source_path="prompt")
    rubric_names: list[dict[str, Any]] = []
    rubric_formats: list[dict[str, Any]] = []
    for entry in rubrics:
        path = f"rubric_json[{entry.index}].criterion"
        for claim in _extract_filename_claims(entry.criterion, source="rubric", source_path=path):
            claim["rubric_item_id"] = entry.rubric_item_id
            claim["rubric_index"] = entry.index
            rubric_names.append(claim)
        for claim in _extract_output_formats(entry.criterion, source="rubric", source_path=path):
            claim["rubric_item_id"] = entry.rubric_item_id
            claim["rubric_index"] = entry.index
            rubric_formats.append(claim)

    reference_names = [_normalize_basename(value) for value in row.get("reference_files", []) if isinstance(value, str)]
    deliverable_names = [_normalize_basename(value) for value in row.get("deliverable_files", []) if isinstance(value, str)]
    facts: list[ObjectiveFact] = []

    def filename_mismatch(
        claim: Mapping[str, Any],
        observed: Sequence[str],
        *,
        defect_type: str,
        level: str,
        label: str,
        severity: str = "minor",
    ) -> None:
        if (
            not observed
            or claim["basename"] in observed
            or claim.get("match_policy") != "exact"
        ):
            return
        facts.append(ObjectiveFact(
            defect_type,
            level,
            {
                "kind": "exact_filename_absent",
                "artifact_role": claim["artifact_role"],
                "expected_basename": claim["basename"],
                "observed_basenames": sorted(observed),
                "claim": dict(claim),
            },
            f"An explicit {label} filename is absent from the published artifact manifest.",
            severity,
            1.0,
            "Align the task/rubric filename with the published artifact or replace the artifact.",
        ))

    for claim in task_names:
        observed = reference_names if claim["artifact_role"] == "reference" else deliverable_names
        filename_mismatch(
            claim,
            observed,
            defect_type=(
                "rubric_reference_contract_mismatch"
                if claim["artifact_role"] == "reference"
                else "task_artifact_contract_mismatch"
            ),
            level=(
                "gdpval_task_reference_filename_replay"
                if claim["artifact_role"] == "reference"
                else "gdpval_task_deliverable_filename_replay"
            ),
            label="task",
        )
    for claim in rubric_names:
        observed = reference_names if claim["artifact_role"] == "reference" else deliverable_names
        filename_mismatch(
            claim,
            observed,
            defect_type=(
                "rubric_reference_contract_mismatch"
                if claim["artifact_role"] == "reference"
                else "rubric_artifact_contract_mismatch"
            ),
            level=(
                "gdpval_rubric_reference_filename_replay"
                if claim["artifact_role"] == "reference"
                else "gdpval_rubric_deliverable_filename_replay"
            ),
            label="rubric",
        )

    actual_extensions = sorted({Path(name).suffix.casefold() for name in deliverable_names if Path(name).suffix})
    if len(deliverable_names) == 1 and len(actual_extensions) == 1:
        actual = actual_extensions[0]
        for claim in task_formats:
            if claim["extension"] != actual and claim.get("confirmation_capable"):
                facts.append(ObjectiveFact(
                    "task_artifact_contract_mismatch",
                    "gdpval_task_deliverable_format_replay",
                    {
                        "kind": "output_format_mismatch",
                        "expected_extension": claim["extension"],
                        "observed_extension": actual,
                        "observed_basenames": deliverable_names,
                        "claim": claim,
                    },
                    "The published deliverable format conflicts with an explicit task output format.",
                    "major",
                    1.0,
                    "Align the task output format, rubric, and expert deliverable.",
                ))
        for claim in rubric_formats:
            if claim["extension"] != actual and claim.get("confirmation_capable"):
                facts.append(ObjectiveFact(
                    "rubric_artifact_contract_mismatch",
                    "gdpval_rubric_deliverable_format_replay",
                    {
                        "kind": "output_format_mismatch",
                        "expected_extension": claim["extension"],
                        "observed_extension": actual,
                        "observed_basenames": deliverable_names,
                        "claim": claim,
                    },
                    "The published deliverable format conflicts with an explicit rubric output format.",
                    "major",
                    1.0,
                    "Align the rubric output format with the task and expert deliverable.",
                ))
    return facts


_PERSON_NAME = r"[A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+){1,2}"
_DOCTOR = re.compile(rf"\bDr\.?\s+({_PERSON_NAME})\b")
_RECIPIENT = re.compile(
    rf"\b(?:email|notice|message)\b[^.\n]{{0,180}}?"
    rf"\b(?:to|sent\s+to|addressed\s+to|for\s+review\s+by|from)\s+Dr\.?\s+({_PERSON_NAME})\b",
    re.I,
)


def _normalized_person(value: str) -> str:
    return _normalize_space(value).casefold().replace("’", "'")


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def _entity_facts(row: Mapping[str, Any]) -> list[ObjectiveFact]:
    """Emit conservative review signals for explicit person-name conflicts."""

    task = str(row.get("prompt") or "")
    try:
        rubrics = _rubric_entries(row.get("rubric_json"))
    except ValueError:
        return []
    rubric_text = "\n".join(entry.criterion for entry in rubrics)
    facts: list[ObjectiveFact] = []

    task_recipients = sorted({_normalize_space(value) for value in _RECIPIENT.findall(task)})
    rubric_recipients = sorted({_normalize_space(value) for value in _RECIPIENT.findall(rubric_text)})
    normalized_task_recipients = {_normalized_person(value) for value in task_recipients}
    unsupported_recipients = [
        value for value in rubric_recipients
        if _normalized_person(value) not in normalized_task_recipients
    ]
    if task_recipients and unsupported_recipients:
        facts.append(ObjectiveFact(
            "task_rubric_mismatch",
            "gdpval_recipient_contract_candidate",
            {
                "kind": "recipient_name_difference",
                "task_recipients": task_recipients,
                "rubric_recipients": rubric_recipients,
                "unsupported_rubric_recipients": unsupported_recipients,
            },
            "Task and rubric name different recipients for the requested communication.",
            "review",
            0.99,
            "Confirm the intended recipient and update every affected rubric criterion.",
            confirmation_capable=False,
        ))

    # Only apply the typo heuristic when the task explicitly closes the entity
    # set (e.g. "two physicians ...") and a rubric name is a near edit of a
    # supported full name.  It remains review-only because professional
    # context could intentionally introduce another person.
    closed_world = bool(re.search(
        r"\b(?:exactly\s+)?(?:two|three|four|2|3|4)\s+"
        r"(?:physicians?|doctors?|attendees?|participants?)\b",
        task,
        re.I,
    ))
    if closed_world:
        task_people = sorted({_normalize_space(value) for value in _DOCTOR.findall(task)})
        rubric_people = sorted({_normalize_space(value) for value in _DOCTOR.findall(rubric_text)})
        normalized_task = {_normalized_person(value): value for value in task_people}
        candidates = []
        for rubric_person in rubric_people:
            normalized = _normalized_person(rubric_person)
            if normalized in normalized_task or not normalized_task:
                continue
            nearest_key = min(normalized_task, key=lambda value: _edit_distance(normalized, value))
            distance = _edit_distance(normalized, nearest_key)
            if distance <= 2:
                candidates.append({
                    "rubric_person": rubric_person,
                    "nearest_task_person": normalized_task[nearest_key],
                    "edit_distance": distance,
                })
        if candidates:
            facts.append(ObjectiveFact(
                "task_rubric_mismatch",
                "gdpval_closed_world_entity_candidate",
                {
                    "kind": "closed_world_entity_name_difference",
                    "task_people": task_people,
                    "rubric_people": rubric_people,
                    "nearest_name_candidates": candidates,
                },
                "A rubric person name is absent from an explicitly bounded task entity set and closely resembles a supported name.",
                "review",
                0.98,
                "Verify the intended person name and replace the apparent rubric typo consistently.",
                confirmation_capable=False,
            ))
    return facts


def collect_record_facts(
    row: Mapping[str, Any],
    dataset_revision: str = DEFAULT_GDPVAL_REVISION,
) -> list[ObjectiveFact]:
    """Collect deterministic and explicitly review-only facts for one row."""

    schema_facts = _schema_facts(row)
    if schema_facts:
        return schema_facts
    facts = [
        *_representation_facts(row),
        *_manifest_facts(row, dataset_revision),
        *_rubric_structure_facts(row),
        *_column_facts(row),
        *_contract_facts(row),
        *_entity_facts(row),
    ]
    # Stable root-cause order, independent of worker scheduling.
    unique = {fact.signature: fact for fact in facts}
    return [unique[key] for key in sorted(unique)]


@dataclass(frozen=True)
class WorkbookReplayFact:
    fact: ObjectiveFact
    artifacts: tuple[Mapping[str, Any], ...]

    def evidence(
        self,
        row: Mapping[str, Any],
        dataset_revision: str,
    ) -> dict[str, Any]:
        payload = self.fact.evidence(row, dataset_revision)
        payload["artifacts"] = [dict(artifact) for artifact in self.artifacts]
        return payload


def _header_role(value: str) -> str | None:
    normalized = _normalize_criterion(value)
    if re.fullmatch(r"q2(?:\s+20\d{2})?(?:\s+kri)?", normalized):
        return "q2"
    if re.fullmatch(r"q3(?:\s+20\d{2})?(?:\s+kri)?", normalized):
        return "q3"
    if re.fullmatch(
        r"(?:variance|%\s*variance|%?\s*var(?:iance)?\s+q3\s+(?:vs|v)\.?\s+q2|"
        r"quarter[\s-]*on[\s-]*quarter\s+variance)",
        normalized,
    ):
        return "variance"
    if normalized in {"sample selected", "sample flag", "selected sample"}:
        return "sample_flag"
    return None


def _column_from_coordinate(value: str) -> str | None:
    match = re.fullmatch(r"([A-Z]{1,3})[1-9][0-9]*", str(value or "").upper())
    return match.group(1) if match else None


def _workbook_header_claims(snapshot: Any, *, artifact_role: str) -> list[dict[str, Any]]:
    """Extract role-bearing cells from a structurally supported header row.

    A lone title such as ``Q2 overview`` is not a header witness.  We require
    at least two distinct recognized roles on one row.  Reference workbooks
    with multiple sheets must also identify a unique population-named sheet;
    deliverable claims explicitly target the first sheet.
    """

    if not snapshot.sheets:
        return []
    if artifact_role == "reference" and len(snapshot.sheets) > 1:
        population_sheets = [
            sheet for sheet in snapshot.sheets
            if "population" in _normalize_criterion(sheet.name)
        ]
        if len(population_sheets) != 1:
            return []
        sheet = population_sheets[0]
    else:
        sheet = snapshot.sheets[0]
    rows: dict[int, list[Any]] = defaultdict(list)
    for cell in sheet.cells:
        match = re.fullmatch(r"[A-Z]{1,3}([1-9][0-9]*)", cell.coordinate.upper())
        if match:
            rows[int(match.group(1))].append(cell)
    chosen: tuple[int, list[Any]] | None = None
    for row_index in sorted(rows):
        roles = {
            role for cell in rows[row_index]
            if (role := _header_role(str(cell.value))) is not None
        }
        if len(roles) >= 2:
            chosen = (row_index, rows[row_index])
            break
    if chosen is None:
        return []
    row_index, cells = chosen
    claims = []
    for cell in cells:
        role = _header_role(str(cell.value))
        column = _column_from_coordinate(cell.coordinate)
        if role is None or column is None:
            continue
        claims.append({
            "role": role,
            "column": column,
            "scope": (
                "reference:population"
                if artifact_role == "reference"
                else "deliverable:first_sheet"
            ),
            "artifact_role": artifact_role,
            "sheet": sheet.name,
            "coordinate": cell.coordinate,
            "value": str(cell.value),
            "row_index": row_index,
            "parser_version": snapshot.parser_version,
            "artifact_sha256": snapshot.file_sha256,
        })
    return sorted(claims, key=lambda claim: (claim["role"], claim["column"]))


def _artifact_receipt(
    resolved: Any,
    snapshot: Any,
    header_claims: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    resolver_evidence = resolved.to_evidence()
    return {
        "declared_path": resolved.declared_path,
        "artifact_role": resolved.declared_path.split("/", 1)[0].removesuffix("_files"),
        "artifact_sha256": resolved.sha256,
        "size_bytes": resolved.size_bytes,
        "dataset_revision": resolved.revision,
        "resolver_schema_version": resolver_evidence["resolver_schema_version"],
        "artifact_authenticity": resolver_evidence.get("authenticity", "unknown"),
        "source_url": resolver_evidence.get("source_url"),
        "snapshot_schema_version": snapshot.schema_version,
        "parser_version": snapshot.parser_version,
        "sheet_names": list(snapshot.sheet_names),
        "cell_count": snapshot.cell_count,
        "header_claims": [dict(claim) for claim in header_claims],
    }


def _workbook_mismatches(
    expected_claims: Sequence[Mapping[str, Any]],
    observed_claims: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    observed: dict[tuple[str, str], set[str]] = defaultdict(set)
    supporting: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for claim in observed_claims:
        key = (str(claim["scope"]), str(claim["role"]))
        observed[key].add(str(claim["column"]))
        supporting[key].append(claim)
    mismatches: list[dict[str, Any]] = []
    for expected in expected_claims:
        if expected.get("conditional"):
            continue
        key = (str(expected.get("scope")), str(expected.get("role")))
        actual = observed.get(key)
        if not actual or str(expected.get("column")) in actual:
            continue
        # Multiple observed columns for one semantic role are ambiguous rather
        # than evidence that a particular expected coordinate is wrong.
        if len(actual) != 1:
            continue
        mismatches.append({
            "scope": key[0],
            "role": key[1],
            "expected_column": str(expected.get("column")),
            "observed_columns": sorted(actual),
            "expected_claim": dict(expected),
            "observed_claims": [dict(value) for value in supporting[key]],
        })
    unique = {_sha256_json(row): row for row in mismatches}
    return [unique[key] for key in sorted(unique)]


def collect_workbook_replay_facts(
    row: Mapping[str, Any],
    resolver: Any,
    *,
    allow_download: bool,
) -> list[WorkbookReplayFact]:
    """Replay explicit column claims against pinned XLSX header cells."""

    from .ooxml_cells import snapshot_xlsx

    task_claims, rubric_claims = _all_column_claims(row)
    relevant_scopes = {
        str(claim.get("scope")) for claim in (*task_claims, *rubric_claims)
        if claim.get("scope") in {"reference:population", "deliverable:first_sheet"}
    }
    if not relevant_scopes:
        return []

    resolved_rows: list[tuple[Any, Any, list[dict[str, Any]]]] = []
    for artifact_role, field in (
        ("reference", "reference_files"),
        ("deliverable", "deliverable_files"),
    ):
        scope = (
            "reference:population"
            if artifact_role == "reference"
            else "deliverable:first_sheet"
        )
        if scope not in relevant_scopes:
            continue
        paths = [
            path for path in row.get(field, [])
            if isinstance(path, str) and Path(path).suffix.casefold() == ".xlsx"
        ]
        # Multiple workbooks need an independently resolved artifact-role
        # selector; guessing which workbook a claim refers to would not be E3.
        if len(paths) != 1:
            raise AuditUnsupported(
                f"{artifact_role} column replay requires exactly one XLSX; "
                f"observed {len(paths)}",
                details={"artifact_role": artifact_role, "xlsx_count": len(paths)},
            )
        resolved = resolver.resolve(paths[0], allow_download=allow_download)
        snapshot = snapshot_xlsx(resolved.materialized_path)
        if snapshot.file_sha256 != resolved.sha256:
            raise ValueError("XLSX snapshot digest differs from resolver receipt")
        header_claims = _workbook_header_claims(snapshot, artifact_role=artifact_role)
        if not header_claims:
            raise AuditUnsupported(
                f"{artifact_role} workbook has no unambiguous supported header row",
                details={
                    "artifact_role": artifact_role,
                    "artifact_sha256": resolved.sha256,
                },
            )
        resolved_rows.append((resolved, snapshot, header_claims))

    observed_claims = [
        claim for _resolved, _snapshot, claims in resolved_rows for claim in claims
    ]
    observed_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for claim in observed_claims:
        observed_by_key[(str(claim["scope"]), str(claim["role"]))].add(
            str(claim["column"])
        )
    required_keys = {
        (str(claim["scope"]), str(claim["role"]))
        for claim in (*task_claims, *rubric_claims)
        if not claim.get("conditional")
        and claim.get("scope") in relevant_scopes
    }
    unresolved = [
        {"scope": scope, "role": role, "observed_columns": sorted(
            observed_by_key.get((scope, role), set())
        )}
        for scope, role in sorted(required_keys)
        if len(observed_by_key.get((scope, role), set())) != 1
    ]
    if unresolved:
        raise AuditUnsupported(
            "workbook replay could not resolve every claimed semantic role to one column",
            details={"unresolved_claim_roles": unresolved},
        )
    receipts = tuple(
        _artifact_receipt(resolved, snapshot, claims)
        for resolved, snapshot, claims in resolved_rows
    )
    facts: list[WorkbookReplayFact] = []
    for source, claims, defect_type, level in (
        (
            "task",
            task_claims,
            "task_artifact_contract_mismatch",
            "gdpval_task_workbook_header_replay",
        ),
        (
            "rubric",
            rubric_claims,
            "rubric_artifact_contract_mismatch",
            "gdpval_rubric_workbook_header_replay",
        ),
    ):
        mismatches = _workbook_mismatches(claims, observed_claims)
        if not mismatches:
            continue
        fact = ObjectiveFact(
            defect_type,
            level,
            {
                "kind": "workbook_header_column_mismatch",
                "claim_source": source,
                "mismatches": mismatches,
                "artifact_sha256s": sorted({
                    receipt["artifact_sha256"] for receipt in receipts
                }),
            },
            f"{source.title()} spreadsheet-column claims disagree with pinned reference/gold workbook headers.",
            "major",
            1.0,
            "Correct the column references and all affected objective rubric criteria.",
        )
        facts.append(WorkbookReplayFact(fact=fact, artifacts=receipts))
    return facts


def replay_workbook_fact(
    violation: Violation,
    item: BenchmarkItem | None,
) -> bool:
    if item is None or not isinstance(item.raw, dict):
        return False
    resolver = getattr(item, "_gdpval_artifact_resolver", None)
    if resolver is None:
        return False
    evidence = violation.evidence
    if (
        evidence.get("predicate_version") != GDPVAL_PREDICATE_VERSION
        or evidence.get("benchmark_family") != "gdpval"
        or evidence.get("dataset_revision") != getattr(resolver, "revision", None)
        or evidence.get("replay_input_sha256") != _sha256_json(item.raw)
    ):
        return False
    try:
        replayed_facts = collect_workbook_replay_facts(
            item.raw,
            resolver,
            allow_download=False,
        )
    except Exception:
        return False
    for replayed in replayed_facts:
        if (
            replayed.fact.defect_type == violation.defect_type
            and replayed.fact.evidence_level == evidence.get("evidence_level")
            and replayed.fact.signature == evidence.get("fact_signature")
            and dict(replayed.fact.atom) == evidence.get("atom")
            and [dict(value) for value in replayed.artifacts] == evidence.get("artifacts")
        ):
            return True
    return False


def replay_record_fact(
    violation: Violation,
    item: BenchmarkItem | None,
) -> bool:
    """Recompute a claimed record fact from the live row for promotion."""

    if item is None or not isinstance(item.raw, dict):
        return False
    evidence = violation.evidence
    if evidence.get("predicate_version") != GDPVAL_PREDICATE_VERSION:
        return False
    if evidence.get("benchmark_family") != "gdpval":
        return False
    dataset_revision = getattr(item, "_gdpval_dataset_revision", None)
    if evidence.get("dataset_revision") != dataset_revision:
        return False
    if evidence.get("replay_input_sha256") != _sha256_json(item.raw):
        return False
    signature = evidence.get("fact_signature")
    return any(
        fact.confirmation_capable
        and fact.defect_type == violation.defect_type
        and fact.evidence_level == evidence.get("evidence_level")
        and fact.signature == signature
        and dict(fact.atom) == evidence.get("atom")
        for fact in collect_record_facts(item.raw, dataset_revision)
    )


class GDPValRecordIntegrityChecker(Checker):
    name = "gdpval_objective"

    def __init__(self, *, dataset_revision: str = DEFAULT_GDPVAL_REVISION) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}", dataset_revision):
            raise ValueError("GDPval dataset revision must be a 40-character commit hash")
        self.dataset_revision = dataset_revision

    def audit_eligibility(
        self,
        item: BenchmarkItem,
        root: Path | None = None,
    ) -> AuditEligibility:
        del root
        return AuditEligibility.applicable(
            "the explicit GDPval checker validates both row schema and content"
        )

    def check(
        self,
        item: BenchmarkItem,
        root: Path | None = None,
    ) -> Iterable[Violation]:
        del root
        setattr(item, "_gdpval_dataset_revision", self.dataset_revision)
        for fact in collect_record_facts(item.raw, self.dataset_revision):
            yield _violation(
                item,
                fact.defect_type,
                fact.confidence,
                fact.message,
                fact.evidence(item.raw, self.dataset_revision),
                severity=fact.severity,
                review_only=not fact.confirmation_capable,
                repair=fact.repair,
                method=DETECTION_METHOD,
            )


class GDPValWorkbookReplayChecker(Checker):
    """Replay explicit spreadsheet-column contracts on pinned XLSX artifacts."""

    name = "gdpval_workbook_replay"

    def __init__(
        self,
        resolver: Any,
        *,
        allow_download: bool = False,
        task_ids: Sequence[str] | None = None,
    ) -> None:
        self.resolver = resolver
        self.allow_download = bool(allow_download)
        self.task_ids = frozenset(task_ids or ())

    def audit_eligibility(
        self,
        item: BenchmarkItem,
        root: Path | None = None,
    ) -> AuditEligibility:
        del root
        if GDPVAL_REQUIRED_FIELDS - set(item.raw):
            return AuditEligibility.not_applicable("record is not GDPval v2")
        if self.task_ids and item.item_id not in self.task_ids:
            return AuditEligibility.not_applicable(
                "task is outside the explicitly selected deep-replay set"
            )
        task_claims, rubric_claims = _all_column_claims(item.raw)
        supported_scopes = {"reference:population", "deliverable:first_sheet"}
        supported_claims = [
            claim for claim in (*task_claims, *rubric_claims)
            if claim.get("scope") in supported_scopes
        ]
        if not supported_claims:
            return AuditEligibility.not_applicable(
                "no artifact-resolvable spreadsheet-column contract was extracted"
            )
        scopes = {str(claim["scope"]) for claim in supported_claims}
        for scope, field, role in (
            ("reference:population", "reference_files", "reference"),
            ("deliverable:first_sheet", "deliverable_files", "deliverable"),
        ):
            if scope not in scopes:
                continue
            value = item.raw.get(field)
            if not isinstance(value, list):
                return AuditEligibility(
                    False,
                    f"{role} artifact manifest is not a list",
                    "unsupported",
                )
            xlsx = [
                path for path in value
                if isinstance(path, str) and Path(path).suffix.casefold() == ".xlsx"
            ]
            if len(xlsx) != 1:
                return AuditEligibility(
                    False,
                    f"{role} replay requires exactly one XLSX; observed {len(xlsx)}",
                    "unsupported",
                )
        return AuditEligibility.applicable(
            "supported column claims and pinned XLSX artifacts are available"
        )

    def check(
        self,
        item: BenchmarkItem,
        root: Path | None = None,
    ) -> Iterable[Violation]:
        del root
        # Promotion replays from the same resolver in cache-only mode.  The
        # private attachment is deliberately absent from serialized reports.
        setattr(item, "_gdpval_artifact_resolver", self.resolver)
        replayed = collect_workbook_replay_facts(
            item.raw,
            self.resolver,
            allow_download=self.allow_download,
        )
        for row in replayed:
            fact = row.fact
            yield _violation(
                item,
                fact.defect_type,
                fact.confidence,
                fact.message,
                row.evidence(item.raw, self.resolver.revision),
                severity=fact.severity,
                review_only=False,
                repair=fact.repair,
                method=DETECTION_METHOD,
            )


class GDPValDatasetIntegrityChecker(DatasetChecker):
    """Complete-dataset scans that cannot be proved from a single row."""

    name = "gdpval_dataset_objective"

    def __init__(self, *, dataset_revision: str = DEFAULT_GDPVAL_REVISION) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}", dataset_revision):
            raise ValueError("GDPval dataset revision must be a 40-character commit hash")
        self.dataset_revision = dataset_revision

    def audit_eligibility(
        self,
        item: BenchmarkItem,
        items: list[BenchmarkItem],
    ) -> AuditEligibility:
        if GDPVAL_REQUIRED_FIELDS - set(item.raw):
            return AuditEligibility.not_applicable("record is not GDPval v2")
        if len(items) < 2:
            return AuditEligibility.not_applicable("dataset identity checks require multiple rows")
        return AuditEligibility.applicable("complete GDPval identity registry is available")

    def check(self, items: list[BenchmarkItem]) -> Iterable[Violation]:
        # Existing DuplicateConflictChecker owns duplicate task_id promotion.
        # This checker adds the benchmark-specific global rubric-ID registry.
        by_rubric_id: dict[str, list[tuple[BenchmarkItem, int]]] = defaultdict(list)
        for item in items:
            try:
                rows = parse_rubrics(item.raw.get("rubric_json"))
            except ValueError:
                continue
            for index, row in enumerate(rows):
                rubric_id = row.get("rubric_item_id")
                if isinstance(rubric_id, str) and rubric_id:
                    by_rubric_id[rubric_id].append((item, index))
        for rubric_id, occurrences in sorted(by_rubric_id.items()):
            if len(occurrences) <= 1:
                continue
            source = occurrences[0][0]
            atom = {
                "kind": "global_duplicate_rubric_item_id",
                "rubric_item_id": rubric_id,
                "occurrences": [
                    {"row_uid": item.row_uid, "rubric_index": index}
                    for item, index in occurrences
                ],
            }
            yield _violation(
                source,
                "duplicate_rubric_item_id",
                1.0,
                "The same rubric_item_id appears in multiple live GDPval records.",
                {
                    "proof_schema_version": "1.0",
                    "evidence_level": "gdpval_global_rubric_identifier_replay",
                    "benchmark_family": "gdpval",
                    "dataset_revision": self.dataset_revision,
                    "predicate_version": GDPVAL_PREDICATE_VERSION,
                    "atom": atom,
                    "target_row_uids": [item.row_uid for item, _ in occurrences],
                    "fact_signature": _sha256_json(atom),
                },
                severity="major",
                review_only=True,
                repair="Assign globally unique rubric_item_id values.",
                method=DETECTION_METHOD,
            )


def gdpval_mapping() -> "FieldMapping":
    """Return the explicit role mapping used by the objective experiment."""

    from .schema import FieldMapping

    return FieldMapping(
        item_id="task_id",
        task="prompt",
        context=[
            "reference_files",
            "reference_file_urls",
            "reference_file_hf_uris",
        ],
        gold="deliverable_files",
        output_contract=None,
        evaluator="rubric_json",
        metadata=["sector", "occupation"],
        diagnostics={"source": "explicit", "profile": "gdpval_objective_v2"},
    )


def build_gdpval_items(rows: list[dict[str, Any]]) -> list[BenchmarkItem]:
    from .loader import build_items

    return build_items(rows, gdpval_mapping())


def dataset_uuid_is_valid(value: Any) -> bool:
    try:
        return str(uuid.UUID(str(value))) == str(value).casefold()
    except (ValueError, TypeError, AttributeError):
        return False


__all__ = [
    "DEFAULT_GDPVAL_REVISION",
    "GDPVAL_PREDICATE_VERSION",
    "GDPValDatasetIntegrityChecker",
    "GDPValRecordIntegrityChecker",
    "GDPValWorkbookReplayChecker",
    "build_gdpval_items",
    "collect_record_facts",
    "collect_workbook_replay_facts",
    "dataset_uuid_is_valid",
    "extract_column_claims",
    "gdpval_mapping",
    "parse_pretty_rubrics",
    "parse_rubrics",
    "replay_record_fact",
    "replay_workbook_fact",
]
