#!/usr/bin/env python3
"""Download and convert SVAMP-Platinum for supervised benchmark auditing."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

from datasets import load_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchcore.sampling import build_sample, write_jsonl, write_manifest


DEFAULT_OUT = Path(
    "/home/zhoujun/llmdata/datasets/svamp_platinum/svamp_platinum_all.jsonl"
)
DEFAULT_MANIFEST = PROJECT_ROOT / "experiments/svamp_platinum_pilot100.manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare SVAMP-Platinum and a defect-enriched Pilot 100 manifest."
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pilot-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    dataset = load_dataset("madrylab/platinum-bench", "svamp", split="test")
    rows = [convert_row(row) for row in dataset]
    write_jsonl(args.out, rows)

    defect_count = sum(row["metadata"]["audit_label"] != "clean" for row in rows)
    pilot_size = min(max(args.pilot_size, defect_count), len(rows))
    sample, manifest = build_sample(
        rows,
        source_path=args.out,
        size=pilot_size,
        seed=args.seed,
        stratify_fields=[],
        id_field="id",
        label_field="metadata.audit_label",
        clean_values={"clean"},
        defect_fraction=defect_count / pilot_size,
    )
    write_manifest(args.manifest, manifest)

    status_counts = Counter(row["metadata"]["cleaning_status"] for row in rows)
    label_counts = Counter(row["metadata"]["audit_label"] for row in rows)
    print(f"wrote {len(rows)} items to {args.out}")
    print(f"cleaning_status={dict(status_counts)}")
    print(f"audit_label={dict(label_counts)}")
    print(f"pilot_items={len(sample)} manifest={args.manifest}")
    return 0


def convert_row(row: dict) -> dict:
    status = str(row["cleaning_status"])
    original_target = first_value(row.get("original_target"))
    platinum_target = first_value(row.get("platinum_target"))
    if status == "revised":
        audit_label = "wrong_gold"
    elif status == "rejected":
        audit_label = "bad_question"
    else:
        audit_label = "clean"

    return {
        "id": f"svamp-platinum-{row['ID']}",
        "task": row["question_concat"],
        "gold": original_target,
        "output_contract": {
            "type": "number",
            "format": "single numeric answer",
        },
        "evaluator": {
            "type": "numeric_exact_match",
        },
        "metadata": {
            # These supervision fields are stripped before every LLM call.
            "audit_label": audit_label,
            "cleaning_status": status,
            "platinum_target": platinum_target,
            "human_defect": audit_label != "clean",
            # Safe task metadata may be exposed to auditors.
            "problem_type": row.get("Type"),
            "source_dataset": "SVAMP",
        },
    }


def first_value(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


if __name__ == "__main__":
    raise SystemExit(main())
