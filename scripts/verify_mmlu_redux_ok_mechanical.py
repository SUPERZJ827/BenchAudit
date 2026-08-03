#!/usr/bin/env python3
"""Run the two frozen deterministic rules over all 86 MMLU-Redux ok candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchcore.evaluators import choice_label_to_index, normalize_choice_for_duplicate


SOURCE = ROOT / "experiments/mmlu_redux_pilot1000.jsonl"
REPORT = ROOT / "reports/ranking_impact/audit_full1000.json"
PROTOCOL_V1 = ROOT / "docs/research/MMLU_REDUX_OK_BLIND_ADJUDICATION_PROTOCOL_20260803.md"
PROTOCOL_V2 = ROOT / "docs/research/MMLU_REDUX_OK_BLIND_ADJUDICATION_PROTOCOL_V2_20260803.md"
EXPECTED_HASHES = {
    "source": "70cc9ee184db4017b323bda03061f7c3d56e57ad1ab4b1a3415263fd664072b8",
    "report": "8fc5fa57330b704faa48f7007f228a7ae3f44d02beaa30c1e96970ba9aa88cc6",
    "protocol_v1": "93ee87f57e761a13a4b3f7af5d9581222362393b3cf9f45b19f5fae560ee4868",
    "protocol_v2": "e6c004f1f600159716a187ea32f48234ca40b521be8df23b39c44e3c1aa9c846",
}
EXPECTED_D_ID_SET_SHA256 = "4ddb19f6c1cdff3d68f5e6c3a95d75b80d9268c420895bfbe88180122c479e1b"
EXPLICIT_DEFECTS = frozenset(
    {
        "wrong_groundtruth", "bad_question_clarity", "multiple_correct_answers",
        "no_correct_answer", "bad_options_clarity",
    }
)
DUP_ELIGIBLE = frozenset(
    {"duplicate_choices", "multiple_correct_answers", "bad_options_clarity"}
)
GOLD_DOMAIN_ELIGIBLE = frozenset(
    {"wrong_gold_answer", "no_correct_answer", "multiple_correct_answers"}
)
RULE_STATUSES = frozenset(
    {"mechanically_confirmed", "mechanically_not_triggered", "not_applicable"}
)


class VerificationError(RuntimeError):
    pass


def stable_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def substantive_review(violation: dict[str, Any]) -> bool:
    return (
        violation.get("defect_scope") == "substantive"
        and violation.get("evidence_tier") == "review"
    )


def single_choice_contract(row: dict[str, Any]) -> bool:
    evaluator = row.get("evaluator")
    return (
        isinstance(evaluator, dict)
        and evaluator.get("type") in {"multiple_choice", "multiple_choice_exact_match"}
    )


def duplicate_rule(row: dict[str, Any], defect_types: set[str]) -> dict[str, Any]:
    if not (defect_types & DUP_ELIGIBLE):
        return {"status": "not_applicable", "reason": "no_compatible_frozen_finding"}
    choices = row.get("choices")
    if not isinstance(choices, list) or len(choices) < 2:
        return {"status": "not_applicable", "reason": "choices_not_explicit_list"}
    normalized = [normalize_choice_for_duplicate(choice) for choice in choices]
    duplicate_groups: dict[str, list[int]] = defaultdict(list)
    for index, value in enumerate(normalized):
        if value:
            duplicate_groups[value].append(index)
    duplicates = [indices for indices in duplicate_groups.values() if len(indices) > 1]
    if not duplicates:
        return {
            "status": "mechanically_not_triggered",
            "reason": "no_exact_normalized_duplicate",
            "normalized_choice_sha256": hashlib.sha256(stable_bytes(normalized)).hexdigest(),
        }
    return {
        "status": "mechanically_confirmed",
        "confirmed_defect": "duplicate_choices",
        "compatibility": "mechanical_duplicate_supports_option_defect_only",
        "duplicate_index_groups": duplicates,
        "normalized_choice_sha256": hashlib.sha256(stable_bytes(normalized)).hexdigest(),
    }


def gold_domain_rule(row: dict[str, Any], defect_types: set[str]) -> dict[str, Any]:
    if not (defect_types & GOLD_DOMAIN_ELIGIBLE):
        return {"status": "not_applicable", "reason": "no_compatible_frozen_finding"}
    choices = row.get("choices")
    if not isinstance(choices, list) or len(choices) < 2:
        return {"status": "not_applicable", "reason": "choices_not_explicit_list"}
    if not single_choice_contract(row):
        return {"status": "not_applicable", "reason": "contract_not_explicit_single_choice"}
    gold = row.get("gold")
    if gold in (None, ""):
        return {"status": "not_applicable", "reason": "declared_gold_empty"}
    aliases = row.get("aliases")
    if aliases is None:
        aliases = []
    if not isinstance(aliases, list):
        return {"status": "not_applicable", "reason": "aliases_not_list"}
    declared = [gold, *aliases]
    mapped = [choice_label_to_index(value, choices) for value in declared]
    evidence = {
        "declared_value_sha256": hashlib.sha256(stable_bytes(declared)).hexdigest(),
        "choice_domain_size": len(choices),
        "mapped_indices": mapped,
    }
    if any(index is not None for index in mapped):
        return {
            "status": "mechanically_not_triggered",
            "reason": "declared_gold_or_alias_maps_to_choice_domain",
            **evidence,
        }
    return {
        "status": "mechanically_confirmed",
        "confirmed_defect": "declared_gold_outside_choice_domain",
        "compatibility": "supports_wrong_or_missing_gold_domain_claim_only",
        **evidence,
    }


def load_frozen() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    paths = {
        "source": SOURCE, "report": REPORT,
        "protocol_v1": PROTOCOL_V1, "protocol_v2": PROTOCOL_V2,
    }
    for name, path in paths.items():
        actual = sha256_file(path)
        if actual != EXPECTED_HASHES[name]:
            raise VerificationError(f"frozen hash mismatch: {name}: {actual}")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line]
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if len(rows) != 1000 or report.get("summary", {}).get("items") != 1000:
        raise VerificationError("frozen 1000-item population mismatch")
    return rows, report


def pools(rows: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, set[str]]:
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise VerificationError("duplicate source item ID")
    findings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for violation in report.get("violations", []):
        if violation.get("item_id") not in by_id:
            raise VerificationError("report finding references unknown item")
        findings[violation["item_id"]].append(violation)
    review = {
        item_id for item_id, violations in findings.items()
        if any(substantive_review(violation) for violation in violations)
    }
    labels = {item_id: row["metadata"]["error_type"] for item_id, row in by_id.items()}
    result = {
        "d": {item_id for item_id in review if labels[item_id] == "ok"},
        "p_agree": {item_id for item_id in review if labels[item_id] in EXPLICIT_DEFECTS},
        "p_missed": {
            item_id for item_id, label in labels.items()
            if label in EXPLICIT_DEFECTS and item_id not in review
        },
        "n_agree": {
            item_id for item_id, label in labels.items()
            if label == "ok" and item_id not in review
        },
        "expert_review": {item_id for item_id in review if labels[item_id] == "expert"},
        "expert_no_review": {
            item_id for item_id, label in labels.items()
            if label == "expert" and item_id not in review
        },
    }
    expected = {
        "d": 86, "p_agree": 196, "p_missed": 142, "n_agree": 544,
        "expert_review": 10, "expert_no_review": 22,
    }
    actual = {name: len(values) for name, values in result.items()}
    if actual != expected:
        raise VerificationError(f"frozen pool count mismatch: {actual}")
    d_sha = hashlib.sha256(("\n".join(sorted(result["d"])) + "\n").encode()).hexdigest()
    if d_sha != EXPECTED_D_ID_SET_SHA256:
        raise VerificationError("D item-set hash mismatch")
    return result


def verify_all(rows: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    by_id = {row["id"]: row for row in rows}
    selected = pools(rows, report)
    findings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for violation in report["violations"]:
        if substantive_review(violation):
            findings[violation["item_id"]].append(violation)
    item_results = []
    for item_id in sorted(selected["d"]):
        row = by_id[item_id]
        frozen = findings[item_id]
        defect_types = {violation["defect_type"] for violation in frozen}
        dup = duplicate_rule(row, defect_types)
        gold = gold_domain_rule(row, defect_types)
        if dup["status"] not in RULE_STATUSES or gold["status"] not in RULE_STATUSES:
            raise VerificationError("rule emitted unknown status")
        confirmed = [name for name, result in (("M-DUP-V1", dup), ("M-GOLD-DOMAIN-V1", gold))
                     if result["status"] == "mechanically_confirmed"]
        item_results.append({
            "item_id": item_id,
            "input_fields_sha256": hashlib.sha256(stable_bytes({
                "choices": row.get("choices"), "gold": row.get("gold"),
                "aliases": row.get("aliases", []), "evaluator": row.get("evaluator"),
            })).hexdigest(),
            "frozen_finding_keys": sorted({
                (violation["detection_method"], violation["defect_type"])
                for violation in frozen
            }),
            "rules": {"M-DUP-V1": dup, "M-GOLD-DOMAIN-V1": gold},
            "mechanically_confirmed_rules": confirmed,
            "route": "mechanical_confirmed" if confirmed else "blind_adjudication",
        })
    if len(item_results) != 86:
        raise VerificationError("not every D item was verified")
    mechanically_confirmed = [row["item_id"] for row in item_results if row["route"] == "mechanical_confirmed"]
    status_counts = {
        rule: dict(sorted(Counter(row["rules"][rule]["status"] for row in item_results).items()))
        for rule in ("M-DUP-V1", "M-GOLD-DOMAIN-V1")
    }
    return {
        "schema_version": "mmlu-redux-ok-mechanical-routing-v1",
        "outcome": "PASS_MECHANICAL_ROUTING_COMPLETE",
        "api_attempts": 0,
        "network_attempts": 0,
        "llm_used": False,
        "items_inspected": 86,
        "all_d_items_ran_both_rules": True,
        "pool_counts": {name: len(values) for name, values in selected.items()},
        "rule_status_counts": status_counts,
        "mechanically_confirmed_count": len(mechanically_confirmed),
        "mechanically_confirmed_item_ids": mechanically_confirmed,
        "blind_adjudication_count": 86 - len(mechanically_confirmed),
        "item_results": item_results,
        "frozen_hashes": {
            **EXPECTED_HASHES,
            "verifier": sha256_file(Path(__file__)),
        },
    }


def run(out: Path) -> dict[str, Any]:
    rows, report = load_frozen()
    result = verify_all(rows, report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(stable_bytes(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.out)
    print(json.dumps({
        "outcome": result["outcome"],
        "items_inspected": result["items_inspected"],
        "mechanically_confirmed_count": result["mechanically_confirmed_count"],
        "blind_adjudication_count": result["blind_adjudication_count"],
        "rule_status_counts": result["rule_status_counts"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
