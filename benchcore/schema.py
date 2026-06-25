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
