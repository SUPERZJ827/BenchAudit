"""Verify a proposed refutation instead of judging whether one exists.

A claim that some reference value has no source in the supplied artifacts cannot
be checked by asking a model to prove the negative; asked that way it retreats to
"the source might be external" and never commits. Reversing the burden makes the
question answerable: let a model produce the span it believes grounds the value,
and have a program decide whether that span is real.

The program never judges whether a value is *justified*. It decides only whether
a quoted span occurs in the material and carries the value, which is a string
question with a definite answer.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

REFUTED = "refuted"            # a verbatim span was produced and verified
UNREFUTED = "unrefuted"        # no grounding was offered at all
UNRESOLVED = "unresolved"      # a claim of grounding that a program cannot check

GROUNDING_KINDS = frozenset({"verbatim", "derived", "none"})


def normalize(text: Any) -> str:
    """Fold the differences a quote may legitimately introduce, and no others."""
    folded = unicodedata.normalize("NFKC", str(text)).casefold()
    folded = folded.replace("‘", "'").replace("’", "'")
    folded = folded.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", folded).strip()


def span_occurs(materials: str, span: str) -> bool:
    span_text = normalize(span)
    return bool(span_text) and span_text in normalize(materials)


def value_in_span(span: str, value: Any) -> bool:
    """Does the quoted span actually carry the value it is offered to ground?

    Booleans are excluded: `false` never appears in a user's words, so a span
    could never carry one, and demanding it would refute nothing.
    """
    if isinstance(value, bool):
        return True
    return normalize(value) in normalize(span)


def verify(materials: str, claim: dict[str, Any]) -> tuple[str, str]:
    """Return (outcome, reason) for one proposed grounding."""
    kind = str(claim.get("grounding_kind", "")).strip()
    if kind not in GROUNDING_KINDS:
        return UNRESOLVED, f"unknown grounding_kind {kind!r}"
    if kind == "none":
        return UNREFUTED, "no grounding offered"
    if kind == "derived":
        # A derivation is an argument, and this module does not evaluate
        # arguments.  It blocks confirmation without granting refutation.
        return UNRESOLVED, "grounding claimed as derived, not verbatim"
    span = str(claim.get("span") or "")
    if not span.strip():
        return UNRESOLVED, "verbatim grounding claimed without a span"
    if not span_occurs(materials, span):
        return UNREFUTED, "quoted span does not occur in the supplied material"
    if not value_in_span(span, claim.get("value")):
        return UNRESOLVED, "span occurs but does not carry the value"
    return REFUTED, "verbatim span verified in the supplied material"
