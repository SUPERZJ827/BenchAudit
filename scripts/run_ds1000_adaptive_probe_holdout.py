#!/usr/bin/env python3
"""Paired, execution-grounded holdout test for single-model probe adaptation.

For deterministic DS-1000 holdout items, inject two evaluator defects and run
the same GPT-5.5 client in two conditions:

* baseline: one default probe pass;
* adaptive: the same cached default pass plus one alternate investigator lens
  only when the initial execution contains no differential lead.

The baseline is deliberately run first.  Both conditions share one LLM cache,
so their default probes are identical; the only additional model calls are for
the adaptive lens.  A hit is an execution-grounded candidate of the expected
family, never a model self-report.  This is sensitivity to synthetic defects,
not a claim of automatic semantic confirmation.

The item selection is deterministic from a protocol label and dataset hash,
and excludes the earlier development IDs/ranges.  Do not inspect results and
then change that selection for this protocol.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchcore.evaluator_execution import ExecutionEvaluatorAuditChecker, generate_probes
from benchcore.execution import ContainerRunner
from benchcore.llm_client import LLMClient, load_llm_config
from benchcore.schema import BenchmarkItem
try:  # Supports both ``python scripts/...`` and module-style test imports.
    from scripts.run_ds1000_defect_injection import inject
except ModuleNotFoundError:  # pragma: no cover - direct-script fallback
    from run_ds1000_defect_injection import inject


DS1000 = Path.home() / (
    ".cache/huggingface/hub/datasets--xlangai--DS-1000/"
    "snapshots/4416080ac5cb80bdf7576aefb8f9a0b4d5426a44/test.jsonl"
)
PROTOCOL = "single-model-adaptive-probes-holdout-v3-strict-paired"
# Previous prompt-development / qualitative-control ranges.  The holdout
# selector refuses them so the experiment cannot accidentally recycle a case
# that informed the strategy wording.
EXCLUDED_IDS = frozenset({
    11, 294, 308,
    *range(0, 30), *range(291, 321),
    # v1 was invalidated before its injection was strengthened.  Excluding its
    # already revealed selection keeps v2 genuinely unseen.
    264, 218, 64, 221, 164, 289, 400, 345, 411, 465, 413, 477,
})
EXPECTED = {
    "neutralize_comparator": {
        "evaluator_mutation_survived", "underconstrained_evaluator_risk",
    },
    "implementation_assert": {"overstrict_evaluator", "output_format_overstrict_risk"},
}


def choose_holdout(rows: list[dict[str, Any]], n_per_library: int) -> list[dict[str, Any]]:
    """Select an uninspected, reproducible Pandas/Numpy holdout."""
    picked: list[dict[str, Any]] = []
    for library in ("Pandas", "Numpy"):
        candidates = [
            row for row in rows
            if row["metadata"].get("library") == library
            and row["metadata"].get("problem_id") not in EXCLUDED_IDS
            and all(inject_case(kind, row["code_context"], row["reference_code"])[0] is not None
                    for kind in EXPECTED)
        ]
        ranked = sorted(
            candidates,
            key=lambda row: hashlib.sha256(
                f"{PROTOCOL}:{library}:{row['metadata']['problem_id']}".encode()
            ).hexdigest(),
        )
        if len(ranked) < n_per_library:
            raise RuntimeError(f"only {len(ranked)} eligible {library} holdout items")
        picked.extend(ranked[:n_per_library])
    return picked


def inject_case(kind: str, code_context: str, reference: str) -> tuple[str | None, str]:
    """Return a guaranteed-active synthetic defect and its gold source.

    The old token-based overstrict injection could accidentally accept a
    genuinely different implementation that happened to use the same common
    token (for example ``df.``).  For this control we append a unique Python
    comment to the reference and make the harness require that exact comment.
    The comment has no execution semantics, the tagged gold still passes, and
    any implementation-independent equivalent lacks it by construction.
    """
    if kind == "neutralize_comparator":
        return inject(kind, code_context, reference), reference
    if kind == "implementation_assert":
        marker = "# BENCHAUDIT_REFERENCE_MARKER_" + hashlib.sha256(
            reference.encode("utf-8")
        ).hexdigest()
        tagged_reference = reference.rstrip() + "\n" + marker
        match = re.search(r"(def test_execution\(solution(?:: str)?\):\n)", code_context)
        if not match:
            return None, tagged_reference
        bad_context = code_context.replace(
            match.group(1), match.group(1) + f"    assert {marker!r} in solution\n", 1,
        )
        return bad_context, tagged_reference
    raise ValueError(kind)


def stats_delta(after: dict[str, Any], before: dict[str, Any]) -> dict[str, int]:
    return {
        key: int(after.get(key, 0)) - int(before.get(key, 0))
        for key in ("api_attempts", "api_successes", "api_failures", "total_tokens")
    }


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """Persist progress without leaving a partially-written resumable run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def run_condition(
    client: LLMClient,
    runner: ContainerRunner,
    row: dict[str, Any],
    kind: str,
    adaptive_rounds: int,
    initial_probes: list[dict[str, str]],
) -> dict[str, Any]:
    bad_context, gold = inject_case(kind, row["code_context"], row["reference_code"])
    assert bad_context is not None
    before = client.run_stats()
    checker = ExecutionEvaluatorAuditChecker(
        client,
        runner=runner,
        gen_slack=0,
        adaptive_probe_rounds=adaptive_rounds,
    )
    item = BenchmarkItem(
        item_id=f"ds1000_{row['metadata']['problem_id']}_{kind}", raw={},
        task=row["prompt"], gold=gold,
        evaluator={
            "code_context": bad_context,
            "n_cases": int(row["metadata"].get("test_case_cnt") or 1),
        },
    )
    violations = list(checker.check_with_initial_probes(item, initial_probes))
    found = {violation.defect_type for violation in violations}
    report = checker.last_report or {}
    return {
        "found": sorted(found),
        "hit": bool(found & EXPECTED[kind]),
        "fatal": report.get("fatal"),
        "gold_pass": report.get("gold", {}).get("pass"),
        "probe_coverage": report.get("probe_coverage"),
        "adaptive_probe_rounds": report.get("adaptive_probe_rounds", []),
        "initial_probe_source": report.get("initial_probe_source"),
        "initial_probe_sha256": report.get("initial_probe_sha256"),
        "transport": stats_delta(client.run_stats(), before),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-image", required=True)
    parser.add_argument("--container-engine", default="docker")
    parser.add_argument("--items-per-library", type=int, default=6)
    parser.add_argument("--out", default="reports/adaptive_probe_holdout/result.json")
    parser.add_argument("--max-tokens", type=int, default=2000,
                        help="JSON probe-generation cap; code snippets do not need long essays")
    parser.add_argument("--request-timeout", type=int, default=90,
                        help="wall-clock deadline for one provider response")
    args = parser.parse_args()
    if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-fA-F]{64}", args.container_image):
        parser.error("--container-image must be digest-pinned as name@sha256:<64 hex>")
    if args.items_per_library < 1:
        parser.error("--items-per-library must be positive")
    if args.max_tokens < 256 or args.request_timeout < 1:
        parser.error("--max-tokens must be >= 256 and --request-timeout positive")
    if not DS1000.is_file():
        raise FileNotFoundError(f"DS-1000 test set not found: {DS1000}")

    dataset_bytes = DS1000.read_bytes()
    rows = [json.loads(line) for line in dataset_bytes.decode("utf-8").splitlines()]
    holdout = choose_holdout(rows, args.items_per_library)
    cfg = load_llm_config(str(REPO / "configs/llm_openrouter_gpt55.json"))
    output = (REPO / args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Persist only this run's responses.  It ensures the paired default probes
    # remain byte-for-byte shared if a run is resumed, without touching a user
    # cache from unrelated experiments.
    cfg.cache_path = str(output.with_suffix(".llm_cache.jsonl"))
    cfg.max_tokens = args.max_tokens
    cfg.timeout = args.request_timeout
    # A timeout/transport failure is coverage loss, not a reason to blindly
    # repeat an identical request and make a paired experiment non-comparable.
    cfg.max_retries = 1
    client = LLMClient(cfg)
    runner = ContainerRunner(args.container_image, engine=args.container_engine)

    selections = [
        {"problem_id": row["metadata"]["problem_id"], "library": row["metadata"]["library"]}
        for row in holdout
    ]
    print(f"{PROTOCOL}: {len(holdout)} sealed items: {selections}", flush=True)
    progress_path = output.with_suffix(".progress.json")
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if progress.get("protocol_version") != PROTOCOL or progress.get("selection") != selections:
            raise RuntimeError("existing progress belongs to a different holdout protocol")
        records = list(progress.get("records", []))
    else:
        records = []
    completed = {(row["problem_id"], row["injection"]) for row in records}
    for row in holdout:
        pid = row["metadata"]["problem_id"]
        for kind in EXPECTED:
            if (pid, kind) in completed:
                print(f"[{pid} {kind}] already recorded; resuming", flush=True)
                continue
            bad_context, gold = inject_case(kind, row["code_context"], row["reference_code"])
            assert bad_context is not None
            before_generation = client.run_stats()
            initial_probes = generate_probes(client, row["prompt"], gold, 3, 4)
            generation_transport = stats_delta(client.run_stats(), before_generation)
            baseline = run_condition(
                client, runner, row, kind, adaptive_rounds=0,
                initial_probes=initial_probes,
            )
            adaptive = run_condition(
                client, runner, row, kind, adaptive_rounds=1,
                initial_probes=initial_probes,
            )
            if baseline["initial_probe_sha256"] != adaptive["initial_probe_sha256"]:
                raise RuntimeError("strict-pair invariant failed: initial probe hashes differ")
            records.append({
                "problem_id": pid,
                "library": row["metadata"]["library"],
                "injection": kind,
                "baseline": baseline,
                "adaptive": adaptive,
                "initial_generation_transport": generation_transport,
            })
            atomic_json_write(progress_path, {
                "protocol_version": PROTOCOL,
                "selection": selections,
                "model": cfg.model,
                "records": records,
            })
            print(
                f"[{pid} {kind}] baseline={'HIT' if baseline['hit'] else 'miss'} "
                f"adaptive={'HIT' if adaptive['hit'] else 'miss'} "
                f"rounds={len(adaptive['adaptive_probe_rounds'])}",
                flush=True,
            )

    n = len(records)
    base_hits = sum(record["baseline"]["hit"] for record in records)
    adaptive_hits = sum(record["adaptive"]["hit"] for record in records)
    gained = sum(
        not record["baseline"]["hit"] and record["adaptive"]["hit"] for record in records
    )
    regressed = sum(
        record["baseline"]["hit"] and not record["adaptive"]["hit"] for record in records
    )
    result = {
        "protocol_version": PROTOCOL,
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "container_image": args.container_image,
        "model": cfg.model,
        "selection": selections,
        "excluded_development_ids": sorted(EXCLUDED_IDS),
        "metric_semantics": (
            "execution-grounded injected-defect candidate sensitivity; "
            "not automatic semantic confirmation"
        ),
        "aggregate": {
            "injected_conditions": n,
            "baseline_hits": base_hits,
            "adaptive_hits": adaptive_hits,
            "baseline_recall": base_hits / n if n else None,
            "adaptive_recall": adaptive_hits / n if n else None,
            "paired_gains": gained,
            "paired_regressions": regressed,
        },
        "records": records,
        "final_client_stats": client.run_stats(),
    }
    atomic_json_write(output, result)
    print(json.dumps(result["aggregate"], indent=2), flush=True)
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
