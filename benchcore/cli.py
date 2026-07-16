from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .adapter import canonicalize_rows, write_canonical_jsonl
from .adaptation import (
    AdapterController,
    AdapterGatePolicy,
    AdapterRegistry,
    AdapterSpec,
    HybridAdapterSynthesizer,
    LLMAdapterSynthesizer,
    StaticAdapterSynthesizer,
    adapt_rows,
    analyze_component_gaps,
    build_schema_profile,
    mapping_for_adapted_rows,
)
from .adaptation.synthesis import deterministic_adapter_candidate
from .artifact_consistency import (
    CrossArtifactConsistencyChecker,
    GroundedRubricConsistencyChecker,
    RubricCoverageChecker,
    RubricOutputContractConsistencyChecker,
)
from .auditor import audit_items_with_ledger
from .comparison import compare_report, write_comparison_markdown
from .forensic import build_forensic_bundle, write_forensic_json, write_forensic_markdown
from .gold_study import build_gold_study, write_gold_study_jsonl, write_gold_study_markdown
from .loader import build_items, load_mapping, load_rows
from .llm_auditor import (
    DirectLLMAuditor,
    EventStateLLMAuditor,
    EvidenceGoldLLMAuditor,
    GoldLLMAuditor,
    HolisticSamplingLLMAuditor,
    OptionSetLLMAuditor,
    PresentationLLMAuditor,
    QuantityConsistencyLLMAuditor,
    QuestionClarityLLMAuditor,
)
from .code_verifier import CodeExecVerifier
from .llm_client import LLMClient, load_llm_config
from .investigator import (
    investigate_audit_report,
    refine_investigation_report,
    write_investigation_json,
    write_investigation_markdown,
)
from .methods import DEFAULT_DATASET_CHECKERS, DEFAULT_METHOD_CHECKERS
from .defect_injection import MUTATION_OPERATORS, inject_defects, score_injected_report
from .evaluator_execution import ExecutionEvaluatorAuditChecker
from .execution import ContainerRunner, ExecutionPolicy, LocalProcessRunner
from .package_scan import add_canonical_item_artifacts, scan_benchmark_package
from .planning import (
    apply_family_policy,
    build_audit_plan,
    detect_benchmark_family,
    plan_for_executed_methods,
    write_audit_plan_markdown,
)
from .report import build_report, write_json_report, write_markdown_report
from .sampling import (
    build_sample,
    load_rows_from_manifest,
    load_rows_with_source_indices_from_manifest,
    manifest_indices,
    write_jsonl,
    write_manifest,
)
from .swe_leak import SolutionLeakChecker
from .value_recompute import ValueRecomputeChecker
from .workspace_invariants import WorkspaceArtifactInvariantChecker
from .workspace_visibility import WorkspaceRunnerVisibilityIndex
from .workspace_grounding import (
    WorkspaceRubricGroundingAuditor,
    WorkspaceRubricGroundingChecker,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchcore")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser(
        "audit", help="Audit a benchmark JSONL/JSON/CSV/TSV/Parquet file"
    )
    audit_parser.add_argument(
        "input", help="Input benchmark file (.jsonl, .json, .csv, .tsv, .parquet)"
    )
    audit_parser.add_argument(
        "--profile",
        choices=("auto", "generic", "swebench", "workspacebench", "terminalbench"),
        default="auto",
        help="Benchmark-family profile; auto detects the family and executes its audit plan",
    )
    audit_parser.add_argument("--mapping", help="Optional field mapping JSON")
    audit_adapter_group = audit_parser.add_mutually_exclusive_group()
    audit_adapter_group.add_argument(
        "--adapter-spec",
        help="Validated typed AdapterSpec JSON to apply before auditing",
    )
    audit_adapter_group.add_argument(
        "--adapter-registry",
        help="Resolve an integrity-checked adapter by family and schema fingerprint",
    )
    audit_parser.add_argument(
        "--adapter-family",
        choices=("generic", "workspacebench", "swebench", "terminalbench"),
        help="Family used to resolve --adapter-registry (defaults to explicit --profile)",
    )
    audit_parser.add_argument(
        "--allow-shadow-adapter",
        action="store_true",
        help="Explicitly allow a structurally gated but reference-unverified adapter",
    )
    audit_parser.add_argument("--root", help="Root directory for relative attachments")
    audit_parser.add_argument("--limit", type=int, help="Only audit the first N rows after offset")
    audit_parser.add_argument("--offset", type=int, default=0, help="Skip the first N rows")
    audit_parser.add_argument("--manifest", help="Select rows using a reproducible sample manifest")
    audit_parser.add_argument("--out", default="audit_report.json", help="Output JSON report")
    audit_parser.add_argument("--md", help="Optional Markdown report")
    audit_parser.add_argument("--canonical-out", help="Optional canonical JSONL output")
    audit_parser.add_argument(
        "--evolution-registry",
        help=(
            "Load integrity-checked, gate-accepted declarative rules from this "
            "registry; generated findings remain review-only"
        ),
    )
    audit_parser.add_argument("--llm-audit", action="store_true", help="Enable generic LLM semantic auditor")
    audit_parser.add_argument(
        "--llm-auditors",
        default="gold,question,option",
        help=(
            "Comma-separated LLM auditors: gold,gold-single,question,option,"
            "presentation; use all for every core auditor"
        ),
    )
    audit_parser.add_argument(
        "--gold-evidence-mode",
        choices=("cascade", "full"),
        default="cascade",
        help=(
            "Structured gold verification: cascade only challenges risky blind "
            "solutions; full always runs defender and challenger"
        ),
    )
    audit_parser.add_argument("--llm-config", help="LLM config JSON")
    audit_parser.add_argument("--llm-cache", help="LLM response cache JSONL")
    audit_parser.add_argument("--llm-dry-run", action="store_true", help="Do not call API; emit dry-run uncertain outputs")
    audit_parser.add_argument("--llm-confirm-threshold", type=float, default=0.75)
    audit_parser.add_argument("--llm-review-threshold", type=float, default=0.45)
    audit_parser.add_argument(
        "--swe-leak-audit",
        action="store_true",
        help="Enable code benchmark solution-leak auditing for patch/problem_statement fields",
    )
    audit_parser.add_argument(
        "--swe-leak-llm-confirm",
        action="store_true",
        help="Use LLM semantic confirmation for solution-leak candidates",
    )
    audit_parser.add_argument(
        "--cross-artifact-audit",
        action="store_true",
        help="Enable LLM cross-artifact consistency audit over task/context/reference/evaluator",
    )
    audit_parser.add_argument(
        "--value-recompute-audit",
        action="store_true",
        help=(
            "Recompute numeric rubric values from inputs with generated code; "
            "requires --execution-container-image by default"
        ),
    )
    audit_parser.add_argument(
        "--execution-evaluator-audit",
        action="store_true",
        help=(
            "Run LLM-generated evaluator probes with execution-grounded replay; "
            "requires --execution-container-image by default"
        ),
    )
    audit_parser.add_argument(
        "--execution-container-image",
        help=(
            "Container image containing Python and benchmark dependencies for the "
            "execution evaluator and/or value-recompute audit; production audit "
            "images must be pinned as NAME@sha256:<64 lowercase hex>"
        ),
    )
    audit_parser.add_argument(
        "--allow-unsafe-local-execution",
        action="store_true",
        help=(
            "First explicit opt-in to run trusted harness/probe code on the host "
            "without an OS sandbox"
        ),
    )
    audit_parser.add_argument(
        "--acknowledge-unsafe-local-execution",
        action="store_true",
        help=(
            "Second required acknowledgement that unsafe local execution can access "
            "host files, processes, and network"
        ),
    )
    audit_parser.add_argument(
        "--grounded-rubric-audit",
        action="store_true",
        help=(
            "Enable grounded rubric checks against task text and provided context artifacts "
            "(enabled by default for --profile workspacebench)"
        ),
    )
    audit_parser.add_argument(
        "--rubric-contract-audit",
        action="store_true",
        help=(
            "Enable checks for rubric/evaluator requirements inconsistent with output_contract "
            "(enabled by default for --profile workspacebench)"
        ),
    )
    audit_parser.add_argument(
        "--rubric-coverage-audit",
        action="store_true",
        help="Enable checks for evaluator/rubric under-coverage of central task requirements",
    )
    audit_parser.add_argument(
        "--workspace-rubric-grounding-audit",
        action="store_true",
        help=(
            "Run rubric-level task/contract/input grounding with an adversarial verifier "
            "(WorkspaceBench; paid LLM calls)"
        ),
    )
    audit_parser.add_argument(
        "--workspace-grounding-verifier",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Verify every unsupported Workspace rubric-grounding verdict (default: enabled)",
    )
    audit_parser.add_argument(
        "--workspace-runner-visibility-report",
        help=(
            "Validated transcript from audit_workspace_runner_visibility.py; "
            "byte-matched actor-view evidence can strengthen a Workspace "
            "solution-leak review candidate, but visibility alone cannot confirm "
            "that the file reproduces the hidden oracle"
        ),
    )
    audit_parser.add_argument(
        "--workspace-runner-visibility-online-reverify",
        action="store_true",
        help=(
            "Re-fetch pinned runner sources and the exact remote ZIP member before "
            "using a visibility transcript as review-level evidence"
        ),
    )
    audit_parser.add_argument(
        "--allow-input-root",
        action="append",
        default=[],
        help=(
            "Additional trusted root for input_files. Absolute paths and symlinks "
            "outside the benchmark directory are blocked unless their resolved path "
            "is under one of these roots (repeatable)."
        ),
    )
    audit_parser.add_argument(
        "--allow-remote-data-egress",
        action="store_true",
        help=(
            "Explicitly authorize sending the run metadata's declared benchmark "
            "fields and attachment previews to the configured remote LLM provider"
        ),
    )
    audit_parser.add_argument(
        "--allow-workspace-data-egress",
        action="store_true",
        help=(
            "Deprecated alias for --allow-remote-data-egress (retained for "
            "backward compatibility)"
        ),
    )
    audit_parser.add_argument("--basic-only", action="store_true", help="Disable replay/metamorphic/mutation/dataset methods")
    audit_parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="Print progress every N items; use 0 to disable",
    )
    audit_parser.add_argument("--workers", type=int, default=1, help="Parallel item workers")
    audit_parser.add_argument("--print-summary", action="store_true", help="Print summary to stdout")
    audit_parser.set_defaults(func=run_audit)

    map_parser = subparsers.add_parser("infer-mapping", help="Infer field mapping for a dataset")
    map_parser.add_argument(
        "input", help="Input benchmark file (.jsonl, .json, .csv, .tsv, .parquet)"
    )
    map_parser.add_argument("--out", help="Optional output mapping JSON")
    map_parser.set_defaults(func=run_infer_mapping)

    canon_parser = subparsers.add_parser("canonicalize", help="Canonicalize a benchmark file")
    canon_parser.add_argument(
        "input", help="Input benchmark file (.jsonl, .json, .csv, .tsv, .parquet)"
    )
    canon_parser.add_argument("--mapping", help="Optional field mapping JSON")
    canon_parser.add_argument("--limit", type=int, help="Only canonicalize the first N rows after offset")
    canon_parser.add_argument("--offset", type=int, default=0, help="Skip the first N rows")
    canon_parser.add_argument("--out", required=True, help="Output canonical JSONL")
    canon_parser.set_defaults(func=run_canonicalize)

    compare_parser = subparsers.add_parser("compare", help="Compare an audit report with human labels")
    compare_parser.add_argument("input", help="Original benchmark file")
    compare_parser.add_argument("--report", required=True, help="Audit JSON report")
    compare_parser.add_argument("--truth-field", required=True, help="Nested label path, e.g. metadata.error_type")
    compare_parser.add_argument("--clean-value", action="append", default=["ok"], help="Label value treated as clean")
    compare_parser.add_argument("--id-field", default="id")
    compare_parser.add_argument("--include-method", action="append", help="Only evaluate selected detection method")
    compare_parser.add_argument("--include-defect", action="append", help="Only evaluate selected defect type")
    compare_parser.add_argument(
        "--include-scope",
        action="append",
        help="Only evaluate selected defect scope: substantive or presentation",
    )
    compare_parser.add_argument("--limit", type=int)
    compare_parser.add_argument("--offset", type=int, default=0)
    compare_parser.add_argument("--manifest", help="Select truth rows using the same sample manifest")
    compare_parser.add_argument("--out", required=True, help="Output comparison JSON")
    compare_parser.add_argument("--md", help="Optional comparison Markdown")
    compare_parser.add_argument("--print-summary", action="store_true")
    compare_parser.set_defaults(func=run_compare)

    investigate_parser = subparsers.add_parser(
        "investigate",
        help="Run an evidence-grounded investigator pass over audit report candidates",
    )
    investigate_parser.add_argument("input", help="Original benchmark file used for audit")
    investigate_parser.add_argument("--report", required=True, help="Audit JSON report to investigate")
    investigate_parser.add_argument("--root", help="Root directory for relative attachments")
    investigate_parser.add_argument("--out", required=True, help="Output investigation JSON")
    investigate_parser.add_argument("--md", help="Optional Markdown investigation report")
    investigate_parser.add_argument("--llm-config", help="LLM config JSON")
    investigate_parser.add_argument("--llm-cache", help="LLM response cache JSONL")
    investigate_parser.add_argument("--llm-dry-run", action="store_true", help="Do not call API")
    investigate_parser.add_argument(
        "--allow-input-root",
        action="append",
        default=[],
        help="Additional trusted root for investigation attachment reads (repeatable)",
    )
    investigate_parser.add_argument(
        "--allow-remote-data-egress",
        action="store_true",
        help=(
            "Explicitly authorize sending benchmark artifacts, audit findings, "
            "and attachment previews to the configured remote LLM provider"
        ),
    )
    investigate_parser.add_argument(
        "--investigator-passes",
        type=int,
        default=3,
        help="Independent adjudication passes per candidate (default: 3)",
    )
    investigate_parser.add_argument(
        "--investigator-quorum",
        type=int,
        help="Required matching verdicts; defaults to strict majority",
    )
    investigate_parser.add_argument(
        "--evidence-verifier",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run an independent evidence-verification gate after pass aggregation",
    )
    investigate_parser.add_argument(
        "--verifier-llm-config",
        help="Optional separate LLM config for evidence verification",
    )
    investigate_parser.add_argument(
        "--verifier-llm-cache",
        help="Optional separate evidence-verifier cache JSONL",
    )
    investigate_parser.add_argument("--include-defect", action="append", help="Only investigate selected defect type")
    investigate_parser.add_argument("--include-method", action="append", help="Only investigate selected detection method")
    investigate_parser.add_argument("--min-confidence", type=float, default=0.0)
    investigate_parser.add_argument("--offset", type=int, default=0)
    investigate_parser.add_argument("--limit", type=int)
    investigate_parser.add_argument("--max-context-chars", type=int, default=18000)
    investigate_parser.add_argument("--workers", type=int, default=1, help="Parallel investigator workers")
    investigate_parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="Print investigation progress every N candidates; use 0 to disable",
    )
    investigate_parser.add_argument("--print-summary", action="store_true")
    investigate_parser.set_defaults(func=run_investigate)

    refine_parser = subparsers.add_parser(
        "refine-investigation",
        help="Reapply deterministic policy gates to an existing investigation report",
    )
    refine_parser.add_argument("--report", required=True, help="Existing investigation JSON")
    refine_parser.add_argument("--out", required=True, help="Refined investigation JSON")
    refine_parser.add_argument("--md", help="Optional refined Markdown report")
    refine_parser.add_argument("--print-summary", action="store_true")
    refine_parser.set_defaults(func=run_refine_investigation)

    forensic_parser = subparsers.add_parser(
        "forensic",
        help="Build a task-level evidence bundle for human/agent deep review",
    )
    forensic_parser.add_argument("input", help="Original benchmark file")
    forensic_parser.add_argument("--item-id", required=True, help="Benchmark item id to inspect")
    forensic_parser.add_argument(
        "--row-uid",
        help=(
            "Stable source-row identity from the audit report; required when "
            "--item-id is duplicated"
        ),
    )
    forensic_parser.add_argument("--report", help="Optional audit JSON report")
    forensic_parser.add_argument("--investigation", help="Optional investigation JSON report")
    forensic_parser.add_argument("--root", help="Root directory for relative attachments")
    forensic_parser.add_argument("--max-context-chars", type=int, default=30000)
    forensic_parser.add_argument("--out", required=True, help="Output forensic JSON")
    forensic_parser.add_argument("--md", help="Optional Markdown evidence bundle")
    forensic_parser.set_defaults(func=run_forensic)

    study_parser = subparsers.add_parser(
        "gold-study",
        help="Build a stratified human gold set with flagged and unflagged controls",
    )
    study_parser.add_argument("input", help="Original benchmark file")
    study_parser.add_argument("--report", required=True, help="Audit JSON report")
    study_parser.add_argument("--investigation", help="Optional investigation JSON")
    study_parser.add_argument("--flagged-size", type=int, default=60)
    study_parser.add_argument("--unflagged-size", type=int, default=60)
    study_parser.add_argument("--seed", type=int, default=20260710)
    study_parser.add_argument("--out", required=True, help="Output annotation JSONL")
    study_parser.add_argument("--md", help="Optional readable Markdown workbook")
    study_parser.set_defaults(func=run_gold_study)

    sample_parser = subparsers.add_parser("sample", help="Create a reproducible stratified sample")
    sample_parser.add_argument("input", help="Original benchmark file")
    sample_parser.add_argument("--size", type=int, required=True)
    sample_parser.add_argument("--seed", type=int, default=42)
    sample_parser.add_argument("--id-field", default="id")
    sample_parser.add_argument("--stratify-field", action="append", default=[])
    sample_parser.add_argument("--label-field", help="Nested label field used for clean/defect balancing")
    sample_parser.add_argument("--clean-value", action="append", default=[])
    sample_parser.add_argument("--defect-fraction", type=float)
    sample_parser.add_argument("--exclude-manifest", action="append", default=[])
    sample_parser.add_argument("--exclude-first", type=int, default=0)
    sample_parser.add_argument("--sample-out", required=True, help="Output sampled JSONL")
    sample_parser.add_argument("--manifest-out", required=True, help="Output reproducibility manifest JSON")
    sample_parser.set_defaults(func=run_sample)

    plan_parser = subparsers.add_parser(
        "plan",
        help="Scan a benchmark file/directory and build a capability-aware audit plan",
    )
    plan_parser.add_argument("input", help="Benchmark file, package directory, or repository")
    plan_parser.add_argument("--max-files", type=int, default=10_000)
    plan_parser.add_argument("--llm", action="store_true", help="Mark LLM-backed checks as available")
    plan_parser.add_argument("--execution", action="store_true", help="Mark safe execution as available")
    plan_parser.add_argument("--out", required=True, help="Output plan JSON")
    plan_parser.add_argument("--md", help="Optional readable Markdown plan")
    plan_parser.set_defaults(func=run_plan)

    inject_parser = subparsers.add_parser(
        "inject-defects",
        help="Create deterministic synthetic benchmark defects with provenance",
    )
    inject_parser.add_argument("input", help="Input benchmark JSONL/JSON/CSV/TSV/Parquet")
    inject_parser.add_argument("--mapping", help="Optional field mapping JSON")
    inject_parser.add_argument("--seed", type=int, default=20260712)
    inject_parser.add_argument("--operator", action="append", choices=sorted(MUTATION_OPERATORS))
    inject_parser.add_argument("--mutations-per-item", type=int, default=1)
    inject_parser.add_argument("--out", required=True, help="Output mutated JSONL")
    inject_parser.add_argument("--manifest-out", required=True, help="Output mutation provenance JSON")
    inject_parser.set_defaults(func=run_inject_defects)

    score_parser = subparsers.add_parser(
        "score-injections",
        help="Measure checker recall against an injected-defect provenance manifest",
    )
    score_parser.add_argument("--manifest", required=True, help="Mutation provenance JSON")
    score_parser.add_argument("--report", required=True, help="Audit report over mutated items")
    score_parser.add_argument("--out", required=True, help="Output synthetic recall JSON")
    score_parser.set_defaults(func=run_score_injections)

    evolve_parser = subparsers.add_parser(
        "evolve-rules",
        help=(
            "Synthesize and gate bounded review-only checker rules on a "
            "group-disjoint train/dev/holdout corpus"
        ),
    )
    evolve_parser.add_argument("corpus", help="Evolution corpus JSON/JSONL")
    evolve_parser.add_argument(
        "--proposal",
        help="Offline RuleSpec JSON (one rule, list, or {rules:[...]})",
    )
    evolve_parser.add_argument(
        "--llm-config",
        help="LLM config used when --proposal is omitted",
    )
    evolve_parser.add_argument("--llm-cache", help="Optional synthesis response cache JSONL")
    evolve_parser.add_argument(
        "--allow-remote-data-egress",
        action="store_true",
        help=(
            "Explicitly authorize sending bounded, identifier-free TRAIN rows "
            "and labels to the configured remote model; dev/holdout are never sent"
        ),
    )
    evolve_parser.add_argument(
        "--gate-policy",
        help="Optional GatePolicy JSON; omitted fields use fail-closed defaults",
    )
    evolve_parser.add_argument("--max-rounds", type=int, default=3)
    evolve_parser.add_argument("--max-candidates-per-round", type=int, default=6)
    evolve_parser.add_argument("--max-total-candidates", type=int, default=12)
    evolve_parser.add_argument("--registry-dir", help="Evolution registry directory")
    evolve_parser.add_argument(
        "--activate",
        action="store_true",
        help="Atomically activate an accepted rule as active_review",
    )
    evolve_parser.add_argument("--out", required=True, help="Evolution run JSON")
    evolve_parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero unless a rule passes every gate",
    )
    evolve_parser.set_defaults(func=run_evolve_rules)

    adapt_parser = subparsers.add_parser(
        "auto-adapt",
        help=(
            "Synthesize, gate, and optionally register a non-executable typed "
            "adapter for an unseen benchmark schema"
        ),
    )
    adapt_parser.add_argument("input", help="Benchmark JSONL/JSON/CSV/TSV/Parquet")
    adapt_parser.add_argument(
        "--family",
        choices=("generic", "workspacebench", "swebench", "terminalbench"),
        required=True,
    )
    adapt_parser.add_argument(
        "--proposal",
        help="Offline AdapterSpec JSON (one adapter, list, or {adapters:[...]})",
    )
    adapt_parser.add_argument(
        "--llm-config",
        help="LLM config for fallback when deterministic aliases do not pass",
    )
    adapt_parser.add_argument("--llm-cache", help="Adapter synthesis cache JSONL")
    adapt_parser.add_argument(
        "--allow-remote-data-egress",
        action="store_true",
        help=(
            "Authorize sending a bounded schema/type profile to the configured "
            "remote model; no reference sidecar is ever sent"
        ),
    )
    adapt_parser.add_argument(
        "--reference",
        help=(
            "Complete external canonical sidecar used at most once within this run; "
            "persistent blind-holdout consumption requires an experiment ledger"
        ),
    )
    adapt_parser.add_argument("--gate-policy", help="Optional AdapterGatePolicy JSON")
    adapt_parser.add_argument("--max-rounds", type=int, default=3)
    adapt_parser.add_argument("--max-candidates-per-round", type=int, default=4)
    adapt_parser.add_argument("--max-total-candidates", type=int, default=8)
    adapt_parser.add_argument("--registry-dir", help="Adapter registry directory")
    adapt_parser.add_argument(
        "--activate",
        action="store_true",
        help="Activate an accepted adapter (shadow or verified) in the registry",
    )
    adapt_parser.add_argument("--adapted-out", help="Optional adapted JSONL output")
    adapt_parser.add_argument("--spec-out", help="Optional selected AdapterSpec JSON")
    adapt_parser.add_argument("--profile-out", help="Optional bounded schema profile JSON")
    adapt_parser.add_argument("--out", required=True, help="Adapter synthesis run JSON")
    adapt_parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero unless an adapter passes every available gate",
    )
    adapt_parser.set_defaults(func=run_auto_adapt)

    args = parser.parse_args(argv)
    return args.func(args)


def run_audit(args: argparse.Namespace) -> int:
    run_started = time.monotonic()
    started_at = datetime.now(timezone.utc)
    execution_runner, allow_unsafe_local, execution_metadata = _execution_backend(args)
    input_path = Path(args.input)
    source_rows = load_rows(input_path)
    if args.mapping and (args.adapter_spec or args.adapter_registry):
        raise ValueError("--mapping cannot be combined with an adapter")
    adapter_metadata = None
    if args.adapter_spec or args.adapter_registry:
        profile = build_schema_profile(source_rows, max_examples_per_path=0)
        if args.adapter_spec:
            if not args.allow_shadow_adapter:
                raise ValueError(
                    "an unregistered --adapter-spec has no independent semantic "
                    "receipt; pass --allow-shadow-adapter to cap derived findings at review"
                )
            spec = AdapterSpec.from_dict(
                json.loads(Path(args.adapter_spec).read_text(encoding="utf-8"))
            )
            receipt = None
            mode = "explicit_unregistered"
        else:
            adapter_family = args.adapter_family
            if adapter_family is None and args.profile not in {"auto", "generic"}:
                adapter_family = args.profile
            if adapter_family is None:
                raise ValueError(
                    "--adapter-registry requires --adapter-family when --profile is auto/generic"
                )
            registry = AdapterRegistry(Path(args.adapter_registry))
            spec, receipt = registry.resolve(
                family=adapter_family,
                schema_fingerprint=profile.fingerprint,
                allow_shadow=args.allow_shadow_adapter,
            )
            mode = str(receipt["activation_mode"])
        adapted = adapt_rows(source_rows, spec, strict_rows=True)
        source_rows = list(adapted.rows)
        mapping = mapping_for_adapted_rows(spec)
        adapter_metadata = {
            "adapter_id": spec.adapter_id,
            "adapter_version": spec.version,
            "adapter_sha256": spec.sha256,
            "schema_fingerprint": profile.fingerprint,
            "mode": mode,
            "receipt_id": receipt.get("receipt_id") if receipt else None,
            "adaptation": adapted.to_dict(include_rows=False),
            "evidence_warning": (
                "semantic field identity is not independently proven"
                if mode in {"active_shadow", "explicit_unregistered"}
                else None
            ),
        }
    else:
        mapping = load_mapping(Path(args.mapping) if args.mapping else None, source_rows)
    if args.manifest:
        rows, source_indices = load_rows_with_source_indices_from_manifest(
            source_rows, input_path, Path(args.manifest),
        )
        rows = slice_rows(rows, args.offset, args.limit)
        source_indices = slice_rows(source_indices, args.offset, args.limit)
    else:
        source_indices = slice_rows(
            list(range(len(source_rows))), args.offset, args.limit,
        )
        rows = [source_rows[index] for index in source_indices]
    items = build_items(rows, mapping, source_indices=source_indices)
    if args.canonical_out:
        write_canonical_jsonl(args.canonical_out, canonicalize_rows(rows, mapping))
    root = Path(args.root) if args.root else input_path.parent
    workspace_allowed_roots: list[Path] = []
    for value in (root, *(Path(value) for value in args.allow_input_root)):
        allowed_root = value.expanduser().resolve()
        if not allowed_root.is_dir():
            raise ValueError(f"allowed input root is not a directory: {allowed_root}")
        if allowed_root not in workspace_allowed_roots:
            workspace_allowed_roots.append(allowed_root)
    from .checkers import DEFAULT_CHECKERS, ContextChecker, TaskSpecChecker

    benchmark_package = scan_benchmark_package(input_path)
    add_canonical_item_artifacts(benchmark_package, items)
    detected_family, _, _ = detect_benchmark_family(benchmark_package, items)
    effective_profile = _effective_profile(args.profile, detected_family)
    visibility_index = None
    visibility_metadata = None
    if (
        args.workspace_runner_visibility_online_reverify
        and not args.workspace_runner_visibility_report
    ):
        raise ValueError(
            "--workspace-runner-visibility-online-reverify requires "
            "--workspace-runner-visibility-report"
        )
    if args.workspace_runner_visibility_report:
        if effective_profile != "workspacebench":
            raise ValueError(
                "--workspace-runner-visibility-report is only valid for a Workspace profile"
            )
        visibility_path = Path(args.workspace_runner_visibility_report).expanduser().resolve()
        visibility_index = WorkspaceRunnerVisibilityIndex.load(
            visibility_path,
            dataset_path=input_path,
            online_reverify=args.workspace_runner_visibility_online_reverify,
        )
        visibility_metadata = {
            "path": str(visibility_path),
            "transcript_sha256": visibility_index.transcript_sha256,
            "dataset_sha256": visibility_index.dataset_sha256,
            "validated_proofs": len(visibility_index),
            "online_reverified": args.workspace_runner_visibility_online_reverify,
        }
    # Auto-selection never silently opts into paid LLM calls. An explicitly
    # requested workspace profile preserves the established rich-audit default.
    explicit_workspace = args.profile == "workspacebench"
    use_grounded_rubric = args.grounded_rubric_audit or explicit_workspace
    use_rubric_contract = args.rubric_contract_audit or explicit_workspace
    use_rubric_coverage = args.rubric_coverage_audit
    execution_available = execution_runner is not None
    llm_requested = bool(
        args.llm_audit
        or args.swe_leak_llm_confirm
        or args.cross_artifact_audit
        or use_grounded_rubric
        or use_rubric_contract
        or use_rubric_coverage
        or args.workspace_rubric_grounding_audit
        or args.value_recompute_audit
        or args.execution_evaluator_audit
    )
    remote_egress_manifest = _remote_egress_manifest(
        args,
        use_grounded_rubric=use_grounded_rubric,
        use_rubric_contract=use_rubric_contract,
        use_rubric_coverage=use_rubric_coverage,
    )
    remote_egress_metadata = _enforce_remote_egress_policy(
        args,
        remote_egress_manifest,
    )
    if llm_requested and not remote_egress_manifest:
        raise RuntimeError(
            "internal safety invariant failed: an LLM-backed checker has no declared "
            "remote-data egress capability"
        )
    audit_plan = apply_family_policy(build_audit_plan(
        benchmark_package,
        items=items,
        family_override=None if args.profile == "auto" else effective_profile,
        available_llm=llm_requested,
        available_execution=execution_available,
    ))
    selected_methods = {
        check.name for check in audit_plan.checks if check.status == "selected"
    }

    # Profiles are policies layered on top of the common safety checks. They no
    # longer replace the entire checker set (the former SWE-bench behavior lost
    # every structural defect detector).
    checkers = list(DEFAULT_CHECKERS)
    if effective_profile in {"workspacebench", "terminalbench"}:
        profile_checkers = []
        for checker in checkers:
            if checker.name == "oracle_ground_truth":
                continue
            if checker.name == "task_specification":
                profile_checkers.append(TaskSpecChecker(check_ambiguity=False))
                continue
            if checker.name == "context_attachment":
                profile_checkers.append(ContextChecker(check_version_risk=False))
                continue
            profile_checkers.append(checker)
        checkers = profile_checkers
    if effective_profile == "workspacebench":
        checkers.append(WorkspaceArtifactInvariantChecker(
            allowed_roots=workspace_allowed_roots,
            visibility_index=visibility_index,
        ))
    if args.profile == "auto":
        checkers = [checker for checker in checkers if checker.name in selected_methods]
    dataset_checkers = []
    if not args.basic_only:
        method_checkers = list(DEFAULT_METHOD_CHECKERS)
        candidate_dataset_checkers = list(DEFAULT_DATASET_CHECKERS)
        if args.profile == "auto":
            method_checkers = [
                checker for checker in method_checkers if checker.name in selected_methods
            ]
            candidate_dataset_checkers = [
                checker
                for checker in candidate_dataset_checkers
                if checker.name in selected_methods
            ]
        checkers.extend(method_checkers)
        dataset_checkers.extend(candidate_dataset_checkers)
    evolution_registry_metadata = None
    if args.evolution_registry:
        from .evolution import EvolutionRegistry

        evolution_registry = EvolutionRegistry(Path(args.evolution_registry))
        learned_checkers = evolution_registry.load_active(family=effective_profile)
        checkers.extend(learned_checkers)
        evolution_registry_metadata = {
            **evolution_registry.snapshot(),
            "loaded_checker_count": len(learned_checkers),
            "evidence_ceiling": "review",
        }
    client = None
    if llm_requested:
        client = build_llm_client(args)
    if args.execution_evaluator_audit:
        checkers.append(ExecutionEvaluatorAuditChecker(
            client,
            runner=execution_runner,
            allow_unsafe_local=allow_unsafe_local,
        ))
    if args.llm_audit:
        auditor_types = {
            "direct": DirectLLMAuditor,
            "event": EventStateLLMAuditor,
            "gold-single": GoldLLMAuditor,
            "question": QuestionClarityLLMAuditor,
            "option": OptionSetLLMAuditor,
            "presentation": PresentationLLMAuditor,
            "quantity": QuantityConsistencyLLMAuditor,
            "holistic": HolisticSamplingLLMAuditor,
            "codeexec": CodeExecVerifier,
        }
        requested = [name.strip() for name in args.llm_auditors.split(",") if name.strip()]
        if requested == ["all"]:
            requested = ["gold", "question", "option", "presentation", "quantity", "event"]
        known = {*auditor_types, "gold"}
        unknown = [name for name in requested if name not in known]
        if unknown:
            raise ValueError(f"Unknown LLM auditors: {', '.join(unknown)}")
        for name in requested:
            if name == "gold":
                checkers.append(
                    EvidenceGoldLLMAuditor(
                        client,
                        confirm_threshold=args.llm_confirm_threshold,
                        review_threshold=args.llm_review_threshold,
                        mode=args.gold_evidence_mode,
                    )
                )
                continue
            if name == "codeexec":
                checkers.append(CodeExecVerifier(
                    client,
                    confirm_threshold=args.llm_confirm_threshold,
                    review_threshold=args.llm_review_threshold,
                    runner=execution_runner,
                    policy=ExecutionPolicy(
                        timeout_seconds=12,
                        max_output_chars=10_000,
                        memory_mb=512,
                        cpu_count=1.0,
                        pids_limit=64,
                        network_enabled=False,
                        allow_local_process=allow_unsafe_local,
                        allowed_environment=frozenset(),
                    ),
                    allow_unsafe_local=allow_unsafe_local,
                ))
                continue
            checkers.append(
                auditor_types[name](
                    client,
                    confirm_threshold=args.llm_confirm_threshold,
                    review_threshold=args.llm_review_threshold,
                )
            )
    if effective_profile == "swebench" or args.swe_leak_audit or args.swe_leak_llm_confirm:
        checkers.append(
            SolutionLeakChecker(
                client if args.swe_leak_llm_confirm else None,
            )
        )
    if args.cross_artifact_audit:
        checkers.append(
            CrossArtifactConsistencyChecker(
                client,
                review_threshold=args.llm_review_threshold,
                allowed_roots=workspace_allowed_roots,
            )
        )
    if use_grounded_rubric:
        checkers.append(
            GroundedRubricConsistencyChecker(
                client,
                review_threshold=args.llm_review_threshold,
                allowed_roots=workspace_allowed_roots,
            )
        )
    if use_rubric_contract:
        checkers.append(
            RubricOutputContractConsistencyChecker(
                client,
                review_threshold=args.llm_review_threshold,
            )
        )
    if use_rubric_coverage:
        checkers.append(
            RubricCoverageChecker(
                client,
                review_threshold=args.llm_review_threshold,
            )
        )
    if args.workspace_rubric_grounding_audit:
        checkers.append(WorkspaceRubricGroundingChecker(
            WorkspaceRubricGroundingAuditor(
                client,
                verify_unsupported=args.workspace_grounding_verifier,
                allowed_roots=workspace_allowed_roots,
            )
        ))
    if args.value_recompute_audit:
        checkers.append(ValueRecomputeChecker(
            client,
            runner=execution_runner,
            policy=ExecutionPolicy(
                timeout_seconds=15,
                max_output_chars=100_000,
                memory_mb=512,
                cpu_count=1.0,
                pids_limit=128,
                network_enabled=False,
                allow_local_process=allow_unsafe_local,
                allowed_environment=frozenset(),
            ),
            allow_unsafe_local=allow_unsafe_local,
            allowed_roots=workspace_allowed_roots,
        ))
    progress_callback = make_progress_callback(args.progress_every)
    audit_result = audit_items_with_ledger(
        items,
        root=root,
        checkers=checkers,
        dataset_checkers=dataset_checkers,
        progress_callback=progress_callback,
        workers=max(args.workers, 1),
    )
    violations = audit_result.violations
    if allow_unsafe_local:
        _apply_unsafe_local_evidence_ceiling(violations)
    if adapter_metadata and adapter_metadata["mode"] != "active_verified":
        _apply_adapter_evidence_ceiling(violations, adapter_metadata)
    methods_run = [checker.name for checker in checkers] + [checker.name for checker in dataset_checkers]
    audit_plan = plan_for_executed_methods(
        benchmark_package,
        methods_run,
        base_plan=audit_plan,
        audit_ledger=audit_result.ledger,
    )
    extra_metadata = {"remote_data_egress": remote_egress_metadata}
    if execution_metadata:
        extra_metadata["execution"] = execution_metadata
    if visibility_metadata:
        extra_metadata["workspace_runner_visibility"] = visibility_metadata
    if evolution_registry_metadata:
        extra_metadata["evolution_registry"] = evolution_registry_metadata
    if adapter_metadata:
        extra_metadata["adapter"] = adapter_metadata
    report = build_report(
        str(input_path),
        items,
        violations,
        mapping,
        methods_run=methods_run,
        run_metadata=collect_run_metadata(
            run_started=run_started,
            started_at=started_at,
            primary_client=client,
            extra=extra_metadata or None,
        ),
        benchmark_package=benchmark_package.to_dict(),
        audit_plan=audit_plan.to_dict(),
        audit_ledger=audit_result.ledger,
    )
    write_json_report(Path(args.out), report)
    if args.md:
        write_markdown_report(Path(args.md), report)
    if args.print_summary:
        print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


def _effective_profile(requested: str, detected: str) -> str:
    if requested != "auto":
        return requested
    if detected in {"swebench", "workspacebench", "terminalbench"}:
        return detected
    if detected == "rubric":
        return "workspacebench"
    return "generic"


def _remote_egress_manifest(
    args: argparse.Namespace,
    *,
    use_grounded_rubric: bool,
    use_rubric_contract: bool,
    use_rubric_coverage: bool,
) -> list[dict[str, object]]:
    """Declare every benchmark payload an enabled LLM checker may transmit.

    The registry deliberately describes possible outbound data, not what a
    particular prompt happened to include.  That keeps consent fail-closed when
    prompt construction or checker internals evolve.
    """

    manifest: list[dict[str, object]] = []

    def add(
        checker: str,
        outbound_fields: tuple[str, ...],
        *,
        attachment_content: bool = False,
    ) -> None:
        manifest.append({
            "checker": checker,
            "outbound_fields": list(dict.fromkeys(outbound_fields)),
            "attachment_content": attachment_content,
        })

    if args.execution_evaluator_audit:
        add(
            "execution_evaluator_audit",
            ("task", "reference_or_gold", "evaluator_code_and_configuration"),
        )
    if args.llm_audit:
        add(
            "generic_llm_auditors",
            (
                "task",
                "context",
                "choices",
                "gold",
                "aliases",
                "output_contract",
                "evaluator",
                "benchmark_metadata",
            ),
            attachment_content=True,
        )
    if args.swe_leak_llm_confirm:
        add(
            "solution_leak",
            (
                "task_or_problem_statement",
                "reference_patch_or_solution",
                "tests",
                "hints_and_metadata",
            ),
        )
    if args.cross_artifact_audit:
        capability = CrossArtifactConsistencyChecker.remote_egress_capability
        add(
            CrossArtifactConsistencyChecker.name,
            tuple(capability["outbound_fields"]),
            attachment_content=bool(capability["attachment_content"]),
        )
    if use_grounded_rubric:
        capability = GroundedRubricConsistencyChecker.remote_egress_capability
        add(
            GroundedRubricConsistencyChecker.name,
            tuple(capability["outbound_fields"]),
            attachment_content=bool(capability["attachment_content"]),
        )
    if use_rubric_contract:
        capability = RubricOutputContractConsistencyChecker.remote_egress_capability
        add(
            RubricOutputContractConsistencyChecker.name,
            tuple(capability["outbound_fields"]),
            attachment_content=bool(capability["attachment_content"]),
        )
    if use_rubric_coverage:
        capability = RubricCoverageChecker.remote_egress_capability
        add(
            RubricCoverageChecker.name,
            tuple(capability["outbound_fields"]),
            attachment_content=bool(capability["attachment_content"]),
        )
    if args.workspace_rubric_grounding_audit:
        add(
            "workspace_rubric_grounding",
            (
                "task",
                "rubrics",
                "evaluator",
                "output_contract",
                "attachment_inventory",
                "attachment_content",
            ),
            attachment_content=True,
        )
    if args.value_recompute_audit:
        add(
            "value_recompute",
            ("rubrics", "attachment_inventory", "attachment_content"),
            attachment_content=True,
        )
    return manifest


def _enforce_remote_egress_policy(
    args: argparse.Namespace,
    manifest: list[dict[str, object]],
) -> dict[str, object]:
    modern = bool(getattr(args, "allow_remote_data_egress", False))
    legacy = bool(getattr(args, "allow_workspace_data_egress", False))
    authorized = modern or legacy
    if legacy:
        print(
            "warning: --allow-workspace-data-egress is deprecated; use "
            "--allow-remote-data-egress",
            file=sys.stderr,
        )
    if authorized and not manifest:
        flag = (
            "--allow-remote-data-egress"
            if modern
            else "--allow-workspace-data-egress"
        )
        raise ValueError(f"{flag} requires an enabled LLM-backed audit")

    dry_run = bool(args.llm_dry_run)
    network_egress_possible = bool(manifest) and not dry_run
    if network_egress_possible and not authorized:
        raise ValueError(
            "LLM-backed auditing can send benchmark task/context/gold/evaluator data "
            "or extracted attachment content to a remote provider; pass "
            "--allow-remote-data-egress only after confirming every declared field "
            "in the outbound manifest is safe to share"
        )

    outbound_fields = sorted({
        str(field)
        for entry in manifest
        for field in entry.get("outbound_fields", [])
    })
    if modern and legacy:
        authorization_source = "new_and_deprecated_alias"
    elif modern:
        authorization_source = "allow_remote_data_egress"
    elif legacy:
        authorization_source = "deprecated_workspace_alias"
    else:
        authorization_source = "none"
    return {
        "schema_version": "remote-data-egress-manifest-v1",
        "authorized": authorized,
        "authorization_source": authorization_source,
        "dry_run": dry_run,
        "network_egress_possible": network_egress_possible,
        "attachment_content_in_scope": any(
            bool(entry.get("attachment_content")) for entry in manifest
        ),
        "outbound_fields": outbound_fields,
        "checkers": manifest,
    }


def _apply_unsafe_local_evidence_ceiling(violations) -> None:
    """Host execution is diagnostic evidence and can never self-confirm."""

    execution_methods = {
        "execution_replay",
        "execution_differential",
        "execution_kill_matrix",
        "value_recompute",
        "code_exec_verifier",
    }
    for violation in violations:
        if violation.detection_method not in execution_methods:
            continue
        violation.review_only = True
        if violation.defect_scope != "operational":
            violation.severity = "review"
        violation.evidence["execution_trust_boundary"] = "unsafe_local_host"
        violation.evidence["confirmation_eligible"] = False
        violation.evidence["confirmation_ceiling_reason"] = (
            "unsafe local execution is not an isolated, reproducible adjudication environment"
        )


def _apply_adapter_evidence_ceiling(violations, metadata: dict) -> None:
    """An unverified semantic mapping cannot yield self-confirmed defects."""

    for violation in violations:
        violation.review_only = True
        violation.evidence_tier = "review"
        if violation.defect_scope != "operational":
            violation.severity = "review"
        violation.evidence["adapter_trust_boundary"] = {
            "adapter_id": metadata.get("adapter_id"),
            "adapter_sha256": metadata.get("adapter_sha256"),
            "mode": metadata.get("mode"),
        }
        violation.evidence["confirmation_eligible"] = False
        violation.evidence["confirmation_ceiling_reason"] = (
            "adapter semantic field identity lacks an independent reference-equivalence receipt"
        )


def _execution_backend(
    args: argparse.Namespace,
) -> tuple[ContainerRunner | LocalProcessRunner | None, bool, dict | None]:
    """Resolve an explicitly authorized backend for generated-code audits.

    Local execution is deliberately guarded by two independent CLI switches:
    neither a typo nor a copied single flag should silently grant generated
    code access to the host.  Constructing a ``ContainerRunner`` also verifies
    that a supported container engine is actually available, so the planner's
    execution capability reflects reality rather than user intent alone.
    """
    requested_llm_auditors = {
        name.strip()
        for name in str(getattr(args, "llm_auditors", "")).split(",")
        if name.strip()
    }
    codeexec_requested = bool(
        getattr(args, "llm_audit", False)
        and "codeexec" in requested_llm_auditors
    )
    requested_methods = [
        name
        for enabled, name in (
            (args.execution_evaluator_audit, "execution_evaluator_audit"),
            (args.value_recompute_audit, "value_recompute"),
            (codeexec_requested, "code_exec_verifier"),
        )
        if enabled
    ]
    requested = bool(requested_methods)
    image = (args.execution_container_image or "").strip()
    allow_local = bool(args.allow_unsafe_local_execution)
    acknowledge_local = bool(args.acknowledge_unsafe_local_execution)

    if allow_local != acknowledge_local:
        raise ValueError(
            "unsafe local execution requires both "
            "--allow-unsafe-local-execution and "
            "--acknowledge-unsafe-local-execution"
        )
    unsafe_local = allow_local and acknowledge_local

    if not requested:
        if image or unsafe_local:
            raise ValueError(
                "execution backend flags require --execution-evaluator-audit "
                "or --value-recompute-audit or an explicit "
                "--llm-auditors codeexec request"
            )
        return None, False, None
    if image and re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", image) is None:
        raise ValueError(
            "--execution-container-image must use an immutable digest-pinned "
            "reference: NAME@sha256:<64 lowercase hex>"
        )
    if args.basic_only and args.execution_evaluator_audit:
        raise ValueError(
            "--execution-evaluator-audit cannot be combined with --basic-only"
        )
    if image and unsafe_local:
        raise ValueError(
            "choose either --execution-container-image or unsafe local execution, not both"
        )
    if image:
        runner = ContainerRunner(image)
        method_evidence_ceilings = {
            method: (
                "review_until_separate_adjudicator"
                if method == "execution_evaluator_audit"
                else "review"
            )
            for method in requested_methods
        }
        return runner, False, {
            "enabled": True,
            "backend": "container",
            "image": image,
            "image_digest_pinned": True,
            "host_isolation": "container",
            "environment_reference_pinned": True,
            "evidence_integrity_proven": False,
            "method_evidence_ceilings": method_evidence_ceilings,
            "sandboxed": True,
            "methods": requested_methods,
            "network_enabled": False,
            "network_isolated": True,
            "workspace_mount": "read_only",
        }
    if unsafe_local:
        method_evidence_ceilings = {
            method: "review_unsafe_local_host" for method in requested_methods
        }
        return LocalProcessRunner(), True, {
            "enabled": True,
            "backend": "unsafe_local",
            "sandboxed": False,
            "methods": requested_methods,
            "network_enabled": None,
            "network_isolated": False,
            "workspace_mount": "temporary_but_not_isolated",
            "confirmation_eligible": False,
            "evidence_ceiling": "review",
            "method_evidence_ceilings": method_evidence_ceilings,
            "warning": (
                "generated code can access host files, processes, and network; "
                "unsafe-local observations cannot be automatically confirmed"
            ),
        }
    raise ValueError(
        "generated-code audits require --execution-container-image "
        "(recommended), or both --allow-unsafe-local-execution and "
        "--acknowledge-unsafe-local-execution"
    )


def build_llm_client(args: argparse.Namespace) -> LLMClient:
    config = load_llm_config(args.llm_config)
    if args.llm_cache:
        config.cache_path = args.llm_cache
    if args.llm_dry_run:
        config.dry_run = True
    return LLMClient(config)


def make_progress_callback(every: int):
    if every <= 0:
        return None
    started = time.monotonic()

    def report(completed, total, item):
        if completed != total and completed % every != 0:
            return
        elapsed = time.monotonic() - started
        rate = completed / elapsed if elapsed > 0 else 0.0
        remaining = max(total - completed, 0)
        eta = remaining / rate if rate > 0 else 0.0
        percent = completed / total * 100 if total else 100.0
        print(
            f"[{completed}/{total} {percent:.1f}%] "
            f"item={item.item_id} elapsed={format_duration(elapsed)} "
            f"eta={format_duration(eta)}",
            file=sys.stderr,
            flush=True,
        )

    return report


def format_duration(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def run_canonicalize(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    rows = load_rows(input_path)
    mapping = load_mapping(Path(args.mapping) if args.mapping else None, rows)
    rows = slice_rows(rows, args.offset, args.limit)
    records = canonicalize_rows(rows, mapping)
    write_canonical_jsonl(args.out, records)
    print(f"wrote {len(records)} canonical records to {args.out}")
    return 0


def run_infer_mapping(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    rows = load_rows(input_path)
    mapping = load_mapping(None, rows)
    data = {
        "item_id": mapping.item_id,
        "task": mapping.task,
        "context": mapping.context,
        "choices": mapping.choices,
        "gold": mapping.gold,
        "aliases": mapping.aliases,
        "output_contract": mapping.output_contract,
        "evaluator": mapping.evaluator,
        "metadata": mapping.metadata,
    }
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def run_compare(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    rows_override = None
    if args.manifest:
        all_rows = load_rows(input_path)
        rows_override = load_rows_from_manifest(all_rows, input_path, Path(args.manifest))
    comparison = compare_report(
        input_path,
        Path(args.report),
        truth_field=args.truth_field,
        clean_values={str(v).lower() for v in args.clean_value},
        offset=args.offset,
        limit=args.limit,
        id_field=args.id_field,
        include_methods=set(args.include_method or []),
        include_defects=set(args.include_defect or []),
        include_scopes=set(args.include_scope or []),
        rows_override=rows_override,
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.md:
        write_comparison_markdown(Path(args.md), comparison)
    if args.print_summary:
        print(json.dumps(
            {
                "items": comparison["items"],
                "truth_items": comparison["truth_items"],
                "confirmed": comparison["confirmed"],
                "candidate": comparison["candidate"],
                "priority_candidate": comparison.get("priority_candidate"),
                "exploratory_candidate": comparison.get("exploratory_candidate"),
                "substantive_only": comparison.get("substantive_only"),
                "per_type_candidate_recall": {
                    label: {
                        "truth_count": s["truth_count"],
                        "candidate_recall": round(s["candidate_recall"], 3),
                        "confirmed_recall": round(s["confirmed_recall"], 3),
                    }
                    for label, s in comparison.get("per_type", {}).items()
                },
                "review_budget": comparison.get("review_budget"),
            },
            indent=2,
            ensure_ascii=False,
        ))
    return 0


def run_investigate(args: argparse.Namespace) -> int:
    run_started = time.monotonic()
    started_at = datetime.now(timezone.utc)
    input_path = Path(args.input)
    root = (
        Path(args.root).expanduser().resolve()
        if args.root
        else input_path.parent.expanduser().resolve()
    )
    allowed_roots: list[Path] = []
    for value in (root, *(Path(path) for path in args.allow_input_root)):
        resolved = value.expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"allowed input root is not a directory: {resolved}")
        if resolved not in allowed_roots:
            allowed_roots.append(resolved)
    egress_manifest = [{
        "checker": "evidence_grounded_investigator",
        "outbound_fields": [
            "task",
            "context",
            "gold",
            "output_contract",
            "evaluator_or_rubrics",
            "audit_finding",
            "attachment_content",
        ],
        "attachment_content": True,
    }]
    if args.evidence_verifier:
        egress_manifest.append({
            "checker": "investigation_evidence_verifier",
            "outbound_fields": [
                "task",
                "evaluator_or_rubrics",
                "audit_finding",
                "investigator_results",
                "attachment_content",
            ],
            "attachment_content": True,
        })
    egress_metadata = _enforce_remote_egress_policy(args, egress_manifest)
    client = build_llm_client(args)
    verifier_client = build_verifier_client(args, fallback=client) if args.evidence_verifier else None
    report = investigate_audit_report(
        input_path=input_path,
        report_path=Path(args.report),
        client=client,
        root=root,
        allowed_roots=allowed_roots,
        include_defects=set(args.include_defect or []),
        include_methods=set(args.include_method or []),
        min_confidence=args.min_confidence,
        offset=args.offset,
        limit=args.limit,
        max_context_chars=args.max_context_chars,
        investigator_passes=max(args.investigator_passes, 1),
        investigator_quorum=args.investigator_quorum,
        verifier_client=verifier_client,
        workers=max(args.workers, 1),
        progress_every=args.progress_every,
    )
    report["run_metadata"] = collect_run_metadata(
        run_started=run_started,
        started_at=started_at,
        primary_client=client,
        verifier_client=verifier_client if verifier_client is not client else None,
        extra={
            "investigator_passes": max(args.investigator_passes, 1),
            "investigator_quorum": args.investigator_quorum,
            "evidence_verifier": bool(args.evidence_verifier),
            "remote_data_egress": egress_metadata,
        },
    )
    write_investigation_json(Path(args.out), report)
    if args.md:
        write_investigation_markdown(Path(args.md), report)
    if args.print_summary:
        print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


def run_refine_investigation(args: argparse.Namespace) -> int:
    source = json.loads(Path(args.report).read_text(encoding="utf-8"))
    report = refine_investigation_report(source)
    write_investigation_json(Path(args.out), report)
    if args.md:
        write_investigation_markdown(Path(args.md), report)
    if args.print_summary:
        print(json.dumps({
            **report["summary"],
            "refinement": report.get("refinement"),
        }, indent=2, ensure_ascii=False))
    return 0


def build_verifier_client(args: argparse.Namespace, *, fallback: LLMClient) -> LLMClient:
    if not args.verifier_llm_config and not args.verifier_llm_cache:
        return fallback
    config = load_llm_config(args.verifier_llm_config or args.llm_config)
    if args.verifier_llm_cache:
        config.cache_path = args.verifier_llm_cache
    if args.llm_dry_run:
        config.dry_run = True
    return LLMClient(config)


def collect_run_metadata(
    *,
    run_started: float,
    started_at: datetime,
    primary_client: LLMClient | None,
    verifier_client: LLMClient | None = None,
    extra: dict | None = None,
) -> dict:
    metadata = {
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - run_started, 3),
        "git": git_metadata(),
        # A dirty worktree cannot be reproduced from the Git commit alone.
        # Bind every report to the exact BenchCore Python source bytes used by
        # that process; individual hashes also make later diffs diagnosable.
        "implementation": implementation_metadata(),
    }
    if primary_client is not None:
        metadata["llm"] = primary_client.run_stats()
    if verifier_client is not None:
        metadata["verifier_llm"] = verifier_client.run_stats()
    if extra:
        metadata.update(extra)
    return metadata


def git_metadata() -> dict:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def implementation_metadata() -> dict:
    root = Path(__file__).resolve().parent
    files = {
        path.relative_to(root.parent).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*.py"))
        if path.is_file()
    }
    canonical = json.dumps(
        files, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": "benchcore-python-source-manifest-v1",
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "files": files,
    }


def run_forensic(args: argparse.Namespace) -> int:
    bundle = build_forensic_bundle(
        input_path=Path(args.input),
        item_id=args.item_id,
        row_uid=args.row_uid,
        report_path=Path(args.report) if args.report else None,
        investigation_path=Path(args.investigation) if args.investigation else None,
        root=Path(args.root) if args.root else None,
        max_context_chars=args.max_context_chars,
    )
    write_forensic_json(Path(args.out), bundle)
    if args.md:
        write_forensic_markdown(Path(args.md), bundle)
    print(json.dumps(
        {
            "item_id": bundle["item_id"],
            "row_uid": bundle.get("row_uid"),
            "candidate_violations": len(bundle.get("candidate_violations", [])),
            "investigations": len(bundle.get("investigations", [])),
            "target_terms": len(bundle.get("target_terms", [])),
            "out": args.out,
            "md": args.md,
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0


def run_gold_study(args: argparse.Namespace) -> int:
    study = build_gold_study(
        input_path=Path(args.input),
        report_path=Path(args.report),
        investigation_path=Path(args.investigation) if args.investigation else None,
        flagged_size=max(args.flagged_size, 0),
        unflagged_size=max(args.unflagged_size, 0),
        seed=args.seed,
    )
    write_gold_study_jsonl(Path(args.out), study)
    if args.md:
        write_gold_study_markdown(Path(args.md), study)
    print(json.dumps(study["manifest"], ensure_ascii=False, indent=2))
    return 0


def run_sample(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    rows = load_rows(input_path)
    if args.defect_fraction is not None and not 0.0 <= args.defect_fraction <= 1.0:
        raise ValueError("--defect-fraction must be between 0 and 1")
    excluded = manifest_indices([Path(path) for path in args.exclude_manifest])
    excluded.update(range(max(args.exclude_first, 0)))
    clean_values = {str(value) for value in args.clean_value}
    sample_rows, manifest = build_sample(
        rows,
        source_path=input_path,
        size=args.size,
        seed=args.seed,
        stratify_fields=args.stratify_field,
        id_field=args.id_field,
        label_field=args.label_field,
        clean_values=clean_values,
        defect_fraction=args.defect_fraction,
        excluded_indices=excluded,
    )
    write_jsonl(Path(args.sample_out), sample_rows)
    write_manifest(Path(args.manifest_out), manifest)
    print(json.dumps(
        {
            "sample_items": manifest["sample_items"],
            "seed": manifest["seed"],
            "label_distribution": manifest["sample_label_distribution"],
            "strata": len(manifest["sample_stratum_distribution"]),
            "sample_out": args.sample_out,
            "manifest_out": args.manifest_out,
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0


def run_plan(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    package = scan_benchmark_package(input_path, max_files=args.max_files)
    items = None
    if input_path.is_file() and input_path.suffix.lower() in {
        ".json",
        ".jsonl",
        ".csv",
        ".tsv",
        ".parquet",
    }:
        rows = load_rows(input_path)
        mapping = load_mapping(None, rows)
        items = build_items(rows, mapping)
        add_canonical_item_artifacts(package, items)
    plan = build_audit_plan(
        package,
        items=items,
        available_llm=args.llm,
        available_execution=args.execution,
    )
    payload = {"benchmark_package": package.to_dict(), "audit_plan": plan.to_dict()}
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md:
        write_audit_plan_markdown(Path(args.md), package, plan)
    print(json.dumps(plan.to_dict()["summary"], ensure_ascii=False, indent=2))
    return 0


def run_inject_defects(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    rows = load_rows(input_path)
    mapping = load_mapping(Path(args.mapping) if args.mapping else None, rows)
    results = inject_defects(
        rows,
        mapping,
        seed=args.seed,
        operators=args.operator,
        mutations_per_item=args.mutations_per_item,
    )
    write_jsonl(Path(args.out), [result.row for result in results])
    manifest = {
        "source": str(input_path.resolve()),
        "seed": args.seed,
        "operators": args.operator or sorted(MUTATION_OPERATORS),
        "mutations_per_item": args.mutations_per_item,
        "source_items": len(rows),
        "mutated_items": len(results),
        "mutations": [asdict(result.provenance) for result in results],
    }
    manifest_path = Path(args.manifest_out)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source_items": len(rows), "mutated_items": len(results)}, indent=2))
    return 0


def run_score_injections(args: argparse.Namespace) -> int:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    score = score_injected_report(manifest, report)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: score[key] for key in ("expected", "detected", "recall")}, indent=2))
    return 0


def run_evolve_rules(args: argparse.Namespace) -> int:
    """Run bounded rule induction without exposing sealed holdout to the model."""

    from .evolution import (
        EvolutionController,
        EvolutionRegistry,
        GatePolicy,
        LLMRuleSynthesizer,
        RuleSpec,
        StaticRuleSynthesizer,
    )
    from .evolution.corpus import load_evolution_corpus

    examples, corpus_metadata = load_evolution_corpus(Path(args.corpus))
    client = None
    if args.proposal:
        raw = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "rules" in raw:
            raw_rules = raw["rules"]
        elif isinstance(raw, list):
            raw_rules = raw
        else:
            raw_rules = [raw]
        if not isinstance(raw_rules, list):
            raise ValueError("--proposal must contain one rule or a rules list")
        synthesizer = StaticRuleSynthesizer(
            [RuleSpec.from_dict(row) for row in raw_rules]
        )
        synthesis_metadata = {
            "mode": "offline_proposal",
            "proposal": str(Path(args.proposal).resolve()),
            "remote_data_egress": False,
        }
    else:
        if not args.allow_remote_data_egress:
            raise ValueError(
                "remote rule synthesis is disabled by default; pass "
                "--allow-remote-data-egress or provide --proposal"
            )
        config = load_llm_config(args.llm_config)
        if args.llm_cache:
            config.cache_path = args.llm_cache
        client = LLMClient(config)
        synthesizer = LLMRuleSynthesizer(client)
        synthesis_metadata = {
            "mode": "remote_llm",
            "remote_data_egress": True,
            "egress_scope": {
                "sent": ["bounded_identifier_free_train_rows", "train_expected_defect_types"],
                "not_sent": ["dev_rows", "dev_labels", "holdout_rows", "holdout_labels", "source_group", "example_id"],
            },
            "model": config.model,
            "base_url": config.base_url,
        }
    policy_payload: dict[str, object] = {}
    if args.gate_policy:
        loaded_policy = json.loads(Path(args.gate_policy).read_text(encoding="utf-8"))
        if not isinstance(loaded_policy, dict):
            raise ValueError("--gate-policy must contain a JSON object")
        policy_payload = loaded_policy
    policy = GatePolicy(**policy_payload)
    controller = EvolutionController(
        synthesizer,
        policy=policy,
        max_rounds=args.max_rounds,
        max_candidates_per_round=args.max_candidates_per_round,
        max_total_candidates=args.max_total_candidates,
    )
    run = controller.run(examples)
    payload = run.to_dict(include_example_details=False)
    payload["corpus"] = corpus_metadata
    payload["synthesis"] = synthesis_metadata
    if client is not None:
        payload["synthesis"]["client"] = client.run_stats()
    if args.activate:
        if not args.registry_dir:
            raise ValueError("--activate requires --registry-dir")
        if run.selected_rule is None:
            raise RuntimeError("no selected rule is available for activation")
        selected = RuleSpec.from_dict(run.selected_rule)
        activation = EvolutionRegistry(Path(args.registry_dir)).activate(selected, run)
        payload["activation"] = activation
    elif args.registry_dir:
        payload["registry"] = EvolutionRegistry(Path(args.registry_dir)).snapshot()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "run_id": run.run_id,
        "status": run.status,
        "stop_reason": run.stop_reason,
        "holdout_attempts": run.holdout_attempts,
        "activated": bool(payload.get("activation")),
    }, ensure_ascii=False, indent=2))
    return 2 if args.strict and run.status != "accepted" else 0


def run_auto_adapt(args: argparse.Namespace) -> int:
    """Generate a typed adapter; generated code is never imported or executed."""

    input_path = Path(args.input).expanduser().resolve()
    rows = load_rows(input_path)
    profile = build_schema_profile(rows)
    if args.profile_out:
        profile_output = Path(args.profile_out)
        profile_output.parent.mkdir(parents=True, exist_ok=True)
        profile_output.write_text(
            json.dumps(
                profile.to_dict(include_examples=True),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )

    client = None
    if args.proposal and args.llm_config:
        raise ValueError("--proposal and --llm-config are mutually exclusive")
    if args.proposal:
        raw = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "adapters" in raw:
            raw_adapters = raw["adapters"]
        elif isinstance(raw, list):
            raw_adapters = raw
        else:
            raw_adapters = [raw]
        if not isinstance(raw_adapters, list):
            raise ValueError("--proposal must contain one adapter or an adapters list")
        synthesizer = StaticAdapterSynthesizer(
            [AdapterSpec.from_dict(value) for value in raw_adapters]
        )
        synthesis_metadata: dict[str, object] = {
            "mode": "offline_proposal",
            "proposal": str(Path(args.proposal).expanduser().resolve()),
            "remote_data_egress": False,
        }
    else:
        deterministic = deterministic_adapter_candidate(
            rows,
            profile,
            family=args.family,
        )
        fallback = None
        if args.llm_config:
            if not args.allow_remote_data_egress:
                raise ValueError(
                    "LLM adapter fallback can send a bounded schema/type profile to a "
                    "remote provider; pass --allow-remote-data-egress after review"
                )
            config = load_llm_config(args.llm_config)
            if args.llm_cache:
                config.cache_path = args.llm_cache
            client = LLMClient(config)
            fallback = LLMAdapterSynthesizer(client)
            mode = "deterministic_then_remote_llm"
        else:
            mode = "deterministic_only"
        synthesizer = HybridAdapterSynthesizer(
            [deterministic] if deterministic is not None else [],
            fallback,
        )
        synthesis_metadata = {
            "mode": mode,
            "remote_data_egress": fallback is not None,
            "deterministic_candidate": deterministic is not None,
            "egress_scope": (
                {
                    "sent": [
                        "bounded_schema_paths",
                        "types",
                        "list_element_types",
                        "presence_counts",
                    ],
                    "not_sent": [
                        "reference_sidecar",
                        "gate_results_per_row",
                        "registry_receipts",
                        "local_files_outside_input",
                        "raw_example_values",
                    ],
                }
                if fallback is not None else None
            ),
        }

    policy_payload: dict[str, object] = {}
    if args.gate_policy:
        loaded = json.loads(Path(args.gate_policy).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("--gate-policy must contain a JSON object")
        policy_payload = loaded
    policy = AdapterGatePolicy(**policy_payload)
    references = None
    if args.reference:
        reference_path = Path(args.reference).expanduser().resolve()
        if reference_path == input_path:
            raise ValueError("--reference must be physically separate from input")
        references = load_rows(reference_path)
    controller = AdapterController(
        synthesizer,
        policy=policy,
        max_rounds=args.max_rounds,
        max_candidates_per_round=args.max_candidates_per_round,
        max_total_candidates=args.max_total_candidates,
    )
    run = controller.run(
        rows,
        profile,
        family=args.family,
        references=references,
    )
    payload = run.to_dict()
    payload["input"] = {
        "path": str(input_path),
        "row_count": len(rows),
        "schema_profile": profile.to_dict(include_examples=False),
    }
    payload["synthesis"] = synthesis_metadata
    if client is not None:
        payload["synthesis"]["client"] = client.run_stats()

    selected = (
        AdapterSpec.from_dict(run.selected_adapter)
        if run.selected_adapter is not None else None
    )
    payload["component_gaps"] = analyze_component_gaps(
        profile,
        family=args.family,
        spec=selected,
    ).to_dict()
    if selected is not None and run.final_evaluation is not None:
        if args.spec_out:
            spec_output = Path(args.spec_out)
            spec_output.parent.mkdir(parents=True, exist_ok=True)
            spec_output.write_text(
                json.dumps(selected.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        if args.adapted_out and run.final_evaluation.accepted:
            adapted = adapt_rows(rows, selected, strict_rows=True)
            write_jsonl(Path(args.adapted_out), list(adapted.rows))
            payload["adapted_output"] = {
                "path": str(Path(args.adapted_out).expanduser().resolve()),
                "rows": len(adapted.rows),
                "adapter_sha256": selected.sha256,
            }

    if args.activate:
        if not args.registry_dir:
            raise ValueError("--activate requires --registry-dir")
        payload["activation"] = AdapterRegistry(args.registry_dir).activate(run)
    elif args.registry_dir:
        payload["registry"] = AdapterRegistry(args.registry_dir).snapshot()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "run_id": run.run_id,
        "status": run.status,
        "stop_reason": run.stop_reason,
        "schema_fingerprint": run.source_schema_fingerprint,
        "reference_attempts": run.reference_attempts,
        "activated": bool(payload.get("activation")),
    }, ensure_ascii=False, indent=2))
    return 2 if args.strict and run.status not in {
        "active_shadow", "active_verified"
    } else 0


def slice_rows(rows: list[dict], offset: int = 0, limit: int | None = None) -> list[dict]:
    start = max(offset, 0)
    if limit is None:
        return rows[start:]
    return rows[start : start + max(limit, 0)]


if __name__ == "__main__":
    raise SystemExit(main())
