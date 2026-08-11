"""Conservative text contracts for objective oracle integrity checks.

These transforms deliberately serve two different claims:

* ``duplicate_oracle_comparison_value`` decides only whether a raw duplicate
  difference is strong enough to support the claim that two oracles conflict.
  It may downgrade superficial formatting differences, but it must preserve
  answer-bearing symbols such as signs, unit quotes, percent signs, decimal
  points, slashes, and interior punctuation.
* ``unexpected_oracle_characters`` identifies exact Unicode format/control
  characters in a live oracle.  It never depends on a model or external file.

Keeping the contracts narrow prevents both known normalization failure modes:
turning different answers into equal ones, and turning formatting variants
into a mechanically confirmed semantic contradiction.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from .decision_policy import (
    DUPLICATE_ORACLE_COMPARISON_CONTRACT,
    DUPLICATE_ORACLE_TERMINAL_SENTENCE_PUNCTUATION,
    ORACLE_ALLOWED_CONTROL_CHARACTERS,
    ORACLE_CHARACTER_INTEGRITY_CONTRACT,
    ORACLE_UNEXPECTED_UNICODE_CATEGORIES,
)
from .evaluators import parse_number


_PLAIN_NUMERIC_TEXT = re.compile(
    r"[-+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
)


def _numeric_comparison_value(value: Any) -> str | None:
    """Canonicalize a complete numeric scalar, never a numeric substring.

    ``parse_number`` intentionally extracts a number from explanatory text,
    which is useful for answer scoring but too loose for duplicate-oracle
    proof: both ``42\" x 50\"`` and ``42 x 50 mm`` would otherwise become 42.
    The full-match gate also lets us repair the leading-decimal form before
    calling ``parse_number`` (whose regex reads ``.5`` as 5).
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        numeric_text = str(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            return None
        numeric_text = str(value)
    elif isinstance(value, str):
        numeric_text = unicodedata.normalize("NFKC", value).strip()
        if _PLAIN_NUMERIC_TEXT.fullmatch(numeric_text) is None:
            return None
        numeric_text = numeric_text.replace(",", "")
        if numeric_text.startswith("."):
            numeric_text = "0" + numeric_text
        elif numeric_text.startswith("+."):
            numeric_text = "+0" + numeric_text[1:]
        elif numeric_text.startswith("-."):
            numeric_text = "-0" + numeric_text[1:]
    else:
        return None

    # Reuse the production numeric parser as the admissibility check, while
    # Decimal supplies a stable serialization that does not preserve harmless
    # trailing zeroes or introduce float representation noise.
    if parse_number(numeric_text) is None:
        return None
    try:
        parsed = Decimal(numeric_text)
    except InvalidOperation:
        return None
    if not parsed.is_finite():
        return None
    if parsed == 0:
        parsed = Decimal(0)
    return format(parsed.normalize(), "f")


def _surface_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    text = re.sub(r"\s+", " ", text).strip()
    # This is intentionally not a generic punctuation stripper.  In
    # particular, quotes may be units (42\"), and signs/percent/decimal marks
    # carry answer semantics.  Only terminal sentence marks are downgraded.
    return text.rstrip(DUPLICATE_ORACLE_TERMINAL_SENTENCE_PUNCTUATION).rstrip()


def _surface_structure(value: Any) -> Any:
    numeric = _numeric_comparison_value(value)
    if numeric is not None:
        return {"type": "numeric", "value": numeric}
    if isinstance(value, str):
        return {"type": "string", "value": _surface_text(value)}
    if isinstance(value, list):
        return {"type": "list", "value": [_surface_structure(part) for part in value]}
    if isinstance(value, tuple):
        return {"type": "tuple", "value": [_surface_structure(part) for part in value]}
    if isinstance(value, dict):
        entries = [
            [_surface_structure(key), _surface_structure(child)]
            for key, child in value.items()
        ]
        entries.sort(
            key=lambda entry: json.dumps(
                entry[0], sort_keys=True, ensure_ascii=False, separators=(",", ":")
            )
        )
        return {"type": "dict", "value": entries}
    return {
        "type": f"scalar:{type(value).__name__}",
        "value": value if value is None or isinstance(value, (bool, int, float)) else str(value),
    }


def duplicate_oracle_comparison_value(value: Any) -> str:
    """Return the conservative value used only to authorize conflict proof."""

    return json.dumps(
        _surface_structure(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _text_leaves(value: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _text_leaves(child, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for index, (key, child) in enumerate(value.items()):
            # Keys can themselves carry invisible characters.  The ordinal
            # path remains stable for a live replay of the same canonical
            # object and avoids embedding a potentially invisible key in the
            # human-facing location string.
            yield from _text_leaves(key, f"{path}.keys[{index}]")
            yield from _text_leaves(child, f"{path}.values[{index}]")


def unexpected_oracle_characters(value: Any) -> list[dict[str, Any]]:
    """Return exact unexpected Unicode format/control characters in ``value``.

    Tabs and line endings are ordinary formatting in long-form references and
    are explicitly allowed.  Unicode ``Cf`` characters (including U+200B and
    BOM U+FEFF) and all other ``Cc`` controls are reported.
    """

    findings: list[dict[str, Any]] = []
    for path, text in _text_leaves(value):
        for position, character in enumerate(text):
            category = unicodedata.category(character)
            if category not in ORACLE_UNEXPECTED_UNICODE_CATEGORIES:
                continue
            if category == "Cc" and character in ORACLE_ALLOWED_CONTROL_CHARACTERS:
                continue
            findings.append(
                {
                    "path": path,
                    "position": position,
                    "codepoint": f"U+{ord(character):04X}",
                    "unicode_name": unicodedata.name(character, "UNKNOWN"),
                    "category": category,
                }
            )
    return findings
