#!/usr/bin/env python3
"""
Rules-only baseline: run only static/programmatic checkers, no LLM calls.

Runs all deterministic checkers in BenchCore (TaskSpecChecker, OracleChecker,
TaskIntegrityChecker, etc.) and classifies any item with at least one substantive
violation as defective. Outputs a comparison JSON matching the format used by
run_direct_llm_baseline.py for direct table comparison.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchcore.checkers import DEFAULT_CHECKERS
from benchcore.methods import DEFAULT_METHOD_CHECKERS
from benchcore.loader import explicit_mapping_provenance
from benchcore.schema import BenchmarkItem


_IGNORED_DEFECTS = {"llm_audit_failure", "auditor_contradiction"}


def _get_nested(obj: dict, dotpath: str) -> Any:
    cur = obj
    for p in dotpath.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def load_items_with_truth(
    input_path: str,
    manifest_path: str | None,
    truth_field: str,
    clean_values: list[str],
) -> tuple[list[dict], dict[str, bool]]:
    all_items: dict[str, dict] = {}
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            all_items[item["id"]] = item

    if manifest_path:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        raw = manifest.get("selected", manifest.get("ids", []))
        ids = {(e["item_id"] if isinstance(e, dict) else e) for e in raw}
        items = [all_items[i] for i in ids if i in all_items]
    else:
        items = list(all_items.values())

    clean_vals_lower = {v.lower() for v in clean_values}
    truth: dict[str, bool] = {}
    for item in items:
        raw = _get_nested(item, truth_field)
        truth[item["id"]] = str(raw).lower() not in clean_vals_lower
    return items, truth


def item_to_benchcore(raw: dict) -> BenchmarkItem:
    metadata = dict(raw.get("metadata") or {})
    metadata["_mapping_provenance"] = explicit_mapping_provenance(
        adapter_id="rules_only_baseline",
        adapter_version="1",
        raw=raw,
        field_bindings={
            "item_id": "id",
            "task": ["question", "task"],
            "gold": "gold",
            "choices": "choices",
            "aliases": "aliases",
            "output_contract": "output_contract",
            "evaluator": "evaluator",
            "context": ["context", "body", "passage"],
        },
    )
    return BenchmarkItem(
        item_id=raw.get("id", ""),
        task=raw.get("question") or raw.get("task") or "",
        gold=raw.get("gold", ""),
        choices=raw.get("choices"),
        context={k: v for k, v in raw.items() if k in ("context", "body", "passage")},
        output_contract=raw.get("output_contract"),
        evaluator=raw.get("evaluator"),
        aliases=raw.get("aliases", []),
        metadata=metadata,
        raw=raw,
    )


def run_static_checkers(item: BenchmarkItem) -> list[dict]:
    violations = []
    all_checkers = list(DEFAULT_CHECKERS) + list(DEFAULT_METHOD_CHECKERS)
    for checker in all_checkers:
        try:
            for v in checker.check(item):
                violations.append({
                    "item_id": v.item_id,
                    "defect_type": v.defect_type,
                    "detection_method": v.detection_method,
                    "defect_scope": v.defect_scope,
                    "review_only": v.review_only,
                    "confidence": v.confidence,
                    "severity": v.severity,
                    "message": v.message,
                })
        except Exception:
            pass
    return violations


def item_is_defect(violations: list[dict]) -> bool:
    # review_only=True violations exist only to flag items for LLM triage;
    # without an LLM they cannot be confirmed, so exclude them here.
    return any(
        v["defect_scope"] == "substantive"
        and not v["review_only"]
        and v["defect_type"] not in _IGNORED_DEFECTS
        for v in violations
    )


def compute_metrics(predictions: dict[str, bool], truth: dict[str, bool]) -> dict[str, Any]:
    common = set(predictions) & set(truth)
    tp = sum(1 for i in common if predictions[i] and truth[i])
    fp = sum(1 for i in common if predictions[i] and not truth[i])
    fn = sum(1 for i in common if not predictions[i] and truth[i])
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {
        "true_positive": tp, "false_positive": fp, "false_negative": fn,
        "precision": round(precision, 6), "recall": round(recall, 6), "f1": round(f1, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--truth-field", default="metadata.audit_label")
    parser.add_argument("--truth-clean-value", action="append", dest="clean_values", default=[])
    args = parser.parse_args()

    clean_values = args.clean_values or ["clean", "ok"]
    items, truth = load_items_with_truth(args.input, args.manifest, args.truth_field, clean_values)
    print(f"Loaded {len(items)} items | truth defects: {sum(truth.values())}", flush=True)

    all_violations: dict[str, list[dict]] = {}
    predictions: dict[str, bool] = {}
    for raw in items:
        bitem = item_to_benchcore(raw)
        viols = run_static_checkers(bitem)
        all_violations[raw["id"]] = viols
        predictions[raw["id"]] = item_is_defect(viols)

    metrics = compute_metrics(predictions, truth)
    defect_items = [iid for iid, pred in predictions.items() if pred]
    fp_items = [iid for iid in defect_items if not truth.get(iid, False)]
    fn_items = [iid for iid, pred in predictions.items() if not pred and truth.get(iid, False)]

    from collections import Counter
    fp_defect_types: Counter = Counter()
    for iid in defect_items:
        for v in all_violations.get(iid, []):
            if v["defect_scope"] == "substantive" and v["defect_type"] not in _IGNORED_DEFECTS:
                fp_defect_types[v["defect_type"]] += 1

    comparison = {
        "baseline": "rules_only",
        "input_path": args.input,
        "manifest_path": args.manifest,
        "truth_field": args.truth_field,
        "clean_values": clean_values,
        "items": len(items),
        "truth_labels": {k: ("defect" if v else "clean") for k, v in truth.items()},
        "candidate": {"prediction_items": len(defect_items), **metrics},
        "false_positive_items": fp_items,
        "false_negative_items": fn_items,
        "defect_type_breakdown": dict(fp_defect_types.most_common()),
    }

    out = PROJECT_ROOT / "reports" / f"{args.tag}_rules_only_comparison.json"
    out.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")

    n_defects = sum(truth.values())
    print(f"\n=== Rules-Only Baseline: {args.tag} ===")
    print(f"Items: {len(items)} | Defects: {n_defects} | Flagged: {len(defect_items)}")
    print(f"P={metrics['precision']:.3f}  R={metrics['recall']:.3f}  F1={metrics['f1']:.3f}")
    print(f"TP={metrics['true_positive']}  FP={metrics['false_positive']}  FN={metrics['false_negative']}")
    print(f"\nTop defect types triggered: {dict(fp_defect_types.most_common(6))}")
    print(f"\nOutput: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
