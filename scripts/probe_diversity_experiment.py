#!/usr/bin/env python3
"""Step 1 of the probe-diversity question: does SAME-model temperature sampling
raise evaluator blind-spot recall via the UNION of surviving-mutant signals?

Baseline is the temp=0 pilot (reports/ds1000_exec_pilot200): one deterministic
probe set per item. This re-audits the same 60 items K times at temperature 0.7
with caching off, so each round draws a different probe set, and takes the UNION
of items that surface an actionable evaluator-soundness signal
(underconstrained_evaluator_risk / evaluator_mutation_survived /
overstrict_evaluator). If the union meaningfully exceeds the temp=0 baseline, then
probe diversity helps -- and multi-model (step 2) is worth paying for; if not,
single-model sampling is not the lever.

Same-model only: DeepSeek, no OpenRouter cost. gen_slack=0 to match the baseline
(the only differences vs baseline are temperature and the number of rounds).

Usage: probe_diversity_experiment.py --container-image IMG@sha256:... --rounds 3
"""
from __future__ import annotations

import argparse, json, sys, collections
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.evaluator_execution import ExecutionEvaluatorAuditChecker
from benchcore.execution import ContainerRunner
from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.schema import BenchmarkItem
from benchcore.task_uniqueness import classify_task_multiplicity

DS1000 = Path.home() / (".cache/huggingface/hub/datasets--xlangai--DS-1000/"
                        "snapshots/4416080ac5cb80bdf7576aefb8f9a0b4d5426a44/test.jsonl")
BASELINE = REPO / "reports/ds1000_exec_pilot200"
OUT = REPO / "reports/probe_diversity"
ACTIONABLE = {"underconstrained_evaluator_risk", "evaluator_mutation_survived",
              "overstrict_evaluator"}


def pick_items(n_per_lib=30, libs=("Pandas", "Numpy")):
    rows = [json.loads(l) for l in DS1000.read_text().splitlines()]
    seen: dict = {}
    picked = []
    for r in rows:
        lib = r["metadata"]["library"]
        if lib in libs and seen.get(lib, 0) < n_per_lib:
            seen[lib] = seen.get(lib, 0) + 1
            picked.append(r)
    return picked


def flagged_of(violations) -> set[str]:
    return {v.defect_type for v in violations if v.defect_type in ACTIONABLE}


def baseline_flagged(pids: set[str]) -> dict[str, set[str]]:
    out = {}
    for pid in pids:
        f = BASELINE / f"{pid}.json"
        if not f.exists():
            continue
        s = json.loads(f.read_text()).get("summary", {})
        hits = {v["defect_type"] for v in (s.get("violations") or [])
                if v["defect_type"] in ACTIONABLE}
        if hits:
            out[pid] = hits
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--container-image", required=True)
    ap.add_argument("--container-engine", default="docker")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    items = pick_items()
    pids = {r["metadata"]["problem_id"] for r in items}
    runner = ContainerRunner(args.container_image, engine=args.container_engine)
    cfg = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
    cfg.temperature = args.temperature
    cfg.cache_path = None  # force a fresh sample each round
    client = LLMClient(cfg)

    def audit_one(r):
        checker = ExecutionEvaluatorAuditChecker(client, runner=runner, gen_slack=0)
        item = BenchmarkItem(
            item_id=f"ds1000_{r['metadata']['problem_id']}", raw={}, task=r["prompt"],
            gold=r["reference_code"],
            evaluator={"code_context": r["code_context"],
                       "n_cases": int(r["metadata"].get("test_case_cnt") or 1)})
        try:
            return r["metadata"]["problem_id"], flagged_of(list(checker.check(item)))
        except Exception:
            return r["metadata"]["problem_id"], set()

    base = baseline_flagged(pids)
    rounds: list[dict[str, set[str]]] = []
    for k in range(args.rounds):
        print(f"=== round {k+1}/{args.rounds} (temp={args.temperature}) ===", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            res = dict(ex.map(audit_one, items))
        flagged = {pid: h for pid, h in res.items() if h}
        rounds.append(flagged)
        print(f"  round {k+1}: {len(flagged)} items flagged", flush=True)

    union: dict[str, set[str]] = collections.defaultdict(set)
    for rd in rounds:
        for pid, h in rd.items():
            union[pid] |= h
    new_vs_base = sorted(set(union) - set(base))
    lost_vs_base = sorted(set(base) - set(union))

    def triage_of(pid):
        r = next(x for x in items if x["metadata"]["problem_id"] == pid)
        return classify_task_multiplicity(r["prompt"]).triage

    L = ["# 探针多样性 step 1:同模型 temperature 采样能否提升盲点召回?\n",
         f"> {len(items)} 题(Pandas+Numpy 各 30),DeepSeek temp={args.temperature}、无缓存、"
         f"{args.rounds} 轮、gen_slack=0(与 temp=0 baseline 唯一差异=温度+轮数)。取存活/过严信号并集。\n",
         "\n## 结果\n",
         f"- **temp=0 baseline(单次)flagged**: {len(base)} 题 — {sorted(base)}",
         *[f"- temp={args.temperature} round {k+1} flagged: {len(rd)} 题 — {sorted(rd)}"
           for k, rd in enumerate(rounds)],
         f"- **temp={args.temperature} 三轮并集 flagged**: {len(union)} 题 — {sorted(union)}",
         f"\n- **并集比 baseline 新增**: {len(new_vs_base)} 题 — "
         + (", ".join(f"{pid}({triage_of(pid)})" for pid in new_vs_base) or "无"),
         f"- **baseline 有但并集漏掉**: {len(lost_vs_base)} 题 — {lost_vs_base or '无'}",
         "\n## 判读\n",
         "- 新增题里 triage=priority 的才是**真盲点召回提升**;by_design/ambiguous 是多解任务噪声。",
         "- 若并集 ≈ baseline(新增都是噪声或没有)→ 同模型采样多样性无用,多模型多半也不值得花钱。",
         "- 若并集显著 ⊃ baseline 且新增含 priority → 多样性有效,step 2(多模型)值得验证。"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "probe_diversity_step1.md").write_text("\n".join(L), encoding="utf-8")
    (OUT / "probe_diversity_step1.json").write_text(json.dumps({
        "baseline": {k: sorted(v) for k, v in base.items()},
        "rounds": [{k: sorted(v) for k, v in rd.items()} for rd in rounds],
        "union": {k: sorted(v) for k, v in union.items()},
        "new_vs_baseline": {pid: triage_of(pid) for pid in new_vs_base},
        "lost_vs_baseline": lost_vs_base,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nbaseline={len(base)} union={len(union)} new={len(new_vs_base)} "
          f"lost={len(lost_vs_base)}")
    print("wrote reports/probe_diversity/probe_diversity_step1.md")


if __name__ == "__main__":
    main()
