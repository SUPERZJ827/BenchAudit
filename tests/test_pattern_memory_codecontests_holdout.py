import copy
import json
import subprocess
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_pattern_memory_codecontests_holdout as holdout
import run_pattern_memory_evalplus_lobo as base


def _dataset_row(name="task"):
    return {
        "name": name,
        "input_file": "",
        "output_file": "",
        "solutions": {
            "language": [2, 3, 3],
            "solution": ["cpp", "print(input())", "print('other')"],
        },
        "public_tests": {
            "input": ["hello\n"],
            "output": ["hello\n"],
        },
        "private_tests": {
            "input": ["world\n"],
            "output": ["world\n"],
        },
        "generated_tests": {
            "input": [f"{index}\n" for index in range(20)],
            "output": [f"{index}\n" for index in range(20)],
        },
        "source": 2,
    }


def test_codecontests_selection_is_frozen_and_uses_first_python3(monkeypatch):
    rows = [
        {**_dataset_row("file-io"), "input_file": "input.txt"},
        _dataset_row("kept"),
    ]
    monkeypatch.setattr(holdout, "load_dataset", lambda *args, **kwargs: rows)
    tasks = holdout.load_codecontests_tasks(
        dataset="pinned",
        revision="revision",
        split="test",
        candidate_limit=1,
        minimum_strong_cases=10,
        strong_case_cap=7,
    )
    assert len(tasks) == 1
    assert tasks[0].task_id == "kept"
    assert tasks[0].source == "print(input())"
    assert len(tasks[0].weak_cases) == 1
    assert len(tasks[0].strong_cases) == 7


def test_stdio_driver_uses_weak_and_strong_tests_independently():
    payload = {
        "mutants": [{
            "mutant_id": "candidate",
            "family": "numeric_constant",
            "source": "value = int(input())\nprint(value + 1)\n",
        }],
        "weak_cases": [{"input": "0\n", "output": "1\n"}],
        "strong_cases": [{"input": "2\n", "output": "2\n"}],
        "per_case_timeout": 1.0,
    }
    result = subprocess.run(
        [sys.executable, "-c", holdout.STDIO_DRIVER],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=5,
        check=True,
    )
    row = json.loads(result.stdout)["rows"][0]
    assert row["original"]["passed"] is True
    assert row["plus"]["passed"] is False


def _source_task(benchmark, task_id, witness_families):
    rows = [{
        "mutant_id": "canonical",
        "family": "canonical",
        "original": {"passed": True},
        "plus": {"passed": True},
    }]
    rows.extend({
        "mutant_id": f"{family}:0",
        "family": family,
        "original": {"passed": True},
        "plus": {"passed": False},
    } for family in witness_families)
    return {
        "benchmark": benchmark,
        "task_id": task_id,
        "valid": True,
        "rows": rows,
    }


def test_family_must_be_supported_by_every_source_benchmark():
    common = base.FAMILIES[0]
    source_one_only = base.FAMILIES[1]
    groups = {
        "one": [
            _source_task("one", "1a", {common, source_one_only}),
            _source_task("one", "1b", {common, source_one_only}),
        ],
        "two": [
            _source_task("two", "2a", {common}),
            _source_task("two", "2b", {common}),
        ],
    }
    supported, stats = holdout.independently_supported_families(
        groups,
        minimum_witness_tasks=2,
    )
    assert supported == [common]
    assert stats["one"][source_one_only]["witness_task_count"] == 2
    assert stats["two"][source_one_only]["witness_task_count"] == 0


def test_source_filter_does_not_mutate_input():
    allowed = base.FAMILIES[0]
    rejected = base.FAMILIES[1]
    original = [
        _source_task("one", "item", {allowed, rejected}),
    ]
    before = copy.deepcopy(original)
    filtered = holdout.filter_source_families(original, {allowed})
    assert original == before
    assert {
        row["family"] for row in filtered[0]["rows"]
    } == {"canonical", allowed}


def test_manifest_binds_solution_and_both_test_sets():
    task = holdout.StdioTask(
        benchmark="codecontests",
        task_id="item",
        source="print(input())",
        weak_cases=({"input": "a", "output": "a"},),
        strong_cases=({"input": "b", "output": "b"},),
        source_name="CODEFORCES",
    )
    first = holdout.task_manifest([task])
    changed = holdout.task_manifest([
        holdout.StdioTask(
            **{
                **task.__dict__,
                "strong_cases": ({"input": "b", "output": "c"},),
            }
        )
    ])
    assert first["manifest_sha256"] != changed["manifest_sha256"]


def test_evidence_hash_excludes_runtime_timing_but_binds_verdicts():
    row = _source_task("one", "item", {base.FAMILIES[0]})
    first = [{**row, "runner": {"elapsed_seconds": 1.0}}]
    second = [{**row, "runner": {"elapsed_seconds": 99.0}}]
    assert (
        holdout.evidence_results_sha256(first)
        == holdout.evidence_results_sha256(second)
    )
    changed = copy.deepcopy(second)
    changed[0]["rows"][1]["plus"]["passed"] = True
    assert (
        holdout.evidence_results_sha256(first)
        != holdout.evidence_results_sha256(changed)
    )


def test_success_gate_requires_every_non_reproducibility_check():
    direction = {
        "valid_target_tasks": 100,
        "witnessable_target_tasks": 20,
        "random_family_order_control": {
            "witness_yield": {
                "memory_minus_random_mean": 0.01,
                "empirical_one_sided_p": 0.01,
            },
            "task_recall": {"memory_minus_random_mean": 0.02},
        },
        "paired_bootstrap_D_minus_A": {
            "witness_yield": {"ci95": [0.001, 0.02]},
        },
    }
    protocol = {
        "success_gate": {
            "minimum_valid_target_tasks": 80,
            "minimum_witnessable_target_tasks": 10,
            "memory_minus_random_mean_gt": 0.0,
            "empirical_one_sided_p_lte": 0.05,
            "paired_bootstrap_ci95_lower_gt": 0.0,
        }
    }
    assert holdout.success_gate(
        direction, protocol
    )["all_non_reproducibility_checks_pass"]
    direction["random_family_order_control"]["witness_yield"][
        "empirical_one_sided_p"
    ] = 0.2
    assert not holdout.success_gate(
        direction, protocol
    )["all_non_reproducibility_checks_pass"]
