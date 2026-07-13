from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .adapter import canonicalize_rows, write_canonical_jsonl
from .artifact_consistency import (
    CrossArtifactConsistencyChecker,
    GroundedRubricConsistencyChecker,
    RubricCoverageChecker,
    RubricOutputContractConsistencyChecker,
)
from .auditor import audit_items
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
    manifest_indices,
    write_jsonl,
    write_manifest,
)
from .swe_leak import SolutionLeakChecker
from .value_recompute import ValueRecomputeChecker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchcore")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Audit a benchmark JSONL/JSON/CSV file")
    audit_parser.add_argument("input", help="Input benchmark file (.jsonl, .json, .csv)")
    audit_parser.add_argument(
        "--profile",
        choices=("auto", "generic", "swebench", "workspacebench", "terminalbench"),
        default="auto",
        help="Benchmark-family profile; auto detects the family and executes its audit plan",
    )
    audit_parser.add_argument("--mapping", help="Optional field mapping JSON")
    audit_parser.add_argument("--root", help="Root directory for relative attachments")
    audit_parser.add_argument("--limit", type=int, help="Only audit the first N rows after offset")
    audit_parser.add_argument("--offset", type=int, default=0, help="Skip the first N rows")
    audit_parser.add_argument("--manifest", help="Select rows using a reproducible sample manifest")
    audit_parser.add_argument("--out", default="audit_report.json", help="Output JSON report")
    audit_parser.add_argument("--md", help="Optional Markdown report")
    audit_parser.add_argument("--canonical-out", help="Optional canonical JSONL output")
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
        help="Recompute numeric rubric values from tabular inputs (EXECUTES LLM-generated code; trusted data only)",
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
    map_parser.add_argument("input", help="Input benchmark file (.jsonl, .json, .csv)")
    map_parser.add_argument("--out", help="Optional output mapping JSON")
    map_parser.set_defaults(func=run_infer_mapping)

    canon_parser = subparsers.add_parser("canonicalize", help="Canonicalize a benchmark file")
    canon_parser.add_argument("input", help="Input benchmark file (.jsonl, .json, .csv)")
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
    inject_parser.add_argument("input", help="Input benchmark JSONL/JSON/CSV")
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

    args = parser.parse_args(argv)
    return args.func(args)


def run_audit(args: argparse.Namespace) -> int:
    run_started = time.monotonic()
    started_at = datetime.now(timezone.utc)
    input_path = Path(args.input)
    rows = load_rows(input_path)
    mapping = load_mapping(Path(args.mapping) if args.mapping else None, rows)
    if args.manifest:
        rows = load_rows_from_manifest(rows, input_path, Path(args.manifest))
        rows = slice_rows(rows, args.offset, args.limit)
    else:
        rows = slice_rows(rows, args.offset, args.limit)
    items = build_items(rows, mapping)
    if args.canonical_out:
        write_canonical_jsonl(args.canonical_out, canonicalize_rows(rows, mapping))
    root = Path(args.root) if args.root else input_path.parent
    from .checkers import DEFAULT_CHECKERS, ContextChecker, TaskSpecChecker

    benchmark_package = scan_benchmark_package(input_path)
    add_canonical_item_artifacts(benchmark_package, items)
    detected_family, _, _ = detect_benchmark_family(benchmark_package, items)
    effective_profile = _effective_profile(args.profile, detected_family)
    # Auto-selection never silently opts into paid LLM calls. An explicitly
    # requested workspace profile preserves the established rich-audit default.
    explicit_workspace = args.profile == "workspacebench"
    use_grounded_rubric = args.grounded_rubric_audit or explicit_workspace
    use_rubric_contract = args.rubric_contract_audit or explicit_workspace
    use_rubric_coverage = args.rubric_coverage_audit
    llm_requested = bool(
        args.llm_audit
        or args.swe_leak_llm_confirm
        or args.cross_artifact_audit
        or use_grounded_rubric
        or use_rubric_contract
        or use_rubric_coverage
        or args.value_recompute_audit
    )
    audit_plan = apply_family_policy(build_audit_plan(
        benchmark_package,
        items=items,
        family_override=None if args.profile == "auto" else effective_profile,
        available_llm=llm_requested,
        available_execution=not args.basic_only,
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
    client = None
    if llm_requested:
        client = build_llm_client(args)
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
            )
        )
    if use_grounded_rubric:
        checkers.append(
            GroundedRubricConsistencyChecker(
                client,
                review_threshold=args.llm_review_threshold,
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
    if args.value_recompute_audit:
        checkers.append(ValueRecomputeChecker(client))
    progress_callback = make_progress_callback(args.progress_every)
    violations = audit_items(
        items,
        root=root,
        checkers=checkers,
        dataset_checkers=dataset_checkers,
        progress_callback=progress_callback,
        workers=max(args.workers, 1),
    )
    methods_run = [checker.name for checker in checkers] + [checker.name for checker in dataset_checkers]
    audit_plan = plan_for_executed_methods(
        benchmark_package,
        methods_run,
        base_plan=audit_plan,
    )
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
        ),
        benchmark_package=benchmark_package.to_dict(),
        audit_plan=audit_plan.to_dict(),
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
    client = build_llm_client(args)
    verifier_client = build_verifier_client(args, fallback=client) if args.evidence_verifier else None
    report = investigate_audit_report(
        input_path=input_path,
        report_path=Path(args.report),
        client=client,
        root=Path(args.root) if args.root else input_path.parent,
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


def run_forensic(args: argparse.Namespace) -> int:
    bundle = build_forensic_bundle(
        input_path=Path(args.input),
        item_id=args.item_id,
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
    package = scan_benchmark_package(Path(args.input), max_files=args.max_files)
    plan = build_audit_plan(
        package,
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


def slice_rows(rows: list[dict], offset: int = 0, limit: int | None = None) -> list[dict]:
    start = max(offset, 0)
    if limit is None:
        return rows[start:]
    return rows[start : start + max(limit, 0)]


if __name__ == "__main__":
    raise SystemExit(main())
