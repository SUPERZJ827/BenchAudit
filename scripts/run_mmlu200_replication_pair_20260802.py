#!/usr/bin/env python3
"""Run the frozen MMLU-200 replication pair and enforce its stop gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


DATA_SHA256 = "0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4"
MANIFEST_SHA256 = "f60757deeb3f8ba6a682575fd7a87573999b8f0004894729f4904c189f6d77e1"
CONFIG_SHA256 = "0bb50a1316370c39541e2d3e7d9cffd21bddc2eaab4bfc48de905a8f64695e6c"
WORKERS = 8
MAX_OPERATIONAL_FAILURE_RATE = 0.05
MAX_RUN_TOKENS = 4_000_000
MAX_TOTAL_TOKENS = 8_000_000
MAX_API_ATTEMPTS = 1_400

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
    "llm_presentation_integrity",
    "llm_quantity_consistency",
    "llm_event_state",
    "duplicate_conflict",
    "schema_drift",
    "choice_encoding_contract",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_json_bytes(value))


def substantive_violations(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in report.get("violations", [])
        if isinstance(row, dict) and row.get("defect_scope") != "presentation"
    ]


def item_set(report: dict[str, Any]) -> set[str]:
    return {str(row.get("item_id")) for row in substantive_violations(report)}


def finding_set(report: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (
            str(row.get("item_id")),
            str(row.get("detection_method")),
            str(row.get("defect_type")),
        )
        for row in substantive_violations(report)
    }


def jaccard(left: set[Any], right: set[Any]) -> float:
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def per_method_jaccard(
    left: set[tuple[str, str, str]], right: set[tuple[str, str, str]]
) -> dict[str, float]:
    by_method_left: dict[str, set[tuple[str, str]]] = defaultdict(set)
    by_method_right: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for item_id, method, defect_type in left:
        by_method_left[method].add((item_id, defect_type))
    for item_id, method, defect_type in right:
        by_method_right[method].add((item_id, defect_type))
    return {
        method: jaccard(by_method_left[method], by_method_right[method])
        for method in sorted(set(by_method_left) | set(by_method_right))
    }


def _operational_failure_rate(report: dict[str, Any]) -> tuple[int, int, float]:
    coverage = report.get("summary", {}).get("audit_coverage", {})
    failed = int(coverage.get("operational_failed", 0))
    attempted = int(coverage.get("attempted", 0))
    rate = failed / attempted if attempted else (1.0 if failed else 0.0)
    return failed, attempted, rate


def validate_run(
    report: dict[str, Any], *, expected_cache_path: Path
) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    if report.get("methods_run") != EXPECTED_METHODS:
        failures.append("methods_run_mismatch")

    metadata = report.get("run_metadata", {})
    if metadata.get("workers") != WORKERS:
        failures.append("workers_mismatch")
    llm = metadata.get("llm", {})
    expected_llm = {
        "model": "deepseek-v4-flash",
        "temperature": 0.0,
        "configured_votes": 1,
        "thinking": "disabled",
        "max_tokens": 5000,
        "proxy_url": "http://127.0.0.1:17890",
    }
    for field, expected in expected_llm.items():
        if llm.get(field) != expected:
            failures.append(f"llm_{field}_mismatch")
    if int(llm.get("cache_hits", -1)) != 0:
        failures.append("cache_hits_nonzero")
    if Path(str(llm.get("cache_path", ""))).resolve() != expected_cache_path.resolve():
        failures.append("cache_path_mismatch")

    attempts = int(llm.get("api_attempts", 0))
    tokens = int(llm.get("total_tokens", 0))
    if attempts > MAX_API_ATTEMPTS:
        failures.append("api_attempt_limit_exceeded")
    if tokens > MAX_RUN_TOKENS:
        failures.append("run_token_limit_exceeded")

    llm_confirmed = [
        row
        for row in report.get("violations", [])
        if isinstance(row, dict)
        and str(row.get("detection_method", "")).startswith("llm_")
        and row.get("evidence_tier") == "confirmed"
    ]
    if llm_confirmed:
        failures.append("llm_derived_confirmed")

    failed, attempted, failure_rate = _operational_failure_rate(report)
    if failure_rate > MAX_OPERATIONAL_FAILURE_RATE:
        failures.append("operational_failure_rate_exceeded")

    diagnostics = {
        "api_attempts": attempts,
        "cache_entries": int(llm.get("cache_entries", 0)),
        "cache_hits": int(llm.get("cache_hits", 0)),
        "total_tokens": tokens,
        "operational_failed": failed,
        "operational_attempted": attempted,
        "operational_failure_rate": failure_rate,
        "llm_derived_confirmed": len(llm_confirmed),
    }
    return failures, diagnostics


def run_command(command: Iterable[str], *, cwd: Path) -> None:
    printable = " ".join(str(part) for part in command)
    print(f"\n$ {printable}", flush=True)
    completed = subprocess.run(list(command), cwd=cwd, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed with exit {completed.returncode}: {printable}")


def git_value(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def git_is_detached(repo: Path) -> bool:
    completed = subprocess.run(
        ["git", "symbolic-ref", "-q", "HEAD"],
        cwd=repo,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode != 0


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

    run_command(
        [
            sys.executable,
            "-m",
            "benchcore.cli",
            "audit",
            str(data),
            "--manifest",
            str(manifest),
            "--llm-audit",
            "--llm-auditors",
            "all",
            "--gold-evidence-mode",
            "cascade",
            "--llm-config",
            str(config),
            "--llm-cache",
            str(cache),
            "--workers",
            str(WORKERS),
            "--progress-every",
            "10",
            "--out",
            str(report_path),
            "--md",
            str(report_md),
            "--allow-remote-data-egress",
            "--print-summary",
        ],
        cwd=repo,
    )
    report = load_json(report_path)
    failures, diagnostics = validate_run(report, expected_cache_path=cache)
    gate = {"run": index, "passed": not failures, "failures": failures, **diagnostics}
    write_json(run_dir / "integrity_gate.json", gate)
    if failures:
        raise RuntimeError(f"run {index} failed integrity gate: {', '.join(failures)}")

    run_command(
        [
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
        ],
        cwd=repo,
    )
    return report, load_json(comparison_path), gate


def build_pair_summary(
    reports: list[dict[str, Any]], comparisons: list[dict[str, Any]], gates: list[dict[str, Any]]
) -> dict[str, Any]:
    left_items, right_items = item_set(reports[0]), item_set(reports[1])
    left_findings, right_findings = finding_set(reports[0]), finding_set(reports[1])
    method_scores = per_method_jaccard(left_findings, right_findings)
    candidate_metrics = [row["substantive_only"]["candidate"] for row in comparisons]
    f1s = [float(row["f1"]) for row in candidate_metrics]
    violation_score = jaccard(left_findings, right_findings)
    f1_difference = abs(f1s[0] - f1s[1])
    if violation_score > 0.845 and f1_difference < 0.046:
        interpretation = "SUPPORTS_MMLU_MORE_STABLE_FOR_THIS_PAIR"
    elif violation_score < 0.845 and f1_difference > 0.046:
        interpretation = "DOES_NOT_SUPPORT_MMLU_MORE_STABLE_FOR_THIS_PAIR"
    else:
        interpretation = "INCONCLUSIVE_MIXED_METRICS"
    values = sorted(method_scores.values())
    median = None
    if values:
        middle = len(values) // 2
        median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    return {
        "schema_version": "mmlu200-replication-pair-summary-v1",
        "runs": gates,
        "metrics": {
            "item_jaccard": jaccard(left_items, right_items),
            "violation_jaccard": violation_score,
            "per_method_jaccard": method_scores,
            "per_method_jaccard_summary": {
                "min": min(values) if values else None,
                "median": median,
                "max": max(values) if values else None,
            },
            "candidate_metrics": candidate_metrics,
            "f1_absolute_difference": f1_difference,
        },
        "interpretation": interpretation,
    }


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
        default=Path("reports/mmlu200_replication_pair_20260802"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    data = args.data.resolve()
    manifest = (repo / "experiments/mmlu_redux_pilot200.manifest.json").resolve()
    config = (repo / "configs/llm_deepseek_mmlu200_replication_20260802.json").resolve()
    output_root = args.output_root.resolve()
    if output_root.exists():
        raise RuntimeError(f"output root must not exist: {output_root}")

    expected_hashes = ((data, DATA_SHA256), (manifest, MANIFEST_SHA256), (config, CONFIG_SHA256))
    for path, expected in expected_hashes:
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")

    if git_value(repo, "status", "--porcelain"):
        raise RuntimeError("execution checkout must be clean")
    output_root.mkdir(parents=True, exist_ok=False)
    receipt = {
        "schema_version": "mmlu200-replication-pair-receipt-v1",
        "git_commit": git_value(repo, "rev-parse", "HEAD"),
        "git_detached": git_is_detached(repo),
        "inputs": {str(path): sha for path, sha in expected_hashes},
        "workers": WORKERS,
        "expected_methods": EXPECTED_METHODS,
    }
    write_json(output_root / "execution_receipt.json", receipt)

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
            raise RuntimeError("pair token limit exceeded; second run result retained but pair gate failed")

    summary = build_pair_summary(reports, comparisons, gates)
    artifact_hashes: dict[str, str] = {}
    for path in sorted(output_root.rglob("*")):
        if path.is_file():
            artifact_hashes[str(path.relative_to(output_root))] = sha256_file(path)
    summary["artifact_sha256_before_summary"] = artifact_hashes
    write_json(output_root / "replication_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
