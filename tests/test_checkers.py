from dataclasses import replace

from benchcore.benchmark_profile import ITEM_TASK_SHAPE_KEY
from benchcore.checkers import TaskSpecChecker
from benchcore.schema import BenchmarkItem


def test_keyword_ambiguity_applies_to_a_question_not_an_instruction():
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
    instruction_item = replace(
        item, metadata={**item.metadata, ITEM_TASK_SHAPE_KEY: "artifact_production"}
    )
    workspace_types = [v.defect_type for v in TaskSpecChecker().check(instruction_item)]

    assert "missing_context" in default_types
    assert "ambiguous_goal" in default_types
    assert workspace_types == ["missing_context"]
