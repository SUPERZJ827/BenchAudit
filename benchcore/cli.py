from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .adapter import canonicalize_rows, write_canonical_jsonl
from .auditor import audit_items
from .comparison import compare_report, write_comparison_markdown
from .loader import build_items, load_mapping, load_rows
from .llm_auditor import (
    EvidenceGoldLLMAuditor,
    GoldLLMAuditor,
    OptionSetLLMAuditor,
    PresentationLLMAuditor,
    QuestionClarityLLMAuditor,
)
from .llm_client import LLMClient, load_llm_config
from .methods import DEFAULT_DATASET_CHECKERS, DEFAULT_METHOD_CHECKERS
from .report import build_report, write_json_report, write_markdown_report
from .sampling import (
    build_sample,
    load_rows_from_manifest,
    manifest_indices,
    write_jsonl,
    write_manifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchcore")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Audit a benchmark JSONL/JSON/CSV file")
    audit_parser.add_argument("input", help="Input benchmark file (.jsonl, .json, .csv)")
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

    args = parser.parse_args(argv)
    return args.func(args)


def run_audit(args: argparse.Namespace) -> int:
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
    from .checkers import DEFAULT_CHECKERS

    checkers = list(DEFAULT_CHECKERS)
    dataset_checkers = []
    if not args.basic_only:
        checkers.extend(DEFAULT_METHOD_CHECKERS)
        dataset_checkers.extend(DEFAULT_DATASET_CHECKERS)
    if args.llm_audit:
        config = load_llm_config(args.llm_config)
        if args.llm_cache:
            config.cache_path = args.llm_cache
        if args.llm_dry_run:
            config.dry_run = True
        client = LLMClient(config)
        auditor_types = {
            "gold-single": GoldLLMAuditor,
            "question": QuestionClarityLLMAuditor,
            "option": OptionSetLLMAuditor,
            "presentation": PresentationLLMAuditor,
        }
        requested = [name.strip() for name in args.llm_auditors.split(",") if name.strip()]
        if requested == ["all"]:
            requested = ["gold", "question", "option", "presentation"]
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
    report = build_report(str(input_path), items, violations, mapping, methods_run=methods_run)
    write_json_report(Path(args.out), report)
    if args.md:
        write_markdown_report(Path(args.md), report)
    if args.print_summary:
        print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


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
            },
            indent=2,
            ensure_ascii=False,
        ))
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


def slice_rows(rows: list[dict], offset: int = 0, limit: int | None = None) -> list[dict]:
    start = max(offset, 0)
    if limit is None:
        return rows[start:]
    return rows[start : start + max(limit, 0)]


if __name__ == "__main__":
    raise SystemExit(main())
