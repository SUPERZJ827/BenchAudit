#!/usr/bin/env python3
"""Generate the frozen P1 family-reference blind package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchcore.loader import build_items, load_mapping, load_rows
from benchcore.workspace_grounding import (
    build_workspace_evidence_bundle,
    workspace_rubrics,
)
from scripts.analyze_workspace_grounding_dual_holdout import decision_sets
from scripts.generate_workspace_p0_blind_package import (
    ensure_private_output_dir,
    sha256_file,
    write_jsonl,
)
from scripts.run_workspace_static_llm_ablation import (
    POSITIVE_REVIEW_LABEL,
    _read_completed_items,
    input_roots,
    materialize_input_view,
    parse_reviewed_reference,
)


PROTOCOL = "workspace-grounding-p1-family-reference-v1-20260728"


def stable_id(kind: str, *parts: object) -> str:
    # Deliberately use a P1-specific namespace; no P0 blind id is reused.
    payload = ":".join((PROTOCOL, kind, *(str(value) for value in parts)))
    import hashlib
    return f"{kind}-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dual-results", type=Path, required=True)
    parser.add_argument("--reviewed-reference", type=Path, required=True)
    parser.add_argument("--holdout-manifest", type=Path, required=True)
    parser.add_argument("--protocol-file", type=Path, required=True)
    parser.add_argument("--artifact-view-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--sealed-mapping", type=Path, required=True)
    return parser.parse_args()


def _decision_by_key(
    rows: dict[str, dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    result = {}
    for item_id, row in rows.items():
        for decision in row.get("decisions", []):
            if isinstance(decision, dict) and isinstance(
                decision.get("rubric_index"), int,
            ):
                result[(item_id, decision["rubric_index"])] = decision
    return result


def select_reference_positives(
    reviewed: dict[tuple[str, int], str],
    *,
    expected_items: set[str],
) -> list[tuple[str, int]]:
    selected = sorted(
        key for key, value in reviewed.items()
        if key[0] in expected_items and value == POSITIVE_REVIEW_LABEL
    )
    if len(selected) != 30:
        raise ValueError(f"expected 30 reviewed positives, got {len(selected)}")
    return selected


def main() -> None:
    args = parse_args()
    inputs = {
        "dataset": args.dataset.expanduser().resolve(),
        "dual_results": args.dual_results.expanduser().resolve(),
        "reviewed_reference": args.reviewed_reference.expanduser().resolve(),
        "holdout_manifest": args.holdout_manifest.expanduser().resolve(),
        "protocol_file": args.protocol_file.expanduser().resolve(),
    }
    out_dir = ensure_private_output_dir(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.chmod(0o700)
    receipt_path = args.receipt_out.expanduser().resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path = args.sealed_mapping.expanduser().resolve()
    mapping_path.parent.mkdir(parents=True, exist_ok=True)

    holdout = json.loads(inputs["holdout_manifest"].read_text(encoding="utf-8"))
    expected_items = {str(value) for value in holdout["item_ids"]}
    dual_rows = _read_completed_items(inputs["dual_results"])
    if set(dual_rows) != expected_items:
        raise ValueError("dual-result coverage does not match frozen holdout")
    reviewed = parse_reviewed_reference(inputs["reviewed_reference"])
    selected = select_reference_positives(
        reviewed, expected_items=expected_items,
    )
    selected_tasks = {item_id for item_id, _ in selected}

    raw_rows = load_rows(inputs["dataset"])
    by_id = {
        str(row.get("item_id") or row.get("id") or index): row
        for index, row in enumerate(raw_rows)
        if str(row.get("item_id") or row.get("id") or index) in selected_tasks
    }
    if set(by_id) != selected_tasks:
        raise ValueError("dataset is missing selected P1 tasks")
    staged_rows, artifact_receipt = materialize_input_view(
        [by_id[item_id] for item_id in sorted(by_id)],
        args.artifact_view_dir,
    )
    mapping = load_mapping(None, staged_rows)
    items = build_items(staged_rows, mapping)
    roots = input_roots(staged_rows)
    root = roots[0] if len(roots) == 1 else None
    items_by_id = {item.item_id: item for item in items}

    task_rows = []
    for item_id in sorted(selected_tasks, key=lambda value: stable_id("task", value)):
        item = items_by_id[item_id]
        bundle = build_workspace_evidence_bundle(
            item, root, allowed_roots=roots,
        )
        task_rows.append({
            "task_blind_id": stable_id("task", item_id),
            "task": item.task,
            "output_contract": item.output_contract,
            "allowed_input_evidence": bundle.text,
            "evidence_status": {
                "actor_view_complete": bundle.actor_view_complete,
                "bundle_truncated": bundle.bundle_truncated,
                "indexed_files": bundle.indexed_files,
                "partial_files": bundle.partial_files,
                "parse_failures": bundle.parse_failures,
            },
        })

    route_sets = decision_sets(dual_rows)
    decisions = _decision_by_key(dual_rows)
    candidates = []
    template = []
    sealed = []
    for item_id, rubric_index in sorted(
        selected, key=lambda key: stable_id("case", *key),
    ):
        item = items_by_id[item_id]
        rubrics = workspace_rubrics(item)
        blind_id = stable_id("case", item_id, rubric_index)
        candidates.append({
            "blind_id": blind_id,
            "task_blind_id": stable_id("task", item_id),
            "rubric": rubrics[rubric_index],
        })
        template.append({
            "blind_id": blind_id,
            "acceptable_families": [],
            "confidence": None,
            "evaluation_objectivity": "",
            "evidence": [],
            "grounding_class": "",
            "is_grounding_defect": "",
            "primary_family": "",
            "root_cause_summary": "",
            "satisfaction_checkability": "",
        })
        key = (item_id, rubric_index)
        sealed.append({
            "blind_id": blind_id,
            "item_id": item_id,
            "rubric_index": rubric_index,
            "reviewed_label": reviewed[key],
            "routed_hidden_constraint": key in route_sets[
                "routed_hidden_constraint"
            ],
            "routed_support_challenge": key in route_sets[
                "routed_support_challenge"
            ],
            "routed_union": key in route_sets["routed_union"],
            "final_label": decisions[key].get("label"),
        })

    tasks_path = out_dir / "BLIND_TASKS.jsonl"
    candidates_path = out_dir / "BLIND_CANDIDATES.jsonl"
    template_path = out_dir / "ANNOTATION_TEMPLATE.jsonl"
    write_jsonl(tasks_path, task_rows)
    write_jsonl(candidates_path, candidates)
    write_jsonl(template_path, template)
    for path in (tasks_path, candidates_path, template_path):
        path.chmod(0o600)
    mapping_path.write_text(
        json.dumps(
            {"protocol": PROTOCOL, "rows": sealed},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    mapping_path.chmod(0o600)

    receipt = {
        "protocol": PROTOCOL,
        "counts": {
            "cases": len(candidates),
            "tasks": len(task_rows),
        },
        "input_sha256": {
            name: sha256_file(path) for name, path in inputs.items()
        },
        "package_sha256": {
            path.name: sha256_file(path)
            for path in (tasks_path, candidates_path, template_path)
        },
        "sealed_mapping_sha256": sha256_file(mapping_path),
        "artifact_view": {
            key: artifact_receipt[key]
            for key in (
                "files", "rows", "source_symlinks", "total_bytes",
                "source_values_changed",
            )
        },
        "blinding": {
            "contains_item_id": False,
            "contains_reviewed_label": False,
            "contains_route_status": False,
            "contains_verifier_label": False,
            "sealed_mapping_committed": False,
        },
    }
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
