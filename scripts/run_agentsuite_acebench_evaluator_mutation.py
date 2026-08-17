#!/usr/bin/env python3
"""Run the reference-evaluator mutation checker over the frozen ACEBench-102 input.

Binds BenchCore's benchmark-agnostic checker to ACEBench's own ``normal_checker``
and reports every reference parameter whose corrupted value that evaluator still
accepts. Deterministic and offline: no model is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from benchcore.loader import build_items, load_mapping, load_rows
from benchcore.reference_evaluator_mutation import ReferenceEvaluatorMutationChecker
from benchcore.schema import BenchmarkItem

REPO = Path(__file__).resolve().parents[1]
ACE = Path("/home/zhoujun/llmdata/AgentSuite-main/ACEBench")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_tree(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_route_module():
    spec = importlib.util.spec_from_file_location(
        "probe_routes", REPO / "scripts/probe_agentsuite_evaluator_routes.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["probe_routes"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    report_path = args.out_dir / "report.json"
    receipt_path = args.out_dir / "receipt.json"
    for path in (report_path, receipt_path):
        if path.exists():
            raise SystemExit(f"refusing to overwrite existing experiment artifact: {path}")

    module = load_route_module()
    tasks = module.load_rows(ACE / "data_all/data_en", answer=False)
    answers = module.load_rows(ACE / "data_all/data_en/possible_answer", answer=True)
    evaluator_files = [ACE / "eval_main.py"] + sorted((ACE / "model_eval").glob("*.py"))
    evaluator_sha256 = sha256_tree([p for p in evaluator_files if p.exists()])
    sys.path.insert(0, str(ACE))
    try:
        from model_eval.checker import normal_checker  # type: ignore
    finally:
        sys.path.pop(0)

    rows = load_rows(args.input)
    items = build_items(rows, load_mapping(args.mapping, rows), source_indices=list(range(len(rows))))

    operational: list[dict[str, Any]] = []

    def replay(item: BenchmarkItem, candidate: dict[str, Any]) -> tuple[bool, Any]:
        _, task_name, task_id = item.item_id.split("::")
        task = tasks[(task_name, task_id)]
        ground_truth = answers[(task_name, task_id)]["ground_truth"]
        verdict = normal_checker(task.get("function") or [], module.normal_model_output(candidate),
                                 ground_truth, task.get("question") or "", task_name)
        return bool(verdict.get("valid")), verdict.get("error")

    checker = ReferenceEvaluatorMutationChecker(replay, evaluator_sha256=evaluator_sha256)
    violations: list[dict[str, Any]] = []
    eligible = 0
    for item in items:
        if not checker.audit_eligibility(item).eligible:
            continue
        _, task_name, task_id = item.item_id.split("::")
        native = answers.get((task_name, task_id), {}).get("ground_truth")
        if not isinstance(native, dict):
            operational.append({"item_id": item.item_id, "stage": "load",
                                "error": "ground_truth_not_dict"})
            continue
        if native != item.raw.get("reference_solution"):
            operational.append({"item_id": item.item_id, "stage": "consistency",
                                "error": "audit input reference differs from ACEBench possible_answer"})
            continue
        eligible += 1
        try:
            found = list(checker.check(item))
        except Exception as exc:  # upstream evaluator failure is research output
            operational.append({"item_id": item.item_id, "stage": "replay",
                                "error": f"{type(exc).__name__}: {exc}"})
            continue
        for violation in found:
            violations.append({
                "item_id": violation.item_id,
                "artifact": violation.artifact,
                "defect_type": violation.defect_type,
                "detection_method": violation.detection_method,
                "severity": violation.severity,
                "evidence_tier": violation.evidence_tier,
                "message": violation.message,
                "evidence": violation.evidence,
            })

    flagged = {v["item_id"] for v in violations}
    unscored = [entry for v in violations for entry in v["evidence"]["unscored_parameters"]]
    by_task = Counter(item_id.split("::")[1] for item_id in flagged)
    report = {
        "schema_version": 1,
        "protocol": "acebench-reference-evaluator-mutation-v1",
        "claims_ceiling": "mechanical evaluator behaviour; no model judgement involved",
        "input_sha256": sha256_file(args.input),
        "mapping_sha256": sha256_file(args.mapping),
        "evaluator_sha256": evaluator_sha256,
        "items_total": len(items),
        "items_eligible": eligible,
        "items_flagged": len(flagged),
        "unscored_parameters": len(unscored),
        "mutation_distribution": dict(Counter(entry["mutation"] for entry in unscored)),
        "flagged_by_task_name": dict(sorted(by_task.items(), key=lambda kv: -kv[1])),
        "operational_failures": operational,
        "violations": violations,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt_path.write_text(json.dumps({
        "schema_version": 1,
        "report_sha256": sha256_file(report_path),
        **{k: report[k] for k in ("protocol", "input_sha256", "mapping_sha256", "evaluator_sha256",
                                  "items_total", "items_eligible", "items_flagged",
                                  "unscored_parameters", "mutation_distribution",
                                  "flagged_by_task_name")},
        "operational_failure_count": len(operational),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "items_total", "items_eligible", "items_flagged", "unscored_parameters",
        "mutation_distribution", "flagged_by_task_name")}, ensure_ascii=False, indent=2))
    print(f"operational failures: {len(operational)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
