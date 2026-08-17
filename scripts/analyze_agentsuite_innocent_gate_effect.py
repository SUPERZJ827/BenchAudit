#!/usr/bin/env python3
"""Post-hoc, zero-API decomposition of prompt effects versus the hard gate."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import benchcore.artifact_consistency as artifact_consistency
from benchcore.artifact_consistency import CrossArtifactConsistencyChecker
from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.loader import build_items, load_mapping, load_rows
from scripts.run_agentsuite_innocent_explanation_ab import build_treatment_prompt


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def metrics(predicted: set[str], positive: set[str], all_ids: set[str]) -> dict[str, Any]:
    tp = len(predicted & positive)
    fp = len(predicted - positive)
    fn = len(positive - predicted)
    tn = len((all_ids - positive) - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "candidates": len(predicted),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "metrics": {"precision": precision, "recall": recall, "f1": f1},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--llm-config", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path, action="append")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    rows = load_rows(args.input)
    items = build_items(rows, load_mapping(args.mapping, rows), source_indices=list(range(len(rows))))
    truth = {str(row["id"]): int(row["is_issue"]) for row in load_jsonl(args.truth)}
    all_ids = {item.item_id for item in items}
    positive = {item_id for item_id, label in truth.items() if label == 1}
    if len(items) != 102 or set(truth) != all_ids or len(positive) != 51:
        raise SystemExit("unexpected ACEBench development subset")

    artifact_consistency.USER_PROMPT = build_treatment_prompt(
        artifact_consistency.USER_PROMPT
    )
    config = load_llm_config(args.llm_config)
    scored: dict[str, Any] = {}
    for cache_path in args.cache:
        client = LLMClient(replace(config, cache_path=str(cache_path)))
        checker = CrossArtifactConsistencyChecker(client)
        predicted: set[str] = set()
        for item in items:
            if list(checker.check(item, root=args.input.parent)):
                predicted.add(item.item_id)
        stats = client.run_stats()
        if stats["api_attempts"] != 0 or stats["cache_hits"] != 102:
            raise SystemExit(
                f"offline invariant failed for {cache_path}: "
                f"attempts={stats['api_attempts']} hits={stats['cache_hits']}"
            )
        scored[cache_path.parent.name] = {
            **metrics(predicted, positive, all_ids),
            "cache_hits": stats["cache_hits"],
            "api_attempts": stats["api_attempts"],
        }

    result = {
        "schema_version": 1,
        "status": "POST_HOC_ZERO_API_PROMPT_ONLY_DIAGNOSTIC",
        "warning": "not preregistered; decomposes the already-scored treatment only",
        "runs": scored,
    }
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite output: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
