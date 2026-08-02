#!/usr/bin/env python3
"""Run frozen verifier-topology probes inside the verifier container."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
from typing import Any


PROXY_ENVIRONMENT_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def _run(
    argv: list[str],
    *,
    environment: dict[str, str],
    timeout: float = 60,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _connect_status(proxy_host: str, proxy_port: int, authority: str) -> str:
    with socket.create_connection((proxy_host, proxy_port), timeout=10) as stream:
        stream.sendall(
            f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode(
                "ascii"
            )
        )
        stream.settimeout(20)
        data = bytearray()
        while b"\r\n\r\n" not in data and len(data) < 16384:
            chunk = stream.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data).split(b"\r\n", 1)[0].decode("ascii", errors="replace")


def _direct_probe(ip: str, port: int) -> dict[str, Any]:
    try:
        with socket.create_connection((ip, port), timeout=3):
            return {"ip": ip, "port": port, "connected": True, "error": None}
    except OSError as exc:
        return {
            "ip": ip,
            "port": port,
            "connected": False,
            "error": type(exc).__name__,
        }


def _write_result(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _fetch(args: argparse.Namespace) -> int:
    saved_proxy = {
        key: os.environ[key]
        for key in PROXY_ENVIRONMENT_KEYS
        if key in os.environ
    }
    for key in PROXY_ENVIRONMENT_KEYS:
        os.environ.pop(key, None)
    direct = [_direct_probe(ip, 443) for ip in args.canonical_ip]
    third_party = _direct_probe(args.third_party_ip, args.third_party_port)
    try:
        resolved = sorted({
            value[4][0]
            for value in socket.getaddrinfo(args.canonical_host, 443)
        })
        dns = {"resolved": True, "addresses": resolved, "error": None}
    except OSError as exc:
        dns = {
            "resolved": False,
            "addresses": [],
            "error": type(exc).__name__,
        }
    proxy_status = _connect_status(
        args.proxy_host, args.proxy_port, args.allowed_authority
    )

    git_environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
        "GIT_SSH_COMMAND": "false",
    }
    git_environment.update(saved_proxy)
    repository = args.output.parent / "objects.git"
    init = _run(
        ["git", "init", "--bare", str(repository)],
        environment=git_environment,
    )
    fetch = _run(
        [
            "git", "-C", str(repository),
            "-c", "credential.helper=",
            "fetch", "--no-tags", args.remote, args.revision,
        ],
        environment=git_environment,
        timeout=120,
    ) if init.returncode == 0 else None
    blob_spec = f"{args.revision}:{args.blob_path}"
    oid = _run(
        ["git", "-C", str(repository), "rev-parse", blob_spec],
        environment=git_environment,
    ) if fetch is not None and fetch.returncode == 0 else None
    content = _run(
        ["git", "-C", str(repository), "cat-file", "blob", blob_spec],
        environment=git_environment,
    ) if oid is not None and oid.returncode == 0 else None
    observed_oid = oid.stdout.decode("ascii", errors="replace").strip() if oid else None
    content_sha256 = hashlib.sha256(content.stdout).hexdigest() if content else None
    result = {
        "probe_schema": "benchaudit-verifier-topology-fetch-probe-v1",
        "proxy_status_line": proxy_status,
        "proxy_environment_restored_only_for_git": sorted(saved_proxy),
        "direct_proxy_environment_cleared": True,
        "direct_canonical_ip_results": direct,
        "direct_third_party_ip_result": third_party,
        "container_dns_result": dns,
        "git_configuration": {
            "new_empty_bare_repository": True,
            "system_config_disabled": True,
            "global_config_path": "/dev/null",
            "credential_helper_cleared": True,
            "terminal_prompt_disabled": True,
            "askpass_disabled": True,
            "ssh_disabled": True,
        },
        "git_init_exit_code": init.returncode,
        "git_fetch_exit_code": fetch.returncode if fetch else None,
        "git_fetch_stderr_sha256": (
            hashlib.sha256(fetch.stderr).hexdigest() if fetch else None
        ),
        "observed_blob_oid": observed_oid,
        "observed_content_sha256": content_sha256,
        "expected_blob_oid": args.expected_blob_oid,
        "expected_content_sha256": args.expected_content_sha256,
    }
    result["gate_results"] = {
        "canonical_proxy_connect_succeeded": proxy_status.startswith("HTTP/1.1 200"),
        "canonical_direct_connections_blocked": all(
            not value["connected"] for value in direct
        ) and bool(direct),
        "third_party_direct_connection_blocked": not third_party["connected"],
        "container_dns_blocked": dns["resolved"] is False,
        "exact_fetch_succeeded": fetch is not None and fetch.returncode == 0,
        "blob_oid_matches": observed_oid == args.expected_blob_oid,
        "blob_content_matches": content_sha256 == args.expected_content_sha256,
    }
    result["all_gates_passed"] = all(result["gate_results"].values())
    _write_result(args.output, result)
    return 0 if result["all_gates_passed"] else 2


def _reject(args: argparse.Namespace) -> int:
    status = _connect_status(
        args.proxy_host, args.proxy_port, args.rejected_authority
    )
    result = {
        "probe_schema": "benchaudit-verifier-topology-rejection-probe-v1",
        "rejected_authority": args.rejected_authority,
        "proxy_status_line": status,
        "gate_results": {
            "live_non_allowlisted_authority_rejected": status.startswith(
                "HTTP/1.1 403"
            )
        },
    }
    result["all_gates_passed"] = all(result["gate_results"].values())
    _write_result(args.output, result)
    return 0 if result["all_gates_passed"] else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("fetch", "reject"), required=True)
    parser.add_argument("--proxy-host", required=True)
    parser.add_argument("--proxy-port", type=int, default=8080)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allowed-authority", default="huggingface.co:443")
    parser.add_argument("--rejected-authority", default="example.com:443")
    parser.add_argument("--canonical-host", default="huggingface.co")
    parser.add_argument("--canonical-ip", action="append", default=[])
    parser.add_argument("--third-party-ip", default="1.1.1.1")
    parser.add_argument("--third-party-port", type=int, default=443)
    parser.add_argument(
        "--remote", default="https://huggingface.co/datasets/codeparrot/apps"
    )
    parser.add_argument(
        "--revision", default="21e74ddf8de1a21436da12e3e653065c5213e9d1"
    )
    parser.add_argument("--blob-path", default="README.md")
    parser.add_argument(
        "--expected-blob-oid", default="6053317a3ea13af4b2490691aff725e21a40268f"
    )
    parser.add_argument(
        "--expected-content-sha256",
        default="bc954bda94e94e9ce92d80ec16d69607444fcdff240cae89df6ca84ff497e846",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    return _fetch(args) if args.mode == "fetch" else _reject(args)


if __name__ == "__main__":
    raise SystemExit(main())
