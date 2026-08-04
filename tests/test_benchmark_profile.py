"""Lookup is code, not a prompt.

The fingerprint is computed from the data and matched exactly, so the stored
table never enters a prompt and prompt size does not grow with the number of
benchmarks profiled.  Exact matching is deliberate: a miss costs one small
call, while a loose match risks reading one benchmark with another's
assumptions.
"""

from __future__ import annotations

import json

from benchcore.benchmark_profile import (
    BenchmarkProfile,
    BenchmarkProfileStore,
    schema_fingerprint,
    schema_shape,
)

ROWS = [
    {"id": "1", "question": "q", "targets": ["a", "b"], "n": 3},
    {"id": "2", "question": "q2", "targets": ["c"], "n": 4},
]


def test_fingerprint_ignores_values():
    other = [dict(row, question="entirely different text") for row in ROWS]
    assert schema_fingerprint(ROWS) == schema_fingerprint(other)


def test_fingerprint_tracks_field_names():
    renamed = [{("prompt" if k == "question" else k): v for k, v in row.items()} for row in ROWS]
    assert schema_fingerprint(ROWS) != schema_fingerprint(renamed)


def test_fingerprint_tracks_value_shape():
    flattened = [dict(row, targets="a") for row in ROWS]
    assert schema_fingerprint(ROWS) != schema_fingerprint(flattened)


def test_optional_fields_seen_in_any_row_belong_to_the_schema():
    shape = schema_shape([{"a": 1}, {"a": 1, "b": "x"}])
    assert set(shape) == {"a", "b"}


def test_mixed_types_are_all_recorded():
    shape = schema_shape([{"a": 1}, {"a": "x"}])
    assert shape["a"] == ["int", "str"]


def test_fingerprint_is_order_independent():
    reordered = [{k: row[k] for k in reversed(list(row))} for row in ROWS]
    assert schema_fingerprint(ROWS) == schema_fingerprint(reordered)


def _profile(fingerprint: str) -> BenchmarkProfile:
    return BenchmarkProfile(
        fingerprint=fingerprint,
        field_names=("id", "question", "targets"),
        field_roles={"task": "question", "gold": "targets"},
        gold_semantics={"shape": "set_of_equally_acceptable_answers"},
    )


def test_miss_then_hit(tmp_path):
    store = BenchmarkProfileStore(tmp_path / "profiles.jsonl")
    fingerprint, profile = store.lookup(ROWS)
    assert profile is None
    store.put(_profile(fingerprint))
    _, again = store.lookup(ROWS)
    assert again is not None
    assert again.gold_semantics["shape"] == "set_of_equally_acceptable_answers"


def test_store_survives_reload(tmp_path):
    path = tmp_path / "profiles.jsonl"
    fingerprint = schema_fingerprint(ROWS)
    BenchmarkProfileStore(path).put(_profile(fingerprint))
    assert BenchmarkProfileStore(path).get(fingerprint) is not None


def test_existing_entry_is_never_silently_replaced(tmp_path):
    """An audit must not change how earlier audits read the same schema."""
    path = tmp_path / "profiles.jsonl"
    store = BenchmarkProfileStore(path)
    fingerprint = schema_fingerprint(ROWS)
    assert store.put(_profile(fingerprint)) is True
    replacement = BenchmarkProfile(
        fingerprint=fingerprint, field_names=(), field_roles={"gold": "something_else"}
    )
    assert store.put(replacement) is False
    assert store.get(fingerprint).field_roles["gold"] == "targets"


def test_malformed_rows_are_skipped_rather_than_trusted(tmp_path):
    path = tmp_path / "profiles.jsonl"
    fingerprint = schema_fingerprint(ROWS)
    path.write_text(
        "not json\n"
        + json.dumps({"no_fingerprint": True})
        + "\n"
        + json.dumps(_profile(fingerprint).to_dict())
        + "\n",
        encoding="utf-8",
    )
    store = BenchmarkProfileStore(path)
    assert len(store) == 1
    assert store.get(fingerprint) is not None


def test_profiles_default_to_inferred_provenance():
    """Promotion downgrades findings that depend on an inferred mapping."""
    assert _profile("x").provenance == "llm_inferred"
