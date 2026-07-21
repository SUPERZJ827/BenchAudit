from benchcore.paired_claim_adjudication import (
    FrozenClaim,
    aggregate_trials,
    build_pair_prompt,
    map_trial_to_versions,
    parse_pair_response,
)


def _claim() -> FrozenClaim:
    return FrozenClaim(
        candidate_id="task:abc",
        category="verifier_undercoverage",
        claim="The verifier does not check the required result.",
        why_material="An invalid solution can pass.",
        artifact_path="tests/test.py",
        artifact_quote="assert output.exists()",
        instruction_quote="Compute the exact result.",
    )


def _raw(a_verdict: str = "supported", b_verdict: str = "refuted") -> dict:
    return {
        "claims": [{
            "candidate_id": "task:abc",
            "A": {
                "verdict": a_verdict,
                "confidence": 0.9,
                "path": "tests/test.py" if a_verdict == "supported" else "",
                "quote": "assert output.exists()" if a_verdict == "supported" else "",
                "reason": "A only checks existence.",
            },
            "B": {
                "verdict": b_verdict,
                "confidence": 0.9,
                "path": "tests/test.py" if b_verdict == "supported" else "",
                "quote": "assert exact_result(output)" if b_verdict == "supported" else "",
                "reason": "B checks the value.",
            },
            "comparison": "A_worse",
            "comparison_reason": "A omits the central assertion.",
        }]
    }


def test_prompt_is_blinded_and_contains_frozen_ids() -> None:
    system, user = build_pair_prompt(
        [_claim()],
        {"tests/test.py": "assert output.exists()"},
        {"tests/test.py": "assert exact_result(output)"},
        nonce="nonce-1",
    )
    assert "task:abc" in user
    assert "PACKET_A" in user and "PACKET_B" in user
    assert "2.0" not in user and "2.1" not in user
    assert "untrusted" in system


def test_parser_demotes_ungrounded_supported_verdict() -> None:
    raw = _raw()
    raw["claims"][0]["A"]["quote"] = "invented assertion"
    parsed = parse_pair_response(
        raw,
        [_claim()],
        {"tests/test.py": "assert output.exists()"},
        {"tests/test.py": "assert exact_result(output)"},
    )
    assert parsed["valid"] is True
    assert parsed["invalid_grounding"] == 1
    assert parsed["claims"][0]["A"]["verdict"] == "uncertain"


def test_ba_mapping_recovers_old_and_new_sides() -> None:
    parsed = parse_pair_response(
        _raw(a_verdict="supported", b_verdict="refuted"),
        [_claim()],
        {"tests/test.py": "assert output.exists()"},
        {"tests/test.py": "assert exact_result(output)"},
    )
    mapped = map_trial_to_versions(parsed, order="BA")
    row = mapped["claims"][0]
    assert row["old"]["verdict"] == "refuted"
    assert row["new"]["verdict"] == "supported"
    assert row["comparison"] == "new_worse"


def test_aggregate_requires_stability_in_both_orders() -> None:
    trials = []
    for seed, order in enumerate(("AB", "BA", "BA", "AB", "AB", "BA")):
        trials.append({
            "valid": True,
            "seed": seed,
            "order": order,
            "claims": [{
                "candidate_id": "task:abc",
                "old": {"verdict": "supported", "confidence": 0.9, "evidence_grounded": True},
                "new": {"verdict": "refuted", "confidence": 0.9, "evidence_grounded": True},
                "comparison": "old_worse",
            }],
        })
    result = aggregate_trials(trials, ["task:abc"])
    assert result["task_stable_old_only"] is True
    assert result["claims"][0]["directional"] == 6
    assert result["claims"][0]["order_directional"] == {"AB": 3, "BA": 3}


def test_aggregate_rejects_one_order_only_effect() -> None:
    trials = []
    for seed, order in enumerate(("AB", "BA", "BA", "AB", "AB", "BA")):
        directional = order == "AB"
        trials.append({
            "valid": True,
            "seed": seed,
            "order": order,
            "claims": [{
                "candidate_id": "task:abc",
                "old": {
                    "verdict": "supported" if directional else "refuted",
                    "confidence": 0.9,
                    "evidence_grounded": True,
                },
                "new": {"verdict": "refuted", "confidence": 0.9, "evidence_grounded": True},
                "comparison": "old_worse" if directional else "same",
            }],
        })
    result = aggregate_trials(trials, ["task:abc"])
    assert result["task_stable_old_only"] is False
