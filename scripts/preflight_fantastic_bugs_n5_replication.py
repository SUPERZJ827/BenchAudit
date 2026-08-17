#!/usr/bin/env python3
"""Fail-closed preflight and prediction locking for GSM8K-997 Runs 3--5.

This script never calls an API and never reads the sealed truth contents.  It
binds the supplementary stability replication to the exact inputs, source
manifest, configuration, method set, and the two already-published runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchcore.cli import implementation_metadata


OLD_ROOT = REPO_ROOT / "reports/fantastic_bugs_gsm8k_997_20260813"
NEW_ROOT = REPO_ROOT / "reports/fantastic_bugs_gsm8k_997_n5_20260816"
CONFIG = REPO_ROOT / "configs/llm_deepseek_fantastic_bugs_gsm997_v2.json"
PROTOCOL = (
    REPO_ROOT
    / "docs/research/FANTASTIC_BUGS_GSM8K_997_N5_STABILITY_ADDENDUM_20260816.md"
)
SCORER = REPO_ROOT / "scripts/score_fantastic_bugs_n5_stability.py"
TEST = REPO_ROOT / "tests/test_fantastic_bugs_n5_stability.py"

EXPECTED_HASHES = {
    "audit_input": "bb2aea21b3c15079e0cc14eaead775eb47c3d63f34be1396069d7aafbb74ab72",
    "sealed_truth": "9592a7d9677766255e4f34d3508b952498a0287157c3bb99df81512f7f30806b",
    "response_matrix": "a23b44c76e866a3e7328f8c3b20cf493306253a9de495a30669a2966450e5aab",
    "config": "31da3423b320d14f083229f00cd21c8561df1f6822c64041e70598ac07c84be0",
    "run1_report": "6673f506fcf5b03737818ac386e949bc911d9410cd9ee690ec42c20dc962bddb",
    "run2_report": "2466a8a789307bbe734868a57b312a0c1ebe3a54cbb9feac3d712fab354bc16e",
    "old_prediction_lock": "6f8f790289357f95acf436d8e5ac6947aa2a51f5eb03360ef9469c3b15019339",
    "implementation": "fd2edff1e8c17622c9e673970479008e8052066f24f3568d6a14c4d005b30dca",
    "decision_policy": "56e1e670782e01229e6d6554f133800c32bd8d66ddb0d9deaee06a0012acac9b",
}

EXPECTED_METHODS = [
    "task_specification",
    "context_attachment",
    "expected_output",
    "oracle_ground_truth",
    "evaluator",
    "workspace_artifact_invariants",
    "task_integrity",
    "contract_consistency",
    "evaluator_replay",
    "metamorphic_answer",
    "evaluator_mutation",
    "executable_evidence",
    "differential_candidate",
    "llm_gold_audit",
    "llm_question_clarity",
    "llm_quantity_consistency",
    "llm_event_state",
    "solution_leak",
    "duplicate_conflict",
    "schema_drift",
]

EXPECTED_CONFIG = {
    "model": "deepseek-v4-flash",
    "base_url": "https://api.deepseek.com",
    "temperature": 0.0,
    "max_tokens": 5000,
    "n_votes": 1,
    "vote_temperature": 0.3,
    "thinking": "disabled",
    "max_api_attempts": 8000,
    "observed_token_stop": 18_000_000,
    "dry_run": False,
}

RUN_COMMAND_TEMPLATE = [
    "reports/fantastic_bugs_gsm8k_997_20260813/venv/bin/python",
    "-c",
    "from benchcore.cli import main; raise SystemExit(main())",
    "audit",
    "reports/fantastic_bugs_gsm8k_997_20260813/materialized/audit_input.jsonl",
    "--out",
    "{run_dir}/report.json",
    "--md",
    "{run_dir}/report.md",
    "--llm-audit",
    "--llm-auditors",
    "gold,question,quantity,event",
    "--gold-evidence-mode",
    "cascade",
    "--llm-config",
    "configs/llm_deepseek_fantastic_bugs_gsm997_v2.json",
    "--llm-cache",
    "{run_dir}/cache.jsonl",
    "--no-benchmark-profile",
    "--allow-remote-data-egress",
    "--workers",
    "8",
    "--progress-every",
    "100",
]


class PreflightError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise PreflightError(f"missing frozen file: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise PreflightError(f"hash mismatch for {path}: expected {expected}, got {actual}")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreflightError(f"expected JSON object: {path}")
    return value


def validate_frozen_inputs() -> dict[str, Any]:
    paths = {
        "audit_input": OLD_ROOT / "materialized/audit_input.jsonl",
        "sealed_truth": OLD_ROOT / "materialized/sealed_truth.jsonl",
        "response_matrix": OLD_ROOT / "materialized/responses_90models.jsonl",
        "config": CONFIG,
        "run1_report": OLD_ROOT / "complete_run1/report.json",
        "run2_report": OLD_ROOT / "complete_run2/report.json",
        "old_prediction_lock": OLD_ROOT / "final_prediction_lock.json",
    }
    for key, path in paths.items():
        require_hash(path, EXPECTED_HASHES[key])

    current_implementation = implementation_metadata()
    if current_implementation["sha256"] != EXPECTED_HASHES["implementation"]:
        raise PreflightError(
            "BenchCore implementation differs from Runs 1-2: expected "
            f"{EXPECTED_HASHES['implementation']}, got {current_implementation['sha256']}"
        )

    config = load_json(CONFIG)
    for key, expected in EXPECTED_CONFIG.items():
        if config.get(key) != expected:
            raise PreflightError(
                f"config mismatch for {key}: expected {expected!r}, got {config.get(key)!r}"
            )

    old_reports = []
    for run_number in (1, 2):
        report = load_json(OLD_ROOT / f"complete_run{run_number}/report.json")
        validate_report(report, run_number=run_number, old_run=True)
        old_reports.append(report)
    if old_reports[0]["methods_run"] != old_reports[1]["methods_run"]:
        raise PreflightError("Runs 1 and 2 methods_run differ")

    return {
        "implementation": current_implementation,
        "config": config,
        "old_run_cost_cny": [cost_cny(report) for report in old_reports],
        "old_run_total_tokens": [
            int(report["run_metadata"]["llm"]["total_tokens"]) for report in old_reports
        ],
    }


def cost_cny(report: dict[str, Any]) -> float:
    llm = report["run_metadata"]["llm"]
    return float(llm["prompt_tokens"]) / 1_000_000 + 2 * float(
        llm["completion_tokens"]
    ) / 1_000_000


def validate_report(
    report: dict[str, Any], *, run_number: int, old_run: bool = False
) -> dict[str, Any]:
    if report.get("methods_run") != EXPECTED_METHODS:
        raise PreflightError(f"Run {run_number} methods_run differs from the frozen list")
    metadata = report.get("run_metadata", {})
    if metadata.get("implementation", {}).get("sha256") != EXPECTED_HASHES["implementation"]:
        raise PreflightError(f"Run {run_number} implementation manifest mismatch")
    if metadata.get("decision_policy", {}).get("sha256") != EXPECTED_HASHES["decision_policy"]:
        raise PreflightError(f"Run {run_number} decision policy mismatch")
    if metadata.get("workers") != 8:
        raise PreflightError(f"Run {run_number} workers is not 8")
    llm = metadata.get("llm", {})
    expected_llm = {
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "temperature": 0.0,
        "vote_temperature": 0.3,
        "max_tokens": 5000,
        "configured_votes": 1,
        "thinking": "disabled",
        "max_api_attempts": 8000,
        "observed_token_stop": 18_000_000,
    }
    for key, expected in expected_llm.items():
        if llm.get(key) != expected:
            raise PreflightError(
                f"Run {run_number} LLM metadata mismatch for {key}: "
                f"expected {expected!r}, got {llm.get(key)!r}"
            )
    if not old_run and int(llm.get("cache_hits", -1)) != 0:
        raise PreflightError(f"Run {run_number} reused cache entries")
    if int(llm.get("api_attempts", 0)) > 8_000:
        raise PreflightError(f"Run {run_number} exceeded 8,000 API attempts")
    if int(llm.get("total_tokens", 0)) > 18_000_000:
        raise PreflightError(f"Run {run_number} exceeded 18,000,000 observed tokens")
    operational = int(report.get("summary", {}).get("operational_affected_items", 0))
    if operational / 997 > 0.05:
        raise PreflightError(f"Run {run_number} operational failure rate exceeded 5%")
    llm_confirmed = [
        row
        for row in report.get("violations", [])
        if str(row.get("detection_method", "")).startswith("llm_")
        and row.get("evidence_tier") == "confirmed"
    ]
    if llm_confirmed:
        raise PreflightError(f"Run {run_number} contains LLM-derived confirmed findings")
    return {
        "run": run_number,
        "report_sha256": None,
        "api_attempts": int(llm.get("api_attempts", 0)),
        "total_tokens": int(llm.get("total_tokens", 0)),
        "cost_cny": cost_cny(report),
        "operational_affected_items": operational,
        "provider_model_field": llm.get("model"),
        "started_at_utc": metadata.get("started_at_utc"),
        "finished_at_utc": metadata.get("finished_at_utc"),
    }


def run_dir(run_number: int) -> Path:
    return NEW_ROOT / f"complete_run{run_number}"


def command_for_run(run_number: int) -> list[str]:
    relative = run_dir(run_number).relative_to(REPO_ROOT).as_posix()
    return [part.format(run_dir=relative) for part in RUN_COMMAND_TEMPLATE]


def validate_new_runs(completed_through: int) -> list[dict[str, Any]]:
    if completed_through not in {2, 3, 4, 5}:
        raise PreflightError("completed-through must be 2, 3, 4, or 5")
    summaries: list[dict[str, Any]] = []
    for run_number in range(3, completed_through + 1):
        directory = run_dir(run_number)
        report_path = directory / "report.json"
        cache_path = directory / "cache.jsonl"
        if not report_path.is_file() or not cache_path.is_file():
            raise PreflightError(f"Run {run_number} is incomplete")
        report = load_json(report_path)
        summary = validate_report(report, run_number=run_number)
        summary["report_sha256"] = sha256_file(report_path)
        summary["cache_sha256"] = sha256_file(cache_path)
        summary["cache_bytes"] = cache_path.stat().st_size
        summaries.append(summary)

    for run_number in range(completed_through + 1, 6):
        directory = run_dir(run_number)
        for name in ("report.json", "report.md", "cache.jsonl"):
            if (directory / name).exists():
                raise PreflightError(
                    f"future Run {run_number} output already exists: {directory / name}"
                )

    cumulative_tokens = sum(row["total_tokens"] for row in summaries)
    cumulative_cost = sum(row["cost_cny"] for row in summaries)
    if cumulative_tokens > 40_000_000:
        raise PreflightError("supplementary runs exceeded the 40,000,000-token hard stop")
    if cumulative_cost > 46.0:
        raise PreflightError("supplementary runs exceeded the CNY 46 hard stop")
    return summaries


def materials() -> dict[str, Any]:
    paths = {
        "protocol": PROTOCOL,
        "preflight_script": Path(__file__).resolve(),
        "scoring_script": SCORER,
        "test": TEST,
        "config": CONFIG,
    }
    return {
        key: {"path": path.relative_to(REPO_ROOT).as_posix(), "sha256": sha256_file(path)}
        for key, path in paths.items()
    }


def write_freeze_receipt(path: Path, frozen: dict[str, Any]) -> None:
    if path.exists():
        raise PreflightError(f"freeze receipt already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "fantastic-bugs-gsm997-n5-freeze-v1",
        "status": "FROZEN_BEFORE_RUN3_NO_API_CALLED_BY_PREFLIGHT",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "old_experiment_root": OLD_ROOT.relative_to(REPO_ROOT).as_posix(),
        "new_experiment_root": NEW_ROOT.relative_to(REPO_ROOT).as_posix(),
        "expected_hashes": EXPECTED_HASHES,
        "materials": materials(),
        "implementation_sha256": frozen["implementation"]["sha256"],
        "expected_methods": EXPECTED_METHODS,
        "planned_runs": [3, 4, 5],
        "commands": {f"run{n}": command_for_run(n) for n in (3, 4, 5)},
        "known_run1_run2": {
            "cost_cny": frozen["old_run_cost_cny"],
            "total_tokens": frozen["old_run_total_tokens"],
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_prediction_lock(path: Path, freeze_receipt: Path) -> None:
    if path.exists():
        raise PreflightError(f"supplemental prediction lock already exists: {path}")
    summaries = validate_new_runs(5)
    require_hash(OLD_ROOT / "final_prediction_lock.json", EXPECTED_HASHES["old_prediction_lock"])
    payload = {
        "schema_version": "fantastic-bugs-gsm997-n5-prediction-lock-v1",
        "status": "PREDICTIONS_LOCKED_BEFORE_N5_SCORING",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "old_prediction_lock": {
            "path": (OLD_ROOT / "final_prediction_lock.json").relative_to(REPO_ROOT).as_posix(),
            "sha256": EXPECTED_HASHES["old_prediction_lock"],
        },
        "freeze_receipt": {
            "path": freeze_receipt.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(freeze_receipt),
        },
        "new_runs": summaries,
        "truth_sha256_bound_but_not_read": EXPECTED_HASHES["sealed_truth"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed-through", type=int, default=2)
    parser.add_argument(
        "--freeze-receipt", type=Path, default=NEW_ROOT / "freeze_receipt.json"
    )
    parser.add_argument(
        "--prediction-lock", type=Path, default=NEW_ROOT / "supplemental_prediction_lock.json"
    )
    parser.add_argument("--write-freeze", action="store_true")
    parser.add_argument("--write-lock", action="store_true")
    args = parser.parse_args()

    frozen = validate_frozen_inputs()
    summaries = validate_new_runs(args.completed_through)
    if args.write_freeze:
        if args.completed_through != 2:
            raise PreflightError("freeze receipt must be written before Run 3")
        write_freeze_receipt(args.freeze_receipt.resolve(), frozen)
    if args.write_lock:
        if args.completed_through != 5:
            raise PreflightError("prediction lock requires all five runs")
        write_prediction_lock(args.prediction_lock.resolve(), args.freeze_receipt.resolve())

    result = {
        "status": "PASS",
        "completed_through": args.completed_through,
        "new_run_summaries": summaries,
        "next_command": (
            command_for_run(args.completed_through + 1) if args.completed_through < 5 else None
        ),
        "freeze_receipt": str(args.freeze_receipt),
        "prediction_lock": str(args.prediction_lock),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PreflightError as exc:
        raise SystemExit(f"FAIL_CLOSED: {exc}") from exc
