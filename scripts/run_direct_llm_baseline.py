#!/usr/bin/env python3
"""
Direct LLM classification baseline for benchmark defect detection.

Prompts the LLM once per item to classify it as defective or clean,
without any structured artifact decomposition or programmatic rules.
Outputs a comparison JSON in the same format as BenchCore comparison files,
so P/R/F1 can be compared directly.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchcore.llm_client import LLMClient, LLMConfig, load_llm_config

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a benchmark quality auditor. Given a benchmark item and its declared gold answer, determine whether the item has any quality issue that would make it unfair to evaluate a model on.

Return ONLY valid JSON:
{
  "has_defect": true | false,
  "confidence": 0.95,
  "rationale": "one sentence"
}

Rules:
- First solve the problem yourself, then compare with the declared gold.
- Flag the item if you believe a reasonable person could consider it defective.
- Difficulty alone is not a defect.
"""

TAXONOMY_SYSTEM_PROMPT = """You are a benchmark quality auditor. Given a benchmark item and its declared gold answer, determine whether the item has any quality issue that would make it unfair to evaluate a model on.

Return ONLY valid JSON:
{
  "has_defect": true | false,
  "defect_type": "<type from list below or null>",
  "confidence": 0.95,
  "rationale": "one sentence"
}

Rules:
- First solve the problem yourself, then compare with the declared gold.
- Flag the item if it matches ANY of the defect types below.
- Difficulty alone is not a defect.
- Academic domain knowledge is NOT missing_context.

Defect taxonomy — flag the item if it has any of:

ORACLE / GOLD ANSWER defects:
- wrong_gold_answer: The declared gold answer is factually or arithmetically incorrect
- no_correct_answer: No provided choice is correct under the task
- multiple_correct_answers: More than one choice is clearly correct
- multiple_correct_answers_risk: A second choice is plausibly correct
- invalid_choice_gold: Gold letter cannot be matched to the available choices

TASK SPECIFICATION defects:
- ambiguous_goal: Task has multiple equally valid interpretations yielding different answers
- missing_condition: Task requires information not given to determine a unique answer
- incomplete_task_instruction: Task stem is truncated or missing a required component
- temporal_scope_missing: Task is time-sensitive but lacks a reference date

CONTEXT / PRESENTATION defects:
- missing_context: Task explicitly references an external passage or figure that is absent
- bad_options_clarity: One or more MCQ choices are uninterpretable or semantically overlapping
- duplicate_choices: Two or more choices normalize to identical content
- presentation_corruption: OCR errors, garbled text, or encoding corruption visible in the item
"""


def build_user_prompt(item: dict[str, Any]) -> str:
    question = item.get("question") or item.get("task") or ""
    gold = item.get("gold", "")
    choices = item.get("choices")

    lines = [f"Question: {question}", f"Declared gold answer: {gold}"]

    if choices:
        labels = "ABCDE"
        for i, c in enumerate(choices):
            marker = " ← gold" if labels[i] == str(gold) else ""
            lines.append(f"  {labels[i]}) {c}{marker}")

    context = item.get("context") or item.get("body") or ""
    if context and len(str(context)) < 500:
        lines.insert(0, f"Context: {context}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Truth label helpers
# ---------------------------------------------------------------------------

def _get_nested(obj: dict, dotpath: str) -> Any:
    parts = dotpath.split(".")
    cur = obj
    for p in parts:
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
    """Return (items, truth_labels) where truth_labels[id] = True means defective."""
    all_items: dict[str, dict] = {}
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            all_items[item["id"]] = item

    # Filter by manifest if provided
    if manifest_path:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        # Support both flat id lists and the selected-entry format used by build_sample
        raw = manifest.get("selected", manifest.get("ids", manifest.get("sample_ids", [])))
        ids = {
            (entry["item_id"] if isinstance(entry, dict) else entry)
            for entry in raw
        }
        items = [all_items[i] for i in ids if i in all_items]
    else:
        items = list(all_items.values())

    clean_vals_lower = {v.lower() for v in clean_values}
    truth: dict[str, bool] = {}
    for item in items:
        raw = _get_nested(item, truth_field)
        truth[item["id"]] = str(raw).lower() not in clean_vals_lower

    return items, truth


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def classify_item(
    item: dict[str, Any],
    client: LLMClient,
    system_prompt: str = SYSTEM_PROMPT,
) -> dict[str, Any]:
    user = build_user_prompt(item)
    try:
        result = client.chat_json(system_prompt, user)
    except Exception as e:
        result = {
            "has_defect": False,
            "defect_types": [],
            "confidence": 0.0,
            "rationale": f"LLM call failed: {e}",
            "error": str(e),
        }
    return {
        "id": item["id"],
        "predicted_defect": bool(result.get("has_defect", False)),
        "confidence": float(result.get("confidence", 0.0)),
        "rationale": result.get("rationale", ""),
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(
    predictions: dict[str, bool],
    truth: dict[str, bool],
) -> dict[str, Any]:
    common_ids = set(predictions) & set(truth)
    tp = sum(1 for i in common_ids if predictions[i] and truth[i])
    fp = sum(1 for i in common_ids if predictions[i] and not truth[i])
    fn = sum(1 for i in common_ids if not predictions[i] and truth[i])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Source JSONL dataset")
    parser.add_argument("--tag", required=True, help="Output file prefix")
    parser.add_argument("--manifest", help="Manifest JSON to select pilot items")
    parser.add_argument(
        "--truth-field", default="metadata.audit_label",
        help="Dotted path to the ground-truth label field",
    )
    parser.add_argument(
        "--truth-clean-value", action="append", dest="clean_values",
        default=[], metavar="VAL",
        help="Label value meaning 'clean' (repeat for multiple, default: clean ok false)",
    )
    parser.add_argument("--model", choices=["deepseek", "openrouter"], default="deepseek")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--llm-dry-run", action="store_true")
    parser.add_argument(
        "--with-taxonomy", action="store_true",
        help="Use taxonomy-augmented prompt (lists all BenchCore defect types)",
    )
    args = parser.parse_args()

    clean_values = args.clean_values or ["clean", "ok", "false"]
    active_prompt = TAXONOMY_SYSTEM_PROMPT if args.with_taxonomy else SYSTEM_PROMPT

    # Config
    config_map = {
        "deepseek": "configs/llm_deepseek.json",
        "openrouter": "configs/llm_openrouter.json",
    }
    config_path = PROJECT_ROOT / config_map[args.model]
    llm_config = load_llm_config(str(config_path))
    llm_config.cache_path = f"reports/{args.tag}_direct_llm_cache.jsonl"
    if args.llm_dry_run:
        llm_config.dry_run = True

    client = LLMClient(llm_config)

    # Load data
    items, truth = load_items_with_truth(
        args.input, args.manifest, args.truth_field, clean_values
    )
    print(f"Loaded {len(items)} items | truth defects: {sum(truth.values())}", flush=True)

    # Classify
    results: list[dict] = []
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(classify_item, item, client, active_prompt): item["id"] for item in items}
        done = 0
        for future in as_completed(futures):
            results.append(future.result())
            done += 1
            if done % args.progress_every == 0:
                elapsed = time.time() - start
                print(f"  {done}/{len(items)} ({elapsed:.0f}s)", flush=True)

    print(f"Done: {len(results)} items in {time.time()-start:.0f}s", flush=True)

    # Compute metrics
    predictions = {r["id"]: r["predicted_defect"] for r in results}
    metrics = compute_metrics(predictions, truth)

    defect_items = [r["id"] for r in results if r["predicted_defect"]]
    fp_items = [r["id"] for r in results if r["predicted_defect"] and not truth.get(r["id"], False)]
    fn_items = [r["id"] for r in results if not r["predicted_defect"] and truth.get(r["id"], False)]

    # Output comparison JSON (same structure as BenchCore comparison files)
    comparison = {
        "baseline": "llm_taxonomy" if args.with_taxonomy else "direct_llm_classification",
        "model": args.model,
        "with_taxonomy": args.with_taxonomy,
        "input_path": args.input,
        "truth_field": args.truth_field,
        "clean_values": clean_values,
        "items": len(items),
        "truth_labels": {k: ("defect" if v else "clean") for k, v in truth.items()},
        "candidate": {
            "prediction_items": defect_items,
            **metrics,
        },
        "false_positive_items": fp_items,
        "false_negative_items": fn_items,
        "per_item": results,
    }

    out_json = PROJECT_ROOT / "reports" / f"{args.tag}_direct_llm_comparison.json"
    out_json.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print summary
    n_defects = sum(truth.values())
    n_flagged = len(defect_items)
    print(f"\n=== Direct LLM Baseline: {args.tag} ===")
    print(f"Items: {len(items)} | Known defects: {n_defects} | Flagged: {n_flagged}")
    print(f"P={metrics['precision']:.3f}  R={metrics['recall']:.3f}  F1={metrics['f1']:.3f}")
    print(f"TP={metrics['true_positive']}  FP={metrics['false_positive']}  FN={metrics['false_negative']}")
    print(f"\nOutput: {out_json}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
