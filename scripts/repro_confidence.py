#!/usr/bin/env python3
"""Reproducibility diagnostic: is the ~50% verdict flip a DECISION-BOUNDARY effect
(the model sits at P(defect)~=0.5 on hard rubrics) rather than a temperature bug?

For each labeled (task, rubric) pilot case we run ONLY the detector's voting step,
K times, each with a FRESH no-cache client, and record the raw per-vote defect
decisions -- WITHOUT the flag gate, so we see the vote margin even when the majority
says 'no defect'. Then per case:
  * P_hat(defect) = mean of all K*n individual votes = the model's confidence
  * flip = the majority verdict is NOT unanimous across the K runs
The claim, if true: flips concentrate where P_hat ~= 0.5; stable cases sit near 0 or 1.
We run at two vote temperatures (0.0 and 0.3) to see how much temperature actually
contributes. Reuses the real detector prompts/grounding from auditor_agent (no prod change).

Usage: python scripts/repro_confidence.py [--k 10]
"""
from __future__ import annotations

import argparse, importlib.util, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, LLMConfig, load_llm_config
from benchcore.file_reader import read_file

_a = importlib.util.spec_from_file_location("aa", REPO / "scripts" / "auditor_agent.py")
A = importlib.util.module_from_spec(_a); _a.loader.exec_module(A)

# 8 pilot cases (reproducibility_pilot.md): substrings uniquely identify the rubric.
CASES = [
    (107, "specific suggestions for market expansion", "B4", True,  "pinned market recommendation"),
    (45,  "cost accountant have edit, modify, and reference permissions", "B4", True, "pinned designed permission"),
    (33,  "1,057 tertiary hospitals", "B1", True,  "grade dimension absent (east)"),
    (33,  "808 tertiary hospitals",   "B1", True,  "grade dimension absent (central)"),
    (33,  "819 tertiary hospitals",   "B1", True,  "grade dimension absent (west)"),
    (37,  "identified as strong departments", "B4", False, "objective conclusion (not defect)"),
    (23,  "confusion between inboun", "B4", False, "objective issue (not defect)"),
    (388, "include a retention rate data table", "B1", False, "cross-language present (not defect)"),
]


def find_rubric(item, sub):
    hits = [r for r in item["rubrics"] if sub.lower() in r.lower()]
    if len(hits) != 1:
        raise SystemExit(f"substring {sub!r} matched {len(hits)} rubrics in id={item['id']}")
    return hits[0]


def raw_votes(item, rubric, detector, single, vote):
    """Per-vote defect booleans for ONE rubric, ungated. Reuses auditor_agent internals."""
    r = rubric
    if detector == "B4":
        res = vote.chat_json_multi(
            A.B4_JUDGE.replace("{task}", item["task"][:1200]).replace("{rubric}", r), "judge")
        return [x.get("leakage") is True for x in res if isinstance(x, dict)]
    # B1: reproduce extract -> literal miss -> verify voting (grounding is deterministic)
    names = " ".join(p.name for p in item["inputs"])
    blob = A.norm(names + " " + "\n".join(A.read_full(p) for p in item["inputs"])).lower()
    files_view = "所有输入文件: " + names + "\n\n" + "\n\n".join(
        f"FILE {p.name}\n" + read_file(p, 1500) for p in item["inputs"])
    ext = single.chat_json(A.B1_EXTRACT.replace("{rubric}", r), "extract")
    required = [t for t in ext.get("required", []) if A.core_term(t) and len(A.core_term(t)) >= 2]
    missing = [t for t in required if A.core_term(t).lower() not in blob]
    if not (required and missing):
        return []  # literal present -> B1 is confidently 'no defect' (no vote needed)
    res = vote.chat_json_multi(
        A.B1_VERIFY.replace("{missing}", ", ".join(missing))
                   .replace("{task}", item["task"][:1000] or "(未提供)")
                   .replace("{files}", files_view[:14000])
                   .replace("{hits}", A._search_terms(item["inputs"], missing))
                   .replace("{rubric}", r), "verify")
    return [x.get("verdict") == "not_in_inputs" for x in res if isinstance(x, dict)]


# model -> (single/extract base config, vote config prefix)
MODELS = {"deepseek": ("configs/llm_deepseek.json", "llm_deepseek"),
          "gpt55":    ("configs/llm_openrouter_gpt55.json", "llm_gpt55")}


def fresh_vote_client(detector, temp, model="deepseek"):
    v = "vote5" if detector == "B1" else "vote3"
    cfg_name = f"configs/{MODELS[model][1]}_{v}.json"
    cfg = LLMConfig(**{**load_llm_config(str(REPO / cfg_name)).__dict__})
    cfg.vote_temperature = temp
    cfg.cache_path = None
    return LLMClient(cfg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--temps", nargs="+", type=float, default=[0.0, 0.3])
    ap.add_argument("--model", choices=list(MODELS), default="deepseek")
    ap.add_argument("--out", default=None, help="output path; default reports/repro_confidence[_model].json")
    args = ap.parse_args()

    single = LLMClient(load_llm_config(str(REPO / MODELS[args.model][0])))  # extract, cached
    items: dict[int, A.Item] = {}
    out = []
    for cid, sub, det, gold, note in CASES:
        if cid not in items:
            items[cid] = A.load_hf_item(cid)
        item = items[cid]
        rubric = find_rubric(item, sub)
        rec = {"id": cid, "detector": det, "gold_defect": gold, "note": note,
               "rubric": rubric[:80], "by_temp": {}}
        for T in args.temps:
            # K independent runs, each a fresh no-cache client -> a real resample.
            def one_run(_):
                v = raw_votes(item, rubric, det, single, fresh_vote_client(det, T, args.model))
                if not v:
                    return {"n": 0, "frac": 0.0}          # confident no-defect
                return {"n": len(v), "frac": sum(v) / len(v)}
            with ThreadPoolExecutor(max_workers=min(5, args.k)) as ex:
                runs = list(ex.map(one_run, range(args.k)))
            fracs = [r["frac"] for r in runs]
            p_hat = sum(fracs) / len(fracs)
            majs = [f > 0.5 for f in fracs]               # per-run majority verdict
            n_defect = sum(majs)
            flip = 0 < n_defect < args.k
            rec["by_temp"][str(T)] = {
                "p_hat": round(p_hat, 3), "dist_from_boundary": round(abs(p_hat - 0.5), 3),
                "run_fracs": [round(f, 2) for f in fracs],
                "n_majority_defect": n_defect, "flip": flip}
            mark = "FLIP" if flip else "stbl"
            print(f"id={cid:<3} {det} T={T}  P_hat={p_hat:.2f} dist={abs(p_hat-0.5):.2f} "
                  f"maj_defect={n_defect}/{args.k} [{mark}]  {'DEF' if gold else 'ok'}  {sub[:30]}",
                  flush=True)
        out.append(rec)
    suffix = "" if args.model == "deepseek" else f"_{args.model}"
    outpath = REPO / (args.out or f"reports/repro_confidence{suffix}.json")
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {outpath.relative_to(REPO)}", flush=True)


if __name__ == "__main__":
    main()
