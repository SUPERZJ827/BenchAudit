import json

from benchcore.forensic import build_forensic_bundle


def test_build_forensic_bundle_includes_item_reports_and_evidence(tmp_path):
    input_path = tmp_path / "bench.jsonl"
    source = tmp_path / "source.txt"
    source.write_text("The expected export analysis section is present here.", encoding="utf-8")
    input_path.write_text(
        json.dumps(
            {
                "item_id": "workspacebench-1",
                "task": "Create a report with sales and export analysis.",
                "input_files": [str(source)],
                "rubrics": ["Does the report include sales analysis?"],
                "output_contract": {"type": "workspace_files", "required_files": ["report.docx"]},
                "evaluator": {"type": "workspacebench_rubric"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report_path = tmp_path / "audit.json"
    report_path.write_text(
        json.dumps(
            {
                "field_mapping": {
                    "item_id": "item_id",
                    "task": "task",
                    "context": ["input_files"],
                    "output_contract": "output_contract",
                    "evaluator": "evaluator",
                },
                "violations": [
                    {
                        "item_id": "workspacebench-1",
                        "defect_type": "underconstrained_evaluator_risk",
                        "detection_method": "rubric_coverage",
                        "message": "Rubric omits export analysis.",
                        "evidence": {"missing_obligations": ["export analysis"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    investigation_path = tmp_path / "investigation.json"
    investigation_path.write_text(
        json.dumps(
            {
                "investigations": [
                    {
                        "item_id": "workspacebench-1",
                        "verdict": "likely_true",
                        "issue_category": "other",
                        "claim": "Rubric omits export analysis.",
                        "reasoning": "The task asks for export analysis.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    bundle = build_forensic_bundle(
        input_path=input_path,
        item_id="workspacebench-1",
        report_path=report_path,
        investigation_path=investigation_path,
        root=tmp_path,
    )

    assert bundle["item_id"] == "workspacebench-1"
    assert len(bundle["candidate_violations"]) == 1
    assert len(bundle["investigations"]) == 1
    assert "export analysis" in bundle["evidence_context"]
