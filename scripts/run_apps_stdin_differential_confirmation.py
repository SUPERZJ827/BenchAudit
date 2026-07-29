#!/usr/bin/env python3
"""Frozen APPS stdin/stdout differential-oracle transfer pilot.

This experiment deliberately constructs a weak two-case prefix and compares it
with the complete APPS test list.  It tests transfer of BenchAudit's generic
MR-4 proof contract; it does not claim that the official APPS evaluator is
defective.  No LLM or model API is used.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import heapq
import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

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
from benchcore.execution_attestation import ATTESTATION_PROTOCOL, transcript_sha256
from benchcore.loader import explicit_mapping_provenance
from benchcore.schema import BenchmarkItem
from scripts.run_pattern_memory_evalplus_lobo import generate_mutants


PROTOCOL_VERSION = "apps-stdin-differential-confirmation-v1"
RECEIPT_SCHEMA = "benchaudit-apps-stdin-input-receipt-v1"
SELECTION_SALT = "benchaudit-apps-stdin-v1:"
COMPARATOR_VERSION = "benchaudit-apps-stdin-comparator-v1"
EXPECTED_DATASET_SHA256 = (
    "5b003a65ac40feb47dd5eaec267a767a6fc435bdcfa68ff715fe869f948e760c"
)
EXPECTED_DATASET_BYTES = 1_292_436_853
MAX_TEST_BYTES = 100_000
MAX_SOURCE_BYTES = 10_000
MIN_CASES = 5
MAX_CASES = 20


APPS_STDIN_DRIVER = r'''
import collections
import json
import math
import subprocess
import sys

payload = json.loads(sys.stdin.read())

def materialize_input(value):
    if isinstance(value, list):
        return "\n".join(str(part) for part in value)
    return str(value)

def materialize_expected(value):
    if isinstance(value, list):
        return "\n".join(str(part) for part in value)
    return str(value)

def normalized_lines(value):
    return [line.strip() for line in value.strip().splitlines() if line.strip()]

def compare(actual, expected):
    if actual.strip() == expected.strip():
        return True
    actual_lines = normalized_lines(actual)
    expected_lines = normalized_lines(expected)
    if actual_lines == expected_lines:
        return True
    actual_tokens = actual.split()
    expected_tokens = expected.split()
    if len(actual_tokens) == len(expected_tokens):
        try:
            if all(math.isclose(
                float(left), float(right), rel_tol=1e-5, abs_tol=1e-6,
            ) for left, right in zip(actual_tokens, expected_tokens)):
                return True
        except (TypeError, ValueError, OverflowError):
            pass
        if collections.Counter(actual_tokens) == collections.Counter(expected_tokens):
            return True
    return False

def run_case(source, raw_input, raw_expected):
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", source],
            input=materialize_input(raw_input),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=payload["per_case_timeout"],
            check=False,
            env={
                "HOME": "/tmp",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONHASHSEED": "0",
                "TZ": "UTC",
            },
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "accepted": None, "detail": "case_timeout"}
    except BaseException as exc:
        return {
            "status": "error", "accepted": None, "detail": type(exc).__name__,
        }
    if proc.returncode < 0:
        return {
            "status": "error",
            "accepted": None,
            "detail": "candidate_signal",
        }
    if proc.returncode != 0:
        return {
            "status": "completed",
            "accepted": False,
            "detail": "candidate_nonzero_exit",
        }
    try:
        accepted = compare(proc.stdout, materialize_expected(raw_expected))
    except BaseException as exc:
        return {
            "status": "error", "accepted": None, "detail": type(exc).__name__,
        }
    return {
        "status": "completed",
        "accepted": bool(accepted),
        "detail": None if accepted else "output_mismatch",
    }

def execute(source, tests):
    for case in tests:
        if not isinstance(case, dict) or "input" not in case or "output" not in case:
            return {
                "status": "error",
                "accepted": None,
                "detail": "malformed_case",
            }
        result = run_case(source, case["input"], case["output"])
        if result["status"] != "completed" or result["accepted"] is not True:
            return result
    return {"status": "completed", "accepted": True, "detail": None}

rows = []
for candidate in payload["candidates"]:
    rows.append({
        "candidate_id": candidate["candidate_id"],
        "source_sha256": candidate["source_sha256"],
        "weak": execute(candidate["source"], payload["weak_tests"]),
        "strong": execute(candidate["source"], payload["strong_tests"]),
    })
print(json.dumps({"rows": rows}, ensure_ascii=False, sort_keys=True))
'''

EXECUTION_DRIVER_SHA256 = hashlib.sha256(
    APPS_STDIN_DRIVER.encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class AppsTask:
    problem_id: int
    source: str
    tests: tuple[dict[str, Any], ...]
    difficulty: str

    @property
    def task_id(self) -> str:
        return f"apps/{self.problem_id}"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_dataset_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size != EXPECTED_DATASET_BYTES:
        raise ValueError("APPS test split byte size does not match frozen receipt")
    if _sha256_file(path) != EXPECTED_DATASET_SHA256:
        raise ValueError("APPS test split SHA-256 does not match frozen receipt")


def _parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _eligible_task(row: dict[str, Any]) -> tuple[AppsTask | None, str]:
    raw_id = row.get("problem_id", row.get("id"))
    if isinstance(raw_id, bool) or not isinstance(raw_id, int):
        return None, "invalid_problem_id"
    try:
        in_out = _parse_json_field(row.get("input_output"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "invalid_input_output"
    if not isinstance(in_out, dict):
        return None, "invalid_input_output"
    if in_out.get("fn_name") is not None:
        return None, "call_based"
    inputs = in_out.get("inputs")
    outputs = in_out.get("outputs")
    if not isinstance(inputs, list) or not isinstance(outputs, list):
        return None, "invalid_cases"
    if len(inputs) != len(outputs) or not MIN_CASES <= len(inputs) <= MAX_CASES:
        return None, "case_count_out_of_range"
    try:
        solutions = _parse_json_field(row.get("solutions"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "invalid_solutions"
    if not isinstance(solutions, list) or not solutions:
        return None, "invalid_solutions"
    source = solutions[0]
    if not isinstance(source, str) or not source:
        return None, "invalid_canonical_source"
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        return None, "source_too_large"
    try:
        ast.parse(source)
    except SyntaxError:
        return None, "canonical_syntax_error"
    test_material = _canonical_json({"inputs": inputs, "outputs": outputs})
    if len(test_material.encode("utf-8")) > MAX_TEST_BYTES:
        return None, "tests_too_large"
    tests = tuple(
        {"input": input_value, "output": output_value}
        for input_value, output_value in zip(inputs, outputs)
    )
    return AppsTask(
        problem_id=raw_id,
        source=source,
        tests=tests,
        difficulty=str(row.get("difficulty") or "unknown"),
    ), "eligible"


def load_selected_tasks(
    path: Path,
    *,
    limit: int,
) -> tuple[list[AppsTask], dict[str, Any]]:
    selected: list[tuple[int, int, AppsTask]] = []
    reason_counts: dict[str, int] = {}
    seen_ids: set[int] = set()
    total = 0
    eligible = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at line {line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"non-object row at line {line_number}")
            task, reason = _eligible_task(row)
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            if task is None:
                continue
            if task.problem_id in seen_ids:
                raise ValueError(f"duplicate APPS problem id: {task.problem_id}")
            seen_ids.add(task.problem_id)
            eligible += 1
            rank = int(hashlib.sha256(
                f"{SELECTION_SALT}{task.problem_id}".encode("utf-8")
            ).hexdigest(), 16)
            entry = (-rank, -task.problem_id, task)
            if len(selected) < limit:
                heapq.heappush(selected, entry)
            elif entry > selected[0]:
                heapq.heapreplace(selected, entry)
    tasks = [
        entry[2] for entry in sorted(
            selected,
            key=lambda value: (-value[0], -value[1]),
        )
    ]
    return tasks, {
        "rows_scanned": total,
        "statically_eligible_rows": eligible,
        "eligibility_reason_counts": dict(sorted(reason_counts.items())),
        "selection_salt": SELECTION_SALT,
        "requested_task_ids": [task.task_id for task in tasks],
    }


def _candidates(task: AppsTask, per_family: int) -> list[DifferentialCandidate]:
    return [
        DifferentialCandidate(
            candidate_id=row["mutant_id"],
            source=row["source"],
            family=row["family"],
            transformation_index=int(row["mutant_id"].rsplit(":", 1)[1]),
        )
        for row in generate_mutants(task.source, per_family)
    ]


def _contract(
    task: AppsTask,
    candidates: list[DifferentialCandidate],
) -> dict[str, Any]:
    manifest = [candidate.to_evidence() for candidate in candidates]
    weak_tests = list(task.tests[:2])
    strong_tests = list(task.tests)
    revision = {
        "dataset_sha256": EXPECTED_DATASET_SHA256,
        "problem_id": task.problem_id,
        "canonical_source_sha256": _sha256_text(task.source),
        "weak_tests_sha256": _sha256_text(_canonical_json(weak_tests)),
        "strong_tests_sha256": _sha256_text(_canonical_json(strong_tests)),
        "comparator_version": COMPARATOR_VERSION,
        "execution_driver_sha256": EXECUTION_DRIVER_SHA256,
    }
    return {
        "schema_version": DIFFERENTIAL_ORACLE_CONTRACT_VERSION,
        "relation": "declared_strict_test_extension",
        "evaluator_identity": "apps:stdin:prefix2-vs-full:comparator-v1",
        "weak_oracle_identity": "apps:stdin:test-prefix-2:v1",
        "strong_oracle_identity": "apps:stdin:full-tests:v1",
        "source_revision": _sha256_text(_canonical_json(revision)),
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
        rows_by_hash = {
            row["candidate"]["candidate_source_sha256"]: row for row in rows
        }
        for entry in contract["candidate_manifest"]:
            row = rows_by_hash[entry["candidate_source_sha256"]]
            source_hash = entry["candidate_source_sha256"]
            self._outcomes[(source_hash, self.oracle_identities[0])] = (
                _observation(row["weak"])
            )
            self._outcomes[(source_hash, self.oracle_identities[1])] = (
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
        "weak_tests": payload["weak_tests"],
        "strong_tests": payload["strong_tests"],
        "per_case_timeout": payload["per_case_timeout"],
    }
    result = runner.run(
        CommandSpec(
            argv=(sys.executable, "-c", APPS_STDIN_DRIVER),
            cwd=REPO_ROOT,
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
    attestation = {
        "protocol": ATTESTATION_PROTOCOL,
        "payload_sha256": payload_sha256,
        "attester": "apps-stdin-separate-worker-v1",
        "run_id": run_id,
        "public_key_ed25519": base64.b64encode(public_key).decode("ascii"),
        "signature_ed25519": base64.b64encode(
            private_key.sign(bytes.fromhex(payload_sha256))
        ).decode("ascii"),
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
    }


def _payload(
    task: AppsTask,
    *,
    per_family: int,
    image: str,
    per_case_timeout: float,
    task_timeout: float,
) -> tuple[dict[str, Any], list[DifferentialCandidate]]:
    candidates = _candidates(task, per_family)
    contract = _contract(task, candidates)
    return {
        "task_id": task.task_id,
        "canonical_source": task.source,
        "weak_tests": list(task.tests[:2]),
        "strong_tests": list(task.tests),
        "candidates": [{
            "candidate_id": row.candidate_id,
            "source": row.source,
            "family": row.family,
            "transformation_index": row.transformation_index,
        } for row in candidates],
        "contract": contract,
        "image": image,
        "per_case_timeout": per_case_timeout,
        "task_timeout": task_timeout,
        "operational_retries": 1,
    }, candidates


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
    for _ in range(int(payload.get("operational_retries", 0)) + 1):
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


def _item(task: AppsTask, contract: dict[str, Any]) -> BenchmarkItem:
    evaluator = {"differential_oracle_contract": contract}
    raw = {
        "id": task.task_id,
        "task": "APPS stdin/stdout executable task",
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
        adapter_id="apps_stdin_differential_oracle",
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


def _corrupt_attestation(value: dict[str, Any]) -> dict[str, Any]:
    corrupted = dict(value)
    signature = bytearray(base64.b64decode(corrupted["signature_ed25519"]))
    signature[0] ^= 1
    corrupted["signature_ed25519"] = base64.b64encode(signature).decode("ascii")
    return corrupted


def _adjudicate(
    task: AppsTask,
    candidates: list[DifferentialCandidate],
    worker: dict[str, Any],
) -> dict[str, Any]:
    if worker.get("ok") is not True:
        return {
            "task_id": task.task_id,
            "difficulty": task.difficulty,
            "status": "operational_failed",
            "reason": worker.get("reason"),
            "runner": worker.get("runner"),
            "operational_attempts": worker.get("operational_attempts", []),
            "confirmed": 0,
        }
    if not candidates:
        return {
            "task_id": task.task_id,
            "difficulty": task.difficulty,
            "status": "not_applicable_no_candidates",
            "test_cases": len(task.tests),
            "candidates": 0,
            "confirmed": 0,
            "review": 0,
            "operational_attempts": worker.get("operational_attempts", []),
        }
    contract = worker["contract"]
    recorded = RecordedOraclePair(
        contract, task.source, worker["canonical"], worker["rows"],
    )
    item = _item(task, contract)
    findings = list(DifferentialOracleAuditChecker(
        recorded,
        candidates,
        transcript_attester=FrozenAttester(worker["attestation"]),
        transcript_verifier=PinnedWorkerVerifier(worker["attestation"]),
    ).check(item))
    unattested = list(DifferentialOracleAuditChecker(
        recorded, candidates,
    ).check(_item(task, contract)))
    corrupt = _corrupt_attestation(worker["attestation"])
    corrupt_findings = list(DifferentialOracleAuditChecker(
        recorded,
        candidates,
        transcript_attester=FrozenAttester(corrupt),
        transcript_verifier=PinnedWorkerVerifier(worker["attestation"]),
    ).check(_item(task, contract)))
    confirmed_ids = {
        finding.evidence["candidate"]["candidate_id"]
        for finding in findings if finding.evidence_tier == "confirmed"
    }
    rows = worker["rows"]
    complete = [
        row for row in rows
        if row["weak"]["status"] == "completed"
        and row["strong"]["status"] == "completed"
    ]
    indeterminate = [row for row in rows if row not in complete]
    identical = [
        row for row in complete
        if row["weak"]["accepted"] == row["strong"]["accepted"]
    ]
    swapped = [
        row for row in complete
        if row["weak"]["accepted"] is False
        and row["strong"]["accepted"] is True
    ]
    canonical_valid = (
        worker["canonical"]["weak"] == {
            "status": "completed", "accepted": True, "detail": None,
        }
        and worker["canonical"]["strong"] == {
            "status": "completed", "accepted": True, "detail": None,
        }
    )
    return {
        "task_id": task.task_id,
        "difficulty": task.difficulty,
        "status": "valid" if canonical_valid else "canonical_invalid",
        "canonical_observations": worker["canonical"],
        "candidate_observations": rows,
        "test_cases": len(task.tests),
        "candidates": len(candidates),
        "completed_pairs": len(complete),
        "indeterminate_pairs": len(indeterminate),
        "timeout_pairs": sum(
            row["weak"]["status"] == "timeout"
            or row["strong"]["status"] == "timeout"
            for row in rows
        ),
        "confirmed": sum(
            finding.evidence_tier == "confirmed" for finding in findings
        ),
        "review": sum(
            finding.evidence_tier == "review" for finding in findings
        ),
        "identical_outcome_confirmed_control": sum(
            row["candidate"]["candidate_id"] in confirmed_ids
            for row in identical
        ),
        "swapped_direction_confirmed_control": sum(
            row["candidate"]["candidate_id"] in confirmed_ids
            for row in swapped
        ),
        "indeterminate_confirmed_control": sum(
            row["candidate"]["candidate_id"] in confirmed_ids
            for row in indeterminate
        ),
        "unattested_confirmed_control": sum(
            finding.evidence_tier == "confirmed" for finding in unattested
        ),
        "corrupt_attestation_confirmed_control": sum(
            finding.evidence_tier == "confirmed" for finding in corrupt_findings
        ),
        "findings": [{
            "defect_type": finding.defect_type,
            "tier": finding.evidence_tier,
            "candidate_id": finding.evidence["candidate"]["candidate_id"],
            "family": finding.evidence["candidate"]["family"],
            "transcript_sha256":
                finding.evidence["execution_transcript_sha256"],
        } for finding in findings],
        "runner": {
            key: worker["runner"].get(key)
            for key in (
                "backend", "exit_code", "succeeded", "timed_out", "isolation",
            )
        },
        "operational_attempts": worker.get("operational_attempts", []),
    }


def _weak_pass_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    weak_pass = 0
    weak_pass_with_completed_strong = 0
    weak_pass_strong_fail = 0
    for task in rows:
        for candidate in task.get("candidate_observations", []):
            weak = candidate.get("weak", {})
            strong = candidate.get("strong", {})
            if weak.get("status") != "completed" or weak.get("accepted") is not True:
                continue
            weak_pass += 1
            if strong.get("status") != "completed":
                continue
            weak_pass_with_completed_strong += 1
            if strong.get("accepted") is False:
                weak_pass_strong_fail += 1
    return {
        "weak_pass_pairs": weak_pass,
        "weak_pass_with_completed_strong_pairs":
            weak_pass_with_completed_strong,
        "weak_pass_strong_fail_pairs": weak_pass_strong_fail,
        "conditional_gap_yield": (
            weak_pass_strong_fail / weak_pass_with_completed_strong
            if weak_pass_with_completed_strong else 0.0
        ),
    }


def _aggregate(
    rows: list[dict[str, Any]],
    *,
    input_stats: dict[str, Any],
    image: str,
    image_resolved: str,
    per_family: int,
    per_case_timeout: float,
    task_timeout: float,
    workers: int,
) -> dict[str, Any]:
    valid = [row for row in rows if row["status"] == "valid"]
    candidates = sum(row.get("candidates", 0) for row in valid)
    completed = sum(row.get("completed_pairs", 0) for row in valid)
    confirmed = sum(row.get("confirmed", 0) for row in valid)
    affected = sum(row.get("confirmed", 0) > 0 for row in valid)
    weak_pass_metrics = _weak_pass_metrics(valid)
    families: dict[str, int] = {}
    for row in valid:
        for finding in row.get("findings", []):
            family = str(finding["family"])
            families[family] = families.get(family, 0) + 1
    stable = {
        "protocol": {
            "schema_version": PROTOCOL_VERSION,
            "dataset_sha256": EXPECTED_DATASET_SHA256,
            "dataset_bytes": EXPECTED_DATASET_BYTES,
            "comparator_version": COMPARATOR_VERSION,
            "execution_driver_sha256": EXECUTION_DRIVER_SHA256,
            "image_requested": image,
            "image_resolved": image_resolved,
            "per_family": per_family,
            "per_case_timeout": per_case_timeout,
            "task_timeout": task_timeout,
            "workers": workers,
            "operational_retries": 1,
            "llm_calls": 0,
        },
        "input": input_stats,
        "apps_stdin": {
            "requested_tasks": len(rows),
            "valid_tasks": len(valid),
            "canonical_invalid_tasks": sum(
                row["status"] == "canonical_invalid" for row in rows
            ),
            "operational_failed_tasks": sum(
                row["status"] == "operational_failed" for row in rows
            ),
            "no_candidate_tasks": sum(
                row["status"] == "not_applicable_no_candidates" for row in rows
            ),
            "generated_candidates": candidates,
            "completed_pairs": completed,
            "indeterminate_pairs": sum(
                row.get("indeterminate_pairs", 0) for row in valid
            ),
            "timeout_pairs": sum(
                row.get("timeout_pairs", 0) for row in valid
            ),
            "confirmed_relative_coverage_gaps": confirmed,
            "affected_tasks": affected,
            "witness_yield": confirmed / completed if completed else 0.0,
            "affected_task_rate": affected / len(valid) if valid else 0.0,
            "confirmed_by_family": dict(sorted(families.items())),
            **weak_pass_metrics,
        },
        "controls": {
            "canonical_finding_count": 0,
            "identical_outcome_confirmed_count": sum(
                row.get("identical_outcome_confirmed_control", 0)
                for row in valid
            ),
            "timeout_error_confirmed_count": sum(
                row.get("indeterminate_confirmed_control", 0) for row in valid
            ),
            "swapped_direction_confirmed_count": sum(
                row.get("swapped_direction_confirmed_control", 0)
                for row in valid
            ),
            "unattested_confirmed_count": sum(
                row.get("unattested_confirmed_control", 0) for row in valid
            ),
            "corrupt_attestation_confirmed_count": sum(
                row.get("corrupt_attestation_confirmed_control", 0)
                for row in valid
            ),
        },
    }
    stable["stable_summary_sha256"] = _sha256_text(_canonical_json(stable))
    return stable


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset_file = Path(args.dataset_file).resolve()
    verify_dataset_file(dataset_file)
    tasks, input_stats = load_selected_tasks(dataset_file, limit=args.limit)
    payloads = [
        (task, *_payload(
            task,
            per_family=args.per_family,
            image=args.image,
            per_case_timeout=args.per_case_timeout,
            task_timeout=args.task_timeout,
        ))
        for task in tasks
    ]
    worker_results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_invoke_worker, payload): task.task_id
            for task, payload, _ in payloads
        }
        for index, future in enumerate(as_completed(futures), start=1):
            worker_results[futures[future]] = future.result()
            if index % 5 == 0 or index == len(futures):
                print(
                    f"completed {index}/{len(futures)} APPS worker tasks",
                    file=sys.stderr,
                    flush=True,
                )
    raw = [
        _adjudicate(task, candidates, worker_results[task.task_id])
        for task, _, candidates in payloads
    ]
    raw.sort(key=lambda row: row["task_id"])
    resolved = subprocess.run(
        ["docker", "image", "inspect", args.image, "--format", "{{.Id}}"],
        text=True, capture_output=True, check=False,
    ).stdout.strip()
    return {
        **_aggregate(
            raw,
            input_stats=input_stats,
            image=args.image,
            image_resolved=resolved,
            per_family=args.per_family,
            per_case_timeout=args.per_case_timeout,
            task_timeout=args.task_timeout,
            workers=args.workers,
        ),
        "raw": raw,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--dataset-file")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--per-family", type=int, default=1)
    parser.add_argument("--per-case-timeout", type=float, default=2.0)
    parser.add_argument("--task-timeout", type=float, default=120.0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--image", default="ds1000-audit:v1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.worker:
        try:
            payload = json.loads(sys.stdin.read())
            result = _worker(payload)
        except Exception as exc:
            result = {"ok": False, "reason": type(exc).__name__}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    if not args.dataset_file or args.output is None:
        raise SystemExit("--dataset-file and --output are required")
    if (
        args.limit != 30
        or args.per_family != 1
        or args.per_case_timeout != 2.0
        or args.task_timeout != 120.0
        or args.workers != 6
    ):
        raise SystemExit("pilot parameters are frozen by the protocol")
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "stable_summary_sha256": result["stable_summary_sha256"],
        "apps_stdin": result["apps_stdin"],
        "controls": result["controls"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
