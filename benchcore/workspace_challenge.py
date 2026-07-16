"""Paired, provenance-safe structural challenges for Workspace-Bench.

The public Workspace-Bench records duplicate several facts across raw metadata,
the canonical evaluator, the output contract, and the materialized input-file
package.  That makes it possible to create objective mutations without asking a
model (or a person) what the benchmark author intended.

Each challenge consists of a semantically equivalent clean-side clone with a
derived complete-inventory declaration, plus one single-defect mutant. Mutation
provenance is returned separately and is never embedded in either row. Scoring
operates on *atomic evidence* and subtracts clean-side
findings from mutant findings, so a real issue already present in a source task
does not receive credit for an injected issue.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .auditor import audit_items
from .loader import build_items, load_mapping
from .schema import Violation
from .workspace_invariants import WorkspaceArtifactInvariantChecker, parse_jsonish


MANIFEST_UNRESOLVED = "manifest_unresolved"
DANGLING_DEPENDENCY = "dangling_dependency"
CONTRACT_FILENAME_CONFLICT = "contract_filename_conflict"
RAW_EVALUATOR_RUBRIC_DIVERGENCE = "raw_evaluator_rubric_divergence"
RUBRIC_TYPES_CARDINALITY = "rubric_types_cardinality"

WORKSPACE_CHALLENGE_OPERATORS = (
    MANIFEST_UNRESOLVED,
    DANGLING_DEPENDENCY,
    CONTRACT_FILENAME_CONFLICT,
    RAW_EVALUATOR_RUBRIC_DIVERGENCE,
    RUBRIC_TYPES_CARDINALITY,
)

_EXPECTED = {
    MANIFEST_UNRESOLVED: ("artifact_data_gap", "manifest_unresolved"),
    DANGLING_DEPENDENCY: ("artifact_data_gap", "dependency_dangling"),
    CONTRACT_FILENAME_CONFLICT: (
        "output_evaluator_contract_mismatch",
        "contract_filename_conflict",
    ),
    RAW_EVALUATOR_RUBRIC_DIVERGENCE: ("schema_drift", "raw_evaluator_divergence"),
    RUBRIC_TYPES_CARDINALITY: ("schema_drift", "rubric_types_cardinality"),
}

_PROVENANCE_FIELDS = {
    "_injected_defect",
    "_workspace_challenge",
    "_challenge_provenance",
}


@dataclass(frozen=True)
class WorkspaceChallengeProvenance:
    """Sidecar-only description of one controlled mutation."""

    mutation_id: str
    pair_id: str
    source_item_id: str
    clean_item_id: str
    mutant_item_id: str
    operator: str
    expected_defect_type: str
    expected_atom_kind: str
    evidence_marker: str | None
    changed_fields: tuple[str, ...]
    seed: int
    source_sha256: str
    clean_sha256: str
    mutant_sha256: str


@dataclass
class WorkspaceChallenge:
    """Rows visible to the auditor plus a separate provenance sidecar."""

    clean_rows: list[dict[str, Any]]
    mutant_rows: list[dict[str, Any]]
    provenance: list[WorkspaceChallengeProvenance]
    source_items: int
    seed: int
    operators: tuple[str, ...]
    skipped: list[dict[str, str]]

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "seed": self.seed,
            "source_items": self.source_items,
            "clean_items": len(self.clean_rows),
            "mutant_items": len(self.mutant_rows),
            "pair_count": len(self.provenance),
            "operators": list(self.operators),
            "skipped": list(self.skipped),
            "mutations": [asdict(row) for row in self.provenance],
        }


@dataclass(frozen=True)
class FindingAtom:
    """One independently matchable fact extracted from an audit violation."""

    item_id: str
    defect_type: str
    kind: str
    key: str
    payload: Any
    message: str

    @property
    def searchable_text(self) -> str:
        return canonical_json(self.payload)


@dataclass(frozen=True)
class _Mutation:
    row: dict[str, Any]
    changed_fields: tuple[str, ...]
    marker: str | None


def build_workspace_challenge(
    rows: Sequence[dict[str, Any]],
    *,
    seed: int = 20260714,
    operators: Iterable[str] | None = None,
) -> WorkspaceChallenge:
    """Create clean/mutant pairs for every applicable source row.

    The input rows are never modified.  A clean row is shared by all mutations
    derived from the same source item, while every mutant receives an opaque ID.
    IDs intentionally omit operator and clean/mutant labels.
    """

    selected = tuple(operators or WORKSPACE_CHALLENGE_OPERATORS)
    unknown = set(selected) - set(WORKSPACE_CHALLENGE_OPERATORS)
    if unknown:
        raise ValueError("unknown Workspace challenge operator(s): " + ", ".join(sorted(unknown)))
    if len(selected) != len(set(selected)):
        raise ValueError("Workspace challenge operators must be unique")

    clean_by_id: dict[str, dict[str, Any]] = {}
    mutants: list[dict[str, Any]] = []
    provenance: list[WorkspaceChallengeProvenance] = []
    skipped: list[dict[str, str]] = []

    for index, source in enumerate(rows):
        source_id = str(source.get("item_id") or f"item-{index}")
        source_hash = canonical_sha256(source)
        clean_id = opaque_id(seed, source_id, "clean")
        clean = _clean_clone(source, clean_id)
        clean_by_id.setdefault(clean_id, clean)

        for operator in selected:
            pair_id = hashlib.sha256(
                f"workspace-challenge:{seed}:{source_id}:{operator}".encode("utf-8")
            ).hexdigest()[:24]
            marker_token = pair_id[:16]
            result, reason = _apply_operator(clean, operator, marker_token)
            if result is None:
                skipped.append({
                    "source_item_id": source_id,
                    "operator": operator,
                    "reason": reason or "operator is not applicable",
                })
                continue

            mutant_id = opaque_id(seed, source_id, operator)
            result.row["item_id"] = mutant_id
            _strip_provenance(result.row)
            expected_type, expected_kind = _EXPECTED[operator]
            mutations_hash = canonical_sha256(result.row)
            mutation_id = hashlib.sha256(
                f"{pair_id}:{source_hash}:{mutations_hash}".encode("utf-8")
            ).hexdigest()[:24]
            mutants.append(result.row)
            provenance.append(WorkspaceChallengeProvenance(
                mutation_id=mutation_id,
                pair_id=pair_id,
                source_item_id=source_id,
                clean_item_id=clean_id,
                mutant_item_id=mutant_id,
                operator=operator,
                expected_defect_type=expected_type,
                expected_atom_kind=expected_kind,
                evidence_marker=result.marker,
                changed_fields=result.changed_fields,
                seed=seed,
                source_sha256=source_hash,
                clean_sha256=canonical_sha256(clean),
                mutant_sha256=mutations_hash,
            ))

    return WorkspaceChallenge(
        clean_rows=list(clean_by_id.values()),
        mutant_rows=mutants,
        provenance=provenance,
        source_items=len(rows),
        seed=seed,
        operators=selected,
        skipped=skipped,
    )


def audit_workspace_challenge(
    challenge: WorkspaceChallenge,
    *,
    root: Path | None = None,
    allowed_roots: Iterable[Path] | None = None,
    workers: int = 1,
) -> dict[str, Any]:
    """Run only the existing deterministic Workspace invariant checker."""

    clean_items = _items_for_rows(challenge.clean_rows)
    mutant_items = _items_for_rows(challenge.mutant_rows)
    checker = WorkspaceArtifactInvariantChecker(allowed_roots=allowed_roots)
    clean = audit_items(
        clean_items,
        root=root,
        checkers=[checker],
        dataset_checkers=[],
        workers=max(1, workers),
    )
    mutant = audit_items(
        mutant_items,
        root=root,
        checkers=[checker],
        dataset_checkers=[],
        workers=max(1, workers),
    )
    clean_rows = sorted((asdict(row) for row in clean), key=_violation_sort_key)
    mutant_rows = sorted((asdict(row) for row in mutant), key=_violation_sort_key)
    return {
        "clean": {
            "items": len(clean_items),
            "violation_count": len(clean_rows),
            "violations": clean_rows,
        },
        "mutant": {
            "items": len(mutant_items),
            "violation_count": len(mutant_rows),
            "violations": mutant_rows,
        },
        "score": score_workspace_challenge(challenge.provenance, clean_rows, mutant_rows),
    }


def score_workspace_challenge(
    provenance: Sequence[WorkspaceChallengeProvenance | Mapping[str, Any]],
    clean_violations: Sequence[Violation | Mapping[str, Any]],
    mutant_violations: Sequence[Violation | Mapping[str, Any]],
) -> dict[str, Any]:
    """Score exact mutation recall using clean-to-mutant atomic deltas."""

    prov_rows = [_provenance_dict(row) for row in provenance]
    clean_atoms = atoms_by_item(clean_violations)
    mutant_atoms = atoms_by_item(mutant_violations)
    per_operator_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    details: list[dict[str, Any]] = []

    for row in prov_rows:
        clean = clean_atoms.get(str(row["clean_item_id"]), [])
        mutant = mutant_atoms.get(str(row["mutant_item_id"]), [])
        clean_counter = Counter(atom.key for atom in clean)
        mutant_counter = Counter(atom.key for atom in mutant)
        delta_counter = mutant_counter - clean_counter
        mutant_by_key = {atom.key: atom for atom in mutant}
        delta = [
            mutant_by_key[key]
            for key, count in delta_counter.items()
            for _ in range(count)
        ]

        expected_in_clean = [atom for atom in clean if _matches_expected(atom, row)]
        expected_in_mutant = [atom for atom in mutant if _matches_expected(atom, row)]
        expected_in_delta = [atom for atom in delta if _matches_expected(atom, row)]
        exact = bool(expected_in_mutant)
        paired = bool(expected_in_delta) and not expected_in_clean
        expected_credit = 1 if expected_in_delta else 0
        duplicate_count = sum(max(0, count - 1) for count in delta_counter.values())
        extra_count = max(0, len(delta) - expected_credit)
        result = {
            "mutation_id": row["mutation_id"],
            "source_item_id": row["source_item_id"],
            "clean_item_id": row["clean_item_id"],
            "mutant_item_id": row["mutant_item_id"],
            "operator": row["operator"],
            "exact_detected": exact,
            "paired_discriminated": paired,
            "clean_expected_alarm": bool(expected_in_clean),
            "clean_alarm": bool(clean),
            "clean_atom_count": len(clean),
            "mutant_atom_count": len(mutant),
            "delta_atom_count": len(delta),
            "extra_alarm_count": extra_count,
            "duplicate_alarm_count": duplicate_count,
            "delta_atoms": [_atom_summary(atom) for atom in delta],
        }
        details.append(result)
        per_operator_rows[str(row["operator"])].append(result)

    total = len(details)
    exact = sum(bool(row["exact_detected"]) for row in details)
    paired = sum(bool(row["paired_discriminated"]) for row in details)
    clean_expected = sum(bool(row["clean_expected_alarm"]) for row in details)
    clean_alarm_pairs = sum(bool(row["clean_alarm"]) for row in details)
    unique_clean_ids = sorted({str(row["clean_item_id"]) for row in prov_rows})
    clean_alarm_items = sum(bool(clean_atoms.get(item_id)) for item_id in unique_clean_ids)
    per_operator = {
        operator: _aggregate_pair_rows(rows)
        for operator, rows in sorted(per_operator_rows.items())
    }
    return {
        "pairs": total,
        "exact_detected": exact,
        "exact_recall": exact / total if total else 0.0,
        "exact_recall_wilson95": list(wilson_interval(exact, total)),
        "paired_discriminated": paired,
        "paired_discrimination": paired / total if total else 0.0,
        "paired_discrimination_wilson95": list(wilson_interval(paired, total)),
        "clean_expected_alarm_pairs": clean_expected,
        "clean_expected_alarm_rate": clean_expected / total if total else 0.0,
        "clean_expected_alarm_wilson95": list(wilson_interval(clean_expected, total)),
        "clean_alarm_pairs": clean_alarm_pairs,
        "clean_alarm_pair_rate": clean_alarm_pairs / total if total else 0.0,
        "clean_alarm_pair_wilson95": list(wilson_interval(clean_alarm_pairs, total)),
        "unique_clean_items": len(unique_clean_ids),
        "clean_alarm_items": clean_alarm_items,
        "clean_alarm_item_rate": (
            clean_alarm_items / len(unique_clean_ids) if unique_clean_ids else 0.0
        ),
        "clean_alarm_item_wilson95": list(wilson_interval(
            clean_alarm_items, len(unique_clean_ids),
        )),
        "extra_alarm_count": sum(int(row["extra_alarm_count"]) for row in details),
        "duplicate_alarm_count": sum(int(row["duplicate_alarm_count"]) for row in details),
        "per_operator": per_operator,
        "misses": [row for row in details if not row["exact_detected"]],
        "pair_failures": [row for row in details if not row["paired_discriminated"]],
        "details": details,
    }


def violation_atoms(violation: Violation | Mapping[str, Any]) -> list[FindingAtom]:
    """Expand an aggregate checker violation into independently scored facts."""

    row = asdict(violation) if isinstance(violation, Violation) else dict(violation)
    item_id = str(row.get("item_id") or "")
    defect_type = str(row.get("defect_type") or "unknown")
    message = str(row.get("message") or "")
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}

    if isinstance(evidence.get("unresolved_manifest_entries"), list):
        return [
            _finding_atom(item_id, defect_type, "manifest_unresolved", payload, message)
            for payload in evidence["unresolved_manifest_entries"]
        ]
    if isinstance(evidence.get("dangling_edges"), list):
        return [
            _finding_atom(item_id, defect_type, "dependency_dangling", payload, message)
            for payload in evidence["dangling_edges"]
        ]
    if "raw_output_files" in evidence and "contract_required_files" in evidence:
        payload = {
            "raw_output_files": evidence.get("raw_output_files"),
            "contract_required_files": evidence.get("contract_required_files"),
        }
        return [_finding_atom(
            item_id, defect_type, "contract_filename_conflict", payload, message,
        )]
    if "raw_rubric_count" in evidence and "evaluator_rubric_count" in evidence:
        payload = {
            "raw_rubric_count": evidence.get("raw_rubric_count"),
            "evaluator_rubric_count": evidence.get("evaluator_rubric_count"),
        }
        return [_finding_atom(
            item_id, defect_type, "raw_evaluator_divergence", payload, message,
        )]
    if "rubric_count" in evidence and "rubric_type_count" in evidence:
        payload = {
            "rubric_count": evidence.get("rubric_count"),
            "rubric_type_count": evidence.get("rubric_type_count"),
        }
        return [_finding_atom(
            item_id, defect_type, "rubric_types_cardinality", payload, message,
        )]
    if isinstance(evidence.get("missing_paths"), list):
        return [
            _finding_atom(item_id, defect_type, "inaccessible_attachment", path, message)
            for path in evidence["missing_paths"]
        ]
    if isinstance(evidence.get("files"), list):
        return [
            _finding_atom(item_id, defect_type, "visible_reference_generator", payload, message)
            for payload in evidence["files"]
        ]
    return [_finding_atom(item_id, defect_type, f"generic:{defect_type}", evidence, message)]


def atoms_by_item(
    violations: Sequence[Violation | Mapping[str, Any]],
) -> dict[str, list[FindingAtom]]:
    out: dict[str, list[FindingAtom]] = defaultdict(list)
    for violation in violations:
        for atom in violation_atoms(violation):
            out[atom.item_id].append(atom)
    return dict(out)


def wilson_interval(
    successes: int,
    total: int,
    z: float = 1.959963984540054,
) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
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


def render_workspace_challenge_markdown(
    challenge: WorkspaceChallenge,
    score: Mapping[str, Any],
    *,
    dataset: str | None = None,
) -> str:
    lines = [
        "# Workspace-Bench paired invariant experiment",
        "",
        f"- Dataset: `{dataset or '(not recorded)'}`",
        f"- Source items: `{challenge.source_items}`",
        f"- Clean items: `{len(challenge.clean_rows)}`",
        f"- Mutant pairs: `{score.get('pairs', 0)}`",
        f"- Seed: `{challenge.seed}`",
        "- Provenance is sidecar-only and is not present in audited rows.",
        "",
        "## Core metrics",
        "",
        "| Metric | Count | Rate | 95% Wilson CI |",
        "|---|---:|---:|---:|",
        _metric_line(
            score, "Exact mutation recall", "exact_detected",
            "exact_recall", "exact_recall_wilson95",
        ),
        _metric_line(
            score, "Paired discrimination", "paired_discriminated",
            "paired_discrimination", "paired_discrimination_wilson95",
        ),
        _metric_line(
            score, "Clean expected-signature alarms", "clean_expected_alarm_pairs",
            "clean_expected_alarm_rate", "clean_expected_alarm_wilson95",
        ),
        _metric_line(
            score, "Clean-side items with any invariant alarm", "clean_alarm_items",
            "clean_alarm_item_rate", "clean_alarm_item_wilson95",
            denominator=int(score.get("unique_clean_items", 0)),
        ),
        "",
        f"- Extra delta alarms: `{score.get('extra_alarm_count', 0)}`",
        f"- Duplicate delta alarms: `{score.get('duplicate_alarm_count', 0)}`",
        f"- Inapplicable mutations skipped: `{len(challenge.skipped)}`",
        "",
        "## By mutation",
        "",
        "| Mutation | Pairs | Exact recall | Paired discrimination | Extra | Duplicate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for operator, row in sorted((score.get("per_operator") or {}).items()):
        lines.append(
            f"| `{operator}` | {row['pairs']} | {row['exact_recall']:.3f} | "
            f"{row['paired_discrimination']:.3f} | {row['extra_alarm_count']} | "
            f"{row['duplicate_alarm_count']} |"
        )
    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        "These are controlled structural mutations with objective provenance. The metrics do not "
        "estimate the precision, recall, or defect prevalence of unmodified Workspace-Bench tasks. "
        "`clean-side alarm` reports existing deterministic invariant findings in source clones; it "
        "is not a human-gold false-positive rate.",
        "",
    ])
    return "\n".join(lines)


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


def opaque_id(seed: int, source_id: str, role: str) -> str:
    digest = hashlib.sha256(
        f"workspace-challenge-id:{seed}:{source_id}:{role}".encode("utf-8")
    ).hexdigest()[:24]
    return f"workspace-challenge-{digest}"


def rows_contain_provenance(rows: Iterable[Mapping[str, Any]]) -> bool:
    """Return whether audited rows contain a known provenance field."""

    return any(_PROVENANCE_FIELDS.intersection(row) for row in rows)


def _apply_operator(
    clean: dict[str, Any],
    operator: str,
    token: str,
) -> tuple[_Mutation | None, str | None]:
    if operator == MANIFEST_UNRESOLVED:
        return _manifest_unresolved(clean, token)
    if operator == DANGLING_DEPENDENCY:
        return _dangling_dependency(clean, token)
    if operator == CONTRACT_FILENAME_CONFLICT:
        return _contract_filename_conflict(clean, token)
    if operator == RAW_EVALUATOR_RUBRIC_DIVERGENCE:
        return _raw_evaluator_rubric_divergence(clean, token)
    if operator == RUBRIC_TYPES_CARDINALITY:
        return _rubric_types_cardinality(clean, token)
    raise ValueError(f"unknown Workspace challenge operator: {operator}")


def _manifest_unresolved(
    clean: dict[str, Any], token: str,
) -> tuple[_Mutation | None, str | None]:
    manifest = _workspace_list(clean, "data_manifest")
    input_files = clean.get("input_files")
    if not manifest or not isinstance(input_files, list) or not input_files:
        return None, "requires a non-empty data_manifest and materialized input_files"
    marker = f"__benchaudit_missing_{token}.bin"
    mutated = copy.deepcopy(clean)
    value = [*manifest, {"filename": marker, "stored_relpath": f"data/{marker}"}]
    _set_workspace_list(mutated, "data_manifest", value)
    return _Mutation(
        mutated,
        ("data_manifest", "context.data_manifest"),
        marker,
    ), None


def _dangling_dependency(
    clean: dict[str, Any], token: str,
) -> tuple[_Mutation | None, str | None]:
    manifest = _workspace_list(clean, "data_manifest")
    outputs = _canonical_outputs(clean)
    if not manifest and not outputs:
        return None, "requires at least one declared input or output artifact"
    graph = _workspace_list(clean, "file_dep_graph")
    source = (
        str(manifest[0].get("filename"))
        if manifest and isinstance(manifest[0], dict)
        else str(outputs[0])
    )
    marker = f"__benchaudit_dangling_{token}.out"
    mutated = copy.deepcopy(clean)
    value = [*graph, {"from": source, "to": marker}]
    _set_workspace_list(mutated, "file_dep_graph", value)
    return _Mutation(
        mutated,
        ("file_dep_graph", "context.file_dep_graph"),
        marker,
    ), None


def _contract_filename_conflict(
    clean: dict[str, Any], token: str,
) -> tuple[_Mutation | None, str | None]:
    outputs = _canonical_outputs(clean)
    raw_outputs = _raw_list(clean, "output_files")
    if not outputs or raw_outputs is None:
        return None, "requires canonical and raw output filenames"
    if {_normalized(value) for value in outputs} != {
        _normalized(value) for value in raw_outputs
    }:
        return None, "source output metadata already conflicts with the contract"
    suffix = Path(str(outputs[0])).suffix or ".out"
    marker = f"__benchaudit_contract_{token}{suffix}"
    value = [marker, *raw_outputs[1:]]
    mutated = copy.deepcopy(clean)
    _set_raw_list(mutated, "output_files", value)
    context = mutated.get("context")
    if isinstance(context, dict):
        context["output_files"] = copy.deepcopy(value)
    return _Mutation(
        mutated,
        ("output_files", "context.output_files"),
        marker,
    ), None


def _raw_evaluator_rubric_divergence(
    clean: dict[str, Any], token: str,
) -> tuple[_Mutation | None, str | None]:
    raw_rubrics = _raw_list(clean, "rubrics")
    evaluator = clean.get("evaluator")
    eval_rubrics = evaluator.get("rubrics") if isinstance(evaluator, dict) else None
    if raw_rubrics is None or not isinstance(eval_rubrics, list) or not eval_rubrics:
        return None, "requires raw and evaluator rubric lists"
    eval_text = [str(value) for value in eval_rubrics]
    if raw_rubrics != eval_text:
        return None, "source raw rubrics already diverge from evaluator rubrics"
    marker = f"__benchaudit_rubric_{token}"
    value = list(raw_rubrics)
    value[0] = f"{value[0]} [{marker}]"
    mutated = copy.deepcopy(clean)
    _set_raw_list(mutated, "rubrics", value)
    # The existing checker intentionally records only the two rubric counts, not
    # rubric contents, so this mutation is matched by its distinct atom kind.
    return _Mutation(mutated, ("rubrics",), None), None


def _rubric_types_cardinality(
    clean: dict[str, Any], token: str,
) -> tuple[_Mutation | None, str | None]:
    evaluator = clean.get("evaluator")
    if not isinstance(evaluator, dict) or not isinstance(evaluator.get("rubrics"), list):
        return None, "requires canonical evaluator rubrics"
    rubrics = evaluator["rubrics"]
    rubric_types = evaluator.get("rubric_types")
    if not isinstance(rubric_types, list):
        rubric_types = _raw_list(clean, "rubric_types")
    if rubric_types is None:
        rubric_types = []
    if len(rubric_types) != len(rubrics):
        return None, "source rubric_types cardinality already differs from rubrics"
    marker = f"__benchaudit_type_{token}"
    value = [*rubric_types, marker]
    mutated = copy.deepcopy(clean)
    mutated_evaluator = mutated.get("evaluator")
    assert isinstance(mutated_evaluator, dict)
    mutated_evaluator["rubric_types"] = copy.deepcopy(value)
    _set_raw_list(mutated, "rubric_types", value)
    return _Mutation(
        mutated,
        ("evaluator.rubric_types", "rubric_types"),
        None,
    ), None


def _clean_clone(source: dict[str, Any], clean_id: str) -> dict[str, Any]:
    row = copy.deepcopy(source)
    row["item_id"] = clean_id
    _strip_provenance(row)
    _declare_complete_challenge_inventory(row)
    return row


def _declare_complete_challenge_inventory(row: dict[str, Any]) -> None:
    """Make dependency mutations objectively decidable in the synthetic world.

    Public Workspace-Bench task manifests are not complete role-workspace
    inventories, so their absent graph endpoints cannot be called dangling.
    The controlled challenge explicitly declares all clean graph endpoints,
    inputs, and outputs present; the mutation then adds one endpoint absent from
    that frozen inventory.
    """
    names: list[str] = []
    for entry in _workspace_list(row, "data_manifest"):
        if isinstance(entry, dict) and entry.get("filename"):
            names.append(str(entry["filename"]))
    names.extend(_canonical_outputs(row))
    for edge in _workspace_list(row, "file_dep_graph"):
        if not isinstance(edge, dict):
            continue
        for key in ("from", "source", "to", "target"):
            if edge.get(key):
                names.append(str(edge[key]))
    inventory = list(dict.fromkeys(names))
    row["workspace_inventory"] = inventory
    row["workspace_inventory_complete"] = True
    context = row.get("context")
    if not isinstance(context, dict):
        context = {}
        row["context"] = context
    context["workspace_inventory"] = copy.deepcopy(inventory)
    context["workspace_inventory_complete"] = True


def _strip_provenance(row: dict[str, Any]) -> None:
    for key in _PROVENANCE_FIELDS:
        row.pop(key, None)


def _workspace_list(row: Mapping[str, Any], key: str) -> list[Any]:
    context = row.get("context")
    if isinstance(context, dict) and isinstance(context.get(key), list):
        return copy.deepcopy(context[key])
    value = parse_jsonish(row.get(key), [])
    return copy.deepcopy(value) if isinstance(value, list) else []


def _set_workspace_list(row: dict[str, Any], key: str, value: list[Any]) -> None:
    _set_raw_list(row, key, value)
    context = row.get("context")
    if isinstance(context, dict):
        context[key] = copy.deepcopy(value)


def _raw_list(row: Mapping[str, Any], key: str) -> list[str] | None:
    if key not in row:
        return None
    value = parse_jsonish(row.get(key), None)
    if not isinstance(value, list):
        return None
    return [str(item) for item in value]


def _set_raw_list(row: dict[str, Any], key: str, value: list[Any]) -> None:
    original = row.get(key)
    row[key] = (
        json.dumps(value, ensure_ascii=False)
        if isinstance(original, str)
        else copy.deepcopy(value)
    )


def _canonical_outputs(row: Mapping[str, Any]) -> list[str]:
    contract = row.get("output_contract")
    if not isinstance(contract, dict):
        return []
    values = contract.get("required_files") or contract.get("files") or []
    return [str(value) for value in values] if isinstance(values, list) else []


def _normalized(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").strip("/").casefold()


def _items_for_rows(rows: list[dict[str, Any]]):
    if not rows:
        return []
    mapping = load_mapping(None, rows)
    return build_items(rows, mapping)


def _finding_atom(
    item_id: str,
    defect_type: str,
    kind: str,
    payload: Any,
    message: str,
) -> FindingAtom:
    fingerprint = hashlib.sha256(
        canonical_json({"defect_type": defect_type, "kind": kind, "payload": payload}).encode(
            "utf-8"
        )
    ).hexdigest()
    return FindingAtom(item_id, defect_type, kind, fingerprint, payload, message)


def _matches_expected(atom: FindingAtom, row: Mapping[str, Any]) -> bool:
    if atom.defect_type != str(row.get("expected_defect_type")):
        return False
    if atom.kind != str(row.get("expected_atom_kind")):
        return False
    marker = row.get("evidence_marker")
    return marker in atom.searchable_text if marker else True


def _aggregate_pair_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    exact = sum(bool(row["exact_detected"]) for row in rows)
    paired = sum(bool(row["paired_discriminated"]) for row in rows)
    clean = sum(bool(row["clean_expected_alarm"]) for row in rows)
    return {
        "pairs": total,
        "exact_detected": exact,
        "exact_recall": exact / total if total else 0.0,
        "exact_recall_wilson95": list(wilson_interval(exact, total)),
        "paired_discriminated": paired,
        "paired_discrimination": paired / total if total else 0.0,
        "paired_discrimination_wilson95": list(wilson_interval(paired, total)),
        "clean_expected_alarm_pairs": clean,
        "clean_expected_alarm_rate": clean / total if total else 0.0,
        "clean_expected_alarm_wilson95": list(wilson_interval(clean, total)),
        "extra_alarm_count": sum(int(row["extra_alarm_count"]) for row in rows),
        "duplicate_alarm_count": sum(int(row["duplicate_alarm_count"]) for row in rows),
    }


def _provenance_dict(
    row: WorkspaceChallengeProvenance | Mapping[str, Any],
) -> dict[str, Any]:
    return asdict(row) if isinstance(row, WorkspaceChallengeProvenance) else dict(row)


def _atom_summary(atom: FindingAtom) -> dict[str, Any]:
    return {
        "defect_type": atom.defect_type,
        "kind": atom.kind,
        "key": atom.key,
        "payload": atom.payload,
        "message": atom.message,
    }


def _violation_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("item_id") or ""),
        str(row.get("defect_type") or ""),
        str(row.get("detection_method") or ""),
        str(row.get("message") or ""),
    )


def _metric_line(
    score: Mapping[str, Any],
    label: str,
    count_key: str,
    rate_key: str,
    ci_key: str,
    *,
    denominator: int | None = None,
) -> str:
    count = int(score.get(count_key, 0))
    total = int(score.get("pairs", 0) if denominator is None else denominator)
    rate = float(score.get(rate_key, 0.0))
    ci = score.get(ci_key) or [0.0, 0.0]
    return (
        f"| {label} | {count}/{total} | {rate:.3f} | "
        f"[{float(ci[0]):.3f}, {float(ci[1]):.3f}] |"
    )
