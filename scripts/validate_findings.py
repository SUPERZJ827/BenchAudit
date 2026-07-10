#!/usr/bin/env python3
"""Independent validation of our Workspace-Bench rubric findings.

A different model family (GPT-5.5 via OpenRouter) BLINDLY judges each rubric --
given the task and the input files' real column structure but NOT our verdict --
deciding whether the rubric is a fair, satisfiable grading criterion. We then
compare its "defective" calls against our flags:
  - agreement on OUR-flagged rubrics  -> precision proxy
  - false-alarm on a clean case (仓敏_5) -> calibration (is the judge conservative?)
"""
from __future__ import annotations

import collections, importlib.util, json, re, sys, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
_spec = importlib.util.spec_from_file_location("rdv", REPO / "scripts" / "rubric_data_verifier.py")
rdv = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(rdv)
from benchcore.llm_client import LLMClient, load_llm_config

JUDGE = """You are a strict, conservative benchmark reviewer. Given a TASK, the
INPUT FILES' columns, and one grading RUBRIC, decide whether the rubric is a fair
and satisfiable grading criterion. Be conservative: default to "fair".
Call it "defective" ONLY if clearly: the data it checks is NOT obtainable from the
inputs; OR it pins one specific answer for an open/subjective task (over-constrained);
OR it is brittle/unverifiable. Do not flag merely strict-but-reasonable checks.
Return ONLY JSON: {"verdict":"fair"|"defective","type":"data_not_available|over_constrained|brittle|other|none","reason":"one sentence"}"""


def input_cols(inputs):
    out = []
    for p in inputs:
        if p.suffix.lower() in (".xlsx", ".csv"):
            try:
                xl = pd.ExcelFile(p)
                for sh in xl.sheet_names[:2]:
                    df = xl.parse(sh, header=None, nrows=4)
                    out.append(f"{p.name} [{sh}] 行0-3:\n" + df.to_string(max_colwidth=12)[:600])
            except Exception:
                out.append(f"{p.name} (读取失败)")
        else:
            out.append(f"{p.name} (非表格: {p.suffix})")
    return "\n".join(out)[:3000]


def judge_case(name, client, our_flags):
    text = (REPO / "Workspace-Bench Case Learning.md").read_text(encoding="utf-8")
    block = rdv.case_block(text, name)
    task = (re.search(r"Task[:：](.*?)(?=\n###)", text.replace("\\", "").split(f"## {name}", 1)[-1], re.S) or [None, ""])
    task = task[1].strip() if hasattr(task, "__getitem__") else ""
    att = REPO / "图片和附件"
    inputs = [att / p for p in rdv.input_paths(block) if (att / p).exists()]
    cols = input_cols(inputs)
    rubrics = rdv.rubrics_of(block)
    res = []
    def one(i, r):
        u = f"TASK: {task[:600]}\n\nINPUT FILES (columns):\n{cols}\n\nRUBRIC: {r}"
        try:
            v = client.chat_json(JUDGE, u)
        except Exception as e:
            v = {"verdict": "error", "reason": str(e)}
        return i, r, v
    with ThreadPoolExecutor(max_workers=8) as pool:
        for fut in as_completed([pool.submit(one, i, r) for i, r in enumerate(rubrics)]):
            res.append(fut.result())
    return sorted(res), task


def main():
    cfg = load_llm_config(str(REPO / "configs/llm_openrouter_gpt55.json"))
    cfg.cache_path = "reports/validate_findings_cache.jsonl"
    client = LLMClient(cfg)

    # which rubric indices WE flagged high-confidence (from data-verify not_in_inputs/likely_wrong)
    def our_flagged(name):
        dv = REPO / f"reports/rubric_data_verify_{name}_20260630.json"
        flags = set()
        if dv.exists():
            data = json.loads(dv.read_text(encoding="utf-8"))
            for d in data:
                if d.get("verdict") in ("not_in_inputs", "likely_wrong"):
                    flags.add(rdv_clean(d["rubric"]))
        return flags

    overall = {}
    for name, role in [("仓敏_3", "我们标了缺陷"), ("仓敏_17", "我们标了缺陷"), ("仓敏_5", "干净case-校准")]:
        flagged_texts = our_flagged(name)
        res, _ = judge_case(name, client, flagged_texts)
        gpt_def = [r for i, r, v in res if v.get("verdict") == "defective"]
        # agreement: among rubrics WE flagged, did GPT-5.5 also call defective?
        our = [r for i, r, v in res if rdv_clean(r) in flagged_texts]
        agree = [r for r in our if r in gpt_def]
        print(f"\n===== {name}（{role}）=====")
        print(f"  rubric 总数 {len(res)} | 我们标缺陷 {len(our)} | GPT-5.5判缺陷 {len(gpt_def)}")
        if our:
            print(f"  我们标的里 GPT-5.5 也认同: {len(agree)}/{len(our)} = {len(agree)/len(our):.0%}")
        clean = [r for i, r, v in res if rdv_clean(r) not in flagged_texts]
        fa = [r for r in clean if r in gpt_def]
        if clean:
            print(f"  我们没标的里 GPT-5.5 判缺陷(误报率): {len(fa)}/{len(clean)} = {len(fa)/len(clean):.0%}")
        overall[name] = {"total": len(res), "our_flag": len(our), "agree": len(agree),
                         "clean": len(clean), "gpt_flag_clean": len(fa)}
        # show GPT-5.5's defective verdicts
        for i, r, v in res:
            if v.get("verdict") == "defective":
                mk = "✓我们也标了" if rdv_clean(r) in flagged_texts else "✗我们没标"
                print(f"    [GPT判缺陷·{mk}] {v.get('type')}: {r[:46]}")
    (REPO / "reports/validate_findings_20260630.json").write_text(
        json.dumps(overall, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote reports/validate_findings_20260630.json")


def rdv_clean(s):
    return re.sub(r"\\", "", str(s)).strip()


if __name__ == "__main__":
    main()
