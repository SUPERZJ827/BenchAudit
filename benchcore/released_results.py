from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

from .trace_bundle import (
    TraceArtifact,
    TraceBundle,
    TraceEvaluation,
    TraceOutcome,
    TraceRun,
)


RELEASED_RESULT_SCHEMA_VERSION = "released-result-audit.v1"

_ITEM_FIELDS = ("item_id", "questionId", "question_id", "task_id", "id")
_PREDICTION_FIELDS = ("prediction", "pred", "output", "response", "result_json")
_REFERENCE_FIELDS = ("reference", "gold", "answer", "target", "expected", "origin_code")
_EVALUATION_FIELDS = (
    ("published_evaluator", "verdict"),
    ("published_evaluator", "judge"),
    ("published_evaluator", "correct"),
    ("published_evaluator", "is_success"),
)

_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|[@-_])")
_SQL_DIAGNOSTIC_PATTERNS = (
    re.compile(r"^\s*Invalid expression\s*/\s*Unexpected token\b", re.I),
    re.compile(r"^\s*Expecting\b.*\bLine\s+\d+\s*,\s*Col\s*:", re.I | re.S),
    re.compile(r"^\s*Error tokenizing\b", re.I),
    re.compile(r"^\s*Required keyword\s*:", re.I),
    re.compile(r"^\s*Unsupported syntax\b", re.I),
    re.compile(r"^\s*Traceback\s+\(most recent call last\)\s*:", re.I),
)


@dataclass(frozen=True)
class ReleasedResultMapping:
    """Explicit mapping from a released result record into TraceBundle fields.

    ``__key__`` is reserved for the top-level key of a dict-of-records file.
    Evaluation tuples contain ``(evaluator_id, source_field)``.
    """

    item_id: str
    prediction: str
    reference: str | None = None
    evaluations: tuple[tuple[str, str], ...] = ()
    reference_evaluations: tuple[tuple[str, str], ...] = ()
    reference_contract: str | None = None


@dataclass(frozen=True)
class ReleasedResultSource:
    path: Path
    system_id: str | None = None
    mapping: ReleasedResultMapping | None = None


@dataclass(frozen=True)
class _SourceRecord:
    row: dict[str, Any]
    index: int
    top_level_key: str | None = None


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_records(path: Path) -> list[_SourceRecord]:
    if not path.is_file():
        raise ValueError(f"released result source does not exist: {path}")
    try:
        if path.suffix.lower() == ".jsonl":
            result = []
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(
                        f"{path}:{line_number}: expected a JSON object per line"
                    )
                result.append(_SourceRecord(value, line_number))
            return result

        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read released result source {path}: {exc}") from exc

    if isinstance(document, list):
        records = []
        for index, value in enumerate(document):
            if not isinstance(value, dict):
                raise ValueError(f"{path}[{index}]: expected a JSON object")
            records.append(_SourceRecord(value, index))
        return records
    if isinstance(document, dict):
        if not document:
            return []
        if all(isinstance(value, dict) for value in document.values()):
            return [
                _SourceRecord(value, index, str(key))
                for index, (key, value) in enumerate(document.items())
            ]
        return [_SourceRecord(document, 0)]
    raise ValueError(f"{path}: expected a JSON array, object, or JSONL records")


def _present_fields(
    records: Sequence[_SourceRecord],
    candidates: Sequence[str],
) -> list[str]:
    return [
        candidate
        for candidate in candidates
        if any(candidate in record.row for record in records)
    ]


def _infer_unique_field(
    records: Sequence[_SourceRecord],
    candidates: Sequence[str],
    *,
    role: str,
    required: bool,
) -> str | None:
    present = _present_fields(records, candidates)
    if len(present) > 1:
        raise ValueError(
            f"ambiguous {role}: found fields {', '.join(present)}; "
            "provide ReleasedResultMapping explicitly"
        )
    if not present:
        if required:
            raise ValueError(
                f"could not infer {role}; provide ReleasedResultMapping explicitly"
            )
        return None
    return present[0]


def _infer_mapping(records: Sequence[_SourceRecord]) -> ReleasedResultMapping:
    item_id = _infer_unique_field(
        records, _ITEM_FIELDS, role="item_id", required=True
    )
    prediction = _infer_unique_field(
        records, _PREDICTION_FIELDS, role="prediction", required=True
    )
    reference = _infer_unique_field(
        records, _REFERENCE_FIELDS, role="reference", required=False
    )
    evaluation_fields = [
        (evaluator_id, field_name)
        for evaluator_id, field_name in _EVALUATION_FIELDS
        if any(field_name in record.row for record in records)
    ]
    if len(evaluation_fields) > 1:
        names = ", ".join(field for _, field in evaluation_fields)
        raise ValueError(
            f"ambiguous evaluation: found fields {names}; "
            "provide ReleasedResultMapping explicitly"
        )
    return ReleasedResultMapping(
        item_id=item_id or "",
        prediction=prediction or "",
        reference=reference,
        evaluations=tuple(evaluation_fields),
    )


def _field_value(record: _SourceRecord, field_name: str | None) -> Any:
    if field_name is None:
        return None
    if field_name == "__key__":
        if record.top_level_key is None:
            raise ValueError("__key__ mapping requires a dict-of-records source")
        return record.top_level_key
    return record.row.get(field_name)


def _prediction_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("Answer", "answer", "prediction", "output"):
            if key in value:
                return value[key]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                return value
            return _prediction_value(decoded)
    return value


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return _stable_json(value)


def _normalize_verdict(value: Any) -> str:
    if isinstance(value, bool):
        return "pass" if value else "fail"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return "pass"
        if value == 0:
            return "fail"
    if value is None:
        return "unknown"
    text = str(value).strip().casefold()
    if text in {"t", "true", "pass", "passed", "correct", "ok", "valid", "success"}:
        return "pass"
    if text in {
        "f",
        "false",
        "fail",
        "failed",
        "incorrect",
        "invalid",
        "failure",
    }:
        return "fail"
    if text in {"error", "exception", "crash"}:
        return "error"
    return "unknown"


def _reference_integrity_flags(
    value: Any,
    *,
    contract: str | None,
) -> list[str]:
    if contract != "sql" or not isinstance(value, str):
        return []
    flags = []
    if any(pattern.search(value) for pattern in _SQL_DIAGNOSTIC_PATTERNS):
        flags.append("parser_diagnostic_payload")
    if _ANSI_ESCAPE_RE.search(value):
        flags.append("ansi_escape_sequence")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in value):
        flags.append("unexpected_control_character")
    return flags


def _safe_artifact_path(run_id: str) -> str:
    path = PurePosixPath("released-results") / f"{run_id}.output"
    return str(path)


def _source_provenance(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "source_kind": "released_result",
    }


def adapt_released_results(
    sources: Sequence[ReleasedResultSource],
    *,
    benchmark_id: str,
) -> TraceBundle:
    """Convert heterogeneous released result files into a strict TraceBundle.

    Alignment is always by explicit item identifier, never by row position.
    Inference fails closed on competing aliases. Released verdicts are retained
    as observations; the adapter does not treat them as defect ground truth.
    """

    if not benchmark_id.strip():
        raise ValueError("benchmark_id must not be empty")
    if not sources:
        raise ValueError("at least one released result source is required")

    runs: list[TraceRun] = []
    provenance = []
    attempts: Counter[tuple[str, str]] = Counter()
    for source in sources:
        path = Path(source.path)
        records = _read_records(path)
        if not records:
            raise ValueError(f"{path}: released result source contains no records")
        mapping = source.mapping or _infer_mapping(records)
        system_id = (source.system_id or path.stem).strip()
        if not system_id:
            raise ValueError(f"{path}: system_id must not be empty")
        source_provenance = _source_provenance(path)
        provenance.append(source_provenance)
        source_sha256 = source_provenance["sha256"]

        for record in records:
            raw_item_id = _field_value(record, mapping.item_id)
            if raw_item_id is None or not str(raw_item_id).strip():
                raise ValueError(
                    f"{path}:{record.index}: mapped item_id is missing or empty"
                )
            item_id = str(raw_item_id).strip()
            prediction = _prediction_value(
                _field_value(record, mapping.prediction)
            )
            reference = _field_value(record, mapping.reference)
            prediction_text = _content_text(prediction)
            reference_text = None if reference is None else _content_text(reference)
            attempt_key = (item_id, system_id)
            attempt = attempts[attempt_key]
            attempts[attempt_key] += 1
            run_key = (
                f"{benchmark_id}\0{source_sha256}\0{system_id}\0{item_id}\0"
                f"{attempt}\0{record.index}"
            )
            run_id = f"released:{_sha256_text(run_key)[:20]}"

            evaluations = tuple(
                TraceEvaluation(
                    evaluator_id=evaluator_id,
                    verdict=_normalize_verdict(_field_value(record, field_name)),
                )
                for evaluator_id, field_name in mapping.evaluations
            )
            if len(evaluations) == 1:
                verdict = evaluations[0].verdict
                status = {
                    "pass": "passed",
                    "fail": "failed",
                    "error": "error",
                }.get(verdict, "unknown")
                correct = (
                    True
                    if verdict == "pass"
                    else False
                    if verdict == "fail"
                    else None
                )
            else:
                status = "unknown"
                correct = None

            integrity_flags = _reference_integrity_flags(
                reference, contract=mapping.reference_contract
            )
            released_metadata: dict[str, Any] = {
                "source_name": path.name,
                "source_record_index": record.index,
                "mapping": {
                    "item_id": mapping.item_id,
                    "prediction": mapping.prediction,
                    "reference": mapping.reference,
                    "evaluations": [list(row) for row in mapping.evaluations],
                    "reference_evaluations": [
                        list(row) for row in mapping.reference_evaluations
                    ],
                },
                "reference_contract": mapping.reference_contract,
                "reference_sha256": (
                    _sha256_text(reference_text)
                    if reference_text is not None
                    else None
                ),
                "reference_kind": (
                    type(reference).__name__ if reference is not None else "missing"
                ),
                "reference_integrity_flags": integrity_flags,
                "reference_evaluations": [
                    {
                        "evaluator_id": evaluator_id,
                        "verdict": _normalize_verdict(
                            _field_value(record, field_name)
                        ),
                    }
                    for evaluator_id, field_name in mapping.reference_evaluations
                ],
                "prediction_missing": prediction is None,
                "reference_missing": reference is None,
            }
            if integrity_flags and reference_text is not None:
                released_metadata["reference_diagnostic_preview"] = reference_text[:240]

            runs.append(
                TraceRun(
                    run_id=run_id,
                    item_id=item_id,
                    system_id=system_id,
                    attempt=attempt,
                    outcome=TraceOutcome(status=status, correct=correct),
                    artifacts=(
                        (
                            TraceArtifact(
                                artifact_id="published_output",
                                role="output",
                                path=_safe_artifact_path(run_id),
                                sha256=_sha256_text(prediction_text),
                                media_type="text/plain",
                            ),
                        )
                        if prediction is not None
                        else ()
                    ),
                    evaluations=evaluations,
                    metadata={
                        "evaluation_scope": "output",
                        "released_result": released_metadata,
                    },
                )
            )

    runs.sort(key=lambda run: (run.item_id, run.system_id, run.attempt, run.run_id))
    return TraceBundle(
        benchmark_id=benchmark_id,
        runs=runs,
        sources=provenance,
    )


def _candidate(
    *,
    kind: str,
    item_ids: Iterable[str],
    run_ids: Iterable[str],
    message: str,
    confidence: float,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    item_list = sorted(set(item_ids))
    key = f"{kind}\0{_stable_json(item_list)}"
    candidate_id = f"released:{kind}:{_sha256_text(key)[:16]}"
    return {
        "candidate_id": candidate_id,
        "item_ids": item_list,
        "run_ids": sorted(set(run_ids)),
        "defect_type": kind,
        "message": message,
        "confidence": confidence,
        "detection_method": "released_result_consistency",
        "evidence_tier": "review",
        "review_only": True,
        "confirmation_eligible": False,
        "evidence": evidence,
    }


def analyze_released_results(bundle: TraceBundle) -> dict[str, Any]:
    """Find reference-integrity and version anomalies in adapted results.

    These observations are deliberately dataset-level and review-only. They
    identify where independent replay should be concentrated; they do not prove
    that a benchmark item is defective.
    """

    diagnostic_items: dict[str, dict[str, Any]] = {}
    reference_versions: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    missing_predictions = 0
    missing_references = 0
    runs_with_evaluations = 0
    reference_evaluator_failures: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )

    for run in bundle.runs:
        metadata = run.metadata.get("released_result", {})
        if not isinstance(metadata, dict):
            continue
        flags = metadata.get("reference_integrity_flags", [])
        if isinstance(flags, list) and flags:
            entry = diagnostic_items.setdefault(
                run.item_id,
                {
                    "flags": set(),
                    "run_ids": set(),
                    "previews": set(),
                },
            )
            entry["flags"].update(str(flag) for flag in flags)
            entry["run_ids"].add(run.run_id)
            preview = metadata.get("reference_diagnostic_preview")
            if isinstance(preview, str):
                entry["previews"].add(preview)
        reference_sha256 = metadata.get("reference_sha256")
        if isinstance(reference_sha256, str):
            reference_versions[run.item_id][reference_sha256].add(run.run_id)
        missing_predictions += bool(metadata.get("prediction_missing"))
        missing_references += bool(metadata.get("reference_missing"))
        runs_with_evaluations += bool(run.evaluations)
        for evaluation in metadata.get("reference_evaluations", []):
            if not isinstance(evaluation, dict):
                continue
            if evaluation.get("verdict") != "fail":
                continue
            evaluator_id = str(evaluation.get("evaluator_id") or "unknown")
            reference_evaluator_failures[run.item_id][evaluator_id].add(run.run_id)

    candidates = []
    if diagnostic_items:
        all_run_ids = [
            run_id
            for entry in diagnostic_items.values()
            for run_id in entry["run_ids"]
        ]
        flag_counts = Counter(
            flag
            for entry in diagnostic_items.values()
            for flag in entry["flags"]
        )
        candidates.append(
            _candidate(
                kind="reference_diagnostic_payload",
                item_ids=diagnostic_items,
                run_ids=all_run_ids,
                message=(
                    "Published reference fields contain parser diagnostics or "
                    "control payloads instead of a clean reference artifact."
                ),
                confidence=0.98,
                evidence={
                    "affected_items": len(diagnostic_items),
                    "flag_counts": dict(sorted(flag_counts.items())),
                    "bounded_previews": {
                        item_id: sorted(entry["previews"])[:2]
                        for item_id, entry in sorted(diagnostic_items.items())
                    },
                },
            )
        )

    drift_items = {
        item_id: versions
        for item_id, versions in reference_versions.items()
        if len(versions) > 1
    }
    if drift_items:
        all_run_ids = [
            run_id
            for versions in drift_items.values()
            for run_ids in versions.values()
            for run_id in run_ids
        ]
        candidates.append(
            _candidate(
                kind="reference_version_disagreement",
                item_ids=drift_items,
                run_ids=all_run_ids,
                message=(
                    "The same item ID is associated with multiple published "
                    "reference payloads across result sources."
                ),
                confidence=0.95,
                evidence={
                    "affected_items": len(drift_items),
                    "reference_versions": max(
                        len(versions) for versions in drift_items.values()
                    ),
                    "versions_by_item": {
                        item_id: sorted(versions)
                        for item_id, versions in sorted(drift_items.items())
                    },
                },
            )
        )

    if reference_evaluator_failures:
        all_run_ids = [
            run_id
            for evaluators in reference_evaluator_failures.values()
            for run_ids in evaluators.values()
            for run_id in run_ids
        ]
        candidates.append(
            _candidate(
                kind="published_reference_evaluator_failure",
                item_ids=reference_evaluator_failures,
                run_ids=all_run_ids,
                message=(
                    "A published evaluator rejects reference artifacts used by "
                    "the released benchmark results."
                ),
                confidence=0.90,
                evidence={
                    "affected_items": len(reference_evaluator_failures),
                    "evaluator_counts": dict(sorted(Counter(
                        evaluator_id
                        for evaluators in reference_evaluator_failures.values()
                        for evaluator_id in evaluators
                    ).items())),
                },
            )
        )

    candidates.sort(key=lambda candidate: candidate["candidate_id"])
    return {
        "schema_version": RELEASED_RESULT_SCHEMA_VERSION,
        "benchmark_id": bundle.benchmark_id,
        "promotion_ceiling": "review",
        "confirmation_eligible": False,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "coverage": {
            "runs": len(bundle.runs),
            "items": len(bundle.item_ids),
            "systems": len(bundle.system_ids),
            "runs_with_evaluations": runs_with_evaluations,
            "missing_predictions": missing_predictions,
            "missing_references": missing_references,
        },
    }
