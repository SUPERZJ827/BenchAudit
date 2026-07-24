import json
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import noncode_pattern_corpus as noncode
import run_pattern_memory_online_adaptation as online


def _stats(*, supported_family: str | None = None):
    return {
        family: {
            "eligible_tasks": 10,
            "confirmed_findings": int(family == supported_family),
            "confirmed_yield": 0.1 if family == supported_family else 0.0,
        }
        for family in noncode.PROBE_FAMILIES
    }


def _corpus(count=3):
    applicable = list(noncode.PROBE_FAMILIES[:4])
    return [
        {
            "dataset": "synthetic",
            "task_id": f"item-{index}",
            "applicable": applicable,
            # Deliberately no outcomes: labels live in a separate object.
        }
        for index in range(count)
    ]


def test_future_target_label_cannot_change_prior_selections():
    corpus = _corpus(2)
    first = online.run_policy(
        corpus,
        {},
        _stats(),
        policy="H_online_ucb1",
        budget=2,
        exploration_constant=2**0.5,
        seed=17,
    )
    second = online.run_policy(
        corpus,
        {"item-1": frozenset({noncode.PROBE_FAMILIES[0]})},
        _stats(),
        policy="H_online_ucb1",
        budget=2,
        exploration_constant=2**0.5,
        seed=17,
    )
    # item-1's reward is revealed only after its probes are selected, and
    # there is no item after it.  The complete selection trace must match.
    assert first["selection_sha256"] == second["selection_sha256"]
    assert first["confirmed_findings"] != second["confirmed_findings"]


def test_all_policies_spend_the_same_probe_budget():
    corpus = _corpus(3)
    labels = {
        "item-0": frozenset({noncode.PROBE_FAMILIES[0]}),
    }
    probe_counts = {
        online.run_policy(
            corpus,
            labels,
            _stats(supported_family=noncode.PROBE_FAMILIES[1]),
            policy=policy,
            budget=2,
            exploration_constant=2**0.5,
            seed=23,
        )["probes"]
        for policy in online.POLICIES
    }
    assert probe_counts == {6}


def test_workspace_loader_excludes_contract_dependent_annotations(tmp_path):
    path = tmp_path / "workspace.json"
    path.write_text(json.dumps([
        {
            "item": "safe",
            "label": "已确认·确定性矛盾",
            "family": "placeholder_leak",
        },
        {
            "item": "excluded",
            "label": "已确认·确定性矛盾",
            "family": "task_vs_contract_filename",
        },
        {
            "item": "review",
            "label": "客观证据支持·仍需语义判定",
            "family": "placeholder_leak",
        },
    ], ensure_ascii=False), encoding="utf-8")
    assert online.load_workspace_confirmed(path) == {
        "safe": frozenset({"placeholder_leak"}),
    }


def test_gdpval_loader_accepts_only_confirmed_replays(tmp_path):
    path = tmp_path / "gdpval.json"
    path.write_text(json.dumps({
        "violations": [
            {
                "item_id": "format",
                "evidence_tier": "confirmed",
                "defect_type": "task_artifact_contract_mismatch",
                "message": (
                    "The published deliverable format conflicts with an "
                    "explicit task output format."
                ),
            },
            {
                "item_id": "review",
                "evidence_tier": "review",
                "defect_type": "task_artifact_contract_mismatch",
                "message": (
                    "The published deliverable format conflicts with an "
                    "explicit task output format."
                ),
            },
        ]
    }), encoding="utf-8")
    assert online.load_gdpval_confirmed(path) == {
        "format": frozenset({"task_output_format"}),
    }


def test_confirmed_label_must_be_applicable():
    corpus = [{
        "task_id": "item",
        "applicable": ["placeholder_leak"],
    }]
    try:
        online.validate_label_applicability(
            corpus,
            {"item": frozenset({"task_output_filename"})},
        )
    except ValueError as exc:
        assert "not probe-applicable" in str(exc)
    else:
        raise AssertionError("invalid confirmed label was accepted")
