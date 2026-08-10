from __future__ import annotations

import re
import string
from typing import Any, Mapping


CHOICE_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _drop_formatting_punctuation(text: str) -> str:
    """Remove punctuation that is formatting, keep punctuation that is value.

    The SQuAD recipe this follows deletes every punctuation mark, which suits
    text spans and corrupts numbers: "-5" becomes "5", "0.46" becomes "046".
    A minus sign before a number and a point or hyphen between digits are part
    of the answer; the same characters between letters are not, and are dropped
    exactly as before so "e-mail" and "state-of-the-art" read unchanged.
    """

    kept: list[str] = []
    for index, char in enumerate(text):
        if char not in string.punctuation:
            kept.append(char)
            continue
        previous = text[index - 1] if index else ""
        following = text[index + 1] if index + 1 < len(text) else ""
        if char in ".-" and previous.isdigit() and following.isdigit():
            kept.append(char)
        elif char == "-" and following.isdigit() and not (
            previous.isdigit() or previous.isalpha()
        ):
            kept.append(char)
    return "".join(kept)


def normalize_loose(value: Any) -> str:
    text = normalize_text(value)
    text = _drop_formatting_punctuation(text)
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


# What a profiled scoring verdict means for how answers are compared.  The
# verdict is derived from the benchmark's own rows, so it decides ahead of the
# evaluator label, which our adapter writes from a hand-maintained table.
#
# Verdicts with no bearing on comparing two answer strings -- tests being run,
# criteria being graded, an end state being inspected, a model judging -- are
# absent on purpose: for those the label's own inference is no worse.
_SCORING_COMPARISON_KINDS = {
    "exact_match": "exact",
    "numeric_tolerance": "numeric",
    "any_of_accepted": "normalized_exact",
    "structured_match": "normalized_exact",
}

# Several acceptable wordings of one answer, as against an answer that is
# itself several values.  Both arrive as a list of strings; only a profile's
# verdict tells them apart, and it asserts this one only where some record
# really carries more than one value.  Conflating them scored "any of these"
# as "all of these", so answering correctly failed and reciting every wording
# passed.
CARDINALITY_ALTERNATIVES = "alternatives"
_ALTERNATIVE_COMPARISONS = frozenset({"any_of_accepted"})

# Cardinalities that describe the answer rather than how one value is compared,
# so they name the contract in place of its comparison kind.
MULTI_VALUE_CARDINALITIES = frozenset({"set", "compound", CARDINALITY_ALTERNATIVES})

# Comparisons that judge something other than a reference answer: a test suite
# passing, criteria being graded, an end state being inspected.  A benchmark
# scored this way has no scalar gold, so checks written against one do not
# apply to it -- its absence is the design, not a defect.
NON_SCALAR_COMPARISONS = frozenset({"test_execution", "rubric_graded", "state_check"})


# Whether any record in this benchmark carries a gold.  A benchmark where none
# does is not scored against reference answers -- observable from the rows
# alone, without a model and without knowing what the benchmark is called.
ITEM_GOLD_COVERAGE_KEY = "_benchmark_has_any_gold"


def scores_a_scalar_answer(item: Any) -> bool | None:
    """Whether this benchmark judges a reference answer, or None if unjudged.

    A profile decides where it has ruled.  Failing that, a benchmark in which
    not one record carries a gold is not judging reference answers; one where
    some do and some do not has a gap worth reporting, which is the distinction
    a per-item check cannot draw on its own.

    None is not False: with neither source, nothing has ruled on the shape and
    a check must not assume one either way.
    """

    comparison = scoring_comparison(item_scoring(item))
    if comparison:
        return comparison not in NON_SCALAR_COMPARISONS
    metadata = getattr(item, "metadata", None)
    if isinstance(metadata, Mapping) and ITEM_GOLD_COVERAGE_KEY in metadata:
        return bool(metadata[ITEM_GOLD_COVERAGE_KEY])
    return None


def scoring_comparison(scoring: Any) -> str:
    """The comparison a profile settled on, or "" when it settled on none."""

    if not isinstance(scoring, Mapping):
        return ""
    return str(scoring.get("comparison") or "")



# Where a contract decision came from.  The three sources disagree -- gold
# "1500" is compared numerically with no label and exactly with one saying
# exact_match -- so which was used changes what counts as correct, and until
# now no artifact recorded it.
CONTRACT_BASIS_PROFILE = "profile"   # derived from the benchmark's own rows
CONTRACT_BASIS_LABEL = "adapter_label"  # a string our adapter wrote
CONTRACT_BASIS_GUESS = "gold_shape"  # inferred from the gold alone


ITEM_SCORING_KEY = "_scoring"


def item_scoring(item: Any) -> Any:
    """The profile's scoring verdict carried on an item, if one was attached."""

    metadata = getattr(item, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    verdict = metadata.get(ITEM_SCORING_KEY)
    return verdict if isinstance(verdict, Mapping) else None


def answer_contract(
    gold: Any,
    choices: list[Any] | None,
    evaluator: Any = None,
    output_contract: Any = None,
    scoring: Any = None,
) -> dict[str, Any]:
    """Infer generic answer-contract properties from benchmark artifacts.

    ``scoring`` is a profile's verdict on how this benchmark decides
    correctness, derived from its own rows.  Where it speaks it decides; where
    it is absent or says nothing about comparing answers, the evaluator label
    is read as before.
    """

    comparison = scoring_comparison(scoring)
    basis = CONTRACT_BASIS_LABEL
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
    if comparison in _ALTERNATIVE_COMPARISONS and cardinality != "compound":
        cardinality = CARDINALITY_ALTERNATIVES
    if comparison in _SCORING_COMPARISON_KINDS and not choices:
        kind = _SCORING_COMPARISON_KINDS[comparison]
        basis = CONTRACT_BASIS_PROFILE
    elif choices:
        # Position-matching an option set is stricter than any comparison a
        # profile can name, so the options keep deciding how.  But where a
        # profile independently read these rows and named one, that is what the
        # run rested on, and recording the label understates it.
        kind = "choice"
        basis = CONTRACT_BASIS_PROFILE if comparison else CONTRACT_BASIS_LABEL
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
        basis = CONTRACT_BASIS_GUESS
    else:
        kind = "normalized_exact"
        basis = CONTRACT_BASIS_GUESS if not evaluator_text else CONTRACT_BASIS_LABEL
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
        "basis": basis,
    }


def infer_evaluator_type(gold: Any, choices: list[Any] | None, evaluator: Any = None) -> str:
    contract = answer_contract(gold, choices, evaluator)
    if contract["cardinality"] in MULTI_VALUE_CARDINALITIES:
        return contract["cardinality"]
    return contract["kind"]



def evaluator_accepts_aliases(evaluator: Any = None) -> bool:
    """Does the declared evaluator claim to accept an alias list?

    A benchmark that ships several accepted answers and an evaluator that says
    it handles aliases is not defective; it is doing exactly what it declares.
    Only an evaluator whose declaration makes no such claim can be "overstrict"
    with respect to declared alternatives.
    """

    return "alias" in normalize_contract_value(evaluator)



def contract_basis_census(items: Any) -> dict[str, int]:
    """How many items had their comparison decided by each basis.

    A run reporting mostly `gold_shape` or `adapter_label` rested on inference
    rather than on anything the benchmark stated, which is worth knowing when
    reading its findings.
    """

    counts: dict[str, int] = {}
    for item in items or ():
        contract = answer_contract(
            getattr(item, "gold", None),
            getattr(item, "choices", None),
            getattr(item, "evaluator", None),
            getattr(item, "output_contract", None),
            scoring=item_scoring(item),
        )
        basis = str(contract.get("basis") or "")
        if basis:
            counts[basis] = counts.get(basis, 0) + 1
    return counts


def evaluate_answer(
    prediction: Any,
    gold: Any,
    choices: list[Any] | None,
    evaluator: Any = None,
    aliases: list[Any] | None = None,
    scoring: Any = None,
) -> bool:
    contract = answer_contract(gold, choices, evaluator, scoring=scoring)
    kind = contract["kind"]
    if contract["cardinality"] == CARDINALITY_ALTERNATIVES:
        accepted = any(
            _evaluate_single_answer(prediction, value, kind, choices)
            for value in answer_values(gold)
        )
    elif contract["cardinality"] == "set":
        accepted = _evaluate_answer_set(
            prediction, answer_values(gold), kind, choices, evaluator
        )
    elif contract["cardinality"] == "compound":
        accepted = _evaluate_compound_answer(prediction, gold, kind, choices)
    else:
        accepted = _evaluate_single_answer(prediction, gold, kind, choices)
    if accepted or not aliases or not evaluator_accepts_aliases(evaluator):
        return accepted
    # The declaration promises alias handling, so a declared alternative is
    # accepted under the same comparison kind as the primary gold.
    return any(
        _evaluate_single_answer(prediction, alias, kind, choices) for alias in aliases
    )


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
    scoring: Any = None,
) -> list[tuple[str, Any]]:
    variants: list[tuple[str, Any]] = []
    if gold is None:
        return variants
    contract = answer_contract(gold, choices, evaluator, output_contract, scoring)
    if contract["cardinality"] == CARDINALITY_ALTERNATIVES:
        # Reordering alternatives leaves every one of them acceptable, and
        # joining them makes a wrong answer.  Neither is the rephrasing these
        # variants exist to try.
        return variants
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
