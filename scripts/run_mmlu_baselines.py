#!/usr/bin/env python3
"""Run ablation baselines on the MMLU-Redux Pilot 200 and print a comparison table.

Baselines (in order):
  1. direct          – single direct LLM call, sees full item including gold
  2. gold-single     – single structured gold check (GoldLLMAuditor)
  3. gold            – blind-solve cascade (EvidenceGoldLLMAuditor), no other auditors
  4. gold,question,option – cascade + question clarity + option set (no presentation)
  5. all (full)      – all four auditors (should already exist as option_applicability_v2)

Cache strategy:
  - Baselines 1-2 use their own cache (completely different prompts).
  - Baselines 3-4 reuse the existing v2 cache (same prompts, zero extra API calls).
  - Baseline 5 is assumed to already exist under the v2 tag.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path(
    PROJECT_ROOT
    / "datasets"
    / "mmlu_redux"
    / "mmlu_redux_all_5700_finegrained.jsonl"
)
DEFAULT_MANIFEST = PROJECT_ROOT / "experiments/mmlu_redux_pilot200.manifest.json"
SHARED_CACHE_TAG = "option_applicability_v2"  # reused by cache-sharing baselines

BASELINES = [
    {
        "name": "Direct LLM",
        "tag": "baseline_direct",
        "auditors": "direct",
        "reuse_cache": False,
    },
    {
        "name": "Gold-single",
        "tag": "baseline_gold_single",
        "auditors": "gold-single",
        "reuse_cache": False,
    },
    {
        "name": "Gold cascade",
        "tag": "baseline_gold",
        "auditors": "gold",
        "reuse_cache": True,
    },
    {
        "name": "Gold+Question+Option",
        "tag": "baseline_gold_q_o",
        "auditors": "gold,question,option",
        "reuse_cache": True,
    },
    {
        "name": "Full system (all)",
        "tag": SHARED_CACHE_TAG,
        "auditors": "all",
        "reuse_cache": True,
        "skip_audit": True,  # already run; only re-run compare if needed
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run MMLU-Redux ablation baselines and print a comparison table."
    )
    parser.add_argument("--model", choices=("deepseek", "openrouter"), default="deepseek")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--only",
        help="Comma-separated subset of baseline tags to run (e.g. baseline_direct,baseline_gold)",
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip audit step; only re-run compare and print table.",
    )
    args = parser.parse_args()

    config = config_path(args.model)
    validate_inputs(args.input, args.manifest, config)
    ensure_api_key(config)

    reports = PROJECT_ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    only_tags = {t.strip() for t in args.only.split(",")} if args.only else None

    for baseline in BASELINES:
        tag = baseline["tag"]
        if only_tags and tag not in only_tags:
            continue

        audit_json = reports / f"{tag}_report.json"
        audit_md = reports / f"{tag}_report.md"
        comparison_json = reports / f"{tag}_comparison.json"
        comparison_md = reports / f"{tag}_comparison.md"

        skip_audit = args.skip_audit or baseline.get("skip_audit", False)
        if skip_audit and audit_json.exists():
            print(f"\n[{tag}] audit report exists, skipping audit step.")
        else:
            if baseline.get("skip_audit") and not audit_json.exists():
                print(
                    f"\n[{tag}] WARN: expected audit report not found at {audit_json}. "
                    "Run the full system first with run_mmlu_pilot.py --tag option_applicability_v2 --auditors all"
                )
                continue

            cache_file = _cache_path(reports, tag, baseline["reuse_cache"])
            audit_cmd = [
                sys.executable, "-m", "benchcore.cli", "audit",
                str(args.input),
                "--manifest", str(args.manifest),
                "--llm-audit",
                "--llm-auditors", baseline["auditors"],
                "--llm-config", str(config),
                "--llm-cache", str(cache_file),
                "--workers", str(max(args.workers, 1)),
                "--progress-every", str(max(args.progress_every, 0)),
                "--out", str(audit_json),
                "--md", str(audit_md),
                "--print-summary",
            ]
            print(f"\n{'='*60}")
            print(f"Baseline: {baseline['name']}  (tag={tag})")
            print(f"{'='*60}")
            run(audit_cmd)

        compare_cmd = [
            sys.executable, "-m", "benchcore.cli", "compare",
            str(args.input),
            "--report", str(audit_json),
            "--truth-field", "metadata.error_type",
            "--clean-value", "ok",
            "--manifest", str(args.manifest),
            "--out", str(comparison_json),
            "--md", str(comparison_md),
        ]
        run(compare_cmd)

    print("\n\n" + "=" * 70)
    print("ABLATION COMPARISON TABLE")
    print("=" * 70)
    print_comparison_table(reports, only_tags)
    return 0


def _cache_path(reports: Path, tag: str, reuse: bool) -> Path:
    if reuse:
        return reports / f"{SHARED_CACHE_TAG}_cache.jsonl"
    return reports / f"{tag}_cache.jsonl"


def print_comparison_table(reports: Path, only_tags: set[str] | None) -> None:
    rows = []
    for baseline in BASELINES:
        tag = baseline["tag"]
        if only_tags and tag not in only_tags:
            continue
        cmp_path = reports / f"{tag}_comparison.json"
        if not cmp_path.exists():
            print(f"  [missing] {tag}")
            continue
        cmp = json.loads(cmp_path.read_text(encoding="utf-8"))
        conf = cmp["confirmed"]
        cand = cmp["candidate"]
        rb20 = (cmp.get("review_budget") or {}).get("20", {})
        rows.append({
            "name": baseline["name"],
            "tag": tag,
            "cand_p": cand["precision"],
            "cand_r": cand["recall"],
            "cand_f1": cand["f1"],
            "conf_p": conf["precision"],
            "conf_r": conf["recall"],
            "conf_f1": conf["f1"],
            "rb20": rb20.get("recall", float("nan")),
            "per_type": cmp.get("per_type", {}),
        })

    if not rows:
        print("  No comparison files found.")
        return

    # Overall metrics table
    header = f"{'System':<28} {'CandP':>6} {'CandR':>6} {'CandF1':>7} {'ConfP':>6} {'ConfR':>6} {'ConfF1':>7} {'R@20%':>6}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['name']:<28} "
            f"{r['cand_p']:>6.3f} {r['cand_r']:>6.3f} {r['cand_f1']:>7.3f} "
            f"{r['conf_p']:>6.3f} {r['conf_r']:>6.3f} {r['conf_f1']:>7.3f} "
            f"{r['rb20']:>6.3f}"
        )

    # Per-type candidate recall table
    all_types = []
    for r in rows:
        for t in r["per_type"]:
            if t not in all_types:
                all_types.append(t)
    if all_types:
        print()
        print("Per-type candidate recall:")
        col_w = 10
        type_w = 28
        header2 = f"{'Truth type':<{type_w}}" + "".join(
            r["name"][:col_w].rjust(col_w + 1) for r in rows
        )
        print(header2)
        print("-" * len(header2))
        for t in sorted(all_types):
            line = f"{t:<{type_w}}"
            for r in rows:
                recall = r["per_type"].get(t, {}).get("candidate_recall", float("nan"))
                line += f"{recall:>{col_w + 1}.3f}"
            print(line)


def config_path(model: str) -> Path:
    filename = {
        "deepseek": "llm_deepseek.json",
        "openrouter": "llm_openrouter_gpt55.json",
    }[model]
    return PROJECT_ROOT / "configs" / filename


def validate_inputs(input_path: Path, manifest: Path, config: Path) -> None:
    missing = [p for p in (input_path, manifest, config) if not p.exists()]
    if missing:
        raise SystemExit("Missing required file(s): " + ", ".join(map(str, missing)))


def ensure_api_key(config_path: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    key_name = config.get("api_key_env")
    if key_name and not os.environ.get(key_name):
        raise SystemExit(
            f"Environment variable {key_name} is not set. Run `source ~/.bashrc` first."
        )


def run(command: list[str]) -> None:
    print("\n$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
