from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts/audit_research_citations.py"
SPEC = importlib.util.spec_from_file_location("citation_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _citation() -> dict:
    return {
        "cite_key": "cite-001",
        "url": "https://example.test/paper",
        "claimed_title": "A Real Research Paper",
    }


def _fetched(title: str, *, status: int | None = 200) -> dict:
    body = f"<html><title>{title}</title></html>".encode()
    return {
        "http_status": status,
        "resolved_url": "https://example.test/paper",
        "content_type": "text/html",
        "body": body,
        "body_truncated": False,
        "error": "",
    }


def test_antibot_interstitial_is_neither_resolved_nor_title_mismatch() -> None:
    receipt = MODULE.adjudicate(_citation(), _fetched("Verifying your browser"))
    assert receipt["verdict"] == "blocked_by_anti_bot"
    assert receipt["title_match"] is None
    assert receipt["title_check_reason"] == "anti_bot_interstitial_not_cited_content"


def test_normal_title_still_uses_frozen_title_rule() -> None:
    receipt = MODULE.adjudicate(_citation(), _fetched("A Real Research Paper"))
    assert receipt["verdict"] == "resolved"
    assert receipt["title_match"] is True


def test_terminal_counts_are_mutually_exhaustive() -> None:
    receipts = [{"verdict": verdict} for verdict in sorted(MODULE.TERMINAL_VERDICTS)]
    counts = MODULE.terminal_counts(receipts, expected=5)
    assert sum(counts.values()) == 5
    assert all(value == 1 for value in counts.values())
    with pytest.raises(RuntimeError):
        MODULE.terminal_counts([{"verdict": "skipped"}], expected=1)


def test_proxy_configuration_is_explicit_and_rejects_credentials() -> None:
    opener = MODULE.build_opener(transport="proxy", proxy_url="http://127.0.0.1:17890")
    assert opener is not None
    with pytest.raises(ValueError):
        MODULE.build_opener(transport="proxy", proxy_url=None)
    with pytest.raises(ValueError):
        MODULE.build_opener(transport="proxy", proxy_url="http://user:secret@127.0.0.1:17890")
    with pytest.raises(ValueError):
        MODULE.build_opener(transport="direct", proxy_url="http://127.0.0.1:17890")
