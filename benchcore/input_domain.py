"""Fail-closed input-domain checks for the benchmark audit command.

``benchcore audit`` audits benchmark definitions.  A per-method result export
can contain question and answer-looking fields too, so allowing it to fall
through field inference produces plausible but meaningless benchmark findings.
This module only recognizes one narrow, high-confidence export shape.  It does
not claim to classify every input artifact or prove that a rejected artifact is
not also usable as a benchmark source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


AUDIT_INPUT_DOMAIN_SCHEMA_VERSION = "result-export-refusal-v1"

# These are artifact-role markers, not value checks.  An explicitly present but
# empty contract field prevents refusal because row-local emptiness cannot prove
# that a benchmark/package-level contract is absent.
RESULT_EXPORT_MARKERS = frozenset({"prediction", "judge"})
CONTRACT_CARRIER_FIELDS = frozenset({
    "choices",
    "evaluator",
    "options",
    "output_contract",
    "output_format",
    "rubric",
    "rubrics",
})


@dataclass(frozen=True)
class InputDomainRefusal:
    schema_version: str
    rows_checked: int
    required_result_markers: tuple[str, ...]
    absent_contract_carriers: tuple[str, ...]


class UnsupportedAuditInput(ValueError):
    """The artifact has a recognized shape outside ``benchcore audit``'s domain."""

    def __init__(self, refusal: InputDomainRefusal):
        self.refusal = refusal
        markers = ", ".join(refusal.required_result_markers)
        carriers = ", ".join(refusal.absent_contract_carriers)
        super().__init__(
            "unsupported audit input: result-export-like schema detected "
            f"({refusal.rows_checked} row(s) all contain top-level {markers}; "
            f"no top-level benchmark contract carrier was found among {carriers}). "
            "`benchcore audit` accepts benchmark definitions, not per-method "
            "prediction/judgment exports. Use a dedicated result-export analysis "
            "workflow. No audit report was produced."
        )


def result_export_refusal(
    rows: Sequence[Mapping[str, Any]],
) -> InputDomainRefusal | None:
    """Return a refusal for the one frozen result-export-like schema.

    The rule intentionally requires both result markers on every row and the
    absence of every known contract carrier across the complete input.  Keys
    are compared case-insensitively but only at the top level.  Nested marker
    names, file names, task shapes, inferred profiles, and field values do not
    participate.
    """

    if not rows:
        return None

    row_keys = [
        {str(key).casefold() for key in row.keys()}
        for row in rows
    ]
    if not all(RESULT_EXPORT_MARKERS <= keys for keys in row_keys):
        return None
    if any(CONTRACT_CARRIER_FIELDS & keys for keys in row_keys):
        return None

    return InputDomainRefusal(
        schema_version=AUDIT_INPUT_DOMAIN_SCHEMA_VERSION,
        rows_checked=len(rows),
        required_result_markers=tuple(sorted(RESULT_EXPORT_MARKERS)),
        absent_contract_carriers=tuple(sorted(CONTRACT_CARRIER_FIELDS)),
    )


def enforce_audit_input_domain(rows: Sequence[Mapping[str, Any]]) -> None:
    refusal = result_export_refusal(rows)
    if refusal is not None:
        raise UnsupportedAuditInput(refusal)
