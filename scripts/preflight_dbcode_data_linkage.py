#!/usr/bin/env python3
"""Aggregate-only DBCode data-linkage preflight.

The scanner reads schema keys and allowlisted identity/status values, but never
emits task text, model code, reference code, traces, patches, or raw item IDs.
It executes no benchmark code and makes no network/API calls.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = (
    REPO / "docs/experiments/DBCODE_DATA_LINKAGE_PREFLIGHT_PROTOCOL_20260730.md"
)
EXPECTED_PROTOCOL_SHA256 = (
    "95f215b6b1e6814d37b5047011e37bc02a9cf45eb6d421247a102f81d4da3fd4"
)
SCHEMA_VERSION = "dbcode-data-linkage-preflight-v1-20260730"
FAMILIES = (
    "SQLite_Function_Code_Generation",
    "PostgreSQL_Function_Code_Generation",
)

IDENTITY_ALIASES = (
    "item_id",
    "problem_id",
    "task_id",
    "sample_id",
    "case_id",
    "id",
    "function_name",
    "function",
    "name",
)
MODEL_ALIASES = ("model", "model_id", "model_name", "generator", "agent")
VARIANT_ALIASES = (
    "variant",
    "dependency_mode",
    "mode",
    "setting",
    "run_type",
)
TASK_ALIASES = (
    "task",
    "question",
    "problem",
    "prompt",
    "instruction",
    "description",
)
REFERENCE_ALIASES = (
    "reference",
    "reference_answer",
    "reference_code",
    "gold",
    "gold_code",
    "canonical_solution",
    "expected",
)
CANDIDATE_ALIASES = (
    "candidate",
    "candidate_code",
    "generated_code",
    "generation",
    "output",
    "model_output",
    "prediction",
    "response",
    "answer",
    "code",
)
STATUS_ALIASES = (
    "score",
    "status",
    "passed",
    "pass",
    "result",
    "verdict",
    "reward",
)

TRACE_BEFORE_DATE_RE = re.compile(
    r"(?:^|_)trajectory_(?P<identity>.+?)_"
    r"(?P<date>\d{8})_(?P<time>\d{6})\.[^.]+$",
    re.IGNORECASE,
)
TRACE_AFTER_DATE_RE = re.compile(
    r"(?:^|_)(?P<identity>[^_/]+)_"
    r"(?P<date>\d{8})_(?P<time>\d{6})_trajectory\.[^.]+$",
    re.IGNORECASE,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text)).strip("_")


def normalize_identity(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    text = " ".join(text.split())
    return text or None


def _normalized_record(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        normalized = normalize_key(key)
        if normalized and normalized not in result:
            result[normalized] = item
    return result


def _first_value(
    record: Mapping[str, Any],
    aliases: Iterable[str],
) -> tuple[str | None, Any]:
    for alias in aliases:
        if alias in record:
            return alias, record[alias]
    return None, None


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _has_any(record: Mapping[str, Any], aliases: Iterable[str]) -> bool:
    return any(alias in record and _present(record[alias]) for alias in aliases)


@dataclass(frozen=True)
class Record:
    identity: str
    model: str
    variant: str
    has_task: bool
    has_reference: bool
    has_candidate: bool
    has_status: bool


@dataclass
class ParsedFile:
    records: list[Record]
    key_counts: Counter[str]
    reasons: Counter[str]
    identity_conflicts: int = 0


def _record_from_mapping(
    raw: Mapping[str, Any],
    *,
    mapping_identity: str | None = None,
) -> tuple[Record | None, bool, Counter[str]]:
    record = _normalized_record(raw)
    # Count schema keys only. Passing the mapping itself to Counter would use
    # raw field values as counts and retain task/code text in diagnostics.
    key_counts: Counter[str] = Counter(record.keys())
    _, explicit_raw = _first_value(record, IDENTITY_ALIASES)
    explicit = normalize_identity(explicit_raw)
    mapped = normalize_identity(mapping_identity)
    conflict = bool(explicit and mapped and explicit != mapped)
    identity = explicit or mapped
    if not identity or conflict:
        return None, conflict, key_counts
    _, model_raw = _first_value(record, MODEL_ALIASES)
    _, variant_raw = _first_value(record, VARIANT_ALIASES)
    return (
        Record(
            identity=identity,
            model=normalize_identity(model_raw) or "",
            variant=normalize_identity(variant_raw) or "",
            has_task=_has_any(record, TASK_ALIASES),
            has_reference=_has_any(record, REFERENCE_ALIASES),
            has_candidate=_has_any(record, CANDIDATE_ALIASES),
            has_status=_has_any(record, STATUS_ALIASES),
        ),
        conflict,
        key_counts,
    )


def parse_json_file(path: Path) -> ParsedFile:
    reasons: Counter[str] = Counter()
    key_counts: Counter[str] = Counter()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ParsedFile([], key_counts, Counter({"malformed_json": 1}))

    raw_records: list[tuple[str | None, Mapping[str, Any]]] = []
    if isinstance(value, list):
        if not all(isinstance(row, dict) for row in value):
            return ParsedFile(
                [], key_counts, Counter({"non_object_list_record": 1})
            )
        raw_records = [(None, row) for row in value]
    elif isinstance(value, dict):
        list_fields = [
            item
            for item in value.values()
            if isinstance(item, list)
            and all(isinstance(row, dict) for row in item)
        ]
        if len(list_fields) == 1:
            raw_records = [(None, row) for row in list_fields[0]]
        elif len(list_fields) > 1:
            return ParsedFile(
                [],
                key_counts,
                Counter({"record_container_not_identifiable": 1}),
            )
        elif value and all(isinstance(item, dict) for item in value.values()):
            raw_records = [
                (str(identity), row) for identity, row in value.items()
            ]
        else:
            return ParsedFile(
                [],
                key_counts,
                Counter({"record_container_not_identifiable": 1}),
            )
    else:
        return ParsedFile(
            [], key_counts, Counter({"record_container_not_identifiable": 1})
        )

    records: list[Record] = []
    conflicts = 0
    for mapping_identity, raw in raw_records:
        record, conflict, keys = _record_from_mapping(
            raw, mapping_identity=mapping_identity
        )
        key_counts.update(keys)
        if conflict:
            conflicts += 1
            reasons["identity_conflict"] += 1
        elif record is None:
            reasons["record_id_not_identifiable"] += 1
        else:
            records.append(record)
    if not raw_records:
        reasons["empty_record_container"] += 1
    return ParsedFile(records, key_counts, reasons, conflicts)


def parse_csv_file(path: Path) -> ParsedFile:
    reasons: Counter[str] = Counter()
    key_counts: Counter[str] = Counter()
    records: list[Record] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                return ParsedFile(
                    [], key_counts, Counter({"missing_csv_header": 1})
                )
            normalized_fields = [normalize_key(name) for name in reader.fieldnames]
            key_counts.update(normalized_fields)
            identity_alias = next(
                (alias for alias in IDENTITY_ALIASES if alias in normalized_fields),
                None,
            )
            if identity_alias is None:
                return ParsedFile(
                    [], key_counts, Counter({"id_not_identifiable": 1})
                )
            for raw in reader:
                normalized = {
                    normalize_key(key): value for key, value in raw.items()
                }
                identity = normalize_identity(normalized.get(identity_alias))
                if not identity:
                    reasons["record_id_not_identifiable"] += 1
                    continue
                _, model_raw = _first_value(normalized, MODEL_ALIASES)
                _, variant_raw = _first_value(normalized, VARIANT_ALIASES)
                records.append(Record(
                    identity=identity,
                    model=normalize_identity(model_raw) or "",
                    variant=normalize_identity(variant_raw) or "",
                    has_task=_has_any(normalized, TASK_ALIASES),
                    has_reference=_has_any(normalized, REFERENCE_ALIASES),
                    has_candidate=_has_any(normalized, CANDIDATE_ALIASES),
                    has_status=_has_any(normalized, STATUS_ALIASES),
                ))
    except (OSError, UnicodeError, csv.Error):
        return ParsedFile([], key_counts, Counter({"malformed_csv": 1}))
    return ParsedFile(records, key_counts, reasons)


def trace_identity(path: Path) -> tuple[str | None, str]:
    name = path.name
    match = TRACE_BEFORE_DATE_RE.search(name)
    if match:
        value = normalize_identity(match.group("identity"))
        return value, "filename_before_date" if value else "trace_id_missing"
    match = TRACE_AFTER_DATE_RE.search(name)
    if match:
        value = normalize_identity(match.group("identity"))
        parent = normalize_identity(path.parent.name)
        if value and parent and value == parent:
            return value, "parent_confirmed_after_date"
        return None, "trace_identity_ambiguous"
    return None, "trace_identity_not_identifiable"


def _set_sha256(label: str, values: set[str]) -> str:
    payload = json.dumps(
        {"label": label, "values": sorted(values)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _source_manifest(root: Path, files: list[Path]) -> tuple[str, int]:
    rows = []
    total_bytes = 0
    for path in files:
        size = path.stat().st_size
        total_bytes += size
        rows.append({
            "path": path.relative_to(root).as_posix(),
            "size": size,
            "sha256": sha256_file(path),
        })
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), total_bytes


def _pairwise_counts(components: Mapping[str, set[str]]) -> dict[str, int]:
    names = tuple(components)
    return {
        f"{left}_and_{right}": len(components[left] & components[right])
        for index, left in enumerate(names)
        for right in names[index + 1 :]
    }


def scan_family(root: Path, family: str) -> dict[str, Any]:
    family_root = root / family
    if not family_root.is_dir():
        return {
            "family": family,
            "decision": "OPERATIONAL_UNKNOWN",
            "reason_counts": {"missing_family_root": 1},
        }

    candidate_files = sorted(
        path
        for path in (family_root / "different_model_outputs").rglob("*.json")
        if path.is_file()
    )
    score_file = family_root / "scores/per_item_status.csv"
    trace_files = sorted(
        path
        for path in (family_root / "logs_and_execution_traces").rglob("*")
        if path.is_file()
        and "trajectory" in path.name.casefold()
        and path.suffix.casefold() in {".json", ".txt"}
    )

    reasons: Counter[str] = Counter()
    key_counts: Counter[str] = Counter()
    identity_conflicts = 0
    candidate_records: list[Record] = []
    for path in candidate_files:
        parsed = parse_json_file(path)
        candidate_records.extend(parsed.records)
        key_counts.update(parsed.key_counts)
        reasons.update(parsed.reasons)
        identity_conflicts += parsed.identity_conflicts

    score_records: list[Record] = []
    if score_file.is_file():
        parsed_score = parse_csv_file(score_file)
        score_records.extend(parsed_score.records)
        key_counts.update(parsed_score.key_counts)
        reasons.update(parsed_score.reasons)
        identity_conflicts += parsed_score.identity_conflicts
    else:
        reasons["missing_per_item_status"] += 1

    trace_ids: set[str] = set()
    trace_reason_counts: Counter[str] = Counter()
    for path in trace_files:
        identity, reason = trace_identity(path)
        trace_reason_counts[reason] += 1
        if identity:
            trace_ids.add(identity)
    reasons.update(trace_reason_counts)

    candidate_ids = {row.identity for row in candidate_records}
    task_ids = {row.identity for row in candidate_records if row.has_task}
    reference_ids = {
        row.identity for row in candidate_records if row.has_reference
    }
    candidate_content_ids = {
        row.identity for row in candidate_records if row.has_candidate
    }
    score_ids = {row.identity for row in score_records if row.has_status}
    components = {
        "task": task_ids,
        "candidate": candidate_ids,
        "reference": reference_ids,
        "score": score_ids,
        "trace": trace_ids,
    }
    full_chain = set.intersection(*components.values()) if components else set()
    triples = Counter(
        (row.identity, row.model, row.variant) for row in candidate_records
    )
    exact_duplicate_records = sum(count - 1 for count in triples.values() if count > 1)
    gate = {
        "candidate_ids_at_least_30": len(candidate_ids) >= 30,
        "score_ids_at_least_30": len(score_ids) >= 30,
        "task_ids_at_least_30": len(task_ids) >= 30,
        "reference_ids_at_least_30": len(reference_ids) >= 30,
        "trace_ids_at_least_30": len(trace_ids) >= 30,
        "full_chain_at_least_30": len(full_chain) >= 30,
        "identity_conflicts_zero": identity_conflicts == 0,
    }
    return {
        "family": family,
        "decision": (
            "GO_WRITE_A1_PROTOCOL"
            if all(gate.values())
            else "NOT_IDENTIFIABLE_DATA_LINKAGE"
        ),
        "file_counts": {
            "candidate_json": len(candidate_files),
            "per_item_status_csv": int(score_file.is_file()),
            "trajectory": len(trace_files),
        },
        "record_counts": {
            "candidate_records": len(candidate_records),
            "score_records": len(score_records),
            "exact_duplicate_candidate_triples": exact_duplicate_records,
            "identity_conflicts": identity_conflicts,
        },
        "component_unique_id_counts": {
            name: len(values) for name, values in components.items()
        },
        "candidate_content_ids": len(candidate_content_ids),
        "pairwise_join_counts": _pairwise_counts(components),
        "full_chain_count": len(full_chain),
        "full_chain_coverage_over_candidate_ids": (
            len(full_chain) / len(candidate_ids) if candidate_ids else 0.0
        ),
        "id_set_sha256": {
            name: _set_sha256(f"{family}:{name}", values)
            for name, values in components.items()
        },
        "full_chain_id_set_sha256": _set_sha256(
            f"{family}:full_chain", full_chain
        ),
        "schema_key_frequencies": dict(sorted(key_counts.items())),
        "reason_counts": dict(sorted(reasons.items())),
        "gate": gate,
    }


def run(root: Path) -> dict[str, Any]:
    if sha256_file(PROTOCOL_PATH) != EXPECTED_PROTOCOL_SHA256:
        raise ValueError("frozen protocol hash mismatch")
    if not root.is_dir():
        raise ValueError("artifact root is missing")
    in_scope_files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (
            "different_model_outputs" in path.parts
            or "scores" in path.parts
            or "logs_and_execution_traces" in path.parts
            or path.name in {"README.md", "HARNESS_AND_VARIANTS.md"}
        )
    )
    source_manifest_sha256, total_bytes = _source_manifest(root, in_scope_files)
    families = [scan_family(root, family) for family in FAMILIES]
    if any(row["decision"] == "GO_WRITE_A1_PROTOCOL" for row in families):
        decision = "GO_WRITE_A1_PROTOCOL"
    elif any(row["decision"] == "OPERATIONAL_UNKNOWN" for row in families):
        decision = "OPERATIONAL_UNKNOWN"
    else:
        decision = "NOT_IDENTIFIABLE_DATA_LINKAGE"
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "families": families,
        "source_receipt": {
            "file_count": len(in_scope_files),
            "total_bytes": total_bytes,
            "manifest_sha256": source_manifest_sha256,
        },
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "scanner_sha256": sha256_file(Path(__file__)),
        "raw_content_emitted": False,
        "raw_item_ids_emitted": False,
        "candidate_executions": 0,
        "sql_executions": 0,
        "llm_api_calls": 0,
    }
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
    result = run(args.artifact_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("refusing to overwrite existing receipt")
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
