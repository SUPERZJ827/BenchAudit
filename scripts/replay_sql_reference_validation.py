#!/usr/bin/env python3
"""Replay SQL reference parsing with a pinned SQLGlot installation.

Run with a Python environment containing exactly SQLGlot 30.2.1. This checks
that the published reference verdicts are reproducible; it does not establish
semantic equivalence or prove that SQLGlot supports every target construct.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import ErrorLevel, expressions


EXPECTED_VERSION = "30.2.1"


def _classify(reference: str, dialect: str) -> tuple[str, bool | None]:
    try:
        parsed = [
            expression
            for expression in sqlglot.parse(
                reference,
                read=dialect,
                error_level=ErrorLevel.RAISE,
            )
            if expression is not None
        ]
    except Exception:
        return "invalid", False
    if not parsed:
        return "invalid", False
    if any(isinstance(expression, expressions.Command) for expression in parsed):
        return "unsupported_fallback", None
    return "valid", True


def _sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--normalized-root",
        type=Path,
        required=True,
        help="normalized/sql_dialect directory from collection audit",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sqlglot.__version__ != EXPECTED_VERSION:
        raise SystemExit(
            f"SQLGlot version {sqlglot.__version__!r} is not pinned "
            f"{EXPECTED_VERSION!r}"
        )
    logging.getLogger("sqlglot").setLevel(logging.ERROR)

    items: dict[str, dict[str, Any]] = {}
    for path in sorted(args.normalized_root.glob("*/*.jsonl")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            row = json.loads(line)
            item_id = str(row["item_id"])
            observation = {
                "reference": row["reference"],
                "target_dialect": row["target_dialect"],
                "published_reference_valid": row["reference_valid"],
            }
            previous = items.setdefault(item_id, observation)
            if previous != observation:
                raise ValueError(
                    f"{path}:{line_number}: inconsistent repeated reference "
                    f"for item {item_id}"
                )

    counts: Counter[str] = Counter()
    mismatches = []
    rows = []
    for item_id, observation in sorted(items.items()):
        status, syntax_valid = _classify(
            observation["reference"], observation["target_dialect"]
        )
        counts[status] += 1
        if syntax_valid != observation["published_reference_valid"]:
            mismatches.append(item_id)
        rows.append({
            "item_id": item_id,
            "target_dialect": observation["target_dialect"],
            "status": status,
            "syntax_valid": syntax_valid,
            "published_reference_valid": observation["published_reference_valid"],
            "reference_sha256": hashlib.sha256(
                observation["reference"].encode("utf-8")
            ).hexdigest(),
        })

    result = {
        "schema_version": "sql-reference-replay.v1",
        "parser": "sqlglot",
        "parser_version": sqlglot.__version__,
        "items": len(items),
        "status_counts": dict(sorted(counts.items())),
        "published_replay_mismatches": len(mismatches),
        "mismatch_item_ids": mismatches,
        "evidence_boundary": (
            "Exact parser-version replay verifies reproducibility of published "
            "syntax labels, not SQL semantic correctness or dialect coverage."
        ),
        "rows": rows,
    }
    result["stable_sha256"] = _sha256(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "items": result["items"],
        "status_counts": result["status_counts"],
        "published_replay_mismatches": result["published_replay_mismatches"],
        "stable_sha256": result["stable_sha256"],
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
