from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "docs" / "security_claims_registry.json"
VALIDATOR = ROOT / "scripts" / "validate_safety_claim_registry.py"


def _module():
    spec = importlib.util.spec_from_file_location(
        "safety_claim_registry_validator", VALIDATOR,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registered_safety_claims_have_live_mutation_tests():
    assert _module().validate_registry(REGISTRY, ROOT) == []


def test_registry_validator_rejects_a_missing_mutation_test(tmp_path):
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    document["claims"][0]["mutation_test"]["function"] = (
        "test_intentionally_missing_mutation"
    )
    mutated = tmp_path / "mutated_registry.json"
    mutated.write_text(json.dumps(document), encoding="utf-8")

    errors = _module().validate_registry(mutated, ROOT)

    assert any("must exist exactly once" in error for error in errors)


def test_registry_validator_rejects_a_vacuous_test_contract(tmp_path):
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    document["claims"][0]["mutation_test"]["required_tokens"].append(
        "__TOKEN_NOT_EMITTED_BY_THE_REAL_TEST__"
    )
    mutated = tmp_path / "mutated_registry.json"
    mutated.write_text(json.dumps(document), encoding="utf-8")

    errors = _module().validate_registry(mutated, ROOT)

    assert any("lacks required tokens" in error for error in errors)
