"""Deterministic evidence checks for rubric-based workspace benchmarks.

Workspace-Bench does not expose a DS-1000-style executable oracle.  Its public
record contains a task, natural-language rubrics, a declared output contract, a
file dependency graph and concrete input files.  This module checks the subset
of defects that can be decided from those artifacts without an LLM:

* every declared input exists and reconciles with ``data_manifest``;
* dependency-graph endpoints resolve when a complete workspace inventory is
  explicitly provided (task-local manifests alone are not complete workspaces);
* duplicate metadata views of rubrics and output files agree;
* rubric types are cardinality-aligned with rubrics; and
* declared task-package inputs do not contain an obvious reference generator
  (actor visibility is established separately by a runner-view replay).

These checks intentionally stay silent when an artifact was never materialized.
Absence of a local cache is an operational limitation, not a benchmark defect.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from .checkers import Checker, _violation
from .schema import BenchmarkItem, Violation
from .workspace_visibility import WorkspaceRunnerVisibilityIndex
from .coverage import AuditEligibility


REFERENCE_GENERATOR_NAME = re.compile(
    r"(?:^|[_-])(?:generate|generator|build|create)[_-].*\.(?:py|js|ts|sh)$|"
    r"(?:ground[_-]?truth|reference[_-]?(?:answer|output)|gold[_-]?(?:answer|output|solution))",
    re.I,
)
REFERENCE_GENERATOR_BODY = re.compile(
    r"(?:output_cc|ground[_-]?truth|reference[_-]?(?:answer|output)|gold[_-]?(?:answer|output))|"
    r"(?:Presentation|Workbook|Document)\s*\([^)]*\).*?\.save\s*\(",
    re.I | re.S,
)
MAX_GENERATOR_SCAN_BYTES = 2_000_000


@dataclass(frozen=True)
class WorkspaceInvariantIssue:
    defect_type: str
    message: str
    evidence: dict[str, Any]
    severity: str = "major"
    review_only: bool = False


def parse_jsonish(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def normalized_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.strip("/").casefold()


def logical_input_name(path: Path) -> str:
    """Strip the hash prefix used by Workspace-Bench's downloaded task files."""
    name = path.name
    if re.match(r"^[0-9a-f]{16}_.+", name, re.I):
        return name.split("_", 1)[1]
    return name


def workspace_rubrics(item: BenchmarkItem) -> list[str]:
    evaluator = item.evaluator if isinstance(item.evaluator, dict) else {}
    value = evaluator.get("rubrics")
    if not isinstance(value, list):
        value = parse_jsonish(item.raw.get("rubrics"), [])
    return [str(row) for row in value] if isinstance(value, list) else []


def workspace_rubric_types(item: BenchmarkItem) -> list[str]:
    evaluator = item.evaluator if isinstance(item.evaluator, dict) else {}
    value = evaluator.get("rubric_types")
    if not isinstance(value, list):
        value = parse_jsonish(item.raw.get("rubric_types"), [])
    return [str(row) for row in value] if isinstance(value, list) else []


def workspace_outputs(item: BenchmarkItem) -> list[str]:
    contract = item.output_contract if isinstance(item.output_contract, dict) else {}
    value = contract.get("required_files") or contract.get("files") or []
    return [str(row) for row in value] if isinstance(value, list) else []


def workspace_manifest(item: BenchmarkItem) -> list[dict[str, Any]]:
    value = item.context.get("data_manifest") if isinstance(item.context, dict) else None
    if not isinstance(value, list):
        value = parse_jsonish(item.raw.get("data_manifest"), [])
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def workspace_dependency_graph(item: BenchmarkItem) -> list[dict[str, Any]]:
    value = item.context.get("file_dep_graph") if isinstance(item.context, dict) else None
    if not isinstance(value, list):
        value = parse_jsonish(item.raw.get("file_dep_graph"), [])
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def workspace_complete_inventory(item: BenchmarkItem) -> tuple[bool, list[str]]:
    """Return a declared *complete* workspace inventory when one is available.

    Workspace-Bench agents operate in a large role workspace in addition to the
    current task's ``data_manifest``. Therefore a graph endpoint absent from the
    task-local manifest is not objectively dangling. Promotion is allowed only
    when the package explicitly declares that its inventory is complete.
    """
    context = item.context if isinstance(item.context, dict) else {}
    complete = context.get("workspace_inventory_complete")
    if complete is None:
        complete = item.raw.get("workspace_inventory_complete")
    value = context.get("workspace_inventory")
    if not isinstance(value, list):
        value = parse_jsonish(item.raw.get("workspace_inventory"), [])
    names: list[str] = []
    if isinstance(value, list):
        for row in value:
            if isinstance(row, dict):
                candidate = row.get("filename") or row.get("path") or row.get("name")
            else:
                candidate = row
            if candidate not in (None, ""):
                names.append(str(candidate))
    return bool(complete), names


def workspace_input_paths(
    item: BenchmarkItem,
    root: Path | None = None,
    *,
    allowed_roots: Iterable[Path] | None = None,
) -> list[Path]:
    return [
        row["path"]
        for row in workspace_input_path_records(
            item, root, allowed_roots=allowed_roots,
        )
        if row["allowed"]
    ]


def workspace_input_path_records(
    item: BenchmarkItem,
    root: Path | None = None,
    *,
    allowed_roots: Iterable[Path] | None = None,
) -> list[dict[str, Any]]:
    """Resolve declared files under an explicit containment policy.

    A CLI-supplied ``root`` activates fail-closed containment.  Programmatic
    callers that deliberately use already-pinned absolute artifacts can omit
    both values; experiment drivers are then responsible for their own trust
    gate.  Existing symlinks are resolved before containment is checked.
    """
    values = item.raw.get("input_files") or []
    if not isinstance(values, list):
        return []
    roots = (
        list(allowed_roots)
        if allowed_roots is not None
        else ([] if root is None else [root])
    )
    resolved_roots = [path.expanduser().resolve() for path in roots]
    records: list[dict[str, Any]] = []
    for value in values:
        declared = str(value)
        path = Path(declared).expanduser()
        if not path.is_absolute() and root is not None:
            path = root / path
        original = path.absolute()
        resolved = original.resolve(strict=False)
        allowed = bool(resolved_roots) and any(
            resolved == allowed_root or resolved.is_relative_to(allowed_root)
            for allowed_root in resolved_roots
        )
        records.append({
            "declared": declared,
            # Preserve the declared/materialized basename for manifest
            # reconciliation.  ``resolved_path`` is used only for the security
            # decision; Hugging Face snapshots legitimately use hash-blob
            # symlinks whose resolved basename is opaque.
            "path": original,
            "resolved_path": resolved,
            "allowed": allowed,
            "reason": (
                "within_allowed_root" if allowed
                else (
                    "no_allowed_roots_configured"
                    if not resolved_roots
                    else "absolute_or_symlink_path_escapes_allowed_roots"
                )
            ),
            "allowed_roots": [str(candidate) for candidate in resolved_roots],
        })
    return records


def _raw_list(item: BenchmarkItem, key: str) -> list[str] | None:
    if key not in item.raw:
        return None
    value = parse_jsonish(item.raw.get(key), None)
    return [str(row) for row in value] if isinstance(value, list) else None


def _canonical_list_sha256(values: list[str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def collect_workspace_invariant_issues(
    item: BenchmarkItem,
    root: Path | None = None,
    *,
    allowed_roots: Iterable[Path] | None = None,
    include_solution_leak_scan: bool = True,
) -> list[WorkspaceInvariantIssue]:
    manifest = workspace_manifest(item)
    graph = workspace_dependency_graph(item)
    outputs = workspace_outputs(item)
    rubrics = workspace_rubrics(item)
    rubric_types = workspace_rubric_types(item)
    path_records = workspace_input_path_records(
        item, root, allowed_roots=allowed_roots,
    )
    input_paths = [row["path"] for row in path_records if row["allowed"]]
    issues: list[WorkspaceInvariantIssue] = []

    blocked = [row for row in path_records if not row["allowed"]]
    if blocked:
        issues.append(WorkspaceInvariantIssue(
            "inaccessible_attachment",
            f"{len(blocked)} input path(s) were blocked by the audit containment policy.",
            {
                "blocked_paths": [
                    {
                        "declared": row["declared"],
                        "resolved": str(row["resolved_path"]),
                        "reason": row["reason"],
                    }
                    for row in blocked[:20]
                ],
                "allowed_roots": blocked[0]["allowed_roots"],
                "evidence_level": "path_policy_block",
            },
            severity="review",
            review_only=True,
        ))

    # Only call missing files a benchmark defect when paths were explicitly
    # materialized in the record. A metadata-only distribution may omit them.
    missing_paths = [str(path) for path in input_paths if not path.is_file()]
    if missing_paths:
        issues.append(WorkspaceInvariantIssue(
            "inaccessible_attachment",
            f"{len(missing_paths)} declared Workspace input file(s) are inaccessible.",
            {"missing_paths": missing_paths[:20], "declared_input_count": len(input_paths)},
        ))

    if manifest and input_paths:
        existing = [path for path in input_paths if path.is_file()]
        physical_names = {normalized_path(path.name) for path in existing}
        logical_names = {normalized_path(logical_input_name(path)) for path in existing}
        unresolved: list[dict[str, Any]] = []
        for row in manifest:
            filename = normalized_path(row.get("filename"))
            stored_name = normalized_path(Path(str(row.get("stored_relpath") or "")).name)
            if not (
                (filename and filename in logical_names)
                or (stored_name and stored_name in physical_names)
                or (stored_name and stored_name in logical_names)
            ):
                unresolved.append({
                    "filename": row.get("filename"),
                    "stored_relpath": row.get("stored_relpath"),
                })
        if unresolved:
            issues.append(WorkspaceInvariantIssue(
                "artifact_data_gap",
                f"{len(unresolved)} data_manifest entrie(s) have no materialized input file.",
                {
                    "unresolved_manifest_entries": unresolved[:20],
                    "manifest_count": len(manifest),
                    "input_file_count": len(input_paths),
                    "evidence_level": "filesystem_manifest_replay",
                    "proof_schema_version": "1.0",
                },
            ))

        # Workspace runners expose task inputs by their logical filename.  Two
        # different materialized bytes assigned the same logical name are not
        # merely duplicate metadata: one input necessarily shadows/overwrites
        # the other in any flat filename view.  Require both contained files
        # and distinct hashes before calling this a benchmark defect; duplicate
        # labels alone can be harmless aliases in an incomplete distribution.
        collisions = _manifest_filename_content_collisions(manifest, input_paths)
        if collisions:
            issues.append(WorkspaceInvariantIssue(
                "ambiguous_input_filename",
                (
                    f"{len(collisions)} logical input filename(s) map to distinct "
                    "materialized file contents."
                ),
                {
                    "ambiguous_input_filenames": collisions,
                    "evidence_level": "manifest_filename_collision_replay",
                    "proof_schema_version": "1.0",
                },
                severity="critical",
            ))

    # The graph may contain input-to-input edges, so either endpoint is valid if
    # it resolves to a manifest file or a declared output.
    inventory_complete, inventory = workspace_complete_inventory(item)
    known_names = {
        normalized_path(row.get("filename")) for row in manifest if row.get("filename")
    }
    known_names.update(normalized_path(path) for path in outputs)
    known_names.update(normalized_path(path) for path in inventory)
    dangling: list[dict[str, Any]] = []
    if graph and known_names and inventory_complete:
        for index, edge in enumerate(graph):
            source = normalized_path(edge.get("from") or edge.get("source"))
            target = normalized_path(edge.get("to") or edge.get("target"))
            missing = [name for name in (source, target) if name and name not in known_names]
            if missing:
                dangling.append({"edge_index": index, "edge": edge, "unresolved": missing})
        if dangling:
            issues.append(WorkspaceInvariantIssue(
                "artifact_data_gap",
                f"{len(dangling)} dependency-graph edge(s) reference undeclared artifacts.",
                {
                    "dangling_edges": dangling[:20],
                    "known_artifact_count": len(known_names),
                    "workspace_inventory_complete": True,
                    "evidence_level": "dependency_graph_replay",
                    "proof_schema_version": "1.0",
                },
            ))

    raw_outputs = _raw_list(item, "output_files")
    if raw_outputs is not None and {
        normalized_path(value) for value in raw_outputs
    } != {normalized_path(value) for value in outputs}:
        issues.append(WorkspaceInvariantIssue(
            "output_evaluator_contract_mismatch",
            "Raw output_files and canonical output contract declare different deliverables.",
            {
                "raw_output_files": raw_outputs,
                "contract_required_files": outputs,
                "evidence_level": "metadata_contract_replay",
                "proof_schema_version": "1.0",
            },
        ))

    raw_rubrics = _raw_list(item, "rubrics")
    if raw_rubrics is not None and raw_rubrics != rubrics:
        issues.append(WorkspaceInvariantIssue(
            "schema_drift",
            "Raw rubrics and canonical evaluator rubrics are not identical.",
            {
                "raw_rubric_count": len(raw_rubrics),
                "evaluator_rubric_count": len(rubrics),
                "raw_rubrics_sha256": _canonical_list_sha256(raw_rubrics),
                "evaluator_rubrics_sha256": _canonical_list_sha256(rubrics),
                "evidence_level": "metadata_evaluator_replay",
                "proof_schema_version": "1.0",
            },
        ))

    if rubric_types and len(rubric_types) != len(rubrics):
        issues.append(WorkspaceInvariantIssue(
            "schema_drift",
            "rubric_types cardinality does not match rubrics cardinality.",
            {
                "rubric_count": len(rubrics),
                "rubric_type_count": len(rubric_types),
                "evidence_level": "metadata_evaluator_replay",
                "proof_schema_version": "1.0",
            },
        ))

    leak_rows = _reference_generator_leaks(input_paths) if include_solution_leak_scan else []
    if leak_rows:
        issues.append(WorkspaceInvariantIssue(
            "solution_leak",
            (
                "The declared task input package contains a script whose name and "
                "body match an output-generation heuristic; equivalence to a hidden "
                "oracle and score impact are not established."
            ),
            {
                "files": leak_rows,
                "evidence_level": "task_package_static_execution_intent",
                "oracle_equivalence_proven": False,
                "score_impact_proven": False,
                "visibility": {
                    "task_package_present": True,
                    "agent_visible": None,
                    "evaluator_visible": None,
                    "visibility_verified": False,
                },
            },
            severity="major",
            review_only=True,
        ))
    return _dedupe_issues(issues)


def _reference_generator_leaks(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file() or path.stat().st_size > MAX_GENERATOR_SCAN_BYTES:
            continue
        if path.suffix.lower() not in {".py", ".js", ".ts", ".sh"}:
            continue
        if not REFERENCE_GENERATOR_NAME.search(path.name):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = REFERENCE_GENERATOR_BODY.search(text)
        if not match:
            continue
        start = max(0, match.start() - 120)
        end = min(len(text), match.end() + 220)
        rows.append({
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "matched": match.group(0)[:160],
            "excerpt": text[start:end],
        })
    return rows


def _manifest_filename_content_collisions(
    manifest: list[dict[str, Any]],
    input_paths: list[Path],
) -> list[dict[str, Any]]:
    """Find logical manifest names bound to two different pinned byte streams."""
    paths_by_stored_name: dict[str, list[Path]] = {}
    for path in input_paths:
        if not path.is_file():
            continue
        paths_by_stored_name.setdefault(normalized_path(path.name), []).append(path)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in manifest:
        filename = normalized_path(entry.get("filename"))
        stored = normalized_path(Path(str(entry.get("stored_relpath") or "")).name)
        if filename and stored:
            grouped.setdefault(filename, []).append({
                "filename": str(entry.get("filename") or ""),
                "stored_name": stored,
                "stored_relpath": str(entry.get("stored_relpath") or ""),
            })

    digest_cache: dict[Path, tuple[int, str]] = {}

    def digest(path: Path) -> tuple[int, str]:
        if path not in digest_cache:
            payload = path.read_bytes()
            digest_cache[path] = (
                len(payload), hashlib.sha256(payload).hexdigest(),
            )
        return digest_cache[path]

    collisions: list[dict[str, Any]] = []
    for logical_name, entries in sorted(grouped.items()):
        if len(entries) < 2:
            continue
        resolved: list[dict[str, Any]] = []
        for entry in entries:
            paths = paths_by_stored_name.get(entry["stored_name"], [])
            # A stored basename must map to one exact materialized path.  Any
            # unresolved/ambiguous storage mapping is handled elsewhere rather
            # than being overclaimed as a content collision.
            if len(paths) != 1:
                resolved = []
                break
            size, content_sha = digest(paths[0])
            resolved.append({
                **entry,
                "size_bytes": size,
                "content_sha256": content_sha,
            })
        if resolved and len({row["content_sha256"] for row in resolved}) > 1:
            collisions.append({
                "logical_filename": logical_name,
                "entries": resolved,
            })
    return collisions


def _dedupe_issues(issues: list[WorkspaceInvariantIssue]) -> list[WorkspaceInvariantIssue]:
    seen: set[tuple[str, str]] = set()
    out: list[WorkspaceInvariantIssue] = []
    for issue in issues:
        key = (issue.defect_type, issue.message)
        if key in seen:
            continue
        seen.add(key)
        out.append(issue)
    return out


class WorkspaceArtifactInvariantChecker(Checker):
    """Emit only objective Workspace artifact and metadata contradictions."""

    name = "workspace_artifact_invariants"

    def __init__(
        self,
        *,
        allowed_roots: Iterable[Path] | None = None,
        visibility_index: WorkspaceRunnerVisibilityIndex | None = None,
    ) -> None:
        self.allowed_roots = tuple(allowed_roots) if allowed_roots is not None else None
        self.visibility_index = visibility_index

    def audit_eligibility(self, item, root=None) -> AuditEligibility:
        evaluator = item.evaluator if isinstance(item.evaluator, dict) else {}
        if (
            evaluator.get("type") == "workspacebench_rubric"
            or {"rubrics", "data_manifest", "file_dep_graph"}.intersection(item.raw)
        ):
            return AuditEligibility.applicable("Workspace artifact schema is present")
        return AuditEligibility.not_applicable("item is not a Workspace artifact benchmark")

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        evaluator = item.evaluator if isinstance(item.evaluator, dict) else {}
        if (
            evaluator.get("type") != "workspacebench_rubric"
            and not {"rubrics", "data_manifest", "file_dep_graph"}.intersection(item.raw)
        ):
            return
        root_values = (
            self.allowed_roots
            if self.allowed_roots is not None
            else (() if root is None else (root,))
        )
        trusted_roots = tuple(
            Path(value).expanduser().resolve() for value in root_values
        )
        # Process-local replay context: this is never loaded from benchmark
        # payloads or serialized evidence, so central promotion can reproduce
        # the same containment decision without trusting self-reported roots.
        setattr(item, "_workspace_replay_allowed_roots", trusted_roots)
        for issue in collect_workspace_invariant_issues(
            item, root, allowed_roots=trusted_roots,
        ):
            if issue.defect_type == "solution_leak" and self.visibility_index is not None:
                proof = None
                for row in issue.evidence.get("files", []):
                    if not isinstance(row, dict):
                        continue
                    proof = self.visibility_index.find(
                        item.item_id, str(row.get("sha256") or ""),
                    )
                    if proof is not None:
                        break
                if proof is not None and proof.online_reverified:
                    issue = replace(
                        issue,
                        review_only=True,
                        message=(
                            "A suspected output-generation script is byte-identical to "
                            "the file observed in both pinned agent and evaluator views; "
                            "its relation to the hidden oracle and score impact remain "
                            "unproven."
                        ),
                        evidence={
                            **issue.evidence,
                            **proof.to_evidence(),
                            "oracle_equivalence_proven": False,
                            "score_impact_proven": False,
                        },
                    )
                elif proof is not None:
                    issue = replace(
                        issue,
                        message=(
                            "A visibility transcript matches this generator, but its "
                            "pinned remote runner/archive bytes were not independently "
                            "re-fetched in this audit run."
                        ),
                        evidence={**issue.evidence, **proof.to_evidence()},
                        review_only=True,
                    )
            yield _violation(
                item,
                issue.defect_type,
                0.99 if not issue.review_only else 0.75,
                issue.message,
                issue.evidence,
                severity=issue.severity,
                review_only=issue.review_only,
                repair="Reconcile the public task metadata and agent-visible artifact package.",
                method=self.name,
            )


def workspace_artifact_manifest(
    items: Iterable[BenchmarkItem],
    root: Path | None = None,
    *,
    allowed_roots: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Create a portable integrity manifest for every declared physical input."""
    rows: list[dict[str, Any]] = []
    total_bytes = 0
    missing = 0
    for item in items:
        manifest_by_stored = {
            normalized_path(Path(str(row.get("stored_relpath") or "")).name): row
            for row in workspace_manifest(item)
        }
        for path in workspace_input_paths(
            item, root, allowed_roots=allowed_roots,
        ):
            exists = path.is_file()
            row: dict[str, Any] = {
                "item_id": item.item_id,
                "logical_name": logical_input_name(path),
                "source_path": str(path),
                "exists": exists,
            }
            source = manifest_by_stored.get(normalized_path(path.name))
            if source:
                row["declared_filename"] = source.get("filename")
                row["stored_relpath"] = source.get("stored_relpath")
            if exists:
                payload = path.read_bytes()
                row["size_bytes"] = len(payload)
                row["sha256"] = hashlib.sha256(payload).hexdigest()
                total_bytes += len(payload)
            else:
                missing += 1
            rows.append(row)
    return {
        "schema_version": "1.0",
        "summary": {
            "items": len({row["item_id"] for row in rows}),
            "declared_files": len(rows),
            "materialized_files": len(rows) - missing,
            "missing_files": missing,
            "total_bytes": total_bytes,
            "byte_coverage": 1.0 if not rows else (len(rows) - missing) / len(rows),
        },
        "files": rows,
    }
