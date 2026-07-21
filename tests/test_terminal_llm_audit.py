from pathlib import Path

from benchcore.terminal_llm_audit import (
    EvidencePacket,
    accepted_candidate,
    build_evidence_packet,
    investigate_task,
    quote_is_grounded,
    select_audit_text,
    validate_investigator_response,
    verify_finding,
)


class FakeClient:
    def __init__(self, response):
        self.response = response

    def chat_json(self, system, user):
        return self.response


class TruncatingThenCompactClient:
    def __init__(self):
        self.calls = 0

    def chat_json(self, system, user):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("LLM JSON response was truncated")
        return {"status": "consistent", "findings": [], "summary": "No defect."}


def packet() -> EvidencePacket:
    return EvidencePacket(
        task_id="x",
        rendered="===== FILE: tests/test.py =====\nassert files == ['a']",
        sources={
            "instruction.md": "Create the required output.",
            "tests/test.py": "assert files == ['a']",
        },
        truncated_files=(),
    )


def test_quote_grounding_normalizes_whitespace_but_requires_real_path():
    p = packet()

    assert quote_is_grounded("tests/test.py", "assert   files == ['a']", p.sources)
    assert not quote_is_grounded("tests/missing.py", "assert files == ['a']", p.sources)


def test_investigator_drops_hallucinated_evidence():
    raw = {
        "findings": [
            {
                "category": "verifier_overconstraint",
                "severity": "major",
                "confidence": 0.9,
                "artifact_path": "tests/test.py",
                "artifact_quote": "this quote is not present",
                "instruction_quote": "",
                "claim": "over-strict",
                "why_material": "rejects valid output",
            }
        ]
    }

    findings, diagnostics = validate_investigator_response(raw, packet())

    assert findings == []
    assert diagnostics["invalid_evidence"] == 1


def test_verifier_acceptance_requires_grounded_support_quote():
    finding = {
        "category": "verifier_overconstraint",
        "severity": "major",
        "confidence": 0.9,
        "artifact_path": "tests/test.py",
        "artifact_quote": "assert files == ['a']",
        "claim": "over-strict",
    }
    result = verify_finding(
        FakeClient(
            {
                "verdict": "accepted",
                "confidence": 0.9,
                "supporting_artifact_path": "tests/test.py",
                "supporting_quote": "invented quote",
                "reason": "material",
            }
        ),
        packet(),
        finding,
    )

    assert result["verdict"] == "uncertain"
    assert not result["evidence_valid"]


def test_candidate_requires_two_high_confidence_major_votes():
    finding = {"severity": "major", "confidence": 0.8}
    verification = {"verdict": "accepted", "confidence": 0.8, "evidence_valid": True}

    assert accepted_candidate(finding, verification)
    assert not accepted_candidate({**finding, "severity": "minor"}, verification)
    assert not accepted_candidate(finding, {**verification, "verdict": "uncertain"})


def test_packet_prioritizes_instruction_and_bounds_large_tests(tmp_path: Path):
    task = tmp_path / "task"
    (task / "tests").mkdir(parents=True)
    (task / "instruction.md").write_text("Do X.", encoding="utf-8")
    (task / "task.toml").write_text("memory_mb = 4096\n", encoding="utf-8")
    (task / "tests" / "test.py").write_text(
        "noise\n" * 1000 + "assert Path('/app/x').exists()\n", encoding="utf-8"
    )

    result = build_evidence_packet(task, max_total_chars=2500, max_file_chars=1600)

    assert result.rendered.index("instruction.md") < result.rendered.index("task.toml")
    assert len(result.rendered) <= 2700
    assert "tests/test.py" in result.truncated_files


def test_select_audit_text_keeps_assertions_from_long_file():
    text = "boring\n" * 1000 + "assert result == expected\n"

    selected, truncated = select_audit_text(text, 1000)

    assert truncated
    assert "assert result == expected" in selected


def test_investigator_uses_compact_fallback_after_transport_truncation():
    client = TruncatingThenCompactClient()

    result = investigate_task(client, packet())

    assert client.calls == 2
    assert result["recovered_from_truncation"] is True
    assert result["findings"] == []
