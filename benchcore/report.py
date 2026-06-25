from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .schema import BenchmarkItem, FieldMapping, Violation


def summarize(items: list[BenchmarkItem], violations: list[Violation]) -> dict[str, Any]:
    confirmed = [v for v in violations if not v.review_only]
    review = [v for v in violations if v.review_only]
    return {
        "items": len(items),
        "violation_count": len(violations),
        "confirmed_count": len(confirmed),
        "review_signal_count": len(review),
        "artifact_distribution": dict(Counter(v.artifact for v in violations)),
        "confirmed_artifact_distribution": dict(Counter(v.artifact for v in confirmed)),
        "defect_distribution": dict(Counter(v.defect_type for v in violations)),
        "method_distribution": dict(Counter(v.detection_method for v in violations)),
        "scope_distribution": dict(Counter(v.defect_scope for v in violations)),
        "severity_distribution": dict(Counter(v.severity for v in violations)),
        "affected_items": len({v.item_id for v in violations}),
        "confirmed_affected_items": len({v.item_id for v in confirmed}),
        "review_items": len({v.item_id for v in review}),
    }


def build_report(
    input_path: str,
    items: list[BenchmarkItem],
    violations: list[Violation],
    mapping: FieldMapping,
    methods_run: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "input_path": input_path,
        "summary": summarize(items, violations),
        "field_mapping": asdict(mapping),
        "methods_run": methods_run or [],
        "violations": [asdict(v) for v in violations],
    }


def write_json_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    violations = report["violations"]
    by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for violation in violations:
        by_item[violation["item_id"]].append(violation)

    lines: list[str] = []
    lines.append("# Benchmark Audit Report")
    lines.append("")
    lines.append(f"- Input: `{report['input_path']}`")
    lines.append(f"- Items: `{summary['items']}`")
    lines.append(f"- Violations: `{summary['violation_count']}`")
    lines.append(f"- Confirmed: `{summary['confirmed_count']}`")
    lines.append(f"- Review signals: `{summary['review_signal_count']}`")
    lines.append(f"- Affected items: `{summary['affected_items']}`")
    if report.get("methods_run"):
        lines.append(f"- Methods run: `{', '.join(report['methods_run'])}`")
    lines.append("")
    lines.append("## Artifact Distribution")
    lines.append("")
    for key, value in sorted(summary["artifact_distribution"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Defect Distribution")
    lines.append("")
    for key, value in sorted(summary["defect_distribution"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Detection Method Distribution")
    lines.append("")
    for key, value in sorted(summary.get("method_distribution", {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Defect Scope Distribution")
    lines.append("")
    for key, value in sorted(summary.get("scope_distribution", {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Field Mapping")
    lines.append("")
    for key, value in report["field_mapping"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Cases")
    lines.append("")
    for item_id, item_violations in by_item.items():
        lines.append(f"### `{item_id}`")
        lines.append("")
        for v in item_violations:
            mark = "review" if v["review_only"] else "confirmed"
            lines.append(
                f"- `{v['defect_type']}` / `{v['artifact']}` / `{v['detection_method']}` / "
                f"`{v['severity']}` / {mark} "
                f"(confidence={v['confidence']:.2f})"
            )
            lines.append(f"  - {v['message']}")
            if v.get("suggested_repair"):
                lines.append(f"  - Repair: {v['suggested_repair']}")
            if v.get("evidence"):
                compact = json.dumps(v["evidence"], ensure_ascii=False)
                if len(compact) > 500:
                    compact = compact[:500] + "..."
                lines.append(f"  - Evidence: `{compact}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
