from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .artifact_consistency import (
    append_targeted_search_context,
    extract_rubrics,
    full_context_text,
    preview,
    strictness_grounding_terms,
)
from .loader import build_items, load_mapping, load_rows
from .schema import BenchmarkItem, FieldMapping


def build_forensic_bundle(
    *,
    input_path: Path,
    item_id: str,
    report_path: Path | None = None,
    investigation_path: Path | None = None,
    root: Path | None = None,
    max_context_chars: int = 30000,
) -> dict[str, Any]:
    report = load_optional_json(report_path)
    item = load_item(input_path, item_id, report)
    root = root or input_path.parent
    violations = select_item_rows(report, "violations", item_id)
    investigations = select_item_rows(load_optional_json(investigation_path), "investigations", item_id)
    terms = forensic_terms(item, violations, investigations)
    base_context = full_context_text(item, root, max_context_chars)
    evidence_context = append_targeted_search_context(
        item,
        root,
        base_context,
        terms,
        rubric="\n".join(extract_rubrics(item)),
        max_chars=max(6000, max_context_chars // 2),
    )
    return {
        "item_id": item.item_id,
        "task": item.task,
        "output_contract": item.output_contract,
        "rubrics": extract_rubrics(item),
        "context_keys": sorted(item.context.keys()),
        "input_files": item.raw.get("input_files", []),
        "candidate_violations": violations,
        "investigations": investigations,
        "target_terms": terms,
        "evidence_context": evidence_context,
    }


def load_item(input_path: Path, item_id: str, report: dict[str, Any] | None) -> BenchmarkItem:
    rows = load_rows(input_path)
    mapping = mapping_from_report(report) if report else load_mapping(None, rows)
    items = {str(item.item_id): item for item in build_items(rows, mapping)}
    if item_id not in items:
        raise ValueError(f"item_id {item_id!r} not found in {input_path}")
    return items[item_id]


def mapping_from_report(report: dict[str, Any] | None) -> FieldMapping:
    mapping_data = (report or {}).get("field_mapping") or {}
    return FieldMapping(
        item_id=mapping_data.get("item_id"),
        task=mapping_data.get("task"),
        context=list(mapping_data.get("context") or []),
        choices=mapping_data.get("choices"),
        gold=mapping_data.get("gold"),
        aliases=mapping_data.get("aliases"),
        output_contract=mapping_data.get("output_contract"),
        evaluator=mapping_data.get("evaluator"),
        metadata=list(mapping_data.get("metadata") or []),
    )


def load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def select_item_rows(payload: dict[str, Any] | None, key: str, item_id: str) -> list[dict[str, Any]]:
    if not payload:
        return []
    rows = payload.get(key, [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and str(row.get("item_id")) == item_id]


def forensic_terms(
    item: BenchmarkItem,
    violations: list[dict[str, Any]],
    investigations: list[dict[str, Any]],
) -> list[str]:
    chunks: list[str] = []
    chunks.append(str(item.task or ""))
    chunks.extend(extract_rubrics(item))
    for row in violations:
        chunks.append(str(row.get("message", "")))
        chunks.append(json.dumps(row.get("evidence", {}), ensure_ascii=False))
    for row in investigations:
        for key in (
            "claim",
            "evidence_from_task",
            "evidence_from_input",
            "evidence_from_rubric",
            "evidence_from_contract",
            "reasoning",
        ):
            chunks.append(str(row.get(key, "")))
    terms: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        for term in strictness_grounding_terms(chunk):
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(term)
            if len(terms) >= 96:
                return terms
    return terms


def write_forensic_json(path: Path, bundle: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_forensic_markdown(path: Path, bundle: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_verdict = defaultdict(int)
    for row in bundle.get("investigations", []):
        by_verdict[str(row.get("verdict", "unknown"))] += 1
    lines: list[str] = []
    lines.append(f"# Forensic Evidence Bundle: `{bundle['item_id']}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Candidate violations: `{len(bundle.get('candidate_violations', []))}`")
    lines.append(f"- Investigations: `{len(bundle.get('investigations', []))}`")
    if by_verdict:
        lines.append(f"- Investigation verdicts: `{dict(by_verdict)}`")
    lines.append("")
    lines.append("## Task")
    lines.append("")
    lines.append(preview(bundle.get("task"), 4000) or "(missing)")
    lines.append("")
    lines.append("## Output Contract")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(bundle.get("output_contract"), indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Rubrics")
    lines.append("")
    for index, rubric in enumerate(bundle.get("rubrics", [])):
        lines.append(f"{index}. {rubric}")
    lines.append("")
    lines.append("## Candidate Violations")
    lines.append("")
    for row in bundle.get("candidate_violations", []):
        lines.append(f"- `{row.get('defect_type')}` / `{row.get('detection_method')}`: {row.get('message')}")
    lines.append("")
    lines.append("## Investigations")
    lines.append("")
    for row in bundle.get("investigations", []):
        lines.append(
            f"- `{row.get('verdict')}` / `{row.get('issue_category')}` "
            f"(confidence={row.get('confidence')}): {row.get('claim')}"
        )
        if row.get("reasoning"):
            lines.append(f"  - Reasoning: {row.get('reasoning')}")
    lines.append("")
    lines.append("## Target Terms")
    lines.append("")
    lines.append(", ".join(bundle.get("target_terms", [])) or "(none)")
    lines.append("")
    lines.append("## Evidence Context")
    lines.append("")
    lines.append("```text")
    lines.append(str(bundle.get("evidence_context", "")))
    lines.append("```")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
