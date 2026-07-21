from pathlib import Path

import pytest

from scripts.materialize_artifact_counterexample import materialize_from_plan


def test_plan_materializes_variant_and_scored_pair_sidecar(tmp_path: Path):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "report.md").write_text("# Report\nRequired section.\n", encoding="utf-8")
    plan = {
        "mutations": [
            {
                "operator": "text_delete_exact",
                "relative_path": "report.md",
                "parameters": {"needle": "Required section.\n"},
            }
        ],
        "scored_pair": {
            "family": "workspace",
            "relation": "degradation_should_lower",
            "rubric_quote": "The report must contain the required section.",
            "grader_kind": "llm",
        },
    }

    result = materialize_from_plan(baseline, tmp_path / "variant", plan)

    assert result["certificate"]["changed_paths"] == ("report.md",)
    assert result["scored_pair_spec"]["pair_id"] == result["certificate"]["mutation_id"]
    assert result["scored_pair_spec"]["construction"] == "deterministic"


def test_invalid_scored_sidecar_is_rejected_before_variant_creation(tmp_path: Path):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "report.md").write_text("required", encoding="utf-8")
    variant = tmp_path / "variant"

    with pytest.raises(ValueError, match="unexpected field"):
        materialize_from_plan(
            baseline,
            variant,
            {
                "mutations": [
                    {"operator": "delete_file", "relative_path": "report.md"}
                ],
                "scored_pair": {
                    "family": "workspace",
                    "relation": "degradation_should_lower",
                    "rubric_quote": "Required",
                    "hidden_label": "defect",
                },
            },
        )

    assert not variant.exists()
