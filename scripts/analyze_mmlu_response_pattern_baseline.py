#!/usr/bin/env python3
"""Evaluate the frozen 15-model MMLU response-pattern baseline offline."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments/mmlu_redux_pilot1000.jsonl"
AUDIT_REPORT = ROOT / "reports/ranking_impact/audit_full1000.json"
ANSWERS = ROOT / "reports/ranking_impact/answers"
PROTOCOL = ROOT / "docs/research/MMLU_RESPONSE_PATTERN_BASELINE_PROTOCOL_20260803.md"
MECHANICAL_INTERPRETATION = (
    ROOT / "reports/mmlu_redux_mechanical_scan_20260803/interpretation_addendum.json"
)
EXPECTED_HASHES = {
    "source": "70cc9ee184db4017b323bda03061f7c3d56e57ad1ab4b1a3415263fd664072b8",
    "audit_report": "8fc5fa57330b704faa48f7007f228a7ae3f44d02beaa30c1e96970ba9aa88cc6",
    "protocol": "826acbac44f08f8d0cdc611f22b38f6b974765cbbec9cd8343a5d6aea34bb5eb",
    "mechanical_interpretation": "d5d8957734d7e47186628ccd7d6e579d959b04efad6fd02ca79bb2b3bbaf9bcd",
}
ANSWER_HASHES = {
    "amazon__nova-pro-v1.jsonl": "75c8f1239ac93b248594799beea47f9642743db0b30b07c1fb929a60420186e7",
    "cohere__command-r-08-2024.jsonl": "a550b7dd005294267c769f860297b84dbcc9607bbc52fbbebd7918e71f4cf4be",
    "deepseek.jsonl": "fa7acdf241df1a01eee1eda1a00e645c605aee503b0416edd726d089527b6101",
    "google__gemini-2.5-flash.jsonl": "2bc96f33b908d22b4703f91e33c598eafa03b3be6a3516ca9c92fdd8fb400ec9",
    "meta-llama__llama-3.1-70b-instruct.jsonl": "c19b0936c1ea6723f2f7169a0793d622eb7a43a14bd816d90c9c221d83efa72a",
    "meta-llama__llama-3.1-8b-instruct.jsonl": "afc4ad5b9f76a08ee5929771880d35019e2b98055a30711200addf5500ccaf19",
    "meta-llama__llama-3.3-70b-instruct.jsonl": "2d9ee021748d2501754cac714faafb09b7159b419a6ef11eaded46c86e5edf44",
    "microsoft__phi-4.jsonl": "ca82caa157fd6816368e80bfd805b50943e5063d80108375c20215c4d6710a20",
    "mistralai__mistral-nemo.jsonl": "f024d64e3c14fa07614e930906715af54f8394bb50eaade17fc4dcdfe789c6a8",
    "mistralai__mistral-small-24b-instruct-2501.jsonl": "7d28319ac1b4b45bdfb80bfb786ce1c443c75e824043959321672b2ca28760bf",
    "openai__gpt-4.1-mini.jsonl": "ad595880ab90cbe09411c96eba97f6e533101ebf293d66ae3f37c1a6fba3bf42",
    "openai__gpt-4o-mini.jsonl": "7e122b072aba7874815f75c62203b628970ad003ed86776a1ab1b9ba358cdcd4",
    "openai__gpt-4o.jsonl": "9b274b186d8e60a03ece47b032823f0d79d3bc879c30152b91f340a103515ec9",
    "qwen__qwen-2.5-72b-instruct.jsonl": "c043efc588e2166a525e42f6093c7469aa3f08a7517d5d1126be5bcefa072465",
    "qwen__qwen-2.5-7b-instruct.jsonl": "85c50927156ca133b0e09cad0d72a9fc71bd75dcbffdd495451686ccac22b04c",
}
EXPECTED_ID_SET_SHA256 = "91325c9c67cb0a92ebf8832efbf5ee09730d47322493d29def9fe222799475b3"
VALID_LABELS = frozenset("ABCD")
EXPLICIT_DEFECTS = frozenset(
    {
        "wrong_groundtruth",
        "bad_question_clarity",
        "multiple_correct_answers",
        "no_correct_answer",
        "bad_options_clarity",
    }
)
GOLD_RELATED = frozenset(
    {"wrong_groundtruth", "multiple_correct_answers", "no_correct_answer"}
)
ALL_SOURCE_LABELS = EXPLICIT_DEFECTS | {"ok", "expert"}


class BaselineError(RuntimeError):
    pass


def stable_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sorted_id_sha256(values: set[str]) -> str:
    return sha256_bytes(("\n".join(sorted(values)) + "\n").encode("utf-8"))


def answer_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return normalized if normalized in VALID_LABELS else None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BaselineError(f"{path}: row {line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise BaselineError(f"{path}: row {line_number}: not a mapping")
            rows.append(row)
    return rows


def source_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for line_number, row in enumerate(rows, 1):
        item_id = row.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in result:
            raise BaselineError(f"source row {line_number}: invalid or duplicate ID")
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            raise BaselineError(f"source row {line_number}: invalid metadata")
        if metadata.get("error_type") not in ALL_SOURCE_LABELS:
            raise BaselineError(f"source row {line_number}: unknown truth label")
        if not isinstance(metadata.get("subject"), str) or not metadata["subject"]:
            raise BaselineError(f"source row {line_number}: invalid subject")
        if answer_label(row.get("gold")) is None:
            raise BaselineError(f"source row {line_number}: invalid gold")
        result[item_id] = row
    if len(result) != 1000 or sorted_id_sha256(set(result)) != EXPECTED_ID_SET_SHA256:
        raise BaselineError("source population mismatch")
    return result


def verify_bindings() -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, dict[str, Any]]], dict[str, Any]
]:
    paths = {
        "source": SOURCE,
        "audit_report": AUDIT_REPORT,
        "protocol": PROTOCOL,
        "mechanical_interpretation": MECHANICAL_INTERPRETATION,
    }
    for name, path in paths.items():
        if not path.is_file() or sha256_file(path) != EXPECTED_HASHES[name]:
            raise BaselineError(f"frozen binding mismatch: {name}")
    actual_answer_files = {path.name for path in ANSWERS.glob("*.jsonl")}
    if actual_answer_files != set(ANSWER_HASHES):
        raise BaselineError("answer-file set mismatch")
    source = source_index(load_jsonl(SOURCE))
    matrices: dict[str, dict[str, dict[str, Any]]] = {}
    for filename, expected_hash in sorted(ANSWER_HASHES.items()):
        path = ANSWERS / filename
        if sha256_file(path) != expected_hash:
            raise BaselineError(f"answer hash mismatch: {filename}")
        indexed: dict[str, dict[str, Any]] = {}
        for line_number, row in enumerate(load_jsonl(path), 1):
            item_id = row.get("id")
            if item_id not in source or item_id in indexed:
                raise BaselineError(f"{filename}: row {line_number}: invalid/duplicate ID")
            src = source[item_id]
            metadata = src["metadata"]
            if row.get("gold") != src.get("gold"):
                raise BaselineError(f"{filename}: gold mismatch: {item_id}")
            if row.get("error_type") != metadata["error_type"]:
                raise BaselineError(f"{filename}: truth mismatch: {item_id}")
            if row.get("subject") != metadata["subject"]:
                raise BaselineError(f"{filename}: subject mismatch: {item_id}")
            correct = answer_label(row.get("pred")) == answer_label(row.get("gold"))
            if bool(row.get("correct")) != correct:
                raise BaselineError(f"{filename}: correct flag mismatch: {item_id}")
            indexed[item_id] = row
        if set(indexed) != set(source):
            raise BaselineError(f"{filename}: incomplete ID set")
        matrices[filename] = indexed
    report = json.loads(AUDIT_REPORT.read_text(encoding="utf-8"))
    if report.get("summary", {}).get("items") != 1000:
        raise BaselineError("audit report population mismatch")
    return source, matrices, report


def score_items(
    source: dict[str, dict[str, Any]], matrices: dict[str, dict[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    scores = []
    for item_id in sorted(source):
        src = source[item_id]
        gold = answer_label(src["gold"])
        if gold is None:
            raise BaselineError(f"invalid source gold after validation: {item_id}")
        valid_counts: Counter[str] = Counter()
        abstentions = 0
        for filename in sorted(matrices):
            prediction = answer_label(matrices[filename][item_id].get("pred"))
            if prediction is None:
                abstentions += 1
            else:
                valid_counts[prediction] += 1
        non_gold = {
            label: valid_counts[label]
            for label in sorted(VALID_LABELS - {gold})
            if valid_counts[label]
        }
        maximum = max(non_gold.values(), default=0)
        maximizing = sorted(label for label, count in non_gold.items() if count == maximum)
        scores.append(
            {
                "item_id": item_id,
                "subject": src["metadata"]["subject"],
                "source_error_type": src["metadata"]["error_type"],
                "gold": gold,
                "model_count": len(matrices),
                "valid_vote_count": sum(valid_counts.values()),
                "abstention_count": abstentions,
                "gold_vote_count": valid_counts[gold],
                "non_gold_label_counts": non_gold,
                "max_same_non_gold_count": maximum,
                "maximizing_non_gold_labels": maximizing,
            }
        )
    return scores


def endpoint_sets(source: dict[str, dict[str, Any]]) -> dict[str, dict[str, set[str]]]:
    labels = {item_id: row["metadata"]["error_type"] for item_id, row in source.items()}
    definitions = {
        "legacy_non_ok_including_expert": (
            lambda value: value != "ok", lambda value: value == "ok"
        ),
        "strict_explicit_defect": (
            lambda value: value in EXPLICIT_DEFECTS, lambda value: value == "ok"
        ),
        "gold_related": (
            lambda value: value in GOLD_RELATED, lambda value: value == "ok"
        ),
        "wrong_groundtruth_only": (
            lambda value: value == "wrong_groundtruth", lambda value: value == "ok"
        ),
    }
    result = {}
    for name, (is_positive, is_negative) in definitions.items():
        positive = {item_id for item_id, label in labels.items() if is_positive(label)}
        negative = {item_id for item_id, label in labels.items() if is_negative(label)}
        excluded = set(source) - positive - negative
        if positive & negative or positive & excluded or negative & excluded:
            raise BaselineError(f"endpoint overlap: {name}")
        result[name] = {"positive": positive, "negative": negative, "excluded": excluded}
    return result


def safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def classification_metrics(
    candidates: set[str], endpoint: dict[str, set[str]]
) -> dict[str, Any]:
    positive = endpoint["positive"]
    negative = endpoint["negative"]
    evaluated = positive | negative
    selected = candidates & evaluated
    tp = len(selected & positive)
    fp = len(selected & negative)
    fn = len(positive - selected)
    tn = len(negative - selected)
    precision = safe_ratio(tp, tp + fp)
    recall = safe_ratio(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None and precision + recall:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "population": len(evaluated),
        "positives": len(positive),
        "negatives": len(negative),
        "excluded": len(endpoint["excluded"]),
        "candidate_count": len(selected),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": safe_ratio(tn, tn + fp),
        "false_positive_rate": safe_ratio(fp, fp + tn),
    }


def bench_candidates(report: dict[str, Any], source_ids: set[str]) -> set[str]:
    candidates = set()
    for violation in report.get("violations", []):
        item_id = violation.get("item_id")
        if item_id not in source_ids:
            raise BaselineError(f"audit finding references unknown item: {item_id}")
        if (
            violation.get("defect_scope") == "substantive"
            and violation.get("evidence_tier") == "review"
        ):
            candidates.add(item_id)
    return candidates


def random_expectation(candidate_count: int, endpoint_metrics: dict[str, Any]) -> dict[str, Any]:
    population = endpoint_metrics["population"]
    return {
        "matched_candidate_count": candidate_count,
        "expected_precision": safe_ratio(endpoint_metrics["positives"], population),
        "expected_recall": safe_ratio(candidate_count, population),
    }


def oracle_threshold(rows: dict[str, dict[str, Any]]) -> int:
    """Return the in-sample best-F1 threshold, breaking ties toward larger k."""
    return max(
        (int(threshold) for threshold in rows),
        key=lambda threshold: (
            rows[str(threshold)]["f1"]
            if rows[str(threshold)]["f1"] is not None else float("-inf"),
            threshold,
        ),
    )


def build_metrics(
    scores: list[dict[str, Any]], source: dict[str, dict[str, Any]], report: dict[str, Any]
) -> dict[str, Any]:
    endpoints = endpoint_sets(source)
    score_by_id = {row["item_id"]: row["max_same_non_gold_count"] for row in scores}
    bench = bench_candidates(report, set(source))
    bench_by_endpoint = {
        name: classification_metrics(bench, endpoint) for name, endpoint in endpoints.items()
    }
    legacy = bench_by_endpoint["legacy_non_ok_including_expert"]
    expected_legacy = {"tp": 206, "fp": 86, "fn": 164, "tn": 544}
    if {key: legacy[key] for key in expected_legacy} != expected_legacy:
        raise BaselineError(f"BenchAudit legacy confusion mismatch: {legacy}")

    curves: dict[str, dict[str, Any]] = {}
    for endpoint_name, endpoint in endpoints.items():
        rows = {}
        for threshold in range(1, 16):
            candidates = {item_id for item_id, score in score_by_id.items() if score >= threshold}
            measured = classification_metrics(candidates, endpoint)
            measured["random_same_count"] = random_expectation(
                measured["candidate_count"], measured
            )
            rows[str(threshold)] = measured
        best_threshold = oracle_threshold(rows)
        curves[endpoint_name] = {
            "thresholds": rows,
            "named_points": {"primary": 8, "strong": 12, "unanimous_panel": 15},
            "post_hoc_oracle_upper_bound": {
                "threshold": best_threshold,
                "metrics": rows[str(best_threshold)],
                "in_sample_only": True,
            },
        }

    primary_candidates = {item_id for item_id, score in score_by_id.items() if score >= 8}
    per_subject = {}
    subjects = sorted({row["metadata"]["subject"] for row in source.values()})
    for endpoint_name, endpoint in endpoints.items():
        per_subject[endpoint_name] = {}
        for subject in subjects:
            subject_ids = {
                item_id for item_id, row in source.items()
                if row["metadata"]["subject"] == subject
            }
            narrowed = {
                key: values & subject_ids for key, values in endpoint.items()
            }
            per_subject[endpoint_name][subject] = classification_metrics(
                primary_candidates, narrowed
            )
    mechanical = json.loads(MECHANICAL_INTERPRETATION.read_text(encoding="utf-8"))
    return {
        "schema_version": "mmlu-response-pattern-baseline-metrics-v1",
        "model_count": len(ANSWER_HASHES),
        "source_rows": len(source),
        "score_histogram": dict(sorted(Counter(
            str(row["max_same_non_gold_count"]) for row in scores
        ).items(), key=lambda pair: int(pair[0]))),
        "abstention_count_histogram": dict(sorted(Counter(
            str(row["abstention_count"]) for row in scores
        ).items(), key=lambda pair: int(pair[0]))),
        "benchcore": {
            "candidate_count": len(bench),
            "endpoints": bench_by_endpoint,
            "random_same_count": {
                name: random_expectation(values["candidate_count"], values)
                for name, values in bench_by_endpoint.items()
            },
        },
        "response_pattern": {"endpoints": curves},
        "primary_overlap_with_benchcore": {
            "both": sorted(primary_candidates & bench),
            "response_only": sorted(primary_candidates - bench),
            "benchcore_only": sorted(bench - primary_candidates),
            "neither_count": len(set(source) - primary_candidates - bench),
        },
        "per_subject_primary_k8": per_subject,
        "mechanical_t1_note": {
            "interpretation_sha256": EXPECTED_HASHES["mechanical_interpretation"],
            "confirmation_eligible_distinct_items": mechanical["confirmation_eligible"]["distinct_items"],
            "redux_ok_items": mechanical["confirmation_eligible"]["redux_ok_items"],
            "item_ids": mechanical["confirmation_eligible"]["item_ids"],
            "not_scored_as_a_complete_truth_source": True,
        },
    }


def fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def build_report(metrics: dict[str, Any]) -> str:
    lines = [
        "# MMLU-1000 offline response-pattern baseline",
        "",
        "Outcome: **BASELINE_COMPLETE**",
        "",
        "The response baseline flags an item when at least `k` of 15 recorded models "
        "emit the same valid non-gold option. Invalid/missing predictions abstain.",
        "",
        "## Legacy endpoint (non-`ok`, including `expert`)",
        "",
        "| System | Threshold | Candidates | P | R | F1 | Specificity | Incremental API cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    legacy_bench = metrics["benchcore"]["endpoints"]["legacy_non_ok_including_expert"]
    lines.append(
        f"| BenchAudit | review candidate | {legacy_bench['candidate_count']} | "
        f"{fmt(legacy_bench['precision'])} | {fmt(legacy_bench['recall'])} | "
        f"{fmt(legacy_bench['f1'])} | {fmt(legacy_bench['specificity'])} | historical paid run |"
    )
    legacy_curve = metrics["response_pattern"]["endpoints"]["legacy_non_ok_including_expert"]
    for label, threshold in (("primary", 8), ("strong", 12), ("unanimous", 15)):
        values = legacy_curve["thresholds"][str(threshold)]
        lines.append(
            f"| Response pattern ({label}) | ≥{threshold} | {values['candidate_count']} | "
            f"{fmt(values['precision'])} | {fmt(values['recall'])} | {fmt(values['f1'])} | "
            f"{fmt(values['specificity'])} | ¥0 incremental |"
        )
    oracle = legacy_curve["post_hoc_oracle_upper_bound"]
    values = oracle["metrics"]
    lines.append(
        f"| Response pattern (post-hoc upper bound) | ≥{oracle['threshold']} | "
        f"{values['candidate_count']} | {fmt(values['precision'])} | {fmt(values['recall'])} | "
        f"{fmt(values['f1'])} | {fmt(values['specificity'])} | ¥0 incremental |"
    )

    lines.extend([
        "",
        "## Strict explicit-defect endpoint (`expert` excluded)",
        "",
        "| System | Threshold | TP | FP | FN | TN | P | R | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    strict_bench = metrics["benchcore"]["endpoints"]["strict_explicit_defect"]
    lines.append(
        f"| BenchAudit | review candidate | {strict_bench['tp']} | {strict_bench['fp']} | "
        f"{strict_bench['fn']} | {strict_bench['tn']} | {fmt(strict_bench['precision'])} | "
        f"{fmt(strict_bench['recall'])} | {fmt(strict_bench['f1'])} |"
    )
    strict_curve = metrics["response_pattern"]["endpoints"]["strict_explicit_defect"]
    for label, threshold in (("primary", 8), ("strong", 12), ("unanimous", 15)):
        values = strict_curve["thresholds"][str(threshold)]
        lines.append(
            f"| Response pattern ({label}) | ≥{threshold} | {values['tp']} | {values['fp']} | "
            f"{values['fn']} | {values['tn']} | {fmt(values['precision'])} | "
            f"{fmt(values['recall'])} | {fmt(values['f1'])} |"
        )
    oracle = strict_curve["post_hoc_oracle_upper_bound"]
    values = oracle["metrics"]
    lines.append(
        f"| Response pattern (post-hoc upper bound) | ≥{oracle['threshold']} | {values['tp']} | "
        f"{values['fp']} | {values['fn']} | {values['tn']} | {fmt(values['precision'])} | "
        f"{fmt(values['recall'])} | {fmt(values['f1'])} |"
    )

    lines.extend([
        "",
        "## Endpoint summary at primary k≥8",
        "",
        "| Endpoint | Positives | Candidates | P | R | F1 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for endpoint_name in (
        "legacy_non_ok_including_expert", "strict_explicit_defect",
        "gold_related", "wrong_groundtruth_only",
    ):
        values = metrics["response_pattern"]["endpoints"][endpoint_name]["thresholds"]["8"]
        lines.append(
            f"| `{endpoint_name}` | {values['positives']} | {values['candidate_count']} | "
            f"{fmt(values['precision'])} | {fmt(values['recall'])} | {fmt(values['f1'])} |"
        )

    overlap = metrics["primary_overlap_with_benchcore"]
    mechanical = metrics["mechanical_t1_note"]
    lines.extend([
        "",
        "## Overlap and evidence boundary",
        "",
        f"At k≥8: both systems flag {len(overlap['both'])} items; response-pattern only "
        f"{len(overlap['response_only'])}; BenchAudit only {len(overlap['benchcore_only'])}.",
        "",
        f"Separately, the deterministic T1 scan confirmed {mechanical['confirmation_eligible_distinct_items']} "
        f"byte-identical duplicate-choice items, including {mechanical['redux_ok_items']} labelled `ok`. "
        "Those prove that the supervised labels are incomplete; a mechanically confirmed `ok` item must not "
        "be interpreted as a genuine detector false positive merely because Redux says `ok`.",
        "",
        "The response panel is not 15 independent experts, and this population was used during BenchAudit "
        "development. The comparison is an in-sample baseline, not a generalization result. The post-hoc "
        "best threshold is an optimistic upper bound and is not the primary result.",
        "",
    ])
    return "\n".join(lines)


def build_receipt(
    scores_bytes: bytes, metrics_bytes: bytes, report_bytes: bytes, metrics: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": "mmlu-response-pattern-baseline-receipt-v1",
        "outcome": "BASELINE_COMPLETE",
        "bindings": {
            "source_sha256": EXPECTED_HASHES["source"],
            "audit_report_sha256": EXPECTED_HASHES["audit_report"],
            "protocol_sha256": EXPECTED_HASHES["protocol"],
            "mechanical_interpretation_sha256": EXPECTED_HASHES["mechanical_interpretation"],
            "answer_file_sha256": dict(sorted(ANSWER_HASHES.items())),
            "scanner_sha256": sha256_file(Path(__file__)),
        },
        "population": {
            "items": 1000,
            "models": 15,
            "sorted_id_sha256": EXPECTED_ID_SET_SHA256,
        },
        "execution": {
            "incremental_api_attempts": 0,
            "network_attempts": 0,
            "llm_used": False,
            "production_activation": False,
        },
        "primary_threshold": 8,
        "legacy_benchcore_confusion_reproduced": True,
        "stable_summary": {
            "score_histogram": metrics["score_histogram"],
            "benchcore_legacy": metrics["benchcore"]["endpoints"]["legacy_non_ok_including_expert"],
            "response_primary_legacy": metrics["response_pattern"]["endpoints"]
            ["legacy_non_ok_including_expert"]["thresholds"]["8"],
            "response_primary_strict": metrics["response_pattern"]["endpoints"]
            ["strict_explicit_defect"]["thresholds"]["8"],
        },
        "outputs": {
            "scores_sha256": sha256_bytes(scores_bytes),
            "metrics_sha256": sha256_bytes(metrics_bytes),
            "report_sha256": sha256_bytes(report_bytes),
        },
    }


def ensure_empty(output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise BaselineError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)


def run(output: Path) -> dict[str, Any]:
    ensure_empty(output)
    started = dt.datetime.now().astimezone()
    monotonic = time.monotonic()
    raw: dict[str, Any] = {
        "schema_version": "mmlu-response-pattern-baseline-raw-v1",
        "started_at": started.isoformat(),
        "pid": os.getpid(),
        "output_dir": str(output.resolve()),
        "python": platform.python_version(),
    }
    try:
        source, matrices, audit_report = verify_bindings()
        scores = score_items(source, matrices)
        metrics = build_metrics(scores, source, audit_report)
        scores_bytes = b"".join(stable_bytes(row) for row in scores)
        metrics_bytes = stable_bytes(metrics)
        report_bytes = build_report(metrics).encode("utf-8")
        receipt = build_receipt(scores_bytes, metrics_bytes, report_bytes, metrics)
        receipt_bytes = stable_bytes(receipt)
        (output / "scores.jsonl").write_bytes(scores_bytes)
        (output / "metrics.json").write_bytes(metrics_bytes)
        (output / "REPORT.md").write_bytes(report_bytes)
        (output / "receipt.json").write_bytes(receipt_bytes)
        raw.update({"outcome": "BASELINE_COMPLETE", "receipt_sha256": sha256_bytes(receipt_bytes)})
    except Exception as exc:
        raw.update({"outcome": "BASELINE_INCOMPLETE", "error": f"{type(exc).__name__}: {exc}"})
        raise
    finally:
        raw.update({
            "ended_at": dt.datetime.now().astimezone().isoformat(),
            "elapsed_seconds": round(time.monotonic() - monotonic, 6),
        })
        (output / "raw_run.json").write_bytes(stable_bytes(raw))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = run(args.out_dir)
    except Exception as exc:
        print(f"BASELINE_INCOMPLETE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt["stable_summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
