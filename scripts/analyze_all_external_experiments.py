#!/usr/bin/env python3
"""Deterministically analyze all local external experimental artifacts.

The evidence contracts are frozen in:
docs/research/本地全部外部实验数据系统挖掘_PROTOCOL_20260810.md

This script never calls an API and never executes benchmark candidate code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


MODORA_FILES = {
    "udop": "resudop.jsonl",
    "docowl": "resdocowl.jsonl",
    "m3rag": "resm3rag.jsonl",
    "svrag": "ressvrag.jsonl",
    "txtrag": "restxtrag.jsonl",
    "zendb": "reszendb.jsonl",
    "quest": "resquest.jsonl",
    "gpt5": "resgpt5.jsonl",
    "modora": "resmodora.jsonl",
}
MODORA_SHA256 = {
    "resdocowl.jsonl": "6b2200b92c6003753893eaeb88778502dafa4ee0bace2b1fd8d3c0ff8c57be40",
    "resgpt5.jsonl": "cfae7760d82f33ce4114134e106011008659c40bd1389912d307af11509196f1",
    "resm3rag.jsonl": "736e21ff1391ec3c05d95ff6bc0e4fadcf1769af924b0c04cd49a651ff1a2542",
    "resmodora.jsonl": "15fa922b92937cd95c7c39d28df89c6d8ece71588566da6e6f3d8c88859e6db4",
    "resquest.jsonl": "f71b4f8e1362a81e535088cbd51024aced95587ee4613d485a808e0929202d43",
    "ressvrag.jsonl": "229d02847d6abe367af8e71c292958f85f1fe57c8a05a625579dc9ca280e1d0f",
    "restxtrag.jsonl": "8a9093d1eb0f27be7b894385b22723dfee72f917521ecfb5a158b5c1d3c58e0d",
    "resudop.jsonl": "b9f3c2c6bfe7065ea5f29a7165afee193e5a64f75d11fc09532a62690ef1f036",
    "reszendb.jsonl": "6645dc5df7fb29883331720732dfaeb826dc203bdfd1da74e2ee0761c6b7b60a",
}
SCORE_LINE = re.compile(r"^(?:Pred|Match|Exec)\s+(OK|Fail)\b")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def analyze_modora(root: Path) -> dict[str, Any]:
    data: dict[str, dict[int, dict[str, Any]]] = {}
    hashes: dict[str, str] = {}
    for method, filename in MODORA_FILES.items():
        path = root / filename
        actual = sha256_file(path)
        hashes[filename] = actual
        if actual != MODORA_SHA256[filename]:
            raise RuntimeError(f"MoDora input hash mismatch: {filename}")
        rows = load_jsonl(path)
        data[method] = {int(row["questionId"]): row for row in rows}
    id_sets = {method: set(rows) for method, rows in data.items()}
    if len({tuple(sorted(ids)) for ids in id_sets.values()}) != 1:
        raise RuntimeError("MoDora method item sets differ")
    ids = sorted(next(iter(id_sets.values())))
    positives = {
        method: {item_id for item_id in ids if rows[item_id].get("judge") == "T"}
        for method, rows in data.items()
    }
    oracle = set().union(*positives.values())
    method_rows = []
    for method in MODORA_FILES:
        other_union = set().union(
            *(positives[other] for other in MODORA_FILES if other != method)
        )
        method_rows.append(
            {
                "method": method,
                "items": len(ids),
                "stored_positive": len(positives[method]),
                "stored_positive_rate": f"{len(positives[method]) / len(ids):.12f}",
                "unique_positive": len(positives[method] - other_union),
                "oracle_loss_without_method": len(oracle - other_union),
            }
        )
    pair_rows = []
    for a, b in itertools.combinations(MODORA_FILES, 2):
        both = len(positives[a] & positives[b])
        a_only = len(positives[a] - positives[b])
        b_only = len(positives[b] - positives[a])
        union = positives[a] | positives[b]
        pair_rows.append(
            {
                "method_a": a,
                "method_b": b,
                "both_positive": both,
                "a_only": a_only,
                "b_only": b_only,
                "neither": len(ids) - both - a_only - b_only,
                "union_positive": len(union),
                "correct_set_jaccard": f"{both / len(union):.12f}" if union else "",
            }
        )
    tags: dict[str, list[int]] = defaultdict(list)
    pdfs: dict[str, list[int]] = defaultdict(list)
    canonical_method = "modora"
    for item_id in ids:
        tags[str(data[canonical_method][item_id].get("tag", ""))].append(item_id)
        pdfs[str(data[canonical_method][item_id].get("pdf_id", ""))].append(item_id)
    tag_rows = []
    for tag, tag_ids in sorted(tags.items()):
        for method in MODORA_FILES:
            count = sum(item_id in positives[method] for item_id in tag_ids)
            tag_rows.append(
                {
                    "tag": tag,
                    "items": len(tag_ids),
                    "small_n_lt_30": len(tag_ids) < 30,
                    "method": method,
                    "stored_positive": count,
                    "stored_positive_rate": f"{count / len(tag_ids):.12f}",
                }
            )
    pdf_rows = []
    for method in MODORA_FILES:
        values = [
            sum(item_id in positives[method] for item_id in pdf_ids) / len(pdf_ids)
            for pdf_ids in pdfs.values()
        ]
        pdf_rows.append(
            {
                "method": method,
                "documents": len(values),
                "macro_stored_positive_rate": f"{statistics.mean(values):.12f}",
                "population_sd": f"{statistics.pstdev(values):.12f}",
                "zero_positive_documents": sum(value == 0 for value in values),
                "perfect_documents": sum(value == 1 for value in values),
            }
        )
    additions = {
        method: len(positives[method] - positives["modora"])
        for method in MODORA_FILES
        if method != "modora"
    }
    return {
        "input_sha256": hashes,
        "method_rows": method_rows,
        "pair_rows": pair_rows,
        "tag_rows": tag_rows,
        "pdf_rows": pdf_rows,
        "summary": {
            "items": len(ids),
            "oracle_union_positive": len(oracle),
            "all_methods_negative": len(ids) - len(oracle),
            "modora_positive": len(positives["modora"]),
            "modora_unique_positive": next(
                row["unique_positive"] for row in method_rows if row["method"] == "modora"
            ),
            "additions_to_modora": additions,
        },
    }


def analyze_sql_dialect(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.jsonl")):
        rows.extend(load_jsonl(path))
    models = sorted({row["model"] for row in rows})
    dialects = sorted({row["target_dialect"] for row in rows})

    def summarize(group: list[dict[str, Any]]) -> dict[str, Any]:
        statuses = Counter(row["parse"]["status"] for row in group)
        return {
            "records": len(group),
            "valid": statuses["valid"],
            "invalid": statuses["invalid"],
            "unsupported_fallback": statuses["unsupported_fallback"],
            "timeout": statuses["timeout"],
            "empty": statuses["empty"],
            "valid_rate": f"{statuses['valid'] / len(group):.12f}",
            "raw_valid": sum(row["raw_parse"]["status"] == "valid" for row in group),
            "normalization_applied": sum(row["normalization_applied"] for row in group),
            "reference_valid": sum(
                row["reference_parse"]["status"] == "valid" for row in group
            ),
        }

    model_rows = []
    for model in models:
        model_rows.append({"model": model, **summarize([r for r in rows if r["model"] == model])})
    dialect_rows = []
    for dialect in dialects:
        dialect_rows.append(
            {
                "target_dialect": dialect,
                **summarize([r for r in rows if r["target_dialect"] == dialect]),
            }
        )
    model_dialect_rows = []
    for model in models:
        for dialect in dialects:
            group = [
                row
                for row in rows
                if row["model"] == model and row["target_dialect"] == dialect
            ]
            model_dialect_rows.append(
                {"model": model, "target_dialect": dialect, **summarize(group)}
            )
    by_task: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_task[(row["target_dialect"], row["task_sha256"])][row["model"]] = row
    if any(set(group) != set(models) for group in by_task.values()):
        raise RuntimeError("SQL dialect task matrix is incomplete")
    task_rows = []
    for (dialect, task_sha), group in sorted(by_task.items()):
        reference_statuses = {row["reference_parse"]["status"] for row in group.values()}
        if len(reference_statuses) != 1:
            raise RuntimeError("reference parse status differs across models")
        n_valid = sum(row["parse"]["status"] == "valid" for row in group.values())
        task_rows.append(
            {
                "target_dialect": dialect,
                "task_sha256": task_sha,
                "reference_status": next(iter(reference_statuses)),
                "models_valid": n_valid,
                "models_nonvalid": len(models) - n_valid,
                "all_models_nonvalid": n_valid == 0,
                "all_models_valid": n_valid == len(models),
            }
        )
    all_nonvalid = [row for row in task_rows if row["all_models_nonvalid"]]
    return {
        "model_rows": model_rows,
        "dialect_rows": dialect_rows,
        "model_dialect_rows": model_dialect_rows,
        "task_rows": task_rows,
        "summary": {
            "records": len(rows),
            "models": len(models),
            "tasks": len(task_rows),
            "all_models_nonvalid_tasks": len(all_nonvalid),
            "all_models_nonvalid_reference_nonvalid": sum(
                row["reference_status"] != "valid" for row in all_nonvalid
            ),
            "models_valid_distribution": dict(
                sorted(Counter(row["models_valid"] for row in task_rows).items())
            ),
        },
    }


def llama_source_name(path: Path) -> str:
    match = re.search(r"opensource_selected_(.+?)_to_clickhouse", path.name)
    if not match:
        raise RuntimeError(f"cannot parse Llama source name: {path.name}")
    return match.group(1)


def llama_task_key(row: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    return row.get("id"), row.get("norm"), row.get("clickhouse")


def result_answer(row: Mapping[str, Any]) -> Any:
    result_json = row.get("result_json")
    return result_json.get("Answer") if isinstance(result_json, dict) else None


def analyze_llama(root: Path) -> dict[str, Any]:
    data: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(root.rglob("*.json")):
        data[llama_source_name(path)] = json.loads(path.read_text(encoding="utf-8"))
    task_sets = {source: {llama_task_key(row) for row in rows} for source, rows in data.items()}
    file_rows = []
    all_rows: list[tuple[str, dict[str, Any]]] = []
    for source, rows in sorted(data.items()):
        all_rows.extend((source, row) for row in rows)
        file_rows.append(
            {
                "source_label": source,
                "records": len(rows),
                "unique_tasks": len(task_sets[source]),
                "empty_answer": sum(not result_answer(row) for row in rows),
            }
        )
    overlap_rows = []
    for a, b in itertools.combinations(sorted(data), 2):
        intersection = task_sets[a] & task_sets[b]
        a_map = {llama_task_key(row): result_answer(row) for row in data[a]}
        b_map = {llama_task_key(row): result_answer(row) for row in data[b]}
        overlap_rows.append(
            {
                "source_a": a,
                "source_b": b,
                "overlap_tasks": len(intersection),
                "same_answer_on_overlap": sum(a_map[key] == b_map[key] for key in intersection),
            }
        )
    result_hashes: Counter[str] = Counter()
    completion_to_results: dict[str, set[str]] = defaultdict(set)
    task_occurrences: Counter[tuple[Any, Any, Any]] = Counter()
    for _, row in all_rows:
        result_hash = canonical_hash(row.get("result"))
        result_hashes[result_hash] += 1
        completion_id = str((row.get("result") or {}).get("id", ""))
        completion_to_results[completion_id].add(result_hash)
        task_occurrences[llama_task_key(row)] += 1
    ambiguous_ids = {
        completion_id: hashes
        for completion_id, hashes in completion_to_results.items()
        if completion_id and len(hashes) > 1
    }
    diagnostic_rows = [
        {
            "completion_id": completion_id,
            "distinct_result_objects": len(hashes),
        }
        for completion_id, hashes in sorted(ambiguous_ids.items())
    ]
    return {
        "file_rows": file_rows,
        "overlap_rows": overlap_rows,
        "completion_id_rows": diagnostic_rows,
        "summary": {
            "records": len(all_rows),
            "unique_tasks": len(task_occurrences),
            "unique_result_objects": len(result_hashes),
            "unique_completion_ids": len(completion_to_results),
            "ambiguous_completion_ids": len(ambiguous_ids),
            "max_distinct_result_objects_per_completion_id": max(
                (len(hashes) for hashes in completion_to_results.values()), default=0
            ),
            "task_occurrence_distribution": dict(
                sorted(Counter(task_occurrences.values()).items())
            ),
        },
    }


def parse_portuguese_score(path: Path, root: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = SCORE_LINE.match(line)
        if match:
            counts[match.group(1)] += 1
    relative = path.relative_to(root)
    metric = "exec" if "exec" in path.name.lower() else "match" if "match" in path.name.lower() else "unknown"
    n = counts["OK"] + counts["Fail"]
    parts = relative.parts
    language_match = re.search(
        r"(?:^|[_-])(?:Div-|Eval-)?(en|pt|es|fr)-eval(?:[_-]|\.)", path.name
    )
    return {
        "path": str(relative),
        "configuration": parts[0] if parts else "",
        "checkpoint_or_subdir": parts[1] if len(parts) > 2 else "",
        "metric": metric,
        "eval_language": language_match.group(1) if language_match else "",
        "detailed": n > 0,
        "records": n,
        "ok": counts["OK"],
        "fail": counts["Fail"],
        "rate": f"{counts['OK'] / n:.12f}" if n else "",
    }


def analyze_portuguese(root: Path) -> dict[str, Any]:
    all_rows = [parse_portuguese_score(path, root) for path in sorted(root.rglob("*")) if path.is_file()]
    detailed = [row for row in all_rows if row["detailed"]]
    by_path = {row["path"]: row for row in detailed}
    pair_rows = []
    for match_row in detailed:
        if match_row["metric"] != "match":
            continue
        match_path = Path(match_row["path"])
        exec_name = match_path.name.replace("spider_eval_match_", "spider_eval_exec_")
        exec_path = str(match_path.with_name(exec_name))
        exec_row = by_path.get(exec_path)
        if not exec_row:
            continue
        pair_rows.append(
            {
                "match_path": match_row["path"],
                "exec_path": exec_path,
                "match_records": match_row["records"],
                "exec_records": exec_row["records"],
                "same_coverage_count": match_row["records"] == exec_row["records"],
                "match_rate": match_row["rate"],
                "exec_rate": exec_row["rate"],
                "exec_minus_match": f"{float(exec_row['rate']) - float(match_row['rate']):.12f}",
            }
        )
    deltas = [float(row["exec_minus_match"]) for row in pair_rows]
    mbart_language_rates: dict[str, list[float]] = defaultdict(list)
    for row in detailed:
        if (
            row["configuration"] == "mBART50MtoM-large-en-pt-es-fr-train"
            and row["metric"] == "match"
            and row["records"] == 1034
            and row["eval_language"]
        ):
            mbart_language_rates[row["eval_language"]].append(float(row["rate"]))
    return {
        "run_rows": all_rows,
        "pair_rows": pair_rows,
        "summary": {
            "score_files": len(all_rows),
            "detailed_files": len(detailed),
            "detailed_match_files": sum(row["metric"] == "match" for row in detailed),
            "detailed_exec_files": sum(row["metric"] == "exec" for row in detailed),
            "paired_match_exec_runs": len(pair_rows),
            "pairs_exec_lower": sum(delta < 0 for delta in deltas),
            "exec_minus_match_min": min(deltas) if deltas else None,
            "exec_minus_match_median": statistics.median(deltas) if deltas else None,
            "exec_minus_match_max": max(deltas) if deltas else None,
            "mbart_match_mean_by_eval_language": {
                language: statistics.mean(values)
                for language, values in sorted(mbart_language_rates.items())
            },
        },
    }


def csv_bool(value: str, present: str) -> bool | None:
    if present.lower() != "true":
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    raise ValueError(f"unexpected boolean: {value!r}")


def analyze_dbcode(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    database_dirs = {
        "postgresql": "PostgreSQL_Function_Code_Generation",
        "sqlite": "SQLite_Function_Code_Generation",
    }
    for database, dirname in database_dirs.items():
        path = root / dirname / "scores" / "per_item_status.csv"
        for row in csv.DictReader(path.open(encoding="utf-8")):
            row = dict(row)
            row["database"] = database
            row["success_value"] = csv_bool(row["is_success"], row["has_is_success"])
            row["func_value"] = csv_bool(
                row["is_success_func"], row["has_is_success_func"]
            )
            rows.append(row)
    group_rows = []
    groups: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        key = (row["database"], row["harness"], row["variant"], row["model"])
        groups[key][row["task_id"]] = row
    for (database, harness, variant, model), items in sorted(groups.items()):
        values = list(items.values())
        group_rows.append(
            {
                "database": database,
                "harness": harness,
                "variant": variant,
                "model": model,
                "records": len(values),
                "scored": sum(row["success_value"] is not None for row in values),
                "pass": sum(row["success_value"] is True for row in values),
                "fail": sum(row["success_value"] is False for row in values),
                "missing": sum(row["success_value"] is None for row in values),
                "func_scored": sum(row["func_value"] is not None for row in values),
                "func_pass": sum(row["func_value"] is True for row in values),
                "func_fail": sum(row["func_value"] is False for row in values),
            }
        )
    context_rows = []
    for database in database_dirs:
        models = sorted(
            {
                model
                for db, harness, _, model in groups
                if db == database and harness == "direct_llm"
            }
        )
        for model in models:
            aware = groups.get((database, "direct_llm", "dependency_aware", model), {})
            no_dep = groups.get((database, "direct_llm", "no_dependency", model), {})
            common = set(aware) & set(no_dep)
            for metric, field in (("full", "success_value"), ("function", "func_value")):
                scored = [
                    task_id
                    for task_id in common
                    if aware[task_id][field] is not None and no_dep[task_id][field] is not None
                ]
                if not scored:
                    continue
                both = sum(aware[i][field] and no_dep[i][field] for i in scored)
                aware_only = sum(aware[i][field] and not no_dep[i][field] for i in scored)
                no_dep_only = sum(no_dep[i][field] and not aware[i][field] for i in scored)
                context_rows.append(
                    {
                        "database": database,
                        "model": model,
                        "metric": metric,
                        "common_tasks": len(common),
                        "scored_pairs": len(scored),
                        "aware_pass": both + aware_only,
                        "no_dependency_pass": both + no_dep_only,
                        "both_pass": both,
                        "aware_only_pass": aware_only,
                        "no_dependency_only_pass": no_dep_only,
                        "neither_pass": len(scored) - both - aware_only - no_dep_only,
                        "aware_minus_no_dependency_rate": f"{(aware_only - no_dep_only) / len(scored):.12f}",
                    }
                )
    model_pair_rows = []
    for database in database_dirs:
        for variant in ("dependency_aware", "no_dependency"):
            model_items = {
                model: items
                for (db, harness, cond, model), items in groups.items()
                if db == database and harness == "direct_llm" and cond == variant
            }
            for model_a, model_b in itertools.combinations(sorted(model_items), 2):
                a, b = model_items[model_a], model_items[model_b]
                common = {
                    task_id
                    for task_id in set(a) & set(b)
                    if a[task_id]["success_value"] is not None
                    and b[task_id]["success_value"] is not None
                }
                if not common:
                    continue
                model_pair_rows.append(
                    {
                        "database": database,
                        "variant": variant,
                        "model_a": model_a,
                        "model_b": model_b,
                        "common_scored_tasks": len(common),
                        "a_pass": sum(a[i]["success_value"] for i in common),
                        "b_pass": sum(b[i]["success_value"] for i in common),
                        "a_only_pass": sum(
                            a[i]["success_value"] and not b[i]["success_value"] for i in common
                        ),
                        "b_only_pass": sum(
                            b[i]["success_value"] and not a[i]["success_value"] for i in common
                        ),
                    }
                )
    sqlite_direct = [
        row
        for row in rows
        if row["database"] == "sqlite"
        and row["harness"] == "direct_llm"
        and row["success_value"] is not None
        and row["func_value"] is not None
    ]
    full_func = Counter((row["success_value"], row["func_value"]) for row in sqlite_direct)

    trace_rows = []
    for database, dirname in database_dirs.items():
        trace_root = root / dirname / "logs_and_execution_traces"
        for path in sorted(trace_root.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or "success" not in payload:
                continue
            relative = path.relative_to(trace_root)
            if database == "postgresql":
                harness = "trae_agent" if "TRAE" in relative.parts else "unclassified"
            else:
                harness = "code_agent"
            task_payload = payload.get("task")
            trace_rows.append(
                {
                    "database": database,
                    "harness": harness,
                    "path": str(relative),
                    "stored_success": payload.get("success"),
                    "task_payload_sha256": canonical_hash(task_payload),
                    "agent_steps": len(payload.get("agent_steps") or []),
                    "llm_interactions": len(payload.get("llm_interactions") or []),
                }
            )
    trace_group_rows = []
    for (database, harness), group_iter in itertools.groupby(
        sorted(trace_rows, key=lambda row: (row["database"], row["harness"])),
        key=lambda row: (row["database"], row["harness"]),
    ):
        group = list(group_iter)
        trace_group_rows.append(
            {
                "database": database,
                "harness": harness,
                "trajectory_files": len(group),
                "stored_success_true": sum(row["stored_success"] is True for row in group),
                "stored_success_false": sum(row["stored_success"] is False for row in group),
                "unique_task_payloads": len({row["task_payload_sha256"] for row in group}),
            }
        )
    return {
        "group_rows": group_rows,
        "context_rows": context_rows,
        "model_pair_rows": model_pair_rows,
        "trace_rows": trace_rows,
        "trace_group_rows": trace_group_rows,
        "summary": {
            "per_item_rows": len(rows),
            "sqlite_direct_full_func_both_fail": full_func[(False, False)],
            "sqlite_direct_func_pass_full_fail": full_func[(False, True)],
            "sqlite_direct_both_pass": full_func[(True, True)],
            "sqlite_direct_full_pass_func_fail": full_func[(True, False)],
            "trajectory_files_with_success": len(trace_rows),
        },
    }


def verify_collection(root: Path) -> dict[str, Any]:
    manifest_path = root / "FILE_MANIFEST.csv"
    rows = list(csv.DictReader(manifest_path.open(encoding="utf-8")))
    manifest_paths = {row["relative_path"] for row in rows}
    result_rows = []
    for row in rows:
        path = root / row["relative_path"]
        exists = path.is_file()
        size_ok = exists and path.stat().st_size == int(row["bytes"])
        hash_ok = exists and sha256_file(path) == row["sha256"]
        result_rows.append(
            {
                "relative_path": row["relative_path"],
                "status": "verified" if exists and size_ok and hash_ok else "mismatch",
                "exists": exists,
                "size_ok": size_ok,
                "sha256_ok": hash_ok,
            }
        )
    extras = [
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
        and path.name != "FILE_MANIFEST.csv"
        and str(path.relative_to(root)) not in manifest_paths
    ]
    result_rows.extend(
        {
            "relative_path": relative,
            "status": "unmanifested",
            "exists": True,
            "size_ok": "",
            "sha256_ok": "",
        }
        for relative in sorted(extras)
    )
    return {
        "rows": result_rows,
        "summary": {
            "manifest_sha256": sha256_file(manifest_path),
            "manifest_entries": len(rows),
            "verified_entries": sum(row["status"] == "verified" for row in result_rows),
            "mismatch_entries": sum(row["status"] == "mismatch" for row in result_rows),
            "unmanifested_files": len(extras),
            "unmanifested_paths": extras,
        },
    }


def validate_anchors(results: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "modora_items_1065": results["modora"]["summary"]["items"] == 1065,
        "modora_oracle_914": results["modora"]["summary"]["oracle_union_positive"]
        == 914,
        "sql_dialect_records_4448": results["sql_dialect"]["summary"]["records"]
        == 4448,
        "sql_dialect_tasks_556": results["sql_dialect"]["summary"]["tasks"] == 556,
        "sql_all_nonvalid_32_reference_nonvalid_27": (
            results["sql_dialect"]["summary"]["all_models_nonvalid_tasks"] == 32
            and results["sql_dialect"]["summary"][
                "all_models_nonvalid_reference_nonvalid"
            ]
            == 27
        ),
        "llama_records_3418_unique_tasks_1332": (
            results["llama"]["summary"]["records"] == 3418
            and results["llama"]["summary"]["unique_tasks"] == 1332
        ),
        "llama_ambiguous_completion_ids_53": results["llama"]["summary"][
            "ambiguous_completion_ids"
        ]
        == 53,
        "portuguese_detailed_115_pairs_19": (
            results["portuguese"]["summary"]["detailed_files"] == 115
            and results["portuguese"]["summary"]["paired_match_exec_runs"] == 19
        ),
        "portuguese_all_paired_exec_lower": results["portuguese"]["summary"][
            "pairs_exec_lower"
        ]
        == 19,
        "dbcode_rows_1413": results["dbcode"]["summary"]["per_item_rows"] == 1413,
        "sqlite_function_pass_full_fail_60": results["dbcode"]["summary"][
            "sqlite_direct_func_pass_full_fail"
        ]
        == 60,
        "collection_manifest_615_clean": (
            results["integrity"]["summary"]["manifest_entries"] == 615
            and results["integrity"]["summary"]["mismatch_entries"] == 0
        ),
    }


def render_findings(results: Mapping[str, Any]) -> str:
    m = results["modora"]["summary"]
    sql = results["sql_dialect"]["summary"]
    llama = results["llama"]["summary"]
    pt = results["portuguese"]["summary"]
    db = results["dbcode"]
    integrity = results["integrity"]["summary"]
    method_map = {row["method"]: row for row in results["modora"]["method_rows"]}
    sql_models = {row["model"]: row for row in results["sql_dialect"]["model_rows"]}
    context = {
        (row["database"], row["model"], row["metric"]): row
        for row in db["context_rows"]
    }
    tag_lookup = defaultdict(dict)
    for row in results["modora"]["tag_rows"]:
        tag_lookup[row["tag"]][row["method"]] = row
    lines = [
        "# 本地全部外部实验数据：系统挖掘结果",
        "",
        "> 这是一份对 MoDora、SQLBench 和 DBCode 外部实验产物的确定性二次分析；它不是 BenchAudit 自身的实验成绩，也不存在跨任务统一总分。",
        "",
        "## 一、最能守住的结论",
        "",
        "### 1. MoDora 总体最强，但其他方法仍提供真实互补",
        "",
        f"MoDora stored-positive 为 **{m['modora_positive']}/{m['items']} ({m['modora_positive']/m['items']:.1%})**；九方法 oracle union 为 **{m['oracle_union_positive']}/{m['items']} ({m['oracle_union_positive']/m['items']:.1%})**，仍有 {m['all_methods_negative']} 条九法全负。MoDora 有 {m['modora_unique_positive']} 条独有 positive。",
        "",
        f"单独与 MoDora 组合时，GPT-5 新增 {m['additions_to_modora']['gpt5']} 条、SV-RAG 新增 {m['additions_to_modora']['svrag']} 条、M3DocRAG 新增 {m['additions_to_modora']['m3rag']} 条。说明总体领先没有消灭互补价值。",
        "",
        f"分层反转也存在：`tag=1-5`（n={tag_lookup['1-5']['modora']['items']}）MoDora={float(tag_lookup['1-5']['modora']['stored_positive_rate']):.1%}，M3DocRAG={float(tag_lookup['1-5']['m3rag']['stored_positive_rate']):.1%}；`tag=2-5`（n={tag_lookup['2-5']['modora']['items']}，small-n）MoDora={float(tag_lookup['2-5']['modora']['stored_positive_rate']):.1%}，M3DocRAG={float(tag_lookup['2-5']['m3rag']['stored_positive_rate']):.1%}。不能把单一总分理解成所有任务类型都占优。",
        "",
        "### 2. SQL parser acceptance 强烈依赖后处理和 reference 可解析性",
        "",
        f"在 {sql['records']} 条 model-record 中，o1-preview final-valid={sql_models['o1-preview']['valid']}/556，但 raw-valid 只有 {sql_models['o1-preview']['raw_valid']}/556；o3-mini 为 {sql_models['o3-mini']['valid']}/556 vs raw {sql_models['o3-mini']['raw_valid']}/556。这个巨大差异来自冻结 normalization 管线，不能写成模型能力差异。",
        "",
        f"共有 {sql['all_models_nonvalid_tasks']} 个任务八模型全部 non-valid，其中 {sql['all_models_nonvalid_reference_nonvalid']} 个（{sql['all_models_nonvalid_reference_nonvalid']/sql['all_models_nonvalid_tasks']:.1%}）连 reference 也被同一 parser 判为 non-valid。对这批任务，首先需要审计 parser/reference compatibility，而不是直接归因于八个模型共同失败。",
        "",
        "### 3. PortugueseSpider 的 match 与 execution 不是可互换指标",
        "",
        f"找到 {pt['paired_match_exec_runs']} 对同目录、同名干的 match/exec 详细评分文件；{pt['pairs_exec_lower']}/{pt['paired_match_exec_runs']} 对都是 execution 更低。`exec-match` 中位数为 {pt['exec_minus_match_median']:.1%}，范围 {pt['exec_minus_match_min']:.1%} 到 {pt['exec_minus_match_max']:.1%}。因此只报其中一个会显著改变结论，但这项差异本身不自动证明 evaluator 有 bug。",
        "",
        f"在 mBART50MtoM 四语训练配置的三个 checkpoint 上，match 均值按 eval language 为 en={pt['mbart_match_mean_by_eval_language']['en']:.1%}、fr={pt['mbart_match_mean_by_eval_language']['fr']:.1%}、es={pt['mbart_match_mean_by_eval_language']['es']:.1%}、pt={pt['mbart_match_mean_by_eval_language']['pt']:.1%}。同一模型/训练族仍存在约 8 个百分点的 en–pt 差距；多语言训练没有消除语言层差异。",
        "",
        "### 4. DBCode 的 dependency context 有平均收益，但存在 item-level 反转",
        "",
    ]
    for key in [
        ("postgresql", "DeepSeek-V3.1", "full"),
        ("postgresql", "Kimi-K2-Instruct", "full"),
        ("postgresql", "Qwen3-Coder-480B-A35B-Instruct", "full"),
        ("sqlite", "DeepSeek-V3.1", "full"),
        ("sqlite", "Qwen3-Coder-480B-A35B-Instruct", "full"),
    ]:
        row = context[key]
        lines.append(
            f"- {key[0]} / {key[1]}：在共同且两侧均有分数的 n={row['scored_pairs']} 条任务上，aware={row['aware_pass']}，no-dependency={row['no_dependency_pass']}；aware-only={row['aware_only_pass']}，no-dependency-only={row['no_dependency_only_pass']}。"
        )
    qwen_postgresql = context[
        ("postgresql", "Qwen3-Coder-480B-A35B-Instruct", "full")
    ]
    sqlite_dual_score_total = sum(
        db["summary"][key]
        for key in (
            "sqlite_direct_full_func_both_fail",
            "sqlite_direct_func_pass_full_fail",
            "sqlite_direct_both_pass",
            "sqlite_direct_full_pass_func_fail",
        )
    )
    llama_occurrences = llama["task_occurrence_distribution"]
    lines.extend(
        [
            "",
            f"收益并非逐题单调。尤其在 PostgreSQL Qwen 两条件共同且两侧均有分数的 {qwen_postgresql['scored_pairs']} 条任务上，有 {qwen_postgresql['aware_only_pass']} 条 aware-only success，同时有 {qwen_postgresql['no_dependency_only_pass']} 条 no-dependency-only success；上下文也可能改变或干扰生成路径。",
            "",
            f"SQLite 四个 79 题 direct-LLM 条件合计 {sqlite_dual_score_total} 条完整/function 双评分记录中：both-pass={db['summary']['sqlite_direct_both_pass']}，function-pass 但 full-fail={db['summary']['sqlite_direct_func_pass_full_fail']}，both-fail={db['summary']['sqlite_direct_full_func_both_fail']}。function-level 会额外放行 {db['summary']['sqlite_direct_func_pass_full_fail']} 条，不能拿它替代完整 PASS。",
            "",
            "### 5. Llama3.1 四个“source dialect”文件不是 3,418 个独立实验样本",
            "",
            f"四文件共有 {llama['records']} 行，但按 `(id,norm,clickhouse)` 只有 {llama['unique_tasks']} 个唯一任务；{llama_occurrences[3]} 个任务出现三次、{llama_occurrences[2]} 个出现两次，**只有 {llama_occurrences[1]} 个任务是单文件独有**。重叠任务的 answer 完全相同，说明这些行是复用产物，不应按 {llama['records']:,} 个独立调用或独立证据计数。",
            "",
            f"此外，{llama['ambiguous_completion_ids']} 个 completion ID 对应多个不同 result object，单个 ID 最多对应 {llama['max_distinct_result_objects_per_completion_id']} 个对象；completion ID 不能作为安全 join key。该集合没有评分，只能做 artifact/coverage 分析。",
            "",
            "## 二、异常与审计资产",
            "",
            "- MoDora 已有 9 条相同 prediction 的 T/F 冲突、3 条 U+200B gold、5 条需原 PDF 的收敛假设；详见独立 V2 报告。",
            "- SQL dialect 的 all-model non-valid 与 reference non-valid 高度重叠，是很强的 evaluator/reference 审计候选池。",
            "- SQLite trajectory 保存了尝试级 `success`，但 aggregate CodeAgent 四任务结果为 0/4；trajectory success 与最终 benchmark outcome 不能混用。",
            f"- 外部 collection manifest 的 {integrity['manifest_entries']} 个条目全部通过 size/SHA-256；另有 {integrity['unmanifested_files']} 个未进 manifest 的文件：`{integrity['unmanifested_paths']}`。",
            "",
            "## 三、不能做出的结论",
            "",
            "1. 不能把 `/data/expdata/BenchAudit` 写成 BenchAudit 系统成绩。",
            "2. 不能把 SQLGlot valid 写成 SQL 语义正确或执行成功。",
            "3. 不能把 MoDora stored judge 未核验地写成官方准确率。",
            "4. 不能把 PortugueseSpider 缺失 metric 当 0，也不能跨不同 coverage 文件直接排总榜。",
            "5. 不能把 DBCode function-level PASS、full PASS、trajectory success 合成一个成功率。",
            "6. 不能把 Llama3.1 重复文件行当独立模型调用。",
            "",
            "## 四、研究价值排序",
            "",
            "1. **测量合同断裂**：同一输出在 syntax/match/exec/full-function 层级得到不同结论，是这批资产最统一的跨数据集现象。",
            "2. **互补而非单榜**：MoDora 总体占优但仍遗漏其他方法能做对的 133 条；DBCode 模型和 context 也存在双向独有成功。",
            "3. **共识失败审计**：多模型全失败只有在 reference/evaluator 同时健康时才可解释为共同困难。",
            "4. **覆盖与身份卫生**：Llama 重复行、completion-ID 冲突、DBCode coverage/missing score 都会让朴素排行榜失真。",
            "",
            "## 五、证据边界",
            "",
            "- 全部分析为离线确定性重放，API attempts=0。",
            "- 没有重跑 SQL、数据库或代码 benchmark；所有 outcome 均来自已存字段/sidecar。",
            "- 本报告是探索性二次分析，已知性披露见冻结协议。",
            "- 不存在跨四类任务的统一性能分数。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modora-root", type=Path, default=Path("data/MoDora"))
    parser.add_argument(
        "--collection-root", type=Path, default=Path("/data/expdata/BenchAudit")
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("docs/research/本地全部外部实验数据系统挖掘_PROTOCOL_20260810.md"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/all_external_experiment_mining_20260810"),
    )
    args = parser.parse_args()
    collection = args.collection_root
    results = {
        "modora": analyze_modora(args.modora_root),
        "sql_dialect": analyze_sql_dialect(
            collection / "SQLBench/SQL_Dialect_Translation/scores/sqlglot_syntax_validation"
        ),
        "llama": analyze_llama(
            collection / "SQLBench/Llama3.1_SQL_Dialect_Translation/different_model_outputs"
        ),
        "portuguese": analyze_portuguese(collection / "SQLBench/PortugueseSpider/scores"),
        "dbcode": analyze_dbcode(collection / "DBCode"),
        "integrity": verify_collection(collection),
    }
    anchors = validate_anchors(results)
    if not all(anchors.values()):
        failed = [name for name, passed in anchors.items() if not passed]
        raise RuntimeError(f"analysis anchor failure: {failed}")
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    output_specs = {
        "modora_method_summary.csv": results["modora"]["method_rows"],
        "modora_pairwise.csv": results["modora"]["pair_rows"],
        "modora_tag_summary.csv": results["modora"]["tag_rows"],
        "modora_pdf_summary.csv": results["modora"]["pdf_rows"],
        "sql_dialect_model_summary.csv": results["sql_dialect"]["model_rows"],
        "sql_dialect_summary.csv": results["sql_dialect"]["dialect_rows"],
        "sql_dialect_model_by_dialect.csv": results["sql_dialect"]["model_dialect_rows"],
        "sql_dialect_task_consensus.csv": results["sql_dialect"]["task_rows"],
        "llama_file_summary.csv": results["llama"]["file_rows"],
        "llama_file_overlap.csv": results["llama"]["overlap_rows"],
        "llama_ambiguous_completion_ids.csv": results["llama"]["completion_id_rows"],
        "portuguese_spider_run_scores.csv": results["portuguese"]["run_rows"],
        "portuguese_spider_metric_pairs.csv": results["portuguese"]["pair_rows"],
        "dbcode_group_summary.csv": results["dbcode"]["group_rows"],
        "dbcode_context_pairs.csv": results["dbcode"]["context_rows"],
        "dbcode_model_pairs.csv": results["dbcode"]["model_pair_rows"],
        "dbcode_trajectory_summary.csv": results["dbcode"]["trace_group_rows"],
        "artifact_integrity.csv": results["integrity"]["rows"],
    }
    for filename, rows in output_specs.items():
        write_csv(output / filename, rows)
    (output / "FINDINGS.md").write_text(render_findings(results), encoding="utf-8")
    generated = sorted(path for path in output.iterdir() if path.is_file() and path.name != "receipt.json")
    receipt = {
        "schema_version": "all-external-experiment-mining-v1",
        "script": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
        "protocol": {"path": str(args.protocol), "sha256": sha256_file(args.protocol)},
        "inputs": {
            "modora_root": str(args.modora_root.resolve()),
            "modora_sha256": results["modora"]["input_sha256"],
            "collection_root": str(collection.resolve()),
            "collection_manifest_sha256": results["integrity"]["summary"]["manifest_sha256"],
        },
        "summary": {key: value["summary"] for key, value in results.items()},
        "anchors": anchors,
        "output_sha256": {path.name: sha256_file(path) for path in generated},
        "api_attempts": 0,
        "benchmark_execution_attempts": 0,
        "inputs_modified": False,
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
