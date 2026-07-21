"""Run a frozen, same-context paired adjudication of Terminal-Bench claims.

This experiment deliberately reuses previously generated LLM findings.  It
measures only whether blinded, order-balanced A/B adjudication can distinguish
claims localized to the older release from identical controls and unresolved
claims.  Official old/new labels are never included in model prompts.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.paired_claim_adjudication import (
    FrozenClaim,
    aggregate_trials,
    build_pair_prompt,
    claim_id,
    map_trial_to_versions,
    parse_pair_response,
)
from benchcore.terminal_audit import read_task_text_files
from scripts.run_terminal_bench_paired_audit import (
    changed_tasks,
    classification_metrics,
    directory_digest,
    task_directories,
)


SELECTION_SEED = "terminal-paired-adjudication-v1"
ORDER_SCHEDULE = ("AB", "BA", "BA", "AB", "AB", "BA")
PILOT_COUNTS = {
    "incremental_tp": 6,
    "missed_by_both": 1,
    "incremental_fp": 10,
    "deterministic_tp": 10,
    "clean_negative": 4,
}
PILOT_GATES = {
    "retain_incremental_tp": 5,
    "filter_incremental_fp": 5,
    "identical_verdict_mismatch_rate_lt": 0.10,
    "union_f1_improves": True,
    "invalid_trials": 0,
}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, value: Any, lock: threading.Lock) -> None:
    line = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _task_sets(report: Mapping[str, Any]) -> dict[str, set[str]]:
    methods = report["methods"]
    deterministic = set(methods["deterministic_only"]["tp_tasks"]) | set(
        methods["deterministic_only"]["fp_proxy_tasks"]
    )
    positives = set(methods["deterministic_only"]["tp_tasks"]) | set(
        methods["deterministic_only"]["missed_tasks"]
    )
    llm = set(methods["llm_two_stage"]["tp_tasks"]) | set(
        methods["llm_two_stage"]["fp_proxy_tasks"]
    )
    universe = set(report["old_llm_results"])
    return {
        "universe": universe,
        "positives": positives,
        "deterministic": deterministic,
        "llm": llm,
        "incremental_tp": (llm - deterministic) & positives,
        "missed_by_both": positives - deterministic - llm,
        "incremental_fp": (llm - deterministic) - positives,
        "deterministic_tp": deterministic & positives,
        "clean_negative": universe - positives - deterministic - llm,
    }


def _hash_select(values: Iterable[str], count: int, stratum: str) -> list[str]:
    ranked = sorted(
        values,
        key=lambda value: hashlib.sha256(
            f"{SELECTION_SEED}:{stratum}:{value}".encode("utf-8")
        ).hexdigest(),
    )
    if len(ranked) < count:
        raise ValueError(f"stratum {stratum} has {len(ranked)} tasks, needs {count}")
    return ranked[:count]


def _freeze_claims(task_id: str, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    for row in rows:
        frozen = FrozenClaim(
            candidate_id=claim_id(task_id, row),
            category=str(row.get("category", "")),
            claim=str(row.get("claim", "")),
            why_material=str(row.get("why_material", "")),
            artifact_path=str(row.get("artifact_path", "")),
            artifact_quote=str(row.get("artifact_quote", "")),
            instruction_quote=str(row.get("instruction_quote", "")),
        )
        claims.append(frozen.prompt_dict())
    return sorted(claims, key=lambda row: row["candidate_id"])


def freeze_protocol(
    source_report: Path,
    old_repo: Path,
    new_repo: Path,
    run_root: Path,
    *,
    scope: str,
) -> dict[str, Any]:
    if run_root.exists():
        raise FileExistsError(f"run root already exists: {run_root}")
    report = _json(source_report)
    old_tasks = task_directories(old_repo)
    new_tasks = task_directories(new_repo)
    if set(old_tasks) != set(new_tasks):
        raise ValueError("old/new task universes differ")
    actual_positives = changed_tasks(old_tasks, new_tasks)
    sets = _task_sets(report)
    if sets["universe"] != set(old_tasks) or sets["positives"] != actual_positives:
        raise ValueError("source report labels do not match the supplied repositories")
    if scope == "pilot":
        strata = {
            name: _hash_select(sets[name], count, name)
            for name, count in PILOT_COUNTS.items()
        }
        selected = sorted({task for values in strata.values() for task in values})
    elif scope == "full":
        strata = {name: sorted(sets[name]) for name in PILOT_COUNTS}
        selected = sorted(sets["universe"])
    else:
        raise ValueError("scope must be pilot or full")
    membership = {
        task: sorted(name for name, values in strata.items() if task in values)
        for task in selected
    }
    frozen_tasks = []
    for task in selected:
        frozen_tasks.append({
            "task_id": task,
            "strata": membership[task],
            "positive_proxy": task in sets["positives"],
            "deterministic_candidate": task in sets["deterministic"],
            "prior_llm_candidate": task in sets["llm"],
            "old_digest": directory_digest(old_tasks[task]),
            "new_digest": directory_digest(new_tasks[task]),
            "identical_control": directory_digest(old_tasks[task]) == directory_digest(new_tasks[task]),
            "claims": _freeze_claims(
                task, report["old_llm_results"][task].get("accepted", [])
            ),
        })
    protocol = {
        "schema_version": "terminal-noise-controlled-protocol-v1",
        "scope": scope,
        "selection_seed": SELECTION_SEED,
        "selection_counts": PILOT_COUNTS if scope == "pilot" else None,
        "order_schedule": list(ORDER_SCHEDULE),
        "source_report": str(source_report.resolve()),
        "source_report_sha256": _sha256_bytes(source_report.read_bytes()),
        "old_repo": str(old_repo.resolve()),
        "new_repo": str(new_repo.resolve()),
        "universe_size": len(sets["universe"]),
        "positive_proxy_size": len(sets["positives"]),
        "strata": strata,
        "tasks": frozen_tasks,
        "gates": PILOT_GATES if scope == "pilot" else None,
        "blindness": (
            "The model sees A/B packets in balanced hidden order. Release names, change labels, "
            "strata, and expected direction are absent from prompts."
        ),
        "confirmation_policy": "paired LLM evidence remains review-only",
    }
    protocol["protocol_sha256"] = _canonical_sha256(protocol)
    run_root.mkdir(parents=True)
    _write_json(run_root / "frozen_protocol.json", protocol)
    return protocol


def _claim_objects(rows: Sequence[Mapping[str, Any]]) -> list[FrozenClaim]:
    return [
        FrozenClaim(
            candidate_id=str(row["candidate_id"]),
            category=str(row["category"]),
            claim=str(row["claim"]),
            why_material=str(row["why_material"]),
            artifact_path=str(row["original_artifact_path"]),
            artifact_quote=str(row["original_artifact_quote"]),
            instruction_quote=str(row.get("original_instruction_quote", "")),
        )
        for row in rows
    ]


def _clip(text: str, quotes: Sequence[str], allowance: int) -> str:
    if len(text) <= allowance:
        return text
    normalized_quotes = [quote for quote in quotes if quote and quote in text]
    if not normalized_quotes:
        return text[: allowance // 2] + "\n... omitted ...\n" + text[-allowance // 2 :]
    chunks: list[str] = []
    per_quote = max(1000, allowance // len(normalized_quotes))
    for quote in normalized_quotes:
        index = text.find(quote)
        before = max(0, index - per_quote // 3)
        after = min(len(text), index + len(quote) + 2 * per_quote // 3)
        chunks.append(text[before:after])
    joined = "\n... omitted ...\n".join(chunks)
    return joined[:allowance]


def targeted_packet(task_dir: Path, claims: Sequence[FrozenClaim], max_chars: int = 32_000) -> dict[str, str]:
    sources = read_task_text_files(task_dir)
    required = {"instruction.md", "task.toml"} | {claim.artifact_path for claim in claims}
    categories = {claim.category for claim in claims}
    if categories & {"dependency_or_environment_drift", "resource_mismatch", "oracle_or_reference_failure"}:
        required |= {path for path in sources if path == "environment/Dockerfile" or path.startswith("solution/")}
    optional = [
        path for path in sorted(sources)
        if path.startswith("tests/") and path not in required
    ]
    paths = [path for path in sorted(required) if path in sources]
    for path in optional:
        if path not in paths:
            paths.append(path)
    result: dict[str, str] = {}
    remaining = max_chars
    for index, path in enumerate(paths):
        if remaining < 1000:
            break
        later_required = sum(item in required for item in paths[index + 1 :])
        allowance = min(12_000, max(1000, remaining - later_required * 1200))
        quotes = [
            value for claim in claims for value in (claim.artifact_quote, claim.instruction_quote)
            if (path == claim.artifact_path or path == "instruction.md") and value
        ]
        selected = _clip(sources[path], quotes, allowance)
        result[path] = selected
        remaining -= len(selected)
    return result


def _verify_protocol(protocol: Mapping[str, Any]) -> None:
    expected = protocol.get("protocol_sha256")
    unsigned = dict(protocol)
    unsigned.pop("protocol_sha256", None)
    if expected != _canonical_sha256(unsigned):
        raise ValueError("frozen protocol hash mismatch")
    old_tasks = task_directories(Path(str(protocol["old_repo"])))
    new_tasks = task_directories(Path(str(protocol["new_repo"])))
    for row in protocol["tasks"]:
        task = row["task_id"]
        if directory_digest(old_tasks[task]) != row["old_digest"]:
            raise ValueError(f"old task changed after freeze: {task}")
        if directory_digest(new_tasks[task]) != row["new_digest"]:
            raise ValueError(f"new task changed after freeze: {task}")


def _trial_key(row: Mapping[str, Any]) -> tuple[str, int]:
    return str(row["task_id"]), int(row["seed"])


def _load_trials(path: Path) -> dict[tuple[str, int], dict[str, Any]]:
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[_trial_key(row)] = row
    return rows


def _run_trial(
    client: LLMClient,
    task: Mapping[str, Any],
    old_dir: Path,
    new_dir: Path,
    seed: int,
    order: str,
    protocol_sha256: str,
) -> dict[str, Any]:
    claims = _claim_objects(task["claims"])
    old_packet = targeted_packet(old_dir, claims)
    new_packet = targeted_packet(new_dir, claims)
    packet_a, packet_b = ((old_packet, new_packet) if order == "AB" else (new_packet, old_packet))
    nonce = _canonical_sha256({
        "protocol": protocol_sha256,
        "task": task["task_id"],
        "seed": seed,
        "order": order,
    })
    system, user = build_pair_prompt(claims, packet_a, packet_b, nonce=nonce)
    started = time.monotonic()
    try:
        raw = client.chat_json(system, user)
        parsed = parse_pair_response(raw, claims, packet_a, packet_b)
        mapped = map_trial_to_versions(parsed, order=order)
        error = None
        raw_sha256 = _canonical_sha256(raw)
    except Exception as exc:
        mapped = {"valid": False, "error": f"{type(exc).__name__}:{exc}", "claims": []}
        error = mapped["error"]
        raw_sha256 = None
    return {
        "task_id": task["task_id"],
        "seed": seed,
        "order": order,
        "valid": bool(mapped.get("valid")),
        "error": error or mapped.get("error"),
        "invalid_grounding": int(mapped.get("invalid_grounding", 0)),
        "claims": mapped.get("claims", []),
        "prompt_sha256": _sha256_bytes((system + "\n" + user).encode("utf-8")),
        "raw_response_sha256": raw_sha256,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def run_trials(
    run_root: Path,
    llm_config: Path,
    cache: Path,
    *,
    workers: int,
) -> dict[str, Any]:
    protocol = _json(run_root / "frozen_protocol.json")
    _verify_protocol(protocol)
    config = replace(
        load_llm_config(str(llm_config)),
        cache_path=str(cache),
        temperature=0.2,
        max_tokens=4500,
        max_api_attempts=None,
        observed_token_stop=None,
        cache_only=False,
    )
    client = LLMClient(config)
    old_tasks = task_directories(Path(protocol["old_repo"]))
    new_tasks = task_directories(Path(protocol["new_repo"]))
    path = run_root / "trials.jsonl"
    existing = _load_trials(path)
    jobs = []
    for task in protocol["tasks"]:
        if not task["claims"]:
            continue
        for seed, order in enumerate(protocol["order_schedule"]):
            prior = existing.get((task["task_id"], seed))
            if not prior or not prior.get("valid"):
                jobs.append((task, seed, order))
    print(f"[paired] total={sum(bool(t['claims']) for t in protocol['tasks']) * len(ORDER_SCHEDULE)} reused={len(existing)} pending={len(jobs)}", flush=True)
    lock = threading.Lock()
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(
                _run_trial,
                client,
                task,
                old_tasks[task["task_id"]],
                new_tasks[task["task_id"]],
                seed,
                order,
                protocol["protocol_sha256"],
            ): (task["task_id"], seed)
            for task, seed, order in jobs
        }
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            _append_jsonl(path, row, lock)
            existing[_trial_key(row)] = row
            completed += 1
            if completed == 1 or completed % 10 == 0 or completed == len(jobs):
                print(
                    f"[paired] completed={completed}/{len(jobs)} valid={sum(r['valid'] for r in existing.values())}/{len(existing)}",
                    flush=True,
                )
    summary = {
        "model": config.model,
        "config": str(llm_config),
        "tasks_with_claims": sum(bool(task["claims"]) for task in protocol["tasks"]),
        "trials": len(existing),
        "valid": sum(bool(row.get("valid")) for row in existing.values()),
        "usage": client.run_stats(),
    }
    _write_json(run_root / "run_summary.json", summary)
    return summary


def analyze(run_root: Path) -> dict[str, Any]:
    protocol = _json(run_root / "frozen_protocol.json")
    _verify_protocol(protocol)
    source = _json(Path(protocol["source_report"]))
    if _sha256_bytes(Path(protocol["source_report"]).read_bytes()) != protocol["source_report_sha256"]:
        raise ValueError("source report changed after freeze")
    trials = _load_trials(run_root / "trials.jsonl")
    selected = {row["task_id"] for row in protocol["tasks"]}
    positives = {row["task_id"] for row in protocol["tasks"] if row["positive_proxy"]}
    deterministic = {row["task_id"] for row in protocol["tasks"] if row["deterministic_candidate"]}
    task_results = []
    defect_supported: set[str] = set()
    repair_localized: set[str] = set()
    identical_mismatch_numerator = 0.0
    identical_mismatch_denominator = 0
    invalid_trials = 0
    for task in protocol["tasks"]:
        task_trials = [
            row for (task_id, _), row in sorted(trials.items()) if task_id == task["task_id"]
        ]
        candidate_ids = [row["candidate_id"] for row in task["claims"]]
        aggregated = aggregate_trials(task_trials, candidate_ids) if candidate_ids else {
            "valid_trials": 0,
            "invalid_trials": 0,
            "orders": {"AB": 0, "BA": 0},
            "claims": [],
            "task_defect_supported": False,
            "task_repair_localized": False,
            "task_stable_old_only": False,
            "verdict_mismatch_rate": 0.0,
        }
        if aggregated["task_defect_supported"]:
            defect_supported.add(task["task_id"])
        if aggregated["task_repair_localized"]:
            repair_localized.add(task["task_id"])
        invalid_trials += int(aggregated["invalid_trials"])
        if task["identical_control"] and candidate_ids:
            observations = sum(row["valid_trials"] for row in aggregated["claims"])
            identical_mismatch_numerator += aggregated["verdict_mismatch_rate"] * observations
            identical_mismatch_denominator += observations
        task_results.append({**task, "adjudication": aggregated})
    # Official release changes can proxy whether a finding localizes to the old
    # version, but they are not valid negative labels for defects shared by both
    # releases.  Therefore change-proxy precision/recall uses repair_localized;
    # broader defect support is reported separately and never mislabeled FP.
    paired = repair_localized
    union = deterministic | paired
    methods = {
        "deterministic": classification_metrics(deterministic, positives, selected),
        "paired_only": classification_metrics(paired, positives, selected),
        "union": classification_metrics(union, positives, selected),
        "defect_support_descriptive": {
            "tasks": len(defect_supported),
            "task_ids": sorted(defect_supported),
            "label_boundary": (
                "Descriptive only: unchanged official tasks are not ground-truth "
                "negatives for defects shared by both releases."
            ),
        },
    }
    strata = {name: set(values) for name, values in protocol["strata"].items()}
    results_by_task = {row["task_id"]: row for row in task_results}
    retained_tp = len(paired & strata.get("incremental_tp", set()))
    retained_fp = len(paired & strata.get("incremental_fp", set()))
    complete_tasks = {
        task_id for task_id, row in results_by_task.items()
        if row["adjudication"]["valid_trials"] >= len(ORDER_SCHEDULE)
        and row["adjudication"]["invalid_trials"] == 0
    }
    complete_rejected_tp = (
        strata.get("incremental_tp", set()) & complete_tasks
    ) - paired
    pending_tp = strata.get("incremental_tp", set()) - complete_tasks
    max_attainable_tp = retained_tp + len(pending_tp)
    complete_rejected_fp = (
        strata.get("incremental_fp", set()) & complete_tasks
    ) - paired
    pending_fp = strata.get("incremental_fp", set()) - complete_tasks
    fp_total = len(strata.get("incremental_fp", set()))
    mismatch_rate = (
        identical_mismatch_numerator / identical_mismatch_denominator
        if identical_mismatch_denominator else 0.0
    )
    gates = {
        "retain_incremental_tp": retained_tp >= min(5, len(strata.get("incremental_tp", set()))),
        "filter_incremental_fp": len(complete_rejected_fp) >= min(5, fp_total),
        "identical_verdict_mismatch_rate_lt_0_10": mismatch_rate < 0.10,
        "union_f1_improves": methods["union"]["f1"] > methods["deterministic"]["f1"],
        "invalid_trials_zero": invalid_trials == 0,
    }
    retain_required = min(5, len(strata.get("incremental_tp", set())))
    early_stop = {
        "retain_required": retain_required,
        "retained": retained_tp,
        "complete_rejected": len(complete_rejected_tp),
        "pending": len(pending_tp),
        "max_attainable": max_attainable_tp,
        "gate_mathematically_impossible": max_attainable_tp < retain_required,
        "pending_tasks": sorted(pending_tp),
    }
    result = {
        "schema_version": "terminal-noise-controlled-results-v1",
        "protocol_sha256": protocol["protocol_sha256"],
        "scope": protocol["scope"],
        "dataset": {"selected": len(selected), "positive_proxy": len(positives)},
        "methods": methods,
        "incremental": {
            "retained_tp": retained_tp,
            "available_tp": len(strata.get("incremental_tp", set())),
            "retained_fp_proxy": retained_fp,
            "available_fp_proxy": fp_total,
            "definitively_filtered_fp_proxy": len(complete_rejected_fp),
            "pending_fp_proxy": len(pending_fp),
            "defect_supported_tasks": len(defect_supported),
            "repair_localized_tasks": len(repair_localized),
        },
        "noise_control": {
            "identical_claim_observations": identical_mismatch_denominator,
            "identical_verdict_mismatch_rate": mismatch_rate,
        },
        "quality": {
            "expected_trials": sum(bool(task["claims"]) for task in protocol["tasks"]) * len(ORDER_SCHEDULE),
            "observed_trials": len(trials),
            "valid_trials": len(trials) - invalid_trials,
            "invalid_trials": invalid_trials,
        },
        "early_stop": early_stop,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "decision": (
            "early_stopped_gate_impossible"
            if early_stop["gate_mathematically_impossible"] else
            "pass" if all(gates.values()) else
            "incomplete_or_failed"
        ),
        "task_results": task_results,
        "source_baseline": {
            "deterministic_full": source["methods"]["deterministic_only"],
            "old_llm_incremental": source["incremental"],
        },
        "boundary": (
            "Official release changes are proxy labels, not exhaustive human defect labels. "
            "Stable paired LLM decisions remain review evidence, never automatic confirmed."
        ),
    }
    _write_json(run_root / "results.json", result)
    (run_root / "results.md").write_text(render_markdown(result), encoding="utf-8")
    return result


def render_markdown(result: Mapping[str, Any]) -> str:
    methods = result["methods"]
    inc = result["incremental"]
    noise = result["noise_control"]
    quality = result["quality"]
    early = result["early_stop"]
    lines = [
        "# Terminal-Bench 噪声控制配对裁决",
        "",
        "> 固定旧候选；同一上下文盲化比较 A/B；AB/BA 各 3 次。所有结果仍为 review。",
        "",
        "## 指标",
        "",
        "| 方法 | TP | FP proxy | Precision proxy | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, label in (("deterministic", "确定性"), ("paired_only", "配对裁决"), ("union", "确定性 ∪ 配对裁决")):
        row = methods[key]
        lines.append(
            f"| {label} | {row['tp']} | {row['fp_proxy']} | {row['precision_proxy']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |"
        )
    lines.extend([
        "",
        "## 冻结增量与噪声",
        "",
        f"- 旧 LLM 增量 TP 保留：**{inc['retained_tp']}/{inc['available_tp']}**。",
        f"- 已确定过滤的 FP proxy：**{inc['definitively_filtered_fp_proxy']}/{inc['available_fp_proxy']}**；待定 **{inc['pending_fp_proxy']}**。",
        f"- identical verdict mismatch：**{noise['identical_verdict_mismatch_rate']:.1%}**（{noise['identical_claim_observations']} claim-trials）。",
        f"- Trials：**{quality['observed_trials']}/{quality['expected_trials']}**；invalid **{quality['invalid_trials']}**。",
        f"- TP 保留门槛上界：当前 {early['retained']}，待定 {early['pending']}，理论最多 **{early['max_attainable']}/{early['retain_required']}**。",
        "",
        "## 冻结门槛",
        "",
    ])
    for gate, passed in result["gates"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} `{gate}`")
    lines.extend([
        "",
        f"**总裁决：{'通过，可进入全量' if result['all_gates_pass'] else '未通过，停止全量并诊断'}（`{result['decision']}`）。**",
        "",
        "## 证据边界",
        "",
        str(result["boundary"]),
    ])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--source-report", type=Path, required=True)
    freeze.add_argument("--old-repo", type=Path, required=True)
    freeze.add_argument("--new-repo", type=Path, required=True)
    freeze.add_argument("--run-root", type=Path, required=True)
    freeze.add_argument("--scope", choices=("pilot", "full"), default="pilot")
    run = sub.add_parser("run")
    run.add_argument("--run-root", type=Path, required=True)
    run.add_argument("--llm-config", type=Path, required=True)
    run.add_argument("--cache", type=Path, required=True)
    run.add_argument("--workers", type=int, default=6)
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("--run-root", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "freeze":
        protocol = freeze_protocol(
            args.source_report.resolve(strict=True),
            args.old_repo.resolve(strict=True),
            args.new_repo.resolve(strict=True),
            args.run_root.absolute(),
            scope=args.scope,
        )
        print(json.dumps({
            "tasks": len(protocol["tasks"]),
            "tasks_with_claims": sum(bool(task["claims"]) for task in protocol["tasks"]),
            "protocol_sha256": protocol["protocol_sha256"],
        }, ensure_ascii=False))
    elif args.command == "run":
        print(json.dumps(run_trials(
            args.run_root.resolve(strict=True),
            args.llm_config.resolve(strict=True),
            args.cache.absolute(),
            workers=args.workers,
        ), ensure_ascii=False, indent=2))
    else:
        result = analyze(args.run_root.resolve(strict=True))
        print(json.dumps({
            "methods": result["methods"],
            "incremental": result["incremental"],
            "noise_control": result["noise_control"],
            "gates": result["gates"],
            "all_gates_pass": result["all_gates_pass"],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
