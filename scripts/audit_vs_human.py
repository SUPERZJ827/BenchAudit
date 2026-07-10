#!/usr/bin/env python3
"""E4: auditor-vs-human precision/recall over the hand-labeled ground truth.

Ground truth = reports/标注_已收集.md (40 human labels across 5 tasks). Each label is
one (task, rubric#) pair tagged 有问题/没问题 (defect / clean), plus a detector code
(B1/B2/B4/B5) on the defect ones. We re-run TODAY's full auditor (all four detectors,
each self-gating) over each labeled rubric and compare its flag to the human gold, to
report a confusion matrix + per-detector precision. Rubric #N is a 1-based index into
the task's rubric list (verified against known cases: id=23 #6→"27 pending",
#7→"6 approved"; id=33 #4→"1,057 tertiary", #15-17→worksheet names).

Run:  /home/zhoujun/llmdata/.venv/bin/python scripts/audit_vs_human.py
"""
from __future__ import annotations

import collections, importlib.util, json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

_a = importlib.util.spec_from_file_location("aa", REPO / "scripts" / "auditor_agent.py")
A = importlib.util.module_from_spec(_a); _a.loader.exec_module(A)

LABELS = REPO / "reports" / "标注_已收集.md"
# "- id=23 #6 **有问题** B2　..."  /  "- id=33 #1 **没问题** 　..."   (整任务/#None lines are skipped)
LINE = re.compile(r"-\s*id=(\d+)\s+#(\d+)\s+\*\*(有问题|没问题)\*\*\s*(B\d)?")


def parse_labels():
    """-> list of (id, rnum, gold_defect, human_detector|None). Dedup on (id,rnum)."""
    seen: dict[tuple[int, int], tuple] = {}
    for ln in LABELS.read_text(encoding="utf-8").splitlines():
        m = LINE.search(ln)
        if not m:
            continue
        cid, rnum, verdict, det = int(m[1]), int(m[2]), m[3], m[4]
        gold = verdict == "有问题"
        key = (cid, rnum)
        rec = (cid, rnum, gold, det)
        if key in seen and seen[key][2:] != rec[2:]:
            print(f"  ! conflicting labels for id={cid} #{rnum}: {seen[key]} vs {rec}", file=sys.stderr)
        seen.setdefault(key, rec)
    return sorted(seen.values())


def run_all_detectors(item1, single, vote3, vote5):
    """Union of the four detectors on a single-rubric item -> set of detectors that fired."""
    fired = set()
    for det, flags in (("B1", A.exec_B1(item1, single, vote5)),
                       ("B2", A.exec_B2(item1, vote5)),
                       ("B4", A.exec_B4(item1, vote3)),
                       ("B5", A.exec_B5(item1, vote3))):
        if flags:
            fired.add(det)
    return fired


def main():
    single = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek.json")))
    vote3 = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek_vote3.json")))
    vote5 = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek_vote5.json")))

    labels = parse_labels()
    print(f"parsed {len(labels)} labeled (task,rubric) pairs "
          f"({sum(x[2] for x in labels)} defect / {sum(not x[2] for x in labels)} clean)\n")

    items: dict[int, A.Item] = {}
    conf = {"TP": 0, "FP": 0, "TN": 0, "FN": 0}
    det_prec = collections.defaultdict(lambda: {"fire": 0, "correct": 0})  # auditor-side precision
    det_recall = collections.defaultdict(lambda: {"gold": 0, "caught": 0})  # human-attributed recall
    rows = []
    for cid, rnum, gold, hdet in labels:
        if cid not in items:
            items[cid] = A.load_hf_item(cid)
        item = items[cid]
        if rnum > len(item["rubrics"]):
            print(f"  ! id={cid} #{rnum} out of range ({len(item['rubrics'])} rubrics) -- skip", file=sys.stderr)
            continue
        rubric = item["rubrics"][rnum - 1]
        item1 = A.Item({**item, "rubrics": [rubric]})
        fired = run_all_detectors(item1, single, vote3, vote5)
        flagged = bool(fired)

        cell = ("TP" if flagged else "FN") if gold else ("FP" if flagged else "TN")
        conf[cell] += 1
        for d in fired:
            det_prec[d]["fire"] += 1
            if gold:
                det_prec[d]["correct"] += 1
        if gold and hdet:
            det_recall[hdet]["gold"] += 1
            if flagged:
                det_recall[hdet]["caught"] += 1

        ok = "✅" if cell in ("TP", "TN") else "❌"
        rows.append({"id": cid, "rnum": rnum, "gold": gold, "human_det": hdet,
                     "fired": sorted(fired), "cell": cell, "rubric": rubric[:80]})
        print(f"{ok} [{cell}] id={cid:<4} #{rnum:<2} gold={'DEF' if gold else 'ok '} "
              f"human={hdet or '--':<2} auditor={','.join(sorted(fired)) or '--':<8} {rubric[:52]}")

    P = conf["TP"] / (conf["TP"] + conf["FP"]) if conf["TP"] + conf["FP"] else float("nan")
    R = conf["TP"] / (conf["TP"] + conf["FN"]) if conf["TP"] + conf["FN"] else float("nan")
    F1 = 2 * P * R / (P + R) if P + R else float("nan")
    n = sum(conf.values())
    acc = (conf["TP"] + conf["TN"]) / n if n else float("nan")

    print("\n=== overall (auditor flag vs human gold) ===")
    print(f"  TP={conf['TP']} FP={conf['FP']} TN={conf['TN']} FN={conf['FN']}")
    print(f"  Precision={P:.3f}  Recall={R:.3f}  F1={F1:.3f}  Acc={acc:.3f}  (n={n})")

    print("\n=== auditor-side precision by detector (of the rubrics this detector fired on) ===")
    for d in sorted(det_prec):
        c = det_prec[d]
        p = c["correct"] / c["fire"] if c["fire"] else float("nan")
        print(f"  {d}: fired={c['fire']}  correct={c['correct']}  precision={p:.3f}")

    print("\n=== recall by human-attributed detector (did the auditor catch it, any detector) ===")
    for d in sorted(det_recall):
        c = det_recall[d]
        r = c["caught"] / c["gold"] if c["gold"] else float("nan")
        print(f"  {d}: gold_defects={c['gold']}  caught={c['caught']}  recall={r:.3f}")

    out = {"n": n, "confusion": conf,
           "overall": {"precision": P, "recall": R, "f1": F1, "accuracy": acc},
           "det_precision": {d: dict(v) for d, v in det_prec.items()},
           "det_recall": {d: dict(v) for d, v in det_recall.items()},
           "rows": rows}
    (REPO / "reports" / "auditor_vs_human.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote reports/auditor_vs_human.json")


if __name__ == "__main__":
    main()
