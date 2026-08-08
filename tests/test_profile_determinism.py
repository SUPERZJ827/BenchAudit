"""A profile decides how every later check reads the data, so it must not move.

Measured on real data: the same schema, the same model and temperature 0 gave
``exact_match`` at one hour and ``other`` at the next -- five identical calls
inside each batch, opposite verdicts across them.  On one 300-record benchmark
that single value was the difference between 26 findings and 2.

Three defences, in the order they matter.  A claim the rows do not support is
dropped, which is pure code and catches exactly that failure.  The prompt that
produced a profile identifies it, so a stored answer to a question we no longer
ask expires.  Votes see different rows, and a dimension they disagree on falls
back rather than being reported as settled.
"""

from __future__ import annotations

import json

from benchcore.benchmark_profile import (
    BenchmarkProfileStore,
    PROMPT_FINGERPRINT,
    derive_profile,
    profile_benchmark,
    schema_fingerprint,
)

NUMERIC_ROWS = [
    {"question": "2 apples plus 3?", "answer": "5"},
    {"question": "half of 7?", "answer": "3.5"},
]
TEXT_ROWS = [
    {"question": "capital of France?", "answer": "Paris"},
    {"question": "capital of Japan?", "answer": "Tokyo"},
]
ALTERNATIVES_ROWS = [
    {"question": "capital of France?", "answer": ["Paris", "paris"]},
    {"question": "capital of Japan?", "answer": ["Tokyo"]},
]
RUBRIC_ROWS = [
    {"brief": "write a memo", "criteria": "covers cost and risk"},
    {"brief": "write a plan", "criteria": "names owners"},
]


def _response(**overrides):
    base = {
        "field_roles": {"task": "question", "gold": "answer"},
        "task_shape": "open_ended_qa",
        "answer_cardinality": "single",
        "modality": "text",
        "scoring": {"comparison": "exact_match", "why": "one recorded answer"},
        "components": ["question answering"],
    }
    base.update(overrides)
    return base


class _Votes:
    """Returns a different answer per call, so votes can be made to disagree."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def chat_json(self, system, user):
        self.prompts.append(user)
        return self.responses[(len(self.prompts) - 1) % len(self.responses)]


def _same(response):
    return _Votes(response)


# --- a claim the rows do not support ------------------------------------------


def test_exact_match_is_dropped_when_every_answer_is_a_number():
    """The observed flip: nothing in numeric rows shows character-exactness."""
    profile = derive_profile(NUMERIC_ROWS, _same(_response()))
    assert profile.scoring["comparison"] == "other"


def test_dropping_a_claim_records_why():
    profile = derive_profile(NUMERIC_ROWS, _same(_response()))
    assert "number" in profile.disputed["scoring.comparison"]


def test_exact_match_survives_on_answers_that_are_not_numbers():
    profile = derive_profile(TEXT_ROWS, _same(_response()))
    assert profile.scoring["comparison"] == "exact_match"
    assert profile.disputed == {}


def test_numeric_tolerance_is_dropped_when_no_answer_is_a_number():
    response = _response(scoring={"comparison": "numeric_tolerance", "why": "sums"})
    profile = derive_profile(TEXT_ROWS, _same(response))
    assert profile.scoring["comparison"] == "other"


def test_any_of_accepted_is_dropped_when_each_record_holds_one_answer():
    response = _response(scoring={"comparison": "any_of_accepted", "why": "wordings"})
    profile = derive_profile(TEXT_ROWS, _same(response))
    assert profile.scoring["comparison"] == "other"


def test_any_of_accepted_survives_where_a_record_holds_alternatives():
    response = _response(scoring={"comparison": "any_of_accepted", "why": "wordings"})
    profile = derive_profile(ALTERNATIVES_ROWS, _same(response))
    assert profile.scoring["comparison"] == "any_of_accepted"


def test_rubric_graded_is_dropped_when_no_field_holds_criteria():
    response = _response(scoring={"comparison": "rubric_graded", "why": "criteria"})
    profile = derive_profile(TEXT_ROWS, _same(response))
    assert profile.scoring["comparison"] == "other"


def test_rubric_graded_survives_where_a_rubric_field_was_identified():
    response = _response(
        field_roles={"task": "brief", "rubric": "criteria"},
        task_shape="artifact_production",
        scoring={"comparison": "rubric_graded", "why": "criteria"},
    )
    profile = derive_profile(RUBRIC_ROWS, _same(response))
    assert profile.scoring["comparison"] == "rubric_graded"


# --- votes --------------------------------------------------------------------


def test_a_profile_is_voted_on_rather_than_asked_once():
    client = _same(_response())
    derive_profile(TEXT_ROWS, client)
    assert len(client.prompts) == 3


def test_each_vote_sees_different_rows():
    """Identical calls agreed 5/5 while flipping across batches; only the
    rows shown decorrelate them."""
    rows = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(9)]
    client = _same(_response())
    derive_profile(rows, client)
    assert len(set(client.prompts)) == 3


def test_a_dimension_the_votes_disagree_on_falls_back():
    client = _Votes(
        _response(task_shape="open_ended_qa"),
        _response(task_shape="code_generation"),
        _response(task_shape="open_ended_qa"),
    )
    profile = derive_profile(TEXT_ROWS, client)
    assert profile.task_shape == "other"


def test_a_disagreement_names_the_dimension_and_the_answers():
    client = _Votes(
        _response(task_shape="open_ended_qa"),
        _response(task_shape="code_generation"),
        _response(task_shape="open_ended_qa"),
    )
    profile = derive_profile(TEXT_ROWS, client)
    reason = profile.disputed["task_shape"]
    assert "open_ended_qa" in reason and "code_generation" in reason


def test_a_role_the_votes_disagree_on_is_left_unbound():
    """An unbound role leaves the caller on its own inference; a wrong one
    silently redirects every later check."""
    client = _Votes(
        _response(field_roles={"task": "question", "gold": "answer"}),
        _response(field_roles={"task": "question", "gold": "question"}),
        _response(field_roles={"task": "question", "gold": "answer"}),
    )
    profile = derive_profile(TEXT_ROWS, client)
    assert profile.field_roles["gold"] is None
    assert "field_roles.gold" in profile.disputed
    assert profile.field_roles["task"] == "question"


def test_a_profile_whose_every_role_is_contested_is_rejected():
    """Nothing survives to read the data by, so the caller keeps its own
    mapping rather than being handed an empty one."""
    client = _Votes(
        _response(field_roles={"task": "question", "gold": "answer"}),
        _response(field_roles={"task": "answer", "gold": "question"}),
        _response(field_roles={"task": "question", "gold": "answer"}),
    )
    assert derive_profile(TEXT_ROWS, client) is None


def test_roles_the_votes_agree_on_survive_a_disagreement_elsewhere():
    client = _Votes(
        _response(modality="text"),
        _response(modality="text_and_code"),
        _response(modality="text"),
    )
    profile = derive_profile(TEXT_ROWS, client)
    assert profile.field_roles["task"] == "question"
    assert profile.modality == "other"


def test_a_profile_no_vote_could_use_is_still_rejected():
    client = _Votes(
        _response(field_roles={"task": "nope"}),
        _response(field_roles={"gold": "also_nope"}),
        _response(field_roles={"task": "still_nope"}),
    )
    assert derive_profile(TEXT_ROWS, client) is None


# --- the prompt that produced it ----------------------------------------------


def test_a_stored_profile_records_which_prompt_produced_it(tmp_path):
    store = BenchmarkProfileStore(tmp_path / "profiles.jsonl")
    profile_benchmark(TEXT_ROWS, store, _same(_response()))
    written = json.loads((tmp_path / "profiles.jsonl").read_text(encoding="utf-8"))
    assert written["prompt_fingerprint"] == PROMPT_FINGERPRINT


def test_a_profile_from_a_prompt_we_no_longer_ask_is_not_served(tmp_path):
    """Nothing expired the answer to a question we since rewrote, so the
    repository's one stored profile was still an old prompt's verdict."""
    path = tmp_path / "profiles.jsonl"
    store = BenchmarkProfileStore(path)
    profile_benchmark(TEXT_ROWS, store, _same(_response()))
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["prompt_fingerprint"] = "from-an-older-prompt"
    path.write_text(json.dumps(stale) + "\n", encoding="utf-8")
    assert BenchmarkProfileStore(path).get(schema_fingerprint(TEXT_ROWS)) is None


def test_a_superseded_profile_is_rederived_rather_than_reused(tmp_path):
    path = tmp_path / "profiles.jsonl"
    profile_benchmark(TEXT_ROWS, BenchmarkProfileStore(path), _same(_response()))
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["prompt_fingerprint"] = "from-an-older-prompt"
    path.write_text(json.dumps(stale) + "\n", encoding="utf-8")
    _, status = profile_benchmark(TEXT_ROWS, BenchmarkProfileStore(path), _same(_response()))
    assert status == "derived"
