from __future__ import annotations

import json
import subprocess
import sys

import pytest

from scripts.run_apps_stdin_differential_confirmation import (
    APPS_STDIN_DRIVER,
    AppsTask,
    _candidates,
    _contract,
    _eligible_task,
    _payload,
)


def row(
    *,
    problem_id: int = 7,
    inputs=None,
    outputs=None,
    fn_name=None,
    source: str = "print(input())\n",
):
    if inputs is None:
        inputs = [["a"], ["b"], ["c"], ["d"], ["e"]]
    if outputs is None:
        outputs = ["a", "b", "c", "d", "e"]
    return {
        "id": problem_id,
        "input_output": json.dumps({
            "inputs": inputs,
            "outputs": outputs,
            "fn_name": fn_name,
        }),
        "solutions": json.dumps([source]),
        "difficulty": "introductory",
    }


def execute_driver(source: str, tests, *, timeout=0.5):
    payload = {
        "candidates": [{
            "candidate_id": "candidate",
            "source": source,
            "source_sha256": "fixture",
        }],
        "weak_tests": tests,
        "strong_tests": tests,
        "per_case_timeout": timeout,
    }
    completed = subprocess.run(
        [sys.executable, "-c", APPS_STDIN_DRIVER],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=5,
        check=True,
    )
    return json.loads(completed.stdout)["rows"][0]


def test_static_eligibility_accepts_stdin_task_with_five_cases():
    task, reason = _eligible_task(row())
    assert reason == "eligible"
    assert task is not None
    assert task.problem_id == 7
    assert len(task.tests) == 5


def test_static_eligibility_rejects_call_based_task():
    task, reason = _eligible_task(row(fn_name="solve"))
    assert task is None
    assert reason == "call_based"


@pytest.mark.parametrize("count", [0, 4, 21])
def test_static_eligibility_enforces_frozen_case_count(count):
    task, reason = _eligible_task(row(
        inputs=[["x"]] * count,
        outputs=["x"] * count,
    ))
    assert task is None
    assert reason == "case_count_out_of_range"


def test_driver_accepts_exact_and_whitespace_equivalent_output():
    tests = [{"input": ["4"], "output": "4\n"}]
    result = execute_driver("print('  ' + input() + '  ')\n", tests)
    assert result["weak"] == {
        "status": "completed", "accepted": True, "detail": None,
    }


def test_driver_accepts_fixed_tolerance_numeric_output():
    tests = [{"input": [""], "output": "0.333333"}]
    result = execute_driver("print(1/3)\n", tests)
    assert result["weak"]["accepted"] is True


def test_driver_accepts_only_equal_token_multisets_when_order_changes():
    tests = [{"input": [""], "output": "a b b"}]
    accepted = execute_driver("print('b a b')\n", tests)
    rejected = execute_driver("print('b a a')\n", tests)
    assert accepted["weak"]["accepted"] is True
    assert rejected["weak"]["accepted"] is False


def test_driver_treats_timeout_as_indeterminate():
    tests = [{"input": [""], "output": "done"}]
    result = execute_driver("while True: pass\n", tests, timeout=0.05)
    assert result["weak"] == {
        "status": "timeout",
        "accepted": None,
        "detail": "case_timeout",
    }


def test_driver_treats_signal_as_indeterminate_not_semantic_failure():
    tests = [{"input": [""], "output": "done"}]
    result = execute_driver(
        "import os, signal\nos.kill(os.getpid(), signal.SIGTERM)\n",
        tests,
    )
    assert result["weak"]["status"] == "error"
    assert result["weak"]["accepted"] is None


def test_contract_declares_distinct_oracles_and_binds_manifest():
    task = AppsTask(
        problem_id=9,
        source="x = int(input())\nprint(x + 1)\n",
        tests=tuple(
            {"input": [str(index)], "output": str(index + 1)}
            for index in range(5)
        ),
        difficulty="introductory",
    )
    candidates = _candidates(task, 1)
    contract = _contract(task, candidates)
    assert contract["weak_oracle_identity"] != contract["strong_oracle_identity"]
    assert contract["candidate_manifest"] == [
        candidate.to_evidence() for candidate in candidates
    ]


def test_payload_preserves_strict_test_prefix_without_reordering():
    task = AppsTask(
        problem_id=10,
        source="print(input())\n",
        tests=tuple(
            {"input": [str(index)], "output": str(index)}
            for index in range(5)
        ),
        difficulty="introductory",
    )
    payload, _ = _payload(
        task,
        per_family=1,
        image="fixture",
        per_case_timeout=2.0,
        task_timeout=120.0,
    )
    assert payload["weak_tests"] == list(task.tests[:2])
    assert payload["strong_tests"] == list(task.tests)
    assert payload["strong_tests"][:2] == payload["weak_tests"]
