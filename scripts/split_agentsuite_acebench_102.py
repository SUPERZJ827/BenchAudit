#!/usr/bin/env python3
"""Split the ACEBench-102 balanced subset into a dev half and a held-back test half.

The labels of this subset were unsealed on 2026-08-16, so the test half is only a
not-individually-inspected half, never a blind holdout. It exists to stop per-item
tuning from silently consuming every labelled case.

The assignment is a pure function of the frozen audit input and a fixed seed
label, so it can be regenerated from code alone; the emitted files are a
convenience, not the source of truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any


SEED_LABEL = "agentsuite-acebench-102-devtest-split-v1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def task_name(row: dict[str, Any]) -> str:
    metadata = row.get("metadata")
    name = metadata.get("task_name") if isinstance(metadata, dict) else None
    if not name:
        raise SystemExit(f"row {row.get('id')!r} has no metadata.task_name to stratify on")
    return str(name)


def build_strata(
    audit_rows: list[dict[str, Any]], truth_by_id: dict[str, int]
) -> dict[tuple[str, int], list[str]]:
    """Group item ids by (ACEBench task type, human label)."""
    strata: dict[tuple[str, int], list[str]] = {}
    for row in audit_rows:
        item_id = str(row["id"])
        strata.setdefault((task_name(row), truth_by_id[item_id]), []).append(item_id)
    return strata


def seed_for(audit_sha256: str) -> int:
    digest = hashlib.sha256(f"{SEED_LABEL}:{audit_sha256}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _assign(
    shuffled: dict[tuple[str, int], list[str]], negative_extra_to_dev: bool
) -> tuple[list[str], list[str]]:
    """Halve every stratum, alternating the odd member independently per label.

    Sharing one alternation flag across both labels lets every odd positive
    stratum tip the same way, which skews the per-half issue count.
    """
    dev: list[str] = []
    test: list[str] = []
    extra_to_dev = {1: True, 0: negative_extra_to_dev}
    for key in sorted(shuffled):
        members = shuffled[key]
        label = key[1]
        cut = len(members) // 2
        if len(members) % 2:
            if extra_to_dev[label]:
                cut += 1
            extra_to_dev[label] = not extra_to_dev[label]
        dev.extend(members[:cut])
        test.extend(members[cut:])
    return dev, test


def split_ids(
    strata: dict[tuple[str, int], list[str]], seed: int
) -> tuple[list[str], list[str]]:
    rng = random.Random(seed)
    shuffled: dict[tuple[str, int], list[str]] = {}
    for key in sorted(strata):
        members = sorted(strata[key])
        rng.shuffle(members)
        shuffled[key] = members
    for negative_extra_to_dev in (False, True):
        dev, test = _assign(shuffled, negative_extra_to_dev)
        if len(dev) == len(test):
            return sorted(dev), sorted(test)
    raise SystemExit("no alternating assignment yields an even split")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-input", required=True, type=Path)
    parser.add_argument("--sealed-truth", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    dev_path = args.out_dir / "dev_ids.json"
    test_path = args.out_dir / "test_ids.json"
    receipt_path = args.out_dir / "receipt.json"
    for path in (dev_path, test_path, receipt_path):
        if path.exists():
            raise SystemExit(f"refusing to overwrite existing experiment artifact: {path}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    audit_rows = load_jsonl(args.audit_input)
    truth_by_id = {str(row["id"]): int(row["is_issue"]) for row in load_jsonl(args.sealed_truth)}
    audit_ids = {str(row["id"]) for row in audit_rows}
    if len(audit_ids) != 102 or set(truth_by_id) != audit_ids:
        raise SystemExit("audit input and sealed truth must share the same 102 unique ids")
    if sum(truth_by_id.values()) != 51:
        raise SystemExit("expected exactly 51 positive labels")

    audit_sha256 = sha256_file(args.audit_input)
    strata = build_strata(audit_rows, truth_by_id)
    dev, test = split_ids(strata, seed_for(audit_sha256))

    if set(dev) & set(test):
        raise SystemExit("dev and test halves overlap")
    if set(dev) | set(test) != audit_ids:
        raise SystemExit("dev and test halves do not cover the audit input")
    if len(dev) != 51 or len(test) != 51:
        raise SystemExit(f"expected a 51/51 split, got {len(dev)}/{len(test)}")
    dev_positive = sum(truth_by_id[item_id] for item_id in dev)
    test_positive = sum(truth_by_id[item_id] for item_id in test)
    if {dev_positive, test_positive} != {25, 26}:
        raise SystemExit(f"expected 25/26 positives per half, got {dev_positive}/{test_positive}")

    dev_path.write_text(json.dumps(dev, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    test_path.write_text(json.dumps(test, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "protocol": SEED_LABEL,
        "holdout_strength": (
            "not-individually-inspected half; labels were unsealed 2026-08-16 and the "
            "aggregate failure-mode breakdown is already published, so this is not a blind holdout"
        ),
        "audit_input_sha256": audit_sha256,
        "sealed_truth_sha256": sha256_file(args.sealed_truth),
        "strata": len(strata),
        "dev": {"items": len(dev), "positive": dev_positive},
        "test": {"items": len(test), "positive": test_positive},
        "dev_ids_sha256": sha256_file(dev_path),
        "test_ids_sha256": sha256_file(test_path),
    }
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
