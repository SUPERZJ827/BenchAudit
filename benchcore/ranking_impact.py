from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class TrialResult:
    task_id: str
    system_id: str
    reward: float
    raw: dict[str, Any]


@dataclass(frozen=True)
class LeaderboardRow:
    system_id: str
    score: float
    n_trials: int
    rank: int


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row at {path}:{line_no} is not an object")
            rows.append(row)
    return rows


def load_trials(path: Path) -> list[TrialResult]:
    trials: list[TrialResult] = []
    for row in load_jsonl(path):
        task_id = str(row.get("task_id") or row.get("task_name") or "").strip()
        if task_id.startswith("terminal-bench/"):
            task_id = task_id.removeprefix("terminal-bench/")
        if not task_id:
            continue
        system_id = system_identifier(row)
        reward = row.get("reward")
        # Harbor/Terminal-Bench uses null reward for failed/error trials; the public
        # aggregate treats these as score 0.
        numeric_reward = 0.0 if reward is None else float(reward)
        trials.append(TrialResult(task_id=task_id, system_id=system_id, reward=numeric_reward, raw=row))
    return trials


def system_identifier(row: dict[str, Any]) -> str:
    agent = str(row.get("agent") or row.get("agent_name") or "").strip()
    model = str(row.get("model") or row.get("model_name") or "").strip()
    if agent and model:
        return f"{agent} / {model}"
    return str(row.get("system_id") or row.get("model") or row.get("agent") or "unknown").strip()


def leaderboard(trials: Iterable[TrialResult], exclude_tasks: set[str] | None = None) -> list[LeaderboardRow]:
    excluded = normalize_task_ids(exclude_tasks or set())
    grouped: dict[str, list[float]] = {}
    for trial in trials:
        if trial.task_id in excluded:
            continue
        grouped.setdefault(trial.system_id, []).append(trial.reward)
    rows = [
        LeaderboardRow(system_id=system, score=sum(scores) / len(scores), n_trials=len(scores), rank=0)
        for system, scores in grouped.items()
        if scores
    ]
    rows.sort(key=lambda row: (-row.score, row.system_id))
    return [LeaderboardRow(row.system_id, row.score, row.n_trials, rank=index + 1) for index, row in enumerate(rows)]


def ranking_impact(
    trials: Iterable[TrialResult],
    exclude_tasks: set[str],
) -> dict[str, Any]:
    trial_list = list(trials)
    original = leaderboard(trial_list)
    cleaned = leaderboard(trial_list, exclude_tasks=exclude_tasks)
    original_by_system = {row.system_id: row for row in original}
    cleaned_by_system = {row.system_id: row for row in cleaned}
    systems = sorted(set(original_by_system) & set(cleaned_by_system))
    rows: list[dict[str, Any]] = []
    for system in systems:
        before = original_by_system[system]
        after = cleaned_by_system[system]
        rows.append(
            {
                "system_id": system,
                "original_rank": before.rank,
                "cleaned_rank": after.rank,
                "rank_delta": after.rank - before.rank,
                "original_score": before.score,
                "cleaned_score": after.score,
                "score_delta": after.score - before.score,
                "original_n_trials": before.n_trials,
                "cleaned_n_trials": after.n_trials,
            }
        )
    return {
        "excluded_tasks": sorted(normalize_task_ids(exclude_tasks)),
        "n_excluded_tasks": len(normalize_task_ids(exclude_tasks)),
        "original_leaderboard": [row.__dict__ for row in original],
        "cleaned_leaderboard": [row.__dict__ for row in cleaned],
        "system_deltas": sorted(rows, key=lambda row: row["original_rank"]),
        "pairwise_flips": pairwise_flips(original, cleaned),
        "kendall_tau": kendall_tau_from_leaderboards(original, cleaned),
        "spearman_rho": spearman_rho_from_leaderboards(original, cleaned),
    }


def normalize_task_ids(task_ids: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for task_id in task_ids:
        value = str(task_id).strip()
        if not value:
            continue
        if value.startswith("terminal-bench/"):
            value = value.removeprefix("terminal-bench/")
        out.add(value)
    return out


def load_task_set(path: Path) -> set[str]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return normalize_task_ids(str(x) for x in data)
        if isinstance(data, dict):
            for key in ("task_ids", "tasks", "excluded_tasks"):
                if isinstance(data.get(key), list):
                    return normalize_task_ids(str(x) for x in data[key])
        raise ValueError(f"Cannot read task set from JSON file {path}")
    if suffix == ".jsonl":
        tasks = set()
        for row in load_jsonl(path):
            value = row.get("task_id") or row.get("item_id") or row.get("task_name")
            if value:
                tasks.add(str(value))
        return normalize_task_ids(tasks)
    if suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            field = "task_id" if "task_id" in (reader.fieldnames or []) else (reader.fieldnames or [""])[0]
            return normalize_task_ids(row.get(field, "") for row in reader)
    return normalize_task_ids(path.read_text(encoding="utf-8").splitlines())


def load_investigation_task_set(
    path: Path,
    *,
    verdicts: set[str] | None = None,
    issue_categories: set[str] | None = None,
    min_confidence: float = 0.0,
) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("investigations", data if isinstance(data, list) else [])
    if not isinstance(rows, list):
        raise ValueError(f"Cannot read investigations from {path}")
    verdicts_norm = {v.strip() for v in verdicts or set() if v.strip()}
    categories_norm = {c.strip() for c in issue_categories or set() if c.strip()}
    task_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if verdicts_norm and str(row.get("verdict", "")).strip() not in verdicts_norm:
            continue
        if categories_norm and str(row.get("issue_category", "")).strip() not in categories_norm:
            continue
        try:
            confidence = float(row.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < min_confidence:
            continue
        value = row.get("task_id") or row.get("item_id")
        if value:
            task_ids.add(str(value))
    return normalize_task_ids(task_ids)


def pairwise_flips(original: list[LeaderboardRow], cleaned: list[LeaderboardRow]) -> int:
    original_rank = {row.system_id: row.rank for row in original}
    cleaned_rank = {row.system_id: row.rank for row in cleaned}
    systems = sorted(set(original_rank) & set(cleaned_rank))
    flips = 0
    for i, a in enumerate(systems):
        for b in systems[i + 1 :]:
            before = original_rank[a] - original_rank[b]
            after = cleaned_rank[a] - cleaned_rank[b]
            if before == 0 or after == 0:
                continue
            if (before < 0) != (after < 0):
                flips += 1
    return flips


def kendall_tau_from_leaderboards(original: list[LeaderboardRow], cleaned: list[LeaderboardRow]) -> float | None:
    original_rank = {row.system_id: row.rank for row in original}
    cleaned_rank = {row.system_id: row.rank for row in cleaned}
    systems = sorted(set(original_rank) & set(cleaned_rank))
    n_pairs = len(systems) * (len(systems) - 1) // 2
    if n_pairs == 0:
        return None
    concordant = 0
    discordant = 0
    for i, a in enumerate(systems):
        for b in systems[i + 1 :]:
            before = original_rank[a] - original_rank[b]
            after = cleaned_rank[a] - cleaned_rank[b]
            if before * after > 0:
                concordant += 1
            elif before * after < 0:
                discordant += 1
    return (concordant - discordant) / n_pairs


def spearman_rho_from_leaderboards(original: list[LeaderboardRow], cleaned: list[LeaderboardRow]) -> float | None:
    original_rank = {row.system_id: row.rank for row in original}
    cleaned_rank = {row.system_id: row.rank for row in cleaned}
    systems = sorted(set(original_rank) & set(cleaned_rank))
    n = len(systems)
    if n < 2:
        return None
    d2 = sum((original_rank[system] - cleaned_rank[system]) ** 2 for system in systems)
    return 1 - (6 * d2) / (n * (n * n - 1))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_leaderboard_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
