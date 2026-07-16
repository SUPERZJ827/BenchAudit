"""Leakage-resistant train/dev/holdout corpus handling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from ..loader import build_items, load_mapping
from ..schema import BenchmarkItem
from .models import (
    CORPUS_SCHEMA_VERSION,
    FORBIDDEN_PATH_SEGMENTS,
    CorpusExample,
    RuleValidationError,
    corpus_sha256,
)


def load_evolution_corpus(path: Path) -> tuple[list[CorpusExample], dict[str, Any]]:
    """Load and validate a sidecar-labeled evolution corpus.

    Labels and source groups live in the outer corpus record; they are never
    copied into the row evaluated by a candidate rule.  Source groups must be
    exclusive to one split, preventing clean/mutant siblings from leaking
    across train and holdout.
    """

    path = Path(path)
    if path.suffix.casefold() == ".jsonl":
        raw_examples = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        metadata: dict[str, Any] = {
            "schema_version": CORPUS_SCHEMA_VERSION,
            "source": str(path.resolve()),
        }
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuleValidationError("evolution corpus JSON must be an object")
        if payload.get("schema_version") != CORPUS_SCHEMA_VERSION:
            raise RuleValidationError(
                f"unsupported corpus schema version: {payload.get('schema_version')!r}"
            )
        raw_examples = payload.get("examples")
        if not isinstance(raw_examples, list):
            raise RuleValidationError("evolution corpus requires an examples list")
        metadata = {
            key: value
            for key, value in payload.items()
            if key != "examples"
        }
        metadata["source"] = str(path.resolve())
    examples = [CorpusExample.from_dict(row) for row in raw_examples]
    validate_corpus(examples)
    metadata["corpus_sha256"] = corpus_sha256(examples)
    metadata["example_count"] = len(examples)
    metadata["split_counts"] = {
        split: sum(example.split == split for example in examples)
        for split in ("train", "dev", "holdout")
    }
    return examples, metadata


def validate_corpus(examples: Iterable[CorpusExample]) -> None:
    rows = list(examples)
    if not rows:
        raise RuleValidationError("evolution corpus is empty")
    ids = [example.example_id for example in rows]
    if len(ids) != len(set(ids)):
        raise RuleValidationError("evolution corpus contains duplicate example_id values")
    groups: dict[str, set[str]] = {}
    for example in rows:
        groups.setdefault(example.source_group, set()).add(example.split)
    leaks = {
        group: sorted(splits)
        for group, splits in groups.items()
        if len(splits) != 1
    }
    if leaks:
        preview = dict(list(sorted(leaks.items()))[:10])
        raise RuleValidationError(
            "source groups cross train/dev/holdout boundaries: " + repr(preview)
        )
    missing = {
        split
        for split in ("train", "dev", "holdout")
        if not any(example.split == split for example in rows)
    }
    if missing:
        raise RuleValidationError(f"evolution corpus is missing splits: {sorted(missing)}")


def build_corpus_items(examples: list[CorpusExample]) -> list[BenchmarkItem]:
    """Canonicalize visible rows without exposing sidecar labels to checkers."""

    rows = [example.row for example in examples]
    mapping = load_mapping(None, rows)
    return build_items(rows, mapping, source_indices=list(range(len(rows))))


def synthesis_projection(
    examples: Iterable[CorpusExample],
    *,
    max_examples: int = 48,
    max_string_chars: int = 500,
    max_collection_items: int = 40,
) -> list[dict[str, Any]]:
    """Return a bounded, identifier-free training view for a remote model.

    Only train rows should be passed here.  Labels remain necessary for rule
    induction, but example IDs, split names and source groups are omitted.  Any
    benchmark text is still untrusted data and is quoted as JSON by the
    synthesizer prompt.
    """

    projected: list[dict[str, Any]] = []
    for example in list(examples)[:max_examples]:
        projected.append({
            "row": _bounded_projection(
                example.row,
                max_string_chars=max_string_chars,
                max_collection_items=max_collection_items,
            ),
            "expected_defect_types": list(example.expected_defect_types),
        })
    return projected


def _bounded_projection(
    value: Any,
    *,
    max_string_chars: int,
    max_collection_items: int,
    depth: int = 0,
) -> Any:
    if depth >= 8:
        return "[DEPTH_LIMIT]"
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in {"[", "{"}:
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed, (list, dict)):
                    # Preserve the crucial fact that deployment data is JSON
                    # *text* while avoiding invalid mid-string truncation.  The
                    # tag is prompt-only metadata and never enters candidate
                    # evaluation rows.
                    return {
                        "__benchcore_projection__": "json_encoded_text",
                        "parsed_type": "array" if isinstance(parsed, list) else "object",
                        "parsed_length": len(parsed),
                        "sample": _bounded_projection(
                            parsed,
                            max_string_chars=max_string_chars,
                            max_collection_items=min(max_collection_items, 3),
                            depth=depth + 1,
                        ),
                    }
        return value[:max_string_chars]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [
            _bounded_projection(
                child,
                max_string_chars=max_string_chars,
                max_collection_items=max_collection_items,
                depth=depth + 1,
            )
            for child in value[:max_collection_items]
        ]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key in list(value)[:max_collection_items]:
            lowered = str(key).casefold()
            if (
                lowered in FORBIDDEN_PATH_SEGMENTS
                or lowered.startswith("_")
                or lowered.endswith("_id")
            ):
                continue
            result[str(key)] = _bounded_projection(
                value[key],
                max_string_chars=max_string_chars,
                max_collection_items=max_collection_items,
                depth=depth + 1,
            )
        return result
    return str(value)[:max_string_chars]
