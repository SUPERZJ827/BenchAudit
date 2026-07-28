#!/usr/bin/env python3
"""Run the frozen P1 full-reference family review through OpenRouter."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import stat
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scripts.run_workspace_p0_openrouter_blind_review import (
    MODEL,
    ensure_private_dir,
    review_task,
    sha256,
    validate_task_annotations,
)
from scripts.validate_workspace_p0_annotations import (
    read_jsonl,
    validate_annotations,
)


DEFAULT_ROOT = Path(
    "/home/zhoujun/llmdata/after623/reports/"
    "workspace_p1_family_reference_20260728"
)
PROTOCOL_VERSION = "workspace-grounding-p1-family-reference-v1-20260728"


def family_system_prompt() -> str:
    return """You are independently reviewing benchmark rubric requirements.
You have no prior conversation and must use only this request's TASK, OUTPUT
CONTRACT, ALLOWED INPUT EVIDENCE, and RUBRIC text. You are not told how any
router or previous reviewer treated the case.

First judge whether the requirement itself is grounded. Do not judge whether an
unseen candidate output satisfies it.

Classes:
- hidden_exact_constraint/yes: a narrow literal, count, title, layout, color,
  filename, threshold, or rule absent from allowed sources.
- task_contract_conflict/yes: the requirement conflicts with task or output
  contract.
- task_or_input_derived/no: explicitly stated or uniquely derivable, without
  inventing filters, rounding rules, thresholds, or tie-breaks.
- intrinsic_validity/no: basic requested-artifact validity or openability.
- general_quality/no: ordinary clarity, correctness, professionalism, visual
  quality, or relevance.
- insufficient_evidence/uncertain: neither side is supportable without guessing.

Family responsibility:
- workspace_rubric_grounding: whether a rubric requirement is supported by the
  task/input.
- task_contract: inconsistency among task, output contract, required filenames,
  delivery form, or internal contract.
- artifact_execution: the requirement is legitimate but satisfaction requires
  opening or executing the delivered artifact.
- input_recomputation: legitimacy/checking requires recomputing data, tables, or
  constraints from inputs.
- subjective_quality_review: general quality/style judgments.
- unknown: evidence cannot support stable assignment.

primary_family is the main responsibility. acceptable_families may contain
other detectors that could legitimately find the same root cause; do not add
workspace_rubric_grounding merely to increase coverage.

Every evidence quote must be copied EXACTLY from task, output contract, or
allowed input evidence. For absence, quote the closest relevant source and use
relation=insufficient. Return only schema-compliant JSON."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    private_root = ensure_private_dir(args.private_root)
    raw_dir = ensure_private_dir(private_root / "gemini_3_1_pro_raw")
    package = args.package_dir.expanduser().resolve()
    tasks_path = package / "BLIND_TASKS.jsonl"
    candidates_path = package / "BLIND_CANDIDATES.jsonl"
    template_path = package / "ANNOTATION_TEMPLATE.jsonl"
    tasks = read_jsonl(tasks_path)
    candidates = read_jsonl(candidates_path)
    template = read_jsonl(template_path)
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_task[str(row["task_blind_id"])].append(row)
    task_by_id = {str(row["task_blind_id"]): row for row in tasks}
    if set(by_task) != set(task_by_id):
        raise ValueError("task and candidate coverage differs")

    results = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.workers,
    ) as executor:
        futures = {
            executor.submit(
                review_task,
                api_key=api_key,
                task_row=task_by_id[task_id],
                candidate_rows=rows,
                raw_dir=raw_dir,
                max_attempts=args.max_attempts,
                system_prompt=family_system_prompt(),
            ): task_id
            for task_id, rows in sorted(by_task.items())
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"completed {result['task_blind_id']} "
                f"attempts={result['attempts']} "
                f"latency={result['latency_seconds']}s",
                flush=True,
            )

    annotations = [
        row for result in results for row in result["annotations"]
    ]
    order = {
        str(row["blind_id"]): index for index, row in enumerate(template)
    }
    annotations.sort(key=lambda row: order[str(row["blind_id"])])
    summary = validate_annotations(template, annotations)
    for task_id, rows in by_task.items():
        ids = {row["blind_id"] for row in rows}
        validate_task_annotations(
            task_by_id[task_id],
            rows,
            [row for row in annotations if row["blind_id"] in ids],
        )

    annotation_path = (
        private_root / "GEMINI_3_1_PRO_FAMILY_ANNOTATIONS.jsonl"
    )
    annotation_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in annotations
        ),
        encoding="utf-8",
    )
    annotation_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    usage: Counter[str] = Counter()
    models = set()
    for result in results:
        models.add(result["observed_model"])
        for key, value in result["usage"].items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage[key] += value
    receipt = {
        "protocol_version": PROTOCOL_VERSION,
        "requested_model": MODEL,
        "observed_models": sorted(models),
        "fresh_context_per_task": True,
        "logical_task_requests": len(tasks),
        "api_requests_including_retries": sum(
            int(result["attempts"]) for result in results
        ),
        "candidates": len(annotations),
        "sealed_mapping_read": False,
        "prior_route_status_read": False,
        "blinding_compromised": False,
        "exact_evidence_quotes_validated": True,
        "annotation_sha256": sha256(annotation_path),
        "package_sha256": {
            path.name: sha256(path)
            for path in (tasks_path, candidates_path, template_path)
        },
        "usage": dict(sorted(usage.items())),
        "grounding_defect_counts": summary["grounding_defect_counts"],
        "grounding_class_counts": summary["grounding_class_counts"],
    }
    receipt_path = private_root / "GEMINI_3_1_PRO_FAMILY_RECEIPT.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
