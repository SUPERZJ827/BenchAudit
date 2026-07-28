#!/usr/bin/env python3
"""Score the frozen Workspace dual-triage holdout without retuning it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.analyze_workspace_grounding_cost_pilot import (  # noqa: E402
    _combine_runtime,
)
from scripts.run_workspace_static_llm_ablation import (  # noqa: E402
    NEGATIVE_REVIEW_LABEL,
    POSITIVE_REVIEW_LABEL,
    _read_completed_items,
    binary_metrics,
    parse_reviewed_reference,
)

Key = tuple[str, int]
VIEWS = ("hidden_constraint", "support_challenge")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-grounding", type=Path, required=True)
    parser.add_argument("--legacy-grounding", type=Path, required=True)
    parser.add_argument("--reviewed-reference", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime-phase", type=Path, action="append", default=[])
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def decision_sets(
    rows: dict[str, dict[str, Any]],
) -> dict[str, set[Key]]:
    result = {
        "routed_union": set(),
        "routed_hidden_constraint": set(),
        "routed_support_challenge": set(),
        "scanner_unsupported": set(),
        "final_unsupported": set(),
    }
    for item_id, row in rows.items():
        for decision in row.get("decisions", []):
            if not isinstance(decision, dict):
                continue
            index = decision.get("rubric_index")
            if not isinstance(index, int):
                continue
            key = (item_id, index)
            scanner = (
                decision.get("scanner")
                if isinstance(decision.get("scanner"), dict)
                else {}
            )
            if scanner.get("triage_selected") is True:
                result["routed_union"].add(key)
            selected_views = scanner.get("triage_selected_views")
            if isinstance(selected_views, list):
                for view in VIEWS:
                    if view in selected_views:
                        result[f"routed_{view}"].add(key)
            if str(scanner.get("label") or "").casefold() == "unsupported":
                result["scanner_unsupported"].add(key)
            if str(decision.get("label") or "").casefold() == "unsupported":
                result["final_unsupported"].add(key)
    return result


def _recall(predicted: set[Key], positives: set[Key]) -> float:
    return len(predicted & positives) / len(positives) if positives else 1.0


def score(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    item_ids = [str(value) for value in manifest["item_ids"]]
    expected = set(item_ids)
    new = _read_completed_items(args.new_grounding)
    legacy_all = _read_completed_items(args.legacy_grounding)
    if set(new) != expected:
        raise ValueError(
            f"new result item coverage mismatch: {len(new)}/{len(expected)}"
        )
    missing_legacy = expected - set(legacy_all)
    if missing_legacy:
        raise ValueError(f"legacy results are missing: {sorted(missing_legacy)}")
    legacy = {item_id: legacy_all[item_id] for item_id in item_ids}
    new_sets = decision_sets(new)
    legacy_sets = decision_sets(legacy)

    references = parse_reviewed_reference(args.reviewed_reference)
    reviewed_universe = {
        key for key, value in references.items()
        if key[0] in expected
        and value in {POSITIVE_REVIEW_LABEL, NEGATIVE_REVIEW_LABEL}
    }
    reviewed_positive = {
        key for key, value in references.items()
        if key[0] in expected and value == POSITIVE_REVIEW_LABEL
    }
    legacy_final = legacy_sets["final_unsupported"]
    union_final = new_sets["final_unsupported"]
    routed_a = new_sets["routed_hidden_constraint"]
    routed_b = new_sets["routed_support_challenge"]
    routed_union = new_sets["routed_union"]
    # All union candidates share the same isolated verifier outcome. Intersecting
    # with a view reconstructs that view's final output without another API call.
    final_a = union_final & routed_a
    final_b = union_final & routed_b
    support_only = routed_b - routed_a
    support_only_outcomes = {
        label: sum(
            1
            for item_id, row in new.items()
            for decision in row.get("decisions", [])
            if isinstance(decision, dict)
            and (item_id, decision.get("rubric_index")) in support_only
            and str(decision.get("label") or "").casefold() == label
        )
        for label in ("supported", "uncertain", "unsupported")
    }

    metrics = {
        "legacy_final": binary_metrics(
            legacy_final, reviewed_positive, reviewed_universe,
        ),
        "hidden_constraint_final": binary_metrics(
            final_a, reviewed_positive, reviewed_universe,
        ),
        "support_challenge_final": binary_metrics(
            final_b, reviewed_positive, reviewed_universe,
        ),
        "union_final": binary_metrics(
            union_final, reviewed_positive, reviewed_universe,
        ),
    }

    rubrics = sum(len(row.get("decisions", [])) for row in new.values())
    legacy_verifiers = sum(
        int(decision.get("verifier") is not None)
        for row in legacy.values()
        for decision in row.get("decisions", [])
        if isinstance(decision, dict)
    )
    shared_union = sum(
        int(row.get("cost_structure", {}).get("shared_triage_calls") or 0)
        for row in new.values()
    )
    verifier_union = sum(
        int(row.get("cost_structure", {}).get("isolated_verifier_calls") or 0)
        for row in new.values()
    )
    routed_items = sum(
        int(row.get("cost_structure", {}).get("shared_triage_calls") or 0) > 0
        for row in new.values()
    )
    legacy_calls = rubrics + legacy_verifiers
    view_a_calls = routed_items + len(routed_a)
    view_b_calls = routed_items + len(routed_b)
    union_calls = shared_union + verifier_union
    reduction = 1.0 - union_calls / legacy_calls if legacy_calls else 0.0

    operational = []
    escaped = []
    for item_id, row in new.items():
        for finding in row.get("findings", []):
            evidence = (
                finding.get("evidence")
                if isinstance(finding.get("evidence"), dict)
                else {}
            )
            if finding.get("defect_scope") == "operational":
                operational.append({
                    "item_id": item_id,
                    "rubric_index": evidence.get("rubric_index"),
                })
            if (
                finding.get("evidence_tier") == "confirmed"
                or not finding.get("review_only")
            ):
                escaped.append({
                    "item_id": item_id,
                    "defect_type": finding.get("defect_type"),
                })

    routing = {
        "legacy_final": {
            "total": len(legacy_final),
            "hidden_constraint_hits": len(routed_a & legacy_final),
            "hidden_constraint_recall": _recall(routed_a, legacy_final),
            "support_challenge_hits": len(routed_b & legacy_final),
            "support_challenge_recall": _recall(routed_b, legacy_final),
            "union_hits": len(routed_union & legacy_final),
            "union_recall": _recall(routed_union, legacy_final),
        },
        "reviewed_positive": {
            "total": len(reviewed_positive),
            "hidden_constraint_hits": len(routed_a & reviewed_positive),
            "hidden_constraint_recall": _recall(routed_a, reviewed_positive),
            "support_challenge_hits": len(routed_b & reviewed_positive),
            "support_challenge_recall": _recall(routed_b, reviewed_positive),
            "union_hits": len(routed_union & reviewed_positive),
            "union_recall": _recall(routed_union, reviewed_positive),
        },
        "candidate_counts": {
            "hidden_constraint": len(routed_a),
            "support_challenge": len(routed_b),
            "intersection": len(routed_a & routed_b),
            "union": len(routed_union),
            "hidden_only": len(routed_a - routed_b),
            "support_only": len(routed_b - routed_a),
        },
        "final_candidate_counts": {
            "hidden_constraint": len(final_a),
            "support_challenge": len(final_b),
            "union": len(union_final),
            "union_minus_hidden_constraint": len(union_final - final_a),
            "union_minus_hidden_constraint_reviewed_positive": len(
                (union_final - final_a) & reviewed_positive
            ),
            "union_minus_hidden_constraint_reviewed_negative": len(
                (union_final - final_a)
                & (reviewed_universe - reviewed_positive)
            ),
            "union_minus_hidden_constraint_unlabeled": len(
                (union_final - final_a) - reviewed_universe
            ),
            "support_only_verifier_outcomes": support_only_outcomes,
        },
    }

    thresholds = manifest["go_no_go"]
    f1_delta = (
        metrics["union_final"]["f1"] - metrics["legacy_final"]["f1"]
    )
    precision_drop = (
        metrics["hidden_constraint_final"]["precision"]
        - metrics["union_final"]["precision"]
    )
    gate_results = {
        "review_ceiling": (
            len(escaped) <= thresholds["max_review_ceiling_escapes"]
        ),
        "logical_call_reduction": (
            reduction
            >= thresholds["min_logical_call_reduction_vs_legacy"]
        ),
        "union_recall_legacy_final": (
            routing["legacy_final"]["union_recall"]
            >= thresholds["min_union_router_recall_of_legacy_final_candidates"]
        ),
        "union_recall_reviewed_positive": (
            routing["reviewed_positive"]["union_recall"]
            >= thresholds["min_union_router_recall_of_reviewed_positives"]
        ),
        "reviewed_reference_f1_delta": (
            f1_delta
            >= thresholds["min_reviewed_reference_f1_delta_vs_legacy"]
        ),
        "union_precision_drop_vs_hidden_constraint": (
            precision_drop
            <= thresholds["max_union_precision_drop_vs_hidden_constraint"]
        ),
    }
    return {
        "schema_version": "workspace-grounding-dual-holdout-summary-v1",
        "protocol": manifest["protocol"],
        "sample": {
            "items": len(new),
            "rubrics": rubrics,
            "reviewed_positive": len(reviewed_positive),
            "reviewed_negative": len(reviewed_universe - reviewed_positive),
            "selection_warning": manifest["interpretation"],
        },
        "cost": {
            "legacy_logical_calls": legacy_calls,
            "legacy_scanner_calls": rubrics,
            "legacy_verifier_calls": legacy_verifiers,
            "hidden_constraint_counterfactual_calls": view_a_calls,
            "support_challenge_counterfactual_calls": view_b_calls,
            "dual_shared_triage_calls": shared_union,
            "union_isolated_verifier_calls": verifier_union,
            "dual_union_logical_calls": union_calls,
            "logical_call_reduction": reduction,
            "runtime": _combine_runtime(args.runtime_phase),
        },
        "routing": routing,
        "reviewed_reference": {
            **metrics,
            "union_final_f1_delta_vs_legacy": f1_delta,
            "union_precision_drop_vs_hidden_constraint": precision_drop,
            "warning": (
                "Labels are prior evidence-based reviews, not exhaustive "
                "independent human gold. Per-view final metrics reuse the "
                "union run's identical isolated verifier outcomes."
            ),
        },
        "safety": {
            "operational_unknowns": len(operational),
            "operational_rows": operational,
            "review_ceiling_escapes": len(escaped),
            "escaped_rows": escaped,
        },
        "go_no_go": {
            "thresholds": thresholds,
            "results": gate_results,
            "passed": sum(gate_results.values()),
            "total": len(gate_results),
            "all_passed": all(gate_results.values()),
        },
    }


def render(summary: dict[str, Any]) -> str:
    cost = summary["cost"]
    routing = summary["routing"]
    reviewed = summary["reviewed_reference"]
    runtime = cost["runtime"]
    gates = summary["go_no_go"]
    candidate = routing["candidate_counts"]
    final_candidate = routing["final_candidate_counts"]
    legacy_routing = routing["legacy_final"]
    reviewed_routing = routing["reviewed_positive"]
    gate_rows = "\n".join(
        f"| {name} | {'PASS' if passed else 'FAIL'} |"
        for name, passed in gates["results"].items()
    )
    metric_rows = []
    for name, label in (
        ("legacy_final", "旧 isolated final"),
        ("hidden_constraint_final", "视角 A final（反事实重放）"),
        ("support_challenge_final", "视角 B final（反事实重放）"),
        ("union_final", "双视角并集 final"),
    ):
        row = reviewed[name]
        metric_rows.append(
            f"| {label} | {row['tp']} | {row['fp']} | {row['fn']} | "
            f"{row['precision']:.3f} | {row['recall']:.3f} | "
            f"{row['f1']:.3f} |"
        )
    return f"""# Workspace 双 triage 独立 holdout（30 题）

> 冻结协议：`{summary['protocol']}`。该 holdout 与开发用 30 题重合为 0，
> 且在实现双视角前冻结。结果不用于在同一 holdout 上继续调参。

## 结论

预注册门槛通过 **{gates['passed']}/{gates['total']}**；
`all_passed={str(gates['all_passed']).lower()}`。

## 路由互补性

| 路由 | candidates | 旧 final recall | reviewed-positive recall |
|---|---:|---:|---:|
| A hidden-constraint | {candidate['hidden_constraint']} | {legacy_routing['hidden_constraint_recall']:.1%} | {reviewed_routing['hidden_constraint_recall']:.1%} |
| B support-challenge | {candidate['support_challenge']} | {legacy_routing['support_challenge_recall']:.1%} | {reviewed_routing['support_challenge_recall']:.1%} |
| A ∪ B | {candidate['union']} | {legacy_routing['union_recall']:.1%} | {reviewed_routing['union_recall']:.1%} |

- A∩B：{candidate['intersection']}；A-only：{candidate['hidden_only']}；
  B-only：{candidate['support_only']}。
- B-only 的 verifier 结果：supported
  {final_candidate['support_only_verifier_outcomes']['supported']}、
  uncertain {final_candidate['support_only_verifier_outcomes']['uncertain']}、
  unsupported {final_candidate['support_only_verifier_outcomes']['unsupported']}。
- 并集相对 A 新增 {final_candidate['union_minus_hidden_constraint']} 条
  review-only unsupported；其中 reviewed positive
  {final_candidate['union_minus_hidden_constraint_reviewed_positive']}、
  reviewed negative
  {final_candidate['union_minus_hidden_constraint_reviewed_negative']}、
  未标注 {final_candidate['union_minus_hidden_constraint_unlabeled']}。未标注项不能
  直接记为真阳性或假阳性。

## 成本

| 结构 | 逻辑调用 |
|---|---:|
| 旧 isolated | {cost['legacy_logical_calls']} |
| 仅 A（反事实估算） | {cost['hidden_constraint_counterfactual_calls']} |
| 仅 B（反事实估算） | {cost['support_challenge_counterfactual_calls']} |
| 双视角并集（实际结构） | {cost['dual_union_logical_calls']} |

- 相对旧 isolated 减少：**{cost['logical_call_reduction']:.1%}**
- 仅 A 的反事实调用削减：
  **{1 - cost['hidden_constraint_counterfactual_calls'] / cost['legacy_logical_calls']:.1%}**
- 仅 B 的反事实调用削减：
  **{1 - cost['support_challenge_counterfactual_calls'] / cost['legacy_logical_calls']:.1%}**
- 实际 API attempts：{runtime['api_attempts']}
- 实际 tokens：{runtime['total_tokens']:,}
- API failures：{runtime['api_failures']}
- truncated responses：{runtime['truncated_responses']}

## reviewed-reference 指标

| 系统 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(metric_rows)}

- 并集 final F1 delta vs legacy：
  **{reviewed['union_final_f1_delta_vs_legacy']:+.3f}**
- 并集相对 A 的 precision drop：
  **{reviewed['union_precision_drop_vs_hidden_constraint']:+.3f}**

## 预注册 gates

| gate | result |
|---|---|
{gate_rows}

## 安全与解释边界

- operational unknown：{summary['safety']['operational_unknowns']}
- review ceiling escape：{summary['safety']['review_ceiling_escapes']}
- reviewed reference 不是穷尽性的独立人工 gold。
- A/B 单视角 final 是在完全相同的并集 verifier 结果上做集合重放，不是额外
  调用 API 得到的独立 verifier 重跑。
"""


def main() -> None:
    args = parse_args()
    summary = score(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (args.out_dir / "report.md").write_text(render(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
