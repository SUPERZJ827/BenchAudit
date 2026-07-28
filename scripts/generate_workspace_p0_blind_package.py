#!/usr/bin/env python3
"""Generate the frozen Workspace P0 blind adjudication package."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchcore.loader import build_items, load_mapping, load_rows  # noqa: E402
from benchcore.workspace_grounding import (  # noqa: E402
    build_workspace_evidence_bundle,
    workspace_rubrics,
)
from scripts.run_workspace_static_llm_ablation import (  # noqa: E402
    POSITIVE_REVIEW_LABEL,
    _read_completed_items,
    input_roots,
    materialize_input_view,
    parse_reviewed_reference,
)

PROTOCOL = "workspace-grounding-p0-adjudication-v1-20260728"
SEED = "workspace-grounding-p0-blind-v1-20260728"
VIEWS = {"hidden_constraint", "support_challenge"}
SUPPORT_ONLY = {"support_challenge"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dual-results", type=Path, required=True)
    parser.add_argument("--reviewed-reference", type=Path, required=True)
    parser.add_argument("--holdout-manifest", type=Path, required=True)
    parser.add_argument("--protocol-file", type=Path, required=True)
    parser.add_argument("--artifact-view-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sealed-mapping", type=Path, required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(kind: str, *parts: object) -> str:
    payload = ":".join((PROTOCOL, kind, *(str(value) for value in parts)))
    return f"{kind}-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


def selected_views(decision: dict[str, Any]) -> set[str]:
    scanner = decision.get("scanner")
    if not isinstance(scanner, dict):
        return set()
    values = scanner.get("triage_selected_views")
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values}


def candidate_rows(
    rows: dict[str, dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    result = {}
    for item_id, row in rows.items():
        for decision in row.get("decisions", []):
            if not isinstance(decision, dict):
                continue
            index = decision.get("rubric_index")
            if isinstance(index, int):
                result[(item_id, index)] = decision
    return result


def sample_task_distinct(
    pool: list[tuple[str, int]],
    *,
    count: int,
    rng: random.Random,
) -> list[tuple[str, int]]:
    shuffled = sorted(pool)
    rng.shuffle(shuffled)
    selected: list[tuple[str, int]] = []
    seen_tasks: set[str] = set()
    for key in shuffled:
        if key[0] in seen_tasks:
            continue
        selected.append(key)
        seen_tasks.add(key[0])
        if len(selected) == count:
            return selected
    for key in shuffled:
        if key in selected:
            continue
        selected.append(key)
        if len(selected) == count:
            return selected
    raise ValueError(f"candidate pool has only {len(selected)}/{count} rows")


def select_cases(
    decisions: dict[tuple[str, int], dict[str, Any]],
    reviewed: dict[tuple[str, int], str],
) -> tuple[list[tuple[str, int]], dict[tuple[str, int], str]]:
    b_only_unsupported = sorted(
        key for key, decision in decisions.items()
        if selected_views(decision) == SUPPORT_ONLY
        and str(decision.get("label") or "").casefold() == "unsupported"
    )
    missed_positive = sorted(
        key for key, label in reviewed.items()
        if label == POSITIVE_REVIEW_LABEL
        and key in decisions
        and not (
            selected_views(decisions[key]) & VIEWS
        )
    )
    if len(b_only_unsupported) != 13:
        raise ValueError(
            f"expected 13 B-only unsupported rows, got {len(b_only_unsupported)}"
        )
    if len(missed_positive) != 4:
        raise ValueError(
            f"expected 4 missed reviewed positives, got {len(missed_positive)}"
        )
    focus = set(b_only_unsupported) | set(missed_positive)
    focus_tasks = {item_id for item_id, _ in focus}
    pools: dict[str, list[tuple[str, int]]] = {"supported": [], "uncertain": []}
    for key, decision in decisions.items():
        label = str(decision.get("label") or "").casefold()
        if (
            key[0] not in focus_tasks
            and selected_views(decision) == SUPPORT_ONLY
            and label in pools
        ):
            pools[label].append(key)
    rng = random.Random(SEED)
    supported_controls = sample_task_distinct(
        pools["supported"], count=10, rng=rng,
    )
    uncertain_controls = sample_task_distinct(
        pools["uncertain"], count=10, rng=rng,
    )
    strata = {
        **{key: "focus_b_only_unsupported" for key in b_only_unsupported},
        **{key: "focus_missed_reviewed_positive" for key in missed_positive},
        **{key: "control_b_only_supported" for key in supported_controls},
        **{key: "control_b_only_uncertain" for key in uncertain_controls},
    }
    selected = sorted(strata, key=lambda key: stable_id("case", *key))
    if len(selected) != len(set(selected)) or len(selected) != 37:
        raise AssertionError("P0 package must contain 37 unique candidates")
    return selected, strata


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    inputs = {
        "dataset": args.dataset.expanduser().resolve(),
        "dual_results": args.dual_results.expanduser().resolve(),
        "reviewed_reference": args.reviewed_reference.expanduser().resolve(),
        "holdout_manifest": args.holdout_manifest.expanduser().resolve(),
        "protocol_file": args.protocol_file.expanduser().resolve(),
    }
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    sealed_mapping_path = args.sealed_mapping.expanduser().resolve()
    sealed_mapping_path.parent.mkdir(parents=True, exist_ok=True)

    dual_rows = _read_completed_items(inputs["dual_results"])
    holdout = json.loads(inputs["holdout_manifest"].read_text(encoding="utf-8"))
    expected_items = {str(value) for value in holdout["item_ids"]}
    if set(dual_rows) != expected_items:
        raise ValueError("dual-result coverage does not match frozen holdout")
    reviewed = {
        key: value
        for key, value in parse_reviewed_reference(
            inputs["reviewed_reference"],
        ).items()
        if key[0] in expected_items
    }
    decisions = candidate_rows(dual_rows)
    selected, strata = select_cases(decisions, reviewed)

    raw_rows = load_rows(inputs["dataset"])
    selected_tasks = {item_id for item_id, _ in selected}
    by_id = {
        str(row.get("item_id") or row.get("id") or index): row
        for index, row in enumerate(raw_rows)
        if str(row.get("item_id") or row.get("id") or index) in selected_tasks
    }
    if set(by_id) != selected_tasks:
        raise ValueError("dataset is missing one or more selected P0 tasks")
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
            item,
            root,
            allowed_roots=roots,
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

    candidate_package = []
    annotation_template = []
    sealed_rows = []
    for item_id, index in selected:
        item = items_by_id[item_id]
        rubrics = workspace_rubrics(item)
        if not 0 <= index < len(rubrics):
            raise ValueError(f"invalid rubric index for {item_id}: {index}")
        blind_id = stable_id("case", item_id, index)
        candidate_package.append({
            "blind_id": blind_id,
            "task_blind_id": stable_id("task", item_id),
            "rubric": rubrics[index],
        })
        annotation_template.append({
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
        decision = decisions[(item_id, index)]
        sealed_rows.append({
            "blind_id": blind_id,
            "item_id": item_id,
            "rubric_index": index,
            "source_stratum": strata[(item_id, index)],
            "prior_final_label": decision.get("label"),
            "prior_selected_views": sorted(selected_views(decision)),
            "prior_reviewed_label": reviewed.get((item_id, index)),
        })

    tasks_path = out_dir / "BLIND_TASKS.jsonl"
    candidates_path = out_dir / "BLIND_CANDIDATES.jsonl"
    template_path = out_dir / "ANNOTATION_TEMPLATE.jsonl"
    write_jsonl(tasks_path, task_rows)
    write_jsonl(candidates_path, candidate_package)
    write_jsonl(template_path, annotation_template)
    sealed_mapping_path.write_text(
        json.dumps(
            {
                "protocol": PROTOCOL,
                "rows": sealed_rows,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    sealed_mapping_path.chmod(0o600)

    receipt = {
        "protocol": PROTOCOL,
        "selection_seed": SEED,
        "counts": {
            "cases": len(candidate_package),
            "tasks": len(task_rows),
            "focus_b_only_unsupported": sum(
                value == "focus_b_only_unsupported" for value in strata.values()
            ),
            "focus_missed_reviewed_positive": sum(
                value == "focus_missed_reviewed_positive"
                for value in strata.values()
            ),
            "control_b_only_supported": sum(
                value == "control_b_only_supported" for value in strata.values()
            ),
            "control_b_only_uncertain": sum(
                value == "control_b_only_uncertain" for value in strata.values()
            ),
        },
        "input_sha256": {
            name: sha256_file(path) for name, path in inputs.items()
        },
        "package_sha256": {
            tasks_path.name: sha256_file(tasks_path),
            candidates_path.name: sha256_file(candidates_path),
            template_path.name: sha256_file(template_path),
        },
        "sealed_mapping_sha256": sha256_file(sealed_mapping_path),
        "artifact_view": {
            key: artifact_receipt[key]
            for key in (
                "files", "rows", "source_symlinks", "total_bytes",
                "source_values_changed",
            )
        },
        "blinding": {
            "candidate_package_contains_source_stratum": False,
            "candidate_package_contains_prior_verdict": False,
            "candidate_package_contains_item_id": False,
            "candidate_package_contains_reviewed_label": False,
            "sealed_mapping_committed": False,
        },
    }
    receipt_path = out_dir / "SELECTION_RECEIPT.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
