"""Contract checks are about artifact-producing benchmarks, not about GDPval.

"The task names a file the artifact manifest does not contain" is true of any
benchmark that ships input materials and expects deliverables.  Only the field
names were specific, so the checks now resolve each role through a map whose
defaults are the GDPval names.

The promotion validator recomputes these facts from the live row, so it must
resolve roles exactly as the checker did; otherwise a correct finding fails its
own replay and can never be confirmed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_gdpval_objective import make_row, rubric_item  # noqa: E402

from benchcore.artifact_contract import (  # noqa: E402
    CONTRACT_ROLE_DEFAULTS,
    _contract_facts,
    _role_field,
)

RENAMED_ROLES = {
    "task": "instruction",
    "rubric": "grading_criteria",
    "reference_artifacts": "given_files",
    "deliverable_artifacts": "expected_outputs",
}


def _mismatching_row():
    return make_row(
        prompt="Create the final policy as a Word document (.docx).",
        rubrics=[rubric_item("The policy contains an approval section.")],
        deliverables=("final_policy.pdf",),
    )


def _rename(row):
    return {
        RENAMED_ROLES["task"]: row.get(CONTRACT_ROLE_DEFAULTS["task"]),
        RENAMED_ROLES["rubric"]: row.get(CONTRACT_ROLE_DEFAULTS["rubric"]),
        RENAMED_ROLES["reference_artifacts"]: row.get(
            CONTRACT_ROLE_DEFAULTS["reference_artifacts"], []
        ),
        RENAMED_ROLES["deliverable_artifacts"]: row.get(
            CONTRACT_ROLE_DEFAULTS["deliverable_artifacts"], []
        ),
    }


def test_defaults_preserve_the_original_field_names():
    for role, field in CONTRACT_ROLE_DEFAULTS.items():
        assert _role_field(None, role) == field
        assert _role_field({}, role) == field


def test_a_declared_role_overrides_the_default():
    assert _role_field({"task": "instruction"}, "task") == "instruction"


def test_a_blank_or_wrong_typed_role_falls_back():
    assert _role_field({"task": ""}, "task") == CONTRACT_ROLE_DEFAULTS["task"]
    assert _role_field({"task": 3}, "task") == CONTRACT_ROLE_DEFAULTS["task"]


def test_the_check_still_fires_on_the_original_field_names():
    facts = _contract_facts(_mismatching_row())
    assert [fact.defect_type for fact in facts] == ["task_artifact_contract_mismatch"]


def test_the_same_content_under_other_field_names_yields_the_same_facts():
    original = _contract_facts(_mismatching_row())
    renamed = _contract_facts(_rename(_mismatching_row()), RENAMED_ROLES)
    assert [(f.defect_type, f.evidence_level) for f in renamed] == [
        (f.defect_type, f.evidence_level) for f in original
    ]
    # Signatures differ by design: they record which field the evidence came
    # from, so a finding cannot be replayed against a different field.
    assert [f.signature for f in renamed] != [f.signature for f in original]


def test_unrecognised_field_names_without_roles_report_nothing():
    """Reading nothing must stay silent rather than invent a finding."""
    assert _contract_facts(_rename(_mismatching_row())) == []


def test_a_clean_row_reports_nothing_under_either_naming():
    clean = make_row(
        prompt="Create the final policy as a PDF document (.pdf).",
        rubrics=[rubric_item("The policy contains an approval section.")],
        deliverables=("final_policy.pdf",),
    )
    assert _contract_facts(clean) == []
    assert _contract_facts(_rename(clean), RENAMED_ROLES) == []


def test_the_validator_resolves_roles_the_way_the_checker_did():
    """A finding must survive its own replay under a non-default role map."""
    from benchcore.gdpval_objective import (
        DEFAULT_GDPVAL_REVISION,
        GDPValRecordIntegrityChecker,
        replay_record_fact,
    )
    from benchcore.schema import BenchmarkItem

    row = _rename(_mismatching_row())
    item = BenchmarkItem(item_id="x", raw=row, task=str(row["instruction"]), gold="")
    checker = GDPValRecordIntegrityChecker(
        dataset_revision=DEFAULT_GDPVAL_REVISION, roles=RENAMED_ROLES
    )
    violations = [
        violation
        for violation in checker.check(item)
        if violation.defect_type == "task_artifact_contract_mismatch"
        and not violation.review_only
    ]
    assert violations, "the renamed row should still produce a confirmable finding"
    assert getattr(item, "_gdpval_contract_roles") == RENAMED_ROLES
    for violation in violations:
        assert replay_record_fact(violation, item) is True
