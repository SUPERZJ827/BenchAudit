#!/usr/bin/env python3
"""Score the frozen Workspace A + exact-constraint routing holdout."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.run_workspace_static_llm_ablation import (  # noqa: E402
    NEGATIVE_REVIEW_LABEL,
    POSITIVE_REVIEW_LABEL,
    _read_completed_items,
    binary_metrics,
    parse_reviewed_reference,
    sha256_file,
)

Key = tuple[str, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grounding", type=Path, required=True)
    parser.add_argument("--reviewed-reference", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def routing_sets(
    rows: dict[str, dict[str, Any]],
) -> tuple[dict[str, set[Key]], list[dict[str, Any]]]:
    selected = {
        "hidden_constraint": set(),
        "exact_constraint": set(),
        "union": set(),
    }
    exact_details: list[dict[str, Any]] = []
    for item_id, row in rows.items():
        for decision in row.get("decisions", []):
            if not isinstance(decision, dict):
                continue
            rubric_index = decision.get("rubric_index")
            if not isinstance(rubric_index, int):
                continue
            key = (item_id, rubric_index)
            scanner = (
                decision.get("scanner")
                if isinstance(decision.get("scanner"), dict)
                else {}
            )
            views = scanner.get("triage_selected_views")
            views = views if isinstance(views, list) else []
            for view in ("hidden_constraint", "exact_constraint"):
                if view in views:
                    selected[view].add(key)
            if views:
                selected["union"].add(key)
            route = scanner.get("exact_constraint_route")
            if isinstance(route, dict) and route.get("selected") is True:
                exact_details.append({
                    "item_id": item_id,
                    "rubric_index": rubric_index,
                    "rubric": decision.get("rubric"),
                    "reason_codes": route.get("reason_codes") or [],
                    "matched_literals": route.get("matched_literals") or [],
                })
    return selected, exact_details


def analyze(
    *,
    rows: dict[str, dict[str, Any]],
    references: dict[Key, str],
    manifest: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    item_ids = [str(value) for value in manifest["item_ids"]]
    expected = set(item_ids)
    if set(rows) != expected:
        raise ValueError(
            f"result item coverage mismatch: {len(rows)}/{len(expected)}"
        )
    selected, exact_details = routing_sets(rows)
    reviewed_universe = {
        key
        for key, label in references.items()
        if key[0] in expected
        and label in {POSITIVE_REVIEW_LABEL, NEGATIVE_REVIEW_LABEL}
    }
    reviewed_positive = {
        key
        for key, label in references.items()
        if key[0] in expected and label == POSITIVE_REVIEW_LABEL
    }
    metrics = {
        name: binary_metrics(values, reviewed_positive, reviewed_universe)
        for name, values in selected.items()
    }
    incremental = (
        selected["exact_constraint"] - selected["hidden_constraint"]
    )
    incremental_labeled = incremental & reviewed_universe
    incremental_tp = incremental & reviewed_positive
    incremental_fp = incremental_labeled - reviewed_positive
    exact_detail_by_key = {
        (row["item_id"], row["rubric_index"]): row
        for row in exact_details
    }
    all_decisions = [
        decision
        for row in rows.values()
        for decision in row.get("decisions", [])
        if isinstance(decision, dict)
    ]
    verifier_calls = sum(
        int(decision.get("verifier") is not None)
        for decision in all_decisions
    )
    confirmed_or_nonreview = [
        {
            "item_id": item_id,
            "defect_type": finding.get("defect_type"),
            "evidence_tier": finding.get("evidence_tier"),
            "review_only": finding.get("review_only"),
        }
        for item_id, row in rows.items()
        for finding in row.get("findings", [])
        if isinstance(finding, dict)
        and (
            finding.get("evidence_tier") == "confirmed"
            or finding.get("review_only") is not True
        )
    ]
    llm = runtime.get("grounding", {}).get("llm", {})
    api_attempts = int(llm.get("api_attempts") or 0)
    total_tokens = int(llm.get("total_tokens") or 0)
    rubric_count = len(all_decisions)
    incremental_precision = (
        len(incremental_tp) / len(incremental_labeled)
        if incremental_labeled else 0.0
    )
    routed_rate = (
        len(selected["exact_constraint"]) / rubric_count
        if rubric_count else 0.0
    )
    gates = {
        "review_ceiling_escapes_zero": not confirmed_or_nonreview,
        "isolated_verifier_calls_zero": verifier_calls == 0,
        "api_attempts_at_most_40": api_attempts <= 40,
        "reported_tokens_soft_stop_observed": total_tokens <= 600_000,
        "union_recall_not_below_a": (
            metrics["union"]["recall"]
            >= metrics["hidden_constraint"]["recall"]
        ),
        "incremental_reviewed_tp_at_least_1": len(incremental_tp) >= 1,
        "incremental_labeled_precision_at_least_0_50": (
            bool(incremental_labeled) and incremental_precision >= 0.5
        ),
        "exact_routed_rubric_rate_at_most_0_15": routed_rate <= 0.15,
    }
    return {
        "protocol": manifest.get("protocol"),
        "counts": {
            "tasks": len(rows),
            "rubrics": rubric_count,
            "reviewed_universe": len(reviewed_universe),
            "reviewed_positive": len(reviewed_positive),
            "reviewed_negative": len(reviewed_universe - reviewed_positive),
        },
        "metrics": metrics,
        "candidate_counts_all_rubrics": {
            "hidden_constraint": len(selected["hidden_constraint"]),
            "exact_constraint": len(selected["exact_constraint"]),
            "intersection": len(
                selected["hidden_constraint"] & selected["exact_constraint"]
            ),
            "union": len(selected["union"]),
            "exact_incremental_over_a": len(incremental),
        },
        "reviewed_positive_misses": {
            name: sorted(reviewed_positive - values)
            for name, values in selected.items()
        },
        "incremental_exact_over_a": {
            "candidates": len(incremental),
            "reviewed_labeled": len(incremental_labeled),
            "reviewed_tp": len(incremental_tp),
            "reviewed_fp": len(incremental_fp),
            "unlabeled": len(incremental - reviewed_universe),
            "labeled_precision": incremental_precision,
            "llm_calls": 0,
            "calls_per_incremental_reviewed_tp": 0.0
            if incremental_tp else None,
            "reviewed_tp_keys": sorted(incremental_tp),
            "reviewed_fp_keys": sorted(incremental_fp),
            "details": [
                exact_detail_by_key[key]
                for key in sorted(incremental)
                if key in exact_detail_by_key
            ],
        },
        "exact_router": {
            "routed_rubrics": len(selected["exact_constraint"]),
            "routed_rubric_rate": routed_rate,
            "reason_counts": dict(sorted(Counter(
                reason
                for row in exact_details
                for reason in row["reason_codes"]
            ).items())),
            "details": sorted(
                exact_details,
                key=lambda row: (row["item_id"], row["rubric_index"]),
            ),
        },
        "cost_and_safety": {
            "api_attempts": api_attempts,
            "prompt_tokens": int(llm.get("prompt_tokens") or 0),
            "completion_tokens": int(llm.get("completion_tokens") or 0),
            "total_tokens": total_tokens,
            "cache_hits": int(llm.get("cache_hits") or 0),
            "isolated_verifier_calls": verifier_calls,
            "review_ceiling_escapes": confirmed_or_nonreview,
        },
        "gates": gates,
        "all_preregistered_gates_pass": all(gates.values()),
    }


def render_markdown(result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    candidates = result["candidate_counts_all_rubrics"]
    inc = result["incremental_exact_over_a"]
    cost = result["cost_and_safety"]
    gates = result["gates"]
    lines = [
        "# Workspace grounding 第三份 holdout 结果",
        "",
        f"协议：`{result['protocol']}`",
        "",
        "## 路由指标（既有 reviewed-reference 条件口径）",
        "",
        "| 路由 | P | R | F1 | TP | FP | FN |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in (
        ("hidden_constraint", "A：DeepSeek 单视角"),
        ("exact_constraint", "Exact：零 API"),
        ("union", "A + Exact"),
    ):
        row = metrics[key]
        lines.append(
            f"| {label} | {row['precision']:.3f} | {row['recall']:.3f} | "
            f"{row['f1']:.3f} | {row['tp']} | {row['fp']} | {row['fn']} |"
        )
    lines += [
        "",
        "## Exact 相对 A 的增量",
        "",
        (
            "- 全部 rubric 候选数（A / Exact / 交集 / 并集）："
            f"{candidates['hidden_constraint']} / "
            f"{candidates['exact_constraint']} / "
            f"{candidates['intersection']} / {candidates['union']}"
        ),
        f"- 新增候选：{inc['candidates']}",
        f"- reviewed TP / FP：{inc['reviewed_tp']} / {inc['reviewed_fp']}",
        f"- 未标注候选：{inc['unlabeled']}",
        f"- 已标注增量 precision：{inc['labeled_precision']:.3f}",
        "- 额外 LLM 调用：0",
        "",
        "## 成本与安全",
        "",
        f"- API attempts：{cost['api_attempts']}（硬上限 40）",
        f"- tokens：{cost['total_tokens']}（软停止线 600,000）",
        f"- isolated verifier calls：{cost['isolated_verifier_calls']}",
        f"- review ceiling escapes：{len(cost['review_ceiling_escapes'])}",
        "",
        "## 预注册 gate",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'} `{name}`"
        for name, passed in gates.items()
    )
    lines += [
        "",
        f"总裁决：**{'PASS' if result['all_preregistered_gates_pass'] else 'FAIL'}**",
        "",
        "> 本结果只衡量候选路由，不是最终缺陷判定；所有 LLM/路由信号均为 review-only。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    grounding_path = args.grounding.expanduser().resolve()
    reference_path = args.reviewed_reference.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()
    runtime_path = args.runtime.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    result = analyze(
        rows=_read_completed_items(grounding_path),
        references=parse_reviewed_reference(reference_path),
        manifest=manifest,
        runtime=runtime,
    )
    result["provenance"] = {
        "grounding_sha256": sha256_file(grounding_path),
        "reviewed_reference_sha256": sha256_file(reference_path),
        "manifest_sha256": sha256_file(manifest_path),
        "runtime_sha256": sha256_file(runtime_path),
    }
    (out_dir / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "RESULTS.md").write_text(
        render_markdown(result),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
