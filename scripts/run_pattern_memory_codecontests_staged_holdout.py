#!/usr/bin/env python3
"""Frozen staged CodeContests holdout for pattern-memory routing.

The target split is consumed in two phases.  Up to three pinned, official
Python 3 reference solutions are checked without mutants.  Mutants are
generated only for the first reference that passes both the public evaluator
and the independent stronger oracle.  Target mutation outcomes never
participate in probe selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from datasets import load_dataset


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_pattern_memory_codecontests_holdout as codecontests
import run_pattern_memory_evalplus_lobo as base


PROTOCOL_ID = "pattern-memory-codecontests-train-staged-holdout-v3"


@dataclass(frozen=True)
class CandidateTask:
    benchmark: str
    task_id: str
    source_candidates: tuple[str, ...]
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


def load_candidate_tasks(
    *,
    dataset: str,
    revision: str,
    split: str,
    candidate_limit: int,
    maximum_python3_reference_candidates: int,
    minimum_strong_cases: int,
    strong_case_cap: int,
) -> list[CandidateTask]:
    if maximum_python3_reference_candidates < 1:
        raise ValueError("maximum reference candidates must be positive")
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
        sources = tuple(
            str(solutions[index])
            for index, language in enumerate(languages)
            if int(language) == 3
        )[:maximum_python3_reference_candidates]
        weak = codecontests._cases(
            row["public_tests"]["input"],
            row["public_tests"]["output"],
        )
        strong = [
            *codecontests._cases(
                row["private_tests"]["input"],
                row["private_tests"]["output"],
            ),
            *codecontests._cases(
                row["generated_tests"]["input"],
                row["generated_tests"]["output"],
            ),
        ]
        if not sources or not weak or len(strong) < minimum_strong_cases:
            continue
        tasks.append(CandidateTask(
            benchmark="codecontests",
            task_id=str(row["name"]),
            source_candidates=sources,
            weak_cases=tuple(weak),
            strong_cases=tuple(strong[:strong_case_cap]),
            source_name=str(row.get("source") or ""),
        ))
        if len(tasks) >= candidate_limit:
            break
    if not tasks:
        raise RuntimeError("no eligible CodeContests tasks were found")
    return tasks


def candidate_manifest(tasks: Sequence[CandidateTask]) -> dict[str, Any]:
    rows = []
    for task in tasks:
        rows.append({
            "task_id": task.task_id,
            "source_candidate_sha256": [
                hashlib.sha256(source.encode("utf-8")).hexdigest()
                for source in task.source_candidates
            ],
            "weak_cases": len(task.weak_cases),
            "weak_cases_sha256": hashlib.sha256(
                canonical_json(task.weak_cases).encode("utf-8")
            ).hexdigest(),
            "strong_cases": len(task.strong_cases),
            "strong_cases_sha256": hashlib.sha256(
                canonical_json(task.strong_cases).encode("utf-8")
            ).hexdigest(),
        })
    return {
        "tasks": len(rows),
        "manifest_sha256": hashlib.sha256(
            canonical_json(rows).encode("utf-8")
        ).hexdigest(),
        "rows": rows,
    }


def _execution_task(task: CandidateTask, source: str) -> codecontests.StdioTask:
    return codecontests.StdioTask(
        benchmark=task.benchmark,
        task_id=task.task_id,
        source=source,
        weak_cases=task.weak_cases,
        strong_cases=task.strong_cases,
        source_name=task.source_name,
    )


def _canonical_semantics(result: Mapping[str, Any]) -> dict[str, Any]:
    canonical = next(
        (
            row
            for row in result.get("rows", [])
            if row.get("mutant_id") == "canonical"
        ),
        None,
    )
    return {
        "valid": bool(result.get("valid")),
        "weak_passed": bool(
            canonical and canonical.get("original", {}).get("passed")
        ),
        "strong_passed": bool(
            canonical and canonical.get("plus", {}).get("passed")
        ),
    }


def _canonical_diagnostics(result: Mapping[str, Any]) -> dict[str, Any]:
    canonical = next(
        (
            row
            for row in result.get("rows", [])
            if row.get("mutant_id") == "canonical"
        ),
        None,
    )
    return {
        "weak_error": (
            canonical.get("original", {}).get("error") if canonical else None
        ),
        "strong_error": (
            canonical.get("plus", {}).get("error") if canonical else None
        ),
        "runner_succeeded": bool(
            result.get("runner", {}).get("succeeded")
            if isinstance(result.get("runner"), dict)
            else False
        ),
    }


ExecutionFunction = Callable[
    [codecontests.StdioTask, int],
    dict[str, Any],
]


def stage_task(
    task: CandidateTask,
    *,
    execute: ExecutionFunction,
    mutants_per_family: int,
) -> dict[str, Any]:
    attempts = []
    for index, source in enumerate(task.source_candidates):
        execution_task = _execution_task(task, source)
        validation = execute(execution_task, 0)
        semantic = {
            "candidate_index": index,
            "source_sha256": hashlib.sha256(
                source.encode("utf-8")
            ).hexdigest(),
            **_canonical_semantics(validation),
            **_canonical_diagnostics(validation),
        }
        attempts.append(semantic)
        if not semantic["valid"]:
            continue

        result = execute(execution_task, mutants_per_family)
        result["selected_source_candidate_index"] = index
        result["selected_source_sha256"] = semantic["source_sha256"]
        result["canonical_validation_attempts"] = attempts
        result["staged_reference_valid"] = bool(result.get("valid"))
        return result

    return {
        "benchmark": task.benchmark,
        "task_id": task.task_id,
        "mutants_generated": 0,
        "runner": None,
        "rows": [],
        "valid": False,
        "selected_source_candidate_index": None,
        "selected_source_sha256": None,
        "canonical_validation_attempts": attempts,
        "staged_reference_valid": False,
    }


def collect_staged(
    tasks: Sequence[CandidateTask],
    *,
    workers: int,
    mutants_per_family: int,
    per_case_timeout: float,
    container_image: str,
) -> list[dict[str, Any]]:
    runner = base.ContainerRunner(container_image, engine="docker")

    def execute(
        task: codecontests.StdioTask,
        per_family: int,
    ) -> dict[str, Any]:
        return codecontests.run_stdio_task(
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
        )

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                stage_task,
                task,
                execute=execute,
                mutants_per_family=mutants_per_family,
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
                    "rows": [],
                    "canonical_validation_attempts": [],
                    "error": f"{type(exc).__name__}: {exc}",
                })
            if index % 20 == 0:
                print(f"codecontests staged: {index}/{len(tasks)}", file=sys.stderr)
    return sorted(results, key=lambda row: row["task_id"])


def staged_evidence_sha256(results: Sequence[Mapping[str, Any]]) -> str:
    rows = []
    for row in results:
        rows.append({
            "task_id": str(row["task_id"]),
            "valid": bool(row.get("valid")),
            "selected_source_candidate_index": row.get(
                "selected_source_candidate_index"
            ),
            "selected_source_sha256": row.get("selected_source_sha256"),
            "canonical_validation_attempts": [
                {
                    "candidate_index": attempt.get("candidate_index"),
                    "source_sha256": attempt.get("source_sha256"),
                    "valid": bool(attempt.get("valid")),
                    "weak_passed": bool(attempt.get("weak_passed")),
                    "strong_passed": bool(attempt.get("strong_passed")),
                }
                for attempt in row.get("canonical_validation_attempts", [])
            ],
            "rows": [
                {
                    "mutant_id": candidate.get("mutant_id"),
                    "family": candidate.get("family"),
                    "weak_passed": bool(
                        candidate.get("original", {}).get("passed")
                    ),
                    "strong_passed": bool(
                        candidate.get("plus", {}).get("passed")
                    ),
                }
                for candidate in row.get("rows", [])
            ],
        })
    return hashlib.sha256(
        canonical_json(rows).encode("utf-8")
    ).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(
            "experiments/pattern_memory/"
            "codecontests_train_staged_holdout_protocol_v3.json"
        ),
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reuse-source", type=Path, required=True)
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("protocol ID mismatch")
    expected_workers = int(protocol["controls"]["execution_workers"])
    if args.workers != expected_workers:
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

    prior = json.loads(args.reuse_source.read_text(encoding="utf-8"))
    humaneval = prior["raw"]["humaneval"]
    mbpp = prior["raw"]["mbpp"]
    expected_sources = protocol["prior_results"]["source_evidence_sha256"]
    for name, rows in (("humaneval", humaneval), ("mbpp", mbpp)):
        actual = codecontests.evidence_results_sha256(rows)
        if actual != expected_sources[name]:
            raise ValueError(
                f"reused {name} evidence mismatch: "
                f"{actual} != {expected_sources[name]}"
            )

    target = protocol["target_benchmark"]
    tasks = load_candidate_tasks(
        dataset=target["dataset"],
        revision=target["revision"],
        split=target["split"],
        candidate_limit=target["candidate_limit"],
        maximum_python3_reference_candidates=target[
            "maximum_python3_reference_candidates"
        ],
        minimum_strong_cases=target["minimum_strong_cases"],
        strong_case_cap=target["strong_case_cap"],
    )
    manifest = candidate_manifest(tasks)
    codecontests_rows = collect_staged(
        tasks,
        workers=args.workers,
        mutants_per_family=protocol["mutation_protocol"][
            "mutants_per_family"
        ],
        per_case_timeout=target["per_case_timeout_seconds"],
        container_image=resolved_image,
    )

    supported, source_support = codecontests.independently_supported_families(
        {"humaneval": humaneval, "mbpp": mbpp},
        minimum_witness_tasks=protocol["memory_gate"][
            "minimum_witness_tasks_per_source_benchmark"
        ],
    )
    pooled = codecontests.filter_source_families(
        [*humaneval, *mbpp],
        set(supported),
    )
    primary = base.evaluate_direction(
        "humaneval+mbpp",
        "codecontests-train",
        pooled,
        codecontests_rows,
        budget=protocol["mutation_protocol"]["budget_per_task"],
        minimum_witness_tasks=protocol["memory_gate"][
            "minimum_witness_tasks_per_source_benchmark"
        ],
    )
    target_evidence_sha256 = staged_evidence_sha256(codecontests_rows)
    result = {
        "schema_version": "pattern-memory-codecontests-staged-holdout-v1",
        "protocol": protocol,
        "collection": {
            "humaneval": {
                "requested": protocol["source_benchmarks"]["humaneval"]["limit"],
                "valid": sum(row.get("valid", False) for row in humaneval),
                "evidence_sha256": codecontests.evidence_results_sha256(humaneval),
            },
            "mbpp": {
                "requested": protocol["source_benchmarks"]["mbpp"]["limit"],
                "valid": sum(row.get("valid", False) for row in mbpp),
                "evidence_sha256": codecontests.evidence_results_sha256(mbpp),
            },
            "codecontests": {
                "requested": len(tasks),
                "valid": sum(
                    row.get("valid", False) for row in codecontests_rows
                ),
                "selected_after_first_candidate": sum(
                    (row.get("selected_source_candidate_index") or 0) > 0
                    for row in codecontests_rows
                    if row.get("selected_source_candidate_index") is not None
                ),
                "evidence_sha256": target_evidence_sha256,
                "manifest": manifest,
            },
        },
        "independently_supported_source_families": supported,
        "source_family_statistics": source_support,
        "primary_direction": primary,
        "success_gate": codecontests.success_gate(primary, protocol),
        "promotion_ceiling": "review",
        "selection_uses_target_problem_text": False,
        "probe_selection_uses_target_outcomes": False,
        "reference_selection_uses_strong_oracle": True,
        "raw": {
            "humaneval": humaneval,
            "mbpp": mbpp,
            "codecontests": codecontests_rows,
        },
    }
    stable = {
        "protocol": protocol,
        "collection": result["collection"],
        "independently_supported_source_families": supported,
        "source_family_statistics": source_support,
        "primary_direction": primary,
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
