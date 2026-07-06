#!/usr/bin/env python3
"""Automated L1 data-correctness verifier (general).

For each numeric rubric, an LLM writes pandas code that RE-COMPUTES the asserted
quantity from the real input files; we execute it and check whether every number
the rubric asserts is reproduced by the computation. Objective (computed, not
judged), layout-robust, and catches wrong values + values whose data is absent.
Reuses the DeepSeek client; reads inputs via file_reader for the structure preview.
"""
from __future__ import annotations

import importlib.util, json, re, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
_spec = importlib.util.spec_from_file_location("rdv", REPO / "scripts" / "rubric_data_verifier.py")
rdv = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(rdv)
from benchcore.file_reader import read_file
from benchcore.llm_client import LLMClient, load_llm_config

PROMPT = """Write Python (pandas as pd) that RE-COMPUTES, from the input files, the
quantities the rubric asserts, and prints each as `label=value`. Read files by the
absolute paths given. If the data needed is NOT in the inputs, print
`DATA_NOT_AVAILABLE` and nothing else. Do not trust the rubric's numbers; compute
independently.

Return ONLY JSON: {"code": "<python that prints label=value lines>"}

INPUT FILES (absolute paths + structure preview):
{inputs}

RUBRIC: {rubric}"""


def run_code(code: str, timeout=15):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("import pandas as pd, numpy as np, warnings\nwarnings.filterwarnings('ignore')\n" + code)
        p = f.name
    try:
        r = subprocess.run([sys.executable, p], capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip() or (r.stderr or "")[-200:]
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    finally:
        Path(p).unlink(missing_ok=True)


def nums(s):
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", s.replace(",", ""))]


def rubric_values(s):
    """Extract only the SUBSTANTIVE numeric claims from a rubric, dropping the numbers
    that are identifiers / indices / years / filename digits / THRESHOLDS -- nums() treats
    those as 'expected values' and produces false B2 mismatches (Partner 3, item 14, PO
    #1013, SR-021, DES-06, year 2024, '4-financial-table.xlsx', the '50' in 'discount
    >=50%'). Keeps real counts/sums/figures."""
    t = s
    t = re.sub(r'\b[\w\-./]+\.(?:xlsx|xls|csv|txt|docx?|pdf|md|py|json|pptx?|png|html?)\b', ' ', t, flags=re.I)  # filenames
    # inequality / threshold numbers ('>=50%', 'at least 3', 'top 10%') are FILTER conditions,
    # not asserted results -- a recompute reproduces the asserted value, never the threshold.
    t = re.sub(r'(?:≥|≤|>=|<=|>|<|至少|至多|不少于|不超过|不低于|不高于|大于|小于|超过|低于|高于|'
               r'at least|at most|no (?:less|more) than|not (?:less|more) than|greater than|'
               r'less than|more than|over|above|below|up to|within|between)\s*[¥$]?\s*\d[\d,]*\.?\d*\s*%?',
               ' ', t, flags=re.I)
    t = re.sub(r'\b\d[\d,]*\.?\d*\s*%?\s*(?:-|to|~|–|—|至|到)\s*\d[\d,]*\.?\d*\s*%', ' ', t)  # ranges '35%-45%'
    t = re.sub(r'\b[A-Za-z]{1,}[-_]?\d[\w-]*', ' ', t)      # SR-021, DES-06, DEV-0108, PO-2024-019, W42, P4, A4
    t = re.sub(r'#\s*\d+', ' ', t)                          # #1013
    t = re.sub(r'\b(?:item|items|partner|chapter|page|pages|top|no|number|question|article|'
               r'figure|fig|table|slide|part|day|days|month|months|week|weeks|step|point|'
               r'grades?|level|priority|section|row|column|col|q|dev|proj)\.?\s*#?\s*\d+',
               ' ', t, flags=re.I)                          # ordinal/index words + number
    t = re.sub(r'第\s*\d+\s*(?:个|条|项|章|页|位|名|列|行|款|季度|周|天|月)?', ' ', t)
    t = re.sub(r'序号\s*\d+', ' ', t)
    # Chinese calendar tokens: '2024年' (the English \b year rule fails before 年, a word char),
    # month/day indices '1月' '01月' '15日' -- calendar references, never asserted results.
    # '12个月' (a duration) keeps its number: the 个 blocks the N月 match.
    t = re.sub(r'(?:19|20)\d{2}\s*年', ' ', t)
    t = re.sub(r'\d{1,2}\s*[月日号]', ' ', t)
    t = re.sub(r'\b(?:19|20)\d{2}\b', ' ', t)               # standalone years
    return nums(t)


def reproduced(expected, computed_out):
    """Each expected number must appear (within 0.5% or ±1) in the computed output."""
    got = nums(computed_out)
    miss = []
    for e in expected:
        if not any(abs(e - g) <= max(1, abs(e) * 0.005) for g in got):
            miss.append(e)
    return miss


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "仓敏_5"
    text = (REPO / "Workspace-Bench Case Learning.md").read_text(encoding="utf-8")
    block = rdv.case_block(text, name)
    att = REPO / "图片和附件"
    inputs = [att / p for p in rdv.input_paths(block) if (att / p).exists() and p.lower().endswith((".xlsx", ".csv"))]
    rubrics = rdv.rubrics_of(block)
    if not inputs:
        print(f"{name}: 无 xlsx/csv 输入,L1 跳过"); return
    profile = "\n\n".join(f"路径: {p}\n" + read_file(p, 1200) for p in inputs)
    cfg = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
    cfg.cache_path = "reports/output_l1_cache.jsonl"
    client = LLMClient(cfg)

    # only rubrics that ASSERT a substantive numeric value are recomputable; rubric_values()
    # drops identifiers/thresholds/years/filenames so those never trigger a B2 recompute.
    numeric = [r for r in rubrics
               if rubric_values(r) and not re.search(r"工作表|文件名|sheet|命名|包含名为|格式", r)]
    print(f"{name}: {len(inputs)} 输入文件, 核验 {len(numeric)} 条数值 rubric\n")
    tally = {"✅一致": 0, "🔴不符": 0, "🔴数据缺失": 0, "⚠️无法核验": 0}
    out = []
    for r in numeric:
        try:
            g = client.chat_json(PROMPT.replace("{inputs}", profile[:8000]).replace("{rubric}", r), "compute")
            code = g.get("code", "")
        except Exception as e:
            code = ""
        comp = run_code(code) if "print" in code else ""
        exp = rubric_values(r)
        if "DATA_NOT_AVAILABLE" in comp:
            verdict = "🔴数据缺失"
        elif not comp or "Error" in comp or "Traceback" in comp or "TIMEOUT" in comp:
            verdict = "⚠️无法核验"
        else:
            miss = reproduced(exp, comp)
            verdict = "✅一致" if not miss else "🔴不符"
        tally[verdict] += 1
        out.append({"rubric": r, "verdict": verdict, "computed": comp[:160], "code": code})
        print(f"  {verdict}  {r[:52]}")
        if verdict in ("🔴不符",):
            print(f"        重算输出: {comp[:120]}")
        elif verdict == "🔴数据缺失":
            print(f"        → 输入里没有该 rubric 所需数据")
    print(f"\n{name} L1 汇总: {tally}")
    (REPO / f"reports/output_l1_{name}_20260630.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
