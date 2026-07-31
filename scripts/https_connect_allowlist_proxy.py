#!/usr/bin/env python3
"""Minimal CONNECT proxy restricted to one exact HTTPS authority."""
from __future__ import annotations

import argparse
import select
import socket
import socketserver


MAX_HEADER_BYTES = 16 * 1024


class ConnectHandler(socketserver.BaseRequestHandler):
    allowed_authority: str

    def handle(self) -> None:
        self.request.settimeout(10)
        data = bytearray()
        while b"\r\n\r\n" not in data and len(data) < MAX_HEADER_BYTES:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            data.extend(chunk)
        try:
            first_line = bytes(data).split(b"\r\n", 1)[0].decode("ascii")
            method, authority, version = first_line.split(" ")
        except (UnicodeDecodeError, ValueError):
            self.request.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return
        if (
            method != "CONNECT"
            or version not in {"HTTP/1.0", "HTTP/1.1"}
            or authority.casefold() != self.allowed_authority.casefold()
        ):
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
            return
        host, port_text = authority.rsplit(":", 1)
        try:
            upstream = socket.create_connection((host, int(port_text)), timeout=15)
        except OSError:
            self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            return
        with upstream:
            upstream.setblocking(False)
            self.request.setblocking(False)
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            sockets = (self.request, upstream)
            while True:
                readable, _, exceptional = select.select(sockets, (), sockets, 30)
                if exceptional or not readable:
                    return
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


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--allow-authority", required=True)
    args = parser.parse_args()
    handler = type(
        "PinnedConnectHandler",
        (ConnectHandler,),
        {"allowed_authority": args.allow_authority},
    )
    with ThreadingTCPServer((args.listen, args.port), handler) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
