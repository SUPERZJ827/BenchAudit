"""Replay cross-domain counterexample evidence from a JSON manifest.

The manifest contains observations and sidecar certificates, never executable
code.  Untrusted code/table recomputation must already have run in the existing
isolated execution layer and provide its attested transcript hash here.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path
from typing import Any, Mapping

from benchcore.counterexample_validation import (
    CounterexampleDecision,
    CounterexamplePolicy,
    ObjectivePairObservation,
    ScoredPairSpec,
    ScoredPairTrial,
    TableRecomputeObservation,
    adjudicate_objective_pair,
    adjudicate_scored_pair,
    adjudicate_table_recompute,
    replay_exact_answer_pairs,
    verification_capabilities,
)
from benchcore.schema import BenchmarkItem


SCHEMA_VERSION = "counterexample-evidence-replay-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON manifest containing a records array")
    parser.add_argument("--out", required=True, help="Output decision JSON")
    parser.add_argument("--md", help="Optional Markdown summary")
    return parser.parse_args()


def replay_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("manifest.records must be a list")
    decisions: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            errors.append({"index": index, "error": "record must be an object"})
            continue
        kind = str(raw.get("kind") or "")
        try:
            record_decisions, record_routes = replay_record(kind, raw)
        except (TypeError, ValueError, KeyError) as exc:
            errors.append({
                "index": index,
                "kind": kind,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        decisions.extend(decision.to_dict() for decision in record_decisions)
        routes.extend(record_routes)
    distribution: dict[str, int] = {}
    tiers: dict[str, int] = {}
    for row in decisions:
        distribution[row["status"]] = distribution.get(row["status"], 0) + 1
        tiers[row["evidence_tier"]] = tiers.get(row["evidence_tier"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "records": len(records),
        "decisions": decisions,
        "routes": routes,
        "errors": errors,
        "summary": {
            "decisions": len(decisions),
            "errors": len(errors),
            "status_distribution": distribution,
            "evidence_tier_distribution": tiers,
        },
    }


def replay_record(
    kind: str,
    raw: Mapping[str, Any],
) -> tuple[list[CounterexampleDecision], list[dict[str, Any]]]:
    if kind == "objective_pair":
        observation = _strict_dataclass(ObjectivePairObservation, raw.get("observation"))
        return [adjudicate_objective_pair(observation)], []
    if kind == "table_recompute":
        observation = _strict_dataclass(TableRecomputeObservation, raw.get("observation"))
        return [adjudicate_table_recompute(observation)], []
    if kind == "scored_pair":
        spec = _strict_dataclass(ScoredPairSpec, raw.get("spec"))
        trial_rows = raw.get("trials")
        if not isinstance(trial_rows, list):
            raise ValueError("scored_pair.trials must be a list")
        trials = [_strict_dataclass(ScoredPairTrial, row) for row in trial_rows]
        policy_value = raw.get("policy")
        policy = (
            _strict_dataclass(CounterexamplePolicy, policy_value)
            if policy_value is not None
            else CounterexamplePolicy()
        )
        return [adjudicate_scored_pair(spec, trials, policy)], []
    if kind == "exact_answer":
        item = _benchmark_item(raw.get("item"))
        routes = [route.to_dict() for route in verification_capabilities(item)]
        return replay_exact_answer_pairs(item), routes
    if kind == "route_only":
        item = _benchmark_item(raw.get("item"))
        return [], [route.to_dict() for route in verification_capabilities(item)]
    raise ValueError(f"unsupported record kind: {kind!r}")


def render_markdown(result: Mapping[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# Counterexample evidence replay",
        "",
        f"- Records: **{result['records']}**",
        f"- Decisions: **{summary['decisions']}**",
        f"- Input errors: **{summary['errors']}**",
        "",
        "| Pair | Family | Status | Evidence tier | Proof kind |",
        "|---|---|---|---|---|",
    ]
    for row in result["decisions"]:
        lines.append(
            f"| `{row['pair_id']}` | {row['family']} | {row['status']} | "
            f"{row['evidence_tier']} | {row['proof_kind']} |"
        )
    if result["errors"]:
        lines.extend(["", "## Rejected records", ""])
        for row in result["errors"]:
            lines.append(f"- Record {row['index']}: {row['error']}")
    lines.extend([
        "",
        "## Boundary",
        "",
        "An expected-behavior result validates only the supplied intervention. "
        "It is not proof that the full benchmark item is clean.",
    ])
    return "\n".join(lines) + "\n"


def _strict_dataclass(cls, value):
    if not isinstance(value, dict):
        raise ValueError(f"{cls.__name__} payload must be an object")
    allowed = {field.name for field in fields(cls)}
    unexpected = set(value) - allowed
    if unexpected:
        raise ValueError(
            f"{cls.__name__} has unexpected field(s): {', '.join(sorted(unexpected))}"
        )
    return cls(**value)


def _benchmark_item(value: Any) -> BenchmarkItem:
    if not isinstance(value, dict):
        raise ValueError("item must be an object")
    allowed = {field.name for field in fields(BenchmarkItem)}
    unexpected = set(value) - allowed
    if unexpected:
        raise ValueError(f"BenchmarkItem has unexpected field(s): {', '.join(sorted(unexpected))}")
    if not value.get("item_id"):
        raise ValueError("item.item_id is required")
    row = dict(value)
    row.setdefault("raw", {})
    return BenchmarkItem(**row)


def main() -> None:
    args = parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    result = replay_manifest(payload)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md:
        md = Path(args.md)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
