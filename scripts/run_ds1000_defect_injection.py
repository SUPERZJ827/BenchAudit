#!/usr/bin/env python3
"""Synthetic evaluator-defect injection for the execution-observation tier.

Take DS-1000 items that audited CLEAN in the pilot, inject one known evaluator
defect into each harness, and measure candidate sensitivity. Shared-driver
evidence remains review-only until a separate trusted adjudicator exists.
Probes are LLM-cached by prompt, so the injected condition reuses the SAME
probes as the clean condition -- a paired comparison isolating the harness edit.

Injections (all rely on the shared DS-1000 harness skeleton):
  neutralize_comparator  exec_test returns 1 before comparing
                         -> expect evaluator_mutation_survived
  implementation_assert  test_execution asserts a gold-specific token in the
                         solution string -> expect overstrict_evaluator
  reject_gold            the harness assertion is inverted
                         -> expect gold_rejected_by_evaluator

Usage: run_ds1000_defect_injection.py --pilot-dir DIR --container-image IMAGE@sha256:DIGEST
"""
from __future__ import annotations

import argparse
import hashlib
import json, re, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.evaluator_execution import ExecutionEvaluatorAuditChecker
from benchcore.execution import ContainerRunner
from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.loader import explicit_mapping_provenance
from benchcore.schema import BenchmarkItem

DS1000 = Path.home() / (".cache/huggingface/hub/datasets--xlangai--DS-1000/"
                        "snapshots/4416080ac5cb80bdf7576aefb8f9a0b4d5426a44/test.jsonl")


def gold_token(reference: str) -> str | None:
    """A short implementation-specific token that appears in the gold solution."""
    for pat in (r"\.\w+\(", r"\w+\.\w+", r"\w{4,}"):
        m = re.search(pat, reference)
        if m:
            return m.group(0)
    return None


def inject(kind: str, code_context: str, reference: str) -> str | None:
    """Return the defective harness, or None if this item can't host the injection."""
    if kind == "neutralize_comparator":
        m = re.search(r"(def exec_test\([^)]*\):\n)", code_context)
        if not m:
            return None
        return code_context.replace(m.group(1), m.group(1) + "    return 1\n", 1)
    if kind == "implementation_assert":
        token = gold_token(reference)
        m = re.search(r"(def test_execution\(solution(?:: str)?\):\n)", code_context)
        if not token or not m:
            return None
        return code_context.replace(
            m.group(1), m.group(1) + f"    assert {token!r} in solution\n", 1)
    if kind == "reject_gold":
        if "assert exec_test" not in code_context:
            return None
        return code_context.replace("assert exec_test", "assert not exec_test", 1)
    raise ValueError(kind)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", required=True)
    parser.add_argument("--container-image", required=True)
    parser.add_argument("--container-engine")
    parser.add_argument("--items", type=int, default=20)
    parser.add_argument("--out", default="reports/ds1000_exec_injection_v2.json")
    args = parser.parse_args()
    if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-fA-F]{64}", args.container_image):
        parser.error("--container-image must be digest-pinned as name@sha256:<64 hex>")
    if args.items < 1:
        parser.error("--items must be positive")
    pilot = Path(args.pilot_dir).expanduser().resolve()
    manifest_path = pilot / "run_manifest.json"
    if not manifest_path.is_file():
        parser.error("--pilot-dir must contain a current run_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol_version") != "ds1000-execution-review-v2":
        parser.error("pilot protocol is stale/superseded")
    if manifest.get("container_image") != args.container_image:
        parser.error("injection container must exactly match the clean pilot image")
    runner = ContainerRunner(args.container_image, engine=args.container_engine)
    output_path = (REPO / args.out).resolve()
    m_items = args.items
    # clean = pilot said: gold passes, no violations, and probes were validated
    clean_ids = []
    for f in sorted(pilot.glob("[0-9]*.json"), key=lambda p: int(p.stem)):
        payload = json.loads(f.read_text(encoding="utf-8"))
        if payload.get("run_signature") != manifest.get("run_signature"):
            raise RuntimeError(f"pilot item signature mismatch: {f}")
        s = payload["summary"]
        if (s["status"] == "ok" and s.get("gold_pass") is True and not s["violations"]
                and s["kill"]["validated_equivalent"] >= 1 and s["kill"]["validated_mutant"] >= 1):
            clean_ids.append(s["problem_id"])
    clean_ids = clean_ids[:m_items]
    rows = {json.loads(l)["metadata"]["problem_id"]: json.loads(l)
            for l in DS1000.read_text(encoding="utf-8").splitlines()}
    cfg = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
    cfg.cache_path = "reports/ds1000_exec_llm_cache.jsonl"  # SAME cache -> same probes
    client = LLMClient(cfg)

    expected = {"neutralize_comparator": "evaluator_mutation_survived",
                "implementation_assert": "overstrict_evaluator",
                "reject_gold": "gold_rejected_by_evaluator"}
    results = {k: {"applicable": 0, "detected": 0, "misses": []} for k in expected}
    print(f"injecting into {len(clean_ids)} clean items: {clean_ids}")
    for kind, want in expected.items():
        for pid in clean_ids:
            r = rows[pid]
            bad = inject(kind, r["code_context"], r["reference_code"])
            if bad is None:
                continue
            results[kind]["applicable"] += 1
            checker = ExecutionEvaluatorAuditChecker(client, runner=runner)
            audited_row = {**r, "audited_code_context": bad}
            item = BenchmarkItem(
                item_id=f"ds1000_{pid}_{kind}", raw=audited_row, task=r["prompt"],
                gold=r["reference_code"],
                evaluator={"code_context": bad,
                           "n_cases": int(r["metadata"].get("test_case_cnt") or 1)},
                metadata={"_mapping_provenance": explicit_mapping_provenance(
                    adapter_id="ds1000_defect_injection",
                    adapter_version="ds1000-injection-review-v2",
                    raw=audited_row,
                    field_bindings={
                        "task": "prompt", "gold": "reference_code",
                        "evaluator": "audited_code_context",
                    },
                )},
            )
            found = {v.defect_type for v in checker.check(item)}
            if want in found:
                results[kind]["detected"] += 1
            else:
                results[kind]["misses"].append({"problem_id": pid, "found": sorted(found)})
            print(f"  [{kind}] {pid}: {'HIT' if want in found else 'miss'} {sorted(found)}",
                  flush=True)

    for kind, res in results.items():
        n, d = res["applicable"], res["detected"]
        print(f"{kind}: {d}/{n} detected" + (f" ({d/n:.0%})" if n else ""))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({
        "protocol_version": "ds1000-injection-review-v2",
        "pilot_run_signature": manifest["run_signature"],
        "dataset_sha256": hashlib.sha256(DS1000.read_bytes()).hexdigest(),
        "container_image": args.container_image,
        "metric_semantics": "review-candidate sensitivity, not automatic confirmation",
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
