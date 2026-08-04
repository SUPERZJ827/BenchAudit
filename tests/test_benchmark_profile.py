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


# --- derivation ---------------------------------------------------------------

from benchcore.benchmark_profile import (  # noqa: E402
    build_profile_prompt,
    derive_profile,
    profile_benchmark,
)


class _Client:
    """Stands in for an LLM client; records what it was asked."""

    def __init__(self, response):
        self.response = response
        self.calls = 0
        self.last_prompt = None

    def chat_json(self, system, user):
        self.calls += 1
        self.last_prompt = user
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


GOOD = {
    "field_roles": {"task": "question", "gold": "targets", "choices": None, "context": None},
    "gold_semantics": {"shape": "set_of_equally_acceptable_answers", "why": "alternatives"},
    "components": ["open-ended question answering"],
}


def test_roles_naming_absent_fields_are_dropped():
    """A role bound to a missing field would silently read nothing."""
    client = _Client({**GOOD, "field_roles": {"task": "question", "gold": "no_such_field"}})
    profile = derive_profile(ROWS, client)
    assert profile.field_roles["task"] == "question"
    assert profile.field_roles["gold"] is None


def test_response_with_no_usable_role_is_rejected():
    client = _Client({**GOOD, "field_roles": {"task": "nope", "gold": "nope"}})
    assert derive_profile(ROWS, client) is None


def test_unknown_gold_shape_falls_back_to_unclear():
    client = _Client({**GOOD, "gold_semantics": {"shape": "invented", "why": "x"}})
    assert derive_profile(ROWS, client).gold_semantics["shape"] == "unclear"


def test_provider_failure_yields_no_profile():
    assert derive_profile(ROWS, _Client(RuntimeError("boom"))) is None


def test_non_mapping_response_yields_no_profile():
    assert derive_profile(ROWS, _Client(["not", "a", "mapping"])) is None


def test_derived_profiles_are_marked_inferred():
    assert derive_profile(ROWS, _Client(GOOD)).provenance == "llm_inferred"


def test_prompt_carries_shape_and_samples_but_stays_bounded():
    prompt = build_profile_prompt(ROWS)
    assert "question" in prompt and "value_shapes" in prompt
    assert len(prompt) <= 12000


def test_prompt_does_not_grow_with_the_stored_table(tmp_path):
    """The table is looked up in code and never shown to the model."""
    store = BenchmarkProfileStore(tmp_path / "profiles.jsonl")
    for index in range(50):
        store.put(_profile(f"filler-{index}"))
    client = _Client(GOOD)
    profile_benchmark(ROWS, store, client)
    assert all(f"filler-{index}" not in client.last_prompt for index in range(50))


def test_second_dataset_with_the_same_schema_costs_no_call(tmp_path):
    store = BenchmarkProfileStore(tmp_path / "profiles.jsonl")
    client = _Client(GOOD)
    _, first = profile_benchmark(ROWS, store, client)
    other = [dict(row, question="different wording entirely") for row in ROWS]
    _, second = profile_benchmark(other, store, client)
    assert (first, second) == ("derived", "cache_hit")
    assert client.calls == 1


def test_derivation_failure_leaves_the_table_untouched(tmp_path):
    store = BenchmarkProfileStore(tmp_path / "profiles.jsonl")
    _, status = profile_benchmark(ROWS, store, _Client(RuntimeError("boom")))
    assert status == "derivation_failed"
    assert len(store) == 0


def test_absent_client_is_reported_rather_than_guessed(tmp_path):
    store = BenchmarkProfileStore(tmp_path / "profiles.jsonl")
    profile, status = profile_benchmark(ROWS, store, None)
    assert (profile, status) == (None, "no_client")
