#!/usr/bin/env python3
"""Score a frozen Workspace two-stage grounding pilot against legacy outputs."""

from __future__ import annotations

import argparse
import json
import sys
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
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-grounding", type=Path, required=True)
    parser.add_argument("--legacy-grounding", type=Path, required=True)
    parser.add_argument("--reviewed-reference", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime-phase", type=Path, action="append", default=[])
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def _decision_sets(
    rows: dict[str, dict[str, Any]],
) -> tuple[set[tuple[str, int]], set[tuple[str, int]], set[tuple[str, int]]]:
    routed: set[tuple[str, int]] = set()
    scanner_unsupported: set[tuple[str, int]] = set()
    final_unsupported: set[tuple[str, int]] = set()
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
                routed.add(key)
            if str(scanner.get("label") or "").casefold() == "unsupported":
                scanner_unsupported.add(key)
            if str(decision.get("label") or "").casefold() == "unsupported":
                final_unsupported.add(key)
    return routed, scanner_unsupported, final_unsupported


def _combine_runtime(paths: list[Path]) -> dict[str, Any]:
    counters = {
        "api_attempts", "api_successes", "api_failures", "prompt_tokens",
        "completion_tokens", "total_tokens", "invalid_responses",
        "truncated_responses", "cache_hits",
    }
    combined = {key: 0 for key in counters}
    wall_seconds = 0.0
    phases = []
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8")).get("grounding", {})
        llm = value.get("llm", {})
        for key in counters:
            combined[key] += int(llm.get(key) or 0)
        wall_seconds += float(value.get("wall_seconds") or 0.0)
        phases.append(str(path))
    return {
        **combined,
        "wall_seconds_sum": wall_seconds,
        "runtime_phases": phases,
    }


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

    new_routed, _, new_final = _decision_sets(new)
    _, legacy_scanner, legacy_final = _decision_sets(legacy)
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
    old_metrics = binary_metrics(
        legacy_final, reviewed_positive, reviewed_universe,
    )
    new_metrics = binary_metrics(
        new_final, reviewed_positive, reviewed_universe,
    )
    routed_metrics = binary_metrics(
        new_routed, reviewed_positive, reviewed_universe,
    )

    rubrics = sum(len(row.get("decisions", [])) for row in new.values())
    legacy_verifiers = sum(
        int(decision.get("verifier") is not None)
        for row in legacy.values()
        for decision in row.get("decisions", [])
        if isinstance(decision, dict)
    )
    shared_calls = sum(
        int(row.get("cost_structure", {}).get("shared_triage_calls") or 0)
        for row in new.values()
    )
    isolated_calls = sum(
        int(row.get("cost_structure", {}).get("isolated_verifier_calls") or 0)
        for row in new.values()
    )
    legacy_calls = rubrics + legacy_verifiers
    new_calls = shared_calls + isolated_calls

    operational = []
    escaped = []
    for item_id, row in new.items():
        for finding in row.get("findings", []):
            if finding.get("defect_scope") == "operational":
                operational.append({
                    "item_id": item_id,
                    "rubric_index": finding.get("evidence", {}).get("rubric_index"),
                })
            if (
                finding.get("evidence_tier") == "confirmed"
                or not finding.get("review_only")
            ):
                escaped.append({
                    "item_id": item_id,
                    "defect_type": finding.get("defect_type"),
                })

    router_legacy_recall = (
        len(new_routed & legacy_final) / len(legacy_final)
        if legacy_final else 1.0
    )
    call_reduction = 1.0 - new_calls / legacy_calls if legacy_calls else 0.0
    f1_delta = new_metrics["f1"] - old_metrics["f1"]
    gates = manifest["go_no_go"]
    gate_results = {
        "review_ceiling": len(escaped) <= gates["max_review_ceiling_escapes"],
        "logical_call_reduction": (
            call_reduction
            >= gates["min_logical_call_reduction_vs_legacy"]
        ),
        "router_recall_legacy_final": (
            router_legacy_recall
            >= gates["min_router_recall_of_legacy_final_candidates"]
        ),
        "reviewed_reference_f1_delta": (
            f1_delta
            >= gates["min_reviewed_reference_f1_delta_vs_legacy"]
        ),
    }
    return {
        "schema_version": "workspace-grounding-cost-pilot-summary-v1",
        "protocol": manifest["protocol"],
        "sample": {
            "items": len(new),
            "rubrics": rubrics,
            "reviewed_positive": len(reviewed_positive),
            "reviewed_negative": len(reviewed_universe - reviewed_positive),
            "selection_warning": manifest["interpretation"],
        },
        "cost": {
            "legacy_scanner_calls": rubrics,
            "legacy_verifier_calls": legacy_verifiers,
            "legacy_logical_calls": legacy_calls,
            "new_shared_triage_calls": shared_calls,
            "new_isolated_verifier_calls": isolated_calls,
            "new_logical_calls": new_calls,
            "logical_call_reduction": call_reduction,
            "runtime": _combine_runtime(args.runtime_phase),
        },
        "routing": {
            "legacy_scanner_candidates": len(legacy_scanner),
            "legacy_final_candidates": len(legacy_final),
            "new_routed_candidates": len(new_routed),
            "new_final_candidates": len(new_final),
            "legacy_final_candidates_routed": len(new_routed & legacy_final),
            "legacy_final_candidate_recall": router_legacy_recall,
            "reviewed_positive_routed": len(new_routed & reviewed_positive),
            "reviewed_positive_routing_recall": (
                len(new_routed & reviewed_positive) / len(reviewed_positive)
                if reviewed_positive else 1.0
            ),
        },
        "reviewed_reference": {
            "legacy_final": old_metrics,
            "new_final": new_metrics,
            "new_router": routed_metrics,
            "final_f1_delta": f1_delta,
            "reference_warning": (
                "These labels are prior evidence-based reviews, not exhaustive "
                "independent human gold."
            ),
        },
        "safety": {
            "operational_unknowns": len(operational),
            "operational_rows": operational,
            "review_ceiling_escapes": len(escaped),
            "escaped_rows": escaped,
        },
        "go_no_go": {
            "thresholds": gates,
            "results": gate_results,
            "passed": sum(gate_results.values()),
            "total": len(gate_results),
            "all_passed": all(gate_results.values()),
        },
    }


def render(summary: dict[str, Any]) -> str:
    cost = summary["cost"]
    routing = summary["routing"]
    old = summary["reviewed_reference"]["legacy_final"]
    new = summary["reviewed_reference"]["new_final"]
    runtime = cost["runtime"]
    gates = summary["go_no_go"]
    gate_rows = "\n".join(
        f"| {name} | {'PASS' if passed else 'FAIL'} |"
        for name, passed in gates["results"].items()
    )
    return f"""# Workspace grounding 成本结构 30-item pilot

> 冻结协议：`{summary['protocol']}`。样本刻意富集难例，不能用于估计
> WorkspaceBench 的自然缺陷率。

## 结论

新结构显著减少调用，并基本保持 reviewed-reference F1；但未复现至少 90%
的旧 final candidates，因此本轮是 **{gates['passed']}/{gates['total']} gates
通过，不是全通过**。

## 成本

| 结构 | scanner/shared | verifier | 逻辑调用 |
|---|---:|---:|---:|
| 旧 isolated | {cost['legacy_scanner_calls']} | {cost['legacy_verifier_calls']} | {cost['legacy_logical_calls']} |
| 新 item-triage | {cost['new_shared_triage_calls']} | {cost['new_isolated_verifier_calls']} | {cost['new_logical_calls']} |

- 逻辑调用减少：**{cost['logical_call_reduction']:.1%}**
- 实际 API attempts：{runtime['api_attempts']}
- 实际 tokens：{runtime['total_tokens']:,}
- API failures：{runtime['api_failures']}
- 截断响应：{runtime['truncated_responses']}

## 路由与质量

- 旧 final candidates 路由召回：
  {routing['legacy_final_candidates_routed']}/{routing['legacy_final_candidates']}
  = **{routing['legacy_final_candidate_recall']:.1%}**
- reviewed positives 路由召回：
  {routing['reviewed_positive_routed']}/{summary['sample']['reviewed_positive']}
  = **{routing['reviewed_positive_routing_recall']:.1%}**

| 系统 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| 旧 isolated final | {old['tp']} | {old['fp']} | {old['fn']} | {old['precision']:.3f} | {old['recall']:.3f} | {old['f1']:.3f} |
| 新 two-stage final | {new['tp']} | {new['fp']} | {new['fn']} | {new['precision']:.3f} | {new['recall']:.3f} | {new['f1']:.3f} |

F1 delta：{summary['reviewed_reference']['final_f1_delta']:+.3f}。

## 预注册 gates

| gate | result |
|---|---|
{gate_rows}

## 安全与边界

- operational unknown：{summary['safety']['operational_unknowns']}
- review ceiling escape：{summary['safety']['review_ceiling_escapes']}
- reviewed reference 不是穷尽性的独立人工 gold。
- 旧 final candidate 也是一次历史模型运行的输出，不等同真值；但该门槛在
  运行前已冻结，因此失败必须如实保留。
"""


def main() -> None:
    args = parse_args()
    args.new_grounding = args.new_grounding.expanduser().resolve()
    args.legacy_grounding = args.legacy_grounding.expanduser().resolve()
    args.reviewed_reference = args.reviewed_reference.expanduser().resolve()
    args.manifest = args.manifest.expanduser().resolve()
    args.runtime_phase = [
        path.expanduser().resolve() for path in args.runtime_phase
    ]
    summary = score(args)
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out_dir / "report.md").write_text(render(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
