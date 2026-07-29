#!/usr/bin/env python3
"""Aggregate-only, zero-execution APPS InputDomainCertificateV1 preflight.

Target task ids are derived from the frozen survivor artifact and skipped from
raw JSONL text before json decoding, so their question text is never parsed or
reported by this preflight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_apps_stdin_differential_confirmation import (
    EXPECTED_DATASET_SHA256,
    _eligible_task,
    verify_dataset_file,
)


SCHEMA_VERSION = "apps-input-contract-v1-preflight-v1"
EXPECTED_PAIR_SHA256 = (
    "7b2190b71b02ccf5a26fea93857edc4fadc01253be16120ca9352a84297d5420"
)
PROCEED_THRESHOLD = 0.20

_ID_RE = re.compile(r'"id"\s*:\s*(\d+)')
_INPUT_HEADER_RE = re.compile(
    r"(?im)^[ \t]*(?:-+[ \t]*)?input(?:[ \t]*-+)?[ \t]*$"
)
_OUTPUT_HEADER_RE = re.compile(
    r"(?im)^[ \t]*(?:-+[ \t]*)?output(?:[ \t]*-+)?[ \t]*$"
)
_MULTI_CASE_RE = re.compile(
    r"(?is)\b(?:number of test cases|test cases|integer\s+t\b)"
)
_ORDINAL = r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
_VAR = r"([A-Za-z][A-Za-z0-9_]*)"
_SINGLE_INTEGER_RE = re.compile(
    rf"(?is)\b{_ORDINAL}\s+line\s+contains\s+"
    rf"(?:a\s+)?(?:single\s+)?integer(?:\s+(?:called\s+)?)?{_VAR}\b"
)
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
}
_FIXED_TUPLE_RE = re.compile(
    rf"(?is)\b{_ORDINAL}\s+line\s+contains\s+"
    r"(one|two|three|four|five|six|seven|eight|nine|ten|[1-9]|10)"
    r"(?:\s+space-separated)?\s+integers?\s+"
    r"([A-Za-z][A-Za-z0-9_]*(?:\s*(?:,|and)\s*"
    r"[A-Za-z][A-Za-z0-9_]*)+)"
)
_COUNT_VECTOR_RE = re.compile(
    r"(?is)\b(?:second|third|fourth|fifth)\s+line\s+contains\s+"
    r"([A-Za-z][A-Za-z0-9_]*)\s+(?:space-separated\s+)?integers?\b"
)
_GLOBAL_MARKERS = (
    "guaranteed",
    "distinct",
    "pairwise",
    "permutation",
    "connected",
    "tree",
    "sorted",
    "non-decreasing",
    "non-increasing",
    "strictly increasing",
    "prime",
    "coprime",
    "no two",
    "exactly one",
)
_PARITY_CONTEXT = re.compile(
    r"(?is)(?:^|[.!?\n])[^.!?\n]*\b(?:even|odd)\b[^.!?\n]*"
    r"\b(?:input|integer|number|n|m|value|element)\b"
    r"|(?:^|[.!?\n])[^.!?\n]*"
    r"\b(?:input|integer|number|n|m|value|element)\b[^.!?\n]*"
    r"\b(?:even|odd)\b"
)
_AT_LEAST_ONE_SUCH_THAT = re.compile(
    r"(?is)\bat least one\b[^.!?\n]{0,160}\bsuch that\b"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _target_ids(pair_file: Path) -> set[int]:
    if _sha256(pair_file) != EXPECTED_PAIR_SHA256:
        raise ValueError("survivor-pair artifact SHA-256 mismatch")
    values: set[int] = set()
    survivors = 0
    with pair_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("outcome") != "weak_pass_strong_pass":
                continue
            survivors += 1
            problem_id = row.get("problem_id")
            if isinstance(problem_id, bool) or not isinstance(problem_id, int):
                raise ValueError("invalid survivor problem id")
            values.add(problem_id)
    if survivors != 26 or len(values) != 16:
        raise ValueError("frozen survivor pool must contain 26 mutants / 16 tasks")
    return values


def _input_section(question: str) -> str | None:
    start = _INPUT_HEADER_RE.search(question)
    if start is None:
        return None
    end = _OUTPUT_HEADER_RE.search(question, start.end())
    if end is None:
        return None
    return question[start.end():end.start()]


def _unsupported_full_question_marker(question: str) -> str | None:
    folded = question.casefold()
    for marker in _GLOBAL_MARKERS:
        if marker in folded:
            return marker
    if _AT_LEAST_ONE_SUCH_THAT.search(question):
        return "at_least_one_such_that"
    if _PARITY_CONTEXT.search(question):
        return "parity_guarantee"
    return None


def _has_explicit_bounds(section: str, variable: str) -> bool:
    escaped = re.escape(variable)
    number = r"-?\d+"
    patterns = (
        rf"{number}\s*(?:<=|≤)\s*\$?{escaped}\$?\s*(?:<=|≤)\s*{number}",
        rf"\$?{escaped}\$?\s+(?:is\s+)?between\s+{number}\s+and\s+{number}",
        rf"\$?{escaped}\$?\s+(?:is\s+)?from\s+{number}\s+to\s+{number}",
    )
    return any(re.search(pattern, section, re.IGNORECASE) for pattern in patterns)


def _tuple_variables(raw: str) -> list[str]:
    return [
        value.strip()
        for value in re.split(r"\s*(?:,|\band\b)\s*", raw)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value.strip())
    ]


def classify_question(question: str) -> tuple[str | None, str]:
    marker = _unsupported_full_question_marker(question)
    if marker is not None:
        return None, f"full_question_marker:{marker}"
    section = _input_section(question)
    if section is None:
        return None, "missing_exact_input_output_sections"
    if _MULTI_CASE_RE.search(section):
        return None, "multiple_test_cases"

    singles = _SINGLE_INTEGER_RE.findall(section)
    tuples = list(_FIXED_TUPLE_RE.finditer(section))
    vectors = list(_COUNT_VECTOR_RE.finditer(section))

    if len(singles) == 1 and not tuples and not vectors:
        variable = singles[0]
        if _has_explicit_bounds(section, variable):
            return "single_integer", "supported"
        return None, "single_integer_missing_bounds"

    if len(tuples) == 1 and not vectors:
        match = tuples[0]
        count_token = match.group(1).casefold()
        declared_count = (
            _NUMBER_WORDS[count_token]
            if count_token in _NUMBER_WORDS else int(count_token)
        )
        variables = _tuple_variables(match.group(2))
        if len(variables) != declared_count:
            return None, "fixed_tuple_count_mismatch"
        if all(_has_explicit_bounds(section, value) for value in variables):
            return "fixed_integer_tuple", "supported"
        return None, "fixed_tuple_missing_bounds"

    if len(vectors) == 1 and singles:
        count_variable = vectors[0].group(1)
        if count_variable.casefold() not in {value.casefold() for value in singles}:
            return None, "counted_vector_unmatched_count"
        if not _has_explicit_bounds(section, count_variable):
            return None, "counted_vector_missing_count_bounds"
        # V1 requires an explicit bound over every vector element.  Recognize
        # only a mechanically unambiguous indexed element name.
        element_match = re.search(
            r"(?is)(-?\d+)\s*(?:<=|≤)\s*"
            r"(?:a|x|v)(?:_?i|\[i\])\s*(?:<=|≤)\s*(-?\d+)",
            section,
        )
        if element_match is None:
            return None, "counted_vector_missing_element_bounds"
        return "counted_integer_vector", "supported"

    ordinal_declarations = len(re.findall(
        rf"(?is)\b{_ORDINAL}\s+line\s+contains\b", section
    ))
    if ordinal_declarations >= 2 and not vectors:
        declared_variables = list(singles)
        for match in tuples:
            declared_variables.extend(_tuple_variables(match.group(2)))
        if (
            len(singles) + len(tuples) == ordinal_declarations
            and declared_variables
            and all(
                _has_explicit_bounds(section, value)
                for value in declared_variables
            )
        ):
            return "fixed_lines_of_integers", "supported"
        return None, "fixed_lines_incomplete_or_unbounded"

    return None, "unsupported_input_grammar"


def run(dataset_file: Path, pair_file: Path) -> dict[str, Any]:
    verify_dataset_file(dataset_file)
    target_ids = _target_ids(pair_file)
    target_id_material = json.dumps(sorted(target_ids), separators=(",", ":"))
    reasons: dict[str, int] = {}
    schemas: dict[str, int] = {}
    rows_scanned = 0
    non_target_eligible = 0
    target_rows_skipped_before_json_decode = 0

    with dataset_file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            rows_scanned += 1
            id_match = _ID_RE.search(line)
            if id_match is None:
                raise ValueError(f"problem id unavailable at line {line_number}")
            problem_id = int(id_match.group(1))
            if problem_id in target_ids:
                target_rows_skipped_before_json_decode += 1
                continue
            row = json.loads(line)
            eligible, _ = _eligible_task(row)
            if eligible is None:
                continue
            non_target_eligible += 1
            question = row.get("question")
            if not isinstance(question, str):
                reason = "missing_question"
                schema = None
            else:
                schema, reason = classify_question(question)
            reasons[reason] = reasons.get(reason, 0) + 1
            if schema is not None:
                schemas[schema] = schemas.get(schema, 0) + 1

    supported = sum(schemas.values())
    coverage = supported / non_target_eligible if non_target_eligible else 0.0
    stable = {
        "schema_version": SCHEMA_VERSION,
        "dataset_sha256": EXPECTED_DATASET_SHA256,
        "survivor_pair_sha256": EXPECTED_PAIR_SHA256,
        "scanner_sha256": _sha256(Path(__file__)),
        "target_id_set_sha256": hashlib.sha256(
            target_id_material.encode("utf-8")
        ).hexdigest(),
        "target_task_count": len(target_ids),
        "target_rows_skipped_before_json_decode":
            target_rows_skipped_before_json_decode,
        "rows_scanned": rows_scanned,
        "non_target_statically_eligible_rows": non_target_eligible,
        "supported_rows": supported,
        "coverage": coverage,
        "proceed_threshold": PROCEED_THRESHOLD,
        "decision": (
            "PROCEED_TO_V1_IMPLEMENTATION"
            if coverage >= PROCEED_THRESHOLD
            else "NOT_IDENTIFIABLE_PREFLIGHT_V1"
        ),
        "schema_counts": dict(sorted(schemas.items())),
        "reason_counts": dict(sorted(reasons.items())),
        "llm_api_calls": 0,
        "candidate_executions": 0,
        "target_question_text_parsed": False,
    }
    stable["stable_summary_sha256"] = hashlib.sha256(
        json.dumps(
            stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return stable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-file", type=Path, required=True)
    parser.add_argument("--pair-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.dataset_file.resolve(), args.pair_file.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
