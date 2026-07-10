#!/usr/bin/env python3
"""Labeled-ground-truth regression harness for the Workspace-Bench auditor.

A small hand-verified set of (task, rubric) cases from reports/verified_defects.md:
the two confirmed real defects MUST fire, and each known false-positive class MUST
stay silent. Each case runs ONE rubric through ONE detector (by building a single-
rubric view of the item) and compares the detector's flag to the gold label, then
prints a confusion matrix per detector. This is the measurement the precision work
is optimized against -- run it before/after any detector change.

Run:  /home/zhoujun/llmdata/.venv/bin/python scripts/audit_eval.py
"""
from __future__ import annotations

import importlib.util, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, load_llm_config

_a = importlib.util.spec_from_file_location("aa", REPO / "scripts" / "auditor_agent.py")
A = importlib.util.module_from_spec(_a); _a.loader.exec_module(A)

# (case_id, rubric substring, detector, gold_is_defect, note). Labels & notes trace to
# reports/verified_defects.md; substrings uniquely identify the rubric within the case.
CASES = [
    # --- confirmed real defects (must fire) ---
    (33, "1,057 tertiary hospitals", "B1", True,  "grade dimension absent from inputs"),
    (23, "6 approved purchase orders", "B2", True, "rubric says 6, data has 7 (omits #1015)"),
    (23, "27 purchase orders pending", "B2", True, "rubric says 27, data has 29"),
    # --- known false-positive classes (must stay silent) ---
    (23, "3 inbound purchase orders", "B2", False, "rubric correct (matches Stocked In)"),
    (15, "Top 1 expense amount 534", "B2", False, "aggregation口径; rubric 534 correct"),
    (269, "total shipment amount of 1,309,880", "B2", False, "Dec reconciliation; rubric correct"),
    (328, "average recruitment cycle 19", "B2", False, "input states 19 days; rubric correct"),
    (44, "total of 120 tasks", "B2", False, "all 120 Java/React; rubric correct"),
    (388, "include a retention rate data table", "B1", False, "present as Chinese label 次日留存 (cross-language)"),
    (37, "identified as strong departments", "B4", False, "objective data-driven conclusion, not over-constraint"),
    # --- FP classes found in the 2026-07-04 broad scan (all non-defects). First four are
    #     FIXED (threshold-strip / B2_SKIP_PAT) -> expect TN; last two are documented RESIDUALS. ---
    (108, "clearly indicate that the unique order count", "B2", False, "'50' is a ≥50% threshold; 729 is the real value (rubric_values threshold-strip)"),
    (131, "table_preprocess.py file size", "B2", False, "output-artifact byte size, not input data (B2_SKIP_PAT)"),
    (227, "exactly match the source", "B2", False, "transcription-accuracy example numbers (B2_SKIP_PAT)"),
    (276, "accurately extracted the information of employee 4", "B2", False, "transcription (B2_SKIP_PAT)"),
    (357, "combined budget of the five projects", "B2", False, "RESIDUAL: rubric lists 5 components, recompute returns their total (granularity)"),
    (359, "Dental Instruments` have 2", "B2", False, "RESIDUAL: '17' is a category CODE label, not a count"),
]


def find_rubric(item, sub):
    hits = [r for r in item["rubrics"] if sub.lower() in r.lower()]
    if len(hits) != 1:
        raise SystemExit(f"substring {sub!r} matched {len(hits)} rubrics in {item['id']} (need exactly 1)")
    return hits[0]


def run_detector(item1, det, single, vote, vote_b1):
    """item1 = the item with rubrics narrowed to the single target rubric."""
    if det == "B1":
        return A.exec_B1(item1, single, vote_b1)
    if det == "B2":
        return A.exec_B2(item1, vote_b1)
    if det == "B4":
        return A.exec_B4(item1, vote)
    raise ValueError(det)


def main():
    single = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek.json")))
    vote = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek_vote3.json")))
    vote_b1 = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek_vote5.json")))

    items: dict[int, A.Item] = {}
    from collections import defaultdict
    conf = defaultdict(lambda: {"TP": 0, "FP": 0, "TN": 0, "FN": 0})
    rows = []
    for cid, sub, det, gold, note in CASES:
        if cid not in items:
            items[cid] = A.load_hf_item(cid)
        item = items[cid]
        rubric = find_rubric(item, sub)
        item1 = A.Item({**item, "rubrics": [rubric]})
        flags = run_detector(item1, det, single, vote, vote_b1)
        flagged = len(flags) > 0
        cell = ("TP" if flagged else "FN") if gold else ("FP" if flagged else "TN")
        conf[det][cell] += 1
        ok = "✅" if cell in ("TP", "TN") else "❌"
        ev = flags[0].get("evidence", "")[:70] if flags else ""
        rows.append((ok, cell, det, cid, gold, flagged, sub, ev, note))
        print(f"{ok} [{cell}] {det} id={cid} gold={'DEF' if gold else 'ok '} flag={flagged}  {sub[:34]}")
        if ev:
            print(f"        └ {ev}")

    print("\n=== confusion by detector ===")
    tot = {"TP": 0, "FP": 0, "TN": 0, "FN": 0}
    for det, c in sorted(conf.items()):
        for k in tot: tot[k] += c[k]
        p = c["TP"] / (c["TP"] + c["FP"]) if (c["TP"] + c["FP"]) else float("nan")
        r = c["TP"] / (c["TP"] + c["FN"]) if (c["TP"] + c["FN"]) else float("nan")
        print(f"  {det}: TP={c['TP']} FP={c['FP']} TN={c['TN']} FN={c['FN']}  P={p:.2f} R={r:.2f}")
    P = tot["TP"] / (tot["TP"] + tot["FP"]) if (tot["TP"] + tot["FP"]) else float("nan")
    R = tot["TP"] / (tot["TP"] + tot["FN"]) if (tot["TP"] + tot["FN"]) else float("nan")
    acc = (tot["TP"] + tot["TN"]) / len(CASES)
    print(f"  ALL: TP={tot['TP']} FP={tot['FP']} TN={tot['TN']} FN={tot['FN']}  "
          f"P={P:.2f} R={R:.2f} acc={acc:.2f} ({tot['TP']+tot['TN']}/{len(CASES)})")


if __name__ == "__main__":
    main()
