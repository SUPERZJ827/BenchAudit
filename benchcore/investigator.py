from __future__ import annotations

import json
import re
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
- An evaluator-undercoverage finding is true when the task has a central
  answer-affecting requirement that no rubric/evaluator item checks. Do not mark
  undercoverage when rubrics collectively imply the requirement through count,
  inclusion, exclusion, or final-output checks.
- Judge coverage against the COMPLETE evaluation contract, including enforced
  output_contract fields and harness behavior, not only natural-language rubrics.
  If output_contract already declares the exact required filename or file type,
  do not call it undercoverage merely because a rubric does not repeat it.
- A save-directory-only omission is harness-dependent. Return uncertain unless
  the provided evidence establishes that the harness accepts a file from the
  wrong directory. The fact that rubrics omit a path does not establish that the
  complete evaluator omits it.
- A rubric that checks a DIFFERENT filename or directory from the task is still a
  supported mismatch; that is distinct from merely omitting a path check.
- Judge evaluator-undercoverage against the rubric set as a whole. Mark
  false_positive when a supposedly missing requirement is covered indirectly by
  exact totals, inclusion/exclusion constraints, "all/no omission" completeness
  rubrics, output-contract checks, or by enumerating all relevant input files.
- Do not mark hypothetical branches as undercoverage when the branch is not
  triggered by the provided benchmark inputs (for example unreadable-file
  behavior when all provided files are readable).

Return ONLY JSON with this schema:
{
  "verdict": "likely_true|false_positive|uncertain",
  "confidence": 0.0,
  "issue_category": "contract_mismatch|data_gap|over_strict_rubric|task_rubric_mismatch|evaluator_undercoverage|harness_dependent|other",
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


EVIDENCE_VERIFIER_SYSTEM_PROMPT = """You are an independent benchmark evidence verifier.

Treat both the candidate finding and investigator conclusions as untrusted claims.
Check whether the cited task, input, rubric, and output-contract evidence actually
supports the candidate. Do not discover unrelated issues and do not decide by
majority vote. Resolve semantic equivalents, derived values, and counter-evidence.

For evaluator-undercoverage, "rubric does not mention X" is not sufficient.
Return supported only when the evidence establishes that an output violating X
could pass the COMPLETE evaluator. Treat an exact filename/file type declared by
an enforced output_contract as covered. Treat save-directory-only claims as
insufficient when harness path enforcement is unknown. A rubric that actively
checks a conflicting filename/path remains a supported benchmark issue.

Return ONLY JSON:
{
  "evidence_verdict": "supported|refuted|insufficient",
  "confidence": 0.0,
  "verified_evidence": ["specific source-grounded fact"],
  "unsupported_claims": ["claim not established by the provided sources"],
  "contradictions": ["source fact contradicting the candidate"],
  "reasoning": "short verification rationale"
}
"""


EVIDENCE_VERIFIER_USER_PROMPT = """Verify the evidence for this candidate issue.

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

INDEPENDENT INVESTIGATOR RESULTS:
{investigator_results}
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
    pass_count: int
    verdict_votes: dict[str, int]
    agreement: float
    evidence_verdict: str
    evidence_confidence: float
    verified_evidence: list[str]
    unsupported_claims: list[str]
    evidence_contradictions: list[str]
    independent_results: list[dict[str, Any]]
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
    investigator_passes: int = 1,
    investigator_quorum: int | None = None,
    verifier_client: LLMClient | None = None,
    workers: int = 1,
    progress_every: int = 10,
    run_metadata: dict[str, Any] | None = None,
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
                    investigator_passes=investigator_passes,
                    investigator_quorum=investigator_quorum,
                    verifier_client=verifier_client,
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
                    investigator_passes=investigator_passes,
                    investigator_quorum=investigator_quorum,
                    verifier_client=verifier_client,
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
        run_metadata=run_metadata,
    )


def investigate_one_selected_violation(
    violation: dict[str, Any],
    *,
    items: dict[str, BenchmarkItem],
    client: LLMClient,
    root: Path | None,
    max_context_chars: int,
    investigator_passes: int,
    investigator_quorum: int | None,
    verifier_client: LLMClient | None,
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
            investigator_passes=investigator_passes,
            investigator_quorum=investigator_quorum,
            verifier_client=verifier_client,
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
    investigator_passes: int = 1,
    investigator_quorum: int | None = None,
    verifier_client: LLMClient | None = None,
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
    results = run_independent_passes(
        client,
        INVESTIGATOR_SYSTEM_PROMPT,
        user,
        passes=investigator_passes,
        failure_claim=str(violation.get("message", "")),
    )
    result = aggregate_investigator_results(results, quorum=investigator_quorum)
    verification: dict[str, Any] | None = None
    if verifier_client is not None:
        verification = verify_investigation_evidence(
            verifier_client,
            item,
            violation,
            context=context,
            investigator_results=results,
        )
        result = apply_evidence_verdict(result, verification)
    result = apply_harness_dependency_gate(violation, result)
    return investigation_from_result(
        violation,
        result,
        independent_results=results,
        verification=verification,
    )


def run_independent_passes(
    client: LLMClient,
    system: str,
    user: str,
    *,
    passes: int,
    failure_claim: str,
) -> list[dict[str, Any]]:
    passes = max(int(passes), 1)
    try:
        if hasattr(client, "chat_json_repeated"):
            results = client.chat_json_repeated(system, user, passes)
        else:
            results = [client.chat_json(system, user) for _ in range(passes)]
    except Exception as exc:  # noqa: BLE001 - investigation should not kill batch
        return [{
            "verdict": "uncertain",
            "confidence": 0.0,
            "issue_category": "other",
            "claim": failure_claim,
            "reasoning": f"investigator_call_failed: {type(exc).__name__}: {exc}",
            "recommended_action": "keep_for_review",
        }]
    return [result for result in results if isinstance(result, dict)] or [{
        "verdict": "uncertain",
        "confidence": 0.0,
        "issue_category": "other",
        "claim": failure_claim,
        "reasoning": "investigator_returned_no_valid_results",
        "recommended_action": "keep_for_review",
    }]


def aggregate_investigator_results(
    results: list[dict[str, Any]],
    *,
    quorum: int | None = None,
) -> dict[str, Any]:
    """Conservatively aggregate independent adjudications.

    A verdict needs an absolute quorum. Ties or fragmented votes become
    ``uncertain`` instead of being resolved by label ordering.
    """
    normalized = [normalize_verdict(result.get("verdict")) for result in results]
    votes = Counter(normalized)
    required = quorum if quorum is not None and quorum > 0 else len(results) // 2 + 1
    winner, winner_count = votes.most_common(1)[0]
    tied = sum(1 for count in votes.values() if count == winner_count) > 1
    verdict = winner if winner_count >= required and not tied else "uncertain"
    matching = [
        result for result, value in zip(results, normalized)
        if value == verdict
    ] if verdict != "uncertain" else [
        result for result, value in zip(results, normalized)
        if value == winner
    ]
    exemplar = max(matching or results, key=lambda row: bounded_float(row.get("confidence"), 0.0))
    agreement = winner_count / len(results)
    confidence_values = [bounded_float(row.get("confidence"), 0.0) for row in matching]
    base_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    merged = dict(exemplar)
    merged["verdict"] = verdict
    merged["confidence"] = base_confidence * agreement
    merged["pass_count"] = len(results)
    merged["verdict_votes"] = dict(votes)
    merged["agreement"] = agreement
    if verdict == "uncertain" and not str(merged.get("reasoning", "")).startswith("investigator_call_failed"):
        merged["reasoning"] = (
            f"Independent investigator passes did not reach quorum: {dict(votes)}. "
            + str(merged.get("reasoning", ""))
        ).strip()
        merged["recommended_action"] = "keep_for_review"
    return merged


def verify_investigation_evidence(
    client: LLMClient,
    item: BenchmarkItem,
    violation: dict[str, Any],
    *,
    context: str,
    investigator_results: list[dict[str, Any]],
) -> dict[str, Any]:
    user = EVIDENCE_VERIFIER_USER_PROMPT.format(
        task=preview(item.task, 3000) or "(no task text)",
        output_contract=preview(item.output_contract, 2200) or "(no output contract)",
        rubrics=preview(format_item_rubrics(item), 6000) or "(no rubric/evaluator)",
        finding=preview(violation, 5000),
        context=context,
        investigator_results=preview(investigator_results, 9000),
    )
    try:
        result = client.chat_json(EVIDENCE_VERIFIER_SYSTEM_PROMPT, user)
    except Exception as exc:  # noqa: BLE001 - verifier failure becomes insufficient evidence
        return {
            "evidence_verdict": "insufficient",
            "confidence": 0.0,
            "verified_evidence": [],
            "unsupported_claims": [f"verifier_call_failed: {type(exc).__name__}: {exc}"],
            "contradictions": [],
            "reasoning": "Evidence verifier failed; preserve candidate for review.",
        }
    verdict = str(result.get("evidence_verdict", "insufficient")).strip().lower()
    if verdict not in {"supported", "refuted", "insufficient"}:
        verdict = "insufficient"
    result["evidence_verdict"] = verdict
    return result


def apply_evidence_verdict(
    aggregate: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(aggregate)
    candidate_verdict = normalize_verdict(aggregate.get("verdict"))
    evidence_verdict = str(verification.get("evidence_verdict", "insufficient"))
    evidence_confidence = bounded_float(verification.get("confidence"), 0.0)
    aligned = (
        (candidate_verdict == "likely_true" and evidence_verdict == "supported")
        or (candidate_verdict == "false_positive" and evidence_verdict == "refuted")
    )
    if not aligned:
        merged["verdict"] = "uncertain"
        merged["recommended_action"] = "keep_for_review"
        merged["reasoning"] = (
            f"Evidence verifier did not confirm the aggregate verdict "
            f"({candidate_verdict} vs {evidence_verdict}). "
            + str(verification.get("reasoning", ""))
        ).strip()
    merged["confidence"] = min(
        bounded_float(aggregate.get("confidence"), 0.0),
        evidence_confidence,
    ) if aligned else 0.0
    return merged


SAVE_LOCATION_PATTERN = re.compile(
    r"\b(save|saved|saving|place|placed|placing|location|directory|folder|path|desktop|downloads?)\b|"
    r"保存|存放|放置|位置|目录|文件夹|路径|桌面|下载",
    re.I,
)

EXPLICIT_PATH_CONFLICT_PATTERN = re.compile(
    r"\b(different|conflict|contradict|mismatch|wrong|rather than|instead of|"
    r"checks? (?:a )?(?:different|wrong)|requires? (?:a )?(?:different|wrong))\b|"
    r"不一致|冲突|矛盾|不同路径|错误路径|而不是",
    re.I,
)

NON_LOCATION_OBLIGATION_PATTERN = re.compile(
    r"\b(analysis|data|value|accuracy|chart|figure|content|integrat|top\s*\d|"
    r"timeline|citation|hyperlink|field|column|milestone|permission|copy|move|"
    r"format|title|calculation|relationship|journey|recommendation|source)\b|"
    r"分析|数据|数值|准确|图表|图片|内容|整合|时间线|引用|链接|字段|列|里程碑|"
    r"权限|复制|移动|格式|标题|计算|关系|流程|建议|来源",
    re.I,
)


def apply_harness_dependency_gate(
    violation: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Prevent save-location omissions from becoming unsupported true issues.

    Whether a file in the wrong directory can pass depends on the benchmark
    harness. A language model may acknowledge that uncertainty in its evidence
    and still emit ``likely_true``. This final policy gate makes the conservative
    rule deterministic. Explicit task/rubric path conflicts and findings with a
    separate substantive obligation remain eligible for ``likely_true``.
    """
    if str(violation.get("defect_type", "")) != "underconstrained_evaluator_risk":
        return result
    current_verdict = normalize_verdict(result.get("verdict"))
    if current_verdict == "false_positive":
        return result
    text = str(result.get("claim", "")).strip() or str(violation.get("message", ""))
    if not SAVE_LOCATION_PATTERN.search(text):
        return result
    if EXPLICIT_PATH_CONFLICT_PATTERN.search(text):
        return result
    if NON_LOCATION_OBLIGATION_PATTERN.search(text):
        return result
    merged = dict(result)
    if current_verdict == "likely_true":
        merged["verdict"] = "uncertain"
        merged["confidence"] = 0.0
    merged["issue_category"] = "harness_dependent"
    merged["recommended_action"] = "keep_for_review"
    merged["reasoning"] = (
        "Programmatic harness-dependency gate: the candidate only establishes "
        "that a save location is not repeated in the visible rubrics; it does not "
        "establish that the complete harness accepts an output from the wrong location. "
        + str(merged.get("reasoning", ""))
    ).strip()
    return merged


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
    *,
    independent_results: list[dict[str, Any]] | None = None,
    verification: dict[str, Any] | None = None,
) -> Investigation:
    verdict = normalize_verdict(result.get("verdict"))
    verification = verification or {}
    independent_results = independent_results or [result]
    raw_votes = result.get("verdict_votes")
    if isinstance(raw_votes, dict):
        verdict_votes = {str(key): int(value) for key, value in raw_votes.items()}
    else:
        verdict_votes = dict(Counter(normalize_verdict(row.get("verdict")) for row in independent_results))
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
        pass_count=len(independent_results),
        verdict_votes=verdict_votes,
        agreement=bounded_float(result.get("agreement"), 1.0),
        evidence_verdict=str(verification.get("evidence_verdict", "not_run") or "not_run"),
        evidence_confidence=bounded_float(verification.get("confidence"), 0.0),
        verified_evidence=normalized_string_list(verification.get("verified_evidence")),
        unsupported_claims=normalized_string_list(verification.get("unsupported_claims")),
        evidence_contradictions=normalized_string_list(verification.get("contradictions")),
        independent_results=independent_results,
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


def normalized_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]


def build_investigation_report(
    *,
    input_path: Path,
    report_path: Path,
    investigations: list[Investigation],
    total_candidates: int,
    run_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = [asdict(inv) for inv in investigations]
    summary = summarize_investigation_rows(
        rows,
        input_path=str(input_path),
        report_path=str(report_path),
        total_candidates=total_candidates,
    )
    report = {"summary": summary, "investigations": rows}
    if run_metadata:
        report["run_metadata"] = run_metadata
    return report


def summarize_investigation_rows(
    rows: list[dict[str, Any]],
    *,
    input_path: str,
    report_path: str,
    total_candidates: int,
) -> dict[str, Any]:
    return {
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
        "mean_agreement": (
            sum(float(row.get("agreement", 0.0)) for row in rows) / len(rows)
            if rows else 0.0
        ),
        "evidence_verdict_distribution": dict(Counter(row["evidence_verdict"] for row in rows)),
    }


def refine_investigation_report(report: dict[str, Any]) -> dict[str, Any]:
    """Reapply deterministic policy gates without rereading artifacts or calling LLMs."""
    old_summary = report.get("summary") or {}
    rows: list[dict[str, Any]] = []
    changed = 0
    for source in report.get("investigations", []):
        row = dict(source)
        result = {
            "verdict": row.get("verdict"),
            "confidence": row.get("confidence"),
            "issue_category": row.get("issue_category"),
            "claim": row.get("claim"),
            "reasoning": row.get("reasoning"),
            "recommended_action": row.get("recommended_action"),
        }
        refined = apply_harness_dependency_gate(row.get("source_violation") or {}, result)
        for key in (
            "verdict",
            "confidence",
            "issue_category",
            "reasoning",
            "recommended_action",
        ):
            row[key] = refined.get(key, row.get(key))
        if row.get("verdict") != source.get("verdict"):
            changed += 1
        rows.append(row)
    summary = summarize_investigation_rows(
        rows,
        input_path=str(old_summary.get("input_path", "")),
        report_path=str(old_summary.get("source_report", "")),
        total_candidates=int(old_summary.get("candidates_investigated", len(rows))),
    )
    refined_report = dict(report)
    refined_report["summary"] = summary
    refined_report["investigations"] = rows
    refined_report["refinement"] = {
        "policy": "harness_dependency_gate_v1",
        "changed_verdicts": changed,
        "llm_calls": 0,
    }
    return refined_report


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
    if "mean_agreement" in summary:
        lines.append(f"- Mean investigator agreement: `{summary['mean_agreement']:.3f}`")
    if summary.get("evidence_verdict_distribution"):
        lines.append(
            "- Evidence verification: `"
            + json.dumps(summary["evidence_verdict_distribution"], ensure_ascii=False)
            + "`"
        )
    metadata = report.get("run_metadata") or {}
    if metadata:
        lines.append(f"- Elapsed seconds: `{metadata.get('elapsed_seconds', 'unknown')}`")
        git = metadata.get("git") or {}
        if git.get("commit"):
            dirty = " dirty" if git.get("dirty") else ""
            lines.append(f"- Git commit: `{git['commit']}{dirty}`")
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
            if row.get("pass_count"):
                lines.append(
                    f"  - Independent passes: `{row['pass_count']}`; "
                    f"votes=`{json.dumps(row.get('verdict_votes', {}), ensure_ascii=False)}`; "
                    f"agreement=`{row.get('agreement', 0.0):.3f}`"
                )
            if row.get("evidence_verdict") not in (None, "", "not_run"):
                lines.append(
                    f"  - Evidence verifier: `{row['evidence_verdict']}` "
                    f"(confidence={row.get('evidence_confidence', 0.0):.2f})"
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
            if row.get("unsupported_claims"):
                lines.append(f"  - Unsupported claims: {'; '.join(row['unsupported_claims'])}")
            if row.get("evidence_contradictions"):
                lines.append(f"  - Evidence contradictions: {'; '.join(row['evidence_contradictions'])}")
            if row.get("reasoning"):
                lines.append(f"  - Reasoning: {row['reasoning']}")
            lines.append(f"  - Action: `{row['recommended_action']}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
