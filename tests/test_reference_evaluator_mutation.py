from __future__ import annotations

from benchcore.reference_evaluator_mutation import (
    MUTATION_SENTINEL,
    ReferenceEvaluatorMutationChecker,
    corrupt,
    parse_path,
    replace_at,
    scalar_positions,
)
from benchcore.schema import BenchmarkItem


def test_corrupt_keeps_the_json_type_and_changes_the_value() -> None:
    assert corrupt(True) == ("boolean_negated", False)
    assert corrupt(34.0522)[0] == "numeric_offset"
    assert corrupt(34.0522)[1] != 34.0522
    assert corrupt(2024) == ("numeric_offset", 3023)
    assert corrupt("Summary") == ("string_replaced", MUTATION_SENTINEL)


def test_corrupt_prefers_another_declared_enum_member() -> None:
    spec = {"enum": ["2021-06", "2022-06"]}
    assert corrupt("2022-06", spec) == ("enum_swapped", "2021-06")


def test_corrupt_skips_containers_because_structure_is_scored_separately() -> None:
    assert corrupt({"a": 1}) is None
    assert corrupt([1, 2]) is None


def test_scalar_positions_reaches_values_nested_in_lists_and_objects() -> None:
    arguments = {"dataSources": [{"sourceId": "1", "details": {"accessProtocol": "HTTPS"}}]}
    paths = {path for path, _, _ in scalar_positions(arguments)}
    assert paths == {".dataSources[0].sourceId", ".dataSources[0].details.accessProtocol"}


def test_replace_at_rewrites_only_the_addressed_leaf() -> None:
    arguments = {"dataSources": [{"sourceId": "1", "sourceType": "API"}]}
    updated = replace_at(arguments, parse_path(".dataSources[0].sourceId"), "2")
    assert updated == {"dataSources": [{"sourceId": "2", "sourceType": "API"}]}
    assert arguments["dataSources"][0]["sourceId"] == "1"


def build_item() -> BenchmarkItem:
    return BenchmarkItem(
        item_id="probe::1",
        raw={"reference_solution": {"tool": {"latitude": 34.0522, "label": "Beijing"}}},
        context={"available_functions": [{
            "name": "tool",
            "parameters": {"properties": {"latitude": {"type": "number"},
                                          "label": {"type": "string"}}},
        }]},
    )


def test_checker_reports_only_the_parameters_whose_corruption_survives() -> None:
    def replay(item, candidate):
        latitude = candidate["tool"]["latitude"]
        label = candidate["tool"]["label"]
        # A stand-in evaluator that scores the label but ignores the number.
        return label == "Beijing", {"latitude": latitude}

    findings = list(ReferenceEvaluatorMutationChecker(replay, evaluator_sha256="ab").check(build_item()))
    assert len(findings) == 1
    unscored = findings[0].evidence["unscored_parameters"]
    assert [entry["parameter_path"] for entry in unscored] == ["tool.latitude"]
    assert unscored[0]["original_value"] == 34.0522
    assert unscored[0]["mutation"] == "numeric_offset"
    assert findings[0].evidence["evaluator_sha256"] == "ab"


def test_checker_stays_silent_when_the_evaluator_scores_every_parameter() -> None:
    def strict(item, candidate):
        return candidate == {"tool": {"latitude": 34.0522, "label": "Beijing"}}, None

    assert list(ReferenceEvaluatorMutationChecker(strict, evaluator_sha256="ab").check(build_item())) == []


def test_checker_abstains_when_the_reference_itself_fails_its_evaluator() -> None:
    def rejects_everything(item, candidate):
        return False, {"error": "baseline rejected"}

    checker = ReferenceEvaluatorMutationChecker(rejects_everything, evaluator_sha256="ab")
    assert list(checker.check(build_item())) == []


def test_eligibility_requires_a_structured_reference() -> None:
    checker = ReferenceEvaluatorMutationChecker(lambda item, candidate: (True, None), evaluator_sha256="ab")
    assert checker.audit_eligibility(build_item()).eligible
    bare = BenchmarkItem(item_id="probe::2", raw={}, context={})
    assert not checker.audit_eligibility(bare).eligible
