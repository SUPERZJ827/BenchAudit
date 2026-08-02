from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import socketserver
import threading
import time

import pytest

from scripts.https_connect_allowlist_proxy import (
    AuditLogger,
    AuditedThreadingTCPServer,
    ConnectHandler,
    DISPOSITIONS,
    normalize_listen_address,
)
from scripts.run_verifier_topology_preflight import _summary_gate


class _UpstreamHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(1)
        try:
            while self.request.recv(4096):
                pass
        except (OSError, socket.timeout):
            pass


class _ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _start_upstream():
    server = _ThreadedServer(("127.0.0.1", 0), _UpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _start_proxy(
    tmp_path: Path,
    *,
    allowed_authority: str,
    handler_base: type[ConnectHandler] = ConnectHandler,
):
    audit = AuditLogger(
        audit_log=tmp_path / "raw.jsonl",
        stable_summary_out=tmp_path / "stable.json",
        session_id="fixture-session",
        allowed_authority=allowed_authority,
        listen_text="127.0.0.1",
        listen_normalized="127.0.0.1",
        port=0,
    )
    handler = type(
        "FixtureConnectHandler",
        (handler_base,),
        {"allowed_authority": allowed_authority},
    )
    server = AuditedThreadingTCPServer(
        ("127.0.0.1", 0), handler, audit=audit
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, audit


def _wait_for_connections(audit: AuditLogger, count: int) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        summary = audit.stable_summary()
        observed = sum(
            sum(values.values())
            for values in summary["disposition_counts"].values()
        ) + sum(summary["unparsed_disposition_counts"].values())
        if observed >= count:
            return
        time.sleep(0.01)
    raise AssertionError(f"only observed {observed} of {count} connections")


def _finish_proxy(server, thread, audit):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    return audit.finish()


def _request(proxy_port: int, request: bytes, *, read_response: bool = True) -> bytes:
    with socket.create_connection(("127.0.0.1", proxy_port), timeout=1) as client:
        client.sendall(request)
        client.shutdown(socket.SHUT_WR)
        if not read_response:
            return b""
        chunks = []
        while True:
            value = client.recv(4096)
            if not value:
                return b"".join(chunks)
            chunks.append(value)


def _assert_single_disposition(summary, authority, disposition):
    assert summary["parsed_authorities"] == [authority]
    counts = summary["disposition_counts"][authority]
    assert set(counts) == set(DISPOSITIONS)
    assert counts[disposition] == 1
    assert sum(counts.values()) == 1
    assert sum(summary["unparsed_disposition_counts"].values()) == 0


def test_allowed_connect_is_audited_with_session_boundaries(tmp_path: Path):
    upstream, upstream_thread = _start_upstream()
    authority = f"127.0.0.1:{upstream.server_address[1]}"
    server, thread, audit = _start_proxy(tmp_path, allowed_authority=authority)
    response = _request(
        server.server_address[1],
        f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode(),
    )
    _wait_for_connections(audit, 1)
    summary = _finish_proxy(server, thread, audit)
    upstream.shutdown()
    upstream.server_close()
    upstream_thread.join(timeout=2)

    assert response.startswith(b"HTTP/1.1 200")
    _assert_single_disposition(summary, authority, "allowed")
    rows = [json.loads(line) for line in (tmp_path / "raw.jsonl").read_text().splitlines()]
    assert [row["record_type"] for row in rows] == [
        "session_start", "connection", "session_end"
    ]
    assert rows[1]["connection_sequence"] == 1
    assert rows[1]["upstream_connected"] is True
    assert json.loads((tmp_path / "stable.json").read_text()) == summary


def test_live_non_allowlisted_authority_is_forbidden_and_visible(tmp_path: Path):
    allowed = "allowed.invalid:443"
    denied = "denied.invalid:443"
    server, thread, audit = _start_proxy(tmp_path, allowed_authority=allowed)
    response = _request(
        server.server_address[1],
        f"CONNECT {denied} HTTP/1.1\r\n\r\n".encode(),
    )
    _wait_for_connections(audit, 1)
    summary = _finish_proxy(server, thread, audit)

    assert response.startswith(b"HTTP/1.1 403")
    _assert_single_disposition(summary, denied, "forbidden")


def test_upstream_failure_is_audited(tmp_path: Path):
    temporary = socket.socket()
    temporary.bind(("127.0.0.1", 0))
    unused_port = temporary.getsockname()[1]
    temporary.close()
    authority = f"127.0.0.1:{unused_port}"
    server, thread, audit = _start_proxy(tmp_path, allowed_authority=authority)
    response = _request(
        server.server_address[1],
        f"CONNECT {authority} HTTP/1.1\r\n\r\n".encode(),
    )
    _wait_for_connections(audit, 1)
    summary = _finish_proxy(server, thread, audit)

    assert response.startswith(b"HTTP/1.1 502")
    _assert_single_disposition(summary, authority, "upstream_failed")


def test_malformed_and_client_aborted_connections_are_not_silent(tmp_path: Path):
    server, thread, audit = _start_proxy(
        tmp_path, allowed_authority="allowed.invalid:443"
    )
    malformed = _request(server.server_address[1], b"not-a-request\r\n\r\n")
    client = socket.create_connection(("127.0.0.1", server.server_address[1]))
    client.close()
    _wait_for_connections(audit, 2)
    summary = _finish_proxy(server, thread, audit)

    assert malformed.startswith(b"HTTP/1.1 400")
    assert summary["parsed_authorities"] == []
    assert summary["unparsed_disposition_counts"]["malformed"] == 1
    assert summary["unparsed_disposition_counts"]["client_aborted"] == 1
    assert sum(summary["unparsed_disposition_counts"].values()) == 2


def test_unexpected_relay_exception_is_audited_as_handler_error(tmp_path: Path):
    class FailingRelayHandler(ConnectHandler):
        def _relay(self, upstream: socket.socket) -> None:
            del upstream
            raise RuntimeError("fixture relay failure")

    upstream, upstream_thread = _start_upstream()
    authority = f"127.0.0.1:{upstream.server_address[1]}"
    server, thread, audit = _start_proxy(
        tmp_path,
        allowed_authority=authority,
        handler_base=FailingRelayHandler,
    )
    response = _request(
        server.server_address[1],
        f"CONNECT {authority} HTTP/1.1\r\n\r\n".encode(),
    )
    _wait_for_connections(audit, 1)
    summary = _finish_proxy(server, thread, audit)
    upstream.shutdown()
    upstream.server_close()
    upstream_thread.join(timeout=2)

    assert response.startswith(b"HTTP/1.1 200")
    _assert_single_disposition(summary, authority, "handler_error")


@pytest.mark.parametrize("value", ["0.0.0.0", "::", "not-an-ip"])
def test_unspecified_or_nonliteral_listen_addresses_are_rejected(value: str):
    with pytest.raises(argparse.ArgumentTypeError):
        normalize_listen_address(value)


def test_concurrent_jsonl_records_are_complete_and_sequences_unique(tmp_path: Path):
    server, thread, audit = _start_proxy(
        tmp_path, allowed_authority="allowed.invalid:443"
    )
    denied = "denied.invalid:443"
    workers = [
        threading.Thread(
            target=_request,
            args=(
                server.server_address[1],
                f"CONNECT {denied} HTTP/1.1\r\n\r\n".encode(),
            ),
        )
        for _ in range(8)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    _wait_for_connections(audit, 8)
    _finish_proxy(server, thread, audit)

    rows = [json.loads(line) for line in (tmp_path / "raw.jsonl").read_text().splitlines()]
    connections = [row for row in rows if row["record_type"] == "connection"]
    assert len(connections) == 8
    assert sorted(row["connection_sequence"] for row in connections) == list(range(1, 9))
    assert {row["disposition"] for row in connections} == {"forbidden"}


def test_preflight_summary_gates_require_live_allow_and_live_reject():
    zeroes = {value: 0 for value in DISPOSITIONS}
    fetch_counts = dict(zeroes, allowed=2)
    fetch = {
        "parsed_authorities": ["huggingface.co:443"],
        "disposition_counts": {"huggingface.co:443": fetch_counts},
        "unparsed_disposition_counts": zeroes,
    }
    assert all(_summary_gate(
        fetch,
        expected_authority="huggingface.co:443",
        expected_disposition="allowed",
    ).values())

    reject_counts = dict(zeroes, forbidden=1)
    rejection = {
        "parsed_authorities": ["example.com:443"],
        "disposition_counts": {"example.com:443": reject_counts},
        "unparsed_disposition_counts": zeroes,
    }
    assert all(_summary_gate(
        rejection,
        expected_authority="example.com:443",
        expected_disposition="forbidden",
    ).values())

    never_rejects = dict(rejection)
    never_rejects["disposition_counts"] = {
        "example.com:443": dict(zeroes, allowed=1)
    }
    assert not all(_summary_gate(
        never_rejects,
        expected_authority="example.com:443",
        expected_disposition="forbidden",
    ).values())


def test_preflight_gate_rejects_unparsed_or_second_authority_events():
    zeroes = {value: 0 for value in DISPOSITIONS}
    counts = dict(zeroes, allowed=1)
    value = {
        "parsed_authorities": ["example.com:443", "huggingface.co:443"],
        "disposition_counts": {
            "huggingface.co:443": counts,
            "example.com:443": dict(zeroes, forbidden=1),
        },
        "unparsed_disposition_counts": dict(zeroes, client_aborted=1),
    }
    decision = _summary_gate(
        value,
        expected_authority="huggingface.co:443",
        expected_disposition="allowed",
    )
    assert decision["authority_set_exact"] is False
    assert decision["no_unparsed_events"] is False
