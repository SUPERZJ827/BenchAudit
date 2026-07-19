#!/usr/bin/env python3
"""Run the provenance-safe paired Workspace-Bench invariant challenge.

Examples:

  python scripts/run_workspace_invariant_experiment.py --suite lite100
  python scripts/run_workspace_invariant_experiment.py --suite full388 --workers 8

The audited clean/mutant JSONL files contain no mutation provenance.  The only
mapping between source, clean, mutant, operator, and expected evidence is the
separate ``challenge_manifest.json`` sidecar.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchcore.loader import load_rows
from benchcore.workspace_challenge import (
    WORKSPACE_CHALLENGE_OPERATORS,
    audit_workspace_challenge,
    build_workspace_challenge,
    render_workspace_challenge_markdown,
    rows_contain_provenance,
)


SUITES = {
    "lite100": Path("datasets/workspacebench/lite_100.jsonl"),
    "full388": Path("datasets/workspacebench/full.jsonl"),
}

# These hashes bind the convenience auto-containment path to the exact local
# exports used for the reported experiments.  Dataset overrides must opt into
# their attachment roots explicitly instead of widening access from row data.
PINNED_SUITE_SHA256 = {
    "lite100": "fe59c5962694214e8ed5bb9c3a1ef0d7e3b8a5ad94536e1504486802a50803db",
    "full388": "2e3d8fd1f5a741b9e6b73ebab9ce23e26ce054527b4f3477de8fdd950aad9dbe",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=sorted(SUITES), default="lite100")
    parser.add_argument(
        "--dataset",
        help="Optional Workspace JSONL override; --suite still names the output directory",
    )
    parser.add_argument("--seed", type=int, default=20260714)
    parser.add_argument("--limit", type=int, help="Run only the first N source tasks")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--allow-input-root",
        action="append",
        default=[],
        help=(
            "Repeatable realpath containment root for declared attachments. "
            "Required for dataset overrides; pinned built-in suites discover "
            "only their Hugging Face dataset cache root."
        ),
    )
    parser.add_argument(
        "--operator",
        action="append",
        choices=WORKSPACE_CHALLENGE_OPERATORS,
        help="Repeat to select a subset; default runs all five objective mutations",
    )
    parser.add_argument(
        "--out-dir",
        help="Default: reports/workspace_invariant_experiment_<suite>_20260714",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero on any exact miss, paired failure, extra alarm, or duplicate alarm",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    implementation_before = implementation_manifest()
    dataset = Path(args.dataset) if args.dataset else SUITES[args.suite]
    if not dataset.is_absolute():
        dataset = REPO / dataset
    if not dataset.is_file():
        raise FileNotFoundError(dataset)
    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else REPO / "reports" / f"workspace_invariant_experiment_{args.suite}_20260714"
    )
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(dataset)
    if args.limit is not None:
        if args.limit < 0:
            raise ValueError("--limit must be non-negative")
        rows = rows[: args.limit]
    if not rows:
        raise ValueError("selected Workspace dataset is empty")

    dataset_digest = file_sha256(dataset)
    allowed_roots = resolve_allowed_roots(
        rows,
        explicit=args.allow_input_root,
        suite=args.suite,
        dataset_digest=dataset_digest,
        using_override=bool(args.dataset),
    )

    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    challenge = build_workspace_challenge(
        rows,
        seed=args.seed,
        operators=args.operator,
        allowed_roots=allowed_roots,
    )
    if rows_contain_provenance(challenge.clean_rows) or rows_contain_provenance(
        challenge.mutant_rows
    ):
        raise RuntimeError("challenge provenance leaked into an audited row")

    write_jsonl(out_dir / "clean.jsonl", challenge.clean_rows)
    write_jsonl(out_dir / "mutants.jsonl", challenge.mutant_rows)
    write_json(out_dir / "challenge_manifest.json", challenge.manifest())

    print(
        f"Workspace challenge: suite={args.suite} sources={len(rows)} "
        f"clean={len(challenge.clean_rows)} mutants={len(challenge.mutant_rows)}",
        flush=True,
    )
    result = audit_workspace_challenge(
        challenge,
        root=None,
        allowed_roots=allowed_roots,
        workers=max(1, args.workers),
    )
    write_json(out_dir / "clean_audit.json", result["clean"])
    write_json(out_dir / "mutant_audit.json", result["mutant"])

    implementation_after = implementation_manifest()
    if implementation_after["sha256"] != implementation_before["sha256"]:
        raise RuntimeError(
            "auditor source changed while the experiment was running; discard the "
            "partial outputs and rerun against one frozen implementation"
        )

    artifact_hashes = {
        name: file_sha256(out_dir / name)
        for name in (
            "clean.jsonl",
            "mutants.jsonl",
            "challenge_manifest.json",
            "clean_audit.json",
            "mutant_audit.json",
        )
    }

    finished_at = datetime.now(timezone.utc)
    summary = {
        "run": {
            "suite": args.suite,
            "dataset": str(dataset),
            "dataset_sha256": dataset_digest,
            "allowed_input_roots": [str(path) for path in allowed_roots],
            "seed": args.seed,
            "source_items": len(rows),
            "workers": max(1, args.workers),
            "operators": list(args.operator or WORKSPACE_CHALLENGE_OPERATORS),
            "started_at_utc": started_at.isoformat(),
            "finished_at_utc": finished_at.isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "git": git_metadata(),
            "implementation": implementation_before,
            "artifact_sha256": artifact_hashes,
        },
        "challenge": {
            "clean_items": len(challenge.clean_rows),
            "mutant_items": len(challenge.mutant_rows),
            "pair_count": len(challenge.provenance),
            "skipped_count": len(challenge.skipped),
        },
        "metrics": result["score"],
    }
    write_json(out_dir / "summary.json", summary)
    (out_dir / "summary.md").write_text(
        render_workspace_challenge_markdown(
            challenge,
            result["score"],
            dataset=str(dataset),
        ),
        encoding="utf-8",
    )

    score = result["score"]
    print(
        "Result: "
        f"exact={score['exact_detected']}/{score['pairs']} "
        f"paired={score['paired_discriminated']}/{score['pairs']} "
        f"extra={score['extra_alarm_count']} "
        f"duplicate={score['duplicate_alarm_count']} "
        f"clean_items_with_alarm={score['clean_alarm_items']}/{score['unique_clean_items']}",
        flush=True,
    )
    print(f"Wrote {out_dir}", flush=True)

    if args.strict and (
        score["exact_detected"] != score["pairs"]
        or score["paired_discriminated"] != score["pairs"]
        or score["extra_alarm_count"]
        or score["duplicate_alarm_count"]
    ):
        return 2
    return 0


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def implementation_manifest() -> dict[str, Any]:
    """Bind a dirty-worktree run to the exact Python source bytes it executed."""

    paths = [Path(__file__).resolve(), *sorted((REPO / "benchcore").glob("*.py"))]
    files = {
        path.relative_to(REPO).as_posix(): file_sha256(path)
        for path in paths
        if path.is_file()
    }
    canonical = json.dumps(
        files, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": "workspace-invariant-source-manifest-v1",
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "files": files,
    }


def resolve_allowed_roots(
    rows: list[dict[str, Any]],
    *,
    explicit: list[str],
    suite: str,
    dataset_digest: str,
    using_override: bool,
) -> tuple[Path, ...]:
    """Return fail-closed roots without trusting arbitrary row path prefixes."""
    if explicit:
        roots = tuple(Path(value).expanduser().resolve() for value in explicit)
        missing = [str(path) for path in roots if not path.is_dir()]
        if missing:
            raise ValueError(f"allowed input root(s) are not directories: {missing}")
        return roots

    expected = PINNED_SUITE_SHA256.get(suite)
    if using_override or expected != dataset_digest:
        raise ValueError(
            "dataset is not the pinned built-in export; pass one or more "
            "--allow-input-root values explicitly"
        )

    candidates: set[Path] = set()
    for row in rows:
        values = row.get("input_files")
        if not isinstance(values, list):
            continue
        for value in values:
            path = Path(str(value)).expanduser()
            if not path.is_absolute():
                raise ValueError(
                    "pinned Workspace export unexpectedly contains a relative attachment path"
                )
            cache_root = next(
                (
                    parent for parent in (path, *path.parents)
                    if parent.name in {
                        "datasets--Workspace-Bench--Workspace-Bench-Lite",
                        "datasets--Workspace-Bench--Workspace-Bench",
                    }
                ),
                None,
            )
            if cache_root is None:
                raise ValueError(
                    f"attachment is outside the expected pinned HF cache: {path}"
                )
            candidates.add(cache_root.resolve())
    if not candidates:
        raise ValueError("no trusted attachment roots could be established")
    return tuple(sorted(candidates, key=str))


def git_metadata() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


if __name__ == "__main__":
    raise SystemExit(main())
