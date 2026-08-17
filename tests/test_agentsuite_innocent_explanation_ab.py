from scripts.run_agentsuite_innocent_explanation_ab import (
    build_treatment_prompt,
    passes_innocent_explanation_gate,
)


def test_treatment_prompt_adds_only_frozen_epistemic_fields():
    base = '''Be conservative:\nReturn ONLY JSON:\n{{\n  "severity": "high|medium|low|none",\n}}'''
    prompt = build_treatment_prompt(base)
    assert "claims to audit" in prompt
    assert "strongest_innocent_explanation" in prompt
    assert "innocent_explanation_ruled_out" in prompt
    assert "Be conservative:\nReturn ONLY JSON:" in prompt


def test_innocent_gate_requires_explanation_boolean_and_evidence():
    valid = {
        "status": "reference_mismatch",
        "strongest_innocent_explanation": "The value may come from a stated default.",
        "innocent_explanation_ruled_out": True,
        "why_ruled_out": "The schema explicitly has no default and the policy forbids invention.",
    }
    assert passes_innocent_explanation_gate(valid)
    for key in (
        "strongest_innocent_explanation",
        "innocent_explanation_ruled_out",
        "why_ruled_out",
    ):
        broken = dict(valid)
        broken.pop(key)
        assert not passes_innocent_explanation_gate(broken)


def test_innocent_gate_never_emits_consistent_or_uncertain():
    payload = {
        "strongest_innocent_explanation": "An innocent explanation.",
        "innocent_explanation_ruled_out": True,
        "why_ruled_out": "Evidence.",
    }
    assert not passes_innocent_explanation_gate({**payload, "status": "consistent"})
    assert not passes_innocent_explanation_gate({**payload, "status": "uncertain"})
