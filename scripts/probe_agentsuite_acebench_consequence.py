#!/usr/bin/env python3
"""Replay the official ACEBench evaluator against defensible solver alternatives.

For a reference parameter whose value cannot be derived from the task, the
question that decides whether the item is actually broken is not what a human
annotator judged, but what the benchmark's own evaluator does to a solver that
declines to invent that value. Omitting an optional parameter and substituting an
equally defensible value for a required one are both things a correct solver may
do; if the evaluator rejects them, the item cannot be solved except by guessing.

Deterministic and offline: no model is involved in any verdict here.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
ACE = Path("/home/zhoujun/llmdata/AgentSuite-main/ACEBench")
TRUTH = REPO / "reports/agentsuite_acebench_102_v2_20260816/materialized/sealed_truth.jsonl"
OUT = REPO / "reports/agentsuite_acebench_consequence_probe_20260817"

# (item, probe kind, parameter path, human-readable probe, mutation)
PROBES: list[tuple[str, str, str, str, Callable[[dict[str, Any]], None]]] = [
    ("normal_atom_enum::22", "omit_optional",
     "TrendAnalysisTool_generateMarketInsights.outputDetail", "省略 outputDetail",
     lambda v: v["TrendAnalysisTool_generateMarketInsights"].pop("outputDetail")),
    ("normal_atom_enum::24", "omit_optional",
     "WorldCityClimateAnalyzer_analyzeCityClimate.outputDetailLevel", "省略 outputDetailLevel",
     lambda v: v["WorldCityClimateAnalyzer_analyzeCityClimate"].pop("outputDetailLevel")),
    ("normal_multi_turn_user_adjust::49_0", "omit_optional",
     "travelDealsAggregator_fetchDeals.pricingOptions", "省略 pricingOptions",
     lambda v: v["travelDealsAggregator_fetchDeals"].pop("pricingOptions")),
    ("normal_atom_bool::33", "omit_optional",
     "AudienceEngagementProfiler.include_*", "省略三个 include_* 开关",
     lambda v: [v["AudienceEngagementProfiler"].pop(k) for k in
                ("include_age_group_analysis", "include_device_usage", "include_location_analysis")]),
    ("normal_multi_turn_user_switch::11_1", "omit_optional",
     "MuseumExplorer_getExhibitInfo.navigationOptions", "省略 navigationOptions",
     lambda v: v["MuseumExplorer_getExhibitInfo"].pop("navigationOptions")),
    ("normal_single_turn_parallel_function::1", "omit_optional",
     "finance_credit_scoring.applicant_details.recent_activities[0].amount",
     "省略 recent_activities[0].amount",
     lambda v: v["finance_credit_scoring"]["applicant_details"]["recent_activities"][0].pop("amount")),
    ("normal_preference::49", "substitute_value",
     "addMenuItem.UserDietaryPreference", "Vegetarian 换成 Gluten-Free",
     lambda v: v["addMenuItem"].__setitem__("UserDietaryPreference", "Gluten-Free")),
    ("normal_single_turn_single_function::9", "substitute_value",
     "techHistoryAnalyzer_generateReport.dataSources[0].sourceId", "sourceId 从 1 换成 2",
     lambda v: v["techHistoryAnalyzer_generateReport"]["dataSources"][0].__setitem__("sourceId", "2")),
    ("normal_single_turn_single_function::91", "substitute_value",
     "heritage_damageAssessment.siteDetails.siteId", "siteId 换等价写法",
     lambda v: v["heritage_damageAssessment"]["siteDetails"].__setitem__("siteId", "Beijing Great Wall")),
    ("normal_single_turn_single_function::91", "substitute_value",
     "heritage_damageAssessment.siteDetails.assessmentDate", "assessmentDate 换成另一个合法 June",
     lambda v: v["heritage_damageAssessment"]["siteDetails"].__setitem__("assessmentDate", "2021-06")),
]


def load_probe_module():
    path = REPO / "scripts/probe_agentsuite_evaluator_routes.py"
    spec = importlib.util.spec_from_file_location("probe_routes", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["probe_routes"] = module
    spec.loader.exec_module(module)
    return module


def top_level_required(functions: list[dict[str, Any]], names: list[str]) -> dict[str, list[str]]:
    """Top-level required list per called function. Informational only: it says
    nothing about nested objects, where several probed parameters actually live."""
    wanted = set(names)
    out: dict[str, list[str]] = {}
    for entry in functions:
        body = entry.get("function") if isinstance(entry.get("function"), dict) else entry
        name = str(body.get("name", ""))
        if name in wanted:
            out[name] = list((body.get("parameters") or {}).get("required") or [])
    return out


def main() -> int:
    module = load_probe_module()
    tasks = module.load_rows(ACE / "data_all/data_en", answer=False)
    answers = module.load_rows(ACE / "data_all/data_en/possible_answer", answer=True)
    sys.path.insert(0, str(ACE))
    try:
        from model_eval.checker import normal_checker  # type: ignore
    finally:
        sys.path.pop(0)

    truth = {json.loads(l)["id"]: int(json.loads(l)["is_issue"])
             for l in TRUTH.read_text(encoding="utf-8").splitlines() if l}

    results = []
    for item, kind, path, label, mutate in PROBES:
        task_name, task_id = item.split("::")
        task = tasks[(task_name, task_id)]
        reference = answers[(task_name, task_id)]["ground_truth"]
        variant = copy.deepcopy(reference)
        mutate(variant)
        verdict = normal_checker(task.get("function") or [], module.normal_model_output(variant),
                                 reference, task.get("question") or "", task_name)
        called = [str(n) for n in reference]
        results.append({
            "item": item,
            "human_is_issue": truth[f"agentsuite-ace::{item}"],
            "probe_kind": kind,
            "parameter_path": path,
            "probe": label,
            "evaluator_accepts": bool(verdict.get("valid")),
            "evaluator_error": verdict.get("error"),
            "top_level_required": top_level_required(task.get("function") or [], called),
        })
        print(f"{item:<42}{label:<34}{'接受' if verdict.get('valid') else '拒绝'}"
              f"   人工={'缺陷' if truth[f'agentsuite-ace::{item}'] else '非缺陷'}")

    hard = [r for r in results if not r["evaluator_accepts"]]
    cosmetic = [r for r in results if r["evaluator_accepts"]]
    receipt = {
        "schema_version": 1,
        "protocol": "acebench-evaluation-consequence-probe-v1",
        "claims_ceiling": "mechanical evaluator behaviour on defensible solver alternatives; "
                          "no model judgement enters any verdict here",
        "probes": len(results),
        "evaluator_rejects": len(hard),
        "evaluator_accepts": len(cosmetic),
        "disagreement_with_human_label": {
            "rejected_but_labelled_non_issue": sorted({r["item"] for r in hard if not r["human_is_issue"]}),
            "accepted_but_labelled_issue": sorted({r["item"] for r in cosmetic if r["human_is_issue"]}),
        },
        "results": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "probe_results.json"
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwritten {out} sha256={hashlib.sha256(out.read_bytes()).hexdigest()[:16]}")
    print(json.dumps(receipt["disagreement_with_human_label"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
