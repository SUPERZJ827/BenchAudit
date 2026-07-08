"""Compute leaderboard impact after excluding or downselecting benchmark tasks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchcore.ranking_impact import (
    leaderboard,
    load_task_set,
    load_trials,
    ranking_impact,
    write_json,
    write_leaderboard_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", required=True, help="Per-trial JSONL with task_id, agent/model, reward")
    parser.add_argument("--exclude-tasks", help="Task ids to remove; txt/csv/json/jsonl supported")
    parser.add_argument("--exclude-task", action="append", default=[], help="Single task id to remove; repeatable")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-csv", help="System delta CSV")
    parser.add_argument(
        "--leaderboard-only",
        action="store_true",
        help="Only compute the original leaderboard; ignore exclude options.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trials = load_trials(Path(args.trials))
    if args.leaderboard_only:
        rows = [row.__dict__ for row in leaderboard(trials)]
        payload = {"leaderboard": rows}
        write_json(Path(args.out_json), payload)
        if args.out_csv:
            write_leaderboard_csv(Path(args.out_csv), rows)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    exclude_tasks = set(args.exclude_task)
    if args.exclude_tasks:
        exclude_tasks |= load_task_set(Path(args.exclude_tasks))
    payload = ranking_impact(trials, exclude_tasks)
    write_json(Path(args.out_json), payload)
    if args.out_csv:
        write_leaderboard_csv(Path(args.out_csv), payload["system_deltas"])
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
