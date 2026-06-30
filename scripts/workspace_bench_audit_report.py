#!/usr/bin/env python3
"""Generate a boss-facing audit report of suspicious rubrics in Workspace-Bench.

Principle (same as BenchAudit's cross-signal corroboration): a rubric that almost
every capable model independently fails is a strong candidate for a *bad rubric*
(wrong expected value / ambiguous task / over-strict check). Stage 2 inspects the
failing agents' evidence: if they converge on a consistent ALTERNATIVE value, the
rubric value is likely wrong; if they fail in scattered ways, the task may just be
hard. No input files or extra API calls needed -- mined from existing run logs.
"""
import re, json, collections, sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "Workspace-Bench Case Learning.md")
text = path.read_text(encoding="utf-8")
cases = re.split(r"\n## (?=仓敏)", text)
FAIL_THRESHOLD = 0.2   # suspicious if <=20% of runs pass
MIN_RUNS = 3


def clean(s):
    return re.sub(r"\\", "", s).strip()


def parse_runs(block):
    """Return list of (model_label, rubrics_list) for any code-fence format."""
    runs = []
    # each run starts with a level-3 heading then a fenced block
    for sec in re.split(r"\n### ", block)[1:]:
        label = clean(sec.split("\n", 1)[0])
        m = re.search(r"```[a-zA-Z]*\n(.*?)```", sec, re.S)
        if not m:
            continue
        raw = m.group(1)
        am = re.search(r'"rubrics"\s*:\s*(\[.*\])', raw, re.S)
        if not am:
            continue
        try:
            runs.append((label, json.loads(am.group(1))))
        except Exception:
            continue
    return runs


def numeric(rubric_text):
    return bool(re.search(r"\d", rubric_text)) and not re.search(r"工作表|文件名|sheet|格式|表头|命名|包含名为", rubric_text)


def converged_alt(rubric_text, fail_evidences):
    """Numbers that recur across failing runs but are NOT in the rubric text."""
    in_rubric = set(re.findall(r"\d[\d,\.]*", rubric_text.replace(",", "")))
    counter = collections.Counter()
    for ev in fail_evidences:
        for n in re.findall(r"\d[\d,\.]*", ev.replace(",", "")):
            if len(n) >= 2 and n not in in_rubric:
                counter[n] += 1
    return [(n, c) for n, c in counter.most_common(4) if c >= 2]


out = ["# Workspace-Bench 可疑 rubric 审计报告",
       "",
       "> 方法:把每条 rubric 在多个 agent+模型上的过/不过汇总。**被绝大多数模型一致判错的 rubric** 是\"坏 rubric\"的高度疑似(值错/任务歧义/过严)。第二阶段看失败 agent 的证据是否**一致指向另一个值**——若是,rubric 值很可能错;若失败方式分散,可能只是任务难。仅用现有运行日志,无需输入文件或额外调用。",
       ""]
summary = []
detail = []
for c in cases:
    name = clean(c.split("\n", 1)[0])
    if not name.startswith("仓敏"):
        continue
    runs = parse_runs(c)
    if not runs:
        continue
    passes = collections.defaultdict(list)
    rtext, evid = {}, collections.defaultdict(list)
    for label, rubrics in runs:
        for r in rubrics:
            i = r.get("index")
            if i is None:
                continue
            ok = bool(r.get("passed"))
            passes[i].append(ok)
            rtext[i] = r.get("rubric", "")
            if not ok:
                evid[i].append((label, r.get("evidence", "")))
    susp = [(i, sum(v), len(v)) for i, v in passes.items()
            if len(v) >= MIN_RUNS and sum(v) / len(v) <= FAIL_THRESHOLD]
    summary.append((name, len(passes), len(runs), len(susp)))
    if not susp:
        continue
    detail.append(f"\n## {name}（{len(runs)} 个模型运行，{len(susp)} 条可疑 rubric）\n")
    for i, npass, ntot in sorted(susp):
        kind = "数值断言" if numeric(rtext[i]) else "结构/格式"
        alt = converged_alt(rtext[i], [e for _, e in evid[i]])
        detail.append(f"### #{i} [{npass}/{ntot} 模型通过] · {kind}")
        detail.append(f"- **rubric**: {rtext[i]}")
        if alt and kind == "数值断言":
            altstr = "; ".join(f"{n}（{c}个模型）" for n, c in alt)
            detail.append(f"- **🔴 多模型一致算出另一个值**: {altstr} → rubric 期望值很可能错")
        detail.append("- 失败模型证据(样本):")
        for label, ev in evid[i][:3]:
            detail.append(f"    - `{label}`: {clean(ev)[:130]}")
        detail.append("")

out.append("## 概览\n")
out.append("| Case | rubric 数 | 模型运行数 | 可疑 rubric 数 |")
out.append("|---|--:|--:|--:|")
for name, nr, nrun, ns in summary:
    out.append(f"| {name} | {nr} | {nrun} | **{ns}** |")
out.append(f"\n**合计可疑 rubric:{sum(s[3] for s in summary)}**(覆盖 {len(summary)} 个 case)")
out.append("\n> 注:运行数 <3 的 case 不下结论(样本不足)。被所有模型判错≠一定是坏 rubric——需看第二阶段证据是否一致指向另一个值。\n")
out += detail
Path("reports/workspace_bench_suspicious_rubrics_20260630.md").write_text("\n".join(out), encoding="utf-8")
print("wrote reports/workspace_bench_suspicious_rubrics_20260630.md")
for name, nr, nrun, ns in summary:
    print(f"  {name}: {nr} rubrics, {nrun} runs, {ns} suspicious")
print("total suspicious:", sum(s[3] for s in summary))
