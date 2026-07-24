from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


TRACE_SCHEMA_VERSION = "tracebundle.v1"
SUPPORTED_TRACE_SUFFIXES = {".json", ".jsonl"}
OUTCOME_STATUSES = {"passed", "failed", "error", "timeout", "cancelled", "unknown"}
EVALUATION_VERDICTS = {"pass", "fail", "error", "unknown"}
CONTROL_KINDS = {"identical", "mutation", "metamorphic", "random", "other"}
ARTIFACT_ROLES = {"input", "output", "log", "evaluator", "reference", "other"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[^\x00-\x1f\x7f]+$")


@dataclass(frozen=True)
class TraceOutcome:
    status: str
    correct: bool | None = None
    score: float | None = None
    reward: float | None = None
    error_type: str | None = None


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    event_type: str
    timestamp: str | None = None
    message: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TraceArtifact:
    artifact_id: str
    role: str
    path: str
    sha256: str | None = None
    media_type: str | None = None


@dataclass(frozen=True)
class TraceEvaluation:
    evaluator_id: str
    verdict: str
    rubric_id: str | None = None
    score: float | None = None
    message: str | None = None


@dataclass(frozen=True)
class TraceRun:
    run_id: str
    item_id: str
    system_id: str
    attempt: int
    outcome: TraceOutcome
    control_id: str | None = None
    control_kind: str | None = None
    events: tuple[TraceEvent, ...] = ()
    artifacts: tuple[TraceArtifact, ...] = ()
    evaluations: tuple[TraceEvaluation, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceBundle:
    benchmark_id: str
    runs: list[TraceRun]
    sources: list[dict[str, Any]]

    @property
    def item_ids(self) -> list[str]:
        return sorted({run.item_id for run in self.runs})

    @property
    def system_ids(self) -> list[str]:
        return sorted({run.system_id for run in self.runs})

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "benchmark_id": self.benchmark_id,
            "metadata": {"source_provenance": self.sources},
            "runs": [_run_to_dict(run) for run in self.runs],
        }


def _run_to_dict(run: TraceRun) -> dict[str, Any]:
    data = asdict(run)
    data["events"] = [asdict(event) for event in run.events]
    data["artifacts"] = [asdict(artifact) for artifact in run.artifacts]
    data["evaluations"] = [asdict(evaluation) for evaluation in run.evaluations]
    return data


def _require_object(value: Any, *, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{location}: expected a JSON object")
    return value


def _check_keys(
    value: dict[str, Any],
    *,
    allowed: set[str],
    required: set[str],
    location: str,
) -> None:
    missing = sorted(required - value.keys())
    if missing:
        raise ValueError(f"{location}: missing required field(s): {', '.join(missing)}")
    unknown = sorted(value.keys() - allowed)
    if unknown:
        raise ValueError(
            f"{location}: unknown field(s): {', '.join(unknown)}; "
            "put benchmark-specific extensions under metadata or attributes"
        )


def _identifier(value: Any, *, name: str, location: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{location}: {name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{location}: {name} must not be empty")
    if not _IDENTIFIER_RE.fullmatch(text):
        raise ValueError(f"{location}: {name} contains a control character")
    return text


def _optional_identifier(value: Any, *, name: str, location: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, name=name, location=location)


def _strict_bool_or_none(value: Any, *, name: str, location: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"{location}: {name} must be a JSON boolean or null")


def _finite_number_or_none(
    value: Any,
    *,
    name: str,
    location: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{location}: {name} must be a JSON number or null")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{location}: {name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{location}: {name} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{location}: {name} must be <= {maximum}")
    return result


def _json_compatible(value: Any, *, location: str, depth: int = 0) -> Any:
    if depth > 20:
        raise ValueError(f"{location}: JSON extension nesting exceeds 20 levels")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{location}: JSON extension contains a non-finite number")
        return value
    if isinstance(value, list):
        return [
            _json_compatible(item, location=f"{location}[{index}]", depth=depth + 1)
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{location}: JSON object keys must be strings")
            result[key] = _json_compatible(
                item, location=f"{location}.{key}", depth=depth + 1
            )
        return result
    raise ValueError(f"{location}: value is not JSON-compatible")


def _metadata(value: Any, *, location: str) -> dict[str, Any]:
    if value is None:
        return {}
    return _json_compatible(
        _require_object(value, location=location),
        location=location,
    )


def _parse_outcome(value: Any, *, location: str) -> TraceOutcome:
    row = _require_object(value, location=location)
    _check_keys(
        row,
        allowed={"status", "correct", "score", "reward", "error_type"},
        required={"status"},
        location=location,
    )
    status = _identifier(row["status"], name="status", location=location).lower()
    if status not in OUTCOME_STATUSES:
        raise ValueError(
            f"{location}: unsupported status {status!r}; "
            f"expected one of {sorted(OUTCOME_STATUSES)}"
        )
    return TraceOutcome(
        status=status,
        correct=_strict_bool_or_none(
            row.get("correct"), name="correct", location=location
        ),
        score=_finite_number_or_none(
            row.get("score"),
            name="score",
            location=location,
            minimum=0.0,
            maximum=1.0,
        ),
        reward=_finite_number_or_none(
            row.get("reward"), name="reward", location=location
        ),
        error_type=_optional_identifier(
            row.get("error_type"), name="error_type", location=location
        ),
    )


def _parse_event(value: Any, *, location: str) -> TraceEvent:
    row = _require_object(value, location=location)
    _check_keys(
        row,
        allowed={"sequence", "event_type", "timestamp", "message", "attributes"},
        required={"sequence", "event_type"},
        location=location,
    )
    sequence = row["sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError(f"{location}: sequence must be a non-negative integer")
    timestamp = row.get("timestamp")
    if timestamp is not None and not isinstance(timestamp, str):
        raise ValueError(f"{location}: timestamp must be a string or null")
    message = row.get("message")
    if message is not None and not isinstance(message, str):
        raise ValueError(f"{location}: message must be a string or null")
    return TraceEvent(
        sequence=sequence,
        event_type=_identifier(
            row["event_type"], name="event_type", location=location
        ).lower(),
        timestamp=timestamp,
        message=message,
        attributes=_metadata(row.get("attributes"), location=f"{location}.attributes"),
    )


def _safe_artifact_path(value: Any, *, location: str) -> str:
    path = _identifier(value, name="path", location=location).replace("\\", "/")
    pure = PurePosixPath(path)
    windows_absolute = bool(re.match(r"^[A-Za-z]:/", path))
    if (
        pure.is_absolute()
        or windows_absolute
        or any(part == ".." for part in pure.parts)
    ):
        raise ValueError(
            f"{location}: artifact path must be relative and must not contain '..'"
        )
    if any(part in {"", "."} for part in pure.parts):
        raise ValueError(f"{location}: artifact path contains an empty or '.' segment")
    return str(pure)


def _parse_artifact(value: Any, *, location: str) -> TraceArtifact:
    row = _require_object(value, location=location)
    _check_keys(
        row,
        allowed={"artifact_id", "role", "path", "sha256", "media_type"},
        required={"artifact_id", "role", "path"},
        location=location,
    )
    role = _identifier(row["role"], name="role", location=location).lower()
    if role not in ARTIFACT_ROLES:
        raise ValueError(
            f"{location}: unsupported artifact role {role!r}; "
            f"expected one of {sorted(ARTIFACT_ROLES)}"
        )
    digest = row.get("sha256")
    if digest is not None:
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest.lower()):
            raise ValueError(f"{location}: sha256 must contain 64 hexadecimal digits")
        digest = digest.lower()
    media_type = row.get("media_type")
    if media_type is not None and not isinstance(media_type, str):
        raise ValueError(f"{location}: media_type must be a string or null")
    return TraceArtifact(
        artifact_id=_identifier(
            row["artifact_id"], name="artifact_id", location=location
        ),
        role=role,
        path=_safe_artifact_path(row["path"], location=location),
        sha256=digest,
        media_type=media_type,
    )


def _parse_evaluation(value: Any, *, location: str) -> TraceEvaluation:
    row = _require_object(value, location=location)
    _check_keys(
        row,
        allowed={"evaluator_id", "verdict", "rubric_id", "score", "message"},
        required={"evaluator_id", "verdict"},
        location=location,
    )
    verdict = _identifier(row["verdict"], name="verdict", location=location).lower()
    if verdict not in EVALUATION_VERDICTS:
        raise ValueError(
            f"{location}: unsupported verdict {verdict!r}; "
            f"expected one of {sorted(EVALUATION_VERDICTS)}"
        )
    message = row.get("message")
    if message is not None and not isinstance(message, str):
        raise ValueError(f"{location}: message must be a string or null")
    return TraceEvaluation(
        evaluator_id=_identifier(
            row["evaluator_id"], name="evaluator_id", location=location
        ),
        verdict=verdict,
        rubric_id=_optional_identifier(
            row.get("rubric_id"), name="rubric_id", location=location
        ),
        score=_finite_number_or_none(
            row.get("score"),
            name="score",
            location=location,
            minimum=0.0,
            maximum=1.0,
        ),
        message=message,
    )


def _parse_run(value: Any, *, location: str) -> TraceRun:
    row = _require_object(value, location=location)
    _check_keys(
        row,
        allowed={
            "schema_version",
            "benchmark_id",
            "run_id",
            "item_id",
            "system_id",
            "attempt",
            "control_id",
            "control_kind",
            "outcome",
            "events",
            "artifacts",
            "evaluations",
            "metadata",
        },
        required={"run_id", "item_id", "system_id", "attempt", "outcome"},
        location=location,
    )
    attempt = row["attempt"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        raise ValueError(f"{location}: attempt must be a non-negative integer")
    control_id = _optional_identifier(
        row.get("control_id"), name="control_id", location=location
    )
    control_kind = _optional_identifier(
        row.get("control_kind"), name="control_kind", location=location
    )
    if control_kind is not None:
        control_kind = control_kind.lower()
        if control_kind not in CONTROL_KINDS:
            raise ValueError(
                f"{location}: unsupported control_kind {control_kind!r}; "
                f"expected one of {sorted(CONTROL_KINDS)}"
            )
        if control_id is None:
            raise ValueError(f"{location}: control_kind requires control_id")
    if control_id is not None and control_kind is None:
        raise ValueError(f"{location}: control_id requires control_kind")

    events_value = row.get("events", [])
    artifacts_value = row.get("artifacts", [])
    evaluations_value = row.get("evaluations", [])
    for name, collection in (
        ("events", events_value),
        ("artifacts", artifacts_value),
        ("evaluations", evaluations_value),
    ):
        if not isinstance(collection, list):
            raise ValueError(f"{location}: {name} must be an array")

    events = tuple(
        _parse_event(event, location=f"{location}.events[{index}]")
        for index, event in enumerate(events_value)
    )
    sequences = [event.sequence for event in events]
    if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
        raise ValueError(
            f"{location}: event sequences must be unique and monotonically increasing"
        )
    artifacts = tuple(
        _parse_artifact(artifact, location=f"{location}.artifacts[{index}]")
        for index, artifact in enumerate(artifacts_value)
    )
    artifact_ids = [artifact.artifact_id for artifact in artifacts]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError(f"{location}: duplicate artifact_id within a run")
    evaluations = tuple(
        _parse_evaluation(evaluation, location=f"{location}.evaluations[{index}]")
        for index, evaluation in enumerate(evaluations_value)
    )
    return TraceRun(
        run_id=_identifier(row["run_id"], name="run_id", location=location),
        item_id=_identifier(row["item_id"], name="item_id", location=location),
        system_id=_identifier(
            row["system_id"], name="system_id", location=location
        ),
        attempt=attempt,
        outcome=_parse_outcome(row["outcome"], location=f"{location}.outcome"),
        control_id=control_id,
        control_kind=control_kind,
        events=events,
        artifacts=artifacts,
        evaluations=evaluations,
        metadata=_metadata(row.get("metadata"), location=f"{location}.metadata"),
    )


def _read_document(path: Path, *, maximum_file_bytes: int) -> Any:
    size = path.stat().st_size
    if size > maximum_file_bytes:
        raise ValueError(
            f"{path}: file is {size} bytes, above maximum_file_bytes="
            f"{maximum_file_bytes}"
        )
    if path.suffix.lower() == ".json":
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON") from exc
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row must be an object")
            rows.append(row)
        return rows
    raise ValueError(
        f"{path}: unsupported trace suffix; expected "
        f"{sorted(SUPPORTED_TRACE_SUFFIXES)}"
    )


def _expand_trace_paths(paths: Iterable[Path]) -> list[Path]:
    expanded: list[Path] = []
    for raw_path in paths:
        path = raw_path.expanduser().resolve()
        if path.is_dir():
            children = sorted(
                child
                for child in path.iterdir()
                if child.is_file()
                and child.suffix.lower() in SUPPORTED_TRACE_SUFFIXES
            )
            if not children:
                raise ValueError(f"trace directory has no JSON/JSONL files: {path}")
            expanded.extend(children)
        elif path.is_file():
            expanded.append(path)
        else:
            raise FileNotFoundError(path)
    if not expanded:
        raise ValueError("at least one trace artifact is required")
    duplicate = next(
        (path for path, count in Counter(expanded).items() if count > 1),
        None,
    )
    if duplicate is not None:
        raise ValueError(f"trace artifact provided more than once: {duplicate}")
    return expanded


def load_trace_bundle(
    paths: Iterable[Path],
    *,
    maximum_file_bytes: int = 256 * 1024 * 1024,
    maximum_runs: int = 1_000_000,
    maximum_events_per_run: int = 100_000,
) -> TraceBundle:
    """Load and strictly validate TraceBundle v1 JSON or JSONL artifacts.

    JSON files use ``{"schema_version": "tracebundle.v1", "benchmark_id": ...,
    "runs": [...]}``.  JSONL stores one run per line; every row must declare
    ``schema_version`` and ``benchmark_id``.  Multiple files are merged only
    when their benchmark identifiers agree.
    """

    if maximum_file_bytes < 1 or maximum_runs < 1 or maximum_events_per_run < 0:
        raise ValueError(
            "maximum_file_bytes and maximum_runs must be positive; "
            "maximum_events_per_run must be non-negative"
        )
    files = _expand_trace_paths(paths)
    benchmark_id: str | None = None
    runs: list[TraceRun] = []
    sources: list[dict[str, Any]] = []
    run_locations: dict[str, str] = {}
    observation_locations: dict[tuple[str, str, int], str] = {}

    for path in files:
        document = _read_document(path, maximum_file_bytes=maximum_file_bytes)
        if path.suffix.lower() == ".json":
            root = _require_object(document, location=str(path))
            _check_keys(
                root,
                allowed={"schema_version", "benchmark_id", "runs", "metadata"},
                required={"schema_version", "benchmark_id", "runs"},
                location=str(path),
            )
            version = root["schema_version"]
            file_benchmark_id = _identifier(
                root["benchmark_id"], name="benchmark_id", location=str(path)
            )
            rows = root["runs"]
            if not isinstance(rows, list):
                raise ValueError(f"{path}: runs must be an array")
            row_locations = [f"{path}.runs[{index}]" for index in range(len(rows))]
        else:
            rows = document
            if not rows:
                raise ValueError(f"{path}: trace JSONL is empty")
            versions = {row.get("schema_version") for row in rows}
            benchmark_ids = {row.get("benchmark_id") for row in rows}
            if len(versions) != 1 or len(benchmark_ids) != 1:
                raise ValueError(
                    f"{path}: every JSONL row must declare one consistent "
                    "schema_version and benchmark_id"
                )
            version = next(iter(versions))
            file_benchmark_id = _identifier(
                next(iter(benchmark_ids)),
                name="benchmark_id",
                location=str(path),
            )
            row_locations = [f"{path}:{index + 1}" for index in range(len(rows))]
        if version != TRACE_SCHEMA_VERSION:
            raise ValueError(
                f"{path}: unsupported schema_version {version!r}; "
                f"expected {TRACE_SCHEMA_VERSION!r}"
            )
        if benchmark_id is None:
            benchmark_id = file_benchmark_id
        elif benchmark_id != file_benchmark_id:
            raise ValueError(
                f"{path}: benchmark_id {file_benchmark_id!r} does not match "
                f"{benchmark_id!r}"
            )

        for row, location in zip(rows, row_locations):
            if len(runs) >= maximum_runs:
                raise ValueError(f"trace bundle exceeds maximum_runs={maximum_runs}")
            row_object = _require_object(row, location=location)
            row_version = row_object.get("schema_version")
            if row_version is not None and row_version != version:
                raise ValueError(
                    f"{location}: row schema_version {row_version!r} does not "
                    f"match file version {version!r}"
                )
            row_benchmark_id = row_object.get("benchmark_id")
            if (
                row_benchmark_id is not None
                and row_benchmark_id != file_benchmark_id
            ):
                raise ValueError(
                    f"{location}: row benchmark_id {row_benchmark_id!r} does not "
                    f"match file benchmark_id {file_benchmark_id!r}"
                )
            run = _parse_run(row, location=location)
            if len(run.events) > maximum_events_per_run:
                raise ValueError(
                    f"{location}: events exceed maximum_events_per_run="
                    f"{maximum_events_per_run}"
                )
            if run.run_id in run_locations:
                raise ValueError(
                    f"{location}: duplicate run_id {run.run_id!r}; "
                    f"first seen at {run_locations[run.run_id]}"
                )
            observation_key = (run.item_id, run.system_id, run.attempt)
            if observation_key in observation_locations:
                raise ValueError(
                    f"{location}: duplicate (item_id, system_id, attempt) "
                    f"{observation_key!r}; first seen at "
                    f"{observation_locations[observation_key]}"
                )
            run_locations[run.run_id] = location
            observation_locations[observation_key] = location
            runs.append(run)
        sources.append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
        )

    if benchmark_id is None or not runs:
        raise ValueError("trace bundle contains no runs")
    runs.sort(key=lambda run: (run.item_id, run.system_id, run.attempt, run.run_id))
    return TraceBundle(benchmark_id=benchmark_id, runs=runs, sources=sources)


def _candidate(
    *,
    candidate_id: str,
    item_ids: Iterable[str],
    run_ids: Iterable[str],
    defect_type: str,
    message: str,
    evidence: dict[str, Any],
    confidence: float,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "item_ids": sorted(set(item_ids)),
        "run_ids": sorted(set(run_ids)),
        "defect_type": defect_type,
        "message": message,
        "confidence": confidence,
        "detection_method": "historical_trace_consistency",
        "evidence_tier": "review",
        "review_only": True,
        "confirmation_eligible": False,
        "evidence": evidence,
    }


def _candidate_id(kind: str, key: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{key}".encode("utf-8")).hexdigest()[:16]
    return f"trace:{kind}:{digest}"


def _output_signature(run: TraceRun) -> tuple[tuple[str, str, str], ...] | None:
    outputs = [
        (artifact.artifact_id, artifact.path, artifact.sha256)
        for artifact in run.artifacts
        if artifact.role == "output" and artifact.sha256 is not None
    ]
    return tuple(sorted(outputs)) if outputs else None


def analyze_trace_bundle(
    bundle: TraceBundle,
    *,
    minimum_repeated_runs: int = 2,
    score_spread_threshold: float = 0.10,
    high_reward_threshold: float = 0.90,
    infrastructure_rate_threshold: float = 0.20,
    minimum_infrastructure_runs: int = 5,
) -> dict[str, Any]:
    """Generate deterministic, review-only candidates from archived runs."""

    if minimum_repeated_runs < 2:
        raise ValueError("minimum_repeated_runs must be at least 2")
    if not 0.0 <= score_spread_threshold <= 1.0:
        raise ValueError("score_spread_threshold must be in [0, 1]")
    if not math.isfinite(high_reward_threshold):
        raise ValueError("high_reward_threshold must be finite")
    if not 0.0 <= infrastructure_rate_threshold <= 1.0:
        raise ValueError("infrastructure_rate_threshold must be in [0, 1]")
    if minimum_infrastructure_runs < 1:
        raise ValueError("minimum_infrastructure_runs must be positive")

    candidates: list[dict[str, Any]] = []
    by_item_system: dict[tuple[str, str], list[TraceRun]] = defaultdict(list)
    identical_groups: dict[str, list[TraceRun]] = defaultdict(list)
    status_counts: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    correct_runs = 0
    score_runs = 0
    reward_runs = 0
    output_digest_runs = 0

    for run in bundle.runs:
        by_item_system[(run.item_id, run.system_id)].append(run)
        status_counts[run.outcome.status] += 1
        event_counts.update(event.event_type for event in run.events)
        correct_runs += run.outcome.correct is not None
        score_runs += run.outcome.score is not None
        reward_runs += run.outcome.reward is not None
        output_digest_runs += _output_signature(run) is not None
        if run.control_kind == "identical" and run.control_id is not None:
            identical_groups[run.control_id].append(run)

        nonzero_exits = []
        for event in run.events:
            if event.event_type not in {"process_exit", "command_exit"}:
                continue
            exit_code = event.attributes.get("exit_code")
            if isinstance(exit_code, int) and not isinstance(exit_code, bool):
                if exit_code != 0:
                    nonzero_exits.append(
                        {"sequence": event.sequence, "exit_code": exit_code}
                    )
        if run.outcome.status == "passed" and nonzero_exits:
            key = run.run_id
            candidates.append(
                _candidate(
                    candidate_id=_candidate_id("pass_with_nonzero_exit", key),
                    item_ids=[run.item_id],
                    run_ids=[run.run_id],
                    defect_type="pass_with_execution_error",
                    message=(
                        "Run is marked passed even though its trace contains a "
                        "non-zero process exit."
                    ),
                    confidence=0.95,
                    evidence={"nonzero_exits": nonzero_exits},
                )
            )
        status_correct_mismatch = (
            run.outcome.correct is not None
            and (
                (run.outcome.status == "passed" and not run.outcome.correct)
                or (run.outcome.status == "failed" and run.outcome.correct)
            )
        )
        if status_correct_mismatch:
            candidates.append(
                _candidate(
                    candidate_id=_candidate_id(
                        "outcome_correctness_mismatch", run.run_id
                    ),
                    item_ids=[run.item_id],
                    run_ids=[run.run_id],
                    defect_type="outcome_correctness_mismatch",
                    message=(
                        "The run's pass/fail status disagrees with its explicit "
                        "correctness value."
                    ),
                    confidence=0.90,
                    evidence={
                        "status": run.outcome.status,
                        "correct": run.outcome.correct,
                    },
                )
            )
        if (
            run.outcome.status in {"failed", "error", "timeout"}
            and run.outcome.reward is not None
            and run.outcome.reward >= high_reward_threshold
        ):
            candidates.append(
                _candidate(
                    candidate_id=_candidate_id("reward_verdict_mismatch", run.run_id),
                    item_ids=[run.item_id],
                    run_ids=[run.run_id],
                    defect_type="reward_verdict_mismatch",
                    message=(
                        "Run has a failing outcome but a high reward; the result "
                        "and reward channels may disagree."
                    ),
                    confidence=0.90,
                    evidence={
                        "status": run.outcome.status,
                        "reward": run.outcome.reward,
                        "high_reward_threshold": high_reward_threshold,
                    },
                )
            )

        evaluation_groups: dict[str, list[TraceEvaluation]] = defaultdict(list)
        for evaluation in run.evaluations:
            evaluation_groups[evaluation.rubric_id or "__overall__"].append(evaluation)
        for rubric_id, evaluations in evaluation_groups.items():
            verdicts = {evaluation.verdict for evaluation in evaluations}
            if "pass" in verdicts and "fail" in verdicts:
                key = f"{run.run_id}\0{rubric_id}"
                candidates.append(
                    _candidate(
                        candidate_id=_candidate_id(
                            "evaluator_verdict_disagreement", key
                        ),
                        item_ids=[run.item_id],
                        run_ids=[run.run_id],
                        defect_type="evaluator_verdict_disagreement",
                        message=(
                            "Evaluators disagree on the same run and rubric; "
                            "this may reflect judge instability or rubric ambiguity."
                        ),
                        confidence=0.80,
                        evidence={
                            "rubric_id": None
                            if rubric_id == "__overall__"
                            else rubric_id,
                            "evaluations": [
                                {
                                    "evaluator_id": evaluation.evaluator_id,
                                    "verdict": evaluation.verdict,
                                    "score": evaluation.score,
                                }
                                for evaluation in evaluations
                            ],
                        },
                    )
                )

    for (item_id, system_id), runs in sorted(by_item_system.items()):
        if len(runs) < minimum_repeated_runs:
            continue
        identical_keys = {
            run.control_id
            for run in runs
            if run.control_kind == "identical" and run.control_id is not None
        }
        pure_identical_group = (
            len(identical_keys) == 1
            and all(
                run.control_kind == "identical"
                and run.control_id in identical_keys
                for run in runs
            )
        )
        semantic_statuses = {
            run.outcome.status
            for run in runs
            if run.outcome.status in {"passed", "failed"}
        }
        if semantic_statuses == {"passed", "failed"} and not pure_identical_group:
            key = f"{item_id}\0{system_id}"
            candidates.append(
                _candidate(
                    candidate_id=_candidate_id("repeated_outcome_disagreement", key),
                    item_ids=[item_id],
                    run_ids=[run.run_id for run in runs],
                    defect_type="repeated_outcome_disagreement",
                    message=(
                        "Repeated runs of the same system on the same item contain "
                        "both pass and fail outcomes."
                    ),
                    confidence=0.85,
                    evidence={
                        "system_id": system_id,
                        "statuses": [run.outcome.status for run in runs],
                        "attempts": [run.attempt for run in runs],
                    },
                )
            )
        scores = [
            run.outcome.score for run in runs if run.outcome.score is not None
        ]
        if len(scores) >= minimum_repeated_runs and not pure_identical_group:
            spread = max(scores) - min(scores)
            if spread >= score_spread_threshold:
                key = f"{item_id}\0{system_id}"
                candidates.append(
                    _candidate(
                        candidate_id=_candidate_id("repeated_score_instability", key),
                        item_ids=[item_id],
                        run_ids=[run.run_id for run in runs],
                        defect_type="repeated_score_instability",
                        message=(
                            "Repeated runs of the same system on the same item "
                            "have a score spread above the configured threshold."
                        ),
                        confidence=0.75,
                        evidence={
                            "system_id": system_id,
                            "scores": scores,
                            "score_spread": spread,
                            "threshold": score_spread_threshold,
                        },
                    )
                )

    for control_id, runs in sorted(identical_groups.items()):
        if len(runs) < minimum_repeated_runs:
            continue
        statuses = {run.outcome.status for run in runs}
        outcome_mismatch = "passed" in statuses and "failed" in statuses
        scores = [
            run.outcome.score for run in runs if run.outcome.score is not None
        ]
        score_spread = None
        if len(scores) >= minimum_repeated_runs:
            observed_spread = max(scores) - min(scores)
            if observed_spread >= score_spread_threshold:
                score_spread = observed_spread
        signatures = [
            signature
            for signature in (_output_signature(run) for run in runs)
            if signature is not None
        ]
        artifact_mismatch = (
            len(signatures) >= minimum_repeated_runs and len(set(signatures)) > 1
        )
        if outcome_mismatch or score_spread is not None or artifact_mismatch:
            modalities = []
            if outcome_mismatch:
                modalities.append("outcome")
            if score_spread is not None:
                modalities.append("score")
            if artifact_mismatch:
                modalities.append("artifact")
            candidates.append(
                _candidate(
                    candidate_id=_candidate_id(
                        "identical_control_mismatch", control_id
                    ),
                    item_ids=[run.item_id for run in runs],
                    run_ids=[run.run_id for run in runs],
                    defect_type="identical_control_mismatch",
                    message=(
                        "Runs declared as an identical control disagree in "
                        f"{', '.join(modalities)} evidence."
                    ),
                    confidence=0.95 if outcome_mismatch else 0.90,
                    evidence={
                        "control_id": control_id,
                        "mismatch_modalities": modalities,
                        "statuses": [run.outcome.status for run in runs],
                        "scores": scores,
                        "score_spread": score_spread,
                        "score_spread_threshold": score_spread_threshold,
                        "output_signatures": [
                            list(signature) for signature in signatures
                        ],
                    },
                )
            )

    infrastructure_runs = [
        run
        for run in bundle.runs
        if run.outcome.status in {"error", "timeout", "cancelled"}
    ]
    infrastructure_rate = len(infrastructure_runs) / len(bundle.runs)
    if (
        len(bundle.runs) >= minimum_infrastructure_runs
        and infrastructure_rate >= infrastructure_rate_threshold
    ):
        candidates.append(
            _candidate(
                candidate_id=_candidate_id(
                    "infrastructure_failure_cluster", bundle.benchmark_id
                ),
                item_ids=[run.item_id for run in infrastructure_runs],
                run_ids=[run.run_id for run in infrastructure_runs],
                defect_type="infrastructure_failure_cluster",
                message=(
                    "A substantial fraction of archived runs ended in an "
                    "infrastructure-like state; benchmark results may be confounded."
                ),
                confidence=0.85,
                evidence={
                    "affected_runs": len(infrastructure_runs),
                    "total_runs": len(bundle.runs),
                    "rate": infrastructure_rate,
                    "threshold": infrastructure_rate_threshold,
                },
            )
        )

    candidates.sort(
        key=lambda row: (
            -float(row["confidence"]),
            row["defect_type"],
            row["candidate_id"],
        )
    )
    repeat_groups = sum(
        len(runs) >= minimum_repeated_runs for runs in by_item_system.values()
    )
    warnings = []
    if repeat_groups == 0:
        warnings.append(
            "No repeated item/system groups are available; run-level stability "
            "cannot be estimated."
        )
    if not identical_groups:
        warnings.append(
            "No identical controls are declared; evaluator self-noise cannot be "
            "separated from real run differences."
        )
    if correct_runs == 0:
        warnings.append(
            "No outcome.correct values are present; this bundle cannot yet feed "
            "historical-response triage."
        )
    if output_digest_runs == 0:
        warnings.append(
            "No output artifact SHA-256 digests are present; artifact identity "
            "and replay comparisons are unavailable."
        )
    return {
        "schema_version": "trace-audit.v1",
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "benchmark_id": bundle.benchmark_id,
        "promotion_ceiling": "review",
        "confirmation_eligible": False,
        "method": "historical_trace_consistency",
        "sources": bundle.sources,
        "quality": {
            "runs": len(bundle.runs),
            "items": len(bundle.item_ids),
            "systems": len(bundle.system_ids),
            "status_counts": dict(sorted(status_counts.items())),
            "event_type_counts": dict(sorted(event_counts.items())),
            "runs_with_correct": correct_runs,
            "runs_with_score": score_runs,
            "runs_with_reward": reward_runs,
            "runs_with_output_digest": output_digest_runs,
            "repeated_item_system_groups": repeat_groups,
            "identical_control_groups": len(identical_groups),
            "infrastructure_failure_rate": infrastructure_rate,
            "warnings": warnings,
        },
        "thresholds": {
            "minimum_repeated_runs": minimum_repeated_runs,
            "score_spread_threshold": score_spread_threshold,
            "high_reward_threshold": high_reward_threshold,
            "infrastructure_rate_threshold": infrastructure_rate_threshold,
            "minimum_infrastructure_runs": minimum_infrastructure_runs,
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def trace_response_rows(bundle: TraceBundle) -> list[dict[str, Any]]:
    """Export correctness observations for ``triage-responses``.

    Attempts become stable panel columns (``system_id#attempt=N``) when any
    item/system pair has repeats; otherwise the system identifier is preserved.
    """

    repeated_systems = {
        system_id
        for (item_id, system_id), count in Counter(
            (run.item_id, run.system_id) for run in bundle.runs
        ).items()
        if count > 1
    }
    rows = []
    for run in bundle.runs:
        if run.outcome.correct is None:
            continue
        model_id = run.system_id
        if run.system_id in repeated_systems:
            model_id = f"{run.system_id}#attempt={run.attempt}"
        rows.append(
            {
                "item_id": run.item_id,
                "model_id": model_id,
                "correct": run.outcome.correct,
                "source_run_id": run.run_id,
            }
        )
    rows.sort(key=lambda row: (row["item_id"], row["model_id"]))
    return rows


def write_trace_audit_markdown(
    path: Path,
    result: dict[str, Any],
    *,
    top_k: int = 100,
) -> None:
    quality = result["quality"]
    candidates = result["candidates"][: max(0, top_k)]
    lines = [
        "# Historical trace audit",
        "",
        "> Archived traces provide observational evidence. Every candidate is "
        "review-only until an independent verifier or replay confirms the defect.",
        "",
        "## Summary",
        "",
        f"- Benchmark: `{result['benchmark_id']}`",
        f"- Runs: `{quality['runs']}`",
        f"- Items: `{quality['items']}`",
        f"- Systems: `{quality['systems']}`",
        f"- Repeated item/system groups: `{quality['repeated_item_system_groups']}`",
        f"- Identical-control groups: `{quality['identical_control_groups']}`",
        f"- Runs with correctness: `{quality['runs_with_correct']}`",
        f"- Runs with output digest: `{quality['runs_with_output_digest']}`",
        f"- Candidates: `{result['candidate_count']}`",
        "- Evidence ceiling: `review`",
        "",
    ]
    if quality["warnings"]:
        lines.extend(["## Quality warnings", ""])
        lines.extend(f"- {warning}" for warning in quality["warnings"])
        lines.append("")
    lines.extend(
        [
            f"## Top {len(candidates)} candidates",
            "",
            "| Confidence | Type | Items | Runs | Message |",
            "|---:|---|---|---:|---|",
        ]
    )
    for candidate in candidates:
        items = ", ".join(f"`{item}`" for item in candidate["item_ids"][:3])
        if len(candidate["item_ids"]) > 3:
            items += f" +{len(candidate['item_ids']) - 3}"
        message = str(candidate["message"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {candidate['confidence']:.2f} | "
            f"`{candidate['defect_type']}` | {items or 'dataset'} | "
            f"{len(candidate['run_ids'])} | {message} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
