"""The client speaks raw http.client, which ignores the environment.

On a host whose only egress is a loopback CONNECT proxy, a direct connection
hangs for the full timeout on every retry, which looks exactly like an
unresponsive provider.  These tests pin the proxy-selection rules; they make
no network calls.
"""

from __future__ import annotations

import pytest

from benchcore.llm_client import resolve_https_proxy


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch):
    for name in ("https_proxy", "HTTPS_PROXY", "no_proxy", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)


def test_no_proxy_configured_means_direct(monkeypatch):
    assert resolve_https_proxy("api.deepseek.com") is None


def test_https_proxy_is_used(monkeypatch):
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:17890")
    assert resolve_https_proxy("api.deepseek.com") == "http://127.0.0.1:17890"


def test_uppercase_variant_is_honoured(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1080")
    assert resolve_https_proxy("api.deepseek.com") == "http://127.0.0.1:1080"


@pytest.mark.parametrize(
    "no_proxy,host,expect_proxy",
    [
        ("api.deepseek.com", "api.deepseek.com", False),
        ("deepseek.com", "api.deepseek.com", False),
        (".deepseek.com", "api.deepseek.com", False),
        ("localhost,127.*", "api.deepseek.com", True),
        ("other.com", "api.deepseek.com", True),
    ],
)
def test_no_proxy_list_is_respected(monkeypatch, no_proxy, host, expect_proxy):
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:17890")
    monkeypatch.setenv("no_proxy", no_proxy)
    resolved = resolve_https_proxy(host)
    assert (resolved is not None) is expect_proxy


def test_localhost_wildcard_does_not_leak_to_other_hosts(monkeypatch):
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:17890")
    monkeypatch.setenv("no_proxy", "127.*")
    assert resolve_https_proxy("127.0.0.1") is None
    assert resolve_https_proxy("api.deepseek.com") is not None
