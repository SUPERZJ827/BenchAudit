from pathlib import Path

import pytest

from scripts.generate_workspace_p0_blind_package import (
    REPO,
    ensure_private_output_dir,
    select_cases,
)
from scripts.run_workspace_static_llm_ablation import POSITIVE_REVIEW_LABEL
from scripts.validate_workspace_p0_annotations import validate_annotations


def _decision(label, views):
    return {
        "label": label,
        "scanner": {"triage_selected_views": views},
    }


def test_select_cases_freezes_17_focus_and_task_distinct_controls():
    decisions = {}
    for index in range(13):
        decisions[(f"focus-b-{index % 10}", index)] = _decision(
            "unsupported", ["support_challenge"],
        )
    reviewed = {}
    for index in range(4):
        key = (f"focus-missed-{index}", index)
        decisions[key] = _decision("uncertain", [])
        reviewed[key] = POSITIVE_REVIEW_LABEL
    for index in range(12):
        decisions[(f"control-s-{index}", index)] = _decision(
            "supported", ["support_challenge"],
        )
        decisions[(f"control-u-{index}", index)] = _decision(
            "uncertain", ["support_challenge"],
        )

    first, strata = select_cases(decisions, reviewed)
    second, second_strata = select_cases(decisions, reviewed)

    assert first == second
    assert strata == second_strata
    assert len(first) == len(set(first)) == 37
    counts = {
        label: list(strata.values()).count(label)
        for label in set(strata.values())
    }
    assert counts == {
        "focus_b_only_unsupported": 13,
        "focus_missed_reviewed_positive": 4,
        "control_b_only_supported": 10,
        "control_b_only_uncertain": 10,
    }
    supported_tasks = {
        item_id for (item_id, _), label in strata.items()
        if label == "control_b_only_supported"
    }
    uncertain_tasks = {
        item_id for (item_id, _), label in strata.items()
        if label == "control_b_only_uncertain"
    }
    assert len(supported_tasks) == 10
    assert len(uncertain_tasks) == 10


def test_blind_evidence_package_cannot_be_written_inside_repo():
    with pytest.raises(ValueError, match="outside the git worktree"):
        ensure_private_output_dir(REPO / "experiments" / "unsafe")

    outside = Path("/tmp/benchaudit-private-blind-package")
    assert ensure_private_output_dir(outside) == outside.resolve()


def test_annotation_validator_requires_exact_ids_and_typed_evidence():
    template = [{"blind_id": "case-a"}]
    valid = [{
        "blind_id": "case-a",
        "acceptable_families": ["workspace_rubric_grounding"],
        "confidence": 0.8,
        "evaluation_objectivity": "objective",
        "evidence": [{
            "source": "task",
            "quote": "exact title",
            "relation": "supports",
        }],
        "grounding_class": "task_or_input_derived",
        "is_grounding_defect": "no",
        "primary_family": "workspace_rubric_grounding",
        "root_cause_summary": "The requirement is explicit.",
        "satisfaction_checkability": "static",
    }]

    assert validate_annotations(template, valid)["rows"] == 1
    invalid = [{**valid[0], "blind_id": "case-b"}]
    with pytest.raises(ValueError, match="blind-id coverage"):
        validate_annotations(template, invalid)
