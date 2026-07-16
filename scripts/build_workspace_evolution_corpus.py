#!/usr/bin/env python3
"""Build a leakage-resistant Workspace rule-evolution corpus.

This is a mechanism-recovery experiment, not evidence of a new natural
WorkspaceBench defect.  It hides the operator and side in a controller-only
sidecar, gives candidate rules opaque record IDs, and keeps all siblings from a
source task in the same train/dev/holdout split.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from benchcore.evolution.corpus import validate_corpus
from benchcore.evolution.models import (
    CORPUS_SCHEMA_VERSION,
    CorpusExample,
    canonical_sha256,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="datasets/workspacebench/full.jsonl",
        help="Pinned Workspace Full JSONL",
    )
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument("--train-groups", type=int, default=188)
    parser.add_argument("--dev-groups", type=int, default=100)
    parser.add_argument("--holdout-groups", type=int, default=100)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    rows = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    required = args.train_groups + args.dev_groups + args.holdout_groups
    if required != len(rows):
        raise ValueError(
            f"split groups total {required}, but dataset contains {len(rows)} rows"
        )
    ranked = sorted(
        rows,
        key=lambda row: hashlib.sha256(
            (
                f"workspace-evolution-split:{args.seed}:"
                f"{row.get('item_id')}:{canonical_sha256(row)}"
            ).encode("utf-8")
        ).hexdigest(),
    )
    boundaries = (
        ("train", args.train_groups),
        ("dev", args.dev_groups),
        ("holdout", args.holdout_groups),
    )
    examples: list[CorpusExample] = []
    selected_source_hashes: dict[str, list[str]] = {name: [] for name, _ in boundaries}
    offset = 0
    for split, count in boundaries:
        for source in ranked[offset : offset + count]:
            source_id = str(source.get("item_id") or "")
            source_sha = canonical_sha256(source)
            group = _opaque("group", args.seed, source_id, source_sha)
            selected_source_hashes[split].append(source_sha)
            clean, mutant = _paired_rows(source, args.seed, source_sha)
            examples.extend([
                CorpusExample(
                    example_id=_opaque("example-a", args.seed, source_id, source_sha),
                    source_group=group,
                    split=split,
                    row=clean,
                    expected_defect_types=(),
                ),
                CorpusExample(
                    example_id=_opaque("example-b", args.seed, source_id, source_sha),
                    source_group=group,
                    split=split,
                    row=mutant,
                    expected_defect_types=("schema_drift",),
                ),
            ])
        offset += count
    validate_corpus(examples)
    payload = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "experiment": "workspace-rubric-type-cardinality-mechanism-recovery-v2",
        "claim_scope": (
            "controlled sidecar-only mechanism recovery; not natural-defect recall"
        ),
        "source": str(input_path),
        "source_sha256": _file_sha256(input_path),
        "seed": args.seed,
        "split_groups": {name: count for name, count in boundaries},
        "split_source_manifest_sha256": {
            split: canonical_sha256(values)
            for split, values in selected_source_hashes.items()
        },
        "visible_row_fields": ["item_id", "task", "rubrics", "rubric_types"],
        "label_visibility": {
            "candidate_rule": False,
            "remote_synthesizer": "train labels only",
            "development_gate": True,
            "sealed_holdout_gate": True,
        },
        "examples": [example.to_dict() for example in examples],
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "source_rows": len(rows),
        "examples": len(examples),
        "train": sum(example.split == "train" for example in examples),
        "dev": sum(example.split == "dev" for example in examples),
        "holdout": sum(example.split == "holdout" for example in examples),
        "output": str(output.resolve()),
        "sha256": _file_sha256(output),
    }, ensure_ascii=False, indent=2))
    return 0


def _paired_rows(
    source: dict[str, Any],
    seed: int,
    source_sha: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rubrics = _jsonish_list(source.get("rubrics"))
    rubric_types = _jsonish_list(source.get("rubric_types"))
    if not rubrics or len(rubrics) != len(rubric_types):
        raise ValueError("source row is not eligible for cardinality intervention")
    clean = {
        "item_id": _opaque("visible-a", seed, source_sha),
        "task": "Audit the internal consistency of this Workspace benchmark record.",
        # Preserve the deployment representation.  Workspace Full stores
        # rubric_types as JSON text while rubrics is already a list.  The v1
        # challenge parsed both into lists, allowing a generated rule to pass
        # its holdout yet flag every natural row after representation shift.
        "rubrics": copy.deepcopy(source.get("rubrics")),
        "rubric_types": copy.deepcopy(source.get("rubric_types")),
    }
    mutant = copy.deepcopy(clean)
    mutant["item_id"] = _opaque("visible-b", seed, source_sha)
    # One atomic intervention.  Operator/side/expected label never enters row.
    reduced_types = rubric_types[:-1]
    mutant["rubric_types"] = (
        json.dumps(reduced_types, ensure_ascii=False, separators=(",", ":"))
        if isinstance(source.get("rubric_types"), str)
        else reduced_types
    )
    return clean, mutant


def _jsonish_list(value: Any) -> list[Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise ValueError("expected a list or JSON-encoded list")
    return value


def _opaque(domain: str, seed: int, *parts: str) -> str:
    payload = ":".join((domain, str(seed), *parts))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:28]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
