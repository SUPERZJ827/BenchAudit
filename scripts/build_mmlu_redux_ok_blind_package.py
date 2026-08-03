#!/usr/bin/env python3
"""Build the four-arm MMLU-Redux blind package and a repository-external sealed map."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import verify_mmlu_redux_ok_mechanical as mechanical


PROTOCOL_V1 = ROOT / "docs/research/MMLU_REDUX_OK_BLIND_ADJUDICATION_PROTOCOL_20260803.md"
PROTOCOL_V2 = ROOT / "docs/research/MMLU_REDUX_OK_BLIND_ADJUDICATION_PROTOCOL_V2_20260803.md"
MECHANICAL_RECEIPT = ROOT / "reports/mmlu_redux_ok_mechanical_20260803/receipt.json"
EXPECTED_HASHES = {
    "protocol_v1": "93ee87f57e761a13a4b3f7af5d9581222362393b3cf9f45b19f5fae560ee4868",
    "protocol_v2": "e6c004f1f600159716a187ea32f48234ca40b521be8df23b39c44e3c1aa9c846",
    "mechanical_receipt": "2634748bb9cbbf67efeac9bf9cd94166709c0ef390c8546052b4063f67a92365",
}
SEED = "benchaudit-mmlu-redux-ok-blind-adjudication-v1-20260803"
ARM_SIZE = 40
PUBLIC_KEYS = frozenset({"blind_id", "question", "choices", "declared_gold", "evaluator"})
FORBIDDEN_PUBLIC_FRAGMENTS = (
    "class", "redux", "error_type", "subject", "item_id", "finding", "method",
    "confidence", "evidence", "source", "potential_reason", "verified",
)


class PackageError(RuntimeError):
    pass


def stable_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_inputs() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, set[str]]]:
    for name, path in {
        "protocol_v1": PROTOCOL_V1,
        "protocol_v2": PROTOCOL_V2,
        "mechanical_receipt": MECHANICAL_RECEIPT,
    }.items():
        actual = sha256_file(path)
        if actual != EXPECTED_HASHES[name]:
            raise PackageError(f"frozen hash mismatch: {name}: {actual}")
    rows, report = mechanical.load_frozen()
    selected = mechanical.pools(rows, report)
    receipt = json.loads(MECHANICAL_RECEIPT.read_text(encoding="utf-8"))
    if receipt.get("outcome") != "PASS_MECHANICAL_ROUTING_COMPLETE":
        raise PackageError("mechanical routing receipt is not PASS")
    if receipt.get("items_inspected") != 86 or not receipt.get("all_d_items_ran_both_rules"):
        raise PackageError("mechanical routing did not cover every D item")
    return rows, report, receipt, selected


def rank(domain: str, subject: str, item_id: str) -> str:
    payload = "\0".join((SEED, domain, subject, item_id)).encode()
    return hashlib.sha256(payload).hexdigest()


def largest_remainder_quotas(subject_counts: Counter[str], size: int) -> dict[str, int]:
    total = sum(subject_counts.values())
    if total < 1 or size < 1:
        raise PackageError("invalid quota population")
    exact = {subject: size * count / total for subject, count in subject_counts.items()}
    quotas = {subject: int(value) for subject, value in exact.items()}
    remaining = size - sum(quotas.values())
    order = sorted(subject_counts, key=lambda subject: (-(exact[subject] - quotas[subject]), subject))
    for subject in order[:remaining]:
        quotas[subject] += 1
    if sum(quotas.values()) != size:
        raise PackageError("largest-remainder quota mismatch")
    return dict(sorted(quotas.items()))


def select_control(
    pool: set[str], by_id: dict[str, dict[str, Any]],
    d_subject_counts: Counter[str], domain: str, *, size: int = ARM_SIZE,
) -> tuple[list[str], dict[str, Any]]:
    by_subject: dict[str, list[str]] = defaultdict(list)
    for item_id in pool:
        subject = str(by_id[item_id]["metadata"]["subject"])
        by_subject[subject].append(item_id)
    for subject, item_ids in by_subject.items():
        item_ids.sort(key=lambda item_id: (rank(domain, subject, item_id), item_id))
    target = largest_remainder_quotas(d_subject_counts, size)
    assigned = {subject: min(quota, len(by_subject.get(subject, []))) for subject, quota in target.items()}
    deficit = size - sum(assigned.values())
    redistribution_order = sorted(
        by_subject,
        key=lambda subject: (-d_subject_counts.get(subject, 0), subject),
    )
    while deficit:
        progress = False
        for subject in redistribution_order:
            if assigned.get(subject, 0) < len(by_subject[subject]):
                assigned[subject] = assigned.get(subject, 0) + 1
                deficit -= 1
                progress = True
                if deficit == 0:
                    break
        if not progress:
            raise PackageError(f"insufficient control pool for {domain}")
    chosen = []
    for subject, quota in sorted(assigned.items()):
        chosen.extend(by_subject[subject][:quota])
    if len(chosen) != size or len(chosen) != len(set(chosen)):
        raise PackageError(f"control selection mismatch: {domain}")
    return chosen, {
        "target_subject_quotas": target,
        "actual_subject_quotas": dict(sorted((s, q) for s, q in assigned.items() if q)),
        "shortage_redistribution_count": sum(
            max(0, assigned.get(subject, 0) - target.get(subject, 0)) for subject in assigned
        ),
    }


def blinded_id(salt: bytes, item_id: str) -> str:
    return hmac.new(salt, b"id\0" + item_id.encode(), hashlib.sha256).hexdigest()


def order_key(salt: bytes, item_id: str) -> str:
    return hmac.new(salt, b"order\0" + item_id.encode(), hashlib.sha256).hexdigest()


def build(
    rows: list[dict[str, Any]], report: dict[str, Any], mechanical_receipt: dict[str, Any],
    selected: dict[str, set[str]], salt: bytes,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if len(salt) != 32:
        raise PackageError("salt must be exactly 32 bytes")
    by_id = {row["id"]: row for row in rows}
    mechanical_ids = set(mechanical_receipt["mechanically_confirmed_item_ids"])
    if not mechanical_ids <= selected["d"]:
        raise PackageError("mechanical result outside D pool")
    semantic_d = selected["d"] - mechanical_ids
    d_subject_counts = Counter(str(by_id[item_id]["metadata"]["subject"]) for item_id in semantic_d)
    p_agree, q1 = select_control(selected["p_agree"], by_id, d_subject_counts, "p_agree")
    p_missed, q2 = select_control(selected["p_missed"], by_id, d_subject_counts, "p_missed")
    n_agree, q3 = select_control(selected["n_agree"], by_id, d_subject_counts, "n_agree")
    arms = {
        "d": sorted(semantic_d),
        "p_agree": p_agree,
        "p_missed": p_missed,
        "n_agree": n_agree,
    }
    all_ids = [item_id for values in arms.values() for item_id in values]
    if len(all_ids) != 205 or len(all_ids) != len(set(all_ids)):
        raise PackageError("four-arm union mismatch")

    report_findings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for violation in report["violations"]:
        if mechanical.substantive_review(violation):
            report_findings[violation["item_id"]].append(violation)

    public = []
    mapping_items = []
    for arm, item_ids in arms.items():
        for item_id in item_ids:
            row = by_id[item_id]
            blind = blinded_id(salt, item_id)
            public_row = {
                "blind_id": blind,
                "question": row["question"],
                "choices": row["choices"],
                "declared_gold": row["gold"],
                "evaluator": row["evaluator"],
            }
            if set(public_row) != PUBLIC_KEYS:
                raise PackageError("public schema mismatch")
            lowered_keys = "\n".join(public_row).lower()
            if any(fragment in lowered_keys for fragment in FORBIDDEN_PUBLIC_FRAGMENTS):
                raise PackageError("public package key leaks source class")
            public.append((order_key(salt, item_id), public_row))
            mapping_items.append({
                "blind_id": blind,
                "item_id": item_id,
                "arm": arm,
                "redux_error_type": row["metadata"]["error_type"],
                "subject": row["metadata"]["subject"],
                "frozen_substantive_review_findings": [
                    {
                        "detection_method": violation["detection_method"],
                        "defect_type": violation["defect_type"],
                        "artifact": violation["artifact"],
                        "evidence_tier": violation["evidence_tier"],
                    }
                    for violation in report_findings.get(item_id, [])
                ],
            })
    public_rows = [row for _key, row in sorted(public, key=lambda pair: pair[0])]
    mapping = {
        "schema_version": "mmlu-redux-ok-blind-mapping-v1",
        "salt_hex": salt.hex(),
        "seed": SEED,
        "mechanically_confirmed_item_ids": sorted(mechanical_ids),
        "items": sorted(mapping_items, key=lambda item: item["blind_id"]),
    }
    receipt = {
        "schema_version": "mmlu-redux-ok-blind-package-receipt-v1",
        "outcome": "PASS_BLIND_PACKAGE_205",
        "public_rows": len(public_rows),
        "mechanically_confirmed_count": len(mechanical_ids),
        "blind_semantic_d_count": len(semantic_d),
        "control_counts": {"p_agree": 40, "p_missed": 40, "n_agree": 40},
        "source_pool_counts": {
            "d_before_mechanical": 86, "p_agree": 196, "p_missed": 142,
            "n_agree": 544, "expert_review": 10, "expert_no_review": 22,
        },
        "quota_receipts": {"p_agree": q1, "p_missed": q2, "n_agree": q3},
        "public_schema_keys": sorted(PUBLIC_KEYS),
        "class_field_emitted": False,
        "redux_label_emitted": False,
        "subject_emitted": False,
        "source_item_id_emitted": False,
        "finding_emitted": False,
        "salt_sha256": hashlib.sha256(salt).hexdigest(),
        "mapping_item_count": len(mapping_items),
        "api_attempts": 0,
        "network_attempts": 0,
        "adjudication_performed": False,
        "frozen_hashes": {
            **EXPECTED_HASHES,
            "builder": sha256_file(Path(__file__)),
        },
    }
    return public_rows, mapping, receipt


def run(public_out: Path, mapping_out: Path, receipt_out: Path, *, salt: bytes | None = None) -> dict[str, Any]:
    if mapping_out.resolve() == ROOT or ROOT in mapping_out.resolve().parents:
        raise PackageError("sealed mapping must be outside repository")
    if mapping_out.exists():
        raise PackageError("refusing to overwrite sealed mapping")
    rows, report, mechanical_receipt, selected = verify_inputs()
    salt = os.urandom(32) if salt is None else salt
    public, mapping, receipt = build(rows, report, mechanical_receipt, selected, salt)
    public_out.parent.mkdir(parents=True, exist_ok=True)
    mapping_out.parent.mkdir(parents=True, exist_ok=True)
    receipt_out.parent.mkdir(parents=True, exist_ok=True)
    public_out.write_bytes(b"".join(stable_bytes(row) for row in public))
    mapping_out.write_bytes(stable_bytes(mapping))
    os.chmod(mapping_out, 0o600)
    receipt.update({
        "public_package_sha256": sha256_file(public_out),
        "sealed_mapping_sha256": sha256_file(mapping_out),
        "sealed_mapping_path_emitted": False,
    })
    receipt_out.write_bytes(stable_bytes(receipt))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-out", type=Path, required=True)
    parser.add_argument("--mapping-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()
    receipt = run(args.public_out, args.mapping_out, args.receipt_out)
    print(json.dumps({
        "outcome": receipt["outcome"],
        "public_rows": receipt["public_rows"],
        "mechanically_confirmed_count": receipt["mechanically_confirmed_count"],
        "blind_semantic_d_count": receipt["blind_semantic_d_count"],
        "public_package_sha256": receipt["public_package_sha256"],
        "sealed_mapping_sha256": receipt["sealed_mapping_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
