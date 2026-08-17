#!/usr/bin/env python3
"""Build a human-reviewable item ledger for the three ACEBench thinking runs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = REPO_ROOT / "reports/agentsuite_acebench_102_deepseek_thinking_pilot_20260816"
MATERIALIZED_ROOT = REPO_ROOT / "reports/agentsuite_acebench_102_v2_20260816/materialized"
DEFAULT_AGENTSUITE_ROOT = Path("/home/zhoujun/llmdata/AgentSuite-main")

RUNS = (
    ("R1", EXPERIMENT_ROOT / "run/report.json", EXPERIMENT_ROOT / "scoring/result.json"),
    ("R2", EXPERIMENT_ROOT / "run_r2/report.json", EXPERIMENT_ROOT / "scoring/result_r2.json"),
    ("R3", EXPERIMENT_ROOT / "run_r3/report.json", EXPERIMENT_ROOT / "scoring/result_r3.json"),
)

STABLE_MISS_MECHANISMS = {
    "agentsuite-ace::normal_atom_enum::22": "reference 加入用户未要求的可选参数",
    "agentsuite-ace::normal_atom_enum::24": "reference 加入用户未要求的可选参数",
    "agentsuite-ace::normal_atom_object_deep::29": "reference 重复调用；前序状态已经足够",
    "agentsuite-ace::normal_multi_turn_user_adjust::49_0": "reference 猜测用户未给出的后端配置",
    "agentsuite-ace::normal_multi_turn_user_switch::10_0": "任务时间上下文与 schema/枚举不一致",
    "agentsuite-ace::normal_preference::46": "schema 参数描述与 reference 取值边界含混",
    "agentsuite-ace::normal_preference::49": "reference 在多个偏好中任意选一个",
    "agentsuite-ace::normal_similar_api::47": "多个相似 API 都合理，但 gold 只接受一个",
    "agentsuite-ace::normal_single_turn_single_function::9": "reference 使用没有来源的具体值",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def md_text(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def short(value: Any, limit: int = 170) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def clean_block(value: Any) -> str:
    return "\n".join(line.rstrip() for line in str(value).splitlines()).strip()


def official_key(item_id: str) -> str:
    return item_id.removeprefix("agentsuite-ace::").replace("::", "_")


def issue_summary(rows: list[dict[str, Any]]) -> str:
    summaries: list[str] = []
    for row in rows:
        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            continue
        llm_result = evidence.get("llm_result")
        if isinstance(llm_result, dict) and llm_result.get("summary"):
            summaries.append(str(llm_result["summary"]))
        issue = evidence.get("issue")
        if isinstance(issue, dict) and issue.get("detail"):
            summaries.append(str(issue["detail"]))
    return short(summaries[0], 260) if summaries else "—"


def run_details(report: dict[str, Any], candidate_ids: set[str]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report.get("violations", []):
        if row.get("detection_method") != "llm_cross_artifact_consistency":
            continue
        if row.get("defect_scope", "substantive") in {"presentation", "operational"}:
            continue
        if row.get("defect_type") == "llm_audit_failure":
            continue
        grouped[str(row["item_id"])].append(row)
    result: dict[str, dict[str, Any]] = {}
    for item_id in candidate_ids:
        rows = grouped[item_id]
        result[item_id] = {
            "flag": True,
            "types": sorted({str(row.get("defect_type", "unknown")) for row in rows}),
            "confidence": max((float(row.get("confidence", 0.0)) for row in rows), default=0.0),
            "summary": issue_summary(rows),
        }
    return result


def status_cell(detail: dict[str, Any] | None) -> str:
    if not detail:
        return "未报"
    types = ", ".join(detail["types"])
    return f"报：{types}（c={detail['confidence']:.2f}）"


def review_card(
    item: dict[str, Any],
    label: int,
    official: dict[str, str] | None,
    details: list[dict[str, Any] | None],
    audit_line: int,
) -> list[str]:
    item_id = str(item["id"])
    hits = sum(detail is not None for detail in details)
    lines = [f"### `{item_id}`", ""]
    lines.append(f"- 人工标签：**{'问题' if label else '正常'}**；三跑报告次数：**{hits}/3**。")
    lines.append(f"- 任务族：`{item.get('metadata', {}).get('task_name', 'unknown')}`。")
    lines.append(f"- 原始审计输入：`{MATERIALIZED_ROOT / 'audit_input.jsonl'}:{audit_line}`。")
    if official:
        lines.append(f"- AgentSuite issue catalog 原因：{official.get('issue_reason') or '未提供'}")
        lines.append(
            f"- 官方处理建议：`{official.get('resolution') or '—'}`；"
            f"{official.get('resolution_detail') or '未提供'}"
        )
    else:
        lines.append("- AgentSuite issue catalog 原因：无；人工 CSV 只标记为正常。")
    lines.extend(["", "| 运行 | 是否报告 | 模型给出的首要解释 |", "|---|---|---|"])
    for (name, _, _), detail in zip(RUNS, details):
        lines.append(
            f"| {name} | {md_text(status_cell(detail))} | "
            f"{md_text(detail['summary'] if detail else '没有形成实质性 finding')} |"
        )
    lines.extend(
        [
            "",
            "<details><summary>题目与 reference（点击展开）</summary>",
            "",
            "**Task**",
            "",
            "```text",
            clean_block(item.get("task", "")),
            "```",
            "",
            "**Reference solution**",
            "",
            "```json",
            json.dumps(item.get("reference_solution"), ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
            "</details>",
            "",
            "人工复核：",
            "",
            "- [ ] 官方问题标签与理由合理",
            "- [ ] 我们的三跑判定与证据合理",
            "- [ ] 需要修改检查逻辑",
            "- 备注：",
            "",
        ]
    )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agentsuite-root", type=Path, default=DEFAULT_AGENTSUITE_ROOT)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    input_path = MATERIALIZED_ROOT / "audit_input.jsonl"
    truth_path = MATERIALIZED_ROOT / "sealed_truth.jsonl"
    issue_path = args.agentsuite_root / "ACEBench/acebench_issues.csv"
    human_path = args.agentsuite_root / "pipeline/human_labelled_ground_truth/ACEBench.csv"

    items = load_jsonl(input_path)
    item_by_id = {str(row["id"]): row for row in items}
    input_line = {str(row["id"]): index for index, row in enumerate(items, start=1)}
    truth_rows = load_jsonl(truth_path)
    truth = {str(row["id"]): int(row["is_issue"]) for row in truth_rows}
    official_rows = list(csv.DictReader(issue_path.open(encoding="utf-8-sig", newline="")))
    official: dict[str, dict[str, str]] = {}
    for row in official_rows:
        key = str(row["task_id"])
        if key in official:
            raise SystemExit(f"duplicate official issue key: {key}")
        official[key] = row

    reports: list[dict[str, Any]] = []
    candidates: list[set[str]] = []
    details_by_run: list[dict[str, dict[str, Any]]] = []
    score_hashes: dict[str, str] = {}
    report_hashes: dict[str, str] = {}
    for name, report_path, score_path in RUNS:
        report = load_json(report_path)
        score = load_json(score_path)["thinking_enabled"]
        predicted = set(score["tp_ids"]) | set(score["fp_ids"])
        reports.append(report)
        candidates.append(predicted)
        details_by_run.append(run_details(report, predicted))
        score_hashes[name] = sha256(score_path)
        report_hashes[name] = sha256(report_path)

    if len(items) != 102 or len(truth) != 102 or sum(truth.values()) != 51:
        raise SystemExit("unexpected ACEBench balanced-subset shape")
    if set(item_by_id) != set(truth):
        raise SystemExit("input/truth id mismatch")
    missing_official = [item_id for item_id, label in truth.items() if label and official_key(item_id) not in official]
    if missing_official:
        raise SystemExit(f"positive items missing official issue reasons: {missing_official}")

    hit_count = {item_id: sum(item_id in run for run in candidates) for item_id in truth}
    positive_distribution = Counter(hit_count[item_id] for item_id, label in truth.items() if label)
    negative_distribution = Counter(hit_count[item_id] for item_id, label in truth.items() if not label)
    expected_positive = {0: 9, 1: 5, 2: 4, 3: 33}
    expected_negative = {0: 44, 2: 2, 3: 5}
    if dict(sorted(positive_distribution.items())) != expected_positive:
        raise SystemExit(f"positive distribution drift: {positive_distribution}")
    if dict(sorted(negative_distribution.items())) != expected_negative:
        raise SystemExit(f"negative distribution drift: {negative_distribution}")

    lines = [
        "# ACEBench-102 thinking 三跑逐题人工复核表",
        "",
        "> 用途：开发集误差分析，帮助确认哪些题是稳定漏检、随机漏检或稳定误报。",
        ">",
        "> 重要边界：102 题是 51/51 平衡人工子集，标签已经解封；本文不能作为未见测试结果。",
        "",
        "## 1. 三跑总体结果",
        "",
        "| 运行 | TP | FP | FN | TN | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, _, score_path in RUNS:
        scored = load_json(score_path)["thinking_enabled"]
        cm, metric = scored["confusion_matrix"], scored["metrics"]
        lines.append(
            f"| {name} | {cm['tp']} | {cm['fp']} | {cm['fn']} | {cm['tn']} | "
            f"{metric['precision']:.3f} | {metric['recall']:.3f} | {metric['f1']:.3f} |"
        )

    lines.extend(
        [
            "",
            "R3 是第三套独立生成的响应，但执行在 101/102 条写入自己的新 cache 后遇到最后一条 retry 长尾；最终报告复用这 101 条并只补请求 1 条。三个 cache 的 102 个 key 相同，但任意两跑的 102 个 response 均无逐字相同项。因此 R3 可用于题级三跑比较，但其完整 token/费用不可重建。",
        ]
    )

    lines.extend(
        [
            "",
            "## 2. 跨运行分层",
            "",
            "### 人工阳性 51 题",
            "",
            "| 三跑中报告次数 | 题数 | 含义 |",
            "|---:|---:|---|",
            "| 3/3 | 33 | 稳定检出，可作为已有能力 |",
            "| 2/3 | 4 | 不稳定检出，运行噪声 |",
            "| 1/3 | 5 | 高度不稳定检出，接近稳定漏检 |",
            "| 0/3 | 9 | **稳定漏检，下一轮优先分析** |",
            "",
            "### 人工阴性 51 题",
            "",
            "| 三跑中报告次数 | 题数 | 含义 |",
            "|---:|---:|---|",
            "| 3/3 | 5 | **稳定误报，优先检查判定口径** |",
            "| 2/3 | 2 | 不稳定误报 |",
            "| 1/3 | 0 | 无 |",
            "| 0/3 | 44 | 三跑均未报 |",
            "",
            "### 9 条稳定漏检的初步机制归组",
            "",
            "这只是为了方便人工检查的开发期归组，不是新的人工真值。最终以每题的官方 issue reason 和题目内容为准。",
            "",
            "| 初步机制 | 题数 | Item |",
            "|---|---:|---|",
            "| 用户未授权/无法溯源的 reference 参数或取值 | 5 | `normal_atom_enum::22`、`normal_atom_enum::24`、`normal_multi_turn_user_adjust::49_0`、`normal_preference::49`、`normal_single_turn_single_function::9` |",
            "| schema、时间上下文或参数描述不一致 | 2 | `normal_multi_turn_user_switch::10_0`、`normal_preference::46` |",
            "| 前序状态已足够，却重复调用工具 | 1 | `normal_atom_object_deep::29` |",
            "| 多个相似 API 都合理，但 gold 只接受一个 | 1 | `normal_similar_api::47` |",
            "",
            "## 3. 优先人工复核：9 条稳定漏检（人工阳性、0/3）",
            "",
        ]
    )

    stable_misses = sorted(item_id for item_id, label in truth.items() if label and hit_count[item_id] == 0)
    partial_positives = sorted(item_id for item_id, label in truth.items() if label and hit_count[item_id] in {1, 2})
    false_positives = sorted(item_id for item_id, label in truth.items() if not label and hit_count[item_id] > 0)
    stable_positives = sorted(item_id for item_id, label in truth.items() if label and hit_count[item_id] == 3)

    if set(stable_misses) != set(STABLE_MISS_MECHANISMS):
        raise SystemExit("stable-miss mechanism review is stale")
    for item_id in stable_misses:
        lines.extend(
            review_card(
                item_by_id[item_id],
                1,
                official[official_key(item_id)],
                [run.get(item_id) for run in details_by_run],
                input_line[item_id],
            )
        )

    lines.extend(["## 4. 不稳定检出：9 条人工阳性（1/3 或 2/3）", ""])
    for item_id in partial_positives:
        lines.extend(
            review_card(
                item_by_id[item_id],
                1,
                official[official_key(item_id)],
                [run.get(item_id) for run in details_by_run],
                input_line[item_id],
            )
        )

    lines.extend(["## 5. 误报复核：7 条人工阴性（至少两跑报告）", ""])
    for item_id in false_positives:
        lines.extend(
            review_card(
                item_by_id[item_id],
                0,
                None,
                [run.get(item_id) for run in details_by_run],
                input_line[item_id],
            )
        )

    lines.extend(
        [
            "## 6. 稳定检出：33 条人工阳性紧凑表",
            "",
            "这部分不是下一轮首要优化对象，但保留题级证据，便于检查新逻辑是否破坏既有能力。",
            "",
            "| Item | 官方问题原因（摘要） | R1 类型 | R2 类型 | R3 类型 |",
            "|---|---|---|---|---|",
        ]
    )
    for item_id in stable_positives:
        d = [run[item_id] for run in details_by_run]
        lines.append(
            f"| `{item_id}` | {md_text(short(official[official_key(item_id)]['issue_reason'], 180))} | "
            f"{md_text(', '.join(d[0]['types']))} | {md_text(', '.join(d[1]['types']))} | "
            f"{md_text(', '.join(d[2]['types']))} |"
        )

    family_rows: dict[str, list[str]] = defaultdict(list)
    for item_id in truth:
        family_rows[str(item_by_id[item_id].get("metadata", {}).get("task_name", "unknown"))].append(item_id)
    lines.extend(
        [
            "",
            "## 7. 按任务族查看稳定漏检",
            "",
            "| 任务族 | 人工阳性 | 稳定检出 | 不稳定检出 | 稳定漏检 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for family in sorted(family_rows):
        positive_ids = [item_id for item_id in family_rows[family] if truth[item_id]]
        if not positive_ids:
            continue
        stable = sum(hit_count[item_id] == 3 for item_id in positive_ids)
        partial = sum(hit_count[item_id] in {1, 2} for item_id in positive_ids)
        missed = sum(hit_count[item_id] == 0 for item_id in positive_ids)
        lines.append(f"| `{family}` | {len(positive_ids)} | {stable} | {partial} | {missed} |")

    lines.extend(
        [
            "",
            "## 8. 证据绑定",
            "",
            f"- 审计输入 SHA-256：`{sha256(input_path)}`",
            f"- 人工标签 SHA-256：`{sha256(truth_path)}`",
            f"- AgentSuite 人工 CSV SHA-256：`{sha256(human_path)}`",
            f"- AgentSuite issue catalog SHA-256：`{sha256(issue_path)}`",
        ]
    )
    for name, _, _ in RUNS:
        lines.append(f"- {name} report SHA-256：`{report_hashes[name]}`")
        lines.append(f"- {name} score SHA-256：`{score_hashes[name]}`")
    lines.extend(
        [
            "",
            "本文不重新调用模型，也不修改既有预测；它只是把已经锁定并评分的三跑结果连接到官方 issue catalog，供人工检查。",
            "",
        ]
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "positive_distribution": dict(sorted(positive_distribution.items())),
                "negative_distribution": dict(sorted(negative_distribution.items())),
                "stable_miss_ids": stable_misses,
                "partial_positive_ids": partial_positives,
                "false_positive_ids": false_positives,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
