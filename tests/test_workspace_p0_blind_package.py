from pathlib import Path

import pytest

from scripts.generate_workspace_p0_blind_package import (
    REPO,
    ensure_private_output_dir,
    select_cases,
)
from scripts.compare_workspace_p0_annotations import compare_annotations
from scripts.run_workspace_static_llm_ablation import POSITIVE_REVIEW_LABEL
from scripts.validate_workspace_p0_annotations import validate_annotations
from scripts.run_workspace_p0_openrouter_blind_review import (
    MODEL as INDEPENDENT_REVIEW_MODEL,
    annotation_schema,
    ensure_private_dir,
    validate_task_annotations,
)
from scripts.analyze_workspace_p0_independent_review import summarize


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


def test_annotation_comparison_reports_confusion_and_kappa():
    first = [
        {"blind_id": "a", "is_grounding_defect": "yes", "grounding_class": "x"},
        {"blind_id": "b", "is_grounding_defect": "no", "grounding_class": "y"},
        {
            "blind_id": "c",
            "is_grounding_defect": "uncertain",
            "grounding_class": "z",
        },
    ]
    second = [
        {"blind_id": "a", "is_grounding_defect": "yes", "grounding_class": "x"},
        {
            "blind_id": "b",
            "is_grounding_defect": "uncertain",
            "grounding_class": "y",
        },
        {
            "blind_id": "c",
            "is_grounding_defect": "uncertain",
            "grounding_class": "z",
        },
    ]
    for rows in (first, second):
        for row in rows:
            row.update({
                "evaluation_objectivity": "objective",
                "satisfaction_checkability": "static",
                "primary_family": "workspace_rubric_grounding",
            })

    result = compare_annotations(first, second)

    assert result["rows"] == 3
    assert result["field_agreement"]["is_grounding_defect"]["count"] == 2
    assert result["grounding_defect_confusion"]["no"]["uncertain"] == 1
    assert len(result["disagreements"]) == 1


def test_independent_review_model_and_schema_are_protocol_frozen():
    assert INDEPENDENT_REVIEW_MODEL == "google/gemini-3.1-pro-preview"
    schema = annotation_schema()
    row_schema = schema["properties"]["annotations"]["items"]
    assert row_schema["additionalProperties"] is False
    assert set(row_schema["required"]) == set(row_schema["properties"])


def test_independent_review_requires_exact_source_quotes():
    task = {
        "task_blind_id": "task-a",
        "task": "Create report.txt.",
        "output_contract": {
            "type": "workspace_files",
            "required_files": ["report.txt"],
        },
        "allowed_input_evidence": (
            "[INPUT FILE: facts.txt]\nThe required total is 12.\n"
        ),
    }
    candidates = [{
        "blind_id": "case-a",
        "task_blind_id": "task-a",
        "rubric": "The report gives a total of 12.",
    }]
    row = {
        "blind_id": "case-a",
        "acceptable_families": ["workspace_rubric_grounding"],
        "confidence": 0.9,
        "evaluation_objectivity": "objective",
        "evidence": [{
            "source": "input:facts.txt",
            "quote": "The required total is 12.",
            "relation": "supports",
        }],
        "grounding_class": "task_or_input_derived",
        "is_grounding_defect": "no",
        "primary_family": "workspace_rubric_grounding",
        "root_cause_summary": "The input supplies the exact total.",
        "satisfaction_checkability": "static",
    }
    validate_task_annotations(task, candidates, [row])
    invalid = {
        **row,
        "evidence": [{
            "source": "input:facts.txt",
            "quote": "The required total is twelve.",
            "relation": "supports",
        }],
    }
    with pytest.raises(ValueError, match="not an exact substring"):
        validate_task_annotations(task, candidates, [invalid])


def test_independent_review_output_must_remain_outside_worktree():
    with pytest.raises(ValueError, match="outside the git worktree"):
        ensure_private_dir(REPO / "unsafe-independent-review")


def test_independent_review_analysis_keeps_conflicts_out_of_consensus():
    mapping = [
        {
            "blind_id": "a",
            "source_stratum": "focus_b_only_unsupported",
            "item_id": "item-a",
            "rubric_index": 0,
        },
        {
            "blind_id": "b",
            "source_stratum": "focus_b_only_unsupported",
            "item_id": "item-b",
            "rubric_index": 1,
        },
    ]

    def row(blind_id, verdict, family="workspace_rubric_grounding"):
        return {
            "blind_id": blind_id,
            "is_grounding_defect": verdict,
            "grounding_class": (
                "hidden_exact_constraint" if verdict == "yes"
                else "task_or_input_derived"
            ),
            "evaluation_objectivity": "objective",
            "satisfaction_checkability": "static",
            "primary_family": family,
            "acceptable_families": [family],
            "confidence": 0.9,
        }

    result = summarize(
        mapping,
        [row("a", "yes"), row("b", "no")],
        [row("a", "yes"), row("b", "yes")],
        incremental_dual_calls=10,
    )

    focus = result["b_only_final_unsupported"]
    assert focus["independent_yes"] == 1
    assert focus["cross_review_agreed_positive"] == 1
    assert focus["calls_per_independent_positive"] == 10
    assert result["by_stratum"]["focus_b_only_unsupported"][
        "cross_review_consensus"
    ] == {"conflict": 1, "yes": 1}
