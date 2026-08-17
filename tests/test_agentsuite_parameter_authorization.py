import json

from benchcore.schema import BenchmarkItem
from scripts.run_agentsuite_parameter_authorization import (
    LEGITIMATE_SOURCES,
    parameter_candidate,
    reference_calls_and_parameters,
    validate_result_shape,
)
from scripts.score_agentsuite_parameter_authorization import ids_at_threshold


def valid_ungrounded(confidence=0.9):
    return {
        "parameters": [{
            "parameter_path": "book.date",
            "value": "2026-08-20",
            "source_status": "ungrounded",
            "source_evidence": "",
            "closed_world_rule": "unmentioned parameters must be omitted",
            "excluded_sources": sorted(LEGITIMATE_SOURCES),
            "material": True,
            "reason": "the date is invented",
            "confidence": confidence,
        }],
        "summary": "one ungrounded parameter",
    }


def test_candidate_is_fail_closed():
    assert parameter_candidate(valid_ungrounded())
    for key in ("parameter_path", "closed_world_rule", "reason"):
        broken = valid_ungrounded()
        broken["parameters"][0][key] = ""
        assert not parameter_candidate(broken)
    broken = valid_ungrounded()
    broken["parameters"][0]["excluded_sources"] = ["explicit_task_or_context"]
    assert not parameter_candidate(broken)
    broken = valid_ungrounded()
    broken["parameters"][0]["material"] = False
    assert not parameter_candidate(broken)
    assert not parameter_candidate(valid_ungrounded(0.59))


def test_non_ungrounded_states_never_become_candidates():
    for state in LEGITIMATE_SOURCES:
        result = valid_ungrounded()
        result["parameters"][0]["source_status"] = state
        assert not parameter_candidate(result)


def test_thresholds_are_offline_and_nested():
    rows = [
        {"item_id": "a", "operational_error": None, "result": valid_ungrounded(0.9)},
        {"item_id": "b", "operational_error": None, "result": valid_ungrounded(0.65)},
    ]
    assert ids_at_threshold(rows, 0.60) == {"a", "b"}
    assert ids_at_threshold(rows, 0.80) == {"a"}


def test_reference_parameters_from_normal_reference():
    item = BenchmarkItem(
        item_id="x",
        raw={"reference_solution": {"search": {"query": "x", "limit": 3}}},
    )
    reference, parameters = reference_calls_and_parameters(item)
    assert reference == {"search": {"query": "x", "limit": 3}}
    assert parameters == [
        {"parameter_path": "search.query", "value": "x"},
        {"parameter_path": "search.limit", "value": 3},
    ]


def test_reference_parameters_from_multiturn_calls():
    item = BenchmarkItem(
        item_id="x",
        raw={
            "reference_solution": [{"environment": "final state"}],
            "milestones": {"calls": ["[lookup(city='Paris')]", "[book(id='F1', seats=2)]"]},
        },
    )
    reference, parameters = reference_calls_and_parameters(item)
    assert len(reference) == 2
    assert parameters == [
        {"parameter_path": "call[1].lookup.city", "value": "Paris"},
        {"parameter_path": "call[2].book.id", "value": "F1"},
        {"parameter_path": "call[2].book.seats", "value": 2},
    ]


def test_shape_validation_requires_all_paths_in_order():
    expected = [{"parameter_path": "f.x", "value": 1}]
    result = valid_ungrounded()
    result["parameters"][0]["parameter_path"] = "f.x"
    assert validate_result_shape(result, expected) is None
    result["parameters"] = []
    assert validate_result_shape(result, expected)
