from pathlib import Path

import pytest

from scripts.generate_workspace_p0_blind_package import (
    REPO,
    ensure_private_output_dir,
    select_cases,
)
from scripts.run_workspace_static_llm_ablation import POSITIVE_REVIEW_LABEL


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
