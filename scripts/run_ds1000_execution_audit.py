#!/usr/bin/env python3
"""DS-1000 execution-grounded evaluator audit (pilot).

Runs ExecutionEvaluatorAuditChecker over DS-1000 items whose libraries are
available in a digest-pinned container (Pandas / Numpy). Per item we record
review observations plus full kill-matrix provenance, incrementally, so the run can
be inspected mid-flight and resumed.

Usage:
  run_ds1000_execution_audit.py --container-image IMAGE@sha256:DIGEST
"""
from __future__ import annotations

import argparse
import hashlib
import json, re, sys, time, traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.evaluator_execution import ExecutionEvaluatorAuditChecker
from benchcore.execution import ContainerRunner
from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.schema import BenchmarkItem

DS1000 = Path.home() / (".cache/huggingface/hub/datasets--xlangai--DS-1000/"
                        "snapshots/4416080ac5cb80bdf7576aefb8f9a0b4d5426a44/test.jsonl")
DEFAULT_OUTDIR = REPO / "reports" / "ds1000_exec_trust_split_pending"
PROTOCOL_VERSION = "ds1000-execution-review-v2"


def kill_stats(report: dict) -> dict:
    """Kill-matrix summary from the checker's raw provenance."""
    stats = {"probes": 0, "validated_equivalent": 0, "validated_mutant": 0,
             "equivalent_rejected": 0, "mutant_killed": 0, "mutant_survived": 0}
    for pr in report.get("probes", []):
        stats["probes"] += 1
        harness_pass = pr.get("harness", {}).get("pass")
        if pr["kind"] == "equivalent" and pr.get("validated_equivalent"):
            stats["validated_equivalent"] += 1
            if harness_pass is False:
                stats["equivalent_rejected"] += 1
        elif pr["kind"] == "mutant" and pr.get("validated_differs"):
            stats["validated_mutant"] += 1
            # A mutant only survives if it clears BOTH the value check and the
            # test_string surface check -- mirroring the emit gate in
            # ExecutionEvaluatorAuditChecker so the aggregate does not over-report
            # survivors that the string check actually caught.
            string_pass = pr.get("harness", {}).get("string_pass", True)
            if harness_pass is True and string_pass is not False:
                stats["mutant_survived"] += 1
            elif harness_pass is False:
                stats["mutant_killed"] += 1
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-per-lib", type=int, default=30)
    parser.add_argument("--libs", default="Pandas,Numpy")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--container-image", required=True)
    parser.add_argument("--container-engine")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTDIR))
    parser.add_argument("--gen-slack", type=int, default=2,
                        help="extra probes generated per kind beyond the "
                             "comparison-valid threshold (absorbs LLM under-"
                             "generation / dud probes; threshold unchanged)")
    parser.add_argument("--adaptive-probe-rounds", type=int, default=0,
                        help="extra execution-grounded alternate-lens rounds; "
                             "0 keeps the one-pass protocol")
    args = parser.parse_args()
    if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-fA-F]{64}", args.container_image):
        parser.error("--container-image must be digest-pinned as name@sha256:<64 hex>")
    if args.n_per_lib < 1 or args.workers < 1:
        parser.error("--n-per-lib and --workers must be positive")
    if args.gen_slack < 0 or args.adaptive_probe_rounds < 0:
        parser.error("--gen-slack and --adaptive-probe-rounds must be non-negative")
    libs = set(filter(None, args.libs.split(",")))
    workers = args.workers
    outdir = Path(args.out_dir).expanduser().resolve()
    runner = ContainerRunner(args.container_image, engine=args.container_engine)

    rows = [json.loads(l) for l in DS1000.read_text(encoding="utf-8").splitlines()]
    picked = []
    seen: dict[str, int] = {}
    for r in rows:
        lib = r["metadata"]["library"]
        if lib in libs and seen.get(lib, 0) < args.n_per_lib:
            seen[lib] = seen.get(lib, 0) + 1
            picked.append(r)
    outdir.mkdir(parents=True, exist_ok=True)
    run_signature = hashlib.sha256(json.dumps({
        "protocol": PROTOCOL_VERSION,
        "dataset_sha256": hashlib.sha256(DS1000.read_bytes()).hexdigest(),
        "implementation_sha256": hashlib.sha256(
            (REPO / "benchcore/evaluator_execution.py").read_bytes()
        ).hexdigest(),
        "container_image": args.container_image,
        "libs": sorted(libs),
        "n_per_lib": args.n_per_lib,
        "gen_slack": args.gen_slack,
        "adaptive_probe_rounds": args.adaptive_probe_rounds,
    }, sort_keys=True).encode()).hexdigest()
    (outdir / "run_manifest.json").write_text(json.dumps({
        "protocol_version": PROTOCOL_VERSION,
        "run_signature": run_signature,
        "dataset": str(DS1000),
        "dataset_sha256": hashlib.sha256(DS1000.read_bytes()).hexdigest(),
        "container_image": args.container_image,
        "evidence_policy": "shared-driver observations remain review until trust split",
    }, indent=2) + "\n", encoding="utf-8")
    cfg = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
    cfg.cache_path = "reports/ds1000_exec_llm_cache.jsonl"
    client = LLMClient(cfg)
    print(f"auditing {len(picked)} items ({seen}), workers={workers}")

    def one(r: dict) -> dict:
        pid = r["metadata"]["problem_id"]
        out = outdir / f"{pid}.json"
        if out.exists():
            prior = json.loads(out.read_text(encoding="utf-8"))
            if prior.get("run_signature") != run_signature:
                raise RuntimeError(f"stale result has a different run signature: {out}")
            return prior["summary"]
        t0 = time.time()
        checker = ExecutionEvaluatorAuditChecker(
            client, runner=runner, gen_slack=args.gen_slack,
            adaptive_probe_rounds=args.adaptive_probe_rounds)
        item = BenchmarkItem(
            item_id=f"ds1000_{pid}", raw={}, task=r["prompt"],
            gold=r["reference_code"],
            evaluator={"code_context": r["code_context"],
                       "n_cases": int(r["metadata"].get("test_case_cnt") or 1)})
        try:
            violations = list(checker.check(item))
            status, err = "ok", ""
        except Exception as exc:
            violations, status, err = [], "error", f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        report = checker.last_report or {}
        summary = {"problem_id": pid, "library": r["metadata"]["library"],
                   "perturbation": r["metadata"].get("perturbation_type"),
                   "status": status, "err": err, "secs": round(time.time() - t0, 1),
                   "fatal": report.get("fatal", "")[:120] if "fatal" in report else "",
                   "gold_pass": report.get("gold", {}).get("pass"),
                   "kill": kill_stats(report),
                   "violations": [{"defect_type": v.defect_type, "severity": v.severity,
                                   "probe_id": v.evidence.get("probe_id"),
                                   "message": v.message} for v in violations]}
        out.write_text(json.dumps(
            {"run_signature": run_signature, "summary": summary,
             "violation_evidence": [v.evidence for v in violations],
             "probe_report": report}, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        flag = " ".join(v["defect_type"] for v in summary["violations"]) or "-"
        print(f"[{pid}] {status} {summary['secs']}s gold_pass={summary['gold_pass']} "
              f"kill={summary['kill']} {flag}", flush=True)
        return summary

    with ThreadPoolExecutor(max_workers=workers) as ex:
        summaries = list(ex.map(one, picked))

    agg = {"items": len(summaries),
           "ok": sum(1 for s in summaries if s["status"] == "ok"),
           "fatal_env": sum(1 for s in summaries if s.get("fatal")),
           "gold_fail": sum(1 for s in summaries if s.get("gold_pass") is False),
           "probes": sum(s["kill"]["probes"] for s in summaries),
           "validated_equivalent": sum(s["kill"]["validated_equivalent"] for s in summaries),
           "equivalent_rejected": sum(s["kill"]["equivalent_rejected"] for s in summaries),
           "validated_mutant": sum(s["kill"]["validated_mutant"] for s in summaries),
           "mutant_killed": sum(s["kill"]["mutant_killed"] for s in summaries),
           "mutant_survived": sum(s["kill"]["mutant_survived"] for s in summaries)}
    (outdir / "summary.json").write_text(
        json.dumps({"run_signature": run_signature, "aggregate": agg, "items": summaries}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("\n==== AGGREGATE ====")
    for k, v in agg.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
