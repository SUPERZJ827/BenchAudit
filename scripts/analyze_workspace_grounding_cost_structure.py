#!/usr/bin/env python3
"""Analyze Workspace grounding call structure without making LLM calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.run_workspace_static_llm_ablation import (  # noqa: E402
    _read_completed_items,
    estimate_grounding_call_structure,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grounding-items", type=Path, required=True)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def render_report(summary: dict[str, Any]) -> str:
    legacy = summary["legacy"]
    conservative = summary["two_stage_conservative"]
    floor = summary["two_stage_final_candidate_floor"]
    observed = summary.get("observed_legacy_api") or {}
    return f"""# Workspace rubric grounding 成本结构重放

> 本报告不调用 LLM。它冻结旧实验的 scanner/verifier 语义结果，只替换调用
> 编排，以隔离“结构优化”本身的收益。

## 结果

| 结构 | shared scan | isolated scanner/verifier | 逻辑调用 | 相对旧结构减少 |
|---|---:|---:|---:|---:|
| 旧逐 rubric 双阶段 | 0 | {legacy['logical_calls']:,} | {legacy['logical_calls']:,} | 0.0% |
| 新两阶段（保守重放） | {conservative['shared_triage_calls']:,} | {conservative['isolated_verifier_calls']:,} | {conservative['logical_calls']:,} | {conservative['relative_call_reduction']:.1%} |
| 最终候选下界（仅规划） | {floor['shared_triage_calls']:,} | {floor['isolated_verifier_calls']:,} | {floor['logical_calls']:,} | {floor['relative_call_reduction']:.1%} |

- 数据：{summary['items']} items / {summary['rubrics']:,} rubrics。
- 旧结构：{legacy['isolated_scanner_calls']:,} 次逐 rubric scanner +
  {legacy['isolated_verifier_calls']:,} 次 verifier。
- 保守重放把旧 scanner 判为 unsupported 的每一条都送入隔离 verifier，
  因此没有通过减少旧候选集合来制造节省。
- “最终候选下界”假设路由器只选择旧实验最终保留的候选；它不是新模型
  已达到的实测结果。

## 旧 API 观测

- API attempts：{observed.get('api_attempts', '未提供')}
- prompt tokens：{observed.get('prompt_tokens', '未提供')}
- completion tokens：{observed.get('completion_tokens', '未提供')}
- total tokens：{observed.get('total_tokens', '未提供')}

不能把 67.0% 的逻辑调用降幅直接等同于 token 或人民币降幅：新的 shared
triage prompt 会一次携带该 item 的全部 rubrics，而 isolated verifier 仍需原始
证据。真实 token 降幅必须在小规模固定样本上测量。

## 安全边界

shared triage 只允许路由候选，不能直接产生 substantive finding。只有逐条
隔离 verifier 同意、且本地 citation replay 通过后，结果才能进入 review；
LLM 路径仍不能升级为 confirmed。
"""


def main() -> None:
    args = parse_args()
    rows = _read_completed_items(args.grounding_items.expanduser().resolve())
    summary = estimate_grounding_call_structure(rows)
    if args.runtime:
        runtime = json.loads(args.runtime.expanduser().resolve().read_text(encoding="utf-8"))
        summary["observed_legacy_api"] = (
            runtime.get("grounding", {}).get("llm", {})
        )
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out_dir / "report.md").write_text(
        render_report(summary),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
