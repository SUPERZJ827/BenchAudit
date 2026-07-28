#!/usr/bin/env python3
"""Paired WorkspaceBench rules-only vs DeepSeek-assisted static audit.

The experiment never executes a benchmark task.  It compares deterministic
artifact checks with the same checks augmented by two review-only semantic
front ends:

* task text -> explicit output filenames -> local inventory replay;
* task/contract/input evidence -> per-rubric grounding decision.

The existing evidence-first annotations are not human gold.  The report
therefore separates an objective output-filename reference from conditional
metrics on the previously reviewed rubric subset.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchcore.artifact_consistency import static_output_contract_issues
from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.loader import build_items, load_mapping, load_rows
from benchcore.schema import BenchmarkItem, Violation
from benchcore.task_contract import LLMTaskContractAuditor
from benchcore.workspace_grounding import (
    WorkspaceRubricGroundingAuditor,
    WorkspaceRubricGroundingChecker,
    build_workspace_evidence_bundle,
    resolve_objective_grounding_certificate,
    workspace_rubrics,
)
from benchcore.workspace_invariants import collect_workspace_invariant_issues


POSITIVE_REVIEW_LABEL = "较可信真问题"
NEGATIVE_REVIEW_LABEL = "较可信非问题"
UNCERTAIN_REVIEW_LABEL = "证据不足/分歧"
OUTPUT_REFERENCE_FAMILY = "task_vs_contract_filename"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--reviewed-reference", type=Path, required=True)
    parser.add_argument("--objective-reference", type=Path, required=True)
    parser.add_argument("--llm-config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--artifact-view-dir",
        type=Path,
        help=(
            "Optional private directory in which declared input symlinks are "
            "materialized as regular files before rubric grounding. "
            "Use a directory on the same filesystem as the source cache to "
            "permit zero-copy hard links."
        ),
    )
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument(
        "--stages",
        default="rules,taskcontract,grounding,score",
        help="Comma-separated subset of rules,taskcontract,grounding,score",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Debug-only prefix limit. Omit for the registered full388 experiment.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_label(text: str) -> str:
    return re.sub(r"[*`]", "", text).strip()


def parse_reviewed_reference(path: Path) -> dict[tuple[str, int], str]:
    """Parse only explicit rubric-level positive/negative/uncertain judgements."""

    labels: dict[tuple[str, int], str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `workspacebench-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 9:
            continue
        item_id = cells[0].strip("`")
        try:
            rubric_index = int(cells[1])
        except ValueError:
            continue
        label = normalize_label(cells[2])
        if label in {
            POSITIVE_REVIEW_LABEL,
            NEGATIVE_REVIEW_LABEL,
            UNCERTAIN_REVIEW_LABEL,
        }:
            key = (item_id, rubric_index)
            if key in labels and labels[key] != label:
                raise ValueError(f"conflicting reviewed label for {key}")
            labels[key] = label
    counts = Counter(labels.values())
    if not counts[POSITIVE_REVIEW_LABEL] or not counts[NEGATIVE_REVIEW_LABEL]:
        raise ValueError("reviewed reference has no usable positive/negative rows")
    return labels


def parse_objective_output_reference(path: Path) -> set[str]:
    """Read the all-library deterministic task-vs-contract filename scan."""

    positives: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `workspacebench-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        family = cells[2].strip("`")
        if family == OUTPUT_REFERENCE_FAMILY:
            positives.add(cells[0].strip("`"))
    if not positives:
        raise ValueError("objective reference has no task_vs_contract_filename rows")
    return positives


def input_roots(rows: list[dict[str, Any]]) -> list[Path]:
    roots = {
        Path(str(value)).expanduser().resolve(strict=False).parent
        for row in rows
        for value in (row.get("input_files") or [])
    }
    return sorted(roots, key=str)


def materialize_input_view(
    rows: list[dict[str, Any]],
    destination: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a task-scoped regular-file view of declared Workspace inputs.

    Hugging Face snapshots commonly expose immutable blobs through symlinks.
    BenchAudit's evidence identity layer correctly rejects those links to avoid
    containment/open races.  The experiment therefore resolves each declared
    source once, verifies that it is a regular file, and creates a task-scoped
    regular-file view.  A hard link is preferred; a byte copy is used only
    across filesystems.  The original dataset rows remain untouched.

    This is input staging, not a relaxation of the reader: the grounding
    auditor still receives only non-symlink paths and applies its normal
    bounded hashing, parsing, citation, and review-only gates.
    """

    destination = destination.expanduser().resolve(strict=False)
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("artifact view root must be a real directory")

    staged_rows: list[dict[str, Any]] = []
    hardlinked = 0
    copied = 0
    total_bytes = 0
    source_symlinks = 0
    for row_index, row in enumerate(rows):
        cloned = dict(row)
        values = row.get("input_files") or []
        if not isinstance(values, list):
            staged_rows.append(cloned)
            continue
        item_id = str(row.get("item_id") or row.get("id") or row_index)
        safe_item_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", item_id).strip("._")
        if not safe_item_id:
            raise ValueError(f"unsafe empty item id at row {row_index}")
        item_dir = destination / safe_item_id
        item_dir.mkdir(parents=True, exist_ok=True)
        if item_dir.is_symlink() or not item_dir.is_dir():
            raise ValueError(f"artifact item view is not a real directory: {item_dir}")

        staged: list[str] = []
        seen_names: dict[str, Path] = {}
        for value in values:
            declared = Path(str(value)).expanduser()
            try:
                declared_meta = declared.lstat()
                resolved = declared.resolve(strict=True)
                resolved_meta = resolved.stat()
            except OSError as exc:
                raise ValueError(
                    f"cannot materialize declared input {declared}: {exc}"
                ) from exc
            if stat.S_ISLNK(declared_meta.st_mode):
                source_symlinks += 1
            if not stat.S_ISREG(resolved_meta.st_mode):
                raise ValueError(f"declared input is not a regular file: {declared}")
            if not declared.name or declared.name in {".", ".."}:
                raise ValueError(f"declared input has no safe basename: {declared}")
            previous = seen_names.get(declared.name)
            if previous is not None and previous != resolved:
                raise ValueError(
                    f"two distinct inputs share staged basename {declared.name!r} "
                    f"for {item_id}"
                )
            seen_names[declared.name] = resolved

            target = item_dir / declared.name
            if target.exists() or target.is_symlink():
                target_meta = target.lstat()
                if not stat.S_ISREG(target_meta.st_mode):
                    raise ValueError(f"refusing to replace non-regular staged path {target}")
                target.unlink()
            try:
                os.link(resolved, target, follow_symlinks=False)
                hardlinked += 1
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                shutil.copyfile(resolved, target, follow_symlinks=False)
                copied += 1
            target_meta = target.lstat()
            if stat.S_ISLNK(target_meta.st_mode) or not stat.S_ISREG(target_meta.st_mode):
                raise ValueError(f"materialized input is not a regular file: {target}")
            total_bytes += int(target_meta.st_size)
            staged.append(str(target))
        cloned["input_files"] = staged
        staged_rows.append(cloned)

    receipt = {
        "schema_version": "workspace-artifact-view-v1",
        "root": str(destination),
        "rows": len(staged_rows),
        "files": hardlinked + copied,
        "source_symlinks": source_symlinks,
        "hardlinked": hardlinked,
        "copied": copied,
        "total_bytes": total_bytes,
        "source_values_changed": False,
    }
    return staged_rows, receipt


def violation_dict(value: Violation) -> dict[str, Any]:
    return asdict(value)


def run_rules(
    items: list[BenchmarkItem],
    allowed_roots: list[Path],
) -> dict[str, Any]:
    output_rows: list[dict[str, Any]] = []
    invariant_rows: list[dict[str, Any]] = []
    for item in items:
        for issue in static_output_contract_issues(item):
            output_rows.append({"item_id": item.item_id, **issue})
        for issue in collect_workspace_invariant_issues(
            item,
            allowed_roots=allowed_roots,
            include_solution_leak_scan=False,
        ):
            invariant_rows.append({
                "item_id": item.item_id,
                "defect_type": issue.defect_type,
                "message": issue.message,
                "evidence": issue.evidence,
                "severity": issue.severity,
                "review_only": issue.review_only,
            })
        # The assisted auditor applies this deterministic resolver before
        # emitting its final rubric decision.  Run the identical resolver in
        # the rules arm so its contribution is not misattributed to DeepSeek.
        bundle = build_workspace_evidence_bundle(
            item,
            allowed_roots=allowed_roots,
        )
        for rubric_index, rubric in enumerate(workspace_rubrics(item)):
            certificate = resolve_objective_grounding_certificate(
                item,
                bundle,
                rubric,
            )
            if (
                certificate.get("eligible")
                and certificate.get("label") == "unsupported"
            ):
                invariant_rows.append({
                    "item_id": item.item_id,
                    "defect_type": "task_rubric_mismatch",
                    "message": str(certificate.get("reason") or ""),
                    "evidence": {
                        "rubric_index": rubric_index,
                        "rubric": rubric,
                        "evidence_level": (
                            "objective_structured_grounding_certificate"
                        ),
                        "objective_certificate": certificate,
                    },
                    "severity": "review",
                    "review_only": True,
                    "source": "deterministic_objective_grounding_resolver",
                })
    return {
        "schema_version": "workspace-static-rules-v1",
        "output_filename_findings": output_rows,
        "workspace_invariant_findings": invariant_rows,
    }


def _read_completed_items(path: Path) -> dict[str, dict[str, Any]]:
    completed: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return completed
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        item_id = str(row.get("item_id") or "")
        if not item_id:
            raise ValueError(f"{path}:{line_number} has no item_id")
        if item_id in completed:
            raise ValueError(f"{path} contains duplicate item_id {item_id}")
        completed[item_id] = row
    return completed


def _append_jsonl(path: Path, row: dict[str, Any], lock: threading.Lock) -> None:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
    with lock:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(payload + "\n")
            stream.flush()


def _assert_review_only(findings: Iterable[Violation]) -> None:
    for finding in findings:
        allowed_tier = (
            finding.evidence_tier in {"unknown", "review"}
            if finding.defect_scope == "operational"
            else finding.evidence_tier == "review"
        )
        if (
            not finding.review_only
            or not allowed_tier
            or finding.evidence_tier == "confirmed"
        ):
            raise AssertionError(
                "LLM-derived finding escaped review-only ceiling: "
                f"{finding.item_id}/{finding.defect_type}/"
                f"{finding.evidence_tier}/{finding.review_only}"
            )


def run_task_contract(
    items: list[BenchmarkItem],
    config_path: Path,
    cache_path: Path,
    rows_path: Path,
    workers: int,
) -> dict[str, Any]:
    config = load_llm_config(str(config_path))
    config.cache_path = str(cache_path)
    client = LLMClient(config)
    completed = _read_completed_items(rows_path)
    pending = [item for item in items if item.item_id not in completed]
    lock = threading.Lock()
    started = time.monotonic()

    def one(item: BenchmarkItem) -> dict[str, Any]:
        checker = LLMTaskContractAuditor(client)
        findings = list(checker.check(item))
        _assert_review_only(findings)
        observation = (
            item.metadata.get("_llm_observations", {}).get(checker.name, {})
        )
        return {
            "item_id": item.item_id,
            "observation": observation,
            "findings": [violation_dict(row) for row in findings],
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, item): item.item_id for item in pending}
        for completed_count, future in enumerate(as_completed(futures), 1):
            row = future.result()
            _append_jsonl(rows_path, row, lock)
            completed[row["item_id"]] = row
            if completed_count % 20 == 0 or completed_count == len(pending):
                print(
                    f"taskcontract {len(completed)}/{len(items)} items",
                    flush=True,
                )
    return {
        "wall_seconds": time.monotonic() - started,
        "resumed_items": len(items) - len(pending),
        "new_items": len(pending),
        "llm": client.run_stats(),
    }


def run_grounding(
    items: list[BenchmarkItem],
    allowed_roots: list[Path],
    config_path: Path,
    cache_path: Path,
    rows_path: Path,
    workers: int,
) -> dict[str, Any]:
    config = load_llm_config(str(config_path))
    config.cache_path = str(cache_path)
    client = LLMClient(config)
    auditor = WorkspaceRubricGroundingAuditor(
        client,
        verifier_client=client,
        verify_unsupported=True,
        allowed_roots=allowed_roots,
    )
    completed = _read_completed_items(rows_path)
    pending = [item for item in items if item.item_id not in completed]
    lock = threading.Lock()
    started = time.monotonic()

    def one(item: BenchmarkItem) -> dict[str, Any]:
        # A per-call wrapper keeps last_decisions local while sharing only the
        # thread-safe client and immutable auditor configuration.
        checker = WorkspaceRubricGroundingChecker(auditor)
        findings = list(checker.check(item))
        _assert_review_only(findings)
        return {
            "item_id": item.item_id,
            "decisions": [row.to_dict() for row in checker.last_decisions],
            "findings": [violation_dict(row) for row in findings],
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, item): item.item_id for item in pending}
        for completed_count, future in enumerate(as_completed(futures), 1):
            row = future.result()
            _append_jsonl(rows_path, row, lock)
            completed[row["item_id"]] = row
            if completed_count % 10 == 0 or completed_count == len(pending):
                rubric_count = sum(
                    len(value.get("decisions", [])) for value in completed.values()
                )
                print(
                    f"grounding {len(completed)}/{len(items)} items; "
                    f"{rubric_count} rubric decisions",
                    flush=True,
                )
    return {
        "wall_seconds": time.monotonic() - started,
        "resumed_items": len(items) - len(pending),
        "new_items": len(pending),
        "llm": client.run_stats(),
    }


def binary_metrics(
    predictions: set[Any],
    positives: set[Any],
    universe: set[Any],
) -> dict[str, Any]:
    if not positives <= universe:
        raise ValueError("positive set must be contained in metric universe")
    predictions = predictions & universe
    negatives = universe - positives
    tp = len(predictions & positives)
    fp = len(predictions & negatives)
    fn = len(positives - predictions)
    tn = len(negatives - predictions)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "predicted": len(predictions),
        "positives": len(positives),
        "universe": len(universe),
    }


def _all_findings(records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        finding
        for row in records.values()
        for finding in row.get("findings", [])
        if isinstance(finding, dict)
    ]


def score_experiment(
    *,
    items: list[BenchmarkItem],
    rules: dict[str, Any],
    task_rows: dict[str, dict[str, Any]],
    grounding_rows: dict[str, dict[str, Any]],
    reviewed_labels: dict[tuple[str, int], str],
    output_positive_items: set[str],
) -> dict[str, Any]:
    item_ids = {item.item_id for item in items}
    output_universe = set(item_ids)
    output_positive_items &= output_universe
    rules_output = {
        str(row["item_id"]) for row in rules["output_filename_findings"]
    }
    task_findings = _all_findings(task_rows)
    llm_output = {
        str(row["item_id"])
        for row in task_findings
        if row.get("defect_type") == "task_artifact_contract_mismatch"
    }
    assisted_output = rules_output | llm_output

    reviewed = {
        key: value for key, value in reviewed_labels.items()
        if key[0] in item_ids
    }
    reviewed_universe = {
        key for key, value in reviewed.items()
        if value in {POSITIVE_REVIEW_LABEL, NEGATIVE_REVIEW_LABEL}
    }
    reviewed_positives = {
        key for key, value in reviewed.items()
        if value == POSITIVE_REVIEW_LABEL
    }

    rules_rubric: set[tuple[str, int]] = set()
    for row in rules["workspace_invariant_findings"]:
        index = row.get("evidence", {}).get("rubric_index")
        if isinstance(index, int) and index >= 0:
            rules_rubric.add((str(row["item_id"]), index))

    grounding_findings = _all_findings(grounding_rows)
    llm_rubric = {
        (str(row["item_id"]), int(row["evidence"]["rubric_index"]))
        for row in grounding_findings
        if row.get("defect_type") == "task_rubric_mismatch"
        and isinstance(row.get("evidence", {}).get("rubric_index"), int)
    }
    assisted_rubric = rules_rubric | llm_rubric

    extracted_paths = 0
    output_mapped_paths = 0
    role_suppressed_paths = 0
    neither_inventory_paths = 0
    rejected_task_items = 0
    for row in task_rows.values():
        observation = row.get("observation", {})
        if observation.get("validation_status") != "validated":
            rejected_task_items += 1
            continue
        contract = observation.get("contract", {})
        replay = observation.get("inventory_replay", {})
        extracted = contract.get("expected_output_paths") or []
        extracted_paths += len(extracted)
        role_suppressed_paths += int(
            replay.get("suppressed_input_output_overlap_count") or 0
        )
        missing = int(replay.get("missing_output_count") or 0)
        neither_inventory_paths += missing
        output_mapped_paths += max(
            0,
            len(extracted)
            - int(replay.get("suppressed_input_output_overlap_count") or 0)
            - missing,
        )

    all_llm_findings = task_findings + grounding_findings
    escaped = [
        row for row in all_llm_findings
        if (
            not row.get("review_only")
            or row.get("evidence_tier") == "confirmed"
            or (
                row.get("defect_scope") != "operational"
                and row.get("evidence_tier") != "review"
            )
            or (
                row.get("defect_scope") == "operational"
                and row.get("evidence_tier") not in {"unknown", "review"}
            )
        )
    ]
    confirmed = [
        row for row in all_llm_findings
        if row.get("evidence_tier") == "confirmed"
    ]
    operational_failures = [
        row for row in all_llm_findings
        if row.get("defect_scope") == "operational"
    ]
    total_rubrics = sum(len(workspace_rubrics(item)) for item in items)

    return {
        "schema_version": "workspace-static-llm-ablation-summary-v1",
        "naming": {
            "project": "BenchAudit",
            "historical_runner_alias": "BenchCore",
            "alias_policy": (
                "BenchCore is retained only when quoting an old runner label; "
                "this experiment and current system are named BenchAudit."
            ),
        },
        "dataset": {
            "items": len(items),
            "rubrics": total_rubrics,
        },
        "reference": {
            "reviewed_rubrics": len(reviewed),
            "reviewed_positive": len(reviewed_positives),
            "reviewed_negative": sum(
                value == NEGATIVE_REVIEW_LABEL for value in reviewed.values()
            ),
            "reviewed_uncertain": sum(
                value == UNCERTAIN_REVIEW_LABEL for value in reviewed.values()
            ),
            "objective_output_positive_items": len(output_positive_items),
            "output_reference_has_exhaustive_negative_labels": False,
            "human_gold": False,
            "warning": (
                "The rubric reference is a prior two-stage LLM evidence review, "
                "not exhaustive human gold. Rubric P/R/F1 are conditional on "
                "the explicitly reviewed positive/negative subset. The output "
                "reference supplies known positives from a deterministic scan, "
                "not exhaustive human clean labels; output precision/F1 are "
                "strict reference-alignment metrics."
            ),
        },
        "output_filename": {
            "rules_only": binary_metrics(
                rules_output, output_positive_items, output_universe,
            ),
            "deepseek_assisted": binary_metrics(
                assisted_output, output_positive_items, output_universe,
            ),
            "rules_candidate_items": sorted(rules_output),
            "llm_candidate_items": sorted(llm_output),
            "assisted_candidate_items": sorted(assisted_output),
            "assisted_added_over_rules": sorted(assisted_output - rules_output),
            "assisted_lost_vs_rules": sorted(rules_output - assisted_output),
        },
        "rubric_grounding_reviewed_reference": {
            "rules_only": binary_metrics(
                rules_rubric, reviewed_positives, reviewed_universe,
            ),
            "deepseek_assisted": binary_metrics(
                assisted_rubric, reviewed_positives, reviewed_universe,
            ),
            "rules_total_candidates_all_rubrics": len(rules_rubric),
            "llm_total_candidates_all_rubrics": len(llm_rubric),
            "assisted_total_candidates_all_rubrics": len(assisted_rubric),
            "assisted_candidate_items_all_rubrics": len({
                item_id for item_id, _ in assisted_rubric
            }),
            "review_burden_all_rubrics": (
                len(assisted_rubric) / total_rubrics if total_rubrics else 0.0
            ),
            "assisted_added_over_rules": len(assisted_rubric - rules_rubric),
            "assisted_lost_vs_rules": len(rules_rubric - assisted_rubric),
            "unlabeled_assisted_candidates": len(
                assisted_rubric - set(reviewed)
            ),
        },
        "input_output_role_confusion": {
            "extracted_paths": extracted_paths,
            "mapped_to_output_inventory": output_mapped_paths,
            "suppressed_input_only_paths": role_suppressed_paths,
            "neither_inventory_mismatch_paths": neither_inventory_paths,
            "task_contract_validation_rejected_items": rejected_task_items,
        },
        "safety": {
            "llm_findings": len(all_llm_findings),
            "review_only_findings": len(all_llm_findings) - len(escaped),
            "escaped_review_ceiling": len(escaped),
            "confirmed_llm_findings": len(confirmed),
            "operational_failure_findings": len(operational_failures),
            "all_llm_findings_review_only": not escaped,
        },
        "sets": {
            "rules_rubric_predictions": sorted(
                [item, index] for item, index in rules_rubric
            ),
            "llm_rubric_predictions": sorted(
                [item, index] for item, index in llm_rubric
            ),
        },
    }


def _fmt_metric(value: float) -> str:
    return f"{value:.3f}"


def render_report(
    summary: dict[str, Any],
    provenance: dict[str, Any],
    runtime: dict[str, Any],
) -> str:
    output = summary["output_filename"]
    rubric = summary["rubric_grounding_reviewed_reference"]
    role = summary["input_output_role_confusion"]
    safety = summary["safety"]

    def metric_row(name: str, values: dict[str, Any]) -> str:
        return (
            f"| {name} | {values['tp']} | {values['fp']} | "
            f"{values['fn']} | {_fmt_metric(values['precision'])} | "
            f"{_fmt_metric(values['recall'])} | {_fmt_metric(values['f1'])} |"
        )

    return f"""# WorkspaceBench full388 静态 LLM 配对消融

> 项目：**BenchAudit**  
> 数据：388 items / {summary['dataset']['rubrics']:,} rubrics  
> 执行：不运行 benchmark task；仅做确定性静态检查与 DeepSeek 静态语义审计

## 结论

本实验比较的是同一批数据上的 **Rules-only** 与
**DeepSeek-assisted BenchAudit**。历史名称 `BenchCore` 不是另一个系统，
只是旧 runner 标签；本报告不使用它指代当前实现。

Rubric 指标只是在既有证据化复核子集上的条件指标，不是完整人工真值：
现有文件明确记录为双阶段 LLM 复核。未标注 rubric 不被当成 clean。

## 1. 输出文件名：全库确定性扫描参考

已知正类是全库确定性复核得到的
`task_vs_contract_filename`，共
{summary['reference']['objective_output_positive_items']} 个 item。下表为便于
配对而采用严格 reference convention：其余 full388 item 暂按未命中参考
处理。由于新的语义抽取可能发现旧扫描规则覆盖不到的文件名冲突，FP
在这里表示“未进入旧参考集”，**不等价于已经人工证伪**；因此主要看
已知正类召回和两臂差异，Precision/F1 只作 reference-alignment 指标。

| 系统 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
{metric_row('Rules-only', output['rules_only'])}
{metric_row('DeepSeek-assisted BenchAudit', output['deepseek_assisted'])}

- Rules-only 候选 item：{len(output['rules_candidate_items'])}
- LLM task-contract 候选 item：{len(output['llm_candidate_items'])}
- Assisted 相对 rules 新增：{len(output['assisted_added_over_rules'])}
- Assisted 相对 rules 丢失：{len(output['assisted_lost_vs_rules'])}

## 2. Rubric grounding：reviewed-reference 条件指标

计分子集包含
{summary['reference']['reviewed_positive']} 个“较可信真问题”和
{summary['reference']['reviewed_negative']} 个“较可信非问题”；
{summary['reference']['reviewed_uncertain']} 个分歧项不参与 P/R/F1。

| 系统 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
{metric_row('Rules-only', rubric['rules_only'])}
{metric_row('DeepSeek-assisted BenchAudit', rubric['deepseek_assisted'])}

全量候选与复核负担：

- Rules-only rubric candidates：{rubric['rules_total_candidates_all_rubrics']}
- DeepSeek-assisted rubric candidates：{rubric['assisted_total_candidates_all_rubrics']}
- 涉及 item：{rubric['assisted_candidate_items_all_rubrics']}
- review burden：{rubric['review_burden_all_rubrics']:.2%}
- Assisted 新增：{rubric['assisted_added_over_rules']}
- 尚无明确 reviewed label 的新增候选：
  {rubric['unlabeled_assisted_candidates']}（不计作 FP）

## 3. Input/output role confusion

| 指标 | 数量 |
|---|---:|
| LLM 抽取的显式路径 | {role['extracted_paths']} |
| 映射到 output inventory | {role['mapped_to_output_inventory']} |
| 仅命中 input inventory、被本地抑制 | {role['suppressed_input_only_paths']} |
| 两边均未命中、形成 mismatch 候选 | {role['neither_inventory_mismatch_paths']} |
| 模型响应未通过 schema/grounding 校验的 item | {role['task_contract_validation_rejected_items']} |

被 input inventory 命中的路径只记录为抽取角色混淆，不报告 benchmark
缺陷。

## 4. Review-only 安全门

| 指标 | 数量 |
|---|---:|
| LLM-derived findings | {safety['llm_findings']} |
| review-only findings | {safety['review_only_findings']} |
| 越过 review ceiling | {safety['escaped_review_ceiling']} |
| LLM-derived confirmed | {safety['confirmed_llm_findings']} |
| operational failures | {safety['operational_failure_findings']} |

验收要求是越权与 confirmed 均为 0。

## 5. API 与复现

```json
{json.dumps(runtime, ensure_ascii=False, indent=2, sort_keys=True)}
```

Provenance：

```json
{json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True)}
```

## 6. 解释边界

1. 输出文件名的 12 个参考正类来自全库确定性扫描，但其余 item 没有逐条
   人工 clean 标签；因此已知正类 Recall 可直接解读，Precision/F1 只能
   解读为对该窄参考集的 alignment，新增项需要复核。
2. Rubric grounding 的参考集由旧系统候选触发并由双阶段 LLM 复核，
   存在 selection bias；指标只回答“在已明确复核的候选上，哪一臂覆盖
   更多可信问题且少命中可信非问题”。
3. 全量新增候选没有被自动记成 FP，也不能自动宣称为 TP。
4. LLM 的作用是提高静态语义候选召回；confirmed 仍需要独立 replay、
   约束求解或真实执行。
"""


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
    ).strip()


def main() -> None:
    args = parse_args()
    stages = {value.strip() for value in args.stages.split(",") if value.strip()}
    unknown = stages - {"rules", "taskcontract", "grounding", "score"}
    if unknown:
        raise ValueError(f"unknown stages: {sorted(unknown)}")
    if args.workers < 1:
        raise ValueError("--workers must be positive")

    dataset = args.dataset.expanduser().resolve()
    reviewed_reference = args.reviewed_reference.expanduser().resolve()
    objective_reference = args.objective_reference.expanduser().resolve()
    config_path = args.llm_config.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(dataset)
    if args.limit is not None:
        rows = rows[: args.limit]
    artifact_view_receipt: dict[str, Any] | None = None
    if args.artifact_view_dir is not None:
        rows, artifact_view_receipt = materialize_input_view(
            rows,
            args.artifact_view_dir,
        )
    mapping = load_mapping(None, rows)
    items = build_items(rows, mapping)
    roots = input_roots(rows)
    reviewed_labels = parse_reviewed_reference(reviewed_reference)
    objective_output = parse_objective_output_reference(objective_reference)

    provenance = {
        "protocol": "workspace-static-llm-paired-v1-20260728",
        "git_head": git_head(),
        "dataset": str(dataset),
        "dataset_sha256": sha256_file(dataset),
        "reviewed_reference": str(reviewed_reference),
        "reviewed_reference_sha256": sha256_file(reviewed_reference),
        "objective_reference": str(objective_reference),
        "objective_reference_sha256": sha256_file(objective_reference),
        "items": len(items),
        "rubrics": sum(len(workspace_rubrics(item)) for item in items),
        "workers": args.workers,
        "full388": len(items) == 388 and args.limit is None,
        "artifact_view": artifact_view_receipt,
    }
    (out_dir / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    runtime_path = out_dir / "runtime.json"
    runtime = (
        json.loads(runtime_path.read_text(encoding="utf-8"))
        if runtime_path.exists()
        else {}
    )
    rules_path = out_dir / "rules_only.json"
    task_rows_path = out_dir / "task_contract_items.jsonl"
    grounding_rows_path = out_dir / "grounding_items.jsonl"

    if "rules" in stages:
        rules = run_rules(items, roots)
        rules["sha256"] = stable_json_sha256(rules)
        rules_path.write_text(
            json.dumps(rules, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"rules complete: {rules_path}", flush=True)

    if "taskcontract" in stages:
        runtime["taskcontract"] = run_task_contract(
            items,
            config_path,
            out_dir / "task_contract_cache.jsonl",
            task_rows_path,
            args.workers,
        )
        runtime_path.write_text(
            json.dumps(runtime, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    if "grounding" in stages:
        runtime["grounding"] = run_grounding(
            items,
            roots,
            config_path,
            out_dir / "grounding_cache.jsonl",
            grounding_rows_path,
            args.workers,
        )
        runtime_path.write_text(
            json.dumps(runtime, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    if "score" in stages:
        missing = [
            path for path in (rules_path, task_rows_path, grounding_rows_path)
            if not path.exists()
        ]
        if missing:
            raise FileNotFoundError(
                "score stage requires completed arm files: "
                + ", ".join(map(str, missing))
            )
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
        task_rows = _read_completed_items(task_rows_path)
        grounding_rows = _read_completed_items(grounding_rows_path)
        expected = {item.item_id for item in items}
        for name, values in (
            ("taskcontract", task_rows),
            ("grounding", grounding_rows),
        ):
            if set(values) != expected:
                raise ValueError(
                    f"{name} item coverage mismatch: "
                    f"{len(values)}/{len(expected)}"
                )
        summary = score_experiment(
            items=items,
            rules=rules,
            task_rows=task_rows,
            grounding_rows=grounding_rows,
            reviewed_labels=reviewed_labels,
            output_positive_items=objective_output,
        )
        summary["provenance_sha256"] = stable_json_sha256(provenance)
        summary["runtime"] = runtime
        summary_path = out_dir / "summary.json"
        report_path = out_dir / "report.md"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        report_path.write_text(
            render_report(summary, provenance, runtime),
            encoding="utf-8",
        )
        print(f"summary: {summary_path}", flush=True)
        print(f"report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
