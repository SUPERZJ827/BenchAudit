from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from .investigator import load_report_items


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
    violations_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for violation in report.get("violations", []):
        violations_by_item[str(violation.get("item_id", ""))].append(violation)

    investigations_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if investigation_path:
        investigation = json.loads(investigation_path.read_text(encoding="utf-8"))
        for row in investigation.get("investigations", []):
            investigations_by_item[str(row.get("item_id", ""))].append(row)

    rng = random.Random(seed)
    flagged_ids = stratified_flagged_sample(
        violations_by_item,
        investigations_by_item,
        size=max(flagged_size, 0),
        rng=rng,
    )
    unflagged_pool = sorted(set(items) - set(violations_by_item))
    rng.shuffle(unflagged_pool)
    unflagged_ids = unflagged_pool[: max(unflagged_size, 0)]

    records: list[dict[str, Any]] = []
    for item_id in [*flagged_ids, *unflagged_ids]:
        item = items[item_id]
        investigations = investigations_by_item.get(item_id, [])
        records.append({
            "item_id": item_id,
            "sampling_group": "flagged" if item_id in violations_by_item else "unflagged_control",
            "sampling_stratum": task_stratum(
                violations_by_item.get(item_id, []),
                investigations,
            ),
            "task": item.task,
            "context": item.context,
            "output_contract": item.output_contract,
            "evaluator": item.evaluator,
            "candidate_violations": violations_by_item.get(item_id, []),
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
            "flagged_selected": len(flagged_ids),
            "unflagged_selected": len(unflagged_ids),
            "selected_items": len(records),
        },
        "records": records,
    }


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
    lines = [
        f"### {index}. `{record['item_id']}`",
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
