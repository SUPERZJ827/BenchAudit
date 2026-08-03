#!/usr/bin/env python3
"""Run the frozen deterministic construction-defect scan over MMLU-Redux."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(
    "/home/zhoujun/llmdata/datasets/mmlu_redux/"
    "mmlu_redux_all_5700_finegrained.jsonl"
)
INVENTORY = ROOT / "reports/mmlu_holdout_contamination_inventory_20260803/inventory.json"
AVAILABILITY = ROOT / "reports/mmlu_cache_binding_a0_20260803/availability.json"
PROTOCOL = ROOT / "docs/research/MMLU_REDUX_MECHANICAL_FULL_SCAN_PROTOCOL_20260803.md"
CLARIFICATION = ROOT / (
    "docs/research/MMLU_REDUX_MECHANICAL_FULL_SCAN_PROTOCOL_CLARIFICATION_20260803.md"
)
PRIOR_RECEIPT = ROOT / "reports/mmlu_redux_ok_mechanical_20260803/receipt.json"

EXPECTED_HASHES = {
    "dataset": "0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4",
    "inventory": "a416ea4a2e3dd41865d6f0f12db46df67db91b324a7a2b6273fa66c21b5d0f10",
    "availability": "15b777f4049799ed8538d00bbfb11a7847b9fc32d0c48ece187307308ac6f9e1",
    "protocol": "b974fef9962653c99f4787c820258d45d7c2cc0f32225539e0216fcde4e08bc4",
    "clarification": "42cebe47d7bc17b85715b032b26e9de25c4bdd5730e05df5ce15bc7a1e22ba77",
    "prior_receipt": "2634748bb9cbbf67efeac9bf9cd94166709c0ef390c8546052b4063f67a92365",
}
EXPECTED_DATASET_BYTES = 4_505_750
EXPECTED_ROWS = 5_700
EXPECTED_USED_COUNT = 1_087
EXPECTED_UNUSED_COUNT = 4_613
EXPECTED_USED_SHA256 = "f06faeb336ef5241d76ef2342a2810d3bf460671bcfdb9d2b273a4033fdd077a"
EXPECTED_UNUSED_SHA256 = "28915b353b27ef6f1a71283540830fd70dd4aa0ed87b7d259fa47359e477ebff"
EXPECTED_PYTHON = "3.10.12"
EXPECTED_UNICODE = "13.0.0"
KNOWN_POSITIVE = "mmlu-redux-public_relations-36"
EXPLICIT_DEFECTS = frozenset(
    {
        "wrong_groundtruth",
        "bad_question_clarity",
        "multiple_correct_answers",
        "no_correct_answer",
        "bad_options_clarity",
    }
)
ALLOWED_LABELS = EXPLICIT_DEFECTS | {"ok", "expert"}
TIER_ORDER = {"T1": 1, "T2": 2, "T3": 3, None: 9}


class ScanError(RuntimeError):
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


def sorted_id_sha256(values: set[str] | list[str]) -> str:
    return sha256_bytes(("\n".join(sorted(values)) + "\n").encode("utf-8"))


def normalize_t1(value: str) -> str:
    return value


def normalize_t2(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    parts: list[str] = []
    in_space = False
    for character in text:
        if character.isspace():
            if parts and not in_space:
                parts.append(" ")
            in_space = True
        else:
            parts.append(character)
            in_space = False
    return "".join(parts).strip(" ")


def normalize_t3(value: str) -> str:
    text = normalize_t2(value)
    while text:
        before = text
        text = text.strip(" ")
        start = 0
        end = len(text)
        while start < end and unicodedata.category(text[start]).startswith("P"):
            start += 1
        while end > start and unicodedata.category(text[end - 1]).startswith("P"):
            end -= 1
        text = text[start:end].strip(" ")
        if text == before:
            break
    return text


NORMALIZERS = {"T1": normalize_t1, "T2": normalize_t2, "T3": normalize_t3}


def duplicate_groups(choices: list[str], tier: str) -> list[dict[str, Any]]:
    normalized: dict[bytes | str, list[int]] = defaultdict(list)
    rendered: dict[bytes | str, str] = {}
    for index, choice in enumerate(choices):
        value = NORMALIZERS[tier](choice)
        if value == "":
            continue
        key: bytes | str = value.encode("utf-8") if tier == "T1" else value
        normalized[key].append(index)
        rendered[key] = value
    groups = []
    for key, indices in normalized.items():
        if len(indices) < 2:
            continue
        value = rendered[key]
        groups.append(
            {
                "indices": indices,
                "normalized_value": value,
                "normalized_value_sha256": sha256_bytes(value.encode("utf-8")),
                "raw_choices": [choices[index] for index in indices],
            }
        )
    return sorted(groups, key=lambda group: group["indices"])


def r1_findings(row: dict[str, Any], common: dict[str, Any]) -> list[dict[str, Any]]:
    choices = row["choices"]
    result = []
    for tier in ("T1", "T2", "T3"):
        groups = duplicate_groups(choices, tier)
        if groups:
            result.append(
                {
                    **common,
                    "rule": "R1_duplicate_choices",
                    "tier": tier,
                    "implicated_indices": sorted(
                        {index for group in groups for index in group["indices"]}
                    ),
                    "evidence": {"duplicate_groups": groups},
                }
            )
    return result


def r2_finding(row: dict[str, Any], common: dict[str, Any]) -> dict[str, Any] | None:
    choices = row["choices"]
    if "gold" not in row:
        reason = "gold_missing"
        raw_gold: Any = None
        normalized = None
        index = None
    else:
        raw_gold = row["gold"]
        if not isinstance(raw_gold, str):
            reason = "gold_non_string"
            normalized = None
            index = None
        else:
            normalized = raw_gold.strip().upper()
            labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[: len(choices)]
            if not normalized:
                reason = "gold_empty"
                index = None
            elif normalized not in labels:
                reason = "gold_outside_choice_domain"
                index = None
            else:
                index = labels.index(normalized)
                if index >= len(choices):
                    reason = "gold_index_out_of_range"
                elif choices[index].strip() == "":
                    reason = "gold_points_to_empty_choice"
                else:
                    return None
    implicated = [] if index is None or index >= len(choices) else [index]
    return {
        **common,
        "rule": "R2_unresolvable_declared_gold",
        "tier": None,
        "implicated_indices": implicated,
        "evidence": {
            "reason": reason,
            "raw_gold": raw_gold,
            "normalized_gold_label": normalized,
            "choice_domain_size": len(choices),
            "selected_index": index,
            "raw_choices": [choices[value] for value in implicated],
        },
    }


def r3_finding(row: dict[str, Any], common: dict[str, Any]) -> dict[str, Any] | None:
    indices = [index for index, choice in enumerate(row["choices"]) if choice.strip() == ""]
    if not indices:
        return None
    return {
        **common,
        "rule": "R3_empty_choice",
        "tier": None,
        "implicated_indices": indices,
        "evidence": {
            "raw_choices": [row["choices"][index] for index in indices],
        },
    }


def validate_row(row: Any, line_number: int, seen: set[str]) -> None:
    if not isinstance(row, dict):
        raise ScanError(f"row {line_number}: row_not_mapping")
    required = {"id", "question", "choices", "evaluator", "metadata"}
    missing = sorted(required - set(row))
    if missing:
        raise ScanError(f"row {line_number}: missing_fields:{','.join(missing)}")
    if not isinstance(row["id"], str) or not row["id"]:
        raise ScanError(f"row {line_number}: invalid_id")
    if row["id"] in seen:
        raise ScanError(f"row {line_number}: duplicate_id:{row['id']}")
    seen.add(row["id"])
    if not isinstance(row["question"], str):
        raise ScanError(f"row {line_number}: question_not_string")
    choices = row["choices"]
    if not isinstance(choices, list) or len(choices) != 4:
        raise ScanError(f"row {line_number}: choices_not_four_item_list")
    if any(not isinstance(choice, str) for choice in choices):
        raise ScanError(f"row {line_number}: choice_not_string")
    if row["evaluator"] != {"type": "multiple_choice"}:
        raise ScanError(f"row {line_number}: evaluator_schema_drift")
    metadata = row["metadata"]
    if not isinstance(metadata, dict):
        raise ScanError(f"row {line_number}: metadata_not_mapping")
    if not isinstance(metadata.get("subject"), str) or not metadata["subject"]:
        raise ScanError(f"row {line_number}: invalid_subject")
    if metadata.get("error_type") not in ALLOWED_LABELS:
        raise ScanError(f"row {line_number}: unknown_redux_label:{metadata.get('error_type')!r}")


def label_class(label: str) -> str:
    if label == "ok":
        return "ok"
    if label == "expert":
        return "expert_abstention"
    if label in EXPLICIT_DEFECTS:
        return "explicit_defect"
    raise ScanError(f"unknown label after validation: {label}")


def load_bindings() -> tuple[list[dict[str, Any]], set[str], set[str]]:
    paths = {
        "dataset": DATASET,
        "inventory": INVENTORY,
        "availability": AVAILABILITY,
        "protocol": PROTOCOL,
        "clarification": CLARIFICATION,
        "prior_receipt": PRIOR_RECEIPT,
    }
    for name, path in paths.items():
        if not path.is_file():
            raise ScanError(f"missing frozen input: {name}: {path}")
        actual = sha256_file(path)
        if actual != EXPECTED_HASHES[name]:
            raise ScanError(f"frozen hash mismatch: {name}: {actual}")
    if DATASET.stat().st_size != EXPECTED_DATASET_BYTES:
        raise ScanError("dataset byte-size mismatch")
    if platform.python_version() != EXPECTED_PYTHON:
        raise ScanError(f"python version mismatch: {platform.python_version()}")
    if unicodedata.unidata_version != EXPECTED_UNICODE:
        raise ScanError(f"Unicode database mismatch: {unicodedata.unidata_version}")

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    availability = json.loads(AVAILABILITY.read_text(encoding="utf-8"))
    used = {entry["item_id"] for entry in inventory.get("exposures", [])}
    unused = set(inventory.get("candidate_ids", []))
    if len(used) != EXPECTED_USED_COUNT or sorted_id_sha256(used) != EXPECTED_USED_SHA256:
        raise ScanError("recorded-development partition mismatch")
    if len(unused) != EXPECTED_UNUSED_COUNT or sorted_id_sha256(unused) != EXPECTED_UNUSED_SHA256:
        raise ScanError("remaining partition mismatch")
    if used & unused:
        raise ScanError("partition overlap")
    if availability.get("counts", {}).get("upper_bound_union_items") != EXPECTED_USED_COUNT:
        raise ScanError("A0 forward-union count mismatch")
    if availability.get("upper_bound_union_ids_sha256") != EXPECTED_USED_SHA256:
        raise ScanError("A0 forward-union hash mismatch")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with DATASET.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ScanError(f"row {line_number}: invalid_json:{exc.msg}") from exc
            validate_row(row, line_number, seen)
            rows.append(row)
    if len(rows) != EXPECTED_ROWS:
        raise ScanError(f"row-count mismatch: {len(rows)}")
    if seen != used | unused:
        raise ScanError("dataset IDs do not equal frozen partition union")
    return rows, used, unused


def scan_rows(
    rows: list[dict[str, Any]], used: set[str], unused: set[str]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in rows:
        item_id = row["id"]
        partition = "development_1087" if item_id in used else "remaining_4613"
        if partition == "remaining_4613" and item_id not in unused:
            raise ScanError(f"item outside frozen partitions: {item_id}")
        input_fields = {
            "choices": row["choices"],
            "evaluator": row["evaluator"],
            "gold_present": "gold" in row,
            "gold": row.get("gold"),
        }
        common = {
            "item_id": item_id,
            "subject": row["metadata"]["subject"],
            "redux_error_type": row["metadata"]["error_type"],
            "redux_label_class": label_class(row["metadata"]["error_type"]),
            "partition": partition,
            "rule_input_fields_sha256": sha256_bytes(stable_bytes(input_fields)),
        }
        findings.extend(r1_findings(row, common))
        gold_finding = r2_finding(row, common)
        if gold_finding is not None:
            findings.append(gold_finding)
        empty_finding = r3_finding(row, common)
        if empty_finding is not None:
            findings.append(empty_finding)
    findings.sort(key=lambda finding: (
        finding["item_id"], finding["rule"], TIER_ORDER[finding["tier"]]
    ))
    return findings


def item_sets(findings: list[dict[str, Any]]) -> dict[str, set[str]]:
    result = {
        "R1_T1": set(), "R1_T2": set(), "R1_T3": set(),
        "R2": set(), "R3": set(),
    }
    for finding in findings:
        if finding["rule"] == "R1_duplicate_choices":
            result[f"R1_{finding['tier']}"] .add(finding["item_id"])
        elif finding["rule"] == "R2_unresolvable_declared_gold":
            result["R2"].add(finding["item_id"])
        elif finding["rule"] == "R3_empty_choice":
            result["R3"].add(finding["item_id"])
        else:
            raise ScanError(f"unknown finding rule: {finding['rule']}")
    if not result["R1_T1"] <= result["R1_T2"] <= result["R1_T3"]:
        raise ScanError("R1 tiers are not cumulative")
    return result


def count_breakdown(ids: set[str], rows_by_id: dict[str, dict[str, Any]]) -> dict[str, int]:
    labels = Counter(label_class(rows_by_id[item_id]["metadata"]["error_type"]) for item_id in ids)
    return {
        "total": len(ids),
        "ok": labels["ok"],
        "explicit_defect": labels["explicit_defect"],
        "expert_abstention": labels["expert_abstention"],
    }


def summarize(
    rows: list[dict[str, Any]], findings: list[dict[str, Any]], used: set[str], unused: set[str]
) -> dict[str, Any]:
    by_id = {row["id"]: row for row in rows}
    sets = item_sets(findings)
    primary = {
        name: count_breakdown(ids, by_id) for name, ids in sets.items()
    }
    increments = {
        "T1": count_breakdown(sets["R1_T1"], by_id),
        "T2_only": count_breakdown(sets["R1_T2"] - sets["R1_T1"], by_id),
        "T3_only": count_breakdown(sets["R1_T3"] - sets["R1_T2"], by_id),
    }
    union = sets["R1_T3"] | sets["R2"] | sets["R3"]
    overlaps = Counter()
    for item_id in union:
        active = []
        if item_id in sets["R1_T3"]:
            active.append("R1")
        if item_id in sets["R2"]:
            active.append("R2")
        if item_id in sets["R3"]:
            active.append("R3")
        overlaps["+".join(active)] += 1
    partitions = {}
    for name, population in (("development_1087", used), ("remaining_4613", unused)):
        partitions[name] = {
            "population": len(population),
            "R1_T1": count_breakdown(sets["R1_T1"] & population, by_id),
            "R1_T2": count_breakdown(sets["R1_T2"] & population, by_id),
            "R1_T3": count_breakdown(sets["R1_T3"] & population, by_id),
            "R2": count_breakdown(sets["R2"] & population, by_id),
            "R3": count_breakdown(sets["R3"] & population, by_id),
            "union": count_breakdown(union & population, by_id),
        }
    known = {
        finding["tier"] for finding in findings
        if finding["item_id"] == KNOWN_POSITIVE
        and finding["rule"] == "R1_duplicate_choices"
    }
    known_row = by_id.get(KNOWN_POSITIVE)
    if known != {"T1", "T2", "T3"}:
        raise ScanError(f"known R1 positive control failed: {sorted(known)}")
    if known_row is None or known_row["metadata"]["error_type"] != "ok" or KNOWN_POSITIVE not in used:
        raise ScanError("known R1 positive control binding failed")
    label_counts = Counter(row["metadata"]["error_type"] for row in rows)
    return {
        "source_rows": len(rows),
        "finding_records": len(findings),
        "redux_error_type_counts": dict(sorted(label_counts.items())),
        "primary_counts": primary,
        "r1_disjoint_increment_counts": increments,
        "distinct_union": count_breakdown(union, by_id),
        "rule_overlap_distinct_item_counts": dict(sorted(overlaps.items())),
        "partitions": partitions,
        "known_positive_control": {
            "item_id": KNOWN_POSITIVE,
            "matched_tiers": ["T1", "T2", "T3"],
            "redux_error_type": "ok",
            "partition": "development_1087",
        },
    }


def markdown_table_row(name: str, tier: str, values: dict[str, int]) -> str:
    return (
        f"| {name} | {tier} | {values['total']} | {values['ok']} | "
        f"{values['explicit_defect']} | {values['expert_abstention']} |"
    )


def build_report(summary: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    counts = summary["primary_counts"]
    lines = [
        "# MMLU-Redux deterministic mechanical-defect full scan",
        "",
        "Outcome: **SCAN_COMPLETE**",
        "",
        "## Main table",
        "",
        "| Rule | Tier | Distinct items | Redux `ok` | Explicit defect | `expert` abstention |",
        "|---|---|---:|---:|---:|---:|",
        markdown_table_row("R1 duplicate choices", "T1", counts["R1_T1"]),
        markdown_table_row("R1 duplicate choices", "T2", counts["R1_T2"]),
        markdown_table_row("R1 duplicate choices", "T3", counts["R1_T3"]),
        markdown_table_row("R2 unresolvable gold", "—", counts["R2"]),
        markdown_table_row("R3 empty choice", "—", counts["R3"]),
        "",
        "R1 tiers are cumulative. Disjoint increments:",
        "",
        "| Increment | Distinct items | Redux `ok` | Explicit defect | `expert` abstention |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in ("T1", "T2_only", "T3_only"):
        values = summary["r1_disjoint_increment_counts"][name]
        lines.append(
            f"| {name} | {values['total']} | {values['ok']} | "
            f"{values['explicit_defect']} | {values['expert_abstention']} |"
        )
    union = summary["distinct_union"]
    lines.extend([
        "",
        "## Distinct-item union",
        "",
        f"The R1(T3) ∪ R2 ∪ R3 union contains **{union['total']}** distinct items: "
        f"{union['ok']} Redux `ok`, {union['explicit_defect']} explicit defect, and "
        f"{union['expert_abstention']} `expert` abstention.",
        "",
        "Rule-overlap counts: `" + json.dumps(
            summary["rule_overlap_distinct_item_counts"], sort_keys=True
        ) + "`.",
        "",
        "## Frozen partitions",
        "",
        "| Partition | Population | R1 T1 | R1 T2 | R1 T3 | R2 | R3 | Union |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for name in ("development_1087", "remaining_4613"):
        part = summary["partitions"][name]
        lines.append(
            f"| {name} | {part['population']} | {part['R1_T1']['total']} | "
            f"{part['R1_T2']['total']} | {part['R1_T3']['total']} | "
            f"{part['R2']['total']} | {part['R3']['total']} | {part['union']['total']} |"
        )
    ok_findings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        if finding["redux_error_type"] == "ok":
            ok_findings[finding["item_id"]].append(finding)
    lines.extend(["", "## Itemized Redux-`ok` findings", ""])
    if not ok_findings:
        lines.append("No Redux-`ok` item triggered a frozen rule.")
    for item_id in sorted(ok_findings):
        group = ok_findings[item_id]
        lines.append(f"### `{item_id}`")
        lines.append("")
        lines.append(f"- Subject: `{group[0]['subject']}`")
        lines.append(f"- Partition: `{group[0]['partition']}`")
        for finding in group:
            label = finding["rule"] + (f"/{finding['tier']}" if finding["tier"] else "")
            lines.append(f"- `{label}`: indices `{finding['implicated_indices']}`")
            raw = finding["evidence"].get("raw_choices")
            if raw is None and finding["rule"] == "R1_duplicate_choices":
                raw = [
                    choice
                    for duplicate in finding["evidence"]["duplicate_groups"]
                    for choice in duplicate["raw_choices"]
                ]
            lines.append(
                "  - Raw implicated choices: `" +
                json.dumps(raw, ensure_ascii=False, separators=(",", ":")) + "`"
            )
        lines.append("")
    lines.extend([
        "## Claim boundary",
        "",
        "This scan covers only duplicate choices, unresolvable declared labels, and empty choices. "
        "It does not estimate the total MMLU-Redux defect rate, establish score impact, or show "
        "that human annotation quality is poor. R1 was partially informed by one previously known "
        "development-subset positive; R2 and R3 were declared unrun before freezing.",
        "",
    ])
    return "\n".join(lines)


def build_receipt(
    summary: dict[str, Any], findings_bytes: bytes, report_bytes: bytes
) -> dict[str, Any]:
    return {
        "schema_version": "mmlu-redux-mechanical-full-scan-receipt-v1",
        "outcome": "SCAN_COMPLETE",
        "bindings": {
            "dataset": {
                "path": str(DATASET),
                "sha256": EXPECTED_HASHES["dataset"],
                "bytes": EXPECTED_DATASET_BYTES,
                "rows": EXPECTED_ROWS,
            },
            "inventory_sha256": EXPECTED_HASHES["inventory"],
            "availability_sha256": EXPECTED_HASHES["availability"],
            "protocol_sha256": EXPECTED_HASHES["protocol"],
            "clarification_sha256": EXPECTED_HASHES["clarification"],
            "prior_r1_receipt_sha256": EXPECTED_HASHES["prior_receipt"],
            "scanner_sha256": sha256_file(Path(__file__)),
        },
        "environment": {
            "python": platform.python_version(),
            "unicode_database": unicodedata.unidata_version,
        },
        "partitions": {
            "development_1087": {
                "count": EXPECTED_USED_COUNT, "sorted_id_sha256": EXPECTED_USED_SHA256,
            },
            "remaining_4613": {
                "count": EXPECTED_UNUSED_COUNT, "sorted_id_sha256": EXPECTED_UNUSED_SHA256,
            },
        },
        "rule_versions": {
            "R1": "duplicate-choice-tiers-v1",
            "R2": "mmlu-label-domain-v1",
            "R3": "unicode-whitespace-empty-choice-v1",
        },
        "prior_knowledge": {
            "r1_rule_definition_partially_informed": True,
            "r1_known_positive_count_before_freeze": 1,
            "r2_previously_run": False,
            "r3_previously_run": False,
        },
        "execution": {
            "api_attempts": 0,
            "network_attempts": 0,
            "llm_used": False,
            "thresholds_used": False,
            "production_activation": False,
            "rows_validated": EXPECTED_ROWS,
            "rows_scanned_by_every_rule": EXPECTED_ROWS,
        },
        "summary": summary,
        "outputs": {
            "findings_sha256": sha256_bytes(findings_bytes),
            "report_sha256": sha256_bytes(report_bytes),
        },
    }


def ensure_empty_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ScanError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)


def run(output_dir: Path) -> dict[str, Any]:
    ensure_empty_output_dir(output_dir)
    started_at = dt.datetime.now().astimezone()
    start = time.monotonic()
    raw: dict[str, Any] = {
        "schema_version": "mmlu-redux-mechanical-full-scan-raw-run-v1",
        "started_at": started_at.isoformat(),
        "pid": os.getpid(),
        "output_dir": str(output_dir.resolve()),
        "dataset_path": str(DATASET),
    }
    try:
        rows, used, unused = load_bindings()
        findings = scan_rows(rows, used, unused)
        summary = summarize(rows, findings, used, unused)
        findings_bytes = b"".join(stable_bytes(finding) for finding in findings)
        report_bytes = build_report(summary, findings).encode("utf-8")
        receipt = build_receipt(summary, findings_bytes, report_bytes)
        receipt_bytes = stable_bytes(receipt)
        (output_dir / "findings.jsonl").write_bytes(findings_bytes)
        (output_dir / "REPORT.md").write_bytes(report_bytes)
        (output_dir / "receipt.json").write_bytes(receipt_bytes)
        raw.update(
            {
                "outcome": "SCAN_COMPLETE",
                "stable_receipt_sha256": sha256_bytes(receipt_bytes),
            }
        )
    except Exception as exc:
        raw.update({"outcome": "SCAN_INCOMPLETE", "error": f"{type(exc).__name__}: {exc}"})
        raise
    finally:
        ended_at = dt.datetime.now().astimezone()
        raw.update(
            {
                "ended_at": ended_at.isoformat(),
                "elapsed_seconds": round(time.monotonic() - start, 6),
            }
        )
        (output_dir / "raw_run.json").write_bytes(stable_bytes(raw))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = run(args.out_dir)
    except Exception as exc:
        print(f"SCAN_INCOMPLETE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "outcome": receipt["outcome"],
        "distinct_union": receipt["summary"]["distinct_union"],
        "primary_counts": receipt["summary"]["primary_counts"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
