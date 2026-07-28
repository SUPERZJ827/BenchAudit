import json
import os
import subprocess
import sys
import unittest
from argparse import Namespace
from pathlib import Path

from benchcore.cli import _remote_egress_manifest
from benchcore.schema import BenchmarkItem
from benchcore.task_contract import (
    LLMTaskContractAuditor,
    TaskContractValidationError,
    parse_task_contract,
)


class FakeClient:
    def __init__(self, response):
        self.response = response

    def chat_json(self, system, user):
        return self.response


def output_contract():
    return {
        "schema_version": "task-output-contract.v1",
        "output_requirements": [
            {"path": "123.txt", "evidence": "123.txt"}
        ],
    }


class TaskContractParsingTest(unittest.TestCase):
    def test_extracts_an_evidence_grounded_output_filename(self):
        contract = parse_task_contract(
            "请总结1.txt,2.txt,.....100.txt为123.txt",
            output_contract(),
        )

        self.assertEqual(contract.expected_output_paths, ("123.txt",))

    def test_rejects_a_fabricated_evidence_anchor(self):
        response = output_contract()
        response["output_requirements"][0]["evidence"] = "save as 123.txt"

        with self.assertRaisesRegex(TaskContractValidationError, "not an exact substring"):
            parse_task_contract("请总结1.txt,2.txt,.....100.txt为123.txt", response)

    def test_rejects_unsafe_output_paths(self):
        response = output_contract()
        response["output_requirements"] = [
            {"path": "../123.txt", "evidence": "123.txt"}
        ]

        with self.assertRaisesRegex(TaskContractValidationError, "unsafe path"):
            parse_task_contract("请总结1.txt,2.txt,.....100.txt为123.txt", response)

    def test_inventory_path_precedence_is_stable_across_hash_seeds(self):
        program = (
            "import json; "
            "from benchcore.task_contract import _paths_from_inventory; "
            "print(json.dumps(_paths_from_inventory("
            "{'path':'a.txt','name':'b.txt','file':'c.txt'})))"
        )
        outputs = set()
        for seed in range(1, 6):
            environment = dict(os.environ)
            environment["PYTHONHASHSEED"] = str(seed)
            outputs.add(
                subprocess.check_output(
                    [sys.executable, "-c", program],
                    cwd=Path(__file__).resolve().parents[1],
                    env=environment,
                    text=True,
                ).strip()
            )

        self.assertEqual(outputs, {json.dumps(["a.txt"])})


class TaskContractAuditorTest(unittest.TestCase):
    def test_reports_a_replayed_output_filename_mismatch(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"
        item = BenchmarkItem(
            item_id="demo",
            raw={
                "task": task,
                "input_files": [f"{index}.txt" for index in range(1, 100)],
                "output_files": ["wrong.txt"],
            },
            task=task,
        )

        violations = list(LLMTaskContractAuditor(FakeClient(output_contract())).check(item))

        self.assertEqual(
            [violation.defect_type for violation in violations],
            ["task_artifact_contract_mismatch"],
        )
        self.assertEqual(violations[0].evidence_tier, "review")
        self.assertTrue(violations[0].review_only)
        self.assertEqual(violations[0].severity, "review")
        self.assertEqual(violations[0].evidence["missing_output_paths"], ["123.txt"])

    def test_input_filename_extraction_is_suppressed_as_role_ambiguous(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"
        response = {
            "schema_version": "task-output-contract.v1",
            "output_requirements": [{"path": "1.txt", "evidence": "1.txt"}],
        }
        item = BenchmarkItem(
            item_id="input-misclassified-as-output",
            raw={
                "task": task,
                "input_files": ["1.txt"],
                "output_files": ["123.txt"],
            },
            task=task,
        )

        violations = list(LLMTaskContractAuditor(FakeClient(response)).check(item))

        self.assertEqual(violations, [])
        replay = item.metadata["_llm_observations"]["llm_task_contract"]["inventory_replay"]
        self.assertEqual(replay["suppressed_input_output_overlap_paths"], ["1.txt"])
        self.assertEqual(replay["missing_output_count"], 0)

    def test_reference_files_are_inputs_not_an_output_inventory_by_default(self):
        task = "Use data.csv and save into report.docx"
        item = BenchmarkItem(
            item_id="reference-input",
            raw={"task": task, "reference_files": ["data.csv"]},
            task=task,
        )
        response = {
            "schema_version": "task-output-contract.v1",
            "output_requirements": [
                {"path": "report.docx", "evidence": "report.docx"}
            ],
        }

        violations = list(LLMTaskContractAuditor(FakeClient(response)).check(item))

        self.assertEqual(violations, [])
        replay = item.metadata["_llm_observations"]["llm_task_contract"]["inventory_replay"]
        self.assertFalse(replay["output_inventory_available"])
        self.assertTrue(replay["input_inventory_available"])

    def test_missing_input_files_are_out_of_scope_when_output_name_matches(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"
        item = BenchmarkItem(
            item_id="input-gap-is-irrelevant",
            raw={
                "task": task,
                "input_files": ["1.txt"],
                "output_files": ["123.txt"],
            },
            task=task,
        )

        violations = list(LLMTaskContractAuditor(FakeClient(output_contract())).check(item))

        self.assertEqual(violations, [])

    def test_workspace_json_string_output_inventory_matches_extracted_path(self):
        task = "Create and save `report.docx`."
        item = BenchmarkItem(
            item_id="workspace-json-output",
            raw={
                "task": task,
                "output_files": '["report.docx"]',
            },
            task=task,
            output_contract={
                "type": "workspace_files",
                "required_files": ["report.docx"],
            },
        )
        response = {
            "schema_version": "task-output-contract.v1",
            "output_requirements": [
                {"path": "report.docx", "evidence": "`report.docx`"}
            ],
        }

        violations = list(LLMTaskContractAuditor(FakeClient(response)).check(item))

        self.assertEqual(violations, [])
        replay = item.metadata["_llm_observations"]["llm_task_contract"]["inventory_replay"]
        self.assertEqual(replay["observed_output_count"], 1)
        self.assertEqual(replay["missing_output_count"], 0)

    def test_workspace_data_manifest_supports_input_role_suppression(self):
        task = "Summarize `source.txt` into `report.txt`."
        item = BenchmarkItem(
            item_id="workspace-manifest-input",
            raw={
                "task": task,
                "data_manifest": [{
                    "filename": "source.txt",
                    "stored_relpath": "data/0123456789abcdef_source.txt",
                }],
                "output_files": '["report.txt"]',
            },
            task=task,
            output_contract={
                "type": "workspace_files",
                "required_files": ["report.txt"],
            },
        )
        response = {
            "schema_version": "task-output-contract.v1",
            "output_requirements": [
                {"path": "source.txt", "evidence": "`source.txt`"}
            ],
        }

        violations = list(LLMTaskContractAuditor(FakeClient(response)).check(item))

        self.assertEqual(violations, [])
        replay = item.metadata["_llm_observations"]["llm_task_contract"]["inventory_replay"]
        self.assertEqual(
            replay["suppressed_input_output_overlap_paths"], ["source.txt"],
        )
        self.assertEqual(replay["missing_output_count"], 0)

    def test_absent_output_inventory_is_unknown_not_a_defect(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"
        item = BenchmarkItem(item_id="no-manifest", raw={"task": task}, task=task)

        violations = list(LLMTaskContractAuditor(FakeClient(output_contract())).check(item))

        self.assertEqual(violations, [])
        replay = item.metadata["_llm_observations"]["llm_task_contract"]["inventory_replay"]
        self.assertFalse(replay["output_inventory_available"])

    def test_explicitly_empty_output_inventory_is_replayed_as_missing(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"
        item = BenchmarkItem(
            item_id="empty-manifest",
            raw={"task": task, "output_files": []},
            task=task,
        )

        violations = list(LLMTaskContractAuditor(FakeClient(output_contract())).check(item))

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].evidence["missing_output_count"], 1)

    def test_invalid_model_output_is_an_operational_failure_not_a_defect(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"
        response = output_contract()
        response["output_requirements"][0]["path"] = "invented.txt"
        item = BenchmarkItem(item_id="invalid", raw={"task": task}, task=task)

        violations = list(LLMTaskContractAuditor(FakeClient(response)).check(item))

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].defect_type, "llm_audit_failure")
        self.assertEqual(violations[0].evidence_tier, "unknown")
        self.assertEqual(violations[0].defect_scope, "operational")

    def test_taskcontract_only_declares_task_text_for_remote_egress(self):
        args = Namespace(
            execution_evaluator_audit=False,
            llm_audit=True,
            llm_auditors="taskcontract",
            swe_leak_llm_confirm=False,
            cross_artifact_audit=False,
            workspace_rubric_grounding_audit=False,
            value_recompute_audit=False,
        )

        manifest = _remote_egress_manifest(
            args,
            use_grounded_rubric=False,
            use_rubric_contract=False,
            use_rubric_coverage=False,
        )

        self.assertEqual(
            manifest,
            [
                {
                    "checker": "llm_task_contract",
                    "outbound_fields": ["item_id", "task"],
                    "attachment_content": False,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
