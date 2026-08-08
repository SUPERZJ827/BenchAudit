"""The profile refines an inferred mapping; it never overrides a resolved one.

Name-list inference leaves a role unresolved whenever a benchmark uses field
names nobody listed, and the default five checkers then run against nothing.
A profile fills those gaps.  It does not replace a role inference already
resolved: the profile is itself a model judgement, and silently redirecting
what every later check reads on the strength of one call is the failure this
system exists to catch.
"""

from __future__ import annotations

import argparse
import json

from benchcore.benchmark_profile import BenchmarkProfile, BenchmarkProfileStore
from benchcore.cli import _apply_benchmark_profile, _remote_egress_manifest
from benchcore.loader import load_mapping

ODD_ROWS = [
    {"uid": "1", "problem_text": "how many?", "expected_result": "5"},
    {"uid": "2", "problem_text": "how much?", "expected_result": "6"},
]


def _args(store_path, **overrides):
    base = dict(
        benchmark_profiles=str(store_path),
        no_benchmark_profile=False,
        llm_config=None,
        llm_cache=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _egress_args(**overrides):
    base = dict(
        llm_config="cfg.json", no_benchmark_profile=False,
        cross_artifact_audit=False, execution_evaluator_audit=False,
        llm_audit=False, swe_leak_llm_confirm=False,
        value_recompute_audit=False, workspace_rubric_grounding_audit=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _seed(store_path, roles):
    store = BenchmarkProfileStore(store_path)
    fingerprint, _ = store.lookup(ODD_ROWS)
    store.put(
        BenchmarkProfile(
            fingerprint=fingerprint,
            field_names=("uid", "problem_text", "expected_result"),
            field_roles=roles,
            task_shape="open_ended_qa",
            scoring={"comparison": "numeric_tolerance"},
        )
    )


def test_name_list_inference_leaves_unusual_fields_unresolved():
    mapping = load_mapping(None, ODD_ROWS)
    assert mapping.task is None and mapping.gold is None


def test_profile_fills_roles_inference_could_not_resolve(tmp_path):
    path = tmp_path / "profiles.jsonl"
    _seed(path, {"task": "problem_text", "gold": "expected_result"})
    mapping = load_mapping(None, ODD_ROWS)
    mapping, meta = _apply_benchmark_profile(_args(path), ODD_ROWS, mapping)
    assert mapping.task == "problem_text"
    assert mapping.gold == "expected_result"
    assert meta["roles_filled"] == {"task": "problem_text", "gold": "expected_result"}


def test_a_dimension_the_profile_withheld_is_reported(tmp_path):
    """A dimension that fell back is indistinguishable from one nobody
    contested unless the run says which it was."""
    path = tmp_path / "profiles.jsonl"
    store = BenchmarkProfileStore(path)
    fingerprint, _ = store.lookup(ODD_ROWS)
    store.put(
        BenchmarkProfile(
            fingerprint=fingerprint,
            field_names=("uid", "problem_text", "expected_result"),
            field_roles={"task": "problem_text", "gold": "expected_result"},
            scoring={"comparison": "other"},
            disputed={"scoring.comparison": "votes split between exact_match, other"},
        )
    )
    _, meta = _apply_benchmark_profile(_args(path), ODD_ROWS, load_mapping(None, ODD_ROWS))
    assert meta["disputed"] == {
        "scoring.comparison": "votes split between exact_match, other"
    }


def test_profile_does_not_override_a_resolved_role(tmp_path):
    path = tmp_path / "profiles.jsonl"
    rows = [{"id": "1", "task": "q", "gold": "5"}]
    store = BenchmarkProfileStore(path)
    fingerprint, _ = store.lookup(rows)
    store.put(
        BenchmarkProfile(
            fingerprint=fingerprint,
            field_names=("id", "task", "gold"),
            field_roles={"task": "id", "gold": "gold"},
        )
    )
    mapping = load_mapping(None, rows)
    assert mapping.task == "task"
    mapping, meta = _apply_benchmark_profile(_args(path), rows, mapping)
    assert mapping.task == "task"
    assert meta["roles_disagreeing"]["task"] == {"inferred": "task", "profile": "id"}


def test_roles_naming_absent_fields_are_not_applied(tmp_path):
    path = tmp_path / "profiles.jsonl"
    _seed(path, {"task": "problem_text", "gold": "no_such_field"})
    mapping = load_mapping(None, ODD_ROWS)
    mapping, meta = _apply_benchmark_profile(_args(path), ODD_ROWS, mapping)
    assert mapping.task == "problem_text"
    assert mapping.gold is None


def test_opting_out_leaves_the_mapping_untouched(tmp_path):
    path = tmp_path / "profiles.jsonl"
    _seed(path, {"task": "problem_text", "gold": "expected_result"})
    mapping = load_mapping(None, ODD_ROWS)
    mapping, meta = _apply_benchmark_profile(
        _args(path, no_benchmark_profile=True), ODD_ROWS, mapping
    )
    assert mapping.task == "problem_text", "an existing entry is still honoured"


def test_absent_store_and_client_changes_nothing(tmp_path):
    mapping = load_mapping(None, ODD_ROWS)
    mapping, meta = _apply_benchmark_profile(
        _args(tmp_path / "missing.jsonl"), ODD_ROWS, mapping
    )
    assert (mapping.task, mapping.gold) == (None, None)
    assert meta["status"] == "no_client"


def test_profiling_is_declared_in_the_egress_manifest():
    """Profiling transmits a sample before any checker runs."""
    args = _egress_args(no_benchmark_profile=False)
    manifest = _remote_egress_manifest(
        args, use_grounded_rubric=False, use_rubric_contract=False,
        use_rubric_coverage=False,
    )
    assert any(entry["checker"] == "benchmark_schema_profile" for entry in manifest)


def test_no_profiling_means_no_egress_entry():
    args = _egress_args(no_benchmark_profile=True)
    manifest = _remote_egress_manifest(
        args, use_grounded_rubric=False, use_rubric_contract=False,
        use_rubric_coverage=False,
    )
    assert not any(entry["checker"] == "benchmark_schema_profile" for entry in manifest)
