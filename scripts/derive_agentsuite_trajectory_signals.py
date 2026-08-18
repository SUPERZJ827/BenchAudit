#!/usr/bin/env python3
"""Derive optional solver-disagreement signals from published model trajectories.

Where a benchmark publishes what many models actually produced for a task, two
deterministic quantities fall out for free: how much those models disagree, and
how often they fail. A task whose required parameters admit several defensible
fills shows up as disagreement without anyone judging whether it is ambiguous.

Trajectories are optional evidence. Nothing here is required to audit an item,
and an item with no trajectories simply gets no signal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

CALL_LINE = re.compile(r"\[[A-Za-z_][^\n]*\]\s*$")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_id(task_name: str, raw_id: Any) -> str:
    text = str(raw_id)
    return text[len(task_name) + 1:] if text.startswith(task_name + "_") else text


def emitted_call(row: dict[str, Any]) -> str:
    """The call the model actually produced, with any reasoning preamble dropped."""
    text = "".join(
        str(message.get("content") or "")
        for message in row.get("messages", [])
        if message.get("role") == "assistant"
    ).strip()
    match = CALL_LINE.search(text)
    return match.group().strip() if match else text


def signals(calls: list[str], scores: list[float]) -> dict[str, Any]:
    counts = Counter(calls)
    total = sum(counts.values())
    majority = counts.most_common(1)[0][1] if counts else 0
    failed = sum(1 for s in scores if not s)
    return {
        "models": total,
        "distinct_outputs": len(counts),
        # 1.0 means every model produced something different.
        "disagreement": round(1 - majority / total, 4) if total else 0.0,
        "failure_rate": round(failed / total, 4) if total else 0.0,
        "majority_share": round(majority / total, 4) if total else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectory-dir", required=True, type=Path,
                        help="directory of <model>.jsonl trajectory files")
    parser.add_argument("--item-ids", required=True, type=Path,
                        help="jsonl carrying the `id` of every item to score")
    parser.add_argument("--id-prefix", default="agentsuite-ace::",
                        help="prefix our item ids carry over the benchmark's own ids")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite existing artifact: {args.out}")

    wanted = {
        str(json.loads(line)["id"]).removeprefix(args.id_prefix)
        for line in args.item_ids.read_text(encoding="utf-8").splitlines() if line
    }
    calls: dict[str, list[str]] = defaultdict(list)
    scores: dict[str, list[float]] = defaultdict(list)
    files = sorted(args.trajectory_dir.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"no trajectory files under {args.trajectory_dir}")
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            task = str(row.get("task_name") or "")
            key = f"{task}::{normalized_id(task, (row.get('meta') or {}).get('id'))}"
            if key not in wanted:
                continue
            calls[key].append(emitted_call(row))
            scores[key].append((row.get("eval_result") or {}).get("score", 0))

    per_item = {key: signals(calls[key], scores[key]) for key in sorted(calls)}
    result = {
        "schema_version": 1,
        "protocol": "trajectory-disagreement-signal-v1",
        "claims_ceiling": "deterministic statistics over published solver attempts; "
                          "a signal for ranking and corroboration, not a defect claim",
        "trajectory_dir": str(args.trajectory_dir),
        "trajectory_files": len(files),
        "items_requested": len(wanted),
        "items_with_trajectories": len(per_item),
        "items_without_trajectories": sorted(wanted - set(per_item)),
        "signals": per_item,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in
                      ("trajectory_files", "items_requested", "items_with_trajectories")},
                     ensure_ascii=False, indent=2))
    print(f"written {args.out} sha256={sha256_file(args.out)[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
