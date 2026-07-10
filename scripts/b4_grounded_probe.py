#!/usr/bin/env python3
"""Probe: does a TASK+DATA-grounded B4 over-constraint judge beat the current task+rubric-only
B4? Current B4 flags leakage on a bare majority and can't tell id=13's task-derivable title (FP)
from its invented-theme title (TP), nor see that id=37's pinned conclusion is data-determined (FP).
The grounded judge gets the INPUT FILE previews and decides among task_specified / data_determined /
over_constrained -> leakage only for the last. We compare both on the discriminating cases. No prod change.

Run: /home/zhoujun/llmdata/.venv/bin/python scripts/b4_grounded_probe.py
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.file_reader import read_file

_a = importlib.util.spec_from_file_location("aa", REPO / "scripts" / "auditor_agent.py")
A = importlib.util.module_from_spec(_a); _a.loader.exec_module(A)

B4_GROUNDED = """Decide whether a grading RUBRIC OVER-CONSTRAINS an open deliverable. Judge it
against BOTH the TASK (what was actually asked) and the INPUT FILES (what the data determines).
- task_specified: the TASK explicitly asks for this exact result / deliverable / detail (this
  specific analysis, output value, field, name, title or structure). Pinning it is then fair. -> false
- data_determined: the pinned result is a FACT UNIQUELY DETERMINED by the input data -- exactly one
  correct answer is computable/derivable from the inputs (a count/total, which department has the
  highest KPI, which items meet a stated condition, a value present in a file). An objective outcome
  check, even if the value/list is spelled out. -> false
- over_constrained: the rubric pins a SPECIFIC analysis result, conclusion, recommendation, label,
  title or structure that (a) the TASK left OPEN -- it asked only for a generic report/analysis/
  suggestions, or did not mention this at all -- AND (b) is NOT uniquely determined by the data, so a
  correct agent could reasonably produce a different valid output. -> true
Rule of thumb: a rubric demanding a particular DERIVED analysis result is over_constrained UNLESS the
task explicitly asked for that result OR the data forces that one answer.
Return ONLY JSON {"verdict":"task_specified|data_determined|over_constrained","evidence":"one sentence: what the task did/didn't ask, or what the data determines"}.
TASK: {task}
INPUT FILES (name + preview):
{files}
RUBRIC: {rubric}"""

# (id, rubric#, gold_is_defect, note). gold=True => want leakage=True (over_constrained).
CASES = [
    (13, 3,  False, "FP: title = category name, task-derivable"),
    (13, 9,  False, "FP: content-presence 'such as'"),
    (13, 14, False, "FP: correctness 'no misplaced'"),
    (13, 11, True,  "TP: title = invented theme name"),
    (37, None, False, "FP-STABLE: pinned conclusion is DATA-DETERMINED"),
    (23, 11, True,  "TP: pinned specific issue analysis"),
    (23, 15, True,  "TP: pinned specific recommendation"),
    (35, 6,  True,  "TP: pinned permission not in task"),
    (107, None, True, "TP: pinned market recommendation"),
    (45, None, True,  "TP: pinned designed permission"),
]
SUBS = {37: "identified as strong departments", 107: "specific suggestions for market expansion",
        45: "cost accountant have edit"}


def files_view(item):
    names = " ".join(p.name for p in item["inputs"])
    return ("所有输入文件: " + names + "\n\n" + "\n\n".join(
        f"FILE {p.name}\n" + read_file(p, 1200) for p in item["inputs"]))[:12000]


def main():
    vote = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek_vote3.json")))
    items: dict[int, A.Item] = {}
    hits = {"old": 0, "new": 0}
    for cid, n, gold, note in CASES:
        if cid not in items:
            items[cid] = A.load_hf_item(cid)
        it = items[cid]
        r = it["rubrics"][n - 1] if n else [x for x in it["rubrics"] if SUBS[cid].lower() in x.lower()][0]
        # OLD B4 (task+rubric only)
        old = A.majority(vote.chat_json_multi(
            A.B4_JUDGE.replace("{task}", it["task"][:1200]).replace("{rubric}", r), "judge"), "leakage", False) is True
        # NEW grounded B4 (task + data + rubric)
        res = vote.chat_json_multi(
            B4_GROUNDED.replace("{task}", it["task"][:1200]).replace("{files}", files_view(it)).replace("{rubric}", r), "b4g")
        verdicts = [x.get("verdict") for x in res if isinstance(x, dict)]
        new = A.majority(res, "verdict", "task_specified") == "over_constrained"
        hits["old"] += (old == gold); hits["new"] += (new == gold)
        mark = lambda pred: "✅" if pred == gold else "❌"
        print(f"id={cid} #{n} gold={'DEF' if gold else 'ok '}  OLD leak={old}{mark(old)}  "
              f"NEW={('over' if new else 'ok  ')}{mark(new)}  {verdicts}  | {note}")
    n = len(CASES)
    print(f"\naccuracy on discriminating set:  OLD {hits['old']}/{n}   NEW {hits['new']}/{n}")


if __name__ == "__main__":
    main()
