from __future__ import annotations

import math
import re
import string
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


CHOICE_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHINESE_CHOICE_LABELS = "甲乙丙丁戊己庚辛壬癸"

_DECLARED_CHOICE_TYPES = frozenset({
    "choice",
    "multiple_choice",
    "multiple choice",
    "multiple-choice",
    "mcq",
})


def normalize_text(value: Any) -> str:
    text = "" if value is None else unicodedata.normalize("NFKC", str(value))
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_loose(value: Any) -> str:
    text = normalize_text(value)
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\b(the|a|an)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_contract_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, (dict, list)):
        return normalize_text(value)
    return normalize_text(value)


def declares_choice_contract(evaluator: Any, output_contract: Any = None) -> bool:
    """Return whether benchmark metadata explicitly declares a choice answer.

    The presence of a list-valued field is deliberately insufficient: retrieval
    datasets commonly call a document pool ``candidates`` while their target is
    an identifier in a different namespace.  Only an explicit evaluator/output
    type may establish the per-item choice/gold relation used by confirmation.
    """

    declared: list[Any] = []
    for value in (evaluator, output_contract):
        if isinstance(value, dict):
            declared.extend(
                value.get(key)
                for key in ("type", "kind", "answer_type", "metric")
                if value.get(key) not in (None, "")
            )
        elif value not in (None, ""):
            declared.append(value)
    return any(normalize_text(value) in _DECLARED_CHOICE_TYPES for value in declared)


def declared_choice_labels(contract: Any, choice_count: int) -> tuple[str, ...] | None:
    """Return an explicit label namespace, never one inferred from MCQ type.

    ``type=multiple_choice`` proves task family but says nothing about whether
    labels are A/B, 0-based, 1-based, localized, or custom.  Only a literal
    label list or an unambiguous format declaration can support single-item
    invalid-label confirmation.
    """

    if choice_count <= 0 or not isinstance(contract, dict):
        return None
    for key in ("labels", "choice_labels", "allowed_labels", "label_set"):
        value = contract.get(key)
        if isinstance(value, (list, tuple)) and len(value) == choice_count:
            labels = tuple(str(label).strip() for label in value)
            if all(labels) and len({label.casefold() for label in labels}) == len(labels):
                return labels
    base = contract.get("index_base")
    if base in (0, "0", "zero", "zero_based", "zero-based"):
        return tuple(str(index) for index in range(choice_count))
    if base in (1, "1", "one", "one_based", "one-based"):
        return tuple(str(index) for index in range(1, choice_count + 1))
    texts = [
        str(contract.get(key) or "")
        for key in ("format", "label_format", "answer_format", "output_format")
    ]
    text = " ".join(texts).strip()
    normalized = normalize_text(text)
    if re.search(r"\b(?:zero|0)[ -]?based\b", normalized):
        return tuple(str(index) for index in range(choice_count))
    if re.search(r"\b(?:one|1)[ -]?based\b", normalized):
        return tuple(str(index) for index in range(1, choice_count + 1))
    # Require an explicit sequence such as A/B/C/D; merely saying "a single
    # letter" is underspecified for benchmarks with non-Latin labels.
    tokens = re.findall(r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])", text)
    if len(tokens) == choice_count:
        labels = tuple(token.upper() for token in tokens)
        if len(set(labels)) == choice_count:
            return labels
    return None


def normalize_choice_for_duplicate(value: Any) -> str:
    text = normalize_text(value)
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"^[a-z]\s*[\).:]\s*", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_strict_number(value: Any) -> float | None:
    """Parse a complete scalar numeric answer without substring guessing."""

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(
        r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text,
    ):
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def choice_values(choices: Any) -> list[Any]:
    if isinstance(choices, Mapping):
        return list(choices.values())
    if isinstance(choices, Sequence) and not isinstance(choices, (str, bytes)):
        return list(choices)
    return []


def _choice_label_candidates(label: Any, choices: Any) -> set[int]:
    values = choice_values(choices)
    if not values or isinstance(label, (list, tuple, set, dict)):
        return set()
    text = unicodedata.normalize("NFKC", str(label)).strip()
    if not text:
        return set()
    candidates: set[int] = set()
    if isinstance(choices, Mapping):
        for index, (key, value) in enumerate(choices.items()):
            if normalize_loose(text) in {normalize_loose(key), normalize_loose(value)}:
                candidates.add(index)
    upper = text.upper()
    if upper in CHOICE_LABELS[: len(values)]:
        candidates.add(CHOICE_LABELS.index(upper))
    wrapped = re.fullmatch(r"[\(\[]\s*([A-Za-z])\s*[\)\]]", text)
    if wrapped:
        letter = wrapped.group(1).upper()
        if letter in CHOICE_LABELS[: len(values)]:
            candidates.add(CHOICE_LABELS.index(letter))
    simple_decorated = re.fullmatch(r"([A-Za-z])[\).:]", text)
    if simple_decorated:
        letter = simple_decorated.group(1).upper()
        if letter in CHOICE_LABELS[: len(values)]:
            candidates.add(CHOICE_LABELS.index(letter))
    prefixed = re.fullmatch(
        r"[\(\[]?\s*([A-Za-z])\s*[\)\]]?\s*[\).:]\s*(.*)", text,
    )
    if prefixed:
        letter = prefixed.group(1).upper()
        if letter in CHOICE_LABELS[: len(values)]:
            index = CHOICE_LABELS.index(letter)
            suffix = prefixed.group(2).strip()
            if not suffix or normalize_loose(suffix) == normalize_loose(values[index]):
                candidates.add(index)
    if text in CHINESE_CHOICE_LABELS[: len(values)]:
        candidates.add(CHINESE_CHOICE_LABELS.index(text))
    if re.fullmatch(r"[+-]?\d+", text):
        number = int(text)
        if 0 <= number < len(values):
            candidates.add(number)  # possible 0-based convention
        if 1 <= number <= len(values):
            candidates.add(number - 1)  # possible 1-based convention
    for index, choice in enumerate(values):
        if normalize_loose(text) == normalize_loose(choice):
            candidates.add(index)
    return candidates


def choice_gold_is_mappable(gold: Any, choices: Any) -> bool:
    """Whether every gold component belongs to some valid choice namespace.

    Numeric labels may be ambiguous between 0- and 1-based indexing; ambiguity
    is an evaluator-interpretation coverage gap, not evidence that the gold is
    invalid.  Lists are treated component-wise so multi-select benchmarks are
    not forced into a scalar MCQ contract.
    """

    values = answer_values(gold)
    return bool(values) and all(_choice_label_candidates(value, choices) for value in values)


def gold_uses_declared_choice_labels(gold: Any, labels: Sequence[Any]) -> bool:
    """Accept direct and conventional decorated forms of declared labels."""

    declared = [str(label).strip() for label in labels]
    if not declared or not all(declared):
        return False
    for value in answer_values(gold):
        text = str(value).strip()
        matched = False
        for label in declared:
            escaped = re.escape(label)
            if (
                normalize_text(text) == normalize_text(label)
                or re.fullmatch(rf"[\(\[]\s*{escaped}\s*[\)\]]", text, re.I)
                or re.fullmatch(rf"{escaped}\s*[\).:]\s*.+", text, re.I)
            ):
                matched = True
                break
        if not matched:
            return False
    return True


def characterize_unknown_choice_encoding(
    golds: Sequence[Any],
    choice_count: int,
) -> dict[str, Any]:
    """Profile an encoding without assuming a known label alphabet.

    This can establish that a stable, cardinality-compatible namespace exists;
    it cannot establish the semantic permutation between tokens and choices.
    """

    tokens: list[str] = []
    scalar = True
    for gold in golds:
        values = answer_values(gold)
        if len(values) != 1 or isinstance(values[0], (dict, list, tuple, set)):
            scalar = False
            break
        tokens.append(normalize_text(values[0]))
    counts = Counter(token for token in tokens if token)
    total = sum(counts.values())
    entropy = 0.0
    if total and len(counts) > 1:
        entropy = -sum(
            (count / total) * math.log(count / total)
            for count in counts.values()
        ) / math.log(len(counts))
    minimum_records = max(8, 2 * choice_count)
    coherent = bool(
        scalar
        and total == len(golds)
        and len(golds) >= minimum_records
        and len(counts) == choice_count
        and entropy >= 0.75
    )
    return {
        "coherent": coherent,
        "records": len(golds),
        "minimum_records": minimum_records,
        "choice_count": choice_count,
        "distinct_gold_tokens": len(counts),
        "normalized_entropy": entropy,
        "token_counts": dict(sorted(counts.items())),
        "semantic_permutation_verified": False,
    }


def choice_label_to_index(label: Any, choices: Any) -> int | None:
    if choices is None:
        return None
    candidates = _choice_label_candidates(label, choices)
    return next(iter(candidates)) if len(candidates) == 1 else None


def answer_values(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return [entry for entry in value if entry not in (None, "")]
    return [value]


def answer_contract(
    gold: Any,
    choices: list[Any] | None,
    evaluator: Any = None,
    output_contract: Any = None,
) -> dict[str, Any]:
    """Infer generic answer-contract properties from benchmark artifacts."""
    evaluator_text = normalize_contract_value(evaluator)
    output_text = normalize_contract_value(output_contract)
    combined = f"{evaluator_text} {output_text}".strip()
    values = answer_values(gold)
    cardinality = "set" if len(values) > 1 else "single"
    if any(token in combined for token in ("compound", "compound_answer", "compound answer", "single response containing all requested values")):
        cardinality = "compound"
    if any(token in combined for token in ("set", "list", "multi", "multiple", "all answers", "denotation")):
        if cardinality != "compound":
            cardinality = "set"
    if choices:
        kind = "choice"
    elif "ratio" in evaluator_text:
        kind = "ratio"
    elif "numeric" in evaluator_text or "number" in evaluator_text:
        kind = "numeric"
    elif "choice" in evaluator_text or "multiple choice" in evaluator_text:
        kind = "choice"
    elif any(token in evaluator_text for token in ("normalized", "loose", "alias", "denotation")):
        kind = "normalized_exact"
    elif "exact" in evaluator_text:
        kind = "exact"
    elif len(values) == 1 and parse_number(values[0]) is not None:
        kind = "numeric"
    else:
        kind = "normalized_exact"
    accepts_explanatory_text = any(
        token in combined
        for token in (
            "free form",
            "free-form",
            "natural language",
            "answer extraction",
            "extract",
            "explanation",
            "sentence",
        )
    )
    return {
        "kind": kind,
        "cardinality": cardinality,
        "accepts_explanatory_text": accepts_explanatory_text,
    }


def infer_evaluator_type(gold: Any, choices: list[Any] | None, evaluator: Any = None) -> str:
    contract = answer_contract(gold, choices, evaluator)
    if contract["cardinality"] in {"set", "compound"}:
        return contract["cardinality"]
    return contract["kind"]


def evaluate_answer(prediction: Any, gold: Any, choices: list[Any] | None, evaluator: Any = None) -> bool:
    contract = answer_contract(gold, choices, evaluator)
    kind = contract["kind"]
    if contract["cardinality"] == "set":
        return _evaluate_answer_set(prediction, answer_values(gold), kind, choices, evaluator)
    if contract["cardinality"] == "compound":
        return _evaluate_compound_answer(prediction, gold, kind, choices)
    return _evaluate_single_answer(prediction, gold, kind, choices)


def _evaluate_single_answer(prediction: Any, gold: Any, kind: str, choices: list[Any] | None) -> bool:
    if kind == "choice":
        prediction_index = choice_label_to_index(prediction, choices)
        gold_index = choice_label_to_index(gold, choices)
        if prediction_index is not None and gold_index is not None:
            return prediction_index == gold_index
        return normalize_text(prediction) == normalize_text(gold)
    if kind == "numeric":
        pred_num = parse_number(prediction)
        gold_num = parse_number(gold)
        return pred_num is not None and gold_num is not None and abs(pred_num - gold_num) < 1e-9
    if kind == "ratio":
        return _evaluate_ratio_answer(prediction, gold)
    if kind == "exact":
        return str(prediction).strip() == str(gold).strip()
    return normalize_loose(prediction) == normalize_loose(gold)


def parse_ratio_value(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    ratio = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)\s*:\s*([-+]?\d+(?:\.\d+)?)", text)
    fraction = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)\s*/\s*([-+]?\d+(?:\.\d+)?)", text)
    match = ratio or fraction
    if match:
        numerator = float(match.group(1))
        denominator = float(match.group(2))
        if denominator == 0:
            return None
        return numerator / denominator
    decimal = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text)
    if decimal:
        return float(text)
    return None


def _evaluate_ratio_answer(prediction: Any, gold: Any) -> bool:
    pred_ratio = parse_ratio_value(prediction)
    gold_ratio = parse_ratio_value(gold)
    if pred_ratio is not None and gold_ratio is not None:
        tolerance = max(1e-9, 1e-6 * max(1.0, abs(pred_ratio), abs(gold_ratio)))
        return abs(pred_ratio - gold_ratio) <= tolerance
    return normalize_loose(prediction) == normalize_loose(gold)


def answer_variants(
    gold: Any,
    choices: list[Any] | None = None,
    evaluator: Any = None,
    output_contract: Any = None,
) -> list[tuple[str, Any]]:
    variants: list[tuple[str, Any]] = []
    if gold is None:
        return variants
    contract = answer_contract(gold, choices, evaluator, output_contract)
    if contract["cardinality"] == "set":
        values = [str(value).strip() for value in answer_values(gold)]
        if len(values) > 1:
            variants.append(("set_reordered", list(reversed(values))))
            variants.append(("set_comma_joined", ", ".join(values)))
        return variants
    if contract["cardinality"] == "compound":
        return variants
    text = str(gold).strip()
    if contract["accepts_explanatory_text"]:
        variants.append(("answer_prefix", f"Answer: {text}"))
        variants.append(("final_answer_sentence", f"The final answer is {text}."))
    if text:
        variants.append(("case_variant", text.swapcase()))
    num = parse_number(text)
    if num is not None and float(num).is_integer():
        variants.append(("comma_numeric", f"{int(num):,}"))
    if choices:
        idx = choice_label_to_index(gold, choices)
        if idx is not None:
            variants.append(("choice_text", str(choice_values(choices)[idx])))
            variants.append(("choice_label_with_period", f"{CHOICE_LABELS[idx]}."))
    return variants


def _evaluate_answer_set(
    prediction: Any,
    gold_values: list[Any],
    kind: str,
    choices: list[Any] | None,
    evaluator: Any = None,
) -> bool:
    predicted_values = answer_values(prediction)
    if len(predicted_values) == 1 and isinstance(predicted_values[0], str) and len(gold_values) > 1:
        predicted_values = _split_list_answer(predicted_values[0])
    if len(predicted_values) != len(gold_values):
        return False
    remaining = list(gold_values)
    for predicted in predicted_values:
        matched_index = None
        for idx, gold in enumerate(remaining):
            if _evaluate_single_answer(predicted, gold, kind, choices):
                matched_index = idx
                break
        if matched_index is None:
            return False
        remaining.pop(matched_index)
    return not remaining


def _evaluate_compound_answer(
    prediction: Any,
    gold: Any,
    kind: str,
    choices: list[Any] | None,
) -> bool:
    predicted_parts = _split_compound_answer(prediction)
    gold_parts = _split_compound_answer(gold)
    if len(predicted_parts) != len(gold_parts):
        return False
    for predicted, expected in zip(predicted_parts, gold_parts):
        if parse_number(predicted) is not None and parse_number(expected) is not None:
            if not _evaluate_single_answer(predicted, expected, "numeric", choices):
                return False
            continue
        if not _evaluate_single_answer(predicted, expected, kind, choices):
            return False
    return True


def _split_compound_answer(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    text = str(value).strip()
    if not text:
        return []
    parts = re.split(r"\s*;\s*", text)
    return [part.strip() for part in parts if part.strip()]


def _split_list_answer(value: str) -> list[str]:
    text = value.strip()
    if not text:
        return []
    parts = re.split(r"\s*(?:,|;|\||\band\b)\s*", text)
    return [part.strip() for part in parts if part.strip()]
