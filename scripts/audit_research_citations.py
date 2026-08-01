#!/usr/bin/env python3
"""Resolve Markdown citations without validating their numerical claims.

The extraction, title-matching, and verdict rules in this file are intentionally
frozen before any cited URL is fetched.  The script uses direct HTTP(S) only,
does not call a model API, and does not consult search engines or substitute
sources.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Any


LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
TITLE_PATTERNS = (
    re.compile(
        r"<meta\s+[^>]*(?:name|property)=[\"']citation_title[\"'][^>]*content=[\"']([^\"']+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"<meta\s+[^>]*content=[\"']([^\"']+)[\"'][^>]*(?:name|property)=[\"']citation_title[\"']",
        re.IGNORECASE,
    ),
    re.compile(
        r"<meta\s+[^>]*(?:name|property)=[\"'](?:og:title|dc.title)[\"'][^>]*content=[\"']([^\"']+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"<meta\s+[^>]*content=[\"']([^\"']+)[\"'][^>]*(?:name|property)=[\"'](?:og:title|dc.title)[\"']",
        re.IGNORECASE,
    ),
    re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL),
)
NUMBER_RE = re.compile(
    r"(?<![\w.])(?:\d{1,3}(?:\.\d+)?%|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:倍|位|项|个|条|篇|组|次|题|模型|instances?|tests?))(?!\w)",
    re.IGNORECASE,
)
YEAR_ONLY_RE = re.compile(r"^(?:19|20)\d{2}$")
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")

NOT_FOUND_STATUSES = {404, 410}
USER_AGENT = "BenchAudit-CitationReceipt/1.0 (+offline-verification; no model API)"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", html.unescape(TAG_RE.sub(" ", value))).strip()


def _normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", html.unescape(value)).casefold()
    return " ".join(re.findall(r"[\w]+", value, flags=re.UNICODE))


def _title_matches(claimed: str, observed: str) -> bool:
    """Frozen title rule: containment or token Jaccard >= 0.70.

    Very short link labels (fewer than three tokens) are aliases, not claimed
    paper titles.  They are treated as unresolved title claims rather than as
    mismatches.
    """

    left = _normalize_title(claimed)
    right = _normalize_title(observed)
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if len(left_tokens) < 3 or not right_tokens:
        return False
    if left in right or right in left:
        return True
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) >= 0.70


def _extract_html_title(body: bytes, content_type: str) -> str:
    if "html" not in content_type.casefold() and not body.lstrip().startswith(b"<"):
        return ""
    text = body.decode("utf-8", errors="replace")
    for pattern in TITLE_PATTERNS:
        match = pattern.search(text)
        if match:
            return _clean_text(match.group(1))
    return ""


def _claimed_venue(line: str, url: str) -> str:
    marker = f"]({url})"
    if marker not in line:
        return ""
    tail = line.split(marker, 1)[1]
    tail = tail.split("。", 1)[0].split("；", 1)[0].strip(" ,，。")
    if len(tail) > 120:
        return ""
    venue_markers = (
        "ACL", "NAACL", "EMNLP", "EACL", "COLING", "CoNLL", "ICLR",
        "ICML", "NeurIPS", "AISTATS", "FAccT", "FAT", "TACL", "CACM",
        "SOSP", "ICSE", "FSE", "USENIX", "ACM", "preprint", "workshop",
        "official specification", "Recommendation",
    )
    return tail if any(marker.casefold() in tail.casefold() for marker in venue_markers) else ""


def _numbers_near_occurrence(line: str) -> list[str]:
    values: list[str] = []
    for value in NUMBER_RE.findall(line):
        stripped = value.strip()
        if YEAR_ONLY_RE.match(stripped):
            continue
        if stripped not in values:
            values.append(stripped)
    return values


def _slug(value: str) -> str:
    normalized = _normalize_title(value)
    asciiish = re.sub(r"[^a-z0-9]+", "-", normalized.encode("ascii", "ignore").decode())
    return asciiish.strip("-")[:36] or "citation"


def extract_citations(markdown: str) -> list[dict[str, Any]]:
    records: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        for match in LINK_RE.finditer(line):
            label, url = match.group(1).strip(), match.group(2).strip()
            record = records.setdefault(
                url,
                {
                    "claimed_titles": [],
                    "claimed_venues": [],
                    "numbers_claimed_in_survey": [],
                    "line_numbers": [],
                },
            )
            if label not in record["claimed_titles"]:
                record["claimed_titles"].append(label)
            venue = _claimed_venue(line, url)
            if venue and venue not in record["claimed_venues"]:
                record["claimed_venues"].append(venue)
            for value in _numbers_near_occurrence(line):
                if value not in record["numbers_claimed_in_survey"]:
                    record["numbers_claimed_in_survey"].append(value)
            record["line_numbers"].append(line_number)

    extracted: list[dict[str, Any]] = []
    for index, (url, record) in enumerate(records.items(), start=1):
        # Prefer the longest label because bibliography entries usually carry
        # the full title, while prose often uses a short alias.
        claimed_title = max(record["claimed_titles"], key=lambda value: (len(_normalize_title(value).split()), len(value)))
        extracted.append(
            {
                "cite_key": f"cite-{index:03d}-{_slug(claimed_title)}",
                "url": url,
                "claimed_title": claimed_title,
                "claimed_title_aliases": record["claimed_titles"],
                "claimed_venue": " | ".join(record["claimed_venues"]),
                "numbers_claimed_in_survey": record["numbers_claimed_in_survey"],
                "source_line_numbers": record["line_numbers"],
            }
        )
    return extracted


def fetch_direct(url: str, timeout_seconds: float, max_bytes: int) -> dict[str, Any]:
    # An empty ProxyHandler deliberately disables environment proxies.  The
    # audit either reaches the cited host directly or reports unreachable.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPRedirectHandler(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.1"})
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = int(response.status)
            body = response.read(max_bytes + 1)
            truncated = len(body) > max_bytes
            if truncated:
                body = body[:max_bytes]
            content_type = response.headers.get("Content-Type", "")
            return {
                "http_status": status,
                "resolved_url": response.geturl(),
                "content_type": content_type,
                "body": body,
                "body_truncated": truncated,
                "error": "",
            }
    except urllib.error.HTTPError as error:
        return {
            "http_status": int(error.code),
            "resolved_url": error.geturl() or url,
            "content_type": error.headers.get("Content-Type", "") if error.headers else "",
            "body": b"",
            "body_truncated": False,
            "error": f"HTTPError: {error.reason}",
        }
    except Exception as error:  # Network/TLS errors are receipt data.
        return {
            "http_status": None,
            "resolved_url": url,
            "content_type": "",
            "body": b"",
            "body_truncated": False,
            "error": f"{type(error).__name__}: {error}",
        }


def adjudicate(citation: dict[str, Any], fetched: dict[str, Any]) -> dict[str, Any]:
    status = fetched["http_status"]
    resolved_title = _extract_html_title(fetched["body"], fetched["content_type"])
    title_match: bool | None = None
    title_check_reason = "no_machine_readable_title"
    if resolved_title:
        title_match = _title_matches(citation["claimed_title"], resolved_title)
        title_check_reason = "frozen_containment_or_jaccard_rule"

    if status in NOT_FOUND_STATUSES:
        verdict = "not_found"
    elif status is None or (status is not None and status >= 500) or status in {401, 403, 408, 429}:
        verdict = "unreachable"
    elif 200 <= status < 400:
        # A URL that resolves but exposes no machine-readable title remains
        # resolved; title_match=null makes clear that the title was not proved.
        verdict = "title_mismatch" if title_match is False else "resolved"
    else:
        verdict = "unreachable"

    return {
        **citation,
        "http_status": status,
        "resolved_url": fetched["resolved_url"],
        "resolved_title": resolved_title,
        "title_match": title_match,
        "title_check_reason": title_check_reason,
        "observed_venue": "",
        "numbers_verified": None,
        "verdict": verdict,
        "content_type": fetched["content_type"],
        "response_prefix_sha256": _sha256(fetched["body"]) if fetched["body"] else None,
        "response_prefix_bytes": len(fetched["body"]),
        "response_truncated": fetched["body_truncated"],
        "error": fetched["error"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("survey", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--max-bytes", type=int, default=4_000_000)
    parser.add_argument("--delay-seconds", type=float, default=0.15)
    args = parser.parse_args()

    survey_bytes = args.survey.read_bytes()
    markdown = survey_bytes.decode("utf-8")
    citations = extract_citations(markdown)
    if not citations:
        raise SystemExit("no Markdown citations found")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as output:
        for index, citation in enumerate(citations, start=1):
            fetched = fetch_direct(citation["url"], args.timeout_seconds, args.max_bytes)
            receipt = adjudicate(citation, fetched)
            receipt["receipt_schema"] = "benchaudit-citation-resolution-v1"
            receipt["survey_sha256"] = _sha256(survey_bytes)
            output.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
            print(f"[{index}/{len(citations)}] {receipt['verdict']:14s} {citation['url']}", flush=True)
            if index != len(citations):
                time.sleep(args.delay_seconds)

    print(json.dumps({"citations": len(citations), "out": str(args.out), "survey_sha256": _sha256(survey_bytes)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
