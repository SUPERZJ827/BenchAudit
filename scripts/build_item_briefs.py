"""Build per-item briefing packets so the annotation can be made by *reading*
the real task, contract and input contents rather than by string matching.

The script does retrieval only; every judgement is made by the human/model
reading the packet.  Output: reports/workspace_reannotation/briefs/<item>.md
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from benchcore.file_reader import read_file_result  # noqa: E402

DATASET = ROOT / "datasets/workspacebench/full.jsonl"
CANDIDATES = ROOT / "reports/workspace_reannotation/reannotation.json"
OUT = ROOT / "reports/workspace_reannotation/briefs"

INPUT_HEAD = 600       # chars of each input file shown inline
INPUT_BUDGET = 4000    # total chars of input excerpts per item
SNIPPET = 90           # context chars around a retrieval hit

# Salient terms to look up: quoted literals, and CJK/Latin phrases long enough
# to be discriminative.
QUOTED_RE = re.compile(r"[`\"'“‘《]([^`\"'”’》]{2,80})[`\"'”’》]")
CJK_RE = re.compile(r"[一-鿿]{3,}")
CAP_RE = re.compile(r"\b(?:[A-Z][\w\-]+(?:\s+(?:of|for|and|the|in|to)\s+)?){2,}")
STOP = {"the", "and", "for", "output", "file", "does", "the output file"}


def load_dataset():
    return {json.loads(l)["item_id"]: json.loads(l) for l in DATASET.open(encoding="utf-8")}


def load_candidates():
    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    rows = data["rows"] if isinstance(data, dict) else data
    by_item = {}
    for r in rows:
        by_item.setdefault(r["item"], []).append(r)
    return by_item


def logical_names(item):
    """stored basename -> logical filename declared in data_manifest."""
    man = item.get("data_manifest")
    if isinstance(man, str):
        man = json.loads(man)
    return {Path(e["stored_relpath"]).name: e["filename"] for e in (man or [])}


def input_texts(item):
    """Return [(name, status, size, text)] for every input file."""
    out, logical = [], logical_names(item)
    for p in item.get("input_files") or []:
        path = Path(p)
        size = path.stat().st_size if path.exists() else -1
        try:
            res = read_file_result(p)
            status, text = res.status, res.text
        except Exception as exc:  # a reader crash is evidence too
            status, text = f"error:{type(exc).__name__}", ""
        out.append((logical.get(path.name, path.name), status, size, text))
    return out


def terms(rubric):
    found = []
    for m in QUOTED_RE.finditer(rubric):
        found.append(m.group(1).strip())
    for m in CJK_RE.finditer(rubric):
        found.append(m.group(0))
    for m in CAP_RE.finditer(rubric):
        t = m.group(0).strip()
        if len(t) > 8:
            found.append(t)
    seen, out = set(), []
    for t in found:
        k = t.lower()
        if k in STOP or k in seen or len(t) < 3:
            continue
        seen.add(k)
        out.append(t)
    return out[:8]


def lookup(term, haystacks):
    """haystacks: [(label, text)] -> list of 'label×n: …snippet…'"""
    hits = []
    low = term.lower()
    for label, text in haystacks:
        tl = text.lower()
        n = tl.count(low)
        if not n:
            continue
        i = tl.find(low)
        snip = text[max(0, i - SNIPPET // 2): i + len(term) + SNIPPET // 2]
        snip = " ".join(snip.split())
        hits.append(f"{label}×{n}: …{snip}…")
    return hits


def render(item_id, item, cands):
    inputs = input_texts(item)
    haystacks = [("task", item["task"]),
                 ("contract", json.dumps(item.get("output_contract"), ensure_ascii=False))]
    haystacks += [(f"in:{n}", t) for n, _, _, t in inputs]
    haystacks.append(("filenames", "\n".join(n for n, _, _, _ in inputs)))

    L = [f"# {item_id}", "", "## TASK", item["task"].strip(), "",
         "## OUTPUT CONTRACT", "```json",
         json.dumps(item.get("output_contract"), ensure_ascii=False, indent=1), "```", "",
         f"## INPUT FILES ({len(inputs)})"]
    budget = INPUT_BUDGET
    for name, status, size, text in inputs:
        head = " ".join(text[:INPUT_HEAD].split())
        if budget <= 0:
            head = "(预算耗尽,未展示)"
        else:
            head = head[:budget]
            budget -= len(head)
        L += [f"- **{name}** [{status}, {size}B, textlen={len(text)}]", f"  > {head}"]
    rtypes = item.get("rubric_types")
    if isinstance(rtypes, str):
        rtypes = json.loads(rtypes)
    rtypes = rtypes or []
    L += ["", f"## 全部 rubrics ({len(item['rubrics'])})"]
    cand_idx = {int(c["ridx"]) for c in cands if str(c.get("ridx", "")).isdigit()}
    for i, r in enumerate(item["rubrics"]):
        mark = " **<<候选**" if i in cand_idx else ""
        t = f"[{rtypes[i]}] " if i < len(rtypes) else ""
        L.append(f"{i}. {t}{' '.join(r.split())[:300]}{mark}")

    L += ["", "## 候选逐条(含关键词检索)"]
    for c in cands:
        L += [f"### {item_id}#{c.get('ridx')}  上游={c.get('codex', '')}",
              f"- rubric: {' '.join(str(c.get('rubric', '')).split())}",
              f"- codex claim: {c.get('claim', '')}"]
        rub = str(c.get("rubric") or "")
        for t in terms(rub):
            hits = lookup(t, haystacks)
            L.append(f"  - `{t}` → " + ("; ".join(hits[:3]) if hits else "**四处皆无**"))
    return "\n".join(L)


def main():
    ds, by_item = load_dataset(), load_candidates()
    OUT.mkdir(parents=True, exist_ok=True)
    order = sorted(by_item, key=lambda i: int(i.split("-")[1]))
    for item_id in order:
        (OUT / f"{item_id}.md").write_text(
            render(item_id, ds[item_id], by_item[item_id]), encoding="utf-8")
    print(f"wrote {len(order)} briefs to {OUT}")
    (OUT / "_order.json").write_text(json.dumps(order), encoding="utf-8")


if __name__ == "__main__":
    main()
