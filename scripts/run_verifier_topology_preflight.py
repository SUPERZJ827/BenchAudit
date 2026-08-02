#!/usr/bin/env python3
"""Run the frozen, non-evidentiary verifier topology preflight."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Any, Sequence
import uuid
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchcore.execution import (  # noqa: E402
    CommandSpec,
    ContainerRunner,
    ExecutionPolicy,
)


PLAN = (
    REPO_ROOT
    / "docs"
    / "VERIFIER_TOPOLOGY_UPSTREAM_CHAIN_CORRECTION_PLAN_20260802.md"
)
PROXY_SCRIPT = REPO_ROOT / "scripts" / "https_connect_allowlist_proxy.py"
PROBE_SCRIPT = REPO_ROOT / "scripts" / "verifier_topology_probe.py"
PINNED_IMAGE = (
    "docker.io/alexgshaw/fix-git@"
    "sha256:61e431c00c58df652287aadce5457634d9f9330cfdd153ebdf2802df0d540119"
)
EXPECTED_IMAGE_DIGEST = "sha256:61e431c00c58df652287aadce5457634d9f9330cfdd153ebdf2802df0d540119"
ALLOWED_AUTHORITY = "huggingface.co:443"
REJECTED_AUTHORITY = "example.com:443"
REMOTE = "https://huggingface.co/datasets/codeparrot/apps"
REVISION = "21e74ddf8de1a21436da12e3e653065c5213e9d1"
BLOB_PATH = "README.md"
EXPECTED_BLOB_OID = "6053317a3ea13af4b2490691aff725e21a40268f"
EXPECTED_CONTENT_SHA256 = "bc954bda94e94e9ce92d80ec16d69607444fcdff240cae89df6ca84ff497e846"
THIRD_PARTY_IP = "1.1.1.1"
ENGINE_PROFILES: dict[str, dict[str, str]] = {
    "podman-3.4.4": {
        "executable": "/usr/bin/podman",
        "engine_name": "podman",
        "client_version": "3.4.4",
        "server_version": "3.4.4",
        "executable_sha256": "02a390253e13563c04bcfe0046f915c10198a5b76c80f9a7bb5b7e880c37255d",
        "version_output_sha256": "6e512fbb1aec411a5f0335731f6409dda03e0a5908f59801c010da04a761cf06",
        "invocation_schema": "podman-cli-3.4-cni-v1",
    },
    "docker-29.4.1": {
        "executable": "/usr/bin/docker",
        "engine_name": "docker",
        "client_version": "29.4.1",
        "server_version": "29.4.1",
        "executable_sha256": "1fc0af13dcb8070408ce2ac4051b76f76ff0c63570bdaeeb6bd5b13b993d0249",
        "version_output_sha256": "7728e85580e079e17edb6b02fe937fe85727034c12a8d017a9efab6567e2733b",
        "invocation_schema": "docker-cli-29.4-v1",
    },
}
UPSTREAM_PROXY_PROFILES: dict[str, dict[str, Any]] = {
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
    },
}


class PreflightFailure(RuntimeError):
    def __init__(self, gate: str, detail: str) -> None:
        super().__init__(f"{gate}: {detail}")
        self.gate = gate
        self.detail = detail


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _run(
    argv: Sequence[str],
    *,
    check: bool = True,
    timeout: float = 120,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        list(argv),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and process.returncode != 0:
        raise PreflightFailure(
            "command_failed",
            f"exit={process.returncode} argv={list(argv)!r} stderr={process.stderr[-1000:]!r}",
        )
    return process


def _engine_identity(profile_id: str) -> dict[str, Any]:
    try:
        profile = ENGINE_PROFILES[profile_id]
    except KeyError as exc:
        raise PreflightFailure("engine_profile", "engine profile is not code-owned") from exc
    engine = profile["executable"]
    path = Path(engine)
    if not path.is_file() or _sha256(path) != profile["executable_sha256"]:
        raise PreflightFailure("engine_executable", "engine executable hash mismatch")
    if profile["engine_name"] == "docker":
        version = _run([engine, "version", "--format", "{{json .}}"], check=False)
    else:
        version = _run([engine, "version", "--format", "json"], check=False)
    if (
        version.returncode != 0
        or hashlib.sha256(version.stdout.encode()).hexdigest()
        != profile["version_output_sha256"]
    ):
        raise PreflightFailure("engine_version", "engine version output mismatch")
    info = _run([engine, "info", "--format", "json"], check=False)
    info_value: dict[str, Any] = {}
    if info.returncode == 0:
        try:
            parsed = json.loads(info.stdout)
            host = parsed.get("host") or parsed.get("Host") or {}
            security = host.get("security") or host.get("Security") or {}
            info_value = {
                "rootless": security.get("rootless"),
                "network_backend": host.get("networkBackend") or host.get("NetworkBackend"),
            }
        except (TypeError, ValueError):
            info_value = {"parse_error": True}
    return {
        "profile_id": profile_id,
        "selected_executable": engine,
        "engine_name": profile["engine_name"],
        "client_version": profile["client_version"],
        "server_version": profile["server_version"],
        "executable_sha256": profile["executable_sha256"],
        "invocation_schema": profile["invocation_schema"],
        "version_output_sha256": hashlib.sha256(version.stdout.encode()).hexdigest(),
        "version_output": version.stdout.strip(),
        "info_subset": info_value,
        "code_owned_profile": True,
    }


def _upstream_proxy_identity(profile_id: str) -> dict[str, Any]:
    try:
        profile = UPSTREAM_PROXY_PROFILES[profile_id]
    except KeyError as exc:
        raise PreflightFailure(
            "upstream_proxy_profile", "upstream proxy profile is not code-owned"
        ) from exc
    binary = Path(profile["binary"])
    unit = Path(profile["unit"])
    if not binary.is_file() or _sha256(binary) != profile["binary_sha256"]:
        raise PreflightFailure("upstream_proxy_binary", "mihomo binary hash mismatch")
    if not unit.is_file() or _sha256(unit) != profile["unit_sha256"]:
        raise PreflightFailure("upstream_proxy_unit", "mihomo unit hash mismatch")
    version = _run([str(binary), "-v"], check=False)
    observed_version = version.stdout.strip().splitlines()[0] if version.stdout else ""
    if version.returncode != 0 or observed_version != profile["version"]:
        raise PreflightFailure("upstream_proxy_version", "mihomo version mismatch")
    properties = _run([
        "systemctl", "show", profile["service"], "--no-pager",
        "--property=MainPID,ActiveState,SubState,ExecMainStartTimestampMonotonic,"
        "ActiveEnterTimestampMonotonic,ExecStart,FragmentPath",
    ])
    values = {}
    for line in properties.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    listener = _run(["ss", "-ltnpe", "( sport = :17890 )"])
    if not _upstream_proxy_observation_matches(
        profile,
        properties=values,
        observed_version=observed_version,
        listener_stdout=listener.stdout,
    ):
        raise PreflightFailure(
            "upstream_proxy_service_identity", "mihomo runtime identity drifted"
        )
    return {
        "profile_id": profile_id,
        "access_endpoint": f"{profile['access_host']}:{profile['port']}",
        "listener_inode": profile["listener_inode"],
        "listener_cgroup": profile["listener_cgroup"],
        "service": profile["service"],
        "main_pid": profile["main_pid"],
        "active_enter_timestamp_monotonic": profile[
            "active_enter_timestamp_monotonic"
        ],
        "exec_main_start_timestamp_monotonic": profile[
            "exec_main_start_timestamp_monotonic"
        ],
        "binary_sha256": profile["binary_sha256"],
        "version": profile["version"],
        "unit_sha256": profile["unit_sha256"],
        "configuration_readable": profile["configuration_readable"],
        "code_owned_profile": True,
    }


def _upstream_proxy_observation_matches(
    profile: dict[str, Any],
    *,
    properties: dict[str, str],
    observed_version: str,
    listener_stdout: str,
) -> bool:
    expected = {
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
    }
    required_listener_fragments = (
        "*:17890",
        f"ino:{profile['listener_inode']}",
        f"cgroup:{profile['listener_cgroup']}",
    )
    return (
        observed_version == profile["version"]
        and all(properties.get(key) == value for key, value in expected.items())
        and profile["exec_start_fragment"] in properties.get("ExecStart", "")
        and all(value in listener_stdout for value in required_listener_fragments)
    )


def _image_identity(engine: str) -> dict[str, Any]:
    process = _run([engine, "image", "inspect", PINNED_IMAGE], check=False)
    if process.returncode != 0:
        raise PreflightFailure("pinned_image_unavailable", process.stderr.strip())
    values = json.loads(process.stdout)
    if len(values) != 1:
        raise PreflightFailure("pinned_image_identity", "image inspect was not singular")
    value = values[0]
    repo_digests = value.get("RepoDigests") or []
    if not any(EXPECTED_IMAGE_DIGEST in item for item in repo_digests):
        raise PreflightFailure(
            "pinned_image_identity",
            f"expected repository digest absent: {repo_digests!r}",
        )
    return {
        "configured_image": PINNED_IMAGE,
        "expected_repository_digest": EXPECTED_IMAGE_DIGEST,
        "image_id": value.get("Id") or value.get("ID"),
        "digest": value.get("Digest"),
        "repo_digests": sorted(repo_digests),
        "inspect_sha256": hashlib.sha256(process.stdout.encode()).hexdigest(),
    }


def _security_args() -> list[str]:
    return [
        "--read-only",
        "--user", "65534:65534",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "128",
        "--memory", "512m",
        "--cpus", "1.0",
        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=192m,mode=1777",
    ]


def _create_network(
    engine: str,
    *,
    name: str,
    subnet_prefix: str,
    internal: bool,
) -> dict[str, Any]:
    argv = [engine, "network", "create"]
    if internal:
        argv.append("--internal")
    argv.extend(["--subnet", subnet_prefix + ".0/24", name])
    result = _run(argv)
    inspect = _run([engine, "network", "inspect", name])
    value = json.loads(inspect.stdout)
    if isinstance(value, list):
        value = value[0]
    observed_internal, derivation = _derive_internal_network(value)
    if bool(observed_internal) is not internal:
        raise PreflightFailure(
            "network_internal_flag",
            f"{name}: expected internal={internal}, got {observed_internal!r}",
        )
    gateways: list[str] = []
    ipam = value.get("IPAM") or value.get("ipam_options") or {}
    configs = ipam.get("Config") or ipam.get("config") or []
    for config in configs:
        gateway = config.get("Gateway") or config.get("gateway")
        if gateway:
            try:
                address = ipaddress.ip_address(gateway)
            except ValueError as exc:
                raise PreflightFailure(
                    "network_gateway", "network gateway was not a literal IPv4 address"
                ) from exc
            if address.version != 4 or address.is_unspecified:
                raise PreflightFailure(
                    "network_gateway", "network gateway was not a usable literal IPv4 address"
                )
            gateways.append(address.compressed)
    if len(set(gateways)) != 1:
        raise PreflightFailure(
            "network_gateway", f"expected one network gateway, got {gateways!r}"
        )
    return {
        "name": name,
        "network_id": result.stdout.strip(),
        "subnet": subnet_prefix + ".0/24",
        "internal": internal,
        "internal_derivation": derivation,
        "gateway": gateways[0],
        "inspect_sha256": hashlib.sha256(inspect.stdout.encode()).hexdigest(),
    }


def _derive_internal_network(value: dict[str, Any]) -> tuple[bool | None, str]:
    """Recognize explicit booleans or the frozen Podman-CNI representation."""

    explicit = value.get("internal")
    if explicit is None:
        explicit = value.get("Internal")
    if isinstance(explicit, bool):
        return explicit, "explicit_internal_boolean"
    plugins = value.get("plugins")
    if not isinstance(plugins, list):
        return None, "unknown_network_inspect_representation"
    bridges = [item for item in plugins if item.get("type") == "bridge"]
    if len(bridges) != 1:
        return None, "podman_cni_bridge_cardinality_invalid"
    bridge = bridges[0]
    plugin_types = {str(item.get("type")) for item in plugins}
    if (
        bridge.get("isGateway") is False
        and bridge.get("ipMasq") in (None, False)
        and "dnsname" not in plugin_types
        and "masq" not in plugin_types
    ):
        return True, "podman_cni_no_gateway_no_masquerade_no_dnsname"
    if bridge.get("isGateway") is True and bridge.get("ipMasq") is True:
        return False, "podman_cni_gateway_with_masquerade"
    return None, "podman_cni_ambiguous"


def _container_networks(engine: str, name: str) -> tuple[set[str], dict[str, Any]]:
    process = _run([engine, "container", "inspect", name])
    values = json.loads(process.stdout)
    value = values[0]
    settings = value.get("NetworkSettings") or {}
    networks = settings.get("Networks") or {}
    return set(networks), {
        "networks": sorted(networks),
        "inspect_sha256": hashlib.sha256(process.stdout.encode()).hexdigest(),
        "user": (value.get("Config") or {}).get("User"),
        "read_only_rootfs": (value.get("HostConfig") or {}).get("ReadonlyRootfs"),
        "mount_destinations": sorted(
            str(item.get("Destination")) for item in (value.get("Mounts") or [])
        ),
    }


def _wait_container(engine: str, name: str) -> int:
    value = _run([engine, "wait", name]).stdout.strip().splitlines()[-1]
    return int(value)


def _stop_proxy(engine: str, name: str) -> int:
    _run([engine, "kill", "--signal", "TERM", name], check=False)
    return _wait_container(engine, name)


def _summary_gate(
    summary: dict[str, Any],
    *,
    expected_authority: str,
    expected_disposition: str,
) -> dict[str, bool]:
    counts = summary.get("disposition_counts", {}).get(expected_authority, {})
    unparsed = summary.get("unparsed_disposition_counts", {})
    if expected_disposition == "allowed":
        cardinality = counts.get("allowed", 0) >= 1
    else:
        cardinality = counts.get("forbidden", 0) == 1 and counts.get("allowed", 0) == 0
    prohibited = {
        key: value
        for key, value in counts.items()
        if key != expected_disposition and value
    }
    return {
        "authority_set_exact": summary.get("parsed_authorities") == [expected_authority],
        "expected_disposition_cardinality": cardinality,
        "no_other_dispositions": not prohibited,
        "no_unparsed_events": sum(unparsed.values()) == 0,
    }


def _start_proxy(
    *,
    engine: str,
    name: str,
    internal_network: str,
    egress_network: str,
    internal_ip: str,
    bundle: Path,
    output: Path,
    session_id: str,
    upstream_profile_id: str,
    upstream_proxy_authority: str,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    os.chmod(output, 0o777)
    _run([
        engine, "create", "--name", name,
        "--network", internal_network,
        "--ip", internal_ip,
        *_security_args(),
        "--mount", f"type=bind,src={bundle},dst=/workspace,readonly",
        "--mount", f"type=bind,src={output},dst=/output",
        PINNED_IMAGE,
        "python3", "/workspace/scripts/https_connect_allowlist_proxy.py",
        "--listen", internal_ip,
        "--port", "8080",
        "--allow-authority", ALLOWED_AUTHORITY,
        "--audit-log", "/output/raw.jsonl",
        "--stable-summary-out", "/output/stable.json",
        "--session-id", session_id,
        "--upstream-profile-id", upstream_profile_id,
        "--upstream-proxy-authority", upstream_proxy_authority,
    ])
    _run([engine, "network", "connect", egress_network, name])
    networks, inspect = _container_networks(engine, name)
    if networks != {internal_network, egress_network}:
        raise PreflightFailure("proxy_network_set", repr(sorted(networks)))
    _run([engine, "start", name])
    time.sleep(0.75)
    state = _run([
        engine, "container", "inspect", name, "--format", "{{.State.Running}}"
    ])
    if state.stdout.strip().casefold() != "true":
        logs = _run([engine, "logs", name], check=False)
        raise PreflightFailure("proxy_start", logs.stderr + logs.stdout)
    return inspect


def _make_proxy_artifacts_readable(engine: str, output: Path) -> dict[str, Any]:
    """Let the artifact owner expose completed logs without host-side rewriting."""

    process = _run([
        engine, "run", "--rm", "--network", "none",
        "--user", "65534:65534",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--read-only",
        "--mount", f"type=bind,src={output},dst=/output",
        PINNED_IMAGE,
        "chmod", "0644", "/output/raw.jsonl", "/output/stable.json",
    ], check=False)
    if process.returncode != 0:
        raise PreflightFailure(
            "proxy_artifact_permissions", process.stderr[-1000:]
        )
    return {
        "performed": True,
        "image": PINNED_IMAGE,
        "user": "65534:65534",
        "network": "none",
        "content_rewritten": False,
    }


def _run_verifier(
    *,
    engine: str,
    name: str,
    internal_network: str,
    verifier_ip: str,
    proxy_ip: str,
    bundle: Path,
    output: Path,
    mode: str,
    canonical_ips: list[str],
) -> tuple[int, dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=False)
    os.chmod(output, 0o777)
    argv = [
        engine, "create", "--name", name,
        "--network", internal_network,
        "--ip", verifier_ip,
        "--dns", "127.0.0.1",
        *_security_args(),
        "--env", f"HTTPS_PROXY=http://{proxy_ip}:8080",
        "--env", f"https_proxy=http://{proxy_ip}:8080",
        "--env", "HTTP_PROXY=",
        "--env", "http_proxy=",
        "--env", "ALL_PROXY=",
        "--env", "all_proxy=",
        "--env", "NO_PROXY=",
        "--env", "no_proxy=",
        "--mount", f"type=bind,src={bundle},dst=/workspace,readonly",
        "--mount", f"type=bind,src={output},dst=/output",
        "--workdir", "/workspace",
        PINNED_IMAGE,
        "python3", "/workspace/scripts/verifier_topology_probe.py",
        "--mode", mode,
        "--proxy-host", proxy_ip,
        "--proxy-port", "8080",
        "--output", "/output/result.json",
    ]
    for value in canonical_ips:
        argv.extend(["--canonical-ip", value])
    _run(argv)
    networks, inspect = _container_networks(engine, name)
    if networks != {internal_network}:
        raise PreflightFailure("verifier_network_set", repr(sorted(networks)))
    _run([engine, "start", name])
    exit_code = _wait_container(engine, name)
    return exit_code, inspect


def _candidate_network_regression(engine: str, scratch: Path) -> dict[str, Any]:
    scratch.mkdir(exist_ok=True)
    runner = ContainerRunner("candidate-fixture", engine=engine)
    argv = runner.build_argv(
        CommandSpec(("python", "-c", "print(1)"), cwd=scratch),
        ExecutionPolicy(),
    )
    pairs = [argv[index:index + 2] for index, value in enumerate(argv) if value == "--network"]
    passed = pairs == [("--network", "none")]
    return {
        "passed": passed,
        "network_arguments": [list(value) for value in pairs],
        "container_runner_modified_by_preflight": False,
    }


def run_preflight(
    output_dir: Path,
    *,
    engine_profile: str,
    upstream_proxy_profile: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    engine_identity = _engine_identity(engine_profile)
    upstream_identity = _upstream_proxy_identity(upstream_proxy_profile)
    engine = engine_identity["selected_executable"]
    image_identity = _image_identity(engine)
    canonical_ips = sorted({
        value[4][0] for value in socket.getaddrinfo("huggingface.co", 443)
    })
    if not canonical_ips:
        raise PreflightFailure("host_dns", "canonical host resolved to no addresses")

    token = uuid.uuid4().hex[:10]
    octet = 32 + (int(token[:2], 16) % 160)
    internal_prefix = f"10.251.{octet}"
    egress_prefix = f"10.252.{octet}"
    internal = f"benchaudit-verifier-internal-{token}"
    egress = f"benchaudit-verifier-egress-{token}"
    proxy_fetch = f"benchaudit-verifier-proxy-fetch-{token}"
    verifier_fetch = f"benchaudit-verifier-fetch-{token}"
    proxy_reject = f"benchaudit-verifier-proxy-reject-{token}"
    verifier_reject = f"benchaudit-verifier-reject-{token}"
    containers: list[str] = []
    networks: list[str] = []
    scratch = Path(tempfile.mkdtemp(prefix="benchaudit-verifier-preflight-"))
    bundle = scratch / "bundle"
    (bundle / "scripts").mkdir(parents=True)
    shutil.copyfile(PROXY_SCRIPT, bundle / "scripts" / PROXY_SCRIPT.name)
    shutil.copyfile(PROBE_SCRIPT, bundle / "scripts" / PROBE_SCRIPT.name)
    os.chmod(bundle, 0o755)
    for path in (bundle / "scripts").iterdir():
        os.chmod(path, 0o644)
    result: dict[str, Any] = {
        "receipt_schema": "benchaudit-verifier-topology-upstream-chain-v1",
        "decision": "NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY",
        "claim_boundary": {
            "topology_only": True,
            "provenance_receipt_produced": False,
            "attestation_produced": False,
            "finding_produced": False,
            "candidate_code_executed": False,
        },
        "frozen_inputs": {
            "remote": REMOTE,
            "revision": REVISION,
            "blob_path": BLOB_PATH,
            "expected_blob_oid": EXPECTED_BLOB_OID,
            "expected_content_sha256": EXPECTED_CONTENT_SHA256,
            "allowed_authority": ALLOWED_AUTHORITY,
            "rejected_authority": REJECTED_AUTHORITY,
            "third_party_direct_ip": THIRD_PARTY_IP,
        },
        "engine": engine_identity,
        "upstream_proxy": upstream_identity,
        "image": image_identity,
        "code_bindings": {
            "plan_sha256": _sha256(PLAN),
            "proxy_script_sha256": _sha256(PROXY_SCRIPT),
            "probe_script_sha256": _sha256(PROBE_SCRIPT),
        },
        "host_resolved_canonical_ips": canonical_ips,
    }
    try:
        networks.append(internal)
        internal_value = _create_network(
            engine, name=internal, subnet_prefix=internal_prefix, internal=True
        )
        networks.append(egress)
        egress_value = _create_network(
            engine, name=egress, subnet_prefix=egress_prefix, internal=False
        )
        upstream_proxy_authority = (
            f"{egress_value['gateway']}:"
            f"{UPSTREAM_PROXY_PROFILES[upstream_proxy_profile]['port']}"
        )
        result["network_mechanism"] = {
            "mechanism_blocking_direct_egress": (
                "verifier attached only to engine-enforced internal network; "
                "dual-homed proxy is sole member with egress network"
            ),
            "internal_network": internal_value,
            "egress_network": egress_value,
            "proxy_listen_text": internal_prefix + ".2",
            "proxy_listen_normalized": internal_prefix + ".2",
            "wildcard_listen": False,
            "host_network": False,
            "upstream_proxy_authority_inside_container": upstream_proxy_authority,
            "upstream_proxy_authority_source": (
                "inspected Docker egress-network gateway plus code-owned port"
            ),
        }
        result["protocol_deviations"] = [{
            "path": "V1 §3.3 / direct canonical-host egress implementation",
            "change": (
                "audited proxy reaches a pinned host HTTP CONNECT proxy"
            ),
            "exact_loss": (
                "packet-level egress terminates first at a host proxy whose "
                "configuration is unreadable; the original direct-egress "
                "mechanism is not preserved"
            ),
            "retained_guards": [
                "exact downstream authority allowlist",
                "no direct fallback",
                "end-to-end TLS",
                "five live probes",
                "candidate network none",
            ],
            "confirmation_eligible": False,
        }]

        containers.append(proxy_fetch)
        fetch_proxy_inspect = _start_proxy(
            engine=engine,
            name=proxy_fetch,
            internal_network=internal,
            egress_network=egress,
            internal_ip=internal_prefix + ".2",
            bundle=bundle,
            output=output_dir / "fetch_proxy",
            session_id="fetch-session",
            upstream_profile_id=upstream_proxy_profile,
            upstream_proxy_authority=upstream_proxy_authority,
        )
        containers.append(verifier_fetch)
        fetch_exit, fetch_verifier_inspect = _run_verifier(
            engine=engine,
            name=verifier_fetch,
            internal_network=internal,
            verifier_ip=internal_prefix + ".3",
            proxy_ip=internal_prefix + ".2",
            bundle=bundle,
            output=output_dir / "fetch_verifier",
            mode="fetch",
            canonical_ips=canonical_ips,
        )
        fetch_proxy_exit = _stop_proxy(engine, proxy_fetch)
        fetch_permission_adjustment = _make_proxy_artifacts_readable(
            engine, output_dir / "fetch_proxy"
        )
        fetch_probe = json.loads(
            (output_dir / "fetch_verifier" / "result.json").read_text()
        )
        fetch_summary = json.loads(
            (output_dir / "fetch_proxy" / "stable.json").read_text()
        )
        fetch_summary_gate = _summary_gate(
            fetch_summary,
            expected_authority=ALLOWED_AUTHORITY,
            expected_disposition="allowed",
        )
        result["fetch_session"] = {
            "verifier_exit_code": fetch_exit,
            "proxy_exit_code": fetch_proxy_exit,
            "proxy_inspect": fetch_proxy_inspect,
            "verifier_inspect": fetch_verifier_inspect,
            "probe": fetch_probe,
            "proxy_stable_summary": fetch_summary,
            "proxy_stable_summary_gate": fetch_summary_gate,
            "artifact_permission_adjustment": fetch_permission_adjustment,
            "raw_log_sha256": _sha256(output_dir / "fetch_proxy" / "raw.jsonl"),
            "stable_summary_sha256": _sha256(output_dir / "fetch_proxy" / "stable.json"),
            "direct_canonical_ip_probe_result": "corroboration_only",
            "direct_third_party_ip_probe_result": "corroboration_only",
            "dns_probe_result": "corroboration_only",
        }

        _run([engine, "rm", proxy_fetch], check=False)
        containers.remove(proxy_fetch)
        containers.append(proxy_reject)
        reject_proxy_inspect = _start_proxy(
            engine=engine,
            name=proxy_reject,
            internal_network=internal,
            egress_network=egress,
            internal_ip=internal_prefix + ".2",
            bundle=bundle,
            output=output_dir / "reject_proxy",
            session_id="reject-session",
            upstream_profile_id=upstream_proxy_profile,
            upstream_proxy_authority=upstream_proxy_authority,
        )
        containers.append(verifier_reject)
        reject_exit, reject_verifier_inspect = _run_verifier(
            engine=engine,
            name=verifier_reject,
            internal_network=internal,
            verifier_ip=internal_prefix + ".4",
            proxy_ip=internal_prefix + ".2",
            bundle=bundle,
            output=output_dir / "reject_verifier",
            mode="reject",
            canonical_ips=[],
        )
        reject_proxy_exit = _stop_proxy(engine, proxy_reject)
        reject_permission_adjustment = _make_proxy_artifacts_readable(
            engine, output_dir / "reject_proxy"
        )
        reject_probe = json.loads(
            (output_dir / "reject_verifier" / "result.json").read_text()
        )
        reject_summary = json.loads(
            (output_dir / "reject_proxy" / "stable.json").read_text()
        )
        reject_summary_gate = _summary_gate(
            reject_summary,
            expected_authority=REJECTED_AUTHORITY,
            expected_disposition="forbidden",
        )
        result["rejection_session"] = {
            "verifier_exit_code": reject_exit,
            "proxy_exit_code": reject_proxy_exit,
            "proxy_inspect": reject_proxy_inspect,
            "verifier_inspect": reject_verifier_inspect,
            "probe": reject_probe,
            "proxy_stable_summary": reject_summary,
            "proxy_stable_summary_gate": reject_summary_gate,
            "artifact_permission_adjustment": reject_permission_adjustment,
            "raw_log_sha256": _sha256(output_dir / "reject_proxy" / "raw.jsonl"),
            "stable_summary_sha256": _sha256(output_dir / "reject_proxy" / "stable.json"),
        }
        candidate = _candidate_network_regression(engine, scratch / "candidate")
        result["candidate_network_regression"] = candidate
        result["v1_section_3_3"] = {
            "digest_pinned_environment": True,
            "no_mounted_git_repository_or_object_cache": True,
            "no_credentials_ssh_agent_or_secrets": True,
            "system_and_global_git_configuration_disabled": fetch_probe[
                "git_configuration"
            ]["system_config_disabled"] and fetch_probe["git_configuration"][
                "global_config_path"
            ] == "/dev/null",
            "application_layer_connect_restricted_to_manifest_authority": (
                internal_value["internal"]
                and all(fetch_summary_gate.values())
                and all(reject_summary_gate.values())
            ),
            "original_direct_egress_mechanism_preserved": False,
            "host_upstream_configuration_verified": False,
        }
        all_gates = (
            fetch_exit == 0
            and fetch_proxy_exit == 0
            and fetch_probe["all_gates_passed"]
            and all(fetch_summary_gate.values())
            and reject_exit == 0
            and reject_proxy_exit == 0
            and reject_probe["all_gates_passed"]
            and all(reject_summary_gate.values())
            and candidate["passed"]
            and result["v1_section_3_3"]["digest_pinned_environment"]
            and result["v1_section_3_3"][
                "no_mounted_git_repository_or_object_cache"
            ]
            and result["v1_section_3_3"]["no_credentials_ssh_agent_or_secrets"]
            and result["v1_section_3_3"][
                "system_and_global_git_configuration_disabled"
            ]
            and result["v1_section_3_3"][
                "application_layer_connect_restricted_to_manifest_authority"
            ]
        )
        result["decision"] = (
            "TOPOLOGY_SATISFIABLE_WITH_UPSTREAM_CHAIN_DEVIATION"
            if all_gates else "NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY"
        )
        result["all_preflight_gates_passed"] = all_gates
        if not all_gates:
            result["first_failing_gate"] = "one_or_more_recorded_topology_gates"
    finally:
        for name in reversed(containers):
            _run([engine, "rm", "-f", name], check=False)
        for name in reversed(networks):
            _run([engine, "network", "rm", name], check=False)
        shutil.rmtree(scratch, ignore_errors=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--engine-profile",
        choices=tuple(sorted(ENGINE_PROFILES)),
        required=True,
    )
    parser.add_argument(
        "--upstream-proxy-profile",
        choices=tuple(sorted(UPSTREAM_PROXY_PROFILES)),
        required=True,
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    try:
        result = run_preflight(
            output_dir,
            engine_profile=args.engine_profile,
            upstream_proxy_profile=args.upstream_proxy_profile,
        )
    except PreflightFailure as exc:
        output_dir.mkdir(parents=True, exist_ok=True)
        result = {
            "receipt_schema": "benchaudit-verifier-topology-upstream-chain-v1",
            "decision": "NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY",
            "first_failing_gate": exc.gate,
            "reason": exc.detail,
            "claim_boundary": {
                "topology_only": True,
                "provenance_receipt_produced": False,
                "attestation_produced": False,
                "finding_produced": False,
                "candidate_code_executed": False,
            },
        }
    except Exception as exc:  # an operational surprise is a fail-closed result
        output_dir.mkdir(parents=True, exist_ok=True)
        result = {
            "receipt_schema": "benchaudit-verifier-topology-upstream-chain-v1",
            "decision": "NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY",
            "first_failing_gate": "unexpected_preflight_error",
            "reason": type(exc).__name__,
            "claim_boundary": {
                "topology_only": True,
                "provenance_receipt_produced": False,
                "attestation_produced": False,
                "finding_produced": False,
                "candidate_code_executed": False,
            },
        }
    receipt = output_dir / "topology_preflight_receipt.json"
    receipt.write_bytes(_canonical_bytes(result) + b"\n")
    print(json.dumps({
        "decision": result["decision"],
        "first_failing_gate": result.get("first_failing_gate"),
        "receipt": str(receipt),
    }, ensure_ascii=False, sort_keys=True))
    return (
        0
        if result["decision"]
        == "TOPOLOGY_SATISFIABLE_WITH_UPSTREAM_CHAIN_DEVIATION"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
