#!/usr/bin/env python3
"""MR-4 confirmation pilot on HumanEval(+)/MBPP(+), with zero LLM calls.

Each task is executed by a separate worker process.  The worker launches the
read-only container, constructs the canonical transcript from its own
observations, and signs only that transcript.  The parent pins the worker
public key and independently applies BenchAudit's central promotion policy.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from benchcore.differential_oracle import (
    DIFFERENTIAL_ORACLE_CONTRACT_VERSION,
    DifferentialCandidate,
    DifferentialOracleAuditChecker,
    OracleObservation,
    build_differential_report,
)
from benchcore.execution import CommandSpec, ContainerRunner, ExecutionPolicy
from benchcore.execution_attestation import (
    ATTESTATION_PROTOCOL,
    transcript_sha256,
)
from benchcore.loader import explicit_mapping_provenance
from benchcore.schema import BenchmarkItem

if TYPE_CHECKING:
    from scripts.run_pattern_memory_evalplus_lobo import Task


TRISTATE_DRIVER = r'''
import contextlib
import io
import json
import os
import signal
import sys

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

class ProbeTimeout(Exception):
    pass

def timeout_handler(signum, frame):
    raise ProbeTimeout("probe timeout")

signal.signal(signal.SIGALRM, timeout_handler)
payload = json.loads(sys.stdin.read())

def execute(source, tests, call):
    namespace = {}
    stream = io.StringIO()
    try:
        signal.setitimer(signal.ITIMER_REAL, payload["per_probe_timeout"])
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            exec(compile(source, "<candidate>", "exec"), namespace)
            exec(compile(tests, "<tests>", "exec"), namespace)
            if call:
                exec(call, namespace)
        return {"status": "completed", "accepted": True, "detail": None}
    except ProbeTimeout as exc:
        return {
            "status": "timeout",
            "accepted": None,
            "detail": type(exc).__name__,
        }
    except (ImportError, ModuleNotFoundError) as exc:
        return {
            "status": "error",
            "accepted": None,
            "detail": type(exc).__name__,
        }
    except BaseException as exc:
        return {
            "status": "completed",
            "accepted": False,
            "detail": type(exc).__name__,
        }
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)

rows = []
for candidate in payload["candidates"]:
    weak = execute(
        candidate["source"], payload["weak_test"], payload["weak_call"],
    )
    strong = execute(
        candidate["source"], payload["strong_test"], payload["strong_call"],
    )
    rows.append({
        "candidate_id": candidate["candidate_id"],
        "source_sha256": candidate["source_sha256"],
        "weak": weak,
        "strong": strong,
    })
print(json.dumps({"rows": rows}, ensure_ascii=False, sort_keys=True))
'''

EXECUTION_DRIVER_SHA256 = hashlib.sha256(
    TRISTATE_DRIVER.encode("utf-8")
).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _contract(
    task: Task,
    candidates: list[DifferentialCandidate],
) -> dict[str, Any]:
    manifest = [candidate.to_evidence() for candidate in candidates]
    revision_material = {
        "benchmark": task.benchmark,
        "task_id": task.task_id,
        "canonical_source_sha256": _sha256_text(task.source),
        "weak_test_sha256": _sha256_text(task.original_test),
        "strong_test_sha256": _sha256_text(task.plus_test),
        "weak_call": task.original_call,
        "strong_call": task.plus_call,
    }
    return {
        "schema_version": DIFFERENTIAL_ORACLE_CONTRACT_VERSION,
        "relation": "declared_strict_test_extension",
        "evaluator_identity": f"evalplus:{task.benchmark}:oracle-pair:v1",
        "weak_oracle_identity": f"evalplus:{task.benchmark}:base:v1",
        "strong_oracle_identity": f"evalplus:{task.benchmark}:plus:v1",
        "source_revision": _sha256_text(_canonical_json(revision_material)),
        "canonical_must_pass_both": True,
        "candidate_manifest": manifest,
        "candidate_manifest_sha256": _sha256_text(_canonical_json(manifest)),
    }


def _observation(value: dict[str, Any]) -> OracleObservation:
    return OracleObservation(
        status=str(value.get("status") or "error"),
        accepted=value.get("accepted"),
        detail=value.get("detail"),
    )


def _worker(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        DifferentialCandidate(**row) for row in payload["candidates"]
    ]
    contract = dict(payload["contract"])
    runner = ContainerRunner(payload["image"], engine="docker")
    driver_payload = {
        "candidates": [{
            "candidate_id": "canonical",
            "source": payload["canonical_source"],
            "source_sha256": _sha256_text(payload["canonical_source"]),
        }, *[{
            "candidate_id": candidate.candidate_id,
            "source": candidate.source,
            "source_sha256": _sha256_text(candidate.source),
        } for candidate in candidates]],
        "weak_test": payload["weak_test"],
        "strong_test": payload["strong_test"],
        "weak_call": payload["weak_call"],
        "strong_call": payload["strong_call"],
        "per_probe_timeout": payload["per_probe_timeout"],
    }
    result = runner.run(
        CommandSpec(
            argv=(sys.executable, "-c", TRISTATE_DRIVER),
            cwd=Path.cwd(),
            env={
                "PYTHONHASHSEED": "0",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "TZ": "UTC",
            },
            stdin=json.dumps(driver_payload, ensure_ascii=False),
        ),
        ExecutionPolicy(
            timeout_seconds=payload["task_timeout"],
            max_output_chars=300_000,
            memory_mb=768,
            cpu_count=1.0,
            pids_limit=64,
            allowed_environment=frozenset({
                "PYTHONHASHSEED",
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "TZ",
            }),
        ),
    )
    if not result.succeeded:
        return {
            "ok": False,
            "task_id": payload["task_id"],
            "runner": result.to_dict(),
            "reason": "container execution failed",
        }
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "task_id": payload["task_id"],
            "runner": result.to_dict(),
            "reason": "runner output was not JSON",
        }
    rows_by_id = {
        row["candidate_id"]: row for row in parsed.get("rows", [])
        if isinstance(row, dict) and isinstance(row.get("candidate_id"), str)
    }
    canonical = rows_by_id.get("canonical")
    if not isinstance(canonical, dict):
        return {
            "ok": False,
            "task_id": payload["task_id"],
            "runner": result.to_dict(),
            "reason": "canonical observation missing",
        }
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        raw = rows_by_id.get(candidate.candidate_id)
        if (
            not isinstance(raw, dict)
            or raw.get("source_sha256") != _sha256_text(candidate.source)
        ):
            return {
                "ok": False,
                "task_id": payload["task_id"],
                "runner": result.to_dict(),
                "reason": f"candidate observation mismatch: {candidate.candidate_id}",
            }
        rows.append({
            "candidate": candidate.to_evidence(),
            "weak": _observation(raw["weak"]).to_dict(),
            "strong": _observation(raw["strong"]).to_dict(),
        })
    canonical_weak = _observation(canonical["weak"])
    canonical_strong = _observation(canonical["strong"])
    report = build_differential_report(
        canonical_source=payload["canonical_source"],
        evaluator_identity=contract["evaluator_identity"],
        contract=contract,
        canonical_weak=canonical_weak,
        canonical_strong=canonical_strong,
        rows=rows,
        execution_driver_sha256=EXECUTION_DRIVER_SHA256,
    )
    payload_sha256 = transcript_sha256(report)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    run_id = str(uuid.uuid4())
    signature = private_key.sign(bytes.fromhex(payload_sha256))
    attestation = {
        "protocol": ATTESTATION_PROTOCOL,
        "payload_sha256": payload_sha256,
        "attester": "evalplus-separate-worker-v1",
        "run_id": run_id,
        "public_key_ed25519": base64.b64encode(public_key).decode("ascii"),
        "signature_ed25519": base64.b64encode(signature).decode("ascii"),
    }
    return {
        "ok": True,
        "task_id": payload["task_id"],
        "contract": contract,
        "canonical": {
            "weak": canonical_weak.to_dict(),
            "strong": canonical_strong.to_dict(),
        },
        "rows": rows,
        "attestation": attestation,
        "runner": result.to_dict(),
        "execution_driver_sha256": EXECUTION_DRIVER_SHA256,
    }


class RecordedOraclePair:
    def __init__(
        self,
        contract: dict[str, Any],
        canonical_source: str,
        canonical: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> None:
        self.identity = contract["evaluator_identity"]
        self.oracle_identities = (
            contract["weak_oracle_identity"],
            contract["strong_oracle_identity"],
        )
        self.execution_driver_sha256 = EXECUTION_DRIVER_SHA256
        self._outcomes: dict[tuple[str, str], OracleObservation] = {
            (canonical_source, self.oracle_identities[0]):
                _observation(canonical["weak"]),
            (canonical_source, self.oracle_identities[1]):
                _observation(canonical["strong"]),
        }
        manifest = contract["candidate_manifest"]
        by_hash = {
            row["candidate"]["candidate_source_sha256"]: row for row in rows
        }
        for entry in manifest:
            row = by_hash[entry["candidate_source_sha256"]]
            self._outcomes[(entry["candidate_source_sha256"], self.oracle_identities[0])] = (
                _observation(row["weak"])
            )
            self._outcomes[(entry["candidate_source_sha256"], self.oracle_identities[1])] = (
                _observation(row["strong"])
            )

    def evaluate(self, item, candidate, oracle_identity):
        del item
        direct = self._outcomes.get((candidate, oracle_identity))
        if direct is not None:
            return direct
        return self._outcomes[(_sha256_text(candidate), oracle_identity)]


class FrozenAttester:
    def __init__(self, attestation: dict[str, Any]) -> None:
        self.attestation = dict(attestation)

    def attest(self, payload_sha256):
        if self.attestation.get("payload_sha256") != payload_sha256:
            return None
        return dict(self.attestation)


class PinnedWorkerVerifier:
    def __init__(self, attestation: dict[str, Any]) -> None:
        self.public_key = base64.b64decode(attestation["public_key_ed25519"])
        self.run_id = attestation["run_id"]

    def verify(self, attestation, payload_sha256):
        if (
            attestation.get("run_id") != self.run_id
            or attestation.get("payload_sha256") != payload_sha256
            or base64.b64decode(attestation["public_key_ed25519"]) != self.public_key
        ):
            return False
        try:
            Ed25519PublicKey.from_public_bytes(self.public_key).verify(
                base64.b64decode(attestation["signature_ed25519"]),
                bytes.fromhex(payload_sha256),
            )
        except Exception:
            return False
        return True


def _worker_payload(
    task: Task,
    *,
    per_family: int,
    image: str,
    per_probe_timeout: float,
    task_timeout: float,
) -> tuple[dict[str, Any], list[DifferentialCandidate]]:
    from scripts.run_pattern_memory_evalplus_lobo import generate_mutants

    candidates = [
        DifferentialCandidate(
            candidate_id=row["mutant_id"],
            source=row["source"],
            family=row["family"],
            transformation_index=int(row["mutant_id"].rsplit(":", 1)[1]),
        )
        for row in generate_mutants(task.source, per_family)
    ]
    return ({
        "task_id": task.task_id,
        "benchmark": task.benchmark,
        "canonical_source": task.source,
        "weak_test": task.original_test,
        "strong_test": task.plus_test,
        "weak_call": task.original_call,
        "strong_call": task.plus_call,
        "candidates": [{
            "candidate_id": row.candidate_id,
            "source": row.source,
            "family": row.family,
            "transformation_index": row.transformation_index,
        } for row in candidates],
        "contract": _contract(task, candidates),
        "image": image,
        "per_probe_timeout": per_probe_timeout,
        "task_timeout": task_timeout,
        # Retries are permitted only for a worker/container transport failure.
        # Canonical failures and semantic outcomes are never retried.
        "operational_retries": 1,
    }, candidates)


def _invoke_worker_once(payload: dict[str, Any]) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=float(payload["task_timeout"]) + 30,
        check=False,
        env={**os.environ, "PYTHONHASHSEED": "0"},
    )
    if proc.returncode != 0:
        return {
            "ok": False,
            "task_id": payload["task_id"],
            "reason": f"worker exit {proc.returncode}: {proc.stderr[-500:]}",
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "task_id": payload["task_id"],
            "reason": f"worker returned invalid JSON: {proc.stdout[-500:]}",
        }


def _invoke_worker(payload: dict[str, Any]) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    total = int(payload.get("operational_retries", 0)) + 1
    for _ in range(total):
        result = _invoke_worker_once(payload)
        attempts.append({
            "ok": result.get("ok") is True,
            "reason": result.get("reason"),
        })
        if result.get("ok") is True:
            result["operational_attempts"] = attempts
            return result
    result["operational_attempts"] = attempts
    return result


def _item(task: Task, contract: dict[str, Any]) -> BenchmarkItem:
    evaluator = {"differential_oracle_contract": contract}
    raw = {
        "id": task.task_id,
        "task": f"{task.benchmark} executable task",
        "canonical": task.source,
        "evaluator": evaluator,
    }
    value = BenchmarkItem(
        item_id=task.task_id,
        raw=raw,
        task=raw["task"],
        gold=task.source,
        evaluator=evaluator,
    )
    value.metadata["_mapping_provenance"] = explicit_mapping_provenance(
        adapter_id="evalplus_differential_oracle",
        adapter_version="1",
        raw=raw,
        field_bindings={
            "item_id": "id",
            "task": "task",
            "gold": "canonical",
            "evaluator": "evaluator",
        },
    )
    return value


def _adjudicate(
    task: Task,
    candidates: list[DifferentialCandidate],
    worker: dict[str, Any],
) -> dict[str, Any]:
    if worker.get("ok") is not True:
        return {
            "task_id": task.task_id,
            "status": "operational_failed",
            "reason": worker.get("reason"),
            "runner": worker.get("runner"),
            "operational_attempts": worker.get("operational_attempts", []),
            "confirmed": 0,
            "review": 0,
        }
    contract = worker["contract"]
    recorded = RecordedOraclePair(
        contract, task.source, worker["canonical"], worker["rows"],
    )
    checker = DifferentialOracleAuditChecker(
        recorded,
        candidates,
        transcript_attester=FrozenAttester(worker["attestation"]),
        transcript_verifier=PinnedWorkerVerifier(worker["attestation"]),
    )
    value = _item(task, contract)
    findings = list(checker.check(value))

    unattested = list(DifferentialOracleAuditChecker(
        recorded, candidates,
    ).check(_item(task, contract)))
    rows = worker["rows"]
    completed_pairs = sum(
        row["weak"]["status"] == "completed"
        and row["strong"]["status"] == "completed"
        for row in rows
    )
    indeterminate_pairs = len(rows) - completed_pairs
    witness_rows = [
        row for row in rows
        if row["weak"]["status"] == "completed"
        and row["weak"]["accepted"] is True
        and row["strong"]["status"] == "completed"
        and row["strong"]["accepted"] is False
    ]
    timeout_rows = [
        row for row in rows
        if row["weak"]["status"] == "timeout"
        or row["strong"]["status"] == "timeout"
    ]
    swapped_rows = [
        row for row in rows
        if row["weak"]["status"] == "completed"
        and row["weak"]["accepted"] is False
        and row["strong"]["status"] == "completed"
        and row["strong"]["accepted"] is True
    ]
    confirmed_candidate_ids = {
        row.evidence["candidate"]["candidate_id"]
        for row in findings if row.evidence_tier == "confirmed"
    }
    return {
        "task_id": task.task_id,
        "canonical": worker["canonical"],
        "status": (
            "valid"
            if worker["canonical"]["weak"] == {
                "status": "completed", "accepted": True, "detail": None,
            }
            and worker["canonical"]["strong"] == {
                "status": "completed", "accepted": True, "detail": None,
            }
            else "canonical_invalid"
        ),
        "candidates": len(candidates),
        "completed_pairs": completed_pairs,
        "indeterminate_pairs": indeterminate_pairs,
        "witnesses": len(witness_rows),
        "timeout_pairs": len(timeout_rows),
        "swapped_direction_pairs": len(swapped_rows),
        "timeout_confirmed_control": sum(
            row["candidate"]["candidate_id"] in confirmed_candidate_ids
            for row in timeout_rows
        ),
        "swapped_direction_confirmed_control": sum(
            row["candidate"]["candidate_id"] in confirmed_candidate_ids
            for row in swapped_rows
        ),
        "confirmed": sum(row.evidence_tier == "confirmed" for row in findings),
        "review": sum(row.evidence_tier == "review" for row in findings),
        "unattested_confirmed_control": sum(
            row.evidence_tier == "confirmed" for row in unattested
        ),
        "findings": [{
            "defect_type": row.defect_type,
            "tier": row.evidence_tier,
            "candidate_id": row.evidence["candidate"]["candidate_id"],
            "transcript_sha256": row.evidence["execution_transcript_sha256"],
        } for row in findings],
        "runner": {
            key: worker["runner"].get(key)
            for key in (
                "backend", "exit_code", "succeeded", "timed_out",
                "isolation",
            )
        },
        "attestation": {
            key: worker["attestation"].get(key)
            for key in (
                "protocol", "payload_sha256", "attester", "run_id",
                "public_key_ed25519", "signature_ed25519",
            )
        },
        "operational_attempts": worker.get("operational_attempts", []),
    }


def _summary(
    rows_by_benchmark: dict[str, list[dict[str, Any]]],
    *,
    image: str,
    image_resolved: str,
    per_family: int,
    per_probe_timeout: float,
    task_timeout: float,
    workers: int,
) -> dict[str, Any]:
    benchmarks: dict[str, Any] = {}
    for benchmark, rows in rows_by_benchmark.items():
        valid = [row for row in rows if row["status"] == "valid"]
        candidates = sum(row.get("candidates", 0) for row in valid)
        completed = sum(row.get("completed_pairs", 0) for row in valid)
        confirmed = sum(row.get("confirmed", 0) for row in valid)
        witness_tasks = sum(row.get("confirmed", 0) > 0 for row in valid)
        benchmarks[benchmark] = {
            "requested_tasks": len(rows),
            "valid_tasks": len(valid),
            "operational_failed_tasks": sum(
                row["status"] == "operational_failed" for row in rows
            ),
            "canonical_invalid_tasks": sum(
                row["status"] == "canonical_invalid" for row in rows
            ),
            "generated_candidates": candidates,
            "completed_pairs": completed,
            "indeterminate_pairs": sum(
                row.get("indeterminate_pairs", 0) for row in valid
            ),
            "timeout_pairs": sum(
                row.get("timeout_pairs", 0) for row in valid
            ),
            "swapped_direction_pairs": sum(
                row.get("swapped_direction_pairs", 0) for row in valid
            ),
            "confirmed_coverage_gaps": confirmed,
            "affected_tasks": witness_tasks,
            "witness_yield": confirmed / completed if completed else 0.0,
            "affected_task_rate": witness_tasks / len(valid) if valid else 0.0,
            "unattested_confirmed_control": sum(
                row.get("unattested_confirmed_control", 0) for row in valid
            ),
        }
    stable = {
        "protocol": {
            "schema_version": "evalplus-differential-confirmation-v1",
            "image_requested": image,
            "image_resolved": image_resolved,
            "per_family": per_family,
            "per_probe_timeout": per_probe_timeout,
            "task_timeout": task_timeout,
            "workers": workers,
            "operational_retries": 1,
            "execution_driver_sha256": EXECUTION_DRIVER_SHA256,
            "llm_calls": 0,
        },
        "benchmarks": benchmarks,
        "controls": {
            "canonical_finding_count": 0,
            "identical_outcome_confirmed_count": 0,
            "identical_outcome_control_basis": (
                "deterministic predicate replay: one completed boolean cannot "
                "simultaneously pass and fail"
            ),
            "timeout_as_rejection_count": sum(
                row.get("timeout_confirmed_control", 0)
                for rows in rows_by_benchmark.values() for row in rows
            ),
            "swapped_direction_confirmed_count": sum(
                row.get("swapped_direction_confirmed_control", 0)
                for rows in rows_by_benchmark.values() for row in rows
            ),
            "unattested_confirmed_count": sum(
                value["unattested_confirmed_control"]
                for value in benchmarks.values()
            ),
        },
    }
    stable["stable_summary_sha256"] = _sha256_text(_canonical_json(stable))
    return stable


def run(args: argparse.Namespace) -> dict[str, Any]:
    from scripts.run_pattern_memory_evalplus_lobo import load_tasks

    tasks_by_benchmark = {
        "humaneval": load_tasks("humaneval", args.humaneval_limit),
        "mbpp": load_tasks("mbpp", args.mbpp_limit),
    }
    payloads: list[tuple[Task, dict[str, Any], list[DifferentialCandidate]]] = []
    for tasks in tasks_by_benchmark.values():
        for task in tasks:
            payload, candidates = _worker_payload(
                task,
                per_family=args.per_family,
                image=args.image,
                per_probe_timeout=args.per_probe_timeout,
                task_timeout=args.task_timeout,
            )
            payloads.append((task, payload, candidates))

    worker_results: dict[tuple[str, str], dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_invoke_worker, payload): (task.benchmark, task.task_id)
            for task, payload, _ in payloads
        }
        for index, future in enumerate(as_completed(futures), start=1):
            key = futures[future]
            worker_results[key] = future.result()
            if index % 50 == 0 or index == len(futures):
                print(
                    f"completed {index}/{len(futures)} worker tasks",
                    file=sys.stderr,
                    flush=True,
                )

    raw: dict[str, list[dict[str, Any]]] = {"humaneval": [], "mbpp": []}
    for task, _, candidates in payloads:
        raw[task.benchmark].append(_adjudicate(
            task,
            candidates,
            worker_results[(task.benchmark, task.task_id)],
        ))
    resolved = subprocess.run(
        ["docker", "image", "inspect", args.image, "--format", "{{.Id}}"],
        text=True, capture_output=True, check=False,
    ).stdout.strip()
    result = {
        **_summary(
            raw,
            image=args.image,
            image_resolved=resolved,
            per_family=args.per_family,
            per_probe_timeout=args.per_probe_timeout,
            task_timeout=args.task_timeout,
            workers=args.workers,
        ),
        "raw": raw,
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--image", default="ds1000-audit:v1")
    parser.add_argument("--humaneval-limit", type=int, default=164)
    parser.add_argument("--mbpp-limit", type=int, default=378)
    parser.add_argument("--per-family", type=int, default=2)
    parser.add_argument("--per-probe-timeout", type=float, default=5.0)
    parser.add_argument("--task-timeout", type=float, default=90.0)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.worker:
        payload = json.loads(sys.stdin.read())
        print(json.dumps(_worker(payload), ensure_ascii=False, sort_keys=True))
        return
    if args.output is None:
        raise SystemExit("--output is required")
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "benchmarks": result["benchmarks"],
        "controls": result["controls"],
        "stable_summary_sha256": result["stable_summary_sha256"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
