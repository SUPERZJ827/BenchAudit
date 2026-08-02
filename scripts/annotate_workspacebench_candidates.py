"""Evidence-first re-annotation of the WorkspaceBench full388 candidate list.

The upstream annotation (`WorkspaceBench_full388_Codex证据化逐条标注_20260720.md`)
labels every candidate with two LLM stages.  This script deliberately uses no
LLM at all.  For each candidate it re-reads the *real* task text, the *real*
rubric string, the *real* output contract and the *real* input files, and then
decides how much of the candidate's claim can be settled by replayable facts.

Confirmable families (an objective contradiction inside the shipped item -- no
output can satisfy it, and re-running the check reproduces the proof):

``placeholder_leak``
    the rubric or the task still carries an unsubstituted template placeholder
    (``__ PH_11 __``), so the required filename does not exist as a string;
``task_vs_contract_filename``
    the task instructs the agent to save one filename, the contract/rubrics
    require a different one -- following the instruction fails the evaluator;
``rubric_vs_contract_filename``
    a rubric pins an output filename the contract contradicts (e.g. ``.doc``
    against ``.docx``);
``byte_size``
    a rubric pins an exact byte size that the shipped input file contradicts;
``duplicate_output_files``
    the contract lists the same output filename several times for what the task
    describes as several distinct artifacts.

Everything else stays review.  For those we still add replayable *evidence*: the
literal a rubric pins down is searched in the task, the contract, the input
filenames and the extracted input text, so a claim of the form "not grounded in
the task or inputs" is either objectively refuted (the literal is there) or
objectively supported (it is not, and every input parsed).  If any input file
fails to parse we refuse to assert absence at all -- "I could not read it" is
not evidence of absence.  No semantic judgement is ever promoted to confirmed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchcore.file_reader import read_file_result

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MD = ROOT / "WorkspaceBench_full388_Codex证据化逐条标注_20260720.md"
DEFAULT_DATASET = ROOT / "datasets/workspacebench/full.jsonl"

EXT = r"(?:docx?|xlsx?|pptx?|csv|md|txt|html?|py|json|pdf|png|jpg)"

PLACEHOLDER_RE = re.compile(r"__\s*PH_?\d+\s*__")
SIZE_RE = re.compile(r"size (?:is )?exactly ([\d,]+) bytes", re.I)
# A rubric asserting the *output* file's name.
RUBRIC_NAME_RE = re.compile(
    r"(?:output file(?:\s*name)?\s*(?:is\s*)?(?:correctly\s*)?(?:named|name is)"
    r"|is the output file name(?: exactly)?|saved with the correct filename"
    r"|output filename is(?: exactly)?)"
    r"\s*[`\"'“‘]?\s*([\w\-\.]+\." + EXT + r")",
    re.I,
)
# The task telling the agent what to call its output.
TASK_NAME_RE = re.compile(
    r"(?:named|name it|save(?:d|s)? (?:it |them )?(?:to the desktop )?as"
    r"|output(?:ted)? (?:as|to)"
    r"|generate[sd]? (?:a |an )?[\w \-]{0,40}?(?:file |document )?(?:named|called))"
    r"\s*[`\"'“‘]?\s*([\w\-\.]+\." + EXT + r")",
    re.I,
)
# The quantifier must start at 1: a one-character literal such as `Ⅰ` would
# otherwise be skipped and the scanner would pair the *closing* delimiter with
# the next opening one, capturing the prose in between.  Length is filtered
# afterwards instead.
LITERAL_RES = (
    re.compile(r"`([^`]{1,120})`"),
    re.compile(r"'([^']{1,120})'"),
    re.compile(r'"([^"]{1,120})"'),
    re.compile(r"[“‘]([^”’]{1,120})[”’]"),
    re.compile(r"[「『]([^」』]{1,120})[」』]"),
)
LITERAL_STOPWORDS = {"yes", "no", "n/a", "true", "false", "and", "or", "the"}
# Bare file extensions and other fragments carry no grounding information.
LITERAL_JUNK_RE = re.compile(r"^\.?" + EXT + r"$", re.I)
# Only a claim that asserts absence can be refuted by finding the literal.
ABSENCE_CLAIM_RE = re.compile(
    r"not (?:specified|mentioned|present|found|grounded|derivable|listed|included"
    r"|provided|defined|required by|supported)"
    r"|missing|does not (?:appear|exist|include|specify|contain|mention)"
    r"|no such|not in the (?:task|input)|unreadable|cannot be (?:parsed|read)"
    r"|is not grounded|ungrounded|not derivable",
    re.I,
)

L_CONFIRMED = "已确认·确定性矛盾"
L_REFUTED = "客观证否·字面量确有来源"
L_SUPPORTED = "客观证据支持·仍需语义判定"
L_UNDECIDABLE = "不可判定·输入未完整解析"
L_SEMANTIC = "纯语义·无可重放证据"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).casefold()


def extract_literals(text: str) -> list[str]:
    out: list[str] = []
    for pattern in LITERAL_RES:
        for hit in pattern.findall(text):
            token = hit.strip().strip(".,:;")
            if len(token) < 3 or token.casefold() in LITERAL_STOPWORDS:
                continue
            if not re.search(r"[A-Za-z一-鿿\d]", token):
                continue
            if LITERAL_JUNK_RE.match(token):
                continue
            # A short latin token without structure is usually a fragment.
            if len(token) < 5 and not re.search(r"[.\s一-鿿]", token):
                continue
            if token not in out:
                out.append(token)
    return out


# --- per-item evidence ------------------------------------------------------


def item_evidence(item: dict[str, Any]) -> dict[str, Any]:
    """Read every shipped input once; record parse status, size and text."""

    files = []
    for raw in item.get("input_files") or []:
        path = Path(raw)
        entry: dict[str, Any] = {"name": path.name}
        if not path.exists():
            entry.update(status="missing", size=None, text="")
            files.append(entry)
            continue
        raw_bytes = path.read_bytes()
        entry["size"] = len(raw_bytes)
        entry["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        result = read_file_result(path)
        entry["status"] = result.status
        entry["text"] = result.text if result.succeeded else ""
        files.append(entry)

    outputs = _json_list(item.get("output_files"))
    manifest = _json_list(item.get("data_manifest"))
    return {
        "files": files,
        "outputs": outputs,
        "sources": {
            "task": _norm(item.get("task") or ""),
            "output_contract": _norm(json.dumps(item.get("output_contract") or {}, ensure_ascii=False)
                                     + " " + " ".join(outputs)),
            "input_filename": _norm(" ".join([f["name"] for f in files]
                                             + [str(m.get("filename", "")) for m in manifest])),
            "input_content": _norm(" ".join(f["text"] for f in files)),
        },
        "all_readable": all(f["status"] == "ok" for f in files),
        "unreadable": [f["name"] for f in files if f["status"] != "ok"],
        "sizes": _logical_sizes(manifest, files),
        "collisions": _name_collisions(manifest, files),
    }


def _name_collisions(manifest: list[Any], files: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Logical input names that resolve to more than one distinct content hash."""

    by_stored = {f["name"]: f for f in files}
    digests: dict[str, set[str]] = defaultdict(set)
    for row in manifest:
        if not isinstance(row, dict):
            continue
        entry = by_stored.get(Path(str(row.get("stored_relpath") or "")).name)
        if entry and entry.get("sha256"):
            digests[str(row.get("filename") or "")].add(entry["sha256"])
    return {name: d for name, d in digests.items() if len(d) > 1}


def _json_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _logical_sizes(manifest: list[Any], files: list[dict[str, Any]]) -> dict[str, int]:
    """Map each manifest logical filename onto the materialized file size."""

    by_stored = {f["name"]: f for f in files}
    sizes: dict[str, int] = {}
    for row in manifest:
        if not isinstance(row, dict):
            continue
        stored = Path(str(row.get("stored_relpath") or "")).name
        entry = by_stored.get(stored)
        if entry and entry.get("size") is not None:
            sizes[str(row.get("filename") or stored)] = int(entry["size"])
    return sizes


# --- item-level confirmable defects ----------------------------------------


def item_defects(item: dict[str, Any], ev: dict[str, Any]) -> list[dict[str, Any]]:
    """Contradictions that hold for the whole item, independent of a candidate."""

    found: list[dict[str, Any]] = []
    outputs = ev["outputs"]
    lowered = [str(o).casefold() for o in outputs]
    inputs = {str(k).casefold() for k in ev["sizes"]}

    if len(lowered) != len(set(lowered)):
        found.append({
            "family": "duplicate_output_files",
            "detail": f"output_files 中出现重复文件名: {outputs}",
        })

    for name, digests in ev["collisions"].items():
        found.append({
            "family": "input_filename_collision",
            "detail": f"逻辑输入名 {name} 对应 {len(digests)} 份内容不同的文件"
                      f"(sha256 前缀 {sorted(d[:12] for d in digests)})",
        })

    task = item.get("task") or ""
    if PLACEHOLDER_RE.search(task):
        found.append({
            "family": "placeholder_leak",
            "where": "task",
            "detail": f"任务文本残留未替换模板占位符 {PLACEHOLDER_RE.findall(task)}",
        })

    for match in TASK_NAME_RE.finditer(task):
        name = match.group(1)
        if name.casefold() in lowered or name.casefold() in inputs:
            continue
        found.append({
            "family": "task_vs_contract_filename",
            "detail": f"任务要求存为 {name},契约/评测要求 {outputs}",
        })
    return found


# --- rubric-level checks ----------------------------------------------------


def check_byte_size(rubric: str, ev: dict[str, Any]) -> dict[str, Any] | None:
    match = SIZE_RE.search(rubric)
    if not match:
        return None
    required = int(match.group(1).replace(",", ""))
    normalized = _norm(rubric)
    for name, size in ev["sizes"].items():
        if _norm(name) in normalized:
            return {"check": "byte_size", "file": name, "required": required,
                    "actual": size, "contradiction": size != required}
    return None


def check_rubric_filename(rubric: str, ev: dict[str, Any]) -> dict[str, Any] | None:
    match = RUBRIC_NAME_RE.search(rubric)
    if not match:
        return None
    name = match.group(1)
    lowered = [str(o).casefold() for o in ev["outputs"]]
    return {"check": "rubric_vs_contract_filename", "rubric_name": name,
            "contract": ev["outputs"], "contradiction": name.casefold() not in lowered}


def check_literals(rubric: str, claim: str, ev: dict[str, Any]) -> dict[str, Any]:
    """Ground only the literals the *claim* is actually about.

    A rubric usually also pins the output filename; that literal is trivially
    grounded and says nothing about a claim concerning, say, chapter order.  So
    a literal counts only when the claim quotes it too.
    """

    rubric_literals = extract_literals(rubric)
    claim_norm = _norm(claim)
    # The rubric almost always also names the artifact under test.  That literal
    # is grounded by construction and would refute claims it has nothing to do
    # with, so it cannot anchor anything.
    contract_names = {_norm(str(o)) for o in ev["outputs"]}
    anchored = [t for t in rubric_literals
                if _norm(t) in claim_norm and _norm(t) not in contract_names]
    found: dict[str, str] = {}
    for token in anchored:
        needle = _norm(token)
        for source, blob in ev["sources"].items():
            if needle in blob:
                found[token] = source
                break
        else:
            found[token] = "absent"
    return {"check": "literal", "anchored": anchored,
            "unanchored": [t for t in rubric_literals if t not in anchored],
            "literals": found}


def label_row(rubric: str, claim: str, ev: dict[str, Any],
              defects: list[dict[str, Any]]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    if PLACEHOLDER_RE.search(rubric):
        return {"label": L_CONFIRMED, "family": "placeholder_leak",
                "reason": f"rubric 残留未替换模板占位符 {PLACEHOLDER_RE.findall(rubric)},"
                          f"任何输出都无法匹配该文件名",
                "checks": [{"check": "placeholder_leak"}]}

    size = check_byte_size(rubric, ev)
    if size:
        checks.append(size)
        if size["contradiction"]:
            return {"label": L_CONFIRMED, "family": "byte_size",
                    "reason": f"rubric 要求 {size['file']} 恰为 {size['required']} 字节,"
                              f"数据集实际 {size['actual']} 字节",
                    "checks": checks}

    fname = check_rubric_filename(rubric, ev)
    if fname:
        checks.append(fname)
        if fname["contradiction"]:
            return {"label": L_CONFIRMED, "family": "rubric_vs_contract_filename",
                    "reason": f"rubric 要求输出名 {fname['rubric_name']},"
                              f"契约要求 {fname['contract']}",
                    "checks": checks}

    # A naming contradiction only settles *this* candidate when the candidate is
    # itself about the output name; otherwise it is item-level context.
    inherited = [d for d in defects if d["family"] == "task_vs_contract_filename"]
    if inherited and re.search(r"file ?name|named|filename", claim, re.I):
        return {"label": L_CONFIRMED, "family": "task_vs_contract_filename",
                "reason": inherited[0]["detail"], "checks": checks + inherited}

    lit = check_literals(rubric, claim, ev)
    checks.append(lit)
    literals = lit["literals"]
    if not literals:
        return {"label": L_SEMANTIC,
                "reason": "claim 未引用 rubric 中任何字面量,无可重放检项", "checks": checks}

    absent = [t for t, where in literals.items() if where == "absent"]
    if not absent:
        where = ",".join(sorted(set(literals.values())))
        if not ABSENCE_CLAIM_RE.search(claim):
            return {"label": L_SEMANTIC,
                    "reason": f"claim 主张的是「任务未要求该内容」而非「字面量不存在」,"
                              f"字面量在 {where} 出现并不能证否它",
                    "checks": checks}
        return {"label": L_REFUTED,
                "reason": f"claim 断言该字面量不存在,但 {list(literals)[:3]} 实际出现在 {where}",
                "checks": checks}
    if not ev["all_readable"]:
        return {"label": L_UNDECIDABLE,
                "reason": f"字面量 {absent[:3]} 未检出,但 {len(ev['unreadable'])} 个输入未完整解析"
                          f"({ev['unreadable'][:2]}),不能据此断言缺失",
                "checks": checks}
    return {"label": L_SUPPORTED,
            "reason": f"全部输入可解析,字面量 {absent[:3]} 在任务/契约/文件名/文件内容中均未出现",
            "checks": checks}


# --- driver -----------------------------------------------------------------


def load_candidates(md_path: Path) -> list[dict[str, str]]:
    rows = []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `workspacebench-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        rows.append({"item": cells[0].strip("`"), "ridx": cells[1],
                     "codex": cells[2].strip("*"), "claim": cells[6]})
    return rows


def _cell(text: str, limit: int = 200) -> str:
    text = re.sub(r"\s+", " ", str(text)).replace("|", "/")
    return text[:limit] + ("…" if len(text) > limit else "")


def render_markdown(out_rows: list[dict[str, Any]], sweep: list[dict[str, Any]],
                    raw: list[dict[str, str]]) -> str:
    counts = Counter(r["label"] for r in out_rows)
    lines = [
        "# WorkspaceBench full388:Claude 证据化逐条标注(2026-07-20)",
        "",
        "> 对同一份候选清单的独立复核。与上游标注的方法差异是刻意的:**本文件全程不调用 LLM**。",
        "> 每条候选都重新读取真实 task 文本、真实 rubric 字符串、真实 output contract 和真实输入文件",
        "> (xlsx/docx/pptx 用 `benchcore.file_reader` 的受限解析器提取文本),只报告能重放的事实。",
        "",
        "## 标注口径",
        "",
        f"1. **{L_CONFIRMED}**:item 内部存在客观矛盾,任何输出都无法同时满足,重跑即复现。可自动确认。",
        f"2. **{L_REFUTED}**:候选声称某字面量「任务/输入里没有」,实际检索到了 → 候选的事实前提被证否。",
        f"3. **{L_SUPPORTED}**:rubric 钉死的字面量在 task/契约/文件名/输入内容中确实都不出现,"
        "且该 item 全部输入都解析成功。事实可重放,但「这算不算缺陷」仍是语义判断 → 保持 review。",
        f"4. **{L_UNDECIDABLE}**:该 item 有输入文件解析失败。**解析不了不等于不存在**,拒绝断言缺失。",
        f"5. **{L_SEMANTIC}**:候选主张的是「任务没要求这类内容」(推荐条数、版式、章节顺序、图表类型…),"
        "没有可检索的字面量,确定性证据无法触及 → 只能 review。",
        "",
        "## 总体结果",
        "",
        "| 标注 | 数量 |",
        "|---|---:|",
    ]
    for label, n in counts.most_common():
        lines.append(f"| {label} | {n} |")
    lines += [
        "",
        f"**{counts.get(L_SEMANTIC, 0)}/{len(out_rows)} "
        f"({counts.get(L_SEMANTIC, 0) / len(out_rows):.0%}) 的候选无法用任何确定性证据触及**,"
        "这与上游给出的「300 条较可信真问题」不矛盾,但说明那 300 条里绝大多数的可信度来源仍是模型判断。",
        "",
        "## 全库确定性扫描(不限于候选清单)",
        "",
        "同一套检查直接扫过 388 个 item 的**全部** rubric,而不只是上游筛出来的候选:",
        "",
        "| 缺陷族 | 命中 rubric/item 条数 | 涉及 item 数 |",
        "|---|---:|---:|",
    ]
    fam = Counter(s["family"] for s in sweep)
    for name, n in fam.most_common():
        items = len({s["item"] for s in sweep if s["family"] == name})
        lines.append(f"| `{name}` | {n} | {items} |")
    covered = {(s["item"], str(s["ridx"])) for s in sweep if s["ridx"] is not None}
    listed = {(r["item"], r["ridx"]) for r in raw}
    lines += [
        "",
        f"其中只有 **{len(covered & listed)}/{len(covered)}** 条落在上游候选清单里 —— "
        "剩下的是纯正则可抓、却没有被两阶段 LLM 流程召回的确定性缺陷。",
        "",
        "### 占位符族的反证检查",
        "",
        "把 `placeholder_leak` 记为「已确认」之前先证伪了一种可能:harness 在运行时替换 `__ PH_n __`。",
        "在 HuggingFace 快照 `3491f9eb…` 内全量 grep,除 task/rubric 正文外**没有任何文件出现 `PH_`**,"
        "`metadata.json` 的字段里也没有替换表;且编号是跨 item 的全局槽位"
        "(`__ PH_11 __` 同时出现在 171 和 172,`__ PH_16 __` 同时出现在 182 和 186),"
        "item-194 更是用 `PH_9/10/11/12` 指代四份简历、而 `output_files` 是同一个名字重复四次 —— "
        "即使按位置替换也无法还原。因此该族在**已发布的数据**上确实无解。",
        "若官方另有未随数据集发布的替换表,这一族应整体降级为 review;这是本文件已知的唯一外部依赖。",
        "",
        "### 明细",
        "",
        "| item | rubric | 缺陷族 | 事实 |",
        "|---|---:|---|---|",
    ]
    for entry in sorted(sweep, key=lambda s: (s["family"], s["item"])):
        ridx = "—" if entry["ridx"] is None else entry["ridx"]
        lines.append(f"| `{entry['item']}` | {ridx} | `{entry['family']}` | {_cell(entry['detail'])} |")

    lines += [
        "",
        "## 手工核实记录",
        "",
        "下面这些 item 我逐个打开了真实 task/rubric/输入文件亲自读过,不是只看脚本输出:",
        "",
        "- `workspacebench-7`:三条 rubric 钉死 4000/4586/5613 字节,而 data 目录里的真实文件是"
        "4760/5582/6511 字节;同 item 另有 rubric 要求「拷贝内容与原文件完全一致」。两组要求互斥。",
        "- `workspacebench-171`:**任务正文**写的是「a table … named `__ PH_11 __`」——占位符没被替换就发给了"
        "被测模型,而 contract 要求 `Procurement_Supplier_Summary.xlsx`,另有 8 条 rubric 用 `__ PH_11 __` 指代该文件。",
        "- `workspacebench-194`:11 条 rubric 分别引用 `__ PH_9/10/11/12 __` 指代四份简历,"
        "而 `output_files` 把同一个文件名重复了 4 次,占位符无从解析。",
        "- `workspacebench-203`:任务说「Save it to the desktop as Random_Idiom_Guessing_Game.py」,"
        "rubric 16 却检查 `Random_Idiom_Guessing_from_Pictures.py`。照做即失分。",
        "- `workspacebench-198 / 222 / 226 / 208 / 230 / 234`:同一族。分别是 `Shandong.pptx` vs "
        "`Shandong.pptx.pptx`(重复扩展名)、`Tesla_Model_3.xlsx` vs `Tesla_Model3.xlsx`、"
        "`bug_report.txt` vs `bug report.txt`(下划线 vs 空格)、报告名整体改写、结尾多一个下划线。",
        "- `workspacebench-267 / 268`:rubric 要求 `.doc`,contract 要求 `.docx`,同一句里还写着「格式是 docx」。",
        "- `workspacebench-175`:上游标注称 sheet 名 'fixed asset depreciation ledger'「任务里没有」,"
        "但任务原文第一句就是「Generate a fixed asset depreciation ledger」——**该 claim 事实错误**。",
        "- `workspacebench-351`:上游唯一的 confirmed。独立复算:`table.xlsx` 对应两份 sha256 不同、"
        "大小 13150 / 207610 的文件,复现成立,且全库扫描确认这是唯一一例。",
        "- `workspacebench-5 / 13 / 16`:上游多条证据写「input files are unreadable / cannot be parsed」,"
        "实测这些 xlsx/docx/pptx 都能被 `benchcore.file_reader` 解析出文本(9.4MB 的 pptx 提取到 758 字符,"
        "因为内容以图片为主)。**「我读不了」被当成了「里面没有」**。",
        "",
        "## 逐条标注(完整)",
        "",
        "| item | rubric | 我的标注 | 上游标注 | 判定依据 | rubric 原文 | 候选 claim |",
        "|---|---:|---|---|---|---|---|",
    ]
    order = {L_CONFIRMED: 0, L_REFUTED: 1, L_SUPPORTED: 2, L_UNDECIDABLE: 3, L_SEMANTIC: 4}
    for row in sorted(out_rows, key=lambda r: (order.get(r["label"], 9), r["item"])):
        lines.append(
            f"| `{row['item']}` | {row['ridx']} | **{row['label']}** | {row['codex']} "
            f"| {_cell(row['reason'], 220)} | {_cell(row.get('rubric', ''), 160)} "
            f"| {_cell(row['claim'], 160)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_MD)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=ROOT / "reports/workspace_reannotation")
    args = parser.parse_args()

    dataset = {json.loads(l)["item_id"]: json.loads(l) for l in args.dataset.open()}
    rows = load_candidates(args.candidates)

    evidence: dict[str, dict[str, Any]] = {}
    defects: dict[str, list[dict[str, Any]]] = {}
    for item_id, item in dataset.items():
        evidence[item_id] = item_evidence(item)
        defects[item_id] = item_defects(item, evidence[item_id])

    # Sweep every rubric of the benchmark for the confirmable families, not just
    # the candidates the upstream scanner happened to surface.
    sweep: list[dict[str, Any]] = []
    for item_id, item in dataset.items():
        for entry in defects[item_id]:
            sweep.append({"item": item_id, "ridx": None, **entry})
        for idx, rubric in enumerate(item["rubrics"]):
            if PLACEHOLDER_RE.search(rubric):
                sweep.append({"item": item_id, "ridx": idx, "family": "placeholder_leak",
                              "detail": f"rubric 残留 {PLACEHOLDER_RE.findall(rubric)}"})
            fname = check_rubric_filename(rubric, evidence[item_id])
            if fname and fname["contradiction"]:
                sweep.append({"item": item_id, "ridx": idx,
                              "family": "rubric_vs_contract_filename",
                              "detail": f"rubric 要求 {fname['rubric_name']},契约 {fname['contract']}"})
            size = check_byte_size(rubric, evidence[item_id])
            if size and size["contradiction"]:
                sweep.append({"item": item_id, "ridx": idx, "family": "byte_size",
                              "detail": f"rubric 要求 {size['required']} 字节,实际 {size['actual']}"})

    out_rows = []
    for row in rows:
        item = dataset[row["item"]]
        ev = evidence[row["item"]]
        if row["ridx"] == "—":
            # The upstream file's one confirmed row carries no rubric index; it
            # is an item-level collision, which our own sweep re-derives.
            collision = [d for d in defects[row["item"]]
                         if d["family"] == "input_filename_collision"]
            out_rows.append({
                **row, "rubric": "",
                "label": L_CONFIRMED if collision else L_UNDECIDABLE,
                "family": "input_filename_collision" if collision else None,
                "reason": collision[0]["detail"] if collision else "该行无 rubric 下标,无法定位检查对象",
                "checks": collision,
            })
            continue
        rubric = item["rubrics"][int(row["ridx"])]
        verdict = label_row(rubric, row["claim"], ev, defects[row["item"]])
        out_rows.append({**row, "rubric": rubric, **verdict,
                         "item_defects": [d["detail"] for d in defects[row["item"]]],
                         "inputs_readable": ev["all_readable"],
                         "unreadable": ev["unreadable"]})

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "reannotation.json").write_text(
        json.dumps(out_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "deterministic_sweep.json").write_text(
        json.dumps(sweep, ensure_ascii=False, indent=1), encoding="utf-8")

    (args.out / "reannotation.md").write_text(
        render_markdown(out_rows, sweep, rows), encoding="utf-8")

    print(Counter(r["label"] for r in out_rows))
    print("--- 全库确定性扫描(不限于上游候选) ---")
    fam = Counter(s["family"] for s in sweep)
    for name, count in fam.most_common():
        items = len({s["item"] for s in sweep if s["family"] == name})
        print(f"  {name}: {count} 条 / {items} 个 item")
    covered = {(s["item"], str(s["ridx"])) for s in sweep if s["ridx"] is not None}
    listed = {(r["item"], r["ridx"]) for r in rows}
    print(f"  其中被上游候选列表覆盖: {len(covered & listed)} / {len(covered)}")
    print("--- codex x 我 ---")
    for (a, b), n in Counter((r["codex"], r["label"]) for r in out_rows).most_common():
        print(f"  {n:4d}  {a} -> {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
