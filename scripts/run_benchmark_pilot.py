#!/usr/bin/env python3
"""Run a BenchCore pilot audit for any JSON/JSONL/CSV benchmark input."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a generic BenchCore audit, with optional sampling and comparison."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--tag", required=True, help="Prefix used for output files.")
    parser.add_argument("--model", choices=("deepseek", "openrouter"), default="deepseek")
    parser.add_argument("--auditors", default="gold,question,quantity,event")
    parser.add_argument("--mode", choices=("cascade", "full"), default="cascade")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--sample-size", type=int)
    parser.add_argument("--sample-seed", type=int, default=42)
    parser.add_argument("--stratify-field", action="append", default=[])
    parser.add_argument("--label-field", help="Nested label path for balanced sampling.")
    parser.add_argument("--clean-value", action="append", default=[])
    parser.add_argument("--defect-fraction", type=float)
    parser.add_argument("--truth-field", help="Nested label path for supervised comparison.")
    parser.add_argument(
        "--truth-clean-value",
        action="append",
        default=[],
        help="Label value treated as clean during comparison.",
    )
    parser.add_argument("--id-field", default="id")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument(
        "--llm-dry-run",
        action="store_true",
        help="Exercise the pipeline without external LLM calls.",
    )
    args = parser.parse_args()

    config = config_path(args.model)
    validate_inputs(args.input, config, args.mapping, args.manifest)
    if not args.llm_dry_run:
        ensure_api_key(config)

    reports = PROJECT_ROOT / "reports"
    experiments = PROJECT_ROOT / "experiments"
    reports.mkdir(parents=True, exist_ok=True)
    experiments.mkdir(parents=True, exist_ok=True)

    manifest = args.manifest
    sample_jsonl = experiments / f"{args.tag}.jsonl"
    manifest_json = experiments / f"{args.tag}.manifest.json"
    if args.sample_size is not None:
        sample_cmd = [
            sys.executable,
            "-m",
            "benchcore.cli",
            "sample",
            str(args.input),
            "--size",
            str(args.sample_size),
            "--seed",
            str(args.sample_seed),
            "--id-field",
            args.id_field,
            "--sample-out",
            str(sample_jsonl),
            "--manifest-out",
            str(manifest_json),
        ]
        for field in args.stratify_field:
            sample_cmd.extend(["--stratify-field", field])
        if args.label_field:
            sample_cmd.extend(["--label-field", args.label_field])
        for value in args.clean_value:
            sample_cmd.extend(["--clean-value", value])
        if args.defect_fraction is not None:
            sample_cmd.extend(["--defect-fraction", str(args.defect_fraction)])
        run(sample_cmd)
        manifest = manifest_json

    cache = reports / f"{args.tag}_cache.jsonl"
    audit_json = reports / f"{args.tag}_report.json"
    audit_md = reports / f"{args.tag}_report.md"
    comparison_json = reports / f"{args.tag}_comparison.json"
    comparison_md = reports / f"{args.tag}_comparison.md"

    audit_cmd = [
        sys.executable,
        "-m",
        "benchcore.cli",
        "audit",
        str(args.input),
        "--llm-audit",
        "--llm-auditors",
        args.auditors,
        "--gold-evidence-mode",
        args.mode,
        "--llm-config",
        str(config),
        "--llm-cache",
        str(cache),
        "--workers",
        str(max(args.workers, 1)),
        "--progress-every",
        str(max(args.progress_every, 0)),
        "--out",
        str(audit_json),
        "--md",
        str(audit_md),
        "--print-summary",
    ]
    if args.mapping:
        audit_cmd.extend(["--mapping", str(args.mapping)])
    if manifest:
        audit_cmd.extend(["--manifest", str(manifest)])
    if args.llm_dry_run:
        audit_cmd.append("--llm-dry-run")
    run(audit_cmd)

    if not args.audit_only and args.truth_field:
        clean_values = args.truth_clean_value or args.clean_value or ["ok"]
        compare_cmd = [
            sys.executable,
            "-m",
            "benchcore.cli",
            "compare",
            str(args.input),
            "--report",
            str(audit_json),
            "--truth-field",
            args.truth_field,
            "--id-field",
            args.id_field,
            "--out",
            str(comparison_json),
            "--md",
            str(comparison_md),
            "--print-summary",
        ]
        for value in clean_values:
            compare_cmd.extend(["--clean-value", value])
        if manifest:
            compare_cmd.extend(["--manifest", str(manifest)])
        run(compare_cmd)

    print("\nOutputs")
    if args.sample_size is not None:
        print(f"sample:     {sample_jsonl.relative_to(PROJECT_ROOT)}")
        print(f"manifest:   {manifest_json.relative_to(PROJECT_ROOT)}")
    print(f"audit:      {audit_json.relative_to(PROJECT_ROOT)}")
    print(f"cases:      {audit_md.relative_to(PROJECT_ROOT)}")
    print(f"cache:      {cache.relative_to(PROJECT_ROOT)}")
    if not args.audit_only and args.truth_field:
        print(f"comparison: {comparison_json.relative_to(PROJECT_ROOT)}")
        print(f"metrics:    {comparison_md.relative_to(PROJECT_ROOT)}")
    return 0


def config_path(model: str) -> Path:
    filename = {
        "deepseek": "llm_deepseek.json",
        "openrouter": "llm_openrouter_gpt55.json",
    }[model]
    return PROJECT_ROOT / "configs" / filename


def validate_inputs(*paths: Path | None) -> None:
    missing = [path for path in paths if path is not None and not path.exists()]
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
