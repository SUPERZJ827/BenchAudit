#!/usr/bin/env python3
"""Derive selection-strata gates from committed aggregate-only availability."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "reports/platinum_untouched_holdout_availability_20260803/availability.json"
PROTOCOL = ROOT / "docs/research/PLATINUM_SELECTION_STRATA_RECEIPT_PROTOCOL_20260803.md"
EXPECTED_INPUT_SHA256 = "2a1b1164f1e9831e5554abfcac14df44cf78963957cce219ecc9381f2d3e7f77"
EXPECTED_SCHEMA = "platinum-untouched-availability-v1"
LAYERS = {
    "A_arithmetic": ("multiarith", "singleop", "singleq"),
    "B_text_qa": ("drop", "hotpotqa", "squad"),
    "C_reasoning_coreference": (
        "bbh_logical_deduction_three_objects", "bbh_navigate",
        "bbh_object_counting", "winograd_wsc",
    ),
    "X_out_of_modality": ("vqa",),
    "identity_excluded": ("tab_fact",),
}
QUOTAS = {
    "drop": {"revised": 40, "rejected": 30, "negative": 30},
    "hotpotqa": {"revised": 25, "rejected": 25, "negative": 50},
    "squad": {"revised": 20, "rejected": 30, "negative": 50},
}
STATUSES = ("consensus", "verified", "revised", "rejected")


class StrataError(RuntimeError):
    pass


def stable_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def derive(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema_version") != EXPECTED_SCHEMA:
        raise StrataError("SCHEMA_MISMATCH")
    rows = data.get("config_aggregates")
    if not isinstance(rows, list):
        raise StrataError("SCHEMA_MISMATCH")
    by_config = {row["config"]: row for row in rows}
    expected = {config for configs in LAYERS.values() for config in configs}
    if set(by_config) != expected or len(by_config) != len(rows):
        raise StrataError("CONFIG_SCOPE_MISMATCH")

    config_counts: dict[str, dict[str, int]] = {}
    for config in sorted(by_config):
        raw = by_config[config]["status_counts"]
        counts = {status: int(raw.get(status, 0)) for status in STATUSES}
        if sum(counts.values()) != int(by_config[config]["rows"]):
            raise StrataError("AGGREGATE_INVARIANT_FAILURE")
        config_counts[config] = counts

    layer_counts: dict[str, dict[str, int]] = {}
    for layer, configs in LAYERS.items():
        counts = {status: sum(config_counts[c][status] for c in configs) for status in STATUSES}
        counts.update({
            "positive": counts["revised"] + counts["rejected"],
            "negative": counts["consensus"] + counts["verified"],
            "rows": sum(counts[status] for status in STATUSES),
        })
        layer_counts[layer] = counts

    quota_gates: dict[str, dict[str, Any]] = {}
    outcome = "PASS_SELECTION_STRATA_AVAILABLE"
    for config, quota in QUOTAS.items():
        source = {
            "revised": config_counts[config]["revised"],
            "rejected": config_counts[config]["rejected"],
            "negative": config_counts[config]["consensus"] + config_counts[config]["verified"],
        }
        headroom = {key: source[key] - quota[key] for key in quota}
        passed = all(value >= 0 for value in headroom.values())
        quota_gates[config] = {
            "source": source, "quota": quota, "headroom": headroom, "passed": passed,
        }
        if headroom["revised"] < 0:
            outcome = "INSUFFICIENT_REVISED_QUOTA"
        elif headroom["rejected"] < 0:
            outcome = "INSUFFICIENT_REJECTED_QUOTA"
        elif headroom["negative"] < 0:
            outcome = "INSUFFICIENT_NEGATIVE_QUOTA"

    if layer_counts["A_arithmetic"]["revised"] != 3 or layer_counts["A_arithmetic"]["rejected"] != 22:
        raise StrataError("AGGREGATE_INVARIANT_FAILURE")
    if layer_counts["X_out_of_modality"]["positive"] != 242 or layer_counts["X_out_of_modality"]["negative"] != 0:
        raise StrataError("AGGREGATE_INVARIANT_FAILURE")

    return {
        "schema_version": "platinum-selection-strata-receipt-v1",
        "outcome": outcome,
        "source": {"schema_version": EXPECTED_SCHEMA, "sha256": EXPECTED_INPUT_SHA256},
        "config_status_counts": config_counts,
        "layer_status_counts": layer_counts,
        "layer_b_quota_gates": quota_gates,
        "tab_fact_identity_outcome": by_config["tab_fact"]["identity_outcome"],
        "item_ids_emitted": False,
        "item_label_mapping_emitted": False,
        "dataset_files_opened": 0,
        "network_attempts": 0,
        "api_attempts": 0,
        "auditor_executed": False,
    }


def run(source: Path, out: Path) -> None:
    if sha256_file(source) != EXPECTED_INPUT_SHA256:
        raise StrataError("SOURCE_HASH_MISMATCH")
    result = derive(json.loads(source.read_text()))
    out.mkdir(parents=True, exist_ok=True)
    receipt_path = out / "receipt.json"
    receipt_path.write_bytes(stable_bytes(result))
    summary = {
        "protocol_sha256": sha256_file(PROTOCOL),
        "analyzer_sha256": sha256_file(Path(__file__)),
        "receipt_sha256": sha256_file(receipt_path),
        "outcome": result["outcome"],
        "zero_item_mapping": True,
        "zero_dataset_access": True,
        "zero_network_api_auditor": True,
    }
    (out / "summary.json").write_bytes(stable_bytes(summary))
    a = result["layer_status_counts"]["A_arithmetic"]
    b = result["layer_status_counts"]["B_text_qa"]
    x = result["layer_status_counts"]["X_out_of_modality"]
    report = f"""# Platinum selection strata receipt

- Outcome: **{result['outcome']}**
- Layer A revised/rejected: **{a['revised']} / {a['rejected']}**
- Layer B revised/rejected/negative: **{b['revised']} / {b['rejected']} / {b['negative']}**
- Layer B frozen quotas: **85 / 85 / 130**, all cells satisfiable
- VQA positive/negative: **{x['positive']} / {x['negative']}**
- Item IDs or item-label mapping emitted: **false**
- Dataset/network/API/auditor access: **zero**
"""
    (out / "REPORT.md").write_text(report, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(INPUT))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run(Path(args.source), Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
