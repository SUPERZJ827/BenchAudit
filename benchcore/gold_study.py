from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from .investigator import ReportItemIndex, load_report_items


def build_gold_study(
    *,
    input_path: Path,
    report_path: Path,
    investigation_path: Path | None,
    flagged_size: int,
    unflagged_size: int,
    seed: int,
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    items = load_report_items(input_path, report)
    violations_by_row: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unresolved_violations = 0
    for violation in report.get("violations", []):
        target_row_uids = resolve_report_row_uids(
            violation, items, include_dataset_targets=True,
        )
        if not target_row_uids:
            unresolved_violations += 1
            continue
        for row_uid in target_row_uids:
            violations_by_row[row_uid].append(violation)

    investigations_by_row: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unresolved_investigations = 0
    if investigation_path:
        investigation = json.loads(investigation_path.read_text(encoding="utf-8"))
        for row in investigation.get("investigations", []):
            target_row_uids = resolve_report_row_uids(row, items)
            if not target_row_uids:
                unresolved_investigations += 1
                continue
            investigations_by_row[target_row_uids[0]].append(row)

    if unresolved_violations or unresolved_investigations:
        raise ValueError(
            "Gold-study report rows could not be joined to exact live source rows "
            f"(violations={unresolved_violations}, "
            f"investigations={unresolved_investigations}). Every report row must "
            "carry a valid row_uid; refusing an unverified identity join."
        )

    rng = random.Random(seed)
    flagged_row_uids = stratified_flagged_sample(
        violations_by_row,
        investigations_by_row,
        size=max(flagged_size, 0),
        rng=rng,
    )
    all_row_uids = set(items.by_row_uid)
    unflagged_pool = sorted(all_row_uids - set(violations_by_row))
    rng.shuffle(unflagged_pool)
    unflagged_row_uids = unflagged_pool[: max(unflagged_size, 0)]

    records: list[dict[str, Any]] = []
    for row_uid in [*flagged_row_uids, *unflagged_row_uids]:
        item = items.by_row_uid[row_uid]
        investigations = investigations_by_row.get(row_uid, [])
        records.append({
            "item_id": item.item_id,
            "row_uid": row_uid,
            "sampling_group": (
                "flagged" if row_uid in violations_by_row else "unflagged_control"
            ),
            "sampling_stratum": task_stratum(
                violations_by_row.get(row_uid, []),
                investigations,
            ),
            "task": item.task,
            "context": item.context,
            "output_contract": item.output_contract,
            "evaluator": item.evaluator,
            "candidate_violations": violations_by_row.get(row_uid, []),
            "investigations": investigations,
            "human_label": "TODO",
            "human_categories": [],
            "human_severity": "TODO",
            "annotator_confidence": "TODO",
            "notes": "TODO",
        })

    return {
        "manifest": {
            "input_path": str(input_path),
            "report_path": str(report_path),
            "investigation_path": str(investigation_path) if investigation_path else None,
            "input_sha256": file_sha256(input_path),
            "report_sha256": file_sha256(report_path),
            "investigation_sha256": file_sha256(investigation_path) if investigation_path else None,
            "seed": seed,
            "flagged_requested": flagged_size,
            "unflagged_requested": unflagged_size,
            "flagged_selected": len(flagged_row_uids),
            "unflagged_selected": len(unflagged_row_uids),
            "selected_items": len(records),
            "identity_field": "row_uid",
            "unresolved_violation_rows": unresolved_violations,
            "unresolved_investigation_rows": unresolved_investigations,
        },
        "records": records,
    }


def resolve_report_row_uids(
    row: dict[str, Any],
    items: ReportItemIndex,
    *,
    include_dataset_targets: bool = False,
) -> list[str]:
    """Resolve a report row to live source rows without item-id guessing.

    New reports carry ``row_uid``.  Legacy rows may fall back to ``item_id``
    only when that ID is unique in the live input.  Dataset-scoped findings can
    explicitly target several rows, but every target and the source row must
    resolve before any of them enters the annotation sample.
    """

    if not isinstance(row, dict):
        return []
    source = items.resolve(row)
    if source is None or source.row_uid is None:
        return []
    source_uid = str(source.row_uid)
    if not include_dataset_targets:
        return [source_uid]
    evidence = row.get("evidence")
    targets = evidence.get("target_row_uids") if isinstance(evidence, dict) else None
    if targets is None:
        return [source_uid]
    if (
        not isinstance(targets, list)
        or not targets
        or any(not isinstance(value, str) or not value for value in targets)
    ):
        return []
    normalized = list(dict.fromkeys(targets))
    if len(normalized) != len(targets) or source_uid not in normalized:
        return []
    if any(row_uid not in items.by_row_uid for row_uid in normalized):
        return []
    return normalized


def stratified_flagged_sample(
    violations_by_item: dict[str, list[dict[str, Any]]],
    investigations_by_item: dict[str, list[dict[str, Any]]],
    *,
    size: int,
    rng: random.Random,
) -> list[str]:
    strata: dict[str, list[str]] = defaultdict(list)
    for item_id, violations in violations_by_item.items():
        strata[task_stratum(violations, investigations_by_item.get(item_id, []))].append(item_id)
    for values in strata.values():
        rng.shuffle(values)
    selected: list[str] = []
    while len(selected) < size:
        changed = False
        for stratum in sorted(strata):
            if strata[stratum] and len(selected) < size:
                selected.append(strata[stratum].pop())
                changed = True
        if not changed:
            break
    return selected


def task_stratum(
    violations: list[dict[str, Any]],
    investigations: list[dict[str, Any]],
) -> str:
    if investigations:
        priority = {"likely_true": 0, "uncertain": 1, "false_positive": 2}
        row = min(
            investigations,
            key=lambda entry: priority.get(str(entry.get("verdict", "uncertain")), 1),
        )
        return f"{row.get('verdict', 'uncertain')}:{row.get('issue_category', 'other')}"
    if violations:
        return f"candidate:{violations[0].get('defect_type', 'other')}"
    return "unflagged_control"


def write_gold_study_jsonl(path: Path, study: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"_manifest": study["manifest"]}, ensure_ascii=False) + "\n")
        for record in study["records"]:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_gold_study_markdown(path: Path, study: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = study["manifest"]
    lines = [
        "# Benchmark Audit Gold Study",
        "",
        "This workbook includes both flagged cases and randomly sampled unflagged controls.",
        "Unflagged controls are required to estimate false negatives and recall.",
        "",
        f"- Seed: `{manifest['seed']}`",
        f"- Flagged cases: `{manifest['flagged_selected']}`",
        f"- Unflagged controls: `{manifest['unflagged_selected']}`",
        f"- Input SHA-256: `{manifest['input_sha256']}`",
        "",
        "Allowed `human_label` values: `true_issue`, `clean`, `borderline`, `uncertain`.",
        "Annotators should inspect original input artifacts and must not rely only on investigator summaries.",
        "",
        "## Cases",
        "",
    ]
    for index, record in enumerate(study["records"], 1):
        lines.extend(render_gold_case(index, record))
    path.write_text("\n".join(lines), encoding="utf-8")


def render_gold_case(index: int, record: dict[str, Any]) -> list[str]:
    identity = str(record["item_id"])
    if record.get("row_uid") not in (None, ""):
        identity += f" [{record['row_uid']}]"
    lines = [
        f"### {index}. `{identity}`",
        "",
        f"- sampling_group: `{record['sampling_group']}`",
        f"- sampling_stratum: `{record['sampling_stratum']}`",
        "- human_label: `TODO`",
        "- human_categories: `TODO`",
        "- human_severity: `TODO`",
        "- annotator_confidence: `TODO`",
        "- notes: `TODO`",
        "",
        "**Task**",
        "",
        json_block(record.get("task")),
        "",
        "**Output contract**",
        "",
        json_block(record.get("output_contract")),
        "",
        "**Evaluator / rubrics**",
        "",
        json_block(record.get("evaluator")),
        "",
    ]
    if record.get("candidate_violations"):
        lines.extend(["**Candidate findings**", "", json_block(record["candidate_violations"]), ""])
    else:
        lines.extend(["**Candidate findings**", "", "None (negative control).", ""])
    if record.get("investigations"):
        lines.extend(["**Investigation evidence**", "", json_block(record["investigations"]), ""])
    lines.extend(["**Context / input references**", "", json_block(record.get("context")), ""])
    return lines


def json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def file_sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
