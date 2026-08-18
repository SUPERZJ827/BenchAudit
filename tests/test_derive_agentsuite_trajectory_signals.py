from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/derive_agentsuite_trajectory_signals.py"
SPEC = importlib.util.spec_from_file_location("derive_trajectory_signals", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_emitted_call_drops_a_reasoning_preamble() -> None:
    row = {"messages": [
        {"role": "user", "content": "do it"},
        {"role": "assistant", "content": "<think>\nlet me consider\n</think>\n[tool(a='1')]"},
    ]}
    assert MODULE.emitted_call(row) == "[tool(a='1')]"


def test_emitted_call_keeps_output_that_has_no_call() -> None:
    row = {"messages": [{"role": "assistant", "content": "I cannot answer"}]}
    assert MODULE.emitted_call(row) == "I cannot answer"


def test_unanimous_models_score_zero_disagreement() -> None:
    s = MODULE.signals(["[t(a=1)]"] * 5, [1, 1, 1, 1, 1])
    assert s["disagreement"] == 0.0
    assert s["failure_rate"] == 0.0
    assert s["distinct_outputs"] == 1


def test_a_split_on_one_parameter_shows_up_as_disagreement() -> None:
    s = MODULE.signals(["[t(a='x')]"] * 6 + ["[t(a='y')]"] * 4, [1] * 6 + [0] * 4)
    assert s["disagreement"] == 0.4
    assert s["failure_rate"] == 0.4
    assert s["majority_share"] == 0.6


def test_normalized_id_strips_only_its_own_task_prefix() -> None:
    assert MODULE.normalized_id("normal_atom_bool", "normal_atom_bool_33") == "33"
    assert MODULE.normalized_id("normal_atom_bool", "33") == "33"
    assert MODULE.normalized_id("normal_atom_bool", "other_33") == "other_33"
