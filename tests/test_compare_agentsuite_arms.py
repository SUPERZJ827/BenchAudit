from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/compare_agentsuite_arms.py"
SPEC = importlib.util.spec_from_file_location("compare_agentsuite_arms", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_candidate_ids_accepts_every_allowed_method() -> None:
    report = {
        "violations": [
            {"item_id": "a", "detection_method": "llm_cross_artifact_consistency"},
            {"item_id": "b", "detection_method": "reference_schema_validation"},
            {"item_id": "c", "detection_method": "solver_first_diff"},
        ]
    }
    single = frozenset({"llm_cross_artifact_consistency"})
    both = frozenset({"llm_cross_artifact_consistency", "reference_schema_validation"})
    assert MODULE.candidate_ids(report, single) == {"a"}
    assert MODULE.candidate_ids(report, both) == {"a", "b"}


def test_candidate_ids_still_drops_non_substantive_and_audit_failures() -> None:
    allowed = frozenset({"llm_cross_artifact_consistency"})
    report = {
        "violations": [
            {"item_id": "a", "detection_method": "llm_cross_artifact_consistency"},
            {
                "item_id": "b",
                "detection_method": "llm_cross_artifact_consistency",
                "defect_scope": "operational",
            },
            {
                "item_id": "c",
                "detection_method": "llm_cross_artifact_consistency",
                "defect_type": "llm_audit_failure",
            },
        ]
    }
    assert MODULE.candidate_ids(report, allowed) == {"a"}


def test_metrics_ignore_items_outside_the_scored_half() -> None:
    scope = {"a", "b"}
    result = MODULE.metrics({"a", "z"}, {"a", "z"}, scope)
    assert (result["tp"], result["fp"], result["fn"], result["tn"]) == (1, 0, 0, 1)


def test_vote_union_requires_the_requested_number_of_votes() -> None:
    runs = [{"a", "b"}, {"a", "c"}, {"a"}]
    assert MODULE.vote_union(runs, 1) == {"a", "b", "c"}
    assert MODULE.vote_union(runs, 2) == {"a"}
    assert MODULE.vote_union(runs, 3) == {"a"}


def test_summary_reports_the_median_not_the_best_run() -> None:
    per_run = [{"tp": 35, "fp": 7, "precision": 0.8, "recall": 0.6, "f1": 0.68},
               {"tp": 39, "fp": 7, "precision": 0.9, "recall": 0.8, "f1": 0.84},
               {"tp": 38, "fp": 5, "precision": 0.85, "recall": 0.7, "f1": 0.77}]
    summary = MODULE.summarise(per_run)
    assert summary["median"]["tp"] == 38
    assert summary["range"]["tp"] == [35, 39]


def test_paired_difference_separates_unique_hits_by_label() -> None:
    diff = MODULE.paired_difference(
        {"a", "x"}, {"a", "b", "y"}, positive={"a", "b"}, scope={"a", "b", "x", "y"}
    )
    assert diff["only_right_tp"] == ["b"]
    assert diff["only_left_tp"] == []
    assert diff["only_left_fp"] == ["x"]
    assert diff["only_right_fp"] == ["y"]
    assert diff["discordant_positives"] == 1


def test_parse_arm_requires_a_name_and_at_least_one_report() -> None:
    assert MODULE.parse_arm("thinking=a.json,b.json") == (
        "thinking",
        [Path("a.json"), Path("b.json")],
    )
    for bad in ("thinking", "=a.json", "thinking="):
        try:
            MODULE.parse_arm(bad)
        except SystemExit:
            continue
        raise AssertionError(f"expected SystemExit for {bad!r}")


def test_median_of_an_even_number_of_runs_is_not_rounded() -> None:
    per_run = [{"tp": 35, "fp": 7, "precision": 0.8, "recall": 0.6, "f1": 0.7},
               {"tp": 38, "fp": 5, "precision": 0.8, "recall": 0.6, "f1": 0.7},
               {"tp": 39, "fp": 7, "precision": 0.8, "recall": 0.6, "f1": 0.7},
               {"tp": 41, "fp": 5, "precision": 0.8, "recall": 0.6, "f1": 0.7}]
    assert MODULE.summarise(per_run)["median"]["tp"] == 38.5
    assert MODULE.summarise(per_run)["median"]["fp"] == 6
