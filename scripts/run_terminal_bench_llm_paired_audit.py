"""Run evidence-grounded LLM auditing on Terminal-Bench 2.0 and 2.1.

The old release is audited in full.  The new release is audited only for tasks
that changed, which is sufficient for the paired repair-direction measurement.
Official change labels never appear in prompts or detector inputs.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.terminal_audit import audit_terminal_task
from benchcore.terminal_llm_audit import (
    accepted_candidate,
    build_evidence_packet,
    investigate_task,
    verify_finding,
)
from scripts.run_terminal_bench_paired_audit import (
    candidate_tasks,
    changed_tasks,
    classification_metrics,
    hypergeometric_tail,
    task_directories,
)


INVESTIGATOR_THRESHOLD = 0.75
VERIFIER_THRESHOLD = 0.75


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-repo", required=True)
    parser.add_argument("--new-repo", required=True)
    parser.add_argument("--llm-config", default="configs/llm_deepseek.json")
    parser.add_argument("--cache", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-api-attempts", type=int, default=500)
    parser.add_argument("--observed-token-stop", type=int, default=8_000_000)
    parser.add_argument("--pilot-limit", type=int)
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Replay from the exact-response cache without making network calls.",
    )
    return parser.parse_args()


def run_task(client: LLMClient, task_dir: Path) -> dict[str, Any]:
    packet = build_evidence_packet(task_dir)
    try:
        investigation = investigate_task(client, packet)
    except Exception as exc:  # Per-task isolation; errors remain visible in results.
        return {
            "task_id": task_dir.name,
            "error": f"investigator:{type(exc).__name__}:{exc}",
            "findings": [],
            "accepted": [],
            "truncated_files": list(packet.truncated_files),
        }
    accepted: list[dict[str, Any]] = []
    verifier_errors: list[str] = []
    for finding in investigation["findings"]:
        if finding["severity"] != "major" or float(finding["confidence"]) < INVESTIGATOR_THRESHOLD:
            continue
        try:
            verification = verify_finding(client, packet, finding)
        except Exception as exc:
            verifier_errors.append(f"{type(exc).__name__}:{exc}")
            continue
        finding["verification"] = verification
        if accepted_candidate(
            finding,
            verification,
            investigator_threshold=INVESTIGATOR_THRESHOLD,
            verifier_threshold=VERIFIER_THRESHOLD,
        ):
            accepted.append(
                {
                    **finding,
                    "confirmation": "two_stage_llm_review",
                }
            )
    return {
        **investigation,
        "accepted": accepted,
        "verifier_errors": verifier_errors,
    }


def run_many(
    client: LLMClient,
    tasks: dict[str, Path],
    *,
    workers: int,
    label: str,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    started = time.monotonic()
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(run_task, client, path): task for task, path in tasks.items()}
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "task_id": task,
                    "error": f"worker:{type(exc).__name__}:{exc}",
                    "findings": [],
                    "accepted": [],
                }
            with lock:
                results[task] = result
                completed = len(results)
                if completed == 1 or completed % 5 == 0 or completed == len(tasks):
                    elapsed = time.monotonic() - started
                    print(
                        f"[{label}] {completed}/{len(tasks)} elapsed={elapsed:.1f}s "
                        f"accepted_tasks={sum(bool(row.get('accepted')) for row in results.values())}",
                        flush=True,
                    )
    return dict(sorted(results.items()))


def llm_candidate_tasks(results: dict[str, dict[str, Any]]) -> set[str]:
    return {task for task, row in results.items() if row.get("accepted")}


def raw_llm_candidate_tasks(results: dict[str, dict[str, Any]]) -> set[str]:
    return {
        task
        for task, row in results.items()
        if any(
            finding.get("severity") == "major"
            and float(finding.get("confidence", 0.0)) >= INVESTIGATOR_THRESHOLD
            for finding in row.get("findings", [])
        )
    }


def detector_candidates(tasks: dict[str, Path]) -> tuple[set[str], dict[str, list[dict[str, Any]]]]:
    findings = {task: audit_terminal_task(path) for task, path in tasks.items()}
    return candidate_tasks(findings, 0.70), findings


def evaluate(
    old_tasks: dict[str, Path],
    new_tasks: dict[str, Path],
    positives: set[str],
    old_llm: dict[str, dict[str, Any]],
    new_llm: dict[str, dict[str, Any]],
    stats: dict[str, Any],
    *,
    pilot: bool,
) -> dict[str, Any]:
    universe = set(old_tasks)
    evaluated_old = set(old_llm)
    metric_universe = evaluated_old
    metric_positives = positives & metric_universe
    deterministic, deterministic_findings = detector_candidates(old_tasks)
    deterministic &= metric_universe
    llm = llm_candidate_tasks(old_llm)
    raw_llm = raw_llm_candidate_tasks(old_llm)
    combined = deterministic | llm
    intersection = deterministic & llm
    new_llm_candidates = llm_candidate_tasks(new_llm)

    methods = {
        "deterministic_only": classification_metrics(deterministic, metric_positives, metric_universe),
        "llm_investigator_raw": classification_metrics(raw_llm, metric_positives, metric_universe),
        "llm_two_stage": classification_metrics(llm, metric_positives, metric_universe),
        "union": classification_metrics(combined, metric_positives, metric_universe),
        "intersection": classification_metrics(intersection, metric_positives, metric_universe),
    }
    incremental_tp = (llm - deterministic) & metric_positives
    incremental_fp = (llm - deterministic) - metric_positives
    repaired_llm = llm & positives
    residual_llm = new_llm_candidates & positives
    llm_drop = (
        (len(repaired_llm) - len(residual_llm)) / len(repaired_llm)
        if repaired_llm
        else 0.0
    )
    union_metrics = methods["union"]
    expected = (
        (union_metrics["tp"] + union_metrics["fp_proxy"]) * len(metric_positives) / len(metric_universe)
        if metric_universe
        else 0.0
    )
    p_value = hypergeometric_tail(
        population=len(metric_universe),
        positives=len(metric_positives),
        draws=union_metrics["tp"] + union_metrics["fp_proxy"],
        overlap=union_metrics["tp"],
    ) if metric_universe else 1.0
    errors = {
        "old_task_errors": sum(bool(row.get("error")) for row in old_llm.values()),
        "new_task_errors": sum(bool(row.get("error")) for row in new_llm.values()),
        "old_verifier_errors": sum(len(row.get("verifier_errors", [])) for row in old_llm.values()),
        "new_verifier_errors": sum(len(row.get("verifier_errors", [])) for row in new_llm.values()),
        "invalid_investigator_evidence": sum(
            int(row.get("diagnostics", {}).get("invalid_evidence", 0))
            for row in [*old_llm.values(), *new_llm.values()]
        ),
    }
    return {
        "schema_version": "terminal-bench-llm-paired-audit-v1",
        "protocol": {
            "pilot": pilot,
            "old_scope": len(evaluated_old),
            "new_scope": len(new_llm),
            "new_scope_policy": "officially changed task IDs only; labels never included in prompts",
            "investigator_threshold": INVESTIGATOR_THRESHOLD,
            "verifier_threshold": VERIFIER_THRESHOLD,
            "high_confidence_policy": "major + grounded investigator + grounded independent verifier",
            "confirmation_policy": "two LLM stages remain review, never automatic confirmed",
        },
        "dataset": {
            "tasks": len(universe),
            "changed_tasks": len(positives),
            "evaluated_old_tasks": len(metric_universe),
            "evaluated_positive_tasks": len(metric_positives),
        },
        "methods": methods,
        "incremental": {
            "llm_new_true_positives": sorted(incremental_tp),
            "llm_new_fp_proxies": sorted(incremental_fp),
            "llm_added_tp": len(incremental_tp),
            "llm_added_fp_proxy": len(incremental_fp),
            "union_f1_delta_vs_deterministic": (
                methods["union"]["f1"] - methods["deterministic_only"]["f1"]
            ),
        },
        "paired_llm_effect": {
            "changed_candidates_old": len(repaired_llm),
            "changed_candidates_new": len(residual_llm),
            "candidate_drop": llm_drop,
            "cleared": sorted(repaired_llm - residual_llm),
            "residual": sorted(residual_llm),
        },
        "random_control_union": {
            "expected_overlap": expected,
            "observed_overlap": union_metrics["tp"],
            "localization_lift": union_metrics["tp"] / expected if expected else 0.0,
            "hypergeometric_tail_p": p_value,
        },
        "quality_control": errors,
        "llm_usage": stats,
        "deterministic_findings": deterministic_findings,
        "old_llm_results": old_llm,
        "new_llm_results": new_llm,
    }


def render_markdown(result: dict[str, Any]) -> str:
    methods = result["methods"]
    usage = result["llm_usage"]
    incremental = result["incremental"]
    effect = result["paired_llm_effect"]
    quality = result["quality_control"]
    lines = [
        "# Terminal-Bench 2.0 → 2.1：LLM 增强配对审计",
        "",
        "> LLM 分别盲读每个版本，不接触 2.1 修订说明；候选必须引用真实 artifact 原文，并通过第二个独立复核提示。所有 LLM 结果仍为 review。",
        "",
        "## 核心结果",
        "",
        "| 方法 | 候选题 | TP | Precision proxy | Recall | F1 proxy |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, label in (
        ("deterministic_only", "确定性规则"),
        ("llm_investigator_raw", "单阶段 LLM（未复核）"),
        ("llm_two_stage", "双阶段 LLM"),
        ("union", "规则 ∪ 双阶段 LLM"),
        ("intersection", "规则 ∩ 双阶段 LLM"),
    ):
        row = methods[key]
        lines.append(
            f"| {label} | {row['tp'] + row['fp_proxy']} | {row['tp']} | "
            f"{row['precision_proxy']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## LLM 的真实增量",
            "",
            f"- 相对规则基线新增 TP：**{incremental['llm_added_tp']}** — "
            + (", ".join(f"`{x}`" for x in incremental["llm_new_true_positives"]) or "无"),
            f"- 相对规则基线新增 FP proxy：**{incremental['llm_added_fp_proxy']}**。",
            f"- Union F1 变化：**{incremental['union_f1_delta_vs_deterministic']:+.3f}**。",
            f"- 修订任务上的双阶段 LLM 候选：2.0 为 **{effect['changed_candidates_old']}**，2.1 为 **{effect['changed_candidates_new']}**，下降 **{effect['candidate_drop']:.1%}**。",
            "",
            "## 调用与质量控制",
            "",
            f"- 模型：`{usage.get('model')}`；thinking：`{usage.get('thinking')}`。",
            f"- API attempts/successes/failures：`{usage.get('api_attempts')}/{usage.get('api_successes')}/{usage.get('api_failures')}`。",
            f"- Prompt/completion/total tokens：`{usage.get('prompt_tokens')}/{usage.get('completion_tokens')}/{usage.get('total_tokens')}`。",
            f"- Task errors（old/new）：`{quality['old_task_errors']}/{quality['new_task_errors']}`。",
            f"- Verifier errors（old/new）：`{quality['old_verifier_errors']}/{quality['new_verifier_errors']}`。",
            f"- 被本地证据校验拒绝的幻觉引用：`{quality['invalid_investigator_evidence']}`。",
            "",
            "## 双阶段 LLM 命中的修订任务",
            "",
        ]
    )
    for task in methods["llm_two_stage"]["tp_tasks"]:
        accepted = result["old_llm_results"][task].get("accepted", [])
        lines.append(f"### `{task}`")
        lines.append("")
        for row in accepted:
            lines.append(
                f"- `{row['category']}` ({row['confidence']:.2f}/"
                f"{row['verification']['confidence']:.2f})：{row['claim']}"
            )
            lines.append(
                f"  - 证据 `{row['artifact_path']}`：“{row['artifact_quote'].replace(chr(10), ' ')[:280]}”"
            )
        lines.append("")
    lines.extend(
        [
            "## 诚实边界",
            "",
            "- Precision 仍是 proxy：未修订任务不能视为人工确认无缺陷。",
            "- 同一模型使用不同角色提示不等于真正模型独立，只能降低自我确认偏差。",
            "- LLM 引用和双阶段同意只能提高 review 排序，不能产生 confirmed；最终确认仍需执行、差分测试或人工裁决。",
            "- 新版本只重审官方修订的任务，因此 2.1 数据只用于修订方向，不用于计算全局 Precision。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    old_tasks = task_directories(Path(args.old_repo))
    new_tasks = task_directories(Path(args.new_repo))
    positives = changed_tasks(old_tasks, new_tasks)
    selected_old = dict(sorted(old_tasks.items()))
    pilot = args.pilot_limit is not None
    if pilot:
        selected_old = dict(list(selected_old.items())[: max(1, args.pilot_limit)])
    selected_new = {task: new_tasks[task] for task in sorted(positives)}
    if pilot:
        selected_new = {
            task: path for task, path in selected_new.items() if task in selected_old
        }

    config = replace(
        load_llm_config(args.llm_config),
        cache_path=args.cache,
        thinking="disabled",
        max_tokens=3500,
        max_api_attempts=args.max_api_attempts,
        observed_token_stop=args.observed_token_stop,
        cache_only=args.cache_only,
    )
    client = LLMClient(config)
    old_results = run_many(client, selected_old, workers=args.workers, label="old")
    new_results = run_many(client, selected_new, workers=args.workers, label="new")
    result = evaluate(
        old_tasks,
        new_tasks,
        positives,
        old_results,
        new_results,
        client.run_stats(),
        pilot=pilot,
    )
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    out_md.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({"methods": result["methods"], "usage": result["llm_usage"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
