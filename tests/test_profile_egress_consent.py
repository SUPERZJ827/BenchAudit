"""Profiling is the first thing that sends data, so consent must precede it.

The gate that asks whether benchmark rows may leave the machine ran after the
schema profiler had already sent a sample: the run ended in the "pass
--allow-remote-data-egress only after confirming ..." error, with the calls
made and the derived profile written to disk.  Consent that arrives after the
data has left is not consent.

The same ordering made the gate wrong in the other direction.  A schema already
in the store is answered from disk without a client, yet the flag was demanded
anyway -- which is why the store held one entry and profiles almost never
applied to a real audit.
"""

from __future__ import annotations

import argparse

import pytest

from benchcore.benchmark_profile import BenchmarkProfile, BenchmarkProfileStore
from benchcore.cli import (
    _apply_benchmark_profile,
    _enforce_remote_egress_policy,
    _profile_would_derive,
    _remote_egress_manifest,
)
from benchcore.loader import load_mapping

ROWS = [
    {"uid": "1", "problem_text": "how many?", "expected_result": "5"},
    {"uid": "2", "problem_text": "how much?", "expected_result": "6"},
]


def _args(store_path, **overrides):
    base = dict(
        benchmark_profiles=str(store_path),
        no_benchmark_profile=False,
        llm_config="cfg.json",
        llm_cache=None,
        llm_dry_run=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _egress_args(**overrides):
    base = dict(
        llm_config="cfg.json", no_benchmark_profile=False,
        cross_artifact_audit=False, execution_evaluator_audit=False,
        llm_audit=False, swe_leak_llm_confirm=False,
        value_recompute_audit=False, workspace_rubric_grounding_audit=False,
        llm_dry_run=False, allow_remote_data_egress=False,
        allow_workspace_data_egress=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _manifest(args, **overrides):
    base = dict(
        use_grounded_rubric=False, use_rubric_contract=False,
        use_rubric_coverage=False, profile_would_derive=True,
    )
    base.update(overrides)
    return _remote_egress_manifest(args, **base)


def _seed(store_path):
    store = BenchmarkProfileStore(store_path)
    fingerprint, _ = store.lookup(ROWS)
    store.put(
        BenchmarkProfile(
            fingerprint=fingerprint,
            field_names=("uid", "problem_text", "expected_result"),
            field_roles={"task": "problem_text", "gold": "expected_result"},
        )
    )


# --- whether a call will happen at all ----------------------------------------


def test_an_unknown_schema_would_have_to_ask_a_model(tmp_path):
    assert _profile_would_derive(_args(tmp_path / "profiles.jsonl"), ROWS) is True


def test_a_stored_schema_is_answered_from_disk(tmp_path):
    path = tmp_path / "profiles.jsonl"
    _seed(path)
    assert _profile_would_derive(_args(path), ROWS) is False


def test_opting_out_of_profiling_sends_nothing(tmp_path):
    args = _args(tmp_path / "profiles.jsonl", no_benchmark_profile=True)
    assert _profile_would_derive(args, ROWS) is False


def test_without_a_configured_model_nothing_can_be_sent(tmp_path):
    args = _args(tmp_path / "profiles.jsonl", llm_config=None)
    assert _profile_would_derive(args, ROWS) is False


def test_a_dry_run_sends_nothing(tmp_path):
    """--llm-dry-run exists to make a run cost nothing; profiling ignored it."""
    args = _args(tmp_path / "profiles.jsonl", llm_dry_run=True)
    assert _profile_would_derive(args, ROWS) is False


# --- what the manifest declares -----------------------------------------------


def test_a_schema_that_must_be_derived_is_declared():
    manifest = _manifest(_egress_args(), profile_would_derive=True)
    assert any(entry["checker"] == "benchmark_schema_profile" for entry in manifest)


def test_a_cached_schema_declares_no_outbound_data():
    manifest = _manifest(_egress_args(), profile_would_derive=False)
    assert not any(entry["checker"] == "benchmark_schema_profile" for entry in manifest)


# --- the gate -----------------------------------------------------------------


def test_deriving_a_profile_without_authorization_is_refused():
    manifest = _manifest(_egress_args(), profile_would_derive=True)
    with pytest.raises(ValueError, match="allow-remote-data-egress"):
        _enforce_remote_egress_policy(_egress_args(), manifest)


def test_a_cached_profile_needs_no_authorization():
    """Nothing leaves the machine, so nothing needs to be consented to."""
    manifest = _manifest(_egress_args(), profile_would_derive=False)
    metadata = _enforce_remote_egress_policy(_egress_args(), manifest)
    assert metadata["network_egress_possible"] is False


def test_a_cached_profile_still_refuses_a_pointless_authorization():
    """--allow-remote-data-egress with nothing to send stays an error, as it
    already is for every other checker."""
    manifest = _manifest(_egress_args(), profile_would_derive=False)
    with pytest.raises(ValueError, match="requires an enabled LLM-backed audit"):
        _enforce_remote_egress_policy(
            _egress_args(allow_remote_data_egress=True), manifest
        )


# --- and the profiler itself --------------------------------------------------


def test_a_cached_profile_is_applied_without_a_model(tmp_path):
    """The store answers, so no client is built and no key is needed."""
    path = tmp_path / "profiles.jsonl"
    _seed(path)
    mapping, meta = _apply_benchmark_profile(
        _args(path, llm_config="does-not-exist.json"), ROWS, load_mapping(None, ROWS)
    )
    assert meta["status"] == "cache_hit"
    assert mapping.task == "problem_text"
