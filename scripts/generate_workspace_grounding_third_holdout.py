#!/usr/bin/env python3
"""Freeze the third task-disjoint Workspace grounding holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from scripts.generate_workspace_p0_blind_package import sha256_file
from scripts.run_workspace_static_llm_ablation import (
    NEGATIVE_REVIEW_LABEL,
    POSITIVE_REVIEW_LABEL,
    parse_reviewed_reference,
)


PROTOCOL = "workspace-grounding-third-holdout-v1-20260729"
SEED = PROTOCOL


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-manifest", type=Path, action="append", required=True)
    parser.add_argument("--reviewed-reference", type=Path, required=True)
    parser.add_argument("--protocol-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def select_tasks(
    reviewed: dict[tuple[str, int], str],
    *,
    excluded: set[str],
) -> tuple[list[str], dict[str, Counter[str]]]:
    by_task: dict[str, Counter[str]] = defaultdict(Counter)
    for (item_id, _), label in reviewed.items():
        if item_id not in excluded:
            by_task[item_id][label] += 1
    positive = sorted(
        item_id for item_id, counts in by_task.items()
        if counts[POSITIVE_REVIEW_LABEL] > 0
    )
    negative_only = sorted(
        item_id for item_id, counts in by_task.items()
        if (
            counts[POSITIVE_REVIEW_LABEL] == 0
            and counts[NEGATIVE_REVIEW_LABEL] > 0
        )
    )
    rng = random.Random(SEED)
    rng.shuffle(positive)
    rng.shuffle(negative_only)
    selected = [*positive[:20], *negative_only[:10]]
    if len(selected) != 30 or len(set(selected)) != 30:
        raise ValueError("third holdout must contain 30 unique tasks")
    return selected, by_task


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True,
    ).strip()


def main() -> None:
    args = parse_args()
    manifests = [
        path.expanduser().resolve() for path in args.development_manifest
    ]
    excluded = set()
    for path in manifests:
        document = json.loads(path.read_text(encoding="utf-8"))
        excluded.update(str(value) for value in document["item_ids"])
    reviewed_path = args.reviewed_reference.expanduser().resolve()
    protocol_path = args.protocol_file.expanduser().resolve()
    reviewed = parse_reviewed_reference(reviewed_path)
    selected, by_task = select_tasks(reviewed, excluded=excluded)
    positive_tasks = [
        item_id for item_id in selected
        if by_task[item_id][POSITIVE_REVIEW_LABEL] > 0
    ]
    negative_tasks = [
        item_id for item_id in selected
        if by_task[item_id][POSITIVE_REVIEW_LABEL] == 0
    ]
    result = {
        "protocol": PROTOCOL,
        "selection_seed": SEED,
        "git_head": git_head(),
        "selection_policy": [
            {"name": "reviewed_positive_task", "count": 20},
            {"name": "reviewed_negative_without_positive_task", "count": 10},
        ],
        "item_ids": selected,
        "counts": {
            "tasks": len(selected),
            "positive_tasks": len(positive_tasks),
            "negative_only_tasks": len(negative_tasks),
            "reviewed_positive_rubrics": sum(
                by_task[item_id][POSITIVE_REVIEW_LABEL] for item_id in selected
            ),
            "reviewed_negative_rubrics": sum(
                by_task[item_id][NEGATIVE_REVIEW_LABEL] for item_id in selected
            ),
        },
        "frozen_system": {
            "contract_version": (
                "workspace-grounding-decision-contract-v1-20260729"
            ),
            "strategy": "item-exact-triage",
            "llm_router": "hidden_constraint",
            "deterministic_router": "exact_constraint",
            "verifier_enabled": False,
            "model": "deepseek-v4-flash",
            "temperature": 0.0,
        },
        "api_budget": {
            "logical_calls": 30,
            "max_attempts": 40,
            "total_tokens_soft_stop": 600000,
            "exact_router_calls": 0,
        },
        "input_sha256": {
            "reviewed_reference": sha256_file(reviewed_path),
            "protocol_file": sha256_file(protocol_path),
            "development_manifests": {
                str(path): sha256_file(path) for path in manifests
            },
        },
        "selection_sha256": hashlib.sha256(
            json.dumps(
                selected, ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
