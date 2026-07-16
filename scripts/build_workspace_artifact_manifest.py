#!/usr/bin/env python3
"""Hash every materialized Workspace benchmark input for reproducible audits."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchcore.loader import build_items, load_mapping, load_rows
from benchcore.workspace_invariants import workspace_artifact_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--root", help="Root for relative input paths")
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = Path(args.dataset).resolve()
    rows = load_rows(dataset)
    items = build_items(rows, load_mapping(None, rows))
    result = workspace_artifact_manifest(
        items,
        Path(args.root).resolve() if args.root else dataset.parent,
    )
    result["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["dataset"] = str(dataset)
    result["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
    revisions = sorted({
        str(item.metadata.get("source_revision"))
        for item in items if item.metadata.get("source_revision")
    })
    result["source_revisions"] = revisions
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result["summary"]["missing_files"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
