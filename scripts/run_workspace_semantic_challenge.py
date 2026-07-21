#!/usr/bin/env python3
"""Prepare or run the paired Workspace rubric-grounding challenge.

The default ``prepare`` phase is free: it selects a deterministic 50-task
sample, freezes all signatures, and writes provenance-safe clean/mutant files.
API phases require the explicit ``--execute-api`` cost guard.  ``both`` always
finishes the entire clean phase before constructing a separate client/cache for
the mutant phase.

Examples:

  python scripts/run_workspace_semantic_challenge.py --allow-input-root /trusted/workspace-cache
  python scripts/run_workspace_semantic_challenge.py --allow-input-root /trusted/workspace-cache --phase both --execute-api
  python scripts/run_workspace_semantic_challenge.py --allow-input-root /trusted/workspace-cache --phase score
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.loader import build_items, load_mapping, load_rows
from benchcore.workspace_semantic_challenge import (
    CONTRACT_REQUESTED_VS_HIDDEN_COMPANION_FILE,
    INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL,
    INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME,
    SEMANTIC_CHALLENGE_PROTOCOL,
    TASK_EXPLICIT_VS_HIDDEN_TITLE,
    WORKSPACE_SEMANTIC_OPERATORS,
    audit_semantic_phase,
    build_workspace_semantic_challenge,
    canonical_sha256,
    decision_has_operational_failure,
    file_sha256,
    model_signature,
    prompt_signature,
    read_semantic_decisions,
    render_workspace_semantic_markdown,
    rows_contain_semantic_provenance,
    score_workspace_semantic_challenge,
    select_workspace_source_rows,
    semantic_phase_signature,
    semantic_run_signature,
    workspace_semantic_evidence_view_key,
    workspace_snapshot_signature,
)
from benchcore.workspace_grounding import (
    OBJECTIVE_CITATION_RESOLVER_VERSION,
    build_workspace_evidence_bundle,
    resolve_objective_grounding_certificate,
)
from benchcore.workspace_invariants import workspace_input_path_records, workspace_outputs


SUITES = {
    "lite100": Path("datasets/workspacebench/lite_100.jsonl"),
    "full388": Path("datasets/workspacebench/full.jsonl"),
}
DEFAULT_SEED = 20260714


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=sorted(SUITES), default="lite100")
    parser.add_argument("--dataset", help="Optional Workspace JSONL override")
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--operational-passes", type=int, default=2)
    parser.add_argument(
        "--operator",
        action="append",
        choices=WORKSPACE_SEMANTIC_OPERATORS,
        help="Repeat to select a subset; default runs all four objective pairs",
    )
    parser.add_argument("--llm-config", default="configs/llm_deepseek.json")
    parser.add_argument(
        "--allow-input-root",
        action="append",
        required=True,
        help=(
            "Trusted root containing declared Workspace attachments; repeat as needed. "
            "Symlink targets must remain within these roots."
        ),
    )
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--evidence-chars", type=int, default=16_000)
    parser.add_argument("--no-verifier", action="store_true")
    parser.add_argument(
        "--phase",
        choices=("prepare", "clean", "mutant", "both", "score"),
        default="prepare",
    )
    parser.add_argument(
        "--execute-api",
        action="store_true",
        help="Required for clean/mutant/both; acknowledges external API cost",
    )
    parser.add_argument(
        "--reuse-exact-cache-from",
        help=(
            "Directory containing prior clean/mutant request-keyed caches. Every "
            "new request must be an exact cache hit and no HTTP call is allowed."
        ),
    )
    parser.add_argument(
        "--out-dir",
        help=(
            "Default: reports/workspace_semantic_challenge_<suite>_20260714"
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero unless all planned pairs are cleanly discriminated",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _validate_args(args)
    dataset = _resolve(args.dataset or SUITES[args.suite])
    config_path = _resolve(args.llm_config)
    out_dir = _resolve(
        args.out_dir
        or Path("reports")
        / f"workspace_semantic_challenge_{args.suite}_{DEFAULT_SEED}"
    )
    if not dataset.is_file():
        raise FileNotFoundError(dataset)
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_allowed_roots = tuple(
        _resolve(value).resolve() for value in args.allow_input_root
    )

    all_rows = load_rows(dataset)
    selected_sources = select_workspace_source_rows(
        all_rows,
        sample_size=args.sample_size,
        seed=args.seed,
        root=dataset.parent,
        allowed_roots=source_allowed_roots,
    )
    source_snapshot_sha = workspace_snapshot_signature(
        selected_sources,
        root=dataset.parent,
        allowed_roots=source_allowed_roots,
    )
    attachment_root = out_dir / "attachment_snapshot"
    selected, attachment_manifest = materialize_attachment_snapshot(
        selected_sources,
        dataset_root=dataset.parent,
        allowed_roots=source_allowed_roots,
        snapshot_root=attachment_root,
    )
    challenge_allowed_roots = (attachment_root.resolve(),)
    operators = tuple(args.operator or WORKSPACE_SEMANTIC_OPERATORS)
    challenge = build_workspace_semantic_challenge(
        selected,
        root=attachment_root,
        allowed_roots=challenge_allowed_roots,
        seed=args.seed,
        operators=operators,
    )
    expected_pairs = len(selected) * len(operators)
    if challenge.skipped or len(challenge.provenance) != expected_pairs:
        raise RuntimeError(
            "objective challenge construction was incomplete: "
            f"expected={expected_pairs}, built={len(challenge.provenance)}, "
            f"skipped={len(challenge.skipped)}"
        )
    if rows_contain_semantic_provenance(challenge.clean_rows) or (
        rows_contain_semantic_provenance(challenge.mutant_rows)
    ):
        raise RuntimeError("provenance leaked into an auditor-visible challenge file")

    evidence_preflight = preflight_challenge_views(
        challenge,
        root=attachment_root,
        allowed_roots=challenge_allowed_roots,
        # Freeze parser-derived evidence deterministically before model fan-out.
        # LLM calls remain parallel; attachment extraction does not.
        workers=1,
        evidence_chars=args.evidence_chars,
    )
    config = load_llm_config(str(config_path))
    verify = not args.no_verifier
    prompt_sha = prompt_signature()
    model_sha = model_signature(
        config,
        verify_unsupported=verify,
        min_confidence=args.min_confidence,
        evidence_chars=args.evidence_chars,
    )
    snapshot_sha = workspace_snapshot_signature(
        selected,
        root=attachment_root,
        allowed_roots=challenge_allowed_roots,
    )
    challenge_manifest = challenge.manifest()
    implementation_sha = implementation_signature()
    run_sha = semantic_run_signature(
        workspace_snapshot_sha256=snapshot_sha,
        challenge_manifest={
            **challenge_manifest,
            "implementation_signature": implementation_sha,
            "evidence_preflight_signature": evidence_preflight["signature"],
        },
        model_sha256=model_sha,
        prompt_sha256=prompt_sha,
    )
    immutable_manifest = {
        "schema_version": "1.0",
        "protocol_version": SEMANTIC_CHALLENGE_PROTOCOL,
        "run_signature": run_sha,
        "suite": args.suite,
        "dataset": str(dataset),
        "dataset_sha256": file_sha256(dataset),
        "source_allowed_roots": [str(path) for path in source_allowed_roots],
        "attachment_snapshot_root": str(attachment_root),
        "seed": args.seed,
        "sample_size": args.sample_size,
        "selected_source_ids": [str(row["item_id"]) for row in selected],
        "operators": list(operators),
        "pair_count": len(challenge.provenance),
        "response_cache_reuse": {
            "enabled": bool(args.reuse_exact_cache_from),
            "policy": "exact_request_key_all_hits_zero_http",
        },
        "experiment_lineage": {
            "valid_historical_baseline": (
                "reports/workspace_semantic_challenge_lite100_20260714_v2"
            ),
            "invalid_superseded_run": (
                "reports/workspace_semantic_challenge_lite100_20260714_v3"
            ),
            "invalid_superseded_reason": (
                "incomplete pre-final run; no mutant phase or score"
            ),
        },
        "verify_unsupported": verify,
        "min_confidence": args.min_confidence,
        "evidence_chars": args.evidence_chars,
        "evidence_workers": 1,
        "objective_citation_resolver": {
            "version": OBJECTIVE_CITATION_RESOLVER_VERSION,
            "production_visible_inputs": [
                "canonical_task",
                "canonical_output_contract",
                "production_input_inventory",
            ],
            "uses_challenge_sidecar": False,
            "uses_operator_or_expected_label": False,
            "certified_pairs": evidence_preflight["objective_certified_pairs"],
            "verifier_bypass": (
                evidence_preflight["objective_certified_pairs"]
                == len(challenge.provenance)
            ),
        },
        "signatures": {
            "workspace_snapshot_sha256": snapshot_sha,
            "source_workspace_snapshot_sha256": source_snapshot_sha,
            "attachment_manifest_sha256": portable_attachment_manifest_signature(
                attachment_manifest
            ),
            "evidence_preflight_sha256": evidence_preflight["signature"],
            "challenge_manifest_sha256": canonical_sha256(challenge_manifest),
            "clean_rows_sha256": canonical_sha256(challenge.clean_rows),
            "mutant_rows_sha256": canonical_sha256(challenge.mutant_rows),
            "prompt_sha256": prompt_sha,
            "model_sha256": model_sha,
            "implementation_sha256": implementation_sha,
            "clean_phase_sha256": semantic_phase_signature(run_sha, "clean"),
            "mutant_phase_sha256": semantic_phase_signature(run_sha, "mutant"),
        },
        "model": {
            "name": config.model,
            "base_url": config.base_url.rstrip("/"),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "timeout": config.timeout,
            "max_retries": config.max_retries,
        },
    }
    _write_or_validate_run_manifest(out_dir / "run_manifest.json", immutable_manifest)
    write_jsonl_atomic(out_dir / "clean.jsonl", challenge.clean_rows)
    write_jsonl_atomic(out_dir / "mutants.jsonl", challenge.mutant_rows)
    write_json_atomic(out_dir / "challenge_manifest.json", challenge_manifest)
    write_json_atomic(out_dir / "attachment_manifest.json", attachment_manifest)
    write_json_atomic(out_dir / "evidence_preflight.json", evidence_preflight)
    cache_reuse = (
        prepare_exact_cache_reuse(
            _resolve(args.reuse_exact_cache_from), out_dir,
        )
        if args.reuse_exact_cache_from
        else None
    )

    cost = logical_call_budget(
        pairs=len(challenge.provenance),
        verify=verify,
        phases=args.phase,
        operational_passes=args.operational_passes,
        max_retries=config.max_retries,
        objective_verifier_bypass=(
            evidence_preflight["objective_certified_pairs"]
            == len(challenge.provenance)
        ),
    )
    print(
        f"Prepared {len(selected)} source tasks, {len(challenge.provenance)} pairs; "
        f"run_signature={run_sha[:16]}",
        flush=True,
    )
    print(
        "Evidence preflight: "
        f"indexed={evidence_preflight['indexed_files']} "
        f"blocked={evidence_preflight['blocked_files']} "
        f"gold_mismatch={evidence_preflight['synthetic_gold_mismatches']} "
        f"inventory_complete="
        f"{evidence_preflight['input_inventory_complete_tasks']}/"
        f"{evidence_preflight['source_tasks']} "
        f"objective_certified={evidence_preflight['objective_certified_pairs']}/"
        f"{len(challenge.provenance)} "
        f"actor_complete={evidence_preflight['actor_view_complete_tasks']}/"
        f"{evidence_preflight['source_tasks']}",
        flush=True,
    )
    print(
        "Logical model calls: "
        f"expected={cost['expected_calls']} "
        f"configured_upper={cost['configured_logical_call_upper_bound']}; "
        f"HTTP-attempt upper={cost['configured_http_attempt_upper_bound']}",
        flush=True,
    )
    if args.phase == "prepare":
        print(f"Prepared only; no API calls. Wrote {out_dir}", flush=True)
        return 0

    clean_path = out_dir / "clean_decisions.jsonl"
    mutant_path = out_dir / "mutant_decisions.jsonl"
    phase_stats: dict[str, Any] = {}
    started = time.monotonic()
    started_at = datetime.now(timezone.utc)

    with exclusive_run_lock(out_dir / "semantic_challenge.run.lock"):
        if args.phase in {"clean", "both"}:
            clean_client = _phase_client(
                config, out_dir, "clean", cache_only=cache_reuse is not None,
            )
            clean_result = audit_semantic_phase(
                challenge,
                "clean",
                clean_client,
                clean_path,
                run_signature=run_sha,
                root=attachment_root,
                allowed_roots=challenge_allowed_roots,
                workers=args.workers,
                evidence_workers=1,
                operational_passes=args.operational_passes,
                verify_unsupported=verify,
                min_confidence=args.min_confidence,
                evidence_chars=args.evidence_chars,
                progress=ProgressPrinter("clean", len(challenge.clean_rows)),
            )
            phase_stats["clean"] = {
                **_without_decisions(clean_result),
                "client": clean_client.run_stats(),
            }
            write_json_atomic(out_dir / "clean_phase_summary.json", phase_stats["clean"])

        clean_decisions = read_semantic_decisions(
            clean_path,
            phase_signature=semantic_phase_signature(run_sha, "clean"),
        )
        clean_health = phase_health(
            {row.clean_item_id for row in challenge.provenance}, clean_decisions,
        )

        if args.phase in {"mutant", "both"}:
            if not clean_health["complete"]:
                write_json_atomic(out_dir / "clean_gate_failure.json", clean_health)
                raise RuntimeError(
                    "mutant phase is blocked until every clean decision is present, "
                    "unique, and operationally successful; rerun --phase clean"
                )
            # A new client and a distinct cache are a protocol requirement.  No
            # clean challenge row is passed into this phase.
            mutant_client = _phase_client(
                config, out_dir, "mutant", cache_only=cache_reuse is not None,
            )
            mutant_result = audit_semantic_phase(
                challenge,
                "mutant",
                mutant_client,
                mutant_path,
                run_signature=run_sha,
                root=attachment_root,
                allowed_roots=challenge_allowed_roots,
                workers=args.workers,
                evidence_workers=1,
                operational_passes=args.operational_passes,
                verify_unsupported=verify,
                min_confidence=args.min_confidence,
                evidence_chars=args.evidence_chars,
                progress=ProgressPrinter("mutant", len(challenge.mutant_rows)),
            )
            phase_stats["mutant"] = {
                **_without_decisions(mutant_result),
                "client": mutant_client.run_stats(),
            }
            write_json_atomic(out_dir / "mutant_phase_summary.json", phase_stats["mutant"])

        clean_decisions = read_semantic_decisions(
            clean_path,
            phase_signature=semantic_phase_signature(run_sha, "clean"),
        )
        mutant_decisions = read_semantic_decisions(
            mutant_path,
            phase_signature=semantic_phase_signature(run_sha, "mutant"),
        )
        if cache_reuse is not None and args.phase in {"clean", "mutant", "both"}:
            requested_phases = (
                ("clean", "mutant") if args.phase == "both" else (args.phase,)
            )
            cache_checks = {}
            for phase_name in requested_phases:
                client_stats = phase_stats[phase_name]["client"]
                expected_hits = len(
                    challenge.clean_rows
                    if phase_name == "clean"
                    else challenge.mutant_rows
                )
                cache_checks[phase_name] = {
                    "expected_cache_hits": expected_hits,
                    "observed_cache_hits": int(client_stats.get("cache_hits") or 0),
                    "observed_api_attempts": int(client_stats.get("api_attempts") or 0),
                    "passed": (
                        int(client_stats.get("cache_hits") or 0) == expected_hits
                        and int(client_stats.get("api_attempts") or 0) == 0
                    ),
                }
            cache_validation = {
                "schema_version": "1.0",
                "policy": "exact_request_key_all_hits_zero_http",
                "source": cache_reuse,
                "checks": cache_checks,
                "passed": all(row["passed"] for row in cache_checks.values()),
            }
            write_json_atomic(
                out_dir / "exact_cache_reuse_validation.json", cache_validation,
            )
            if not cache_validation["passed"]:
                raise RuntimeError(
                    "exact-cache reuse gate failed: at least one request missed or "
                    "performed an HTTP attempt"
                )
        end_observed = {
            "dataset_sha256": file_sha256(dataset),
            "source_workspace_snapshot_sha256": workspace_snapshot_signature(
                selected_sources,
                root=dataset.parent,
                allowed_roots=source_allowed_roots,
            ),
            "workspace_snapshot_sha256": workspace_snapshot_signature(
                selected,
                root=attachment_root,
                allowed_roots=challenge_allowed_roots,
            ),
            "attachment_manifest_sha256": portable_attachment_manifest_signature(
                json.loads(
                    (out_dir / "attachment_manifest.json").read_text(encoding="utf-8")
                )
            ),
            "evidence_preflight_sha256": str(
                json.loads(
                    (out_dir / "evidence_preflight.json").read_text(encoding="utf-8")
                ).get("signature") or ""
            ),
            "challenge_manifest_sha256": canonical_sha256(
                json.loads(
                    (out_dir / "challenge_manifest.json").read_text(encoding="utf-8")
                )
            ),
            "clean_rows_sha256": canonical_sha256(load_rows(out_dir / "clean.jsonl")),
            "mutant_rows_sha256": canonical_sha256(
                load_rows(out_dir / "mutants.jsonl")
            ),
            "implementation_sha256": implementation_signature(),
        }
        expected_end = {
            key: immutable_manifest["signatures"].get(key)
            if key != "dataset_sha256"
            else immutable_manifest["dataset_sha256"]
            for key in end_observed
        }
        end_check = {
            "schema_version": "1.0",
            "checks": {
                key: {
                    "expected": expected_end[key],
                    "observed": observed,
                    "match": observed == expected_end[key],
                }
                for key, observed in end_observed.items()
            },
        }
        end_check["passed"] = all(
            row["match"] for row in end_check["checks"].values()
        )
        write_json_atomic(out_dir / "source_hash_end_check.json", end_check)
        if not end_check["passed"]:
            raise RuntimeError(
                "source/hash end-check failed; experiment is invalid and was not scored"
            )
        score = score_workspace_semantic_challenge(
            challenge.provenance,
            clean_decisions,
            mutant_decisions,
        )
        summary = {
            "run": {
                **immutable_manifest,
                "requested_phase": args.phase,
                "workers": args.workers,
                "operational_passes": args.operational_passes,
                "started_at_utc": started_at.isoformat(),
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "logical_call_budget": cost,
                "git": git_metadata(),
            },
            "phase_stats": phase_stats,
            "exact_cache_reuse": cache_reuse,
            "clean_health": phase_health(
                {row.clean_item_id for row in challenge.provenance}, clean_decisions,
            ),
            "mutant_health": phase_health(
                {row.mutant_item_id for row in challenge.provenance}, mutant_decisions,
            ),
            "metrics": score,
        }
        write_json_atomic(out_dir / "summary.json", summary)
        write_text_atomic(
            out_dir / "summary.md",
            render_workspace_semantic_markdown(
                challenge,
                score,
                dataset=str(dataset),
            ),
        )

    print(
        "Result: "
        f"mutant={score['mutant_unsupported_hits']}/{score['pairs']} "
        f"paired={score['paired_discriminated']}/{score['pairs']} "
        f"strict={score['strict_paired_discriminated']}/{score['pairs']} "
        f"clean_fp={score['clean_false_alarms']}/{score['clean_evaluable']} "
        f"uncertain={score['uncertain_decisions']} "
        f"operational={score['operational_failure_decisions']} "
        f"extra={score['extra_decision_count']} "
        f"duplicate={score['duplicate_decision_count']}",
        flush=True,
    )
    print(f"Wrote {out_dir}", flush=True)
    if args.strict and not strict_success(score):
        return 2
    return 0


def _validate_args(args: argparse.Namespace) -> None:
    if args.sample_size <= 0:
        raise ValueError("--sample-size must be positive")
    if args.workers <= 0:
        raise ValueError("--workers must be positive")
    if args.operational_passes <= 0:
        raise ValueError("--operational-passes must be positive")
    if not 0.0 <= args.min_confidence <= 1.0:
        raise ValueError("--min-confidence must be between 0 and 1")
    if args.evidence_chars < 1_000:
        raise ValueError("--evidence-chars must be at least 1000")
    if args.phase in {"clean", "mutant", "both"} and not args.execute_api:
        raise ValueError(
            "API execution requires explicit --execute-api; use the default "
            "--phase prepare for a free reproducibility preflight"
        )
    if args.phase in {"prepare", "score"} and args.execute_api:
        raise ValueError("--execute-api is unused for prepare/score")
    if args.reuse_exact_cache_from and args.phase not in {"clean", "mutant", "both"}:
        raise ValueError(
            "--reuse-exact-cache-from requires --phase clean, mutant, or both"
        )


def _resolve(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO / path


def materialize_attachment_snapshot(
    rows: Iterable[Mapping[str, Any]],
    *,
    dataset_root: Path,
    allowed_roots: tuple[Path, ...],
    snapshot_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Freeze declared attachments as regular files under one trusted root.

    Hugging Face dataset files are symlinks into a blob store.  Resolving those
    paths directly loses the logical stored filename and can escape a snapshot
    layout root.  This step validates every resolved source against an explicit
    allowlist, then hardlinks (or copies across filesystems) it to a regular file
    whose basename still matches ``data_manifest.stored_relpath``.
    """

    materialized = [copy.deepcopy(dict(row)) for row in rows]
    if not materialized:
        raise ValueError("cannot materialize an empty source selection")
    snapshot_root.mkdir(parents=True, exist_ok=True)
    items = build_items(materialized, load_mapping(None, materialized))
    file_rows: list[dict[str, Any]] = []
    total_bytes = 0
    for row, item in zip(materialized, items):
        declared = row.get("input_files")
        if not isinstance(declared, list):
            raise ValueError(f"item {item.item_id} has no input_files list")
        records = workspace_input_path_records(
            item,
            dataset_root,
            allowed_roots=allowed_roots,
        )
        if len(records) != len(declared):
            raise RuntimeError(f"path-record cardinality mismatch for {item.item_id}")
        blocked = [record for record in records if not record["allowed"]]
        if blocked:
            preview = ", ".join(str(record["declared"]) for record in blocked[:3])
            raise PermissionError(
                f"item {item.item_id} has {len(blocked)} attachment(s) outside "
                f"--allow-input-root: {preview}"
            )
        task_dir = snapshot_root / hashlib.sha256(
            item.item_id.encode("utf-8")
        ).hexdigest()[:20]
        task_dir.mkdir(parents=True, exist_ok=True)
        relative_paths: list[str] = []
        used_names: dict[str, str] = {}
        for declared_value, record in zip(declared, records):
            # Snapshot the resolved regular file, never the dataset symlink
            # inode.  Hard-linking a relative HF symlink itself produces a
            # broken link once moved under the isolated snapshot directory.
            source = Path(record["resolved_path"])
            if not source.is_file():
                raise FileNotFoundError(
                    f"declared attachment is not a file for {item.item_id}: {source}"
                )
            stored_name = Path(str(declared_value)).name
            if not stored_name or stored_name in {".", ".."}:
                raise ValueError(f"unsafe empty attachment basename for {item.item_id}")
            source_sha = file_sha256(source)
            if stored_name in used_names and used_names[stored_name] != source_sha:
                raise ValueError(
                    f"item {item.item_id} has colliding attachment basename {stored_name}"
                )
            used_names[stored_name] = source_sha
            destination = task_dir / stored_name
            if destination.exists():
                if (
                    destination.is_symlink()
                    or not destination.is_file()
                    or file_sha256(destination) != source_sha
                ):
                    raise RuntimeError(
                        f"attachment snapshot collision at {destination}; use a new --out-dir"
                    )
                mode = "hardlink" if os.path.samefile(source, destination) else "copy"
            else:
                if destination.is_symlink():
                    raise RuntimeError(
                        f"broken symlink collision at {destination}; use a new --out-dir"
                    )
                temporary = destination.with_name(
                    f".{destination.name}.{os.getpid()}.{time.time_ns()}.tmp"
                )
                try:
                    try:
                        os.link(source, temporary)
                        mode = "hardlink"
                    except OSError:
                        shutil.copy2(source, temporary)
                        mode = "copy"
                    if (
                        temporary.is_symlink()
                        or not temporary.is_file()
                        or file_sha256(temporary) != source_sha
                    ):
                        raise RuntimeError(
                            f"attachment snapshot hash mismatch: {temporary}"
                        )
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
                if (
                    destination.is_symlink()
                    or not destination.is_file()
                    or file_sha256(destination) != source_sha
                ):
                    raise RuntimeError(
                        f"attachment snapshot finalization mismatch: {destination}"
                    )
            relative = destination.relative_to(snapshot_root).as_posix()
            relative_paths.append(relative)
            size = destination.stat().st_size
            total_bytes += size
            file_rows.append({
                "source_item_id": item.item_id,
                "declared_path": str(declared_value),
                "resolved_source": str(source),
                "snapshot_relpath": relative,
                "stored_name": stored_name,
                "size_bytes": size,
                "sha256": source_sha,
                "materialization": mode,
            })
        row["input_files"] = relative_paths
    manifest = {
        "schema_version": "1.0",
        "source_allowed_roots": [str(path) for path in allowed_roots],
        # Artifact paths are already relative to this directory.  Recording an
        # absolute temp/output path would make a byte-identical snapshot hash
        # differently across fresh experiment directories.
        "snapshot_root": snapshot_root.name,
        "source_items": len(materialized),
        "files": len(file_rows),
        "total_bytes": total_bytes,
        "artifacts": file_rows,
    }
    return materialized, manifest


def portable_attachment_manifest_signature(manifest: Mapping[str, Any]) -> str:
    """Hash only content/logic identity, excluding machine-local diagnostics."""

    raw_artifacts = manifest.get("artifacts")
    artifacts = raw_artifacts if isinstance(raw_artifacts, list) else []
    portable = [
        {
            "source_item_id": str(row.get("source_item_id") or ""),
            "snapshot_relpath": str(row.get("snapshot_relpath") or ""),
            "stored_name": str(row.get("stored_name") or ""),
            "size_bytes": int(row.get("size_bytes") or 0),
            "sha256": str(row.get("sha256") or ""),
        }
        for row in artifacts
        if isinstance(row, Mapping)
    ]
    return canonical_sha256({
        "schema_version": str(manifest.get("schema_version") or ""),
        "source_items": int(manifest.get("source_items") or 0),
        "files": int(manifest.get("files") or 0),
        "total_bytes": int(manifest.get("total_bytes") or 0),
        "artifacts": sorted(
            portable,
            key=lambda row: (
                row["source_item_id"], row["snapshot_relpath"], row["stored_name"],
            ),
        ),
    })


def prepare_exact_cache_reuse(source_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Stage response-only caches with explicit invalid-run provenance.

    Cache reuse is safe only because ``LLMClient`` keys include the complete
    system/user messages and inference configuration.  The caller additionally
    enforces all expected requests hit and that zero HTTP attempts occur.
    """

    source_dir = Path(source_dir).resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"exact-cache source directory not found: {source_dir}")
    staged: dict[str, Any] = {}
    for phase in ("clean", "mutant"):
        source = source_dir / f"{phase}_llm_cache.jsonl"
        if not source.is_file():
            raise FileNotFoundError(f"missing exact-cache source: {source}")
        rows = []
        for line_number, line in enumerate(
            source.read_text(encoding="utf-8").splitlines(), 1,
        ):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid cache JSON at {source}:{line_number}"
                ) from exc
            if not isinstance(row, dict) or not isinstance(row.get("key"), str) or (
                not isinstance(row.get("response"), dict)
            ):
                raise ValueError(f"invalid cache row shape at {source}:{line_number}")
            rows.append(row)
        keys = [row["key"] for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate request keys in exact-cache source: {source}")
        destination = out_dir / source.name
        if destination.exists():
            if file_sha256(destination) != file_sha256(source):
                raise RuntimeError(
                    f"existing destination cache differs from provenance source: {destination}"
                )
        else:
            shutil.copy2(source, destination)
        staged[phase] = {
            "entries": len(rows),
            "cache_sha256": file_sha256(source),
            "destination_sha256": file_sha256(destination),
        }

    def optional_json(name: str) -> Any:
        path = source_dir / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    source_manifest = optional_json("run_manifest.json")
    provenance = {
        "schema_version": "1.0",
        "source_directory": str(source_dir),
        "source_run_signature": (
            source_manifest.get("run_signature")
            if isinstance(source_manifest, dict)
            else None
        ),
        "source_status": "invalid_source_drift_responses_only",
        "source_end_check": optional_json("source_hash_end_check.json"),
        "source_phase_summaries": {
            phase: optional_json(f"{phase}_phase_summary.json")
            for phase in ("clean", "mutant")
        },
        "staged_caches": staged,
        "reuse_safety": (
            "Complete inference request/config hashes are cache keys; the fresh run "
            "must observe all expected cache hits and zero HTTP attempts."
        ),
    }
    write_json_atomic(out_dir / "cache_provenance.json", provenance)
    return provenance


def preflight_challenge_views(
    challenge: Any,
    *,
    root: Path,
    allowed_roots: tuple[Path, ...],
    workers: int,
    evidence_chars: int,
) -> dict[str, Any]:
    """Prove synthetic gold and production-indexed evidence use one view."""

    clean_rows = list(challenge.clean_rows)
    clean_items = build_items(clean_rows, load_mapping(None, clean_rows))
    item_by_id = {item.item_id: item for item in clean_items}
    source_by_item = {
        provenance.clean_item_id: provenance.source_item_id
        for provenance in challenge.provenance
    }

    # The rendered attachment evidence can be shared, but inventory-completeness
    # also depends on the output contract and the declared complete actor view.
    # Build exactly one production bundle per complete evidence-view key and map
    # it back to every clean challenge item that uses that view.
    items_by_view: dict[str, list[Any]] = defaultdict(list)
    for item in clean_items:
        items_by_view[workspace_semantic_evidence_view_key(item)].append(item)
    bundle_by_view: dict[str, Any] = {}
    with ThreadPoolExecutor(
        max_workers=min(max(1, workers), max(1, len(items_by_view))),
    ) as pool:
        futures = {
            pool.submit(
                build_workspace_evidence_bundle,
                view_items[0],
                root,
                max_chars=evidence_chars,
                allowed_roots=allowed_roots,
            ): view_key
            for view_key, view_items in items_by_view.items()
        }
        for future in as_completed(futures):
            bundle_by_view[futures[future]] = future.result()
    bundle_by_item = {
        item.item_id: bundle_by_view[view_key]
        for view_key, view_items in items_by_view.items()
        for item in view_items
    }

    blocked = sum(
        len(bundle.blocked_files) for bundle in bundle_by_view.values()
    )
    if blocked:
        raise RuntimeError(
            f"production evidence preflight blocked {blocked} snapshotted attachment(s)"
        )
    mismatches: list[dict[str, Any]] = []
    objective_clean_supported = 0
    objective_mutant_unsupported = 0
    objective_certified = 0
    for view_key, view_items in sorted(items_by_view.items()):
        bundle = bundle_by_view[view_key]
        if not bundle.input_inventory_complete:
            mismatches.append({
                "source_item_id": source_by_item[view_items[0].item_id],
                "reason": "production input inventory is not complete",
                "evidence_view": view_key,
                "challenge_item_ids": sorted(item.item_id for item in view_items),
            })
        if not bundle.inventory_absence_is_confirmation_eligible:
            mismatches.append({
                "source_item_id": source_by_item[view_items[0].item_id],
                "reason": "inventory absence is not confirmation-eligible",
                "evidence_view": view_key,
            })

    for provenance in challenge.provenance:
        item = item_by_id[provenance.clean_item_id]
        bundle = bundle_by_item[provenance.clean_item_id]
        clean_certificate = resolve_objective_grounding_certificate(
            item, bundle, provenance.clean_requirement,
        )
        mutant_certificate = resolve_objective_grounding_certificate(
            item, bundle, provenance.mutant_requirement,
        )
        objective_clean_supported += int(
            clean_certificate.get("eligible") is True
            and clean_certificate.get("label") == "supported"
        )
        objective_mutant_unsupported += int(
            mutant_certificate.get("eligible") is True
            and mutant_certificate.get("label") == "unsupported"
        )
        pair_certified = bool(
            clean_certificate.get("eligible") is True
            and clean_certificate.get("label") == "supported"
            and mutant_certificate.get("eligible") is True
            and mutant_certificate.get("label") == "unsupported"
        )
        objective_certified += int(pair_certified)
        if not pair_certified:
            mismatches.append({
                "source_item_id": provenance.source_item_id,
                "operator": provenance.operator,
                "reason": "objective citation resolver does not certify the pair",
                "clean_certificate": clean_certificate,
                "mutant_certificate": mutant_certificate,
            })
        visible_task = (item.task or "(missing task)")[:4000]
        visible_contract = json.dumps(
            {
                "required_files": workspace_outputs(item),
                "declared": item.output_contract,
            },
            ensure_ascii=False,
            default=str,
        )[:2500]
        if provenance.operator == TASK_EXPLICIT_VS_HIDDEN_TITLE:
            title_match = re.search(r'exact title "([^"]+)"', provenance.clean_requirement)
            expected_title = title_match.group(1) if title_match else ""
            if not expected_title or expected_title not in visible_task:
                mismatches.append({
                    "source_item_id": provenance.source_item_id,
                    "operator": provenance.operator,
                    "reason": "clean title support is absent from production task prefix",
                    "expected_title": expected_title,
                })
        elif provenance.operator == CONTRACT_REQUESTED_VS_HIDDEN_COMPANION_FILE:
            filename_match = re.search(r"`([^`]+)`", provenance.clean_requirement)
            expected_filename = filename_match.group(1) if filename_match else ""
            if not expected_filename or expected_filename not in visible_contract:
                mismatches.append({
                    "source_item_id": provenance.source_item_id,
                    "operator": provenance.operator,
                    "reason": "clean companion support is absent from production contract prefix",
                    "expected_filename": expected_filename,
                })
        elif provenance.operator == INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL:
            instruction = (
                "Also include an accurate count of the allowed visible input source "
                "files in the requested output."
            )
            if instruction not in visible_task:
                mismatches.append({
                    "source_item_id": provenance.source_item_id,
                    "operator": provenance.operator,
                    "reason": "clean count relevance is absent from production task prefix",
                })
        elif (
            provenance.operator
            == INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME
        ):
            instruction = (
                "Also identify the allowed visible input source files by filename in "
                "the requested output."
            )
            if instruction not in visible_task:
                mismatches.append({
                    "source_item_id": provenance.source_item_id,
                    "operator": provenance.operator,
                    "reason": "clean filename relevance is absent from production task prefix",
                })
        visible_inventory_lines = [
            line for line in bundle.inventory_text.splitlines()
            if line.startswith("- logical=")
        ]
        if len(visible_inventory_lines) != len(bundle.indexed_files):
            mismatches.append({
                "source_item_id": provenance.source_item_id,
                "operator": provenance.operator,
                "reason": "production prompt truncates or omits input inventory rows",
                "indexed_files": len(bundle.indexed_files),
                "visible_inventory_rows": len(visible_inventory_lines),
            })
            continue
        if provenance.operator == INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL:
            match = re.search(
                r"exactly\s+(\d+)\s+allowed visible input source files",
                provenance.clean_requirement,
                flags=re.I,
            )
            expected = int(match.group(1)) if match else None
            observed = len(bundle.indexed_files)
            rendered_match = re.search(
                r"^file_count=(\d+)$",
                bundle.inventory_text,
                flags=re.MULTILINE,
            )
            rendered = int(rendered_match.group(1)) if rendered_match else None
            if expected != observed or rendered != observed:
                mismatches.append({
                    "source_item_id": provenance.source_item_id,
                    "operator": provenance.operator,
                    "expected_count": expected,
                    "production_indexed_count": observed,
                    "rendered_inventory_count": rendered,
                })
        elif (
            provenance.operator
            == INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME
        ):
            match = re.search(r"`([^`]+)`", provenance.clean_requirement)
            expected_name = match.group(1) if match else ""
            if f"logical={expected_name} |" not in bundle.inventory_text:
                mismatches.append({
                    "source_item_id": provenance.source_item_id,
                    "operator": provenance.operator,
                    "expected_logical_name": expected_name,
                    "reason": "name absent from production input inventory",
                })
    if mismatches:
        raise RuntimeError(
            "synthetic gold diverges from production evidence view: "
            + json.dumps(mismatches[:5], ensure_ascii=False)
        )

    view_keys_by_source: dict[str, set[str]] = defaultdict(set)
    for view_key, view_items in items_by_view.items():
        for item in view_items:
            view_keys_by_source[source_by_item[item.item_id]].add(view_key)
    rows = []
    for source_id, view_keys in sorted(view_keys_by_source.items()):
        source_bundles = [bundle_by_view[key] for key in sorted(view_keys)]
        indexed_views = {tuple(bundle.indexed_files) for bundle in source_bundles}
        artifact_hashes = {
            bundle.artifact_manifest_sha256 for bundle in source_bundles
        }
        evidence_hashes = {bundle.sha256 for bundle in source_bundles}
        if len(indexed_views) != 1 or len(artifact_hashes) != 1:
            raise RuntimeError(
                f"production evidence views diverged for source {source_id}"
            )
        indexed_files = len(next(iter(indexed_views)))
        rows.append({
            "source_item_id": source_id,
            "evidence_views": len(source_bundles),
            "indexed_files": indexed_files,
            "blocked_files": sum(len(bundle.blocked_files) for bundle in source_bundles),
            "parse_failures": sorted({
                name for bundle in source_bundles for name in bundle.parse_failures
            }),
            "partial_files": sorted({
                name for bundle in source_bundles for name in bundle.partial_files
            }),
            "bundle_truncated": any(
                bundle.bundle_truncated for bundle in source_bundles
            ),
            "artifact_identity_failures": [
                failure
                for bundle in source_bundles
                for failure in bundle.artifact_identity_failures
            ],
            "actor_view_complete": all(
                bundle.actor_view_complete for bundle in source_bundles
            ),
            "input_inventory_complete": all(
                bundle.input_inventory_complete for bundle in source_bundles
            ),
            "inventory_absence_is_confirmation_eligible": all(
                bundle.inventory_absence_is_confirmation_eligible
                for bundle in source_bundles
            ),
            "artifact_manifest_sha256": next(iter(artifact_hashes)),
            "evidence_bundle_sha256": canonical_sha256(sorted(evidence_hashes)),
        })
    signature_payload = [
        {
            key: value for key, value in row.items()
            if key not in {"parse_failures", "partial_files"}
        }
        | {
            "parse_failures": sorted(row["parse_failures"]),
            "partial_files": sorted(row["partial_files"]),
        }
        for row in rows
    ]
    return {
        "schema_version": "1.0",
        "source_tasks": len(rows),
        "evidence_views": len(bundle_by_view),
        "indexed_files": sum(int(row["indexed_files"]) for row in rows),
        "blocked_files": blocked,
        "parse_failure_files": sum(len(row["parse_failures"]) for row in rows),
        "partial_files": sum(len(row["partial_files"]) for row in rows),
        "bundle_truncated_tasks": sum(
            bool(row["bundle_truncated"]) for row in rows
        ),
        "artifact_identity_failure_files": sum(
            len(row["artifact_identity_failures"]) for row in rows
        ),
        "actor_view_complete_tasks": sum(
            bool(row["actor_view_complete"]) for row in rows
        ),
        "input_inventory_complete_tasks": sum(
            bool(row["input_inventory_complete"]) for row in rows
        ),
        "inventory_confirmation_eligible_tasks": sum(
            bool(row["inventory_absence_is_confirmation_eligible"])
            for row in rows
        ),
        "objective_clean_supported_pairs": objective_clean_supported,
        "objective_mutant_unsupported_pairs": objective_mutant_unsupported,
        "objective_certified_pairs": objective_certified,
        "synthetic_gold_mismatches": 0,
        "signature": canonical_sha256(signature_payload),
        "per_source": rows,
    }


def _phase_client(
    config: Any, out_dir: Path, phase: str, *, cache_only: bool = False,
) -> LLMClient:
    phase_config = replace(
        config,
        cache_path=str(out_dir / f"{phase}_llm_cache.jsonl"),
        cache_only=cache_only,
    )
    if phase_config.dry_run:
        raise ValueError("dry_run model responses are forbidden in a scored challenge")
    return LLMClient(phase_config)


def logical_call_budget(
    *,
    pairs: int,
    verify: bool,
    phases: str,
    operational_passes: int = 1,
    max_retries: int = 1,
    objective_verifier_bypass: bool = False,
) -> dict[str, int]:
    clean = phases in {"clean", "both"}
    mutant = phases in {"mutant", "both"}
    scanners = pairs * (int(clean) + int(mutant))
    expected_verifiers = (
        pairs if verify and mutant and not objective_verifier_bypass else 0
    )
    maximum_verifiers = 0 if objective_verifier_bypass else scanners if verify else 0
    single_pass_upper = scanners + maximum_verifiers
    return {
        "scanner_calls": scanners,
        "expected_verifier_calls": expected_verifiers,
        "maximum_verifier_calls": maximum_verifiers,
        "objective_verifier_bypass": int(objective_verifier_bypass),
        "expected_calls": scanners + expected_verifiers,
        "single_pass_logical_call_upper_bound": single_pass_upper,
        "operational_passes": max(1, operational_passes),
        "configured_logical_call_upper_bound": (
            single_pass_upper * max(1, operational_passes)
        ),
        # Conservative transport budget.  Valid cached responses reduce this;
        # ``LLMClient`` has an outer malformed-JSON retry loop and an inner
        # transport retry loop, so their theoretical composition is squared.
        "configured_http_attempt_upper_bound": (
            single_pass_upper
            * max(1, operational_passes)
            * max(1, max_retries) ** 2
        ),
    }


def phase_health(expected_ids: set[str], decisions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(decisions)
    counts = Counter(str(row.get("item_id") or "") for row in rows)
    latest = {str(row.get("item_id") or ""): row for row in rows}
    missing = sorted(expected_ids - set(latest))
    duplicates = sum(max(0, counts[item_id] - 1) for item_id in expected_ids)
    extras = sum(count for item_id, count in counts.items() if item_id not in expected_ids)
    operational = sorted(
        item_id for item_id in expected_ids
        if item_id in latest and decision_has_operational_failure(latest[item_id])
    )
    return {
        "expected_items": len(expected_ids),
        "observed_items": len(expected_ids.intersection(latest)),
        "missing_items": len(missing),
        "operational_failure_items": len(operational),
        "duplicate_rows": duplicates,
        "extra_rows": extras,
        "complete": (
            not missing and not operational and duplicates == 0 and extras == 0
        ),
        "missing_item_ids": missing,
        "operational_failure_item_ids": operational,
    }


class ProgressPrinter:
    def __init__(self, phase: str, total: int) -> None:
        self.phase = phase
        self.total = total
        self.completed = 0
        self.started = time.monotonic()

    def __call__(self, event: Mapping[str, Any]) -> None:
        self.completed += 1
        if (
            self.completed == 1
            or self.completed == self.total
            or self.completed % 10 == 0
            or event.get("operational_failure")
        ):
            print(
                f"[{self.phase}] attempts={self.completed} "
                f"label={event.get('label')} "
                f"operational={bool(event.get('operational_failure'))} "
                f"elapsed={time.monotonic() - self.started:.1f}s",
                flush=True,
            )


def strict_success(score: Mapping[str, Any]) -> bool:
    pairs = int(score.get("pairs", 0))
    return bool(
        pairs
        and score.get("mutant_unsupported_hits") == pairs
        and score.get("paired_discriminated") == pairs
        and score.get("strict_paired_discriminated") == pairs
        and score.get("clean_false_alarms") == 0
        and score.get("uncertain_decisions") == 0
        and score.get("operational_failure_decisions") == 0
        and score.get("extra_decision_count") == 0
        and score.get("duplicate_decision_count") == 0
    )


def implementation_signature() -> str:
    paths = (
        REPO / "benchcore" / "workspace_semantic_challenge.py",
        REPO / "benchcore" / "workspace_grounding.py",
        REPO / "benchcore" / "workspace_invariants.py",
        REPO / "benchcore" / "file_reader.py",
        REPO / "benchcore" / "loader.py",
        REPO / "benchcore" / "field_mapping.py",
        REPO / "benchcore" / "schema.py",
        REPO / "benchcore" / "llm_client.py",
        Path(__file__).resolve(),
    )
    return canonical_sha256({path.relative_to(REPO).as_posix(): file_sha256(path) for path in paths})


def _write_or_validate_run_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            raise ValueError(f"existing run manifest is not an object: {path}")
        if existing.get("run_signature") != manifest.get("run_signature"):
            raise RuntimeError(
                f"resume signature mismatch in {path}; use a new --out-dir rather than "
                "mixing snapshots, prompts, models, or challenge definitions"
            )
        return
    value = {
        **dict(manifest),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json_atomic(path, value)


@contextmanager
def exclusive_run_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another semantic challenge process owns {path}") from exc
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _without_decisions(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: row for key, row in value.items() if key != "decisions"}


def write_jsonl_atomic(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    text = "".join(
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows
    )
    write_text_atomic(path, text)


def write_json_atomic(path: Path, value: Any) -> None:
    write_text_atomic(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def git_metadata() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


if __name__ == "__main__":
    raise SystemExit(main())
