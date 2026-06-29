"""Bootstrap 95% CIs for the MMLU-Redux 1000 candidate/priority metrics.

Reconstructs the full 1000-item confusion matrix from the saved comparison
report (truth_labels + candidate_ranking) and resamples items with replacement
to estimate confidence intervals. No new API calls.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
REPORT = REPO / "reports" / "mmlu_redux_pilot1000_v1_20260627_comparison.json"
N_TOTAL = 1000
B = 10000
SEED = 20260629


def build_items() -> list[tuple[int, int, int]]:
    """Return per-item (is_defect, pred_candidate, pred_priority) for all 1000."""
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    truth = d["truth_labels"]                       # 512 relevant items
    ranking = d["candidate_ranking"]                # 396 predicted positives
    cand_ids = {r["item_id"] for r in ranking}
    prio_ids = {r["item_id"] for r in ranking if r["tier"] == "priority"}

    items: list[tuple[int, int, int]] = []
    for iid, label in truth.items():
        is_def = 1 if label != "ok" else 0
        items.append((is_def, 1 if iid in cand_ids else 0, 1 if iid in prio_ids else 0))
    # remaining clean true-negatives (predicted negative) to fill the 1000 universe
    for _ in range(N_TOTAL - len(items)):
        items.append((0, 0, 0))
    assert len(items) == N_TOTAL, len(items)
    return items


def metrics(sample: np.ndarray) -> dict[str, float]:
    is_def, pc, pp = sample[:, 0], sample[:, 1], sample[:, 2]
    tp = int(((is_def == 1) & (pc == 1)).sum())
    fp = int(((is_def == 0) & (pc == 1)).sum())
    fn = int(((is_def == 1) & (pc == 0)).sum())
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    n_def = int((is_def == 1).sum())
    prio_r = int(((is_def == 1) & (pp == 1)).sum()) / n_def if n_def else 0.0
    return {"cand_P": p, "cand_R": r, "cand_F1": f1, "prio_R": prio_r}


def main() -> None:
    arr = np.array(build_items())
    point = metrics(arr)
    rng = np.random.default_rng(SEED)
    keys = ["cand_P", "cand_R", "cand_F1", "prio_R"]
    boot = {k: [] for k in keys}
    for _ in range(B):
        idx = rng.integers(0, N_TOTAL, N_TOTAL)
        m = metrics(arr[idx])
        for k in keys:
            boot[k].append(m[k])

    print(f"Bootstrap 95% CI (B={B}, n={N_TOTAL}, MMLU-Redux v1)\n")
    print(f"{'metric':9} {'point':>7} {'mean':>7} {'2.5%':>7} {'97.5%':>7}")
    out = {}
    for k in keys:
        vals = boot[k]
        lo, hi = np.percentile(vals, [2.5, 97.5])
        print(f"{k:9} {point[k]:7.3f} {statistics.mean(vals):7.3f} {lo:7.3f} {hi:7.3f}")
        out[k] = {"point": round(point[k], 3), "ci95": [round(float(lo), 3), round(float(hi), 3)]}
    (REPO / "reports" / "bootstrap_ci_mmlu1000_20260629.json").write_text(
        json.dumps({"B": B, "n": N_TOTAL, "metrics": out}, indent=2), encoding="utf-8")
    print("\nwrote reports/bootstrap_ci_mmlu1000_20260629.json")


if __name__ == "__main__":
    main()
