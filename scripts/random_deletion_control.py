#!/usr/bin/env python3
"""Random-deletion control: is the per-subject top-1 churn REAL signal, or just an
artifact of deleting more items?

The closed-loop experiment removed the auditor's flagged items and found 11/28
subjects change their top-1 model. But removing MORE items from a subject
mechanically raises the odds the top-1 flips (fewer items left, higher variance).
This control removes, per subject, the SAME NUMBER of items but chosen at RANDOM,
bootstrapped B times, and asks: does defect-guided deletion flip the top-1 in
significantly more subjects than equal-size random deletion?

For each removal source (auditor flags / third-party MMLU-Redux labels):
  observed A = # considered subjects whose top-1 flips under the real deletion
  null distribution = for B iterations, delete the same per-subject count at
                      random and count flips; gives mean, 95% band, p=P(null>=A)
  per subject: p_random = fraction of random draws (same k) that flip the top-1

Uses only cached answers -- no LLM calls, no cost. Reuses ranking_impact_analysis.

Usage: random_deletion_control.py --models "<15 slugs>" [--iters 2000] [--seed 0]
"""
from __future__ import annotations

import argparse, json, random, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import ranking_impact_analysis as ria  # accuracy, ranked, load_model
from closed_loop_ranking import AUDIT_OBJ, MMLU_OBJ  # defect type sets

DATA = REPO / "experiments/mmlu_redux_pilot1000.jsonl"
OUT = REPO / "reports/ranking_impact"
MIN_ITEMS, MIN_REMOVED, MIN_KEEP = 15, 3, 5


def top1(models, keep_ids):
    accs = {s: ria.accuracy(recs, keep_ids)[0] for s, recs in models.items()}
    return ria.ranked(accs)[0]


def considered_subjects(models, subj_ids, removed):
    """Subjects meeting the filter for a given removed-id set; with per-subj k."""
    out = []
    for s, ids in subj_ids.items():
        k = len(ids & removed)
        if len(ids) < MIN_ITEMS or k < MIN_REMOVED or len(ids) - k < MIN_KEEP:
            continue
        out.append((s, ids, k))
    return out


def control(models, subj_ids, removed, iters, rng):
    subs = considered_subjects(models, subj_ids, removed)
    per_subject, observed_total = [], 0
    null_per_subj = {}  # subject -> list of 0/1 over iters
    for s, ids, k in subs:
        base_top1 = top1(models, ids)
        obs_flip = int(top1(models, ids - (ids & removed)) != base_top1)
        observed_total += obs_flip
        ids_list = list(ids)
        flips = 0
        draws = []
        for _ in range(iters):
            drop = set(rng.sample(ids_list, k))
            f = int(top1(models, ids - drop) != base_top1)
            flips += f
            draws.append(f)
        null_per_subj[s] = draws
        per_subject.append({"subject": s, "n": len(ids), "k": k,
                            "observed_flip": obs_flip,
                            "p_random_flip": round(flips / iters, 4)})
    # null distribution of the TOTAL flip count across subjects
    null_totals = [sum(null_per_subj[s][b] for s in null_per_subj) for b in range(iters)]
    ge = sum(1 for t in null_totals if t >= observed_total)
    p_value = (ge + 1) / (iters + 1)  # add-one (never reports p=0)
    null_totals.sort()
    lo, hi = null_totals[int(0.025 * iters)], null_totals[int(0.975 * iters)]
    return {
        "considered": len(subs),
        "observed_total": observed_total,
        "null_mean": round(sum(null_totals) / iters, 2),
        "null_95_lo": lo, "null_95_hi": hi,
        "p_value": round(p_value, 4),
        "per_subject": sorted(per_subject, key=lambda d: d["p_random_flip"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    ap.add_argument("--audit", default=str(OUT / "audit_full1000.json"))
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    rows = {json.loads(l)["id"]: json.loads(l)
            for l in DATA.read_text(encoding="utf-8").splitlines()}
    all_ids = set(rows)
    mmlu_obj = {i for i, r in rows.items() if r["metadata"]["error_type"] in MMLU_OBJ}
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    flagged = {v["item_id"] for v in audit.get("violations", [])
               if v["defect_type"] in AUDIT_OBJ} & all_ids

    slugs = [s.strip() for s in args.models.split(",") if s.strip()]
    models = {s: ria.load_model(s) for s in slugs}
    models = {s: r for s, r in models.items()
              if len([1 for x in r.values() if x["pred"]]) >= 100}
    any_recs = next(iter(models.values()))
    subj_ids = {}
    for i in all_ids:
        subj_ids.setdefault(any_recs[i]["subject"], set()).add(i)

    res_audit = control(models, subj_ids, flagged, args.iters, rng)
    res_mmlu = control(models, subj_ids, mmlu_obj, args.iters, rng)

    def verdict(r):
        return ("**显著**(删题不是靠数量)" if r["p_value"] < 0.05
                else "不显著(可能只是删得多)")

    L = ["# 随机删题对照:冠军易主是真信号还是删得多的假象?\n",
         "> 对每个 subject 删**相同数量**的随机题,bootstrap "
         f"{args.iters} 次,看真实删题(审计器/第三方)导致的冠军易主"
         "是否显著高于等量随机删题。仅用缓存答题,无 LLM 调用。\n",
         "\n## 汇总\n",
         "| 删题依据 | 考察 subject 数 | 真实冠军易主 | 随机删题均值 | 随机 95% 区间 | p 值 | 结论 |",
         "|---|---:|---:|---:|:--:|---:|---|",
         f"| 我们审计器检出 | {res_audit['considered']} | {res_audit['observed_total']} "
         f"| {res_audit['null_mean']} | [{res_audit['null_95_lo']}, {res_audit['null_95_hi']}] "
         f"| {res_audit['p_value']} | {verdict(res_audit)} |",
         f"| 第三方 MMLU-Redux 标注 | {res_mmlu['considered']} | {res_mmlu['observed_total']} "
         f"| {res_mmlu['null_mean']} | [{res_mmlu['null_95_lo']}, {res_mmlu['null_95_hi']}] "
         f"| {res_mmlu['p_value']} | {verdict(res_mmlu)} |"]

    for name, r in [("我们审计器检出", res_audit), ("第三方 MMLU-Redux 标注", res_mmlu)]:
        L += [f"\n## 逐 subject:{name}(按随机翻转概率升序)\n",
              "> `真实翻转`=真实删题是否换冠军;`随机翻转概率`=删同样数量随机题时换冠军的频率。"
              "真实翻转=1 且随机概率低,才是审计器**定位到了关键题**,而非删多了。\n",
              "| subject | 题数 | 删除数 k | 真实翻转 | 随机翻转概率 |",
              "|---|---:|---:|:--:|---:|"]
        for d in r["per_subject"]:
            L.append(f"| {d['subject']} | {d['n']} | {d['k']} "
                     f"| {'✔' if d['observed_flip'] else '·'} | {d['p_random_flip']:.3f} |")

    L += ["\n## 怎么读这张表\n",
          "- **p < 0.05**:真实删题换冠军的 subject 数,显著多于等量随机删题——"
          "排名扰动是**审计器定位到关键缺陷题**的结果,不是删得多的机械假象。",
          "- **某 subject 真实翻转✔但随机概率也高(如 >0.5)**:该 subject 的换冠军对删哪几题不敏感,"
          "证据力弱,不应单独拿来当卖点。",
          "- **真实翻转✔且随机概率低**:审计器精准命中了那道扭转排名的缺陷题,是最硬的单点证据。"]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "random_deletion_control.md").write_text("\n".join(L), encoding="utf-8")
    (OUT / "random_deletion_control.json").write_text(
        json.dumps({"iters": args.iters, "seed": args.seed,
                    "audit": res_audit, "mmlu": res_mmlu},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"audit: obs={res_audit['observed_total']}/{res_audit['considered']} "
          f"null_mean={res_audit['null_mean']} p={res_audit['p_value']}")
    print(f"mmlu:  obs={res_mmlu['observed_total']}/{res_mmlu['considered']} "
          f"null_mean={res_mmlu['null_mean']} p={res_mmlu['p_value']}")
    print("wrote reports/ranking_impact/random_deletion_control.md")


if __name__ == "__main__":
    main()
