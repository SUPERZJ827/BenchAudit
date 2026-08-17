#!/usr/bin/env python3
"""Run one ACEBench prompt arm without changing the production checker.

The treatment arm adds one epistemic instruction and one fail-closed output
gate.  It deliberately does not add provenance analysis, blind solving, a new
taxonomy, or a second LLM call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import benchcore.artifact_consistency as artifact_consistency
from benchcore import cli


TREATMENT_INSTRUCTION = """REFERENCE / EVALUATOR EPISTEMIC STATUS:
- Treat the reference/gold, evaluator, and rubric as claims to audit, not as
  sources presumed correct merely because the benchmark labels them official.
- Before reporting any defect, state the strongest plausible explanation under
  which the artifacts are actually consistent.
- Set innocent_explanation_ruled_out to true only when supplied artifact-level
  evidence rules that explanation out. Otherwise use status=uncertain and do
  not emit a material consistency issue.

"""

TREATMENT_OUTPUT_FIELDS = """  \"strongest_innocent_explanation\": \"strongest plausible no-defect explanation, or empty when status is consistent\",
  \"innocent_explanation_ruled_out\": true,
  \"why_ruled_out\": \"specific supplied evidence, or empty\",
"""


def build_treatment_prompt(base_prompt: str) -> str:
    """Derive the treatment prompt from the exact frozen production prompt."""
    conservative_marker = "Be conservative:\n"
    output_marker = '  "severity": "high|medium|low|none",\n'
    if base_prompt.count(conservative_marker) != 1:
        raise ValueError("base prompt has an unexpected conservative marker")
    if base_prompt.count(output_marker) != 1:
        raise ValueError("base prompt has an unexpected output-schema marker")
    prompt = base_prompt.replace(
        conservative_marker,
        TREATMENT_INSTRUCTION + conservative_marker,
        1,
    )
    return prompt.replace(
        output_marker,
        output_marker + TREATMENT_OUTPUT_FIELDS,
        1,
    )


def passes_innocent_explanation_gate(result: dict[str, Any]) -> bool:
    """Require a concrete rebuttal before a treatment finding may be emitted."""
    status = str(result.get("status", "uncertain")).strip()
    if status in {"consistent", "uncertain"}:
        return False
    explanation = str(result.get("strongest_innocent_explanation") or "").strip()
    why = str(result.get("why_ruled_out") or "").strip()
    return bool(
        explanation
        and result.get("innocent_explanation_ruled_out") is True
        and why
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("baseline", "innocent"), required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--llm-config", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--md", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base_prompt = artifact_consistency.USER_PROMPT
    treatment_prompt = build_treatment_prompt(base_prompt)
    original_consistency_violations = artifact_consistency.consistency_violations

    if args.arm == "innocent":
        artifact_consistency.USER_PROMPT = treatment_prompt

        def gated_consistency_violations(item, result, review_threshold=0.45):
            if not passes_innocent_explanation_gate(result):
                return []
            return original_consistency_violations(item, result, review_threshold)

        artifact_consistency.consistency_violations = gated_consistency_violations

    for path in (args.cache, args.out, args.md, args.receipt):
        if path.exists():
            raise SystemExit(f"refusing to overwrite existing experiment artifact: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    selected_prompt = treatment_prompt if args.arm == "innocent" else base_prompt
    cli_args = [
        "audit",
        str(args.input),
        "--mapping", str(args.mapping),
        "--profile", "generic",
        "--out", str(args.out),
        "--md", str(args.md),
        "--llm-config", str(args.llm_config),
        "--llm-cache", str(args.cache),
        "--cross-artifact-audit",
        "--basic-only",
        "--no-benchmark-profile",
        "--allow-remote-data-egress",
        "--workers", str(args.workers),
    ]
    if args.dry_run:
        cli_args.append("--llm-dry-run")
    rc = cli.main(cli_args)
    if rc:
        return rc

    receipt = {
        "schema_version": 1,
        "status": "PREDICTIONS_GENERATED_TRUTH_NOT_READ_BY_RUNNER",
        "arm": args.arm,
        "dry_run": args.dry_run,
        "prompt_sha256": sha256_text(selected_prompt),
        "base_prompt_sha256": sha256_text(base_prompt),
        "treatment_instruction_sha256": sha256_text(TREATMENT_INSTRUCTION),
        "treatment_output_fields_sha256": sha256_text(TREATMENT_OUTPUT_FIELDS),
        "gate": (
            "none"
            if args.arm == "baseline"
            else "non-consistent status + nonempty strongest explanation + "
                 "ruled_out exactly true + nonempty evidence"
        ),
        "input_sha256": sha256_file(args.input),
        "mapping_sha256": sha256_file(args.mapping),
        "llm_config_sha256": sha256_file(args.llm_config),
        "report_sha256": sha256_file(args.out),
        "cache_sha256": sha256_file(args.cache),
    }
    args.receipt.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
