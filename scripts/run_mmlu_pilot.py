#!/usr/bin/env python3
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run MMLU-Redux Pilot audit and supervised comparison."
    )
    parser.add_argument(
        "--tag",
        default="mmlu_pilot200_open_match",
        help="Prefix used for cache and report files.",
    )
    parser.add_argument(
        "--model",
        choices=("deepseek", "openrouter"),
        default="deepseek",
        help="LLM provider configuration.",
    )
    parser.add_argument(
        "--auditors",
        default="gold",
        help=(
            "Comma-separated auditors, for example gold or "
            "gold,question,option,presentation; use all for every core auditor."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("cascade", "full"),
        default="cascade",
        help="Structured Gold Auditor evidence mode.",
    )
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Run audit without the supervised comparison step.",
    )
    args = parser.parse_args()

    config = config_path(args.model)
    validate_inputs(args.input, args.manifest, config)
    ensure_api_key(config)

    reports = PROJECT_ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    cache = reports / f"{args.tag}_cache.jsonl"
    audit_json = reports / f"{args.tag}_report.json"
    audit_md = reports / f"{args.tag}_report.md"
    comparison_json = reports / f"{args.tag}_comparison.json"
    comparison_md = reports / f"{args.tag}_comparison.md"

    audit_command = [
        sys.executable,
        "-m",
        "benchcore.cli",
        "audit",
        str(args.input),
        "--manifest",
        str(args.manifest),
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
    run(audit_command)

    if not args.audit_only:
        compare_command = [
            sys.executable,
            "-m",
            "benchcore.cli",
            "compare",
            str(args.input),
            "--report",
            str(audit_json),
            "--truth-field",
            "metadata.error_type",
            "--clean-value",
            "ok",
            "--manifest",
            str(args.manifest),
            "--out",
            str(comparison_json),
            "--md",
            str(comparison_md),
            "--print-summary",
        ]
        run(compare_command)

    print("\nOutputs")
    print(f"audit:      {audit_json.relative_to(PROJECT_ROOT)}")
    print(f"cases:      {audit_md.relative_to(PROJECT_ROOT)}")
    print(f"cache:      {cache.relative_to(PROJECT_ROOT)}")
    if not args.audit_only:
        print(f"comparison: {comparison_json.relative_to(PROJECT_ROOT)}")
        print(f"metrics:    {comparison_md.relative_to(PROJECT_ROOT)}")
    return 0


def config_path(model: str) -> Path:
    filename = {
        "deepseek": "llm_deepseek.json",
        "openrouter": "llm_openrouter_gpt55.json",
    }[model]
    return PROJECT_ROOT / "configs" / filename


def validate_inputs(input_path: Path, manifest: Path, config: Path) -> None:
    missing = [path for path in (input_path, manifest, config) if not path.exists()]
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
