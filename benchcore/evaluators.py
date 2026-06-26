from __future__ import annotations

import re
import string
from typing import Any


CHOICE_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
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


def choice_label_to_index(label: Any, choices: list[Any] | None) -> int | None:
    if choices is None:
        return None
    text = str(label).strip()
    if not text:
        return None
    upper = text.upper()
    if upper in CHOICE_LABELS[: len(choices)]:
        return CHOICE_LABELS.index(upper)
    if upper.startswith(tuple(f"{c}." for c in CHOICE_LABELS[: len(choices)])):
        return CHOICE_LABELS.index(upper[0])
    for idx, choice in enumerate(choices):
        if normalize_loose(text) == normalize_loose(choice):
            return idx
    return None


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
        return choice_label_to_index(prediction, choices) == choice_label_to_index(gold, choices)
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
            variants.append(("choice_text", str(choices[idx])))
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
