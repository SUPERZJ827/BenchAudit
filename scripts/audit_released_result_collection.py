#!/usr/bin/env python3
"""Audit the collected SQLBench/DBCode released result artifacts.

This experiment is deliberately zero-API. It converts heterogeneous published
results into TraceBundle observations, runs the generic review-only analyzers,
and reports evaluator/ranking sensitivity. Dataset-specific parsing stays in
this script; the reusable evidence and safety policy live in ``benchcore``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from benchcore.released_results import (
    ReleasedResultMapping,
    ReleasedResultSource,
    adapt_released_results,
    analyze_released_results,
)
from benchcore.trace_bundle import analyze_trace_bundle


_TARGET_RE = re.compile(r"_to_([a-z0-9]+)_", re.I)
_MATCH_RE = re.compile(r"^Match (OK|Fail)\s+\S+\s+pred:\s*(.*)$")
_EXEC_RE = re.compile(r"^Exec\s+(OK|Fail)\s+\S+\s+pred:\s*(.*)$")
_GOLD_RE = re.compile(r"^\s+\S+\s+gold:\s*(.*)$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    result = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            result.append(row)
    return result


def _extract_answer(row: dict[str, Any], field: str) -> Any:
    value = row.get(field)
    if isinstance(value, dict):
        if "Answer" in value:
            return value["Answer"]
        content = value.get("content")
        if isinstance(content, str):
            return content
    return value


def _manifest_row(path: Path, root: Path, *, role: str) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)),
        "role": role,
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _sql_dialect_sources(
    collection: Path,
    output: Path,
) -> tuple[list[ReleasedResultSource], list[dict[str, Any]]]:
    root = collection / "SQLBench" / "SQL_Dialect_Translation"
    result_root = root / "different_model_outputs"
    score_root = root / "scores" / "sqlglot_syntax_validation"
    normalized_root = output / "normalized" / "sql_dialect"
    sources = []
    manifest = []

    score_index: dict[tuple[str, str], Path] = {}
    for score_path in sorted(score_root.glob("*/*.jsonl")):
        first = _load_jsonl(score_path)[:1]
        if not first:
            continue
        target = str(first[0].get("target_dialect") or "")
        key = (score_path.parent.name, target)
        if key in score_index:
            raise ValueError(f"duplicate SQL syntax sidecar for {key}")
        score_index[key] = score_path

    for result_path in sorted(result_root.glob("*/*.json")):
        model = result_path.parent.name
        match = _TARGET_RE.search(result_path.name)
        if not match:
            raise ValueError(f"cannot infer target dialect from {result_path}")
        target = match.group(1).casefold()
        score_path = score_index.get((model, target))
        if score_path is None:
            raise ValueError(f"missing SQL syntax sidecar for {(model, target)}")

        rows = json.loads(result_path.read_text(encoding="utf-8"))
        sidecars = _load_jsonl(score_path)
        if not isinstance(rows, list) or len(rows) != len(sidecars):
            raise ValueError(
                f"SQL result/sidecar length mismatch: {result_path} "
                f"({len(rows)}) vs {score_path} ({len(sidecars)})"
            )
        by_index = {int(row["record_index"]): row for row in sidecars}
        normalized = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"{result_path}[{index}]: expected object")
            sidecar = by_index.get(index)
            if sidecar is None:
                raise ValueError(f"{score_path}: missing record_index={index}")
            prediction = _extract_answer(row, "result_json")
            prediction_text = (
                prediction
                if isinstance(prediction, str)
                else json.dumps(prediction, ensure_ascii=False, sort_keys=True)
            )
            if _sha256_text(prediction_text) != sidecar.get("answer_sha256"):
                raise ValueError(
                    f"{result_path}[{index}]: answer hash disagrees with sidecar"
                )
            reference = row.get(target)
            if reference is None:
                raise ValueError(
                    f"{result_path}[{index}]: missing target reference {target}"
                )
            parse = sidecar.get("parse") or {}
            reference_parse = sidecar.get("reference_parse") or {}
            normalized.append({
                "item_id": sidecar["task_sha256"],
                "prediction": prediction,
                "reference": reference,
                "prediction_valid": parse.get("syntax_valid"),
                "reference_valid": reference_parse.get("syntax_valid"),
                "dataset_id": sidecar.get("dataset_id"),
                "target_dialect": target,
            })

        normalized_path = normalized_root / model / f"{target}.jsonl"
        _write_jsonl(normalized_path, normalized)
        sources.append(
            ReleasedResultSource(
                normalized_path,
                system_id=model,
                mapping=ReleasedResultMapping(
                    item_id="item_id",
                    prediction="prediction",
                    reference="reference",
                    evaluations=(("sqlglot_prediction_syntax", "prediction_valid"),),
                    reference_evaluations=(
                        ("sqlglot_reference_syntax", "reference_valid"),
                    ),
                    reference_contract="sql",
                ),
            )
        )
        manifest.extend([
            _manifest_row(result_path, collection, role="released_outputs"),
            _manifest_row(score_path, collection, role="published_evaluator"),
        ])
    return sources, manifest


def _parse_match_file(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows = []
    index = 0
    while index < len(lines):
        match = _MATCH_RE.match(lines[index])
        if match is None:
            index += 1
            continue
        if index + 1 >= len(lines):
            raise ValueError(f"{path}:{index + 1}: truncated match record")
        gold = _GOLD_RE.match(lines[index + 1])
        if gold is None:
            raise ValueError(f"{path}:{index + 2}: missing gold line")
        rows.append({
            "match_verdict": match.group(1) == "OK",
            "prediction": match.group(2).strip(),
            "reference": gold.group(1).strip(),
        })
        index += 2
    if rows:
        return rows
    return [
        {
            "match_verdict": row["verdict"],
            "prediction": row["prediction"],
            "reference": row["reference"],
        }
        for row in _parse_pred_semicolon(path, lines)
    ]


def _parse_pred_semicolon(
    path: Path, lines: Sequence[str],
) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(lines, start=1):
        if not line.startswith("Pred "):
            continue
        parts = line.split(";", 4)
        if len(parts) != 5:
            raise ValueError(f"{path}:{line_number}: malformed evaluator record")
        status, _difficulty, _database, reference, prediction = parts
        verdict = status.removeprefix("Pred ").strip()
        if verdict not in {"OK", "Fail"}:
            raise ValueError(f"{path}:{line_number}: unknown verdict {verdict!r}")
        rows.append({
            "verdict": verdict == "OK",
            "prediction": prediction.strip(),
            "reference": reference.strip(),
        })
    return rows


def _parse_exec_file(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    structured = []
    index = 0
    while index < len(lines):
        match = _EXEC_RE.match(lines[index])
        if match is None:
            index += 1
            continue
        if index + 1 >= len(lines):
            raise ValueError(f"{path}:{index + 1}: truncated execution record")
        gold = _GOLD_RE.match(lines[index + 1])
        if gold is None:
            raise ValueError(f"{path}:{index + 2}: missing execution gold line")
        structured.append({
            "exec_verdict": match.group(1) == "OK",
            "prediction": match.group(2).strip(),
            "reference": gold.group(1).strip(),
        })
        index += 2
    if structured:
        return structured

    return [
        {
            "exec_verdict": row["verdict"],
            "prediction": row["prediction"],
            "reference": row["reference"],
        }
        for row in _parse_pred_semicolon(path, lines)
    ]


def _portuguese_spider_sources(
    collection: Path,
    output: Path,
) -> tuple[list[ReleasedResultSource], list[dict[str, Any]], dict[str, int]]:
    root = collection / "SQLBench" / "PortugueseSpider" / "scores"
    normalized_root = output / "normalized" / "portuguese_spider"
    sources = []
    manifest = []
    unmatched_match = 0
    unmatched_exec = 0
    pair_count = 0

    for match_path in sorted(root.rglob("*_eval_match_*.txt")):
        exec_path = match_path.with_name(
            match_path.name.replace("_eval_match_", "_eval_exec_", 1)
        )
        if not exec_path.is_file():
            continue
        match_rows = _parse_match_file(match_path)
        exec_rows = _parse_exec_file(exec_path)
        exec_queues: dict[
            tuple[str, str], deque[dict[str, Any]]
        ] = defaultdict(deque)
        for row in exec_rows:
            exec_queues[(row["reference"], row["prediction"])].append(row)

        normalized = []
        for row in match_rows:
            key = (row["reference"], row["prediction"])
            if not exec_queues[key]:
                unmatched_match += 1
                continue
            execution = exec_queues[key].popleft()
            item_id = _sha256_text(f"{key[0]}\0{key[1]}")
            normalized.append({
                "item_id": item_id,
                "prediction": row["prediction"],
                "reference": row["reference"],
                "match_verdict": row["match_verdict"],
                "exec_verdict": execution["exec_verdict"],
            })
        unmatched_exec += sum(
            len(queue) for queue in exec_queues.values()
        )
        if not normalized:
            continue
        pair_count += len(normalized)
        relative = match_path.relative_to(root)
        system_id = str(relative.with_suffix("")).replace("/", "::")
        normalized_path = (
            normalized_root
            / relative.parent
            / f"{match_path.stem}.jsonl"
        )
        _write_jsonl(normalized_path, normalized)
        sources.append(
            ReleasedResultSource(
                normalized_path,
                system_id=system_id,
                mapping=ReleasedResultMapping(
                    item_id="item_id",
                    prediction="prediction",
                    reference="reference",
                    evaluations=(
                        ("structural_match", "match_verdict"),
                        ("database_execution", "exec_verdict"),
                    ),
                    reference_contract="sql",
                ),
            )
        )
        manifest.extend([
            _manifest_row(match_path, collection, role="match_evaluator"),
            _manifest_row(exec_path, collection, role="execution_evaluator"),
        ])
    return sources, manifest, {
        "paired_rows": pair_count,
        "unmatched_match_rows": unmatched_match,
        "unmatched_exec_rows": unmatched_exec,
    }


def _dbcode_sources(
    collection: Path,
    output: Path,
) -> tuple[list[ReleasedResultSource], list[dict[str, Any]]]:
    root = collection / "DBCode"
    normalized_root = output / "normalized" / "dbcode"
    sources = []
    manifest = []
    for source_path in sorted(root.glob("*/different_model_outputs/**/*.json")):
        document = json.loads(source_path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        relative = source_path.relative_to(root)
        database = relative.parts[0].split("_", 1)[0].casefold()
        mode = relative.parts[2] if len(relative.parts) > 3 else "unknown"
        prediction_field = (
            "response_ndep"
            if any("response_ndep" in row for row in document.values())
            else "response"
        )
        normalized = []
        for key, row in document.items():
            if not isinstance(row, dict):
                continue
            normalized.append({
                "item_id": f"{database}:{key}",
                "prediction": _extract_answer(row, prediction_field),
                "reference": row.get("origin_code"),
                "full_harness": row.get("is_success"),
                "function_tests": row.get("is_success_func"),
            })
        if not normalized:
            continue
        normalized_path = normalized_root / relative.with_suffix(".jsonl")
        _write_jsonl(normalized_path, normalized)
        evaluations = []
        if any(row["full_harness"] is not None for row in normalized):
            evaluations.append(("full_harness", "full_harness"))
        if any(row["function_tests"] is not None for row in normalized):
            evaluations.append(("function_tests", "function_tests"))
        system_id = f"{database}:{mode}:{source_path.stem}"
        sources.append(
            ReleasedResultSource(
                normalized_path,
                system_id=system_id,
                mapping=ReleasedResultMapping(
                    item_id="item_id",
                    prediction="prediction",
                    reference="reference",
                    evaluations=tuple(evaluations),
                    reference_contract="code",
                ),
            )
        )
        manifest.append(
            _manifest_row(source_path, collection, role="released_outputs_and_scores")
        )
    return sources, manifest


def _verdict_counts(bundle) -> dict[str, dict[str, int]]:
    result: dict[str, Counter[str]] = defaultdict(Counter)
    for run in bundle.runs:
        for evaluation in run.evaluations:
            result[evaluation.evaluator_id][evaluation.verdict] += 1
    return {
        evaluator_id: dict(sorted(counts.items()))
        for evaluator_id, counts in sorted(result.items())
    }


def _contingency(bundle, first: str, second: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for run in bundle.runs:
        verdicts = {
            evaluation.evaluator_id: evaluation.verdict
            for evaluation in run.evaluations
        }
        if first in verdicts and second in verdicts:
            counts[f"{verdicts[first]}_{verdicts[second]}"] += 1
    return dict(sorted(counts.items()))


def _system_rates(bundle, evaluator_id: str) -> dict[str, float]:
    totals: Counter[str] = Counter()
    passes: Counter[str] = Counter()
    for run in bundle.runs:
        for evaluation in run.evaluations:
            if evaluation.evaluator_id != evaluator_id:
                continue
            if evaluation.verdict not in {"pass", "fail"}:
                continue
            totals[run.system_id] += 1
            passes[run.system_id] += evaluation.verdict == "pass"
    return {
        system_id: passes[system_id] / total
        for system_id, total in totals.items()
        if total
    }


def _ranking_sensitivity(
    bundle,
    first: str,
    second: str,
) -> dict[str, Any]:
    first_rates = _system_rates(bundle, first)
    second_rates = _system_rates(bundle, second)
    systems = sorted(set(first_rates) & set(second_rates))
    concordant = 0
    discordant = 0
    tied = 0
    changed_positions = 0

    first_rank = {
        system: rank
        for rank, system in enumerate(
            sorted(systems, key=lambda row: (-first_rates[row], row)), start=1
        )
    }
    second_rank = {
        system: rank
        for rank, system in enumerate(
            sorted(systems, key=lambda row: (-second_rates[row], row)), start=1
        )
    }
    for left_index, left in enumerate(systems):
        changed_positions += first_rank[left] != second_rank[left]
        for right in systems[left_index + 1:]:
            first_delta = first_rates[left] - first_rates[right]
            second_delta = second_rates[left] - second_rates[right]
            product = first_delta * second_delta
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
            else:
                tied += 1
    comparable = concordant + discordant
    tau = (
        (concordant - discordant) / comparable
        if comparable
        else None
    )
    return {
        "evaluator_a": first,
        "evaluator_b": second,
        "systems": len(systems),
        "pairwise_concordant": concordant,
        "pairwise_discordant": discordant,
        "pairwise_tied_or_unresolved": tied,
        "pairwise_kendall_tau_without_ties": tau,
        "systems_with_changed_rank_position": changed_positions,
        "rates": {
            system: {
                first: first_rates[system],
                second: second_rates[system],
                "rank_a": first_rank[system],
                "rank_b": second_rank[system],
            }
            for system in systems
        },
    }


def _binary_ranking_metrics(
    scores: dict[str, float],
    positives: set[str],
) -> dict[str, Any]:
    ranked = sorted(scores, key=lambda item_id: (-scores[item_id], item_id))
    negatives = set(scores) - positives
    pair_score = 0.0
    pairs = 0
    for positive in positives:
        for negative in negatives:
            pairs += 1
            if scores[positive] > scores[negative]:
                pair_score += 1.0
            elif scores[positive] == scores[negative]:
                pair_score += 0.5
    result: dict[str, Any] = {
        "items": len(scores),
        "positive_proxy_items": len(positives),
        "auroc": pair_score / pairs if pairs else None,
    }
    for cutoff in (20, 50, len(positives), 100):
        if cutoff <= 0:
            continue
        selected = ranked[: min(cutoff, len(ranked))]
        true_positive = len(set(selected) & positives)
        result[f"precision_at_{cutoff}"] = (
            true_positive / len(selected) if selected else None
        )
        result[f"recall_at_{cutoff}"] = (
            true_positive / len(positives) if positives else None
        )
    return result


def _sql_proxy_ablation(bundle) -> dict[str, Any]:
    """Evaluate cheap signals against the published parser-failure proxy.

    The proxy is not semantic ground truth. The diagnostic flag and prediction
    failure rate are computed without reading the published reference verdict.
    """

    item_prediction_verdicts: dict[str, list[str]] = defaultdict(list)
    positives: set[str] = set()
    diagnostic_items: set[str] = set()
    all_items = set()
    for run in bundle.runs:
        all_items.add(run.item_id)
        for evaluation in run.evaluations:
            if evaluation.evaluator_id == "sqlglot_prediction_syntax":
                item_prediction_verdicts[run.item_id].append(evaluation.verdict)
        metadata = run.metadata.get("released_result", {})
        if not isinstance(metadata, dict):
            continue
        if metadata.get("reference_integrity_flags"):
            diagnostic_items.add(run.item_id)
        for evaluation in metadata.get("reference_evaluations", []):
            if (
                isinstance(evaluation, dict)
                and evaluation.get("evaluator_id") == "sqlglot_reference_syntax"
                and evaluation.get("verdict") == "fail"
            ):
                positives.add(run.item_id)

    behavior_scores = {}
    for item_id in all_items:
        verdicts = [
            verdict
            for verdict in item_prediction_verdicts.get(item_id, [])
            if verdict in {"pass", "fail"}
        ]
        behavior_scores[item_id] = (
            sum(verdict == "fail" for verdict in verdicts) / len(verdicts)
            if verdicts
            else 0.0
        )
    diagnostic_scores = {
        item_id: float(item_id in diagnostic_items) for item_id in all_items
    }
    fusion_scores = {
        item_id: 2.0 * diagnostic_scores[item_id] + behavior_scores[item_id]
        for item_id in all_items
    }
    prevalence = len(positives) / len(all_items) if all_items else 0.0
    random_generator = random.Random(20260727)
    random_precision_at_proxy_count = []
    population = sorted(all_items)
    for _ in range(1000):
        shuffled = population.copy()
        random_generator.shuffle(shuffled)
        selected = shuffled[: len(positives)]
        random_precision_at_proxy_count.append(
            len(set(selected) & positives) / len(selected) if selected else 0.0
        )
    return {
        "proxy_label": "published_sqlglot_reference_invalid",
        "proxy_is_semantic_ground_truth": False,
        "feature_label_separation": (
            "behavior and literal-diagnostic scores are computed before "
            "consulting reference parser verdicts"
        ),
        "prevalence": prevalence,
        "variants": {
            "A_prediction_failure_rate": _binary_ranking_metrics(
                behavior_scores, positives
            ),
            "B_literal_diagnostic_only": _binary_ranking_metrics(
                diagnostic_scores, positives
            ),
            "C_diagnostic_then_behavior": _binary_ranking_metrics(
                fusion_scores, positives
            ),
        },
        "random_control": {
            "trials": len(random_precision_at_proxy_count),
            "seed": 20260727,
            "expected_precision": prevalence,
            "mean_precision_at_positive_count": (
                sum(random_precision_at_proxy_count)
                / len(random_precision_at_proxy_count)
            ),
            "p05_precision_at_positive_count": sorted(
                random_precision_at_proxy_count
            )[49],
            "p95_precision_at_positive_count": sorted(
                random_precision_at_proxy_count
            )[949],
        },
    }


def _corpus_result(bundle, *, ranking_pair: tuple[str, str] | None) -> dict[str, Any]:
    trace = analyze_trace_bundle(bundle)
    released = analyze_released_results(bundle)
    result = {
        "coverage": released["coverage"],
        "verdict_counts": _verdict_counts(bundle),
        "trace_candidate_count": trace["candidate_count"],
        "trace_candidate_types": dict(sorted(Counter(
            row["defect_type"] for row in trace["candidates"]
        ).items())),
        "released_candidate_count": released["candidate_count"],
        "released_candidate_types": dict(sorted(Counter(
            row["defect_type"] for row in released["candidates"]
        ).items())),
        "trace_candidates": trace["candidates"],
        "released_candidates": released["candidates"],
    }
    if ranking_pair is not None:
        result["contingency"] = _contingency(bundle, *ranking_pair)
        result["ranking_sensitivity"] = _ranking_sensitivity(
            bundle, *ranking_pair
        )
    if bundle.benchmark_id == "sql-dialect-translation":
        result["proxy_ablation"] = _sql_proxy_ablation(bundle)
    return result


def _fmt_percent(value: float) -> str:
    return f"{100 * value:.2f}%"


def _wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return center - margin, center + margin


def _write_markdown(path: Path, summary: dict[str, Any]) -> None:
    sql = summary["corpora"]["sql_dialect"]
    pt = summary["corpora"]["portuguese_spider"]
    db = summary["corpora"]["dbcode"]
    lines = [
        "# Released-result evidence audit",
        "",
        "> Zero API calls. Historical outputs and verdicts are observational, "
        "review-only evidence; they do not automatically confirm defects.",
        "",
        "## Coverage",
        "",
        "| Corpus | Runs | Items | Systems | Trace candidates | Reference candidates |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in (
        ("SQL Dialect Translation", sql),
        ("PortugueseSpider", pt),
        ("DBCode", db),
    ):
        coverage = result["coverage"]
        lines.append(
            f"| {name} | {coverage['runs']} | {coverage['items']} | "
            f"{coverage['systems']} | {result['trace_candidate_count']} | "
            f"{result['released_candidate_count']} |"
        )

    sql_ref = sql["released_candidates"]
    diagnostic = next(
        (
            row for row in sql_ref
            if row["defect_type"] == "reference_diagnostic_payload"
        ),
        None,
    )
    reference_failure = next(
        (
            row for row in sql_ref
            if row["defect_type"] == "published_reference_evaluator_failure"
        ),
        None,
    )
    lines.extend([
        "",
        "## Main observations",
        "",
        "### SQL Dialect Translation",
        "",
        f"- Reference diagnostic payloads: "
        f"{diagnostic['evidence']['affected_items'] if diagnostic else 0} items.",
        f"- Published SQLGlot reference failures: "
        f"{reference_failure['evidence']['affected_items'] if reference_failure else 0} items.",
        "- These are aggregated dataset-level review candidates, not thousands "
        "of duplicated item-level critical findings.",
    ])
    ablation = sql.get("proxy_ablation", {})
    if ablation:
        behavior = ablation["variants"]["A_prediction_failure_rate"]
        diagnostic = ablation["variants"]["B_literal_diagnostic_only"]
        fusion = ablation["variants"]["C_diagnostic_then_behavior"]
        cutoff = diagnostic["positive_proxy_items"]
        lines.extend([
            f"- Published-invalid proxy prevalence: "
            f"{_fmt_percent(ablation['prevalence'])}.",
            f"- Behavior-only AUROC: {behavior['auroc']:.3f}; literal-diagnostic "
            f"AUROC: {diagnostic['auroc']:.3f}; fusion AUROC: "
            f"{fusion['auroc']:.3f}.",
            f"- At K={cutoff}, diagnostic precision="
            f"{_fmt_percent(diagnostic[f'precision_at_{cutoff}'])}, recall="
            f"{_fmt_percent(diagnostic[f'recall_at_{cutoff}'])}; random expected "
            f"precision={_fmt_percent(ablation['random_control']['expected_precision'])}.",
            "- This ablation uses published parser failure only as a reproducibility "
            "proxy, not as semantic ground truth.",
        ])
    lines.extend([
        "",
        "### PortugueseSpider evaluator disagreement",
        "",
        f"- Contingency: `{json.dumps(pt.get('contingency', {}), sort_keys=True)}`.",
    ])
    pt_contingency = pt.get("contingency", {})
    pt_disagreement = (
        pt_contingency.get("fail_pass", 0)
        + pt_contingency.get("pass_fail", 0)
    )
    pt_total = sum(pt_contingency.values())
    pt_low, pt_high = _wilson_interval(pt_disagreement, pt_total)
    lines.append(
        f"- Disagreement rate: {pt_disagreement}/{pt_total} "
        f"({_fmt_percent(pt_disagreement / pt_total)}; 95% Wilson CI "
        f"{_fmt_percent(pt_low)}–{_fmt_percent(pt_high)})."
    )
    pt_rank = pt.get("ranking_sensitivity", {})
    if pt_rank:
        lines.append(
            f"- {pt_rank['systems_with_changed_rank_position']}/"
            f"{pt_rank['systems']} systems change rank position; "
            f"pairwise tau={pt_rank['pairwise_kendall_tau_without_ties']}."
        )
    lines.extend([
        "",
        "### DBCode harness disagreement",
        "",
        f"- Contingency: `{json.dumps(db.get('contingency', {}), sort_keys=True)}`.",
    ])
    db_contingency = db.get("contingency", {})
    db_disagreement = (
        db_contingency.get("fail_pass", 0)
        + db_contingency.get("pass_fail", 0)
    )
    db_total = sum(db_contingency.values())
    db_low, db_high = _wilson_interval(db_disagreement, db_total)
    lines.append(
        f"- Disagreement rate: {db_disagreement}/{db_total} "
        f"({_fmt_percent(db_disagreement / db_total)}; 95% Wilson CI "
        f"{_fmt_percent(db_low)}–{_fmt_percent(db_high)})."
    )
    db_rank = db.get("ranking_sensitivity", {})
    if db_rank:
        lines.append(
            f"- {db_rank['systems_with_changed_rank_position']}/"
            f"{db_rank['systems']} systems change rank position between the "
            f"full harness and function tests."
        )
    lines.extend([
        "",
        "## Evidence boundary",
        "",
        "- Reference diagnostics and published evaluator failures nominate replay targets.",
        "- Match/execute and full/function disagreement show evaluator sensitivity, "
        "not which evaluator is correct.",
        "- All candidates have `evidence_tier=review`, `review_only=true`, and "
        "`confirmation_eligible=false`.",
        "- Confirmation requires an independently reconstructed environment or "
        "deterministic replay under a frozen dependency image.",
        "",
        "## Reproducibility",
        "",
        f"- Collection manifest SHA256: `{summary['reproducibility']['manifest_sha256']}`.",
        f"- Stable summary SHA256: `{summary['reproducibility']['summary_sha256']}`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _stable_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol": summary["protocol"],
        "manifest": summary["manifest"],
        "corpora": summary["corpora"],
        "parser_diagnostics": summary["parser_diagnostics"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collection = args.collection.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    sql_sources, sql_manifest = _sql_dialect_sources(collection, output)
    pt_sources, pt_manifest, pt_parser = _portuguese_spider_sources(
        collection, output
    )
    db_sources, db_manifest = _dbcode_sources(collection, output)

    sql_bundle = adapt_released_results(
        sql_sources, benchmark_id="sql-dialect-translation"
    )
    pt_bundle = adapt_released_results(
        pt_sources, benchmark_id="portuguese-spider"
    )
    db_bundle = adapt_released_results(
        db_sources, benchmark_id="dbcode"
    )
    manifest = sorted(
        sql_manifest + pt_manifest + db_manifest,
        key=lambda row: (row["path"], row["role"]),
    )
    manifest_sha256 = _sha256_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    )
    summary = {
        "protocol": {
            "schema_version": "released-result-collection-audit.v1",
            "api_calls": 0,
            "alignment": "explicit_item_id_or_content_digest_never_row_position",
            "promotion_ceiling": "review",
            "independent_replay_performed": False,
        },
        "manifest": manifest,
        "parser_diagnostics": {"portuguese_spider": pt_parser},
        "corpora": {
            "sql_dialect": _corpus_result(sql_bundle, ranking_pair=None),
            "portuguese_spider": _corpus_result(
                pt_bundle,
                ranking_pair=("structural_match", "database_execution"),
            ),
            "dbcode": _corpus_result(
                db_bundle,
                ranking_pair=("full_harness", "function_tests"),
            ),
        },
        "reproducibility": {
            "manifest_sha256": manifest_sha256,
        },
    }
    stable = _stable_summary(summary)
    summary_sha256 = _sha256_text(
        json.dumps(stable, sort_keys=True, separators=(",", ":"))
    )
    summary["reproducibility"]["summary_sha256"] = summary_sha256
    _write_json(output / "released_result_audit.json", summary)
    _write_json(output / "input_manifest.json", manifest)
    _write_markdown(output / "released_result_audit.md", summary)
    print(json.dumps({
        "output": str(output),
        "manifest_sha256": manifest_sha256,
        "summary_sha256": summary_sha256,
        "coverage": {
            name: value["coverage"]
            for name, value in summary["corpora"].items()
        },
    }, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
