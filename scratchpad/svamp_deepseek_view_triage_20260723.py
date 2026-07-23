#!/usr/bin/env python3
"""External, label-isolated SVAMP response-triage experiment.

The experiment tests prompt-diverse views of one DeepSeek model as a fallback
for a genuine multi-model response matrix.  It never treats behavioral evidence
as confirmation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchcore.llm_client import LLMClient, LLMConfig


SOURCE = Path(
    "/home/zhoujun/llmdata/datasets/svamp_platinum/svamp_platinum_all.jsonl"
)
MANIFEST = ROOT / "experiments" / "svamp_platinum_pilot100.manifest.json"
PROTOCOL_V1 = ROOT / "scratchpad" / "SVAMP_DEEPSEEK_VIEW_TRIAGE_PROTOCOL_20260723.md"
PROTOCOL = (
    ROOT / "scratchpad" / "SVAMP_DEEPSEEK_VIEW_TRIAGE_PROTOCOL_V2_20260723.md"
)
OUT = ROOT / "reports" / "svamp_deepseek_view_triage_20260723"
PUBLIC = OUT / "public_items.jsonl"
LABELS = OUT / "labels.json"
RESPONSES = OUT / "responses"
ERRORS = OUT / "collection_errors.jsonl"
COLLECTION = OUT / "collection_metadata.json"
AUDIT = OUT / "static_audit.json"
AUDIT_MD = OUT / "static_audit.md"
TRIAGE = OUT / "triage.json"
TRIAGE_MD = OUT / "triage.md"
FOLLOWUP_TRIAGE = OUT / "triage_priority_min4.json"
METRICS = OUT / "metrics.json"
REPORT = OUT / "report.md"

EXPECTED_SHA256 = {
    SOURCE: "f27f8ebf56b33fbeea4b6430f63f24c66adb37bd38a1a8b2bbe62960f588063e",
    MANIFEST: "c4ef5ddfb590b210243c0114d7d9eed7a15c2c0a1cf14a98f763cb7d4992d861",
    PROTOCOL_V1: "f89c0acb66c64d5de46a116f8421640b5de5232ea696cc94c2d47b27b2a800a9",
    PROTOCOL: "b8259076ec1674df168b4915ebaa04ed76614bb8bbe7265b49025a57edfec909",
}
MODEL = "deepseek-v4-flash"
SEED = 20260723
R0_COLLECTION_METADATA_SHA256 = (
    "5151a60ee6b02d0d8832fc6c559625ed5cf9f1561eb1508b7467d5c7b8c80c75"
)
VIEWS = [
    (
        "view01_direct_nonthinking",
        "disabled",
        "Solve the arithmetic word problem directly. Return only the requested JSON.",
    ),
    (
        "view02_equation_nonthinking",
        "disabled",
        "Translate the problem into an equation, solve it, and return only the requested JSON.",
    ),
    (
        "view03_stepwise_nonthinking",
        "disabled",
        "Solve carefully step by step internally. Return only the requested JSON.",
    ),
    (
        "view04_verifier_nonthinking",
        "disabled",
        "Act as an independent verifier. Check the quantities and return only the requested JSON.",
    ),
    (
        "view05_units_thinking",
        "enabled",
        "Check units, entities, and which quantity is asked for before solving. Return only JSON.",
    ),
    (
        "view06_alternative_thinking",
        "enabled",
        "Use an alternative solution method and sanity-check the result. Return only JSON.",
    ),
    (
        "view07_ambiguity_thinking",
        "enabled",
        "Inspect the wording for contradictions or ambiguity, then give the most defensible numeric answer. Return only JSON.",
    ),
    (
        "view08_minimal_thinking",
        "enabled",
        "Find the final numeric answer with minimal assumptions. Return only the requested JSON.",
    ),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise TypeError(f"{path}:{line_number}: row must be an object")
        rows.append(row)
    return rows


def stable_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def stable_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False)
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def verify_inputs() -> None:
    for path, expected in EXPECTED_SHA256.items():
        if not path.exists():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                f"frozen input changed: {path}; expected {expected}, got {actual}"
            )


def prepare() -> None:
    verify_inputs()
    source_rows = load_jsonl(SOURCE)
    if len(source_rows) != 300:
        raise ValueError(f"expected 300 source rows, found {len(source_rows)}")
    public_rows: list[dict[str, Any]] = []
    labels: dict[str, Any] = {}
    for row in source_rows:
        item_id = str(row["id"])
        if item_id in labels:
            raise ValueError(f"duplicate item ID: {item_id}")
        public_rows.append(
            {
                "id": item_id,
                "task": row["task"],
                "gold": row["gold"],
                "output_contract": row["output_contract"],
                "evaluator": row["evaluator"],
            }
        )
        metadata = row["metadata"]
        labels[item_id] = {
            "audit_label": metadata["audit_label"],
            "cleaning_status": metadata["cleaning_status"],
            "is_defect": metadata["audit_label"] != "clean",
            "is_revised": metadata["cleaning_status"] == "revised",
        }
    counts: dict[str, int] = {}
    for row in labels.values():
        key = str(row["cleaning_status"])
        counts[key] = counts.get(key, 0) + 1
    if sum(row["is_defect"] for row in labels.values()) != 38:
        raise ValueError("expected 38 SVAMP-Platinum defects")
    stable_jsonl(PUBLIC, public_rows)
    stable_json(
        LABELS,
        {
            "schema_version": 1,
            "source": str(SOURCE),
            "counts": counts,
            "items": labels,
        },
    )
    forbidden = (b"audit_label", b"cleaning_status", b"platinum_target", b"is_defect")
    leaked = [token.decode() for token in forbidden if token in PUBLIC.read_bytes()]
    if leaked:
        raise AssertionError(f"label leakage into public artifact: {leaked}")
    print(
        f"prepared 300 public rows; public={sha256_file(PUBLIC)[:12]}, "
        f"labels={sha256_file(LABELS)[:12]}"
    )


def parse_numeric(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("answer is not numeric")
    text = str(value).strip().replace(",", "")
    if not text:
        raise ValueError("empty answer")
    if "/" in text:
        try:
            fraction = Fraction(text)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"invalid fraction: {text!r}") from exc
        return Decimal(fraction.numerator) / Decimal(fraction.denominator)
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"answer is not a strict number: {text!r}") from exc
    if not parsed.is_finite():
        raise ValueError("answer must be finite")
    return parsed


def numeric_equal(left: Any, right: Any) -> bool:
    a = parse_numeric(left)
    b = parse_numeric(right)
    tolerance = max(Decimal("1e-9"), Decimal("1e-9") * max(abs(a), abs(b), 1))
    return abs(a - b) <= tolerance


def client_for(thinking: str, *, max_api_attempts: int) -> LLMClient:
    cache = OUT / f"deepseek_{thinking}_cache.jsonl"
    return LLMClient(
        LLMConfig(
            model=MODEL,
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
            temperature=0.0,
            timeout=120,
            max_tokens=1200 if thinking == "enabled" else 300,
            max_retries=2,
            cache_path=str(cache),
            thinking=thinking,
            max_api_attempts=max_api_attempts,
        )
    )


SYSTEM = """You solve arithmetic benchmark items.
Return exactly one JSON object with this schema:
{"answer": "<single numeric value>"}
Do not include units, prose, equations, markdown, or additional keys.
If the wording is flawed, still return the most defensible numeric answer."""


def collect(*, limit: int | None, workers: int) -> None:
    if not PUBLIC.exists():
        raise FileNotFoundError("run prepare first")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    if any(
        token in PUBLIC.read_bytes()
        for token in (b"audit_label", b"cleaning_status", b"platinum_target")
    ):
        raise AssertionError("refusing label-bearing inference input")
    rows = load_jsonl(PUBLIC)
    if limit is not None:
        rows = rows[: max(limit, 0)]
    prior_metadata = load_json(COLLECTION) if COLLECTION.exists() else {}
    prior_clients = prior_metadata.get("clients", {})
    jobs: list[tuple[str, str, str, str, Any]] = []
    for view_id, thinking, instruction in VIEWS:
        existing_path = RESPONSES / f"{view_id}.jsonl"
        existing_ids = (
            {str(row["id"]) for row in load_jsonl(existing_path)}
            if existing_path.exists()
            else set()
        )
        for row in rows:
            item_id = str(row["id"])
            if item_id in existing_ids:
                continue
            user = (
                f"{instruction}\n\nProblem:\n{row['task']}\n\n"
                "Return the JSON answer now."
            )
            jobs.append((view_id, thinking, item_id, user, row["gold"]))
    jobs_by_mode = Counter(job[1] for job in jobs)
    remaining_attempts = {
        mode: 1300
        - int(prior_clients.get(mode, {}).get("api_attempts", 0) or 0)
        for mode in ("disabled", "enabled")
    }
    for mode, count in jobs_by_mode.items():
        if count and remaining_attempts[mode] <= 0:
            raise RuntimeError(
                f"persistent API-attempt budget exhausted for {mode}"
            )
    clients = {
        mode: client_for(
            mode,
            max_api_attempts=max(1, remaining_attempts[mode]),
        )
        for mode in ("disabled", "enabled")
    }
    print(
        f"collecting {len(jobs)} uncached logical responses with "
        f"{max(workers, 1)} workers"
    )

    results: dict[str, list[dict[str, Any]]] = {view[0]: [] for view in VIEWS}
    failures: list[dict[str, Any]] = []

    def run_one(job: tuple[str, str, str, str, Any]) -> tuple[str, dict[str, Any]]:
        view_id, thinking, item_id, user, gold = job
        response = clients[thinking].chat_json(SYSTEM, user)
        if set(response) != {"answer"}:
            raise ValueError(
                f"response keys must be exactly ['answer'], got {sorted(response)}"
            )
        prediction = str(response["answer"]).strip()
        correct = numeric_equal(prediction, gold)
        return view_id, {
            "id": item_id,
            "model_id": view_id,
            "correct": correct,
            "prediction": prediction,
        }

    with ThreadPoolExecutor(max_workers=max(workers, 1)) as executor:
        future_to_job = {executor.submit(run_one, job): job for job in jobs}
        completed = 0
        for future in as_completed(future_to_job):
            job = future_to_job[future]
            completed += 1
            try:
                view_id, result = future.result()
                results[view_id].append(result)
            except Exception as exc:  # preserve failures as missing observations
                failures.append(
                    {
                        "view": job[0],
                        "item_id": job[2],
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            if completed % 100 == 0 or completed == len(jobs):
                print(f"[{completed}/{len(jobs)}] failures={len(failures)}")

    RESPONSES.mkdir(parents=True, exist_ok=True)
    for view_id, _, _ in VIEWS:
        path = RESPONSES / f"{view_id}.jsonl"
        old = load_jsonl(path) if path.exists() else []
        combined = {str(row["id"]): row for row in old}
        for row in results[view_id]:
            if str(row["id"]) in combined:
                raise AssertionError(f"duplicate collected item: {view_id}/{row['id']}")
            combined[str(row["id"])] = row
        stable_jsonl(path, [combined[item_id] for item_id in sorted(combined)])
    successful_pairs = {
        (view_id, str(row["id"]))
        for view_id, _, _ in VIEWS
        for row in load_jsonl(RESPONSES / f"{view_id}.jsonl")
    }
    old_failures = load_jsonl(ERRORS) if ERRORS.exists() else []
    unresolved = {
        (
            row["view"],
            row["item_id"],
            row["error_type"],
            row["message"],
        ): row
        for row in old_failures + failures
        if (row["view"], row["item_id"]) not in successful_pairs
    }
    stable_jsonl(
        ERRORS,
        sorted(
            unresolved.values(),
            key=lambda row: (row["view"], row["item_id"], row["message"]),
        ),
    )
    counter_keys = {
        "cache_hits",
        "singleflight_waits",
        "singleflight_shared_results",
        "singleflight_shared_failures",
        "api_attempts",
        "api_successes",
        "api_failures",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "invalid_responses",
        "truncated_responses",
    }
    cumulative_clients: dict[str, Any] = {}
    for mode, client in clients.items():
        current = client.run_stats()
        prior = prior_clients.get(mode, {})
        merged = dict(current)
        for key in counter_keys:
            merged[key] = int(prior.get(key, 0) or 0) + int(
                current.get(key, 0) or 0
            )
        merged["persistent_attempt_cap"] = 1300
        cumulative_clients[mode] = merged
    metadata = {
        "schema_version": 1,
        "model": MODEL,
        "logical_target": len(rows) * len(VIEWS),
        "logical_completed_files": {
            view_id: len(load_jsonl(RESPONSES / f"{view_id}.jsonl"))
            for view_id, _, _ in VIEWS
        },
        "failures_this_run": len(failures),
        "clients": cumulative_clients,
        "active_unresolved_failures": len(unresolved),
        "r0_collection_metadata_sha256": R0_COLLECTION_METADATA_SHA256,
        "protocol_v1_sha256": sha256_file(PROTOCOL_V1),
        "protocol_sha256": sha256_file(PROTOCOL),
        "public_sha256": sha256_file(PUBLIC),
    }
    stable_json(COLLECTION, metadata)
    print(
        f"collection saved; successes="
        f"{sum(metadata['logical_completed_files'].values())}, "
        f"failures_this_run={len(failures)}"
    )


def audit() -> None:
    if not PUBLIC.exists():
        raise FileNotFoundError("run prepare first")
    command = [
        sys.executable,
        "-m",
        "benchcore.cli",
        "audit",
        str(PUBLIC),
        "--basic-only",
        "--profile",
        "generic",
        "--progress-every",
        "0",
        "--out",
        str(AUDIT),
        "--md",
        str(AUDIT_MD),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    print(f"static audit={sha256_file(AUDIT)[:12]}")


def triage() -> None:
    if not AUDIT.exists():
        raise FileNotFoundError("run audit first")
    expected_files = {f"{view[0]}.jsonl" for view in VIEWS}
    actual_files = {path.name for path in RESPONSES.glob("*.jsonl")}
    if actual_files != expected_files:
        raise ValueError(
            f"response file set differs; expected={sorted(expected_files)}, "
            f"actual={sorted(actual_files)}"
        )
    command = [
        sys.executable,
        "-m",
        "benchcore.cli",
        "triage-responses",
        str(RESPONSES),
        "--report",
        str(AUDIT),
        "--minimum-models",
        "8",
        "--panel-kind",
        "single-model-views",
        "--minimum-responses-per-item",
        "8",
        "--minimum-model-coverage",
        "0.95",
        "--audit-score-mode",
        "risk",
        "--out",
        str(TRIAGE),
        "--md",
        str(TRIAGE_MD),
        "--top-k",
        "50",
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    followup_command = [
        sys.executable,
        "-m",
        "benchcore.cli",
        "triage-responses",
        str(RESPONSES),
        "--report",
        str(AUDIT),
        "--minimum-models",
        "8",
        "--panel-kind",
        "single-model-views",
        "--minimum-responses-per-item",
        "4",
        "--minimum-model-coverage",
        "0.95",
        "--audit-score-mode",
        "priority-risk",
        "--out",
        str(FOLLOWUP_TRIAGE),
    ]
    subprocess.run(followup_command, cwd=ROOT, check=True)
    print(
        f"triage={sha256_file(TRIAGE)[:12]}, "
        f"followup={sha256_file(FOLLOWUP_TRIAGE)[:12]}"
    )


def expected_topk(
    item_ids: list[str],
    scores: dict[str, float],
    positives: set[str],
    ks: tuple[int, ...] = (20, 50, 100),
) -> dict[str, Any]:
    y = np.array([int(item_id in positives) for item_id in item_ids], dtype=int)
    s = np.array([scores[item_id] for item_id in item_ids], dtype=float)
    n_positive = int(y.sum())
    result: dict[str, Any] = {
        "n": len(item_ids),
        "positives": n_positive,
        "prevalence": n_positive / len(item_ids),
        "average_precision": float(average_precision_score(y, s)),
    }
    groups = []
    for score in sorted(set(float(value) for value in s), reverse=True):
        mask = s == score
        groups.append((int(mask.sum()), int(y[mask].sum())))
    for k in ks:
        if k > len(item_ids):
            continue
        remaining = k
        tp = 0.0
        for count, positive_count in groups:
            take = min(remaining, count)
            tp += take * positive_count / count
            remaining -= take
            if remaining == 0:
                break
        result[f"precision_at_{k}"] = tp / k
        result[f"recall_at_{k}"] = tp / n_positive
        result[f"lift_at_{k}"] = result[f"precision_at_{k}"] / result["prevalence"]
    return result


def pairwise_agreement(response_rows: dict[str, dict[str, bool]]) -> dict[str, Any]:
    views = sorted(response_rows)
    values: list[float] = []
    pairs: dict[str, float] = {}
    for left_index, left in enumerate(views):
        for right in views[left_index + 1 :]:
            common = sorted(set(response_rows[left]) & set(response_rows[right]))
            if not common:
                continue
            agreement = sum(
                response_rows[left][item_id] == response_rows[right][item_id]
                for item_id in common
            ) / len(common)
            pairs[f"{left}__{right}"] = agreement
            values.append(agreement)
    return {
        "pairs": pairs,
        "mean": float(np.mean(values)) if values else 0.0,
        "minimum": min(values, default=0.0),
        "maximum": max(values, default=0.0),
    }


def evaluate() -> None:
    for path in (PUBLIC, LABELS, TRIAGE, FOLLOWUP_TRIAGE, COLLECTION):
        if not path.exists():
            raise FileNotFoundError(path)
    labels = load_json(LABELS)["items"]
    triage_doc = load_json(TRIAGE)
    triage_rows = {row["item_id"]: row for row in triage_doc["items"]}
    if set(labels) != set(triage_rows):
        raise ValueError("label and triage item sets differ")
    methods = {
        "static_benchaudit": {
            item_id: float(row["audit_score"])
            for item_id, row in triage_rows.items()
        },
        "deepseek_view_error_rate": {
            item_id: float(row["error_rate"])
            for item_id, row in triage_rows.items()
        },
        "audit_error_rate_fusion": {
            item_id: float(row["fused_score"])
            for item_id, row in triage_rows.items()
        },
    }
    followup_doc = load_json(FOLLOWUP_TRIAGE)
    followup_rows = {
        row["item_id"]: row for row in followup_doc["items"]
    }
    if set(followup_rows) != set(triage_rows):
        raise ValueError("follow-up and preregistered triage item sets differ")
    full_ids = sorted(labels)
    positives = {item_id for item_id in full_ids if labels[item_id]["is_defect"]}
    manifest_ids = {
        str(row["item_id"]) for row in load_json(MANIFEST)["selected"]
    }
    if len(manifest_ids) != 100:
        raise ValueError("expected 100 manifest items")
    evaluation = {
        "full300": {
            method: expected_topk(
                full_ids,
                method_scores,
                positives,
            )
            for method, method_scores in methods.items()
        },
        "enriched_pilot100": {
            method: expected_topk(
                sorted(manifest_ids),
                method_scores,
                positives & manifest_ids,
            )
            for method, method_scores in methods.items()
        },
    }
    revised = {item_id for item_id in full_ids if labels[item_id]["is_revised"]}
    revised_descriptive = {
        method: expected_topk(full_ids, method_scores, revised)
        for method, method_scores in methods.items()
    }
    response_rows: dict[str, dict[str, bool]] = {}
    for path in sorted(RESPONSES.glob("*.jsonl")):
        response_rows[path.stem] = {
            str(row["id"]): bool(row["correct"]) for row in load_jsonl(path)
        }
    collection_counts = [len(rows) for rows in response_rows.values()]
    completeness = min(collection_counts) / len(full_ids)
    full = evaluation["full300"]
    fusion_ap = full["audit_error_rate_fusion"]["average_precision"]
    best_standalone = max(
        full["static_benchaudit"]["average_precision"],
        full["deepseek_view_error_rate"]["average_precision"],
    )
    conditions = {
        "fusion_ap_gain_at_least_0_020": fusion_ap - best_standalone >= 0.020,
        "fusion_p50_not_below_audit": (
            full["audit_error_rate_fusion"]["precision_at_50"]
            >= full["static_benchaudit"]["precision_at_50"]
        ),
        "at_least_three_unique_patterns": (
            triage_doc["quality"]["unique_model_correctness_patterns"] >= 3
        ),
        "at_least_95_percent_complete": completeness >= 0.95,
    }
    use_fallback = all(conditions.values())
    followup_metrics = expected_topk(
        full_ids,
        {
            item_id: float(followup_rows[item_id]["fused_score"])
            for item_id in full_ids
        },
        positives,
    )
    input_tokens = sum(
        client["prompt_tokens"]
        for client in load_json(COLLECTION)["clients"].values()
    )
    output_tokens = sum(
        client["completion_tokens"]
        for client in load_json(COLLECTION)["clients"].values()
    )
    metrics = {
        "schema_version": 1,
        "experiment": "SVAMP DeepSeek prompt-view response triage",
        "single_model_views_not_independent_models": True,
        "evaluation": evaluation,
        "revised_only_descriptive": revised_descriptive,
        "response_quality": {
            "per_view_count": dict(zip(sorted(response_rows), collection_counts)),
            "minimum_completeness": completeness,
            "pairwise_correctness_agreement": pairwise_agreement(response_rows),
            "production_quality": triage_doc["quality"],
        },
        "decision": {
            "conditions": conditions,
            "all_conditions_pass": use_fallback,
            "recommendation": (
                "allow_prompt_view_fallback_review_only"
                if use_fallback
                else "require_genuine_multimodel_trajectories"
            ),
        },
        "posthoc_safety_followup": {
            "not_part_of_frozen_decision": True,
            "change": (
                "exclude exploratory-only audit signals from fusion and allow "
                "the four complete non-thinking views to meet item coverage"
            ),
            "metrics": followup_metrics,
            "interpretation": (
                "prevents four weak static findings from degrading the response "
                "ranking; does not establish independent multi-model evidence"
            ),
        },
        "api": load_json(COLLECTION)["clients"],
        "estimated_api_cost_usd": {
            "as_of": "2026-07-23",
            "input_rate_per_million": 0.14,
            "output_rate_per_million": 0.28,
            "estimate": input_tokens * 0.14 / 1_000_000
            + output_tokens * 0.28 / 1_000_000,
            "caveat": (
                "DeepSeek V4 Flash cache-miss list rates; actual provider "
                "billing and cache discounts may differ"
            ),
        },
        "provenance": {
            "protocol_v1_sha256": sha256_file(PROTOCOL_V1),
            "protocol_sha256": sha256_file(PROTOCOL),
            "source_sha256": sha256_file(SOURCE),
            "public_sha256": sha256_file(PUBLIC),
            "labels_sha256": sha256_file(LABELS),
            "audit_sha256": sha256_file(AUDIT),
            "triage_sha256": sha256_file(TRIAGE),
            "followup_triage_sha256": sha256_file(FOLLOWUP_TRIAGE),
            "response_sha256": {
                path.name: sha256_file(path)
                for path in sorted(RESPONSES.glob("*.jsonl"))
            },
        },
    }
    stable_json(METRICS, metrics)
    REPORT.write_text(render_report(metrics), encoding="utf-8")
    print(
        f"evaluated recommendation={metrics['decision']['recommendation']}; "
        f"metrics={sha256_file(METRICS)[:12]}, report={sha256_file(REPORT)[:12]}"
    )


def render_report(metrics: dict[str, Any]) -> str:
    full = metrics["evaluation"]["full300"]
    pilot = metrics["evaluation"]["enriched_pilot100"]
    decision = metrics["decision"]
    quality = metrics["response_quality"]
    followup = metrics["posthoc_safety_followup"]["metrics"]
    labels = {
        "static_benchaudit": "Static BenchAudit",
        "deepseek_view_error_rate": "DeepSeek view error rate",
        "audit_error_rate_fusion": "Audit + view error rate",
    }
    lines = [
        "# SVAMP-Platinum：DeepSeek 多提示视角候选分诊实验",
        "",
        "> 本实验测试同一个 DeepSeek 模型的 8 种固定提示视角，能否在没有真实多模型"
        "轨迹时充当低成本替代。它们不是 8 个独立模型，所有信号保持 review-only。",
        "",
        "## 结论",
        "",
        (
            "**通过冻结门槛，可把多提示视角作为降级 fallback。**"
            if decision["all_conditions_pass"]
            else "**未通过冻结门槛：多提示视角不能替代真实多模型历史轨迹；"
            "DeepSeek 应只用于候选筛选后的语义归因。**"
        ),
        "",
        "| 冻结条件 | 结果 |",
        "|---|:---:|",
    ]
    for condition, passed in decision["conditions"].items():
        lines.append(f"| `{condition}` | {'✓' if passed else '✗'} |")
    lines.extend(
        [
            "",
            "## Full 300",
            "",
            "| 方法 | AP | P@20 | P@50 | P@100 | R@50 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for method, label in labels.items():
        row = full[method]
        lines.append(
            f"| {label} | {row['average_precision']:.3f} | "
            f"{row['precision_at_20']:.3f} | {row['precision_at_50']:.3f} | "
            f"{row['precision_at_100']:.3f} | {row['recall_at_50']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 旧 Pilot-100（缺陷富集，仅作次要对照）",
            "",
            "| 方法 | AP | P@20 | P@50 | R@50 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for method, label in labels.items():
        row = pilot[method]
        lines.append(
            f"| {label} | {row['average_precision']:.3f} | "
            f"{row['precision_at_20']:.3f} | {row['precision_at_50']:.3f} | "
            f"{row['recall_at_50']:.3f} |"
        )
    api_attempts = sum(
        client["api_attempts"] for client in metrics["api"].values()
    )
    prompt_tokens = sum(
        client["prompt_tokens"] for client in metrics["api"].values()
    )
    completion_tokens = sum(
        client["completion_tokens"] for client in metrics["api"].values()
    )
    lines.extend(
        [
            "",
            "## 响应质量与成本",
            "",
            f"- 最低单视角完整率：{quality['minimum_completeness']:.1%}",
            f"- 唯一 correctness pattern："
            f"{quality['production_quality']['unique_model_correctness_patterns']}",
            f"- 视角两两正确性平均一致率："
            f"{quality['pairwise_correctness_agreement']['mean']:.3f}",
            f"- API attempts：{api_attempts}",
            f"- Provider-reported tokens：input={prompt_tokens}，output={completion_tokens}",
            f"- 按 2026-07-23 Flash cache-miss 标价估算："
            f"${metrics['estimated_api_cost_usd']['estimate']:.3f}",
            "",
            "## 预注册后安全修正（不改变主裁决）",
            "",
            "Full-300 暴露出 4 条弱 exploratory 静态提示会降低行为排序。生产默认已改为"
            "只有 priority/confirmed 审计信号参与融合；同时本数据至少有 4 个完整的"
            "non-thinking 视角，因此以 4 作为该专项的最小覆盖。该修正没有读取标签调权重，"
            "但发生在看过主结果之后，只能作为后续诊断：",
            "",
            f"- 修正后 AP：{followup['average_precision']:.3f}",
            f"- 修正后 P@20/P@50：{followup['precision_at_20']:.3f} / "
            f"{followup['precision_at_50']:.3f}",
            "- 它避免了融合降级，但仍不把同模型视角冒充真实多模型证据。",
            "",
            "## 边界",
            "",
            "- Full 300 的标签在打分阶段物理隔离；评估阶段才读取。",
            "- `rejected` 题可能没有唯一正确答案，因此高错误率既可能是缺陷信号，也可能"
            "是模型无法处理歧义；本实验只评价候选排序，不评价自动确认。",
            "- 只有 3 条 `revised` 错答案，不能据此单独声称 wrong-gold 泛化能力。",
            "- 同模型多提示相关性很高，即使本数据集通过，也不能等价为跨组织多模型证据。",
            "",
            "## Provenance",
            "",
        ]
    )
    for name, value in metrics["provenance"].items():
        if isinstance(value, str):
            lines.append(f"- `{name}`: `{value}`")
    lines.append("")
    return "\n".join(lines)


def self_test() -> None:
    assert parse_numeric("1,234.5") == Decimal("1234.5")
    assert parse_numeric("1/4") == Decimal("0.25")
    assert numeric_equal("2.0", "2")
    try:
        parse_numeric("answer is 2")
    except ValueError:
        pass
    else:
        raise AssertionError("non-strict numeric parser accepted prose")
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase",
        choices=(
            "self-test",
            "prepare",
            "collect",
            "audit",
            "triage",
            "evaluate",
            "all",
        ),
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    if args.phase == "self-test":
        self_test()
    elif args.phase == "prepare":
        prepare()
    elif args.phase == "collect":
        collect(limit=args.limit, workers=args.workers)
    elif args.phase == "audit":
        audit()
    elif args.phase == "triage":
        triage()
    elif args.phase == "evaluate":
        evaluate()
    else:
        self_test()
        prepare()
        collect(limit=args.limit, workers=args.workers)
        if args.limit is not None:
            raise ValueError("all with --limit cannot proceed to full audit/triage")
        audit()
        triage()
        evaluate()


if __name__ == "__main__":
    main()
