from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

from .schema import FieldMapping


@dataclass(frozen=True)
class InjectedDefect:
    mutation_id: str
    source_item_id: str
    mutated_item_id: str
    defect_type: str
    operator: str
    changed_fields: tuple[str, ...]
    evidence_grade: str
    assumptions: tuple[str, ...]
    seed: int
    before_sha256: str
    after_sha256: str


@dataclass(frozen=True)
class MutationResult:
    row: dict[str, Any]
    provenance: InjectedDefect


MutationOperator = Callable[[dict[str, Any], FieldMapping, random.Random], tuple[dict[str, Any], tuple[str, ...]] | None]


def inject_defects(
    rows: Iterable[dict[str, Any]],
    mapping: FieldMapping,
    *,
    seed: int,
    operators: Iterable[str] | None = None,
    mutations_per_item: int = 1,
) -> list[MutationResult]:
    if mutations_per_item <= 0:
        raise ValueError("mutations_per_item must be positive")
    selected_names = list(operators or MUTATION_OPERATORS)
    unknown = set(selected_names) - set(MUTATION_OPERATORS)
    if unknown:
        raise ValueError("unknown mutation operators: " + ", ".join(sorted(unknown)))
    rng = random.Random(seed)
    results: list[MutationResult] = []
    for index, source in enumerate(rows):
        applicable = [name for name in selected_names if _can_apply(name, source, mapping)]
        rng.shuffle(applicable)
        raw_id = source.get(mapping.item_id) if mapping.item_id else None
        source_id = str(raw_id) if raw_id not in (None, "") else f"item-{index}"
        for ordinal, name in enumerate(applicable[:mutations_per_item]):
            mutated = MUTATION_OPERATORS[name](source, mapping, rng)
            if mutated is None:
                continue
            row, changed_fields = mutated
            mutated_id = f"{source_id}__mut_{name}_{ordinal + 1}"
            if mapping.item_id:
                row[mapping.item_id] = mutated_id
                if mapping.item_id not in changed_fields:
                    changed_fields = (*changed_fields, mapping.item_id)
            before_hash = canonical_sha256(source)
            after_hash = canonical_sha256(row)
            mutation_id = hashlib.sha256(
                f"{seed}:{source_id}:{name}:{ordinal}:{after_hash}".encode("utf-8")
            ).hexdigest()[:20]
            defect = InjectedDefect(
                mutation_id=mutation_id,
                source_item_id=source_id,
                mutated_item_id=mutated_id,
                defect_type=OPERATOR_DEFECT_TYPES[name],
                operator=name,
                changed_fields=tuple(changed_fields),
                evidence_grade=OPERATOR_EVIDENCE[name][0],
                assumptions=OPERATOR_EVIDENCE[name][1],
                seed=seed,
                before_sha256=before_hash,
                after_sha256=after_hash,
            )
            row["_injected_defect"] = asdict(defect)
            results.append(MutationResult(row=row, provenance=defect))
    return results


def _can_apply(name: str, row: dict[str, Any], mapping: FieldMapping) -> bool:
    if name == "remove_task":
        return bool(mapping.task and row.get(mapping.task) not in (None, ""))
    if name == "remove_gold":
        return bool(mapping.gold and row.get(mapping.gold) not in (None, ""))
    if name == "wrong_gold":
        return bool(mapping.gold and row.get(mapping.gold) not in (None, ""))
    if name == "duplicate_choice":
        choices = _choices(row.get(mapping.choices)) if mapping.choices else []
        return len(choices) >= 2
    if name == "remove_context":
        if not any(row.get(key) not in (None, "", [], {}) for key in mapping.context):
            return False
        task = str(row.get(mapping.task, "")) if mapping.task else ""
        from .checkers import REFERENCE_PATTERNS
        return any(pattern.search(task) for pattern in REFERENCE_PATTERNS.values())
    if name == "remove_evaluator":
        return bool(mapping.evaluator and row.get(mapping.evaluator) not in (None, ""))
    return False


def _remove_task(row: dict[str, Any], mapping: FieldMapping, rng: random.Random):
    if not mapping.task:
        return None
    result = copy.deepcopy(row)
    result[mapping.task] = ""
    return result, (mapping.task,)


def _remove_gold(row: dict[str, Any], mapping: FieldMapping, rng: random.Random):
    if not mapping.gold:
        return None
    result = copy.deepcopy(row)
    result[mapping.gold] = None
    return result, (mapping.gold,)


def _wrong_gold(row: dict[str, Any], mapping: FieldMapping, rng: random.Random):
    if not mapping.gold:
        return None
    original = row.get(mapping.gold)
    choices = _choices(row.get(mapping.choices)) if mapping.choices else []
    replacement: Any
    if choices:
        from .evaluators import CHOICE_LABELS, choice_label_to_index

        original_index = choice_label_to_index(original, choices)
        alternative_indices = [index for index in range(len(choices)) if index != original_index]
        replacement_index = rng.choice(alternative_indices)
        original_text = str(original).strip()
        if original_text.upper() in CHOICE_LABELS[: len(choices)]:
            replacement = CHOICE_LABELS[replacement_index]
        elif original_index is not None:
            replacement = copy.deepcopy(choices[replacement_index])
        else:
            replacement = f"{original}__incorrect"
    elif isinstance(original, bool):
        replacement = not original
    elif isinstance(original, (int, float)) and not isinstance(original, bool):
        replacement = original + 1
    else:
        replacement = f"{original}__incorrect"
    result = copy.deepcopy(row)
    result[mapping.gold] = replacement
    return result, (mapping.gold,)


def _duplicate_choice(row: dict[str, Any], mapping: FieldMapping, rng: random.Random):
    if not mapping.choices:
        return None
    original = row.get(mapping.choices)
    choices = _choices(original)
    if len(choices) < 2:
        return None
    choices[-1] = copy.deepcopy(choices[0])
    result = copy.deepcopy(row)
    result[mapping.choices] = json.dumps(choices, ensure_ascii=False) if isinstance(original, str) else choices
    return result, (mapping.choices,)


def _remove_context(row: dict[str, Any], mapping: FieldMapping, rng: random.Random):
    present = [key for key in mapping.context if row.get(key) not in (None, "", [], {})]
    if not present:
        return None
    result = copy.deepcopy(row)
    for key in present:
        result[key] = None
    return result, tuple(present)


def _remove_evaluator(row: dict[str, Any], mapping: FieldMapping, rng: random.Random):
    if not mapping.evaluator:
        return None
    result = copy.deepcopy(row)
    result[mapping.evaluator] = None
    return result, (mapping.evaluator,)


MUTATION_OPERATORS: dict[str, MutationOperator] = {
    "remove_task": _remove_task,
    "remove_gold": _remove_gold,
    "wrong_gold": _wrong_gold,
    "duplicate_choice": _duplicate_choice,
    "remove_context": _remove_context,
    "remove_evaluator": _remove_evaluator,
}

OPERATOR_DEFECT_TYPES = {
    "remove_task": "missing_task",
    "remove_gold": "missing_oracle",
    "wrong_gold": "wrong_gold_answer",
    "duplicate_choice": "duplicate_choices",
    "remove_context": "missing_context",
    "remove_evaluator": "missing_evaluator",
}

OPERATOR_EVIDENCE: dict[str, tuple[str, tuple[str, ...]]] = {
    "remove_task": ("structural", ()),
    "remove_gold": ("structural", ("the source item declares a gold answer",)),
    "wrong_gold": ("conditional", ("the source gold is uniquely correct",)),
    "duplicate_choice": ("structural", ()),
    "remove_context": ("structural", ("the task explicitly references provided context",)),
    "remove_evaluator": ("structural", ("the source item declares an evaluator",)),
}


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def score_injected_report(manifest: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Measure exact expected-defect recall on a synthetic mutation set."""
    expected_rows = manifest.get("mutations") or []
    if not isinstance(expected_rows, list):
        raise ValueError("mutation manifest must contain a mutations list")
    detected = {
        (str(row.get("item_id")), str(row.get("defect_type")))
        for row in report.get("violations", [])
        if isinstance(row, dict)
    }
    per_type: dict[str, dict[str, int | float]] = {}
    per_grade: dict[str, dict[str, int | float]] = {}
    misses: list[dict[str, str]] = []
    hits = 0
    for row in expected_rows:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("mutated_item_id", ""))
        defect_type = str(row.get("defect_type", ""))
        operator = str(row.get("operator", ""))
        grade = str(row.get("evidence_grade", "unknown"))
        bucket = per_type.setdefault(defect_type, {"expected": 0, "detected": 0, "recall": 0.0})
        grade_bucket = per_grade.setdefault(grade, {"expected": 0, "detected": 0, "recall": 0.0})
        bucket["expected"] = int(bucket["expected"]) + 1
        grade_bucket["expected"] = int(grade_bucket["expected"]) + 1
        if (item_id, defect_type) in detected:
            hits += 1
            bucket["detected"] = int(bucket["detected"]) + 1
            grade_bucket["detected"] = int(grade_bucket["detected"]) + 1
        else:
            misses.append({"item_id": item_id, "defect_type": defect_type, "operator": operator})
    for bucket in per_type.values():
        expected = int(bucket["expected"])
        bucket["recall"] = int(bucket["detected"]) / expected if expected else 0.0
    for bucket in per_grade.values():
        expected = int(bucket["expected"])
        bucket["recall"] = int(bucket["detected"]) / expected if expected else 0.0
    total = sum(int(bucket["expected"]) for bucket in per_type.values())
    return {
        "expected": total,
        "detected": hits,
        "recall": hits / total if total else 0.0,
        "per_defect_type": dict(sorted(per_type.items())),
        "per_evidence_grade": dict(sorted(per_grade.items())),
        "misses": misses,
    }


def _choices(value: Any) -> list[Any]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []
