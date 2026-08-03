#!/usr/bin/env python3
"""Materialize the sealed Platinum selection and estimate paid-run cost without API access."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchcore.checkers import DEFAULT_CHECKERS
from benchcore.llm_auditor import (
    ANSWER_OPTION_MATCHER_SYSTEM_PROMPT,
    BLIND_SOLVER_SYSTEM_PROMPT,
    EVENT_STATE_SYSTEM_PROMPT,
    GOLD_CHALLENGER_SYSTEM_PROMPT,
    GOLD_DEFENDER_SYSTEM_PROMPT,
    OPTION_APPLICABILITY_SYSTEM_PROMPT,
    QUANTITY_CONSISTENCY_SYSTEM_PROMPT,
    QUESTION_SYSTEM_PROMPT,
    build_blind_user_prompt,
    build_gold_evidence_user_prompt,
    build_option_applicability_user_prompt,
    build_option_match_user_prompt,
    common_item_payload,
)
from benchcore.methods import DEFAULT_DATASET_CHECKERS, DEFAULT_METHOD_CHECKERS
from benchcore.schema import BenchmarkItem
from scripts.preflight_platinum_holdout_availability import row_identity


PROTOCOL_V1 = ROOT / "docs/research/PLATINUM_BLIND_HOLDOUT_RUN_PROTOCOL_20260803.md"
PROTOCOL_V2 = ROOT / "docs/research/PLATINUM_BLIND_HOLDOUT_RUN_PROTOCOL_V2_20260803.md"
MANIFEST = ROOT / "experiments/platinum_blind_holdout_897.manifest.json"
SELECTION_RECEIPT = ROOT / "reports/platinum_blind_holdout_selection_20260803/receipt.json"
AVAILABILITY = ROOT / "reports/platinum_untouched_holdout_availability_20260803/availability.json"
RUN_CONFIG = ROOT / "configs/llm_deepseek_platinum_blind_v1.json"

EXPECTED_HASHES = {
    "protocol_v1": "ba09ef99cefc3f0fa63dbdc49171c1d31dd40a5da21db4200983e28073d57401",
    "protocol_v2": "836021cad630dcb379e72152da02d4e452d4d9ad38bd31b1937c5c87e47e65c8",
    "manifest": "37637b8e4d19e66f002d9b766180b57c7076b31123b7139b28441ec6beaabe32",
    "selection_receipt": "e62acd45f95c0cac00582207d2f02e6618444bb2c3168e595ffc0317e4287f7c",
    "availability": "2a1b1164f1e9831e5554abfcac14df44cf78963957cce219ecc9381f2d3e7f77",
}
DATASET_REVISION = "51920a33bfb4620c789729ace14141e87a14969b"
EXPECTED_ITEMS = 897
ALLOWED_ROW_KEYS = frozenset(
    {"id", "task", "gold", "aliases", "choices", "output_contract", "evaluator", "metadata"}
)
FORBIDDEN_SOURCE_COLUMNS = frozenset({"cleaning_status", "platinum_target", "platinum_prompt"})
FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "layer", "counts", "cleaning_status", "platinum_target", "truth", "binary_truth",
        "selection_seed", "selection_rank", "sealed_truth_sha256",
    }
)
EXPECTED_METHODS = [
    "task_specification", "context_attachment", "expected_output", "oracle_ground_truth",
    "evaluator", "task_integrity", "contract_consistency", "evaluator_replay",
    "metamorphic_answer", "evaluator_mutation", "executable_evidence",
    "differential_candidate", "llm_gold_audit", "llm_question_clarity",
    "llm_quantity_consistency", "llm_event_state", "duplicate_conflict", "schema_drift",
]
LLM_METHODS = [
    "llm_gold_audit", "llm_question_clarity", "llm_quantity_consistency", "llm_event_state"
]
PARSING_MAP = {
    "math": (
        {"type": "numeric_exact_match"},
        {"type": "number", "format": "single numeric answer"},
    ),
    "text": (
        {"type": "normalized_exact_match_with_aliases"},
        {"type": "text", "format": "one short textual answer"},
    ),
    "squad": (
        {"type": "normalized_exact_match_with_aliases"},
        {"type": "text", "format": "one extractive textual answer"},
    ),
    "bbh_multiple_choice": (
        {"type": "multiple_choice_exact_match"},
        {"type": "choice", "format": "one listed choice"},
    ),
    "multiple_choice": (
        {"type": "multiple_choice_exact_match"},
        {"type": "choice", "format": "one listed choice"},
    ),
}
HISTORICAL_RESPONSE_CHAR_P95 = 1645
HISTORICAL_RESPONSE_CHAR_MAX = 5510
HISTORICAL_CALLS_PER_ITEM = 6.64
HISTORICAL_YUAN_PER_CALL = 1.4 / 664
CHARACTERS_PER_TOKEN_PROXY = 4.0


class PreflightError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def verify_frozen_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    paths = {
        "protocol_v1": PROTOCOL_V1,
        "protocol_v2": PROTOCOL_V2,
        "manifest": MANIFEST,
        "selection_receipt": SELECTION_RECEIPT,
        "availability": AVAILABILITY,
    }
    for name, path in paths.items():
        actual = sha256_file(path)
        if actual != EXPECTED_HASHES[name]:
            raise PreflightError(f"frozen input hash mismatch: {name}: {actual}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    availability = json.loads(AVAILABILITY.read_text(encoding="utf-8"))
    if manifest.get("dataset_revision") != DATASET_REVISION:
        raise PreflightError("manifest dataset revision mismatch")
    if len(manifest.get("items", [])) != EXPECTED_ITEMS:
        raise PreflightError("manifest item count mismatch")
    if manifest.get("truth_unsealed") is not False or manifest.get("truth_fields_emitted") is not False:
        raise PreflightError("public manifest truth boundary is not sealed")
    return manifest, availability


def verify_run_config() -> dict[str, Any]:
    config = json.loads(RUN_CONFIG.read_text(encoding="utf-8"))
    expected = {
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "temperature": 0.0,
        "timeout": 120,
        "max_tokens": 5000,
        "max_retries": 3,
        "n_votes": 1,
        "vote_temperature": 0.3,
        "thinking": "disabled",
        "max_api_attempts": 7176,
        "observed_token_stop": 16000000,
        "dry_run": False,
    }
    if config != expected:
        raise PreflightError("run config differs from the frozen execution table")
    return config


def evaluator_for(strategy: str) -> tuple[dict[str, str], dict[str, str]]:
    if strategy not in PARSING_MAP:
        raise PreflightError(f"unknown platinum parsing strategy: {strategy!r}")
    evaluator, output_contract = PARSING_MAP[strategy]
    return dict(evaluator), dict(output_contract)


def normalized_targets(value: Any) -> list[Any]:
    values = value if isinstance(value, list) else [value]
    result = [entry for entry in values if entry not in (None, "")]
    if not result:
        raise PreflightError("empty original_target")
    return result


def materialize_rows(data_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest, availability = verify_frozen_inputs()
    artifact_by_config = {
        row["config"]: row["artifact"] for row in availability["config_aggregates"]
    }
    ordered = [(row["config"], row["opaque_id"]) for row in manifest["items"]]
    selected_by_config: dict[str, set[str]] = {}
    for config, opaque_id in ordered:
        selected_by_config.setdefault(config, set()).add(opaque_id)

    found: dict[tuple[str, str], dict[str, Any]] = {}
    projection_by_config: dict[str, list[str]] = {}
    for config in sorted(selected_by_config):
        path = data_root / "platinum-bench" / config / "test-00000-of-00001.parquet"
        expected_artifact = artifact_by_config.get(config)
        if not path.is_file() or not expected_artifact:
            raise PreflightError(f"missing frozen parquet: {config}")
        if sha256_file(path) != expected_artifact["sha256"]:
            raise PreflightError(f"source artifact mismatch: {config}")
        schema_names = pq.read_schema(path).names
        required = {"platinum_prompt_no_cot", "original_target", "platinum_parsing_strategy"}
        if not required.issubset(schema_names):
            raise PreflightError(f"missing required source columns: {config}")
        projection = [name for name in schema_names if name not in FORBIDDEN_SOURCE_COLUMNS]
        if FORBIDDEN_SOURCE_COLUMNS & set(projection):
            raise PreflightError("truth-bearing source column entered projection")
        projection_by_config[config] = projection
        for source in pq.read_table(path, columns=projection).to_pylist():
            opaque_id = row_identity(config, source)
            if opaque_id not in selected_by_config[config]:
                continue
            key = (config, opaque_id)
            if key in found:
                raise PreflightError(f"duplicate selected identity: {config}/{opaque_id}")
            prompt = source.get("platinum_prompt_no_cot")
            if not isinstance(prompt, str) or not prompt.strip():
                raise PreflightError(f"empty prompt: {config}/{opaque_id}")
            targets = normalized_targets(source.get("original_target"))
            strategy = source.get("platinum_parsing_strategy")
            evaluator, output_contract = evaluator_for(strategy)
            source_choices = source.get("options")
            choices = list(source_choices) if isinstance(source_choices, list) else None
            row = {
                "id": opaque_id,
                "task": prompt,
                "gold": targets[0],
                "aliases": targets[1:],
                "choices": choices,
                "output_contract": output_contract,
                "evaluator": evaluator,
                "metadata": {"platinum_config": config},
            }
            if set(row) != ALLOWED_ROW_KEYS or FORBIDDEN_OUTPUT_KEYS & set(row):
                raise PreflightError("materialized row field boundary violation")
            if set(row["metadata"]) != {"platinum_config"}:
                raise PreflightError("materialized metadata boundary violation")
            found[key] = row

    missing = [key for key in ordered if key not in found]
    if missing or len(found) != EXPECTED_ITEMS:
        raise PreflightError(f"selected identity join mismatch: missing={len(missing)} found={len(found)}")
    rows = [found[key] for key in ordered]
    if len({row["id"] for row in rows}) != EXPECTED_ITEMS:
        raise PreflightError("materialized IDs are not globally unique")
    return rows, {
        "source_projection_by_config": projection_by_config,
        "forbidden_source_columns_read": [],
        "manifest_fields_not_emitted": ["counts", "layer", "sealed_truth_sha256"],
    }


def item_from_row(row: dict[str, Any]) -> BenchmarkItem:
    return BenchmarkItem(
        item_id=row["id"], raw=row, task=row["task"], gold=row["gold"],
        aliases=row["aliases"], choices=row["choices"],
        output_contract=row["output_contract"], evaluator=row["evaluator"],
        metadata=dict(row["metadata"]),
    )


def question_user_prompt(item: BenchmarkItem) -> str:
    payload = common_item_payload(item)
    payload.pop("gold", None)
    payload.pop("aliases", None)
    payload.pop("evaluator", None)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def quantity_event_user_prompt(item: BenchmarkItem) -> str:
    payload = {
        "item_id": item.item_id,
        "task": item.task,
        "context": {},
        "output_contract": item.output_contract,
        "metadata_without_verified_labels": item.metadata,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def current_method_registry() -> list[str]:
    return (
        [checker.name for checker in DEFAULT_CHECKERS]
        + [checker.name for checker in DEFAULT_METHOD_CHECKERS]
        + list(LLM_METHODS)
        + [checker.name for checker in DEFAULT_DATASET_CHECKERS]
    )


def percentile(values: list[int], quantile: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1)]


def length_summary(values: list[int]) -> dict[str, int | float]:
    return {
        "min": min(values),
        "median": statistics.median(values),
        "p95": percentile(values, 0.95),
        "max": max(values),
        "sum": sum(values),
    }


def prompt_budget(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fixed_chars: list[int] = []
    minimum_chars: list[int] = []
    p95_proxy_chars: list[int] = []
    maximum_proxy_chars: list[int] = []
    empty: dict[str, Any] = {}
    for row in rows:
        item = item_from_row(row)
        blind = len(BLIND_SOLVER_SYSTEM_PROMPT) + len(build_blind_user_prompt(item))
        question = len(QUESTION_SYSTEM_PROMPT) + len(question_user_prompt(item))
        quantity = len(QUANTITY_CONSISTENCY_SYSTEM_PROMPT) + len(quantity_event_user_prompt(item))
        event = len(EVENT_STATE_SYSTEM_PROMPT) + len(quantity_event_user_prompt(item))
        fixed = blind + question + quantity + event
        matcher_base = len(ANSWER_OPTION_MATCHER_SYSTEM_PROMPT) + len(build_option_match_user_prompt(item, empty))
        applicability_base = len(OPTION_APPLICABILITY_SYSTEM_PROMPT) + len(
            build_option_applicability_user_prompt(item, empty, empty)
        )
        challenge_base = len(GOLD_CHALLENGER_SYSTEM_PROMPT) + len(
            build_gold_evidence_user_prompt(item, empty, empty, empty)
        )
        defender_base = len(GOLD_DEFENDER_SYSTEM_PROMPT) + len(
            build_gold_evidence_user_prompt(item, empty, empty, empty)
        )
        fixed_chars.append(fixed)
        minimum_chars.append(fixed + matcher_base + applicability_base)
        # Dependent prompts embed prior responses. P95 and historical-max response
        # lengths are planning proxies, not cryptographic provider-token bounds.
        p95_proxy_chars.append(
            fixed + matcher_base + HISTORICAL_RESPONSE_CHAR_P95
            + applicability_base + 2 * HISTORICAL_RESPONSE_CHAR_P95
            + challenge_base + 3 * HISTORICAL_RESPONSE_CHAR_P95
        )
        maximum_proxy_chars.append(
            fixed + matcher_base + HISTORICAL_RESPONSE_CHAR_MAX
            + applicability_base + 2 * HISTORICAL_RESPONSE_CHAR_MAX
            + challenge_base + 3 * HISTORICAL_RESPONSE_CHAR_MAX
            + defender_base + 3 * HISTORICAL_RESPONSE_CHAR_MAX
        )
    return {
        "fixed_four_initial_stage_chars_per_item": length_summary(fixed_chars),
        "six_call_minimum_prompt_chars_per_item": length_summary(minimum_chars),
        "seven_call_p95_response_proxy_prompt_chars_per_item": length_summary(p95_proxy_chars),
        "eight_call_historical_max_response_proxy_prompt_chars_per_item": length_summary(maximum_proxy_chars),
        "response_proxy": {
            "source": "DeepSeek-v4-flash MMLU-1000 frozen cache response JSON character distribution",
            "p95_chars": HISTORICAL_RESPONSE_CHAR_P95,
            "max_chars": HISTORICAL_RESPONSE_CHAR_MAX,
            "characters_per_token_proxy": CHARACTERS_PER_TOKEN_PROXY,
            "limitation": "planning estimate only; provider usage counters govern the paid-run stop",
        },
    }


def build_receipt(rows: list[dict[str, Any]], isolation: dict[str, Any], output_path: Path) -> dict[str, Any]:
    verify_run_config()
    methods = current_method_registry()
    config_counts = dict(sorted(Counter(row["metadata"]["platinum_config"] for row in rows).items()))
    task_lengths = [len(row["task"]) for row in rows]
    alias_counts = [len(row["aliases"]) for row in rows]
    prompt = prompt_budget(rows)
    calls = {
        "per_item_min": 6,
        "per_item_max": 8,
        "per_run_min": EXPECTED_ITEMS * 6,
        "per_run_max": EXPECTED_ITEMS * 8,
        "three_runs_min": EXPECTED_ITEMS * 6 * 3,
        "three_runs_max": EXPECTED_ITEMS * 8 * 3,
        "three_runs_expected_from_svamp_6_64_per_item": round(EXPECTED_ITEMS * HISTORICAL_CALLS_PER_ITEM * 3),
    }
    estimated_cost = {
        "calibration": "SVAMP frozen empirical ~= CNY 1.4 / 664 calls",
        "expected_cny": round(calls["three_runs_expected_from_svamp_6_64_per_item"] * HISTORICAL_YUAN_PER_CALL, 2),
        "call_count_upper_proxy_cny": round(calls["three_runs_max"] * HISTORICAL_YUAN_PER_CALL, 2),
        "hard_budget_cny": 60.0,
        "limitation": "call-mix calibration, not a provider invoice or token-price guarantee",
    }
    # Conservative planning proxy: all three runs use the 8-call prompt maximum
    # proxy plus one historical-max response per call, converted at 4 chars/token.
    prompt_max_sum = prompt["eight_call_historical_max_response_proxy_prompt_chars_per_item"]["sum"]
    token_proxy = math.ceil(
        3 * (prompt_max_sum + EXPECTED_ITEMS * 8 * HISTORICAL_RESPONSE_CHAR_MAX)
        / CHARACTERS_PER_TOKEN_PROXY
    )
    gates = {
        "materialized_897_unique": len(rows) == EXPECTED_ITEMS == len({row["id"] for row in rows}),
        "field_isolation": all(
            set(row) == ALLOWED_ROW_KEYS
            and set(row["metadata"]) == {"platinum_config"}
            and not (FORBIDDEN_OUTPUT_KEYS & set(row))
            for row in rows
        ),
        "method_set_exact": methods == EXPECTED_METHODS,
        "three_run_calls_at_most_21528": calls["three_runs_max"] <= 21528,
        "planning_token_proxy_at_most_50000000": token_proxy <= 50_000_000,
        "estimated_cost_at_most_cny_60": estimated_cost["call_count_upper_proxy_cny"] <= 60.0,
        "no_new_adapter_branch": set(config_counts) == {
            "bbh_logical_deduction_three_objects", "bbh_navigate", "bbh_object_counting",
            "drop", "hotpotqa", "multiarith", "singleop", "singleq", "squad", "winograd_wsc",
        },
    }
    return {
        "schema_version": "platinum-blind-holdout-run-dry-count-v1",
        "outcome": "DRY_COUNT_GO" if all(gates.values()) else "DRY_COUNT_NO_GO",
        "api_attempts": 0,
        "network_attempts": 0,
        "api_key_read": False,
        "model_responses_produced": False,
        "model_cache_written": False,
        "truth_unsealed": False,
        "public_manifest_passed_to_auditor": False,
        "materialized_input": {
            "path": str(output_path.resolve()),
            "sha256": sha256_file(output_path),
            "rows": len(rows),
            "top_level_keys": sorted(ALLOWED_ROW_KEYS),
            "metadata_keys": ["platinum_config"],
            "config_counts": config_counts,
            "task_length_chars": length_summary(task_lengths),
            "nonempty_gold_rows": sum(row["gold"] not in (None, "") for row in rows),
            "alias_count": length_summary(alias_counts),
        },
        "isolation": isolation,
        "methods_run_expected": methods,
        "method_set_sha256": hashlib.sha256(stable_bytes(methods)).hexdigest(),
        "calls": calls,
        "prompt_character_budget": prompt,
        "planning_token_proxy": token_proxy,
        "provider_token_hard_cap": 50_000_000,
        "estimated_cost": estimated_cost,
        "gates": gates,
        "frozen_hashes": {
            **EXPECTED_HASHES,
            "run_config": sha256_file(RUN_CONFIG),
            "preflight_script": sha256_file(Path(__file__)),
        },
    }


def run(data_root: Path, output_path: Path, receipt_path: Path) -> dict[str, Any]:
    verify_run_config()
    rows, isolation = materialize_rows(data_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"".join(stable_bytes(row) for row in rows))
    receipt = build_receipt(rows, isolation, output_path)
    receipt_path.write_bytes(stable_bytes(receipt))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = run(args.data_root, args.out, args.receipt)
    print(json.dumps({
        "outcome": receipt["outcome"],
        "rows": receipt["materialized_input"]["rows"],
        "calls": receipt["calls"],
        "planning_token_proxy": receipt["planning_token_proxy"],
        "estimated_cost": receipt["estimated_cost"],
    }, ensure_ascii=False, indent=2))
    return 0 if receipt["outcome"] == "DRY_COUNT_GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())
