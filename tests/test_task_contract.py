import unittest
from argparse import Namespace

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
        self.calls = []

    def chat_json(self, system, user):
        self.calls.append((system, user))
        return self.response


def range_contract():
    return {
        "schema_version": "task-contract.v1",
        "operation": "summarize",
        "input_requirements": [
            {
                "kind": "numeric_range",
                "prefix": "",
                "suffix": ".txt",
                "start": 1,
                "end": 100,
                "width": 0,
                "evidence": "1.txt,2.txt,.....100.txt",
            }
        ],
        "output_requirements": [
            {"path": "123.txt", "evidence": "123.txt"}
        ],
        "coverage": "all_inputs",
        "coverage_evidence": "总结1.txt,2.txt,.....100.txt",
    }


class TaskContractParsingTest(unittest.TestCase):
    def test_expands_an_evidence_grounded_numeric_file_range(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"

        contract = parse_task_contract(task, range_contract())

        self.assertEqual(len(contract.expected_input_paths), 100)
        self.assertEqual(contract.expected_input_paths[0], "1.txt")
        self.assertEqual(contract.expected_input_paths[-1], "100.txt")
        self.assertEqual(contract.expected_output_paths, ("123.txt",))
        self.assertEqual(contract.coverage, "all_inputs")

    def test_rejects_a_fabricated_evidence_anchor(self):
        response = range_contract()
        response["input_requirements"][0]["evidence"] = "1.txt through 100.txt"

        with self.assertRaisesRegex(TaskContractValidationError, "not an exact substring"):
            parse_task_contract("请总结1.txt,2.txt,.....100.txt为123.txt", response)

    def test_rejects_unsafe_output_paths(self):
        response = range_contract()
        response["output_requirements"] = [
            {"path": "../123.txt", "evidence": "123.txt"}
        ]

        with self.assertRaisesRegex(TaskContractValidationError, "unsafe path"):
            parse_task_contract("请总结1.txt,2.txt,.....100.txt为123.txt", response)


class TaskContractAuditorTest(unittest.TestCase):
    def test_reports_only_statically_replayed_inventory_mismatches(self):
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

        violations = list(LLMTaskContractAuditor(FakeClient(range_contract())).check(item))

        self.assertEqual(
            [violation.defect_type for violation in violations],
            ["artifact_data_gap", "task_artifact_contract_mismatch"],
        )
        self.assertTrue(all(violation.evidence_tier == "review" for violation in violations))
        self.assertTrue(all(violation.review_only for violation in violations))
        self.assertEqual(violations[0].evidence["missing_input_paths"], ["100.txt"])
        self.assertEqual(violations[1].evidence["missing_output_paths"], ["123.txt"])

    def test_clean_inventory_records_the_contract_without_a_finding(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"
        item = BenchmarkItem(
            item_id="clean",
            raw={
                "task": task,
                "input_files": [f"{index}.txt" for index in range(1, 101)],
                "output_files": ["123.txt"],
            },
            task=task,
        )

        violations = list(LLMTaskContractAuditor(FakeClient(range_contract())).check(item))

        self.assertEqual(violations, [])
        observation = item.metadata["_llm_observations"]["llm_task_contract"]
        self.assertEqual(observation["validation_status"], "validated")
        self.assertEqual(observation["inventory_replay"]["missing_input_count"], 0)

    def test_absent_inventory_does_not_turn_unknown_coverage_into_a_defect(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"
        item = BenchmarkItem(item_id="no-manifest", raw={"task": task}, task=task)

        violations = list(LLMTaskContractAuditor(FakeClient(range_contract())).check(item))

        self.assertEqual(violations, [])
        replay = item.metadata["_llm_observations"]["llm_task_contract"]["inventory_replay"]
        self.assertFalse(replay["input_inventory_available"])
        self.assertFalse(replay["output_inventory_available"])

    def test_explicitly_empty_inventories_are_replayed_as_missing(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"
        item = BenchmarkItem(
            item_id="empty-manifest",
            raw={"task": task, "input_files": [], "output_files": []},
            task=task,
        )

        violations = list(LLMTaskContractAuditor(FakeClient(range_contract())).check(item))

        self.assertEqual(
            [violation.defect_type for violation in violations],
            ["artifact_data_gap", "task_artifact_contract_mismatch"],
        )
        self.assertEqual(violations[0].evidence["missing_input_count"], 100)
        self.assertEqual(violations[1].evidence["missing_output_count"], 1)

    def test_invalid_model_output_is_an_operational_failure_not_a_defect(self):
        task = "请总结1.txt,2.txt,.....100.txt为123.txt"
        response = range_contract()
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
