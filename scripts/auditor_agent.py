#!/usr/bin/env python3
"""Thin plan-exec-eval orchestrator for benchmark defect auditing.

A constrained "agent": an LLM PLANS what to check (task_type gate + which
detectors apply), the orchestrator EXECUTES the matched detectors (deterministic
where possible, semantic only where irreducible), then EVALUATES with a gate that
turns candidates into confirmed findings only with evidence.

Design constraints baked in (all learned the hard way):
  * MUST run with the project venv:  /home/zhoujun/llmdata/.venv/bin/python
    (system python lacks openpyxl/pdfplumber/... -> file reads crash)
  * B1 field-existence uses header=None + full-content search, NOT df.columns
    (WB sheets have multi-row headers; df.columns returns 'Unnamed: *')
  * task_type and semantic (T3) judgments use majority voting (multi-run mode),
    because a single LLM pass is not reproducible.

Validates the chain on two known cases:
  仓敏_3  -> B1 (input data missing for grade rubrics)   [deterministic]
  id=244  -> B4 (answer leakage in rubric)               [semantic + vote]
"""
from __future__ import annotations

import importlib.util, json, re, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

_s = importlib.util.spec_from_file_location("rdv", REPO / "scripts" / "rubric_data_verifier.py")
rdv = importlib.util.module_from_spec(_s); _s.loader.exec_module(rdv)
_l = importlib.util.spec_from_file_location("l1", REPO / "scripts" / "output_l1_verifier.py")
l1 = importlib.util.module_from_spec(_l); _l.loader.exec_module(l1)

# rubrics that check the OUTPUT file's shape (name/sheet/format), not input data
STRUCT_PAT = r"工作表|sheet|命名|文件名|格式|结构|包含名为|目录"

DERIVE_WORDS_ZH = ["识别", "分析", "发现", "判断", "建议", "评估", "找出", "总结", "洞察", "原因", "复盘"]
DERIVE_WORDS_EN = ["analy", "identif", "derive", "discover", "recommend", "suggest",
                   "assess", "evaluat", "insight", "root cause", "review", "diagnos", "point out"]
# generic suffixes stripped from LLM-extracted terms before presence search, so a
# paraphrase like '社区卫生服务中心数量' still matches the input's '社区卫生服务中心'
GENERIC = ["数量", "总数", "家数", "名称", "情况", "明细", "信息", "统计", "分布", "数据", "数", "表", "值"]

# B2 recompute is LLM-written and NOT reproducible (measured: 9.4/10 distinct code,
# 40% verdict flip at temp 0 -- reports/b2_nondeterminism.md). So B2 flags ONLY when a
# strong majority of independent code samples agree on a value that disagrees with the
# rubric under a TIGHT tolerance. B2_CONSENSUS = required agreement fraction; the tight
# tolerance replaces the old +/-1 (which absorbed the real 6-vs-7 defect in id=23).
B2_CONSENSUS = 0.8
B2_TOL_ABS, B2_TOL_REL = 0.5, 0.005
# rubrics B2 should NOT try to recompute even though they carry a number: OUTPUT-artifact
# properties (a produced file's byte size) and TRANSCRIPTION-accuracy checks (does the output
# faithfully copy the source, "X rather than Y" example values). Their numbers aren't
# aggregates of input DATA, so a recompute 'mismatch' is a false positive (broad scan: id=131
# file-size, id=227/276 transcription). B1 already guards transcription; B2 did not.
B2_SKIP_PAT = (r"file size|文件大小|\d\s*(?:bytes|字节)\b|rather than|exactly match|"
               r"match the source|accurately (?:extract|transcrib|record)|without omission")


def is_derive_task(task):
    t = task.lower()
    return any(w in task for w in DERIVE_WORDS_ZH) or any(w in t for w in DERIVE_WORDS_EN)


def core_term(t):
    """Strip trailing generic suffixes so presence search is concept-level."""
    t = norm(t)
    changed = True
    while changed:
        changed = False
        for g in GENERIC:
            if t.endswith(g) and len(t) > len(g) + 1:
                t = t[: -len(g)]; changed = True
    return t

CLASSIFY = """Decide the task type.
DETERMINISTIC: has a unique computable/extractable answer.
SUBJECTIVE: asks for judgement / analysis / recommendations.
Return ONLY JSON {"task_type":"deterministic|subjective"}.
TASK: {task}"""

B1_EXTRACT = """Name the core DATA DIMENSION / CATEGORY / COLUMN this rubric needs to EXIST
in the input files for it to be checkable (e.g. a category or level like 'tertiary
hospital'/'三级医院', 'gender'/'性别', 'department'/'部门'). Return ONLY JSON
{"required":[...]} with 1-3 short NOUN terms IN THE SAME LANGUAGE AS THE RUBRIC, naming
the dimension/category. Do NOT include generic DESCRIPTOR words (count/total/number/data/
name/person/source/content/status/size/filename/数量/总数/名称/数据/负责人/来源/内容/状态/
文件名); do NOT include region or proper names.
Return EMPTY [] if the rubric is a TRANSCRIPTION / EXTRACTION-ACCURACY check -- it asks
whether the output RECORDS / lists / accurately states a specific value or fact already
present in the inputs (e.g. "is it recorded that X updated Y", "is the work content
accurately 'Z'", "does the file size equal N"); those verify faithful copying, not the
EXISTENCE of a data dimension. Empty list if it needs no specific field.
RUBRIC: {rubric}"""

B4_JUDGE = """A rubric OVER-CONSTRAINS an open deliverable (the defect) ONLY if it pins a
SUBJECTIVE JUDGEMENT or CHOICE that a correct-but-different output could reasonably fail:
a specific recommendation, a chosen priority/framing, or a particular qualitative
conclusion the agent was free to reach differently.
A rubric that states a COMPUTED FACT or value derivable from the input data -- a count, a
sum, a total, which items meet a condition, a specific figure/date -- is a NORMAL objective
outcome check and is NOT a defect, EVEN IF the exact value or list is spelled out. Objective
benchmarks are supposed to state expected values.
So: pinned recommendation / opinion / chosen narrative -> leakage=true; stated computable
fact/number -> leakage=false.
Return ONLY JSON {"leakage":true|false,"evidence":"the pinned subjective choice, or empty"}.
TASK: {task}
RUBRIC: {rubric}"""

# Semantic escalation for B1: a literal keyword search failed, but the data may
# still be PRESENT under a different name or DERIVABLE by computation. The agent
# must reason over the actual input content, not give up because the exact string
# is absent (e.g. 有床数 = 总计 - 无床数; '中心_无床' == the bed-breakdown of
# 社区卫生服务中心, which IS in the sheets). Only a genuine absence is a defect.
B1_VERIFY = """A rubric mentions terms a literal keyword search did NOT find verbatim in
the input files: {missing}. A literal miss is NOT a defect by itself -- the terms are often
a DESCRIPTOR of what the OUTPUT produces, content EXTRACTABLE from the inputs under other
wording, or a value that is DERIVABLE. Using the TASK, the INPUT FILES (names + schema/
preview) and the SEARCH HITS below, decide which case this is:
- present_or_derivable: pick this if ANY of these holds --
  (a) FILE PROPERTY: the rubric checks a MECHANICAL property of the produced file -- its
      byte/KB size, its filename, that it exists in a folder, or that its report has a named
      section/heading. These depend only on the agent producing the file, not on any input
      DATA value, so they are always satisfiable. (This does NOT cover a rubric asking the
      output to CONTAIN a specific DATA VALUE or breakdown -- judge those by (b)/(c) below.)
  (b) EXTRACTABLE / PRESENT: the entity, value or content EXISTS in the inputs (possibly in
      a file whose NAME matches, under different wording, or spread across files) and the
      rubric is really checking that the output faithfully TRANSCRIBES / EXTRACTS / copies
      it -- a work item, a person, a date, an order number, a chat author, a field value.
      If the raw item plausibly lives in an input (e.g. a weekly-plan sheet holds the week's
      work items), treat it as present_or_derivable even if the literal descriptor did not
      match; it can be read, copied or summarized.
  (c) DERIVABLE: the value is computable from input data (有床数 = 总计 - 无床数), or the
      rubric merely pins a COUNT / TOTAL of items that DO exist -> that number is a VALUE for
      recompute (B2's job), NOT a missing dimension. You cannot count all rows from a short
      preview, so never call a count absent just because one file's preview shows fewer.
- generated_content: the rubric checks content the agent must PRODUCE from its own
  judgement -- recommendations, suggestions, opinions, narrative analysis, OR a scheme the
  agent DESIGNS as the deliverable (roles/permissions, a sensitivity classification, a
  policy/plan) when the task asks to design/define/formulate it. The inputs are the SUBJECT
  being analysed, not a lookup table holding the answer, so absence from them is expected.
  A COUNT / SUM / RATE is NOT generated_content: it is input-grounded even if the agent computes it.
- not_in_inputs: pick this ONLY if producing the answer REQUIRES a SOURCE data dimension /
  column / named item that the agent must READ FROM the inputs, and it is genuinely ABSENT
  from every file -- e.g. the rubric wants counts BY hospital GRADE but no file has any grade
  column (so 三级/二级/一级 counts cannot be produced at all), or a named dependency 'h2'
  appears in no file. A missing SOURCE dimension cannot be supplied by unseen rows, by
  summing, by extraction, or by the agent's own writing. This is about a source THING being
  absent -- NOT about an output property, extractable content, or a pinned count differing.
Do not rely on exact string matching; reason about meaning, FILENAMES, and derivability.
Note: the preview shows each file's COLUMN STRUCTURE / headers even though not all data ROWS
are shown. So never call a specific VALUE or COUNT missing (unseen rows may hold it); BUT a
DIMENSION / breakdown category IS missing when NO column, header or field in ANY file
provides it. Do NOT assume such a column "is probably in the unseen data" -- if the rubric
needs a breakdown BY a category (e.g. hospital GRADE) and no file shows any grade column,
the breakdown cannot be produced -> not_in_inputs. And do not call an entity missing if a
file is NAMED for it or a column lists it as a value.
Return ONLY JSON {"verdict":"present_or_derivable|generated_content|not_in_inputs","reason":"one sentence"}.
TASK: {task}
INPUT FILES (name + schema/preview):
{files}
SEARCH HITS for the missing terms:
{hits}
RUBRIC: {rubric}"""

B5_JUDGE = """This RUBRIC checks the OUTPUT file's STRUCTURE (filename / sheet name /
format), not a data value. Judge it against the TASK only:
- over_constrained: the TASK never asked for this exact name/sheet/layout, so a
  correct output using a different name/layout would wrongly fail.
- task_mismatch: the structure contradicts the task's scope/口径 (e.g. filename says
  '公立医院' but the task covers all hospitals).
- none: the task explicitly requires exactly this structure, so it is fine.
Return ONLY JSON {"defect":"over_constrained|task_mismatch|none","evidence":"the rubric/task phrase, or empty"}.
TASK: {task}
RUBRIC: {rubric}"""


# ---------- item loading ----------
class Item(dict):
    pass


def load_case_item(name):
    text = (REPO / "Workspace-Bench Case Learning.md").read_text(encoding="utf-8")
    block = rdv.case_block(text, name)
    m = re.search(r"Task[:：]\s*(.*?)(?=\n\n|参考步骤|###)", block, re.S)
    task = (m.group(1).strip() if m else "")
    att = REPO / "图片和附件"
    inputs = [att / p for p in rdv.input_paths(block) if (att / p).exists()]
    return Item(id=name, task=task, inputs=inputs, rubrics=rdv.rubrics_of(block))


def lite_inputs(absolute_id):
    """The task's real input files live on HF at task_lite_clean_en/<id>/data/*
    (the parquet only carries the manifest). Fetch that dir; every file in it is
    an input. Matching data_manifest is unreliable (hash prefix is inconsistent),
    so we just use the whole data/ directory."""
    from huggingface_hub import snapshot_download
    root = snapshot_download("Workspace-Bench/Workspace-Bench-Lite", repo_type="dataset",
                             allow_patterns=[f"task_lite_clean_en/{absolute_id}/**"])
    data_dir = Path(root) / "task_lite_clean_en" / str(absolute_id) / "data"
    return sorted(p for p in data_dir.iterdir() if p.is_file()) if data_dir.exists() else []


def load_hf_item(absolute_id, row=None):
    if row is None:
        from datasets import load_dataset
        ds = load_dataset("Workspace-Bench/Workspace-Bench-Lite", split="lite")
        row = next((ds[i] for i in range(len(ds)) if ds[i]["absolute_id"] == absolute_id), None)
        if row is None:
            raise ValueError(f"absolute_id {absolute_id} not found")
    rubrics = row["rubrics"] if isinstance(row["rubrics"], list) else json.loads(row["rubrics"])
    return Item(id=f"id={absolute_id}", task=str(row["task"]),
                inputs=lite_inputs(absolute_id), rubrics=rubrics)


# ---------- helpers ----------
def majority(results, key, default=None):
    vals = [r.get(key) for r in results if isinstance(r, dict) and key in r]
    return Counter(vals).most_common(1)[0][0] if vals else default


def read_full(path):
    """Full text of an input file. xlsx: ALL sheets, header=None (per the rule)."""
    p = Path(path); ext = p.suffix.lower()
    if ext in (".xlsx", ".xls"):
        import pandas as pd
        xl = pd.ExcelFile(p)
        parts = []
        for sh in xl.sheet_names:
            df = xl.parse(sh, header=None)
            parts.append(f"[sheet {sh}]\n" + df.to_string(max_colwidth=20))
        return "\n".join(parts)
    from benchcore.file_reader import read_file
    return read_file(p, 20000)


def norm(s):
    return re.sub(r"\s+", "", str(s))


def _pmap(fn, items, workers=8):
    """Run fn over items concurrently -- the per-rubric LLM calls are independent and
    the client's cache is lock-protected, so this only cuts wall time. Order preserved;
    None results dropped."""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
        return [f for f in ex.map(fn, items) if f is not None]


def _search_terms(inputs, terms):
    """Locate each missing term's full-text context across ALL input files (so the
    B1 verifier gets real evidence instead of a truncated blob)."""
    from benchcore.file_reader import search_file
    lines = []
    for p in inputs:
        for t, ctx in search_file(p, terms).items():
            if ctx and not t.startswith("_"):
                lines.append(f"  '{t}' 命中 {p.name}: …{ctx}…")
    return "\n".join(lines) or "  (缺失词在所有输入文件中均未按字面命中)"


# ---------- plan / exec / eval ----------
def plan(item, vote):
    # B4/B5 judge a rubric AGAINST the task; with no task there is no baseline and
    # every structure/leakage judgement becomes a construction artifact -> skip them.
    has_task = len(norm(item["task"])) >= 8
    task_type = "unknown"
    if has_task:
        res = vote.chat_json_multi(CLASSIFY.replace("{task}", item["task"][:1500]), "classify")
        task_type = majority(res, "task_type", "subjective")
    detectors = []
    if item["inputs"]:
        detectors += ["B1", "B2"]         # B1 existence + B2 value-recompute (need inputs)
    if has_task and any(re.search(STRUCT_PAT, r) for r in item["rubrics"]):
        detectors.append("B5")            # output-structure vs task (task required)
    if has_task and task_type == "subjective":
        detectors.append("B4")            # answer-leakage only meaningful for derive tasks
    return {"task_type": task_type, "detectors": detectors, "has_task": has_task}


def exec_B1(item, single, vote):
    """Two-stage: literal search is only a FILTER; a literal miss escalates to a
    semantic verifier. Grounding is per-file (name + schema) + targeted search, never
    one truncated blob -- a truncated blob silently hides later files and invents
    'missing' defects (e.g. 5 market csvs present but only the first fits in 16KB)."""
    from benchcore.file_reader import read_file
    names = " ".join(p.name for p in item["inputs"])
    # every filename + full content -> the literal presence filter; a market named in a
    # filename (USCA_orders.csv) counts as present. Not sent to the LLM, just searched.
    # lowercased: English data uses 'Gender'/'Purchase Order' but extraction is lowercase.
    blob = norm(names + " " + "\n".join(read_full(p) for p in item["inputs"])).lower()
    files_view = "所有输入文件: " + names + "\n\n" + "\n\n".join(
        f"FILE {p.name}\n" + read_file(p, 1500) for p in item["inputs"])

    def one(r):
        if re.search(STRUCT_PAT, r):
            return None  # output-structure -> B5, not data-existence
        if not re.search(r"\d|等级|三级|二级|一级|字段|分布", r):
            return None  # only data-bearing rubrics
        ext = single.chat_json(B1_EXTRACT.replace("{rubric}", r), "extract")
        required = [t for t in ext.get("required", []) if core_term(t) and len(core_term(t)) >= 2]
        missing = [t for t in required if core_term(t).lower() not in blob]  # literal miss
        if not (required and missing):
            return None
        # literal miss -> semantic verdict grounded on file names + schema + search hits.
        res = vote.chat_json_multi(
            B1_VERIFY.replace("{missing}", ", ".join(missing))
                     .replace("{task}", item["task"][:1000] or "(未提供)")
                     .replace("{files}", files_view[:14000])
                     .replace("{hits}", _search_terms(item["inputs"], missing))
                     .replace("{rubric}", r), "verify")
        if majority(res, "verdict", "not_in_inputs") == "not_in_inputs":
            reason = next((x.get("reason") for x in res
                           if x.get("verdict") == "not_in_inputs" and x.get("reason")), "")
            return {"rubric": r, "tier": "T1→T3", "required": required, "missing": missing,
                    "verdicts": [x.get("verdict") for x in res],
                    "evidence": reason or f"输入中确无维度: {missing}"}
        return None
    return _pmap(one, item["rubrics"])


def exec_B2(item, vote):
    """Recompute each numeric rubric's asserted value from the inputs and flag any the
    computation does not reproduce. The number is computed (not judged), but the recompute
    CODE is LLM-written and NOT reproducible (single-shot flips the verdict ~40% of the
    time, reports/b2_nondeterminism.md), so a single generation is noise. We draw n code
    samples (via chat_json_multi), execute each, and flag ONLY when a strong majority
    (>=B2_CONSENSUS) agree on a value-set that disagrees with the rubric under a TIGHT
    tolerance. Non-reproducible rubrics (no majority) are dropped as inconclusive -- that
    unreproducible noise was the main B2 false-positive source (id=15/269/328/44). Still a
    human-review candidate, not a confirmed verdict. Data-absent cases are left to B1."""
    from benchcore.file_reader import read_file
    # list every path up front so codegen reads all files even when previews truncate
    paths = "所有输入文件绝对路径(逐个读取):\n" + "\n".join(str(p) for p in item["inputs"])
    profile = paths + "\n\n" + "\n\n".join(f"路径: {p}\n" + read_file(p, 1000) for p in item["inputs"])
    n = vote.config.n_votes

    def one(r):
        if re.search(STRUCT_PAT, r) or re.search(B2_SKIP_PAT, r, re.I) or not re.search(r"\d", r):
            return None  # structure / output-artifact / transcription rubrics aren't data recompute
        exp = l1.rubric_values(r)  # substantive figures only; drops index/year/ID/threshold noise
        if not exp:
            return None
        try:
            samples = vote.chat_json_multi(
                l1.PROMPT.replace("{inputs}", profile[:8000]).replace("{rubric}", r), "compute")
        except Exception:
            return None  # a codegen sample overflowed / returned no JSON -> skip this rubric

        # execute each sample; keep the comparable value-sets. Runs that print
        # DATA_NOT_AVAILABLE or no 'label=number' don't count toward consensus.
        valuesets = []
        for s in samples:
            code = s.get("code", "") if isinstance(s, dict) else ""
            if "print" not in code:
                continue
            comp = l1.run_code(code)
            if "DATA_NOT_AVAILABLE" in comp or not re.search(r"=\s*-?[\d.]", comp):
                continue
            valuesets.append(tuple(sorted(round(x, 3) for x in l1.nums(comp))))
        if not valuesets:
            return None
        modal, sup = Counter(valuesets).most_common(1)[0]
        if sup < B2_CONSENSUS * n:
            return None  # recompute not reproducible across samples -> inconclusive, don't report
        # unit-tolerant: a value counts as reproduced if it, /100 or *100 appears in the
        # consensus output (a rate 17.49% vs a fraction 0.1749 is the same number).
        miss = [e for e in exp
                if not any(abs(v - g) <= max(B2_TOL_ABS, abs(v) * B2_TOL_REL)
                           for g in modal for v in (e, e / 100, e * 100))]
        if miss:
            return {"rubric": r, "tier": "T1(重算共识)", "expected": exp, "missing": miss,
                    "consensus": f"{sup}/{n}", "modal": list(modal),
                    "evidence": f"{sup}/{n} 次重算一致得 {list(modal)}, 与 rubric 值 {miss} 不符(紧容差)"}
        return None
    return _pmap(one, item["rubrics"])


def exec_B5(item, vote):
    """Output-structure rubrics vs the task: over-specified or contradicting the scope."""
    def one(r):
        if not re.search(STRUCT_PAT, r):
            return None
        res = vote.chat_json_multi(
            B5_JUDGE.replace("{task}", item["task"][:1200]).replace("{rubric}", r), "b5")
        d = majority(res, "defect", "none")
        if d != "none":
            ev = next((x.get("evidence") for x in res if x.get("defect") == d and x.get("evidence")), "")
            return {"rubric": r, "tier": "T3", "defect": d,
                    "votes": [x.get("defect") for x in res], "evidence": ev}
        return None
    return _pmap(one, item["rubrics"])


def exec_B4(item, vote):
    derive = is_derive_task(item["task"])

    def one(r):
        res = vote.chat_json_multi(
            B4_JUDGE.replace("{task}", item["task"][:1200]).replace("{rubric}", r), "judge")
        leak = majority(res, "leakage", False)
        if leak is True:
            ev = next((x.get("evidence") for x in res if x.get("leakage") and x.get("evidence")), "")
            return {"rubric": r, "tier": "T3", "votes": [x.get("leakage") for x in res],
                    "derive_task": derive, "evidence": ev}
        return None
    return _pmap(one, item["rubrics"])


def evaluate(detector, flags):
    """Gate: deterministic flags -> confirmed; T3 flags -> confirmed only if anchored."""
    out = []
    for f in flags:
        if detector == "B1":
            out.append({**f, "status": "已确认",
                        "why": "字面缺失 + 语义核验(多次投票)确认该维度确不在输入、也无法推导"})
        elif detector == "B2":
            out.append({**f, "status": "候选",
                        "why": f"{f.get('consensus','')} 次重算多数一致且与 rubric 值不符(紧容差) -> 强候选, 仍需人工核对取列/聚合口径"})
        elif detector == "B5":
            # task_mismatch = the structure CONTRADICTS the task scope -> a hard defect.
            # over_constrained = the task merely did not mention it -> soft, because
            # rubric benchmarks always operationalize an open task into some structure;
            # only a human can say whether it is *excessive*. So never auto-confirm it.
            unanimous = len(set(f.get("votes", []))) == 1
            confirmed = unanimous and f.get("defect") == "task_mismatch"
            out.append({**f, "status": "已确认" if confirmed else "候选",
                        "why": "结构与任务口径矛盾(投票一致)" if confirmed
                               else "结构过约束: 任务未提及,但可能是合理细化 -> 待人工判定是否过度"})
        elif detector == "B4":
            # Candidate-only: "over-constraint" is a fuzzy judgement with no verifiable
            # ground truth, and even UNANIMOUS votes are confidently wrong on objective
            # checks (a rubric that pins a data-determined finding -- id=23/37/226 all
            # voted leakage=True yet are legitimate objective checks). Unlike B1 (absence
            # is objectively checkable against the inputs), B4 cannot be auto-confirmed;
            # anchored+unanimous flags are the STRONGEST candidates, not confirmations.
            strong = f.get("derive_task") and all(v is True for v in f.get("votes", []))
            out.append({**f, "status": "候选",
                        "why": ("T3 强候选: 任务需自行推导且投票一致泄漏, 但过约束无客观基准 -> 人工复核"
                                if strong else "T3 候选: 投票泄漏但缺锚定/不全一致 -> 人工复核")})
    return out


def run(item, single, vote, vote_b1=None):
    # B1's semantic verdict on borderline rubrics (not_in_inputs vs generated_content)
    # is the least reproducible call; it gets its own, higher-n voter to tighten the
    # majority. Falls back to the shared voter if none is given.
    vote_b1 = vote_b1 or vote
    print("=" * 72)
    print(f"ITEM {item['id']}  | {len(item['rubrics'])} rubrics | inputs={len(item['inputs'])}")
    p = plan(item, vote)
    if not p["has_task"]:
        print("  [WARN] 该 item 无任务文本 -> 跳过依赖任务的 B4/B5(否则全是构造性假阳性)")
    print(f"  [PLAN] task_type={p['task_type']}  detectors={p['detectors']}")
    report = {"id": item["id"], "plan": p, "findings": []}
    for det in p["detectors"]:
        if det == "B1":
            flags = exec_B1(item, single, vote_b1)
        elif det == "B2":
            flags = exec_B2(item, vote_b1)  # n-sample recompute consensus
        elif det == "B5":
            flags = exec_B5(item, vote)
        else:
            flags = exec_B4(item, vote)
        results = evaluate(det, flags)
        print(f"  [EXEC {det}] {len(flags)} 个疑点 -> [EVAL] "
              f"{sum(r['status']=='已确认' for r in results)} 确认 / "
              f"{sum(r['status']=='候选' for r in results)} 候选")
        for r in results:
            mark = "✅确认" if r["status"] == "已确认" else "🟡候选"
            print(f"     {mark} [{det}/{r['tier']}] {r['rubric'][:46]}")
            print(f"            └ {r['evidence'][:80] if r['evidence'] else r['why']}")
        report["findings"] += [{"detector": det, **r} for r in results]
    return report


def main():
    single = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek.json")))
    vote = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek_vote3.json")))
    vote_b1 = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek_vote5.json")))
    items = [load_case_item("仓敏_3"), load_hf_item(244)]
    reports = [run(it, single, vote, vote_b1) for it in items]
    (REPO / "reports/auditor_agent_run.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote reports/auditor_agent_run.json")


if __name__ == "__main__":
    main()
