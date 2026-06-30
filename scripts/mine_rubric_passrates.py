#!/usr/bin/env python3
"""Mine per-rubric cross-model pass rates from Workspace-Bench case logs.

The case file records, for every (case, model-run), per-rubric pass/fail and the
agent's evidence. A rubric that almost every capable model fails is a strong
candidate for being a *bad rubric* (wrong expected value, ambiguous task, or
over-strict check) -- surfaced for free, no input files needed. This is the
cross-model corroboration idea applied to an agentic benchmark.
"""
import re, json, collections, sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "Workspace-Bench Case Learning.md")
text = path.read_text(encoding="utf-8")
cases = re.split(r"\n## ", text)


def parse_rubrics(block):
    out = []
    for m in re.finditer(r"```JSON(.*?)```", block, re.S):
        raw = m.group(1).strip()
        try:
            arr = re.search(r'"rubrics"\s*:\s*(\[.*\])', raw, re.S).group(1)
            out.append(json.loads(arr))
        except Exception:
            continue
    return out


def clean(s):
    return re.sub(r"\\", "", s).strip()


total_suspicious = 0
print(f"{'case':10} {'#rub':>5} {'#runs':>6}  suspicious rubrics (failed by >=80% of runs)")
for c in cases:
    name = clean(c.split("\n", 1)[0])
    if not re.match(r"[\u4e00-\u9fff]{2,5}_\d", name):
        continue
    runs = parse_rubrics(c)
    if not runs:
        continue
    passes = collections.defaultdict(list)
    rtext = {}
    for run in runs:
        for r in run:
            i = r.get("index")
            if i is None:
                continue
            passes[i].append(1 if r.get("passed") else 0)
            rtext[i] = r.get("rubric", "")
    susp = [(i, sum(v) / len(v)) for i, v in passes.items() if len(v) >= 3 and sum(v) / len(v) <= 0.2]
    total_suspicious += len(susp)
    print(f"{name:10} {len(passes):5} {len(runs):6}  {len(susp)} suspicious")
    for i, pr in sorted(susp):
        print(f"   [#{i} pass={pr:.0%}] {rtext[i][:70]}")
print(f"\nTOTAL suspicious rubrics across cases: {total_suspicious}")
