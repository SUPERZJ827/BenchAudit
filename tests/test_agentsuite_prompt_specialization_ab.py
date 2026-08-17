from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_agentsuite_prompt_specialization_ab.py"


def load_script():
    spec = importlib.util.spec_from_file_location("prompt_ab", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_routes_and_generic_prompt_do_not_name_dataset() -> None:
    module = load_script()
    assert "ACEBench" not in module.GENERIC_PROMPT
    assert "AgentSuite" not in module.GENERIC_PROMPT
    assert "COBA" not in module.GENERIC_PROMPT
    assert module.route_for({"metadata": {"task_name": "normal_atom_bool"}}) == "default"
    assert module.route_for({"metadata": {"task_name": "agent_multi_turn"}}) == "agent"
    assert module.route_for({"metadata": {"task_name": "special_error_param"}}) == "special"


def test_response_contract_is_strict_on_required_fields() -> None:
    module = load_script()
    good = {
        "reasoning": "because",
        "reasoning_summary": "short",
        "error_category": "Not Flawed",
        "is_flawed": False,
    }
    assert module.validate_response(good) is None
    assert module.validate_response({**good, "is_flawed": "false"}) == "is_flawed_not_boolean"
    broken = dict(good)
    del broken["reasoning_summary"]
    assert module.validate_response(broken) == "missing_reasoning_summary"


def test_materialized_route_counts_and_prompt_rendering() -> None:
    module = load_script()
    root = Path("/home/zhoujun/llmdata/AgentSuite-main")
    data = ROOT / "reports/agentsuite_acebench_102_solver_role_dev_20260816/materialized/audit_input.jsonl"
    if not root.exists() or not data.exists():
        return
    rows = [json.loads(line) for line in data.read_text(encoding="utf-8").splitlines()]
    counts = {route: sum(module.route_for(row) == route for row in rows) for route in ("default", "agent", "special")}
    assert counts == {"default": 100, "agent": 2, "special": 0}
    for row in rows:
        specialized = module.render_specialized(row, root)
        generic = module.render_generic(row, root)
        assert row["task"] in specialized
        assert row["task"] in generic
        assert json.dumps(module.normalize_ground_truth(row["reference_solution"]), indent=2) in specialized
        assert json.dumps(module.normalize_ground_truth(row["reference_solution"]), indent=2) in generic


def test_numeric_suffix_ground_truth_normalization_matches_upstream() -> None:
    module = load_script()
    value = {"tool_1": {"x": 1}, "tool_2": [{"x": 2}, {"x": 3}]}
    assert module.normalize_ground_truth(value) == [
        {"tool": {"x": 1}},
        {"tool": {"x": 2}},
        {"tool": {"x": 3}},
    ]
