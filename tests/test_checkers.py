from benchcore.checkers import TaskSpecChecker
from benchcore.schema import BenchmarkItem


def test_task_spec_checker_can_disable_keyword_ambiguity_only():
    item = BenchmarkItem(
        item_id="workspace-current",
        raw={},
        task=(
            "Use the attached PDF. The current version is complete; "
            "create a backup report."
        ),
        context={},
    )

    default_types = [v.defect_type for v in TaskSpecChecker().check(item)]
    workspace_types = [
        v.defect_type for v in TaskSpecChecker(check_ambiguity=False).check(item)
    ]

    assert "missing_context" in default_types
    assert "ambiguous_goal" in default_types
    assert workspace_types == ["missing_context"]
