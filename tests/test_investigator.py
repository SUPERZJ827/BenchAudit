import json
from pathlib import Path

from benchcore.investigator import (
    investigate_audit_report,
    investigation_terms,
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
