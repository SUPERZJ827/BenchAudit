#!/usr/bin/env python3
"""Compare ACEBench audit arms across repeated runs, halves, and vote thresholds.

Single runs of the same arm differ by several true positives, so an arm is
summarised by its median and range over repeats, never by its best run. Arms are
also compared per item, because which cases an arm uniquely recovers is more
informative than the aggregate count on 51 positives.

Deliberately self-contained: these experiment scripts are hash-recorded in run
receipts, so a shared helper module would let one edit silently change the
behaviour of already-frozen experiments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_METHODS = ("llm_cross_artifact_consistency",)
COBA_REFERENCE = {"tp": 45, "fp": 7, "precision": 0.865, "recall": 0.882, "f1": 0.874}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def candidate_ids(report: dict[str, Any], allowed_methods: frozenset[str]) -> set[str]:
    return {
        str(row["item_id"])
        for row in report.get("violations", [])
        if row.get("detection_method") in allowed_methods
        and row.get("defect_scope", "substantive") not in {"presentation", "operational"}
        and row.get("defect_type") != "llm_audit_failure"
    }


def metrics(predicted: set[str], positive: set[str], scope: set[str]) -> dict[str, Any]:
    predicted = predicted & scope
    positive = positive & scope
    tp, fp = len(predicted & positive), len(predicted - positive)
    fn, tn = len(positive - predicted), len((scope - positive) - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "candidates": len(predicted),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def summarise(per_run: list[dict[str, Any]]) -> dict[str, Any]:
    """Median and range of every metric, so no arm is judged by its best run."""
    keys = ("tp", "fp", "precision", "recall", "f1")
    return {
        "runs": len(per_run),
        "median": {key: median([run[key] for run in per_run]) for key in keys},
        "range": {
            key: [min(run[key] for run in per_run), max(run[key] for run in per_run)]
            for key in keys
        },
    }


def vote_union(run_candidates: list[set[str]], vote_k: int) -> set[str]:
    """Items flagged by at least ``vote_k`` of the runs."""
    counts: dict[str, int] = {}
    for candidates in run_candidates:
        for item_id in candidates:
            counts[item_id] = counts.get(item_id, 0) + 1
    return {item_id for item_id, count in counts.items() if count >= vote_k}


def paired_difference(
    left: set[str], right: set[str], positive: set[str], scope: set[str]
) -> dict[str, Any]:
    """Discordant items between two arms, split by human label."""
    left, right = left & scope, right & scope
    only_left, only_right = left - right, right - left
    return {
        "only_left_tp": sorted(only_left & positive),
        "only_right_tp": sorted(only_right & positive),
        "only_left_fp": sorted(only_left - positive),
        "only_right_fp": sorted(only_right - positive),
        "discordant_positives": len((only_left | only_right) & positive),
    }


def parse_arm(spec: str) -> tuple[str, list[Path]]:
    name, _, paths = spec.partition("=")
    if not name or not paths:
        raise SystemExit(f"arm must be given as NAME=report1.json[,report2.json...], got {spec!r}")
    return name, [Path(entry) for entry in paths.split(",") if entry]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--split-dir", type=Path, help="directory holding dev_ids.json/test_ids.json")
    parser.add_argument("--half", default="full", choices=("dev", "test", "full"))
    parser.add_argument(
        "--arm",
        action="append",
        required=True,
        metavar="NAME=REPORT[,REPORT...]",
        help="one arm and its repeated run reports; repeat the flag per arm",
    )
    parser.add_argument("--vote-k", type=int, default=1, help="votes required for the union arm")
    parser.add_argument("--methods", default=",".join(DEFAULT_METHODS))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if args.half != "full" and args.split_dir is None:
        raise SystemExit("--half dev/test requires --split-dir")

    truth_by_id = {str(row["id"]): int(row["is_issue"]) for row in load_jsonl(args.truth)}
    every_id = set(truth_by_id)
    positive = {item_id for item_id, label in truth_by_id.items() if label == 1}
    if args.half == "full":
        scope = every_id
    else:
        scope = set(load_json(args.split_dir / f"{args.half}_ids.json"))
        if not scope <= every_id:
            raise SystemExit(f"{args.half} ids are not a subset of the truth file")

    allowed_methods = frozenset(entry for entry in args.methods.split(",") if entry)
    arms: dict[str, Any] = {}
    for spec in args.arm:
        name, paths = parse_arm(spec)
        run_candidates = [candidate_ids(load_json(path), allowed_methods) for path in paths]
        for path, candidates in zip(paths, run_candidates):
            if not candidates <= every_id:
                raise SystemExit(f"{path} predicts ids outside the truth file")
        per_run = [metrics(candidates, positive, scope) for candidates in run_candidates]
        union = vote_union(run_candidates, args.vote_k)
        arms[name] = {
            "reports": [str(path) for path in paths],
            "report_sha256": [sha256_file(path) for path in paths],
            "per_run": per_run,
            "summary": summarise(per_run),
            f"vote_k{args.vote_k}": metrics(union, positive, scope),
            "_union": union,
        }

    result: dict[str, Any] = {
        "schema_version": 1,
        "half": args.half,
        "scope_items": len(scope),
        "scope_positive": len(positive & scope),
        "vote_k": args.vote_k,
        "allowed_methods": sorted(allowed_methods),
        "truth_sha256": sha256_file(args.truth),
        "arms": {name: {k: v for k, v in arm.items() if k != "_union"} for name, arm in arms.items()},
        "coba_published_reference": (
            COBA_REFERENCE if args.half == "full" else "published only for the full 102 subset"
        ),
    }
    names = list(arms)
    if len(names) == 2:
        result["paired_union_difference"] = paired_difference(
            arms[names[0]]["_union"], arms[names[1]]["_union"], positive, scope
        )

    width = max(len(name) for name in names) + 2
    print(f"half={args.half}  items={len(scope)}  positives={len(positive & scope)}")
    print(f"{'arm':<{width}}{'口径':<16}{'TP':>4}{'FP':>4}{'P':>8}{'R':>8}{'F1':>8}")
    for name, arm in arms.items():
        summary = arm["summary"]
        low, high = summary["range"]["tp"]
        print(
            f"{name:<{width}}{'单跑中位(n=' + str(summary['runs']) + ')':<16}"
            f"{summary['median']['tp']:>4.0f}{summary['median']['fp']:>4.0f}"
            f"{summary['median']['precision']:>8.3f}{summary['median']['recall']:>8.3f}"
            f"{summary['median']['f1']:>8.3f}   TP 全距 {high - low:.0f}"
        )
        union = arm[f"vote_k{args.vote_k}"]
        print(
            f"{'':<{width}}{'票数>=' + str(args.vote_k):<16}"
            f"{union['tp']:>4}{union['fp']:>4}"
            f"{union['precision']:>8.3f}{union['recall']:>8.3f}{union['f1']:>8.3f}"
        )
    if args.half == "full":
        print(
            f"{'COBA(论文值)':<{width}}{'单跑':<16}{COBA_REFERENCE['tp']:>4}{COBA_REFERENCE['fp']:>4}"
            f"{COBA_REFERENCE['precision']:>8.3f}{COBA_REFERENCE['recall']:>8.3f}"
            f"{COBA_REFERENCE['f1']:>8.3f}"
        )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
