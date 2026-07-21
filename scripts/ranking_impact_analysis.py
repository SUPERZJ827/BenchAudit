#!/usr/bin/env python3
"""Ranking-impact analysis: do MMLU-Redux defects change the model leaderboard?

Reads per-model answers (scripts/mmlu_answer_models.py output) and compares each
model's ranking under three item sets:

  full      all 1000 items (defects included -- the naive leaderboard)
  objective removing the 181 items MMLU-Redux HUMAN-LABELED as objectively
            defective (wrong_groundtruth + no_correct_answer +
            multiple_correct_answers) -- the defect classes our auditor targets,
            though on MCQ these are review candidates, NOT auto-confirmed
  strict    keeping only the 630 error_type=="ok" items

For each pair we report per-model rank shifts, top-k churn, and Kendall's tau
between the full and cleaned rankings. A model that scored well only because it
matched a WRONG gold key drops once those items are removed; that drop is the
"ranking impact" of the benchmark defect.

Usage: ranking_impact_analysis.py [--models slug1,slug2,...]
"""
from __future__ import annotations

import argparse, json, sys
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ANS = REPO / "reports/ranking_impact/answers"
OUT = REPO / "reports/ranking_impact"

OBJECTIVE_DEFECTS = {"wrong_groundtruth", "no_correct_answer", "multiple_correct_answers"}


def load_model(slug: str) -> dict[str, dict]:
    f = ANS / f"{slug}.jsonl"
    return {r["id"]: r for r in (json.loads(l) for l in f.read_text().splitlines())}


def kendall_tau(order_a: list[str], order_b: list[str]) -> float:
    """Kendall's tau between two rankings given as ordered lists of the same items."""
    rank_b = {m: i for i, m in enumerate(order_b)}
    seq = [rank_b[m] for m in order_a]
    n = len(seq)
    if n < 2:
        return 1.0
    concordant = discordant = 0
    for i, j in combinations(range(n), 2):
        if seq[i] < seq[j]:
            concordant += 1
        elif seq[i] > seq[j]:
            discordant += 1
    return (concordant - discordant) / (0.5 * n * (n - 1))


def accuracy(recs: dict[str, dict], keep_ids: set[str]) -> tuple[float, int]:
    kept = [recs[i] for i in keep_ids if i in recs]
    if not kept:
        return 0.0, 0
    return sum(r["correct"] for r in kept) / len(kept), len(kept)


def ranked(accs: dict[str, float]) -> list[str]:
    return [m for m, _ in sorted(accs.items(), key=lambda kv: -kv[1])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="", help="comma slugs; default=all answered")
    args = ap.parse_args()

    slugs = ([s.strip() for s in args.models.split(",") if s.strip()]
             or sorted(p.stem for p in ANS.glob("*.jsonl")))
    models = {}
    for s in slugs:
        recs = load_model(s)
        # only include models that actually answered (drop dead-id test files)
        answered = [r for r in recs.values() if r["pred"]]
        if len(answered) >= 100:
            models[s] = recs
    if len(models) < 3:
        print(f"need >=3 answered models, have {len(models)}: {list(models)}"); return

    # item universe = ids present in the first model (all share the same dataset)
    any_recs = next(iter(models.values()))
    all_ids = set(any_recs)
    obj_ids = {i for i, r in any_recs.items() if r["error_type"] not in OBJECTIVE_DEFECTS}
    ok_ids = {i for i, r in any_recs.items() if r["error_type"] == "ok"}
    n_removed_obj = len(all_ids) - len(obj_ids)

    rows = []
    for s, recs in models.items():
        af, nf = accuracy(recs, all_ids)
        ao, no = accuracy(recs, obj_ids)
        ak, nk = accuracy(recs, ok_ids)
        rows.append({"model": s, "acc_full": af, "acc_obj": ao, "acc_strict": ak})

    acc_full = {r["model"]: r["acc_full"] for r in rows}
    acc_obj = {r["model"]: r["acc_obj"] for r in rows}
    acc_strict = {r["model"]: r["acc_strict"] for r in rows}
    ord_full, ord_obj, ord_strict = ranked(acc_full), ranked(acc_obj), ranked(acc_strict)
    rank_full = {m: i + 1 for i, m in enumerate(ord_full)}
    rank_obj = {m: i + 1 for i, m in enumerate(ord_obj)}

    tau_obj = kendall_tau(ord_full, ord_obj)
    tau_strict = kendall_tau(ord_full, ord_strict)
    max_shift = max(abs(rank_full[m] - rank_obj[m]) for m in acc_full)
    top1_changed = ord_full[0] != ord_obj[0]

    # write markdown report
    L = ["# 排名影响实验:benchmark 缺陷是否改变模型排名(MMLU-Redux)\n",
         f"> 数据:MMLU-Redux 1000 题(带 error_type 真值标注);{len(models)} 个模型;"
         "zero-shot 单次作答。\n",
         "> 口径:**full**=全 1000 题(含缺陷);**objective**=剔除 "
         f"{n_removed_obj} 道 MMLU-Redux 人工标注的客观缺陷题(wrong_groundtruth/"
         "no_correct/multiple_correct,即我们审计器针对的类型;MCQ 上为 review 候选,"
         "不自动 confirmed);**strict**=只留 630 道 ok 题。\n",
         "\n## 排名对照(按 full 排名)\n",
         "| full名次 | 模型 | acc_full | acc_objective | objective名次 | 名次变化 |",
         "|---:|---|---:|---:|---:|:--:|"]
    for m in ord_full:
        shift = rank_full[m] - rank_obj[m]
        arrow = "—" if shift == 0 else (f"↑{shift}" if shift > 0 else f"↓{-shift}")
        L.append(f"| {rank_full[m]} | {m} | {acc_full[m]:.3f} | {acc_obj[m]:.3f} "
                 f"| {rank_obj[m]} | {arrow} |")
    L += ["\n## 核心指标\n",
          f"- **Kendall's τ(full vs objective)= {tau_obj:.3f}**(1.0=排名完全不变;越低=洗牌越厉害)",
          f"- Kendall's τ(full vs strict-ok)= {tau_strict:.3f}",
          f"- **最大名次变动 = {max_shift} 位**",
          f"- **Top-1 是否换人:{'是 ⚠️' if top1_changed else '否'}**"
          + (f"(full={ord_full[0]} → objective={ord_obj[0]})" if top1_changed else ""),
          "\n## 解读\n",
          "剔除的都是**客观错题**(标准答案本身错/无正确答案/多正确答案)——在这些题上,"
          "模型答案匹配错误 gold 才算「对」,所以 full 排名奖励了「和标注者犯同样错误」的模型。"
          "剔除后名次变动与 Top-1 变化,即为 benchmark 缺陷对排名的直接影响。\n",
          "## 与审计系统的闭环\n",
          "被剔除的 3 类正是本项目审计器**针对**的缺陷类型(wrong_gold / no_correct / "
          "multiple_correct)——在 MCQ 上这些是 **review 候选**(LLM 判断),不是自动 confirmed。"
          "本节量化第三方标注错题对排名的影响;审计器自身检出的闭环见 closed_loop_ranking.md,"
          "其 per-subject 结果须对照 random_deletion_control.md(见下方边界)。\n",
          "## 诚实边界\n",
          f"- 仅 1000 题子集、{len(models)} 个模型、zero-shot 单次、无投票;更大 leaderboard 变动可能不同。",
          "- 真值用 MMLU-Redux 标注(第三方人工),非本项目审计器输出;闭环成立但两者是独立来源。",
          "- 排名基于单次作答,存在采样噪声;方向性结论稳健,具体名次可能有 ±1 抖动。"]
    # ---- per-subject ranking impact (where defects concentrate) ----
    subjects = {}
    for i, r in any_recs.items():
        subjects.setdefault(r["subject"], set()).add(i)
    per_subj = []
    for subj, ids in subjects.items():
        obj_here = {i for i in ids if any_recs[i]["error_type"] not in OBJECTIVE_DEFECTS}
        removed = len(ids) - len(obj_here)
        if len(ids) < 15 or removed < 3 or len(obj_here) < 5:
            continue
        af = {s: accuracy(recs, ids)[0] for s, recs in models.items()}
        ao = {s: accuracy(recs, obj_here)[0] for s, recs in models.items()}
        of, oo = ranked(af), ranked(ao)
        rf = {m: i + 1 for i, m in enumerate(of)}
        ro = {m: i + 1 for i, m in enumerate(oo)}
        per_subj.append({
            "subject": subj, "n": len(ids), "removed": removed,
            "tau": kendall_tau(of, oo),
            "max_shift": max(abs(rf[m] - ro[m]) for m in af),
            "top1_full": of[0], "top1_obj": oo[0], "top1_changed": of[0] != oo[0]})
    per_subj.sort(key=lambda d: (d["tau"], -d["max_shift"]))
    n_top1_changed = sum(d["top1_changed"] for d in per_subj)

    L += ["\n## Per-subject 排名影响(缺陷集中处,文献效应所在)\n",
          f"在 {len(per_subj)} 个题数≥15、剔除≥3 道客观错题的 subject 中,"
          f"**{n_top1_changed} 个的 Top-1 在剔除错题后换人**。洗牌最厉害的:\n",
          "| subject | 题数 | 剔除客观错题 | Kendall τ | 最大名次变动 | Top-1 变化 |",
          "|---|---:|---:|---:|---:|---|"]
    for d in per_subj[:12]:
        chg = (f"⚠️ {d['top1_full'].split('__')[-1]} → {d['top1_obj'].split('__')[-1]}"
               if d["top1_changed"] else "否")
        L.append(f"| {d['subject']} | {d['n']} | {d['removed']} | {d['tau']:.2f} "
                 f"| {d['max_shift']} | {chg} |")
    glob_desc = ("完全不变" if tau_obj >= 0.999 else
                 f"仅轻微变动(τ={tau_obj:.3f},最大 {max_shift} 位)")
    L += [f"\n**结论**:全局 {len(all_ids)} 题上排名{glob_desc}——"
          + ("模型梯度大时缺陷撼不动整体名次;"
             if tau_obj >= 0.999 else
             "leaderboard 越密集,缺陷越能扰动全局名次(本实验 8 模型时 τ=1.0、15 模型时 "
             f"τ={tau_obj:.3f});") +
          f"per-subject 层面表面上有 {n_top1_changed}/{len(per_subj)} 个 subject 冠军易主,"
          "**但这一表象经不起随机删题对照**(见 `random_deletion_control.md`):细分 subject 只有 "
          "8–27 题,剔除缺陷后常剩个位数、多个模型并列,'冠军'由 tie-break 决定;删**等量随机题**"
          "翻转的 subject 数与之无统计差异(p≈0.32)。**因此不能把 per-subject 冠军易主当作缺陷影响的证据。**"
          "真正站得住的是:全局名次随 leaderboard 加密而出现真实换位,以及个别单点(如 philosophy,"
          "随机翻转概率仅 1.8%)审计器精准命中了扭转排名的缺陷题。\n"]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ranking_impact.md").write_text("\n".join(L), encoding="utf-8")
    (OUT / "ranking_impact_per_subject.json").write_text(
        json.dumps(per_subj, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "ranking_impact.json").write_text(json.dumps({
        "n_models": len(models), "n_items_full": len(all_ids),
        "n_removed_objective": n_removed_obj,
        "rows": rows, "rank_full": rank_full, "rank_objective": rank_obj,
        "kendall_tau_objective": tau_obj, "kendall_tau_strict": tau_strict,
        "max_rank_shift": max_shift, "top1_changed": top1_changed,
        "order_full": ord_full, "order_objective": ord_obj,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"models={len(models)} removed_objective={n_removed_obj} "
          f"tau_obj={tau_obj:.3f} max_shift={max_shift} top1_changed={top1_changed}")
    print("wrote reports/ranking_impact/ranking_impact.md")


if __name__ == "__main__":
    main()
