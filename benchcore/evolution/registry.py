"""Content-addressed, fail-closed registry for accepted declarative rules."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .controller import EvolutionRun
from .models import RuleSpec, RuleValidationError, canonical_json, canonical_sha256
from .rules import DeclarativeRuleChecker


REGISTRY_SCHEMA_VERSION = "benchcore-evolution-registry-v1"
RECEIPT_SCHEMA_VERSION = "benchcore-evolution-receipt-v1"


class EvolutionRegistry:
    """Atomically activate rules that carry a successful gate receipt.

    The registry is integrity checked, not cryptographically authenticated to a
    remote trust root.  Production deployments should mount this directory
    read-only and sign snapshots outside the candidate-accessible environment.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.rules_dir = self.root / "rules"
        self.receipts_dir = self.root / "receipts"
        self.gates_dir = self.root / "gates"
        self.snapshots_dir = self.root / "snapshots"
        self.registry_path = self.root / "registry.json"
        self.events_path = self.root / "events.jsonl"
        self.lock_path = self.root / ".registry.lock"

    def activate(self, spec: RuleSpec, run: EvolutionRun) -> dict[str, Any]:
        evaluation = run.final_evaluation
        if (
            run.status != "accepted"
            or evaluation is None
            or not evaluation.accepted
            or not evaluation.holdout_consumed
            or not evaluation.lineage_closed
        ):
            raise RuleValidationError(
                "only an accepted, one-shot-holdout-closed run may activate a rule"
            )
        if evaluation.rule_sha256 != spec.sha256:
            raise RuleValidationError("selected rule does not match the gate evaluation")
        _validate_activation_floor(run)
        self._ensure_layout()
        with self._lock():
            registry = self._read_registry()
            active = list(registry["active"])
            existing = next(
                (row for row in active if row["rule_id"] == spec.rule_id),
                None,
            )
            if existing is not None:
                if int(existing["version"]) >= spec.version:
                    raise RuleValidationError(
                        "new active rule version must be greater than the current version"
                    )
                active.remove(existing)
            run_payload = run.to_dict(include_example_details=False)
            gate_sha = canonical_sha256(run_payload)
            receipt_id = canonical_sha256({
                "run_id": run.run_id,
                "rule_sha256": spec.sha256,
                "gate_sha256": gate_sha,
            })[:32]
            rule_rel = Path("rules") / spec.rule_id / f"v{spec.version}-{spec.sha256}.json"
            receipt_rel = Path("receipts") / f"{receipt_id}.json"
            gate_rel = Path("gates") / f"{gate_sha}.json"
            receipt = {
                "schema_version": RECEIPT_SCHEMA_VERSION,
                "receipt_id": receipt_id,
                "run_id": run.run_id,
                "rule_id": spec.rule_id,
                "rule_version": spec.version,
                "rule_sha256": spec.sha256,
                "gate_bundle_sha256": gate_sha,
                "gate_bundle_path": str(gate_rel),
                "corpus_sha256": run.corpus_sha256,
                "policy_sha256": canonical_sha256(run.policy),
                "accepted": True,
                "evidence_ceiling": "review",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_write_json(self.root / rule_rel, spec.to_dict())
            _atomic_write_json(self.root / gate_rel, run_payload)
            _atomic_write_json(self.root / receipt_rel, receipt)
            generation = int(registry["generation"]) + 1
            active.append({
                "rule_id": spec.rule_id,
                "version": spec.version,
                "family": spec.family,
                "defect_type": spec.defect_type,
                "rule_sha256": spec.sha256,
                "rule_path": str(rule_rel),
                "receipt_id": receipt_id,
                "receipt_path": str(receipt_rel),
                "mode": "active_review",
            })
            active.sort(key=lambda row: (row["rule_id"], int(row["version"])))
            updated = {
                "schema_version": REGISTRY_SCHEMA_VERSION,
                "generation": generation,
                "active": active,
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_write_json(self.registry_path, updated)
            _atomic_write_json(self.snapshots_dir / f"generation-{generation}.json", updated)
            self._append_event({
                "event": "activate",
                "generation": generation,
                "rule_id": spec.rule_id,
                "rule_version": spec.version,
                "rule_sha256": spec.sha256,
                "receipt_id": receipt_id,
            })
            return {"registry": updated, "receipt": receipt}

    def load_active(self, *, family: str | None = None) -> list[DeclarativeRuleChecker]:
        registry = self._read_registry()
        checkers: list[DeclarativeRuleChecker] = []
        for entry in registry["active"]:
            if family is not None and entry["family"] not in {"generic", family}:
                continue
            rule_path = self._contained_path(entry["rule_path"])
            receipt_path = self._contained_path(entry["receipt_path"])
            rule_payload = json.loads(rule_path.read_text(encoding="utf-8"))
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            spec = RuleSpec.from_dict(rule_payload)
            if spec.sha256 != entry["rule_sha256"]:
                raise RuleValidationError("active rule digest does not match registry")
            if (
                receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION
                or receipt.get("accepted") is not True
                or receipt.get("evidence_ceiling") != "review"
                or receipt.get("rule_sha256") != spec.sha256
                or receipt.get("receipt_id") != entry["receipt_id"]
            ):
                raise RuleValidationError("active rule receipt is invalid")
            gate_path = self._contained_path(receipt.get("gate_bundle_path"))
            gate_payload = json.loads(gate_path.read_text(encoding="utf-8"))
            if canonical_sha256(gate_payload) != receipt.get("gate_bundle_sha256"):
                raise RuleValidationError("active rule gate bundle digest is invalid")
            expected_receipt_id = canonical_sha256({
                "run_id": receipt.get("run_id"),
                "rule_sha256": spec.sha256,
                "gate_sha256": receipt.get("gate_bundle_sha256"),
            })[:32]
            final = gate_payload.get("final_evaluation")
            if (
                expected_receipt_id != receipt.get("receipt_id")
                or gate_payload.get("status") != "accepted"
                or not isinstance(final, dict)
                or final.get("accepted") is not True
                or final.get("holdout_consumed") is not True
                or final.get("lineage_closed") is not True
                or final.get("rule_sha256") != spec.sha256
            ):
                raise RuleValidationError("active rule gate receipt cannot be replayed")
            checkers.append(
                DeclarativeRuleChecker(
                    spec,
                    registry_receipt=str(receipt["receipt_id"]),
                )
            )
        return checkers

    def deactivate(self, rule_id: str, *, reason: str) -> dict[str, Any]:
        """Remove an externally invalidated rule without deleting its evidence.

        Gate acceptance is not proof against distribution or representation
        shift.  A failed deployment canary must therefore have an auditable
        quarantine path instead of requiring destructive registry edits.
        """

        if not isinstance(rule_id, str) or not rule_id:
            raise RuleValidationError("deactivation requires a rule_id")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2_000:
            raise RuleValidationError(
                "deactivation reason must contain 1..2000 characters"
            )
        self._ensure_layout()
        with self._lock():
            registry = self._read_registry()
            selected = next(
                (entry for entry in registry["active"] if entry["rule_id"] == rule_id),
                None,
            )
            if selected is None:
                raise RuleValidationError(f"active rule not found: {rule_id!r}")
            active = [
                entry for entry in registry["active"]
                if entry["rule_id"] != rule_id
            ]
            generation = int(registry["generation"]) + 1
            updated = {
                "schema_version": REGISTRY_SCHEMA_VERSION,
                "generation": generation,
                "active": active,
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_write_json(self.registry_path, updated)
            _atomic_write_json(
                self.snapshots_dir / f"generation-{generation}.json",
                updated,
            )
            self._append_event({
                "event": "deactivate",
                "generation": generation,
                "rule_id": rule_id,
                "rule_version": selected["version"],
                "rule_sha256": selected["rule_sha256"],
                "receipt_id": selected["receipt_id"],
                "reason": reason.strip(),
            })
            return {"registry": updated, "deactivated": selected, "reason": reason.strip()}

    def snapshot(self) -> dict[str, Any]:
        registry = self._read_registry()
        return {
            "path": str(self.registry_path),
            "generation": registry["generation"],
            "active": list(registry["active"]),
            "sha256": canonical_sha256(registry),
        }

    def _ensure_layout(self) -> None:
        for path in (
            self.root,
            self.rules_dir,
            self.receipts_dir,
            self.gates_dir,
            self.snapshots_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _read_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {
                "schema_version": REGISTRY_SCHEMA_VERSION,
                "generation": 0,
                "active": [],
                "updated_at_utc": None,
            }
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != REGISTRY_SCHEMA_VERSION
            or not isinstance(payload.get("generation"), int)
            or not isinstance(payload.get("active"), list)
        ):
            raise RuleValidationError("evolution registry is malformed")
        required = {
            "rule_id", "version", "family", "defect_type", "rule_sha256",
            "rule_path", "receipt_id", "receipt_path", "mode",
        }
        ids: set[str] = set()
        for entry in payload["active"]:
            if not isinstance(entry, dict) or set(entry) != required:
                raise RuleValidationError("evolution registry entry is malformed")
            if entry["mode"] != "active_review":
                raise RuleValidationError("unknown evolution registry mode")
            if entry["rule_id"] in ids:
                raise RuleValidationError("duplicate active rule_id in registry")
            ids.add(entry["rule_id"])
        return payload

    def _contained_path(self, relative: Any) -> Path:
        if not isinstance(relative, str) or not relative:
            raise RuleValidationError("registry path is invalid")
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuleValidationError("registry path escapes registry root")
        unresolved = self.root / relative_path
        cursor = self.root
        for part in relative_path.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise RuleValidationError("registry artifacts may not traverse symlinks")
        candidate = unresolved.resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise RuleValidationError("registry path escapes registry root") from exc
        if not candidate.is_file() or candidate.is_symlink():
            raise RuleValidationError("registry artifact is missing or is a symlink")
        return candidate

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self._ensure_layout()
        with self.lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _append_event(self, payload: dict[str, Any]) -> None:
        previous = "0" * 64
        if self.events_path.exists():
            lines = [line for line in self.events_path.read_text(encoding="utf-8").splitlines() if line]
            if lines:
                last = json.loads(lines[-1])
                previous = str(last.get("event_sha256") or "")
                if len(previous) != 64:
                    raise RuleValidationError("registry event chain is malformed")
        event = {
            **payload,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "previous_event_sha256": previous,
        }
        event["event_sha256"] = canonical_sha256(event)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_activation_floor(run: EvolutionRun) -> None:
    """Independent minimum floor that a caller-supplied policy cannot relax."""

    evaluation = run.final_evaluation
    holdout = evaluation.holdout if evaluation is not None else None
    dev = evaluation.dev if evaluation is not None else None
    if evaluation is None or holdout is None or dev is None:
        raise RuleValidationError("activation requires dev and holdout metrics")
    checks = {
        "dev positives >= 20": dev.positives >= 20,
        "dev negatives >= 20": dev.negatives >= 20,
        "holdout positives >= 80": holdout.positives >= 80,
        "holdout negatives >= 80": holdout.negatives >= 80,
        "dev recall >= 0.90": dev.recall >= 0.90,
        "holdout recall >= 0.90": holdout.recall >= 0.90,
        "dev false-positive rate <= 0.02": dev.false_positive_rate <= 0.02,
        "holdout false-positive rate <= 0.02": holdout.false_positive_rate <= 0.02,
        "dev paired discrimination >= 0.90": dev.paired_discrimination >= 0.90,
        "holdout paired discrimination >= 0.90": holdout.paired_discrimination >= 0.90,
        "dev abstention == 0": dev.abstention_rate == 0.0,
        "holdout abstention == 0": holdout.abstention_rate == 0.0,
        "holdout recall Wilson lower >= 0.90": (
            holdout.recall_wilson95[0] is not None
            and holdout.recall_wilson95[0] >= 0.90
        ),
        "holdout false-positive Wilson upper <= 0.05": (
            holdout.false_positive_rate_wilson95[1] is not None
            and holdout.false_positive_rate_wilson95[1] <= 0.05
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuleValidationError(
            "automatic activation floor failed: " + "; ".join(failed)
        )
