from __future__ import annotations

"""Typed coverage outcomes for benchmark audits.

The finding stream answers "what evidence did a checker emit?".  It cannot
answer "what did the checker actually cover?": an empty iterable can mean no
finding, an inapplicable item, an abstention, a provider failure, or a security
policy refusal.  This module keeps those concepts separate.

``AuditLedgerEntry.status`` is the terminal state for one planned
item-by-checker attempt.  ``lifecycle`` records the states reached on the way
there, so ``eligible`` and ``attempted`` are observable rather than inferred
from an empty finding list.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping, Sequence


AuditStatus = Literal[
    "eligible",
    "attempted",
    "completed_no_finding",
    "finding",
    "abstained",
    "unsupported",
    "operational_failed",
    "security_blocked",
    "ineligible",
]

VALID_AUDIT_STATUSES: frozenset[str] = frozenset(
    {
        "eligible",
        "attempted",
        "completed_no_finding",
        "finding",
        "abstained",
        "unsupported",
        "operational_failed",
        "security_blocked",
        "ineligible",
    }
)

COMPLETED_STATUSES: frozenset[str] = frozenset(
    {"completed_no_finding", "finding"}
)
GAP_STATUSES: frozenset[str] = frozenset(
    {
        "eligible",
        "attempted",
        "abstained",
        "unsupported",
        "operational_failed",
        "security_blocked",
    }
)


@dataclass(frozen=True)
class AuditEligibility:
    """A checker's explicit applicability decision for one item.

    ``eligible=None`` deliberately means that the checker has no reliable
    applicability contract.  The auditor may still attempt it, but a normal
    empty return remains coverage-unknown rather than becoming a clean claim.

    ``status`` is only used for a deliberate non-attempt.  Valid values are
    ``ineligible``, ``unsupported``, ``abstained``, and ``security_blocked``.
    """

    eligible: bool | None
    reason: str
    status: AuditStatus | None = None

    def __post_init__(self) -> None:
        if self.status is not None and self.status not in {
            "ineligible",
            "unsupported",
            "abstained",
            "security_blocked",
        }:
            raise ValueError(f"invalid eligibility terminal status: {self.status}")
        if self.eligible is True and self.status is not None:
            raise ValueError("an eligible checker cannot have a non-attempt status")

    @classmethod
    def applicable(cls, reason: str = "checker declared the item applicable") -> "AuditEligibility":
        return cls(True, reason)

    @classmethod
    def unknown(
        cls,
        reason: str = "checker does not declare an applicability contract",
    ) -> "AuditEligibility":
        return cls(None, reason)

    @classmethod
    def not_applicable(cls, reason: str) -> "AuditEligibility":
        return cls(False, reason, "ineligible")


@dataclass
class AuditLedgerEntry:
    """Coverage record for one planned item-by-checker audit."""

    item_id: str
    checker: str
    status: AuditStatus
    reason: str
    lifecycle: list[str] = field(default_factory=list)
    planned: bool = True
    eligible: bool | None = None
    attempted: bool = False
    completed: bool = False
    finding_count: int = 0
    substantive_finding_count: int = 0
    checker_scope: str = "item"
    details: dict[str, Any] = field(default_factory=dict)
    # Unlike benchmark-supplied item_id, this key is unique per source row.
    row_uid: str | None = None

    def __post_init__(self) -> None:
        if self.status not in VALID_AUDIT_STATUSES:
            raise ValueError(f"invalid audit status: {self.status}")
        if not self.lifecycle:
            self.lifecycle = [self.status]
        invalid = set(self.lifecycle) - (VALID_AUDIT_STATUSES | {"planned"})
        if invalid:
            raise ValueError(f"invalid audit lifecycle states: {sorted(invalid)}")

    @property
    def coverage_unknown(self) -> bool:
        """Whether this entry leaves applicability or execution unresolved."""

        return self.status in GAP_STATUSES or (
            self.status in COMPLETED_STATUSES and self.eligible is None
        )

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["coverage_unknown"] = self.coverage_unknown
        return row


class AuditControlFlow(RuntimeError):
    """Base class for deliberate, non-finding checker termination."""

    status: AuditStatus = "abstained"

    def __init__(self, reason: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = dict(details or {})


class AuditAbstained(AuditControlFlow):
    status: AuditStatus = "abstained"


class AuditUnsupported(AuditControlFlow):
    status: AuditStatus = "unsupported"


class AuditSecurityBlocked(AuditControlFlow):
    status: AuditStatus = "security_blocked"


def ledger_entry_dict(entry: AuditLedgerEntry | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(entry, AuditLedgerEntry):
        return entry.to_dict()
    row = dict(entry)
    status = str(row.get("status", ""))
    if status not in VALID_AUDIT_STATUSES:
        raise ValueError(f"invalid audit status: {status}")
    if "coverage_unknown" not in row:
        row["coverage_unknown"] = status in GAP_STATUSES or (
            status in COMPLETED_STATUSES and row.get("eligible") is None
        )
    return row


def summarize_coverage(
    entries: Sequence[AuditLedgerEntry | Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize coverage without treating no-finding as benchmark cleanliness."""

    rows = [ledger_entry_dict(entry) for entry in entries]
    status_distribution = {
        status: sum(row["status"] == status for row in rows)
        for status in sorted(VALID_AUDIT_STATUSES)
        if any(row["status"] == status for row in rows)
    }
    planned = sum(bool(row.get("planned", True)) for row in rows)
    eligible = sum(row.get("eligible") is True for row in rows)
    eligibility_unknown = sum(row.get("eligible") is None for row in rows)
    attempted = sum(bool(row.get("attempted", False)) for row in rows)
    completed = sum(bool(row.get("completed", False)) for row in rows)
    unknown = sum(bool(row.get("coverage_unknown", False)) for row in rows)
    return {
        "planned": planned,
        "eligible": eligible,
        "eligibility_unknown": eligibility_unknown,
        "attempted": attempted,
        "completed": completed,
        "completed_no_finding": sum(
            row["status"] == "completed_no_finding" for row in rows
        ),
        "finding": sum(row["status"] == "finding" for row in rows),
        "unknown": unknown,
        "operational_failed": sum(
            row["status"] == "operational_failed" for row in rows
        ),
        "security_blocked": sum(
            row["status"] == "security_blocked" for row in rows
        ),
        "abstained": sum(row["status"] == "abstained" for row in rows),
        "unsupported": sum(row["status"] == "unsupported" for row in rows),
        "ineligible": sum(row["status"] == "ineligible" for row in rows),
        "status_distribution": status_distribution,
        "semantics": {
            "completed_no_finding": (
                "the checker returned normally without a finding; this is not a clean verdict"
            ),
            "unknown": (
                "applicability, execution, support, or security coverage remains unresolved"
            ),
        },
    }
