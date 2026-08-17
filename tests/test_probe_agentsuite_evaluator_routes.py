from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/probe_agentsuite_evaluator_routes.py"
SPEC = importlib.util.spec_from_file_location("probe_agentsuite_evaluator_routes", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

normal_model_output = MODULE.normal_model_output
probe_candidates = MODULE.probe_candidates
route_id = MODULE.route_id
value_shape = MODULE.value_shape


def test_normal_model_output_splits_parallel_calls_and_removes_instance_suffix() -> None:
    reference = {
        "lookup_1": {"city": "Paris"},
        "lookup_2": {"city": "Tokyo"},
    }
    assert normal_model_output(reference) == [
        {"lookup": {"city": "Paris"}},
        {"lookup": {"city": "Tokyo"}},
    ]


def test_route_id_is_stable_and_bound_to_evaluator_hash() -> None:
    first = route_id("a" * 64, "normal_checker", "str", ["type_checker", "string_checker:normal"])
    repeated = route_id("a" * 64, "normal_checker", "str", ["type_checker", "string_checker:normal"])
    changed = route_id("b" * 64, "normal_checker", "str", ["type_checker", "string_checker:normal"])
    assert first == repeated
    assert first != changed


def test_value_shape_follows_comparator_shape_not_enum_metadata() -> None:
    assert value_shape("Summary", {"type": "string", "enum": ["Summary", "Detailed"]}) == "str"
    assert value_shape("free text", {"type": "string"}) == "str"
    assert value_shape(1, {"type": "integer"}) == "number"
    assert value_shape(1.5, {"type": "float"}) == "number"
    assert value_shape(True, {"type": "boolean"}) == "bool"


def test_probe_candidates_are_single_parameter_and_bounded() -> None:
    reference = {"render": {"detail": "Summary", "topic": "AI"}}
    probes = probe_candidates(
        reference=reference,
        reference_function_name="render",
        parameter_name="detail",
        schema={"type": "string", "enum": ["Summary", "Detailed"]},
        required={"topic"},
    )
    assert [name for name, _, _ in probes] == ["omit_optional", "enum_swap"]
    assert probes[0][1] == {"render": {"topic": "AI"}}
    assert probes[1][1] == {"render": {"detail": "Detailed", "topic": "AI"}}
    assert reference == {"render": {"detail": "Summary", "topic": "AI"}}
