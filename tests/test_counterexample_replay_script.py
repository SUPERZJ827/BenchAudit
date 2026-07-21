import hashlib

from scripts.replay_counterexample_evidence import replay_manifest


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_manifest_replays_all_supported_observation_shapes():
    scored_trials = [
        {
            "seed": index,
            "presented_order": "AB" if index % 2 == 0 else "BA",
            "evaluator_id": "judge",
            "baseline_score": 0.8,
            "variant_score": 0.8,
            "transcript_sha256": digest(f"trial-{index}"),
        }
        for index in range(6)
    ]
    payload = {
        "records": [
            {
                "kind": "objective_pair",
                "observation": {
                    "pair_id": "code-1",
                    "family": "code",
                    "relation": "invalid_should_fail",
                    "baseline_accepted": True,
                    "variant_accepted": True,
                    "relation_certified": True,
                    "official_evaluator": True,
                    "transcript_attested": True,
                    "independent_adjudicator": True,
                    "execution_transcript_sha256": digest("code-transcript"),
                    "baseline_sha256": digest("code-good"),
                    "variant_sha256": digest("code-bad"),
                    "mutation_operator": "off_by_one",
                },
            },
            {
                "kind": "table_recompute",
                "observation": {
                    "item_id": "table-1",
                    "declared_value": 10.0,
                    "recomputed_value": 9.0,
                    "absolute_tolerance": 0.01,
                    "relative_tolerance": 1e-6,
                    "source_cells_pinned": True,
                    "formula_pinned": True,
                    "transcript_attested": True,
                    "independent_adjudicator": True,
                    "official_value_sha256": digest("10"),
                    "recompute_transcript_sha256": digest("table-transcript"),
                },
            },
            {
                "kind": "scored_pair",
                "spec": {
                    "pair_id": "workspace-1",
                    "family": "workspace",
                    "relation": "degradation_should_lower",
                    "mutation_operator": "delete_required_sheet",
                    "construction": "deterministic",
                    "baseline_sha256": digest("workbook"),
                    "variant_sha256": digest("workbook-no-sheet"),
                    "changed_paths": ["required-sheet"],
                    "rubric_quote": "The workbook must include Required Sheet.",
                },
                "trials": scored_trials,
            },
            {
                "kind": "exact_answer",
                "item": {
                    "item_id": "answer-1",
                    "raw": {},
                    "task": "What is 3 + 3?",
                    "gold": "6",
                    "evaluator": {"type": "numeric"},
                },
            },
            {
                "kind": "route_only",
                "item": {
                    "item_id": "open-1",
                    "raw": {},
                    "task": "Write a thoughtful essay.",
                },
            },
        ]
    }

    result = replay_manifest(payload)

    assert result["summary"]["errors"] == 0
    assert result["summary"]["status_distribution"]["defect_observed"] == 3
    assert any(row["family"] == "exact_answer" for row in result["routes"])
    assert any(row["family"] == "open_ended" for row in result["routes"])


def test_manifest_rejects_unknown_fields_without_aborting_other_records():
    result = replay_manifest({
        "records": [
            {
                "kind": "route_only",
                "item": {"item_id": "bad", "raw": {}, "invented": True},
            },
            {
                "kind": "route_only",
                "item": {"item_id": "good", "raw": {}, "task": "Write."},
            },
        ]
    })

    assert result["summary"]["errors"] == 1
    assert len(result["routes"]) == 1
