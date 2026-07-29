from __future__ import annotations

import json
import hashlib
import subprocess
import sys

import pytest

import scripts.run_apps_stdin_differential_confirmation as apps
from scripts.run_apps_stdin_differential_confirmation import (
    APPS_STDIN_DRIVER,
    AppsTask,
    _candidates,
    _contract,
    _eligible_task,
    _weak_pass_metrics,
    load_selected_tasks,
    _payload,
    verify_dataset_file,
)

ROOT = apps.REPO_ROOT
DETAIL_ARTIFACT = (
    ROOT / "docs" / "experiments"
    / "apps_stdin_differential_confirmation_detail.json"
)
SUMMARY_ARTIFACT = (
    ROOT / "docs" / "experiments"
    / "apps_stdin_differential_confirmation_summary.json"
)
PAIR_ARTIFACT = (
    ROOT / "docs" / "experiments"
    / "apps_stdin_differential_pairs_20260729.jsonl"
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


def test_hash_selection_is_independent_of_input_row_order(tmp_path):
    rows = [row(problem_id=problem_id) for problem_id in range(50)]
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text(
        "\n".join(json.dumps(value) for value in rows) + "\n",
        encoding="utf-8",
    )
    second.write_text(
        "\n".join(json.dumps(value) for value in reversed(rows)) + "\n",
        encoding="utf-8",
    )
    selected_first, _ = load_selected_tasks(first, limit=10)
    selected_second, _ = load_selected_tasks(second, limit=10)
    assert [value.problem_id for value in selected_first] == [
        value.problem_id for value in selected_second
    ]


def test_input_receipt_fails_closed_on_same_size_byte_change(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "test.jsonl"
    source.write_bytes(b"frozen")
    monkeypatch.setattr(apps, "EXPECTED_DATASET_BYTES", 6)
    monkeypatch.setattr(
        apps,
        "EXPECTED_DATASET_SHA256",
        hashlib.sha256(b"frozen").hexdigest(),
    )
    verify_dataset_file(source)
    source.write_bytes(b"broken")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_dataset_file(source)


def test_conditional_yield_excludes_weak_failures_and_indeterminate_strong():
    metrics = _weak_pass_metrics([{
        "candidate_observations": [
            {
                "weak": {"status": "completed", "accepted": False},
                "strong": {"status": "completed", "accepted": False},
            },
            {
                "weak": {"status": "completed", "accepted": True},
                "strong": {"status": "timeout", "accepted": None},
            },
            {
                "weak": {"status": "completed", "accepted": True},
                "strong": {"status": "completed", "accepted": True},
            },
            {
                "weak": {"status": "completed", "accepted": True},
                "strong": {"status": "completed", "accepted": False},
            },
        ],
    }])
    assert metrics == {
        "weak_pass_pairs": 3,
        "weak_pass_with_completed_strong_pairs": 2,
        "weak_pass_strong_fail_pairs": 1,
        "conditional_gap_yield": 0.5,
    }


def test_tracked_detail_artifact_independently_recomputes_summary():
    detail = json.loads(DETAIL_ARTIFACT.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY_ARTIFACT.read_text(encoding="utf-8"))
    valid = [row for row in detail["raw"] if row["status"] == "valid"]
    observations = [
        candidate
        for task in valid
        for candidate in task["candidate_observations"]
    ]
    completed = [
        row for row in observations
        if row["weak"]["status"] == "completed"
        and row["strong"]["status"] == "completed"
    ]
    confirmed = sum(
        finding["tier"] == "confirmed"
        for task in valid for finding in task["findings"]
    )
    recomputed = _weak_pass_metrics(valid)
    assert len(completed) == 135
    assert confirmed == 7
    assert recomputed == {
        "weak_pass_pairs": 33,
        "weak_pass_with_completed_strong_pairs": 33,
        "weak_pass_strong_fail_pairs": 7,
        "conditional_gap_yield": 7 / 33,
    }
    for key, value in recomputed.items():
        assert detail["apps_stdin"][key] == value
    assert summary["metrics"]["weak_pass_count"] == 33
    assert summary["metrics"]["weak_pass_with_completed_strong_pairs"] == 33
    assert summary["metrics"]["weak_pass_strong_fail_pairs"] == 7
    assert summary["metrics"]["conditional_witness_yield"] == 7 / 33
    assert (
        summary["metrics"]["witness_yield_over_all_completed_pairs"]
        == 7 / 135
    )


def test_completed_pair_jsonl_recomputes_public_metrics():
    rows = [
        json.loads(line)
        for line in PAIR_ARTIFACT.read_text(encoding="utf-8").splitlines()
    ]
    confirmed = [row for row in rows if row["outcome"] == "confirmed"]
    weak_pass = [
        row for row in rows if row["weak"]["accepted"] is True
    ]
    assert len(rows) == 135
    assert len(confirmed) == 7
    assert len(weak_pass) == 33
    assert len({row["problem_id"] for row in confirmed}) == 4
    assert len(confirmed) / len(rows) == 7 / 135
    assert len(confirmed) / len(weak_pass) == 7 / 33
