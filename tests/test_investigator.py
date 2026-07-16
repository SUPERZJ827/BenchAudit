import json
from pathlib import Path

from benchcore.investigator import (
    aggregate_investigator_results,
    apply_evidence_verdict,
    apply_harness_dependency_gate,
    investigate_audit_report,
    investigation_terms,
    load_report_items,
    refine_investigation_report,
    summarize_investigation_rows,
    write_investigation_markdown,
)
from benchcore.llm_client import LLMConfig, LLMClient


class FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat_json(self, system, user):
        self.calls.append((system, user))
        return dict(self.response)


class RepeatedFakeLLMClient:
    def __init__(self, responses, verifier_response=None):
        self.responses = responses
        self.verifier_response = verifier_response
        self.calls = []

    def chat_json_repeated(self, system, user, passes):
        self.calls.append(("repeat", passes, system, user))
        return [dict(row) for row in self.responses[:passes]]

    def chat_json(self, system, user):
        self.calls.append(("single", system, user))
        return dict(self.verifier_response or {})


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def test_investigator_loads_item_and_returns_verdict(tmp_path: Path):
    input_path = tmp_path / "items.jsonl"
    data_file = tmp_path / "source.txt"
    data_file.write_text("The emergency mutual aid agreement is present.", encoding="utf-8")
    write_jsonl(
        input_path,
        [
            {
                "item_id": "wb-1",
                "task": "Create a report from the provided source.",
                "context": ["source.txt"],
                "output_contract": {"required_files": ["report.md"]},
                "evaluator": {"rubrics": ["Does the report mention emergency mutual assistance?"]},
            }
        ],
    )
    report_path = tmp_path / "audit.json"
    report_path.write_text(
        json.dumps(
            {
                "field_mapping": {
                    "item_id": "item_id",
                    "task": "task",
                    "context": ["context"],
                    "output_contract": "output_contract",
                    "evaluator": "evaluator",
                    "metadata": [],
                },
                "violations": [
                    {
                        "item_id": "wb-1",
                        "row_uid": "source-row-00000000",
                        "artifact": "context_attachment",
                        "mechanism": "missing",
                        "defect_type": "artifact_data_gap",
                        "severity": "review",
                        "confidence": 0.8,
                        "message": "Rubric requires mutual assistance but input lacks it.",
                        "detection_method": "grounded_rubric_consistency",
                        "evidence": {
                            "rubric": "Does the report mention emergency mutual assistance?",
                            "missing": ["emergency mutual assistance"],
                        },
                        "review_only": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = FakeLLMClient(
        {
            "verdict": "false_positive",
            "confidence": 0.9,
            "issue_category": "data_gap",
            "claim": "The data-gap claim is refuted.",
            "evidence_from_input": "source.txt contains emergency mutual aid agreement.",
            "counter_evidence": "aid is semantically equivalent to assistance.",
            "reasoning": "The input grounds the rubric.",
            "recommended_action": "no_action",
        }
    )

    result = investigate_audit_report(
        input_path=input_path,
        report_path=report_path,
        client=client,
        root=tmp_path,
    )

    assert result["summary"]["verdict_distribution"] == {"false_positive": 1}
    assert result["investigations"][0]["item_id"] == "wb-1"
    assert "emergency mutual aid agreement" in client.calls[0][1]


def test_report_item_index_never_collapses_duplicate_item_ids(tmp_path: Path):
    input_path = tmp_path / "duplicates.jsonl"
    write_jsonl(input_path, [
        {"item_id": "duplicate", "task": "first task"},
        {"item_id": "duplicate", "task": "second task"},
    ])
    report = {
        "field_mapping": {
            "item_id": "item_id",
            "task": "task",
            "context": [],
            "metadata": [],
        }
    }

    items = load_report_items(input_path, report)

    assert "duplicate" not in items
    assert items.resolve({"item_id": "duplicate"}) is None
    assert items.resolve({
        "item_id": "duplicate", "row_uid": "source-row-00000000",
    }).task == "first task"
    assert items.resolve({
        "item_id": "duplicate", "row_uid": "source-row-00000001",
    }).task == "second task"
    assert items.resolve({
        "item_id": "wrong-id", "row_uid": "source-row-00000000",
    }) is None


def test_report_item_index_rejects_unique_legacy_row_without_row_uid(tmp_path: Path):
    input_path = tmp_path / "unique.jsonl"
    write_jsonl(input_path, [{"item_id": "unique", "task": "task"}])
    items = load_report_items(input_path, {
        "field_mapping": {"item_id": "item_id", "task": "task"},
    })

    assert items.resolve({"item_id": "unique"}) is None


def test_investigation_summary_counts_duplicate_ids_by_row_uid():
    rows = [
        {
            "item_id": "duplicate", "row_uid": "source-row-00000000",
            "verdict": "likely_true", "issue_category": "other",
            "defect_type": "wrong_gold_answer", "agreement": 1.0,
            "evidence_verdict": "supported",
        },
        {
            "item_id": "duplicate", "row_uid": "source-row-00000001",
            "verdict": "likely_true", "issue_category": "other",
            "defect_type": "wrong_gold_answer", "agreement": 1.0,
            "evidence_verdict": "supported",
        },
    ]

    summary = summarize_investigation_rows(
        rows,
        input_path="items.jsonl",
        report_path="audit.json",
        total_candidates=2,
    )

    assert summary["likely_true_items"] == 2


def test_investigation_terms_extract_rubric_and_message_terms():
    terms = investigation_terms(
        {
            "message": "Rubric requires slide 4 to contain risk matrix.",
            "evidence": {"rubric": "Does slide 4 include `risk_matrix.png`?"},
        }
    )

    assert "4" in terms
    assert "risk_matrix.png" in terms


def test_write_investigation_markdown_groups_cases(tmp_path: Path):
    report = {
        "summary": {
            "input_path": "items.jsonl",
            "source_report": "audit.json",
            "investigation_count": 1,
            "verdict_distribution": {"likely_true": 1},
            "issue_category_distribution": {"contract_mismatch": 1},
        },
        "investigations": [
            {
                "item_id": "wb-2",
                "verdict": "likely_true",
                "issue_category": "contract_mismatch",
                "defect_type": "output_evaluator_contract_mismatch",
                "detection_method": "rubric_output_contract_consistency",
                "confidence": 0.95,
                "original_confidence": 0.9,
                "claim": "Contract requires output.md but task requires report.docx.",
                "original_message": "Contract mismatch",
                "evidence_from_task": "task names report.docx",
                "evidence_from_input": "",
                "evidence_from_rubric": "",
                "evidence_from_contract": "contract names output.md",
                "counter_evidence": "",
                "reasoning": "deliverables differ",
                "recommended_action": "repair",
            }
        ],
    }

    out = tmp_path / "investigation.md"
    write_investigation_markdown(out, report)

    text = out.read_text(encoding="utf-8")
    assert "Benchmark Issue Investigation Report" in text
    assert "`wb-2`" in text
    assert "Contract evidence" in text


def test_cli_dry_run_shape(tmp_path: Path):
    # Smoke-test the real LLM dry-run client response normalization.
    client = LLMClient(LLMConfig(model="m", base_url="http://localhost", dry_run=True))
    assert client.chat_json("s", "u")["defect_type"] == "none"


def test_aggregate_independent_passes_requires_quorum():
    result = aggregate_investigator_results(
        [
            {"verdict": "likely_true", "confidence": 0.9, "reasoning": "a"},
            {"verdict": "false_positive", "confidence": 0.8, "reasoning": "b"},
            {"verdict": "uncertain", "confidence": 0.7, "reasoning": "c"},
        ]
    )

    assert result["verdict"] == "uncertain"
    assert result["verdict_votes"] == {
        "likely_true": 1,
        "false_positive": 1,
        "uncertain": 1,
    }
    assert result["agreement"] == 1 / 3


def test_aggregate_independent_passes_uses_majority_and_discounted_confidence():
    result = aggregate_investigator_results(
        [
            {"verdict": "likely_true", "confidence": 0.9, "claim": "first"},
            {"verdict": "likely_true", "confidence": 0.8, "claim": "second"},
            {"verdict": "false_positive", "confidence": 0.95, "claim": "third"},
        ]
    )

    assert result["verdict"] == "likely_true"
    assert result["pass_count"] == 3
    assert result["agreement"] == 2 / 3
    assert round(result["confidence"], 4) == round(0.85 * 2 / 3, 4)


def test_evidence_verifier_downgrades_unconfirmed_consensus():
    result = apply_evidence_verdict(
        {
            "verdict": "likely_true",
            "confidence": 0.8,
            "reasoning": "passes support it",
            "recommended_action": "repair",
        },
        {
            "evidence_verdict": "insufficient",
            "confidence": 0.9,
            "reasoning": "the relevant input was truncated",
        },
    )

    assert result["verdict"] == "uncertain"
    assert result["confidence"] == 0.0
    assert result["recommended_action"] == "keep_for_review"


def test_harness_gate_downgrades_save_location_only_finding():
    result = apply_harness_dependency_gate(
        {
            "defect_type": "underconstrained_evaluator_risk",
            "message": "No rubric checks that the file is saved to the desktop directory.",
        },
        {
            "verdict": "likely_true",
            "confidence": 0.95,
            "issue_category": "evaluator_undercoverage",
            "claim": "The output location is not checked.",
            "reasoning": "Rubrics omit the desktop path.",
            "recommended_action": "repair",
        },
    )

    assert result["verdict"] == "uncertain"
    assert result["issue_category"] == "harness_dependent"
    assert result["confidence"] == 0.0


def test_harness_gate_keeps_explicit_path_conflict():
    original = {
        "verdict": "likely_true",
        "confidence": 0.9,
        "issue_category": "task_rubric_mismatch",
        "claim": "Rubric checks a different directory than the task requires.",
    }
    result = apply_harness_dependency_gate(
        {
            "defect_type": "underconstrained_evaluator_risk",
            "message": "Task and rubric require different paths.",
        },
        original,
    )

    assert result == original


def test_refine_report_recomputes_summary_without_llm_calls():
    report = {
        "summary": {
            "input_path": "items.jsonl",
            "source_report": "audit.json",
            "candidates_investigated": 1,
        },
        "investigations": [{
            "item_id": "wb-1",
            "verdict": "likely_true",
            "confidence": 0.95,
            "issue_category": "evaluator_undercoverage",
            "claim": "No rubric checks that the file is saved to the desktop directory.",
            "reasoning": "path omitted",
            "recommended_action": "repair",
            "evidence_verdict": "supported",
            "agreement": 1.0,
            "defect_type": "underconstrained_evaluator_risk",
            "source_violation": {"defect_type": "underconstrained_evaluator_risk"},
        }],
    }

    refined = refine_investigation_report(report)

    assert refined["investigations"][0]["verdict"] == "uncertain"
    assert refined["summary"]["verdict_distribution"] == {"uncertain": 1}
    assert refined["refinement"]["changed_verdicts"] == 1
    assert refined["refinement"]["llm_calls"] == 0


def test_rigorous_investigation_records_passes_and_verification(tmp_path: Path):
    input_path = tmp_path / "items.jsonl"
    write_jsonl(
        input_path,
        [{
            "item_id": "wb-2",
            "task": "Create report.docx.",
            "context": ["source.txt"],
            "output_contract": {"required_files": ["output.md"]},
            "evaluator": {"rubrics": ["Can report.docx be opened?"]},
        }],
    )
    (tmp_path / "source.txt").write_text("source", encoding="utf-8")
    report_path = tmp_path / "audit.json"
    report_path.write_text(json.dumps({
        "field_mapping": {
            "item_id": "item_id",
            "task": "task",
            "context": ["context"],
            "output_contract": "output_contract",
            "evaluator": "evaluator",
            "metadata": [],
        },
        "violations": [{
            "item_id": "wb-2",
            "row_uid": "source-row-00000000",
            "artifact": "evaluator",
            "defect_type": "output_evaluator_contract_mismatch",
            "confidence": 0.9,
            "message": "Contract requires output.md but rubric requires report.docx.",
            "detection_method": "rubric_output_contract_consistency",
            "evidence": {"rubric": "Can report.docx be opened?"},
        }],
    }), encoding="utf-8")
    passes = [{
        "verdict": "likely_true",
        "confidence": 0.9,
        "issue_category": "contract_mismatch",
        "claim": "deliverables differ",
        "reasoning": "task and contract differ",
        "recommended_action": "repair",
    }] * 3
    client = RepeatedFakeLLMClient(
        passes,
        verifier_response={
            "evidence_verdict": "supported",
            "confidence": 0.95,
            "verified_evidence": ["task names report.docx; contract names output.md"],
            "unsupported_claims": [],
            "contradictions": [],
            "reasoning": "the mismatch is explicit",
        },
    )

    result = investigate_audit_report(
        input_path=input_path,
        report_path=report_path,
        client=client,
        verifier_client=client,
        investigator_passes=3,
        root=tmp_path,
    )

    row = result["investigations"][0]
    assert row["verdict"] == "likely_true"
    assert row["pass_count"] == 3
    assert row["verdict_votes"] == {"likely_true": 3}
    assert row["evidence_verdict"] == "supported"
    assert len(row["independent_results"]) == 3
