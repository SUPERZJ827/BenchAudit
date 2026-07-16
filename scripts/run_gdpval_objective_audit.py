#!/usr/bin/env python3
"""Run the deterministic GDPval v2 objective-integrity audit.

This experiment has two explicit layers:

* all records receive an offline metadata/rubric/manifest census;
* selected tasks may additionally materialize commit-pinned XLSX artifacts and
  replay column contracts against a bounded OOXML cell snapshot.

No LLM is used.  Findings are still passed through BenchCore's fail-closed
promotion registry, so an unregistered or non-replayable observation remains
review-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Keep the documented ``python scripts/...`` entry point working from a source
# checkout without requiring an editable install or a caller-supplied
# ``PYTHONPATH``.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from benchcore.auditor import audit_items_with_ledger
from benchcore.gdpval_artifacts import GDPvalArtifactResolver
from benchcore.gdpval_objective import (
    DEFAULT_GDPVAL_REVISION,
    GDPVAL_PREDICATE_VERSION,
    GDPValDatasetIntegrityChecker,
    GDPValRecordIntegrityChecker,
    GDPValWorkbookReplayChecker,
    build_gdpval_items,
    gdpval_mapping,
    parse_rubrics,
)
from benchcore.loader import load_rows
from benchcore.methods import DuplicateConflictChecker
from benchcore.report import build_report, write_json_report, write_markdown_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Pinned GDPval v2 Parquet/JSON/JSONL input")
    parser.add_argument(
        "--dataset-revision",
        default=DEFAULT_GDPVAL_REVISION,
        help="Immutable 40-hex openai/gdpval Hugging Face revision",
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--artifact-cache",
        help="Private content-addressed cache used for optional artifact replay",
    )
    parser.add_argument(
        "--deep-task-id",
        action="append",
        default=[],
        help="Task ID to include in pinned XLSX replay; repeat for multiple tasks",
    )
    parser.add_argument(
        "--deep-all-applicable",
        action="store_true",
        help="Replay every task with supported column claims and an unambiguous XLSX",
    )
    parser.add_argument(
        "--download-artifacts",
        action="store_true",
        help="Explicitly authorize pinned GDPval artifact downloads; otherwise cache-only",
    )
    parser.add_argument("--max-artifact-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def _hash_regular_file(path: Path) -> tuple[str, int]:
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    size = 0
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"audit snapshot is not a regular file: {path}")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or after.st_size != size
        ):
            raise RuntimeError(f"audit snapshot changed while hashing: {path}")
        return digest.hexdigest(), size
    finally:
        os.close(descriptor)


def _census(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rubric_items = 0
    rubric_parse_failures = 0
    for row in rows:
        try:
            rubric_items += len(parse_rubrics(row.get("rubric_json")))
        except ValueError:
            rubric_parse_failures += 1
    def list_length(row: dict[str, Any], key: str) -> int:
        value = row.get(key)
        return len(value) if isinstance(value, list) else 0

    return {
        "rows": len(rows),
        "unique_task_ids": len({str(row.get("task_id")) for row in rows}),
        "empty_prompts": sum(not str(row.get("prompt") or "").strip() for row in rows),
        "rubric_items": rubric_items,
        "rubric_parse_failures": rubric_parse_failures,
        "reference_artifacts_declared": sum(
            list_length(row, "reference_files") for row in rows
        ),
        "deliverable_artifacts_declared": sum(
            list_length(row, "deliverable_files") for row in rows
        ),
        "tasks_without_reference_artifacts": sum(
            list_length(row, "reference_files") == 0 for row in rows
        ),
        "tasks_without_deliverable_artifacts": sum(
            list_length(row, "deliverable_files") == 0 for row in rows
        ),
    }


def _code_provenance() -> dict[str, Any]:
    source_paths = sorted((REPOSITORY_ROOT / "benchcore").rglob("*.py"))
    source_paths.append(Path(__file__).resolve())
    files: dict[str, dict[str, Any]] = {}
    for source_path in source_paths:
        relative = source_path.relative_to(REPOSITORY_ROOT).as_posix()
        digest, size = _hash_regular_file(source_path)
        files[relative] = {"sha256": digest, "size_bytes": size}
    canonical = json.dumps(
        files, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    return {
        "schema_version": "gdpval-objective-code-manifest-v1",
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "files": files,
        "git": {"commit": commit, "dirty": dirty},
    }


def _confirmed_atomic_keys(finding: dict[str, Any]) -> set[str]:
    """Return explicitly defined, mechanically deduplicated assertions."""

    evidence = finding.get("evidence") or {}
    atom = evidence.get("atom") or {}
    kind = atom.get("kind")
    physical_row = finding.get("row_uid") or finding.get("item_id")
    identities: list[dict[str, Any]] = []
    if kind == "exact_filename_absent":
        identities.append({
            "row_uid": physical_row,
            "kind": kind,
            "artifact_role": atom.get("artifact_role"),
            "expected_basename": atom.get("expected_basename"),
            "observed_basenames": atom.get("observed_basenames"),
        })
    elif kind == "output_format_mismatch":
        identities.append({
            "row_uid": physical_row,
            "kind": kind,
            "expected_extension": atom.get("expected_extension"),
            "observed_extension": atom.get("observed_extension"),
            "observed_basenames": atom.get("observed_basenames"),
        })
    elif kind == "workbook_header_column_mismatch":
        identities.extend({
            "row_uid": physical_row,
            "kind": kind,
            "scope": mismatch.get("scope"),
            "role": mismatch.get("role"),
            "expected_column": mismatch.get("expected_column"),
            "observed_columns": mismatch.get("observed_columns"),
            "artifact_sha256s": atom.get("artifact_sha256s"),
        } for mismatch in atom.get("mismatches") or [])
    elif kind == "incompatible_column_role_claims":
        identities.extend({
            "row_uid": physical_row,
            "kind": kind,
            "conflict": conflict,
        } for conflict in atom.get("conflicts") or [])
    if not identities:
        identities.append({
            "row_uid": physical_row,
            "fact_signature": evidence.get("fact_signature"),
        })
    return {
        hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for identity in identities
    }


def _snapshot_input(input_path: Path, out_dir: Path) -> tuple[Path, str, int]:
    """Copy one opened source inode to a content-addressed audit snapshot."""

    source_fd = os.open(input_path, os.O_RDONLY | os.O_CLOEXEC)
    temporary_path: Path | None = None
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"GDPval input is not a regular file: {input_path}")
        temporary_fd, temporary_name = tempfile.mkstemp(
            prefix=".gdpval-source-",
            suffix=input_path.suffix,
            dir=out_dir,
        )
        temporary_path = Path(temporary_name)
        digest = hashlib.sha256()
        with os.fdopen(temporary_fd, "wb", closefd=True) as destination:
            while True:
                block = os.read(source_fd, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
                destination.write(block)
            destination.flush()
            os.fsync(destination.fileno())
        after = os.fstat(source_fd)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise RuntimeError("GDPval input changed while the audit snapshot was created")
        value = digest.hexdigest()
        snapshot = out_dir / f"source-{value}{input_path.suffix.lower()}"
        try:
            os.link(temporary_path, snapshot)
        except FileExistsError:
            existing_digest, existing_size = _hash_regular_file(snapshot)
            if existing_digest != value or existing_size != after.st_size:
                raise RuntimeError("content-addressed GDPval snapshot collision")
        os.chmod(snapshot, 0o400)
        committed_digest, committed_size = _hash_regular_file(snapshot)
        if committed_digest != value or committed_size != after.st_size:
            raise RuntimeError("GDPval snapshot changed during commit")
        return snapshot, value, committed_size
    finally:
        os.close(source_fd)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _write_summary(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    census = report["gdpval_objective"]["census"]
    findings = report["violations"]
    confirmed = [row for row in findings if row["evidence_tier"] == "confirmed"]
    review = [row for row in findings if row["evidence_tier"] == "review"]
    unknown = [row for row in findings if row["evidence_tier"] == "unknown"]
    confirmed_atomic_assertions: set[str] = set()
    for row in confirmed:
        confirmed_atomic_assertions.update(_confirmed_atomic_keys(row))
    coverage = summary.get("audit_coverage") or {}
    implementation = (report.get("run_metadata") or {}).get("implementation") or {}
    lines = [
        "# GDPval v2 Objective Integrity Audit",
        "",
        "> Scope: deterministic benchmark-artifact consistency only. This report does not judge overall professional quality, aesthetics, or whether a human deliverable is best among multiple valid solutions.",
        "",
        "## Run summary",
        "",
        f"- Caller-declared immutable dataset revision: `{report['gdpval_objective']['dataset_revision']}`",
        f"- Source SHA-256: `{report['source_identity']['input_sha256']}`",
        f"- Code manifest SHA-256: `{implementation.get('sha256', 'not recorded')}`",
        f"- Rows: `{census['rows']}`",
        f"- Rubric items parsed: `{census['rubric_items']}`",
        f"- Declared reference artifacts: `{census['reference_artifacts_declared']}`",
        f"- Declared expert deliverables: `{census['deliverable_artifacts_declared']}`",
        f"- Findings: `{summary['violation_count']}`",
        f"- Confirmed objective evidence records: `{len(confirmed)}`",
        f"- Mechanically deduplicated atomic assertions: `{len(confirmed_atomic_assertions)}`",
        "- Root-cause count: `not established`",
        f"- Review-only: `{len(review)}`",
        f"- Operational/unknown: `{len(unknown)}`",
        f"- Completed eligible checks: `{coverage.get('completed', 'not recorded')}`",
        f"- Operationally failed checks: `{coverage.get('operational_failed', 'not recorded')}`",
        "",
        "A normal no-finding result means only that the registered objective predicates completed; it is not a clean-task or complete-quality verdict.",
        "",
        "## Evidence policy",
        "",
        "- `confirmed`: exact versioned proof tuple replayed from the content-addressed live row or XLSX bytes.",
        "- `review`: duplication, semantic/entity candidates, or cross-source differences lacking an independent artifact adjudicator.",
        "- `unknown`: incomplete, blocked, unsupported, or operationally failed coverage.",
        "- LLM votes are not used by this experiment.",
        "- Atomic assertion count expands workbook mismatch lists and deduplicates only byte-identical row/scope/role/expected/observed assertions; it is not a root-cause count.",
        "",
        "## Confirmed objective findings",
        "",
    ]
    if not confirmed:
        lines.append("No registered objective finding was confirmed.")
        lines.append("")
    for index, finding in enumerate(confirmed, 1):
        evidence = finding.get("evidence") or {}
        atom = evidence.get("atom") or {}
        lines.extend([
            f"### {index}. `{finding['item_id']}` — `{finding['defect_type']}`",
            "",
            finding["message"],
            "",
            f"- Evidence level: `{evidence.get('evidence_level')}`",
            f"- Proof kind: `{finding.get('proof_kind')}`",
            f"- Predicate: `{evidence.get('predicate_version')}`",
            f"- Fact signature: `{evidence.get('fact_signature')}`",
            f"- Atom kind: `{atom.get('kind')}`",
        ])
        artifact_hashes = atom.get("artifact_sha256s")
        if artifact_hashes:
            lines.append(
                "- Observed artifact SHA-256: "
                + ", ".join(f"`{value}`" for value in artifact_hashes)
            )
        artifacts = evidence.get("artifacts") or []
        authenticity = sorted({
            str(value.get("artifact_authenticity") or "unknown")
            for value in artifacts if isinstance(value, dict)
        })
        if authenticity:
            lines.append(
                "- Artifact authenticity status: "
                + ", ".join(f"`{value}`" for value in authenticity)
            )
        if atom.get("kind") == "exact_filename_absent":
            lines.append(
                f"- Required exact filename: `{atom.get('expected_basename')}`"
            )
            lines.append(
                "- Published artifact filename(s): "
                + ", ".join(
                    f"`{value}`" for value in atom.get("observed_basenames") or []
                )
            )
            excerpt = (atom.get("claim") or {}).get("excerpt")
            if excerpt:
                lines.append(f"- Contract excerpt: {excerpt}")
        if atom.get("kind") == "output_format_mismatch":
            lines.append(
                f"- Required output format: `{atom.get('expected_extension')}`"
            )
            lines.append(
                f"- Published deliverable format: `{atom.get('observed_extension')}`"
            )
            excerpt = (atom.get("claim") or {}).get("excerpt")
            if excerpt:
                lines.append(f"- Contract excerpt: {excerpt}")
        if atom.get("kind") == "incompatible_column_role_claims":
            for conflict in atom.get("conflicts") or []:
                if conflict.get("kind") == "one_column_multiple_roles":
                    lines.append(
                        f"- Conflict: column `{conflict.get('column')}` is assigned roles "
                        + ", ".join(
                            f"`{role}`" for role in conflict.get("roles") or []
                        )
                    )
                elif conflict.get("kind") == "one_role_multiple_columns":
                    lines.append(
                        f"- Conflict: role `{conflict.get('role')}` is assigned columns "
                        + ", ".join(
                            f"`{column}`" for column in conflict.get("columns") or []
                        )
                    )
        mismatches = atom.get("mismatches") or []
        for mismatch in mismatches:
            lines.append(
                "- Mismatch: "
                f"`{mismatch.get('scope')}` / `{mismatch.get('role')}` — "
                f"expected column `{mismatch.get('expected_column')}`, observed "
                f"`{', '.join(mismatch.get('observed_columns') or [])}`"
            )
        lines.append("")
    lines.extend(["## Review queue", ""])
    if not review:
        lines.extend(["No review-only signals.", ""])
    for finding in review:
        atom = (finding.get("evidence") or {}).get("atom") or {}
        lines.append(
            f"- `{finding['item_id']}` — `{finding['defect_type']}` / "
            f"`{atom.get('kind')}`: {finding['message']}"
        )
    lines.extend(["", "## Coverage census", ""])
    for key, value in census.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    # Hugging Face snapshots expose extension-bearing symlinks to content
    # blobs whose object names have no suffix.  Preserve the declared path for
    # format dispatch while every report hash still binds the dereferenced
    # bytes.
    input_path = Path(args.input).expanduser().absolute()
    if not input_path.is_file():
        raise FileNotFoundError(f"GDPval input is not a regular file: {input_path}")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path, snapshot_sha256, snapshot_size = _snapshot_input(
        input_path, out_dir,
    )
    rows = load_rows(snapshot_path)
    loaded_digest, loaded_size = _hash_regular_file(snapshot_path)
    if loaded_digest != snapshot_sha256 or loaded_size != snapshot_size:
        raise RuntimeError("GDPval audit snapshot changed while loading rows")
    items = build_gdpval_items(rows)

    checkers: list[Any] = [
        GDPValRecordIntegrityChecker(dataset_revision=args.dataset_revision),
    ]
    deep_enabled = bool(args.deep_task_id or args.deep_all_applicable)
    if deep_enabled:
        if not args.artifact_cache:
            raise ValueError("deep replay requires --artifact-cache")
        resolver = GDPvalArtifactResolver(
            args.artifact_cache,
            revision=args.dataset_revision,
            max_file_bytes=args.max_artifact_bytes,
        )
        checkers.append(GDPValWorkbookReplayChecker(
            resolver,
            allow_download=args.download_artifacts,
            task_ids=([] if args.deep_all_applicable else args.deep_task_id),
        ))

    result = audit_items_with_ledger(
        items,
        checkers=checkers,
        dataset_checkers=[
            GDPValDatasetIntegrityChecker(dataset_revision=args.dataset_revision),
            DuplicateConflictChecker(),
        ],
        workers=max(args.workers, 1),
    )
    methods = [checker.name for checker in checkers] + [
        "gdpval_dataset_objective",
        "duplicate_conflict",
    ]
    implementation = _code_provenance()
    report = build_report(
        # Avoid a second pathname read inside the generic report builder.  The
        # exact digest/size from the already verified snapshot descriptor are
        # installed below.
        str(out_dir),
        items,
        result.violations,
        mapping=gdpval_mapping(),
        methods_run=methods,
        run_metadata={
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "git": implementation["git"],
            "implementation": implementation,
            "llm": {"used": False},
            "gdpval": {
                "dataset_revision": args.dataset_revision,
                "predicate_version": GDPVAL_PREDICATE_VERSION,
                "deep_replay_enabled": deep_enabled,
                "deep_task_ids": list(args.deep_task_id),
                "deep_all_applicable": bool(args.deep_all_applicable),
                "artifact_download_authorized": bool(args.download_artifacts),
            },
        },
        audit_ledger=result.ledger,
    )
    report["input_path"] = str(input_path)
    report["source_identity"].update({
        "input_sha256": snapshot_sha256,
        "input_size_bytes": snapshot_size,
        "declared_input_path": str(input_path),
        "audited_snapshot_path": str(snapshot_path),
    })
    report["gdpval_objective"] = {
        "schema_version": "benchcore-gdpval-objective-report-v1",
        "dataset_revision": args.dataset_revision,
        "predicate_version": GDPVAL_PREDICATE_VERSION,
        "input_sha256": snapshot_sha256,
        "census": _census(rows),
        "metrics": {
            "confirmed_evidence_records": sum(
                row.evidence_tier == "confirmed" for row in result.violations
            ),
            "confirmed_atomic_assertions": len({
                key
                for row in report["violations"]
                if row["evidence_tier"] == "confirmed"
                for key in _confirmed_atomic_keys(row)
            }),
            "confirmed_affected_rows": len({
                row.row_uid for row in result.violations
                if row.evidence_tier == "confirmed" and row.row_uid is not None
            }),
            "root_cause_count": None,
            "atomic_assertion_definition": (
                "expand workbook mismatch lists and deduplicate exact "
                "row/scope/role/expected/observed assertions"
            ),
        },
        "claim_boundary": (
            "confirmed covers only registered deterministic row/manifest/file/header "
            "predicates; professional-quality judgements remain outside scope"
        ),
    }

    write_json_report(out_dir / "audit.json", report)
    write_markdown_report(out_dir / "audit.md", report)
    _write_summary(out_dir / "summary.md", report)
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
