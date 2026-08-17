from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/score_agentsuite_acebench_102.py"
SPEC = importlib.util.spec_from_file_location("score_agentsuite_acebench_102", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_eligible_finding_is_method_and_scope_locked() -> None:
    base = {
        "detection_method": "llm_cross_artifact_consistency",
        "defect_scope": "substantive",
        "defect_type": "reference_task_mismatch",
    }
    assert MODULE.eligible_finding(base)
    assert not MODULE.eligible_finding({**base, "detection_method": "static_rule"})
    assert not MODULE.eligible_finding({**base, "defect_scope": "operational"})
    assert not MODULE.eligible_finding({**base, "defect_type": "llm_audit_failure"})
