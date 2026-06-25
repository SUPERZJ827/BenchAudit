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


def infer_evaluator_type(gold: Any, choices: list[Any] | None, evaluator: Any = None) -> str:
    if evaluator:
        low = normalize_text(evaluator)
        if "numeric" in low or "number" in low:
            return "numeric"
        if "choice" in low or "multiple" in low:
            return "choice"
        if "normalized" in low:
            return "normalized_exact"
        if "exact" in low:
            return "exact"
    if choices:
        return "choice"
    if parse_number(gold) is not None:
        return "numeric"
    return "normalized_exact"


def evaluate_answer(prediction: Any, gold: Any, choices: list[Any] | None, evaluator: Any = None) -> bool:
    kind = infer_evaluator_type(gold, choices, evaluator)
    if kind == "choice":
        return choice_label_to_index(prediction, choices) == choice_label_to_index(gold, choices)
    if kind == "numeric":
        pred_num = parse_number(prediction)
        gold_num = parse_number(gold)
        return pred_num is not None and gold_num is not None and abs(pred_num - gold_num) < 1e-9
    if kind == "exact":
        return str(prediction).strip() == str(gold).strip()
    return normalize_loose(prediction) == normalize_loose(gold)


def answer_variants(gold: Any, choices: list[Any] | None = None) -> list[tuple[str, Any]]:
    variants: list[tuple[str, Any]] = []
    if gold is None:
        return variants
    text = str(gold).strip()
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
