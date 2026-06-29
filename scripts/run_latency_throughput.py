"""Latency/throughput benchmark for the BenchAudit pipeline.

Runs the same audit workload (gold,question,option cascade) at several worker
concurrency levels, each with a fresh cache (forced cache-miss), and records
wall-clock time and realized throughput. Used for the paper's Efficiency section.

Results are written incrementally (after each worker level) and each level is
isolated, so a failure in one run does not discard the others.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INPUT = REPO / "experiments" / "mmlu_redux_pilot1000.jsonl"
CONFIG = REPO / "configs" / "llm_deepseek.json"
WORKER_LEVELS = [1, 4, 8, 16]


def run_one(workers: int, n_items: int, scratch: Path) -> dict:
    cache = scratch / f"lat_cache_n{n_items}_w{workers}.jsonl"
    report = scratch / f"lat_report_n{n_items}_w{workers}.json"
    if cache.exists():
        cache.unlink()  # force cache-miss
    cmd = [
        sys.executable, "-m", "benchcore.cli", "audit", str(INPUT),
        "--limit", str(n_items),
        "--llm-audit", "--llm-auditors", "gold,question,option",
        "--llm-config", str(CONFIG),
        "--llm-cache", str(cache),
        "--workers", str(workers),
        "--out", str(report),
    ]
    t0 = time.perf_counter()
    subprocess.run(cmd, cwd=str(REPO), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wall = time.perf_counter() - t0
    calls = sum(1 for _ in cache.open(encoding="utf-8"))
    return {
        "workers": workers,
        "items": n_items,
        "wall_clock_s": round(wall, 2),
        "calls": calls,
        "calls_per_item": round(calls / n_items, 2),
        "items_per_s": round(n_items / wall, 4),
        "calls_per_s": round(calls / wall, 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24, help="items to audit")
    ap.add_argument("--out", required=True, help="results JSON path")
    ap.add_argument("--scratch", default=str(REPO / "reports"),
                    help="dir for per-run caches/reports")
    args = ap.parse_args()

    scratch = Path(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    out = Path(args.out)

    results, base = [], None
    for w in WORKER_LEVELS:
        try:
            r = run_one(w, args.n, scratch)
        except Exception as exc:  # keep partial results on failure
            print(json.dumps({"workers": w, "error": str(exc)}), flush=True)
            continue
        if base is None:
            base = r["wall_clock_s"]
        r["speedup_vs_w1"] = round(base / r["wall_clock_s"], 2)
        results.append(r)
        print(json.dumps(r), flush=True)
        out.write_text(json.dumps({"n_items": args.n, "runs": results}, indent=2),
                       encoding="utf-8")  # incremental save
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
