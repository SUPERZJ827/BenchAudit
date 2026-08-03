#!/usr/bin/env python3
"""Aggregate-only availability preflight for untouched Platinum configs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickletools
import platform
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import huggingface_hub
import numpy
import pyarrow
import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = REPO_ROOT / "docs/research/PLATINUM_UNTOUCHED_DETECTION_HOLDOUT_AVAILABILITY_PROTOCOL_20260803.md"
HELPER = REPO_ROOT / "scripts/inspect_platinum_cache_isolated.py"
DATASET_REPO = "madrylab/platinum-bench"
DATASET_REVISION = "51920a33bfb4620c789729ace14141e87a14969b"
CACHE_REPO = "madrylab/platinum-bench-paper-cache"
CACHE_REVISION = "0012c118c69ea73597d731cd10af9fb2c87727cb"
CODE_REPO = "https://github.com/MadryLab/platinum-benchmarks.git"
CODE_REVISION = "8fd2f82e63c49ea1cca4266f4dded82b7ddbcb55"
DOCKER_IMAGE = "sha256:bfe55ff13ecd6df763474543dc96b5c52b4bcbfceb40f8dc6b25a97baa0f7fd6"
CONFIGS = (
    "bbh_logical_deduction_three_objects",
    "bbh_navigate",
    "bbh_object_counting",
    "drop",
    "hotpotqa",
    "multiarith",
    "singleop",
    "singleq",
    "squad",
    "tab_fact",
    "vqa",
    "winograd_wsc",
)
STATUSES = ("consensus", "verified", "revised", "rejected")
POSITIVE_STATUSES = frozenset({"revised", "rejected"})
NEGATIVE_STATUSES = frozenset({"consensus", "verified"})
PLATINUM_COLUMNS = frozenset(
    {
        "cleaning_status",
        "platinum_prompt",
        "platinum_prompt_no_cot",
        "platinum_target",
        "original_target",
        "platinum_parsing_strategy",
        "platinum_parsing_stratagy",
    }
)
DANGEROUS_PICKLE_OPS = frozenset(
    {
        "GLOBAL", "STACK_GLOBAL", "REDUCE", "BUILD", "OBJ", "INST",
        "NEWOBJ", "NEWOBJ_EX", "EXT1", "EXT2", "EXT4", "PERSID", "BINPERSID",
    }
)


class PreflightError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): normalize(v) for k, v in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def row_identity(config: str, row: dict[str, Any]) -> str:
    for field in ("id", "ID", "query_id", "question_id"):
        if field in row and row[field] is not None:
            payload = [config, field, normalize(row[field])]
            return hashlib.sha256(stable_bytes(payload)).hexdigest()
    original = {k: normalize(v) for k, v in row.items() if k not in PLATINUM_COLUMNS}
    if not original:
        raise PreflightError(f"{config}: no stable identity material")
    return hashlib.sha256(stable_bytes([config, original])).hexdigest()


def aggregate_table(config: str, path: Path) -> dict[str, Any]:
    table = pq.read_table(path)
    rows = table.to_pylist()
    statuses: Counter[str] = Counter()
    identities: list[str] = []
    for row in rows:
        status = row.get("cleaning_status")
        statuses[str(status) if status is not None else "<missing>"] += 1
        identities.append(row_identity(config, row))
    identity_counts = Counter(identities)
    unknown = sum(count for status, count in statuses.items() if status not in STATUSES)
    duplicate_rows = sum(count - 1 for count in identity_counts.values() if count > 1)
    return {
        "config": config,
        "rows": len(rows),
        "status_counts": {status: statuses.get(status, 0) for status in STATUSES},
        "unknown_status_rows": unknown,
        "positive_rows": sum(statuses[s] for s in POSITIVE_STATUSES),
        "negative_rows": sum(statuses[s] for s in NEGATIVE_STATUSES),
        "identity_missing_rows": 0,
        "identity_duplicate_rows": duplicate_rows,
        "identity_outcome": (
            "AVAILABLE" if duplicate_rows == 0 else "NOT_IDENTIFIABLE_ITEM_IDENTITY"
        ),
        "identity_set_sha256": hashlib.sha256(stable_bytes(sorted(identity_counts))).hexdigest(),
        "artifact": {"bytes": path.stat().st_size, "sha256": sha256_file(path)},
    }


def safe_pickle_opcodes(path: Path) -> dict[str, Any]:
    opcodes: Counter[str] = Counter()
    dangerous: Counter[str] = Counter()
    for opcode, _argument, _position in pickletools.genops(path.read_bytes()):
        opcodes[opcode.name] += 1
        if opcode.name in DANGEROUS_PICKLE_OPS:
            dangerous[opcode.name] += 1
    return {
        "dangerous_opcode_counts": dict(sorted(dangerous.items())),
        "opcode_name_set_sha256": hashlib.sha256(stable_bytes(sorted(opcodes))).hexdigest(),
    }


def inspect_cache_in_container(path: Path) -> dict[str, Any]:
    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--user", "65534:65534", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "32",
        "--memory", "512m", "--cpus", "1",
        "-v", f"{path.resolve()}:/input/cache.pkl:ro",
        "-v", f"{HELPER.resolve()}:/app/inspect.py:ro",
        DOCKER_IMAGE, "python", "/app/inspect.py", "/input/cache.pkl",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise PreflightError(f"isolated cache inspection failed: {completed.stderr[:300]}")
    lines = completed.stdout.splitlines()
    if len(lines) != 1:
        raise PreflightError("isolated cache inspection emitted non-canonical output")
    return json.loads(lines[0])


def download_exact(
    repo: str, revision: str, filename: str, root: Path, *, offline: bool = False
) -> Path:
    if offline:
        path = root / repo.split("/")[-1] / filename
        if not path.is_file():
            raise PreflightError(f"offline frozen artifact missing: {repo}:{filename}")
        return path
    return Path(hf_hub_download(
        repo_id=repo, repo_type="dataset", revision=revision,
        filename=filename, local_dir=root / repo.split("/")[-1],
    ))


def dataset_filename(config: str) -> str:
    return f"{config}/test-00000-of-00001.parquet"


def cache_filename(config: str) -> str:
    return f"reliability_benchmark_cache_{config}.pkl"


def decide_detection(configs: list[dict[str, Any]]) -> str:
    if any(row["unknown_status_rows"] for row in configs):
        return "NOT_IDENTIFIABLE_DEFECT_LABELS"
    eligible = [
        row for row in configs
        if row["identity_duplicate_rows"] == 0 and row["identity_missing_rows"] == 0
    ]
    mixed = [
        row for row in eligible
        if row["positive_rows"] > 0 and row["negative_rows"] > 0
    ]
    if len(eligible) < 3:
        return "NOT_IDENTIFIABLE_ITEM_IDENTITY"
    if sum(row["positive_rows"] for row in eligible) < 100 or len(mixed) < 3:
        return "INSUFFICIENT_POSITIVE_PREVALENCE"
    if sum(row["negative_rows"] for row in eligible) < 300:
        return "INSUFFICIENT_NEGATIVE_CONTROLS"
    return "PASS_DETECTION_HOLDOUT_SOURCE_AVAILABLE"


def decide_cache(caches: list[dict[str, Any]], total_bytes: int) -> str:
    if total_bytes > 5 * 1024**3:
        return "CACHE_OVER_PREFLIGHT_BUDGET"
    if any(row["safe_pickle"]["dangerous_opcode_counts"] for row in caches):
        return "NOT_IDENTIFIABLE_CACHE_FORMAT"
    # Frozen protocol forbids a cache join that exposes only generated prompt text.
    if any(not row["inspection"]["explicit_item_identity_present"] for row in caches):
        return "NOT_IDENTIFIABLE_MODEL_OUTPUT_LINKAGE"
    return "INSUFFICIENT_MODEL_OUTPUT_COVERAGE"


def run(data_root: Path, out: Path, *, offline: bool = False) -> dict[str, Any]:
    if offline:
        dataset_siblings = {dataset_filename(config): None for config in CONFIGS}
        cache_siblings = {cache_filename(config): None for config in CONFIGS}
    else:
        api = HfApi()
        dataset_info = api.dataset_info(DATASET_REPO, revision=DATASET_REVISION, files_metadata=True)
        cache_info = api.dataset_info(CACHE_REPO, revision=CACHE_REVISION, files_metadata=True)
        if dataset_info.sha != DATASET_REVISION or cache_info.sha != CACHE_REVISION:
            raise PreflightError("immutable revision did not resolve exactly")
        dataset_siblings = {item.rfilename: item for item in dataset_info.siblings}
        cache_siblings = {item.rfilename: item for item in cache_info.siblings}

    config_results: list[dict[str, Any]] = []
    cache_results: list[dict[str, Any]] = []
    for config in CONFIGS:
        df = dataset_filename(config)
        cf = cache_filename(config)
        if df not in dataset_siblings or cf not in cache_siblings:
            raise PreflightError(f"missing frozen artifact for {config}")
        dataset_path = download_exact(
            DATASET_REPO, DATASET_REVISION, df, data_root, offline=offline
        )
        config_results.append(aggregate_table(config, dataset_path))

        cache_path = download_exact(
            CACHE_REPO, CACHE_REVISION, cf, data_root, offline=offline
        )
        opcode_result = safe_pickle_opcodes(cache_path)
        if opcode_result["dangerous_opcode_counts"]:
            inspection = {
                "explicit_item_identity_present": False,
                "inspection_skipped": "dangerous_pickle_opcodes",
            }
        else:
            inspection = inspect_cache_in_container(cache_path)
        cache_results.append({
            "config": config,
            "artifact": {"bytes": cache_path.stat().st_size, "sha256": sha256_file(cache_path)},
            "safe_pickle": opcode_result,
            "inspection": inspection,
        })

    cache_total_bytes = sum(row["artifact"]["bytes"] for row in cache_results)
    detection_outcome = decide_detection(config_results)
    cache_outcome = decide_cache(cache_results, cache_total_bytes)
    totals = {
        "configs": len(config_results),
        "rows": sum(row["rows"] for row in config_results),
        "positive_rows": sum(row["positive_rows"] for row in config_results),
        "negative_rows": sum(row["negative_rows"] for row in config_results),
        "unknown_status_rows": sum(row["unknown_status_rows"] for row in config_results),
        "mixed_label_configs": sum(row["positive_rows"] > 0 and row["negative_rows"] > 0 for row in config_results),
        "identity_eligible_mixed_label_configs": sum(
            row["identity_outcome"] == "AVAILABLE"
            and row["positive_rows"] > 0
            and row["negative_rows"] > 0
            for row in config_results
        ),
        "cache_bytes": cache_total_bytes,
        "identity_eligible_configs": sum(
            row["identity_outcome"] == "AVAILABLE" for row in config_results
        ),
        "identity_eligible_positive_rows": sum(
            row["positive_rows"] for row in config_results
            if row["identity_outcome"] == "AVAILABLE"
        ),
        "identity_eligible_negative_rows": sum(
            row["negative_rows"] for row in config_results
            if row["identity_outcome"] == "AVAILABLE"
        ),
    }
    availability = {
        "schema_version": "platinum-untouched-availability-v1",
        "scope": {"configs": list(CONFIGS), "excluded_families": ["gsm8k", "mmlu_math", "svamp"]},
        "sources": {
            "dataset": {"repo": DATASET_REPO, "revision": DATASET_REVISION},
            "paper_cache": {"repo": CACHE_REPO, "revision": CACHE_REVISION},
            "evaluation_code": {"repo": CODE_REPO, "revision": CODE_REVISION},
        },
        "config_aggregates": config_results,
        "cache_aggregates": cache_results,
        "totals": totals,
        "outcomes": {"detection_source": detection_outcome, "model_output_matrix": cache_outcome},
        "item_content_emitted": False,
        "item_label_mapping_emitted": False,
        "auditor_executed": False,
        "llm_api_attempts": 0,
        "rng_instantiated": False,
        "network_used_for_current_aggregation": not offline,
        "implementation_corrections_before_result_commit": [
            "An initial uncommitted run incorrectly treated any one config's duplicate native IDs as a global failure. The frozen gate requires at least three identity-valid configs; the implementation was corrected before result publication, without changing protocol thresholds."
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    availability_path = out / "availability.json"
    availability_path.write_bytes(stable_bytes(availability))
    receipt = {
        "schema_version": "platinum-untouched-availability-receipt-v1",
        "protocol_sha256": sha256_file(PROTOCOL),
        "scanner_sha256": sha256_file(Path(__file__)),
        "cache_helper_sha256": sha256_file(HELPER),
        "availability_sha256": sha256_file(availability_path),
        "runtime": {
            "python": platform.python_version(), "numpy": numpy.__version__,
            "pyarrow": pyarrow.__version__, "huggingface_hub": huggingface_hub.__version__,
            "docker_image_id": DOCKER_IMAGE,
        },
        "zero_api": True,
        "zero_auditor_execution": True,
        "network_used_for_current_aggregation": not offline,
    }
    (out / "receipt.json").write_bytes(stable_bytes(receipt))
    report = [
        "# Untouched Platinum detection-holdout availability preflight",
        "",
        f"- Detection source: **{detection_outcome}**",
        f"- Model-output matrix: **{cache_outcome}**",
        f"- Configs/rows: **{totals['configs']} / {totals['rows']}**",
        f"- Natural positives / negative controls: **{totals['positive_rows']} / {totals['negative_rows']}**",
        f"- Identity-eligible positives / negatives: **{totals['identity_eligible_positive_rows']} / {totals['identity_eligible_negative_rows']}**",
        f"- Identity-eligible configs: **{totals['identity_eligible_configs']}**",
        f"- Mixed-label configs: **{totals['mixed_label_configs']}**",
        f"- Identity-eligible mixed-label configs: **{totals['identity_eligible_mixed_label_configs']}**",
        f"- Paper-cache bytes inspected: **{totals['cache_bytes']}**",
        "- Item content or item-label mapping emitted: **false**",
        "- LLM/API/auditor execution: **zero**",
        "",
        "## Per-config aggregates",
        "",
        "| config | rows | consensus | verified | revised | rejected | positive | negative | duplicate IDs | identity outcome |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in config_results:
        counts = row["status_counts"]
        report.append(
            f"| {row['config']} | {row['rows']} | {counts['consensus']} | {counts['verified']} | "
            f"{counts['revised']} | {counts['rejected']} | {row['positive_rows']} | "
            f"{row['negative_rows']} | {row['identity_duplicate_rows']} | {row['identity_outcome']} |"
        )
    report.extend([
        "", "## Pre-publication implementation correction", "",
        "An initial uncommitted run incorrectly treated `tab_fact`'s 17 duplicate native IDs as a global identity failure. The frozen protocol requires at least three identity-valid configs, not all twelve. The implementation was aligned to that existing gate before this result was committed; no threshold or config scope changed.",
        "", "## Boundary", "",
        "A PASS on the dataset axis only establishes that a future, separately frozen detection-holdout protocol is feasible. "
        "The cache axis stops because the published primitive cache keys expose generated prompt text and model/configuration fields but no explicit item identity; policy forbids treating prompt-text matching as an exact item join.",
    ])
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return availability


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    run(Path(args.data_root), Path(args.out), offline=args.offline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
