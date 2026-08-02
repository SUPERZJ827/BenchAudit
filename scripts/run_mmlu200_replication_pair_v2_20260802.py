#!/usr/bin/env python3
"""Run the frozen complete 18-method MMLU-200 V2 replication pair."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Iterable


BASE_PATH = Path(__file__).with_name("run_mmlu200_replication_pair_20260802.py")
SPEC = importlib.util.spec_from_file_location("mmlu200_pair_v1_helpers", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import frozen pair helpers: {BASE_PATH}")
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

DATA_SHA256 = "0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4"
MANIFEST_SHA256 = "f60757deeb3f8ba6a682575fd7a87573999b8f0004894729f4904c189f6d77e1"
CONFIG_SHA256 = "9b8c0d774e527c470d3854dc5d0f02512056daa3f01755aa3d17312ac3482e52"
MAX_API_ATTEMPTS = 1_600
MAX_RUN_TOKENS = 4_000_000
MAX_TOTAL_TOKENS = 8_000_000
EXPECTED_ITEMS = 200

EXPECTED_METHODS = [
    "task_specification",
    "context_attachment",
    "expected_output",
    "oracle_ground_truth",
    "evaluator",
    "task_integrity",
    "contract_consistency",
    "evaluator_replay",
    "metamorphic_answer",
    "evaluator_mutation",
    "executable_evidence",
    "differential_candidate",
    "llm_gold_audit",
    "llm_question_clarity",
    "llm_option_set",
    "duplicate_conflict",
    "schema_drift",
    "choice_encoding_contract",
]

# Reuse only the V1 runner's metric and validation implementation. Override its
# frozen experimental constants in this process; the V1 source file and its
# hash-bound result remain unchanged on disk.
BASE.EXPECTED_METHODS = EXPECTED_METHODS
BASE.MAX_API_ATTEMPTS = MAX_API_ATTEMPTS
BASE.MAX_RUN_TOKENS = MAX_RUN_TOKENS


def audit_command(
    *,
    data: Path,
    manifest: Path,
    config: Path,
    cache: Path,
    report_path: Path,
    report_md: Path,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "benchcore.cli",
        "audit",
        str(data),
        "--manifest",
        str(manifest),
        "--llm-audit",
        "--llm-auditors",
        "gold,question,option",
        "--gold-evidence-mode",
        "cascade",
        "--llm-config",
        str(config),
        "--llm-cache",
        str(cache),
        "--workers",
        str(BASE.WORKERS),
        "--progress-every",
        "10",
        "--out",
        str(report_path),
        "--md",
        str(report_md),
        "--allow-remote-data-egress",
        "--print-summary",
    ]


def compare_command(
    *,
    data: Path,
    manifest: Path,
    report_path: Path,
    comparison_path: Path,
    comparison_md: Path,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "benchcore.cli",
        "compare",
        str(data),
        "--report",
        str(report_path),
        "--truth-field",
        "metadata.error_type",
        "--clean-value",
        "ok",
        "--manifest",
        str(manifest),
        "--out",
        str(comparison_path),
        "--md",
        str(comparison_md),
        "--print-summary",
    ]


def run_one(
    *,
    index: int,
    repo: Path,
    data: Path,
    manifest: Path,
    config: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run_dir = output_root / f"run{index}"
    run_dir.mkdir(parents=True, exist_ok=False)
    cache = run_dir / "cache.jsonl"
    report_path = run_dir / "report.json"
    report_md = run_dir / "report.md"
    comparison_path = run_dir / "comparison.json"
    comparison_md = run_dir / "comparison.md"
    for path in (cache, report_path, report_md, comparison_path, comparison_md):
        if path.exists():
            raise RuntimeError(f"run artifact already exists: {path}")

    BASE.run_command(
        audit_command(
            data=data,
            manifest=manifest,
            config=config,
            cache=cache,
            report_path=report_path,
            report_md=report_md,
        ),
        cwd=repo,
    )
    report = BASE.load_json(report_path)
    failures, diagnostics = BASE.validate_run(report, expected_cache_path=cache)
    if int(report.get("summary", {}).get("items", -1)) != EXPECTED_ITEMS:
        failures.append("item_count_mismatch")
    llm = report.get("run_metadata", {}).get("llm", {})
    if int(llm.get("max_api_attempts", -1)) != MAX_API_ATTEMPTS:
        failures.append("configured_api_attempt_limit_mismatch")
    gate = {
        "run": index,
        "passed": not failures,
        "failures": failures,
        "expected_items": EXPECTED_ITEMS,
        "configured_api_attempt_limit": int(llm.get("max_api_attempts", -1)),
        **diagnostics,
    }
    BASE.write_json(run_dir / "integrity_gate.json", gate)
    if failures:
        raise RuntimeError(f"run {index} failed integrity gate: {', '.join(failures)}")

    BASE.run_command(
        compare_command(
            data=data,
            manifest=manifest,
            report_path=report_path,
            comparison_path=comparison_path,
            comparison_md=comparison_md,
        ),
        cwd=repo,
    )
    return report, BASE.load_json(comparison_path), gate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("/home/zhoujun/llmdata/datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/mmlu200_replication_pair_v2_20260802"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    data = args.data.resolve()
    manifest = (repo / "experiments/mmlu_redux_pilot200.manifest.json").resolve()
    config = (repo / "configs/llm_deepseek_mmlu200_replication_v2_20260802.json").resolve()
    output_root = args.output_root.resolve()
    if output_root.exists():
        raise RuntimeError(f"output root must not exist: {output_root}")

    expected_hashes = ((data, DATA_SHA256), (manifest, MANIFEST_SHA256), (config, CONFIG_SHA256))
    for path, expected in expected_hashes:
        actual = BASE.sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")
    if BASE.git_value(repo, "status", "--porcelain"):
        raise RuntimeError("execution checkout must be clean")

    output_root.mkdir(parents=True, exist_ok=False)
    receipt = {
        "schema_version": "mmlu200-replication-pair-v2-receipt-v1",
        "git_commit": BASE.git_value(repo, "rev-parse", "HEAD"),
        "git_detached": BASE.git_is_detached(repo),
        "inputs": {str(path): sha for path, sha in expected_hashes},
        "workers": BASE.WORKERS,
        "auditors": ["gold", "question", "option"],
        "max_api_attempts": MAX_API_ATTEMPTS,
        "expected_methods": EXPECTED_METHODS,
        "v1_cache_reused": False,
    }
    BASE.write_json(output_root / "execution_receipt.json", receipt)

    reports: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    gates: list[dict[str, Any]] = []
    for index in (1, 2):
        report, comparison, gate = run_one(
            index=index,
            repo=repo,
            data=data,
            manifest=manifest,
            config=config,
            output_root=output_root,
        )
        reports.append(report)
        comparisons.append(comparison)
        gates.append(gate)
        if sum(int(row["total_tokens"]) for row in gates) > MAX_TOTAL_TOKENS:
            raise RuntimeError("pair token limit exceeded")

    summary = BASE.build_pair_summary(reports, comparisons, gates)
    summary["schema_version"] = "mmlu200-replication-pair-v2-summary-v1"
    artifact_hashes: dict[str, str] = {}
    for path in sorted(output_root.rglob("*")):
        if path.is_file():
            artifact_hashes[str(path.relative_to(output_root))] = BASE.sha256_file(path)
    summary["artifact_sha256_before_summary"] = artifact_hashes
    BASE.write_json(output_root / "replication_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
