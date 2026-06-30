#!/usr/bin/env python3
"""LLM semantic auditor for human-defined rubric sets (Direction #1).

Audits the TASK + RUBRIC set of an agentic benchmark for *semantic* defects that
cross-model pass-rate mining cannot catch:
  - over_constrained : an open/subjective task pinned to one author answer
  - answer_leakage   : rubric reveals a conclusion the agent was meant to derive
  - unverifiable     : vague/subjective rubric a grader can't judge consistently
  - brittle          : exact value/threshold/name that a correct answer could fail
  - coverage_gap     : task requirement not checked, or rubric checks unasked things
  - task_rubric_mismatch : rubric assumes a definition the task never states
Operates on text only (no input files). Reuses the DeepSeek client.
"""
from __future__ import annotations

import json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

PROMPT = """You audit the QUALITY of a benchmark task's grading rubrics.

FIRST decide the task type:
- DETERMINISTIC: the answer is computed/extracted from data and is unique
  (e.g. "compute totals from these files"). For these, a rubric that states an
  expected value/number is NORMAL grading -- do NOT flag it as answer_leakage or
  over_constrained. Only flag brittle / unverifiable / coverage_gap /
  task_rubric_mismatch (e.g. value needs data not in inputs, or exact sheet name
  not required by the task).
- SUBJECTIVE/OPEN: the task asks for judgement/analysis/recommendations
  (e.g. "which company is most promising", "suggest improvements"). For these, a
  rubric pinning one specific answer/score/suggestion IS over_constrained /
  answer_leakage.

Then find rubrics that are defective as grading criteria. Defect types:
- over_constrained: the task is open-ended/subjective but the rubric pins a single
  author-chosen answer/score/suggestion, penalizing valid alternatives.
- answer_leakage: the rubric states a conclusion the agent was supposed to derive.
- unverifiable: vague/subjective ("reasonable", "no fabrication") -> inconsistent grading.
- brittle: exact value/threshold/filename/sheet-name a correct answer could fail on
  (e.g. ">52.68%" at the exact value, exact worksheet name not required by task).
- coverage_gap: rubric checks something the task never asked, or a task requirement
  has no rubric.
- task_rubric_mismatch: rubric assumes a definition/scope the task never specifies.

Be conservative; only flag real issues. Return ONLY JSON:
{"issues":[{"rubric_index":<int or -1 for set-level>,"defect_type":"...",
            "severity":"high"|"medium"|"low","reason":"one sentence"}],
 "summary":"one sentence on the rubric set's overall quality"}

TASK:
{task}

RUBRICS (index: text):
{rubrics}"""


def parse_cases(text: str):
    out = []
    for m in re.finditer(r"\n## ([一-鿿]{2,5}\\?_\d[^\n]*)(.*?)(?=\n## [一-鿿]{2,5}\\?_\d|\Z)", text, re.S):
        name = re.sub(r"\\", "", m.group(1)).strip()
        body = m.group(2)
        tm = re.search(r"Task[:：](.*?)(?=\n###|\n输入|\n#### )", body, re.S)
        task = re.sub(r"\\", "", tm.group(1)).strip() if tm else ""
        rm = re.search(r"### Rubrics(.*?)(?=\n### |\n#### |\Z)", body, re.S)
        rubrics = []
        if rm:
            for q in re.findall(r'"((?:[^"\\]|\\.)*)"', rm.group(1)):
                q = re.sub(r"\\(.)", r"\1", q).strip()
                if len(q) > 8:
                    rubrics.append(q)
        if task and rubrics:
            out.append((name, task, rubrics))
    return out


def main():
    text = (REPO / "Workspace-Bench Case Learning.md").read_text(encoding="utf-8")
    cases = parse_cases(text)
    cfg = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
    cfg.cache_path = "reports/rubric_semantic_cache.jsonl"
    client = LLMClient(cfg)

    md = ["# Workspace-Bench rubric 语义审计(LLM)\n",
          "> 针对**任务↔rubric**的语义缺陷(过度约束/答案泄漏/不可验/脆弱/覆盖/口径不符),只看文本。\n"]
    allres = {}
    for name, task, rubrics in cases:
        rub_str = "\n".join(f"{i}: {r}" for i, r in enumerate(rubrics))
        try:
            res = client.chat_json(PROMPT.replace("{task}", task[:1500]).replace("{rubrics}", rub_str[:4000]),
                                   "Audit these rubrics.")
        except Exception as e:
            res = {"issues": [], "summary": f"error: {e}"}
        allres[name] = res
        issues = res.get("issues", [])
        md.append(f"\n## {name}（{len(rubrics)} 条 rubric,发现 {len(issues)} 个语义问题）")
        md.append(f"- 总评: {res.get('summary','')}")
        for it in sorted(issues, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity"), 3)):
            idx = it.get("rubric_index")
            rt = rubrics[idx][:80] if isinstance(idx, int) and 0 <= idx < len(rubrics) else "(整套)"
            md.append(f"  - **[{it.get('severity')}] {it.get('defect_type')}** (#{idx}): {it.get('reason')}")
            md.append(f"      rubric: {rt}")
        print(f"{name}: {len(rubrics)} rubrics -> {len(issues)} semantic issues")
    (REPO / "reports/rubric_semantic_audit_20260630.md").write_text("\n".join(md), encoding="utf-8")
    (REPO / "reports/rubric_semantic_audit_20260630.json").write_text(
        json.dumps(allres, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote reports/rubric_semantic_audit_20260630.{md,json}")


if __name__ == "__main__":
    main()
