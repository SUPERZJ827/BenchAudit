"""The fact record shared by contract predicates and their host checkers.

Kept apart from both so a general predicate module and a benchmark-specific one
can each depend on the type without depending on each other.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


GDPVAL_PREDICATE_VERSION = "benchcore-gdpval-objective/1.0"

def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ObjectiveFact:
    defect_type: str
    evidence_level: str
    atom: Mapping[str, Any]
    message: str
    severity: str
    confidence: float
    repair: str
    confirmation_capable: bool = True

    @property
    def signature(self) -> str:
        return _sha256_json({
            "defect_type": self.defect_type,
            "evidence_level": self.evidence_level,
            "atom": self.atom,
            "predicate_version": GDPVAL_PREDICATE_VERSION,
        })

    def evidence(self, row: Mapping[str, Any], dataset_revision: str) -> dict[str, Any]:
        return {
            "proof_schema_version": "1.0",
            "evidence_level": self.evidence_level,
            "benchmark_family": "gdpval",
            "dataset_revision": dataset_revision,
            "predicate_version": GDPVAL_PREDICATE_VERSION,
            "replay_input_sha256": _sha256_json(row),
            "fact_signature": self.signature,
            "atom": dict(self.atom),
        }
