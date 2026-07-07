from pathlib import Path

from benchcore.artifact_consistency import (
    CrossArtifactConsistencyChecker,
    DATA_GROUNDING_PROMPT,
    GroundedRubricConsistencyChecker,
    REQUIRED_DATA_PROMPT,
    RubricOutputContractConsistencyChecker,
    build_context_preview,
    extract_rubrics,
    full_context_text,
    is_generated_role_permission_requirement,
    is_structure_rubric,
    is_material_output_contract_issue,
    static_output_contract_issues,
    targeted_search_context,
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


def test_full_context_text_distributes_budget_across_files(tmp_path: Path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("alpha " * 4000, encoding="utf-8")
    second.write_text(
        "The company signed an emergency mutual aid agreement with surrounding companies.",
        encoding="utf-8",
    )
    item = BenchmarkItem(
        item_id="ctx-balanced",
        raw={},
        task="Task",
        context={"files": ["first.txt", "second.txt"]},
    )

    text = full_context_text(item, tmp_path, 2400)

    assert "first.txt" in text
    assert "second.txt" in text
    assert "emergency mutual aid agreement" in text


def test_data_grounding_prompts_require_semantic_matching():
    required_prompt = REQUIRED_DATA_PROMPT.format(
        task="Summarize the emergency manual.",
        rubric="Does the manual mention emergency mutual assistance?",
    )
    grounding_prompt = DATA_GROUNDING_PROMPT.format(
        missing="emergency mutual assistance",
        task="Summarize the emergency manual.",
        context="The company signed an emergency mutual aid agreement.",
        rubric="Does the manual mention emergency mutual assistance?",
    )

    assert "Do not invent" in required_prompt
    assert "snake_case" in required_prompt
    assert "TASK:" in required_prompt
    assert "synonyms" in grounding_prompt
    assert "aid vs assistance" in grounding_prompt
    assert "dismissed vs dissolved" in grounding_prompt
    assert "enumeration" in grounding_prompt


def test_targeted_search_context_finds_mid_file_semantic_evidence(tmp_path: Path):
    path = tmp_path / "manual.txt"
    path.write_text(
        "opening\n"
        + ("filler\n" * 300)
        + "The company signed an emergency mutual aid agreement with surrounding companies.\n"
        + ("tail\n" * 300),
        encoding="utf-8",
    )
    item = BenchmarkItem(
        item_id="ctx-targeted",
        raw={},
        task="Task",
        context={"files": ["manual.txt"]},
    )

    snippets = targeted_search_context(
        item,
        tmp_path,
        ["emergency mutual assistance agreement with surrounding enterprises"],
    )

    assert "manual.txt" in snippets
    assert "emergency mutual aid agreement" in snippets


def test_report_content_rubrics_are_not_structure_overconstraints():
    assert not is_structure_rubric(
        "Whether the industry prospect analysis section lists the five development opportunities."
    )
    assert not is_structure_rubric(
        "Does the generated report contain raw material price fluctuation risk analysis?"
    )
    assert not is_structure_rubric(
        "Does the report include a data traceability section at the end of the report?"
    )
    assert not is_structure_rubric(
        "Does the manual classify the reimbursement analysis sheet as Level 2 Sensitive?"
    )


def test_true_output_structure_rubrics_still_route_to_structure_checker():
    assert is_structure_rubric(
        "Is the report file saved in Markdown format with a clear multi-level header structure?"
    )
    assert is_structure_rubric(
        "Is the CL-Bench paper section correctly titled CL-Bench: A Benchmark for Context Learning?"
    )
    assert is_structure_rubric("输出文件必须包含名为“数据说明”的工作表。")


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


def test_generated_role_permission_requirement_is_not_data_gap():
    item = BenchmarkItem(
        item_id="ground-generated",
        raw={
            "rubrics": [
                "Does the system administrator have template-level edit access to all reports?"
            ]
        },
        task=(
            "Infer job responsibilities and corresponding spreadsheet permissions "
            "such as view, edit, and delete from the collaboration needs."
        ),
        context={"table": "columns: report_name, revenue, expense"},
    )
    client = FakeLLMClient({"required": ["role", "template edit access", "delete permission"]})

    violations = list(GroundedRubricConsistencyChecker(client).check(item))

    assert violations == []
    assert is_generated_role_permission_requirement(
        item.task or "",
        item.raw["rubrics"][0],
        ["role", "template edit access", "delete permission"],
    )


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


def test_static_contract_ignores_save_location_directory():
    # the directory is only where the named output file is saved; the file IS the contract,
    # so it must not be flagged as a missing required output directory.
    item = BenchmarkItem(
        item_id="save-loc",
        raw={},
        task="Create `Inventory_Optimization_Report.txt` and save it in the folder under `/budget-management/`.",
        output_contract={"type": "workspace_files", "required_files": ["Inventory_Optimization_Report.txt"]},
    )
    assert static_output_contract_issues(item) == []


def test_static_contract_flags_directory_deliverable():
    # here the deliverable itself is a new directory of copied files; contract wrongly names a file.
    item = BenchmarkItem(
        item_id="dir-deliverable",
        raw={},
        task="Copy the documents into a new directory named `project_kickoff_archive`.",
        output_contract={"type": "workspace_files", "required_files": ["output.md"]},
    )
    issues = static_output_contract_issues(item)
    assert [i["type"] for i in issues] == ["extra_output"]


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


def test_output_contract_checker_ignores_internal_sheet_when_contract_is_file_level():
    item = BenchmarkItem(
        item_id="contract-sheet",
        raw={"rubrics": ["Does the workbook include a worksheet named Regional Details?"]},
        task="Create regional_summary.xlsx.",
        output_contract={"type": "workspace_files", "required_files": ["regional_summary.xlsx"]},
        evaluator={
            "type": "workspacebench_rubric",
            "rubrics": ["Does the workbook include a worksheet named Regional Details?"],
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
                            "detail": "Rubric expects worksheet named 'Regional Details' not declared in output contract.",
                            "material": True,
                        }
                    ],
                    "severity": "high",
                    "confidence": 0.9,
                }
            ]
        ]
    )

    violations = list(RubricOutputContractConsistencyChecker(client).check(item))

    assert violations == []
    assert not is_material_output_contract_issue(
        {
            "type": "extra_output",
            "detail": "Rubric expects worksheet named 'Regional Details' not declared in output contract.",
            "material": True,
        },
        item.output_contract,
    )


def test_output_contract_checker_ignores_source_file_access_rubric():
    item = BenchmarkItem(
        item_id="contract-source-file",
        raw={"rubrics": ["Are the three source files successfully located and accessible?"]},
        task="Create report.xlsx from the three source files.",
        output_contract={"type": "workspace_files", "required_files": ["report.xlsx"]},
        evaluator={
            "type": "workspacebench_rubric",
            "rubrics": ["Are the three source files successfully located and accessible?"],
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
                            "detail": "Evaluator requires source files not declared in output contract.",
                            "material": True,
                        }
                    ],
                    "severity": "high",
                    "confidence": 0.9,
                }
            ]
        ]
    )

    violations = list(RubricOutputContractConsistencyChecker(client).check(item))

    assert violations == []


def test_static_output_contract_flags_task_directory_not_in_contract():
    item = BenchmarkItem(
        item_id="contract-static-dir",
        raw={"rubrics": ["Was the root folder created?"]},
        task="Copy the files into a new directory named `project_kickoff_archive`.",
        output_contract={"type": "workspace_files", "required_files": ["output.md"]},
        evaluator={"type": "workspacebench_rubric", "rubrics": ["Was the root folder created?"]},
    )

    issues = static_output_contract_issues(item)

    assert len(issues) == 1
    assert issues[0]["type"] == "extra_output"


def test_static_output_contract_flags_input_files_declared_as_outputs():
    item = BenchmarkItem(
        item_id="contract-static-inputs",
        raw={
            "input_files": [
                "/tmp/hash_interaction_document_6.txt",
                "/tmp/hash_interaction_document_8.txt",
            ],
            "rubrics": ["Does the generated report contain the standardized form?"],
        },
        task="Build a standardized dataset and generate an implementation-ready TXT report.",
        output_contract={
            "type": "workspace_files",
            "required_files": ["interaction_document_6.txt", "interaction_document_8.txt"],
        },
        evaluator={"type": "workspacebench_rubric", "rubrics": ["Does the generated report contain the standardized form?"]},
    )

    issues = static_output_contract_issues(item)

    assert len(issues) == 1
    assert issues[0]["type"] == "file_name_conflict"


def test_output_contract_checker_keeps_static_input_files_declared_as_outputs():
    item = BenchmarkItem(
        item_id="contract-static-inputs-checker",
        raw={
            "input_files": [
                "/tmp/hash_interaction_document_6.txt",
                "/tmp/hash_interaction_document_8.txt",
            ],
            "rubrics": ["Does the generated report contain the standardized form?"],
        },
        task="Build a standardized dataset and generate an implementation-ready TXT report.",
        output_contract={
            "type": "workspace_files",
            "required_files": ["interaction_document_6.txt", "interaction_document_8.txt"],
        },
        evaluator={"type": "workspacebench_rubric", "rubrics": ["Does the generated report contain the standardized form?"]},
    )
    client = FakeLLMClient({"status": "consistent", "confidence": 0.8})

    violations = list(RubricOutputContractConsistencyChecker(client).check(item))

    assert [v.defect_type for v in violations] == ["output_evaluator_contract_mismatch"]
    assert violations[0].evidence["contract_issue"]["source"] == "static_task_contract"
