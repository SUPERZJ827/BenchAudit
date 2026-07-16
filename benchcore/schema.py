from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldMapping:
    item_id: str | None = None
    task: str | None = None
    context: list[str] = field(default_factory=list)
    choices: str | None = None
    gold: str | None = None
    aliases: str | None = None
    output_contract: str | None = None
    evaluator: str | None = None
    metadata: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkItem:
    item_id: str
    raw: dict[str, Any]
    task: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    choices: list[Any] | None = None
    gold: Any = None
    aliases: list[Any] = field(default_factory=list)
    output_contract: Any = None
    evaluator: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Stable per-record identity. ``item_id`` is benchmark data and may itself
    # be duplicated (one of the defects we audit), so it cannot key internal
    # coverage or evidence joins.
    row_uid: str | None = None
    # Physical source identity is deliberately separate from benchmark-owned
    # item_id.  source_row_index remains stable under offset/limit and manifest
    # reordering; the hash detects accidental joins against changed input bytes.
    source_row_index: int | None = None
    source_row_sha256: str | None = None


@dataclass
class Violation:
    item_id: str
    artifact: str
    mechanism: str
    defect_type: str
    severity: str
    confidence: float
    message: str
    detection_method: str = "unknown"
    defect_scope: str = "substantive"
    evidence: dict[str, Any] = field(default_factory=dict)
    suggested_repair: str | None = None
    review_only: bool = False
    # Evidence strength and impact severity are intentionally orthogonal.  The
    # compatibility flag above remains for older consumers; new reports should
    # use this typed tier, assigned by the central promotion policy.
    evidence_tier: str = "unclassified"
    proof_kind: str = "unclassified"
    promotion_reason: str = ""
    # Record identity independent of the potentially defective ``item_id``.
    # Dataset-scoped findings can additionally declare ``target_row_uids`` in
    # their evidence payload.
    row_uid: str | None = None
    source_row_sha256: str | None = None
