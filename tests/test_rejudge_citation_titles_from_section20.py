from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/rejudge_citation_titles_from_section20.py"
SPEC = importlib.util.spec_from_file_location("citation_rejudge", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_extracts_only_section20_and_requires_unique_urls() -> None:
    markdown = """[body](https://example.test/body)
## 20. 扩展文献索引
1. [A Full Paper Title](https://example.test/paper)
## 21. End
[later](https://example.test/later)
"""
    assert MODULE.extract_section20_entries(markdown) == [
        {"index_title": "A Full Paper Title", "url": "https://example.test/paper"}
    ]


def test_rejudge_uses_index_title_without_network() -> None:
    receipt = {
        "cite_key": "cite-001",
        "url": "https://example.test/paper",
        "claimed_title": "Short Alias",
        "resolved_title": "A Full Paper Title",
        "http_status": 200,
        "verdict": "title_mismatch",
    }
    row = MODULE.rejudge(receipt, index_title="A Full Paper Title")
    assert row["rejudged_verdict"] == "resolved"
    assert row["original_verdict"] == "title_mismatch"
    assert row["network_used"] is False


def test_rejudge_does_not_widen_antibot_signature() -> None:
    receipt = {
        "cite_key": "cite-001",
        "url": "https://openreview.net/forum?id=x",
        "claimed_title": "Paper",
        "resolved_title": "Verifying your browser | OpenReview",
        "http_status": 200,
        "verdict": "title_mismatch",
    }
    row = MODULE.rejudge(receipt, index_title="A Full Paper Title")
    assert row["rejudged_verdict"] == "title_mismatch"


def test_summary_is_mutually_exhaustive() -> None:
    rows = [
        {"original_verdict": "title_mismatch", "rejudged_verdict": "resolved"},
        {"original_verdict": "unreachable", "rejudged_verdict": "unreachable"},
    ]
    summary = MODULE.summarize(rows)
    assert summary["terminal_count_sum"] == 2
    assert summary["terminal_counts"]["resolved"] == 1
    assert summary["terminal_counts"]["unreachable"] == 1
