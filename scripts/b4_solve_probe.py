#!/usr/bin/env python3
"""Differential-solve probe for over-constraint (B4). Instead of JUDGING whether a rubric is
over-constrained (subjective, boundary-flippy), MEASURE it: K independent solvers answer the
rubric's underlying question WITHOUT seeing the rubric; we then check what fraction of those
independent-correct solutions satisfy the rubric. A rubric that correct solutions mostly FAIL
is over-constrained (it pinned a free choice); one they mostly satisfy is task/data-determined.
No gold output needed -- the disagreement among competent solves is the signal.

Pipeline per (task, rubric): de-leak rubric -> neutral question; K fresh no-cache temp-0.7 solves
(real resampling); LLM satisfies-check each solve vs the original rubric; satisfy_rate = frac.
Predict over_constrained (defect) iff satisfy_rate <= 0.5.

Run: /home/zhoujun/llmdata/.venv/bin/python scripts/b4_solve_probe.py
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, LLMConfig, load_llm_config
from benchcore.file_reader import read_file

_a = importlib.util.spec_from_file_location("aa", REPO / "scripts" / "auditor_agent.py")
A = importlib.util.module_from_spec(_a); _a.loader.exec_module(A)

K = 5
DELEAK = """Given a TASK and one grading RUBRIC, restate the OPEN QUESTION the rubric is testing about
the deliverable, WITHOUT revealing the specific answer / choice / value / label the rubric pins.
E.g. rubric "does it recommend a safe-stock warning system?" -> "what improvements should the report
recommend?"; rubric "are HR and Finance the strong departments?" -> "which departments are strong?".
Return ONLY JSON {"question":"..."}.
TASK: {task}
RUBRIC: {rubric}"""

SOLVE = """You are completing this task using ONLY the input files. Answer this ONE question about
your deliverable, concretely and specifically (name the actual values/items/choices you would put in
the output). Do not hedge. Return ONLY JSON {"answer":"..."}.
TASK: {task}
INPUT FILES (name + preview):
{files}
QUESTION: {question}"""

SATISFY = """An independent solver who did NOT see the grading rubric produced the ANSWER below.
Does the ANSWER satisfy the RUBRIC (same specific value / choice / conclusion the rubric requires)?
Return ONLY JSON {"satisfied":true|false}.
RUBRIC: {rubric}
ANSWER: {answer}"""

# (id, rubric#, gold_defect=over_constrained?, note)
CASES = [
    (37, None, False, "data-determined conclusion (NOT over-constraint)"),
    (33, 1,    False, "objective value 15,102 (NOT over-constraint)"),
    (13, 3,    False, "task-derivable title (labeled ok)"),
    (13, 11,   True,  "invented-theme title (over-constraint)"),
    (23, 11,   True,  "pinned specific issue analysis"),
    (23, 15,   True,  "pinned specific recommendation"),
    (35, 6,    True,  "pinned permission not in task"),
    (107, None, True, "pinned market recommendation"),
    (45, None,  True, "pinned designed permission"),
]
SUBS = {37: "identified as strong departments", 107: "specific suggestions for market expansion",
        45: "cost accountant have edit"}


def files_view(item):
    names = " ".join(p.name for p in item["inputs"])
    return ("所有输入文件: " + names + "\n\n" + "\n\n".join(
        f"FILE {p.name}\n" + read_file(p, 1000) for p in item["inputs"]))[:11000]


def fresh_solver():
    cfg = LLMConfig(**load_llm_config(str(REPO / "configs/llm_deepseek.json")).__dict__)
    cfg.temperature = 0.7          # diversity across independent solves
    cfg.cache_path = None          # fresh client per solve -> real resample (see b2_nondeterminism)
    return LLMClient(cfg)


def main():
    judge = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek.json")))  # temp0, cached
    items: dict[int, A.Item] = {}
    hits = 0
    for cid, n, gold, note in CASES:
        if cid not in items:
            items[cid] = A.load_hf_item(cid)
        it = items[cid]
        r = it["rubrics"][n - 1] if n else [x for x in it["rubrics"] if SUBS[cid].lower() in x.lower()][0]
        fv = files_view(it)
        q = judge.chat_json(DELEAK.replace("{task}", it["task"][:1200]).replace("{rubric}", r), "deleak").get("question", "")
        sats, answers = [], []
        for _ in range(K):
            ans = fresh_solver().chat_json(
                SOLVE.replace("{task}", it["task"][:1200]).replace("{files}", fv).replace("{question}", q), "solve").get("answer", "")
            answers.append(ans)
            ok = judge.chat_json(SATISFY.replace("{rubric}", r).replace("{answer}", ans[:600]), "sat").get("satisfied") is True
            sats.append(ok)
        rate = sum(sats) / K
        pred_defect = rate <= 0.5
        ok = pred_defect == gold
        hits += ok
        print(f"{'✅' if ok else '❌'} id={cid} #{n}  gold={'OVER' if gold else 'ok  '}  "
              f"satisfy_rate={rate:.1f} ({sum(sats)}/{K}) -> pred={'OVER' if pred_defect else 'ok'}  | {note}")
        print(f"      Q: {q[:88]}")
        for a in answers:
            print(f"        - {a[:88]}")
    print(f"\naccuracy: {hits}/{len(CASES)}   (predict over-constrained iff <=50% of independent solves satisfy the rubric)")


if __name__ == "__main__":
    main()
