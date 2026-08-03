#!/usr/bin/env python3
"""Select the frozen 897-item Platinum blind holdout without exposing truth."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy
import pyarrow
import pyarrow.parquet as pq

from scripts.preflight_platinum_holdout_availability import row_identity


ROOT = Path(__file__).resolve().parents[1]
AVAILABILITY = ROOT / "reports/platinum_untouched_holdout_availability_20260803/availability.json"
STRATA_RECEIPT = ROOT / "reports/platinum_selection_strata_receipt_20260803/receipt.json"
V1 = ROOT / "docs/research/PLATINUM_BLIND_DETECTION_HOLDOUT_SELECTION_PROTOCOL_20260803.md"
V2 = ROOT / "docs/research/PLATINUM_BLIND_DETECTION_HOLDOUT_SELECTION_PROTOCOL_V2_20260803.md"
V3 = ROOT / "docs/research/PLATINUM_BLIND_DETECTION_HOLDOUT_SELECTION_PROTOCOL_V3_20260803.md"
EXPECTED = {
    "availability": "2a1b1164f1e9831e5554abfcac14df44cf78963957cce219ecc9381f2d3e7f77",
    "strata_receipt": "c14921699fd3db461fb424f50c1befac9e233b493f5e7ef4caca03e6399f9ce9",
    "v1": "2ad4cc5c06039f9281e07b7d97372b3588fd20f104cefb0a9879425f19c105b1",
    "v2": "6aec64799c1ee833b0c426a4673ca3424f6bb9786fd6986d09449cb43137ef1c",
    "v3": "19ad4fcdaccd2a57e3f134fd149f6c611f92801ef1ae8e01f22c24c770a6d613",
}
DATASET_REVISION = "51920a33bfb4620c789729ace14141e87a14969b"
SEED = "benchaudit-platinum-blind-holdout-v1-20260803"
LAYERS = {
    "A_arithmetic": ("multiarith", "singleop", "singleq"),
    "B_text_qa": ("drop", "hotpotqa", "squad"),
    "C_reasoning_coreference": (
        "bbh_logical_deduction_three_objects", "bbh_navigate",
        "bbh_object_counting", "winograd_wsc",
    ),
}
LAYER_B_QUOTAS = {
    "drop": {"revised": 40, "rejected": 30, "negative": 30},
    "hotpotqa": {"revised": 25, "rejected": 25, "negative": 50},
    "squad": {"revised": 20, "rejected": 30, "negative": 50},
}
LAYER_C_NEGATIVE_QUOTAS = {
    "bbh_logical_deduction_three_objects": 35,
    "bbh_navigate": 35,
    "bbh_object_counting": 35,
    "winograd_wsc": 35,
}
POSITIVE = frozenset({"revised", "rejected"})
NEGATIVE = frozenset({"consensus", "verified"})
FORBIDDEN_PUBLIC_KEYS = frozenset(
    {"cleaning_status", "truth", "binary_truth", "gold", "target", "question", "prompt", "source_row_index"}
)


class SelectionError(RuntimeError):
    pass


def stable_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_frozen_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    paths = {
        "availability": AVAILABILITY, "strata_receipt": STRATA_RECEIPT,
        "v1": V1, "v2": V2, "v3": V3,
    }
    for name, path in paths.items():
        if sha256_file(path) != EXPECTED[name]:
            raise SelectionError(f"frozen input hash mismatch: {name}")
    availability = json.loads(AVAILABILITY.read_text())
    strata = json.loads(STRATA_RECEIPT.read_text())
    if strata.get("outcome") != "PASS_SELECTION_STRATA_AVAILABLE":
        raise SelectionError("aggregate strata receipt is not PASS")
    if strata.get("item_label_mapping_emitted") is not False:
        raise SelectionError("aggregate receipt leaked item-label mapping")
    if not all(
        gate.get("passed") and all(value >= 0 for value in gate["headroom"].values())
        for gate in strata["layer_b_quota_gates"].values()
    ):
        raise SelectionError("aggregate quota gate failed")
    return availability, strata


def stratum(status: str) -> str:
    if status in POSITIVE:
        return status
    if status in NEGATIVE:
        return "negative"
    raise SelectionError(f"unknown cleaning_status: {status!r}")


def rank(seed: str, config: str, truth_stratum: str, opaque_id: str) -> str:
    payload = "\0".join((seed, config, truth_stratum, opaque_id)).encode()
    return hashlib.sha256(payload).hexdigest()


def load_rows(data_root: Path, availability: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    artifact_by_config = {
        row["config"]: row["artifact"] for row in availability["config_aggregates"]
    }
    included = {config for configs in LAYERS.values() for config in configs}
    result: dict[str, list[dict[str, str]]] = {}
    for config in sorted(included):
        path = data_root / "platinum-bench" / config / "test-00000-of-00001.parquet"
        if not path.is_file() or sha256_file(path) != artifact_by_config[config]["sha256"]:
            raise SelectionError(f"dataset artifact mismatch: {config}")
        rows: list[dict[str, str]] = []
        for source in pq.read_table(path).to_pylist():
            status = source.get("cleaning_status")
            if status not in POSITIVE | NEGATIVE:
                raise SelectionError(f"unknown status in {config}")
            rows.append({
                "opaque_id": row_identity(config, source),
                "status": status,
                "stratum": stratum(status),
            })
        counts = Counter(row["opaque_id"] for row in rows)
        if any(value != 1 for value in counts.values()):
            raise SelectionError(f"identity collision: {config}")
        result[config] = rows
    return result


def take_ranked(
    rows: Iterable[dict[str, str]], *, seed: str, config: str, truth_stratum: str, quota: int
) -> list[dict[str, str]]:
    eligible = [row for row in rows if row["stratum"] == truth_stratum]
    if len(eligible) < quota:
        raise SelectionError(f"insufficient {config}/{truth_stratum}: {len(eligible)} < {quota}")
    return sorted(
        eligible,
        key=lambda row: (rank(seed, config, truth_stratum, row["opaque_id"]), row["opaque_id"]),
    )[:quota]


def select(rows: dict[str, list[dict[str, str]]], *, seed: str = SEED) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    # Layer A is a complete census.
    for config in LAYERS["A_arithmetic"]:
        selected.extend({**row, "config": config, "layer": "A_arithmetic"} for row in rows[config])
    # Layer B uses exact config × status quotas.
    for config, quotas in LAYER_B_QUOTAS.items():
        for truth_stratum, quota in quotas.items():
            chosen = take_ranked(rows[config], seed=seed, config=config, truth_stratum=truth_stratum, quota=quota)
            selected.extend({**row, "config": config, "layer": "B_text_qa"} for row in chosen)
    # Layer C includes every positive and samples negative controls.
    for config, negative_quota in LAYER_C_NEGATIVE_QUOTAS.items():
        positives = [row for row in rows[config] if row["status"] in POSITIVE]
        selected.extend({**row, "config": config, "layer": "C_reasoning_coreference"} for row in positives)
        negatives = take_ranked(rows[config], seed=seed, config=config, truth_stratum="negative", quota=negative_quota)
        selected.extend({**row, "config": config, "layer": "C_reasoning_coreference"} for row in negatives)
    identities = [row["opaque_id"] for row in selected]
    if len(identities) != len(set(identities)):
        raise SelectionError("selected identity collision across configs")
    return sorted(selected, key=lambda row: (row["layer"], row["config"], row["opaque_id"]))


def selection_counts(selected: list[dict[str, str]]) -> dict[str, Any]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in selected:
        counts[row["layer"]][row["status"]] += 1
    return {
        layer: {
            "rows": sum(counter.values()),
            "revised": counter["revised"], "rejected": counter["rejected"],
            "positive": counter["revised"] + counter["rejected"],
            "negative": counter["consensus"] + counter["verified"],
        }
        for layer, counter in sorted(counts.items())
    }


def build_artifacts(selected: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
    item_set_sha = hashlib.sha256(stable_bytes(sorted(row["opaque_id"] for row in selected))).hexdigest()
    truth = {
        "schema_version": "platinum-blind-holdout-truth-v1",
        "dataset_revision": DATASET_REVISION,
        "item_set_sha256": item_set_sha,
        "items": [
            {
                "opaque_id": row["opaque_id"], "config": row["config"], "layer": row["layer"],
                "cleaning_status": row["status"],
                "binary_truth": "positive" if row["status"] in POSITIVE else "negative",
            }
            for row in selected
        ],
    }
    truth_sha = hashlib.sha256(stable_bytes(truth)).hexdigest()
    public = {
        "schema_version": "platinum-blind-holdout-manifest-v1",
        "dataset_revision": DATASET_REVISION,
        "selection_protocol_sha256": {"v1": EXPECTED["v1"], "v2": EXPECTED["v2"], "v3": EXPECTED["v3"]},
        "strata_receipt_sha256": EXPECTED["strata_receipt"],
        "seed": SEED,
        "selection_algorithm": "sha256-rank-v1",
        "item_set_sha256": item_set_sha,
        "sealed_truth_sha256": truth_sha,
        "counts": selection_counts(selected),
        "items": [
            {"opaque_id": row["opaque_id"], "config": row["config"], "layer": row["layer"]}
            for row in selected
        ],
        "truth_unsealed": False,
        "truth_fields_emitted": False,
        "numpy_rng_instantiated": False,
    }
    assert not (FORBIDDEN_PUBLIC_KEYS & set().union(*(item.keys() for item in public["items"])))
    return public, truth


def run(data_root: Path, manifest_out: Path, truth_out: Path, receipt_out: Path) -> None:
    availability, _strata = verify_frozen_inputs()
    if ROOT == truth_out.resolve() or ROOT in truth_out.resolve().parents:
        raise SelectionError("sealed truth path must be outside repository")
    if truth_out.exists():
        raise SelectionError("refusing to overwrite sealed truth")
    selected = select(load_rows(data_root, availability))
    public, truth = build_artifacts(selected)
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    truth_out.parent.mkdir(parents=True, exist_ok=True)
    receipt_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_bytes(stable_bytes(public))
    truth_out.write_bytes(stable_bytes(truth))
    os.chmod(truth_out, 0o600)
    receipt = {
        "schema_version": "platinum-blind-holdout-selection-receipt-v1",
        "outcome": "PASS_BLIND_HOLDOUT_MANIFEST_897",
        "manifest_sha256": sha256_file(manifest_out),
        "sealed_truth_sha256": sha256_file(truth_out),
        "sealed_truth_path_emitted": False,
        "public_item_count": len(public["items"]),
        "public_item_set_sha256": public["item_set_sha256"],
        "counts": public["counts"],
        "protocol_sha256": {"v1": EXPECTED["v1"], "v2": EXPECTED["v2"], "v3": EXPECTED["v3"]},
        "selector_sha256": sha256_file(Path(__file__)),
        "runtime": {"python": os.sys.version.split()[0], "pyarrow": pyarrow.__version__, "numpy": numpy.__version__},
        "item_text_emitted": False,
        "truth_fields_emitted_in_public_manifest": False,
        "network_attempts": 0,
        "api_attempts": 0,
        "auditor_executed": False,
    }
    receipt_out.write_bytes(stable_bytes(receipt))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--manifest-out", required=True)
    parser.add_argument("--truth-out", required=True)
    parser.add_argument("--receipt-out", required=True)
    args = parser.parse_args()
    run(Path(args.data_root), Path(args.manifest_out), Path(args.truth_out), Path(args.receipt_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
