from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .comparison import candidate_tier, compute_item_risk_score


SUPPORTED_SUFFIXES = {".json", ".jsonl"}
PANEL_KINDS = {
    "independent-models",
    "single-model-views",
    "repeated-runs",
    "unspecified",
}


@dataclass(frozen=True)
class ResponseObservation:
    item_id: str
    model_id: str
    correct: bool
    source: str


@dataclass
class ResponseMatrix:
    """A sparse item-by-model correctness matrix joined by stable identifiers."""

    values: dict[str, dict[str, bool]]
    sources: list[str]

    @property
    def item_ids(self) -> list[str]:
        return sorted(self.values)

    @property
    def model_ids(self) -> list[str]:
        return sorted({model for row in self.values.values() for model in row})

    def validate(self, *, minimum_models: int) -> None:
        if not self.values:
            raise ValueError("response matrix is empty")
        if minimum_models < 1:
            raise ValueError("minimum_models must be positive")
        if len(self.model_ids) < minimum_models:
            raise ValueError(
                f"response matrix has {len(self.model_ids)} model(s), below "
                f"minimum_models={minimum_models}"
            )


def _load_json_or_jsonl(path: Path) -> Any:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix.lower() == ".jsonl":
        rows: list[Any] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        return rows
    raise ValueError(
        f"unsupported response artifact {path}; expected one of "
        f"{sorted(SUPPORTED_SUFFIXES)}"
    )


def _expand_paths(paths: Iterable[Path]) -> list[Path]:
    expanded: list[Path] = []
    for raw_path in paths:
        path = raw_path.expanduser().resolve()
        if path.is_dir():
            children = sorted(
                child
                for child in path.iterdir()
                if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES
            )
            if not children:
                raise ValueError(f"response directory has no JSON/JSONL files: {path}")
            expanded.extend(children)
        elif path.is_file():
            expanded.append(path)
        else:
            raise FileNotFoundError(path)
    if not expanded:
        raise ValueError("at least one response artifact is required")
    duplicates = [path for path, count in Counter(expanded).items() if count > 1]
    if duplicates:
        raise ValueError(f"response artifact provided more than once: {duplicates[0]}")
    return expanded


def _strict_bool(value: Any, *, location: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value in (0, 1):
        return bool(value)
    raise ValueError(
        f"{location}: correct must be a JSON boolean or integer 0/1, "
        f"not {value!r}"
    )


def _nonempty_identifier(value: Any, *, name: str, location: str) -> str:
    if value is None:
        raise ValueError(f"{location}: missing {name}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{location}: empty {name}")
    return text


def _rows_from_document(document: Any, *, path: Path) -> list[tuple[str | None, Any]]:
    """Return ``(item_id_from_container, row)`` pairs."""
    if isinstance(document, list):
        return [(None, row) for row in document]
    if not isinstance(document, dict):
        raise ValueError(f"{path}: root must be an object or array")
    if isinstance(document.get("items"), dict):
        return [(str(item_id), row) for item_id, row in document["items"].items()]
    if isinstance(document.get("responses"), list):
        return [(None, row) for row in document["responses"]]
    return [(None, document)]


def load_response_matrix(
    paths: Iterable[Path],
    *,
    item_id_field: str = "id",
    model_id_field: str = "model_id",
    correct_field: str = "correct",
) -> ResponseMatrix:
    """Load wide, long, or one-file-per-model correctness artifacts.

    Supported row shapes:

    - wide: ``{"id": "q1", "correct": {"model-a": true, ...}}``;
    - long: ``{"item_id": "q1", "model_id": "model-a", "correct": true}``;
    - per-model files: scalar ``correct`` rows, with the filename stem used as
      the model identifier when ``model_id`` is absent;
    - feature documents: ``{"items": {"q1": {"correct": {...}}}}``.

    Duplicate ``(item_id, model_id)`` pairs are rejected even when their values
    agree.  Silent duplicate weighting would corrupt error rates.
    """

    files = _expand_paths(paths)
    values: dict[str, dict[str, bool]] = defaultdict(dict)
    pair_sources: dict[tuple[str, str], str] = {}
    for path in files:
        document = _load_json_or_jsonl(path)
        rows = _rows_from_document(document, path=path)
        for row_index, (container_item_id, row) in enumerate(rows):
            location = f"{path}:{row_index + 1}"
            if not isinstance(row, dict):
                raise ValueError(f"{location}: response row must be an object")
            item_value = (
                container_item_id
                if container_item_id is not None
                else row.get(item_id_field, row.get("item_id"))
            )
            item_id = _nonempty_identifier(
                item_value, name="item_id", location=location
            )
            if correct_field not in row:
                raise ValueError(f"{location}: missing {correct_field}")
            correct_value = row[correct_field]
            if isinstance(correct_value, dict):
                if not correct_value:
                    raise ValueError(f"{location}: empty correctness mapping")
                observations = [
                    (
                        _nonempty_identifier(
                            model, name="model_id", location=location
                        ),
                        _strict_bool(
                            value,
                            location=f"{location}:{correct_field}.{model}",
                        ),
                    )
                    for model, value in correct_value.items()
                ]
            else:
                model_value = row.get(model_id_field, row.get("model"))
                if model_value is None:
                    model_value = path.stem
                model_id = _nonempty_identifier(
                    model_value, name="model_id", location=location
                )
                observations = [
                    (
                        model_id,
                        _strict_bool(correct_value, location=location),
                    )
                ]
            for model_id, correct in observations:
                pair = (item_id, model_id)
                if pair in pair_sources:
                    raise ValueError(
                        f"{location}: duplicate response pair {pair!r}; "
                        f"first seen at {pair_sources[pair]}"
                    )
                pair_sources[pair] = location
                values[item_id][model_id] = correct
    return ResponseMatrix(
        values={item_id: dict(row) for item_id, row in values.items()},
        sources=[str(path) for path in files],
    )


def _percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """Tie-aware percentile ranks equivalent to average-rank normalization."""
    if not values:
        return {}
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError("candidate scores must be finite")
    if len(values) == 1:
        return {next(iter(values)): 0.0}
    groups: dict[float, list[str]] = defaultdict(list)
    for item_id, value in values.items():
        groups[float(value)].append(item_id)
    result: dict[str, float] = {}
    number_before = 0
    denominator = len(values) - 1
    for value in sorted(groups):
        members = groups[value]
        average_zero_based_rank = number_before + (len(members) - 1) / 2.0
        percentile = average_zero_based_rank / denominator
        for item_id in members:
            result[item_id] = percentile
        number_before += len(members)
    return result


def _wilson_interval(wrong: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0:
        return [0.0, 1.0]
    proportion = wrong / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    radius = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return [max(0.0, centre - radius), min(1.0, centre + radius)]


def _audit_scores(
    report: dict[str, Any],
    item_ids: set[str],
    *,
    mode: str,
    include_defects: set[str] | None,
) -> tuple[dict[str, float], dict[str, int], dict[str, Any]]:
    if mode not in {"priority-risk", "risk", "max-confidence"}:
        raise ValueError(f"unsupported audit score mode: {mode}")
    violations_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in report.get("violations", []):
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("item_id", "")).strip()
        if not item_id or item_id not in item_ids:
            continue
        if include_defects and raw.get("defect_type") not in include_defects:
            continue
        if raw.get("defect_scope", "substantive") == "operational":
            continue
        violations_by_item[item_id].append(raw)

    scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    for item_id in sorted(item_ids):
        violations = violations_by_item.get(item_id, [])
        counts[item_id] = len(violations)
        if mode == "priority-risk":
            scores[item_id] = (
                compute_item_risk_score(violations)
                if candidate_tier(violations) == "priority"
                else 0.0
            )
        elif mode == "risk":
            scores[item_id] = compute_item_risk_score(violations)
        else:
            scores[item_id] = max(
                (float(row.get("confidence", 0.0) or 0.0) for row in violations),
                default=0.0,
            )
    report_item_ids = {
        str(row.get("item_id", "")).strip()
        for row in report.get("violations", [])
        if isinstance(row, dict) and str(row.get("item_id", "")).strip()
    }
    metadata = {
        "violations_used": sum(counts.values()),
        "items_with_audit_signal": sum(score > 0 for score in scores.values()),
        "items_excluded_from_fusion_as_exploratory": (
            sum(
                bool(violations_by_item.get(item_id))
                and candidate_tier(violations_by_item[item_id]) != "priority"
                for item_id in item_ids
            )
            if mode == "priority-risk"
            else 0
        ),
        "report_items_without_responses": len(report_item_ids - item_ids),
        "response_items_without_findings": sum(count == 0 for count in counts.values()),
    }
    return scores, counts, metadata


def _matrix_quality(
    matrix: ResponseMatrix,
    *,
    minimum_responses_per_item: int,
    minimum_model_coverage: float,
) -> dict[str, Any]:
    if minimum_responses_per_item < 1:
        raise ValueError("minimum_responses_per_item must be positive")
    if not 0.0 <= minimum_model_coverage <= 1.0:
        raise ValueError("minimum_model_coverage must be between 0 and 1")
    item_ids = matrix.item_ids
    model_ids = matrix.model_ids
    model_counts = Counter(
        model for row in matrix.values.values() for model in row
    )
    model_coverage = {
        model: model_counts[model] / len(item_ids) for model in model_ids
    }
    response_counts = {
        item_id: len(matrix.values[item_id]) for item_id in item_ids
    }
    qualified_models = sorted(
        model
        for model, coverage in model_coverage.items()
        if coverage >= minimum_model_coverage
    )
    patterns = {
        tuple(
            matrix.values[item_id].get(model)
            for item_id in item_ids
        )
        for model in qualified_models
    }
    warnings: list[str] = []
    low_coverage_models = sorted(
        model
        for model, coverage in model_coverage.items()
        if coverage < minimum_model_coverage
    )
    if low_coverage_models:
        warnings.append(
            f"{len(low_coverage_models)} model(s) are below the requested "
            f"{minimum_model_coverage:.0%} item coverage"
        )
    minimum_unique_patterns = min(3, len(qualified_models))
    panel_behavior_eligible = (
        bool(qualified_models)
        and len(patterns) >= minimum_unique_patterns
    )
    if not panel_behavior_eligible:
        warnings.append(
            "fewer than three unique model correctness patterns; behavioral "
            "diversity is weak and response fusion is disabled"
        )
    eligible_items = [
        item_id
        for item_id in item_ids
        if sum(model in matrix.values[item_id] for model in qualified_models)
        >= minimum_responses_per_item
    ]
    return {
        "n_items": len(item_ids),
        "n_models": len(model_ids),
        "n_observations": sum(response_counts.values()),
        "matrix_density": (
            sum(response_counts.values()) / (len(item_ids) * len(model_ids))
        ),
        "minimum_responses_per_item": minimum_responses_per_item,
        "eligible_items": len(eligible_items),
        "ineligible_items": len(item_ids) - len(eligible_items),
        "minimum_model_coverage": minimum_model_coverage,
        "low_coverage_models": low_coverage_models,
        "qualified_models": qualified_models,
        "qualified_model_count": len(qualified_models),
        "model_coverage": model_coverage,
        "unique_model_correctness_patterns": len(patterns),
        "panel_behavior_eligible": panel_behavior_eligible,
        "warnings": warnings,
    }


def build_response_triage(
    matrix: ResponseMatrix,
    audit_report: dict[str, Any],
    *,
    minimum_models: int = 5,
    minimum_responses_per_item: int = 5,
    minimum_model_coverage: float = 0.8,
    audit_score_mode: str = "priority-risk",
    include_defects: set[str] | None = None,
    panel_kind: str = "unspecified",
) -> dict[str, Any]:
    """Fuse archived multi-model error rates with BenchAudit review scores.

    The result is a ranking artifact, not a defect finding.  Every row has a
    hard ``review`` ceiling, including rows supported by confirmed findings in
    the source audit report.
    """

    if panel_kind not in PANEL_KINDS:
        raise ValueError(
            f"unsupported panel_kind={panel_kind!r}; expected one of "
            f"{sorted(PANEL_KINDS)}"
        )
    matrix.validate(minimum_models=minimum_models)
    quality = _matrix_quality(
        matrix,
        minimum_responses_per_item=minimum_responses_per_item,
        minimum_model_coverage=minimum_model_coverage,
    )
    if quality["qualified_model_count"] < minimum_models:
        raise ValueError(
            f"only {quality['qualified_model_count']} model(s) meet "
            f"minimum_model_coverage={minimum_model_coverage:.3f}; "
            f"minimum_models={minimum_models}"
        )
    if panel_kind == "unspecified":
        quality["warnings"].append(
            "panel provenance is unspecified; no cross-model independence "
            "claim is supported"
        )
    elif panel_kind == "single-model-views":
        quality["warnings"].append(
            "panel contains correlated views of one model; this is a degraded "
            "observational fallback, not independent multi-model evidence"
        )
    elif panel_kind == "repeated-runs":
        quality["warnings"].append(
            "panel contains repeated runs; run variance is not cross-model "
            "independence"
        )
    item_ids = matrix.item_ids
    item_set = set(item_ids)
    audit_scores, audit_counts, audit_metadata = _audit_scores(
        audit_report,
        item_set,
        mode=audit_score_mode,
        include_defects=include_defects,
    )
    audit_percentiles = _percentile_ranks(audit_scores)

    raw_error_rate: dict[str, float] = {}
    response_counts: dict[str, int] = {}
    wrong_counts: dict[str, int] = {}
    eligible: set[str] = set()
    qualified_models = set(quality["qualified_models"])
    panel_behavior_eligible = bool(quality["panel_behavior_eligible"])
    for item_id in item_ids:
        responses = {
            model: correct
            for model, correct in matrix.values[item_id].items()
            if model in qualified_models
        }
        total = len(responses)
        wrong = sum(not correct for correct in responses.values())
        response_counts[item_id] = total
        wrong_counts[item_id] = wrong
        raw_error_rate[item_id] = wrong / total
        if panel_behavior_eligible and total >= minimum_responses_per_item:
            eligible.add(item_id)
    error_percentiles = _percentile_ranks(
        {item_id: raw_error_rate[item_id] for item_id in eligible}
    )

    rows: list[dict[str, Any]] = []
    for item_id in item_ids:
        fusion_applied = item_id in eligible
        behavior_percentile = (
            error_percentiles[item_id] if fusion_applied else None
        )
        fused_score = (
            0.5 * audit_percentiles[item_id] + 0.5 * behavior_percentile
            if behavior_percentile is not None
            else audit_percentiles[item_id]
        )
        rows.append(
            {
                "item_id": item_id,
                "audit_score": audit_scores[item_id],
                "audit_percentile": audit_percentiles[item_id],
                "audit_finding_count": audit_counts[item_id],
                "responses": response_counts[item_id],
                "wrong_responses": wrong_counts[item_id],
                "error_rate": raw_error_rate[item_id],
                "error_rate_ci95": _wilson_interval(
                    wrong_counts[item_id], response_counts[item_id]
                ),
                "behavior_percentile": behavior_percentile,
                "fusion_applied": fusion_applied,
                "fused_score": fused_score,
                "evidence_tier": "review",
                "review_only": True,
                "confirmation_eligible": False,
                "signal_semantics": (
                    "observational candidate priority; high model error may "
                    "reflect difficulty rather than a benchmark defect"
                ),
            }
        )
    rows.sort(key=lambda row: (-row["fused_score"], row["item_id"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank

    source_hashes = {}
    for source in matrix.sources:
        path = Path(source)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        source_hashes[source] = digest
    return {
        "schema_version": 1,
        "method": "audit_error_rate_fusion",
        "panel_kind": panel_kind,
        "panel_independence": {
            "claimed": panel_kind == "independent-models",
            "basis": (
                "caller-declared model identifiers; not cryptographically verified"
                if panel_kind == "independent-models"
                else "no independent-model claim"
            ),
        },
        "promotion_ceiling": "review",
        "confirmation_eligible": False,
        "fusion_rule": (
            "0.5 * tie-aware percentile(audit_score) + "
            "0.5 * tie-aware percentile(per-item multi-model error_rate)"
        ),
        "audit_score_mode": audit_score_mode,
        "include_defects": sorted(include_defects or []),
        "minimum_models": minimum_models,
        "quality": quality,
        "audit": audit_metadata,
        "sources": {
            "response_sha256": source_hashes,
        },
        "models": matrix.model_ids,
        "qualified_models": quality["qualified_models"],
        "items": rows,
    }


def write_response_triage_markdown(
    path: Path, result: dict[str, Any], *, top_k: int = 50
) -> None:
    quality = result["quality"]
    top_k = max(0, min(top_k, len(result["items"])))
    lines = [
        "# Historical-response candidate triage",
        "",
        "> Multi-model error rate is an observational prioritization signal. "
        "It may measure task difficulty rather than a benchmark defect, so every "
        "row remains review-only.",
        "",
        "## Summary",
        "",
        f"- Items: `{quality['n_items']}`",
        f"- Models: `{quality['n_models']}`",
        f"- Observations: `{quality['n_observations']}`",
        f"- Matrix density: `{quality['matrix_density']:.3f}`",
        f"- Behavior-eligible items: `{quality['eligible_items']}`",
        f"- Unique model correctness patterns: "
        f"`{quality['unique_model_correctness_patterns']}`",
        f"- Panel eligible for behavior fusion: "
        f"`{str(quality['panel_behavior_eligible']).lower()}`",
        f"- Audit items with signal: `{result['audit']['items_with_audit_signal']}`",
        "- Evidence ceiling: `review`",
        "",
    ]
    if quality["warnings"]:
        lines.extend(["## Quality warnings", ""])
        lines.extend(f"- {warning}" for warning in quality["warnings"])
        lines.append("")
    lines.extend(
        [
            f"## Top {top_k} candidates",
            "",
            "| Rank | Item | Fused | Audit | Error rate | Responses | 95% CI |",
            "|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in result["items"][:top_k]:
        interval = row["error_rate_ci95"]
        lines.append(
            f"| {row['rank']} | `{row['item_id']}` | {row['fused_score']:.3f} | "
            f"{row['audit_score']:.3f} | {row['error_rate']:.3f} | "
            f"{row['responses']} | [{interval[0]:.3f}, {interval[1]:.3f}] |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
