#!/usr/bin/env python3
"""Evaluate rubric grounding on Workspace-Bench's official weak-reference audit.

The upstream CSV is explicitly a *preliminary grounding audit*, not human gold.
This script pins its commit and checksum, hides its labels/reasons from the model,
audits each rubric from task/contract/input evidence, and reports agreement with
confidence intervals. Results are resumable at rubric granularity.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import math
import random
import sys
import threading
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.loader import build_items, load_mapping, load_rows
from benchcore.schema import BenchmarkItem
from benchcore.workspace_grounding import (
    BATCH_GROUNDING_PROMPT,
    BATCH_VERIFIER_PROMPT,
    GROUNDING_PROMPT,
    GROUNDING_SYSTEM,
    VERIFIER_PROMPT,
    VERIFIER_SYSTEM,
    WorkspaceRubricGroundingAuditor,
    build_workspace_evidence_bundle,
)
from benchcore.workspace_invariants import (
    parse_jsonish,
    workspace_input_paths,
    workspace_outputs,
    workspace_rubric_types,
    workspace_rubrics,
)


UPSTREAM_COMMIT = "268643b92bb6d417064236ccc2b4999fdd63d240"
UPSTREAM_RELATIVE_PATH = (
    "evaluation/audits/workspace_bench_lite_cn_rubric_grounding_audit_v0.1.csv"
)
UPSTREAM_URL = (
    f"https://raw.githubusercontent.com/OpenDataBox/Workspace-Bench/{UPSTREAM_COMMIT}/"
    f"{UPSTREAM_RELATIVE_PATH}"
)
UPSTREAM_SHA256 = "190d907c1ff6d8283a715568d7b7a879588e37f57acd66be21a92ae1f2d97c5e"
LABEL_MAP = {"有依据": "supported", "无依据": "unsupported", "无法判断": "uncertain"}
LABELS = ("supported", "unsupported", "uncertain")
PROTOCOL_VERSION = "workspace-grounding-isolated-v3-20260714"
WORKSPACE_DATASET_REVISION = "60b08b1cc2e8054afbc3ca2160d37876b4f0765c"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", default="datasets/workspacebench/lite_cn_100_pinned.jsonl",
        help="Pinned Chinese Lite export containing matching materialized inputs",
    )
    parser.add_argument(
        "--labels",
        default="reports/workspace_grounding_20260714/upstream_grounding_audit.csv",
    )
    parser.add_argument("--llm-config", default="configs/llm_deepseek.json")
    parser.add_argument(
        "--llm-cache", default="reports/workspace_grounding_20260714/llm_cache.jsonl",
    )
    parser.add_argument(
        "--rows-out", default="reports/workspace_grounding_20260714/decisions.jsonl",
    )
    parser.add_argument(
        "--summary-out", default="reports/workspace_grounding_20260714/summary.json",
    )
    parser.add_argument(
        "--md", default="reports/workspace_grounding_20260714/summary.md",
    )
    parser.add_argument(
        "--baseline-report",
        help="Optional sparse-detector baseline; reported as non-comparable",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--batch-size", type=int, default=1,
        help="Primary claims require 1; values >1 are cross-rubric leakage ablations",
    )
    parser.add_argument("--allow-cross-rubric-batching", action="store_true")
    parser.add_argument("--operational-passes", type=int, default=2)
    parser.add_argument("--limit-tasks", type=int)
    parser.add_argument("--task-id", action="append", help="Only run selected absolute task id(s)")
    parser.add_argument("--no-verifier", action="store_true")
    parser.add_argument("--min-confidence", type=float, default=0.55)
    return parser.parse_args()


def ensure_labels(path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(UPSTREAM_URL, timeout=60) as response:
            payload = response.read()
        if hashlib.sha256(payload).hexdigest() != UPSTREAM_SHA256:
            raise RuntimeError("downloaded upstream audit checksum mismatch")
        path.write_bytes(payload)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != UPSTREAM_SHA256:
        raise RuntimeError(
            f"label file checksum mismatch: expected {UPSTREAM_SHA256}, got {actual}"
        )
    return path


def load_silver_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"task_id", "task", "output_files", "rubric_index", "rubric", "rubric_type", "basis_label"}
    missing = required - set(rows[0] if rows else {})
    if missing:
        raise ValueError(f"upstream audit missing columns: {sorted(missing)}")
    unknown = {row["basis_label"] for row in rows} - set(LABEL_MAP)
    if unknown:
        raise ValueError(f"unknown upstream labels: {sorted(unknown)}")
    if {row.get("language") for row in rows} != {"cn"}:
        raise ValueError("weak-reference audit is expected to contain only Chinese rows")
    return rows


def build_experiment_items(
    dataset_path: Path,
    labels: list[dict[str, str]],
) -> tuple[dict[str, BenchmarkItem], dict[tuple[str, int], dict[str, str]]]:
    source_rows = load_rows(dataset_path)
    mapping = load_mapping(None, source_rows)
    local_items = {str(item.metadata.get("absolute_id")): item for item in build_items(source_rows, mapping)}
    by_task: dict[str, list[dict[str, str]]] = defaultdict(list)
    truth: dict[tuple[str, int], dict[str, str]] = {}
    for row in labels:
        task_id = str(row["task_id"])
        index = int(row["rubric_index"])
        if (task_id, index) in truth:
            raise ValueError(f"duplicate weak-reference key {(task_id, index)}")
        by_task[task_id].append(row)
        truth[(task_id, index)] = row

    items: dict[str, BenchmarkItem] = {}
    mismatches: list[str] = []
    for task_id, rows in by_task.items():
        if task_id not in local_items:
            raise ValueError(f"task {task_id} is absent from local dataset")
        ordered = sorted(rows, key=lambda row: int(row["rubric_index"]))
        indices = [int(row["rubric_index"]) for row in ordered]
        if indices != list(range(len(ordered))):
            raise ValueError(f"task {task_id} has non-contiguous rubric indices")
        local = local_items[task_id]
        outputs = parse_jsonish(ordered[0]["output_files"], [])
        rubric_texts = [row["rubric"] for row in ordered]
        rubric_types = [row["rubric_type"] for row in ordered]
        checks = {
            "language": (str(local.metadata.get("language") or ""), "cn"),
            "source_revision": (
                str(local.metadata.get("source_revision") or ""),
                WORKSPACE_DATASET_REVISION,
            ),
            "task": (local.task, ordered[0]["task"]),
            "output_files": (workspace_outputs(local), outputs),
            "rubrics": (workspace_rubrics(local), rubric_texts),
            "rubric_types": (workspace_rubric_types(local), rubric_types),
        }
        for field, (actual, expected) in checks.items():
            if actual != expected:
                mismatches.append(f"task={task_id} field={field}")
        missing = [str(path) for path in workspace_input_paths(local) if not path.is_file()]
        if missing:
            mismatches.append(f"task={task_id} missing_inputs={len(missing)}")
        items[task_id] = local
    if mismatches:
        raise ValueError(
            "dataset/weak-reference alignment gate failed: "
            + "; ".join(mismatches[:20])
        )
    if set(items) != set(by_task):
        raise ValueError("local task IDs and weak-reference task IDs are not identical")
    return items, truth


def read_existing(
    path: Path, run_signature: str | None = None,
) -> dict[tuple[str, int], dict[str, Any]]:
    out: dict[tuple[str, int], dict[str, Any]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            key = (str(row["task_id"]), int(row["rubric_index"]))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if run_signature is not None and row.get("run_signature") != run_signature:
            continue
        if decision_has_operational_failure(row):
            continue
        out[key] = row
    return out


@contextmanager
def exclusive_run_lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".run.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another experiment owns {lock_path}") from exc
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def decision_has_operational_failure(row: dict[str, Any]) -> bool:
    scanner = row.get("scanner")
    verifier = row.get("verifier")
    return bool(
        (isinstance(scanner, dict) and scanner.get("operational_failure"))
        or (isinstance(verifier, dict) and verifier.get("operational_failure"))
    )


def stable_split(task_id: str) -> str:
    bucket = int(hashlib.sha256(f"20260714:{task_id}".encode()).hexdigest()[:8], 16) % 10
    if bucket < 2:
        return "test"
    if bucket < 4:
        return "development"
    return "analysis"


def preflight_evidence(
    items: dict[str, BenchmarkItem], *, workers: int = 8,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Materialize extraction coverage and hash every attachment before API use."""
    bundles: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        futures = {
            pool.submit(build_workspace_evidence_bundle, item): task_id
            for task_id, item in items.items()
        }
        for future in as_completed(futures):
            bundles[futures[future]] = future.result()
    rows = []
    digest_rows = []
    for task_id in sorted(items, key=int):
        bundle = bundles[task_id]
        physical_count = len(workspace_input_paths(items[task_id]))
        row = {
            "task_id": task_id,
            "physical_files": physical_count,
            "indexed_files": len(bundle.indexed_files),
            "readable_files": len(bundle.readable_files),
            "partial_files": list(bundle.partial_files),
            "parse_failures": list(bundle.parse_failures),
            "excluded_files": list(bundle.excluded_files),
            "total_bytes": bundle.total_bytes,
            "artifact_manifest_sha256": bundle.artifact_manifest_sha256,
            "evidence_preview_sha256": bundle.sha256,
        }
        rows.append(row)
        digest_rows.append((task_id, bundle.artifact_manifest_sha256))
    snapshot_sha = hashlib.sha256(
        json.dumps(digest_rows, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    failed_tasks = [row["task_id"] for row in rows if row["parse_failures"]]
    summary = {
        "workspace_snapshot_sha256": snapshot_sha,
        "tasks": len(rows),
        "physical_files": sum(row["physical_files"] for row in rows),
        "indexed_files": sum(row["indexed_files"] for row in rows),
        "readable_files": sum(row["readable_files"] for row in rows),
        "total_bytes": sum(row["total_bytes"] for row in rows),
        "parse_failure_files": sum(len(row["parse_failures"]) for row in rows),
        "parse_failure_tasks": len(failed_tasks),
        "parse_complete_task_ids": [
            row["task_id"] for row in rows if not row["parse_failures"]
        ],
        "untruncated_native_preview_task_ids": [
            row["task_id"] for row in rows
            if not row["parse_failures"] and not row["partial_files"]
        ],
        "excluded_reference_files": sum(len(row["excluded_files"]) for row in rows),
        "per_task": rows,
    }
    return bundles, summary


def run_predictions(
    items: dict[str, BenchmarkItem],
    bundles: dict[str, Any],
    client: LLMClient,
    path: Path,
    *,
    workers: int,
    verify: bool,
    min_confidence: float,
    batch_size: int,
    run_signature: str,
) -> list[dict[str, Any]]:
    existing = read_existing(path, run_signature)
    lock = threading.Lock()
    path.parent.mkdir(parents=True, exist_ok=True)

    def one_task(task_id: str, item: BenchmarkItem) -> list[dict[str, Any]]:
        missing = [
            (index, rubric)
            for index, rubric in enumerate(item.evaluator["rubrics"])
            if (task_id, index) not in existing
        ]
        if not missing:
            return []
        auditor = WorkspaceRubricGroundingAuditor(
            client,
            verify_unsupported=verify,
            min_confidence=min_confidence,
        )
        bundle = bundles[task_id]
        rows: list[dict[str, Any]] = []
        if batch_size == 1:
            # This is exactly the production checker path, isolated one rubric
            # at a time so hidden rubric neighbours cannot leak target facts.
            decisions = [
                auditor.audit_rubric(item, index, rubric, bundle)
                for index, rubric in missing
            ]
        else:
            decisions = auditor.audit_rubrics_batched(
                item, missing, bundle, batch_size=batch_size,
            )
        operational_failures = 0
        for value in decisions:
            decision = value.to_dict()
            decision["task_id"] = task_id
            decision["split"] = stable_split(task_id)
            decision["run_signature"] = run_signature
            decision["protocol_version"] = PROTOCOL_VERSION
            if decision_has_operational_failure(decision):
                operational_failures += 1
                continue
            rows.append(decision)
            with lock:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(decision, ensure_ascii=False) + "\n")
        if operational_failures:
            print(
                f"[retryable] task={task_id} operational_failures={operational_failures}",
                flush=True,
            )
        return rows

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(one_task, task_id, item): task_id for task_id, item in items.items()}
        completed = 0
        for future in as_completed(futures):
            task_id = futures[future]
            rows = future.result()
            completed += 1
            print(
                f"[{completed}/{len(futures)}] task={task_id} new_rubrics={len(rows)} "
                f"elapsed={time.monotonic() - started:.1f}s",
                flush=True,
            )
    return list(read_existing(path, run_signature).values())


def experiment_signature(
    *,
    dataset_path: Path,
    workspace_snapshot_sha256: str,
    model: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
    dry_run: bool,
    verify: bool,
    min_confidence: float,
    batch_size: int,
) -> str:
    scanner_prompt = GROUNDING_PROMPT if batch_size == 1 else BATCH_GROUNDING_PROMPT
    verifier_prompt = VERIFIER_PROMPT if batch_size == 1 else BATCH_VERIFIER_PROMPT
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_sha256": UPSTREAM_SHA256,
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "workspace_dataset_revision": WORKSPACE_DATASET_REVISION,
        "workspace_snapshot_sha256": workspace_snapshot_sha256,
        "model": model,
        "base_url": base_url.rstrip("/"),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "dry_run": dry_run,
        "verify": verify,
        "min_confidence": min_confidence,
        "batch_size": batch_size,
        "scanner_prompt_sha256": hashlib.sha256(
            (GROUNDING_SYSTEM + scanner_prompt).encode("utf-8")
        ).hexdigest(),
        "verifier_prompt_sha256": hashlib.sha256(
            (VERIFIER_SYSTEM + verifier_prompt).encode("utf-8")
        ).hexdigest(),
        **implementation_hashes(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def implementation_hashes() -> dict[str, str]:
    """Exact source-byte manifest needed to interpret a dirty-worktree run."""

    return {
        "grounding_code_sha256": hashlib.sha256(
            (REPO / "benchcore/workspace_grounding.py").read_bytes()
        ).hexdigest(),
        "file_reader_code_sha256": hashlib.sha256(
            (REPO / "benchcore/file_reader.py").read_bytes()
        ).hexdigest(),
        "experiment_code_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
    }


def confusion_metrics(
    truth: dict[tuple[str, int], dict[str, str]],
    predictions: Iterable[dict[str, Any]],
    *,
    split: str | None = None,
    task_ids: set[str] | None = None,
) -> dict[str, Any]:
    predicted = {
        (str(row["task_id"]), int(row["rubric_index"])): str(row.get("label") or "uncertain")
        for row in predictions
        if split is None or row.get("split") == split
    }
    expected_keys = [
        key for key in truth
        if (split is None or stable_split(key[0]) == split)
        and (task_ids is None or key[0] in task_ids)
    ]
    keys = [key for key in expected_keys if key in predicted]
    matrix = {label: {other: 0 for other in LABELS} for label in LABELS}
    for key in keys:
        gold = LABEL_MAP[truth[key]["basis_label"]]
        pred = predicted[key]
        if pred not in LABELS:
            pred = "uncertain"
        matrix[gold][pred] += 1
    per_class: dict[str, dict[str, float | int | list[float]]] = {}
    for label in LABELS:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in LABELS if other != label)
        fn = sum(matrix[label][other] for other in LABELS if other != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_class[label] = {
            "support": tp + fn,
            "predicted": tp + fp,
            "precision": precision,
            "recall": recall,
            "recall_wilson95": list(wilson(tp, tp + fn)),
            "f1": harmonic(precision, recall),
        }
    total = len(keys)
    expected_total = len(expected_keys)
    correct = sum(matrix[label][label] for label in LABELS)
    unsupported = per_class["unsupported"]
    supported_negative = sum(matrix["supported"].values())
    false_unsupported = matrix["supported"]["unsupported"]
    return {
        "rows": total,
        "expected_rows": expected_total,
        "operational_missing_rows": expected_total - total,
        "coverage": 0.0 if not expected_total else total / expected_total,
        "matrix": matrix,
        "accuracy": correct / total if total else 0.0,
        "accuracy_wilson95": list(wilson(correct, total)),
        "macro_f1": sum(float(per_class[label]["f1"]) for label in LABELS) / len(LABELS),
        "macro_f1_observed_classes": (
            sum(float(row["f1"]) for row in per_class.values() if row["support"])
            / max(1, sum(1 for row in per_class.values() if row["support"]))
        ),
        "per_class": per_class,
        "unsupported_binary": {
            "precision": unsupported["precision"],
            "recall": unsupported["recall"],
            "f1": unsupported["f1"],
            "false_positive_rate_on_supported": (
                false_unsupported / supported_negative if supported_negative else 0.0
            ),
            "false_positive_wilson95": list(wilson(false_unsupported, supported_negative)),
        },
        "unresolved_rate": (
            sum(matrix[gold]["uncertain"] for gold in LABELS) / total if total else 0.0
        ),
        "task_cluster_bootstrap95": cluster_bootstrap95(truth, predicted, keys),
        "task_macro_accuracy": task_macro_accuracy(truth, predicted, keys),
    }


def _binary_scores(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall, harmonic(precision, recall)


def cluster_bootstrap95(
    truth: dict[tuple[str, int], dict[str, str]],
    predicted: dict[tuple[str, int], str],
    keys: list[tuple[str, int]],
    iterations: int = 2000,
) -> dict[str, list[float]]:
    by_task: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for key in keys:
        by_task[key[0]].append(key)
    task_ids = sorted(by_task, key=int)
    if not task_ids:
        return {name: [0.0, 0.0] for name in (
            "accuracy", "unsupported_precision", "unsupported_recall", "unsupported_f1",
        )}
    rng = random.Random(20260714)
    values: dict[str, list[float]] = defaultdict(list)
    for _ in range(iterations):
        sampled = [rng.choice(task_ids) for _ in task_ids]
        correct = total = tp = fp = fn = 0
        for task_id in sampled:
            for key in by_task[task_id]:
                gold = LABEL_MAP[truth[key]["basis_label"]]
                pred = predicted[key] if predicted[key] in LABELS else "uncertain"
                total += 1
                correct += int(gold == pred)
                tp += int(gold == "unsupported" and pred == "unsupported")
                fp += int(gold != "unsupported" and pred == "unsupported")
                fn += int(gold == "unsupported" and pred != "unsupported")
        precision, recall, f1 = _binary_scores(tp, fp, fn)
        values["accuracy"].append(correct / total if total else 0.0)
        values["unsupported_precision"].append(precision)
        values["unsupported_recall"].append(recall)
        values["unsupported_f1"].append(f1)
    return {name: _percentile95(rows) for name, rows in values.items()}


def _percentile95(values: list[float]) -> list[float]:
    ordered = sorted(values)
    if not ordered:
        return [0.0, 0.0]
    lower = ordered[int(0.025 * (len(ordered) - 1))]
    upper = ordered[int(0.975 * (len(ordered) - 1))]
    return [lower, upper]


def task_macro_accuracy(
    truth: dict[tuple[str, int], dict[str, str]],
    predicted: dict[tuple[str, int], str],
    keys: list[tuple[str, int]],
) -> float:
    by_task: dict[str, list[int]] = defaultdict(list)
    for key in keys:
        by_task[key[0]].append(
            int(LABEL_MAP[truth[key]["basis_label"]] == predicted[key])
        )
    return (
        sum(sum(values) / len(values) for values in by_task.values()) / len(by_task)
        if by_task else 0.0
    )


def baseline_predictions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    report = json.loads(path.read_text(encoding="utf-8"))
    predicted: set[tuple[str, int]] = set()
    for row in report.get("violations", []):
        if row.get("detection_method") != "grounded_rubric_consistency":
            continue
        if row.get("defect_type") != "task_rubric_mismatch":
            continue
        index = (row.get("evidence") or {}).get("rubric_index")
        item_id = str(row.get("item_id") or "")
        if isinstance(index, int) and item_id.startswith("workspacebench-"):
            predicted.add((item_id.removeprefix("workspacebench-"), index))
    rows = []
    # Missing baseline positives are materialized as supported by the caller's truth keys.
    for task_id, index in predicted:
        rows.append({
            "task_id": task_id, "rubric_index": index, "label": "unsupported",
            "split": stable_split(task_id),
        })
    return rows


def score_baseline(
    truth: dict[tuple[str, int], dict[str, str]], rows: list[dict[str, Any]], split: str | None,
) -> dict[str, Any]:
    positive = {(row["task_id"], int(row["rubric_index"])) for row in rows}
    dense = [
        {
            "task_id": task_id,
            "rubric_index": index,
            "label": "unsupported" if (task_id, index) in positive else "supported",
            "split": stable_split(task_id),
        }
        for task_id, index in truth
    ]
    return confusion_metrics(truth, dense, split=split)


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def harmonic(a: float, b: float) -> float:
    return 0.0 if a + b == 0 else 2 * a * b / (a + b)


def render_markdown(summary: dict[str, Any]) -> str:
    current = summary["metrics"]["all"]
    baseline = summary.get("baseline", {}).get("all")
    lines = [
        "# Workspace-Bench rubric grounding 弱参考集实验",
        "",
        f"> 运行时间：{summary['run']['finished_at']}。上游标签是 preliminary audit，**不是人工 gold**。",
        "",
        "## 核心结果",
        "",
        "| 系统 | Rubrics | Unsupported P | Unsupported R | Unsupported F1 | 3-class accuracy | Unresolved |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    if baseline:
        b = baseline["unsupported_binary"]
        lines.append(
            f"| 旧 EN sparse-detector（不可归因对比） | {baseline['rows']} | {b['precision']:.3f} | "
            f"{b['recall']:.3f} | {b['f1']:.3f} | {baseline['accuracy']:.3f} | {baseline['unresolved_rate']:.3f} |"
        )
    c = current["unsupported_binary"]
    lines.append(
        f"| isolated rubric-level + verifier | {current['rows']}/{current['expected_rows']} | {c['precision']:.3f} | "
        f"{c['recall']:.3f} | {c['f1']:.3f} | {current['accuracy']:.3f} | {current['unresolved_rate']:.3f} |"
    )
    lines.extend([
        "",
        "## 证据边界",
        "",
        "- 指标衡量与上游初步 grounding 审计的一致性，不等于真实缺陷 precision/recall。",
        "- 模型看不到 `basis_label/basis/reason/checked_files`，只看到 task、output contract 和本地输入证据。",
        "- 疑似 reference generator 默认从 grounding 证据中遮蔽。",
        "- `uncertain` 单独报告，不强塞进 supported/unsupported。",
        f"- API/格式失败不进入语义矩阵；当前 operational coverage 为 `{current['coverage']:.3%}`。",
        f"- 附件预检：{summary['evidence_preflight']['readable_files']}/{summary['evidence_preflight']['indexed_files']} 可解析，"
        f"{summary['evidence_preflight']['parse_failure_tasks']} 个任务含不可解析文件；另行报告 parse-complete 子集。",
        "- 置信区间主口径按 task 做 cluster bootstrap，避免把同一任务的 rubrics 当成独立样本。",
        "- analysis/development/test 是冻结的 task-level 分区，但本次不是盲测人工 gold，不能称为 held-out 泛化性能。",
        "",
        "## 可复现信息",
        "",
        f"- Upstream commit: `{summary['reference']['commit']}`",
        f"- CSV SHA-256: `{summary['reference']['sha256']}`",
        f"- Workspace snapshot SHA-256: `{summary['evidence_preflight']['workspace_snapshot_sha256']}`",
        f"- Workspace dataset revision: `{summary['run']['workspace_dataset_revision']}`",
        f"- Model: `{summary['run']['llm'].get('model')}`",
        f"- Protocol: `{summary['run']['protocol_version']}`",
        f"- Run signature: `{summary['run']['signature']}`",
        f"- API attempts: {summary['run']['llm'].get('api_attempts', 0)}",
        f"- Total tokens: {summary['run']['llm'].get('total_tokens', 0)}",
        f"- Wall time: {summary['run']['wall_seconds']:.1f}s",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    label_path = ensure_labels(REPO / args.labels)
    labels = load_silver_rows(label_path)
    items, truth = build_experiment_items(REPO / args.dataset, labels)
    selected_ids = set(args.task_id or [])
    if selected_ids:
        items = {key: value for key, value in items.items() if key in selected_ids}
    if args.limit_tasks is not None:
        items = dict(sorted(items.items(), key=lambda row: int(row[0]))[: args.limit_tasks])
    selected_truth = {key: value for key, value in truth.items() if key[0] in items}

    if not 1 <= args.batch_size <= 12:
        raise ValueError("--batch-size must be between 1 and 12")
    if args.batch_size > 1 and not args.allow_cross_rubric_batching:
        raise ValueError(
            "batching can leak hidden rubric facts; pass --allow-cross-rubric-batching "
            "only for a labeled ablation"
        )
    if args.operational_passes < 1:
        raise ValueError("--operational-passes must be positive")

    bundles, evidence_preflight = preflight_evidence(items, workers=args.workers)

    config = load_llm_config(str(REPO / args.llm_config))
    if config.dry_run:
        raise ValueError("dry_run responses are forbidden in a scored experiment")
    config.cache_path = str(REPO / args.llm_cache)
    signature = experiment_signature(
        dataset_path=REPO / args.dataset,
        workspace_snapshot_sha256=evidence_preflight["workspace_snapshot_sha256"],
        model=config.model,
        base_url=config.base_url,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        dry_run=config.dry_run,
        verify=not args.no_verifier,
        min_confidence=args.min_confidence,
        batch_size=args.batch_size,
    )
    client = LLMClient(config)
    rows_path = REPO / args.rows_out
    predictions: list[dict[str, Any]] = []
    with exclusive_run_lock(rows_path):
        for operational_pass in range(1, args.operational_passes + 1):
            predictions = run_predictions(
                items,
                bundles,
                client,
                rows_path,
                workers=args.workers,
                verify=not args.no_verifier,
                min_confidence=args.min_confidence,
                batch_size=args.batch_size,
                run_signature=signature,
            )
            completed_keys = {
                (str(row["task_id"]), int(row["rubric_index"])) for row in predictions
            }
            missing = len(selected_truth) - len(set(selected_truth) & completed_keys)
            print(
                f"operational_pass={operational_pass} completed={len(completed_keys)} "
                f"missing={missing}",
                flush=True,
            )
            if missing == 0:
                break
    predictions = [row for row in predictions if str(row.get("task_id")) in items]
    metrics = {
        split: confusion_metrics(selected_truth, predictions, split=None if split == "all" else split)
        for split in ("all", "test", "development", "analysis")
    }
    parse_complete_ids = set(evidence_preflight["parse_complete_task_ids"])
    parse_complete_metrics = confusion_metrics(
        selected_truth, predictions, task_ids=parse_complete_ids,
    )
    high_confidence_truth = {
        key: row for key, row in selected_truth.items()
        if float(row.get("confidence") or 0.0) >= 0.9
    }
    high_confidence_metrics = confusion_metrics(high_confidence_truth, predictions)
    baseline_rows = (
        baseline_predictions(REPO / args.baseline_report) if args.baseline_report else []
    )
    baseline = {
        split: score_baseline(selected_truth, baseline_rows, None if split == "all" else split)
        for split in ("all", "test", "development", "analysis")
    } if baseline_rows else {}
    summary = {
        "reference": {
            "type": "official_preliminary_grounding_audit_weak_reference",
            "url": UPSTREAM_URL,
            "commit": UPSTREAM_COMMIT,
            "relative_path": UPSTREAM_RELATIVE_PATH,
            "sha256": UPSTREAM_SHA256,
            "label_distribution": dict(Counter(row["basis_label"] for row in labels)),
            "selected_label_distribution": dict(
                Counter(row["basis_label"] for row in selected_truth.values())
            ),
            "selected_high_confidence_rows": len(high_confidence_truth),
            "warning": "This is not independently verified human gold.",
        },
        "run": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_seconds": time.monotonic() - started,
            "tasks": len(items),
            "rubrics": len(selected_truth),
            "workers": args.workers,
            "batch_size": args.batch_size,
            "cross_rubric_batching": args.batch_size > 1,
            "verifier_enabled": not args.no_verifier,
            "min_confidence": args.min_confidence,
            "protocol_version": PROTOCOL_VERSION,
            "signature": signature,
            "dataset": str(REPO / args.dataset),
            "workspace_dataset_revision": WORKSPACE_DATASET_REVISION,
            "implementation": implementation_hashes(),
            "llm": client.run_stats(),
        },
        "alignment_gate": {
            "language": "cn",
            "tasks_exactly_aligned": len(items),
            "rubrics_exactly_aligned": len(selected_truth),
            "status": "passed",
        },
        "evidence_preflight": evidence_preflight,
        "metrics": metrics,
        "metrics_parse_complete_tasks": parse_complete_metrics,
        "metrics_weak_reference_confidence_ge_0_9": high_confidence_metrics,
        "baseline": baseline,
        "baseline_warning": (
            "Optional baseline is an English sparse detector with a different protocol; "
            "it is not an attributable head-to-head comparison."
            if baseline else None
        ),
    }
    summary_path = REPO / args.summary_out
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path = REPO / args.md
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps(metrics["all"], ensure_ascii=False, indent=2))
    return 0 if metrics["all"]["coverage"] == 1.0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
