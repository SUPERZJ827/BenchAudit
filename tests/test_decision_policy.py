"""The decision surface must be enumerable, hashable, and recorded.

A blind-holdout claim of the form "thresholds were frozen before labels were
read" is only checkable if a run records exactly which thresholds it used.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from benchcore import comparison, decision_policy as dp


def test_policy_hash_is_stable_across_calls():
    assert dp.decision_policy_sha256() == dp.decision_policy_sha256()


def test_runtime_threshold_change_changes_the_hash():
    base = dp.decision_policy_sha256()
    moved = dp.decision_policy_sha256(llm_confirm_threshold=0.9)
    assert base != moved


def test_declared_constant_change_changes_the_hash(monkeypatch):
    base = dp.decision_policy_sha256()
    monkeypatch.setattr(dp, "STRONG_SIGNAL_MIN_CONFIDENCE", 0.61)
    assert dp.decision_policy_sha256() != base


def test_snapshot_carries_policy_and_hash():
    snap = dp.decision_policy_snapshot()
    assert snap["sha256"] == dp.decision_policy_sha256(snap["policy"])
    assert snap["policy"]["schema_version"] == dp.POLICY_SCHEMA_VERSION


# Inline thresholds that predate the policy module.  Each entry is a known
# gap, not an approval: the audit decision path (comparison / llm_auditor /
# promotion / auditor) must stay empty, and anything new anywhere fails.
KNOWN_INLINE_THRESHOLDS = {
    "artifact_consistency.py",   # grounded-rubric strictness gates (0.8 / 0.65)
    "evolution/models.py",       # confidence range validation, not a gate
}

CORE_DECISION_MODULES = {
    "comparison.py",
    "llm_auditor.py",
    "promotion.py",
    "auditor.py",
}


def _inline_threshold_sites():
    root = Path(__file__).resolve().parent.parent / "benchcore"
    pattern = re.compile(r"(<=?|>=?)\s*(0\.\d+|max\([^)]*0\.\d+\))")
    sites = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "decision_policy.py":
            continue
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.strip()
            if stripped.startswith("#") or "confidence" not in stripped.lower():
                continue
            if pattern.search(stripped):
                sites.append((rel, lineno, stripped))
    return sites


def test_core_decision_path_has_no_inline_thresholds():
    offenders = [
        f"{rel}:{n}: {text}"
        for rel, n, text in _inline_threshold_sites()
        if rel in CORE_DECISION_MODULES
    ]
    assert not offenders, (
        "the audit decision path must read thresholds from decision_policy:\n"
        + "\n".join(offenders)
    )


def test_no_new_inline_threshold_appears_anywhere():
    unexpected = sorted(
        {rel for rel, _, _ in _inline_threshold_sites()} - KNOWN_INLINE_THRESHOLDS
    )
    assert not unexpected, (
        "new inline confidence thresholds outside decision_policy: "
        + ", ".join(unexpected)
        + " -- declare them in decision_policy or add to KNOWN_INLINE_THRESHOLDS "
          "with a reason"
    )


def test_comparison_uses_the_declared_constants():
    assert comparison._STRONG_METHODS is dp.STRONG_METHODS
    assert comparison._WEAK_REVIEW_DEFECTS is dp.WEAK_REVIEW_DEFECTS


def test_audit_run_metadata_records_the_decision_policy(tmp_path):
    src = Path("/home/zhoujun/llmdata/datasets/svamp_platinum/svamp_platinum_all.jsonl")
    if not src.exists():
        pytest.skip("frozen dataset is not distributed with the repository")
    out = tmp_path / "audit.json"
    subprocess.run(
        [sys.executable, "-m", "benchcore.cli", "audit", str(src),
         "--limit", "3", "--out", str(out)],
        check=True, capture_output=True,
    )
    recorded = json.loads(out.read_text())["run_metadata"]["decision_policy"]
    assert recorded["sha256"] == dp.decision_policy_sha256(recorded["policy"])
