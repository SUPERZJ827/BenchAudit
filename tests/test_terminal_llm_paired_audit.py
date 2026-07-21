from scripts.run_terminal_bench_llm_paired_audit import (
    llm_candidate_tasks,
    raw_llm_candidate_tasks,
)


def test_two_stage_candidates_require_accepted_rows():
    rows = {
        "accepted": {"findings": [], "accepted": [{"claim": "x"}]},
        "raw": {
            "findings": [{"severity": "major", "confidence": 0.9}],
            "accepted": [],
        },
    }

    assert llm_candidate_tasks(rows) == {"accepted"}
    assert raw_llm_candidate_tasks(rows) == {"raw"}
