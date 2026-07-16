from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from .coverage import AuditLedgerEntry, ledger_entry_dict, summarize_coverage
from .schema import BenchmarkItem, FieldMapping, Violation
from .promotion import enforce_all


def summarize(
    items: list[BenchmarkItem],
    violations: list[Violation],
    audit_ledger: Sequence[AuditLedgerEntry | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    enforce_all(violations, items)
    confirmed = [v for v in violations if v.evidence_tier == "confirmed"]
    review = [v for v in violations if v.evidence_tier == "review"]
    unknown = [v for v in violations if v.evidence_tier == "unknown"]
    summary = {
        "items": len(items),
        "violation_count": len(violations),
        "confirmed_count": len(confirmed),
        "review_signal_count": len(review),
        "unknown_count": len(unknown),
        "evidence_tier_distribution": dict(Counter(v.evidence_tier for v in violations)),
        "proof_kind_distribution": dict(Counter(v.proof_kind for v in violations)),
        "artifact_distribution": dict(Counter(v.artifact for v in violations)),
        "confirmed_artifact_distribution": dict(Counter(v.artifact for v in confirmed)),
        "defect_distribution": dict(Counter(v.defect_type for v in violations)),
        "method_distribution": dict(Counter(v.detection_method for v in violations)),
        "scope_distribution": dict(Counter(v.defect_scope for v in violations)),
        "severity_distribution": dict(Counter(v.severity for v in violations)),
        "affected_items": len({
            v.item_id for v in violations if v.defect_scope != "operational"
        }),
        "operational_affected_items": len({
            v.item_id for v in violations if v.defect_scope == "operational"
        }),
        "affected_rows": len({
            v.row_uid for v in violations
            if v.row_uid is not None and v.defect_scope != "operational"
        }),
        "confirmed_affected_items": len({v.item_id for v in confirmed}),
        "review_items": len({v.item_id for v in review}),
    }
    if audit_ledger is not None:
        summary["audit_coverage"] = summarize_coverage(audit_ledger)
    return summary


def build_report(
    input_path: str,
    items: list[BenchmarkItem],
    violations: list[Violation],
    mapping: FieldMapping,
    methods_run: list[str] | None = None,
    run_metadata: dict[str, Any] | None = None,
    benchmark_package: dict[str, Any] | None = None,
    audit_plan: dict[str, Any] | None = None,
    audit_ledger: Sequence[AuditLedgerEntry | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    enforce_all(violations, items)
    serialized_ledger = (
        [ledger_entry_dict(entry) for entry in audit_ledger]
        if audit_ledger is not None
        else None
    )
    report = {
        "input_path": input_path,
        "source_identity": build_source_identity(input_path, items),
        "summary": summarize(items, violations, serialized_ledger),
        "field_mapping": asdict(mapping),
        "methods_run": methods_run or [],
        "violations": [asdict(v) for v in violations],
    }
    if serialized_ledger is not None:
        report["coverage_ledger"] = serialized_ledger
    if run_metadata:
        report["run_metadata"] = run_metadata
    if benchmark_package:
        report["benchmark_package"] = benchmark_package
    if audit_plan:
        report["audit_plan"] = audit_plan
    return report


def build_source_identity(
    input_path: str,
    items: list[BenchmarkItem],
) -> dict[str, Any]:
    """Bind report row identities to exact source bytes and original indices."""

    path = Path(input_path).expanduser()
    input_sha256 = None
    input_size_bytes = None
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        input_sha256 = digest.hexdigest()
        input_size_bytes = path.stat().st_size
    row_manifest = [
        {
            "row_uid": item.row_uid,
            "source_row_index": item.source_row_index,
            "source_row_sha256": item.source_row_sha256,
        }
        for item in items
    ]
    row_manifest_bytes = json.dumps(
        row_manifest,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": "source-row-identity-v1",
        "row_uid_scheme": "zero_based_original_source_index",
        "input_sha256": input_sha256,
        "input_size_bytes": input_size_bytes,
        "audited_rows": len(items),
        "audited_row_manifest_sha256": hashlib.sha256(
            row_manifest_bytes
        ).hexdigest(),
    }


def write_json_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    violations = report["violations"]
    by_item: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for violation in violations:
        by_item[(
            str(violation["item_id"]),
            str(violation.get("row_uid") or ""),
        )].append(violation)

    lines: list[str] = []
    lines.append("# Benchmark Audit Report")
    lines.append("")
    lines.append(f"- Input: `{report['input_path']}`")
    lines.append(f"- Items: `{summary['items']}`")
    lines.append(f"- Violations: `{summary['violation_count']}`")
    lines.append(f"- Confirmed: `{summary['confirmed_count']}`")
    lines.append(f"- Review signals: `{summary['review_signal_count']}`")
    lines.append(f"- Unknown-tier findings: `{summary.get('unknown_count', 0)}`")
    lines.append(f"- Affected items: `{summary['affected_items']}`")
    lines.append(
        f"- Operationally affected items: "
        f"`{summary.get('operational_affected_items', 0)}`"
    )
    if report.get("methods_run"):
        lines.append(f"- Methods run: `{', '.join(report['methods_run'])}`")
    coverage = summary.get("audit_coverage") or {}
    if coverage:
        lines.append(f"- Planned item×checker checks: `{coverage['planned']}`")
        lines.append(f"- Eligible checks: `{coverage['eligible']}`")
        lines.append(f"- Completed checks: `{coverage['completed']}`")
        lines.append(f"- Coverage unknown: `{coverage['unknown']}`")
        lines.append(
            f"- Operational failures: `{coverage['operational_failed']}`"
        )
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
        lines.append(f"- Partially executed checks: `{plan_summary.get('partial', 0)}`")
        lines.append(f"- Failed checks: `{plan_summary.get('failed', 0)}`")
        lines.append(f"- Ineligible checks: `{plan_summary.get('ineligible', 0)}`")
        lines.append(f"- Selected checks not run: `{plan_summary.get('selected', 0)}`")
        lines.append(f"- Skipped checks: `{plan_summary.get('skipped', 0)}`")
        lines.append(f"- Unsupported checks: `{plan_summary.get('unsupported', 0)}`")
        for key, value in sorted((audit_plan.get("artifact_coverage") or {}).items()):
            lines.append(f"- `{key}`: `{value}`")
        for warning in audit_plan.get("unknowns") or []:
            lines.append(f"- Unknown: {warning}")
        lines.append("")
    if coverage:
        lines.append("## Item × Checker Coverage Ledger")
        lines.append("")
        lines.append(
            "`completed_no_finding` means only that a checker returned normally "
            "without emitting a finding. It is not a clean-benchmark verdict."
        )
        lines.append("")
        lines.append(f"- Planned: `{coverage['planned']}`")
        lines.append(f"- Explicitly eligible: `{coverage['eligible']}`")
        lines.append(
            f"- Eligibility unknown: `{coverage['eligibility_unknown']}`"
        )
        lines.append(f"- Attempted: `{coverage['attempted']}`")
        lines.append(f"- Completed: `{coverage['completed']}`")
        lines.append(
            f"- Completed without finding: `{coverage['completed_no_finding']}`"
        )
        lines.append(f"- Finding: `{coverage['finding']}`")
        lines.append(f"- Unknown/incomplete: `{coverage['unknown']}`")
        lines.append(
            f"- Operational failures: `{coverage['operational_failed']}`"
        )
        lines.append(f"- Security blocked: `{coverage['security_blocked']}`")
        lines.append(f"- Unsupported: `{coverage['unsupported']}`")
        lines.append(f"- Abstained: `{coverage['abstained']}`")
        lines.append(f"- Ineligible: `{coverage['ineligible']}`")
        gap_rows = [
            row
            for row in report.get("coverage_ledger", [])
            if row.get("coverage_unknown")
        ]
        if gap_rows:
            lines.append("")
            lines.append("### Coverage gaps")
            lines.append("")
            for row in gap_rows[:100]:
                lines.append(
                    f"- `{row['item_id']}` × `{row['checker']}`: "
                    f"`{row['status']}` — {row['reason']}"
                )
            if len(gap_rows) > 100:
                lines.append(
                    f"- … {len(gap_rows) - 100} additional gap(s); see JSON ledger."
                )
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
    for (item_id, row_uid), item_violations in by_item.items():
        lines.append(
            f"### `{item_id}` (row_uid=`{row_uid}`)"
            if row_uid else f"### `{item_id}`"
        )
        lines.append("")
        for v in item_violations:
            mark = v.get("evidence_tier") or ("review" if v["review_only"] else "confirmed")
            lines.append(
                f"- `{v['defect_type']}` / `{v['artifact']}` / `{v['detection_method']}` / "
                f"`{v['severity']}` / {mark} "
                f"(confidence={v['confidence']:.2f})"
            )
            lines.append(f"  - {v['message']}")
            if v.get("promotion_reason"):
                lines.append(
                    f"  - Evidence: `{v.get('proof_kind', 'unclassified')}` — "
                    f"{v['promotion_reason']}"
                )
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
