#!/usr/bin/env python3
"""Offline title rejudging using bibliography labels from survey section 20."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Any


AUDIT_SCRIPT = Path(__file__).with_name("audit_research_citations.py")
SPEC = importlib.util.spec_from_file_location("citation_audit_frozen_matcher", AUDIT_SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import citation matcher: {AUDIT_SCRIPT}")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

SURVEY_SHA256 = "659f8bf22bf3c0d7068f476fd56c9c3c016ebaa19cc7a38bb75d5df6d195b1a7"
RECEIPT_SHA256 = "0527d9fb8827bc85623d7dc8ec17ae7cc7de39954442391f1f01c73f33ea4367"
EXPECTED_RECEIPT_ROWS = 83
EXPECTED_INDEX_ROWS = 74
SECTION_HEADING = "## 20. 扩展文献索引"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_section20_entries(markdown: str) -> list[dict[str, str]]:
    if SECTION_HEADING not in markdown:
        raise RuntimeError("section 20 heading not found")
    section = markdown.split(SECTION_HEADING, 1)[1]
    if "\n## " in section:
        section = section.split("\n## ", 1)[0]
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in AUDIT.LINK_RE.finditer(section):
        title, url = match.group(1).strip(), match.group(2).strip()
        if url in seen:
            raise RuntimeError(f"duplicate section 20 URL: {url}")
        seen.add(url)
        entries.append({"index_title": title, "url": url})
    return entries


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise RuntimeError(f"non-object JSONL row {line_number}")
        rows.append(value)
    return rows


def rejudge(receipt: dict[str, Any], *, index_title: str) -> dict[str, Any]:
    status = receipt.get("http_status")
    resolved_title = str(receipt.get("resolved_title") or "")
    title_match: bool | None = None
    reason = "no_machine_readable_title"
    if resolved_title:
        title_match = AUDIT._title_matches(index_title, resolved_title)
        reason = "frozen_containment_or_jaccard_rule_with_section20_label"

    anti_bot = status == 200 and AUDIT._normalize_title(resolved_title) in AUDIT.ANTI_BOT_NORMALIZED_TITLES
    if anti_bot:
        verdict = "blocked_by_anti_bot"
        title_match = None
        reason = "anti_bot_interstitial_not_cited_content"
    elif status in AUDIT.NOT_FOUND_STATUSES:
        verdict = "not_found"
    elif status is None or (isinstance(status, int) and status >= 500) or status in {401, 403, 408, 429}:
        verdict = "unreachable"
    elif isinstance(status, int) and 200 <= status < 400:
        verdict = "title_mismatch" if title_match is False else "resolved"
    else:
        verdict = "unreachable"

    if verdict not in AUDIT.TERMINAL_VERDICTS:
        raise RuntimeError(f"unknown terminal verdict: {verdict}")
    return {
        "cite_key": receipt["cite_key"],
        "url": receipt["url"],
        "index_title": index_title,
        "original_claimed_title": receipt.get("claimed_title"),
        "resolved_title": resolved_title,
        "http_status": status,
        "original_verdict": receipt.get("verdict"),
        "rejudged_verdict": verdict,
        "title_match": title_match,
        "title_check_reason": reason,
        "source_receipt_sha256": RECEIPT_SHA256,
        "survey_sha256": SURVEY_SHA256,
        "network_used": False,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = Counter(str(row["rejudged_verdict"]) for row in rows)
    transitions = Counter(
        f"{row['original_verdict']}->{row['rejudged_verdict']}" for row in rows
    )
    return {
        "schema_version": "citation-section20-title-rejudge-summary-v1",
        "rows": len(rows),
        "terminal_counts": {key: verdicts.get(key, 0) for key in sorted(AUDIT.TERMINAL_VERDICTS)},
        "terminal_count_sum": sum(verdicts.values()),
        "transitions": dict(sorted(transitions.items())),
        "network_used": False,
        "model_api_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("survey", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    if sha256_file(args.survey) != SURVEY_SHA256:
        raise RuntimeError("survey SHA-256 mismatch")
    if sha256_file(args.receipt) != RECEIPT_SHA256:
        raise RuntimeError("receipt SHA-256 mismatch")
    if args.out.exists() or args.summary.exists():
        raise RuntimeError("output paths must not exist")

    entries = extract_section20_entries(args.survey.read_text(encoding="utf-8"))
    receipts = load_jsonl(args.receipt)
    if len(entries) != EXPECTED_INDEX_ROWS:
        raise RuntimeError(f"section 20 row count mismatch: {len(entries)}")
    if len(receipts) != EXPECTED_RECEIPT_ROWS:
        raise RuntimeError(f"receipt row count mismatch: {len(receipts)}")
    by_url = {str(row["url"]): row for row in receipts}
    if len(by_url) != len(receipts):
        raise RuntimeError("receipt URLs are not unique")
    missing = [entry["url"] for entry in entries if entry["url"] not in by_url]
    if missing:
        raise RuntimeError(f"section 20 URLs missing from receipt: {missing}")

    rows = [rejudge(by_url[entry["url"]], index_title=entry["index_title"]) for entry in entries]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    summary = summarize(rows)
    summary["survey_sha256"] = SURVEY_SHA256
    summary["source_receipt_sha256"] = RECEIPT_SHA256
    summary["output_sha256"] = sha256_file(args.out)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
