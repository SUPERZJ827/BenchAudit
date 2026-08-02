#!/usr/bin/env python3
"""Audited CONNECT proxy restricted to one exact HTTPS authority."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import select
import signal
import socket
import socketserver
import threading
from typing import Any


MAX_HEADER_BYTES = 16 * 1024
DISPOSITIONS = (
    "allowed",
    "forbidden",
    "malformed",
    "upstream_failed",
    "client_aborted",
    "handler_error",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def normalize_listen_address(value: str) -> str:
    """Require a literal, non-wildcard IP address."""

    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--listen must be a literal IP address") from exc
    if address.is_unspecified:
        raise argparse.ArgumentTypeError("--listen must not be an unspecified address")
    return address.compressed


def normalize_authority(value: str) -> str:
    """Normalize a host:port CONNECT authority without resolving it."""

    value = value.strip()
    try:
        host, port_text = value.rsplit(":", 1)
        port = int(port_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("authority must be host:port") from exc
    if not host or not (1 <= port <= 65535):
        raise ValueError("authority host or port is invalid")
    return f"{host.casefold()}:{port}"


class AuditLogger:
    """Write one terminal record per accepted socket plus stable aggregates."""

    def __init__(
        self,
        *,
        audit_log: Path,
        stable_summary_out: Path,
        session_id: str,
        allowed_authority: str,
        listen_text: str,
        listen_normalized: str,
        port: int,
    ) -> None:
        if not session_id:
            raise ValueError("session_id is required")
        self.audit_log = audit_log
        self.stable_summary_out = stable_summary_out
        self.session_id = session_id
        self.allowed_authority = normalize_authority(allowed_authority)
        self.listen_text = listen_text
        self.listen_normalized = listen_normalized
        self.port = port
        self._lock = threading.RLock()
        self._next_sequence = 1
        self._finished = False
        self._parsed_authorities: set[str] = set()
        self._counts: dict[str, dict[str, int]] = {}
        self._unparsed_counts = {value: 0 for value in DISPOSITIONS}
        audit_log.parent.mkdir(parents=True, exist_ok=True)
        stable_summary_out.parent.mkdir(parents=True, exist_ok=True)
        self._stream = audit_log.open("x", encoding="utf-8")
        os.chmod(audit_log, 0o600)
        self._write_locked({
            "record_type": "session_start",
            "session_id": session_id,
            "timestamp": _utc_now(),
            "allowed_authority": self.allowed_authority,
            "listen_text": listen_text,
            "listen_normalized": listen_normalized,
            "port": port,
        })

    def _write_locked(self, value: dict[str, Any]) -> None:
        self._stream.write(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        )
        self._stream.flush()

    def reserve_connection(self) -> int:
        with self._lock:
            value = self._next_sequence
            self._next_sequence += 1
            return value

    def record_connection(
        self,
        *,
        sequence: int,
        client_address: tuple[Any, ...],
        request_line: bytes,
        method: str | None,
        authority: str | None,
        disposition: str,
        status_code: int | None,
        reason: str,
        upstream_connected: bool,
    ) -> None:
        if disposition not in DISPOSITIONS:
            raise ValueError(f"unknown disposition: {disposition}")
        normalized_authority = None
        if authority is not None:
            try:
                normalized_authority = normalize_authority(authority)
            except ValueError:
                normalized_authority = None
        with self._lock:
            if normalized_authority is None:
                self._unparsed_counts[disposition] += 1
            else:
                self._parsed_authorities.add(normalized_authority)
                counts = self._counts.setdefault(
                    normalized_authority,
                    {value: 0 for value in DISPOSITIONS},
                )
                counts[disposition] += 1
            self._write_locked({
                "record_type": "connection",
                "session_id": self.session_id,
                "timestamp": _utc_now(),
                "connection_sequence": sequence,
                "client_address": [str(value) for value in client_address],
                "request_line_base64": base64.b64encode(request_line).decode("ascii"),
                "method": method,
                "authority": authority,
                "normalized_authority": normalized_authority,
                "disposition": disposition,
                "status_code": status_code,
                "reason": reason,
                "upstream_connected": upstream_connected,
            })

    def stable_summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "summary_schema": "benchaudit-connect-proxy-stable-summary-v1",
                "allowed_authority": self.allowed_authority,
                "listen_text": self.listen_text,
                "listen_normalized": self.listen_normalized,
                "port": self.port,
                "parsed_authorities": sorted(self._parsed_authorities),
                "disposition_counts": {
                    authority: dict(sorted(counts.items()))
                    for authority, counts in sorted(self._counts.items())
                },
                "unparsed_disposition_counts": dict(
                    sorted(self._unparsed_counts.items())
                ),
            }

    def finish(self) -> dict[str, Any]:
        with self._lock:
            if self._finished:
                raise RuntimeError("audit session was already finished")
            summary = self.stable_summary()
            self._write_locked({
                "record_type": "session_end",
                "session_id": self.session_id,
                "timestamp": _utc_now(),
                "accepted_connection_count": self._next_sequence - 1,
            })
            self._stream.close()
            self.stable_summary_out.write_bytes(_canonical_bytes(summary) + b"\n")
            os.chmod(self.stable_summary_out, 0o600)
            self._finished = True
            return summary


class ConnectHandler(socketserver.BaseRequestHandler):
    allowed_authority: str

    def _send_response(self, status_code: int, reason: str) -> None:
        try:
            self.request.sendall(
                f"HTTP/1.1 {status_code} {reason}\r\nConnection: close\r\n\r\n".encode(
                    "ascii"
                )
            )
        except OSError:
            pass

    def _relay(self, upstream: socket.socket) -> None:
        upstream.setblocking(False)
        self.request.setblocking(False)
        sockets = (self.request, upstream)
        while True:
            readable, _, exceptional = select.select(sockets, (), sockets, 30)
            if exceptional:
                raise OSError("relay exceptional socket")
            if not readable:
                raise TimeoutError("relay idle timeout")
            for source in readable:
                try:
                    chunk = source.recv(65536)
                except (BlockingIOError, ConnectionResetError):
                    return
                if not chunk:
                    return
                target = upstream if source is self.request else self.request
                try:
                    target.sendall(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return

    def handle(self) -> None:
        server = self.server
        assert isinstance(server, AuditedThreadingTCPServer)
        sequence = server.connection_sequence_for(self.request)
        disposition = "handler_error"
        status_code: int | None = None
        reason = "handler did not reach a terminal branch"
        method: str | None = None
        authority: str | None = None
        request_line = b""
        upstream_connected = False
        data = bytearray()
        try:
            self.request.settimeout(10)
            while b"\r\n\r\n" not in data and len(data) < MAX_HEADER_BYTES:
                try:
                    chunk = self.request.recv(4096)
                except socket.timeout:
                    disposition = "client_aborted"
                    reason = "header_timeout"
                    return
                if not chunk:
                    disposition = "client_aborted"
                    reason = "eof_before_complete_header"
                    return
                data.extend(chunk)
            request_line = bytes(data).split(b"\r\n", 1)[0]
            if b"\r\n\r\n" not in data:
                disposition = "malformed"
                status_code = 400
                reason = "header_too_large"
                self._send_response(status_code, "Bad Request")
                return
            try:
                first_line = request_line.decode("ascii")
                method, authority, version = first_line.split(" ")
                normalize_authority(authority)
            except (UnicodeDecodeError, ValueError):
                disposition = "malformed"
                status_code = 400
                reason = "invalid_request_line"
                self._send_response(status_code, "Bad Request")
                return
            if (
                method != "CONNECT"
                or version not in {"HTTP/1.0", "HTTP/1.1"}
                or normalize_authority(authority) != self.allowed_authority
            ):
                disposition = "forbidden"
                status_code = 403
                reason = "method_version_or_authority_not_allowed"
                self._send_response(status_code, "Forbidden")
                return
            host, port_text = authority.rsplit(":", 1)
            try:
                upstream = socket.create_connection((host, int(port_text)), timeout=15)
            except OSError as exc:
                disposition = "upstream_failed"
                status_code = 502
                reason = type(exc).__name__
                self._send_response(status_code, "Bad Gateway")
                return
            upstream_connected = True
            with upstream:
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                status_code = 200
                self._relay(upstream)
            disposition = "allowed"
            reason = "allowed_tunnel_completed"
        except Exception as exc:  # fail closed and make every accepted socket visible
            disposition = "handler_error"
            reason = type(exc).__name__
        finally:
            server.audit.record_connection(
                sequence=sequence,
                client_address=self.client_address,
                request_line=request_line,
                method=method,
                authority=authority,
                disposition=disposition,
                status_code=status_code,
                reason=reason,
                upstream_connected=upstream_connected,
            )


class AuditedThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = False
    block_on_close = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[ConnectHandler],
        *,
        audit: AuditLogger,
    ) -> None:
        self.audit = audit
        self.address_family = (
            socket.AF_INET6
            if ipaddress.ip_address(server_address[0]).version == 6
            else socket.AF_INET
        )
        self._sequence_lock = threading.Lock()
        self._connection_sequences: dict[int, int] = {}
        super().__init__(server_address, handler_class)

    def get_request(self) -> tuple[socket.socket, Any]:
        request, client_address = super().get_request()
        with self._sequence_lock:
            self._connection_sequences[id(request)] = self.audit.reserve_connection()
        return request, client_address

    def connection_sequence_for(self, request: socket.socket) -> int:
        with self._sequence_lock:
            try:
                return self._connection_sequences.pop(id(request))
            except KeyError as exc:
                raise RuntimeError("accepted socket has no audit sequence") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", required=True)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--allow-authority", required=True)
    parser.add_argument("--audit-log", type=Path, required=True)
    parser.add_argument("--stable-summary-out", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()
    listen_normalized = normalize_listen_address(args.listen)
    allowed_authority = normalize_authority(args.allow_authority)
    audit = AuditLogger(
        audit_log=args.audit_log,
        stable_summary_out=args.stable_summary_out,
        session_id=args.session_id,
        allowed_authority=allowed_authority,
        listen_text=args.listen,
        listen_normalized=listen_normalized,
        port=args.port,
    )
    handler = type(
        "PinnedConnectHandler",
        (ConnectHandler,),
        {"allowed_authority": allowed_authority},
    )
    with AuditedThreadingTCPServer(
        (listen_normalized, args.port), handler, audit=audit
    ) as server:
        old_handlers: dict[int, Any] = {}

        def stop_server(_signum: int, _frame: Any) -> None:
            threading.Thread(target=server.shutdown, daemon=True).start()

        for signum in (signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.signal(signum, stop_server)
        try:
            server.serve_forever()
        finally:
            server.server_close()
            audit.finish()
            for signum, old_handler in old_handlers.items():
                signal.signal(signum, old_handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
