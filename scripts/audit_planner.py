#!/usr/bin/env python3
"""Audit Planner (Direction A): zero-config onboarding of unseen benchmarks.

Given a few raw items of a benchmark it has never been configured for, an LLM
planner infers (1) the task type, (2) the field mapping to the canonical
(task, gold, options, context, evaluator) schema, (3) the evaluator type, and
(4) which auditors/checkers are worth running. This automates the per-benchmark
onboarding that is otherwise hand-written, and adapts the checker set to the
benchmark instead of always running the same pipeline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

PLANNER_PROMPT = """You are an audit planner for a benchmark quality-checking system.
Given a few raw items from an unseen benchmark, produce an audit plan.

The system can run these auditors:
- gold: verify the gold answer by independently solving (math/QA with a checkable answer)
- question: detect ambiguous/underspecified questions
- option: detect multiple-correct / no-correct / unclear options (multiple-choice only)
- presentation: detect OCR/encoding/format corruption
- quantity: arithmetic/quantity consistency (math word problems)
- event: event-state consistency (narrative math)
- holistic: holistic sampled judge (any task)
- codeexec: compute the answer from a TABLE with executed code (table-QA only)

Return ONLY JSON:
{
  "task_type": "multiple_choice" | "math_word_problem" | "table_qa" | "free_form" | "other",
  "field_mapping": {"task": "<key>", "gold": "<key>", "choices": "<key or null>",
                    "context": "<key or null>", "evaluator": "<key or null>"},
  "evaluator_type": "<short description>",
  "recommended_auditors": ["..."],
  "rationale": "one sentence"
}

Sample items:
{samples}"""


def plan_dataset(path: Path, client: LLMClient, n: int = 3) -> dict:
    rows = [json.loads(l) for l in path.open(encoding="utf-8")][:n]
    samples = json.dumps([{k: (str(v)[:300]) for k, v in r.items()} for r in rows],
                         ensure_ascii=False, indent=1)
    return client.chat_json(PLANNER_PROMPT.replace("{samples}", samples), "Plan this benchmark.")


def main() -> None:
    datasets = {
        "arc_challenge": "datasets/arc_challenge/arc_challenge_normalized_all.jsonl",
        "truthfulqa": "datasets/truthfulqa/truthfulqa_mc1_validation_20.jsonl",
        "goldenswag": "datasets/goldenswag/annotations_strict_train_0_20.jsonl",
        "wikitablequestions": "experiments/wikitablequestions_pilot100.jsonl",
    }
    base = Path("/home/zhoujun/llmdata")
    cfg = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
    cfg.cache_path = "reports/audit_planner_cache.jsonl"
    client = LLMClient(cfg)

    out = {}
    print(f"{'dataset':22} {'task_type':20} {'recommended auditors'}")
    for name, rel in datasets.items():
        p = base / rel if (base / rel).exists() else REPO / rel
        try:
            plan = plan_dataset(p, client)
        except Exception as e:
            plan = {"error": str(e)}
        out[name] = plan
        print(f"{name:22} {str(plan.get('task_type')):20} {plan.get('recommended_auditors')}")
        print(f"{'':22} mapping: {plan.get('field_mapping')}")
        print(f"{'':22} rationale: {plan.get('rationale')}")
    (REPO / "reports/audit_planner_plans_20260630.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote reports/audit_planner_plans_20260630.json")


if __name__ == "__main__":
    main()
