#!/usr/bin/env python3
"""Run two Phase-2A verifier replays inside a pinned, restricted boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PINNED_IMAGE = (
    "alexgshaw/fix-git:20251031@"
    "sha256:61e431c00c58df652287aadce5457634d9f9330cfdd153ebdf2802df0d540119"
)
ALLOWED_AUTHORITY = "huggingface.co:443"


class BoundaryFailure(RuntimeError):
    pass


def _run(argv: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        list(argv),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        raise BoundaryFailure(
            f"command failed ({proc.returncode}): {' '.join(argv)}\n{proc.stderr}"
        )
    return proc


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _container_security_args() -> list[str]:
    return [
        "--read-only",
        "--user", "65534:65534",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--pids-limit", "128",
        "--memory", "512m",
        "--cpus", "1.0",
        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=192m,mode=1777",
    ]


def _inspect_container(name: str, *, expected_networks: set[str]) -> dict[str, Any]:
    value = json.loads(_run(["docker", "inspect", name]).stdout)[0]
    host = value["HostConfig"]
    networks = set(value["NetworkSettings"]["Networks"])
    mounts = value.get("Mounts") or []
    if value["Config"].get("User") != "65534:65534":
        raise BoundaryFailure(f"{name}: container is not non-root")
    if host.get("ReadonlyRootfs") is not True:
        raise BoundaryFailure(f"{name}: root filesystem is not read-only")
    if set(host.get("CapDrop") or []) != {"ALL"}:
        raise BoundaryFailure(f"{name}: Linux capabilities were not all dropped")
    if "no-new-privileges:true" not in set(host.get("SecurityOpt") or []):
        raise BoundaryFailure(f"{name}: no-new-privileges is absent")
    if networks != expected_networks:
        raise BoundaryFailure(f"{name}: unexpected network set {networks}")
    if any("docker.sock" in str(mount.get("Source") or "") for mount in mounts):
        raise BoundaryFailure(f"{name}: Docker socket was mounted")
    return {
        "container_user": value["Config"]["User"],
        "read_only_rootfs": host["ReadonlyRootfs"],
        "cap_drop": sorted(host.get("CapDrop") or []),
        "security_opt": sorted(host.get("SecurityOpt") or []),
        "pids_limit": host.get("PidsLimit"),
        "memory_bytes": host.get("Memory"),
        "nano_cpus": host.get("NanoCpus"),
        "networks": sorted(networks),
        "mounts": [
            {
                "destination": mount.get("Destination"),
                "rw": mount.get("RW"),
                "type": mount.get("Type"),
            }
            for mount in mounts
        ],
    }


def _image_identity() -> dict[str, Any]:
    values = json.loads(_run(["docker", "image", "inspect", PINNED_IMAGE]).stdout)
    if len(values) != 1:
        raise BoundaryFailure("pinned image is unavailable")
    repo_digests = values[0].get("RepoDigests") or []
    expected_digest = PINNED_IMAGE.split("@", 1)[1]
    if not any(digest.endswith("@" + expected_digest) for digest in repo_digests):
        raise BoundaryFailure("local image does not carry the pinned repository digest")
    return {
        "configured_image": PINNED_IMAGE,
        "image_id": values[0]["Id"],
        "repo_digests": sorted(repo_digests),
    }


def run_replays(receipt: Path, output_dir: Path, runs: int) -> dict[str, Any]:
    if runs != 2:
        raise BoundaryFailure("V2 protocol requires exactly two independent replays")
    output_dir.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="benchaudit-ee-v2-"))
    os.chmod(scratch, 0o777)
    bundle = scratch / "execution-bundle"
    (bundle / "scripts").mkdir(parents=True)
    (bundle / "configs").mkdir()
    (bundle / "benchcore").mkdir()
    shutil.copyfile(
        REPO_ROOT / "scripts" / "external_evidence_git_verifier.py",
        bundle / "scripts" / "external_evidence_git_verifier.py",
    )
    shutil.copyfile(
        REPO_ROOT / "scripts" / "https_connect_allowlist_proxy.py",
        bundle / "scripts" / "https_connect_allowlist_proxy.py",
    )
    shutil.copyfile(
        REPO_ROOT / "configs" / "external_evidence_trusted_sources_v1.json",
        bundle / "configs" / "external_evidence_trusted_sources_v1.json",
    )
    shutil.copyfile(REPO_ROOT / "benchcore" / "__init__.py", bundle / "benchcore" / "__init__.py")
    shutil.copyfile(
        REPO_ROOT / "benchcore" / "external_evidence.py",
        bundle / "benchcore" / "external_evidence.py",
    )
    shutil.copyfile(receipt, bundle / "receipt.json")
    os.chmod(bundle, 0o755)
    bundle_hashes = {
        str(path.relative_to(bundle)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(bundle.rglob("*"))
        if path.is_file()
    }
    token = uuid.uuid4().hex[:12]
    internal = f"benchaudit-ee-internal-{token}"
    egress = f"benchaudit-ee-egress-{token}"
    proxy = f"benchaudit-ee-proxy-{token}"
    created_containers: list[str] = []
    created_networks: list[str] = []
    image = _image_identity()
    run_receipts: list[dict[str, Any]] = []
    try:
        _run(["docker", "network", "create", "--internal", internal])
        created_networks.append(internal)
        _run(["docker", "network", "create", egress])
        created_networks.append(egress)
        _run([
            "docker", "create", "--name", proxy,
            "--network", egress,
            *_container_security_args(),
            "--mount", f"type=bind,src={bundle},dst=/workspace,readonly",
            PINNED_IMAGE,
            "python3", "/workspace/scripts/https_connect_allowlist_proxy.py",
            "--allow-authority", ALLOWED_AUTHORITY,
        ])
        created_containers.append(proxy)
        _run(["docker", "network", "connect", internal, proxy])
        _run(["docker", "start", proxy])
        time.sleep(0.5)
        proxy_inspect = _inspect_container(
            proxy, expected_networks={internal, egress}
        )
        for index in range(1, runs + 1):
            run_dir = scratch / f"run-{index}"
            run_dir.mkdir(mode=0o777)
            os.chmod(run_dir, 0o777)
            name = f"benchaudit-ee-verifier-{token}-{index}"
            _run([
                "docker", "create", "--name", name,
                "--network", internal,
                *_container_security_args(),
                "--env", "HTTPS_PROXY=http://" + proxy + ":8080",
                "--env", "https_proxy=http://" + proxy + ":8080",
                "--env", "NO_PROXY=",
                "--env", "no_proxy=",
                "--mount", f"type=bind,src={bundle},dst=/workspace,readonly",
                "--mount", f"type=bind,src={run_dir},dst=/output",
                "--workdir", "/workspace",
                PINNED_IMAGE,
                "python3", "/workspace/scripts/external_evidence_git_verifier.py",
                "--receipt", "/workspace/receipt.json",
                "--raw-out", "/output/raw.json",
                "--stable-out", "/output/stable.json",
            ])
            created_containers.append(name)
            verifier_inspect = _inspect_container(
                name, expected_networks={internal}
            )
            _run(["docker", "start", name])
            wait = json.loads(_run(["docker", "wait", name]).stdout)
            if int(wait) != 0:
                logs = _run(["docker", "logs", name], check=False)
                raise BoundaryFailure(
                    f"verifier replay {index} failed: {logs.stdout}\n{logs.stderr}"
                )
            stable = json.loads((run_dir / "stable.json").read_text(encoding="utf-8"))
            raw = json.loads((run_dir / "raw.json").read_text(encoding="utf-8"))
            run_receipts.append({
                "run": index,
                "stable_summary_sha256": _canonical_hash(stable),
                "raw_transcript_sha256": hashlib.sha256(
                    (run_dir / "raw.json").read_bytes()
                ).hexdigest(),
                "new_empty_object_database": True,
                "verifier_container": verifier_inspect,
                "stable": stable,
                "raw": raw,
            })
        stable_hashes = {run["stable_summary_sha256"] for run in run_receipts}
        result = {
            "receipt_schema": "benchaudit-external-evidence-git-verifier-v2-runs",
            "decision": (
                "PASS_VERIFIER_NOT_ACTIVATED"
                if len(stable_hashes) == 1 else "FAIL"
            ),
            "image": image,
            "execution_bundle_file_sha256": bundle_hashes,
            "network_boundary": {
                "verifier_network_internal": True,
                "verifier_has_only_internal_network": True,
                "proxy_allowed_authority": ALLOWED_AUTHORITY,
                "proxy_container": proxy_inspect,
                "direct_verifier_egress": False,
            },
            "runs": run_receipts,
            "stable_summaries_identical": len(stable_hashes) == 1,
            "stable_summary_sha256": next(iter(stable_hashes)) if len(stable_hashes) == 1 else None,
        }
        for index, run in enumerate(run_receipts, 1):
            shutil.copyfile(scratch / f"run-{index}" / "raw.json", output_dir / f"run_{index}_raw.json")
            shutil.copyfile(scratch / f"run-{index}" / "stable.json", output_dir / f"run_{index}_stable.json")
        return result
    finally:
        for name in reversed(created_containers):
            _run(["docker", "rm", "-f", name], check=False)
        for name in reversed(created_networks):
            _run(["docker", "network", "rm", name], check=False)
        shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()
    try:
        result = run_replays(args.receipt.resolve(), args.output_dir.resolve(), args.runs)
    except BoundaryFailure as exc:
        result = {
            "receipt_schema": "benchaudit-external-evidence-git-verifier-v2-runs",
            "decision": "NOT_IDENTIFIABLE_PRODUCTION_VERIFIER",
            "reason": str(exc),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "execution_receipt.json").write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, sort_keys=True))
        return 2
    (args.output_dir / "execution_receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "decision": result["decision"],
        "stable_summary_sha256": result["stable_summary_sha256"],
    }, sort_keys=True))
    return 0 if result["decision"] == "PASS_VERIFIER_NOT_ACTIVATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
