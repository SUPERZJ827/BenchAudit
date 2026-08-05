"""Contract checks for benchmarks that ship materials and expect deliverables.

"The task names a file the artifact manifest does not contain" is true of any
benchmark that supplies input materials, asks for files to be produced, and
grades them against written criteria.  These predicates lived in the GDPval
module and read GDPval's field names directly, which made a general capability
look benchmark-specific: nobody reading that file would think to point it at
another benchmark.

Each role resolves through a map whose defaults are the GDPval field names, so
an audit supplying no map behaves exactly as before.  What is genuinely
specific to GDPval -- conformance to its published record schema, and
replaying its workbooks -- stays there.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import json
from pathlib import Path, PurePosixPath
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse

from .objective_fact import GDPVAL_PREDICATE_VERSION, ObjectiveFact, _canonical_json


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

_EXACT_FILENAME_CUES = re.compile(
    r"\b(?:file\s*name|filename)\b[^.]{0,80}\bexact(?:ly)?\b|"
    r"\bexact(?:ly)?\b[^.]{0,80}\b(?:file\s*name|filename)\b|"
    r"\bsave(?:d)?\s+(?:the\s+\w+\s+)?(?:exactly\s+)?as\b|"
    r"\blabel\s+the\s+final\b|\bfollowing\s+file\s*name\b",
    re.I,
)

_FILE_EXTENSIONS = frozenset({
    ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".pdf", ".ppt", ".pptx",
    ".csv", ".txt", ".md", ".zip", ".png", ".jpg", ".jpeg", ".wav",
    ".mp3", ".mp4", ".ipynb", ".py", ".yaml", ".yml",
})

_OUTPUT_CUES = re.compile(
    r"\b(?:save(?:d)?|file\s*name|filename|deliverable|return|submit|attach|"
    r"label\s+the\s+final|titled|provided\s+as|create(?:d)?|compile)\b",
    re.I,
)

_QUOTED_FILENAME = re.compile(
    r"[\"'‘’“”]([^\"'‘’“”\r\n]{1,240}\.(?:docx?|xlsx?|xlsm|pdf|pptx?|csv|txt|md|zip|png|jpe?g|wav|mp3|mp4|ipynb|py|ya?ml))[\"'‘’“”]",
    re.I,
)

_REFERENCE_CUES = re.compile(
    r"\b(?:reference|source|attached|input)\s+"
    r"(?:sheet|file|document|workbook|spreadsheet|script|template)|"
    r"\b(?:copy\s+of|consistent\s+with|based\s+on|other\s+than|uses?)\s+(?:the\s+)?$",
    re.I,
)





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


# The field names a record uses for each role.  The defaults are GDPval's, but
# the checks themselves are not about GDPval: "the task names a file the
# artifact manifest does not contain" is true of any benchmark that ships input
# materials and expects deliverables.  Supplying a role map lets the same
# checks run on such a benchmark without another copy of this file.
CONTRACT_ROLE_DEFAULTS = {
    "task": "prompt",
    "rubric": "rubric_json",
    "reference_artifacts": "reference_files",
    "deliverable_artifacts": "deliverable_files",
}

def _contract_facts(
    row: Mapping[str, Any],
    roles: Mapping[str, Any] | None = None,
) -> list[ObjectiveFact]:
    task_field = _role_field(roles, "task")
    rubric_field = _role_field(roles, "rubric")
    task = str(row.get(task_field) or "")
    try:
        rubrics = _rubric_entries(row.get(rubric_field))
    except ValueError:
        return []
    task_names = _extract_filename_claims(task, source="task", source_path=task_field)
    task_formats = _extract_output_formats(task, source="task", source_path=task_field)
    rubric_names: list[dict[str, Any]] = []
    rubric_formats: list[dict[str, Any]] = []
    for entry in rubrics:
        path = f"{rubric_field}[{entry.index}].criterion"
        for claim in _extract_filename_claims(entry.criterion, source="rubric", source_path=path):
            claim["rubric_item_id"] = entry.rubric_item_id
            claim["rubric_index"] = entry.index
            rubric_names.append(claim)
        for claim in _extract_output_formats(entry.criterion, source="rubric", source_path=path):
            claim["rubric_item_id"] = entry.rubric_item_id
            claim["rubric_index"] = entry.index
            rubric_formats.append(claim)

    reference_names = [
        _normalize_basename(value)
        for value in row.get(_role_field(roles, "reference_artifacts"), [])
        if isinstance(value, str)
    ]
    deliverable_names = [
        _normalize_basename(value)
        for value in row.get(_role_field(roles, "deliverable_artifacts"), [])
        if isinstance(value, str)
    ]
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

def _normalize_basename(value: Any) -> str:
    text = unquote(str(value or "").replace("\\", "/"))
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    path = parsed.path if parsed.scheme else text
    return unicodedata.normalize("NFKC", PurePosixPath(path).name).strip()

def _normalize_space(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()

def _role_field(roles: Mapping[str, Any] | None, role: str) -> str:
    """The field holding a role, falling back to the default field name."""

    if roles:
        declared = roles.get(role)
        if isinstance(declared, str) and declared:
            return declared
    return CONTRACT_ROLE_DEFAULTS[role]

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

def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
