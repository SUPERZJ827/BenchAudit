from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import socketserver
import threading
import time

import pytest

import scripts.https_connect_allowlist_proxy as connect_proxy

from scripts.https_connect_allowlist_proxy import (
    AuditLogger,
    AuditedThreadingTCPServer,
    ConnectHandler,
    DISPOSITIONS,
    normalize_listen_address,
    normalize_upstream_proxy_authority,
)
from scripts.run_verifier_topology_preflight import (
    ENGINE_PROFILES,
    UPSTREAM_PROXY_PROFILES,
    _derive_internal_network,
    _summary_gate,
    _upstream_proxy_observation_matches,
)


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


class _NestedConnectHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = bytearray()
        self.request.settimeout(2)
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            data.extend(chunk)
        header, buffered = bytes(data).split(b"\r\n\r\n", 1)
        self.server.request_headers.append(header)  # type: ignore[attr-defined]
        status = self.server.connect_status  # type: ignore[attr-defined]
        self.request.sendall(
            f"HTTP/1.1 {status} fixture\r\n\r\n".encode("ascii")
        )
        if status != 200:
            return
        if buffered:
            self.request.sendall(buffered)
        while True:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            self.request.sendall(chunk)


class _MalformedNestedConnectHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.recv(4096)
        self.request.sendall(b"not-http\r\n\r\n")


class _EofNestedConnectHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.recv(4096)


class _StalledNestedConnectHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.recv(4096)
        time.sleep(0.3)


def _start_nested_connect_upstream(*, status: int = 200):
    server = _ThreadedServer(("127.0.0.1", 0), _NestedConnectHandler)
    server.connect_status = status
    server.request_headers = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _start_custom_nested_upstream(handler):
    server = _ThreadedServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _recv_header(client: socket.socket) -> bytes:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        data.extend(client.recv(4096))
    return bytes(data)


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
    upstream_profile_id: str | None = None,
    upstream_proxy_authority: str | None = None,
):
    audit = AuditLogger(
        audit_log=tmp_path / "raw.jsonl",
        stable_summary_out=tmp_path / "stable.json",
        session_id="fixture-session",
        allowed_authority=allowed_authority,
        listen_text="127.0.0.1",
        listen_normalized="127.0.0.1",
        port=0,
        upstream_profile_id=upstream_profile_id,
        upstream_proxy_authority=upstream_proxy_authority,
    )
    handler = type(
        "FixtureConnectHandler",
        (handler_base,),
        {
            "allowed_authority": allowed_authority,
            "upstream_profile_id": upstream_profile_id,
            "upstream_proxy_authority": upstream_proxy_authority,
        },
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


def test_nested_connect_uses_pinned_upstream_and_relays(tmp_path: Path):
    upstream, upstream_thread = _start_nested_connect_upstream()
    upstream_authority = f"127.0.0.1:{upstream.server_address[1]}"
    authority = "allowed.invalid:443"
    server, thread, audit = _start_proxy(
        tmp_path,
        allowed_authority=authority,
        upstream_profile_id="fixture-upstream-v1",
        upstream_proxy_authority=upstream_authority,
    )
    with socket.create_connection(("127.0.0.1", server.server_address[1])) as client:
        client.settimeout(2)
        client.sendall(f"CONNECT {authority} HTTP/1.1\r\n\r\n".encode())
        assert _recv_header(client).startswith(b"HTTP/1.1 200")
        client.sendall(b"fixture-payload")
        assert client.recv(len(b"fixture-payload")) == b"fixture-payload"
    _wait_for_connections(audit, 1)
    summary = _finish_proxy(server, thread, audit)
    upstream.shutdown()
    upstream.server_close()
    upstream_thread.join(timeout=2)

    _assert_single_disposition(summary, authority, "allowed")
    assert summary["upstream_mode"] == "http_connect"
    assert summary["upstream_profile_id"] == "fixture-upstream-v1"
    assert summary["upstream_proxy_authority"] == upstream_authority
    assert len(upstream.request_headers) == 1
    assert upstream.request_headers[0].startswith(
        f"CONNECT {authority} HTTP/1.1".encode()
    )


@pytest.mark.parametrize("status", [403, 407, 502])
def test_nested_connect_rejection_fails_closed_without_direct_fallback(
    tmp_path: Path, status: int
):
    upstream, upstream_thread = _start_nested_connect_upstream(status=status)
    upstream_authority = f"127.0.0.1:{upstream.server_address[1]}"
    authority = "does-not-resolve.invalid:443"
    server, thread, audit = _start_proxy(
        tmp_path,
        allowed_authority=authority,
        upstream_profile_id="fixture-upstream-v1",
        upstream_proxy_authority=upstream_authority,
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

    assert response.startswith(b"HTTP/1.1 502")
    _assert_single_disposition(summary, authority, "upstream_failed")
    row = [
        json.loads(line)
        for line in (tmp_path / "raw.jsonl").read_text().splitlines()
        if json.loads(line)["record_type"] == "connection"
    ][0]
    assert row["reason"] == f"upstream_proxy_status_{status}"
    assert len(upstream.request_headers) == 1


@pytest.mark.parametrize(
    ("handler", "expected_reason"),
    [
        (_MalformedNestedConnectHandler, "upstream_proxy_invalid_status_line"),
        (_EofNestedConnectHandler, "upstream_proxy_eof_before_complete_header"),
    ],
)
def test_nested_connect_malformed_or_eof_fails_closed(
    tmp_path: Path, handler, expected_reason: str
):
    upstream, upstream_thread = _start_custom_nested_upstream(handler)
    upstream_authority = f"127.0.0.1:{upstream.server_address[1]}"
    authority = "does-not-resolve.invalid:443"
    server, thread, audit = _start_proxy(
        tmp_path,
        allowed_authority=authority,
        upstream_profile_id="fixture-upstream-v1",
        upstream_proxy_authority=upstream_authority,
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

    assert response.startswith(b"HTTP/1.1 502")
    _assert_single_disposition(summary, authority, "upstream_failed")
    rows = [json.loads(line) for line in (tmp_path / "raw.jsonl").read_text().splitlines()]
    connection = [row for row in rows if row["record_type"] == "connection"][0]
    assert connection["reason"] == expected_reason


def test_nested_connect_timeout_fails_closed(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(connect_proxy, "UPSTREAM_TIMEOUT_SECONDS", 0.05)
    upstream, upstream_thread = _start_custom_nested_upstream(
        _StalledNestedConnectHandler
    )
    upstream_authority = f"127.0.0.1:{upstream.server_address[1]}"
    authority = "does-not-resolve.invalid:443"
    server, thread, audit = _start_proxy(
        tmp_path,
        allowed_authority=authority,
        upstream_profile_id="fixture-upstream-v1",
        upstream_proxy_authority=upstream_authority,
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

    assert response.startswith(b"HTTP/1.1 502")
    _assert_single_disposition(summary, authority, "upstream_failed")


def test_nonallowlisted_request_is_rejected_before_nested_upstream_dial(tmp_path: Path):
    upstream, upstream_thread = _start_nested_connect_upstream()
    upstream_authority = f"127.0.0.1:{upstream.server_address[1]}"
    server, thread, audit = _start_proxy(
        tmp_path,
        allowed_authority="allowed.invalid:443",
        upstream_profile_id="fixture-upstream-v1",
        upstream_proxy_authority=upstream_authority,
    )
    response = _request(
        server.server_address[1], b"CONNECT denied.invalid:443 HTTP/1.1\r\n\r\n"
    )
    _wait_for_connections(audit, 1)
    summary = _finish_proxy(server, thread, audit)
    upstream.shutdown()
    upstream.server_close()
    upstream_thread.join(timeout=2)

    assert response.startswith(b"HTTP/1.1 403")
    _assert_single_disposition(summary, "denied.invalid:443", "forbidden")
    assert upstream.request_headers == []


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


@pytest.mark.parametrize(
    "value", ["proxy.invalid:17890", "0.0.0.0:17890", "[::]:17890"]
)
def test_upstream_proxy_authority_requires_usable_literal_ip(value: str):
    with pytest.raises(ValueError):
        normalize_upstream_proxy_authority(value)


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


def test_podman_cni_internal_network_derivation_is_fail_closed():
    internal = {
        "plugins": [
            {"type": "bridge", "isGateway": False},
            {"type": "portmap"},
            {"type": "firewall"},
        ]
    }
    assert _derive_internal_network(internal) == (
        True,
        "podman_cni_no_gateway_no_masquerade_no_dnsname",
    )

    egress = {
        "plugins": [
            {"type": "bridge", "isGateway": True, "ipMasq": True},
            {"type": "dnsname"},
        ]
    }
    assert _derive_internal_network(egress) == (
        False,
        "podman_cni_gateway_with_masquerade",
    )

    assert _derive_internal_network({"plugins": [{"type": "bridge"}]}) == (
        None,
        "podman_cni_ambiguous",
    )


def test_verifier_engine_profiles_are_code_owned_and_not_free_form():
    assert set(ENGINE_PROFILES) == {"podman-3.4.4", "docker-29.4.1"}
    docker = ENGINE_PROFILES["docker-29.4.1"]
    assert docker == {
        "executable": "/usr/bin/docker",
        "engine_name": "docker",
        "client_version": "29.4.1",
        "server_version": "29.4.1",
        "executable_sha256": "1fc0af13dcb8070408ce2ac4051b76f76ff0c63570bdaeeb6bd5b13b993d0249",
        "version_output_sha256": "7728e85580e079e17edb6b02fe937fe85727034c12a8d017a9efab6567e2733b",
        "invocation_schema": "docker-cli-29.4-v1",
    }
    assert UPSTREAM_PROXY_PROFILES == {
        "mihomo-host-17890-v1": {
            "access_host": "127.0.0.1",
            "port": 17890,
            "listener_inode": "2095371633",
            "listener_cgroup": "/system.slice/mihomo.service",
            "service": "mihomo.service",
            "main_pid": "1480383",
            "active_enter_timestamp_monotonic": "7363036411785",
            "exec_main_start_timestamp_monotonic": "7363036411213",
            "exec_start_fragment": "/usr/bin/mihomo -d /etc/mihomo",
            "binary": "/usr/bin/mihomo",
            "binary_sha256": "82f0f824f553d5ad950611cec476b8ed94b9f9ac629388d28c322c0814b2bc12",
            "version": "Mihomo Meta v1.19.29 linux amd64 with go1.26.5 Sat Jul 18 12:22:36 UTC 2026",
            "unit": "/lib/systemd/system/mihomo.service",
            "unit_sha256": "b4b011a4b5670b09cc7d21a73cbaf47e038ff3f504deb16afab460555572f3a4",
            "configuration_readable": False,
        }
    }


def test_upstream_proxy_runtime_binding_rejects_each_identity_drift():
    profile = UPSTREAM_PROXY_PROFILES["mihomo-host-17890-v1"]
    properties = {
        "MainPID": profile["main_pid"],
        "ActiveState": "active",
        "SubState": "running",
        "ExecMainStartTimestampMonotonic": profile[
            "exec_main_start_timestamp_monotonic"
        ],
        "ActiveEnterTimestampMonotonic": profile[
            "active_enter_timestamp_monotonic"
        ],
        "FragmentPath": profile["unit"],
        "ExecStart": "{ argv[]=/usr/bin/mihomo -d /etc/mihomo ; }",
    }
    listener = (
        "LISTEN *:17890 ino:2095371633 "
        "cgroup:/system.slice/mihomo.service"
    )
    kwargs = {
        "properties": properties,
        "observed_version": profile["version"],
        "listener_stdout": listener,
    }
    assert _upstream_proxy_observation_matches(profile, **kwargs)

    for key in (
        "MainPID",
        "ExecMainStartTimestampMonotonic",
        "ActiveEnterTimestampMonotonic",
    ):
        drifted = dict(properties, **{key: "drifted"})
        assert not _upstream_proxy_observation_matches(
            profile, **dict(kwargs, properties=drifted)
        )
    assert not _upstream_proxy_observation_matches(
        profile, **dict(kwargs, observed_version="drifted")
    )
    assert not _upstream_proxy_observation_matches(
        profile, **dict(kwargs, listener_stdout="LISTEN *:17890")
    )
