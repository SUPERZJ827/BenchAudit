"""Detect problem_statement answer leakage in SWE-bench datasets.

The scanner uses two stages:
1. literal matching between gold patch added lines and problem_statement;
2. optional LLM confirmation to separate real solution leakage from bug
   reproduction snippets or incidental string matches.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.swe_leak import (
    added_lines,
    confirm_solution_leak,
    issue_hit_context,
    scan_fields,
)


DATASET_PRESETS = {
    "lite": ("princeton-nlp/SWE-bench_Lite", "test"),
    "verified": ("princeton-nlp/SWE-bench_Verified", "test"),
}

@dataclass(frozen=True)
class DatasetSpec:
    label: str
    path: str
    split: str


def scan_instance(row: dict[str, Any]) -> dict[str, Any] | None:
    return scan_fields(
        patch=row.get("patch") or "",
        problem_statement=row.get("problem_statement") or "",
        hints_text=row.get("hints_text") or "",
        instance_id=row.get("instance_id") or row.get("id") or "",
        repo=row.get("repo") or "",
        base_commit=row.get("base_commit") or "",
    )


def scan_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    problem_candidates: list[dict[str, Any]] = []
    hints_only: list[dict[str, Any]] = []
    for row in rows:
        scanned = scan_instance(row)
        if not scanned:
            continue
        if scanned["problem_statement_hits"]:
            problem_candidates.append(scanned)
        elif scanned["hints_only_hits"]:
            hints_only.append(scanned)

    problem_candidates.sort(
        key=lambda item: (
            -item["problem_statement_hit_frac"],
            -item["problem_statement_hit_count"],
            item["instance_id"],
        )
    )
    hints_only.sort(
        key=lambda item: (
            -item["hints_only_hit_frac"],
            -item["hints_only_hit_count"],
            item["instance_id"],
        )
    )
    return problem_candidates, hints_only


def load_swebench(spec: DatasetSpec, limit: int | None = None) -> list[dict[str, Any]]:
    from datasets import load_dataset

    ds = load_dataset(spec.path, split=spec.split)
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(ds):
        if limit is not None and index >= limit:
            break
        rows.append(dict(row))
    return rows


def confirm_candidates(
    candidates: list[dict[str, Any]],
    *,
    llm_config_path: str,
    cache_path: str | None,
    workers: int,
    issue_chars: int,
    patch_chars: int,
) -> None:
    config = load_llm_config(llm_config_path)
    if cache_path:
        config.cache_path = cache_path
    client = LLMClient(config)

    def one(candidate: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        result = confirm_solution_leak(
            client,
            candidate,
            issue_chars=issue_chars,
            patch_chars=patch_chars,
        )
        return candidate["instance_id"], result

    workers = max(1, workers)
    if workers == 1:
        for candidate in candidates:
            _, result = one(candidate)
            attach_llm_result(candidate, result)
        return

    by_id = {candidate["instance_id"]: candidate for candidate in candidates}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(one, candidate) for candidate in candidates]
        for future in as_completed(futures):
            instance_id, result = future.result()
            attach_llm_result(by_id[instance_id], result)


def attach_llm_result(candidate: dict[str, Any], result: dict[str, Any]) -> None:
    verdict = str(result.get("verdict", "")).strip()
    candidate["llm_verdict"] = verdict or "missing_verdict"
    candidate["llm_evidence"] = str(result.get("evidence", "")).strip()
    candidate["llm_raw"] = result
    candidate["semantic_confirmed"] = verdict == "solution_leaked"


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    candidates = result["problem_statement_candidates"]
    hints_only = result["hints_only_instances"]
    confirmed = [item for item in candidates if item.get("semantic_confirmed")]
    llm_errors = [item for item in candidates if item.get("llm_verdict") == "llm_error"]
    return {
        "dataset": result["dataset"],
        "label": result["label"],
        "split": result["split"],
        "n_instances": result["n_instances"],
        "problem_statement_literal_candidates": len(candidates),
        "problem_statement_literal_rate": safe_rate(len(candidates), result["n_instances"]),
        "hints_only_literal_instances": len(hints_only),
        "hints_only_literal_rate": safe_rate(len(hints_only), result["n_instances"]),
        "semantic_confirmed_leaks": len(confirmed),
        "semantic_confirmed_rate": safe_rate(len(confirmed), result["n_instances"]),
        "llm_errors": len(llm_errors),
    }


def safe_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def strip_heavy_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in {"patch", "problem_statement", "llm_raw"}
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# SWE-bench problem_statement 答案泄漏扫描")
    lines.append("")
    lines.append(f"生成时间: {payload['generated_at']}")
    lines.append("")
    lines.append("## 摘要")
    lines.append("")
    lines.append(
        "本报告只把 gold patch 新增代码逐字出现在 `problem_statement` 中、且经 LLM "
        "判定为修复方案泄漏的样本计为真实候选缺陷。仅出现在 `hints_text` 的命中单独列出，"
        "不计入泄漏率，因为 SWE-bench 标准评测默认不向 agent 提供 hints。"
    )
    lines.append("")
    lines.append("复现命令:")
    lines.append("")
    lines.append("```bash")
    lines.append(
        "python scripts/swe_leak_scan.py "
        "--suite both --llm-confirm --workers 8 "
        "--out-json reports/swe_leak.json --out-md reports/swe_leak.md"
    )
    lines.append("```")
    lines.append("")
    lines.append("| Dataset | N | problem_statement literal | LLM confirmed | hints-only literal | LLM errors |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for summary in payload["summaries"]:
        lines.append(
            "| {label} | {n_instances} | {ps} ({ps_rate:.1%}) | {confirmed} ({confirmed_rate:.1%}) | "
            "{hints} ({hints_rate:.1%}) | {errors} |".format(
                label=summary["label"],
                n_instances=summary["n_instances"],
                ps=summary["problem_statement_literal_candidates"],
                ps_rate=summary["problem_statement_literal_rate"],
                confirmed=summary["semantic_confirmed_leaks"],
                confirmed_rate=summary["semantic_confirmed_rate"],
                hints=summary["hints_only_literal_instances"],
                hints_rate=summary["hints_only_literal_rate"],
                errors=summary["llm_errors"],
            )
        )
    lines.append("")
    lines.append("## 如何理解这里的答案泄漏")
    lines.append("")
    lines.append(
        "这里的答案泄漏不是指模型训练集污染，也不是指 `hints_text` 里有维护者评论。"
        "本报告检查的是更窄、更客观的一类问题：`problem_statement` 这个正式题面里，"
        "已经逐字出现了 gold patch 新增的修复代码。"
    )
    lines.append("")
    lines.append("检测分两步:")
    lines.append("")
    lines.append("1. 从 gold patch 里抽取新增的实质代码行，例如 `and has_add_permission`。")
    lines.append("2. 检查这些新增行是否逐字出现在 `problem_statement` 中；如果出现，再让 LLM 判断它是在给修复方案，还是只是复现代码、traceback 或偶然重合。")
    lines.append("")
    lines.append("几个典型例子:")
    lines.append("")
    lines.append("- `django__django-16527`: gold patch 新增 `and has_add_permission`，issue 题面也直接说需要加这一行。这是强泄漏。")
    lines.append("- `django__django-16139`: issue 题面直接说把旧链接格式替换成包含 `password.help_text = password.help_text.format(...)` 的新写法，gold patch 也新增这一行。这也是泄漏。")
    lines.append("- `matplotlib__matplotlib-23964`: issue 题面写明添加 `if curr_stream:` 似乎可以修复，gold patch 新增同一行，属于修复提示型泄漏。")
    lines.append("- `sympy__sympy-22005`: gold patch 的报错文本在 issue 里出现，但它是 traceback/现象，不是修复方案，所以二级确认判为非泄漏。")
    lines.append("- `hints_text` 命中: 维护者评论里可能出现修复代码，但标准 SWE-bench 不给 agent 看 hints，因此本报告单独统计、不计入 problem_statement 泄漏。")
    lines.append("")
    lines.append("所以这个脚本不是在判断“题目难不难”，而是在判断“正式题面是否已经把修复代码交给了模型”。")
    lines.append("")
    lines.append("## 遇到的问题")
    lines.append("")
    lines.append("- 字面匹配本身不是最终结论：issue 里可能包含复现代码、报错回溯或 API 用法示例，所以需要第二级语义确认。")
    lines.append("- `hints_text` 命中不能和 `problem_statement` 命中混报；前者通常不污染标准 SWE-bench 设置。")
    lines.append("- 过滤规则不能只保留带 `=()` 等符号的代码行，否则会漏掉 `and has_add_permission` 这种自然语言中直接给出的修复条件。")
    lines.append("- LLM 确认结果仍应作为高置信候选；最终论文/汇报里最硬的结论应优先引用逐字命中行和 issue 证据。")
    lines.append("")
    lines.append("## 未做的部分")
    lines.append("")
    lines.append("- 本报告没有人工逐条复核所有 LLM-confirmed 样本；它们应表述为高置信候选或二级确认结果。")
    lines.append("- 目前只检测逐字泄漏，没有检测 issue 用自然语言改写但未逐字给出 gold patch 的泄漏。")
    lines.append("- 目前没有按 repo、题型、难度或模型 pass rate 做分层分析。")
    lines.append("")

    for result in payload["datasets"]:
        lines.extend(render_dataset_section(result))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_dataset_section(result: dict[str, Any]) -> list[str]:
    summary = summarize_result(result)
    candidates = result["problem_statement_candidates"]
    confirmed = [item for item in candidates if item.get("semantic_confirmed")]
    not_confirmed = [item for item in candidates if not item.get("semantic_confirmed")]
    hints_only = result["hints_only_instances"]

    lines: list[str] = []
    lines.append(f"## {result['label']}")
    lines.append("")
    lines.append(
        f"- 数据集: `{result['dataset']}` / split `{result['split']}` / N={result['n_instances']}"
    )
    lines.append(
        "- problem_statement 逐字候选: "
        f"{summary['problem_statement_literal_candidates']} "
        f"({summary['problem_statement_literal_rate']:.1%})"
    )
    lines.append(
        "- LLM 语义确认泄漏: "
        f"{summary['semantic_confirmed_leaks']} "
        f"({summary['semantic_confirmed_rate']:.1%})"
    )
    lines.append(
        "- hints-only 逐字命中: "
        f"{summary['hints_only_literal_instances']} "
        f"({summary['hints_only_literal_rate']:.1%})，不计入 problem_statement 泄漏"
    )
    lines.append("")

    lines.append("### 语义确认为泄漏")
    lines.append("")
    if not confirmed:
        lines.append("无。")
    else:
        for item in confirmed:
            lines.extend(render_candidate(item))
    lines.append("")

    lines.append("### 逐字命中但未确认")
    lines.append("")
    if not not_confirmed:
        lines.append("无。")
    else:
        lines.append("| instance_id | verdict | evidence | hit lines |")
        lines.append("|---|---|---|---|")
        for item in not_confirmed:
            lines.append(
                "| {id} | {verdict} | {evidence} | {hits} |".format(
                    id=escape_md(str(item["instance_id"])),
                    verdict=escape_md(str(item.get("llm_verdict", "not_run"))),
                    evidence=escape_md(str(item.get("llm_evidence", ""))),
                    hits="<br>".join(
                        f"`{escape_backticks(line)}`"
                        for line in item["problem_statement_hits"][:5]
                    ),
                )
            )
    lines.append("")

    lines.append("### hints-only 命中")
    lines.append("")
    if not hints_only:
        lines.append("无。")
    else:
        lines.append("| instance_id | hit lines |")
        lines.append("|---|---|")
        for item in hints_only:
            lines.append(
                "| {id} | {hits} |".format(
                    id=escape_md(str(item["instance_id"])),
                    hits="<br>".join(
                        f"`{escape_backticks(line)}`" for line in item["hints_only_hits"][:5]
                    ),
                )
            )
    lines.append("")
    return lines


def render_candidate(item: dict[str, Any]) -> list[str]:
    lines = []
    lines.append(f"#### {item['instance_id']}")
    if item.get("repo"):
        lines.append(f"- repo: `{item['repo']}`")
    lines.append(
        f"- hit fraction: {item['problem_statement_hit_count']}/"
        f"{item['n_added_substantive_lines']} "
        f"({item['problem_statement_hit_frac']:.1%})"
    )
    lines.append(f"- LLM reason: {item.get('llm_evidence', '')}")
    lines.append("- leaked lines:")
    for hit in item["problem_statement_hits"]:
        lines.append(f"  - `{escape_backticks(hit)}`")
    lines.append("")
    return lines


def escape_md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def escape_backticks(text: str) -> str:
    return text.replace("`", "\\`")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=["lite", "verified", "both"],
        default="lite",
        help="Dataset preset to scan.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit.")
    parser.add_argument(
        "--llm-confirm",
        action="store_true",
        help="Run LLM semantic confirmation for problem_statement literal candidates.",
    )
    parser.add_argument(
        "--llm-config",
        default=str(ROOT / "configs" / "llm_deepseek.json"),
        help="Path to LLM config JSON.",
    )
    parser.add_argument(
        "--cache",
        default=str(ROOT / "reports" / "swe_leak_llm_cache.jsonl"),
        help="LLM cache path.",
    )
    parser.add_argument("--workers", type=int, default=8, help="LLM confirmation workers.")
    parser.add_argument("--issue-chars", type=int, default=3500)
    parser.add_argument("--patch-chars", type=int, default=1500)
    parser.add_argument(
        "--out-json",
        default=str(ROOT / "reports" / "swe_leak.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--out-md",
        default=str(ROOT / "reports" / "swe_leak.md"),
        help="Output Markdown path.",
    )
    return parser.parse_args(argv)


def specs_for_suite(suite: str) -> list[DatasetSpec]:
    labels = ["lite", "verified"] if suite == "both" else [suite]
    return [
        DatasetSpec(label=label, path=DATASET_PRESETS[label][0], split=DATASET_PRESETS[label][1])
        for label in labels
    ]


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset_results: list[dict[str, Any]] = []
    for spec in specs_for_suite(args.suite):
        print(f"Loading {spec.label}: {spec.path} [{spec.split}]", flush=True)
        rows = load_swebench(spec, args.limit)
        candidates, hints_only = scan_rows(rows)
        print(
            f"{spec.label}: {len(candidates)} problem_statement literal candidates, "
            f"{len(hints_only)} hints-only instances",
            flush=True,
        )
        if args.llm_confirm and candidates:
            print(f"{spec.label}: running LLM confirmation on {len(candidates)} candidates", flush=True)
            confirm_candidates(
                candidates,
                llm_config_path=args.llm_config,
                cache_path=args.cache,
                workers=args.workers,
                issue_chars=args.issue_chars,
                patch_chars=args.patch_chars,
            )
            confirmed = sum(1 for item in candidates if item.get("semantic_confirmed"))
            print(f"{spec.label}: {confirmed} semantic confirmed leaks", flush=True)
        else:
            for candidate in candidates:
                candidate.setdefault("llm_verdict", "not_run")
                candidate.setdefault("llm_evidence", "")
                candidate.setdefault("semantic_confirmed", False)

        dataset_results.append(
            {
                "label": spec.label,
                "dataset": spec.path,
                "split": spec.split,
                "n_instances": len(rows),
                "problem_statement_candidates": candidates,
                "hints_only_instances": hints_only,
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "llm_confirmation": bool(args.llm_confirm),
        "summaries": [summarize_result(result) for result in dataset_results],
        "datasets": [
            {
                **result,
                "problem_statement_candidates": [
                    strip_heavy_fields(item) for item in result["problem_statement_candidates"]
                ],
                "hints_only_instances": [
                    strip_heavy_fields(item) for item in result["hints_only_instances"]
                ],
            }
            for result in dataset_results
        ],
    }
    write_json(Path(args.out_json), payload)
    write_markdown(Path(args.out_md), payload)
    return payload


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    payload = run(args)
    for summary in payload["summaries"]:
        print(
            "{label}: ps_literal={ps}, confirmed={confirmed}, hints_only={hints}".format(
                label=summary["label"],
                ps=summary["problem_statement_literal_candidates"],
                confirmed=summary["semantic_confirmed_leaks"],
                hints=summary["hints_only_literal_instances"],
            )
        )
    print(f"Wrote {args.out_json}")
    print(f"Wrote {args.out_md}")


if __name__ == "__main__":
    main()
