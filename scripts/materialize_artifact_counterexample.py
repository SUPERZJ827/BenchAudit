"""Materialize a deterministic rubric/workspace artifact counterexample.

The mutation plan contains only operator/target parameters.  Baseline and
variant roots are explicit CLI arguments so an untrusted plan cannot redirect
filesystem access.  The emitted certificate is a sidecar and is not copied into
the evaluator-visible variant.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchcore.artifact_mutation import (
    ArtifactMutation,
    materialize_artifact_variant,
    scored_pair_spec_from_certificate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="Read-only baseline artifact directory")
    parser.add_argument("--variant", required=True, help="New directory to create")
    parser.add_argument("--plan", required=True, help="Mutation plan JSON")
    parser.add_argument("--certificate", required=True, help="Output sidecar certificate JSON")
    parser.add_argument("--max-files", type=int, default=2_000)
    parser.add_argument("--max-total-bytes", type=int, default=512_000_000)
    return parser.parse_args()


def materialize_from_plan(
    baseline: Path,
    variant: Path,
    plan: dict,
    *,
    max_files: int = 2_000,
    max_total_bytes: int = 512_000_000,
) -> dict:
    rows = plan.get("mutations")
    if not isinstance(rows, list):
        raise ValueError("plan.mutations must be a list")
    mutations = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"plan.mutations[{index}] must be an object")
        unexpected = set(row) - {"operator", "relative_path", "parameters"}
        if unexpected:
            raise ValueError(
                f"plan.mutations[{index}] unexpected field(s): "
                + ", ".join(sorted(unexpected))
            )
        mutations.append(ArtifactMutation(
            operator=str(row.get("operator") or ""),
            relative_path=str(row.get("relative_path") or ""),
            parameters=row.get("parameters") or {},
        ))
    scored = plan.get("scored_pair")
    if scored is not None:
        if not isinstance(scored, dict):
            raise ValueError("plan.scored_pair must be an object")
        allowed = {
            "family", "relation", "rubric_quote", "target_criterion",
            "expected_min_delta", "invariance_tolerance", "explicit_requirement",
            "official_evaluator", "grader_kind",
        }
        unexpected = set(scored) - allowed
        if unexpected:
            raise ValueError(
                "plan.scored_pair unexpected field(s): " + ", ".join(sorted(unexpected))
            )
        required = {"family", "relation", "rubric_quote"}
        missing = required - set(scored)
        if missing:
            raise ValueError(
                "plan.scored_pair missing field(s): " + ", ".join(sorted(missing))
            )
    certificate = materialize_artifact_variant(
        baseline,
        variant,
        mutations,
        max_files=max_files,
        max_total_bytes=max_total_bytes,
    )
    result = {"certificate": certificate.to_dict()}
    if scored is not None:
        spec = scored_pair_spec_from_certificate(certificate, **scored)
        result["scored_pair_spec"] = {
            **spec.__dict__,
            "changed_paths": list(spec.changed_paths),
        }
    return result


def main() -> None:
    args = parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("plan root must be an object")
    result = materialize_from_plan(
        Path(args.baseline),
        Path(args.variant),
        plan,
        max_files=args.max_files,
        max_total_bytes=args.max_total_bytes,
    )
    out = Path(args.certificate)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "mutation_id": result["certificate"]["mutation_id"],
        "changed_paths": result["certificate"]["changed_paths"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
