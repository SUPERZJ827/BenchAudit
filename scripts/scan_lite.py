#!/usr/bin/env python3
"""Batch-scan Workspace-Bench-Lite with the plan-exec-eval auditor.

No ground truth exists for Lite, so this is a candidate-generation + robustness
run, not a precision measurement. Each task is isolated (one crash does not kill
the batch); results are written incrementally to reports/lite_pilot/<id>.json so a
run can be inspected mid-flight or resumed (existing per-task files are skipped).

Usage:
  python scan_lite.py [N]            # scan first N tasks (default 10)
  python scan_lite.py --ids 3,107,55 # scan specific absolute_ids
"""
import importlib.util, json, sys, time, traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
_a = importlib.util.spec_from_file_location("aa", REPO / "scripts" / "auditor_agent.py")
aa = importlib.util.module_from_spec(_a); _a.loader.exec_module(aa)
from benchcore.llm_client import LLMClient, load_llm_config


def tally(findings, status_key):
    out = {}
    for x in findings:
        if x.get("status") == status_key:
            out[x["detector"]] = out.get(x["detector"], 0) + 1
    return out


def main():
    args = sys.argv[1:]
    from datasets import load_dataset
    ds = load_dataset("Workspace-Bench/Workspace-Bench-Lite", split="lite")
    rows = [ds[i] for i in range(len(ds))]
    if args and args[0] == "--ids":
        want = {int(x) for x in args[1].split(",")}
        rows = [r for r in rows if r["absolute_id"] in want]
    else:
        n = int(args[0]) if args else 10
        rows = rows[:n]

    single = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek.json")))
    vote = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek_vote3.json")))
    vote_b1 = LLMClient(load_llm_config(str(REPO / "configs/llm_deepseek_vote5.json")))

    outdir = REPO / "reports" / "lite_pilot"
    outdir.mkdir(parents=True, exist_ok=True)
    summary = []
    for r in rows:
        aid = r["absolute_id"]
        f = outdir / f"{aid}.json"
        if f.exists():
            summary.append(json.loads(f.read_text(encoding="utf-8"))["summary"])
            print(f"[{aid}] skip (already scanned)")
            continue
        item, t0 = None, time.time()
        try:
            item = aa.load_hf_item(aid, row=r)
            report = aa.run(item, single, vote, vote_b1)
            status, err = "ok", ""
        except Exception as e:
            report = {"id": f"id={aid}", "plan": {}, "findings": []}
            status, err = "error", f"{type(e).__name__}: {e}"
            traceback.print_exc()
        s = {"id": aid, "persona": r["persona"], "diff": r["task_diff"],
             "status": status, "err": err, "secs": round(time.time() - t0, 1),
             "n_rubrics": len(item["rubrics"]) if item else None,
             "n_inputs": len(item["inputs"]) if item else None,
             "task_type": report.get("plan", {}).get("task_type"),
             "confirmed": tally(report.get("findings", []), "已确认"),
             "candidates": tally(report.get("findings", []), "候选")}
        summary.append(s)
        f.write_text(json.dumps({"summary": s, "report": report}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        print(f"[{aid}] {status} {s['secs']}s  确认={s['confirmed']} 候选={s['candidates']}")

    (outdir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print("\n==== SUMMARY ====")
    ok = sum(1 for s in summary if s["status"] == "ok")
    print(f"{ok}/{len(summary)} ok")
    for s in summary:
        print(f"  id={s['id']:>4} {str(s['diff']):<7} {s['status']:<6} "
              f"确认={s['confirmed']} 候选={s['candidates']}"
              + (f"  ERR={s['err']}" if s["err"] else ""))


if __name__ == "__main__":
    main()
