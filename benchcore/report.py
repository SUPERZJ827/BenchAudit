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
    run_metadata: dict[str, Any] | None = None,
    benchmark_package: dict[str, Any] | None = None,
    audit_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = {
        "input_path": input_path,
        "summary": summarize(items, violations),
        "field_mapping": asdict(mapping),
        "methods_run": methods_run or [],
        "violations": [asdict(v) for v in violations],
    }
    if run_metadata:
        report["run_metadata"] = run_metadata
    if benchmark_package:
        report["benchmark_package"] = benchmark_package
    if audit_plan:
        report["audit_plan"] = audit_plan
    return report


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
    metadata = report.get("run_metadata") or {}
    if metadata:
        lines.append(f"- Elapsed seconds: `{metadata.get('elapsed_seconds', 'unknown')}`")
        git = metadata.get("git") or {}
        if git.get("commit"):
            dirty = " dirty" if git.get("dirty") else ""
            lines.append(f"- Git commit: `{git['commit']}{dirty}`")
        llm = metadata.get("llm") or {}
        if llm.get("model"):
            lines.append(
                f"- LLM: `{llm['model']}` "
                f"(API attempts={llm.get('api_attempts', 0)}, cache hits={llm.get('cache_hits', 0)})"
            )
    lines.append("")
    audit_plan = report.get("audit_plan") or {}
    if audit_plan:
        lines.append("## Audit Coverage")
        lines.append("")
        lines.append(
            f"- Detected family: `{audit_plan.get('family', 'unknown')}` "
            f"(confidence={audit_plan.get('family_confidence', 0):.2f})"
        )
        plan_summary = audit_plan.get("summary") or {}
        lines.append(f"- Executed checks: `{plan_summary.get('executed', 0)}`")
        lines.append(f"- Selected checks not run: `{plan_summary.get('selected', 0)}`")
        lines.append(f"- Skipped checks: `{plan_summary.get('skipped', 0)}`")
        lines.append(f"- Unsupported checks: `{plan_summary.get('unsupported', 0)}`")
        for key, value in sorted((audit_plan.get("artifact_coverage") or {}).items()):
            lines.append(f"- `{key}`: `{value}`")
        for warning in audit_plan.get("unknowns") or []:
            lines.append(f"- Unknown: {warning}")
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
            if isinstance(v.get("evidence"), dict) and v["evidence"].get("todo"):
                todo = str(v["evidence"]["todo"]).strip()
                if todo.lower().startswith("todo:"):
                    todo = todo.split(":", 1)[1].strip()
                lines.append(f"  - TODO: {todo}")
            if v.get("evidence"):
                compact = json.dumps(v["evidence"], ensure_ascii=False)
                if len(compact) > 500:
                    compact = compact[:500] + "..."
                lines.append(f"  - Evidence: `{compact}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
