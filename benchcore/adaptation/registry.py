"""Tamper-evident, content-addressed registry for accepted adapters."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .controller import AdapterRun
from .models import AdapterSpec, AdapterValidationError, canonical_json, canonical_sha256


REGISTRY_SCHEMA_VERSION = "benchcore-adapter-registry-v1"
RECEIPT_SCHEMA_VERSION = "benchcore-adapter-receipt-v1"


class AdapterRegistry:
    """Registry trust is local filesystem integrity, not model self-approval.

    A production deployment should place this directory behind a read-only or
    signed trust root.  The hash chain here detects accidental and unsophisticated
    tampering; it is not a substitute for an external signing key.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.adapters_dir = self.root / "adapters"
        self.receipts_dir = self.root / "receipts"
        self.gates_dir = self.root / "gates"
        self.snapshots_dir = self.root / "snapshots"
        self.registry_path = self.root / "registry.json"
        self.events_path = self.root / "events.jsonl"
        self.lock_path = self.root / ".registry.lock"

    def activate(self, run: AdapterRun) -> dict[str, Any]:
        evaluation = run.final_evaluation
        if evaluation is None or not evaluation.accepted:
            raise AdapterValidationError("activation requires an accepted final evaluation")
        if run.selected_adapter is None:
            raise AdapterValidationError("activation requires a selected adapter")
        spec = AdapterSpec.from_dict(run.selected_adapter)
        if evaluation.adapter_sha256 != spec.sha256:
            raise AdapterValidationError("selected adapter and gate evaluation differ")
        _validate_activation_floor(run)
        run_payload = run.to_dict()
        gate_sha = canonical_sha256(run_payload)
        receipt_id = canonical_sha256({
            "run_id": run.run_id,
            "adapter_sha256": spec.sha256,
            "gate_sha256": gate_sha,
        })[:32]

        with self._lock():
            registry = self._read_registry()
            replaced = next((
                entry for entry in registry["active"]
                if entry["family"] == spec.family
                and entry["schema_fingerprint"] == spec.schema_fingerprint
            ), None)
            if (
                replaced is not None
                and replaced["mode"] == "active_verified"
                and evaluation.activation_mode != "active_verified"
            ):
                raise AdapterValidationError(
                    "a reference-verified adapter cannot be silently downgraded "
                    "to structural-only"
                )
            same_identity = next((
                entry for entry in registry["active"]
                if entry["adapter_id"] == spec.adapter_id
            ), None)
            if (
                same_identity is not None
                and int(same_identity["version"]) >= spec.version
                and same_identity["adapter_sha256"] != spec.sha256
            ):
                raise AdapterValidationError(
                    "adapter_id replacement requires a strictly increasing version"
                )
            active = [
                entry for entry in registry["active"]
                if not (
                    entry["family"] == spec.family
                    and entry["schema_fingerprint"] == spec.schema_fingerprint
                )
            ]
            adapter_rel = Path("adapters") / f"{spec.sha256}.json"
            gate_rel = Path("gates") / f"{gate_sha}.json"
            receipt_rel = Path("receipts") / f"{receipt_id}.json"
            receipt = {
                "schema_version": RECEIPT_SCHEMA_VERSION,
                "receipt_id": receipt_id,
                "run_id": run.run_id,
                "adapter_id": spec.adapter_id,
                "adapter_version": spec.version,
                "family": spec.family,
                "schema_fingerprint": spec.schema_fingerprint,
                "source_content_sha256": run.source_content_sha256,
                "adapter_sha256": spec.sha256,
                "gate_bundle_sha256": gate_sha,
                "gate_bundle_path": str(gate_rel),
                "accepted": True,
                "activation_mode": evaluation.activation_mode,
                "evidence_tier": evaluation.evidence_tier,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_write_json(self.root / adapter_rel, spec.to_dict())
            _atomic_write_json(self.root / gate_rel, run_payload)
            _atomic_write_json(self.root / receipt_rel, receipt)
            generation = int(registry["generation"]) + 1
            active.append({
                "adapter_id": spec.adapter_id,
                "version": spec.version,
                "family": spec.family,
                "schema_fingerprint": spec.schema_fingerprint,
                "adapter_sha256": spec.sha256,
                "adapter_path": str(adapter_rel),
                "receipt_id": receipt_id,
                "receipt_path": str(receipt_rel),
                "mode": evaluation.activation_mode,
            })
            active.sort(key=lambda entry: (
                entry["family"], entry["schema_fingerprint"], entry["adapter_id"]
            ))
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
                "event": "activate",
                "generation": generation,
                "adapter_id": spec.adapter_id,
                "adapter_version": spec.version,
                "adapter_sha256": spec.sha256,
                "schema_fingerprint": spec.schema_fingerprint,
                "receipt_id": receipt_id,
                "mode": evaluation.activation_mode,
            })
            return {"registry": updated, "receipt": receipt}

    def resolve(
        self,
        *,
        family: str,
        schema_fingerprint: str,
        allow_shadow: bool = False,
    ) -> tuple[AdapterSpec, dict[str, Any]]:
        registry = self._read_registry()
        matches = [
            entry for entry in registry["active"]
            if entry["family"] == family
            and entry["schema_fingerprint"] == schema_fingerprint
        ]
        if not matches:
            raise AdapterValidationError(
                "no active adapter matches this family and schema fingerprint"
            )
        if len(matches) != 1:
            raise AdapterValidationError("adapter registry resolution is ambiguous")
        entry = matches[0]
        if entry["mode"] == "active_shadow" and not allow_shadow:
            raise AdapterValidationError(
                "matching adapter is structural-only; pass explicit shadow opt-in"
            )
        adapter_path = self._contained_file(entry["adapter_path"])
        receipt_path = self._contained_file(entry["receipt_path"])
        spec = AdapterSpec.from_dict(
            json.loads(adapter_path.read_text(encoding="utf-8"))
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self._verify_entry(entry, spec, receipt)
        return spec, receipt

    def snapshot(self) -> dict[str, Any]:
        registry = self._read_registry()
        return {
            "path": str(self.registry_path),
            "generation": registry["generation"],
            "active": list(registry["active"]),
            "sha256": canonical_sha256(registry),
        }

    def _verify_entry(
        self,
        entry: dict[str, Any],
        spec: AdapterSpec,
        receipt: dict[str, Any],
    ) -> None:
        if spec.sha256 != entry["adapter_sha256"]:
            raise AdapterValidationError("active adapter digest does not match registry")
        required = {
            "schema_version", "receipt_id", "run_id", "adapter_id",
            "adapter_version", "family", "schema_fingerprint",
            "source_content_sha256", "adapter_sha256", "gate_bundle_sha256",
            "gate_bundle_path", "accepted", "activation_mode", "evidence_tier",
            "created_at_utc",
        }
        if not isinstance(receipt, dict) or set(receipt) != required:
            raise AdapterValidationError("active adapter receipt is malformed")
        if (
            receipt["schema_version"] != RECEIPT_SCHEMA_VERSION
            or receipt["receipt_id"] != entry["receipt_id"]
            or receipt["adapter_sha256"] != spec.sha256
            or receipt["schema_fingerprint"] != spec.schema_fingerprint
            or receipt["activation_mode"] != entry["mode"]
            or receipt["accepted"] is not True
        ):
            raise AdapterValidationError("active adapter receipt is invalid")
        gate_path = self._contained_file(receipt["gate_bundle_path"])
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        if canonical_sha256(gate) != receipt["gate_bundle_sha256"]:
            raise AdapterValidationError("active adapter gate bundle digest is invalid")
        final = gate.get("final_evaluation")
        expected_receipt_id = canonical_sha256({
            "run_id": receipt["run_id"],
            "adapter_sha256": spec.sha256,
            "gate_sha256": receipt["gate_bundle_sha256"],
        })[:32]
        if (
            expected_receipt_id != receipt["receipt_id"]
            or gate.get("selected_adapter") != spec.to_dict()
            or gate.get("source_schema_fingerprint") != spec.schema_fingerprint
            or gate.get("source_content_sha256") != receipt["source_content_sha256"]
            or not isinstance(final, dict)
            or final.get("accepted") is not True
            or final.get("activation_mode") != entry["mode"]
            or final.get("adapter_sha256") != spec.sha256
        ):
            raise AdapterValidationError("active adapter gate receipt cannot be replayed")

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
            raise AdapterValidationError("adapter registry is malformed")
        required = {
            "adapter_id", "version", "family", "schema_fingerprint",
            "adapter_sha256", "adapter_path", "receipt_id", "receipt_path", "mode",
        }
        identities: set[tuple[str, str]] = set()
        for entry in payload["active"]:
            if not isinstance(entry, dict) or set(entry) != required:
                raise AdapterValidationError("adapter registry entry is malformed")
            if entry["mode"] not in {"active_shadow", "active_verified"}:
                raise AdapterValidationError("unknown adapter registry mode")
            identity = (entry["family"], entry["schema_fingerprint"])
            if identity in identities:
                raise AdapterValidationError("duplicate active family/schema adapter")
            identities.add(identity)
        self._verify_event_chain()
        return payload

    def _verify_event_chain(self) -> None:
        if not self.events_path.exists():
            return
        previous = "0" * 64
        for line_number, line in enumerate(
            self.events_path.read_text(encoding="utf-8").splitlines(),
            1,
        ):
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AdapterValidationError(
                    f"adapter event chain has invalid JSON at line {line_number}"
                ) from exc
            if not isinstance(event, dict) or event.get("previous_event_sha256") != previous:
                raise AdapterValidationError(
                    f"adapter event chain link is invalid at line {line_number}"
                )
            claimed = event.get("event_sha256")
            unsigned = dict(event)
            unsigned.pop("event_sha256", None)
            observed = canonical_sha256(unsigned)
            if claimed != observed:
                raise AdapterValidationError(
                    f"adapter event digest is invalid at line {line_number}"
                )
            previous = observed

    def _ensure_layout(self) -> None:
        for path in (
            self.root,
            self.adapters_dir,
            self.receipts_dir,
            self.gates_dir,
            self.snapshots_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _contained_file(self, relative: Any) -> Path:
        if not isinstance(relative, str) or not relative:
            raise AdapterValidationError("registry artifact path is invalid")
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise AdapterValidationError("registry artifact escapes registry root")
        cursor = self.root
        for part in relative_path.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise AdapterValidationError("registry artifacts may not traverse symlinks")
        resolved = (self.root / relative_path).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise AdapterValidationError("registry artifact escapes registry root") from exc
        if not resolved.is_file() or resolved.is_symlink():
            raise AdapterValidationError("registry artifact is missing or is a symlink")
        return resolved

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
        self._verify_event_chain()
        previous = "0" * 64
        if self.events_path.exists():
            lines = [
                line for line in self.events_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            if lines:
                previous = str(json.loads(lines[-1]).get("event_sha256") or "")
                if len(previous) != 64:
                    raise AdapterValidationError("adapter event chain is malformed")
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


def _validate_activation_floor(run: AdapterRun) -> None:
    evaluation = run.final_evaluation
    if evaluation is None:
        raise AdapterValidationError("activation requires a final evaluation")
    adaptation = evaluation.adaptation
    checks = {
        "at least 20 source rows": int(adaptation.get("total_rows") or 0) >= 20,
        "complete rate is exactly one": adaptation.get("complete_rate") == 1.0,
        "zero abstained rows": adaptation.get("abstained_rows") == 0,
        "structural gate passed": evaluation.structural_passed,
        "evaluation accepted": evaluation.accepted,
    }
    if evaluation.activation_mode == "active_verified":
        reference = evaluation.reference
        checks.update({
            "verified adapter has a reference": reference is not None,
            "reference field accuracy is exactly one": (
                reference is not None and reference.field_accuracy == 1.0
            ),
            "reference row accuracy is exactly one": (
                reference is not None and reference.row_accuracy == 1.0
            ),
        })
    elif evaluation.activation_mode != "active_shadow":
        checks["known activation mode"] = False
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AdapterValidationError(
            "independent adapter activation floor failed: " + "; ".join(failed)
        )


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
