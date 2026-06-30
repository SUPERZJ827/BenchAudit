#!/usr/bin/env python3
"""Data-grounded rubric verifier (Direction #2).

For agentic data tasks whose inputs are spreadsheets, this loads the ACTUAL input
files' structure (sheets + header rows + sample rows) and asks an LLM to judge,
for each value/numeric rubric, whether its asserted value is derivable from the
inputs and looks correct. Catches "rubric requires data not in the inputs" and
"rubric value inconsistent with the source" -- e.g. 仓敏_3 hospital-level rubrics.

More robust than code-generation-then-execute for messy multi-sheet Excel, and
covers all rubric kinds. Uses the cheap DeepSeek client.
"""
from __future__ import annotations

import json, re, sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

PROMPT = """You verify whether a benchmark rubric's claim is supported by the
provided INPUT FILES. You are given each input spreadsheet's sheets and a preview
of rows. Decide if the rubric's asserted value/fact can be derived from these
inputs and appears correct.

Verdicts:
- verifiable_ok: the data needed is present and the asserted value is consistent
  with it (or clearly derivable).
- not_in_inputs: the data needed to check this rubric is NOT present in the inputs
  (e.g. asks for a breakdown the files do not contain).
- likely_wrong: the data is present but the asserted value contradicts it.
- uncertain: cannot tell from the preview.

Return ONLY JSON: {"verdict":"...","reason":"one sentence citing the file/column"}

INPUT FILES (structure + preview):
{inputs}

RUBRIC: {rubric}"""


def case_block(text, name):
    m = re.search(rf"\n## {re.escape(name)}(.*?)(?=\n## [一-鿿]{{2,5}}_\d|\Z)", text.replace("\\", ""), re.S)
    return m.group(1) if m else ""


def input_paths(block):
    from urllib.parse import unquote
    # only look inside the 输入 section, not later model-run sections (which link outputs)
    m = re.search(r"### 输入(.*?)(?=\n### |\Z)", block, re.S)
    seg = m.group(1) if m else ""
    return [unquote(p) for p in re.findall(r"\]\(图片和附件/([^)]+)\)", seg)]


def rubrics_of(block):
    rm = re.search(r"### Rubrics(.*?)(?=\n### |\Z)", block, re.S)
    if not rm:
        return []
    out = []
    for q in re.findall(r'"([^"]{8,})"', rm.group(1)):
        out.append(q.strip())
    return out


def profile_xlsx(path: Path, max_rows=12) -> str:
    try:
        xl = pd.ExcelFile(path)
    except Exception as e:
        return f"[{path.name}] (无法读取: {e})"
    parts = [f"FILE: {path.name}  sheets={xl.sheet_names}"]
    for sh in xl.sheet_names[:2]:
        df = xl.parse(sh, header=None, nrows=max_rows)
        parts.append(f"-- sheet '{sh}' (前{max_rows}行, 全部列) --\n" + df.to_string(max_colwidth=12)[:4000])
    return "\n".join(parts)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "仓敏_3"
    text = (REPO / "Workspace-Bench Case Learning.md").read_text(encoding="utf-8")
    block = case_block(text, name)
    att = REPO / "图片和附件"
    xlsx = [att / p for p in input_paths(block) if p.lower().endswith(".xlsx") and (att / p).exists()]
    rubrics = rubrics_of(block)
    if not xlsx:
        print(f"{name}: 无 xlsx 输入,跳过"); return
    profiles = "\n\n".join(profile_xlsx(p) for p in xlsx)
    cfg = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
    cfg.cache_path = "reports/rubric_data_verify_cache.jsonl"
    client = LLMClient(cfg)

    numeric = [r for r in rubrics if re.search(r"\d", r) and not re.search(r"工作表|文件名|sheet|命名|包含名为|结构|格式", r)]
    print(f"{name}: {len(xlsx)} xlsx 输入, {len(rubrics)} rubric, 核验其中 {len(numeric)} 条数值类\n")
    rows = []
    for r in numeric:
        try:
            res = client.chat_json(PROMPT.replace("{inputs}", profiles[:10000]).replace("{rubric}", r), "Verify.")
        except Exception as e:
            res = {"verdict": "error", "reason": str(e)}
        rows.append((r, res))
        v = res.get("verdict", "?")
        mark = {"verifiable_ok": "✅", "not_in_inputs": "🔴", "likely_wrong": "🔴", "uncertain": "⚪"}.get(v, "?")
        print(f"  {mark} [{v}] {r[:60]}")
        if v in ("not_in_inputs", "likely_wrong"):
            print(f"       └ {res.get('reason','')[:120]}")
    out = REPO / f"reports/rubric_data_verify_{name.replace('/','_')}_20260630.json"
    out.write_text(json.dumps([{"rubric": r, **res} for r, res in rows], ensure_ascii=False, indent=2), encoding="utf-8")
    import collections
    tally = collections.Counter(res.get("verdict") for _, res in rows)
    print(f"\n{name} 汇总: {dict(tally)} -> {out.name}")


if __name__ == "__main__":
    main()
