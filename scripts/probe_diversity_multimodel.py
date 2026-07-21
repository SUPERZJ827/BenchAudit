#!/usr/bin/env python3
"""Step 2 of the probe-diversity question: does MODEL diversity (unlike the
temperature diversity ruled out in step 1) raise evaluator blind-spot recall?

Each model generates probes at temperature 0 (its "obvious" mutation, which step 1
found is the blind-spot-revealing one), and we take the UNION of items that
surface an actionable evaluator-soundness signal. If different models at temp=0
union to catch blind spots DeepSeek alone misses, model diversity is the real
recall lever; if the union barely exceeds DeepSeek, execution-tier recall is
capped and multi-model is not worth it.

DeepSeek baseline is read from the temp=0 pilot (reports/ds1000_exec_pilot200);
the other models run fresh via OpenRouter (cheap, cached, temp=0, gen_slack=0 to
match). Only probe GENERATION differs across models -- execution/adjudication is
identical, so any new signal is attributable to the generating model.

Usage: probe_diversity_multimodel.py --container-image IMG@sha256:...
"""
from __future__ import annotations

import argparse, json, sys, collections
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
from benchcore.evaluator_execution import ExecutionEvaluatorAuditChecker
from benchcore.execution import ContainerRunner
from benchcore.llm_client import LLMClient, LLMConfig, load_llm_config
from benchcore.loader import explicit_mapping_provenance
from benchcore.schema import BenchmarkItem
from benchcore.task_uniqueness import classify_task_multiplicity
from probe_diversity_experiment import pick_items, flagged_of, baseline_flagged, OUT

MODELS = [
    "openrouter:openai/gpt-4o-mini",
    "openrouter:qwen/qwen-2.5-72b-instruct",
    "openrouter:meta-llama/llama-3.3-70b-instruct",
]


def make_client(spec: str) -> tuple[str, LLMClient]:
    slug = spec.split(":", 1)[1].replace("/", "__")
    base = load_llm_config(str(REPO / "configs/llm_openrouter_gpt55.json"))
    cfg = LLMConfig(**{**base.__dict__})
    cfg.model = spec.split(":", 1)[1]
    cfg.temperature = 0.0
    cfg.cache_path = str(OUT / f"cache_{slug}.jsonl")
    return slug, LLMClient(cfg)


def audit_model(spec, items, runner, workers):
    slug, client = make_client(spec)

    def one(r):
        checker = ExecutionEvaluatorAuditChecker(client, runner=runner, gen_slack=0)
        item = BenchmarkItem(
            item_id=f"ds1000_{r['metadata']['problem_id']}", raw=r, task=r["prompt"],
            gold=r["reference_code"],
            evaluator={"code_context": r["code_context"],
                       "n_cases": int(r["metadata"].get("test_case_cnt") or 1)},
            metadata={"_mapping_provenance": explicit_mapping_provenance(
                adapter_id="ds1000_probe_diversity_multimodel",
                adapter_version="1",
                raw=r,
                field_bindings={
                    "task": "prompt", "gold": "reference_code",
                    "evaluator": "code_context",
                },
            )},
        )
        try:
            return r["metadata"]["problem_id"], flagged_of(list(checker.check(item)))
        except Exception:
            return r["metadata"]["problem_id"], set()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = dict(ex.map(one, items))
    flagged = {pid: h for pid, h in res.items() if h}
    print(f"[{slug}] {len(flagged)} items flagged: {sorted(flagged)}", flush=True)
    return slug, flagged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--container-image", required=True)
    ap.add_argument("--container-engine", default="docker")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    items = pick_items()
    pids = {r["metadata"]["problem_id"] for r in items}
    runner = ContainerRunner(args.container_image, engine=args.container_engine)

    per_model = {"deepseek": baseline_flagged(pids)}
    print(f"[deepseek] baseline {len(per_model['deepseek'])} flagged: "
          f"{sorted(per_model['deepseek'])}", flush=True)
    for spec in MODELS:
        slug, flagged = audit_model(spec, items, runner, args.workers)
        per_model[slug] = flagged

    def triage_of(pid):
        r = next(x for x in items if x["metadata"]["problem_id"] == pid)
        return classify_task_multiplicity(r["prompt"]).triage

    union = collections.defaultdict(set)
    for flagged in per_model.values():
        for pid, h in flagged.items():
            union[pid] |= h
    ds = set(per_model["deepseek"])
    new_vs_ds = sorted(set(union) - ds)

    L = ["# 探针多样性 step 2:模型多样性能否提升盲点召回?\n",
         f"> {len(items)} 题(Pandas+Numpy 各 30),每模型 temp=0、gen_slack=0 生成探针,"
         "取存活/过严信号并集。仅生成模型不同,执行/裁决一致。\n",
         "\n## 各模型 flagged\n",
         "| 模型 | flagged 题数 | 题 |", "|---|---:|---|"]
    for slug, flagged in per_model.items():
        L.append(f"| {slug} | {len(flagged)} | {sorted(flagged) or '—'} |")
    L += [f"\n## 并集 vs DeepSeek 单模型\n",
          f"- DeepSeek 单模型 flagged: **{len(ds)}** — {sorted(ds)}",
          f"- 全模型并集 flagged: **{len(union)}** — {sorted(union)}",
          f"- **并集比 DeepSeek 新增**: {len(new_vs_ds)} 题 — "
          + (", ".join(f"{pid}({triage_of(pid)})" for pid in new_vs_ds) or "无"),
          "\n## 结论\n",
          "- 新增里 triage=priority 才是真盲点召回提升;by_design/ambiguous 是多解噪声。",
          ("- **模型多样性有效**:不同模型 temp=0 的显然变异命中了 DeepSeek 漏掉的盲点 → 多模型是执行层召回的真杠杆。"
           if any(triage_of(p) == "priority" for p in new_vs_ds) else
           "- **模型多样性增益有限/为噪声**:并集未新增 priority 盲点 → 执行层召回已近上限,多模型不值得常态化。")]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "probe_diversity_step2.md").write_text("\n".join(L), encoding="utf-8")
    (OUT / "probe_diversity_step2.json").write_text(json.dumps({
        "per_model": {k: {p: sorted(v) for p, v in fl.items()} for k, fl in per_model.items()},
        "union": {k: sorted(v) for k, v in union.items()},
        "new_vs_deepseek": {pid: triage_of(pid) for pid in new_vs_ds},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\ndeepseek={len(ds)} union={len(union)} new={len(new_vs_ds)} "
          f"new_priority={sum(1 for p in new_vs_ds if triage_of(p)=='priority')}")
    print("wrote reports/probe_diversity/probe_diversity_step2.md")


if __name__ == "__main__":
    main()
