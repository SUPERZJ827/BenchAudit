from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .artifact_consistency import (
    append_targeted_search_context,
    extract_rubrics,
    full_context_text,
    preview,
    strictness_grounding_terms,
)
from .loader import build_items, load_rows
from .llm_client import LLMClient
from .schema import BenchmarkItem, FieldMapping


INVESTIGATOR_SYSTEM_PROMPT = """You are a benchmark issue investigator.

Your job is NOT to discover new issues. Your job is to adjudicate one candidate
finding using the task, output contract, rubric/evaluator, and provided input
artifacts.

Use a strict evidence standard:
- Return likely_true only when the candidate is supported by concrete evidence.
- Return false_positive when the input/context semantically supports the rubric,
  even if wording differs (aid vs assistance, dissolved vs dismissed, aliases,
  abbreviations, paraphrases, derived counts, or values spread across files).
- Return uncertain when the provided evidence is incomplete or you cannot inspect
  enough of the relevant artifact.

Workspace/rubric-specific rules:
- A rubric is NOT over-strict merely because it specifies an expected answer,
  count, file content, category, or computed value. Rubrics are allowed to define
  objective oracle values when those values are present in or derivable from the
  inputs.
- A rubric IS over-strict when it forces one arbitrary valid format/structure/
  wording/chart/page/slide/sheet/title/number of recommendations while the task
  allows multiple correct outputs and the exact detail is not grounded in inputs.
- A data-gap finding is true only if required data is absent and not derivable
  from the provided inputs. If targeted snippets show the value or equivalent
  wording, mark false_positive.
- A contract mismatch is true when output_contract requires a different
  deliverable than the task/rubrics. Do not treat a save-location directory as an
  extra required output if the named output file itself is consistent.

Return ONLY JSON with this schema:
{
  "verdict": "likely_true|false_positive|uncertain",
  "confidence": 0.0,
  "issue_category": "contract_mismatch|data_gap|over_strict_rubric|task_rubric_mismatch|other",
  "claim": "one-sentence restatement of the candidate",
  "evidence_from_task": "task evidence or empty",
  "evidence_from_input": "input/context evidence or empty",
  "evidence_from_rubric": "rubric/evaluator evidence or empty",
  "evidence_from_contract": "contract evidence or empty",
  "counter_evidence": "evidence against the candidate or empty",
  "reasoning": "short evidence-grounded rationale",
  "recommended_action": "repair/remove/keep_for_review/no_action"
}
"""


INVESTIGATOR_USER_PROMPT = """Investigate this candidate benchmark issue.

ITEM_ID:
{item_id}

TASK:
{task}

OUTPUT_CONTRACT:
{output_contract}

RUBRICS / EVALUATOR:
{rubrics}

CANDIDATE_FINDING:
{finding}

INPUT / CONTEXT EVIDENCE:
{context}
"""


@dataclass
class Investigation:
    item_id: str
    artifact: str
    defect_type: str
    detection_method: str
    original_confidence: float
    original_message: str
    verdict: str
    confidence: float
    issue_category: str
    claim: str
    evidence_from_task: str
    evidence_from_input: str
    evidence_from_rubric: str
    evidence_from_contract: str
    counter_evidence: str
    reasoning: str
    recommended_action: str
    source_violation: dict[str, Any]


def investigate_audit_report(
    *,
    input_path: Path,
    report_path: Path,
    client: LLMClient,
    root: Path | None = None,
    include_defects: set[str] | None = None,
    include_methods: set[str] | None = None,
    min_confidence: float = 0.0,
    offset: int = 0,
    limit: int | None = None,
    max_context_chars: int = 18000,
    workers: int = 1,
    progress_every: int = 10,
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    items = load_report_items(input_path, report)
    root = root or input_path.parent
    violations = select_violations(
        report.get("violations", []),
        include_defects=include_defects,
        include_methods=include_methods,
        min_confidence=min_confidence,
        offset=offset,
        limit=limit,
    )
    if workers <= 1:
        investigations = []
        started = time.monotonic()
        for index, violation in enumerate(violations, start=1):
            investigations.append(
                investigate_one_selected_violation(
                    violation,
                    items=items,
                    client=client,
                    root=root,
                    max_context_chars=max_context_chars,
                )
            )
            maybe_print_progress(index, len(violations), started, progress_every)
    else:
        investigations = [None] * len(violations)
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    investigate_one_selected_violation,
                    violation,
                    items=items,
                    client=client,
                    root=root,
                    max_context_chars=max_context_chars,
                ): index
                for index, violation in enumerate(violations)
            }
            completed = 0
            for future in as_completed(futures):
                investigations[futures[future]] = future.result()
                completed += 1
                maybe_print_progress(completed, len(violations), started, progress_every)
    return build_investigation_report(
        input_path=input_path,
        report_path=report_path,
        investigations=[inv for inv in investigations if inv is not None],
        total_candidates=len(violations),
    )


def investigate_one_selected_violation(
    violation: dict[str, Any],
    *,
    items: dict[str, BenchmarkItem],
    client: LLMClient,
    root: Path | None,
    max_context_chars: int,
) -> Investigation:
        item = items.get(str(violation.get("item_id")))
        if item is None:
            return missing_item_investigation(violation)
        return investigate_violation(
            item,
            violation,
            client,
            root=root,
            max_context_chars=max_context_chars,
        )


def maybe_print_progress(completed: int, total: int, started: float, every: int) -> None:
    if every <= 0:
        return
    if completed != total and completed % every != 0:
        return
    elapsed = time.monotonic() - started
    rate = completed / elapsed if elapsed > 0 else 0.0
    eta = (total - completed) / rate if rate > 0 else 0.0
    print(
        f"[investigate {completed}/{total}] elapsed={format_duration(elapsed)} "
        f"eta={format_duration(eta)}",
        file=sys.stderr,
        flush=True,
    )


def format_duration(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def load_report_items(input_path: Path, report: dict[str, Any]) -> dict[str, BenchmarkItem]:
    rows = load_rows(input_path)
    mapping_data = report.get("field_mapping") or {}
    mapping = FieldMapping(
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
    return {str(item.item_id): item for item in build_items(rows, mapping)}


def select_violations(
    violations: list[dict[str, Any]],
    *,
    include_defects: set[str] | None,
    include_methods: set[str] | None,
    min_confidence: float,
    offset: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    selected = []
    for violation in violations:
        if include_defects and violation.get("defect_type") not in include_defects:
            continue
        if include_methods and violation.get("detection_method") not in include_methods:
            continue
        try:
            confidence = float(violation.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < min_confidence:
            continue
        selected.append(violation)
    start = max(offset, 0)
    if limit is None:
        return selected[start:]
    return selected[start : start + max(limit, 0)]


def investigate_violation(
    item: BenchmarkItem,
    violation: dict[str, Any],
    client: LLMClient,
    *,
    root: Path | None,
    max_context_chars: int,
) -> Investigation:
    context = investigation_context(item, violation, root=root, max_chars=max_context_chars)
    user = INVESTIGATOR_USER_PROMPT.format(
        item_id=item.item_id,
        task=preview(item.task, 3000) or "(no task text)",
        output_contract=preview(item.output_contract, 2200) or "(no output contract)",
        rubrics=preview(format_item_rubrics(item), 6000) or "(no rubric/evaluator)",
        finding=preview(violation, 5000),
        context=context,
    )
    try:
        result = client.chat_json(INVESTIGATOR_SYSTEM_PROMPT, user)
    except Exception as exc:  # noqa: BLE001 - investigation should not kill batch
        result = {
            "verdict": "uncertain",
            "confidence": 0.0,
            "issue_category": "other",
            "claim": str(violation.get("message", "")),
            "reasoning": f"investigator_call_failed: {type(exc).__name__}: {exc}",
            "recommended_action": "keep_for_review",
        }
    return investigation_from_result(violation, result)


def investigation_context(
    item: BenchmarkItem,
    violation: dict[str, Any],
    *,
    root: Path | None,
    max_chars: int,
) -> str:
    base = full_context_text(item, root, max_chars)
    terms = investigation_terms(violation)
    return append_targeted_search_context(
        item,
        root,
        base,
        terms,
        rubric=str((violation.get("evidence") or {}).get("rubric", "")),
        max_chars=max(3000, max_chars // 3),
    )


def investigation_terms(violation: dict[str, Any]) -> list[str]:
    evidence = violation.get("evidence") if isinstance(violation.get("evidence"), dict) else {}
    chunks = [
        str(violation.get("message", "")),
        str(evidence.get("rubric", "")),
        str(evidence.get("required", "")),
        str(evidence.get("missing", "")),
        str(evidence.get("contract_issue", "")),
    ]
    terms: list[str] = []
    for chunk in chunks:
        terms.extend(strictness_grounding_terms(chunk))
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
        if len(out) >= 64:
            break
    return out


def format_item_rubrics(item: BenchmarkItem) -> str:
    rubrics = extract_rubrics(item)
    parts: list[str] = []
    if rubrics:
        parts.append("\n".join(f"{idx}. {rubric}" for idx, rubric in enumerate(rubrics)))
    if item.evaluator not in (None, "", [], {}):
        parts.append("EVALUATOR:\n" + preview(item.evaluator, 3000))
    return "\n\n".join(parts)


def investigation_from_result(
    violation: dict[str, Any],
    result: dict[str, Any],
) -> Investigation:
    verdict = normalize_verdict(result.get("verdict"))
    return Investigation(
        item_id=str(violation.get("item_id", "")),
        artifact=str(violation.get("artifact", "")),
        defect_type=str(violation.get("defect_type", "")),
        detection_method=str(violation.get("detection_method", "")),
        original_confidence=to_float(violation.get("confidence"), 0.0),
        original_message=str(violation.get("message", "")),
        verdict=verdict,
        confidence=bounded_float(result.get("confidence"), 0.0),
        issue_category=str(result.get("issue_category", "other") or "other"),
        claim=str(result.get("claim", "") or violation.get("message", "")),
        evidence_from_task=str(result.get("evidence_from_task", "") or ""),
        evidence_from_input=str(result.get("evidence_from_input", "") or ""),
        evidence_from_rubric=str(result.get("evidence_from_rubric", "") or ""),
        evidence_from_contract=str(result.get("evidence_from_contract", "") or ""),
        counter_evidence=str(result.get("counter_evidence", "") or ""),
        reasoning=str(result.get("reasoning", "") or ""),
        recommended_action=str(result.get("recommended_action", "keep_for_review") or "keep_for_review"),
        source_violation=violation,
    )


def missing_item_investigation(violation: dict[str, Any]) -> Investigation:
    return investigation_from_result(
        violation,
        {
            "verdict": "uncertain",
            "confidence": 0.0,
            "issue_category": "other",
            "claim": violation.get("message", ""),
            "reasoning": "Original benchmark item was not found for this violation.",
            "recommended_action": "keep_for_review",
        },
    )


def normalize_verdict(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"likely_true", "true", "supported", "confirmed"}:
        return "likely_true"
    if text in {"false_positive", "false", "not_true", "unsupported"}:
        return "false_positive"
    return "uncertain"


def bounded_float(value: Any, default: float) -> float:
    return min(max(to_float(value, default), 0.0), 1.0)


def to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_investigation_report(
    *,
    input_path: Path,
    report_path: Path,
    investigations: list[Investigation],
    total_candidates: int,
) -> dict[str, Any]:
    rows = [asdict(inv) for inv in investigations]
    summary = {
        "input_path": str(input_path),
        "source_report": str(report_path),
        "candidates_investigated": total_candidates,
        "investigation_count": len(rows),
        "verdict_distribution": dict(Counter(row["verdict"] for row in rows)),
        "issue_category_distribution": dict(Counter(row["issue_category"] for row in rows)),
        "defect_distribution": dict(Counter(row["defect_type"] for row in rows)),
        "likely_true_items": len({row["item_id"] for row in rows if row["verdict"] == "likely_true"}),
        "false_positive_items": len({row["item_id"] for row in rows if row["verdict"] == "false_positive"}),
        "uncertain_items": len({row["item_id"] for row in rows if row["verdict"] == "uncertain"}),
    }
    return {"summary": summary, "investigations": rows}


def write_investigation_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def write_investigation_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    investigations = report["investigations"]
    by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in investigations:
        by_item[row["item_id"]].append(row)

    lines: list[str] = []
    lines.append("# Benchmark Issue Investigation Report")
    lines.append("")
    lines.append(f"- Input: `{summary['input_path']}`")
    lines.append(f"- Source report: `{summary['source_report']}`")
    lines.append(f"- Investigated candidates: `{summary['investigation_count']}`")
    lines.append(f"- Verdicts: `{json.dumps(summary['verdict_distribution'], ensure_ascii=False)}`")
    lines.append(f"- Issue categories: `{json.dumps(summary['issue_category_distribution'], ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Cases")
    lines.append("")
    for item_id, rows in by_item.items():
        lines.append(f"### `{item_id}`")
        lines.append("")
        for row in rows:
            lines.append(
                f"- `{row['verdict']}` / `{row['issue_category']}` / "
                f"`{row['defect_type']}` / `{row['detection_method']}` "
                f"(confidence={row['confidence']:.2f}, original={row['original_confidence']:.2f})"
            )
            lines.append(f"  - Claim: {row['claim'] or row['original_message']}")
            if row.get("evidence_from_task"):
                lines.append(f"  - Task evidence: {row['evidence_from_task']}")
            if row.get("evidence_from_input"):
                lines.append(f"  - Input evidence: {row['evidence_from_input']}")
            if row.get("evidence_from_rubric"):
                lines.append(f"  - Rubric evidence: {row['evidence_from_rubric']}")
            if row.get("evidence_from_contract"):
                lines.append(f"  - Contract evidence: {row['evidence_from_contract']}")
            if row.get("counter_evidence"):
                lines.append(f"  - Counter-evidence: {row['counter_evidence']}")
            if row.get("reasoning"):
                lines.append(f"  - Reasoning: {row['reasoning']}")
            lines.append(f"  - Action: `{row['recommended_action']}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
