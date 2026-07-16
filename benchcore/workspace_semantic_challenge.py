"""Provenance-safe paired challenges for Workspace rubric grounding.

The deterministic Workspace challenge in :mod:`benchcore.workspace_challenge`
tests schema and artifact invariants.  This module tests the complementary
semantic question: can the production, single-rubric grounding path distinguish
an independently supported requirement from a minimally changed hidden or
contradicted requirement?

Four operators create objective clean/mutant pairs.  The auditor-visible rows
contain opaque IDs and exactly one rubric; the source/pair/operator/label mapping
exists only in a sidecar.  A phase runner accepts either the clean rows *or* the
mutant rows and calls ``WorkspaceRubricGroundingAuditor.audit_rubric`` once per
row.  It never uses the experimental multi-rubric batching path.

The challenge measures a model-grounded detector, not human-gold performance on
unmodified Workspace-Bench.  In every pair the visible task and contract are
identical and make the clean target relevant.  Only the exact rubric target is
changed: it either matches the task/contract/input inventory or contradicts it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import random
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

from .loader import build_items, load_mapping
from .schema import BenchmarkItem
from .workspace_grounding import (
    GROUNDING_PROMPT,
    GROUNDING_SYSTEM,
    OBJECTIVE_CITATION_RESOLVER_VERSION,
    VERIFIER_PROMPT,
    VERIFIER_SYSTEM,
    WorkspaceEvidenceBundle,
    WorkspaceRubricGroundingAuditor,
    build_workspace_evidence_bundle,
)
from .workspace_invariants import (
    REFERENCE_GENERATOR_NAME,
    logical_input_name,
    parse_jsonish,
    workspace_input_path_records,
)


TASK_EXPLICIT_VS_HIDDEN_TITLE = "task_explicit_vs_hidden_title"
CONTRACT_REQUESTED_VS_HIDDEN_COMPANION_FILE = (
    "contract_requested_vs_hidden_companion_file"
)
INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL = (
    "input_file_count_correct_vs_wrong_literal"
)
INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME = (
    "input_grounded_visible_source_name_vs_nonexistent_name"
)

WORKSPACE_SEMANTIC_OPERATORS = (
    TASK_EXPLICIT_VS_HIDDEN_TITLE,
    CONTRACT_REQUESTED_VS_HIDDEN_COMPANION_FILE,
    INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL,
    INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME,
)

SEMANTIC_CHALLENGE_PROTOCOL = "workspace-semantic-paired-isolated-v3-20260714"
_PROVENANCE_FIELDS = {
    "_injected_defect",
    "_workspace_challenge",
    "_workspace_semantic_challenge",
    "_challenge_provenance",
    "_mutation_provenance",
}
_VALID_LABELS = {"supported", "unsupported", "uncertain"}


@dataclass(frozen=True)
class WorkspaceSemanticProvenance:
    """Sidecar-only ground truth for one semantic pair."""

    pair_id: str
    source_item_id: str
    clean_item_id: str
    mutant_item_id: str
    operator: str
    clean_expected_label: str
    mutant_expected_label: str
    support_source: str
    clean_requirement: str
    mutant_requirement: str
    changed_fields: tuple[str, ...]
    challenge_rubric_index: int
    seed: int
    source_sha256: str
    clean_sha256: str
    mutant_sha256: str


@dataclass
class WorkspaceSemanticChallenge:
    """Auditor-visible phase rows and their separately stored sidecar."""

    clean_rows: list[dict[str, Any]]
    mutant_rows: list[dict[str, Any]]
    provenance: list[WorkspaceSemanticProvenance]
    source_items: int
    seed: int
    operators: tuple[str, ...]
    skipped: list[dict[str, str]]

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "protocol_version": SEMANTIC_CHALLENGE_PROTOCOL,
            "seed": self.seed,
            "source_items": self.source_items,
            "clean_items": len(self.clean_rows),
            "mutant_items": len(self.mutant_rows),
            "pair_count": len(self.provenance),
            "operators": list(self.operators),
            "skipped": list(self.skipped),
            "pairs": [asdict(row) for row in self.provenance],
        }


@dataclass(frozen=True)
class _VisibleInput:
    path: Path
    logical_name: str


@dataclass(frozen=True)
class _PairRows:
    clean: dict[str, Any]
    mutant: dict[str, Any]
    clean_requirement: str
    mutant_requirement: str
    support_source: str
    changed_fields: tuple[str, ...]


def build_workspace_semantic_challenge(
    rows: Sequence[Mapping[str, Any]],
    *,
    root: Path | None = None,
    allowed_roots: Iterable[Path] | None = None,
    seed: int = 20260714,
    operators: Iterable[str] | None = None,
) -> WorkspaceSemanticChallenge:
    """Build deterministic, one-rubric clean/mutant pairs.

    Every operator gets a distinct clean row.  This is intentional: the clean
    support intervention differs by operator, so sharing a clean row would no
    longer be an atomic paired comparison.  The input rows are never modified.
    """

    selected = tuple(operators or WORKSPACE_SEMANTIC_OPERATORS)
    unknown = set(selected) - set(WORKSPACE_SEMANTIC_OPERATORS)
    if unknown:
        raise ValueError(
            "unknown Workspace semantic operator(s): " + ", ".join(sorted(unknown))
        )
    if len(selected) != len(set(selected)):
        raise ValueError("Workspace semantic operators must be unique")
    allowed_root_tuple = (
        tuple(Path(value) for value in allowed_roots)
        if allowed_roots is not None
        else None
    )

    clean_rows: list[dict[str, Any]] = []
    mutant_rows: list[dict[str, Any]] = []
    provenance: list[WorkspaceSemanticProvenance] = []
    skipped: list[dict[str, str]] = []
    source_ids: set[str] = set()

    for source_index, raw_source in enumerate(rows):
        source = copy.deepcopy(dict(raw_source))
        source_id = str(source.get("item_id") or f"item-{source_index}")
        if source_id in source_ids:
            raise ValueError(f"duplicate source item_id: {source_id}")
        source_ids.add(source_id)
        source_hash = canonical_sha256(_portable_source_row(source))
        visible = _visible_inputs(source, root, allowed_roots=allowed_root_tuple)

        for operator in selected:
            pair_id = _opaque_digest(
                "workspace-semantic-pair", seed, source_id, operator,
            )
            # Domain separation keeps even a truncated sidecar pair ID out of
            # auditor-visible synthetic literals.
            token = _opaque_digest(
                "workspace-semantic-content", seed, source_id, operator,
            )[:12]
            clean_id = _opaque_item_id(seed, source_id, operator, "side-a")
            mutant_id = _opaque_item_id(seed, source_id, operator, "side-b")
            pair, reason = _apply_operator(
                source,
                operator,
                token,
                clean_id=clean_id,
                mutant_id=mutant_id,
                visible_inputs=visible,
            )
            if pair is None:
                skipped.append({
                    "source_item_id": source_id,
                    "operator": operator,
                    "reason": reason or "operator is not applicable",
                })
                continue

            _declare_synthetic_actor_inventory(pair.clean, visible)
            _declare_synthetic_actor_inventory(pair.mutant, visible)
            _assert_auditor_row(pair.clean)
            _assert_auditor_row(pair.mutant)
            clean_rows.append(pair.clean)
            mutant_rows.append(pair.mutant)
            provenance.append(WorkspaceSemanticProvenance(
                pair_id=pair_id,
                source_item_id=source_id,
                clean_item_id=clean_id,
                mutant_item_id=mutant_id,
                operator=operator,
                clean_expected_label="supported",
                mutant_expected_label="unsupported",
                support_source=pair.support_source,
                clean_requirement=pair.clean_requirement,
                mutant_requirement=pair.mutant_requirement,
                changed_fields=pair.changed_fields,
                challenge_rubric_index=0,
                seed=seed,
                source_sha256=source_hash,
                clean_sha256=canonical_sha256(pair.clean),
                mutant_sha256=canonical_sha256(pair.mutant),
            ))

    challenge = WorkspaceSemanticChallenge(
        clean_rows=clean_rows,
        mutant_rows=mutant_rows,
        provenance=provenance,
        source_items=len(rows),
        seed=seed,
        operators=selected,
        skipped=skipped,
    )
    _validate_challenge(challenge)
    return challenge


def select_workspace_source_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    sample_size: int = 50,
    seed: int = 20260714,
    root: Path | None = None,
    allowed_roots: Iterable[Path] | None = None,
    require_visible_input: bool = True,
) -> list[dict[str, Any]]:
    """Select a stable, order-independent source-task sample.

    Selection ranks rows by a SHA-256 value derived from the seed, item ID and a
    portable row hash.  It therefore does not depend on input-file ordering or
    Python's random implementation.  By default, rows without a materialized,
    auditor-visible input are excluded so all four operators remain applicable.
    """

    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    allowed_root_tuple = (
        tuple(Path(value) for value in allowed_roots)
        if allowed_roots is not None
        else None
    )
    ranked: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows):
        row = copy.deepcopy(dict(raw))
        source_id = str(row.get("item_id") or f"item-{index}")
        if source_id in seen:
            raise ValueError(f"duplicate source item_id: {source_id}")
        seen.add(source_id)
        if require_visible_input and not _visible_inputs(
            row, root, allowed_roots=allowed_root_tuple,
        ):
            continue
        portable_hash = canonical_sha256(_portable_source_row(row))
        rank = hashlib.sha256(
            f"workspace-semantic-sample:{seed}:{source_id}:{portable_hash}".encode(
                "utf-8"
            )
        ).hexdigest()
        ranked.append((rank, row))
    if len(ranked) < sample_size:
        raise ValueError(
            f"requested {sample_size} source tasks, but only {len(ranked)} are eligible"
        )
    ranked.sort(key=lambda value: value[0])
    return [row for _, row in ranked[:sample_size]]


def audit_semantic_phase(
    challenge: WorkspaceSemanticChallenge,
    phase: Literal["clean", "mutant"],
    client: Any,
    decisions_path: Path,
    *,
    run_signature: str,
    root: Path | None = None,
    allowed_roots: Iterable[Path] | None = None,
    workers: int = 8,
    evidence_workers: int = 1,
    operational_passes: int = 2,
    verify_unsupported: bool = True,
    min_confidence: float = 0.55,
    evidence_chars: int = 16_000,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one isolated side through the production single-rubric path.

    Only rows from ``phase`` are materialized in this function.  Evidence
    bundles are deduplicated within that side, and each model call contains one
    rubric.  Atomic per-item state files make the run resumable without turning
    intentional retries into duplicate scored decisions.
    """

    if phase not in {"clean", "mutant"}:
        raise ValueError("phase must be 'clean' or 'mutant'")
    if not run_signature:
        raise ValueError("run_signature is required")
    if workers <= 0:
        raise ValueError("workers must be positive")
    if evidence_workers <= 0:
        raise ValueError("evidence_workers must be positive")
    if operational_passes <= 0:
        raise ValueError("operational_passes must be positive")
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")
    allowed_root_tuple = (
        tuple(Path(value) for value in allowed_roots)
        if allowed_roots is not None
        else None
    )

    rows = challenge.clean_rows if phase == "clean" else challenge.mutant_rows
    expected_ids = _phase_expected_ids(challenge, phase)
    row_ids = [str(row.get("item_id") or "") for row in rows]
    if len(row_ids) != len(set(row_ids)) or set(row_ids) != expected_ids:
        raise ValueError(f"{phase} rows do not align exactly with provenance sidecar IDs")
    if rows_contain_semantic_provenance(rows):
        raise ValueError("semantic challenge provenance leaked into auditor-visible rows")

    decisions_path = Path(decisions_path)
    phase_signature = semantic_phase_signature(run_signature, phase)
    loaded = read_semantic_decisions(decisions_path, phase_signature=phase_signature)
    counts = Counter(str(row.get("item_id") or "") for row in loaded)
    resume_duplicates = sum(
        max(0, count - 1) for item_id, count in counts.items()
        if item_id in expected_ids
    )
    resume_extras = sum(count for item_id, count in counts.items() if item_id not in expected_ids)
    initial_latest = _last_by_id(loaded)
    latest = dict(initial_latest)
    extras = [row for row in loaded if str(row.get("item_id") or "") not in expected_ids]

    items = _items_for_rows(rows)
    by_id = {item.item_id: item for item in items}
    bundles, bundle_failures = _build_phase_bundles(
        items,
        root=root,
        workers=evidence_workers,
        evidence_chars=evidence_chars,
        allowed_roots=allowed_root_tuple,
    )
    auditor = WorkspaceRubricGroundingAuditor(
        client,
        verify_unsupported=verify_unsupported,
        min_confidence=min_confidence,
        evidence_chars=evidence_chars,
    )
    parts_dir = decisions_path.with_name(decisions_path.name + ".parts")
    write_lock = threading.Lock()
    new_decisions = 0
    retried_decisions = 0

    def reusable(item_id: str, value: Mapping[str, Any] | None = None) -> bool:
        row = value if value is not None else latest.get(item_id)
        return bool(
            row is not None
            and item_id not in bundle_failures
            and not decision_has_operational_failure(row)
            and _decision_matches_current(
                row,
                by_id[item_id],
                bundles[item_id],
            )
        )

    stale_decisions = {
        item_id for item_id in expected_ids
        if item_id in initial_latest
        and not decision_has_operational_failure(initial_latest[item_id])
        and not reusable(item_id, initial_latest[item_id])
    }

    def run_one(item_id: str) -> dict[str, Any]:
        item = by_id[item_id]
        rubric = _single_rubric(item)
        if item_id in bundle_failures:
            row = _operational_decision(
                item,
                rubric,
                f"evidence bundle failed: {bundle_failures[item_id]}",
            )
        else:
            try:
                # This exact call is the production isolated-rubric path.
                row = auditor.audit_rubric(item, 0, rubric, bundles[item_id]).to_dict()
            except Exception as exc:  # evidence/search failure remains row-local
                row = _operational_decision(
                    item,
                    rubric,
                    f"{type(exc).__name__}: {exc}",
                )
        row["protocol_version"] = SEMANTIC_CHALLENGE_PROTOCOL
        row["run_signature"] = run_signature
        row["phase_signature"] = phase_signature
        with write_lock:
            _write_part(parts_dir, item_id, row)
        return row

    for pass_index in range(1, operational_passes + 1):
        pending = [
            item_id for item_id in sorted(expected_ids)
            if not reusable(item_id)
        ]
        if not pending:
            break
        with ThreadPoolExecutor(max_workers=min(workers, len(pending))) as pool:
            futures = {pool.submit(run_one, item_id): item_id for item_id in pending}
            completed = 0
            for future in as_completed(futures):
                item_id = futures[future]
                had_previous = item_id in latest
                row = future.result()
                latest[item_id] = row
                new_decisions += 1
                retried_decisions += int(had_previous)
                completed += 1
                if progress is not None:
                    progress({
                        "phase": phase,
                        "pass": pass_index,
                        "completed": completed,
                        "scheduled": len(pending),
                        "item_id": item_id,
                        "label": row.get("label"),
                        "operational_failure": decision_has_operational_failure(row),
                    })

    ordered = [latest[item_id] for item_id in sorted(expected_ids) if item_id in latest]
    _atomic_write_jsonl(decisions_path, [*ordered, *extras])
    decisions = read_semantic_decisions(
        decisions_path,
        phase_signature=phase_signature,
        include_parts=False,
    )
    expected_rows = [
        row for row in decisions if str(row.get("item_id") or "") in expected_ids
    ]
    final_counts = Counter(str(row.get("item_id") or "") for row in decisions)
    final_duplicates = sum(
        max(0, final_counts[item_id] - 1) for item_id in expected_ids
    )
    final_extras = sum(
        count for item_id, count in final_counts.items() if item_id not in expected_ids
    )
    operational = sum(decision_has_operational_failure(row) for row in expected_rows)
    uncertain = sum(
        str(row.get("label") or "uncertain") == "uncertain"
        and not decision_has_operational_failure(row)
        for row in expected_rows
    )
    return {
        "phase": phase,
        "phase_signature": phase_signature,
        "expected_items": len(expected_ids),
        "decision_items": len({str(row.get('item_id') or '') for row in expected_rows}),
        "complete": (
            len(expected_rows) == len(expected_ids)
            and operational == 0
            and final_duplicates == 0
            and final_extras == 0
        ),
        "operational_failure_items": operational + max(0, len(expected_ids) - len(expected_rows)),
        "semantic_uncertain_items": uncertain,
        "new_attempts": new_decisions,
        "retried_attempts": retried_decisions,
        "resumed_valid_items": sum(
            item_id in initial_latest and reusable(item_id, initial_latest[item_id])
            for item_id in expected_ids
        ),
        "stale_decision_items_seen": len(stale_decisions),
        "resume_duplicate_rows_seen": resume_duplicates,
        "resume_extra_rows_seen": resume_extras,
        "duplicate_decision_rows": final_duplicates,
        "extra_decision_rows": final_extras,
        "decisions": decisions,
    }


def read_semantic_decisions(
    path: Path,
    *,
    phase_signature: str | None = None,
    include_parts: bool = True,
) -> list[dict[str, Any]]:
    """Read a phase decision file, with atomic part files taking precedence."""

    path = Path(path)
    rows = _read_jsonl(path)
    if phase_signature is not None:
        rows = [row for row in rows if row.get("phase_signature") == phase_signature]
    if not include_parts:
        return rows

    parts_dir = path.with_name(path.name + ".parts")
    parts: list[dict[str, Any]] = []
    if parts_dir.is_dir():
        for part in sorted(parts_dir.glob("*.json")):
            try:
                value = json.loads(part.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict):
                continue
            if phase_signature is not None and value.get("phase_signature") != phase_signature:
                continue
            parts.append(value)
    if not parts:
        return rows
    part_ids = {str(row.get("item_id") or "") for row in parts}
    return [row for row in rows if str(row.get("item_id") or "") not in part_ids] + parts


def score_workspace_semantic_challenge(
    provenance: Sequence[WorkspaceSemanticProvenance | Mapping[str, Any]],
    clean_decisions: Sequence[Any],
    mutant_decisions: Sequence[Any],
) -> dict[str, Any]:
    """Score planned-pair recall, discrimination, uncertainty, and integrity.

    The primary mutant and paired rates use all planned pairs as denominator, so
    missing/failed decisions cannot inflate recall.  Clean false-alarm rate uses
    operationally evaluable clean rows and reports that denominator explicitly.
    A stricter paired metric additionally requires ``supported -> unsupported``;
    this exposes detectors that avoid false alarms by returning ``uncertain``.
    """

    prov = [_provenance_dict(row) for row in provenance]
    _validate_provenance_rows(prov)
    clean = [_decision_dict(row) for row in clean_decisions]
    mutant = [_decision_dict(row) for row in mutant_decisions]
    clean_expected = {str(row["clean_item_id"]) for row in prov}
    mutant_expected = {str(row["mutant_item_id"]) for row in prov}
    clean_counts = Counter(str(row.get("item_id") or "") for row in clean)
    mutant_counts = Counter(str(row.get("item_id") or "") for row in mutant)
    clean_by_id = _last_by_id(clean)
    mutant_by_id = _last_by_id(mutant)

    details: list[dict[str, Any]] = []
    by_operator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in prov:
        clean_id = str(row["clean_item_id"])
        mutant_id = str(row["mutant_item_id"])
        clean_row = clean_by_id.get(clean_id)
        mutant_row = mutant_by_id.get(mutant_id)
        clean_duplicate = clean_counts[clean_id] > 1
        mutant_duplicate = mutant_counts[mutant_id] > 1
        clean_operational = clean_row is None or (
            clean_row is not None and decision_has_operational_failure(clean_row)
        )
        mutant_operational = mutant_row is None or (
            mutant_row is not None and decision_has_operational_failure(mutant_row)
        )
        clean_protocol_match = _scored_decision_matches_provenance(
            clean_row,
            item_id=clean_id,
            requirement=str(row["clean_requirement"]),
        )
        mutant_protocol_match = _scored_decision_matches_provenance(
            mutant_row,
            item_id=mutant_id,
            requirement=str(row["mutant_requirement"]),
        )
        evidence_hash_match = _paired_hash_matches(
            clean_row, mutant_row, "evidence_bundle_sha256",
        )
        artifact_hash_match = _paired_hash_matches(
            clean_row, mutant_row, "artifact_manifest_sha256",
        )
        pair_hash_match = evidence_hash_match and artifact_hash_match
        clean_label = _decision_label(clean_row)
        mutant_label = _decision_label(mutant_row)
        raw_clean_label = _raw_scanner_label(clean_row)
        raw_mutant_label = _raw_scanner_label(mutant_row)
        grounded_clean_label = _grounded_model_label(clean_row)
        grounded_mutant_label = _grounded_model_label(mutant_row)
        clean_certificate_label = _objective_certificate_label(clean_row)
        mutant_certificate_label = _objective_certificate_label(mutant_row)
        clean_evaluable = (
            not clean_operational and not clean_duplicate and clean_protocol_match
        )
        mutant_evaluable = (
            not mutant_operational and not mutant_duplicate and mutant_protocol_match
        )
        clean_nonunsupported = clean_evaluable and clean_label != "unsupported"
        clean_false_alarm = clean_evaluable and clean_label == "unsupported"
        inventory_absence_required = str(row["operator"]) in {
            INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL,
            INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME,
        }
        inventory_absence_eligible = (
            not inventory_absence_required
            or _inventory_absence_is_confirmation_eligible(mutant_row)
        )
        # Count and non-existent-filename mutants are negative inventory
        # claims.  An ``unsupported`` string is not a hit unless the production
        # evidence bundle proves that the rendered actor inventory is complete.
        # This is deliberately narrower than ``actor_view_complete``: parsing
        # every PDF is unnecessary when only manifest membership is at issue.
        mutant_hit = (
            mutant_evaluable
            and mutant_label == "unsupported"
            and inventory_absence_eligible
        )
        paired = clean_nonunsupported and mutant_hit and pair_hash_match
        strict_paired = (
            clean_evaluable
            and mutant_evaluable
            and clean_label == "supported"
            and mutant_label == "unsupported"
            and inventory_absence_eligible
            and pair_hash_match
        )
        clean_uncertain = clean_evaluable and clean_label == "uncertain"
        mutant_uncertain = mutant_evaluable and mutant_label == "uncertain"

        raw_clean_nonunsupported = (
            clean_evaluable and raw_clean_label != "unsupported"
        )
        raw_clean_false_alarm = (
            clean_evaluable and raw_clean_label == "unsupported"
        )
        raw_mutant_hit = (
            mutant_evaluable
            and raw_mutant_label == "unsupported"
            and inventory_absence_eligible
        )
        raw_paired = raw_clean_nonunsupported and raw_mutant_hit and pair_hash_match
        raw_strict_paired = bool(
            clean_evaluable
            and mutant_evaluable
            and raw_clean_label == "supported"
            and raw_mutant_label == "unsupported"
            and inventory_absence_eligible
            and pair_hash_match
        )

        grounded_clean_nonunsupported = (
            clean_evaluable and grounded_clean_label != "unsupported"
        )
        grounded_clean_false_alarm = (
            clean_evaluable and grounded_clean_label == "unsupported"
        )
        grounded_mutant_hit = (
            mutant_evaluable
            and grounded_mutant_label == "unsupported"
            and inventory_absence_eligible
        )
        grounded_paired = bool(
            grounded_clean_nonunsupported and grounded_mutant_hit and pair_hash_match
        )
        grounded_strict_paired = bool(
            clean_evaluable
            and mutant_evaluable
            and grounded_clean_label == "supported"
            and grounded_mutant_label == "unsupported"
            and inventory_absence_eligible
            and pair_hash_match
        )

        clean_certificate_supported = bool(
            clean_protocol_match and clean_certificate_label == "supported"
        )
        mutant_certificate_unsupported = bool(
            mutant_protocol_match
            and mutant_certificate_label == "unsupported"
            and inventory_absence_eligible
        )
        objective_certified_pair = bool(
            clean_certificate_supported
            and mutant_certificate_unsupported
            and not clean_duplicate
            and not mutant_duplicate
            and pair_hash_match
        )
        result = {
            "pair_id": row["pair_id"],
            "source_item_id": row["source_item_id"],
            "clean_item_id": clean_id,
            "mutant_item_id": mutant_id,
            "operator": row["operator"],
            "clean_label": clean_label,
            "mutant_label": mutant_label,
            "raw_clean_label": raw_clean_label,
            "raw_mutant_label": raw_mutant_label,
            "grounded_clean_label": grounded_clean_label,
            "grounded_mutant_label": grounded_mutant_label,
            "clean_objective_certificate_label": clean_certificate_label,
            "mutant_objective_certificate_label": mutant_certificate_label,
            "clean_evaluable": clean_evaluable,
            "mutant_evaluable": mutant_evaluable,
            "clean_nonunsupported": clean_nonunsupported,
            "clean_false_alarm": clean_false_alarm,
            "mutant_unsupported_hit": mutant_hit,
            "inventory_absence_required": inventory_absence_required,
            "inventory_absence_is_confirmation_eligible": (
                inventory_absence_eligible
            ),
            "paired_discriminated": paired,
            "strict_paired_discriminated": strict_paired,
            "clean_uncertain": clean_uncertain,
            "mutant_uncertain": mutant_uncertain,
            "raw_clean_nonunsupported": raw_clean_nonunsupported,
            "raw_clean_false_alarm": raw_clean_false_alarm,
            "raw_mutant_unsupported_hit": raw_mutant_hit,
            "raw_paired_discriminated": raw_paired,
            "raw_strict_paired_discriminated": raw_strict_paired,
            "raw_clean_uncertain": (
                clean_evaluable and raw_clean_label == "uncertain"
            ),
            "raw_mutant_uncertain": (
                mutant_evaluable and raw_mutant_label == "uncertain"
            ),
            "grounded_clean_nonunsupported": grounded_clean_nonunsupported,
            "grounded_clean_false_alarm": grounded_clean_false_alarm,
            "grounded_mutant_unsupported_hit": grounded_mutant_hit,
            "grounded_paired_discriminated": grounded_paired,
            "grounded_strict_paired_discriminated": grounded_strict_paired,
            "grounded_clean_uncertain": (
                clean_evaluable and grounded_clean_label == "uncertain"
            ),
            "grounded_mutant_uncertain": (
                mutant_evaluable and grounded_mutant_label == "uncertain"
            ),
            "clean_objective_certificate_supported": clean_certificate_supported,
            "mutant_objective_certificate_unsupported": (
                mutant_certificate_unsupported
            ),
            "objective_certified_pair": objective_certified_pair,
            "clean_operational_failure": clean_operational,
            "mutant_operational_failure": mutant_operational,
            "clean_duplicate": clean_duplicate,
            "mutant_duplicate": mutant_duplicate,
            "clean_protocol_match": clean_protocol_match,
            "mutant_protocol_match": mutant_protocol_match,
            "evidence_bundle_hash_match": evidence_hash_match,
            "artifact_manifest_hash_match": artifact_hash_match,
            "pair_hash_match": pair_hash_match,
            "integrity_failure": (
                clean_duplicate
                or mutant_duplicate
                or (clean_row is not None and not clean_protocol_match)
                or (mutant_row is not None and not mutant_protocol_match)
                or (clean_row is not None and mutant_row is not None and not pair_hash_match)
            ),
        }
        details.append(result)
        by_operator[str(row["operator"])].append(result)

    aggregate = _aggregate_semantic_rows(details)
    extra_clean = sum(
        count for item_id, count in clean_counts.items() if item_id not in clean_expected
    )
    extra_mutant = sum(
        count for item_id, count in mutant_counts.items() if item_id not in mutant_expected
    )
    duplicate_clean = sum(
        max(0, count - 1) for item_id, count in clean_counts.items()
        if item_id in clean_expected
    )
    duplicate_mutant = sum(
        max(0, count - 1) for item_id, count in mutant_counts.items()
        if item_id in mutant_expected
    )
    aggregate.update({
        "extra_decision_count": extra_clean + extra_mutant,
        "extra_clean_decision_count": extra_clean,
        "extra_mutant_decision_count": extra_mutant,
        "duplicate_decision_count": duplicate_clean + duplicate_mutant,
        "duplicate_clean_decision_count": duplicate_clean,
        "duplicate_mutant_decision_count": duplicate_mutant,
        "per_operator": {
            operator: _aggregate_semantic_rows(rows)
            for operator, rows in sorted(by_operator.items())
        },
        "misses": [row for row in details if not row["mutant_unsupported_hit"]],
        "pair_failures": [row for row in details if not row["paired_discriminated"]],
        "details": details,
    })
    return aggregate


def decision_has_operational_failure(row: Mapping[str, Any]) -> bool:
    scanner = row.get("scanner")
    verifier = row.get("verifier")
    return bool(
        row.get("operational_failure")
        or (isinstance(scanner, Mapping) and scanner.get("operational_failure"))
        or (isinstance(verifier, Mapping) and verifier.get("operational_failure"))
    )


def _inventory_absence_is_confirmation_eligible(
    row: Mapping[str, Any] | None,
) -> bool:
    """Read the production inventory-specific eligibility flag fail-closed."""

    return bool(
        row is not None
        and row.get("inventory_absence_is_confirmation_eligible") is True
    )


def prompt_signature() -> str:
    """Hash the exact isolated scanner and verifier prompt protocol."""

    return canonical_sha256({
        "protocol_version": SEMANTIC_CHALLENGE_PROTOCOL,
        "grounding_system": GROUNDING_SYSTEM,
        "grounding_prompt": GROUNDING_PROMPT,
        "verifier_system": VERIFIER_SYSTEM,
        "verifier_prompt": VERIFIER_PROMPT,
        "objective_citation_resolver_version": (
            OBJECTIVE_CITATION_RESOLVER_VERSION
        ),
    })


def model_signature(
    config: Any,
    *,
    verify_unsupported: bool = True,
    min_confidence: float = 0.55,
    evidence_chars: int = 16_000,
) -> str:
    """Hash inference-relevant configuration without API keys or cache paths."""

    def value(name: str, default: Any = None) -> Any:
        if isinstance(config, Mapping):
            return config.get(name, default)
        return getattr(config, name, default)

    return canonical_sha256({
        "model": value("model"),
        "base_url": str(value("base_url") or "").rstrip("/"),
        "temperature": value("temperature"),
        "max_tokens": value("max_tokens"),
        "timeout": value("timeout"),
        "max_retries": value("max_retries"),
        "dry_run": bool(value("dry_run", False)),
        "n_votes": value("n_votes", 1),
        "vote_temperature": value("vote_temperature", 0.3),
        "verify_unsupported": verify_unsupported,
        "min_confidence": min_confidence,
        "evidence_chars": evidence_chars,
    })


def workspace_snapshot_signature(
    rows: Sequence[Mapping[str, Any]],
    *,
    root: Path | None = None,
    allowed_roots: Iterable[Path] | None = None,
) -> str:
    """Hash selected records and every declared attachment's bytes."""

    snapshot: list[dict[str, Any]] = []
    allowed_root_tuple = (
        tuple(Path(value) for value in allowed_roots)
        if allowed_roots is not None
        else None
    )
    materialized_rows = [dict(raw) for raw in rows]
    items = _items_for_rows(materialized_rows)
    for index, (row, item) in enumerate(zip(materialized_rows, items)):
        source_id = str(row.get("item_id") or f"item-{index}")
        files: list[dict[str, Any]] = []
        records = workspace_input_path_records(
            item, root, allowed_roots=allowed_root_tuple,
        )
        for record in records:
            path = record["path"]
            entry: dict[str, Any] = {
                "stored_name": path.name,
                "logical_name": _logical_name_for_path(row, path),
                "allowed": bool(record["allowed"]),
                "exists": bool(record["allowed"] and path.is_file()),
            }
            if record["allowed"] and path.is_file():
                entry.update({
                    "size_bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                })
            files.append(entry)
        snapshot.append({
            "source_item_id": source_id,
            "source_sha256": canonical_sha256(_portable_source_row(row)),
            "files": sorted(
                files,
                key=lambda value: (
                    str(value["logical_name"]), str(value["stored_name"]),
                ),
            ),
        })
    return canonical_sha256(sorted(snapshot, key=lambda value: value["source_item_id"]))


def semantic_run_signature(
    *,
    workspace_snapshot_sha256: str,
    challenge_manifest: Mapping[str, Any],
    model_sha256: str,
    prompt_sha256: str | None = None,
) -> str:
    """Combine all immutable experiment inputs into one resume gate."""

    return canonical_sha256({
        "protocol_version": SEMANTIC_CHALLENGE_PROTOCOL,
        "workspace_snapshot_sha256": workspace_snapshot_sha256,
        "challenge_manifest_sha256": canonical_sha256(challenge_manifest),
        "model_signature": model_sha256,
        "prompt_signature": prompt_sha256 or prompt_signature(),
    })


def semantic_phase_signature(run_signature: str, phase: str) -> str:
    if phase not in {"clean", "mutant"}:
        raise ValueError("phase must be 'clean' or 'mutant'")
    return canonical_sha256({"run_signature": run_signature, "phase": phase})


def rows_contain_semantic_provenance(rows: Iterable[Mapping[str, Any]]) -> bool:
    return any(bool(_PROVENANCE_FIELDS.intersection(row)) for row in rows)


def render_workspace_semantic_markdown(
    challenge: WorkspaceSemanticChallenge,
    score: Mapping[str, Any],
    *,
    dataset: str | None = None,
) -> str:
    """Render a compact, interpretation-safe experiment report."""

    def metric(
        label: str, count_key: str, denominator_key: str, rate_key: str, ci_key: str,
    ) -> str:
        ci = score.get(ci_key) or [0.0, 0.0]
        ci_text = (
            "N/A"
            if ci[0] is None or ci[1] is None
            else f"[{float(ci[0]):.3f}, {float(ci[1]):.3f}]"
        )
        return (
            f"| {label} | {score.get(count_key, 0)}/{score.get(denominator_key, 0)} | "
            f"{float(score.get(rate_key, 0.0)):.3f} | "
            f"{ci_text} |"
        )

    lines = [
        "# Workspace-Bench paired semantic-grounding challenge",
        "",
        f"- Dataset: `{dataset or '(not recorded)'}`",
        f"- Source tasks: `{challenge.source_items}`",
        f"- Objective pairs: `{score.get('pairs', 0)}`",
        f"- Seed: `{challenge.seed}`",
        "- Each API request contains exactly one rubric from exactly one phase.",
        "- Pair labels and source mappings are stored only in the sidecar manifest.",
        "",
        "## Objective certificate coverage",
        "",
        "| Metric | Count | Rate | 95% Wilson CI |",
        "|---|---:|---:|---:|",
        metric(
            "Eligible objective decisions",
            "objective_certificate_eligible_decisions", "planned_decisions",
            "objective_certificate_decision_coverage",
            "objective_certificate_decision_coverage_wilson95",
        ),
        metric(
            "Clean target certified supported",
            "objective_certificate_clean_supported", "pairs",
            "objective_certificate_clean_supported_rate",
            "objective_certificate_clean_supported_wilson95",
        ),
        metric(
            "Mutant target certified unsupported",
            "objective_certificate_mutant_unsupported", "pairs",
            "objective_certificate_mutant_unsupported_rate",
            "objective_certificate_mutant_unsupported_wilson95",
        ),
        metric(
            "Fully certified supported -> unsupported pairs",
            "objective_certified_pairs", "pairs", "objective_certified_pair_rate",
            "objective_certified_pair_wilson95",
        ),
        "",
        "Certificates consume only canonical task text, canonical output contract, "
        "and the production input inventory; they do not consume pair labels, "
        "operator names, or challenge-sidecar truth.",
        "",
        "## Production final decisions (certificate-aware)",
        "",
        "| Metric | Count | Rate | 95% Wilson CI |",
        "|---|---:|---:|---:|",
        metric(
            "Unsupported-mutant recall (planned denominator)",
            "mutant_unsupported_hits", "pairs", "mutant_unsupported_recall",
            "mutant_unsupported_recall_wilson95",
        ),
        metric(
            "Clean non-unsupported", "clean_nonunsupported", "pairs",
            "clean_nonunsupported_rate", "clean_nonunsupported_wilson95",
        ),
        metric(
            "Paired discrimination", "paired_discriminated", "pairs",
            "paired_discrimination", "paired_discrimination_wilson95",
        ),
        metric(
            "Strict supported -> unsupported", "strict_paired_discriminated", "pairs",
            "strict_paired_discrimination", "strict_paired_discrimination_wilson95",
        ),
        metric(
            "Clean false alarms", "clean_false_alarms", "clean_evaluable",
            "clean_false_alarm_rate", "clean_false_alarm_wilson95",
        ),
        "",
        "## Citation-grounded model diagnostic (certificate excluded)",
        "",
        "| Metric | Count | Rate | 95% Wilson CI |",
        "|---|---:|---:|---:|",
        metric(
            "Grounded unsupported-mutant recall", "grounded_mutant_unsupported_hits",
            "pairs", "grounded_mutant_unsupported_recall",
            "grounded_mutant_unsupported_recall_wilson95",
        ),
        metric(
            "Grounded clean non-unsupported", "grounded_clean_nonunsupported",
            "pairs", "grounded_clean_nonunsupported_rate",
            "grounded_clean_nonunsupported_wilson95",
        ),
        metric(
            "Grounded paired discrimination", "grounded_paired_discriminated",
            "pairs", "grounded_paired_discrimination",
            "grounded_paired_discrimination_wilson95",
        ),
        metric(
            "Grounded strict supported -> unsupported",
            "grounded_strict_paired_discriminated", "pairs",
            "grounded_strict_paired_discrimination",
            "grounded_strict_paired_discrimination_wilson95",
        ),
        metric(
            "Grounded clean false alarms", "grounded_clean_false_alarms",
            "clean_evaluable", "grounded_clean_false_alarm_rate",
            "grounded_clean_false_alarm_wilson95",
        ),
        metric(
            "Grounded uncertain decisions", "grounded_uncertain_decisions",
            "planned_decisions", "grounded_uncertain_rate",
            "grounded_uncertain_wilson95",
        ),
        "",
        "## Raw LLM scanner diagnostic (not grounded)",
        "",
        "| Metric | Count | Rate | 95% Wilson CI |",
        "|---|---:|---:|---:|",
        metric(
            "Raw unsupported-mutant recall", "raw_mutant_unsupported_hits",
            "pairs", "raw_mutant_unsupported_recall",
            "raw_mutant_unsupported_recall_wilson95",
        ),
        metric(
            "Raw clean non-unsupported", "raw_clean_nonunsupported", "pairs",
            "raw_clean_nonunsupported_rate", "raw_clean_nonunsupported_wilson95",
        ),
        metric(
            "Raw paired discrimination", "raw_paired_discriminated", "pairs",
            "raw_paired_discrimination", "raw_paired_discrimination_wilson95",
        ),
        metric(
            "Raw strict supported -> unsupported",
            "raw_strict_paired_discriminated", "pairs",
            "raw_strict_paired_discrimination",
            "raw_strict_paired_discrimination_wilson95",
        ),
        metric(
            "Raw clean false alarms", "raw_clean_false_alarms", "clean_evaluable",
            "raw_clean_false_alarm_rate", "raw_clean_false_alarm_wilson95",
        ),
        metric(
            "Raw uncertain decisions", "raw_uncertain_decisions",
            "planned_decisions", "raw_uncertain_rate", "raw_uncertain_wilson95",
        ),
        "",
        "## Coverage and integrity",
        "",
        "| Metric | Count | Rate | 95% Wilson CI |",
        "|---|---:|---:|---:|",
        metric(
            "Inventory negative-proof eligibility",
            "inventory_confirmation_eligible_pairs",
            "inventory_absence_required_pairs",
            "inventory_confirmation_eligibility_rate",
            "inventory_confirmation_eligibility_wilson95",
        ),
        metric(
            "Semantic uncertain decisions", "uncertain_decisions", "planned_decisions",
            "uncertain_rate", "uncertain_wilson95",
        ),
        metric(
            "Operational-failure decisions", "operational_failure_decisions",
            "planned_decisions", "operational_failure_rate",
            "operational_failure_wilson95",
        ),
        metric(
            "Source tasks perfect on every operator", "source_complete_paired",
            "source_tasks", "source_complete_paired_rate",
            "source_complete_paired_wilson95",
        ),
        "",
        "Pair-level Wilson intervals are accompanied in `summary.json` by "
        "source-task cluster bootstrap intervals for the primary rates.",
        "",
        f"- Extra decisions: `{score.get('extra_decision_count', 0)}`",
        f"- Duplicate decisions: `{score.get('duplicate_decision_count', 0)}`",
        f"- Inapplicable pairs skipped: `{len(challenge.skipped)}`",
        "",
        "## By operator",
        "",
        "| Operator | Pairs | Certified pair | Production paired | Grounded paired | Raw paired | Grounded strict | Raw strict | Op failure |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for operator, row in sorted((score.get("per_operator") or {}).items()):
        lines.append(
            f"| `{operator}` | {row['pairs']} | "
            f"{row['objective_certified_pair_rate']:.3f} | "
            f"{row['paired_discrimination']:.3f} | "
            f"{row['grounded_paired_discrimination']:.3f} | "
            f"{row['raw_paired_discrimination']:.3f} | "
            f"{row['grounded_strict_paired_discrimination']:.3f} | "
            f"{row['raw_strict_paired_discrimination']:.3f} | "
            f"{row['operational_failure_rate']:.3f} |"
        )
    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        "These controlled pairs quantify sensitivity and paired specificity for four "
        "grounding mechanisms. They do not estimate defect prevalence or end-to-end "
        "accuracy on arbitrary unmodified benchmarks. A 100% certificate score means "
        "the narrow resolver grammar correctly grounds these controlled forms; it does "
        "not mean the LLM achieved 100% semantic accuracy. Raw scanner metrics expose "
        "the model ceiling, citation-grounded metrics expose evidence-binding loss, and "
        "production metrics show the final fail-closed decision path.",
        "",
    ])
    return "\n".join(lines)


def wilson_interval(
    successes: int,
    total: int,
    z: float = 1.959963984540054,
) -> tuple[float | None, float | None]:
    if total < 0:
        raise ValueError("total must be non-negative")
    if total == 0:
        return None, None
    if successes < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        (p * (1 - p) + z * z / (4 * total)) / total
    ) / denominator
    lower = 0.0 if successes == 0 else max(0.0, center - margin)
    upper = 1.0 if successes == total else min(1.0, center + margin)
    return lower, upper


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _apply_operator(
    source: dict[str, Any],
    operator: str,
    token: str,
    *,
    clean_id: str,
    mutant_id: str,
    visible_inputs: Sequence[_VisibleInput],
) -> tuple[_PairRows | None, str | None]:
    if operator == TASK_EXPLICIT_VS_HIDDEN_TITLE:
        requested_title = f"Orchid Review {token.upper()}"
        hidden_title = f"Cobalt Digest {token[::-1].upper()}"
        clean_rubric = (
            f'Does the primary requested artifact use the exact title "{requested_title}"?'
        )
        mutant_rubric = (
            f'Does the primary requested artifact use the exact title "{hidden_title}"?'
        )
        clean = _base_row(source, clean_id, clean_rubric)
        mutant = _base_row(source, mutant_id, mutant_rubric)
        instruction = (
            f'Use the exact title "{requested_title}" for the primary requested artifact.'
        )
        clean["task"] = _prepend_instruction(clean.get("task"), instruction)
        mutant["task"] = _prepend_instruction(mutant.get("task"), instruction)
        return _PairRows(
            clean,
            mutant,
            clean_rubric,
            mutant_rubric,
            "task",
            ("evaluator.rubrics", "rubrics"),
        ), None

    if operator == CONTRACT_REQUESTED_VS_HIDDEN_COMPANION_FILE:
        requested_filename = f"supporting_notes_{token}.md"
        hidden_filename = f"review_appendix_{token[::-1]}.md"
        clean_rubric = (
            f"Was the required companion file `{requested_filename}` created?"
        )
        mutant_rubric = (
            f"Was the required companion file `{hidden_filename}` created?"
        )
        clean = _base_row(source, clean_id, clean_rubric)
        mutant = _base_row(source, mutant_id, mutant_rubric)
        _add_required_output(clean, requested_filename)
        _add_required_output(mutant, requested_filename)
        return _PairRows(
            clean,
            mutant,
            clean_rubric,
            mutant_rubric,
            "output_contract",
            ("evaluator.rubrics", "rubrics"),
        ), None

    if operator == INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL:
        if not visible_inputs:
            return None, "requires at least one materialized auditor-visible input"
        actual = len(visible_inputs)
        wrong = actual + 1
        instruction = (
            "Also include an accurate count of the allowed visible input source files "
            "in the requested output."
        )
        clean_rubric = (
            "Does the requested output accurately state that there are exactly "
            f"{actual} allowed visible input source files?"
        )
        mutant_rubric = (
            "Does the requested output accurately state that there are exactly "
            f"{wrong} allowed visible input source files?"
        )
        clean = _base_row(source, clean_id, clean_rubric)
        mutant = _base_row(source, mutant_id, mutant_rubric)
        clean["task"] = _prepend_instruction(clean.get("task"), instruction)
        mutant["task"] = _prepend_instruction(mutant.get("task"), instruction)
        return _PairRows(
            clean,
            mutant,
            clean_rubric,
            mutant_rubric,
            "input_inventory",
            ("evaluator.rubrics", "rubrics"),
        ), None

    if operator == INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME:
        if not visible_inputs:
            return None, "requires at least one materialized auditor-visible input"
        names = sorted({value.logical_name for value in visible_inputs}, key=str.casefold)
        actual = names[0]
        nonexistent = f"source_register_{token}.dat"
        existing_casefold = {name.casefold() for name in names}
        while nonexistent.casefold() in existing_casefold:
            nonexistent = "x_" + nonexistent
        instruction = (
            "Also identify the allowed visible input source files by filename in the "
            "requested output."
        )
        clean_rubric = (
            f"Does the requested output identify `{actual}` as one of the allowed "
            "visible input source files?"
        )
        mutant_rubric = (
            f"Does the requested output identify `{nonexistent}` as one of the allowed "
            "visible input source files?"
        )
        clean = _base_row(source, clean_id, clean_rubric)
        mutant = _base_row(source, mutant_id, mutant_rubric)
        clean["task"] = _prepend_instruction(clean.get("task"), instruction)
        mutant["task"] = _prepend_instruction(mutant.get("task"), instruction)
        return _PairRows(
            clean,
            mutant,
            clean_rubric,
            mutant_rubric,
            "input_inventory",
            ("evaluator.rubrics", "rubrics"),
        ), None

    raise ValueError(f"unknown Workspace semantic operator: {operator}")


def _base_row(source: Mapping[str, Any], item_id: str, rubric: str) -> dict[str, Any]:
    row = copy.deepcopy(dict(source))
    _strip_provenance(row)
    row["item_id"] = item_id
    evaluator = row.get("evaluator")
    evaluator_type = (
        str(evaluator.get("type"))
        if isinstance(evaluator, Mapping) and evaluator.get("type")
        else "workspacebench_rubric"
    )
    row["evaluator"] = {
        "type": evaluator_type,
        "rubrics": [rubric],
        "rubric_types": ["Outcome Evaluation"],
    }
    _set_jsonish_list(row, "rubrics", [rubric])
    _set_jsonish_list(row, "rubric_types", ["Outcome Evaluation"])
    return row


def _add_required_output(row: dict[str, Any], filename: str) -> None:
    contract = row.get("output_contract")
    if not isinstance(contract, dict):
        contract = {"type": "workspace_files"}
        row["output_contract"] = contract
    required = contract.get("required_files")
    if not isinstance(required, list):
        required = contract.get("files") if isinstance(contract.get("files"), list) else []
    values = [str(value) for value in required]
    if filename not in values:
        values.insert(0, filename)
    contract["required_files"] = values
    # The controlled companion-file pair needs a closed-world contract to
    # certify both membership and absence without consulting challenge labels.
    contract["required_files_complete"] = True

    raw_outputs = parse_jsonish(row.get("output_files"), [])
    if not isinstance(raw_outputs, list):
        raw_outputs = []
    output_values = [str(value) for value in raw_outputs]
    if filename not in output_values:
        output_values.insert(0, filename)
    _set_jsonish_list(row, "output_files", output_values)
    context = row.get("context")
    if isinstance(context, dict):
        context_outputs = context.get("output_files")
        if not isinstance(context_outputs, list):
            context_outputs = output_values[:-1]
        context_values = [str(value) for value in context_outputs]
        if filename not in context_values:
            context_values.insert(0, filename)
        context["output_files"] = context_values


def _declare_synthetic_actor_inventory(
    row: dict[str, Any],
    visible_inputs: Sequence[_VisibleInput],
) -> None:
    """Freeze the complete actor view used by the controlled challenge.

    Public Workspace-Bench manifests describe a task-local subset of a larger
    role workspace.  Count and non-existence claims would therefore be open
    world.  The synthetic experiment instead declares its materialized allowed
    inputs and requested outputs to be the complete challenge workspace, on
    both sides of every pair.
    """

    names = [value.logical_name for value in visible_inputs]
    contract = row.get("output_contract")
    if isinstance(contract, Mapping):
        outputs = contract.get("required_files") or contract.get("files") or []
        if isinstance(outputs, list):
            names.extend(str(value) for value in outputs)
    inventory = list(dict.fromkeys(str(value) for value in names if str(value)))
    row["workspace_inventory"] = copy.deepcopy(inventory)
    row["workspace_inventory_complete"] = True
    context = row.get("context")
    if not isinstance(context, dict):
        context = {}
        row["context"] = context
    context["workspace_inventory"] = copy.deepcopy(inventory)
    context["workspace_inventory_complete"] = True


def _prepend_instruction(value: Any, instruction: str) -> str:
    """Keep controlled support visible under the production task prefix cap."""

    task = str(value or "").strip()
    return f"{instruction}\n\n{task}" if task else instruction


def _set_jsonish_list(row: dict[str, Any], key: str, values: list[Any]) -> None:
    original = row.get(key)
    row[key] = (
        json.dumps(values, ensure_ascii=False)
        if isinstance(original, str)
        else copy.deepcopy(values)
    )


def _visible_inputs(
    row: Mapping[str, Any],
    root: Path | None,
    *,
    allowed_roots: Iterable[Path] | None = None,
) -> list[_VisibleInput]:
    items = _items_for_rows([copy.deepcopy(dict(row))])
    if not items:
        return []
    visible: list[_VisibleInput] = []
    for record in workspace_input_path_records(
        items[0], root, allowed_roots=allowed_roots,
    ):
        path = record["path"]
        if (
            not record["allowed"]
            or not path.is_file()
            or REFERENCE_GENERATOR_NAME.search(path.name)
        ):
            continue
        visible.append(_VisibleInput(path, _logical_name_for_path(row, path)))
    return sorted(visible, key=lambda value: (value.logical_name.casefold(), value.path.name))


def _logical_name_for_path(row: Mapping[str, Any], path: Path) -> str:
    context = row.get("context")
    manifest = context.get("data_manifest") if isinstance(context, Mapping) else None
    if not isinstance(manifest, list):
        manifest = parse_jsonish(row.get("data_manifest"), [])
    if isinstance(manifest, list):
        for entry in manifest:
            if not isinstance(entry, Mapping):
                continue
            stored = Path(str(entry.get("stored_relpath") or "")).name.casefold()
            if stored and stored == path.name.casefold() and entry.get("filename"):
                return str(entry["filename"])
    return logical_input_name(path)


def _strip_provenance(row: dict[str, Any]) -> None:
    for key in _PROVENANCE_FIELDS:
        row.pop(key, None)


def _assert_auditor_row(row: Mapping[str, Any]) -> None:
    if _PROVENANCE_FIELDS.intersection(row):
        raise ValueError("provenance field present in auditor-visible row")
    evaluator = row.get("evaluator")
    if not isinstance(evaluator, Mapping):
        raise ValueError("semantic challenge row requires an evaluator object")
    rubrics = evaluator.get("rubrics")
    if not isinstance(rubrics, list) or len(rubrics) != 1 or not str(rubrics[0]).strip():
        raise ValueError("semantic challenge row must contain exactly one non-empty rubric")


def _validate_challenge(challenge: WorkspaceSemanticChallenge) -> None:
    clean_ids = [str(row.get("item_id") or "") for row in challenge.clean_rows]
    mutant_ids = [str(row.get("item_id") or "") for row in challenge.mutant_rows]
    if len(clean_ids) != len(set(clean_ids)):
        raise ValueError("duplicate clean challenge item ID")
    if len(mutant_ids) != len(set(mutant_ids)):
        raise ValueError("duplicate mutant challenge item ID")
    if set(clean_ids).intersection(mutant_ids):
        raise ValueError("clean and mutant challenge item IDs overlap")
    if len(challenge.provenance) != len(clean_ids) or len(clean_ids) != len(mutant_ids):
        raise ValueError("semantic challenge rows and provenance are not one-to-one")
    if {row.clean_item_id for row in challenge.provenance} != set(clean_ids):
        raise ValueError("clean IDs do not align with provenance")
    if {row.mutant_item_id for row in challenge.provenance} != set(mutant_ids):
        raise ValueError("mutant IDs do not align with provenance")
    if rows_contain_semantic_provenance(challenge.clean_rows):
        raise ValueError("provenance leaked into clean rows")
    if rows_contain_semantic_provenance(challenge.mutant_rows):
        raise ValueError("provenance leaked into mutant rows")


def _phase_expected_ids(
    challenge: WorkspaceSemanticChallenge,
    phase: str,
) -> set[str]:
    if phase == "clean":
        return {row.clean_item_id for row in challenge.provenance}
    return {row.mutant_item_id for row in challenge.provenance}


def _items_for_rows(rows: Sequence[dict[str, Any]]) -> list[BenchmarkItem]:
    if not rows:
        return []
    materialized = list(rows)
    return build_items(materialized, load_mapping(None, materialized))


def _single_rubric(item: BenchmarkItem) -> str:
    evaluator = item.evaluator if isinstance(item.evaluator, dict) else {}
    rubrics = evaluator.get("rubrics")
    if not isinstance(rubrics, list) or len(rubrics) != 1:
        raise ValueError(f"item {item.item_id} does not contain exactly one rubric")
    rubric = str(rubrics[0]).strip()
    if not rubric:
        raise ValueError(f"item {item.item_id} contains an empty rubric")
    return rubric


def _decision_matches_current(
    row: Mapping[str, Any],
    item: BenchmarkItem,
    bundle: WorkspaceEvidenceBundle,
) -> bool:
    try:
        rubric_index = int(row.get("rubric_index"))
    except (TypeError, ValueError):
        return False
    return bool(
        str(row.get("item_id") or "") == item.item_id
        and rubric_index == 0
        and str(row.get("rubric") or "") == _single_rubric(item)
        and str(row.get("evidence_bundle_sha256") or "") == bundle.sha256
        and str(row.get("artifact_manifest_sha256") or "")
        == bundle.artifact_manifest_sha256
    )


def workspace_semantic_evidence_view_key(item: BenchmarkItem) -> str:
    """Fingerprint every item field that can change its evidence bundle.

    Attachment bytes and manifest names determine the rendered evidence, while
    the declared complete actor inventory and output contract determine whether
    inventory absence is confirmation-eligible.  Grouping only by input paths
    would accidentally reuse completeness metadata across different contracts.
    """

    context = item.context if isinstance(item.context, dict) else {}
    return canonical_sha256({
        "input_files": item.raw.get("input_files"),
        "data_manifest": context.get("data_manifest", item.raw.get("data_manifest")),
        "output_contract": item.output_contract,
        "workspace_inventory_complete": context.get(
            "workspace_inventory_complete",
            item.raw.get("workspace_inventory_complete"),
        ),
        "workspace_inventory": context.get(
            "workspace_inventory",
            item.raw.get("workspace_inventory"),
        ),
    })


def _build_phase_bundles(
    items: Sequence[BenchmarkItem],
    *,
    root: Path | None,
    workers: int,
    evidence_chars: int,
    allowed_roots: Iterable[Path] | None,
) -> tuple[dict[str, WorkspaceEvidenceBundle], dict[str, str]]:
    groups: dict[str, list[BenchmarkItem]] = defaultdict(list)
    for item in items:
        groups[workspace_semantic_evidence_view_key(item)].append(item)
    bundle_by_group: dict[str, WorkspaceEvidenceBundle] = {}
    failure_by_group: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(max(1, workers), max(1, len(groups)))) as pool:
        futures = {
            pool.submit(
                build_workspace_evidence_bundle,
                group_items[0],
                root,
                max_chars=evidence_chars,
                allowed_roots=allowed_roots,
            ): key
            for key, group_items in groups.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                bundle_by_group[key] = future.result()
            except Exception as exc:
                failure_by_group[key] = f"{type(exc).__name__}: {exc}"[:1000]
    bundles: dict[str, WorkspaceEvidenceBundle] = {}
    failures: dict[str, str] = {}
    for key, group_items in groups.items():
        for item in group_items:
            if key in bundle_by_group:
                bundles[item.item_id] = bundle_by_group[key]
            else:
                failures[item.item_id] = failure_by_group.get(
                    key, "unknown evidence-bundle failure",
                )
    return bundles, failures


def _operational_decision(
    item: BenchmarkItem,
    rubric: str,
    reason: str,
) -> dict[str, Any]:
    scanner = {
        "label": "uncertain",
        "confidence": 0.0,
        "reason": reason[:1000],
        "operational_failure": True,
    }
    return {
        "item_id": item.item_id,
        "rubric_index": 0,
        "rubric": rubric,
        "label": "uncertain",
        "confidence": 0.0,
        "requirement_type": "other",
        "atomic_requirement": rubric,
        "reason": reason[:2000],
        "evidence": [],
        "missing_assumption": "",
        "scanner": scanner,
        "verifier": None,
        "evidence_bundle_sha256": "",
        "artifact_manifest_sha256": "",
        "indexed_files": [],
        "readable_files": [],
        "partial_files": [],
        "excluded_files": [],
        "parse_failures": [],
        "blocked_files": [],
        "actor_view_complete": False,
        "input_inventory_complete": False,
        "inventory_absence_is_confirmation_eligible": False,
        "bundle_truncated": False,
        "artifact_identity_failures": [],
        "citation_validation": {
            "all_claimed_valid": False,
            "valid_support_count": 0,
            "valid_contradiction_count": 0,
            "gate_reason": "operational_failure",
            "objective_certificate": {
                "version": OBJECTIVE_CITATION_RESOLVER_VERSION,
                "applicable": False,
                "eligible": False,
                "label": None,
                "certificate_type": "operational_failure",
            },
            "actor_view_complete": False,
            "input_inventory_complete": False,
            "inventory_absence_is_confirmation_eligible": False,
            "negative_absence_is_confirmation_eligible": False,
        },
        "total_input_bytes": 0,
    }


def _aggregate_semantic_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pairs = len(rows)
    planned_decisions = pairs * 2
    mutant_hits = sum(bool(row["mutant_unsupported_hit"]) for row in rows)
    clean_nonunsupported = sum(bool(row["clean_nonunsupported"]) for row in rows)
    paired = sum(bool(row["paired_discriminated"]) for row in rows)
    strict_paired = sum(bool(row["strict_paired_discriminated"]) for row in rows)
    clean_evaluable = sum(bool(row["clean_evaluable"]) for row in rows)
    mutant_evaluable = sum(bool(row["mutant_evaluable"]) for row in rows)
    clean_fp = sum(bool(row["clean_false_alarm"]) for row in rows)
    uncertain = sum(
        bool(row["clean_uncertain"]) + bool(row["mutant_uncertain"])
        for row in rows
    )
    operational_decisions = sum(
        bool(row["clean_operational_failure"])
        + bool(row["mutant_operational_failure"])
        for row in rows
    )
    operational_pairs = sum(
        bool(row["clean_operational_failure"] or row["mutant_operational_failure"])
        for row in rows
    )
    integrity_pairs = sum(bool(row["integrity_failure"]) for row in rows)
    inventory_required_pairs = sum(
        bool(row["inventory_absence_required"]) for row in rows
    )
    inventory_eligible_pairs = sum(
        bool(
            row["inventory_absence_required"]
            and row["inventory_absence_is_confirmation_eligible"]
        )
        for row in rows
    )
    by_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_source[str(row["source_item_id"])].append(row)
    source_tasks = len(by_source)
    source_complete_mutant = sum(
        all(bool(row["mutant_unsupported_hit"]) for row in source_rows)
        for source_rows in by_source.values()
    )
    source_complete_paired = sum(
        all(bool(row["paired_discriminated"]) for row in source_rows)
        for source_rows in by_source.values()
    )
    source_complete_strict = sum(
        all(bool(row["strict_paired_discriminated"]) for row in source_rows)
        for source_rows in by_source.values()
    )
    cluster_bootstrap = _source_cluster_bootstrap(rows)
    raw_metrics = _aggregate_diagnostic_layer(rows, "raw")
    grounded_metrics = _aggregate_diagnostic_layer(rows, "grounded")
    certificate_clean = sum(
        bool(row["clean_objective_certificate_supported"]) for row in rows
    )
    certificate_mutant = sum(
        bool(row["mutant_objective_certificate_unsupported"]) for row in rows
    )
    certified_pairs = sum(bool(row["objective_certified_pair"]) for row in rows)
    certificate_eligible_decisions = sum(
        row.get(key) in {"supported", "unsupported"}
        for row in rows
        for key in (
            "clean_objective_certificate_label",
            "mutant_objective_certificate_label",
        )
    )
    return {
        "pairs": pairs,
        "planned_decisions": planned_decisions,
        "clean_evaluable": clean_evaluable,
        "mutant_evaluable": mutant_evaluable,
        "mutant_unsupported_hits": mutant_hits,
        "mutant_unsupported_recall": _rate(mutant_hits, pairs),
        "mutant_unsupported_recall_wilson95": list(wilson_interval(mutant_hits, pairs)),
        "mutant_unsupported_observed_rate": _rate(mutant_hits, mutant_evaluable),
        "mutant_unsupported_observed_wilson95": list(
            wilson_interval(mutant_hits, mutant_evaluable)
        ),
        "clean_nonunsupported": clean_nonunsupported,
        "clean_nonunsupported_rate": _rate(clean_nonunsupported, pairs),
        "clean_nonunsupported_wilson95": list(
            wilson_interval(clean_nonunsupported, pairs)
        ),
        "paired_discriminated": paired,
        "paired_discrimination": _rate(paired, pairs),
        "paired_discrimination_wilson95": list(wilson_interval(paired, pairs)),
        "strict_paired_discriminated": strict_paired,
        "strict_paired_discrimination": _rate(strict_paired, pairs),
        "strict_paired_discrimination_wilson95": list(
            wilson_interval(strict_paired, pairs)
        ),
        "clean_false_alarms": clean_fp,
        "clean_false_alarm_rate": _rate(clean_fp, clean_evaluable),
        "clean_false_alarm_wilson95": list(wilson_interval(clean_fp, clean_evaluable)),
        "uncertain_decisions": uncertain,
        "uncertain_rate": _rate(uncertain, planned_decisions),
        "uncertain_wilson95": list(wilson_interval(uncertain, planned_decisions)),
        "operational_failure_decisions": operational_decisions,
        "operational_failure_rate": _rate(operational_decisions, planned_decisions),
        "operational_failure_wilson95": list(
            wilson_interval(operational_decisions, planned_decisions)
        ),
        "operational_failure_pairs": operational_pairs,
        "operational_failure_pair_rate": _rate(operational_pairs, pairs),
        "operational_failure_pair_wilson95": list(
            wilson_interval(operational_pairs, pairs)
        ),
        "integrity_failure_pairs": integrity_pairs,
        "integrity_failure_pair_rate": _rate(integrity_pairs, pairs),
        "integrity_failure_pair_wilson95": list(
            wilson_interval(integrity_pairs, pairs)
        ),
        "inventory_absence_required_pairs": inventory_required_pairs,
        "inventory_confirmation_eligible_pairs": inventory_eligible_pairs,
        "inventory_confirmation_eligibility_rate": _rate(
            inventory_eligible_pairs, inventory_required_pairs,
        ),
        "inventory_confirmation_eligibility_wilson95": list(
            wilson_interval(inventory_eligible_pairs, inventory_required_pairs)
        ),
        # Four operator rows from one source task are correlated.  These
        # all-operators-per-source metrics provide a conservative task-level
        # complement to the required pair-level Wilson intervals.
        "source_tasks": source_tasks,
        "source_complete_mutant": source_complete_mutant,
        "source_complete_mutant_rate": _rate(source_complete_mutant, source_tasks),
        "source_complete_mutant_wilson95": list(
            wilson_interval(source_complete_mutant, source_tasks)
        ),
        "source_complete_paired": source_complete_paired,
        "source_complete_paired_rate": _rate(source_complete_paired, source_tasks),
        "source_complete_paired_wilson95": list(
            wilson_interval(source_complete_paired, source_tasks)
        ),
        "source_complete_strict": source_complete_strict,
        "source_complete_strict_rate": _rate(source_complete_strict, source_tasks),
        "source_complete_strict_wilson95": list(
            wilson_interval(source_complete_strict, source_tasks)
        ),
        "source_cluster_bootstrap95": cluster_bootstrap,
        # The three layers are intentionally separate:
        # raw = scanner semantic label; grounded = citation-gated model label;
        # production = top-level label, which may be objectively overridden.
        **raw_metrics,
        **grounded_metrics,
        "objective_certificate_eligible_decisions": certificate_eligible_decisions,
        "objective_certificate_decision_coverage": _rate(
            certificate_eligible_decisions, planned_decisions,
        ),
        "objective_certificate_decision_coverage_wilson95": list(
            wilson_interval(certificate_eligible_decisions, planned_decisions)
        ),
        "objective_certificate_clean_supported": certificate_clean,
        "objective_certificate_clean_supported_rate": _rate(
            certificate_clean, pairs,
        ),
        "objective_certificate_clean_supported_wilson95": list(
            wilson_interval(certificate_clean, pairs)
        ),
        "objective_certificate_mutant_unsupported": certificate_mutant,
        "objective_certificate_mutant_unsupported_rate": _rate(
            certificate_mutant, pairs,
        ),
        "objective_certificate_mutant_unsupported_wilson95": list(
            wilson_interval(certificate_mutant, pairs)
        ),
        "objective_certified_pairs": certified_pairs,
        "objective_certified_pair_rate": _rate(certified_pairs, pairs),
        "objective_certified_pair_wilson95": list(
            wilson_interval(certified_pairs, pairs)
        ),
    }


def _aggregate_diagnostic_layer(
    rows: Sequence[Mapping[str, Any]],
    prefix: str,
) -> dict[str, Any]:
    """Aggregate raw or citation-grounded labels on planned denominators."""

    pairs = len(rows)
    planned_decisions = pairs * 2
    hits = sum(bool(row[f"{prefix}_mutant_unsupported_hit"]) for row in rows)
    clean_nonunsupported = sum(
        bool(row[f"{prefix}_clean_nonunsupported"]) for row in rows
    )
    paired = sum(bool(row[f"{prefix}_paired_discriminated"]) for row in rows)
    strict = sum(
        bool(row[f"{prefix}_strict_paired_discriminated"]) for row in rows
    )
    clean_fp = sum(bool(row[f"{prefix}_clean_false_alarm"]) for row in rows)
    clean_evaluable = sum(bool(row["clean_evaluable"]) for row in rows)
    uncertain = sum(
        bool(row[f"{prefix}_clean_uncertain"])
        + bool(row[f"{prefix}_mutant_uncertain"])
        for row in rows
    )
    by_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_source[str(row["source_item_id"])].append(row)
    source_tasks = len(by_source)
    source_complete_paired = sum(
        all(bool(row[f"{prefix}_paired_discriminated"]) for row in source_rows)
        for source_rows in by_source.values()
    )
    return {
        f"{prefix}_mutant_unsupported_hits": hits,
        f"{prefix}_mutant_unsupported_recall": _rate(hits, pairs),
        f"{prefix}_mutant_unsupported_recall_wilson95": list(
            wilson_interval(hits, pairs)
        ),
        f"{prefix}_clean_nonunsupported": clean_nonunsupported,
        f"{prefix}_clean_nonunsupported_rate": _rate(clean_nonunsupported, pairs),
        f"{prefix}_clean_nonunsupported_wilson95": list(
            wilson_interval(clean_nonunsupported, pairs)
        ),
        f"{prefix}_paired_discriminated": paired,
        f"{prefix}_paired_discrimination": _rate(paired, pairs),
        f"{prefix}_paired_discrimination_wilson95": list(
            wilson_interval(paired, pairs)
        ),
        f"{prefix}_strict_paired_discriminated": strict,
        f"{prefix}_strict_paired_discrimination": _rate(strict, pairs),
        f"{prefix}_strict_paired_discrimination_wilson95": list(
            wilson_interval(strict, pairs)
        ),
        f"{prefix}_clean_false_alarms": clean_fp,
        f"{prefix}_clean_false_alarm_rate": _rate(clean_fp, clean_evaluable),
        f"{prefix}_clean_false_alarm_wilson95": list(
            wilson_interval(clean_fp, clean_evaluable)
        ),
        f"{prefix}_uncertain_decisions": uncertain,
        f"{prefix}_uncertain_rate": _rate(uncertain, planned_decisions),
        f"{prefix}_uncertain_wilson95": list(
            wilson_interval(uncertain, planned_decisions)
        ),
        f"{prefix}_source_complete_paired": source_complete_paired,
        f"{prefix}_source_complete_paired_rate": _rate(
            source_complete_paired, source_tasks,
        ),
        f"{prefix}_source_complete_paired_wilson95": list(
            wilson_interval(source_complete_paired, source_tasks)
        ),
    }


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _source_cluster_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    *,
    iterations: int = 2_000,
    seed: int = 20260714,
) -> dict[str, list[float | None]]:
    """Resample source tasks, retaining all correlated operator rows."""

    by_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_source[str(row["source_item_id"])].append(row)
    source_ids = sorted(by_source)
    metrics = (
        "mutant_unsupported_recall",
        "paired_discrimination",
        "strict_paired_discrimination",
        "clean_false_alarm_rate",
    )
    if not source_ids or iterations <= 0:
        return {metric: [None, None] for metric in metrics}
    samples: dict[str, list[float]] = {metric: [] for metric in metrics}
    rng = random.Random(seed)
    for _ in range(iterations):
        sampled_rows = [
            row
            for _ in source_ids
            for row in by_source[rng.choice(source_ids)]
        ]
        total = len(sampled_rows)
        mutant = sum(bool(row["mutant_unsupported_hit"]) for row in sampled_rows)
        paired = sum(bool(row["paired_discriminated"]) for row in sampled_rows)
        strict = sum(bool(row["strict_paired_discriminated"]) for row in sampled_rows)
        evaluable_clean = sum(bool(row["clean_evaluable"]) for row in sampled_rows)
        clean_fp = sum(bool(row["clean_false_alarm"]) for row in sampled_rows)
        samples["mutant_unsupported_recall"].append(_rate(mutant, total))
        samples["paired_discrimination"].append(_rate(paired, total))
        samples["strict_paired_discrimination"].append(_rate(strict, total))
        if evaluable_clean:
            samples["clean_false_alarm_rate"].append(_rate(clean_fp, evaluable_clean))
    return {
        metric: _percentile_interval(values)
        for metric, values in samples.items()
    }


def _percentile_interval(values: Sequence[float]) -> list[float | None]:
    if not values:
        return [None, None]
    ordered = sorted(values)
    low = ordered[int(0.025 * (len(ordered) - 1))]
    high = ordered[int(0.975 * (len(ordered) - 1))]
    return [low, high]


def _provenance_dict(value: WorkspaceSemanticProvenance | Mapping[str, Any]) -> dict[str, Any]:
    return asdict(value) if isinstance(value, WorkspaceSemanticProvenance) else dict(value)


def _decision_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return dict(result)
    raise TypeError(f"unsupported decision type: {type(value).__name__}")


def _validate_provenance_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    pair_ids = [str(row.get("pair_id") or "") for row in rows]
    clean_ids = [str(row.get("clean_item_id") or "") for row in rows]
    mutant_ids = [str(row.get("mutant_item_id") or "") for row in rows]
    if any(not value for value in [*pair_ids, *clean_ids, *mutant_ids]):
        raise ValueError("provenance IDs must be non-empty")
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("duplicate semantic pair ID")
    if len(clean_ids) != len(set(clean_ids)) or len(mutant_ids) != len(set(mutant_ids)):
        raise ValueError("duplicate semantic challenge item ID")
    if set(clean_ids).intersection(mutant_ids):
        raise ValueError("clean and mutant semantic IDs overlap")


def _decision_label(row: Mapping[str, Any] | None) -> str | None:
    if row is None:
        return None
    label = str(row.get("label") or "uncertain").strip().casefold()
    return label if label in _VALID_LABELS else "uncertain"


def _normalized_semantic_label(value: Any) -> str:
    label = str(value or "uncertain").strip().casefold().replace("-", "_")
    aliases = {
        "grounded": "supported",
        "有依据": "supported",
        "not_grounded": "unsupported",
        "ungrounded": "unsupported",
        "无依据": "unsupported",
        "无法判断": "uncertain",
        "unknown": "uncertain",
    }
    label = aliases.get(label, label)
    return label if label in _VALID_LABELS else "uncertain"


def _raw_scanner_label(row: Mapping[str, Any] | None) -> str | None:
    """Return the scanner's direct semantic classification, before grounding.

    This deliberately excludes objective certificate overrides.  Operationally
    malformed scanner responses remain ``uncertain`` and are separately removed
    from evaluable denominators by the scorer's coverage gate.
    """

    if row is None:
        return None
    scanner = row.get("scanner")
    if not isinstance(scanner, Mapping):
        return "uncertain"
    return _normalized_semantic_label(scanner.get("label"))


def _grounded_model_label(row: Mapping[str, Any] | None) -> str | None:
    """Return the citation-gated model label without deterministic override."""

    if row is None:
        return None
    validation = row.get("citation_validation")
    if not isinstance(validation, Mapping):
        # Legacy decisions without an explicit split used their final label as
        # the grounded model verdict unless a certificate override was present.
        return _decision_label(row)
    stored = validation.get("grounded_label_without_objective_certificate")
    if stored is not None:
        return _normalized_semantic_label(stored)

    # Backward-compatible reconstruction for earlier decision artifacts.  It is
    # exact for scanner-only rows and conservative when legacy verifier state
    # cannot be reconstructed.
    base = validation.get("semantic_label_before_citation_gate")
    label = (
        _normalized_semantic_label(base)
        if base is not None
        else _raw_scanner_label(row) or "uncertain"
    )
    if not bool(validation.get("all_claimed_valid", False)):
        return "uncertain"
    if label == "supported" and int(validation.get("valid_support_count") or 0) == 0:
        return "uncertain"
    if (
        label == "unsupported"
        and int(validation.get("valid_contradiction_count") or 0) == 0
        and row.get("actor_view_complete") is not True
    ):
        return "uncertain"
    return label


def _objective_certificate_label(row: Mapping[str, Any] | None) -> str | None:
    if row is None:
        return None
    validation = row.get("citation_validation")
    if not isinstance(validation, Mapping):
        return None
    certificate = validation.get("objective_certificate")
    if not isinstance(certificate, Mapping) or certificate.get("eligible") is not True:
        return None
    label = _normalized_semantic_label(certificate.get("label"))
    return label if label in {"supported", "unsupported"} else None


def _scored_decision_matches_provenance(
    row: Mapping[str, Any] | None,
    *,
    item_id: str,
    requirement: str,
) -> bool:
    if row is None:
        return False
    try:
        index = int(row.get("rubric_index"))
    except (TypeError, ValueError):
        return False
    return bool(
        str(row.get("item_id") or "") == item_id
        and index == 0
        and str(row.get("rubric") or "") == requirement
    )


def _paired_hash_matches(
    clean: Mapping[str, Any] | None,
    mutant: Mapping[str, Any] | None,
    key: str,
) -> bool:
    if clean is None or mutant is None:
        return False
    clean_value = str(clean.get(key) or "")
    mutant_value = str(mutant.get(key) or "")
    return bool(clean_value and clean_value == mutant_value)


def _last_by_id(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row.get("item_id") or "")
        if item_id:
            out[item_id] = dict(row)
    return out


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _write_part(parts_dir: Path, item_id: str, row: Mapping[str, Any]) -> None:
    parts_dir.mkdir(parents=True, exist_ok=True)
    filename = hashlib.sha256(item_id.encode("utf-8")).hexdigest() + ".json"
    _atomic_write_text(
        parts_dir / filename,
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n",
    )


def _atomic_write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    text = "".join(
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows
    )
    _atomic_write_text(path, text)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}"
    )
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


def _opaque_digest(namespace: str, seed: int, *parts: str) -> str:
    payload = ":".join([namespace, str(seed), *parts])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _opaque_item_id(seed: int, source_id: str, operator: str, side: str) -> str:
    digest = _opaque_digest("workspace-semantic-item", seed, source_id, operator, side)
    return f"workspace-semantic-{digest}"


def _portable_source_row(row: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(row))
    paths = value.get("input_files")
    if isinstance(paths, list):
        value["input_files"] = [Path(str(path)).name for path in paths]
    _strip_provenance(value)
    return value
