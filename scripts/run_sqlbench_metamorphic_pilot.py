#!/usr/bin/env python3
"""Run a review-only SQL layout-invariance pilot over collected SQLBench outputs.

This is intentionally not an official-benchmark confirmation path. It replays
an auxiliary SQL parser over already collected model answers to pressure-test a
typed metamorphic relation. The output records that limitation explicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from benchcore.metamorphic_evaluator import (
    METAMORPHIC_CONTRACT_VERSION,
    generate_semantics_preserving_variants,
)


TARGET_PATTERN = re.compile(
    r"_to_(postgres|mysql|oracle|clickhouse|duckdb|tsql|snowflake)_",
    re.IGNORECASE,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_sidecar_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(
        "benchaudit_sqlbench_sidecar", path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import sidecar module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("classify_sql", "extract_answer", "normalize_layout_escapes"):
        if not callable(getattr(module, name, None)):
            raise TypeError(f"sidecar module lacks callable {name!r}: {path}")
    return module


def _source_manifest(
    paths: list[Path], root: Path,
) -> tuple[list[dict[str, Any]], str]:
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256_file(path),
        }
        for path in paths
    ]
    material = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return rows, _sha256_bytes(material)


def run(dataset_root: Path, sidecar_script: Path) -> dict[str, Any]:
    module = _load_sidecar_module(sidecar_script)
    logging.getLogger("sqlglot").setLevel(logging.CRITICAL)
    input_root = dataset_root / "different_model_outputs"
    input_paths = sorted(input_root.rglob("*.json"))
    if not input_paths:
        raise ValueError(f"no JSON result files under {input_root}")

    manifest, manifest_sha256 = _source_manifest(input_paths, dataset_root)
    contract = {
        "schema_version": METAMORPHIC_CONTRACT_VERSION,
        "semantic_profile": "sql_layout",
        "evaluator_identity": (
            f"auxiliary:sqlglot:{getattr(module.sqlglot, '__version__', 'unknown')}"
        ),
    }
    counts: Counter[str] = Counter()
    flips: Counter[str] = Counter()
    reference_counts: Counter[str] = Counter()
    unique_references: set[tuple[str, str]] = set()

    for path in input_paths:
        match = TARGET_PATTERN.search(path.name)
        if match is None:
            continue
        dialect = match.group(1).lower()
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise TypeError(f"expected list in {path}")
        counts["input_files"] += 1
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError(f"expected object rows in {path}")
            answer = module.extract_answer(row)
            normalized, _ = (
                module.normalize_layout_escapes(answer)
                if answer is not None
                else (None, False)
            )
            baseline = module.classify_sql(normalized, dialect)
            counts["answers"] += 1
            counts[f"baseline_{baseline['status']}"] += 1
            if baseline["syntax_valid"] is None or normalized is None:
                counts["indeterminate_answers"] += 1
            else:
                variants = generate_semantics_preserving_variants(
                    normalized, contract,
                )
                for variant in variants:
                    observed = module.classify_sql(variant.transformed, dialect)
                    counts["variant_runs"] += 1
                    if observed["syntax_valid"] is None:
                        counts["indeterminate_variant_runs"] += 1
                    elif observed["syntax_valid"] != baseline["syntax_valid"]:
                        flips[variant.transformation_id] += 1
            reference = row.get(dialect)
            if isinstance(reference, str):
                unique_references.add((dialect, reference))

    for dialect, reference in unique_references:
        normalized, _ = module.normalize_layout_escapes(reference)
        observed = module.classify_sql(normalized, dialect)
        reference_counts["unique_references"] += 1
        reference_counts[f"reference_{observed['status']}"] += 1

    return {
        "schema_version": "benchaudit-sqlbench-metamorphic-pilot-v1",
        "evidence_tier": "diagnostic",
        "confirmation_eligible": False,
        "claim_boundary": (
            "SQLGlot is an auxiliary syntax parser in this collection, not the "
            "official SQLBench correctness evaluator. Verdict flips are review "
            "candidates only and zero flips do not establish evaluator soundness."
        ),
        "protocol": {
            "relation": "evaluator_format_invariance",
            "semantic_profile": "sql_layout",
            "target_selection_uses_labels": False,
            "llm_calls": 0,
        },
        "parser": {
            "name": "sqlglot",
            "version": getattr(module.sqlglot, "__version__", "unknown"),
            "sidecar_script_sha256": _sha256_file(sidecar_script),
        },
        "source": {
            "dataset_root": str(dataset_root),
            "manifest_sha256": manifest_sha256,
            "files": manifest,
        },
        "counts": dict(sorted(counts.items())),
        "verdict_flips": dict(sorted(flips.items())),
        "reference_replay": dict(sorted(reference_counts.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--sidecar-script", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {output}")
    report = run(
        args.dataset_root.resolve(),
        args.sidecar_script.resolve(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(output),
        "answers": report["counts"].get("answers", 0),
        "variant_runs": report["counts"].get("variant_runs", 0),
        "verdict_flips": sum(report["verdict_flips"].values()),
        "confirmation_eligible": report["confirmation_eligible"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
