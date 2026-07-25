from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from scripts import run_pattern_memory_codecontests_staged_holdout as staged


def task(*sources: str) -> staged.CandidateTask:
    return staged.CandidateTask(
        benchmark="codecontests",
        task_id="task-1",
        source_candidates=tuple(sources),
        weak_cases=({"input": "1\n", "output": "1\n"},),
        strong_cases=({"input": "2\n", "output": "2\n"},),
        source_name="unit",
    )


def result(
    *,
    valid: bool,
    weak: bool | None = None,
    strong: bool | None = None,
    include_mutant: bool = False,
) -> dict:
    weak = valid if weak is None else weak
    strong = valid if strong is None else strong
    rows = [{
        "mutant_id": "canonical",
        "family": "canonical",
        "original": {"passed": weak, "error": None},
        "plus": {"passed": strong, "error": None},
    }]
    if include_mutant:
        rows.append({
            "mutant_id": "numeric_constant:1",
            "family": "numeric_constant",
            "original": {"passed": True, "error": None},
            "plus": {"passed": False, "error": "strong rejection"},
        })
    return {
        "benchmark": "codecontests",
        "task_id": "task-1",
        "valid": valid,
        "rows": rows,
        "runner": {},
        "mutants_generated": int(include_mutant),
    }


def test_staged_selection_uses_first_reference_that_passes_both_oracles() -> None:
    calls = []

    def execute(execution_task, per_family):
        calls.append((execution_task.source, per_family))
        if execution_task.source == "bad":
            return result(valid=False, weak=True, strong=False)
        return result(valid=True, include_mutant=per_family > 0)

    observed = staged.stage_task(
        task("bad", "good", "unused"),
        execute=execute,
        mutants_per_family=2,
    )
    assert calls == [("bad", 0), ("good", 0), ("good", 2)]
    assert observed["valid"]
    assert observed["selected_source_candidate_index"] == 1
    assert len(observed["canonical_validation_attempts"]) == 2
    assert observed["canonical_validation_attempts"][0][
        "strong_error"
    ] is None
    assert observed["rows"][1]["family"] == "numeric_constant"


def test_second_validation_failure_does_not_search_posthoc_replacement() -> None:
    calls = []

    def execute(execution_task, per_family):
        calls.append((execution_task.source, per_family))
        if execution_task.source == "bad":
            return result(valid=False)
        if per_family == 0:
            return result(valid=True)
        return result(valid=False, weak=True, strong=False)

    observed = staged.stage_task(
        task("bad", "unstable", "would-pass"),
        execute=execute,
        mutants_per_family=2,
    )
    assert calls == [("bad", 0), ("unstable", 0), ("unstable", 2)]
    assert not observed["valid"]
    assert observed["selected_source_candidate_index"] == 1
    assert not observed["staged_reference_valid"]


def test_manifest_binds_candidate_order_tests_and_source_bytes() -> None:
    first = staged.candidate_manifest([task("a", "b")])
    reordered = staged.candidate_manifest([task("b", "a")])
    changed = staged.candidate_manifest([task("a", "c")])
    assert first["manifest_sha256"] != reordered["manifest_sha256"]
    assert first["manifest_sha256"] != changed["manifest_sha256"]
    assert first["rows"][0]["source_candidate_sha256"] == [
        hashlib.sha256(value.encode()).hexdigest() for value in ("a", "b")
    ]


def test_staged_evidence_hash_ignores_diagnostics_but_binds_semantics() -> None:
    base = result(valid=True, include_mutant=True)
    base.update({
        "selected_source_candidate_index": 0,
        "selected_source_sha256": "a" * 64,
        "canonical_validation_attempts": [{
            "candidate_index": 0,
            "source_sha256": "a" * 64,
            "valid": True,
            "weak_passed": True,
            "strong_passed": True,
            "elapsed_seconds": 1.0,
        }],
    })
    diagnostic = copy.deepcopy(base)
    diagnostic["runner"] = {"elapsed_seconds": 99.0}
    diagnostic["rows"][1]["plus"]["error"] = "different diagnostic"
    assert staged.staged_evidence_sha256([base]) == staged.staged_evidence_sha256(
        [diagnostic]
    )

    changed = copy.deepcopy(base)
    changed["rows"][1]["plus"]["passed"] = True
    assert staged.staged_evidence_sha256([base]) != staged.staged_evidence_sha256(
        [changed]
    )


def test_v3_protocol_is_frozen_before_train_execution() -> None:
    protocol = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "experiments"
            / "pattern_memory"
            / "codecontests_train_staged_holdout_protocol_v3.json"
        ).read_text(encoding="utf-8")
    )
    assert protocol["protocol_id"] == staged.PROTOCOL_ID
    assert protocol["status"] == "confirmatory_before_train_split_execution"
    assert protocol["target_benchmark"]["split"] == "train"
    assert protocol["target_benchmark"][
        "maximum_python3_reference_candidates"
    ] == 3
    assert protocol["success_gate"]["minimum_valid_target_tasks"] == 100
    assert protocol["success_gate"]["minimum_witnessable_target_tasks"] == 20
