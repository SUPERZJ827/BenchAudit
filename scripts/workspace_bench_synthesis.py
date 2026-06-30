#!/usr/bin/env python3
"""Synthesize three independent signals into a high-confidence bad-rubric report.

Signals (each independent):
  S1 cross-model pass rate  : rubric failed by >=80% of model runs (from logs)
  S2 data-grounded verify   : rubric value not_in_inputs / likely_wrong (vs real xlsx)
  S3 semantic auditor       : over_constrained / brittle / answer_leakage / etc.

A rubric hit by >=2 signals is a high-confidence bad rubric. This is BenchAudit's
multi-signal corroboration applied to an agentic benchmark.
"""
from __future__ import annotations

import json, re, collections
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEXT = (REPO / "Workspace-Bench Case Learning.md").read_text(encoding="utf-8")
cases_raw = re.split(r"\n## ", TEXT)


def clean(s):
    return re.sub(r"\\", "", s).strip()


def parse(block):
    name = clean(block.split("\n", 1)[0])
    # canonical rubric list (order == index)
    rm = re.search(r"### Rubrics(.*?)(?=\n### |\Z)", block, re.S)
    rubrics = [clean(q) for q in re.findall(r'"((?:[^"\\]|\\.)*)"', rm.group(1))] if rm else []
    rubrics = [r for r in rubrics if len(r) > 8]
    # S1: per-index pass rate from run logs
    passes = collections.defaultdict(list)
    for sec in re.split(r"\n### ", block)[1:]:
        m = re.search(r"```[a-zA-Z]*\n(.*?)```", sec, re.S)
        if not m:
            continue
        am = re.search(r'"rubrics"\s*:\s*(\[.*\])', m.group(1), re.S)
        if not am:
            continue
        try:
            for r in json.loads(am.group(1)):
                if r.get("index") is not None:
                    passes[r["index"]].append(1 if r.get("passed") else 0)
        except Exception:
            pass
    return name, rubrics, passes


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else None


sem = load_json(REPO / "reports/rubric_semantic_audit_20260630.json") or {}

report = ["# Workspace-Bench 高置信坏 rubric 总报告(三信号合成)", "",
          "> S1 跨模型通过率 · S2 数据落地核验 · S3 语义审计。**被 ≥2 个独立信号命中 = 高置信坏 rubric。**", ""]
summary = []
detail = []
for block in cases_raw:
    if not re.match(r"[\u4e00-\u9fff]{2,5}\\?_\d", block.lstrip()[:8]):
        continue
    name, rubrics, passes = parse(block)
    if not rubrics:
        continue
    dv = load_json(REPO / f"reports/rubric_data_verify_{name}_20260630.json") or []
    dv_by_text = {clean(d["rubric"]): d for d in dv}
    sem_issues = collections.defaultdict(list)
    for it in (sem.get(name, {}) or {}).get("issues", []):
        if it.get("severity") in ("high", "medium"):
            sem_issues[it.get("rubric_index")].append(it)

    flagged = []
    for i, rtext in enumerate(rubrics):
        sig = []
        pr = passes.get(i, [])
        if len(pr) >= 3 and sum(pr) / len(pr) <= 0.2:
            sig.append(("S1", f"{sum(pr)}/{len(pr)}模型通过"))
        d = dv_by_text.get(rtext)
        if d and d.get("verdict") in ("not_in_inputs", "likely_wrong"):
            sig.append(("S2", f"{d['verdict']}: {d.get('reason','')[:60]}"))
        if sem_issues.get(i):
            it = sem_issues[i][0]
            sig.append(("S3", f"{it.get('defect_type')}: {it.get('reason','')[:60]}"))
        if sig:
            flagged.append((i, rtext, sig))
    high = [f for f in flagged if len(f[2]) >= 2]
    summary.append((name, len(rubrics), len(flagged), len(high)))
    if not flagged:
        continue
    detail.append(f"\n## {name}（{len(rubrics)} 条 rubric｜{len(high)} 条高置信｜{len(flagged)} 条被标）\n")
    for i, rtext, sig in sorted(flagged, key=lambda x: -len(x[2])):
        tag = "🔴 高置信" if len(sig) >= 2 else "🟡"
        detail.append(f"### {tag} #{i} [{'+'.join(s[0] for s in sig)}] {rtext[:64]}")
        for s, why in sig:
            detail.append(f"  - **{s}** {why}")
        detail.append("")

report.append("## 概览\n")
report.append("| Case | rubric 数 | 被标 | **高置信(≥2信号)** |")
report.append("|---|--:|--:|--:|")
for name, nr, nf, nh in summary:
    report.append(f"| {name} | {nr} | {nf} | **{nh}** |")
report.append(f"\n**高置信坏 rubric 合计:{sum(s[3] for s in summary)}**（被 ≥2 个独立信号命中）\n")
report += detail
out = REPO / "reports/workspace_bench_high_confidence_defects_20260630.md"
out.write_text("\n".join(report), encoding="utf-8")
print("wrote", out.name)
for name, nr, nf, nh in summary:
    print(f"  {name}: {nr} rubrics, {nf} flagged, {nh} high-confidence")
print("total high-confidence:", sum(s[3] for s in summary))
