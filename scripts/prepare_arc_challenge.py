#!/usr/bin/env python3
"""Prepare normalized ARC-Challenge pilot dataset for BenchCore audit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from datasets import load_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchcore.sampling import build_sample, write_jsonl, write_manifest

DATASET_ROOT = Path("/home/zhoujun/llmdata/datasets")
ALPHA_LABELS = "ABCDE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    prepare_arc_challenge(args.sample_size, args.seed)
    return 0


def prepare_arc_challenge(sample_size: int, seed: int) -> None:
    ds = load_dataset("allenai/ai2_arc", "ARC-Challenge", split="test")
    rows = []
    schema_types = set()

    for row in ds:
        choices_text: list[str] = row["choices"]["text"]
        choices_label: list[str] = row["choices"]["label"]
        answer_key: str = row["answerKey"]

        # Detect label schema: alphabetic (A/B/C/D) or numeric (1/2/3/4)
        is_numeric = all(lbl.isdigit() for lbl in choices_label)
        schema_type = "numeric_1234" if is_numeric else "alpha_ABCD"
        schema_types.add(schema_type)

        # Normalize to A/B/C/D for BenchCore evaluator
        if is_numeric:
            gold_idx = int(answer_key) - 1  # "2" → index 1 → "B"
        else:
            gold_idx = ALPHA_LABELS.index(answer_key.upper()) if answer_key.upper() in ALPHA_LABELS else None

        gold_normalized = ALPHA_LABELS[gold_idx] if gold_idx is not None else answer_key

        rows.append(
            {
                "id": f"arc-challenge-test-{row['id']}",
                "question": row["question"],
                "choices": choices_text,
                "gold": gold_normalized,
                "aliases": [],
                "output_contract": {
                    "type": "multiple_choice",
                    "format": "single letter A/B/C/D",
                },
                "evaluator": {"type": "choice_exact_match"},
                "metadata": {
                    "source": "allenai/ai2_arc",
                    "config": "ARC-Challenge",
                    "split": "test",
                    "original_id": row["id"],
                    "original_answer_key": answer_key,
                    "original_choice_labels": choices_label,
                    "choice_label_schema": schema_type,
                    "audit_label": "unlabeled",
                },
            }
        )

    # Report schema drift upfront
    print(
        json.dumps(
            {
                "total_items": len(rows),
                "schema_types": {
                    t: sum(1 for r in rows if r["metadata"]["choice_label_schema"] == t)
                    for t in schema_types
                },
                "note": (
                    "22 items use numeric choice labels (1/2/3/4) from NYSEDREGENTS source. "
                    "Gold is normalized to A/B/C/D for evaluator compatibility; "
                    "original labels preserved in metadata.original_choice_labels."
                ),
            },
            indent=2,
        )
    )

    dataset_dir = DATASET_ROOT / "arc_challenge"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    source_path = dataset_dir / "arc_challenge_normalized_all.jsonl"
    sample_path = PROJECT_ROOT / "experiments" / f"arc_challenge_pilot{sample_size}.jsonl"
    manifest_path = PROJECT_ROOT / "experiments" / f"arc_challenge_pilot{sample_size}.manifest.json"

    write_jsonl(source_path, rows)
    sample_rows, manifest = build_sample(
        rows,
        source_path=source_path,
        size=sample_size,
        seed=seed,
        stratify_fields=[],
        id_field="id",
    )
    write_jsonl(sample_path, sample_rows)
    write_manifest(manifest_path, manifest)

    print(
        json.dumps(
            {
                "dataset": "arc_challenge",
                "source": str(source_path),
                "source_items": len(rows),
                "sample": str(sample_path),
                "manifest": str(manifest_path),
                "sample_items": len(sample_rows),
                "seed": seed,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
