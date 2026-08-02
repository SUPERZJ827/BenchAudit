#!/usr/bin/env python3
"""Deterministic reanalysis of MMLU-Redux gold-correction score impact.

This implements the frozen, outcome-inspected protocol in
docs/research/MMLU_GOLD_CORRECTION_IMPACT_PROTOCOL_20260803.md.  It performs no
network or model calls.  All inference is conditional on a fixed 15-model
answer panel; the paired, subject-stratified bootstrap resamples items only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import scipy
from scipy.stats import spearmanr


PROTOCOL = Path("docs/research/MMLU_GOLD_CORRECTION_IMPACT_PROTOCOL_20260803.md")
EXPECTED_DATASET_SHA256 = "0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4"
EXPECTED_PILOT_SHA256 = "70cc9ee184db4017b323bda03061f7c3d56e57ad1ab4b1a3415263fd664072b8"
EXPECTED_ANSWER_SHA256 = {
    "amazon__nova-pro-v1.jsonl": "75c8f1239ac93b248594799beea47f9642743db0b30b07c1fb929a60420186e7",
    "cohere__command-r-08-2024.jsonl": "a550b7dd005294267c769f860297b84dbcc9607bbc52fbbebd7918e71f4cf4be",
    "deepseek.jsonl": "fa7acdf241df1a01eee1eda1a00e645c605aee503b0416edd726d089527b6101",
    "google__gemini-2.5-flash.jsonl": "2bc96f33b908d22b4703f91e33c598eafa03b6be6a3516ca9c92fdd8fb400ec9",
    "meta-llama__llama-3.1-70b-instruct.jsonl": "c19b0936c1ea6723f2f7169a0793d622eb7a43a14bd816d90c9c221d83efa72a",
    "meta-llama__llama-3.1-8b-instruct.jsonl": "afc4ad5b9f76a08ee5929771880d35019e2b98055a30711200addf5500ccaf19",
    "meta-llama__llama-3.3-70b-instruct.jsonl": "2d9ee021748d2501754cac714faafb09b7159b419a6ef11eaded46c86e5edf44",
    "microsoft__phi-4.jsonl": "ca82caa157fd6816368e80bfd805b50943e5063d80108375c20215c4d6710a20",
    "mistralai__mistral-nemo.jsonl": "f024d64e3c14fa07614e930906715af54f8394bb50eaade17fc4dcdfe789c6a8",
    "mistralai__mistral-small-24b-instruct-2501.jsonl": "7d28319ac1b4b45bdfb80bfb786ce1c443c75e824043959321672b2ca28760bf",
    "openai__gpt-4.1-mini.jsonl": "ad595880ab90cbe09411c96eba97f6e533101ebf293d66ae3f37c1a6fba3bf42",
    "openai__gpt-4o-mini.jsonl": "7e122b072aba7874815f75c62203b628970ad003ed86776a1ab1b9ba358cdcd4",
    "openai__gpt-4o.jsonl": "9b274b186d8e60a03ece47b032823f0d79d3bc879c30152b91f340a103515ec9",
    "qwen__qwen-2.5-72b-instruct.jsonl": "c043efc588e2166a525e42f6093c7469aa3f08a7517d5d1126be5bcefa072465",
    "qwen__qwen-2.5-7b-instruct.jsonl": "85c50927156ca133b0e09cad0d72a9fc71bd75dcbffdd495451686ccac22b04c",
}


class InputIntegrityError(RuntimeError):
    """Frozen inputs are missing, mismatched, or internally inconsistent."""


@dataclass(frozen=True)
class Panel:
    item_ids: tuple[str, ...]
    subjects: tuple[str, ...]
    models: tuple[str, ...]
    old_correct: np.ndarray
    new_correct: np.ndarray
    changed_gold: np.ndarray


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise InputIntegrityError(f"{path}:{lineno}: row is not an object")
            rows.append(value)
    return rows


def unique_by_id(rows: Iterable[dict[str, Any]], source: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row.get("id", "")).strip()
        if not item_id:
            raise InputIntegrityError(f"{source}: missing id")
        if item_id in result:
            raise InputIntegrityError(f"{source}: duplicate id {item_id}")
        result[item_id] = row
    return result


def verify_sha(path: Path, expected: str) -> str:
    if not path.is_file():
        raise InputIntegrityError(f"missing frozen input: {path}")
    observed = sha256_file(path)
    if observed != expected:
        raise InputIntegrityError(f"SHA-256 mismatch for {path}: {observed} != {expected}")
    return observed


def load_frozen_panel(
    dataset_path: Path,
    pilot_path: Path,
    answers_dir: Path,
    *,
    enforce_frozen_hashes: bool = True,
) -> tuple[Panel, dict[str, str]]:
    observed_hashes: dict[str, str] = {}
    if enforce_frozen_hashes:
        observed_hashes["dataset"] = verify_sha(dataset_path, EXPECTED_DATASET_SHA256)
        observed_hashes["pilot"] = verify_sha(pilot_path, EXPECTED_PILOT_SHA256)
        actual_files = {p.name for p in answers_dir.glob("*.jsonl")}
        expected_files = set(EXPECTED_ANSWER_SHA256)
        if actual_files != expected_files:
            raise InputIntegrityError(
                f"answer file set mismatch: missing={sorted(expected_files-actual_files)} "
                f"extra={sorted(actual_files-expected_files)}"
            )
        for name, expected in EXPECTED_ANSWER_SHA256.items():
            observed_hashes[f"answer:{name}"] = verify_sha(answers_dir / name, expected)

    dataset = unique_by_id(read_jsonl(dataset_path), dataset_path)
    pilot_rows = read_jsonl(pilot_path)
    pilot = unique_by_id(pilot_rows, pilot_path)
    if len(pilot) != 1000:
        raise InputIntegrityError(f"pilot has {len(pilot)} unique items, expected 1000")
    item_ids = tuple(str(row["id"]).strip() for row in pilot_rows)
    if set(item_ids) - set(dataset):
        raise InputIntegrityError("pilot IDs missing from full dataset")

    subjects: list[str] = []
    original_gold: list[str] = []
    corrected_gold: list[str] = []
    for item_id in item_ids:
        prow = pilot[item_id]
        drow = dataset[item_id]
        pmeta = prow.get("metadata") or {}
        dmeta = drow.get("metadata") or {}
        pgold = str(prow.get("gold", "")).strip()
        dgold = str(drow.get("gold", "")).strip()
        psubject = str(pmeta.get("subject", "")).strip()
        dsubject = str(dmeta.get("subject", "")).strip()
        if not pgold or not psubject or pgold != dgold or psubject != dsubject:
            raise InputIntegrityError(f"pilot/dataset gold or subject mismatch for {item_id}")
        verified = str(dmeta.get("verified_gold") or "").strip() or dgold
        subjects.append(dsubject)
        original_gold.append(dgold)
        corrected_gold.append(verified)

    answer_paths = sorted(answers_dir.glob("*.jsonl"))
    if enforce_frozen_hashes:
        answer_paths = [answers_dir / name for name in sorted(EXPECTED_ANSWER_SHA256)]
    if len(answer_paths) != 15:
        raise InputIntegrityError(f"answer panel has {len(answer_paths)} models, expected 15")

    old_columns: list[list[int]] = []
    new_columns: list[list[int]] = []
    models: list[str] = []
    expected_ids = set(item_ids)
    for path in answer_paths:
        answer_map = unique_by_id(read_jsonl(path), path)
        if set(answer_map) != expected_ids:
            raise InputIntegrityError(f"ID set mismatch for {path}")
        old_col: list[int] = []
        new_col: list[int] = []
        for idx, item_id in enumerate(item_ids):
            row = answer_map[item_id]
            for field in ("pred", "gold", "correct", "subject"):
                if field not in row:
                    raise InputIntegrityError(f"{path}: {item_id} missing {field}")
            pred = str(row["pred"]).strip()
            gold = str(row["gold"]).strip()
            subject = str(row["subject"]).strip()
            if gold != original_gold[idx] or subject != subjects[idx]:
                raise InputIntegrityError(f"{path}: gold/subject mismatch for {item_id}")
            old = int(pred == original_gold[idx])
            if not isinstance(row["correct"], bool) or int(row["correct"]) != old:
                raise InputIntegrityError(f"{path}: incorrect archived correct flag for {item_id}")
            old_col.append(old)
            new_col.append(int(pred == corrected_gold[idx]))
        models.append(path.stem)
        old_columns.append(old_col)
        new_columns.append(new_col)

    old_correct = np.asarray(old_columns, dtype=np.int8).T
    new_correct = np.asarray(new_columns, dtype=np.int8).T
    changed_gold = np.asarray(
        [old != new for old, new in zip(original_gold, corrected_gold)], dtype=np.bool_
    )
    return (
        Panel(
            item_ids=item_ids,
            subjects=tuple(subjects),
            models=tuple(models),
            old_correct=old_correct,
            new_correct=new_correct,
            changed_gold=changed_gold,
        ),
        observed_hashes,
    )


def percentile_interval(values: np.ndarray) -> list[float | None]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return [None, None]
    low, high = np.quantile(finite, [0.025, 0.975])
    return [float(low), float(high)]


def safe_spearman(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.size < 2 or np.all(left == left[0]) or np.all(right == right[0]):
        return None
    value = float(spearmanr(left, right).statistic)
    return value if np.isfinite(value) else None


def kendall_total_order(order_a: list[int], order_b: list[int]) -> float:
    rank_b = {model: i for i, model in enumerate(order_b)}
    concordant = discordant = 0
    for i, j in combinations(range(len(order_a)), 2):
        if rank_b[order_a[i]] < rank_b[order_a[j]]:
            concordant += 1
        else:
            discordant += 1
    return (concordant - discordant) / (concordant + discordant)


def stratified_bootstrap_indices(
    subjects: tuple[str, ...], replicates: int, seed: int
) -> Iterable[np.ndarray]:
    groups = [
        np.asarray([i for i, value in enumerate(subjects) if value == subject], dtype=np.int64)
        for subject in sorted(set(subjects))
    ]
    rng = np.random.Generator(np.random.PCG64(seed))
    for _ in range(replicates):
        yield np.concatenate([rng.choice(group, size=len(group), replace=True) for group in groups])


def analyze_panel(panel: Panel, *, replicates: int = 10000, seed: int = 20260803) -> dict[str, Any]:
    n_items, n_models = panel.old_correct.shape
    if n_models != len(panel.models) or n_items != len(panel.item_ids):
        raise InputIntegrityError("panel array shape mismatch")

    old_counts = panel.old_correct.sum(axis=0).astype(np.int64)
    new_counts = panel.new_correct.sum(axis=0).astype(np.int64)
    old_acc = old_counts / n_items
    new_acc = new_counts / n_items
    gains = new_acc - old_acc

    old_order = sorted(range(n_models), key=lambda i: (-int(old_counts[i]), panel.models[i]))
    new_order = sorted(range(n_models), key=lambda i: (-int(new_counts[i]), panel.models[i]))
    old_rank = {model: rank for rank, model in enumerate(old_order, 1)}
    new_rank = {model: rank for rank, model in enumerate(new_order, 1)}

    pair_specs: list[dict[str, Any]] = []
    for left, right in combinations(range(n_models), 2):
        if old_counts[left] > old_counts[right]:
            high, low = left, right
        elif old_counts[right] > old_counts[left]:
            high, low = right, left
        else:
            high, low = sorted((left, right), key=lambda i: panel.models[i])
        g0_count = int(old_counts[high] - old_counts[low])
        g1_count = int(new_counts[high] - new_counts[low])
        change_count = g1_count - g0_count
        pair_specs.append(
            {
                "high": high,
                "low": low,
                "original_tie": g0_count == 0,
                "g0_count": g0_count,
                "g1_count": g1_count,
                "change_count": change_count,
            }
        )

    model_gain_boot = np.empty((replicates, n_models), dtype=np.float64)
    pair_change_boot = np.empty((replicates, len(pair_specs)), dtype=np.float64)
    mean_relative_boot = np.empty(replicates, dtype=np.float64)
    spearman_boot = np.empty(replicates, dtype=np.float64)
    for b, indices in enumerate(stratified_bootstrap_indices(panel.subjects, replicates, seed)):
        b_old = panel.old_correct[indices].mean(axis=0)
        b_new = panel.new_correct[indices].mean(axis=0)
        b_gain = b_new - b_old
        model_gain_boot[b] = b_gain
        relative_values: list[float] = []
        for pidx, spec in enumerate(pair_specs):
            high, low = spec["high"], spec["low"]
            bg0 = float(b_old[high] - b_old[low])
            bg1 = float(b_new[high] - b_new[low])
            pair_change_boot[b, pidx] = bg1 - bg0
            if bg0 > 0:
                relative_values.append((bg1 - bg0) / bg0)
        mean_relative_boot[b] = (
            float(np.mean(relative_values)) if relative_values else np.nan
        )
        rho = safe_spearman(b_old, b_gain)
        spearman_boot[b] = rho if rho is not None else np.nan

    model_rows = []
    for idx, model in enumerate(panel.models):
        model_rows.append(
            {
                "model": model,
                "old_correct": int(old_counts[idx]),
                "corrected_correct": int(new_counts[idx]),
                "old_accuracy": float(old_acc[idx]),
                "corrected_accuracy": float(new_acc[idx]),
                "correction_gain": float(gains[idx]),
                "correction_gain_ci95": percentile_interval(model_gain_boot[:, idx]),
                "old_rank": old_rank[idx],
                "corrected_rank": new_rank[idx],
            }
        )

    pair_rows = []
    signed_relative: list[float] = []
    expanded = contracted = unchanged = flipped = 0
    for pidx, spec in enumerate(pair_specs):
        g0 = spec["g0_count"] / n_items
        g1 = spec["g1_count"] / n_items
        change = spec["change_count"] / n_items
        if spec["change_count"] > 0:
            expanded += 1
        elif spec["change_count"] < 0:
            contracted += 1
        else:
            unchanged += 1
        if spec["g1_count"] < 0:
            flipped += 1
        relative = None if spec["original_tie"] else change / g0
        if relative is not None:
            signed_relative.append(relative)
        pair_rows.append(
            {
                "original_high_model": panel.models[spec["high"]],
                "original_low_model": panel.models[spec["low"]],
                "original_tie": spec["original_tie"],
                "original_gap": g0,
                "corrected_oriented_gap": g1,
                "gap_change": change,
                "gap_change_ci95": percentile_interval(pair_change_boot[:, pidx]),
                "relative_gap_change": relative,
                "rank_flipped": spec["g1_count"] < 0,
            }
        )

    observed_rho = safe_spearman(old_acc, gains)
    mean_relative = float(np.mean(signed_relative)) if signed_relative else None
    median_relative = float(np.median(signed_relative)) if signed_relative else None
    mean_absolute_relative = (
        float(np.mean(np.abs(signed_relative))) if signed_relative else None
    )
    changed_ranks = [
        {
            "model": panel.models[i],
            "old_rank": old_rank[i],
            "corrected_rank": new_rank[i],
        }
        for i in range(n_models)
        if old_rank[i] != new_rank[i]
    ]

    return {
        "schema_version": "mmlu-gold-correction-impact-v1",
        "outcome_inspected_before_freeze": True,
        "scope": "conditional_on_fixed_15_model_panel_and_1000_items",
        "parameters": {
            "bootstrap_replicates": replicates,
            "bootstrap_seed": seed,
            "bootstrap_kind": "paired_subject_stratified_item_bootstrap",
        },
        "counts": {
            "items": n_items,
            "models": n_models,
            "subjects": len(set(panel.subjects)),
            "changed_gold_items": int(panel.changed_gold.sum()),
            "model_pairs": len(pair_specs),
        },
        "models": model_rows,
        "ranking": {
            "old_order": [panel.models[i] for i in old_order],
            "corrected_order": [panel.models[i] for i in new_order],
            "kendall_tau": kendall_total_order(old_order, new_order),
            "maximum_rank_shift": max(abs(old_rank[i] - new_rank[i]) for i in range(n_models)),
            "top1_changed": old_order[0] != new_order[0],
            "changed_ranks": changed_ranks,
        },
        "pairwise_summary": {
            "expanded": expanded,
            "contracted_including_flips": contracted,
            "unchanged": unchanged,
            "rank_flipped": flipped,
            "mean_signed_relative_gap_change": mean_relative,
            "mean_signed_relative_gap_change_ci95": percentile_interval(mean_relative_boot),
            "median_signed_relative_gap_change": median_relative,
            "mean_absolute_relative_gap_change": mean_absolute_relative,
            "correction_gain_span": float(gains.max() - gains.min()),
        },
        "fixed_panel_association": {
            "spearman_original_accuracy_vs_correction_gain": observed_rho,
            "spearman_item_bootstrap_ci95": percentile_interval(spearman_boot),
            "population_p_value_reported": False,
        },
        "pairs": pair_rows,
        "caveats": [
            "Results were inspected before this analysis protocol was frozen.",
            "The 15 models are related and are not an independent random sample.",
            "Bootstrap intervals resample items and are conditional on the fixed model panel.",
            "Pairwise intervals are exploratory and are not simultaneous family-wise intervals.",
            "No cross-benchmark or novelty claim is supported by this analysis alone.",
        ],
    }


def render_markdown(analysis: dict[str, Any]) -> str:
    counts = analysis["counts"]
    ranking = analysis["ranking"]
    pair = analysis["pairwise_summary"]
    assoc = analysis["fixed_panel_association"]
    lines = [
        "# MMLU-Redux gold-correction score impact",
        "",
        "> Outcome-inspected deterministic reanalysis; not a prospective preregistration.",
        "> Inference is conditional on the fixed 15-model panel.",
        "",
        "## Frozen panel",
        "",
        f"- Items: {counts['items']} ({counts['changed_gold_items']} changed gold labels)",
        f"- Models: {counts['models']}",
        f"- Subjects: {counts['subjects']}",
        f"- Model pairs: {counts['model_pairs']}",
        "",
        "## Model scores",
        "",
        "| Model | Original | Corrected | Gain | 95% item-bootstrap CI | Rank |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(analysis["models"], key=lambda value: value["old_rank"]):
        ci = row["correction_gain_ci95"]
        lines.append(
            f"| {row['model']} | {row['old_accuracy']:.3f} | {row['corrected_accuracy']:.3f} "
            f"| {row['correction_gain']:+.3f} | [{ci[0]:+.3f}, {ci[1]:+.3f}] "
            f"| {row['old_rank']} → {row['corrected_rank']} |"
        )
    lines += [
        "",
        "## Ranking and pairwise effects",
        "",
        f"- Kendall tau: **{ranking['kendall_tau']:.3f}**",
        f"- Maximum rank shift: **{ranking['maximum_rank_shift']}**",
        f"- Top-1 changed: **{str(ranking['top1_changed']).lower()}**",
        f"- Expanded / contracted / unchanged gaps: **{pair['expanded']} / "
        f"{pair['contracted_including_flips']} / {pair['unchanged']}**",
        f"- Rank-flipped pairs: **{pair['rank_flipped']}**",
        f"- Mean signed relative gap change: **{pair['mean_signed_relative_gap_change']:+.3%}** "
        f"(95% item-bootstrap CI [{pair['mean_signed_relative_gap_change_ci95'][0]:+.3%}, "
        f"{pair['mean_signed_relative_gap_change_ci95'][1]:+.3%}])",
        f"- Mean absolute relative gap change (descriptive): "
        f"{pair['mean_absolute_relative_gap_change']:.3%}",
        "",
        "## Fixed-panel association",
        "",
        f"Spearman(original accuracy, correction gain) = **"
        f"{assoc['spearman_original_accuracy_vs_correction_gain']:.3f}**; paired item-bootstrap "
        f"95% interval [{assoc['spearman_item_bootstrap_ci95'][0]:.3f}, "
        f"{assoc['spearman_item_bootstrap_ci95'][1]:.3f}]. This is descriptive for the fixed, "
        "non-independent model panel; no model-population p-value is reported.",
        "",
        "## Interpretation boundary",
        "",
        "In this panel, erroneous gold labels usually compressed model score gaps: most gaps "
        "expanded after correction. The ranking itself was nearly unchanged. This analysis does "
        "not establish novelty, cross-benchmark generality, or that any fixed percentage of model "
        "comparisons is unreliable.",
        "",
    ]
    return "\n".join(lines) + "\n"


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def build_receipt(
    *,
    panel: Panel,
    observed_hashes: dict[str, str],
    before: dict[str, str],
    after: dict[str, str],
    analysis_bytes: bytes,
    report_bytes: bytes,
    code_sha256: str,
    protocol_sha256: str,
    commit: str,
) -> dict[str, Any]:
    return {
        "schema_version": "mmlu-gold-correction-impact-receipt-v1",
        "status": "PASS_REANALYSIS",
        "outcome_inspected_before_freeze": True,
        "api_attempts": 0,
        "network_attempts": 0,
        "git_commit": commit,
        "code_sha256": code_sha256,
        "protocol_sha256": protocol_sha256,
        "input_hashes": observed_hashes,
        "input_bytes_unchanged": before == after,
        "integrity_gates": {
            "exactly_1000_unique_items": len(panel.item_ids) == 1000,
            "exactly_15_models": len(panel.models) == 15,
            "complete_id_join": panel.old_correct.shape == (1000, 15),
            "archived_correct_flags_recomputed": True,
            "frozen_hashes_verified": True,
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "outputs": {
            "analysis_sha256": hashlib.sha256(analysis_bytes).hexdigest(),
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        },
    }


def run(args: argparse.Namespace) -> None:
    dataset = Path(args.dataset).resolve()
    pilot = Path(args.pilot).resolve()
    answers = Path(args.answers_dir).resolve()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise InputIntegrityError(f"output directory must be empty: {out}")

    frozen_paths = [dataset, pilot] + [answers / name for name in sorted(EXPECTED_ANSWER_SHA256)]
    before = {str(path): sha256_file(path) for path in frozen_paths}
    panel, observed_hashes = load_frozen_panel(dataset, pilot, answers)
    analysis = analyze_panel(panel, replicates=args.bootstrap_replicates, seed=args.bootstrap_seed)
    analysis_bytes = stable_json_bytes(analysis)
    report_bytes = render_markdown(analysis).encode("utf-8")
    (out / "analysis.json").write_bytes(analysis_bytes)
    (out / "REPORT.md").write_bytes(report_bytes)
    after = {str(path): sha256_file(path) for path in frozen_paths}
    if before != after:
        raise InputIntegrityError("a frozen input changed during execution")

    script_path = Path(__file__).resolve()
    protocol_path = PROTOCOL.resolve()
    receipt = build_receipt(
        panel=panel,
        observed_hashes=observed_hashes,
        before=before,
        after=after,
        analysis_bytes=analysis_bytes,
        report_bytes=report_bytes,
        code_sha256=sha256_file(script_path),
        protocol_sha256=sha256_file(protocol_path),
        commit=git_head(),
    )
    (out / "receipt.json").write_bytes(stable_json_bytes(receipt))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--pilot", default="experiments/mmlu_redux_pilot1000.jsonl")
    parser.add_argument("--answers-dir", default="reports/ranking_impact/answers")
    parser.add_argument("--out", required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260803)
    args = parser.parse_args()
    if args.bootstrap_replicates != 10000 or args.bootstrap_seed != 20260803:
        parser.error("frozen protocol requires 10000 replicates and seed 20260803")
    return args


if __name__ == "__main__":
    try:
        run(parse_args())
    except InputIntegrityError as exc:
        print(f"NOT_IDENTIFIABLE_INPUT: {exc}", file=sys.stderr)
        raise SystemExit(2)
