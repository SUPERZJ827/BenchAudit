#!/usr/bin/env python3
"""Mine replayable anomalies from aligned MoDora multi-method outputs.

This script implements the frozen V2 protocol in:
docs/research/多模型执行结果挖掘缺陷_一日工单_V2_20260810.md

It deliberately separates hard local inconsistencies from hypotheses that
require the missing source PDFs or scoring contract.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


RULE_VERSION = "modora-defect-mining-v2"
METHOD_FILES = {
    "udop": "resudop.jsonl",
    "docowl": "resdocowl.jsonl",
    "m3rag": "resm3rag.jsonl",
    "svrag": "ressvrag.jsonl",
    "txtrag": "restxtrag.jsonl",
    "zendb": "reszendb.jsonl",
    "quest": "resquest.jsonl",
    "gpt5": "resgpt5.jsonl",
    "modora": "resmodora.jsonl",
}
EXPECTED_SHA256 = {
    "resdocowl.jsonl": "6b2200b92c6003753893eaeb88778502dafa4ee0bace2b1fd8d3c0ff8c57be40",
    "resgpt5.jsonl": "cfae7760d82f33ce4114134e106011008659c40bd1389912d307af11509196f1",
    "resm3rag.jsonl": "736e21ff1391ec3c05d95ff6bc0e4fadcf1769af924b0c04cd49a651ff1a2542",
    "resmodora.jsonl": "15fa922b92937cd95c7c39d28df89c6d8ece71588566da6e6f3d8c88859e6db4",
    "resquest.jsonl": "f71b4f8e1362a81e535088cbd51024aced95587ee4613d485a808e0929202d43",
    "ressvrag.jsonl": "229d02847d6abe367af8e71c292958f85f1fe57c8a05a625579dc9ca280e1d0f",
    "restxtrag.jsonl": "8a9093d1eb0f27be7b894385b22723dfee72f917521ecfb5a158b5c1d3c58e0d",
    "resudop.jsonl": "b9f3c2c6bfe7065ea5f29a7165afee193e5a64f75d11fc09532a62690ef1f036",
    "reszendb.jsonl": "6645dc5df7fb29883331720732dfaeb826dc203bdfd1da74e2ee0761c6b7b60a",
}
METHOD_FAMILY = {
    "udop": "udop",
    "docowl": "docowl",
    "m3rag": "shared_rag",
    "svrag": "shared_rag",
    "txtrag": "shared_rag",
    "zendb": "zendb",
    "quest": "quest",
    "gpt5": "gpt5",
    "modora": "modora",
}
ABILITY_ORDER = [
    "modora",
    "m3rag",
    "zendb",
    "gpt5",
    "svrag",
    "txtrag",
    "docowl",
    "udop",
    "quest",
]
EXPECTED_CORRECT_DISTRIBUTION = {
    0: 151,
    1: 132,
    2: 138,
    3: 116,
    4: 138,
    5: 141,
    6: 108,
    7: 83,
    8: 43,
    9: 15,
}
EXPECTED_ALL_WRONG_E1_BUCKETS = {"divergent_1": 89, "shared_2_4": 55, "convergent_5_plus": 7}
EXPECTED_ALL_WRONG_NONEMPTY_E1_METHOD_COUNTS = {5: 1, 7: 10, 8: 51, 9: 89}


class InputMismatch(RuntimeError):
    """The frozen input contract was not satisfied."""


@dataclass(frozen=True)
class LoadedData:
    by_method: dict[str, dict[int, dict[str, Any]]]
    ids: tuple[int, ...]
    input_hashes: dict[str, str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def e0(value: Any) -> str:
    return "" if value is None else str(value)


def e1(value: Any) -> str:
    """Conservative equality: NFKC + casefold + whitespace collapse only."""

    text = unicodedata.normalize("NFKC", e0(value)).casefold()
    return " ".join(text.split())


def nonempty_e1_prediction_groups(
    predictions_by_method: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Group semantic predictions while treating blank output as missing.

    V2.1 explicitly forbids blank predictions from forming an agreement group.
    Method iteration order is preserved within each group.
    """

    groups: dict[str, list[str]] = defaultdict(list)
    for method, prediction in predictions_by_method.items():
        normalized = e1(prediction)
        if normalized:
            groups[normalized].append(method)
    return dict(groups)


def as_answer_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value]


def answer_signature(value: Any) -> tuple[str, ...]:
    return tuple(e1(part) for part in as_answer_list(value))


def terminal_sentence_format(value: Any) -> str:
    """Used only to downgrade punctuation-only variants; never proves equality."""

    return e1(value).rstrip(" .!?。！？")


def e2_short_relation_text(value: Any) -> str:
    """Review-only text used to recognize an abbreviated answer relation."""

    visible = "".join(
        character
        for character in e0(value)
        if unicodedata.category(character) != "Cf"
        and not (unicodedata.category(character) == "Cc" and character not in "\t\n\r")
    )
    return terminal_sentence_format(visible)


def v1_loose_diagnostic(value: Any) -> str:
    """The superseded V1 transform, retained only to expose its false positives."""

    text = re.sub(r"[^\w%.\-/]+", " ", e0(value).lower()).strip()
    return re.sub(r"\s+", " ", text)


def unexpected_invisible_characters(value: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for position, character in enumerate(e0(value)):
        category = unicodedata.category(character)
        if category == "Cf" or (category == "Cc" and character not in "\t\n\r"):
            findings.append(
                {
                    "position": position,
                    "codepoint": f"U+{ord(character):04X}",
                    "unicode_name": unicodedata.name(character, "UNKNOWN"),
                    "category": category,
                }
            )
    return findings


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or not xs:
        raise ValueError("vectors must have equal non-zero length")
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    centered_x = [value - mean_x for value in xs]
    centered_y = [value - mean_y for value in ys]
    denominator = math.sqrt(
        sum(value * value for value in centered_x)
        * sum(value * value for value in centered_y)
    )
    if denominator == 0:
        return None
    return sum(x * y for x, y in zip(centered_x, centered_y)) / denominator


def load_data(input_dir: Path, *, enforce_hashes: bool = True) -> LoadedData:
    by_method: dict[str, dict[int, dict[str, Any]]] = {}
    input_hashes: dict[str, str] = {}
    for method, filename in METHOD_FILES.items():
        path = input_dir / filename
        if not path.is_file():
            raise InputMismatch(f"missing frozen input: {path}")
        actual_hash = sha256_file(path)
        input_hashes[filename] = actual_hash
        if enforce_hashes and actual_hash != EXPECTED_SHA256[filename]:
            raise InputMismatch(
                f"SHA-256 mismatch for {filename}: {actual_hash} != {EXPECTED_SHA256[filename]}"
            )
        rows: dict[int, dict[str, Any]] = {}
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                question_id = row.get("questionId")
                if not isinstance(question_id, int):
                    raise InputMismatch(f"{filename}:{line_number}: non-integer questionId")
                if question_id in rows:
                    raise InputMismatch(f"{filename}: duplicate questionId {question_id}")
                if row.get("judge") not in {"T", "F"}:
                    raise InputMismatch(f"{filename}:{line_number}: invalid judge {row.get('judge')!r}")
                rows[question_id] = row
        if len(rows) != 1065:
            raise InputMismatch(f"{filename}: expected 1065 rows, found {len(rows)}")
        by_method[method] = rows

    id_sets = {method: set(rows) for method, rows in by_method.items()}
    reference_ids = id_sets[next(iter(METHOD_FILES))]
    if reference_ids != set(range(1, 1066)):
        raise InputMismatch("frozen ID set is not exactly 1..1065")
    for method, ids in id_sets.items():
        if ids != reference_ids:
            raise InputMismatch(f"ID set differs for {method}")
    return LoadedData(by_method, tuple(sorted(reference_ids)), input_hashes)


def _field_signature(field: str, value: Any) -> Any:
    if field == "answer":
        return answer_signature(value)
    return e1(value)


def canonical_metadata(
    loaded: LoadedData,
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    canonical: dict[int, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    fields = ("pdf_id", "tag", "question", "answer")

    for question_id in loaded.ids:
        canonical_row: dict[str, Any] = {"questionId": question_id, "metadata_unresolved": False}
        for field in fields:
            variants: dict[Any, list[str]] = defaultdict(list)
            raw_by_method: dict[str, Any] = {}
            for method in METHOD_FILES:
                raw = loaded.by_method[method][question_id].get(field)
                raw_by_method[method] = raw
                variants[_field_signature(field, raw)].append(method)
            ranked = sorted(variants.items(), key=lambda item: (-len(item[1]), repr(item[0])))
            best_signature, best_methods = ranked[0]
            unique_winner = len(ranked) == 1 or len(best_methods) > len(ranked[1][1])
            if not unique_winner:
                canonical_row["metadata_unresolved"] = True
                canonical_row[field] = None
            else:
                representative = best_methods[0]
                value = raw_by_method[representative]
                canonical_row[field] = as_answer_list(value) if field == "answer" else value

            raw_shapes = {
                method: ("list" if isinstance(value, list) else type(value).__name__)
                for method, value in raw_by_method.items()
            }
            raw_serialized = {
                method: json.dumps(value, ensure_ascii=False, sort_keys=True)
                for method, value in raw_by_method.items()
            }
            structural_difference = len(set(raw_shapes.values())) > 1
            raw_difference = len(set(raw_serialized.values())) > 1
            semantic_difference = len(variants) > 1
            if structural_difference or raw_difference or semantic_difference:
                conflicts.append(
                    {
                        "questionId": question_id,
                        "field": field,
                        "structural_difference": structural_difference,
                        "semantic_difference_e1": semantic_difference,
                        "canonical_resolved": unique_winner,
                        "canonical_methods": ";".join(best_methods),
                        "variant_count": len(variants),
                        "raw_values_json": json.dumps(raw_by_method, ensure_ascii=False, sort_keys=True),
                        "raw_shapes_json": json.dumps(raw_shapes, ensure_ascii=False, sort_keys=True),
                    }
                )
        canonical[question_id] = canonical_row
    return canonical, conflicts


def _corrected_item_total(
    loaded: LoadedData, question_id: int, method_totals: Mapping[str, int]
) -> float | None:
    item_scores = [
        float(loaded.by_method[method][question_id]["judge"] == "T") for method in METHOD_FILES
    ]
    corrected_totals = [
        float(method_totals[method] - item_score)
        for method, item_score in zip(METHOD_FILES, item_scores)
    ]
    return pearson(item_scores, corrected_totals)


def analyze(loaded: LoadedData) -> dict[str, Any]:
    canonical, metadata_conflicts = canonical_metadata(loaded)
    method_totals = {
        method: sum(rows[question_id]["judge"] == "T" for question_id in loaded.ids)
        for method, rows in loaded.by_method.items()
    }

    response_rows: list[dict[str, Any]] = []
    hard_record_rows: list[dict[str, Any]] = []
    hard_artifact_rows: list[dict[str, Any]] = []
    convergence_rows: list[dict[str, Any]] = []
    inversion_rows: list[dict[str, Any]] = []
    scoring_relation_rows: list[dict[str, Any]] = []
    triage_rows: list[dict[str, Any]] = []

    h1_items: set[int] = set()
    h2_items: set[int] = set()
    s1_hard_items: set[int] = set()
    r1_items: set[int] = set()
    r2_items: set[int] = set()
    r3_items: set[int] = set()
    r4_items: set[int] = set()
    long_convergence_items: set[int] = set()
    max_convergence: dict[int, int] = {}
    nonempty_prediction_counts: dict[int, int] = {}
    corrected_rpb: dict[int, float | None] = {}

    # H1: same conservative prediction, conflicting stored judge.
    for question_id in loaded.ids:
        groups = nonempty_e1_prediction_groups(
            {
                method: loaded.by_method[method][question_id].get("prediction")
                for method in METHOD_FILES
            }
        )
        for normalized_prediction, methods in groups.items():
            if len(methods) < 2:
                continue
            labels = {loaded.by_method[method][question_id]["judge"] for method in methods}
            if labels != {"T", "F"}:
                continue
            raw_groups: dict[str, list[str]] = defaultdict(list)
            for method in methods:
                raw_groups[e0(loaded.by_method[method][question_id].get("prediction"))].append(method)
            e0_conflict = any(
                {
                    loaded.by_method[method][question_id]["judge"]
                    for method in raw_methods
                }
                == {"T", "F"}
                for raw_methods in raw_groups.values()
            )
            true_methods = [
                method for method in methods if loaded.by_method[method][question_id]["judge"] == "T"
            ]
            false_methods = [
                method for method in methods if loaded.by_method[method][question_id]["judge"] == "F"
            ]
            hard_record_rows.append(
                {
                    "questionId": question_id,
                    "pdf_id": canonical[question_id]["pdf_id"],
                    "tag": canonical[question_id]["tag"],
                    "evidence_level": "E0" if e0_conflict else "E1",
                    "normalized_prediction": normalized_prediction,
                    "methods_judged_T": ";".join(true_methods),
                    "methods_judged_F": ";".join(false_methods),
                    "raw_predictions_json": json.dumps(
                        {
                            method: loaded.by_method[method][question_id].get("prediction")
                            for method in methods
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "gold_json": json.dumps(canonical[question_id]["answer"], ensure_ascii=False),
                    "question": canonical[question_id]["question"],
                    "metadata_unresolved": canonical[question_id]["metadata_unresolved"],
                }
            )
            h1_items.add(question_id)

        # E2 punctuation-only variants with conflicting labels are review-only.
        format_groups: dict[str, list[str]] = defaultdict(list)
        for method in METHOD_FILES:
            prediction = loaded.by_method[method][question_id].get("prediction")
            formatted = terminal_sentence_format(prediction)
            if formatted:
                format_groups[formatted].append(method)
        for formatted_prediction, methods in format_groups.items():
            labels = {loaded.by_method[method][question_id]["judge"] for method in methods}
            if len(methods) < 2 or labels != {"T", "F"}:
                continue
            # Do not duplicate an E1 hard group.
            e1_groups = defaultdict(list)
            for method in methods:
                e1_groups[e1(loaded.by_method[method][question_id].get("prediction"))].append(
                    method
                )
            if any(
                {
                    loaded.by_method[method][question_id]["judge"]
                    for method in grouped_methods
                }
                == {"T", "F"}
                for grouped_methods in e1_groups.values()
            ):
                continue
            scoring_relation_rows.append(
                {
                    "questionId": question_id,
                    "method": "",
                    "relation_type": "prediction_format_variant_conflicting_judge",
                    "gold_json": json.dumps(
                        canonical[question_id]["answer"], ensure_ascii=False
                    ),
                    "prediction": formatted_prediction,
                    "question": canonical[question_id]["question"],
                    "note": "E2/review only; punctuation was not removed for hard equality",
                }
            )
            r3_items.add(question_id)

    # H2 and static hard anomalies.
    for question_id in loaded.ids:
        answers = canonical[question_id].get("answer") or []
        answer_norms = [e1(answer) for answer in answers]
        if any(not normalized for normalized in answer_norms):
            hard_artifact_rows.append(
                {
                    "questionId": question_id,
                    "anomaly_type": "empty_or_null_gold",
                    "gold_json": json.dumps(answers, ensure_ascii=False),
                    "evidence_json": "{}",
                    "question": canonical[question_id]["question"],
                }
            )
            s1_hard_items.add(question_id)
        if len(answer_norms) != len(set(answer_norms)):
            hard_artifact_rows.append(
                {
                    "questionId": question_id,
                    "anomaly_type": "duplicate_gold_elements_e1",
                    "gold_json": json.dumps(answers, ensure_ascii=False),
                    "evidence_json": json.dumps(answer_norms, ensure_ascii=False),
                    "question": canonical[question_id]["question"],
                }
            )
            s1_hard_items.add(question_id)
        for answer_index, answer in enumerate(answers):
            invisible = unexpected_invisible_characters(answer)
            if invisible:
                hard_artifact_rows.append(
                    {
                        "questionId": question_id,
                        "anomaly_type": "unexpected_invisible_or_control_gold",
                        "gold_json": json.dumps(answers, ensure_ascii=False),
                        "evidence_json": json.dumps(
                            {"answer_index": answer_index, "characters": invisible},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "question": canonical[question_id]["question"],
                    }
                )
                h2_items.add(question_id)

    # Same PDF + E1 question with differing gold: hard only if not terminal punctuation-only.
    repeated_questions: dict[tuple[str, str], list[int]] = defaultdict(list)
    for question_id in loaded.ids:
        repeated_questions[(e1(canonical[question_id]["pdf_id"]), e1(canonical[question_id]["question"]))].append(
            question_id
        )
    for (pdf_id, normalized_question), question_ids in repeated_questions.items():
        if len(question_ids) < 2:
            continue
        signatures = {
            tuple(e1(answer) for answer in canonical[question_id]["answer"])
            for question_id in question_ids
        }
        if len(signatures) <= 1:
            continue
        terminal_signatures = {
            tuple(terminal_sentence_format(answer) for answer in canonical[question_id]["answer"])
            for question_id in question_ids
        }
        if len(terminal_signatures) == 1:
            for question_id in question_ids:
                scoring_relation_rows.append(
                    {
                        "questionId": question_id,
                        "method": "",
                        "relation_type": "same_question_gold_terminal_punctuation_variant",
                        "gold_json": json.dumps(canonical[question_id]["answer"], ensure_ascii=False),
                        "prediction": "",
                        "question": canonical[question_id]["question"],
                        "note": f"paired_ids={';'.join(map(str, question_ids))}",
                    }
                )
                r3_items.add(question_id)
        else:
            for question_id in question_ids:
                hard_artifact_rows.append(
                    {
                        "questionId": question_id,
                        "anomaly_type": "same_pdf_question_substantive_gold_conflict",
                        "gold_json": json.dumps(canonical[question_id]["answer"], ensure_ascii=False),
                        "evidence_json": json.dumps(
                            {
                                "pdf_id": pdf_id,
                                "normalized_question": normalized_question,
                                "paired_ids": question_ids,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "question": canonical[question_id]["question"],
                    }
                )
                s1_hard_items.add(question_id)

    # R1 convergence, all-wrong distribution, and R3/R4 scoring relations.
    all_wrong_bucket_counts = Counter()
    blank_prediction_rows = 0
    all_wrong_blank_prediction_rows = 0
    all_wrong_items_with_blank_prediction = 0
    all_wrong_nonempty_prediction_count_distribution = Counter()
    for question_id in loaded.ids:
        row = canonical[question_id]
        judges = {
            method: loaded.by_method[method][question_id]["judge"] for method in METHOD_FILES
        }
        n_correct = sum(label == "T" for label in judges.values())
        predictions_by_method = {
            method: loaded.by_method[method][question_id].get("prediction")
            for method in METHOD_FILES
        }
        prediction_groups = nonempty_e1_prediction_groups(predictions_by_method)
        n_nonempty_predictions = sum(len(methods) for methods in prediction_groups.values())
        n_blank_predictions = len(METHOD_FILES) - n_nonempty_predictions
        nonempty_prediction_counts[question_id] = n_nonempty_predictions
        blank_prediction_rows += n_blank_predictions
        ranked_groups = sorted(
            prediction_groups.items(), key=lambda item: (-len(item[1]), item[0])
        )
        consensus_answer, consensus_methods = ranked_groups[0] if ranked_groups else ("", [])
        max_count = len(consensus_methods)
        max_convergence[question_id] = max_count
        if n_correct == 0:
            all_wrong_blank_prediction_rows += n_blank_predictions
            all_wrong_items_with_blank_prediction += int(n_blank_predictions > 0)
            all_wrong_nonempty_prediction_count_distribution[n_nonempty_predictions] += 1
            if max_count >= 5:
                all_wrong_bucket_counts["convergent_5_plus"] += 1
            elif max_count >= 2:
                all_wrong_bucket_counts["shared_2_4"] += 1
            else:
                all_wrong_bucket_counts["divergent_1"] += 1

        answers = row.get("answer") or []
        long_gold = any(len(e0(answer)) > 100 for answer in answers)
        gold_e1 = [e1(answer) for answer in answers]
        consensus_relation = "different"
        if consensus_answer and consensus_answer in gold_e1:
            consensus_relation = "equal_e1"
        elif consensus_answer and any(gold.startswith(consensus_answer) for gold in gold_e1):
            consensus_relation = "prediction_strict_prefix_of_gold"
        elif consensus_answer and any(consensus_answer in gold for gold in gold_e1):
            consensus_relation = "prediction_nonprefix_strict_substring_of_gold"
        consensus_e2 = e2_short_relation_text(consensus_answer)
        gold_e2 = [e2_short_relation_text(answer) for answer in answers]
        short_answer_relation = bool(consensus_e2) and any(
            gold.startswith(consensus_e2) and gold != consensus_e2 for gold in gold_e2
        )

        if n_correct == 0 and max_count >= 5:
            families = sorted({METHOD_FAMILY[method] for method in consensus_methods})
            if long_gold or short_answer_relation:
                category = "long_gold_or_short_answer_convergence"
                long_convergence_items.add(question_id)
            elif (
                len(families) >= 3
                and consensus_relation == "different"
                and not row["metadata_unresolved"]
            ):
                category = "fact_conflict_hypothesis"
                r1_items.add(question_id)
            else:
                category = "other_convergence_review"
            convergence_rows.append(
                {
                    "questionId": question_id,
                    "pdf_id": row["pdf_id"],
                    "tag": row["tag"],
                    "category": category,
                    "n_methods": max_count,
                    "n_distinct_families": len(families),
                    "methods": ";".join(consensus_methods),
                    "families": ";".join(families),
                    "consensus_answer": consensus_answer,
                    "consensus_gold_relation": consensus_relation,
                    "e2_short_answer_relation": short_answer_relation,
                    "gold_json": json.dumps(answers, ensure_ascii=False),
                    "question": row["question"],
                }
            )

        # R3: relation rows are descriptive and never hard evidence.
        for method in METHOD_FILES:
            method_row = loaded.by_method[method][question_id]
            if method_row["judge"] != "F":
                continue
            prediction_raw = e0(method_row.get("prediction"))
            prediction_e1 = e1(prediction_raw)
            if not prediction_e1:
                continue
            relations: set[str] = set()
            conservative_relation_found = False
            for answer in answers:
                gold_raw = e0(answer)
                gold_norm = e1(gold_raw)
                if prediction_raw == gold_raw:
                    relations.add("exact_raw_equal_but_F")
                    conservative_relation_found = True
                elif prediction_e1 == gold_norm:
                    relations.add("equal_e1_but_F")
                    conservative_relation_found = True
                elif gold_norm and gold_norm in prediction_e1:
                    relations.add("gold_strict_substring_of_prediction")
                    conservative_relation_found = True
                elif prediction_e1 and gold_norm.startswith(prediction_e1):
                    relations.add("prediction_strict_prefix_of_gold")
                    conservative_relation_found = True
                elif prediction_e1 and prediction_e1 in gold_norm:
                    relations.add("prediction_nonprefix_strict_substring_of_gold")
                    conservative_relation_found = True
                if not conservative_relation_found:
                    loose_gold = v1_loose_diagnostic(gold_raw)
                    loose_prediction = v1_loose_diagnostic(prediction_raw)
                    if loose_gold and loose_gold in loose_prediction:
                        relations.add("loose_normalization_only_containment_negative_control")
            for relation in sorted(relations):
                scoring_relation_rows.append(
                    {
                        "questionId": question_id,
                        "method": method,
                        "relation_type": relation,
                        "gold_json": json.dumps(answers, ensure_ascii=False),
                        "prediction": prediction_raw,
                        "question": row["question"],
                        "note": "review-only relation; units and extra content remain material",
                    }
                )
                if relation != "loose_normalization_only_containment_negative_control":
                    r3_items.add(question_id)
        if long_gold:
            scoring_relation_rows.append(
                {
                    "questionId": question_id,
                    "method": "",
                    "relation_type": "long_gold_scoring_risk",
                    "gold_json": json.dumps(answers, ensure_ascii=False),
                    "prediction": "",
                    "question": row["question"],
                    "note": "scoring contract unknown; length alone is not a defect",
                }
            )
            r4_items.add(question_id)

        # R2 and corrected item-total correlation.
        r_pb = _corrected_item_total(loaded, question_id, method_totals)
        corrected_rpb[question_id] = r_pb
        strong_correct = sum(judges[method] == "T" for method in ABILITY_ORDER[:3])
        weak_correct = sum(judges[method] == "T" for method in ABILITY_ORDER[-3:])
        inversion = strong_correct == 0 and weak_correct >= 2
        if inversion:
            r2_items.add(question_id)
        inversion_rows.append(
            {
                "questionId": question_id,
                "r_pb_corrected": "" if r_pb is None else f"{r_pb:.12f}",
                "r_pb_defined": r_pb is not None,
                "label_relative_inversion": inversion,
                "n_strong_correct": strong_correct,
                "n_weak_correct": weak_correct,
                "strong_predictions_json": json.dumps(
                    {
                        method: loaded.by_method[method][question_id].get("prediction")
                        for method in ABILITY_ORDER[:3]
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "gold_json": json.dumps(answers, ensure_ascii=False),
                "question": row["question"],
            }
        )

        response_row = {
            "questionId": question_id,
            "pdf_id": row["pdf_id"],
            "tag": row["tag"],
            "n_correct": n_correct,
            "n_nonempty_predictions_e1": n_nonempty_predictions,
            "n_blank_predictions_e1": n_blank_predictions,
        }
        response_row.update({method: judges[method] for method in METHOD_FILES})
        response_rows.append(response_row)

    # Triage after all signals are known.
    for question_id in loaded.ids:
        n_correct = sum(
            loaded.by_method[method][question_id]["judge"] == "T" for method in METHOD_FILES
        )
        if question_id in h1_items:
            verdict = "hard_record_inconsistency"
        elif question_id in h2_items or question_id in s1_hard_items:
            verdict = "hard_artifact_anomaly"
        elif question_id in r1_items:
            verdict = "gold_or_item_hypothesis"
        elif question_id in r2_items:
            verdict = "difficulty_inversion_hypothesis"
        elif question_id in r3_items or question_id in r4_items:
            verdict = "scoring_contract_hypothesis"
        elif n_correct == 0:
            verdict = "unresolved_all_wrong"
        elif n_correct == 1:
            verdict = "low_success_unresolved"
        else:
            verdict = "not_flagged"
        triage_rows.append(
            {
                "questionId": question_id,
                "pdf_id": canonical[question_id]["pdf_id"],
                "tag": canonical[question_id]["tag"],
                "n_correct": n_correct,
                "n_nonempty_predictions_e1": nonempty_prediction_counts[question_id],
                "n_blank_predictions_e1": len(METHOD_FILES)
                - nonempty_prediction_counts[question_id],
                "max_e1_prediction_convergence": max_convergence[question_id],
                "r_pb_corrected": ""
                if corrected_rpb[question_id] is None
                else f"{corrected_rpb[question_id]:.12f}",
                "sig_h1_record_inconsistency": question_id in h1_items,
                "sig_h2_invisible_gold": question_id in h2_items,
                "sig_s1_static_hard": question_id in s1_hard_items,
                "sig_r1_fact_convergence": question_id in r1_items,
                "sig_r1_long_gold_convergence": question_id in long_convergence_items,
                "sig_r2_difficulty_inversion": question_id in r2_items,
                "sig_r3_scoring_relation": question_id in r3_items,
                "sig_r4_long_gold": question_id in r4_items,
                "primary_verdict": verdict,
                "question": canonical[question_id]["question"],
                "gold_json": json.dumps(canonical[question_id]["answer"], ensure_ascii=False),
            }
        )

    correct_distribution = Counter(row["n_correct"] for row in response_rows)
    verdict_distribution = Counter(row["primary_verdict"] for row in triage_rows)
    relation_distribution = Counter(row["relation_type"] for row in scoring_relation_rows)
    summary = {
        "items": len(loaded.ids),
        "method_totals": method_totals,
        "correct_distribution": {str(key): correct_distribution[key] for key in range(10)},
        "all_wrong_items": correct_distribution[0],
        "all_wrong_e1_buckets": dict(all_wrong_bucket_counts),
        "blank_prediction_rows_e1": blank_prediction_rows,
        "all_wrong_blank_prediction_rows_e1": all_wrong_blank_prediction_rows,
        "all_wrong_items_with_blank_prediction_e1": all_wrong_items_with_blank_prediction,
        "all_wrong_nonempty_prediction_method_count_distribution": {
            str(key): all_wrong_nonempty_prediction_count_distribution[key]
            for key in sorted(all_wrong_nonempty_prediction_count_distribution)
        },
        "all_wrong_participating_prediction_rows_e1": sum(
            count * frequency
            for count, frequency in all_wrong_nonempty_prediction_count_distribution.items()
        ),
        "hard_record_inconsistency_items": len(h1_items),
        "hard_artifact_anomaly_items": len(h2_items | s1_hard_items),
        "invisible_gold_items": len(h2_items),
        "static_hard_items": len(s1_hard_items),
        "fact_convergence_hypothesis_items": len(r1_items),
        "long_gold_convergence_items": len(long_convergence_items),
        "difficulty_inversion_items": len(r2_items),
        "r_pb_undefined_items": sum(value is None for value in corrected_rpb.values()),
        "long_gold_items": len(r4_items),
        "metadata_conflict_rows": len(metadata_conflicts),
        "metadata_semantic_conflict_rows": sum(
            bool(row["semantic_difference_e1"]) for row in metadata_conflicts
        ),
        "scoring_relation_distribution": dict(sorted(relation_distribution.items())),
        "primary_verdict_distribution": dict(sorted(verdict_distribution.items())),
        "api_attempts": 0,
        "source_documents_available": False,
        "scoring_contract_available": False,
    }

    return {
        "canonical": canonical,
        "metadata_conflicts": metadata_conflicts,
        "response_rows": response_rows,
        "hard_record_rows": hard_record_rows,
        "hard_artifact_rows": hard_artifact_rows,
        "convergence_rows": convergence_rows,
        "inversion_rows": inversion_rows,
        "scoring_relation_rows": scoring_relation_rows,
        "triage_rows": triage_rows,
        "summary": summary,
    }


def validate_anchors(result: Mapping[str, Any]) -> dict[str, bool]:
    summary = result["summary"]
    checks = {
        "items_1065": summary["items"] == 1065,
        "correct_distribution": summary["correct_distribution"]
        == {str(key): value for key, value in EXPECTED_CORRECT_DISTRIBUTION.items()},
        "all_wrong_151": summary["all_wrong_items"] == 151,
        "all_wrong_e1_buckets": summary["all_wrong_e1_buckets"]
        == EXPECTED_ALL_WRONG_E1_BUCKETS,
        "blank_prediction_rows_471": summary["blank_prediction_rows_e1"] == 471,
        "all_wrong_blank_prediction_rows_75": summary[
            "all_wrong_blank_prediction_rows_e1"
        ]
        == 75,
        "all_wrong_items_with_blank_prediction_62": summary[
            "all_wrong_items_with_blank_prediction_e1"
        ]
        == 62,
        "all_wrong_nonempty_prediction_method_count_distribution": summary[
            "all_wrong_nonempty_prediction_method_count_distribution"
        ]
        == {
            str(key): value
            for key, value in EXPECTED_ALL_WRONG_NONEMPTY_E1_METHOD_COUNTS.items()
        },
        "all_wrong_participating_prediction_rows_1284": summary[
            "all_wrong_participating_prediction_rows_e1"
        ]
        == 1284,
        "h1_items_9": summary["hard_record_inconsistency_items"] == 9,
        "q1060_h1": any(row["questionId"] == 1060 for row in result["hard_record_rows"]),
        "q1048_h2": any(row["questionId"] == 1048 for row in result["hard_artifact_rows"]),
        "fact_convergence_5": summary["fact_convergence_hypothesis_items"] == 5,
        "long_gold_convergence_2": summary["long_gold_convergence_items"] == 2,
        "difficulty_inversion_2": summary["difficulty_inversion_items"] == 2,
        "r_pb_undefined_166": summary["r_pb_undefined_items"] == 166,
        "q994_not_hard": not any(
            row["questionId"] == 994
            for row in result["hard_record_rows"] + result["hard_artifact_rows"]
        ),
        "q110_q1048_not_fact_convergence": all(
            row["category"] != "fact_conflict_hypothesis"
            for row in result["convergence_rows"]
            if row["questionId"] in {110, 1048}
        ),
        "q895_q896_not_hard_static": not any(
            row["questionId"] in {895, 896}
            for row in result["hard_artifact_rows"]
        ),
        "triage_1065_unique": len(result["triage_rows"]) == 1065
        and len({row["questionId"] for row in result["triage_rows"]}) == 1065,
    }
    return checks


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _manual_review_rows(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    triage_by_id = {row["questionId"]: row for row in result["triage_rows"]}
    selected_ids = sorted(
        {
            row["questionId"] for row in result["hard_record_rows"]
        }
        | {row["questionId"] for row in result["hard_artifact_rows"]}
        | {
            row["questionId"]
            for row in result["convergence_rows"]
            if row["category"] == "fact_conflict_hypothesis"
        }
        | {
            row["questionId"]
            for row in result["inversion_rows"]
            if row["label_relative_inversion"]
        }
    )
    for question_id in selected_ids:
        triage = triage_by_id[question_id]
        if triage["primary_verdict"] in {
            "hard_record_inconsistency",
            "hard_artifact_anomaly",
        }:
            ceiling = "locally_inconsistent"
        else:
            ceiling = "not_identifiable_without_source"
        rows.append(
            {
                "questionId": question_id,
                "automatic_primary_verdict": triage["primary_verdict"],
                "protocol_evidence_ceiling": ceiling,
                "reviewer_label": "",
                "reviewer_reason": "",
                "source_pdf_available": False,
                "scoring_contract_available": False,
                "question": triage["question"],
                "gold_json": triage["gold_json"],
            }
        )
    return rows


def render_findings(result: Mapping[str, Any], anchors: Mapping[str, bool]) -> str:
    summary = result["summary"]
    hard_ids = sorted({row["questionId"] for row in result["hard_record_rows"]})
    invisible_ids = sorted(
        {
            row["questionId"]
            for row in result["hard_artifact_rows"]
            if row["anomaly_type"] == "unexpected_invisible_or_control_gold"
        }
    )
    fact_rows = [
        row for row in result["convergence_rows"] if row["category"] == "fact_conflict_hypothesis"
    ]
    inversion_ids = [
        row["questionId"]
        for row in result["inversion_rows"]
        if row["label_relative_inversion"]
    ]
    relation_counts = summary["scoring_relation_distribution"]
    verdict_counts = summary["primary_verdict_distribution"]
    lines = [
        "# MoDora 多模型执行结果缺陷挖掘：V2 结果",
        "",
        "## 一句话",
        "",
        f"> 9 种真实方法的逐题记录提供了 {summary['hard_record_inconsistency_items']} 个可重放的同答案 T/F 冲突和 {summary['invisible_gold_items']} 个含不可见字符的 gold；另有 {summary['fact_convergence_hypothesis_items']} 个事实冲突型高收敛与 {summary['difficulty_inversion_items']} 个能力序反转假设，但由于缺少原始 PDF 和评分合同，它们不能被定性为 benchmark 缺陷。",
        "",
        "## 硬本地证据",
        "",
        f"- 相同 E0/E1 prediction、冲突 judge：**{summary['hard_record_inconsistency_items']} 个 item**，IDs：`{hard_ids}`。",
        f"- gold 含不可见/控制字符：**{summary['invisible_gold_items']} 个 item**，IDs：`{invisible_ids}`。",
        "- H1 证明本地判决记录内部不一致；H2 证明 artifact hygiene anomaly。两者都不自动证明原始 PDF 的事实真值。",
        "",
        "## 151 条九法全错题",
        "",
        "按 V2 保守 E1 关系：",
        "",
        f"- 预测完全发散（最大同答数 1）：**{summary['all_wrong_e1_buckets']['divergent_1']}**；",
        f"- 低/中共享（最大同答数 2–4）：**{summary['all_wrong_e1_buckets']['shared_2_4']}**；",
        f"- 高收敛（最大同答数 ≥5）：**{summary['all_wrong_e1_buckets']['convergent_5_plus']}**。",
        "",
        f"V2.1 在分组前剔除 E1 空预测：全数据共 **{summary['blank_prediction_rows_e1']}** 个空预测；全错题中 **{summary['all_wrong_blank_prediction_rows_e1']}** 个，涉及 **{summary['all_wrong_items_with_blank_prediction_e1']}** 个 item。空预测保留计账，但不构成一致答案。",
        "",
        f"高收敛 {summary['all_wrong_e1_buckets']['convergent_5_plus']} 条中，**{summary['fact_convergence_hypothesis_items']}** 条进入事实冲突 hypothesis，**{summary['long_gold_convergence_items']}** 条被分流为长-gold 短答案关系。其余项目保持未决，不把规则未命中解释为题目无缺陷或事实真值已确定。",
        "",
        "### 事实冲突型高收敛候选",
        "",
        "| questionId | methods | families | consensus | gold |",
        "|---:|---:|---:|---|---|",
    ]
    for row in fact_rows:
        lines.append(
            f"| {row['questionId']} | {row['n_methods']} | {row['n_distinct_families']} | "
            f"`{row['consensus_answer']}` | `{row['gold_json']}` |"
        )
    lines.extend(
        [
            "",
            "这些候选必须查看 hash-pinned 原始 PDF 才能判断是 gold 问题还是共享模型失败。",
            "",
            "## Label-relative difficulty inversion",
            "",
            f"前 3 方法全 F、后 3 至少 2 个 T：**{summary['difficulty_inversion_items']} 条**，IDs：`{inversion_ids}`。",
            f"Corrected item-total `r_pb` 无定义：**{summary['r_pb_undefined_items']} 条**。`r_pb` 只作 bottom-30 排序，不报告显著性。",
            "",
            "## 判分关系 review 信号",
            "",
            "这些关系不进入 hard evidence：",
            "",
        ]
    )
    for relation, count in sorted(relation_counts.items()):
        lines.append(f"- `{relation}`：{count}")
    lines.extend(
        [
            "",
            "q994 是固定负对照：gold 为英寸、prediction 为毫米。V1 的宽松规范化曾错误制造包含关系；V2 E1 保留单位符号，因此不存在相等或包含关系，也不得提升为判分异常。",
            "",
            "## Primary verdict 分布",
            "",
            "| verdict | items |",
            "|---|---:|",
        ]
    )
    for verdict, count in sorted(verdict_counts.items()):
        lines.append(f"| `{verdict}` | {count} |")
    lines.extend(
        [
            "",
            "## 多模型证据相对纯静态检查的增量",
            "",
            f"- 多模型 H1 提供 **{summary['hard_record_inconsistency_items']}** 个本地判决不一致 item；",
            f"- 静态不可见字符检查提供 **{summary['invisible_gold_items']}** 个 artifact anomaly item；",
            f"- 其余静态 hard item：**{summary['static_hard_items']}**；",
            "- R1/R2 是多模型新增的 hypothesis，不与硬证据混计。",
            "",
            "## 诚实边界",
            "",
            "1. 9 种方法不是 9 个独立模型；三个已知 RAG 管线按一个临时方法族计。",
            "2. MoDora 是原论文自己的方法，不能当 ground truth。",
            "3. `judge` 合同未知；H1 的准确说法是“本地相同答案出现冲突标签”。",
            "4. 本机没有对应原始 PDF；R1/R2 的事实真值均为 `NOT_IDENTIFIABLE_WITHOUT_SOURCE`。",
            "5. 本报告不计算缺陷查准率，也不把未命中规则的题称为 clean 或已确认难题。",
            "6. 这是对外部 MoDora 实验产物的二次分析，不是 BenchAudit 的实验结果。",
            "7. 所有结果来自本地确定性脚本，API attempts = 0。",
            "8. `manual_review.csv` 只是待复核队列；本轮没有原始 PDF，也没有完成人工事实裁定。",
            "",
            "## 锚点验证",
            "",
        ]
    )
    for name, passed in anchors.items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} `{name}`")
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    output_dir: Path,
    input_dir: Path,
    loaded: LoadedData,
    result: Mapping[str, Any],
    *,
    script_path: Path,
    v1_protocol_path: Path,
    protocol_path: Path,
    addendum_path: Path,
    correction_path: Path,
    v21_addendum_path: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    anchors = validate_anchors(result)
    if not all(anchors.values()):
        failed = [name for name, passed in anchors.items() if not passed]
        raise RuntimeError(f"anchor validation failed: {failed}")

    write_csv(output_dir / "metadata_conflicts.csv", result["metadata_conflicts"])
    write_csv(output_dir / "response_matrix.csv", result["response_rows"])
    write_csv(output_dir / "hard_record_inconsistencies.csv", result["hard_record_rows"])
    write_csv(output_dir / "hard_artifact_anomalies.csv", result["hard_artifact_rows"])
    write_csv(output_dir / "convergence_hypotheses.csv", result["convergence_rows"])
    write_csv(output_dir / "difficulty_inversion.csv", result["inversion_rows"])
    write_csv(output_dir / "scoring_relation_review.csv", result["scoring_relation_rows"])
    write_csv(output_dir / "triage.csv", result["triage_rows"])
    write_csv(output_dir / "manual_review.csv", _manual_review_rows(result))
    (output_dir / "FINDINGS.md").write_text(
        render_findings(result, anchors), encoding="utf-8"
    )

    generated_paths = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "receipt.json"
    )

    receipt = {
        "schema_version": "modora-defect-mining-receipt-v2",
        "rule_version": RULE_VERSION,
        "input_dir": str(input_dir.resolve()),
        "input_sha256": loaded.input_hashes,
        "v1_protocol": {
            "path": str(v1_protocol_path),
            "sha256": sha256_file(v1_protocol_path),
        },
        "script": {"path": str(script_path), "sha256": sha256_file(script_path)},
        "protocol": {"path": str(protocol_path), "sha256": sha256_file(protocol_path)},
        "protocol_addendum": {
            "path": str(addendum_path),
            "sha256": sha256_file(addendum_path),
        },
        "protocol_correction": {
            "path": str(correction_path),
            "sha256": sha256_file(correction_path),
        },
        "protocol_v2_1_addendum": {
            "path": str(v21_addendum_path),
            "sha256": sha256_file(v21_addendum_path),
        },
        "summary": result["summary"],
        "anchors": anchors,
        "hard_evidence_claim_scope": [
            "local_same_prediction_conflicting_stored_judge",
            "gold_contains_unexpected_invisible_or_control_character",
        ],
        "hypothesis_evidence_ceiling": "review_only_without_source_pdf_or_scoring_contract",
        "api_attempts": 0,
        "source_files_modified": False,
        "output_sha256": {
            path.name: sha256_file(path) for path in generated_paths
        },
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/MoDora"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("reports/modora_defect_mining_20260810")
    )
    parser.add_argument(
        "--v1-protocol",
        type=Path,
        default=Path("docs/research/多模型执行结果挖掘缺陷_一日工单_20260810.md"),
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("docs/research/多模型执行结果挖掘缺陷_一日工单_V2_20260810.md"),
    )
    parser.add_argument(
        "--protocol-addendum",
        type=Path,
        default=Path("docs/research/多模型执行结果挖掘缺陷_V2预飞附录_20260810.md"),
    )
    parser.add_argument(
        "--protocol-correction",
        type=Path,
        default=Path("docs/research/多模型执行结果挖掘缺陷_V2实现前锚点更正_20260810.md"),
    )
    parser.add_argument(
        "--protocol-v2-1-addendum",
        type=Path,
        default=Path(
            "docs/research/多模型执行结果挖掘缺陷_V2.1空预测规则附录_20260810.md"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_path = Path(__file__).resolve()
    loaded = load_data(args.input_dir)
    result = analyze(loaded)
    receipt = write_outputs(
        args.output_dir,
        args.input_dir,
        loaded,
        result,
        script_path=script_path,
        v1_protocol_path=args.v1_protocol,
        protocol_path=args.protocol,
        addendum_path=args.protocol_addendum,
        correction_path=args.protocol_correction,
        v21_addendum_path=args.protocol_v2_1_addendum,
    )
    print(json.dumps(receipt["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
