#!/usr/bin/env python3
"""Task <-> input <-> rubric consistency & solvability auditor (case-level).

Audits the WHOLE benchmark item, not just rubrics:
  - solvability : can the task be completed from the given inputs, or is there a
                  fundamental data gap (task/rubrics need data the inputs lack)?
                  An unsolvable task is the most severe defect -- the item is broken.
  - task ambiguity : underspecified scope/convention/format (e.g. 公立 vs all hospitals).
  - three-way consistency : task<->inputs<->rubrics alignment (rubric checks something
                  the task never asked; task asks something no rubric covers; rubric/
                  task needs data not in inputs).
Reuses the input loader from rubric_data_verifier. Uses the cheap DeepSeek client.
"""
from __future__ import annotations

import importlib.util, json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
_spec = importlib.util.spec_from_file_location("rdv", REPO / "scripts" / "rubric_data_verifier.py")
rdv = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(rdv)
from benchcore.llm_client import LLMClient, load_llm_config

PROMPT = """You audit a whole agentic benchmark item: TASK + INPUT FILES + RUBRICS.
Find item-level defects beyond individual rubrics.

Check:
1. SOLVABILITY: can the task be completed from the given inputs? If the task or
   rubrics require data the inputs do not contain, the item is UNSOLVABLE
   (most severe -- the whole item is broken, not just one rubric).
2. TASK AMBIGUITY: underspecified scope/convention/format that changes the answer
   (e.g. "公立 hospitals" but totals are for all hospitals; region definition;
   rounding; output format/filename not stated).
3. CONSISTENCY: task<->inputs<->rubrics mismatches (a rubric checks something the
   task never asked; the task asks for something no rubric covers; task references
   a file not provided).

Return ONLY JSON:
{
 "solvability": "solvable" | "data_gap" | "uncertain",
 "missing_data": ["what is needed but absent from inputs"],
 "task_ambiguities": ["..."],
 "consistency_issues": [{"type":"task_rubric|task_input|task_self","detail":"..."}],
 "severity": "high"|"medium"|"low",
 "summary": "one sentence"
}

TASK:
{task}

INPUT FILES (structure + preview):
{inputs}

RUBRICS:
{rubrics}"""


def extract_task(block):
    m = re.search(r"Task[:：](.*?)(?=\n### |\n#### )", block, re.S)
    return rdv_clean(m.group(1)) if m else ""


def rdv_clean(s):
    return re.sub(r"\\", "", s).strip()


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "仓敏_3"
    text = (REPO / "Workspace-Bench Case Learning.md").read_text(encoding="utf-8")
    block = rdv.case_block(text, name)
    task = extract_task(text.replace("\\", "").split(f"## {name}", 1)[-1].split("\n## 仓敏", 1)[0])
    att = REPO / "图片和附件"
    xlsx = [att / p for p in rdv.input_paths(block) if p.lower().endswith(".xlsx") and (att / p).exists()]
    rubrics = rdv.rubrics_of(block)
    profiles = "\n\n".join(rdv.profile_xlsx(p) for p in xlsx) if xlsx else "(无 xlsx 输入或为 PDF/PPT/DOCX)"
    rub_str = "\n".join(f"- {r}" for r in rubrics)

    cfg = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
    cfg.cache_path = "reports/task_consistency_cache.jsonl"
    client = LLMClient(cfg)
    p = (PROMPT.replace("{task}", task[:1200] or "(任务描述缺失)")
               .replace("{inputs}", profiles[:9000]).replace("{rubrics}", rub_str[:3500]))
    try:
        res = client.chat_json(p, "Audit this item.")
    except Exception as e:
        res = {"summary": f"error: {e}"}

    print(f"===== {name} =====")
    print(f"任务: {task[:120] or '(缺失)'}")
    print(f"输入 xlsx: {[x.name for x in xlsx] or '无'}")
    print(f"\n🔎 SOLVABILITY: {res.get('solvability')}  (severity={res.get('severity')})")
    for m in res.get("missing_data", []):
        print(f"   🔴 缺数据: {m}")
    for a in res.get("task_ambiguities", []):
        print(f"   🟡 任务歧义: {a}")
    for c in res.get("consistency_issues", []):
        print(f"   🟠 [{c.get('type')}] {c.get('detail')}")
    print(f"\n总评: {res.get('summary')}")
    (REPO / f"reports/task_consistency_{name}_20260630.json").write_text(
        json.dumps({"task": task, "inputs": [x.name for x in xlsx], **res}, ensure_ascii=False, indent=2),
        encoding="utf-8")


if __name__ == "__main__":
    main()
