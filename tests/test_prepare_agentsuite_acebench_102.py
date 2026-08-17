from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_agentsuite_acebench_102.py"
SPEC = importlib.util.spec_from_file_location("prepare_agentsuite_acebench_102", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_normalized_id_removes_only_declared_task_prefix() -> None:
    assert MODULE.normalized_id("normal_atom_bool", "normal_atom_bool_2") == "2"
    assert MODULE.normalized_id("normal_atom_bool", "2") == "2"
    assert MODULE.normalized_id("normal_atom_bool", "other_2") == "other_2"


def test_stable_item_id_keeps_task_namespace() -> None:
    assert (
        MODULE.stable_item_id("normal_atom_bool", "2")
        == "agentsuite-ace::normal_atom_bool::2"
    )


def test_nested_key_helper_distinguishes_text_from_fields() -> None:
    row = {"task": "Call get_is_issue_status", "context": {"safe": "is_issue"}}
    assert "is_issue" not in MODULE.nested_keys(row)
    assert "is_issue" in MODULE.nested_keys({"metadata": {"is_issue": 1}})


def test_parse_inline_structure_recovers_serialized_profile() -> None:
    value = "{'basic_features': {'UserName': 'John Doe'}, 'enabled': True}."
    assert MODULE.parse_inline_structure(value) == {
        "basic_features": {"UserName": "John Doe"},
        "enabled": True,
    }


def test_parse_inline_structure_does_not_execute_or_rewrite_prose() -> None:
    prose = "Use {literal braces} in the answer"
    assert MODULE.parse_inline_structure(prose) == prose
    expression = "__import__('os').system('false')"
    assert MODULE.parse_inline_structure(expression) == expression


def test_python_string_constant_reads_without_executing(tmp_path: Path) -> None:
    source = tmp_path / "prompts.py"
    source.write_text(
        "SAFE = '''quoted policy'''\nDANGER = __import__('os').system('false')\n",
        encoding="utf-8",
    )
    assert MODULE.python_string_constant(source, "SAFE") == "quoted policy"
