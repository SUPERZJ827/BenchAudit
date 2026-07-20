"""Score blind Terminal task audits against a repaired benchmark release.

The auditor processes each version independently.  File differences are used
only after inference to define repair-localization labels and never enter a
detector.  Consequently the experiment measures whether evidence visible in an
older task predicts where maintainers later made repairs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from benchcore.terminal_audit import audit_terminal_task


CONFIDENCE_THRESHOLD = 0.70
SUCCESS_GATES = {
    "precision_proxy": 0.60,
    "recall": 0.70,
    "f1": 0.65,
    "repair_candidate_drop": 0.30,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-repo", required=True)
    parser.add_argument("--new-repo", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--confidence-threshold", type=float, default=CONFIDENCE_THRESHOLD)
    return parser.parse_args()


def task_root(path: Path) -> Path:
    nested = path / "tasks"
    return nested if nested.is_dir() else path


def task_directories(root: Path) -> dict[str, Path]:
    return {
        path.name: path
        for path in sorted(task_root(root).iterdir())
        if path.is_dir() and (path / "task.toml").is_file()
    }


def changed_tasks(old: dict[str, Path], new: dict[str, Path]) -> set[str]:
    common = set(old) & set(new)
    return {name for name in common if directory_digest(old[name]) != directory_digest(new[name])}


def directory_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_symlink() or not item.is_file():
            continue
        relative = item.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def audit_tasks(tasks: dict[str, Path]) -> dict[str, list[dict[str, Any]]]:
    return {name: audit_terminal_task(path) for name, path in tasks.items()}


def candidate_tasks(
    findings: dict[str, list[dict[str, Any]]], threshold: float
) -> set[str]:
    return {
        task
        for task, rows in findings.items()
        if any(
            float(row["confidence"]) >= threshold and row["severity"] != "minor"
            for row in rows
        )
    }


def classification_metrics(predicted: set[str], positive: set[str], universe: set[str]) -> dict[str, Any]:
    tp = predicted & positive
    fp = predicted - positive
    fn = positive - predicted
    tn = universe - predicted - positive
    precision = len(tp) / len(predicted) if predicted else 0.0
    recall = len(tp) / len(positive) if positive else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": len(tp),
        "fp_proxy": len(fp),
        "fn": len(fn),
        "tn_proxy": len(tn),
        "precision_proxy": precision,
        "recall": recall,
        "f1": f1,
        "specificity_proxy": len(tn) / (len(tn) + len(fp)) if tn or fp else 0.0,
        "tp_tasks": sorted(tp),
        "fp_proxy_tasks": sorted(fp),
        "missed_tasks": sorted(fn),
    }


def hypergeometric_tail(*, population: int, positives: int, draws: int, overlap: int) -> float:
    if not 0 <= overlap <= min(positives, draws):
        return 0.0
    denominator = math.comb(population, draws)
    return sum(
        math.comb(positives, hits) * math.comb(population - positives, draws - hits)
        for hits in range(overlap, min(positives, draws) + 1)
        if 0 <= draws - hits <= population - positives
    ) / denominator


def detector_ablation(
    findings: dict[str, list[dict[str, Any]]],
    positives: set[str],
    universe: set[str],
    threshold: float,
) -> dict[str, Any]:
    types = sorted(
        {
            str(row["defect_type"])
            for rows in findings.values()
            for row in rows
            if float(row["confidence"]) >= threshold and row["severity"] != "minor"
        }
    )
    result: dict[str, Any] = {}
    for defect_type in types:
        predicted = {
            task
            for task, rows in findings.items()
            if any(
                row["defect_type"] == defect_type
                and float(row["confidence"]) >= threshold
                and row["severity"] != "minor"
                for row in rows
            )
        }
        result[defect_type] = classification_metrics(predicted, positives, universe)
    return result


def finding_types(
    rows: list[dict[str, Any]], threshold: float
) -> list[str]:
    return sorted(
        {
            str(row["defect_type"])
            for row in rows
            if float(row["confidence"]) >= threshold and row["severity"] != "minor"
        }
    )


def run_experiment(old_repo: Path, new_repo: Path, threshold: float) -> dict[str, Any]:
    old_tasks = task_directories(old_repo)
    new_tasks = task_directories(new_repo)
    if set(old_tasks) != set(new_tasks):
        raise ValueError(
            "paired task IDs differ: "
            f"old_only={sorted(set(old_tasks) - set(new_tasks))}, "
            f"new_only={sorted(set(new_tasks) - set(old_tasks))}"
        )
    universe = set(old_tasks)
    positives = changed_tasks(old_tasks, new_tasks)
    old_findings = audit_tasks(old_tasks)
    new_findings = audit_tasks(new_tasks)
    old_candidates = candidate_tasks(old_findings, threshold)
    new_candidates = candidate_tasks(new_findings, threshold)
    old_metrics = classification_metrics(old_candidates, positives, universe)
    new_metrics = classification_metrics(new_candidates, positives, universe)
    repaired_old = old_candidates & positives
    residual_new = new_candidates & positives
    repair_drop = (
        (len(repaired_old) - len(residual_new)) / len(repaired_old)
        if repaired_old
        else 0.0
    )
    expected_overlap = len(old_candidates) * len(positives) / len(universe)
    p_value = hypergeometric_tail(
        population=len(universe),
        positives=len(positives),
        draws=len(old_candidates),
        overlap=len(repaired_old),
    )
    gates = {
        "precision_proxy": old_metrics["precision_proxy"] >= SUCCESS_GATES["precision_proxy"],
        "recall": old_metrics["recall"] >= SUCCESS_GATES["recall"],
        "f1": old_metrics["f1"] >= SUCCESS_GATES["f1"],
        "repair_candidate_drop": repair_drop >= SUCCESS_GATES["repair_candidate_drop"],
    }
    paired_rows = []
    for task in sorted(positives):
        paired_rows.append(
            {
                "task_id": task,
                "old_signals": finding_types(old_findings[task], threshold),
                "new_signals": finding_types(new_findings[task], threshold),
                "localized": task in old_candidates,
                "cleared_after_repair": task in old_candidates and task not in new_candidates,
            }
        )
    return {
        "schema_version": "terminal-bench-paired-audit-v1",
        "protocol": {
            "blindness": "Each task version is audited independently; new-version diffs are labels only.",
            "confidence_threshold": threshold,
            "success_gates": SUCCESS_GATES,
            "unchanged_task_status": "proxy negatives; may contain undiscovered defects",
            "confirmation_policy": "all static findings remain review; no automatic confirmed",
        },
        "dataset": {
            "old_repo": str(old_repo.resolve()),
            "new_repo": str(new_repo.resolve()),
            "old_tree_sha256": directory_digest(task_root(old_repo)),
            "new_tree_sha256": directory_digest(task_root(new_repo)),
            "tasks": len(universe),
            "changed_tasks": len(positives),
            "unchanged_tasks": len(universe - positives),
        },
        "old_release": {
            "candidate_tasks": len(old_candidates),
            "finding_count": sum(len(rows) for rows in old_findings.values()),
            "metrics": old_metrics,
            "by_type": dict(
                sorted(
                    Counter(
                        str(row["defect_type"])
                        for rows in old_findings.values()
                        for row in rows
                    ).items()
                )
            ),
        },
        "new_release": {
            "candidate_tasks": len(new_candidates),
            "finding_count": sum(len(rows) for rows in new_findings.values()),
            "metrics_against_change_labels": new_metrics,
        },
        "paired_effect": {
            "changed_candidates_old": len(repaired_old),
            "changed_candidates_new": len(residual_new),
            "repair_candidate_drop": repair_drop,
            "cleared_changed_tasks": sorted(repaired_old - residual_new),
            "residual_changed_tasks": sorted(residual_new),
        },
        "random_control": {
            "expected_overlap": expected_overlap,
            "observed_overlap": len(repaired_old),
            "localization_lift": len(repaired_old) / expected_overlap if expected_overlap else 0.0,
            "hypergeometric_tail_p": p_value,
        },
        "ablation": detector_ablation(old_findings, positives, universe, threshold),
        "paired_changed_tasks": paired_rows,
        "success_gates": gates,
        "overall_success": all(gates.values()),
        "old_findings": old_findings,
        "new_findings": new_findings,
    }


def render_markdown(result: dict[str, Any]) -> str:
    old = result["old_release"]
    metrics = old["metrics"]
    effect = result["paired_effect"]
    random = result["random_control"]
    lines = [
        "# Terminal-Bench 2.0 → 2.1 配对审计实验",
        "",
        "> 检测器分别、独立地读取两个版本；2.1 的文件差异只在推理结束后作为修订标签，未进入任何检测规则。",
        "",
        "## 结论",
        "",
        f"- 预设成功门槛：**{'全部通过' if result['overall_success'] else '未全部通过'}**。",
        f"- 2.0 高置信候选：**{old['candidate_tasks']}/{result['dataset']['tasks']}** 题。",
        f"- 官方修订任务命中：**{metrics['tp']}/{result['dataset']['changed_tasks']}**，Recall **{metrics['recall']:.3f}**。",
        f"- Precision proxy **{metrics['precision_proxy']:.3f}**，F1 proxy **{metrics['f1']:.3f}**。",
        f"- 修订任务上的候选从 **{effect['changed_candidates_old']}** 降至 **{effect['changed_candidates_new']}**，下降 **{effect['repair_candidate_drop']:.1%}**。",
        f"- 随机同规模候选期望命中 {random['expected_overlap']:.2f} 题；实际命中 {random['observed_overlap']} 题，lift **{random['localization_lift']:.2f}×**，超几何尾概率 **{random['hypergeometric_tail_p']:.3g}**。",
        "- 所有静态结果仍是 `review`，没有自动 `confirmed`。",
        "",
        "## 预注册式成功门槛",
        "",
        "| 指标 | 门槛 | 实际 | 通过 |",
        "|---|---:|---:|---:|",
        f"| Precision proxy | {SUCCESS_GATES['precision_proxy']:.2f} | {metrics['precision_proxy']:.3f} | {'✅' if result['success_gates']['precision_proxy'] else '❌'} |",
        f"| Recall | {SUCCESS_GATES['recall']:.2f} | {metrics['recall']:.3f} | {'✅' if result['success_gates']['recall'] else '❌'} |",
        f"| F1 proxy | {SUCCESS_GATES['f1']:.2f} | {metrics['f1']:.3f} | {'✅' if result['success_gates']['f1'] else '❌'} |",
        f"| 修订后候选下降 | {SUCCESS_GATES['repair_candidate_drop']:.0%} | {effect['repair_candidate_drop']:.1%} | {'✅' if result['success_gates']['repair_candidate_drop'] else '❌'} |",
        "",
        "## 检测器消融",
        "",
        "| 检测器 | 候选 | 命中 | Precision proxy | Recall | F1 proxy |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in result["ablation"].items():
        lines.append(
            f"| `{name}` | {row['tp'] + row['fp_proxy']} | {row['tp']} | "
            f"{row['precision_proxy']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 28 个修订任务逐题结果",
            "",
            "| 任务 | 2.0 信号 | 2.1 信号 | 命中 | 修订后清除 |",
            "|---|---|---|---:|---:|",
        ]
    )
    for row in result["paired_changed_tasks"]:
        old_signals = ", ".join(f"`{value}`" for value in row["old_signals"]) or "—"
        new_signals = ", ".join(f"`{value}`" for value in row["new_signals"]) or "—"
        lines.append(
            f"| {row['task_id']} | {old_signals} | {new_signals} | "
            f"{'✅' if row['localized'] else '❌'} | "
            f"{'✅' if row['cleared_after_repair'] else '—'} |"
        )
    lines.extend(
        [
            "",
            "## 错误分析",
            "",
            "### 未命中的官方修订任务",
            "",
            ", ".join(f"`{value}`" for value in metrics["missed_tasks"]) or "无",
            "",
            "### Proxy false positives",
            "",
            ", ".join(f"`{value}`" for value in metrics["fp_proxy_tasks"]) or "无",
            "",
            "> 这里的 precision 是 proxy：61 个未改任务并不等于人工确认无缺陷。因此 FP 只能解释为“没有被 2.1 修订标签覆盖”，不能解释为已经证伪。相反，28 个修订也包含维护性和环境性变更，Recall 衡量的是修订定位能力，而不是所有可能缺陷的完备召回。",
            "",
            "## 可复现信息",
            "",
            f"- 2.0 task tree SHA-256：`{result['dataset']['old_tree_sha256']}`",
            f"- 2.1 task tree SHA-256：`{result['dataset']['new_tree_sha256']}`",
            f"- 高置信阈值：`{result['protocol']['confidence_threshold']}`",
            "- LLM/API 调用：`0`",
            "- 自动 confirmed：`0`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    result = run_experiment(
        Path(args.old_repo), Path(args.new_repo), args.confidence_threshold
    )
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    out_md.write_text(render_markdown(result), encoding="utf-8")
    print(
        json.dumps(
            {
                "overall_success": result["overall_success"],
                "old_metrics": result["old_release"]["metrics"],
                "paired_effect": result["paired_effect"],
                "random_control": result["random_control"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
