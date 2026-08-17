#!/usr/bin/env python3
"""Census the official ACEBench evaluator's tolerance surface over all 102 items.

Two questions decide whether a reference value can be a real defect, and only one
of them needs a model. This script answers the mechanical one for every top-level
reference parameter:

- omit an optional parameter: does the evaluator still accept the call?
- substitute a different value: does the evaluator still accept the call?

An optional parameter whose omission is accepted cannot cost any solver a point,
so over-specifying it in the reference is cosmetic. A parameter whose
substitution is rejected is scored by exact match, so if its value also cannot be
derived from the task, the item is unsolvable except by guessing. Deciding
derivability needs a model; this census deliberately stops before that.

Deterministic and offline: no model is involved in any verdict here.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ACE = Path("/home/zhoujun/llmdata/AgentSuite-main/ACEBench")
AUDIT = REPO / "reports/agentsuite_acebench_102_v2_20260816/materialized/audit_input.jsonl"
TRUTH = REPO / "reports/agentsuite_acebench_102_v2_20260816/materialized/sealed_truth.jsonl"
OUT = REPO / "reports/agentsuite_acebench_tolerance_census_20260817"


def load_probe_module():
    spec = importlib.util.spec_from_file_location(
        "probe_routes", REPO / "scripts/probe_agentsuite_evaluator_routes.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["probe_routes"] = module
    spec.loader.exec_module(module)
    return module


def schema_for(functions: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for entry in functions:
        body = entry.get("function") if isinstance(entry.get("function"), dict) else entry
        if str(body.get("name", "")) == name:
            return body
    return None


def alternative(value: Any, spec: dict[str, Any] | None) -> Any:
    """A different value of the same shape, preferring another declared enum member."""
    if isinstance(spec, dict) and isinstance(spec.get("enum"), list):
        for candidate in spec["enum"]:
            if candidate != value:
                return candidate
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + " X" if value else "X"
    if isinstance(value, list):
        return value[:-1] if value else ["X"]
    if isinstance(value, dict):
        return {}
    return "X"


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
    item_ids = [json.loads(l)["id"] for l in AUDIT.read_text(encoding="utf-8").splitlines() if l]

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item_id in item_ids:
        task_name, task_id = item_id.split("::")[1], item_id.split("::")[2]
        key = (task_name, task_id)
        if key not in tasks or key not in answers:
            errors.append({"item": item_id, "stage": "load", "error": "not in ACEBench source"})
            continue
        task = tasks[key]
        reference = answers[key].get("ground_truth")
        if not isinstance(reference, dict):
            errors.append({"item": item_id, "stage": "load", "error": "ground_truth_not_dict"})
            continue
        functions = task.get("function") or []
        question = task.get("question") or ""

        def evaluate(variant: dict[str, Any]) -> tuple[bool, Any]:
            verdict = normal_checker(functions, module.normal_model_output(variant),
                                     reference, question, task_name)
            return bool(verdict.get("valid")), verdict.get("error")

        ok, err = evaluate(copy.deepcopy(reference))
        if not ok:
            errors.append({"item": item_id, "stage": "baseline", "error": err})
            continue

        for call_name, arguments in reference.items():
            if not isinstance(arguments, dict):
                continue
            body = schema_for(functions, str(call_name).rstrip("_0123456789")) or \
                schema_for(functions, str(call_name))
            params = (body or {}).get("parameters") or {}
            required = set(params.get("required") or [])
            properties = params.get("properties") or {}
            for param, value in list(arguments.items()):
                spec = properties.get(param) if isinstance(properties, dict) else None
                is_required = param in required
                row = {"item": item_id, "human_is_issue": truth[item_id],
                       "call": call_name, "parameter": param, "required": is_required,
                       "value_type": type(value).__name__}
                if not is_required:
                    variant = copy.deepcopy(reference)
                    variant[call_name].pop(param, None)
                    row["omit_accepted"], row["omit_error"] = evaluate(variant)
                variant = copy.deepcopy(reference)
                variant[call_name][param] = alternative(value, spec)
                row["substitute_accepted"], row["substitute_error"] = evaluate(variant)
                rows.append(row)

    optional = [r for r in rows if not r["required"]]
    omit_ok = [r for r in optional if r.get("omit_accepted")]
    sub_ok = [r for r in rows if r.get("substitute_accepted")]
    summary = {
        "schema_version": 1,
        "protocol": "acebench-evaluator-tolerance-census-v1",
        "claims_ceiling": "mechanical evaluator behaviour only; deciding whether a value is "
                          "derivable from the task needs a model and is not attempted here",
        "items_probed": len({r["item"] for r in rows}),
        "execution_errors": len(errors),
        "parameters_probed": len(rows),
        "optional_parameters": len(optional),
        "omission_accepted": len(omit_ok),
        "omission_rejected": len(optional) - len(omit_ok),
        "substitution_accepted": len(sub_ok),
        "substitution_rejected": len(rows) - len(sub_ok),
        "omission_rejected_items": sorted({r["item"] for r in optional if not r.get("omit_accepted")}),
        "substitution_accepted_items": sorted({r["item"] for r in sub_ok}),
        "value_type_distribution": dict(Counter(r["value_type"] for r in rows)),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "parameter_probes.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8")
    (OUT / "execution_errors.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = OUT / "receipt.json"
    summary["parameter_probes_sha256"] = hashlib.sha256(
        (OUT / "parameter_probes.jsonl").read_bytes()).hexdigest()
    receipt.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("omission_rejected_items", "substitution_accepted_items")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
