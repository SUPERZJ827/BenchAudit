#!/usr/bin/env python3
"""Run the frozen, non-evidentiary verifier topology preflight."""
from __future__ import annotations

import argparse
import hashlib
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
    find_container_engine,
)


PLAN = REPO_ROOT / "docs" / "VERIFIER_TOPOLOGY_PREFLIGHT_PLAN_V3_20260802.md"
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


def _engine_identity(engine: str) -> dict[str, Any]:
    name = Path(engine).name
    version = _run([engine, "version", "--format", "json"], check=False)
    if version.returncode != 0:
        version = _run([engine, "version"], check=False)
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
        "selected_executable": engine,
        "engine_name": name,
        "version_output_sha256": hashlib.sha256(version.stdout.encode()).hexdigest(),
        "version_output": version.stdout.strip(),
        "info_subset": info_value,
        "selection_order": ["podman", "docker"],
    }


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
    return {
        "name": name,
        "network_id": result.stdout.strip(),
        "subnet": subnet_prefix + ".0/24",
        "internal": internal,
        "internal_derivation": derivation,
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


def run_preflight(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    engine = find_container_engine()
    if engine is None:
        raise PreflightFailure("container_engine", "no Podman or Docker executable")
    engine_identity = _engine_identity(engine)
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
        "receipt_schema": "benchaudit-verifier-topology-preflight-v3",
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
        }

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
            "network_egress_restricted_to_manifest_authority": (
                internal_value["internal"]
                and all(fetch_summary_gate.values())
                and all(reject_summary_gate.values())
            ),
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
            and all(result["v1_section_3_3"].values())
        )
        result["decision"] = (
            "TOPOLOGY_SATISFIABLE"
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
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    try:
        result = run_preflight(output_dir)
    except PreflightFailure as exc:
        output_dir.mkdir(parents=True, exist_ok=True)
        result = {
            "receipt_schema": "benchaudit-verifier-topology-preflight-v3",
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
            "receipt_schema": "benchaudit-verifier-topology-preflight-v3",
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
    return 0 if result["decision"] == "TOPOLOGY_SATISFIABLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
