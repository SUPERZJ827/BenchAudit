#!/usr/bin/env python3
"""Zero-network availability preflight for historical MMLU cache binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.inventory_mmlu_holdout_contamination import (
        EXPECTED_DATASET_SHA256,
        extract_universe_ids,
        sha256_file,
        stable_json_bytes,
    )
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from inventory_mmlu_holdout_contamination import (  # type: ignore[no-redef]
        EXPECTED_DATASET_SHA256,
        extract_universe_ids,
        sha256_file,
        stable_json_bytes,
    )


FINEGRAINED_DATASET = Path(
    "/home/zhoujun/llmdata/datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl"
)


@dataclass(frozen=True)
class CacheCase:
    name: str
    cache: str
    reports: tuple[str, ...]
    golden_report: str
    prompt_commit: str
    key_schema: str
    mutation_manifest: str | None = None


CASES = (
    CacheCase(
        "mmlu1000",
        "reports/deepseek_v4_flash_rerun_20260801/mmlu1000_cache.jsonl",
        ("reports/deepseek_v4_flash_rerun_20260801/mmlu1000_report.json",),
        "reports/deepseek_v4_flash_rerun_20260801/mmlu1000_report.json",
        "8057825e170e1cc742cc667112ba8c7845f59705",
        "legacy_extended_without_schema_version",
    ),
    CacheCase(
        "mmlu200",
        "reports/deepseek_v4_flash_rerun_20260801/mmlu200_cache.jsonl",
        ("reports/deepseek_v4_flash_rerun_20260801/mmlu200_report.json",),
        "reports/deepseek_v4_flash_rerun_20260801/mmlu200_report.json",
        "7d9c426ea460052aadf99881c8058d9e1c9fc40f",
        "legacy_extended_without_schema_version",
    ),
    CacheCase(
        "mmlu200_comparable",
        "reports/deepseek_v4_flash_rerun_20260801/mmlu200_comparable_cache.jsonl",
        ("reports/deepseek_v4_flash_rerun_20260801/mmlu200_comparable_report.json",),
        "reports/deepseek_v4_flash_rerun_20260801/mmlu200_comparable_report.json",
        "8057825e170e1cc742cc667112ba8c7845f59705",
        "legacy_extended_without_schema_version",
    ),
    CacheCase(
        "ranking_impact",
        "reports/ranking_impact/audit_llm_cache.jsonl",
        (
            "reports/ranking_impact/audit_pilot10.json",
            "reports/ranking_impact/audit_full1000.json",
        ),
        "reports/ranking_impact/audit_full1000.json",
        "2b3ce354683132ef03eafe684fc79600200f8c9b",
        "legacy_extended_without_schema_version",
    ),
    CacheCase(
        "universal_clean10",
        "reports/universal_audit_experiment_20260713/mmlu_clean10_cache.jsonl",
        ("reports/universal_audit_experiment_20260713/mmlu_clean10_audit.json",),
        "reports/universal_audit_experiment_20260713/mmlu_clean10_audit.json",
        "1942ac3f758d9e199b9939c92030dd7c5217e63c",
        "legacy_minimal",
        "reports/universal_audit_experiment_20260713/mmlu_clean10_wrong_gold.manifest.json",
    ),
    CacheCase(
        "universal_llm10",
        "reports/universal_audit_experiment_20260713/mmlu_llm10_cache.jsonl",
        ("reports/universal_audit_experiment_20260713/mmlu_llm10_audit.json",),
        "reports/universal_audit_experiment_20260713/mmlu_llm10_audit.json",
        "1942ac3f758d9e199b9939c92030dd7c5217e63c",
        "legacy_minimal",
        "reports/universal_audit_experiment_20260713/mmlu_llm10_wrong_gold.manifest.json",
    ),
    CacheCase(
        "universal_llm10_v2",
        "reports/universal_audit_experiment_20260713/mmlu_llm10_v2_cache.jsonl",
        ("reports/universal_audit_experiment_20260713/mmlu_llm10_v2_audit.json",),
        "reports/universal_audit_experiment_20260713/mmlu_llm10_v2_audit.json",
        "1942ac3f758d9e199b9939c92030dd7c5217e63c",
        "legacy_minimal",
        "reports/universal_audit_experiment_20260713/mmlu_llm10_wrong_gold_v2.manifest.json",
    ),
)


class PreflightError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreflightError(f"not a JSON object: {path}")
    return value


def cache_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or set(value) != {"key", "response"}:
                raise PreflightError(f"unexpected cache row shape: {path}:{lineno}")
            key = value.get("key")
            if not isinstance(key, str) or len(key) != 64:
                raise PreflightError(f"invalid cache key: {path}:{lineno}")
            if key in keys:
                raise PreflightError(f"duplicate cache key: {path}:{lineno}")
            keys.add(key)
    return keys


def report_cache_path(report: dict[str, Any]) -> str:
    try:
        return str(report["run_metadata"]["llm"]["cache_path"])
    except (KeyError, TypeError) as exc:
        raise PreflightError("report does not bind an LLM cache path") from exc


def upper_ids_from_report(report: dict[str, Any]) -> set[str]:
    ledger = report.get("coverage_ledger")
    if not isinstance(ledger, list) or not ledger:
        raise PreflightError("report has no coverage ledger")
    ids = {str(row.get("item_id", "")) for row in ledger if isinstance(row, dict)}
    ids.discard("")
    identity = report.get("source_identity") or {}
    if len(ids) != identity.get("audited_rows"):
        raise PreflightError("coverage-ledger ID count does not match source identity")
    return ids


def upper_ids_from_mutation_manifest(path: Path, report: dict[str, Any], root: Path) -> set[str]:
    manifest = read_json(path)
    mutations = manifest.get("mutations")
    if not isinstance(mutations, list) or not mutations:
        raise PreflightError(f"mutation manifest has no rows: {path}")
    source_ids = {str(row.get("source_item_id", "")) for row in mutations}
    mutated_ids = {str(row.get("mutated_item_id", "")) for row in mutations}
    input_path = Path(str(report.get("input_path", "")))
    if not input_path.is_absolute():
        input_path = root / input_path
    input_ids: set[str] = set()
    with input_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                input_ids.add(str(value.get("id", "")))
    if input_ids != mutated_ids:
        raise PreflightError("mutation manifest does not bind the report input IDs")
    if "" in source_ids or "" in mutated_ids:
        raise PreflightError("blank mutation/source ID")
    return source_ids


def implementation_binding(report: dict[str, Any], commit: str) -> dict[str, Any]:
    implementation = report.get("run_metadata", {}).get("implementation")
    if not isinstance(implementation, dict):
        return {
            "implementation_manifest_present": False,
            "prompt_sources_attested": False,
            "reason": "report_predates_implementation_manifest",
        }
    files = implementation.get("files")
    if not isinstance(files, dict):
        raise PreflightError("malformed implementation manifest")
    checked: dict[str, str] = {}
    for path in ("benchcore/llm_client.py", "benchcore/llm_auditor.py"):
        expected = files.get(path)
        if not isinstance(expected, str):
            raise PreflightError(f"implementation manifest missing {path}")
        process = subprocess.run(
            ["git", "show", f"{commit}:{path}"], capture_output=True, check=False
        )
        if process.returncode:
            raise PreflightError(f"cannot read {path} at {commit}")
        observed = hashlib.sha256(process.stdout).hexdigest()
        if observed != expected:
            raise PreflightError(f"implementation hash mismatch for {path} at {commit}")
        checked[path] = observed
    return {
        "implementation_manifest_present": True,
        "prompt_sources_attested": True,
        "prompt_source_hashes": checked,
    }


GOLDEN_HELPER = r'''
import hashlib, json, sys
from pathlib import Path
root=Path(sys.argv[1]); report_path=Path(sys.argv[2]); schema=sys.argv[3]
sys.path.insert(0, sys.argv[4])
from benchcore.loader import load_rows, load_mapping, build_items
import benchcore.llm_auditor as la
report=json.load(open(report_path)); input_path=Path(report["input_path"])
if not input_path.is_absolute(): input_path=root/input_path
rows=load_rows(input_path); items=build_items(rows, load_mapping(None, rows))
ledger=report.get("coverage_ledger") or []
if ledger:
    wanted=ledger[0]["item_id"]; item=next(value for value in items if value.item_id==wanted)
else:
    item=items[0]
system=la.BLIND_SOLVER_SYSTEM_PROMPT; user=la.build_blind_user_prompt(item)
llm=report["run_metadata"]["llm"]
if schema=="legacy_minimal":
    payload={"model":llm["model"],"temperature":llm["temperature"],"system":system,"user":user}
else:
    payload={"model":llm["model"],"base_url":llm["base_url"].rstrip("/"),"temperature":llm["temperature"],"max_tokens":llm["max_tokens"],"dry_run":False,"response_format":"json_object","thinking":llm.get("thinking"),"system":system,"user":user}
key=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
print(json.dumps({"item_id":item.item_id,"key":key},sort_keys=True))
'''


def golden_key(root: Path, worktree: Path, report_path: Path, schema: str) -> dict[str, str]:
    process = subprocess.run(
        [sys.executable, "-c", GOLDEN_HELPER, str(root), str(report_path), schema, str(worktree)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(worktree)},
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode:
        raise PreflightError(f"golden-key helper failed: {process.stderr.strip()}")
    value = json.loads(process.stdout)
    return {"item_id": str(value["item_id"]), "key": str(value["key"])}


def inspect_case(root: Path, case: CacheCase, universe: set[str], worktree: Path) -> dict[str, Any]:
    cache_path = root / case.cache
    keys = cache_keys(cache_path)
    reports = [read_json(root / path) for path in case.reports]
    if any(report_cache_path(report) != case.cache for report in reports):
        raise PreflightError(f"report/cache path mismatch: {case.name}")
    final_entries = reports[-1]["run_metadata"]["llm"].get("cache_entries")
    if final_entries != len(keys):
        raise PreflightError(f"report/cache entry-count mismatch: {case.name}")

    golden_report = read_json(root / case.golden_report)
    if case.mutation_manifest:
        upper_ids = upper_ids_from_mutation_manifest(
            root / case.mutation_manifest, golden_report, root
        )
    else:
        upper_ids = upper_ids_from_report(golden_report)
    if not upper_ids <= universe:
        raise PreflightError(f"upper-bound IDs outside frozen MMLU universe: {case.name}")

    binding = implementation_binding(golden_report, case.prompt_commit)
    golden = golden_key(root, worktree, root / case.golden_report, case.key_schema)
    match = golden["key"] in keys
    if not match:
        raise PreflightError(f"golden key not present in cache: {case.name}")
    return {
        "name": case.name,
        "cache_path": case.cache,
        "cache_sha256": sha256_file(cache_path),
        "cache_entries": len(keys),
        "reports": [
            {"path": path, "sha256": sha256_file(root / path)} for path in case.reports
        ],
        "upper_bound_item_count": len(upper_ids),
        "upper_bound_ids_sha256": hashlib.sha256(
            ("\n".join(sorted(upper_ids)) + "\n").encode()
        ).hexdigest(),
        "upper_bound_complete": True,
        "_upper_bound_ids": sorted(upper_ids),
        "prompt_commit": case.prompt_commit,
        "report_git_dirty": bool(golden_report["run_metadata"]["git"].get("dirty")),
        "key_schema": case.key_schema,
        **binding,
        "golden_initial_key": golden,
        "golden_initial_key_match": True,
        "reverse_status": (
            "attested_prompt_snapshot_golden_match"
            if binding["prompt_sources_attested"]
            else "unattested_prompt_snapshot_golden_match"
        ),
    }


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# MMLU historical-cache binding availability preflight",
        "",
        f"- Outcome: **{result['outcome']}**",
        f"- Caches checked: **{result['counts']['caches']}**",
        f"- Upper-bound bindings complete: **{result['counts']['upper_bound_complete']}**",
        f"- Union of run-bound source items: **{result['counts']['upper_bound_union_items']}**",
        f"- Attested reverse bindings: **{result['counts']['attested_reverse']}**",
        f"- Empirical/unattested reverse bindings: **{result['counts']['unattested_reverse']}**",
        "- Candidate/holdout prompts reconstructed: **0**",
        "",
        "All seven caches have a complete forward item-set bound and a live golden initial-key "
        "match. Three 2026-07-13 reports predate implementation manifests, so their historical "
        "prompt snapshots remain empirically matched but unattested. V2 is feasible only if this "
        "residual limitation is preserved and forward bounds remain authoritative for those runs.",
        "",
    ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> None:
    root = Path(args.repo_root).resolve()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise PreflightError(f"output directory must be empty: {output}")
    if sha256_file(FINEGRAINED_DATASET) != EXPECTED_DATASET_SHA256:
        raise PreflightError("frozen MMLU dataset hash mismatch")
    universe = set(extract_universe_ids(FINEGRAINED_DATASET))

    cases_by_commit: dict[str, list[CacheCase]] = {}
    for case in CASES:
        cases_by_commit.setdefault(case.prompt_commit, []).append(case)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mmlu-cache-a0-") as temp:
        for index, (commit, cases) in enumerate(sorted(cases_by_commit.items())):
            worktree = Path(temp) / f"w{index}"
            process = subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree), commit],
                cwd=root,
                capture_output=True,
                check=False,
            )
            if process.returncode:
                raise PreflightError(f"cannot create historical worktree for {commit}")
            try:
                for case in cases:
                    rows.append(inspect_case(root, case, universe, worktree))
            finally:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree)],
                    cwd=root,
                    capture_output=True,
                    check=False,
                )
    rows.sort(key=lambda value: value["name"])
    upper_union: set[str] = set()
    for row in rows:
        upper_union.update(row.pop("_upper_bound_ids"))
    attested = sum(row["prompt_sources_attested"] for row in rows)
    unattested = len(rows) - attested
    outcome = "PASS_V2_FEASIBLE_WITH_RESIDUAL_UNATTESTED_PROMPT_SNAPSHOTS"
    result = {
        "schema_version": "mmlu-cache-binding-a0-v1",
        "outcome": outcome,
        "outcome_inspected_before_freeze": True,
        "api_attempts": 0,
        "network_attempts": 0,
        "candidate_or_holdout_prompts_reconstructed": 0,
        "candidate_question_gold_or_label_emitted": False,
        "counts": {
            "caches": len(rows),
            "upper_bound_complete": sum(row["upper_bound_complete"] for row in rows),
            "attested_reverse": attested,
            "unattested_reverse": unattested,
            "upper_bound_union_items": len(upper_union),
        },
        "upper_bound_union_ids_sha256": hashlib.sha256(
            ("\n".join(sorted(upper_union)) + "\n").encode()
        ).hexdigest(),
        "cases": rows,
        "v2_constraints": [
            "Forward run-to-item bounds are authoritative for all seven caches.",
            "Reverse absence is supporting evidence and is limited to reconstructable prompt formats.",
            "The three 2026-07-13 prompt snapshots may not be described as attested.",
            "Legacy cache rows do not store a schema version; schema selection is bound by the historical prompt commit and golden-key match.",
            "No candidate set may be generated or audited by this A0 preflight.",
        ],
    }
    result_bytes = stable_json_bytes(result)
    report_bytes = render_report(result).encode()
    (output / "availability.json").write_bytes(result_bytes)
    (output / "REPORT.md").write_bytes(report_bytes)
    receipt = {
        "schema_version": "mmlu-cache-binding-a0-receipt-v1",
        "outcome": outcome,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "dataset_sha256": sha256_file(FINEGRAINED_DATASET),
        "api_attempts": 0,
        "network_attempts": 0,
        "outputs": {
            "availability_sha256": hashlib.sha256(result_bytes).hexdigest(),
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        },
    }
    (output / "receipt.json").write_bytes(stable_json_bytes(receipt))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--out", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        run(parse_args())
    except (PreflightError, OSError, json.JSONDecodeError) as exc:
        print(f"NOT_IDENTIFIABLE_CACHE_BINDING: {exc}", file=sys.stderr)
        raise SystemExit(2)
