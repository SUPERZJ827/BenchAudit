#!/usr/bin/env python3
"""Frozen subject-grouped robustness diagnostic for MMLU-Redux.

This script deliberately separates label-free score preparation from
label-aware evaluation.  It does not call any API or execute benchmark tasks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.stats import rankdata, wilcoxon
from sklearn.metrics import average_precision_score


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "reports" / "mmlu_psychometric_feasibility_20260722"
FEATURE_PATH = SOURCE_DIR / "features.json"
LABEL_PATH = SOURCE_DIR / "labels.json"
SOURCE_SCORE_PATH = SOURCE_DIR / "scores.json"
PROTOCOL_PATH = ROOT / "scratchpad" / "MMLU_SUBJECT_GROUPED_PROTOCOL_20260723.md"
OUTPUT_DIR = ROOT / "reports" / "mmlu_subject_grouped_robustness_20260723"
FOLD_PATH = OUTPUT_DIR / "subject_folds.json"
SCORE_PATH = OUTPUT_DIR / "scores.json"
METRIC_PATH = OUTPUT_DIR / "metrics.json"
REPORT_PATH = OUTPUT_DIR / "report.md"

SEED = 20260723
N_FOLDS = 5
N_BOOTSTRAP = 10_000
TIE_EPSILON = 1e-12
EXPECTED_SHA256 = {
    FEATURE_PATH: "cfe1c0eb53d4d72f5b20b1c49005b8fa469f4de588b5db6ca4766fc019644651",
    LABEL_PATH: "759766eb7b98da10f7ba8ae9d618a54985be19a74ddf8e327e7715cae0fcd5aa",
    SOURCE_SCORE_PATH: "ac994b02edb2ef9883740ba42bdb777fff7805ff83e0d8716bf6278e5633bc17",
    PROTOCOL_PATH: "ca6f10c2ebfd1e791344a969b4bb07f76ef59e3ff83c253ebbd49ed6c5b521a4",
}
METHODS = [
    "benchaudit_score",
    "audit_error_rate_fusion",
    "audit_majority_fusion",
    "audit_psychometric_fusion",
]
METHOD_LABELS = {
    "benchaudit_score": "BenchAudit",
    "audit_error_rate_fusion": "BenchAudit + error rate",
    "audit_majority_fusion": "BenchAudit + majority disagreement",
    "audit_psychometric_fusion": "BenchAudit + psychometric fusion",
}
SCOPES = {
    "objective_vs_ok": {
        "positive_key": "is_objective",
        "minimum_positive_per_subject": 3,
    },
    "any_error_vs_ok": {
        "positive_key": "is_any_error",
        "minimum_positive_per_subject": 3,
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def stable_json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    path.write_text(text + "\n", encoding="utf-8")


def verify_frozen_inputs(include_labels: bool) -> None:
    paths = [FEATURE_PATH, SOURCE_SCORE_PATH, PROTOCOL_PATH]
    if include_labels:
        paths.append(LABEL_PATH)
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        if actual != EXPECTED_SHA256[path]:
            raise ValueError(
                f"frozen input changed: {path}; expected "
                f"{EXPECTED_SHA256[path]}, got {actual}"
            )


def refuse_label_bearing_scoring_input(path: Path) -> None:
    payload = path.read_bytes()
    forbidden = (b"error_type", b"is_objective", b"is_any_error", b"is_ok")
    found = [token.decode() for token in forbidden if token in payload]
    if found:
        raise AssertionError(f"label-bearing scoring input {path}: {found}")


def percentiles(values: np.ndarray) -> np.ndarray:
    """Return tie-aware percentile ranks on [0, 1]."""
    if values.ndim != 1:
        raise ValueError("percentiles expects a one-dimensional array")
    if len(values) <= 1:
        return np.zeros(len(values), dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("scores must be finite")
    return (rankdata(values, method="average") - 1.0) / (len(values) - 1.0)


def assign_subject_folds(
    subjects: dict[str, int], n_folds: int = N_FOLDS
) -> list[dict[str, Any]]:
    """Greedily balance whole subjects by item count, without labels."""
    if n_folds < 2:
        raise ValueError("at least two folds are required")
    folds = [
        {"fold": index, "n_items": 0, "subjects": []}
        for index in range(n_folds)
    ]
    for subject, count in sorted(subjects.items(), key=lambda row: (-row[1], row[0])):
        target = min(folds, key=lambda fold: (fold["n_items"], fold["fold"]))
        target["subjects"].append(subject)
        target["n_items"] += count
    for fold in folds:
        fold["subjects"].sort()
        fold["n_subjects"] = len(fold["subjects"])
    return folds


def prepare() -> None:
    """Create folds and the four scores without opening the label artifact."""
    verify_frozen_inputs(include_labels=False)
    refuse_label_bearing_scoring_input(FEATURE_PATH)
    refuse_label_bearing_scoring_input(SOURCE_SCORE_PATH)

    features = load_json(FEATURE_PATH)
    source_scores = load_json(SOURCE_SCORE_PATH)
    feature_items = features.get("items", {})
    score_items = source_scores.get("items", {})
    if set(feature_items) != set(score_items):
        raise ValueError("feature and source-score ID sets differ")
    if len(feature_items) != 1000:
        raise ValueError(f"expected 1,000 items, found {len(feature_items)}")

    subject_counts = Counter(
        str(row.get("subject", "")) for row in feature_items.values()
    )
    if "" in subject_counts:
        raise ValueError("feature item is missing subject")
    if len(subject_counts) != 57:
        raise ValueError(f"expected 57 subjects, found {len(subject_counts)}")
    folds = assign_subject_folds(dict(subject_counts))
    subject_to_fold: dict[str, int] = {}
    for fold in folds:
        for subject in fold["subjects"]:
            if subject in subject_to_fold:
                raise AssertionError(f"subject split across folds: {subject}")
            subject_to_fold[subject] = int(fold["fold"])
    if set(subject_to_fold) != set(subject_counts):
        raise AssertionError("not every subject was assigned")

    item_ids = sorted(feature_items)
    arrays = {
        name: np.array(
            [float(score_items[item_id][name]) for item_id in item_ids],
            dtype=float,
        )
        for name in [
            "benchaudit_score",
            "error_rate",
            "majority_against_gold",
            "psychometric_fusion",
            "audit_psychometric_fusion",
        ]
    }
    audit_percentile = percentiles(arrays["benchaudit_score"])
    fused = {
        "audit_error_rate_fusion": (
            audit_percentile + percentiles(arrays["error_rate"])
        )
        / 2.0,
        "audit_majority_fusion": (
            audit_percentile + percentiles(arrays["majority_against_gold"])
        )
        / 2.0,
        "audit_psychometric_fusion": (
            audit_percentile + percentiles(arrays["psychometric_fusion"])
        )
        / 2.0,
    }
    maximum_replay_error = float(
        np.max(
            np.abs(
                fused["audit_psychometric_fusion"]
                - arrays["audit_psychometric_fusion"]
            )
        )
    )
    if maximum_replay_error > 1e-12:
        raise AssertionError(
            "failed to reproduce frozen audit_psychometric_fusion: "
            f"max error={maximum_replay_error}"
        )

    fold_doc = {
        "schema_version": 1,
        "created_by": Path(__file__).name,
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "label_free": True,
        "assignment_rule": (
            "subjects sorted by (-item_count, subject); greedy to minimum-size "
            "fold with fold-index tie break"
        ),
        "n_folds": N_FOLDS,
        "n_items": len(item_ids),
        "n_subjects": len(subject_counts),
        "folds": folds,
        "item_to_fold": {
            item_id: subject_to_fold[str(feature_items[item_id]["subject"])]
            for item_id in item_ids
        },
        "subject_to_fold": subject_to_fold,
        "source_sha256": {
            str(FEATURE_PATH.relative_to(ROOT)): sha256_file(FEATURE_PATH),
        },
    }
    score_rows: dict[str, Any] = {}
    for index, item_id in enumerate(item_ids):
        score_rows[item_id] = {
            "subject": str(feature_items[item_id]["subject"]),
            "fold": int(fold_doc["item_to_fold"][item_id]),
            "benchaudit_score": float(arrays["benchaudit_score"][index]),
            "audit_error_rate_fusion": float(
                fused["audit_error_rate_fusion"][index]
            ),
            "audit_majority_fusion": float(
                fused["audit_majority_fusion"][index]
            ),
            "audit_psychometric_fusion": float(
                fused["audit_psychometric_fusion"][index]
            ),
        }
    score_doc = {
        "schema_version": 1,
        "created_by": Path(__file__).name,
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "promotion_ceiling": "review",
        "label_free": True,
        "methods": METHODS,
        "fusion_rule": (
            "0.5 * global percentile(BenchAudit) + "
            "0.5 * global percentile(component)"
        ),
        "psychometric_replay_max_abs_error": maximum_replay_error,
        "source_sha256": {
            str(FEATURE_PATH.relative_to(ROOT)): sha256_file(FEATURE_PATH),
            str(SOURCE_SCORE_PATH.relative_to(ROOT)): sha256_file(
                SOURCE_SCORE_PATH
            ),
        },
        "items": score_rows,
    }
    stable_json_dump(FOLD_PATH, fold_doc)
    stable_json_dump(SCORE_PATH, score_doc)
    refuse_label_bearing_scoring_input(FOLD_PATH)
    refuse_label_bearing_scoring_input(SCORE_PATH)
    print(
        f"prepared {len(item_ids)} items / {len(subject_counts)} subjects; "
        f"folds={sha256_file(FOLD_PATH)[:12]}, scores={sha256_file(SCORE_PATH)[:12]}"
    )


def exact_topk_metrics(
    item_ids: Iterable[str],
    scores: dict[str, float],
    positives: set[str],
    ks: Iterable[int],
) -> dict[str, Any]:
    """AP plus exact expected P@K under uniform ordering within score ties."""
    ids = list(item_ids)
    if not ids:
        raise ValueError("empty evaluation pool")
    y = np.array([1 if item_id in positives else 0 for item_id in ids], dtype=int)
    s = np.array([scores[item_id] for item_id in ids], dtype=float)
    if not np.all(np.isfinite(s)):
        raise ValueError("non-finite evaluation score")
    n_positive = int(y.sum())
    if n_positive == 0 or n_positive == len(ids):
        raise ValueError("AP requires both positive and negative examples")
    result: dict[str, Any] = {
        "n": len(ids),
        "positives": n_positive,
        "negatives": len(ids) - n_positive,
        "prevalence": n_positive / len(ids),
        "average_precision": float(average_precision_score(y, s)),
    }
    groups: list[tuple[int, int]] = []
    for score in sorted(set(float(value) for value in s), reverse=True):
        mask = s == score
        groups.append((int(mask.sum()), int(y[mask].sum())))
    for k in sorted(set(int(value) for value in ks if 0 < value <= len(ids))):
        remaining = k
        expected_tp = 0.0
        for group_n, group_positive in groups:
            if remaining <= 0:
                break
            take = min(remaining, group_n)
            expected_tp += take * group_positive / group_n
            remaining -= take
        result[f"precision_at_{k}"] = expected_tp / k
        result[f"recall_at_{k}"] = expected_tp / n_positive
        result[f"lift_at_{k}"] = (
            result[f"precision_at_{k}"] / result["prevalence"]
        )
    return result


def bootstrap_mean_delta(deltas: np.ndarray) -> dict[str, Any]:
    if deltas.ndim != 1 or len(deltas) == 0:
        raise ValueError("bootstrap requires a nonempty one-dimensional array")
    rng = np.random.default_rng(SEED)
    indices = rng.integers(0, len(deltas), size=(N_BOOTSTRAP, len(deltas)))
    means = deltas[indices].mean(axis=1)
    return {
        "n_resamples": N_BOOTSTRAP,
        "seed": SEED,
        "observed_mean": float(deltas.mean()),
        "ci95": [
            float(np.quantile(means, 0.025)),
            float(np.quantile(means, 0.975)),
        ],
    }


def paired_summary(
    subject_metrics: dict[str, dict[str, dict[str, float]]]
) -> dict[str, Any]:
    simple = "audit_error_rate_fusion"
    complex_method = "audit_psychometric_fusion"
    subjects = sorted(subject_metrics)
    deltas = np.array(
        [
            subject_metrics[subject][complex_method]["average_precision"]
            - subject_metrics[subject][simple]["average_precision"]
            for subject in subjects
        ],
        dtype=float,
    )
    wins = int(np.sum(deltas > TIE_EPSILON))
    losses = int(np.sum(deltas < -TIE_EPSILON))
    ties = len(deltas) - wins - losses
    nonzero = deltas[np.abs(deltas) > TIE_EPSILON]
    if len(nonzero):
        test = wilcoxon(nonzero, alternative="two-sided", method="auto")
        wilcoxon_result = {
            "n_nonzero": len(nonzero),
            "statistic": float(test.statistic),
            "pvalue": float(test.pvalue),
            "interpretation": "descriptive only; labels were previously inspected",
        }
    else:
        wilcoxon_result = {
            "n_nonzero": 0,
            "statistic": 0.0,
            "pvalue": 1.0,
            "interpretation": "all paired deltas are ties",
        }
    return {
        "comparison": f"{complex_method} - {simple}",
        "n_subjects": len(subjects),
        "subjects": subjects,
        "mean_delta": float(deltas.mean()),
        "median_delta": float(np.median(deltas)),
        "minimum_delta": float(deltas.min()),
        "maximum_delta": float(deltas.max()),
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "bootstrap": bootstrap_mean_delta(deltas),
        "wilcoxon": wilcoxon_result,
        "per_subject_delta": {
            subject: float(delta)
            for subject, delta in zip(subjects, deltas, strict=True)
        },
    }


def evaluate_scope(
    scope_name: str,
    labels: dict[str, dict[str, Any]],
    score_rows: dict[str, dict[str, Any]],
    fold_doc: dict[str, Any],
) -> dict[str, Any]:
    spec = SCOPES[scope_name]
    positive_key = str(spec["positive_key"])
    all_ids = sorted(score_rows)
    if scope_name == "objective_vs_ok":
        pool = [
            item_id
            for item_id in all_ids
            if labels[item_id]["is_objective"] or labels[item_id]["is_ok"]
        ]
    else:
        pool = all_ids
    positives = {item_id for item_id in pool if labels[item_id][positive_key]}
    scores = {
        method: {item_id: float(score_rows[item_id][method]) for item_id in pool}
        for method in METHODS
    }
    full = {
        method: exact_topk_metrics(
            pool, scores[method], positives, ks=(20, 50, 100)
        )
        for method in METHODS
    }

    folds: list[dict[str, Any]] = []
    fold_deltas: list[float] = []
    for fold in fold_doc["folds"]:
        fold_index = int(fold["fold"])
        ids = [
            item_id
            for item_id in pool
            if int(score_rows[item_id]["fold"]) == fold_index
        ]
        fold_positives = positives & set(ids)
        metrics = {
            method: exact_topk_metrics(
                ids,
                scores[method],
                fold_positives,
                ks=(20, 50),
            )
            for method in METHODS
        }
        delta = (
            metrics["audit_psychometric_fusion"]["average_precision"]
            - metrics["audit_error_rate_fusion"]["average_precision"]
        )
        fold_deltas.append(delta)
        folds.append(
            {
                "fold": fold_index,
                "n_subjects": int(fold["n_subjects"]),
                "subjects": list(fold["subjects"]),
                "metrics": metrics,
                "complex_minus_simple_ap": delta,
            }
        )

    subject_to_ids: dict[str, list[str]] = defaultdict(list)
    for item_id in pool:
        subject_to_ids[str(score_rows[item_id]["subject"])].append(item_id)
    eligible: dict[str, dict[str, dict[str, float]]] = {}
    exclusions: dict[str, dict[str, int]] = {}
    minimum_positive = int(spec["minimum_positive_per_subject"])
    for subject, ids in sorted(subject_to_ids.items()):
        subject_positives = positives & set(ids)
        n_positive = len(subject_positives)
        n_negative = len(ids) - n_positive
        if n_positive < minimum_positive or n_negative < 5:
            exclusions[subject] = {
                "positives": n_positive,
                "negatives": n_negative,
            }
            continue
        eligible[subject] = {
            method: exact_topk_metrics(
                ids, scores[method], subject_positives, ks=()
            )
            for method in METHODS
        }
    if not eligible:
        raise ValueError(f"{scope_name}: no eligible subjects")
    macro_ap = {
        method: float(
            statistics.mean(
                metrics[method]["average_precision"]
                for metrics in eligible.values()
            )
        )
        for method in METHODS
    }
    paired = paired_summary(eligible)
    paired["positive_fold_count"] = sum(delta > 0 for delta in fold_deltas)
    paired["fold_deltas"] = fold_deltas
    return {
        "positive_key": positive_key,
        "full": full,
        "folds": folds,
        "subject_analysis": {
            "eligibility": {
                "minimum_positives": minimum_positive,
                "minimum_ok_negatives": 5,
                "n_eligible": len(eligible),
                "n_excluded": len(exclusions),
                "excluded": exclusions,
            },
            "macro_average_precision": macro_ap,
            "per_subject": eligible,
            "paired_complex_vs_simple": paired,
        },
    }


def decide(primary: dict[str, Any]) -> dict[str, Any]:
    paired = primary["subject_analysis"]["paired_complex_vs_simple"]
    conditions = {
        "mean_delta_at_least_0_010": paired["mean_delta"] >= 0.010,
        "bootstrap_lower_bound_above_zero": (
            paired["bootstrap"]["ci95"][0] > 0.0
        ),
        "wins_exceed_losses": paired["wins"] > paired["losses"],
        "positive_in_at_least_four_folds": paired["positive_fold_count"] >= 4,
    }
    use_complex = all(conditions.values())
    return {
        "conditions": conditions,
        "all_conditions_pass": use_complex,
        "recommendation": (
            "engineer_complex_psychometric_fusion"
            if use_complex
            else "use_simple_audit_plus_error_rate"
        ),
        "evidence_ceiling": "review",
    }


def fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def render_report(metrics: dict[str, Any]) -> str:
    primary = metrics["evaluation"]["objective_vs_ok"]
    secondary = metrics["evaluation"]["any_error_vs_ok"]
    paired = primary["subject_analysis"]["paired_complex_vs_simple"]
    decision = metrics["decision"]
    lines = [
        "# MMLU-Redux：按 subject 分组的候选排序稳健性实验",
        "",
        "> 结论先行：这是对已冻结分数的跨学科稳健性诊断，不是一个从未看过标签的全新 holdout。",
        "> 全程使用历史落盘结果，不调用 API，不重新执行 benchmark；所有统计候选仍为 `review-only`。",
        "",
        "## 1. 最终裁决",
        "",
    ]
    if decision["all_conditions_pass"]:
        lines.append(
            "**复杂 psychometric fusion 通过了预先冻结的四项门槛，建议继续工程化。**"
        )
    else:
        lines.append(
            "**复杂 psychometric fusion 未同时通过四项门槛；建议采用更简单的 "
            "`BenchAudit + error rate` 作为便宜的 Q&A 候选排序前端。**"
        )
    lines.extend(
        [
            "",
            "| 冻结门槛 | 实际值 | 是否通过 |",
            "|---|---:|:---:|",
            (
                "| 配对 subject 平均 AP 增益 ≥ 0.010 | "
                f"{paired['mean_delta']:+.4f} | "
                f"{'✓' if decision['conditions']['mean_delta_at_least_0_010'] else '✗'} |"
            ),
            (
                "| subject bootstrap 95% CI 下界 > 0 | "
                f"[{paired['bootstrap']['ci95'][0]:+.4f}, "
                f"{paired['bootstrap']['ci95'][1]:+.4f}] | "
                f"{'✓' if decision['conditions']['bootstrap_lower_bound_above_zero'] else '✗'} |"
            ),
            (
                "| 胜出的 subject 多于落后的 subject | "
                f"{paired['wins']} / {paired['ties']} / {paired['losses']} "
                "(胜/平/负) | "
                f"{'✓' if decision['conditions']['wins_exceed_losses'] else '✗'} |"
            ),
            (
                "| 5 个 fold 中至少 4 个 AP 增益为正 | "
                f"{paired['positive_fold_count']}/5 | "
                f"{'✓' if decision['conditions']['positive_in_at_least_four_folds'] else '✗'} |"
            ),
            "",
            "## 2. 四种固定方法的整体结果",
            "",
            "主口径只比较 181 条客观缺陷与 630 条 `ok`；其他主观标签不混入该指标。",
            "",
            "| 方法 | AP | P@20 | P@50 | P@100 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for method in METHODS:
        row = primary["full"][method]
        lines.append(
            f"| {METHOD_LABELS[method]} | {fmt(row['average_precision'])} | "
            f"{fmt(row['precision_at_20'])} | {fmt(row['precision_at_50'])} | "
            f"{fmt(row['precision_at_100'])} |"
        )
    lines.extend(
        [
            "",
            "补充口径将全部 370 条非 `ok` 项视为正例：",
            "",
            "| 方法 | AP | P@50 | P@100 |",
            "|---|---:|---:|---:|",
        ]
    )
    for method in METHODS:
        row = secondary["full"][method]
        lines.append(
            f"| {METHOD_LABELS[method]} | {fmt(row['average_precision'])} | "
            f"{fmt(row['precision_at_50'])} | {fmt(row['precision_at_100'])} |"
        )
    lines.extend(
        [
            "",
            "## 3. 五个完整 subject fold",
            "",
            "57 个 subject 按题数做确定性贪心均衡；同一 subject 从未被拆分。"
            "这里没有训练或调参，fold 只用于检查结果是否依赖少数学科。",
            "",
            "| Fold | 题数（主口径） | subject 数 | Audit AP | Audit+error AP | "
            "Audit+majority AP | Audit+psych AP | psych-error Δ |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for fold in primary["folds"]:
        fold_metrics = fold["metrics"]
        lines.append(
            f"| {fold['fold']} | {fold_metrics['benchaudit_score']['n']} | "
            f"{fold['n_subjects']} | "
            f"{fmt(fold_metrics['benchaudit_score']['average_precision'])} | "
            f"{fmt(fold_metrics['audit_error_rate_fusion']['average_precision'])} | "
            f"{fmt(fold_metrics['audit_majority_fusion']['average_precision'])} | "
            f"{fmt(fold_metrics['audit_psychometric_fusion']['average_precision'])} | "
            f"{fold['complex_minus_simple_ap']:+.3f} |"
        )
    macro = primary["subject_analysis"]["macro_average_precision"]
    lines.extend(
        [
            "",
            "## 4. 逐 subject 配对结果",
            "",
            f"- 可比较 subject：{paired['n_subjects']}（每个至少 3 个客观缺陷、5 个 `ok`）。",
            f"- Macro AP：Audit={macro['benchaudit_score']:.3f}，"
            f"Audit+error={macro['audit_error_rate_fusion']:.3f}，"
            f"Audit+majority={macro['audit_majority_fusion']:.3f}，"
            f"Audit+psych={macro['audit_psychometric_fusion']:.3f}。",
            f"- psych 相对 error 的平均 AP 差：{paired['mean_delta']:+.4f}；"
            f"中位数：{paired['median_delta']:+.4f}。",
            f"- 两侧 Wilcoxon：p={paired['wilcoxon']['pvalue']:.4g}。"
            "该值仅作描述，不作确证性显著性声明。",
            "",
            "## 5. 怎么解释",
            "",
            "这次实验回答的是：在不重新训练、不读取标签调权重的前提下，复杂融合的优势"
            "是否能稳定出现在不同学科。它不能证明对一个全新 benchmark 的跨数据集泛化；"
            "要证明后者，仍需冻结方法后在未参与设计的新 Q&A benchmark 上复验。",
            "",
            "无论选择简单还是复杂前端，错误率、分歧和心理测量信号都只负责缩小候选范围。"
            "它们不能单独证明 benchmark 有错，因此 promotion 上限保持 `review`；"
            "只有独立重算、执行 replay 或其他客观 verifier 才能升级为 `confirmed`。",
            "",
            "## 6. 可复现性与诚实边界",
            "",
            f"- Protocol SHA-256：`{metrics['provenance']['protocol_sha256']}`",
            f"- Features SHA-256：`{metrics['provenance']['feature_sha256']}`",
            f"- Source scores SHA-256：`{metrics['provenance']['source_score_sha256']}`",
            f"- Labels SHA-256：`{metrics['provenance']['label_sha256']}`",
            f"- Folds SHA-256：`{metrics['provenance']['fold_sha256']}`",
            f"- Frozen scores SHA-256：`{metrics['provenance']['score_sha256']}`",
            "- 标签曾在上一轮整体分析中被查看，因此本报告使用“subject-grouped "
            "robustness diagnostic”，不使用“未见 holdout 证明”。",
            "- AP 的并列分数由 `average_precision_score` 按阈值处理；P@K 使用并列组内"
            "均匀随机顺序的精确期望，不依赖随机抖动。",
            "- 该实验零新增 API 成本，但依赖已有 15 个模型的历史响应矩阵；如果没有"
            "历史运行轨迹，这个候选前端无法凭空产生行为信号。",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate() -> None:
    verify_frozen_inputs(include_labels=True)
    for path in (FOLD_PATH, SCORE_PATH):
        if not path.exists():
            raise FileNotFoundError(f"run prepare first: {path}")
    refuse_label_bearing_scoring_input(FOLD_PATH)
    refuse_label_bearing_scoring_input(SCORE_PATH)
    features = load_json(FEATURE_PATH)
    labels_doc = load_json(LABEL_PATH)
    folds = load_json(FOLD_PATH)
    scores = load_json(SCORE_PATH)
    feature_ids = set(features["items"])
    label_ids = set(labels_doc["items"])
    fold_ids = set(folds["item_to_fold"])
    score_ids = set(scores["items"])
    if not (feature_ids == label_ids == fold_ids == score_ids):
        raise ValueError("feature, label, fold, and score ID sets differ")
    if scores.get("promotion_ceiling") != "review":
        raise ValueError("behavioral score promotion ceiling must remain review")

    evaluation = {
        scope: evaluate_scope(
            scope,
            labels_doc["items"],
            scores["items"],
            folds,
        )
        for scope in SCOPES
    }
    metrics: dict[str, Any] = {
        "schema_version": 1,
        "experiment": "MMLU-Redux subject-grouped robustness diagnostic",
        "not_a_pristine_holdout": True,
        "n_items": len(score_ids),
        "n_subjects": len(folds["subject_to_fold"]),
        "n_folds": len(folds["folds"]),
        "n_bootstrap": N_BOOTSTRAP,
        "methods": METHODS,
        "evaluation": evaluation,
        "decision": decide(evaluation["objective_vs_ok"]),
        "provenance": {
            "protocol_sha256": sha256_file(PROTOCOL_PATH),
            "feature_sha256": sha256_file(FEATURE_PATH),
            "source_score_sha256": sha256_file(SOURCE_SCORE_PATH),
            "label_sha256": sha256_file(LABEL_PATH),
            "fold_sha256": sha256_file(FOLD_PATH),
            "score_sha256": sha256_file(SCORE_PATH),
        },
    }
    stable_json_dump(METRIC_PATH, metrics)
    REPORT_PATH.write_text(render_report(metrics), encoding="utf-8")
    print(
        f"evaluated; recommendation={metrics['decision']['recommendation']}; "
        f"metrics={sha256_file(METRIC_PATH)[:12]}, "
        f"report={sha256_file(REPORT_PATH)[:12]}"
    )


def self_test() -> None:
    values = percentiles(np.array([3.0, 1.0, 1.0, 2.0]))
    assert np.allclose(values, np.array([1.0, 1 / 6, 1 / 6, 2 / 3]))
    all_tied = percentiles(np.ones(4))
    assert np.allclose(all_tied, np.full(4, 0.5))
    folds = assign_subject_folds({"a": 10, "b": 9, "c": 8, "d": 7}, 2)
    assigned = [subject for fold in folds for subject in fold["subjects"]]
    assert sorted(assigned) == ["a", "b", "c", "d"]
    ids = ["a", "b", "c", "d"]
    scores = {"a": 1.0, "b": 0.5, "c": 0.5, "d": 0.0}
    result = exact_topk_metrics(ids, scores, {"a", "c"}, ks=(1, 2, 3))
    assert math.isclose(result["precision_at_1"], 1.0)
    assert math.isclose(result["precision_at_2"], 0.75)
    assert math.isclose(result["precision_at_3"], 2 / 3)
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase",
        choices=("self-test", "prepare", "evaluate", "all"),
        help="prepare is label-free; evaluate opens frozen labels",
    )
    args = parser.parse_args()
    if args.phase == "self-test":
        self_test()
    elif args.phase == "prepare":
        prepare()
    elif args.phase == "evaluate":
        evaluate()
    else:
        self_test()
        prepare()
        evaluate()


if __name__ == "__main__":
    main()
