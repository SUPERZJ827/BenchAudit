#!/usr/bin/env python3
"""Materialize the exact Fantastic Bugs GSM8K-997 comparison inputs.

The official response pickle stores questions, references, Platinum labels and
the 90 x 997 correctness matrix in one pandas object.  This script separates
them into three hash-bound artifacts so the audit path cannot see evaluation
labels or Platinum revisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


EXPECTED_PICKLE_SHA256 = (
    "e1d2251b43f7b94a8709fde750e34469408d6e3c750001cdd9e5cbcf62984c94"
)
EXPECTED_SHAPE = (90, 997)
EXPECTED_LABELS = Counter({1: 909, 0: 88})
ANSWER_RE = re.compile(
    r"(?:The answer is|The final answer is)\s*\$?\s*([^\n]+?)\s*\.?\s*$",
    re.IGNORECASE,
)
NUMERIC_RE = re.compile(r"^[-+]?(?:\d[\d,]*)(?:\.\d+)?(?:%|/\d+)?$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def extract_reference_text(raw: Any) -> str:
    if not isinstance(raw, str):
        raise ValueError("original_answer must be a JSON string")
    references = json.loads(raw)
    if not isinstance(references, list) or len(references) != 1:
        raise ValueError("original_answer must contain exactly one reference")
    reference = references[0]
    if not isinstance(reference, dict):
        raise ValueError("reference must be an object")
    output = reference.get("output")
    if not isinstance(output, dict) or not isinstance(output.get("text"), str):
        raise ValueError("reference output.text is missing")
    return output["text"].strip()


def extract_gold(reference: str) -> str:
    match = ANSWER_RE.search(reference)
    if not match:
        raise ValueError("reference does not end with a GSM8K answer sentence")
    raw = match.group(1).strip().rstrip(".")
    if not NUMERIC_RE.fullmatch(raw):
        raise ValueError(f"reference answer is not a pure numeric scalar: {raw!r}")
    return raw.replace(",", "")


def stable_item_id(question: str) -> str:
    return "fantastic-bugs-gsm-" + hashlib.sha256(question.encode("utf-8")).hexdigest()[:20]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pickle", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    source = args.pickle.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    actual_sha = sha256_file(source)
    if actual_sha != EXPECTED_PICKLE_SHA256:
        raise SystemExit(
            f"source SHA-256 mismatch: expected {EXPECTED_PICKLE_SHA256}, got {actual_sha}"
        )

    # The pinned official file is a Python pickle.  Loading occurs only after
    # the exact upstream content hash has been verified.
    frame = pd.read_pickle(source)
    if frame.shape != EXPECTED_SHAPE:
        raise SystemExit(f"unexpected response shape: {frame.shape!r}")
    if not isinstance(frame.columns, pd.MultiIndex):
        raise SystemExit("expected a MultiIndex question axis")
    required_levels = {
        "input.text",
        "original_answer",
        "scenario",
        "benchmark",
        "platinum_answer",
        "platinum_label",
    }
    if not required_levels.issubset(set(frame.columns.names)):
        raise SystemExit(f"missing column levels: {sorted(required_levels-set(frame.columns.names))}")
    values = set(pd.unique(frame.to_numpy().ravel()).tolist())
    if values != {0.0, 1.0}:
        raise SystemExit(f"unexpected correctness values: {sorted(values)!r}")
    labels = Counter(int(value) for value in frame.columns.get_level_values("platinum_label"))
    if labels != EXPECTED_LABELS:
        raise SystemExit(f"unexpected label distribution: {labels!r}")

    model_ids = [str(value).strip() for value in frame.index]
    if len(model_ids) != len(set(model_ids)) or any(not value for value in model_ids):
        raise SystemExit("model identifiers must be nonempty and unique")

    audit_rows: list[dict[str, Any]] = []
    truth_rows: list[dict[str, Any]] = []
    response_rows: list[dict[str, Any]] = []
    questions: set[str] = set()
    item_ids: set[str] = set()
    for column_index, column in enumerate(frame.columns):
        levels = dict(zip(frame.columns.names, column, strict=True))
        question = levels["input.text"]
        if not isinstance(question, str) or not question.strip():
            raise SystemExit(f"column {column_index}: invalid question")
        question = question.strip()
        if question in questions:
            raise SystemExit(f"duplicate question at column {column_index}")
        questions.add(question)
        item_id = stable_item_id(question)
        if item_id in item_ids:
            raise SystemExit(f"item id collision at column {column_index}")
        item_ids.add(item_id)
        reference = extract_reference_text(levels["original_answer"])
        gold = extract_gold(reference)
        label = int(levels["platinum_label"])
        audit_rows.append(
            {
                "id": item_id,
                "task_type": "math",
                "question": question,
                "gold": gold,
                "evaluator": {"type": "numeric"},
                "metadata": {
                    "source": "stair-lab/fantastic-bugs:gsm",
                    "response_column_index": column_index,
                },
            }
        )
        truth_rows.append(
            {
                "id": item_id,
                "platinum_label": "invalid" if label == 0 else "valid",
            }
        )
        correctness = {
            model_id: bool(frame.iloc[row_index, column_index])
            for row_index, model_id in enumerate(model_ids)
        }
        if len(correctness) != EXPECTED_SHAPE[0]:
            raise SystemExit(f"column {column_index}: incomplete response panel")
        response_rows.append({"id": item_id, "correct": correctness})

    audit_path = out_dir / "audit_input.jsonl"
    truth_path = out_dir / "sealed_truth.jsonl"
    response_path = out_dir / "responses_90models.jsonl"
    write_jsonl(audit_path, audit_rows)
    write_jsonl(truth_path, truth_rows)
    write_jsonl(response_path, response_rows)

    output_hashes = {
        path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in (audit_path, truth_path, response_path)
    }
    receipt = {
        "schema_version": 1,
        "status": "MATERIALIZED_EXACT_ALIGNMENT",
        "source": {
            "path": str(source),
            "sha256": actual_sha,
            "expected_hf_revision": "f352dfc90388ed0e67309dd7898bb411469db387",
            "pickle_trust_boundary": (
                "official revision and exact SHA-256 verified before pandas pickle load"
            ),
        },
        "matrix": {
            "models": len(model_ids),
            "items": len(audit_rows),
            "observations": len(model_ids) * len(audit_rows),
            "value_set": [0, 1],
        },
        "truth": {"valid": labels[1], "invalid": labels[0]},
        "isolation": {
            "audit_input_contains_platinum_label": False,
            "audit_input_contains_platinum_answer": False,
            "audit_input_contains_reference_solution": False,
            "truth_file_separate": True,
            "id_sets_equal": (
                {row["id"] for row in audit_rows}
                == {row["id"] for row in truth_rows}
                == {row["id"] for row in response_rows}
            ),
        },
        "outputs": output_hashes,
    }
    receipt_path = out_dir / "materialization_receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
