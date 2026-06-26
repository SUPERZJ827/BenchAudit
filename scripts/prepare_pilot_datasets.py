#!/usr/bin/env python3
"""Prepare normalized 100-item pilot datasets for cross-benchmark audits."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from datasets import load_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchcore.sampling import build_sample, write_jsonl, write_manifest


DATASET_ROOT = Path("/home/zhoujun/llmdata/datasets")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        choices=("asdiv", "wikitablequestions", "all"),
        default="all",
    )
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.dataset in ("asdiv", "all"):
        prepare_asdiv(args.sample_size, args.seed)
    if args.dataset in ("wikitablequestions", "all"):
        prepare_wikitablequestions(args.sample_size, args.seed)
    return 0


def prepare_asdiv(sample_size: int, seed: int) -> None:
    ds = load_dataset("EleutherAI/asdiv", split="validation")
    rows = []
    for index, row in enumerate(ds):
        answer = normalize_asdiv_answer(row.get("answer"))
        compound_answer = is_compound_answer(answer)
        ratio_answer = is_ratio_answer(answer)
        evaluator_type = (
            "compound_normalized_exact_match"
            if compound_answer
            else (
                "ratio_or_normalized_exact"
                if ratio_answer
                else ("numeric_or_normalized_exact" if has_number(answer) else "normalized_exact")
            )
        )
        rows.append(
            {
                "id": f"asdiv-validation-{index}",
                "question": join_text(row.get("body"), row.get("question")),
                "gold": answer,
                "aliases": unique_strings([row.get("answer"), answer, *ratio_aliases(answer)]),
                "output_contract": {
                    "type": (
                        "compound_answer"
                        if compound_answer
                        else (
                            "ratio"
                            if ratio_answer
                            else ("number" if has_number(answer) else "short_text")
                        )
                    ),
                    "format": (
                        "single response containing all requested values"
                        if compound_answer
                        else "single answer"
                    ),
                },
                "evaluator": {"type": evaluator_type},
                "metadata": {
                    "source": "EleutherAI/asdiv",
                    "split": "validation",
                    "index": index,
                    "solution_type": row.get("solution_type"),
                    "formula": row.get("formula"),
                    "raw_answer": row.get("answer"),
                    "audit_label": "unlabeled",
                },
            }
        )
    write_dataset_and_manifest(
        rows,
        dataset_name="asdiv",
        sample_size=sample_size,
        seed=seed,
        stratify_fields=["metadata.solution_type"],
    )


def prepare_wikitablequestions(sample_size: int, seed: int) -> None:
    ds = load_dataset("lighteval/wikitablequestions", split="test")
    rows = []
    for index, row in enumerate(ds):
        answers = [str(value) for value in row.get("answers", []) if str(value).strip()]
        table_md = row.get("table_md") or ""
        rows.append(
            {
                "id": f"wtq-test-{row.get('id') or index}",
                "question": row.get("question"),
                "context": {
                    "table_markdown": table_md,
                },
                "table": table_md,
                "gold": answers if len(answers) > 1 else (answers[0] if answers else None),
                "aliases": [],
                "output_contract": {
                    "type": "answer_set" if len(answers) > 1 else "short_text_or_number",
                    "format": (
                        "set/list of all answers; order-insensitive"
                        if len(answers) > 1
                        else "single answer"
                    ),
                },
                "evaluator": {
                    "type": "denotation_set_match" if len(answers) > 1 else "normalized_exact_match"
                },
                "metadata": {
                    "source": "lighteval/wikitablequestions",
                    "split": "test",
                    "index": index,
                    "table_name": (row.get("table") or {}).get("name"),
                    "audit_label": "unlabeled",
                },
            }
        )
    write_dataset_and_manifest(
        rows,
        dataset_name="wikitablequestions",
        sample_size=sample_size,
        seed=seed,
        stratify_fields=[],
    )


def write_dataset_and_manifest(
    rows: list[dict[str, Any]],
    dataset_name: str,
    sample_size: int,
    seed: int,
    stratify_fields: list[str],
) -> None:
    dataset_dir = DATASET_ROOT / dataset_name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    source_path = dataset_dir / f"{dataset_name}_normalized_all.jsonl"
    sample_path = PROJECT_ROOT / "experiments" / f"{dataset_name}_pilot{sample_size}.jsonl"
    manifest_path = PROJECT_ROOT / "experiments" / f"{dataset_name}_pilot{sample_size}.manifest.json"

    write_jsonl(source_path, rows)
    sample_rows, manifest = build_sample(
        rows,
        source_path=source_path,
        size=sample_size,
        seed=seed,
        stratify_fields=stratify_fields,
        id_field="id",
    )
    write_jsonl(sample_path, sample_rows)
    write_manifest(manifest_path, manifest)
    print(
        json.dumps(
            {
                "dataset": dataset_name,
                "source": str(source_path),
                "source_items": len(rows),
                "sample": str(sample_path),
                "manifest": str(manifest_path),
                "sample_items": len(sample_rows),
                "seed": seed,
                "stratify_fields": stratify_fields,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def normalize_asdiv_answer(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if ";" in text:
        parts = [normalize_asdiv_answer(part) for part in text.split(";")]
        return "; ".join(part for part in parts if part)
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    return text or None


def has_number(value: Any) -> bool:
    if value is None:
        return False
    return re.search(r"[-+]?\d+(?:\.\d+)?", str(value)) is not None


def is_compound_answer(value: Any) -> bool:
    return isinstance(value, str) and ";" in value


def is_ratio_answer(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.fullmatch(r"\s*[-+]?\d+(?:\.\d+)?\s*:\s*[-+]?\d+(?:\.\d+)?\s*", value))


def ratio_aliases(value: Any) -> list[str]:
    if not is_ratio_answer(value):
        return []
    left, right = [float(part.strip()) for part in str(value).split(":", 1)]
    if right == 0:
        return []
    fraction = f"{_format_number(left)}/{_format_number(right)}"
    decimal = _format_number(left / right)
    return [fraction, decimal]


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.12g}"


def join_text(*parts: Any) -> str:
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def unique_strings(values: list[Any]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
