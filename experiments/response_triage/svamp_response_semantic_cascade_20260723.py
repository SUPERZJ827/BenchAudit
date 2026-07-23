#!/usr/bin/env python3
"""Behavior-first, semantic-second SVAMP cascade experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from sklearn.metrics import average_precision_score


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchcore.comparison import candidate_tier


SOURCE_DIR = ROOT / "reports" / "svamp_deepseek_view_triage_20260723"
PUBLIC = SOURCE_DIR / "public_items.jsonl"
LABELS = SOURCE_DIR / "labels.json"
TRIAGE = SOURCE_DIR / "triage.json"
PROTOCOL = (
    ROOT
    / "experiments"
    / "response_triage"
    / "protocols"
    / "SVAMP_RESPONSE_THEN_SEMANTIC_CASCADE_PROTOCOL_20260723.md"
)
OUT = ROOT / "reports" / "svamp_response_semantic_cascade_20260723"
SUBSET = OUT / "top100_public.jsonl"
SELECTION = OUT / "selection.json"
CONFIG = OUT / "llm_config.json"
CACHE = OUT / "deepseek_cache.jsonl"
AUDIT = OUT / "semantic_audit.json"
AUDIT_MD = OUT / "semantic_audit.md"
METRICS = OUT / "metrics.json"
REPORT = OUT / "report.md"

EXPECTED_SHA256 = {
    PUBLIC: "d7db7872b06559625ac8fd8ad016ea90bfb47d93e4b042016607d4cff74ddc23",
    LABELS: "f95887292267ac4412f0229f7b3e26e47f72cc410a01de879ea165fb405def61",
    PROTOCOL: "e40516d08d04bb996c64442526b605c35e6dff296c78b340a7afff1c22584c25",
}
EXPECTED_TRIAGE_SCORE_SHA256 = (
    "f604ecd1a8c013ab6c03a8d64c448020a790495f0b48062c4124570a4ab341e4"
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(include_labels: bool) -> None:
    paths = [PUBLIC, PROTOCOL]
    if include_labels:
        paths.append(LABELS)
    for path in paths:
        if sha256_file(path) != EXPECTED_SHA256[path]:
            raise ValueError(f"frozen input changed: {path}")
    triage = load_json(TRIAGE)
    score_projection = [
        (row["item_id"], row["error_rate"])
        for row in sorted(triage["items"], key=lambda row: row["item_id"])
    ]
    score_hash = hashlib.sha256(
        json.dumps(
            score_projection,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if score_hash != EXPECTED_TRIAGE_SCORE_SHA256:
        raise ValueError(
            "frozen triage item/error-rate projection changed: "
            f"expected {EXPECTED_TRIAGE_SCORE_SHA256}, got {score_hash}"
        )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def prepare() -> None:
    verify(include_labels=False)
    public_rows = {str(row["id"]): row for row in load_jsonl(PUBLIC)}
    triage = load_json(TRIAGE)
    by_id = {row["item_id"]: row for row in triage["items"]}
    if set(public_rows) != set(by_id) or len(by_id) != 300:
        raise ValueError("public and triage ID sets differ")
    ordered = sorted(
        by_id,
        key=lambda item_id: (-float(by_id[item_id]["error_rate"]), item_id),
    )
    selected = ordered[:100]
    write_jsonl(SUBSET, [public_rows[item_id] for item_id in selected])
    write_json(
        SELECTION,
        {
            "schema_version": 1,
            "selection": "top100_by_deepseek_view_error_rate_then_item_id",
            "label_free": True,
            "selected": selected,
            "error_rate": {
                item_id: float(by_id[item_id]["error_rate"])
                for item_id in selected
            },
            "protocol_sha256": sha256_file(PROTOCOL),
            "public_sha256": sha256_file(PUBLIC),
            "triage_sha256": sha256_file(TRIAGE),
        },
    )
    if any(
        token in SUBSET.read_bytes()
        for token in (b"audit_label", b"cleaning_status", b"platinum_target")
    ):
        raise AssertionError("label leakage into semantic subset")
    write_json(
        CONFIG,
        {
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "temperature": 0.0,
            "thinking": "disabled",
            "timeout": 120,
            "max_tokens": 2000,
            "max_retries": 2,
            "cache_path": str(CACHE),
            "dry_run": False,
        },
    )
    print(
        f"prepared label-free top100; subset={sha256_file(SUBSET)[:12]}, "
        f"selection={sha256_file(SELECTION)[:12]}"
    )


def run_audit() -> None:
    if not SUBSET.exists() or not CONFIG.exists():
        raise FileNotFoundError("run prepare first")
    command = [
        sys.executable,
        "-m",
        "benchcore.cli",
        "audit",
        str(SUBSET),
        "--profile",
        "generic",
        "--basic-only",
        "--llm-audit",
        "--llm-auditors",
        "gold,question,quantity,event",
        "--gold-evidence-mode",
        "cascade",
        "--llm-config",
        str(CONFIG),
        "--llm-cache",
        str(CACHE),
        "--allow-remote-data-egress",
        "--workers",
        "24",
        "--progress-every",
        "20",
        "--out",
        str(AUDIT),
        "--md",
        str(AUDIT_MD),
        "--print-summary",
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    print(f"semantic audit={sha256_file(AUDIT)[:12]}")


def ranking_metrics(order: list[str], positives: set[str]) -> dict[str, Any]:
    if not positives:
        raise ValueError("ranking has no positives")
    tp = 0
    precision_sum = 0.0
    result: dict[str, Any] = {
        "n": len(order),
        "positives": len(positives),
        "prevalence": len(positives) / len(order),
    }
    checkpoints = {20, 50, 100}
    for rank, item_id in enumerate(order, 1):
        if item_id in positives:
            tp += 1
            precision_sum += tp / rank
        if rank in checkpoints:
            result[f"precision_at_{rank}"] = tp / rank
            result[f"recall_at_{rank}"] = tp / len(positives)
    result["average_precision"] = precision_sum / len(positives)
    return result


def evaluate() -> None:
    verify(include_labels=True)
    for path in (SELECTION, AUDIT):
        if not path.exists():
            raise FileNotFoundError(path)
    labels = load_json(LABELS)["items"]
    triage = load_json(TRIAGE)
    selection = load_json(SELECTION)
    audit = load_json(AUDIT)
    by_id = {row["item_id"]: row for row in triage["items"]}
    selected = set(selection["selected"])
    if len(selected) != 100:
        raise ValueError("selection must contain exactly 100 items")
    behavior_order = sorted(
        by_id,
        key=lambda item_id: (-float(by_id[item_id]["error_rate"]), item_id),
    )
    positives = {
        item_id for item_id, row in labels.items() if row["is_defect"]
    }

    semantic_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    llm_violations: list[dict[str, Any]] = []
    for violation in audit.get("violations", []):
        method = str(violation.get("detection_method", ""))
        if not method.startswith("llm_"):
            continue
        llm_violations.append(violation)
        semantic_by_item[str(violation["item_id"])].append(violation)
    priority = {
        item_id
        for item_id, violations in semantic_by_item.items()
        if candidate_tier(violations) == "priority"
    }
    confirmed_model_findings = [
        violation
        for violation in llm_violations
        if not violation.get("review_only", False)
        or violation.get("evidence_tier") == "confirmed"
    ]
    behavior_position = {
        item_id: position for position, item_id in enumerate(behavior_order)
    }
    semantic_order = sorted(
        behavior_order,
        key=lambda item_id: (
            0 if item_id in priority else 1 if item_id in selected else 2,
            behavior_position[item_id],
        ),
    )
    behavior_metrics = ranking_metrics(behavior_order, positives)
    semantic_metrics = ranking_metrics(semantic_order, positives)
    sorted_ids = sorted(by_id)
    binary_labels = [int(item_id in positives) for item_id in sorted_ids]
    threshold_behavior_ap = float(
        average_precision_score(
            binary_labels,
            [float(by_id[item_id]["error_rate"]) for item_id in sorted_ids],
        )
    )
    threshold_semantic_ap = float(
        average_precision_score(
            binary_labels,
            [
                (
                    2.0
                    if item_id in priority
                    else 1.0
                    if item_id in selected
                    else 0.0
                )
                + float(by_id[item_id]["error_rate"])
                for item_id in sorted_ids
            ],
        )
    )
    conditions = {
        "ap_gain_at_least_0_020": (
            semantic_metrics["average_precision"]
            - behavior_metrics["average_precision"]
            >= 0.020
        ),
        "p20_not_decreased": (
            semantic_metrics["precision_at_20"]
            >= behavior_metrics["precision_at_20"]
        ),
        "p50_not_decreased": (
            semantic_metrics["precision_at_50"]
            >= behavior_metrics["precision_at_50"]
        ),
        "zero_model_confirmed": len(confirmed_model_findings) == 0,
        "only_one_third_sent": len(selected) == 100 and len(by_id) == 300,
    }
    run_metadata = audit.get("run_metadata", {})
    metrics = {
        "schema_version": 1,
        "experiment": "SVAMP response-first semantic cascade",
        "not_pristine_holdout": True,
        "ranking": {
            "behavior": behavior_metrics,
            "semantic_gated": semantic_metrics,
            "delta": {
                "average_precision": (
                    semantic_metrics["average_precision"]
                    - behavior_metrics["average_precision"]
                ),
                "precision_at_20": (
                    semantic_metrics["precision_at_20"]
                    - behavior_metrics["precision_at_20"]
                ),
                "precision_at_50": (
                    semantic_metrics["precision_at_50"]
                    - behavior_metrics["precision_at_50"]
                ),
            },
            "tie_sensitivity": {
                "reason": (
                    "eight binary views create many error-rate ties; frozen "
                    "item-ID ordering is compared with threshold/tie-aware AP"
                ),
                "behavior_threshold_average_precision": threshold_behavior_ap,
                "semantic_threshold_average_precision": threshold_semantic_ap,
                "threshold_delta": (
                    threshold_semantic_ap - threshold_behavior_ap
                ),
            },
        },
        "semantic": {
            "items_sent": len(selected),
            "dataset_fraction_sent": len(selected) / len(by_id),
            "llm_violations": len(llm_violations),
            "items_with_llm_findings": len(semantic_by_item),
            "priority_items": len(priority),
            "priority_true_defects": len(priority & positives),
            "priority_precision": (
                len(priority & positives) / len(priority) if priority else 0.0
            ),
            "model_confirmed_findings": len(confirmed_model_findings),
        },
        "decision": {
            "conditions": conditions,
            "all_conditions_pass": all(conditions.values()),
            "recommendation": (
                "use_semantic_gate_for_reranking"
                if all(conditions.values())
                else "use_semantics_for_explanation_only"
            ),
        },
        "api": run_metadata.get("llm_run_stats", run_metadata.get("llm", {})),
        "provenance": {
            "protocol_sha256": sha256_file(PROTOCOL),
            "public_sha256": sha256_file(PUBLIC),
            "triage_sha256": sha256_file(TRIAGE),
            "selection_sha256": sha256_file(SELECTION),
            "subset_sha256": sha256_file(SUBSET),
            "audit_sha256": sha256_file(AUDIT),
            "labels_sha256": sha256_file(LABELS),
        },
    }
    write_json(METRICS, metrics)
    REPORT.write_text(render_report(metrics), encoding="utf-8")
    print(
        f"evaluated recommendation={metrics['decision']['recommendation']}; "
        f"metrics={sha256_file(METRICS)[:12]}"
    )


def render_report(metrics: dict[str, Any]) -> str:
    before = metrics["ranking"]["behavior"]
    after = metrics["ranking"]["semantic_gated"]
    delta = metrics["ranking"]["delta"]
    semantic = metrics["semantic"]
    decision = metrics["decision"]
    tie_sensitivity = metrics["ranking"]["tie_sensitivity"]
    api = metrics["api"]
    estimated_cost = (
        float(api.get("prompt_tokens", 0)) * 0.14 / 1_000_000
        + float(api.get("completion_tokens", 0)) * 0.28 / 1_000_000
    )
    lines = [
        "# SVAMP：行为优先、语义后置的级联实验",
        "",
        "> 先用已有响应轨迹筛到 100/300，再只对这 100 条运行 DeepSeek 语义审计。"
        "所有 LLM finding 保持 review，不参与 confirmed。",
        "",
        "## 裁决",
        "",
        (
            "**语义 gate 通过冻结门槛，可以用于候选重排。**"
            if decision["all_conditions_pass"]
            else "**语义 gate 未通过冻结门槛；语义结果只用于解释候选，不自动重排。**"
        ),
        "",
        "| 指标 | 行为排序 | 语义 gate 后 | 变化 |",
        "|---|---:|---:|---:|",
        f"| AP | {before['average_precision']:.3f} | "
        f"{after['average_precision']:.3f} | {delta['average_precision']:+.3f} |",
        f"| P@20 | {before['precision_at_20']:.3f} | "
        f"{after['precision_at_20']:.3f} | {delta['precision_at_20']:+.3f} |",
        f"| P@50 | {before['precision_at_50']:.3f} | "
        f"{after['precision_at_50']:.3f} | {delta['precision_at_50']:+.3f} |",
        f"| R@100 | {before['recall_at_100']:.3f} | "
        f"{after['recall_at_100']:.3f} | "
        f"{after['recall_at_100'] - before['recall_at_100']:+.3f} |",
        "",
        "## 语义审计产出",
        "",
        f"- 远程发送：{semantic['items_sent']}/300 "
        f"({semantic['dataset_fraction_sent']:.1%})。",
        f"- 有 LLM finding 的条目：{semantic['items_with_llm_findings']}。",
        f"- Priority 条目：{semantic['priority_items']}；其中真实缺陷 "
        f"{semantic['priority_true_defects']}，precision={semantic['priority_precision']:.3f}。",
        f"- LLM 自动 confirmed：{semantic['model_confirmed_findings']}。",
        f"- API attempts：{api.get('api_attempts', 0)}；input/output tokens："
        f"{api.get('prompt_tokens', 0)}/{api.get('completion_tokens', 0)}；"
        f"按 2026-07-23 Flash cache-miss 标价估算约 ${estimated_cost:.3f}。",
        "",
        "## 并列分数敏感性",
        "",
        "8 个二值视角会制造大量相同错误率。冻结协议按 item ID 打破并列，因此主表 AP "
        "会受任意 ID 顺序影响；阈值式 tie-aware AP 是必要的稳健性检查：",
        "",
        f"- 行为 AP：{tie_sensitivity['behavior_threshold_average_precision']:.3f}",
        f"- 语义 gate AP：{tie_sensitivity['semantic_threshold_average_precision']:.3f}",
        f"- 变化：{tie_sensitivity['threshold_delta']:+.4f}",
        "",
        "## 冻结条件",
        "",
    ]
    lines.extend(
        f"- {'✓' if passed else '✗'} `{name}`"
        for name, passed in decision["conditions"].items()
    )
    lines.extend(
        [
            "",
            "## 解释",
            "",
            "这是已看过聚合标签后的后续诊断，不是未见 holdout。真正可迁移的结论是级联"
            "成本结构：先用零新增执行成本的历史轨迹缩小范围，再把 LLM 用在少量候选上；"
            "是否允许 LLM 改变排序必须由冻结对照决定。",
            "",
            "## Provenance",
            "",
        ]
    )
    lines.extend(
        f"- `{name}`: `{value}`"
        for name, value in metrics["provenance"].items()
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "run", "evaluate", "all"))
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare()
    elif args.phase == "run":
        run_audit()
    elif args.phase == "evaluate":
        evaluate()
    else:
        prepare()
        run_audit()
        evaluate()


if __name__ == "__main__":
    main()
