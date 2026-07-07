from pathlib import Path

from benchcore.artifact_consistency import (
    CrossArtifactConsistencyChecker,
    GroundedRubricConsistencyChecker,
    RubricOutputContractConsistencyChecker,
    build_context_preview,
    extract_rubrics,
)
from benchcore.schema import BenchmarkItem


class FakeLLMClient:
    def __init__(self, response):
        self.responses = response if isinstance(response, list) else [response]
        self.index = 0
        self.calls = []

    def chat_json(self, system, user):
        self.calls.append((system, user))
        response = self._next_response()
        return dict(response)

    def chat_json_multi(self, system, user):
        self.calls.append((system, user))
        response = self._next_response()
        if isinstance(response, list):
            return [dict(x) for x in response]
        return [dict(response)]

    def _next_response(self):
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return response


def test_extract_rubrics_from_json_string():
    item = BenchmarkItem(
        item_id="r",
        raw={"rubrics": '["must include total", "must cite source"]'},
        task="Task",
    )

    assert extract_rubrics(item) == ["must include total", "must cite source"]


def test_context_preview_reads_relative_file(tmp_path: Path):
    data = tmp_path / "input.txt"
    data.write_text("hospital grade column is absent", encoding="utf-8")
    item = BenchmarkItem(
        item_id="ctx",
        raw={},
        task="Task",
        context={"files": ["input.txt"]},
    )

    preview = build_context_preview(item, tmp_path, 2000)

    assert "[files inventory]" in preview
    assert "size_bytes=" in preview
    assert "FILE input.txt" in preview
    assert "hospital grade column is absent" in preview


def test_cross_artifact_checker_maps_data_gap_to_violation():
    item = BenchmarkItem(
        item_id="gap",
        raw={"rubrics": ["Count hospitals by grade."]},
        task="Summarize hospital counts.",
        context={"table": "columns: hospital_name, region"},
    )
    client = FakeLLMClient(
        {
            "status": "data_gap",
            "missing_data": ["hospital grade"],
            "task_ambiguities": [],
            "consistency_issues": [
                {
                    "type": "rubric_context",
                    "detail": "Rubric needs hospital grade, but context has no grade field.",
                    "material": True,
                }
            ],
            "severity": "high",
            "confidence": 0.88,
            "summary": "The rubric requires hospital grade data absent from inputs.",
        }
    )

    violations = list(CrossArtifactConsistencyChecker(client).check(item))

    assert {v.defect_type for v in violations} == {"artifact_data_gap"}
    assert all(v.review_only for v in violations)
    assert violations[0].detection_method == "llm_cross_artifact_consistency"
    assert client.calls


def test_cross_artifact_checker_maps_task_rubric_mismatch():
    item = BenchmarkItem(
        item_id="mismatch",
        raw={"rubrics": ["Award points only if the answer recommends Vendor A."]},
        task="Recommend the best vendor from the data.",
        context={"table": "Vendor A margin=1; Vendor B margin=9"},
    )
    client = FakeLLMClient(
        {
            "status": "task_rubric_mismatch",
            "missing_data": [],
            "task_ambiguities": [],
            "consistency_issues": [
                {
                    "type": "task_rubric",
                    "detail": "The task asks for best vendor, but rubric pins Vendor A.",
                    "material": True,
                }
            ],
            "severity": "medium",
            "confidence": 0.74,
            "summary": "Rubric pins a specific conclusion not required by the task.",
        }
    )

    violations = list(CrossArtifactConsistencyChecker(client).check(item))

    assert [v.defect_type for v in violations] == ["task_rubric_mismatch"]
    assert violations[0].severity == "review"
    assert "Vendor A" in violations[0].message


def test_grounded_rubric_checker_flags_absent_required_data():
    item = BenchmarkItem(
        item_id="ground-gap",
        raw={"rubrics": ["按三级/二级/一级医院等级统计各等级医院数量。"]},
        task="统计医院数量。",
        context={"table": "columns: hospital_name, region, ownership_type"},
    )
    client = FakeLLMClient(
        [
            {"required": ["医院等级"]},
            [
                {
                    "verdict": "not_in_inputs",
                    "reason": "The input has no hospital grade field.",
                    "confidence": 0.87,
                },
                {
                    "verdict": "not_in_inputs",
                    "reason": "No tertiary/secondary/primary category is available.",
                    "confidence": 0.82,
                },
            ],
        ]
    )

    violations = list(GroundedRubricConsistencyChecker(client).check(item))

    assert [v.defect_type for v in violations] == ["artifact_data_gap"]
    assert violations[0].severity == "major"
    assert violations[0].review_only
    assert violations[0].detection_method == "grounded_rubric_consistency"
    assert violations[0].evidence["literal_missing_terms"] == ["医院等级"]


def test_grounded_rubric_checker_flags_over_constrained_structure():
    item = BenchmarkItem(
        item_id="ground-structure",
        raw={"rubrics": ["输出文件必须包含名为“数据说明”的工作表。"]},
        task="根据输入表格统计医院数量并输出 Excel。",
        context={"table": "columns: hospital_name, region, ownership_type"},
    )
    client = FakeLLMClient(
        [
            [
                {
                    "defect": "over_constrained",
                    "evidence": "The task asks for an Excel output but not this exact sheet.",
                    "confidence": 0.78,
                },
                {
                    "defect": "over_constrained",
                    "evidence": "The sheet name is not grounded in the task.",
                    "confidence": 0.8,
                },
            ]
        ]
    )

    violations = list(GroundedRubricConsistencyChecker(client).check(item))

    assert [v.defect_type for v in violations] == ["task_rubric_mismatch"]
    assert violations[0].severity == "review"
    assert violations[0].review_only
    assert violations[0].evidence["grounding_check"] == "output_structure_vs_task"


def test_rubric_output_contract_checker_flags_extra_required_output():
    item = BenchmarkItem(
        item_id="contract-extra",
        raw={"rubrics": ["Does the submission also include appendix.xlsx?"]},
        task="Create a concise report.",
        output_contract={"type": "workspace_files", "required_files": ["report.md"]},
        evaluator={
            "type": "workspacebench_rubric",
            "rubrics": ["Does the submission also include appendix.xlsx?"],
        },
    )
    client = FakeLLMClient(
        [
            [
                {
                    "status": "contract_mismatch",
                    "issues": [
                        {
                            "rubric_index": 0,
                            "type": "extra_output",
                            "detail": "Rubric requires appendix.xlsx, but the contract only declares report.md.",
                            "material": True,
                        }
                    ],
                    "severity": "high",
                    "confidence": 0.84,
                    "summary": "Rubric requires an undeclared output file.",
                }
            ]
        ]
    )

    violations = list(RubricOutputContractConsistencyChecker(client).check(item))

    assert [v.defect_type for v in violations] == ["output_evaluator_contract_mismatch"]
    assert violations[0].severity == "major"
    assert violations[0].review_only
    assert violations[0].detection_method == "rubric_output_contract_consistency"
    assert violations[0].evidence["contract_issue"]["type"] == "extra_output"
