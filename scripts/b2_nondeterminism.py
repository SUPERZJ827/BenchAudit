#!/usr/bin/env python3
"""B2 code-nondeterminism experiment.

The reproducibility pilot measured whether the LLM's *verdict* is stable when it
JUDGES a rubric (B1/B4 voting). B2 is different: it does not judge, it asks the
LLM to WRITE pandas code that recomputes the rubric's asserted number, runs that
code, and compares. So B2 carries an extra, stronger source of irreproducibility:
the recompute CODE itself is regenerated every call and may read a different
column / period / granularity each time -> the same rubric can flip
match<->mismatch across runs with the SAME input.

This script quantifies that. It reuses the REAL detector path from auditor_agent
(the same l1.PROMPT codegen, l1.run_code executor, and l1.rubric_values / l1.nums
comparison), reruns ONLY the codegen+exec+compare step K times per numeric rubric
with a FRESH no-cache client each time (llm_client populates its in-memory cache
even when cache_path is None, so one client would return the run-1 answer for
runs 2..K -> a new client per run is required to see the variance), and records
per run: the generated code, the recomputed numbers, and the resulting verdict.

Metrics per (case, rubric):
  * code_diversity     = #distinct normalized code strings / K
  * value_diversity    = #distinct recomputed number-sets / K
  * verdict_flip       = the defect flag (mismatch vs not) is NOT unanimous over K

Usage:
  python scripts/b2_nondeterminism.py \
      --ids 23 15 269 328 44 --k 10 --temp 0.0
  add --list to only print how many rubrics each case would run (no LLM calls).
"""
from __future__ import annotations

import argparse, importlib.util, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, LLMConfig, load_llm_config

# reuse the exact detector building blocks -- do NOT reimplement B2
_a = importlib.util.spec_from_file_location("aa", REPO / "scripts" / "auditor_agent.py")
A = importlib.util.module_from_spec(_a); _a.loader.exec_module(A)
l1 = A.l1
from benchcore.file_reader import read_file


def b2_rubrics(item):
    """The numeric rubrics exec_B2 would actually attempt (same pre-filter)."""
    out = []
    for r in item["rubrics"]:
        if re.search(A.STRUCT_PAT, r) or not re.search(r"\d", r):
            continue
        exp = l1.rubric_values(r)
        if exp:
            out.append((r, exp))
    return out


def b2_profile(item):
    """Identical to exec_B2's `profile` (absolute paths + 1000-char preview each)."""
    paths = "所有输入文件绝对路径(逐个读取):\n" + "\n".join(str(p) for p in item["inputs"])
    return paths + "\n\n" + "\n\n".join(
        f"路径: {p}\n" + read_file(p, 1000) for p in item["inputs"])


def norm_code(code: str) -> str:
    """Whitespace-insensitive code identity: same logic typed differently counts once."""
    return re.sub(r"\s+", " ", code).strip()


def one_run(profile, rubric, expected, cfg_base):
    """One full B2 pass with a FRESH client (empty cache). Mirrors exec_B2's inner
    body exactly, and returns the code + computed output + verdict for this run."""
    cfg = LLMConfig(**{**cfg_base.__dict__})
    cfg.cache_path = None                      # no persistence
    client = LLMClient(cfg)                     # fresh in-memory cache -> real resample
    try:
        code = client.chat_json(
            l1.PROMPT.replace("{inputs}", profile[:8000]).replace("{rubric}", rubric),
            "compute").get("code", "")
    except Exception as e:
        code = ""
    if "print" not in code:
        return {"code": code, "computed": "", "nums": [], "verdict": "no_code"}
    comp = l1.run_code(code)
    if "DATA_NOT_AVAILABLE" in comp:
        return {"code": code, "computed": comp[:160], "nums": [], "verdict": "data_absent"}
    if not re.search(r"=\s*-?[\d.]", comp):
        return {"code": code, "computed": comp[:160], "nums": [], "verdict": "no_compare"}
    got = l1.nums(comp)
    miss = [e for e in expected
            if not any(abs(v - g) <= max(1, abs(v) * 0.01)
                       for g in got for v in (e, e / 100, e * 100))]
    return {"code": code, "computed": comp[:160], "nums": sorted(round(x, 3) for x in got),
            "missing": miss, "verdict": "mismatch" if miss else "match"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", type=int, default=[23, 15, 269, 328, 44])
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--temp", type=float, default=0.0)
    ap.add_argument("--list", action="store_true", help="only list candidate rubric counts")
    ap.add_argument("--out", default="reports/b2_nondeterminism.json")
    args = ap.parse_args()

    cfg_base = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
    cfg_base.temperature = args.temp

    results = []
    for aid in args.ids:
        item = A.load_hf_item(aid)
        rubrics = b2_rubrics(item)
        print(f"\nid={aid}: {len(item['inputs'])} inputs, {len(rubrics)} B2-candidate rubrics"
              f"  (of {len(item['rubrics'])} total)")
        if args.list:
            for r, exp in rubrics:
                print(f"   exp={exp}  {r[:70]}")
            continue
        profile = b2_profile(item)
        for r, exp in rubrics:
            # the K runs are independent (each has its own fresh client + temp exec);
            # a small pool cuts wall time without changing what is measured.
            with ThreadPoolExecutor(max_workers=min(5, args.k)) as ex:
                runs = list(ex.map(lambda _: one_run(profile, r, exp, cfg_base), range(args.k)))
            codes = {norm_code(x["code"]) for x in runs}
            valsets = {tuple(x["nums"]) for x in runs}
            verdicts = [x["verdict"] for x in runs]
            n_flag = verdicts.count("mismatch")  # runs that fired a defect
            flip = 0 < n_flag < args.k
            rec = {"id": aid, "rubric": r, "expected": exp,
                   "K": args.k, "temp": args.temp,
                   "code_diversity": len(codes), "value_diversity": len(valsets),
                   "verdicts": verdicts, "n_mismatch": n_flag, "verdict_flip": flip,
                   "runs": runs}
            results.append(rec)
            vc = {v: verdicts.count(v) for v in sorted(set(verdicts))}
            print(f"   {'⚠FLIP' if flip else '  ok '} codes={len(codes)}/{args.k} "
                  f"valsets={len(valsets)}/{args.k} mismatch={n_flag}/{args.k} {vc}")
            print(f"        {r[:66]}")

    if not args.list:
        Path(REPO / args.out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        n_flip = sum(r["verdict_flip"] for r in results)
        print(f"\n=== {len(results)} rubrics | verdict-flip {n_flip}/{len(results)} "
              f"| wrote {args.out} ===")


if __name__ == "__main__":
    main()
