#!/usr/bin/env python3
"""Recompute internal10 family recall with the independent P1 family reference.

This is a label-denominator correction only. It does not call an LLM, rerun the
router, alter the frozen A-double-prime working point, or rewrite raw outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.analyze_workspace_a_double_prime import (  # noqa: E402
    Key,
    _a_prime_candidates,
    _items_by_id,
    read_jsonl,
    sha256_file,
)
from scripts.analyze_workspace_a_prime import (  # noqa: E402
    _baseline_a_candidates,
    family_positive_keys,
)
from scripts.run_workspace_static_llm_ablation import (  # noqa: E402
    _read_completed_items,
)


PROTOCOL = "workspace-a-double-prime-internal10-p1-correction-v1-20260730"
SELECTED_RULE_IDS = ("R2c", "R2d")

FROZEN_REPO_INPUTS = {
    (
        "experiments/workspace_grounding/"
        "A_PRIME_INTERNAL_VALIDATION_10_20260729.json"
    ): "8af94ea6a23663654bec21e115928f6a7d5b30b86d1912e6992e9a5d24325515",
    (
        "experiments/workspace_grounding/"
        "A_DOUBLE_PRIME_INTERNAL10_ANALYSIS_20260729.json"
    ): "7a8d63a41990747bdafc91f31d712eb1c2dc72decf4a0638bd4ce2aac412aa18",
}

FROZEN_ARTIFACT_INPUTS = {
    (
        "reports/workspace_grounding_dual_triage_holdout30_20260728/"
        "grounding_dual_triage_items.jsonl"
    ): "2562ca10533e8f1a0a87080eed306fcf19389039ed7172ac7f04c1c197f9a50e",
    (
        "reports/workspace_grounding_a_double_prime_internal10_20260729/"
        "grounding_item_structured_triage_items.jsonl"
    ): "cab777f36735f38f182d7ace397e47fd276c1d2a729a6dfb38e5e88298837042",
    (
        "reports/workspace_grounding_a_double_prime_internal10_20260729/"
        "a_double_prime_observations.jsonl"
    ): "9e827aafaf835fafa780455c5bb89b1201778ba2086d17166e9b862803e00edb",
    (
        "reports/workspace_p0_blind_adjudication_20260728/"
        "SEALED_MAPPING.json"
    ): "18232ed0e0e65e9215dd51c857c34b560512d59be51d74b89b1c3efad4619ee9",
    (
        "reports/workspace_p0_blind_adjudication_20260728/"
        "GEMINI_3_1_PRO_INDEPENDENT_ANNOTATIONS.jsonl"
    ): "b091fae11b9ecbd2bffc826c4cf60615e15c39357b700abdf3c9510daa3b8e62",
    (
        "reports/workspace_p1_family_reference_20260728/"
        "SEALED_MAPPING.json"
    ): "3b24d271400355409ce9d5a61c808ebb8f5e9992d7e18ef572a5d54c90fabd6e",
    (
        "reports/workspace_p1_family_reference_20260728/"
        "GEMINI_3_1_PRO_FAMILY_ANNOTATIONS.jsonl"
    ): "cf88ac639d74d7b1bd98d350199b7de3335d8639086107b58aa9cd762c74e1c7",
}


def _key_rows(values: Iterable[Key]) -> list[dict[str, Any]]:
    return [
        {"item_id": item_id, "rubric_index": rubric_index}
        for item_id, rubric_index in sorted(values)
    ]


def summarize_family_reference(
    *,
    positives: set[Key],
    old_a_candidates: set[Key],
    a_prime_candidates: set[Key],
    a_double_prime_candidates: set[Key],
) -> dict[str, Any]:
    predictions = {
        "old_a": old_a_candidates,
        "a_prime": a_prime_candidates,
        "a_double_prime": a_double_prime_candidates,
    }
    denominator = len(positives)
    return {
        "positives": denominator,
        "positive_keys": _key_rows(positives),
        "methods": {
            name: {
                "hits": len(values & positives),
                "recall": (
                    len(values & positives) / denominator
                    if denominator else 0.0
                ),
                "hit_keys": _key_rows(values & positives),
            }
            for name, values in predictions.items()
        },
    }


def _rule_candidates(rows: Iterable[dict[str, Any]]) -> set[Key]:
    result: set[Key] = set()
    for row in rows:
        rule_ids = row.get("rule_ids")
        item_id = row.get("item_id")
        rubric_index = row.get("rubric_index")
        if (
            isinstance(rule_ids, list)
            and any(rule_id in rule_ids for rule_id in SELECTED_RULE_IDS)
            and isinstance(item_id, str)
            and isinstance(rubric_index, int)
        ):
            result.add((item_id, rubric_index))
    return result


def _verify_inputs(artifact_root: Path) -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in FROZEN_REPO_INPUTS.items():
        path = REPO / relative
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"frozen repo input mismatch: {relative}: {actual}")
        observed[f"repo:{relative}"] = actual
    for relative, expected in FROZEN_ARTIFACT_INPUTS.items():
        path = artifact_root / relative
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                f"frozen artifact input mismatch: {relative}: {actual}"
            )
        observed[f"artifact:{relative}"] = actual
    return dict(sorted(observed.items()))


def recompute(artifact_root: Path) -> dict[str, Any]:
    frozen_hashes = _verify_inputs(artifact_root)
    manifest = json.loads((
        REPO
        / "experiments/workspace_grounding/"
        "A_PRIME_INTERNAL_VALIDATION_10_20260729.json"
    ).read_text(encoding="utf-8"))
    expected_items = {str(value) for value in manifest["item_ids"]}

    baseline_all = _read_completed_items(
        artifact_root
        / "reports/workspace_grounding_dual_triage_holdout30_20260728/"
        "grounding_dual_triage_items.jsonl"
    )
    old_a_candidates = _baseline_a_candidates({
        item_id: baseline_all[item_id] for item_id in expected_items
    })

    item_rows = read_jsonl(
        artifact_root
        / "reports/workspace_grounding_a_double_prime_internal10_20260729/"
        "grounding_item_structured_triage_items.jsonl"
    )
    items = _items_by_id(item_rows, expected_items)
    a_prime_candidates, rubric_count, operational_unknown = (
        _a_prime_candidates(items)
    )
    if operational_unknown:
        raise ValueError(
            f"unexpected A-prime operational unknown: {operational_unknown}"
        )
    residue_candidates = _rule_candidates(read_jsonl(
        artifact_root
        / "reports/workspace_grounding_a_double_prime_internal10_20260729/"
        "a_double_prime_observations.jsonl"
    ))
    a_double_prime_candidates = a_prime_candidates | residue_candidates

    p0_all = family_positive_keys(
        artifact_root
        / "reports/workspace_p0_blind_adjudication_20260728/"
        "SEALED_MAPPING.json",
        artifact_root
        / "reports/workspace_p0_blind_adjudication_20260728/"
        "GEMINI_3_1_PRO_INDEPENDENT_ANNOTATIONS.jsonl",
    )
    p1_all = family_positive_keys(
        artifact_root
        / "reports/workspace_p1_family_reference_20260728/"
        "SEALED_MAPPING.json",
        artifact_root
        / "reports/workspace_p1_family_reference_20260728/"
        "GEMINI_3_1_PRO_FAMILY_ANNOTATIONS.jsonl",
    )
    p0 = {key for key in p0_all if key[0] in expected_items}
    p1 = {key for key in p1_all if key[0] in expected_items}

    p0_summary = summarize_family_reference(
        positives=p0,
        old_a_candidates=old_a_candidates,
        a_prime_candidates=a_prime_candidates,
        a_double_prime_candidates=a_double_prime_candidates,
    )
    p1_summary = summarize_family_reference(
        positives=p1,
        old_a_candidates=old_a_candidates,
        a_prime_candidates=a_prime_candidates,
        a_double_prime_candidates=a_double_prime_candidates,
    )
    original = json.loads((
        REPO
        / "experiments/workspace_grounding/"
        "A_DOUBLE_PRIME_INTERNAL10_ANALYSIS_20260729.json"
    ).read_text(encoding="utf-8"))
    non_recall_gates = {
        key: value
        for key, value in original["gate"].items()
        if key != "family_hits_at_least_6_of_7"
    }
    if not all(non_recall_gates.values()):
        raise ValueError("original non-recall gates were not all satisfied")

    result: dict[str, Any] = {
        "protocol": PROTOCOL,
        "correction_scope": "label denominator only; no API or rerun",
        "tasks": len(expected_items),
        "rubrics": rubric_count,
        "selected_rule_ids": list(SELECTED_RULE_IDS),
        "candidate_counts": {
            "old_a": len(old_a_candidates),
            "a_prime": len(a_prime_candidates),
            "a_double_prime": len(a_double_prime_candidates),
            "residue_union": len(residue_candidates),
        },
        "p0_original_reference": p0_summary,
        "p1_corrected_reference": p1_summary,
        "reference_overlap": {
            "intersection": len(p0 & p1),
            "p0_only": len(p0 - p1),
            "p1_only": len(p1 - p0),
        },
        "gate": {
            **non_recall_gates,
            "family_hits_at_least_6_of_7": (
                len(p1) == 7
                and p1_summary["methods"]["a_double_prime"]["hits"] >= 6
            ),
        },
        "decision": "FAIL",
        "interpretation": (
            "The P0 package conditioned the family denominator on cases selected "
            "for review and made old-A recall look artificially zero. The "
            "pre-existing P1 family reference yields old A 6/7, A-prime 4/7, "
            "and A-double-prime 4/7. The original FAIL is unchanged."
        ),
        "frozen_input_sha256": frozen_hashes,
        "llm_api_calls": 0,
        "raw_outputs_modified": False,
    }
    if all(result["gate"].values()):
        raise ValueError("corrected gate unexpectedly passes")
    stable = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    result["stable_summary_sha256"] = hashlib.sha256(stable).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = recompute(args.artifact_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
