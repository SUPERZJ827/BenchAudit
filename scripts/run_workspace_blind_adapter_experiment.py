#!/usr/bin/env python3
"""Blind-schema adaptation experiment over Workspace-Bench Full-388.

This experiment is intentionally distinct from the opaque given-spec
conformance challenge.  It supports separately fingerprinted semantic schema
variants so that a consumed live holdout is never silently recycled as a new
blind claim:

* derived canonical fields are removed from the public input;
* one semantically legible nested schema uses names absent from BenchAudit's
  deterministic alias tables;
* the public challenge, sealed external reference, and offline oracle spec are
  physically separate artifacts;
* discovery and application use :mod:`benchcore.adaptation` exclusively; and
* a live mode delegates discovery to the production ``auto-adapt`` command.

The external reference is consumed only by the controller's final sealed gate.
It is never included in the schema profile or LLM prompt.  Offline mode exists
only as an interpreter/scorer regression and must not be reported as blind
discovery performance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Keep the documented shebang/direct invocation usable without requiring an
# editable install.  Module invocation (``python -m scripts...``) remains the
# preferred reproducible form.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchcore.adaptation import (
    ADAPTER_SCHEMA_VERSION,
    AdapterController,
    AdapterSpec,
    StaticAdapterSynthesizer,
    adapt_rows,
    analyze_component_gaps,
    build_schema_profile,
    evaluate_adapter,
    mapping_for_adapted_rows,
)
from benchcore.adaptation.models import canonical_json, canonical_sha256
from benchcore.adaptation.synthesis import deterministic_adapter_candidate
from benchcore.cli import main as benchcore_main
from benchcore.field_mapping import (
    ALIAS_FIELDS,
    CHOICE_FIELDS,
    CONTEXT_FIELDS,
    EVALUATOR_FIELDS,
    GOLD_FIELDS,
    ID_FIELDS,
    METADATA_FIELDS,
    OUTPUT_FIELDS,
    TASK_FIELDS,
)
from benchcore.loader import build_items, load_rows
from benchcore.schema import Violation
from benchcore.workspace_invariants import (
    WorkspaceArtifactInvariantChecker,
    parse_jsonish,
)


REPO = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPO / "datasets" / "workspacebench" / "full.jsonl"
DEFAULT_OUT_DIR = REPO / "reports" / "workspace_blind_adapter_full388_20260715"
DEFAULT_SCHEMA_VARIANT = "semantic_v1"
SCHEMA_VARIANTS = (DEFAULT_SCHEMA_VARIANT, "semantic_v2")
DEFAULT_FULL_ROOT = Path(
    "/home/zhoujun/.cache/huggingface/hub/"
    "datasets--Workspace-Bench--Workspace-Bench"
)
PINNED_FULL_SHA256 = (
    "2e3d8fd1f5a741b9e6b73ebab9ce23e26ce054527b4f3477de8fdd950aad9dbe"
)

BUILD_MANIFEST_SCHEMA = "workspace-blind-adapter-build-v1"
REFERENCE_JOIN_SCHEMA = "workspace-blind-adapter-reference-join-v1"
SCORE_SCHEMA = "workspace-blind-adapter-score-v1"
LIVE_CONSUMPTION_SCHEMA = "workspace-blind-live-consumption-v1"
LIVE_CONSUMPTION_REGISTRY = (
    REPO / "reports" / ".workspace_blind_live_consumption_registry"
)

# Full-388 has no meaningful choices/gold/aliases.  Every applicable registered
# Workspace target is present in every sealed reference row; inapplicable core
# targets are named explicitly rather than fabricated.
REFERENCE_TARGETS = frozenset({
    "item_id",
    "task",
    "context",
    "output_contract",
    "evaluator",
    "metadata",
    "rubrics",
    "rubric_types",
    "output_files",
    "input_files",
    "data_manifest",
    "file_dep_graph",
    "tested_capabilities",
})
INAPPLICABLE_CORE_TARGETS = frozenset({"choices", "gold", "aliases"})

PUBLIC_CHALLENGE_ROOTS = {
    "semantic_v1": frozenset({
        "identity_record",
        "assignment_brief",
        "grading_blueprint",
        "delivery_plan",
        "workspace_evidence",
        "ability_profile",
        "benchmark_annotations",
    }),
    "semantic_v2": frozenset({
        "unit_identity",
        "work_request",
        "evaluation_rules",
        "deliverables",
        "evidence_bundle",
        "capability_declaration",
        "record_attributes",
    }),
}

PUBLIC_CHALLENGE_KEYS = {
    "semantic_v1": frozenset({
        "sequence_number",
        "request_text",
        "requirement_statements",
        "requirement_classes",
        "artifact_names",
        "source_catalog",
        "dependency_links",
        "materialized_paths",
        "skill_tags",
        "locale_code",
        "role_description",
        "variant_note",
    }),
    "semantic_v2": frozenset({
        "serial_index",
        "objective_text",
        "check_items",
        "check_categories",
        "expected_artifacts",
        "asset_inventory",
        "lineage_edges",
        "resolved_asset_paths",
        "features",
        "language_tag",
        "actor_role",
        "difficulty_band",
    }),
}

SCHEMA_FIELD_PATHS = {
    "semantic_v1": {
        "absolute_id": ("identity_record", "sequence_number"),
        "task": ("assignment_brief", "request_text"),
        "rubrics": ("grading_blueprint", "requirement_statements"),
        "rubric_types": ("grading_blueprint", "requirement_classes"),
        "output_files": ("delivery_plan", "artifact_names"),
        "data_manifest": ("workspace_evidence", "source_catalog"),
        "file_dep_graph": ("workspace_evidence", "dependency_links"),
        "input_files": ("workspace_evidence", "materialized_paths"),
        "tested_capabilities": ("ability_profile", "skill_tags"),
        "language": ("benchmark_annotations", "locale_code"),
        "persona": ("benchmark_annotations", "role_description"),
        "task_diff": ("benchmark_annotations", "variant_note"),
    },
    "semantic_v2": {
        "absolute_id": ("unit_identity", "serial_index"),
        "task": ("work_request", "objective_text"),
        "rubrics": ("evaluation_rules", "check_items"),
        "rubric_types": ("evaluation_rules", "check_categories"),
        "output_files": ("deliverables", "expected_artifacts"),
        "data_manifest": ("evidence_bundle", "asset_inventory"),
        "file_dep_graph": ("evidence_bundle", "lineage_edges"),
        "input_files": ("evidence_bundle", "resolved_asset_paths"),
        "tested_capabilities": ("capability_declaration", "features"),
        "language": ("record_attributes", "language_tag"),
        "persona": ("record_attributes", "actor_role"),
        "task_diff": ("record_attributes", "difficulty_band"),
    },
}

KNOWN_ALIAS_LEAVES = frozenset(
    value.casefold()
    for values in (
        ID_FIELDS,
        TASK_FIELDS,
        CONTEXT_FIELDS,
        CHOICE_FIELDS,
        GOLD_FIELDS,
        ALIAS_FIELDS,
        OUTPUT_FIELDS,
        EVALUATOR_FIELDS,
        METADATA_FIELDS,
    )
    for value in values
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_list(value: Any, *, field: str) -> list[Any]:
    parsed = parse_jsonish(value, None)
    if not isinstance(parsed, list):
        raise ValueError(f"Workspace source field {field!r} must decode to a list")
    return copy.deepcopy(parsed)


def _validated_schema_variant(schema_variant: str) -> str:
    if schema_variant not in SCHEMA_VARIANTS:
        raise ValueError(
            f"unsupported schema variant {schema_variant!r}; expected one of "
            f"{list(SCHEMA_VARIANTS)!r}"
        )
    return schema_variant


def transform_source_row(
    source: Mapping[str, Any],
    *,
    schema_variant: str = DEFAULT_SCHEMA_VARIANT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return public unknown-schema input and its evaluator-only reference."""
    schema_variant = _validated_schema_variant(schema_variant)
    required = {
        "absolute_id", "task", "rubrics", "rubric_types", "output_files",
        "input_files", "data_manifest", "file_dep_graph", "tested_capabilities",
        "language", "persona", "task_diff", "item_id",
    }
    missing = required - set(source)
    if missing:
        raise ValueError(f"Workspace source row is missing fields: {sorted(missing)}")

    rubrics = _json_list(source["rubrics"], field="rubrics")
    rubric_types = _json_list(source["rubric_types"], field="rubric_types")
    output_files = _json_list(source["output_files"], field="output_files")
    input_files = _json_list(source["input_files"], field="input_files")
    data_manifest = _json_list(source["data_manifest"], field="data_manifest")
    file_dep_graph = _json_list(source["file_dep_graph"], field="file_dep_graph")
    tested_capabilities = _json_list(
        source["tested_capabilities"], field="tested_capabilities",
    )
    absolute_id = source["absolute_id"]
    task = source["task"]

    if schema_variant == "semantic_v1":
        challenge = {
            "identity_record": {"sequence_number": absolute_id},
            "assignment_brief": {"request_text": task},
            "grading_blueprint": {
                "requirement_statements": rubrics,
                "requirement_classes": rubric_types,
            },
            "delivery_plan": {"artifact_names": output_files},
            "workspace_evidence": {
                "source_catalog": data_manifest,
                "dependency_links": file_dep_graph,
                "materialized_paths": input_files,
            },
            "ability_profile": {"skill_tags": tested_capabilities},
            "benchmark_annotations": {
                "locale_code": source["language"],
                "role_description": source["persona"],
                "variant_note": source["task_diff"],
            },
        }
    else:
        challenge = {
            "unit_identity": {"serial_index": absolute_id},
            "work_request": {"objective_text": task},
            "evaluation_rules": {
                "check_items": rubrics,
                "check_categories": rubric_types,
            },
            "deliverables": {"expected_artifacts": output_files},
            "evidence_bundle": {
                "asset_inventory": data_manifest,
                "lineage_edges": file_dep_graph,
                "resolved_asset_paths": input_files,
            },
            "capability_declaration": {"features": tested_capabilities},
            "record_attributes": {
                "language_tag": source["language"],
                "actor_role": source["persona"],
                "difficulty_band": source["task_diff"],
            },
        }
    expected_item_id = f"workspacebench-{absolute_id}"
    if str(source["item_id"]) != expected_item_id:
        raise ValueError(
            f"item_id {source['item_id']!r} is inconsistent with absolute_id "
            f"{absolute_id!r}"
        )
    reference = {
        "item_id": expected_item_id,
        "task": task,
        "rubrics": rubrics,
        "rubric_types": rubric_types,
        "output_files": output_files,
        "input_files": input_files,
        "data_manifest": data_manifest,
        "file_dep_graph": file_dep_graph,
        "tested_capabilities": tested_capabilities,
        "context": {
            "data_manifest": data_manifest,
            "file_dep_graph": file_dep_graph,
            "input_files": input_files,
        },
        "evaluator": {
            "type": "workspacebench_rubric",
            "rubrics": rubrics,
            "rubric_types": rubric_types,
        },
        "output_contract": {"required_files": output_files},
        "metadata": {
            "absolute_id": absolute_id,
            "language": source["language"],
            "persona": source["persona"],
            "task_diff": source["task_diff"],
        },
    }
    if set(reference) != REFERENCE_TARGETS:
        raise RuntimeError("sealed reference target set drifted")
    assert_public_schema_is_blind(challenge, schema_variant=schema_variant)
    return challenge, reference


def assert_public_schema_is_blind(
    row: Mapping[str, Any],
    *,
    schema_variant: str = DEFAULT_SCHEMA_VARIANT,
) -> None:
    """Ensure no canonical field, known alias leaf, or sidecar label leaked."""
    schema_variant = _validated_schema_variant(schema_variant)
    observed_leaves: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ValueError("public schema keys must be strings")
                observed_leaves.add(key.casefold())
                visit(child)
        elif isinstance(value, list):
            for child in value:
                # Manifest and dependency entries are payload protocol, not
                # schema-discovery envelope fields.  Their keys are intentionally
                # preserved so the downstream checker can replay them.
                if not isinstance(child, Mapping):
                    visit(child)

    visit(row)
    forbidden = (
        REFERENCE_TARGETS
        | INAPPLICABLE_CORE_TARGETS
        | {"canonical_reference", "reference_row", "adapter_answer", "field_mapping"}
    )
    leaked = observed_leaves & {value.casefold() for value in forbidden}
    if leaked:
        raise ValueError(f"canonical/reference key leaked into public schema: {sorted(leaked)}")
    envelope_leaves = {
        key.casefold()
        for parent in row.values()
        if isinstance(parent, Mapping)
        for key in parent
    }
    alias_leaks = envelope_leaves & KNOWN_ALIAS_LEAVES
    if alias_leaks:
        raise ValueError(
            f"known deterministic alias leaked into public schema: {sorted(alias_leaks)}"
        )
    expected_roots = PUBLIC_CHALLENGE_ROOTS[schema_variant]
    if set(row) != expected_roots:
        missing_roots = sorted(expected_roots - set(row))
        extra_roots = sorted(set(row) - expected_roots)
        raise ValueError(
            "public semantic root set differs from its declared variant: "
            f"missing={missing_roots}, extra={extra_roots}"
        )
    expected_leaves = {
        value.casefold() for value in PUBLIC_CHALLENGE_KEYS[schema_variant]
    }
    missing = expected_leaves - envelope_leaves
    if missing:
        raise ValueError(f"public semantic fields are missing: {sorted(missing)}")
    unexpected = envelope_leaves - expected_leaves
    if unexpected:
        raise ValueError(f"unexpected public semantic fields: {sorted(unexpected)}")


def oracle_adapter_spec(
    rows: list[dict[str, Any]],
    *,
    schema_variant: str = DEFAULT_SCHEMA_VARIANT,
) -> AdapterSpec:
    """Offline-only gold spec expressed in the production trusted DSL."""
    schema_variant = _validated_schema_variant(schema_variant)
    paths = SCHEMA_FIELD_PATHS[schema_variant]
    fingerprint = build_schema_profile(rows, max_examples_per_path=0).fingerprint
    bindings = [
        {
            "target": "item_id",
            "template": {
                "format": "workspacebench-{value}",
                "path": list(paths["absolute_id"]),
                "transforms": ["stringify"],
            },
            "transforms": [],
            "required": True,
        },
        {
            "target": "task",
            "path": list(paths["task"]),
            "transforms": ["strip"],
            "required": True,
        },
        {
            "target": "rubrics",
            "path": list(paths["rubrics"]),
            "transforms": [],
            "required": True,
        },
        {
            "target": "rubric_types",
            "path": list(paths["rubric_types"]),
            "transforms": [],
            "required": True,
        },
        {
            "target": "output_files",
            "path": list(paths["output_files"]),
            "transforms": [],
            "required": True,
        },
        {
            "target": "input_files",
            "path": list(paths["input_files"]),
            "transforms": [],
            "required": True,
        },
        {
            "target": "data_manifest",
            "path": list(paths["data_manifest"]),
            "transforms": [],
            "required": True,
        },
        {
            "target": "file_dep_graph",
            "path": list(paths["file_dep_graph"]),
            "transforms": [],
            "required": True,
        },
        {
            "target": "tested_capabilities",
            "path": list(paths["tested_capabilities"]),
            "transforms": [],
            "required": True,
        },
        {
            "target": "context",
            "object": [
                {
                    "key": "data_manifest",
                    "path": list(paths["data_manifest"]),
                    "transforms": [],
                    "required": True,
                },
                {
                    "key": "file_dep_graph",
                    "path": list(paths["file_dep_graph"]),
                    "transforms": [],
                    "required": True,
                },
                {
                    "key": "input_files",
                    "path": list(paths["input_files"]),
                    "transforms": [],
                    "required": True,
                },
            ],
            "transforms": [],
            "required": True,
        },
        {
            "target": "evaluator",
            "object": [
                {
                    "key": "type",
                    "literal": "workspacebench_rubric",
                    "transforms": [],
                    "required": True,
                },
                {
                    "key": "rubrics",
                    "path": list(paths["rubrics"]),
                    "transforms": [],
                    "required": True,
                },
                {
                    "key": "rubric_types",
                    "path": list(paths["rubric_types"]),
                    "transforms": [],
                    "required": True,
                },
            ],
            "transforms": [],
            "required": True,
        },
        {
            "target": "output_contract",
            "object": [{
                "key": "required_files",
                "path": list(paths["output_files"]),
                "transforms": [],
                "required": True,
            }],
            "transforms": [],
            "required": True,
        },
        {
            "target": "metadata",
            "object": [
                {
                    "key": "absolute_id",
                    "path": list(paths["absolute_id"]),
                    "transforms": [],
                    "required": True,
                },
                {
                    "key": "language",
                    "path": list(paths["language"]),
                    "transforms": [],
                    "required": True,
                },
                {
                    "key": "persona",
                    "path": list(paths["persona"]),
                    "transforms": [],
                    "required": True,
                },
                {
                    "key": "task_diff",
                    "path": list(paths["task_diff"]),
                    "transforms": [],
                    "required": True,
                },
            ],
            "transforms": [],
            "required": True,
        },
    ]
    spec = AdapterSpec.from_dict({
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter_id": (
            "offline_workspace_blind_full388_oracle"
            if schema_variant == DEFAULT_SCHEMA_VARIANT
            else f"offline_workspace_blind_full388_oracle_{schema_variant}"
        ),
        "version": 1,
        "family": "workspacebench",
        "schema_fingerprint": fingerprint,
        "description": (
            "Offline evaluator-only oracle for the Workspace blind-schema "
            f"experiment ({schema_variant}); never exposed to live discovery."
        ),
        "bindings": bindings,
    })
    if spec.targets != REFERENCE_TARGETS:
        raise RuntimeError("offline oracle does not cover every applicable target")
    return spec


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, value: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _live_consumption_dir(out_dir: Path) -> Path:
    return out_dir.expanduser().resolve() / "sealed_reference" / "live_consumption"


def _registry_consumption_dir(holdout_fingerprint: str) -> Path:
    if not holdout_fingerprint or any(
        character not in "0123456789abcdef" for character in holdout_fingerprint
    ):
        raise ValueError("holdout fingerprint is not a lowercase hexadecimal digest")
    return LIVE_CONSUMPTION_REGISTRY.expanduser().resolve() / holdout_fingerprint


def _read_consumption_claim(claim_dir: Path) -> dict[str, Any] | None:
    if not claim_dir.exists():
        return None
    if claim_dir.is_symlink() or not claim_dir.is_dir():
        raise ValueError(f"live-consumption claim is not a directory: {claim_dir}")
    receipt_path = claim_dir / "receipt.json"
    if not receipt_path.is_file():
        # Directory creation is the atomic consume operation.  A crash before
        # receipt persistence must still make the holdout permanently spent.
        return {
            "schema_version": LIVE_CONSUMPTION_SCHEMA,
            "state": "claimed_receipt_unavailable",
            "failure_counts_as_consumed": True,
        }
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"live-consumption receipt is unreadable: {receipt_path}") from exc
    if receipt.get("schema_version") != LIVE_CONSUMPTION_SCHEMA:
        raise ValueError("unsupported live-consumption receipt schema")
    return receipt


def _read_live_consumption(
    out_dir: Path,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    local = _read_consumption_claim(_live_consumption_dir(out_dir))
    fingerprint = manifest.get("holdout_fingerprint") if manifest is not None else None
    registry = (
        _read_consumption_claim(_registry_consumption_dir(fingerprint))
        if isinstance(fingerprint, str) and fingerprint
        else None
    )
    # The content-addressed registry is authoritative across output-directory
    # copies.  The per-experiment receipt is a portable audit mirror.
    return registry if registry is not None else local


def _claim_live_consumption(
    out_dir: Path,
    manifest: Mapping[str, Any],
    *,
    live_dir: Path,
    claim_source: str,
    started_at_utc: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> tuple[tuple[Path, Path], dict[str, Any]]:
    """Atomically and irreversibly consume one fingerprint for live discovery."""
    out_dir = out_dir.expanduser().resolve()
    holdout_fingerprint = manifest.get("holdout_fingerprint")
    if not isinstance(holdout_fingerprint, str) or not holdout_fingerprint:
        raise ValueError(
            "live discovery requires a fingerprint-bound holdout; rebuild into "
            "a fresh directory before attempting live synthesis"
        )
    local_claim_dir = _live_consumption_dir(out_dir)
    if not local_claim_dir.parent.is_dir():
        raise ValueError("sealed-reference directory is missing")
    registry_root = LIVE_CONSUMPTION_REGISTRY.expanduser().resolve()
    registry_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(registry_root, 0o700)
    registry_claim_dir = _registry_consumption_dir(holdout_fingerprint)
    try:
        os.mkdir(registry_claim_dir, mode=0o700)
        _fsync_directory(registry_root)
    except FileExistsError as exc:
        previous = _read_consumption_claim(registry_claim_dir) or {}
        raise RuntimeError(
            "blind live holdout is already consumed; no second attempt is "
            f"permitted (state={previous.get('state')!r}, "
            f"run_id={previous.get('run_id')!r})"
        ) from exc
    try:
        os.mkdir(local_claim_dir, mode=0o700)
        _fsync_directory(local_claim_dir.parent)
    except FileExistsError as exc:
        # The global fingerprint claim has already made this attempt consumed.
        # Keep it even if the local mirror unexpectedly existed.
        raise RuntimeError("local live-consumption receipt already exists") from exc

    receipt = {
        "schema_version": LIVE_CONSUMPTION_SCHEMA,
        "state": "attempt_started",
        "claim_source": claim_source,
        "started_at_utc": started_at_utc or datetime.now(timezone.utc).isoformat(),
        "holdout_fingerprint": holdout_fingerprint,
        "schema_variant": manifest.get("schema_variant", DEFAULT_SCHEMA_VARIANT),
        "public_challenge_sha256": manifest["public_challenge"]["sha256"],
        "sealed_reference_sha256": manifest["sealed_reference"]["sha256"],
        "build_manifest_sha256": file_sha256(out_dir / "build_manifest.json"),
        "implementation_sha256_at_build": manifest["implementation"]["sha256"],
        "live_dir": str(live_dir.expanduser().resolve()),
        "blind_discovery_claim_eligible": True,
        "failure_counts_as_consumed": True,
        "registry_claim_dir": str(registry_claim_dir),
        "local_claim_dir": str(local_claim_dir),
    }
    if extra:
        receipt.update(copy.deepcopy(dict(extra)))
    receipt_paths = (
        registry_claim_dir / "receipt.json",
        local_claim_dir / "receipt.json",
    )
    try:
        for receipt_path in receipt_paths:
            _write_json(receipt_path, receipt)
            os.chmod(receipt_path, 0o600)
            _fsync_directory(receipt_path.parent)
    except BaseException:
        # Never remove either claim: directory creation is the durable tombstone.
        raise
    return receipt_paths, receipt


def _update_live_consumption(
    receipt_paths: Sequence[Path],
    receipt: Mapping[str, Any],
    **updates: Any,
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(receipt))
    updated.update(updates)
    for receipt_path in receipt_paths:
        _write_json(receipt_path, updated)
        os.chmod(receipt_path, 0o600)
        _fsync_directory(receipt_path.parent)
    return updated


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(canonical_json(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _holdout_fingerprint(
    *,
    schema_variant: str,
    source_sha256: str,
    schema_fingerprint: str,
    public_rows: Sequence[Mapping[str, Any]],
    references: Sequence[Mapping[str, Any]],
) -> str:
    """Bind a holdout identity to its variant, source, public view, and oracle."""
    return canonical_sha256({
        "schema_variant": _validated_schema_variant(schema_variant),
        "source_sha256": source_sha256,
        "schema_fingerprint": schema_fingerprint,
        "public_content_sha256": canonical_sha256(public_rows),
        "reference_content_sha256": canonical_sha256(references),
    })


def build_experiment(
    source_path: Path,
    out_dir: Path,
    *,
    expected_rows: int | None = None,
    schema_variant: str = DEFAULT_SCHEMA_VARIANT,
) -> dict[str, Any]:
    schema_variant = _validated_schema_variant(schema_variant)
    source_path = source_path.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    prior_consumption = _read_live_consumption(out_dir)
    if prior_consumption is not None:
        raise RuntimeError(
            "refusing to rebuild a consumed blind holdout; construct a new "
            f"schema variant/output directory instead (state="
            f"{prior_consumption.get('state')!r}, "
            f"run_id={prior_consumption.get('run_id')!r})"
        )
    existing_manifest_path = out_dir / "build_manifest.json"
    if existing_manifest_path.exists():
        try:
            existing_manifest = json.loads(
                existing_manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"refusing to overwrite unreadable build manifest: "
                f"{existing_manifest_path}"
            ) from exc
        existing_variant = existing_manifest.get(
            "schema_variant", DEFAULT_SCHEMA_VARIANT,
        )
        if existing_variant != schema_variant:
            raise ValueError(
                "refusing to overwrite a holdout with a different schema "
                f"variant: existing={existing_variant!r}, "
                f"requested={schema_variant!r}"
            )
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    source_sha_start = file_sha256(source_path)
    implementation_start = implementation_manifest()
    rows = load_rows(source_path)
    if expected_rows is not None and len(rows) != expected_rows:
        raise ValueError(f"expected {expected_rows} rows, observed {len(rows)}")
    public_rows: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    for index, source in enumerate(rows):
        public, reference = transform_source_row(
            source, schema_variant=schema_variant,
        )
        public_rows.append(public)
        references.append(reference)
        joins.append({
            "row_index": index,
            "source_sha256": canonical_sha256(source),
            "public_sha256": canonical_sha256(public),
            "reference_sha256": canonical_sha256(reference),
        })
    profile = build_schema_profile(public_rows)
    deterministic = deterministic_adapter_candidate(
        public_rows, profile, family="workspacebench",
    )
    if deterministic is not None:
        raise RuntimeError(
            "blind challenge unexpectedly matches deterministic alias inference"
        )
    holdout_fingerprint = _holdout_fingerprint(
        schema_variant=schema_variant,
        source_sha256=source_sha_start,
        schema_fingerprint=profile.fingerprint,
        public_rows=public_rows,
        references=references,
    )
    registry_consumption = _read_consumption_claim(
        _registry_consumption_dir(holdout_fingerprint)
    )
    if registry_consumption is not None:
        raise RuntimeError(
            "refusing to rebuild a fingerprint that has already been consumed "
            f"by live discovery (state={registry_consumption.get('state')!r}, "
            f"run_id={registry_consumption.get('run_id')!r})"
        )

    challenge_path = out_dir / "public_challenge" / "challenge.jsonl"
    reference_path = out_dir / "sealed_reference" / "reference.jsonl"
    join_path = out_dir / "sealed_reference" / "join_manifest.json"
    _write_jsonl(challenge_path, public_rows)
    _write_jsonl(reference_path, references)
    _write_json(join_path, {
        "schema_version": REFERENCE_JOIN_SCHEMA,
        "schema_variant": schema_variant,
        "holdout_fingerprint": holdout_fingerprint,
        "rows": len(rows),
        "joins": joins,
    })

    source_sha_end = file_sha256(source_path)
    implementation_end = implementation_manifest()
    if source_sha_start != source_sha_end:
        raise RuntimeError("source dataset changed while the blind challenge was built")
    if implementation_start["sha256"] != implementation_end["sha256"]:
        raise RuntimeError("adaptation implementation changed during challenge build")
    manifest = {
        "schema_version": BUILD_MANIFEST_SCHEMA,
        "schema_variant": schema_variant,
        "holdout_fingerprint": holdout_fingerprint,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(source_path),
            "rows": len(rows),
            "sha256": source_sha_start,
            "hash_end_check": {
                "passed": True,
                "expected": source_sha_start,
                "observed": source_sha_end,
            },
        },
        "public_challenge": {
            "path": str(challenge_path.relative_to(out_dir)),
            "sha256": file_sha256(challenge_path),
            "schema_fingerprint": profile.fingerprint,
            "schema_variant": schema_variant,
            "holdout_fingerprint": holdout_fingerprint,
            "deterministic_alias_candidate": False,
            "contains_reference": False,
            "contains_adapter_spec": False,
        },
        "sealed_reference": {
            "path": str(reference_path.relative_to(out_dir)),
            "sha256": file_sha256(reference_path),
            "schema_variant": schema_variant,
            "holdout_fingerprint": holdout_fingerprint,
            "targets": sorted(REFERENCE_TARGETS),
            "inapplicable_core_targets": sorted(INAPPLICABLE_CORE_TARGETS),
            "join_manifest": str(join_path.relative_to(out_dir)),
            "join_manifest_sha256": file_sha256(join_path),
            "llm_visible": False,
        },
        "implementation": implementation_start,
        "implementation_hash_end_check": {
            "passed": True,
            "expected": implementation_start["sha256"],
            "observed": implementation_end["sha256"],
        },
    }
    _write_json(out_dir / "build_manifest.json", manifest)
    return manifest


def _resolve_within(root: Path, relative: str) -> Path:
    root = root.expanduser().resolve()
    path = (root / relative).resolve()
    if path != root and not path.is_relative_to(root):
        raise ValueError(f"manifest path escapes experiment directory: {relative!r}")
    return path


def load_experiment(out_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    out_dir = out_dir.expanduser().resolve()
    manifest_path = out_dir / "build_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != BUILD_MANIFEST_SCHEMA:
        raise ValueError("unsupported blind adapter build manifest")
    schema_variant = _validated_schema_variant(
        manifest.get("schema_variant", DEFAULT_SCHEMA_VARIANT)
    )
    for section_name in ("public_challenge", "sealed_reference"):
        section_variant = manifest.get(section_name, {}).get(
            "schema_variant", schema_variant,
        )
        if section_variant != schema_variant:
            raise ValueError(
                f"{section_name} schema variant disagrees with build manifest"
            )
    challenge_path = _resolve_within(
        out_dir, manifest["public_challenge"]["path"],
    )
    reference_path = _resolve_within(
        out_dir, manifest["sealed_reference"]["path"],
    )
    join_path = _resolve_within(
        out_dir, manifest["sealed_reference"]["join_manifest"],
    )
    expected_hashes = {
        challenge_path: manifest["public_challenge"]["sha256"],
        reference_path: manifest["sealed_reference"]["sha256"],
        join_path: manifest["sealed_reference"]["join_manifest_sha256"],
    }
    for path, expected in expected_hashes.items():
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"manifest-bound artifact changed: {path}")
    public_rows = load_rows(challenge_path)
    references = load_rows(reference_path)
    join = json.loads(join_path.read_text(encoding="utf-8"))
    if join.get("schema_version") != REFERENCE_JOIN_SCHEMA:
        raise ValueError("unsupported sealed reference join manifest")
    if join.get("schema_variant", DEFAULT_SCHEMA_VARIANT) != schema_variant:
        raise ValueError("sealed reference join schema variant mismatch")
    if len(public_rows) != len(references) or len(public_rows) != join.get("rows"):
        raise ValueError("challenge/reference/join row counts differ")
    join_rows = join.get("joins")
    if not isinstance(join_rows, list) or len(join_rows) != len(public_rows):
        raise ValueError("sealed reference join manifest is malformed")
    for index, (public, reference, binding) in enumerate(zip(
        public_rows, references, join_rows, strict=True,
    )):
        if not isinstance(binding, dict) or binding.get("row_index") != index:
            raise ValueError(f"invalid sealed join at row {index}")
        if canonical_sha256(public) != binding.get("public_sha256"):
            raise ValueError(f"public challenge digest mismatch at row {index}")
        if canonical_sha256(reference) != binding.get("reference_sha256"):
            raise ValueError(f"sealed reference digest mismatch at row {index}")
        if set(reference) != REFERENCE_TARGETS:
            raise ValueError(f"sealed reference target mismatch at row {index}")
        assert_public_schema_is_blind(public, schema_variant=schema_variant)
    profile = build_schema_profile(public_rows, max_examples_per_path=0)
    if profile.fingerprint != manifest["public_challenge"]["schema_fingerprint"]:
        raise ValueError("public challenge schema fingerprint changed")
    declared_holdout = manifest.get("holdout_fingerprint")
    if declared_holdout is None and schema_variant != DEFAULT_SCHEMA_VARIANT:
        raise ValueError("non-default holdout is missing its bound fingerprint")
    if declared_holdout is not None:
        observed_holdout = _holdout_fingerprint(
            schema_variant=schema_variant,
            source_sha256=manifest["source"]["sha256"],
            schema_fingerprint=profile.fingerprint,
            public_rows=public_rows,
            references=references,
        )
        if observed_holdout != declared_holdout:
            raise ValueError("holdout fingerprint changed")
        bound_fingerprints = {
            manifest["public_challenge"].get("holdout_fingerprint"),
            manifest["sealed_reference"].get("holdout_fingerprint"),
            join.get("holdout_fingerprint"),
        }
        if bound_fingerprints != {declared_holdout}:
            raise ValueError("holdout artifact fingerprints disagree")
    if deterministic_adapter_candidate(
        public_rows, profile, family="workspacebench",
    ) is not None:
        raise ValueError("public challenge is no longer blind to deterministic aliases")
    return public_rows, references, manifest


def run_offline(
    out_dir: Path,
    *,
    allowed_roots: Sequence[Path],
    workers: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    public_rows, references, manifest = load_experiment(out_dir)
    schema_variant = manifest.get("schema_variant", DEFAULT_SCHEMA_VARIANT)
    profile = build_schema_profile(public_rows)
    spec = oracle_adapter_spec(public_rows, schema_variant=schema_variant)
    oracle_dir = out_dir / "offline_oracle"
    spec_path = oracle_dir / "oracle_adapter.json"
    run_path = oracle_dir / "run.json"
    _write_json(spec_path, spec.to_dict())
    run = AdapterController(
        StaticAdapterSynthesizer([spec]),
        max_rounds=1,
        max_candidates_per_round=1,
        max_total_candidates=1,
    ).run(
        public_rows,
        profile,
        family="workspacebench",
        references=references,
    )
    payload = run.to_dict()
    payload["synthesis"] = {
        "mode": "offline_oracle_regression",
        "schema_variant": schema_variant,
        "blind_discovery_claim_eligible": False,
        "oracle_spec_path": str(spec_path.resolve()),
        "remote_data_egress": False,
    }
    _write_json(run_path, payload)
    if run.selected_adapter is not None and run.final_evaluation is not None:
        adapted = adapt_rows(public_rows, spec, strict_rows=False)
        _write_jsonl(oracle_dir / "adapted.jsonl", adapted.rows)
    score = score_run(
        out_dir,
        run_path,
        result_dir=oracle_dir,
        allowed_roots=allowed_roots,
        workers=workers,
    )
    return payload, score


def run_live(
    out_dir: Path,
    *,
    llm_config: Path,
    llm_cache: Path | None,
    allow_remote_data_egress: bool,
    max_rounds: int,
    max_candidates_per_round: int,
    max_total_candidates: int,
    live_dir: Path,
    allowed_roots: Sequence[Path],
    workers: int,
) -> tuple[int, dict[str, Any]]:
    if not allow_remote_data_egress:
        raise ValueError(
            "live schema discovery sends bounded public profile examples; pass "
            "--allow-remote-data-egress after reviewing public_challenge/challenge.jsonl"
        )
    out_dir = out_dir.expanduser().resolve()
    _, _, manifest = load_experiment(out_dir)
    prior_consumption = _read_live_consumption(out_dir, manifest)
    if prior_consumption is not None:
        raise RuntimeError(
            "blind live holdout is already consumed; no second attempt is "
            f"permitted (state={prior_consumption.get('state')!r}, "
            f"run_id={prior_consumption.get('run_id')!r})"
        )
    challenge_path = _resolve_within(
        out_dir, manifest["public_challenge"]["path"],
    )
    reference_path = _resolve_within(
        out_dir, manifest["sealed_reference"]["path"],
    )
    llm_config = llm_config.expanduser().resolve()
    if not llm_config.is_file():
        raise FileNotFoundError(llm_config)
    live_dir = live_dir.expanduser().resolve()
    run_path = live_dir / "run.json"
    if run_path.exists():
        raise ValueError(
            f"live output already contains a run and is not fresh: {run_path}"
        )
    gate_policy_path = live_dir / "gate_policy.json"
    _write_json(gate_policy_path, {
        "required_targets": sorted(REFERENCE_TARGETS),
    })
    args = [
        "auto-adapt",
        str(challenge_path),
        "--family", "workspacebench",
        "--reference", str(reference_path),
        "--llm-config", str(llm_config),
        "--allow-remote-data-egress",
        "--max-rounds", str(max_rounds),
        "--max-candidates-per-round", str(max_candidates_per_round),
        "--max-total-candidates", str(max_total_candidates),
        "--gate-policy", str(gate_policy_path),
        "--profile-out", str(live_dir / "profile.json"),
        "--spec-out", str(live_dir / "selected_adapter.json"),
        "--adapted-out", str(live_dir / "adapted.jsonl"),
        "--out", str(run_path),
    ]
    cache_path = None
    if llm_cache is not None:
        cache_path = llm_cache.expanduser().resolve()
        args.extend(["--llm-cache", str(cache_path)])
    receipt_paths, receipt = _claim_live_consumption(
        out_dir,
        manifest,
        live_dir=live_dir,
        claim_source="run_live_atomic_pre_egress_claim",
        extra={
            "llm_config_sha256": file_sha256(llm_config),
            "llm_cache_path": str(cache_path) if cache_path is not None else None,
            "llm_cache_preexisting_sha256": (
                file_sha256(cache_path)
                if cache_path is not None and cache_path.is_file()
                else None
            ),
            "budget": {
                "max_rounds": max_rounds,
                "max_candidates_per_round": max_candidates_per_round,
                "max_total_candidates": max_total_candidates,
            },
        },
    )
    try:
        exit_code = benchcore_main(args)
        score = score_run(
            out_dir,
            run_path,
            result_dir=live_dir,
            allowed_roots=allowed_roots,
            workers=workers,
        )
    except BaseException as exc:
        failure_updates: dict[str, Any] = {
            "state": "attempt_failed",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:1000],
        }
        if run_path.is_file():
            failure_updates["run_sha256"] = file_sha256(run_path)
        _update_live_consumption(receipt_paths, receipt, **failure_updates)
        raise

    run_payload = json.loads(run_path.read_text(encoding="utf-8"))
    _update_live_consumption(
        receipt_paths,
        receipt,
        state="attempt_completed",
        completed_at_utc=datetime.now(timezone.utc).isoformat(),
        cli_exit_code=exit_code,
        run_id=run_payload.get("run_id"),
        run_status=run_payload.get("status"),
        stop_reason=run_payload.get("stop_reason"),
        reference_attempts=run_payload.get("reference_attempts"),
        run_sha256=file_sha256(run_path),
        score_sha256=file_sha256(live_dir / "score.json"),
        strict_passed=score_passed(score),
    )
    return exit_code, score


def backfill_live_consumption(
    out_dir: Path,
    *,
    live_dir: Path,
    expected_run_id: str,
    cli_exit_code: int,
    attest_first_attempt: bool,
) -> dict[str, Any]:
    """Bind a pre-ledger first live run to the holdout without rerunning it."""
    if not attest_first_attempt:
        raise ValueError(
            "backfill requires an explicit attestation that these artifacts "
            "came from the first and only live attempt"
        )
    out_dir = out_dir.expanduser().resolve()
    live_dir = live_dir.expanduser().resolve()
    public_rows, _, manifest = load_experiment(out_dir)
    run_path = live_dir / "run.json"
    score_path = live_dir / "score.json"
    if not run_path.is_file() or not score_path.is_file():
        raise FileNotFoundError("backfill requires existing run.json and score.json")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    score = json.loads(score_path.read_text(encoding="utf-8"))
    profile = build_schema_profile(public_rows)
    checks = {
        "run_id": run.get("run_id") == expected_run_id,
        "schema_fingerprint": (
            run.get("source_schema_fingerprint") == profile.fingerprint
        ),
        "content_sha256": (
            run.get("source_content_sha256") == canonical_sha256(public_rows)
        ),
        "score_run_path": (
            Path(str(score.get("run_path", ""))).expanduser().resolve() == run_path
        ),
        "score_run_sha256": score.get("run_sha256") == file_sha256(run_path),
        "score_build_manifest_sha256": (
            score.get("build_manifest_sha256")
            == file_sha256(out_dir / "build_manifest.json")
        ),
        "score_holdout_fingerprint": (
            score.get("holdout_fingerprint") == manifest.get("holdout_fingerprint")
        ),
        "score_schema_variant": (
            score.get("schema_variant")
            == manifest.get("schema_variant", DEFAULT_SCHEMA_VARIANT)
        ),
        "score_experiment_type": (
            score.get("experiment_type") == "blind_live_schema_discovery"
        ),
        "not_offline_oracle": (
            not isinstance(run.get("synthesis"), dict)
            or run["synthesis"].get("mode") != "offline_oracle_regression"
        ),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ValueError(f"live backfill evidence validation failed: {failed}")

    timestamp_sources = [
        path for path in (
            live_dir / "gate_policy.json",
            live_dir / "profile.json",
            run_path,
        ) if path.is_file()
    ]
    started_timestamp = min(path.stat().st_mtime for path in timestamp_sources)
    started_at = datetime.fromtimestamp(started_timestamp, timezone.utc).isoformat()
    receipt_paths, receipt = _claim_live_consumption(
        out_dir,
        manifest,
        live_dir=live_dir,
        claim_source="backfilled_first_live_attempt_attestation",
        started_at_utc=started_at,
        extra={
            "started_at_source": "earliest_live_artifact_mtime",
            "backfilled_at_utc": datetime.now(timezone.utc).isoformat(),
            "backfill_attestation": "first_and_only_live_attempt",
            "evidence_checks": checks,
        },
    )
    return _update_live_consumption(
        receipt_paths,
        receipt,
        state="attempt_completed",
        completed_at_utc=score.get("scored_at_utc"),
        cli_exit_code=int(cli_exit_code),
        run_id=run.get("run_id"),
        run_status=run.get("status"),
        stop_reason=run.get("stop_reason"),
        reference_attempts=run.get("reference_attempts"),
        run_sha256=file_sha256(run_path),
        score_sha256=file_sha256(score_path),
        strict_passed=score_passed(score),
    )


def promote_live_consumption_registry(out_dir: Path) -> dict[str, Any]:
    """Promote a legacy local receipt into the fingerprint-wide registry."""
    out_dir = out_dir.expanduser().resolve()
    _, _, manifest = load_experiment(out_dir)
    local_claim_dir = _live_consumption_dir(out_dir)
    local = _read_consumption_claim(local_claim_dir)
    if local is None:
        raise ValueError("no local live-consumption receipt exists to promote")
    fingerprint = manifest.get("holdout_fingerprint")
    checks = {
        "holdout_fingerprint": local.get("holdout_fingerprint") == fingerprint,
        "build_manifest_sha256": (
            local.get("build_manifest_sha256")
            == file_sha256(out_dir / "build_manifest.json")
        ),
        "public_challenge_sha256": (
            local.get("public_challenge_sha256")
            == manifest["public_challenge"]["sha256"]
        ),
        "sealed_reference_sha256": (
            local.get("sealed_reference_sha256")
            == manifest["sealed_reference"]["sha256"]
        ),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ValueError(f"local consumption receipt validation failed: {failed}")
    if not isinstance(fingerprint, str):
        raise ValueError("manifest has no holdout fingerprint")
    registry_root = LIVE_CONSUMPTION_REGISTRY.expanduser().resolve()
    registry_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(registry_root, 0o700)
    registry_claim_dir = _registry_consumption_dir(fingerprint)
    try:
        os.mkdir(registry_claim_dir, mode=0o700)
        _fsync_directory(registry_root)
    except FileExistsError:
        existing = _read_consumption_claim(registry_claim_dir) or {}
        if (
            existing.get("holdout_fingerprint") == fingerprint
            and existing.get("run_id") == local.get("run_id")
        ):
            return existing
        raise RuntimeError("fingerprint registry contains a different consumption claim")
    updated = copy.deepcopy(local)
    updated.update({
        "registry_claim_dir": str(registry_claim_dir),
        "local_claim_dir": str(local_claim_dir),
        "registry_promoted_at_utc": datetime.now(timezone.utc).isoformat(),
        "registry_promotion_checks": checks,
    })
    return _update_live_consumption(
        (registry_claim_dir / "receipt.json", local_claim_dir / "receipt.json"),
        updated,
    )


def _attempt_metrics(run: Mapping[str, Any]) -> dict[str, Any]:
    selected = run.get("selected_adapter")
    selected_sha = None
    if isinstance(selected, dict):
        selected_sha = AdapterSpec.from_dict(selected).sha256
    selected_round = None
    rounds = run.get("rounds") if isinstance(run.get("rounds"), list) else []
    per_round_candidates: list[int] = []
    for row in rounds:
        candidates = row.get("candidates") if isinstance(row, dict) else None
        candidates = candidates if isinstance(candidates, list) else []
        per_round_candidates.append(len(candidates))
        if selected_sha and any(
            isinstance(candidate, dict)
            and candidate.get("adapter_sha256") == selected_sha
            for candidate in candidates
        ):
            selected_round = row.get("round")
    budget = run.get("budget") if isinstance(run.get("budget"), dict) else {}
    one_candidate_rounds = int(budget.get("max_candidates_per_round", 0)) == 1
    verified = run.get("status") == "active_verified"
    return {
        "status": run.get("status"),
        "stop_reason": run.get("stop_reason"),
        "rounds_recorded": len(rounds),
        "per_round_evaluable_candidates": per_round_candidates,
        "candidates_evaluated": int(budget.get("actual_candidates", 0)),
        "candidate_budget": int(budget.get("max_total_candidates", 0)),
        "selected_round": selected_round,
        "first_candidate_success_measurable": one_candidate_rounds,
        "first_candidate_verified_success": (
            bool(verified and selected_round == 1) if one_candidate_rounds else None
        ),
        "verified_within_budget": verified,
        "reference_attempts": int(run.get("reference_attempts", 0)),
        "lineage_closed": bool(run.get("lineage_closed")),
    }


def _semantic_signature(violation: Violation) -> dict[str, Any]:
    return asdict(violation)


def _positive_control(row: Mapping[str, Any], index: int) -> dict[str, Any]:
    projected = copy.deepcopy(dict(row))
    evaluator = projected.get("evaluator")
    rubrics = evaluator.get("rubrics") if isinstance(evaluator, dict) else None
    if not isinstance(rubrics, list) or not rubrics:
        raise ValueError("positive control requires evaluator.rubrics")
    raw = copy.deepcopy(rubrics)
    raw[0] = f"{raw[0]} [blind-adapter-positive-control-{index:08d}]"
    projected["rubrics"] = raw
    return projected


def _checker_signature(
    row: dict[str, Any],
    spec: AdapterSpec,
    index: int,
    roots: tuple[Path, ...],
) -> dict[str, Any]:
    try:
        item = build_items(
            [row], mapping_for_adapted_rows(spec), source_indices=[index],
        )[0]
        checker = WorkspaceArtifactInvariantChecker(allowed_roots=roots)
        findings = [_semantic_signature(value) for value in checker.check(item)]
        findings.sort(key=canonical_json)
        return {
            "ok": True,
            "sha256": canonical_sha256(findings),
            "count": len(findings),
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "sha256": None,
            "count": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _wilson95(successes: int, total: int) -> list[float] | None:
    if total <= 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        p * (1 - p) / total + z * z / (4 * total * total)
    ) / denominator
    low, high = max(0.0, centre - margin), min(1.0, centre + margin)
    if successes == 0:
        low = 0.0
    if successes == total:
        high = 1.0
    return [low, high]


def _proportion(successes: int, total: int) -> dict[str, Any]:
    return {
        "successes": successes,
        "total": total,
        "rate": successes / total if total else None,
        "wilson95": _wilson95(successes, total),
    }


def finding_parity(
    references: Sequence[dict[str, Any]],
    adapted_rows: Sequence[dict[str, Any]],
    spec: AdapterSpec,
    *,
    allowed_roots: Sequence[Path],
    workers: int,
) -> dict[str, Any]:
    roots = tuple(Path(value).expanduser().resolve() for value in allowed_roots)
    worker_count = max(1, int(workers))

    def call(payload: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        index, row = payload
        return _checker_signature(row, spec, index, roots)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        natural_reference = list(executor.map(call, enumerate(references)))
        natural_adapted = list(executor.map(call, enumerate(adapted_rows)))
        positive_reference = list(executor.map(
            call,
            enumerate(_positive_control(row, index) for index, row in enumerate(references)),
        ))
        positive_adapted = list(executor.map(
            call,
            enumerate(_positive_control(row, index) for index, row in enumerate(adapted_rows)),
        ))

    def compare(
        left: Sequence[dict[str, Any]],
        right: Sequence[dict[str, Any]],
        *,
        require_nonempty: bool,
    ) -> dict[str, Any]:
        success = errors = empty = 0
        left_findings = right_findings = 0
        mismatches: list[dict[str, Any]] = []
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            left_findings += int(a["count"])
            right_findings += int(b["count"])
            both_ok = bool(a["ok"] and b["ok"])
            nonempty = int(a["count"]) > 0 and int(b["count"]) > 0
            equal = both_ok and a["sha256"] == b["sha256"]
            passed = equal and (nonempty or not require_nonempty)
            success += int(passed)
            errors += int(not both_ok)
            empty += int(both_ok and not nonempty)
            if not passed and len(mismatches) < 20:
                mismatches.append({
                    "row_index": index,
                    "reference_sha256": a["sha256"],
                    "adapted_sha256": b["sha256"],
                    "reference_count": a["count"],
                    "adapted_count": b["count"],
                    "reference_error": a["error"],
                    "adapted_error": b["error"],
                })
        return {
            "parity": _proportion(success, len(left)),
            "reference_findings": left_findings,
            "adapted_findings": right_findings,
            "checker_error_rows": errors,
            "empty_rows": empty,
            "mismatch_preview": mismatches,
        }

    return {
        "natural": compare(natural_reference, natural_adapted, require_nonempty=False),
        "rubric_divergence_positive_control": compare(
            positive_reference, positive_adapted, require_nonempty=True,
        ),
    }


def score_run(
    out_dir: Path,
    run_path: Path,
    *,
    result_dir: Path,
    allowed_roots: Sequence[Path],
    workers: int,
) -> dict[str, Any]:
    implementation_start = implementation_manifest()
    public_rows, references, manifest = load_experiment(out_dir)
    run_path = run_path.expanduser().resolve()
    run = json.loads(run_path.read_text(encoding="utf-8"))
    synthesis = run.get("synthesis") if isinstance(run.get("synthesis"), dict) else {}
    offline_oracle = synthesis.get("mode") == "offline_oracle_regression"
    consumption = _read_live_consumption(out_dir, manifest)
    live_claim_matches = False
    if not offline_oracle and consumption is not None:
        claimed_live_dir = consumption.get("live_dir")
        if isinstance(claimed_live_dir, str):
            live_claim_matches = bool(
                consumption.get("holdout_fingerprint")
                == manifest.get("holdout_fingerprint")
                and Path(claimed_live_dir).expanduser().resolve()
                == result_dir.expanduser().resolve()
                and consumption.get("state")
                in {"attempt_started", "attempt_completed", "attempt_failed"}
            )
    blind_claim_eligible = (
        False if offline_oracle else live_claim_matches
    )
    profile = build_schema_profile(public_rows)
    if run.get("source_schema_fingerprint") != profile.fingerprint:
        raise ValueError("adapter run was produced for a different schema")
    if run.get("source_content_sha256") != canonical_sha256(public_rows):
        raise ValueError("adapter run was produced for different public content")

    attempts = _attempt_metrics(run)
    selected_payload = run.get("selected_adapter")
    if isinstance(selected_payload, dict):
        spec = AdapterSpec.from_dict(selected_payload)
        adaptation = adapt_rows(public_rows, spec, strict_rows=False)
        evaluation = evaluate_adapter(spec, public_rows, references=references)
        reference_metrics = (
            evaluation.reference.to_dict() if evaluation.reference is not None else None
        )
        gaps = analyze_component_gaps(
            profile, family="workspacebench", spec=spec,
        ).to_dict()
        parity = finding_parity(
            references,
            adaptation.rows,
            spec,
            allowed_roots=allowed_roots,
            workers=workers,
        )
        selected_targets = sorted(spec.targets)
        target_coverage_complete = spec.targets == REFERENCE_TARGETS
        recomputed = evaluation.to_dict()
    else:
        spec = None
        adaptation = None
        reference_metrics = None
        gaps = analyze_component_gaps(
            profile, family="workspacebench", spec=None,
        ).to_dict()
        parity = None
        selected_targets = []
        target_coverage_complete = False
        recomputed = None

    implementation_end = implementation_manifest()
    if implementation_start["sha256"] != implementation_end["sha256"]:
        raise RuntimeError("adaptation implementation changed while the run was scored")
    result = {
        "schema_version": SCORE_SCHEMA,
        "scored_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_type": (
            "offline_oracle_interpreter_regression"
            if offline_oracle
            else (
                "blind_live_schema_discovery"
                if live_claim_matches else "adapter_evaluation_control"
            )
        ),
        "blind_discovery_claim_eligible": blind_claim_eligible,
        "live_consumption_state_at_scoring": (
            consumption.get("state") if consumption is not None else None
        ),
        "schema_variant": manifest.get(
            "schema_variant", DEFAULT_SCHEMA_VARIANT,
        ),
        "holdout_fingerprint": manifest.get("holdout_fingerprint"),
        "run_path": str(run_path),
        "run_sha256": file_sha256(run_path),
        "build_manifest_sha256": file_sha256(out_dir / "build_manifest.json"),
        "source_rows": len(public_rows),
        "schema_fingerprint": profile.fingerprint,
        "attempts": attempts,
        "selected_targets": selected_targets,
        "applicable_target_set": sorted(REFERENCE_TARGETS),
        "inapplicable_core_targets": sorted(INAPPLICABLE_CORE_TARGETS),
        "target_coverage_complete": target_coverage_complete,
        "adaptation": adaptation.to_dict(include_rows=False) if adaptation else None,
        "reference_exactness": reference_metrics,
        "recomputed_evaluation": recomputed,
        "component_gaps": gaps,
        "workspace_checker_parity": parity,
        "sealed_reference": {
            "targets_complete": all(set(row) == REFERENCE_TARGETS for row in references),
            "rows": len(references),
            "sha256": manifest["sealed_reference"]["sha256"],
            "llm_visible": False,
            "reference_attempts": run.get("reference_attempts"),
        },
        "implementation": implementation_start,
        "implementation_hash_end_check": {
            "passed": True,
            "expected": implementation_start["sha256"],
            "observed": implementation_end["sha256"],
        },
        "interpretation_boundary": [
            "Offline-oracle runs validate the trusted interpreter/scorer only and are not blind discovery results.",
            "Live success requires active_verified after the controller's one-shot external-reference gate.",
            "The single schema is a controlled transformation of Workspace-Bench Full-388, not an estimate over all external schemas.",
            "Natural and non-empty positive-control checker parity are reported separately.",
            "Five execution/filesystem components remain trusted-plugin gaps even when all declarative fields are resolved.",
        ],
    }
    result_dir = result_dir.expanduser().resolve()
    _write_json(result_dir / "score.json", result)
    _atomic_write_text(result_dir / "score.md", render_markdown(result))
    return result


def _metric_text(metric: Mapping[str, Any] | None) -> str:
    if not metric:
        return "N/A"
    rate = metric.get("rate")
    return (
        "N/A" if rate is None
        else f"{metric['successes']}/{metric['total']} ({float(rate):.3f})"
    )


def render_markdown(result: Mapping[str, Any]) -> str:
    attempts = result["attempts"]
    reference = result.get("reference_exactness") or {}
    parity = result.get("workspace_checker_parity") or {}
    natural = parity.get("natural") or {}
    positive = parity.get("rubric_divergence_positive_control") or {}
    summary = result["component_gaps"]["summary"]
    title = (
        "# WorkspaceBench offline adapter oracle regression"
        if result.get("experiment_type") == "offline_oracle_interpreter_regression"
        else "# WorkspaceBench blind adapter experiment"
    )
    return "\n".join([
        title,
        "",
        f"- Status: `{attempts['status']}`",
        f"- Schema variant: `{result.get('schema_variant', DEFAULT_SCHEMA_VARIANT)}`",
        f"- Holdout fingerprint: `{result.get('holdout_fingerprint', 'legacy-unbound')}`",
        f"- Blind-discovery claim eligible: `{result.get('blind_discovery_claim_eligible')}`",
        f"- First-candidate verified success: `{attempts['first_candidate_verified_success']}`",
        f"- Verified within budget: `{attempts['verified_within_budget']}`",
        f"- Selected round: `{attempts['selected_round']}`",
        f"- Candidates evaluated: `{attempts['candidates_evaluated']}/{attempts['candidate_budget']}`",
        f"- Reference attempts: `{attempts['reference_attempts']}`",
        f"- Applicable targets recovered: `{len(result['selected_targets'])}/{len(result['applicable_target_set'])}`",
        f"- Field exactness: `{reference.get('equal_fields', 0)}/{reference.get('compared_fields', 0)} ({float(reference.get('field_accuracy', 0.0)):.3f})`",
        f"- Row exactness: `{reference.get('equal_rows', 0)}/{reference.get('rows', 0)} ({float(reference.get('row_accuracy', 0.0)):.3f})`",
        f"- Abstained rows: `{(result.get('adaptation') or {}).get('abstained_rows', 'N/A')}`",
        f"- Natural checker parity: `{_metric_text(natural.get('parity'))}`",
        f"- Positive-control checker parity: `{_metric_text(positive.get('parity'))}`",
        f"- Positive-control findings (reference/adapted): `{positive.get('reference_findings', 'N/A')}/{positive.get('adapted_findings', 'N/A')}`",
        f"- Component gaps: resolved `{summary['resolved']}`, unresolved `{summary['unresolved']}`, trusted-plugin `{summary['requires_trusted_plugin']}`",
        "",
        "## Interpretation boundary",
        "",
        *(f"- {line}" for line in result["interpretation_boundary"]),
        "",
    ])


def score_passed(result: Mapping[str, Any]) -> bool:
    reference = result.get("reference_exactness") or {}
    adaptation = result.get("adaptation") or {}
    gaps = result["component_gaps"]["summary"]
    parity = result.get("workspace_checker_parity") or {}
    natural = (parity.get("natural") or {}).get("parity") or {}
    positive_section = parity.get("rubric_divergence_positive_control") or {}
    positive = positive_section.get("parity") or {}
    return bool(
        result["attempts"]["verified_within_budget"]
        and result["target_coverage_complete"]
        and reference.get("field_accuracy") == 1.0
        and reference.get("row_accuracy") == 1.0
        and adaptation.get("abstained_rows") == 0
        and not adaptation.get("errors")
        and gaps.get("unresolved") == 0
        and natural.get("rate") == 1.0
        and positive.get("rate") == 1.0
        and positive_section.get("reference_findings", 0) >= result["source_rows"]
        and positive_section.get("adapted_findings", 0) >= result["source_rows"]
        and result["sealed_reference"]["targets_complete"]
        and result["sealed_reference"]["reference_attempts"] == 1
    )


def implementation_manifest() -> dict[str, Any]:
    paths = [
        REPO / "scripts" / "run_workspace_blind_adapter_experiment.py",
        REPO / "benchcore" / "adaptation" / "models.py",
        REPO / "benchcore" / "adaptation" / "profile.py",
        REPO / "benchcore" / "adaptation" / "apply.py",
        REPO / "benchcore" / "adaptation" / "evaluation.py",
        REPO / "benchcore" / "adaptation" / "controller.py",
        REPO / "benchcore" / "adaptation" / "synthesis.py",
        REPO / "benchcore" / "adaptation" / "gaps.py",
        REPO / "benchcore" / "workspace_invariants.py",
    ]
    files = {
        path.relative_to(REPO).as_posix(): file_sha256(path)
        for path in paths
    }
    return {
        "schema_version": "workspace-blind-adapter-implementation-v1",
        "files": files,
        "sha256": canonical_sha256(files),
        "git": _git_metadata(),
    }


def _git_metadata() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
            capture_output=True, check=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=REPO, text=True,
            capture_output=True, check=True,
        ).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--allow-input-root", type=Path, action="append", default=[])
    parser.add_argument("--strict", action="store_true")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    build.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    build.add_argument("--expected-rows", type=int)
    build.add_argument(
        "--schema-variant",
        choices=SCHEMA_VARIANTS,
        default=DEFAULT_SCHEMA_VARIANT,
    )

    offline = subparsers.add_parser("offline")
    _add_common(offline)

    score = subparsers.add_parser("score")
    _add_common(score)
    score.add_argument("--run-json", type=Path, required=True)
    score.add_argument("--result-dir", type=Path, required=True)

    live = subparsers.add_parser("live")
    _add_common(live)
    live.add_argument("--llm-config", type=Path, required=True)
    live.add_argument("--llm-cache", type=Path)
    live.add_argument("--allow-remote-data-egress", action="store_true")
    live.add_argument("--max-rounds", type=int, default=3)
    live.add_argument("--max-candidates-per-round", type=int, default=1)
    live.add_argument("--max-total-candidates", type=int, default=3)
    live.add_argument("--live-dir", type=Path)

    backfill = subparsers.add_parser("backfill-live-consumption")
    backfill.add_argument("--out-dir", type=Path, required=True)
    backfill.add_argument("--live-dir", type=Path, required=True)
    backfill.add_argument("--run-id", required=True)
    backfill.add_argument("--cli-exit-code", type=int, required=True)
    backfill.add_argument(
        "--attest-first-attempt",
        action="store_true",
        required=True,
        help="attest that the supplied artifacts are the first and only live attempt",
    )

    promote = subparsers.add_parser("promote-live-consumption-registry")
    promote.add_argument("--out-dir", type=Path, required=True)

    all_offline = subparsers.add_parser("all-offline")
    _add_common(all_offline)
    all_offline.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    all_offline.add_argument("--expected-rows", type=int)
    all_offline.add_argument(
        "--schema-variant",
        choices=SCHEMA_VARIANTS,
        default=DEFAULT_SCHEMA_VARIANT,
    )
    return parser.parse_args()


def _roots(args: argparse.Namespace, out_dir: Path) -> list[Path]:
    roots = [path.expanduser().resolve() for path in args.allow_input_root]
    if roots:
        return roots
    manifest_path = out_dir / "build_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source", {}).get("sha256") == PINNED_FULL_SHA256:
            if DEFAULT_FULL_ROOT.is_dir():
                return [DEFAULT_FULL_ROOT.resolve()]
    return []


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir.expanduser().resolve()
    if args.command == "promote-live-consumption-registry":
        receipt = promote_live_consumption_registry(out_dir)
        print(json.dumps({
            "status": receipt["state"],
            "holdout_fingerprint": receipt["holdout_fingerprint"],
            "run_id": receipt.get("run_id"),
            "registry_claim_dir": receipt["registry_claim_dir"],
        }, indent=2))
        return 0
    if args.command == "backfill-live-consumption":
        receipt = backfill_live_consumption(
            out_dir,
            live_dir=args.live_dir,
            expected_run_id=args.run_id,
            cli_exit_code=args.cli_exit_code,
            attest_first_attempt=args.attest_first_attempt,
        )
        print(json.dumps({
            "status": receipt["state"],
            "holdout_fingerprint": receipt["holdout_fingerprint"],
            "run_id": receipt.get("run_id"),
            "failure_counts_as_consumed": receipt["failure_counts_as_consumed"],
        }, indent=2))
        return 0
    if args.command == "build":
        expected = args.expected_rows
        dataset = args.dataset.expanduser().resolve()
        if expected is None and dataset == DEFAULT_DATASET.resolve():
            expected = 388
        manifest = build_experiment(
            dataset,
            out_dir,
            expected_rows=expected,
            schema_variant=args.schema_variant,
        )
        print(json.dumps({
            "status": "built",
            "rows": manifest["source"]["rows"],
            "schema_variant": manifest["schema_variant"],
            "holdout_fingerprint": manifest["holdout_fingerprint"],
            "schema_fingerprint": manifest["public_challenge"]["schema_fingerprint"],
            "deterministic_alias_candidate": False,
            "out_dir": str(out_dir),
        }, indent=2))
        return 0
    if args.command == "all-offline":
        expected = args.expected_rows
        dataset = args.dataset.expanduser().resolve()
        if expected is None and dataset == DEFAULT_DATASET.resolve():
            expected = 388
        build_experiment(
            dataset,
            out_dir,
            expected_rows=expected,
            schema_variant=args.schema_variant,
        )
        _, result = run_offline(
            out_dir,
            allowed_roots=_roots(args, out_dir),
            workers=max(1, args.workers),
        )
        print(json.dumps({
            "status": result["attempts"]["status"],
            "field_accuracy": (result.get("reference_exactness") or {}).get("field_accuracy"),
            "row_accuracy": (result.get("reference_exactness") or {}).get("row_accuracy"),
            "strict_passed": score_passed(result),
        }, indent=2))
        return 2 if args.strict and not score_passed(result) else 0
    if args.command == "offline":
        _, result = run_offline(
            out_dir,
            allowed_roots=_roots(args, out_dir),
            workers=max(1, args.workers),
        )
        print(json.dumps({
            "status": result["attempts"]["status"],
            "strict_passed": score_passed(result),
        }, indent=2))
        return 2 if args.strict and not score_passed(result) else 0
    if args.command == "score":
        result = score_run(
            out_dir,
            args.run_json,
            result_dir=args.result_dir,
            allowed_roots=_roots(args, out_dir),
            workers=max(1, args.workers),
        )
        print(json.dumps({
            "status": result["attempts"]["status"],
            "strict_passed": score_passed(result),
        }, indent=2))
        return 2 if args.strict and not score_passed(result) else 0
    if args.command == "live":
        live_dir = (
            args.live_dir.expanduser().resolve()
            if args.live_dir else out_dir / "live_discovery"
        )
        cli_exit, result = run_live(
            out_dir,
            llm_config=args.llm_config,
            llm_cache=args.llm_cache,
            allow_remote_data_egress=args.allow_remote_data_egress,
            max_rounds=args.max_rounds,
            max_candidates_per_round=args.max_candidates_per_round,
            max_total_candidates=args.max_total_candidates,
            live_dir=live_dir,
            allowed_roots=_roots(args, out_dir),
            workers=max(1, args.workers),
        )
        passed = score_passed(result)
        print(json.dumps({
            "auto_adapt_exit": cli_exit,
            "status": result["attempts"]["status"],
            "first_candidate_success": result["attempts"]["first_candidate_verified_success"],
            "verified_within_budget": result["attempts"]["verified_within_budget"],
            "strict_passed": passed,
            "score": str(live_dir / "score.json"),
        }, indent=2))
        return 2 if args.strict and not passed else cli_exit
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
