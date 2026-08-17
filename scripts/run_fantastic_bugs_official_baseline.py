#!/usr/bin/env python3
"""Replay the pinned Fantastic Bugs GSM response-pattern baseline.

The prediction artifact deliberately excludes Platinum labels and revised
answers.  It can therefore be locked before the separate scoring step joins
the sealed truth file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pandas as pd


EXPECTED_PICKLE_SHA256 = (
    "e1d2251b43f7b94a8709fde750e34469408d6e3c750001cdd9e5cbcf62984c94"
)
EXPECTED_CODE_COMMIT = "cf7f9a822ba18bf670802685021d470df53832df"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_item_id(question: str) -> str:
    return "fantastic-bugs-gsm-" + hashlib.sha256(question.encode("utf-8")).hexdigest()[:20]


def code_commit(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def finite_or_none(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pickle", required=True, type=Path)
    parser.add_argument("--official-code", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    pickle_path = args.pickle.expanduser().resolve()
    code_path = args.official_code.expanduser().resolve()
    out_path = args.out.expanduser().resolve()
    if sha256_file(pickle_path) != EXPECTED_PICKLE_SHA256:
        raise SystemExit("official response pickle hash mismatch")
    commit = code_commit(code_path)
    if commit != EXPECTED_CODE_COMMIT:
        raise SystemExit(f"official code commit mismatch: {commit}")

    # The upstream ``src/__init__.py`` eagerly imports its optional OpenAI,
    # Together and local-vLLM clients even though the response-only analysis
    # does not use them.  Register a namespace package so importing
    # ``src.analyze`` executes the pinned analysis/config/metrics modules but
    # not unrelated provider clients.  The analyzed source files remain byte
    # identical to upstream.
    namespace = types.ModuleType("src")
    namespace.__path__ = [str(code_path / "src")]
    sys.modules["src"] = namespace
    sys.path.insert(0, str(code_path))
    from src.analyze import analyze  # type: ignore[import-not-found]

    source = pd.read_pickle(pickle_path)
    if source.shape != (90, 997):
        raise SystemExit(f"unexpected source shape: {source.shape}")
    questions = list(source.columns.get_level_values("input.text"))
    item_ids = [stable_item_id(str(question).strip()) for question in questions]
    if len(item_ids) != len(set(item_ids)):
        raise SystemExit("stable item identifiers are not unique")

    # Remove all question metadata, labels and answers before invoking the
    # official response-only algorithm.  Only the 90 x 997 correctness matrix
    # and opaque IDs remain.
    responses = source.copy()
    responses.columns = pd.Index(item_ids, name="item_id")
    prediction = analyze(responses)
    if len(prediction) != len(item_ids):
        missing = sorted(set(item_ids) - set(prediction["item_id"]))
    else:
        missing = []

    metric_columns = [
        "tetrachoric",
        "scalability_coeff",
        "item_total_corr",
        "prediction_variance",
        "fleiss_kappa",
        "tetrachoric_gr",
        "scalability_coeff_gr",
        "item_total_corr_gr",
        "tetrachoric_vote",
        "scalability_coeff_vote",
        "item_total_corr_vote",
        "gr_mean",
        "n_invalid",
        "majority_vote",
        "or_vote",
        "and_vote",
    ]
    rows = []
    for raw in prediction.to_dict(orient="records"):
        row = {"item_id": str(raw["item_id"])}
        row.update({key: finite_or_none(raw[key]) for key in metric_columns})
        rows.append(row)
    rows.sort(key=lambda row: (float(row["gr_mean"]), row["item_id"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank

    result = {
        "schema_version": 1,
        "status": "OFFICIAL_BASELINE_PREDICTIONS_LOCKABLE",
        "official_code": {
            "path": str(code_path),
            "commit": commit,
            "analyze_py_sha256": sha256_file(code_path / "src" / "analyze.py"),
            "metrics_py_sha256": sha256_file(code_path / "src" / "metrics.py"),
        },
        "source": {"path": str(pickle_path), "sha256": sha256_file(pickle_path)},
        "input_shape": {"models": source.shape[0], "items": source.shape[1]},
        "output_items": len(rows),
        "zero_variance_items_removed": missing,
        "ranking": "gr_mean ascending, item_id ascending tie-break",
        "candidate_rule": "majority_vote == 0",
        "contains_platinum_truth": False,
        "items": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "output_items": len(rows),
                "zero_variance_items_removed": len(missing),
                "sha256": sha256_file(out_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
