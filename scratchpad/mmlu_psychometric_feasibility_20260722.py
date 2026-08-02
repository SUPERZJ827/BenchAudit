#!/usr/bin/env python3
"""Label-isolated, execution-free MMLU-Redux response-matrix feasibility study.

The experiment is intentionally outside ``benchcore``.  It has three phases:

1. materialize: ID-join the archived model answers and physically split features
   from labels;
2. score: read features plus the existing BenchAudit report, never labels;
3. evaluate: join the frozen scores to labels and produce metrics/reporting.

All behavioral/statistical findings have a hard review-only ceiling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.stats import rankdata, spearmanr
from sklearn.metrics import average_precision_score


ROOT = Path(__file__).resolve().parents[1]
ANSWER_DIR = ROOT / "reports" / "ranking_impact" / "answers"
AUDIT_PATH = ROOT / "reports" / "ranking_impact" / "audit_full1000.json"
PROTOCOL_PATH = ROOT / "scratchpad" / "MMLU_PSYCHOMETRIC_PROTOCOL_20260722.md"
OUT = ROOT / "reports" / "mmlu_psychometric_feasibility_20260722"

FEATURE_PATH = OUT / "features.json"
LABEL_PATH = OUT / "labels.json"
SCORE_PATH = OUT / "scores.json"
METRICS_PATH = OUT / "metrics.json"
REPORT_PATH = OUT / "report.md"

SEED = 20260722
OBJECTIVE_TYPES = {
    "wrong_groundtruth",
    "multiple_correct_answers",
    "no_correct_answer",
}
AUDIT_OBJECTIVE_TYPES = {
    "wrong_gold_answer",
    "no_correct_answer",
    "multiple_correct_answers",
    "multiple_correct_answers_risk",
    "invalid_choice_gold",
    "bad_options_clarity",
    "duplicate_choices",
}
METHODS = [
    "random",
    "at_least_one_wrong",
    "error_rate",
    "answer_entropy",
    "global_item_total_anomaly",
    "subject_item_total_anomaly",
    "high_ability_disagreement",
    "majority_against_gold",
    "psychometric_fusion",
    "benchaudit_flag",
    "benchaudit_score",
    "audit_psychometric_fusion",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        item_id = str(row.get("id", ""))
        if not item_id:
            raise ValueError(f"{path}:{line_number}: missing id")
        if item_id in seen:
            raise ValueError(f"{path}:{line_number}: duplicate id {item_id}")
        seen.add(item_id)
        rows.append(row)
    return rows


def model_name(path: Path) -> str:
    return path.stem


def normalized_prediction(value: Any) -> str:
    if value is None:
        return "<MISSING>"
    text = str(value).strip().upper()
    return text if text else "<MISSING>"


def materialize() -> None:
    files = sorted(ANSWER_DIR.glob("*.jsonl"))
    if len(files) != 15:
        raise ValueError(f"expected 15 model files, found {len(files)}")

    model_rows: dict[str, dict[str, dict[str, Any]]] = {}
    raw_orders: dict[str, list[str]] = {}
    source_hashes: dict[str, str] = {}
    common_ids: set[str] | None = None

    for path in files:
        name = model_name(path)
        rows = load_jsonl(path)
        by_id = {str(row["id"]): row for row in rows}
        if len(by_id) != 1000:
            raise ValueError(f"{path}: expected 1000 rows, found {len(by_id)}")
        ids = set(by_id)
        if common_ids is None:
            common_ids = ids
        elif ids != common_ids:
            raise ValueError(f"{path}: ID set differs from other model files")
        model_rows[name] = by_id
        raw_orders[name] = [str(row["id"]) for row in rows]
        source_hashes[str(path.relative_to(ROOT))] = sha256_file(path)

    assert common_ids is not None
    ordered_ids = sorted(common_ids)
    models = sorted(model_rows)
    first_model = models[0]
    first_order = raw_orders[first_model]
    order_same = all(raw_orders[name] == first_order for name in models[1:])

    features: dict[str, Any] = {
        "schema_version": 1,
        "created_by": Path(__file__).name,
        "join_key": "id",
        "promotion_ceiling": "review",
        "models": models,
        "source_sha256": source_hashes,
        "raw_order_same_across_models": order_same,
        "items": {},
    }
    labels: dict[str, Any] = {
        "schema_version": 1,
        "label_source": "MMLU-Redux archived error_type",
        "objective_types": sorted(OBJECTIVE_TYPES),
        "items": {},
    }

    for item_id in ordered_ids:
        anchor = model_rows[first_model][item_id]
        gold = normalized_prediction(anchor.get("gold"))
        subject = str(anchor.get("subject", ""))
        error_type = str(anchor.get("error_type", ""))
        if not subject or not error_type:
            raise ValueError(f"{item_id}: missing subject/error_type")

        predictions: dict[str, str] = {}
        correct: dict[str, bool] = {}
        for name in models:
            row = model_rows[name][item_id]
            identity = (
                normalized_prediction(row.get("gold")),
                str(row.get("subject", "")),
                str(row.get("error_type", "")),
            )
            if identity != (gold, subject, error_type):
                raise ValueError(f"{item_id}: label metadata differs in {name}")
            predictions[name] = normalized_prediction(row.get("pred"))
            correct[name] = bool(row.get("correct", False))

        features["items"][item_id] = {
            "subject": subject,
            "gold": gold,
            "predictions": predictions,
            "correct": correct,
        }
        labels["items"][item_id] = {
            "error_type": error_type,
            "is_ok": error_type == "ok",
            "is_objective": error_type in OBJECTIVE_TYPES,
            "is_any_error": error_type != "ok",
        }

    counts = Counter(row["error_type"] for row in labels["items"].values())
    if counts["ok"] != 630:
        raise ValueError(f"expected 630 OK items, found {counts['ok']}")
    if sum(counts[x] for x in OBJECTIVE_TYPES) != 181:
        raise ValueError("expected 181 objective defects")
    if sum(v for k, v in counts.items() if k != "ok") != 370:
        raise ValueError("expected 370 non-OK items")

    features["n_items"] = len(features["items"])
    features["n_models"] = len(models)
    labels["counts"] = dict(sorted(counts.items()))
    stable_json_dump(FEATURE_PATH, features)
    stable_json_dump(LABEL_PATH, labels)

    if b"error_type" in FEATURE_PATH.read_bytes():
        raise AssertionError("feature artifact contains error_type")
    if any(
        "predictions" in row or "correct" in row
        for row in labels["items"].values()
    ):
        raise AssertionError("label artifact contains response feature keys")

    print(
        f"materialized {len(models)}x{len(ordered_ids)} by ID; "
        f"raw_order_same={order_same}; features={sha256_file(FEATURE_PATH)[:12]}"
    )


def safe_corr(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return 0.0
    value = float(np.corrcoef(x, y)[0, 1])
    return value if math.isfinite(value) else 0.0


def percentiles(values: np.ndarray) -> np.ndarray:
    if len(values) <= 1:
        return np.zeros(len(values), dtype=float)
    finite = np.where(np.isfinite(values), values, np.nanmedian(values))
    return (rankdata(finite, method="average") - 1.0) / (len(finite) - 1.0)


def compute_behavior_scores(
    feature_doc: dict[str, Any], selected_models: list[str] | None = None
) -> tuple[list[str], dict[str, dict[str, float]]]:
    all_models = list(feature_doc["models"])
    models = list(selected_models or all_models)
    unknown = set(models) - set(all_models)
    if unknown:
        raise ValueError(f"unknown model(s): {sorted(unknown)}")
    item_ids = sorted(feature_doc["items"])
    n_models = len(models)
    n_items = len(item_ids)
    if n_models < 3:
        raise ValueError("at least three models are required")

    correct = np.zeros((n_models, n_items), dtype=float)
    predictions: list[list[str]] = []
    gold: list[str] = []
    subjects: list[str] = []
    for item_index, item_id in enumerate(item_ids):
        row = feature_doc["items"][item_id]
        correct[:, item_index] = [1.0 if row["correct"][m] else 0.0 for m in models]
        predictions.append([row["predictions"][m] for m in models])
        gold.append(row["gold"])
        subjects.append(row["subject"])

    model_totals = correct.sum(axis=1)
    subject_indices: dict[str, list[int]] = defaultdict(list)
    for index, subject in enumerate(subjects):
        subject_indices[subject].append(index)
    subject_totals = {
        subject: correct[:, indices].sum(axis=1)
        for subject, indices in subject_indices.items()
    }

    arrays: dict[str, np.ndarray] = {
        "at_least_one_wrong": np.zeros(n_items),
        "error_rate": np.zeros(n_items),
        "answer_entropy": np.zeros(n_items),
        "global_item_total_anomaly": np.zeros(n_items),
        "subject_item_total_anomaly": np.zeros(n_items),
        "high_ability_disagreement": np.zeros(n_items),
        "majority_against_gold": np.zeros(n_items),
    }

    for item_index, item_id in enumerate(item_ids):
        x = correct[:, item_index]
        error_rate = 1.0 - float(np.mean(x))
        arrays["at_least_one_wrong"][item_index] = float(error_rate > 0)
        arrays["error_rate"][item_index] = error_rate

        counts = Counter(predictions[item_index])
        probabilities = [count / n_models for count in counts.values()]
        entropy = -sum(p * math.log(p) for p in probabilities if p > 0)
        arrays["answer_entropy"][item_index] = entropy / math.log(5.0)

        ability_without_item = model_totals - x
        global_corr = safe_corr(x, ability_without_item)
        arrays["global_item_total_anomaly"][item_index] = -global_corr

        subject = subjects[item_index]
        subject_n = len(subject_indices[subject])
        subject_ability = subject_totals[subject] - x
        subject_corr = safe_corr(x, subject_ability)
        shrinkage = max(0, subject_n - 1) / (max(0, subject_n - 1) + 20.0)
        blended_corr = shrinkage * subject_corr + (1.0 - shrinkage) * global_corr
        arrays["subject_item_total_anomaly"][item_index] = -blended_corr

        top_n = max(2, math.ceil(n_models / 3))
        top_indices = sorted(
            range(n_models), key=lambda j: (-ability_without_item[j], models[j])
        )[:top_n]
        top_error_rate = 1.0 - float(np.mean(x[top_indices]))
        arrays["high_ability_disagreement"][item_index] = top_error_rate - error_rate

        gold_count = counts.get(gold[item_index], 0)
        non_gold_max = max(
            (count for answer, count in counts.items() if answer != gold[item_index]),
            default=0,
        )
        arrays["majority_against_gold"][item_index] = (
            non_gold_max - gold_count
        ) / n_models

    psych_components = [
        "answer_entropy",
        "global_item_total_anomaly",
        "subject_item_total_anomaly",
        "high_ability_disagreement",
        "majority_against_gold",
    ]
    arrays["psychometric_fusion"] = np.mean(
        np.vstack([percentiles(arrays[name]) for name in psych_components]), axis=0
    )

    rows: dict[str, dict[str, float]] = {}
    for item_index, item_id in enumerate(item_ids):
        rows[item_id] = {
            name: float(values[item_index]) for name, values in arrays.items()
        }
    return models, rows


def load_audit_scores() -> tuple[dict[str, float], dict[str, int]]:
    audit = load_json(AUDIT_PATH)
    scores: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for violation in audit.get("violations", []):
        if violation.get("defect_type") not in AUDIT_OBJECTIVE_TYPES:
            continue
        item_id = str(violation.get("item_id", ""))
        if not item_id:
            continue
        confidence = float(violation.get("confidence", 0.0) or 0.0)
        scores[item_id] = max(scores[item_id], confidence)
        counts[item_id] += 1
    if len(scores) != 318:
        raise ValueError(f"expected 318 BenchAudit candidates, found {len(scores)}")
    return dict(scores), dict(counts)


def score() -> None:
    if not FEATURE_PATH.exists():
        raise FileNotFoundError("run materialize first")
    if b"error_type" in FEATURE_PATH.read_bytes():
        raise AssertionError("refusing to score a feature artifact containing labels")
    feature_doc = load_json(FEATURE_PATH)
    models, behavior = compute_behavior_scores(feature_doc)
    audit_scores, audit_counts = load_audit_scores()

    item_ids = sorted(behavior)
    psych = np.array([behavior[i]["psychometric_fusion"] for i in item_ids])
    audit = np.array([audit_scores.get(i, 0.0) for i in item_ids])
    combined = 0.5 * percentiles(psych) + 0.5 * percentiles(audit)

    rows: dict[str, Any] = {}
    for index, item_id in enumerate(item_ids):
        row = dict(behavior[item_id])
        row.update(
            {
                "random": 0.0,
                "benchaudit_flag": float(item_id in audit_scores),
                "benchaudit_score": float(audit_scores.get(item_id, 0.0)),
                "benchaudit_finding_count": int(audit_counts.get(item_id, 0)),
                "audit_psychometric_fusion": float(combined[index]),
            }
        )
        rows[item_id] = row

    result = {
        "schema_version": 1,
        "promotion_ceiling": "review",
        "feature_sha256": sha256_file(FEATURE_PATH),
        "audit_sha256": sha256_file(AUDIT_PATH),
        "models": models,
        "methods": METHODS,
        "items": rows,
    }
    stable_json_dump(SCORE_PATH, result)
    if b"error_type" in SCORE_PATH.read_bytes():
        raise AssertionError("score artifact contains labels")
    print(f"scored {len(rows)} items without labels; sha256={sha256_file(SCORE_PATH)[:12]}")


def stable_tie(item_id: str, salt: str) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{SEED}:{salt}:{item_id}".encode()).digest()[:8], "big"
    )


def deterministic_rank(item_ids: Iterable[str], scores: dict[str, float], salt: str) -> list[str]:
    return sorted(item_ids, key=lambda i: (-scores[i], stable_tie(i, salt)))


def tie_aware_metrics(
    item_ids: list[str],
    scores: dict[str, float],
    positives: set[str],
    method: str,
    repetitions: int = 500,
) -> dict[str, Any]:
    y = np.array([1 if item_id in positives else 0 for item_id in item_ids], dtype=int)
    s = np.array([scores[item_id] for item_id in item_ids], dtype=float)
    prevalence = float(np.mean(y))
    ap = float(average_precision_score(y, s))
    ks = sorted({20, 50, 100, 200} & set(range(1, len(item_ids) + 1)))
    values: dict[int, dict[str, list[float]]] = {
        k: {"precision": [], "recall": []} for k in ks
    }
    rng = np.random.default_rng(SEED + stable_tie(method, "metrics") % 1_000_000)
    for _ in range(repetitions):
        jitter = rng.random(len(item_ids))
        order = np.lexsort((jitter, -s))
        ordered_y = y[order]
        for k in ks:
            tp = int(np.sum(ordered_y[:k]))
            values[k]["precision"].append(tp / k)
            values[k]["recall"].append(tp / len(positives))

    result: dict[str, Any] = {
        "n": len(item_ids),
        "positives": len(positives),
        "prevalence": prevalence,
        "average_precision": ap,
    }
    for k, metric_values in values.items():
        for metric, observations in metric_values.items():
            result[f"{metric}_at_{k}"] = float(statistics.mean(observations))
            result[f"{metric}_at_{k}_ci95"] = [
                float(np.quantile(observations, 0.025)),
                float(np.quantile(observations, 0.975)),
            ]
        result[f"lift_at_{k}"] = (
            result[f"precision_at_{k}"] / prevalence if prevalence else 0.0
        )
    return result


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "mean": float(statistics.mean(values)),
        "median": float(statistics.median(values)),
        "q025": float(np.quantile(values, 0.025)),
        "q975": float(np.quantile(values, 0.975)),
        "min": float(min(values)),
        "max": float(max(values)),
    }


def evaluate_subsamples(
    feature_doc: dict[str, Any],
    labels: dict[str, Any],
    full_scores: dict[str, float],
) -> dict[str, Any]:
    all_models = list(feature_doc["models"])
    all_ids = sorted(feature_doc["items"])
    objective_pool = [
        item_id
        for item_id in all_ids
        if labels[item_id]["is_objective"] or labels[item_id]["is_ok"]
    ]
    objective = {item_id for item_id in objective_pool if labels[item_id]["is_objective"]}
    any_error = {item_id for item_id in all_ids if labels[item_id]["is_any_error"]}
    # Use one frozen item-ID tie order for every model subset.  Changing the
    # salt per repetition would mix arbitrary tie noise into subset stability.
    stability_salt = "psychometric-stability"
    objective_salt = "psychometric-stability-objective"
    any_error_salt = "psychometric-stability-any-error"
    full_top50 = set(deterministic_rank(all_ids, full_scores, stability_salt)[:50])
    rng = random.Random(SEED)
    output: dict[str, Any] = {}

    for size in (5, 8, 10, 15):
        repetitions = 100 if size < 15 else 1
        jaccards: list[float] = []
        objective_p50: list[float] = []
        any_error_p50: list[float] = []
        for repetition in range(repetitions):
            selected = (
                sorted(rng.sample(all_models, size)) if size < 15 else list(all_models)
            )
            _, rows = compute_behavior_scores(feature_doc, selected)
            subset_scores = {i: rows[i]["psychometric_fusion"] for i in all_ids}
            top50 = set(deterministic_rank(all_ids, subset_scores, stability_salt)[:50])
            union = top50 | full_top50
            jaccards.append(len(top50 & full_top50) / len(union) if union else 1.0)

            objective_rank = deterministic_rank(
                objective_pool, subset_scores, objective_salt
            )[:50]
            objective_p50.append(sum(i in objective for i in objective_rank) / 50)
            any_rank = deterministic_rank(all_ids, subset_scores, any_error_salt)[:50]
            any_error_p50.append(sum(i in any_error for i in any_rank) / 50)
        output[str(size)] = {
            "repetitions": repetitions,
            "top50_jaccard_vs_full15": summarize(jaccards),
            "objective_vs_ok_precision_at_50": summarize(objective_p50),
            "any_error_precision_at_50": summarize(any_error_p50),
        }
    return output


def fmt(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def build_report(metrics: dict[str, Any]) -> str:
    primary = metrics["evaluation"]["objective_vs_ok"]
    secondary = metrics["evaluation"]["any_error_vs_ok"]
    lines = [
        "# MMLU-Redux 15模型响应矩阵：离线心理测量候选实验",
        "",
        "> 零新增 API、零新增 benchmark 执行、不改主审计链路。统计异常的证据天花板固定为 `review`。",
        "",
        "## 1. 裁决",
        "",
        f"**预注册裁决：{metrics['verdict']['status']}**：{metrics['verdict']['reason']}",
        "",
        f"**Post-hoc 方法解释**：{metrics['posthoc_simple_fusions']['interpretation']}",
        "",
        "## 2. 数据与防泄漏检查",
        "",
        f"- 预注册 SHA256：`{metrics['provenance']['protocol_sha256']}`",
        f"- 模型/题目：**{metrics['data']['n_models']} × {metrics['data']['n_items']}**",
        f"- 原文件 ID 集一致，原始顺序是否一致：**{metrics['data']['raw_order_same']}**（实际按 ID join）",
        f"- 标签：objective={metrics['data']['n_objective']}，other non-OK={metrics['data']['n_other_error']}，OK={metrics['data']['n_ok']}",
        f"- features SHA256：`{metrics['provenance']['features_sha256']}`",
        f"- labels SHA256：`{metrics['provenance']['labels_sha256']}`",
        f"- scores SHA256：`{metrics['provenance']['scores_sha256']}`",
        "- scoring 阶段拒绝任何含 `error_type` 的 feature/score 产物。",
        "",
        "## 3. 主结果：objective-vs-ok",
        "",
        "> 主口径包含 181 道客观缺陷和 630 道 OK；189 道主观/专家题不在该口径中当负例。P@K/R@K 对并列分数做 500 次固定种子随机 tie-breaking。",
        "",
        "| 排序器 | AP | P@20 | P@50 | P@100 | R@50 | R@100 | Lift@50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method in sorted(METHODS, key=lambda m: primary[m]["average_precision"], reverse=True):
        row = primary[method]
        lines.append(
            f"| `{method}` | {fmt(row['average_precision'])} | "
            f"{fmt(row['precision_at_20'])} | {fmt(row['precision_at_50'])} | "
            f"{fmt(row['precision_at_100'])} | {fmt(row['recall_at_50'])} | "
            f"{fmt(row['recall_at_100'])} | {fmt(row['lift_at_50'])} |"
        )

    lines += [
        "",
        "### 3.1 Post-hoc：复杂心理测量是否超过简单 error rate？",
        "",
        "> 该诊断是看到预注册结果后追加，不改变上方裁决。目的是避免把简单模型错误率的价值误写成复杂心理测量的价值。",
        "",
        "| 与 BenchAudit 等权百分位融合的行为信号 | 单独 AP | 融合 AP | 相对 BenchAudit AP 增益 |",
        "|---|---:|---:|---:|",
    ]
    for method, row in sorted(
        metrics["posthoc_simple_fusions"]["rows"].items(),
        key=lambda pair: pair[1]["combined_average_precision"],
        reverse=True,
    ):
        lines.append(
            f"| `{method}` | {fmt(row['standalone_average_precision'])} | "
            f"{fmt(row['combined_average_precision'])} | "
            f"{row['delta_vs_benchaudit']:+.3f} |"
        )

    lines += [
        "",
        "## 4. 补充结果：any-error-vs-ok",
        "",
        "| 排序器 | AP | P@50 | P@100 | R@100 | Lift@50 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in sorted(METHODS, key=lambda m: secondary[m]["average_precision"], reverse=True):
        row = secondary[method]
        lines.append(
            f"| `{method}` | {fmt(row['average_precision'])} | "
            f"{fmt(row['precision_at_50'])} | {fmt(row['precision_at_100'])} | "
            f"{fmt(row['recall_at_100'])} | {fmt(row['lift_at_50'])} |"
        )

    comp = metrics["complementarity"]
    lines += [
        "",
        "## 5. 与现有 BenchAudit 的互补性",
        "",
        f"- BenchAudit 现有候选：{comp['benchaudit_flagged']} 题，命中 objective {comp['benchaudit_objective_hits']}/{metrics['data']['n_objective']}。",
        f"- `psychometric_fusion` 全 1000 题 Top-100：objective={comp['psych_top100']['objective']}，其他 non-OK={comp['psych_top100']['other_error']}，OK={comp['psych_top100']['ok']}。",
        f"- 其中 BenchAudit 没有标记的新 objective 命中：**{comp['psych_top100']['new_objective_not_in_audit']}**。",
        "",
        "| objective 四象限 | 数量 |",
        "|---|---:|",
        f"| BenchAudit 命中 + psych Top-100 命中 | {comp['objective_quadrants']['both']} |",
        f"| 仅 BenchAudit | {comp['objective_quadrants']['audit_only']} |",
        f"| 仅 psych Top-100 | {comp['objective_quadrants']['psych_only']} |",
        f"| 两者都没命中 | {comp['objective_quadrants']['neither']} |",
        "",
        "## 6. 模型子采样稳定性",
        "",
        "| 模型数 | 重复 | Top-50 Jaccard 中位数 | 95% 区间 | objective P@50 中位数 | any-error P@50 中位数 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for size in (5, 8, 10, 15):
        row = metrics["subsample_stability"][str(size)]
        jac = row["top50_jaccard_vs_full15"]
        obj = row["objective_vs_ok_precision_at_50"]
        any_row = row["any_error_precision_at_50"]
        lines.append(
            f"| {size} | {row['repetitions']} | {fmt(jac['median'])} | "
            f"[{fmt(jac['q025'])}, {fmt(jac['q975'])}] | "
            f"{fmt(obj['median'])} | {fmt(any_row['median'])} |"
        )

    lines += [
        "",
        "## 7. 是否只是在找难题",
        "",
        "| 候选分数 | 与 error_rate 的 Spearman ρ |",
        "|---|---:|",
    ]
    for method, value in sorted(metrics["difficulty_correlation"].items()):
        lines.append(f"| `{method}` | {fmt(value)} |")

    lines += [
        "",
        "### 按错误模型数分层",
        "",
        "| 错误模型数 | 题数 | objective 率 | any-error 率 |",
        "|---|---:|---:|---:|",
    ]
    for row in metrics["difficulty_bins"]:
        lines.append(
            f"| {row['bin']} | {row['n']} | {fmt(row['objective_rate'])} | "
            f"{fmt(row['any_error_rate'])} |"
        )

    lines += [
        "",
        "## 8. 诚实边界",
        "",
        "- 15 个模型远少于 Fantastic Bugs 建议的 60–80 模型；本轮没有将 tetrachoric/Rasch 作为主信号。",
        "- MMLU 多学科、非单维能力测试；subject 信号做了 shrinkage，但仍可能受模型专业化影响。",
        "- objective-vs-ok 是条件评估；实际候选队列中仍会包含 189 道主观/专家题。",
        "- 高难度、模型专业化和共同错误都可以造成统计异常；候选不是缺陷证明。",
        "- 任何该层的信号都只能进入 review，不改动 confirmed promotion 规则。",
        "",
        "## 9. 下一步",
        "",
    ]
    lines.extend(f"- {step}" for step in metrics["verdict"]["next_steps"])
    return "\n".join(lines) + "\n"


def evaluate() -> None:
    if not SCORE_PATH.exists() or not LABEL_PATH.exists():
        raise FileNotFoundError("run materialize and score first")
    if b"error_type" in SCORE_PATH.read_bytes():
        raise AssertionError("score artifact unexpectedly contains labels")

    feature_doc = load_json(FEATURE_PATH)
    label_doc = load_json(LABEL_PATH)
    score_doc = load_json(SCORE_PATH)
    labels = label_doc["items"]
    score_rows = score_doc["items"]
    item_ids = sorted(score_rows)
    if set(item_ids) != set(labels) or set(item_ids) != set(feature_doc["items"]):
        raise ValueError("feature/score/label ID sets differ")

    method_scores = {
        method: {item_id: float(score_rows[item_id][method]) for item_id in item_ids}
        for method in METHODS
    }
    objective_pool = [
        item_id
        for item_id in item_ids
        if labels[item_id]["is_objective"] or labels[item_id]["is_ok"]
    ]
    objective = {item_id for item_id in objective_pool if labels[item_id]["is_objective"]}
    any_error = {item_id for item_id in item_ids if labels[item_id]["is_any_error"]}

    evaluation: dict[str, Any] = {"objective_vs_ok": {}, "any_error_vs_ok": {}}
    for method in METHODS:
        evaluation["objective_vs_ok"][method] = tie_aware_metrics(
            objective_pool, method_scores[method], objective, f"obj-{method}"
        )
        evaluation["any_error_vs_ok"][method] = tie_aware_metrics(
            item_ids, method_scores[method], any_error, f"any-{method}"
        )

    # Post-hoc diagnostic: the preregistered combined method won, but determine
    # whether a simple archived-model error rate explains nearly all of that
    # gain.  Percentiles are computed over all 1000 items exactly as in score().
    posthoc_components = [
        "error_rate",
        "majority_against_gold",
        "answer_entropy",
        "global_item_total_anomaly",
        "subject_item_total_anomaly",
        "high_ability_disagreement",
        "psychometric_fusion",
    ]
    audit_all = percentiles(
        np.array([method_scores["benchaudit_score"][i] for i in item_ids])
    )
    audit_ap = evaluation["objective_vs_ok"]["benchaudit_score"]["average_precision"]
    posthoc_rows: dict[str, Any] = {}
    for component in posthoc_components:
        component_all = np.array([method_scores[component][i] for i in item_ids])
        combined_all = 0.5 * audit_all + 0.5 * percentiles(component_all)
        combined_scores = {item_id: float(combined_all[j]) for j, item_id in enumerate(item_ids)}
        combined_metrics = tie_aware_metrics(
            objective_pool,
            combined_scores,
            objective,
            f"posthoc-audit-plus-{component}",
        )
        posthoc_rows[component] = {
            "standalone_average_precision": evaluation["objective_vs_ok"][component][
                "average_precision"
            ],
            "combined_average_precision": combined_metrics["average_precision"],
            "combined_precision_at_50": combined_metrics["precision_at_50"],
            "combined_precision_at_100": combined_metrics["precision_at_100"],
            "delta_vs_benchaudit": combined_metrics["average_precision"] - audit_ap,
        }
    complex_over_simple = (
        posthoc_rows["psychometric_fusion"]["combined_average_precision"]
        - posthoc_rows["error_rate"]["combined_average_precision"]
    )
    posthoc = {
        "rows": posthoc_rows,
        "psychometric_over_error_rate_combined_ap_delta": complex_over_simple,
        "interpretation": (
            "行为信号与 BenchAudit 融合的方向值得继续；但复杂 "
            f"psychometric fusion 相对简单 error rate 只额外增加 "
            f"{complex_over_simple:+.3f} AP，尚不足以证明需要工程化复杂心理测量层。"
        ),
    }

    audit_flagged = {
        item_id for item_id in item_ids if score_rows[item_id]["benchaudit_flag"] > 0
    }
    psych_rank = deterministic_rank(
        item_ids, method_scores["psychometric_fusion"], "psych-top100"
    )
    psych_top100 = set(psych_rank[:100])
    objective_quadrants = {
        "both": len(objective & audit_flagged & psych_top100),
        "audit_only": len((objective & audit_flagged) - psych_top100),
        "psych_only": len((objective & psych_top100) - audit_flagged),
        "neither": len(objective - audit_flagged - psych_top100),
    }
    psych_counts = Counter(labels[item_id]["error_type"] for item_id in psych_top100)
    complementarity = {
        "benchaudit_flagged": len(audit_flagged),
        "benchaudit_objective_hits": len(audit_flagged & objective),
        "psych_top100": {
            "objective": len(psych_top100 & objective),
            "other_error": sum(
                item_id in psych_top100
                and labels[item_id]["is_any_error"]
                and not labels[item_id]["is_objective"]
                for item_id in item_ids
            ),
            "ok": len(psych_top100 - any_error),
            "new_objective_not_in_audit": len((psych_top100 & objective) - audit_flagged),
            "error_type_counts": dict(sorted(psych_counts.items())),
        },
        "objective_quadrants": objective_quadrants,
    }

    difficulty_correlation: dict[str, float] = {}
    error_rates = np.array([method_scores["error_rate"][i] for i in item_ids])
    for method in (
        "answer_entropy",
        "global_item_total_anomaly",
        "subject_item_total_anomaly",
        "high_ability_disagreement",
        "psychometric_fusion",
        "benchaudit_score",
        "audit_psychometric_fusion",
    ):
        value = spearmanr(
            np.array([method_scores[method][i] for i in item_ids]), error_rates
        ).statistic
        difficulty_correlation[method] = float(value) if math.isfinite(value) else 0.0

    bins = [(0, 3), (4, 7), (8, 11), (12, 15)]
    difficulty_bins: list[dict[str, Any]] = []
    for low, high in bins:
        members = [
            item_id
            for item_id in item_ids
            if low <= round(method_scores["error_rate"][item_id] * 15) <= high
        ]
        difficulty_bins.append(
            {
                "bin": f"{low}-{high}",
                "n": len(members),
                "objective_rate": sum(i in objective for i in members) / len(members)
                if members
                else 0.0,
                "any_error_rate": sum(i in any_error for i in members) / len(members)
                if members
                else 0.0,
            }
        )

    subsamples = evaluate_subsamples(
        feature_doc, labels, method_scores["psychometric_fusion"]
    )
    primary = evaluation["objective_vs_ok"]
    delta_psych = (
        primary["psychometric_fusion"]["average_precision"]
        - primary["error_rate"]["average_precision"]
    )
    delta_audit = (
        primary["audit_psychometric_fusion"]["average_precision"]
        - primary["benchaudit_score"]["average_precision"]
    )
    jaccard10 = subsamples["10"]["top50_jaccard_vs_full15"]["median"]
    new_objective = complementarity["psych_top100"]["new_objective_not_in_audit"]
    if (delta_psych >= 0.02 or delta_audit >= 0.02) and jaccard10 >= 0.40:
        verdict = {
            "status": "promising",
            "reason": (
                f"主口径 AP 增益为 psych-vs-error_rate={delta_psych:+.3f}、"
                f"audit+psych-vs-audit={delta_audit:+.3f}，10 模型 Top-50 "
                f"Jaccard 中位数={jaccard10:.3f}。"
            ),
            "next_steps": [
                "在 subject-held-out 切分上冻结无监督融合权重并复验。",
                "再评估 regularized tetrachoric/item scalability，不直接接入 promotion。",
                "将统计候选与原始 pred/gold/evaluator 证据包连接，仅用于 review triage。",
            ],
        }
    elif delta_psych > 0 or delta_audit > 0 or new_objective > 0:
        verdict = {
            "status": "mixed",
            "reason": (
                f"存在正增益或互补命中（psych AP Δ={delta_psych:+.3f}，"
                f"audit fusion AP Δ={delta_audit:+.3f}，新 objective 命中={new_objective}），"
                f"但未同时达到预注册效果/稳定性门槛（Jaccard={jaccard10:.3f}）。"
            ),
            "next_steps": [
                "不接入主链路；先检查新命中是否集中在特定 subject/难度。",
                "如互补命中有语义价值，再做 subject-held-out 复验。",
                "统计信号继续保持 review-only。",
            ],
        }
    else:
        verdict = {
            "status": "not_justified",
            "reason": (
                f"未超过简单分歧/现有 BenchAudit（psych AP Δ={delta_psych:+.3f}，"
                f"audit fusion AP Δ={delta_audit:+.3f}，新 objective 命中={new_objective}）。"
            ),
            "next_steps": [
                "不工程化心理测量层；保留本负结果作为成本为零的可行性裁决。",
                "优先转向 Terminal/Workspace 的历史轨迹确定性矛盾。",
            ],
        }

    metrics = {
        "schema_version": 1,
        "provenance": {
            "protocol_sha256": sha256_file(PROTOCOL_PATH),
            "features_sha256": sha256_file(FEATURE_PATH),
            "labels_sha256": sha256_file(LABEL_PATH),
            "scores_sha256": sha256_file(SCORE_PATH),
            "audit_sha256": sha256_file(AUDIT_PATH),
        },
        "data": {
            "n_models": len(feature_doc["models"]),
            "n_items": len(item_ids),
            "raw_order_same": feature_doc["raw_order_same_across_models"],
            "n_objective": len(objective),
            "n_any_error": len(any_error),
            "n_other_error": len(any_error - objective),
            "n_ok": len(item_ids) - len(any_error),
            "label_counts": label_doc["counts"],
        },
        "evaluation": evaluation,
        "posthoc_simple_fusions": posthoc,
        "complementarity": complementarity,
        "subsample_stability": subsamples,
        "difficulty_correlation": difficulty_correlation,
        "difficulty_bins": difficulty_bins,
        "verdict_inputs": {
            "psychometric_ap_delta_vs_error_rate": delta_psych,
            "audit_fusion_ap_delta_vs_benchaudit": delta_audit,
            "ten_model_top50_jaccard_median": jaccard10,
            "psych_top100_new_objective_not_in_audit": new_objective,
        },
        "verdict": verdict,
    }
    stable_json_dump(METRICS_PATH, metrics)
    REPORT_PATH.write_text(build_report(metrics), encoding="utf-8")
    print(
        f"evaluated: verdict={verdict['status']}; "
        f"metrics={sha256_file(METRICS_PATH)[:12]}; report={REPORT_PATH}"
    )


def self_test() -> None:
    assert safe_corr(np.array([0, 1, 0, 1]), np.array([0, 1, 0, 1])) > 0.99
    assert safe_corr(np.array([1, 1, 1]), np.array([1, 2, 3])) == 0.0
    assert normalized_prediction(None) == "<MISSING>"
    ids = ["b", "a", "c"]
    scores = {"a": 1.0, "b": 1.0, "c": 0.0}
    first = deterministic_rank(ids, scores, "test")
    second = deterministic_rank(reversed(ids), scores, "test")
    assert first == second
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("materialize", "score", "evaluate", "all", "self-test"),
        default="all",
    )
    args = parser.parse_args()
    if args.phase == "self-test":
        self_test()
        return
    if args.phase in {"materialize", "all"}:
        materialize()
    if args.phase in {"score", "all"}:
        score()
    if args.phase in {"evaluate", "all"}:
        evaluate()


if __name__ == "__main__":
    main()
