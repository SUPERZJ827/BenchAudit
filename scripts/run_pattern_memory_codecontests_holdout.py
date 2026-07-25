"""Frozen third-benchmark holdout for code defect-pattern routing.

HumanEval+ and MBPP+ provide source mutation-family evidence.  The unseen
CodeContests test split changes the execution protocol to stdin/stdout:
public tests are the weak evaluator and private/generated tests are the
stronger oracle.  Target outcomes are collected exhaustively and are never
used to choose the target probes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from datasets import load_dataset

import run_pattern_memory_evalplus_lobo as base


PROTOCOL_IDS = {
    "pattern-memory-codecontests-holdout-v1",
    "pattern-memory-codecontests-valid-holdout-v2",
}

STDIO_DRIVER = r'''
import json
import os
import subprocess
import sys

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

payload = json.loads(sys.stdin.read())

def execute(source, cases):
    for index, case in enumerate(cases):
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-c", source],
                input=case["input"],
                text=True,
                capture_output=True,
                timeout=payload["per_case_timeout"],
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONHASHSEED": "0",
                    "OPENBLAS_NUM_THREADS": "1",
                    "OMP_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                    "TZ": "UTC",
                },
            )
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "error": f"case {index}: timeout",
            }
        if result.returncode != 0:
            error = result.stderr.replace("\n", " ")[:300]
            return {
                "passed": False,
                "error": f"case {index}: rc={result.returncode}: {error}",
            }
        if result.stdout.split() != case["output"].split():
            return {
                "passed": False,
                "error": f"case {index}: token mismatch",
            }
    return {"passed": True, "error": None}

rows = []
for mutant in payload["mutants"]:
    original = execute(mutant["source"], payload["weak_cases"])
    strong = execute(mutant["source"], payload["strong_cases"])
    rows.append({
        "mutant_id": mutant["mutant_id"],
        "family": mutant["family"],
        "original": original,
        "plus": strong,
    })
print(json.dumps({"rows": rows}, sort_keys=True))
'''


@dataclass(frozen=True)
class StdioTask:
    benchmark: str
    task_id: str
    source: str
    weak_cases: tuple[dict[str, str], ...]
    strong_cases: tuple[dict[str, str], ...]
    source_name: str


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _cases(inputs: Sequence[Any], outputs: Sequence[Any]) -> list[dict[str, str]]:
    if len(inputs) != len(outputs):
        raise ValueError("test input/output counts differ")
    return [
        {"input": str(input_value), "output": str(output_value)}
        for input_value, output_value in zip(inputs, outputs)
    ]


def load_codecontests_tasks(
    *,
    dataset: str,
    revision: str,
    split: str,
    candidate_limit: int,
    minimum_strong_cases: int,
    strong_case_cap: int,
) -> list[StdioTask]:
    stream = load_dataset(
        dataset,
        split=split,
        revision=revision,
        streaming=True,
    )
    tasks = []
    for row in stream:
        if str(row.get("input_file") or "").strip():
            continue
        if str(row.get("output_file") or "").strip():
            continue
        languages = list(row["solutions"]["language"])
        solutions = list(row["solutions"]["solution"])
        python3_indices = [
            index for index, language in enumerate(languages)
            if int(language) == 3
        ]
        weak = _cases(
            row["public_tests"]["input"],
            row["public_tests"]["output"],
        )
        strong = [
            *_cases(
                row["private_tests"]["input"],
                row["private_tests"]["output"],
            ),
            *_cases(
                row["generated_tests"]["input"],
                row["generated_tests"]["output"],
            ),
        ]
        if (
            not python3_indices
            or not weak
            or len(strong) < minimum_strong_cases
        ):
            continue
        source = str(solutions[python3_indices[0]])
        tasks.append(StdioTask(
            benchmark="codecontests",
            task_id=str(row["name"]),
            source=source,
            weak_cases=tuple(weak),
            strong_cases=tuple(strong[:strong_case_cap]),
            source_name=str(row.get("source") or ""),
        ))
        if len(tasks) >= candidate_limit:
            break
    if not tasks:
        raise RuntimeError(
            "no eligible CodeContests tasks were found"
        )
    return tasks


def task_manifest(tasks: Sequence[StdioTask]) -> dict[str, Any]:
    rows = [{
        "task_id": task.task_id,
        "source_sha256": hashlib.sha256(
            task.source.encode("utf-8")
        ).hexdigest(),
        "weak_cases": len(task.weak_cases),
        "weak_cases_sha256": hashlib.sha256(
            canonical_json(task.weak_cases).encode("utf-8")
        ).hexdigest(),
        "strong_cases": len(task.strong_cases),
        "strong_cases_sha256": hashlib.sha256(
            canonical_json(task.strong_cases).encode("utf-8")
        ).hexdigest(),
    } for task in tasks]
    return {
        "tasks": len(rows),
        "manifest_sha256": hashlib.sha256(
            canonical_json(rows).encode("utf-8")
        ).hexdigest(),
        "rows": rows,
    }


def evidence_results_sha256(results: Sequence[Mapping[str, Any]]) -> str:
    """Bind semantic pass/fail outcomes while excluding runtime noise.

    Error strings may contain object memory addresses and are diagnostic only;
    routing and witness labels depend exclusively on the two booleans.
    """

    rows = [{
        "task_id": str(row["task_id"]),
        "valid": bool(row.get("valid")),
        "rows": [{
            "mutant_id": candidate.get("mutant_id"),
            "family": candidate.get("family"),
            "original_passed": bool(
                candidate.get("original", {}).get("passed")
            ),
            "strong_passed": bool(
                candidate.get("plus", {}).get("passed")
            ),
        } for candidate in row.get("rows", [])],
    } for row in results]
    return hashlib.sha256(
        canonical_json(rows).encode("utf-8")
    ).hexdigest()


def run_stdio_task(
    runner: base.ContainerRunner,
    task: StdioTask,
    *,
    per_family: int,
    per_case_timeout: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    mutants = base.generate_mutants(task.source, per_family)
    payload = {
        "mutants": [
            {
                "mutant_id": "canonical",
                "family": "canonical",
                "source": task.source,
            },
            *mutants,
        ],
        "weak_cases": list(task.weak_cases),
        "strong_cases": list(task.strong_cases),
        "per_case_timeout": per_case_timeout,
    }
    result = runner.run(
        base.CommandSpec(
            argv=(sys.executable, "-c", STDIO_DRIVER),
            cwd=Path.cwd(),
            env={
                "PYTHONHASHSEED": "0",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "TZ": "UTC",
            },
            stdin=json.dumps(payload, ensure_ascii=False),
        ),
        base.ExecutionPolicy(
            timeout_seconds=timeout_seconds,
            max_output_chars=200_000,
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
    row: dict[str, Any] = {
        "benchmark": task.benchmark,
        "task_id": task.task_id,
        "mutants_generated": len(mutants),
        "runner": result.to_dict(),
        "rows": [],
        "valid": False,
    }
    if not result.succeeded:
        return row
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return row
    rows = parsed.get("rows", [])
    row["rows"] = rows
    canonical = next(
        (
            candidate for candidate in rows
            if candidate["mutant_id"] == "canonical"
        ),
        None,
    )
    row["valid"] = bool(
        canonical
        and canonical["original"]["passed"]
        and canonical["plus"]["passed"]
    )
    return row


def collect_codecontests(
    tasks: Sequence[StdioTask],
    *,
    workers: int,
    per_family: int,
    per_case_timeout: float,
    container_image: str,
) -> list[dict[str, Any]]:
    runner = base.ContainerRunner(container_image, engine="docker")
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                run_stdio_task,
                runner,
                task,
                per_family=per_family,
                per_case_timeout=per_case_timeout,
                timeout_seconds=max(
                    180.0,
                    per_case_timeout
                    * (1 + per_family * len(base.FAMILIES))
                    * 8,
                ),
            ): task
            for task in tasks
        }
        for index, future in enumerate(as_completed(futures), 1):
            task = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({
                    "benchmark": task.benchmark,
                    "task_id": task.task_id,
                    "valid": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "rows": [],
                })
            if index % 20 == 0:
                print(
                    f"codecontests: {index}/{len(tasks)}",
                    file=sys.stderr,
                )
    return sorted(results, key=lambda row: row["task_id"])


def independently_supported_families(
    source_groups: Mapping[str, list[dict[str, Any]]],
    *,
    minimum_witness_tasks: int,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    per_source = {
        name: base.family_statistics(rows)
        for name, rows in source_groups.items()
    }
    supported = [
        family
        for family in base.FAMILIES
        if all(
            int(stats[family]["witness_task_count"])
            >= minimum_witness_tasks
            for stats in per_source.values()
        )
    ]
    return supported, per_source


def filter_source_families(
    results: Sequence[dict[str, Any]],
    allowed: set[str],
) -> list[dict[str, Any]]:
    filtered = []
    for task in results:
        copied = copy.deepcopy(task)
        copied["rows"] = [
            row for row in copied.get("rows", [])
            if row.get("family") == "canonical"
            or row.get("family") in allowed
        ]
        filtered.append(copied)
    return filtered


def success_gate(
    primary: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    gate = protocol["success_gate"]
    random_yield = primary["random_family_order_control"]["witness_yield"]
    random_recall = primary["random_family_order_control"]["task_recall"]
    paired = primary["paired_bootstrap_D_minus_A"]["witness_yield"]
    checks = {
        "minimum_valid_target_tasks": (
            primary["valid_target_tasks"]
            >= gate["minimum_valid_target_tasks"]
        ),
        "minimum_witnessable_target_tasks": (
            primary["witnessable_target_tasks"]
            >= gate["minimum_witnessable_target_tasks"]
        ),
        "memory_above_random_mean": (
            random_yield["memory_minus_random_mean"]
            > gate["memory_minus_random_mean_gt"]
        ),
        "random_order_empirical_p": (
            random_yield["empirical_one_sided_p"]
            <= gate["empirical_one_sided_p_lte"]
        ),
        "paired_bootstrap_ci95_lower": (
            paired["ci95"][0]
            > gate["paired_bootstrap_ci95_lower_gt"]
        ),
        "task_recall_not_below_random_mean": (
            random_recall["memory_minus_random_mean"] >= 0
        ),
    }
    task_recall_floor = gate.get("task_recall_paired_ci95_lower_gt")
    if task_recall_floor is not None:
        task_paired = primary["paired_bootstrap_D_minus_A"]["task_recall"]
        checks["task_recall_paired_ci95_lower"] = (
            task_paired["ci95"][0] > task_recall_floor
        )
    return {
        "checks": checks,
        "all_non_reproducibility_checks_pass": all(checks.values()),
        "reproducibility_check_pending": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(
            "experiments/pattern_memory/"
            "codecontests_holdout_protocol_v1.json"
        ),
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--reuse-source",
        type=Path,
        help="Optional prior output whose pinned HumanEval/MBPP raw rows are reused.",
    )
    parser.add_argument(
        "--reuse-target",
        type=Path,
        help="Optional prior output whose pinned CodeContests raw rows are reused.",
    )
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") not in PROTOCOL_IDS:
        raise ValueError("protocol ID mismatch")
    if args.workers < 1:
        raise ValueError("--workers must be positive")
    expected_workers = protocol["controls"].get("execution_workers")
    if expected_workers is not None and args.workers != expected_workers:
        raise ValueError(
            f"protocol requires --workers {expected_workers}, got {args.workers}"
        )

    expected_image = protocol["container"]["resolved_image"]
    resolved_image = subprocess.check_output(
        [
            "docker",
            "image",
            "inspect",
            protocol["container"]["image"],
            "--format",
            "{{.Id}}",
        ],
        text=True,
    ).strip()
    if resolved_image != expected_image:
        raise RuntimeError(
            f"container image mismatch: {resolved_image} != {expected_image}"
        )

    target_spec = protocol["target_benchmark"]
    tasks = load_codecontests_tasks(
        dataset=target_spec["dataset"],
        revision=target_spec["revision"],
        split=target_spec["split"],
        candidate_limit=target_spec["candidate_limit"],
        minimum_strong_cases=target_spec["minimum_strong_cases"],
        strong_case_cap=target_spec["strong_case_cap"],
    )
    manifest = task_manifest(tasks)

    if args.reuse_source:
        prior = json.loads(args.reuse_source.read_text(encoding="utf-8"))
        humaneval = prior["raw"]["humaneval"]
        mbpp = prior["raw"]["mbpp"]
        expected_source = protocol.get(
            "development_result", {}
        ).get("source_evidence_sha256", {})
        for name, rows in (("humaneval", humaneval), ("mbpp", mbpp)):
            actual = evidence_results_sha256(rows)
            expected = expected_source.get(name)
            if expected is not None and actual != expected:
                raise ValueError(
                    f"reused {name} evidence mismatch: {actual} != {expected}"
                )
    else:
        mutation = protocol["mutation_protocol"]
        humaneval = base.collect(
            "humaneval",
            limit=protocol["source_benchmarks"]["humaneval"]["limit"],
            workers=args.workers,
            per_family=mutation["mutants_per_family"],
            per_probe_timeout=5.0,
            container_image=resolved_image,
        )
        mbpp = base.collect(
            "mbpp",
            limit=protocol["source_benchmarks"]["mbpp"]["limit"],
            workers=args.workers,
            per_family=mutation["mutants_per_family"],
            per_probe_timeout=5.0,
            container_image=resolved_image,
        )

    if args.reuse_target:
        prior = json.loads(args.reuse_target.read_text(encoding="utf-8"))
        prior_manifest = prior["collection"]["codecontests"]["manifest"]
        if prior_manifest["manifest_sha256"] != manifest["manifest_sha256"]:
            raise ValueError("reused CodeContests task manifest does not match")
        codecontests = prior["raw"]["codecontests"]
    else:
        codecontests = collect_codecontests(
            tasks,
            workers=args.workers,
            per_family=protocol["mutation_protocol"]["mutants_per_family"],
            per_case_timeout=target_spec["per_case_timeout_seconds"],
            container_image=resolved_image,
        )

    supported, source_support = independently_supported_families(
        {"humaneval": humaneval, "mbpp": mbpp},
        minimum_witness_tasks=protocol["memory_gate"][
            "minimum_witness_tasks_per_source_benchmark"
        ],
    )
    pooled = filter_source_families(
        [*humaneval, *mbpp],
        set(supported),
    )
    primary = base.evaluate_direction(
        "humaneval+mbpp",
        "codecontests",
        pooled,
        codecontests,
        budget=protocol["mutation_protocol"]["budget_per_task"],
        minimum_witness_tasks=protocol["memory_gate"][
            "minimum_witness_tasks_per_source_benchmark"
        ],
    )
    diagnostics = [
        base.evaluate_direction(
            "codecontests",
            target_name,
            codecontests,
            target_rows,
            budget=protocol["mutation_protocol"]["budget_per_task"],
            minimum_witness_tasks=protocol["memory_gate"][
                "minimum_witness_tasks_per_source_benchmark"
            ],
        )
        for target_name, target_rows in (
            ("humaneval", humaneval),
            ("mbpp", mbpp),
        )
    ]
    result = {
        "schema_version": "pattern-memory-codecontests-holdout-v1",
        "protocol": protocol,
        "collection": {
            "humaneval": {
                "requested": protocol["source_benchmarks"]["humaneval"]["limit"],
                "valid": sum(row.get("valid", False) for row in humaneval),
                "evidence_sha256": evidence_results_sha256(humaneval),
            },
            "mbpp": {
                "requested": protocol["source_benchmarks"]["mbpp"]["limit"],
                "valid": sum(row.get("valid", False) for row in mbpp),
                "evidence_sha256": evidence_results_sha256(mbpp),
            },
            "codecontests": {
                "requested": len(tasks),
                "valid": sum(row.get("valid", False) for row in codecontests),
                "manifest": manifest,
            },
        },
        "independently_supported_source_families": supported,
        "source_family_statistics": source_support,
        "primary_direction": primary,
        "diagnostic_directions": diagnostics,
        "success_gate": success_gate(primary, protocol),
        "promotion_ceiling": "review",
        "selection_uses_target_problem_text": False,
        "selection_uses_target_outcomes": False,
        "raw": {
            "humaneval": humaneval,
            "mbpp": mbpp,
            "codecontests": codecontests,
        },
    }
    stable = {
        "protocol": protocol,
        "collection": {
            key: {
                field: value
                for field, value in row.items()
                if field != "manifest" or key == "codecontests"
            }
            for key, row in result["collection"].items()
        },
        "independently_supported_source_families": supported,
        "source_family_statistics": source_support,
        "primary_direction": primary,
        "diagnostic_directions": diagnostics,
        "success_gate": result["success_gate"],
        "promotion_ceiling": "review",
    }
    result["stable_summary_sha256"] = hashlib.sha256(
        canonical_json(stable).encode("utf-8")
    ).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "collection": result["collection"],
        "independently_supported_source_families": supported,
        "primary_direction": primary,
        "success_gate": result["success_gate"],
        "stable_summary_sha256": result["stable_summary_sha256"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
