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

    numeric = [r for r in rubrics if re.search(r"\d", r) and not re.search(r"工作表|文件名|sheet|命名|包含名为|格式", r)]
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
        exp = nums(r)
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
