from __future__ import annotations

import json
from typing import Any, Callable

from .schema import FieldMapping


ID_FIELDS = ("item_id", "id", "instance_id", "task_id", "question_id", "uid")
TASK_FIELDS = (
    "question",
    "prompt",
    "instruction",
    "task",
    "task_description",
    "problem",
    "problem_statement",
    "user_query",
    "query",
    "input",
)
CONTEXT_FIELDS = (
    "context",
    "passage",
    "article",
    "document",
    "documents",
    "schema",
    "database_schema",
    "db_schema",
    "hkb",
    "metadata_files",
    "attachments",
    "files",
    "image",
    "images",
    "table",
    "tables",
    "repo",
    "repository",
)
CHOICE_FIELDS = ("choices", "options", "answer_choices", "candidates")
GOLD_FIELDS = (
    "gold",
    "answer",
    "correct_answer",
    "gold_answer",
    "final_answer",
    "target",
    "label",
    "gold_sql",
    "reference",
    "reference_solution",
)
ALIAS_FIELDS = ("aliases", "accepted_answers", "acceptable_answers", "equivalent_outputs")
OUTPUT_FIELDS = (
    "output_contract",
    "expected_output",
    "output_format",
    "answer_type",
    "submission_format",
)
EVALUATOR_FIELDS = (
    "evaluator",
    "evaluation",
    "metric",
    "rubric",
    "tests",
    "test_cases",
    "checker",
    "scoring",
)
METADATA_FIELDS = (
    "metadata",
    "task_type",
    "subject",
    "domain",
    "category",
    "source",
    "split",
    "version",
    "error_type",
    "verified_gold",
    "verified_answer_text",
)


def _first_present(keys: tuple[str, ...], row: dict[str, Any]) -> str | None:
    lowered = {k.lower(): k for k in row}
    for key in keys:
        if key in lowered:
            return lowered[key]
    return None


def _nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _case_value(row: dict[str, Any], candidate: str) -> tuple[str | None, Any]:
    actual = next((key for key in row if key.casefold() == candidate.casefold()), None)
    if actual is not None:
        return actual, row.get(actual)
    current: Any = row
    resolved: list[str] = []
    for component in candidate.split("."):
        if not isinstance(current, dict):
            return None, None
        actual = next(
            (key for key in current if key.casefold() == component.casefold()),
            None,
        )
        if actual is None:
            return None, None
        resolved.append(actual)
        current = current.get(actual)
    return ".".join(resolved), current


def _iter_paths(
    value: dict[str, Any], prefix: tuple[str, ...] = (), *, max_depth: int = 4,
) -> list[str]:
    paths: list[str] = []
    if len(prefix) >= max_depth:
        return paths
    for key, child in value.items():
        path = (*prefix, str(key))
        paths.append(".".join(path))
        if isinstance(child, dict):
            paths.extend(_iter_paths(child, path, max_depth=max_depth))
    return paths


def _candidate_paths(
    rows: list[dict[str, Any]], candidates: tuple[str, ...],
) -> tuple[str, ...]:
    observed = {path for row in rows for path in _iter_paths(row)}
    expanded: list[str] = []
    seen: set[str] = set()
    for semantic_name in candidates:
        matches = sorted(
            (
                path for path in observed
                if path.rsplit(".", 1)[-1].casefold() == semantic_name.casefold()
            ),
            key=lambda path: (path.count("."), path.casefold()),
        )
        for path in (semantic_name, *matches):
            key = path.casefold()
            if key in seen:
                continue
            seen.add(key)
            expanded.append(path)
    return tuple(expanded)


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_listish(value: Any) -> bool:
    if isinstance(value, (list, tuple)):
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped.startswith("["):
        return False
    try:
        return isinstance(json.loads(stripped), list)
    except json.JSONDecodeError:
        return False


def _is_choice_collection(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            return isinstance(json.loads(value), dict)
        except json.JSONDecodeError:
            return False
    return _is_listish(value)


def _any_nonempty(value: Any) -> bool:
    return _nonempty(value)


def _select_field(
    rows: list[dict[str, Any]],
    candidates: tuple[str, ...],
    compatible: Callable[[Any], bool],
) -> tuple[str | None, dict[str, Any]]:
    """Choose by observed coverage, never by one sparse sample row."""
    stats: list[dict[str, Any]] = []
    total = len(rows)
    for priority, candidate in enumerate(candidates):
        actual_names: dict[str, int] = {}
        present = compatible_count = 0
        values: list[Any] = []
        for row in rows:
            actual, value = _case_value(row, candidate)
            if actual is None or not _nonempty(value):
                continue
            present += 1
            compatible_count += int(compatible(value))
            actual_names[actual] = actual_names.get(actual, 0) + 1
            values.append(value)
        if present:
            selected_actual = max(
                actual_names,
                key=lambda name: (actual_names[name], name == candidate),
            )
            stats.append({
                "candidate": candidate,
                "selected_actual": selected_actual,
                "priority": priority,
                "present": present,
                "coverage": present / total if total else 0.0,
                "type_compatible": compatible_count,
                "type_coverage": compatible_count / present,
                "values": values,
            })
    if not stats:
        return None, {
            "selected": None,
            "coverage": 0.0,
            "type_coverage": 0.0,
            "status": "unmapped",
            "candidates": [],
        }
    ranked = sorted(
        stats,
        key=lambda row: (
            row["coverage"], row["type_coverage"], -row["priority"],
        ),
        reverse=True,
    )
    best = ranked[0]
    conflicts: list[str] = []
    for other in ranked[1:]:
        if other["coverage"] < max(0.5, best["coverage"] - 0.05):
            continue
        disagreements = overlap_disagreements(
            rows, best["candidate"], other["candidate"],
        )
        if disagreements:
            conflicts.append(other["selected_actual"])
    status = "ambiguous" if conflicts else (
        "complete" if best["coverage"] == 1.0 and best["type_coverage"] == 1.0
        else "partial"
    )
    return str(best["selected_actual"]), {
        "selected": best["selected_actual"],
        "coverage": best["coverage"],
        "type_coverage": best["type_coverage"],
        "status": status,
        "conflicting_candidates": conflicts,
        "candidates": [
            {
                key: value for key, value in row.items()
                if key not in {"values", "priority"}
            }
            for row in ranked
        ],
    }


def overlap_disagreements(
    rows: list[dict[str, Any]], left: str, right: str,
) -> int:
    disagreements = 0
    for row in rows:
        _, a = _case_value(row, left)
        _, b = _case_value(row, right)
        if not (_nonempty(a) and _nonempty(b)):
            continue
        if json.dumps(a, ensure_ascii=False, sort_keys=True, default=str) != json.dumps(
            b, ensure_ascii=False, sort_keys=True, default=str,
        ):
            disagreements += 1
    return disagreements


def _present_many(keys: tuple[str, ...], rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for path in _candidate_paths(rows, keys):
        if any(_nonempty(_case_value(row, path)[1]) for row in rows):
            out.append(path)
    return out


def infer_mapping(rows: list[dict[str, Any]]) -> FieldMapping:
    selectors = {
        "item_id": _select_field(rows, _candidate_paths(rows, ID_FIELDS), _any_nonempty),
        "task": _select_field(rows, _candidate_paths(rows, TASK_FIELDS), _is_text),
        "choices": _select_field(
            rows, _candidate_paths(rows, CHOICE_FIELDS), _is_choice_collection,
        ),
        "gold": _select_field(rows, _candidate_paths(rows, GOLD_FIELDS), _any_nonempty),
        "aliases": _select_field(rows, _candidate_paths(rows, ALIAS_FIELDS), _is_listish),
        "output_contract": _select_field(
            rows, _candidate_paths(rows, OUTPUT_FIELDS), _any_nonempty,
        ),
        "evaluator": _select_field(
            rows, _candidate_paths(rows, EVALUATOR_FIELDS), _any_nonempty,
        ),
    }
    return FieldMapping(
        item_id=selectors["item_id"][0],
        task=selectors["task"][0],
        context=_present_many(CONTEXT_FIELDS, rows),
        choices=selectors["choices"][0],
        gold=selectors["gold"][0],
        aliases=selectors["aliases"][0],
        output_contract=selectors["output_contract"][0],
        evaluator=selectors["evaluator"][0],
        metadata=_present_many(METADATA_FIELDS, rows),
        diagnostics={
            "source": "inferred",
            "rows_profiled": len(rows),
            "fields": {name: value[1] for name, value in selectors.items()},
        },
    )


def mapping_from_dict(data: dict[str, Any]) -> FieldMapping:
    return FieldMapping(
        item_id=data.get("item_id"),
        task=data.get("task"),
        context=list(data.get("context", [])),
        choices=data.get("choices"),
        gold=data.get("gold"),
        aliases=data.get("aliases"),
        output_contract=data.get("output_contract"),
        evaluator=data.get("evaluator"),
        metadata=list(data.get("metadata", [])),
        diagnostics={**dict(data.get("diagnostics") or {}), "source": "explicit"},
    )
