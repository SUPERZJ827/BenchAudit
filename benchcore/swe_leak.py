from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .checkers import Checker, _violation
from .llm_client import LLMClient
from .schema import BenchmarkItem, Violation


GENERIC_CODE_LINES = {
    "pass",
    "continue",
    "break",
    "return",
    "return none",
    "return true",
    "return false",
    "return 0",
    "return 1",
    "none",
    "true",
    "false",
    "else:",
    "try:",
    "finally:",
}

SYSTEM_PROMPT = (
    "你是 benchmark 数据质量审计员。只判断 gold patch 新增代码行是否在 issue "
    "problem_statement 中作为修复方案或正确改法被直接给出。返回严格 JSON。"
)

USER_PROMPT_TEMPLATE = """判断:下面这些「gold 修复补丁的新增代码行」是否已在 ISSUE 描述里作为"修复方案/正确改法"
被直接给出——即 agent 照抄 issue 即可解决,构成答案泄漏?还是这些行只是 bug 复现代码、报错回溯、
API 用法示例、或与修复无关的巧合字面匹配(不构成泄漏)?
命中的行(已确认逐字出现在 issue 里):
{lines}
ISSUE(problem_statement excerpts around matched lines):
{issue}
GOLD PATCH:
{patch}
返回 ONLY JSON {{"verdict":"solution_leaked|reproduction_or_incidental","evidence":"一句话理由"}}
"""


class SolutionLeakChecker(Checker):
    """Detect gold-patch code leaking through the visible task statement."""

    name = "solution_leak"

    def __init__(
        self,
        client: LLMClient | None = None,
        *,
        issue_chars: int = 3500,
        patch_chars: int = 1500,
        report_hints_only: bool = True,
    ) -> None:
        self.client = client
        self.issue_chars = issue_chars
        self.patch_chars = patch_chars
        self.report_hints_only = report_hints_only

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        scan = scan_item(item)
        if not scan:
            return

        problem_hits = scan["problem_statement_hits"]
        if problem_hits:
            if self.client is None:
                yield self._literal_candidate(item, scan)
            else:
                result = confirm_solution_leak(
                    self.client,
                    scan,
                    issue_chars=self.issue_chars,
                    patch_chars=self.patch_chars,
                )
                if result.get("verdict") == "solution_leaked":
                    yield self._confirmed_leak(item, scan, result)
                elif result.get("verdict") == "llm_error":
                    yield _violation(
                        item,
                        "llm_audit_failure",
                        0.3,
                        "LLM semantic confirmation failed for solution leak candidate.",
                        {
                            "source_field": "problem_statement",
                            "matched_lines": problem_hits,
                            "llm_result": result,
                        },
                        severity="review",
                        review_only=True,
                        method="solution_leak_llm_confirm",
                        scope="operational",
                    )

        if self.report_hints_only and not problem_hits and scan["hints_only_hits"]:
            yield _violation(
                item,
                "hints_only_solution_leak",
                0.65,
                (
                    "Gold patch added lines appear in hints_text rather than the visible "
                    "problem_statement; this is tracked separately from task-visible leakage."
                ),
                {
                    "source_field": "hints_text",
                    "matched_lines": scan["hints_only_hits"],
                    "n_added_substantive_lines": scan["n_added_substantive_lines"],
                    "hit_count": len(scan["hints_only_hits"]),
                    "hit_frac": scan["hints_only_hit_frac"],
                },
                severity="review",
                review_only=True,
                method="solution_leak_literal",
            )

    def _literal_candidate(self, item: BenchmarkItem, scan: dict[str, Any]) -> Violation:
        return _violation(
            item,
            "solution_leak",
            literal_confidence(scan),
            "Gold patch added lines appear verbatim in the visible problem_statement.",
            {
                "source_field": "problem_statement",
                "matched_lines": scan["problem_statement_hits"],
                "n_added_substantive_lines": scan["n_added_substantive_lines"],
                "hit_count": len(scan["problem_statement_hits"]),
                "hit_frac": scan["problem_statement_hit_frac"],
                "semantic_confirmation": "not_run",
            },
            severity="review",
            review_only=True,
            method="solution_leak_literal",
        )

    def _confirmed_leak(
        self,
        item: BenchmarkItem,
        scan: dict[str, Any],
        result: dict[str, Any],
    ) -> Violation:
        return _violation(
            item,
            "solution_leak",
            max(0.8, literal_confidence(scan)),
            "The visible problem_statement directly provides gold patch repair code.",
            {
                "source_field": "problem_statement",
                "matched_lines": scan["problem_statement_hits"],
                "n_added_substantive_lines": scan["n_added_substantive_lines"],
                "hit_count": len(scan["problem_statement_hits"]),
                "hit_frac": scan["problem_statement_hit_frac"],
                "llm_result": result,
            },
            severity="major",
            review_only=False,
            method="solution_leak_literal+llm_confirm",
        )


def scan_item(item: BenchmarkItem) -> dict[str, Any] | None:
    raw = item.raw or {}
    patch = raw.get("patch") or item.metadata.get("patch") or ""
    problem_statement = raw.get("problem_statement") or item.task or ""
    hints_text = raw.get("hints_text") or item.metadata.get("hints_text") or ""
    return scan_fields(
        patch=patch,
        problem_statement=problem_statement,
        hints_text=hints_text,
        instance_id=item.item_id,
        repo=raw.get("repo") or item.metadata.get("repo") or "",
        base_commit=raw.get("base_commit") or item.metadata.get("base_commit") or "",
    )


def scan_fields(
    *,
    patch: str | None,
    problem_statement: str | None,
    hints_text: str | None,
    instance_id: str = "",
    repo: str = "",
    base_commit: str = "",
) -> dict[str, Any] | None:
    patch_text = patch or ""
    problem_text = problem_statement or ""
    hints = hints_text or ""
    adds = added_lines(patch_text)
    if not adds:
        return None

    in_problem = [line for line in adds if line in problem_text]
    in_hints_only = [line for line in adds if line in hints and line not in problem_text]
    if not in_problem and not in_hints_only:
        return None

    return {
        "instance_id": instance_id,
        "repo": repo,
        "base_commit": base_commit,
        "n_added_substantive_lines": len(adds),
        "problem_statement_hits": in_problem,
        "hints_only_hits": in_hints_only,
        "problem_statement_hit_count": len(in_problem),
        "hints_only_hit_count": len(in_hints_only),
        "problem_statement_hit_frac": round(len(in_problem) / len(adds), 4),
        "hints_only_hit_frac": round(len(in_hints_only) / len(adds), 4),
        "patch": patch_text,
        "problem_statement": problem_text,
    }


def added_lines(patch: str | None) -> list[str]:
    """Return substantive added lines from a unified diff gold patch."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in (patch or "").splitlines():
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        line = raw[1:].strip()
        if not is_substantive_added_line(line):
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def is_substantive_added_line(line: str) -> bool:
    """Keep concrete repair code while filtering generic one-line noise."""
    if not line:
        return False
    lowered = re.sub(r"\s+", " ", line.lower()).strip()
    if lowered in GENERIC_CODE_LINES:
        return False
    if len(line) < 8:
        return False
    if line.startswith(("#", "//", "*")):
        return False
    if re.fullmatch(r"[rubfRUBF]*['\"]{3}.*", line):
        return False
    if re.fullmatch(r"[rubfRUBF]*['\"][^'\"]{0,40}['\"]", line):
        return False
    if re.fullmatch(r"(return\s+)?(none|true|false|\d+(\.\d+)?)", lowered):
        return False
    if re.fullmatch(r"(raise|except|elif|if|for|while|with|class|def)\b[:\s]*", lowered):
        return False

    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", line)
    has_code_punctuation = bool(re.search(r"[=().:\[\]{},]", line))
    has_identifier_phrase = len(tokens) >= 2 and any("_" in token for token in tokens)
    has_keyword_phrase = len(tokens) >= 3 and tokens[0].lower() in {
        "and",
        "or",
        "not",
        "is",
        "in",
    }
    return has_code_punctuation or has_identifier_phrase or has_keyword_phrase


def confirm_solution_leak(
    client: LLMClient,
    scan: dict[str, Any],
    *,
    issue_chars: int = 3500,
    patch_chars: int = 1500,
) -> dict[str, Any]:
    lines = "\n".join(f"- {line}" for line in scan["problem_statement_hits"])
    user_prompt = USER_PROMPT_TEMPLATE.format(
        lines=lines,
        issue=issue_hit_context(
            scan["problem_statement"],
            scan["problem_statement_hits"],
            issue_chars,
        ),
        patch=truncate(scan["patch"], patch_chars),
    )
    try:
        result = client.chat_json(SYSTEM_PROMPT, user_prompt)
    except Exception as exc:  # noqa: BLE001 - record row-level operational failure
        return {
            "verdict": "llm_error",
            "evidence": f"{type(exc).__name__}: {exc}",
        }
    verdict = str(result.get("verdict", "")).strip()
    if verdict not in {"solution_leaked", "reproduction_or_incidental"}:
        result = dict(result)
        result["verdict"] = "llm_error"
        result.setdefault("evidence", f"Unexpected verdict: {verdict!r}")
    return result


def literal_confidence(scan: dict[str, Any]) -> float:
    frac = float(scan.get("problem_statement_hit_frac", 0.0))
    count = int(scan.get("problem_statement_hit_count", 0))
    return round(min(0.9, 0.55 + 0.25 * frac + 0.03 * min(count, 3)), 3)


def truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"


def issue_hit_context(issue: str, hits: list[str], max_chars: int) -> str:
    """Return problem_statement excerpts centered on matched patch lines."""
    if max_chars <= 0 or len(issue) <= max_chars:
        return issue
    spans: list[tuple[int, int]] = []
    radius = max(450, min(1200, max_chars // max(1, len(hits) * 2)))
    for hit in hits:
        pos = issue.find(hit)
        if pos < 0:
            continue
        spans.append((max(0, pos - radius), min(len(issue), pos + len(hit) + radius)))
    if not spans:
        return truncate(issue, max_chars)

    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if not merged or start > merged[-1][1] + 80:
            merged.append((start, end))
        else:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end))

    parts: list[str] = []
    for index, (start, end) in enumerate(merged, start=1):
        prefix = "...[preceding issue text omitted]\n" if start > 0 else ""
        suffix = "\n...[following issue text omitted]" if end < len(issue) else ""
        parts.append(f"[match context {index}]\n{prefix}{issue[start:end]}{suffix}")
    context = "\n\n---\n\n".join(parts)
    if len(context) <= max_chars:
        return context

    trim_each = max(250, max_chars // max(1, len(parts)) - 80)
    trimmed_parts: list[str] = []
    for index, (start, end) in enumerate(merged, start=1):
        center = (start + end) // 2
        half = trim_each // 2
        s = max(0, center - half)
        e = min(len(issue), center + half)
        prefix = "...[preceding issue text omitted]\n" if s > 0 else ""
        suffix = "\n...[following issue text omitted]" if e < len(issue) else ""
        trimmed_parts.append(f"[match context {index}]\n{prefix}{issue[s:e]}{suffix}")
    return truncate("\n\n---\n\n".join(trimmed_parts), max_chars)
