from scripts.run_agentsuite_negative_challenger import challenger_candidate
from scripts.score_agentsuite_negative_challenger import challenger_ids_at_threshold


def test_challenger_candidate_requires_concrete_material_evidence():
    valid = {
        "status": "defect",
        "defect_type": "parameter_contract",
        "reference_target": "search.limit",
        "contradiction": "limit exceeds the declared maximum",
        "task_or_policy_evidence": "schema maximum is 10",
        "reference_evidence": "limit=20",
        "material": True,
        "confidence": 0.9,
    }
    assert challenger_candidate(valid)
    for key in (
        "reference_target",
        "contradiction",
        "task_or_policy_evidence",
        "reference_evidence",
    ):
        broken = dict(valid)
        broken[key] = ""
        assert not challenger_candidate(broken)


def test_challenger_candidate_rejects_uncertain_nonmaterial_and_low_confidence():
    base = {
        "status": "defect",
        "defect_type": "policy_or_state",
        "reference_target": "call[0]",
        "contradiction": "contradiction",
        "task_or_policy_evidence": "policy evidence",
        "reference_evidence": "reference evidence",
        "material": True,
        "confidence": 0.9,
    }
    assert not challenger_candidate({**base, "status": "uncertain"})
    assert not challenger_candidate({**base, "material": False})
    assert not challenger_candidate({**base, "confidence": 0.44})
    assert not challenger_candidate({**base, "defect_type": "none"})


def test_confidence_thresholds_are_nested_without_changing_evidence_tier():
    rows = [
        {
            "item_id": "high",
            "operational_error": None,
            "result": {
                "status": "defect",
                "defect_type": "parameter_contract",
                "reference_target": "call.x",
                "contradiction": "bad x",
                "task_or_policy_evidence": "x must be 1",
                "reference_evidence": "x=2",
                "material": True,
                "confidence": 0.9,
            },
        },
        {
            "item_id": "medium",
            "operational_error": None,
            "result": {
                "status": "defect",
                "defect_type": "task_alignment",
                "reference_target": "call[0]",
                "contradiction": "wrong task",
                "task_or_policy_evidence": "request A",
                "reference_evidence": "does B",
                "material": True,
                "confidence": 0.65,
            },
        },
    ]
    assert challenger_ids_at_threshold(rows, 0.45) == {"high", "medium"}
    assert challenger_ids_at_threshold(rows, 0.8) == {"high"}
