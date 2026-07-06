"""Export SWE-bench HuggingFace splits to local JSONL for benchcore audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DATASET_PRESETS = {
    "lite": ("princeton-nlp/SWE-bench_Lite", "test"),
    "verified": ("princeton-nlp/SWE-bench_Verified", "test"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["lite", "verified", "both"], default="both")
    parser.add_argument("--out-dir", default="datasets/swebench")
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def rows_for_dataset(path: str, split: str, limit: int | None) -> list[dict[str, Any]]:
    from datasets import load_dataset

    ds = load_dataset(path, split=split)
    rows = []
    for index, row in enumerate(ds):
        if limit is not None and index >= limit:
            break
        rows.append(with_benchcore_fields(dict(row)))
    return rows


def with_benchcore_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Add generic BenchCore fields while preserving original SWE-bench fields."""
    out = dict(row)
    out.setdefault("item_id", row.get("instance_id"))
    out.setdefault("task", row.get("problem_statement"))
    out.setdefault("gold", row.get("patch"))
    out.setdefault(
        "output_contract",
        {
            "type": "git_patch",
            "format": "unified_diff",
            "description": "Submit a repository patch that fixes the issue.",
        },
    )
    out.setdefault(
        "evaluator",
        {
            "type": "swebench_pytest",
            "test_patch": row.get("test_patch"),
            "fail_to_pass": row.get("FAIL_TO_PASS"),
            "pass_to_pass": row.get("PASS_TO_PASS"),
        },
    )
    metadata = out.get("metadata") if isinstance(out.get("metadata"), dict) else {}
    metadata = dict(metadata)
    for key in (
        "instance_id",
        "repo",
        "base_commit",
        "environment_setup_commit",
        "version",
        "created_at",
    ):
        if key in row:
            metadata.setdefault(key, row.get(key))
    out["metadata"] = metadata
    return out


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    labels = ["lite", "verified"] if args.suite == "both" else [args.suite]
    out_dir = Path(args.out_dir)
    for label in labels:
        dataset_path, split = DATASET_PRESETS[label]
        rows = rows_for_dataset(dataset_path, split, args.limit)
        suffix = f"_{args.limit}" if args.limit is not None else ""
        out_path = out_dir / f"{label}{suffix}.jsonl"
        write_jsonl(out_path, rows)
        print(f"{label}: wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
