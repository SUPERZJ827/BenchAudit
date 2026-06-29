#!/usr/bin/env python3
"""Equal-budget LLM baseline (B41).

Gives the single-pass naive / taxonomy prompt the SAME per-item call budget as
BenchAudit by sampling it N times at temperature>0, then aggregates the N votes
two ways:
  - union:           flag if ANY of the N calls flags a defect (recall-max).
  - self_consistency: flag by strict majority of the N calls.

This isolates whether BenchAudit's gain comes from structured decomposition or
merely from spending more LLM calls. Reuses prompts/metrics from
run_direct_llm_baseline.py.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

_spec = importlib.util.spec_from_file_location(
    "direct_baseline", PROJECT_ROOT / "scripts" / "run_direct_llm_baseline.py")
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)

from benchcore.llm_client import LLMClient, load_llm_config


def vote_item(item, client, prompt, n):
    user = db.build_user_prompt(item)
    try:
        results = client.chat_json_multi(prompt, user)
    except Exception as e:  # keep the item, count as no-defect
        return {"id": item["id"], "votes": [], "n_yes": 0, "error": str(e)}
    votes = [bool(r.get("has_defect", False)) for r in results]
    return {"id": item["id"], "votes": votes, "n_yes": sum(votes), "n": len(votes)}


def aggregate(rows, truth, n):
    maj_threshold = n // 2 + 1  # strict majority
    out = {}
    for mode, pred_fn in [
        ("union", lambda r: r["n_yes"] >= 1),
        ("self_consistency", lambda r: r["n_yes"] >= maj_threshold),
    ]:
        preds = {r["id"]: pred_fn(r) for r in rows}
        out[mode] = {
            "predicted_defects": sum(preds.values()),
            **db.compute_metrics(preds, truth),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--truth-field", default="metadata.error_type")
    ap.add_argument("--truth-clean-value", action="append", dest="clean_values", default=[])
    ap.add_argument("--manifest", help="Manifest JSON to select a subset of items")
    ap.add_argument("--n-votes", type=int, required=True)
    ap.add_argument("--vote-temp", type=float, default=0.3)
    ap.add_argument("--with-taxonomy", action="store_true")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    clean_values = args.clean_values or ["ok"]
    prompt = db.TAXONOMY_SYSTEM_PROMPT if args.with_taxonomy else db.SYSTEM_PROMPT

    cfg = load_llm_config(str(PROJECT_ROOT / "configs" / "llm_deepseek.json"))
    cfg.n_votes = args.n_votes
    cfg.vote_temperature = args.vote_temp
    cfg.cache_path = f"reports/{args.tag}_eqbudget_cache.jsonl"
    client = LLMClient(cfg)

    items, truth = db.load_items_with_truth(
        args.input, args.manifest, args.truth_field, clean_values)
    if args.limit:
        items = items[:args.limit]
        truth = {it["id"]: truth[it["id"]] for it in items}
    print(f"Loaded {len(items)} items | defects: {sum(truth.values())} | "
          f"N={args.n_votes} taxonomy={args.with_taxonomy}", flush=True)

    rows, start = [], time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(vote_item, it, client, prompt, args.n_votes): it["id"] for it in items}
        done = 0
        for fut in as_completed(futs):
            rows.append(fut.result()); done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(items)} ({time.time()-start:.0f}s)", flush=True)
    print(f"Done {len(rows)} items in {time.time()-start:.0f}s", flush=True)

    agg = aggregate(rows, truth, args.n_votes)
    out = {
        "baseline": ("taxonomy" if args.with_taxonomy else "naive") + "_equal_budget",
        "input_path": args.input, "n_votes": args.n_votes, "vote_temp": args.vote_temp,
        "items": len(items), "truth_defects": sum(truth.values()),
        "aggregations": agg,
        "per_item": rows,
    }
    out_path = PROJECT_ROOT / "reports" / f"{args.tag}_eqbudget_comparison.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    for mode, m in agg.items():
        print(f"{mode:17} P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} "
              f"(flagged {m['predicted_defects']})")
    print(f"wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
