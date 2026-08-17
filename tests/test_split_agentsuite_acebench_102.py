from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/split_agentsuite_acebench_102.py"
SPEC = importlib.util.spec_from_file_location("split_agentsuite_acebench_102", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def odd_strata() -> dict[tuple[str, int], list[str]]:
    """Three odd positive strata and three odd negative strata."""
    return {
        (task, label): [f"{task}::{label}::{index}" for index in range(3)]
        for task in ("a", "b", "c")
        for label in (0, 1)
    }


def test_odd_members_do_not_skew_the_positive_count() -> None:
    strata = odd_strata()
    dev, test = MODULE.split_ids(strata, seed=1)
    positive = {item for key, members in strata.items() if key[1] == 1 for item in members}
    dev_positive = len(set(dev) & positive)
    test_positive = len(set(test) & positive)
    # A single alternation flag shared by both labels sends every odd positive
    # stratum the same way and yields 3/6 here.
    assert abs(dev_positive - test_positive) <= 1
    assert dev_positive + test_positive == len(positive)


def test_split_is_even_and_covers_every_item() -> None:
    strata = odd_strata()
    dev, test = MODULE.split_ids(strata, seed=1)
    every = {item for members in strata.values() for item in members}
    assert len(dev) == len(test)
    assert not set(dev) & set(test)
    assert set(dev) | set(test) == every


def test_split_is_deterministic_for_a_fixed_seed() -> None:
    assert MODULE.split_ids(odd_strata(), seed=7) == MODULE.split_ids(odd_strata(), seed=7)


def test_seed_is_derived_from_the_audit_input_hash() -> None:
    assert MODULE.seed_for("a" * 64) != MODULE.seed_for("b" * 64)
    assert MODULE.seed_for("a" * 64) == MODULE.seed_for("a" * 64)


def test_strata_key_on_task_name_and_human_label() -> None:
    rows = [
        {"id": "x::1", "metadata": {"task_name": "normal_preference"}},
        {"id": "x::2", "metadata": {"task_name": "normal_preference"}},
        {"id": "x::3", "metadata": {"task_name": "normal_atom_enum"}},
    ]
    strata = MODULE.build_strata(rows, {"x::1": 1, "x::2": 0, "x::3": 1})
    assert strata == {
        ("normal_preference", 1): ["x::1"],
        ("normal_preference", 0): ["x::2"],
        ("normal_atom_enum", 1): ["x::3"],
    }
