"""Memoized per-schema reading instructions for unfamiliar benchmarks.

How a benchmark should be read -- which field is the task, whether the gold is
one value or a set of equally acceptable answers, what could be wrong with it --
is a semantic question that keyword tables never answer completely.  A model
answers it well, but a model answers it slightly differently each time, and an
audit whose field mapping moves between runs cannot be compared with itself.

So the answer is derived once per distinct schema and stored.  The lookup is
pure code: the fingerprint is computed from the data and matched exactly, and
the stored table is never shown to a model.  Prompt size therefore does not
grow with the number of benchmarks profiled.

Matching is exact rather than approximate on purpose.  A miss costs one small
call; a loose match risks reading one benchmark with another's assumptions,
which is the failure mode that produced false confirmed findings before.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

PROFILE_SCHEMA_VERSION = "benchaudit-benchmark-profile-v1"

# Only shapes are fingerprinted.  Values would make every dataset unique and
# defeat reuse across benchmarks that genuinely share a schema.
_SCALAR_TYPES = {
    type(None): "null",
    bool: "bool",
    int: "int",
    float: "float",
    str: "str",
}


def _value_shape(value: Any) -> str:
    if isinstance(value, list):
        inner = sorted({_value_shape(entry) for entry in value})
        return f"list[{'|'.join(inner)}]" if inner else "list[]"
    if isinstance(value, dict):
        return "object"
    return _SCALAR_TYPES.get(type(value), "other")


def schema_shape(rows: Iterable[Mapping[str, Any]], *, sample: int = 20) -> dict[str, list[str]]:
    """Field names mapped to every value shape observed for them.

    Several rows are inspected because optional fields and mixed types are
    common; a shape seen in any sampled row belongs to the schema.
    """

    observed: dict[str, set[str]] = {}
    for index, row in enumerate(rows):
        if index >= sample:
            break
        if not isinstance(row, Mapping):
            continue
        for key, value in row.items():
            observed.setdefault(str(key), set()).add(_value_shape(value))
    return {key: sorted(shapes) for key, shapes in sorted(observed.items())}


def schema_fingerprint(rows: Iterable[Mapping[str, Any]], *, sample: int = 20) -> str:
    """Stable identity of a benchmark's shape, independent of its contents."""

    payload = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "shape": schema_shape(rows, sample=sample),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BenchmarkProfile:
    fingerprint: str
    field_names: tuple[str, ...]
    field_roles: dict[str, Any] = field(default_factory=dict)
    gold_semantics: dict[str, Any] = field(default_factory=dict)
    components: tuple[str, ...] = ()
    suggested_checks: tuple[dict[str, Any], ...] = ()
    provenance: str = "llm_inferred"
    model: str | None = None
    first_seen: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "fingerprint": self.fingerprint,
            "field_names": list(self.field_names),
            "field_roles": self.field_roles,
            "gold_semantics": self.gold_semantics,
            "components": list(self.components),
            "suggested_checks": [dict(entry) for entry in self.suggested_checks],
            "provenance": self.provenance,
            "model": self.model,
            "first_seen": self.first_seen,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkProfile":
        return cls(
            fingerprint=str(payload["fingerprint"]),
            field_names=tuple(payload.get("field_names") or ()),
            field_roles=dict(payload.get("field_roles") or {}),
            gold_semantics=dict(payload.get("gold_semantics") or {}),
            components=tuple(payload.get("components") or ()),
            suggested_checks=tuple(
                dict(entry) for entry in (payload.get("suggested_checks") or ())
                if isinstance(entry, Mapping)
            ),
            provenance=str(payload.get("provenance") or "llm_inferred"),
            model=payload.get("model"),
            first_seen=payload.get("first_seen"),
        )


class BenchmarkProfileStore:
    """A JSONL table of schema fingerprints to reading instructions.

    Append-only: a fingerprint already present is never silently overwritten,
    so an audit cannot change how earlier audits read the same schema.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._entries: dict[str, BenchmarkProfile] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                profile = BenchmarkProfile.from_dict(payload)
            except (json.JSONDecodeError, KeyError, TypeError):
                # A malformed row must not silently change how data is read.
                continue
            self._entries.setdefault(profile.fingerprint, profile)

    def get(self, fingerprint: str) -> BenchmarkProfile | None:
        return self._entries.get(fingerprint)

    def lookup(self, rows: Iterable[Mapping[str, Any]]) -> tuple[str, BenchmarkProfile | None]:
        """The fingerprint for these rows and its profile when already known."""

        fingerprint = schema_fingerprint(rows)
        return fingerprint, self._entries.get(fingerprint)

    def put(self, profile: BenchmarkProfile) -> bool:
        """Store a newly derived profile.  Returns False if one already exists."""

        if profile.fingerprint in self._entries:
            return False
        self._entries[profile.fingerprint] = profile
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(profile.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
            )
        return True

    def __len__(self) -> int:
        return len(self._entries)
