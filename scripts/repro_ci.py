#!/usr/bin/env python3
"""E1: bootstrap confidence intervals on the reproducibility P_hat, per case.

Given a repro_confidence*.json (produced by repro_confidence.py, which stores per-run
defect-vote fractions in by_temp[T].run_fracs), we resample the K runs WITH replacement
B times and take the mean each time -> a 95% CI on P_hat that respects run-level structure
(votes within a run are correlated; runs are the independent unit). The paper claim this
tests: id=33 (hard real defect) sits ON the 0.5 decision boundary -- its CI CONTAINS 0.5 --
while stable cases' CIs sit near 0 or 1. Also reports the flip rate over cases.

Run:  python scripts/repro_ci.py [reports/repro_confidence_k30.json]
"""
from __future__ import annotations

import json, sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
B = 10000


def ci(run_fracs, rng):
    a = np.asarray(run_fracs, dtype=float)
    if a.size == 0:
        return 0.0, 0.0, 0.0
    means = a[rng.integers(0, a.size, size=(B, a.size))].mean(axis=1)
    return float(a.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main():
    path = REPO / (sys.argv[1] if len(sys.argv) > 1 else "reports/repro_confidence_k30.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    rng = np.random.default_rng(0)
    temps = sorted({t for r in data for t in r["by_temp"]}, key=float)
    print(f"{path.name}  ({len(data)} cases, K={len(data[0]['by_temp'][temps[0]]['run_fracs'])}, B={B})\n")

    flips = {t: 0 for t in temps}
    for r in data:
        lbl = f"id={r['id']} {r['detector']} {r['note'][:22]}"
        cells = []
        for t in temps:
            b = r["by_temp"].get(t)
            if not b:
                cells.append(f"T{t}: --")
                continue
            p, lo, hi = ci(b["run_fracs"], rng)
            flips[t] += b["flip"]
            straddle = "★0.5" if lo <= 0.5 <= hi else "    "
            cells.append(f"T{t}: {p:.2f} [{lo:.2f},{hi:.2f}] {straddle}")
        gold = "DEF" if r["gold_defect"] else "ok "
        print(f"{lbl:<34} {gold}  " + "   ".join(cells))

    n = len(data)
    print("\nflip rate over cases:")
    for t in temps:
        print(f"  T{t}: {flips[t]}/{n} = {flips[t]/n:.0%}")
    print("\n★0.5 = 95% CI contains 0.5 (model is at the decision boundary -> non-reproducible).")


if __name__ == "__main__":
    main()
