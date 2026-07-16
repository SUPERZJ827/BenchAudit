#!/usr/bin/env python3
"""Build and score opaque-schema adapter challenges for Workspace-Bench.

The experiment deliberately separates three trust domains:

* ``challenge.jsonl`` contains only opaque nested records.  It never contains
  field mappings, source-field names in the envelope, or canonical references.
* ``adapter_spec.json`` is the adapter input.  It maps canonical source fields
  to opaque paths and declares reversible value codecs.
* ``reference_sidecar.jsonl`` is evaluator-only gold.  It binds every challenge
  row to the original canonical raw record by a cryptographic digest.

Consequently, a candidate adapter can be evaluated without receiving the gold
reference, while the scorer can distinguish abstention from a wrong mapping.
The default build creates three deterministic, previously unseen nested schema
families from the pinned Workspace-Bench Full export.

This is a *given-spec conformance experiment*.  A perfect result demonstrates
that an AdapterSpec is executed losslessly and preserves downstream checker
behaviour.  It does not measure automatic schema-discovery accuracy.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import copy
import hashlib
import json
import math
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from benchcore.loader import build_items, load_rows
from benchcore.schema import FieldMapping, Violation
from benchcore.workspace_invariants import WorkspaceArtifactInvariantChecker


REPO = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPO / "datasets" / "workspacebench" / "full.jsonl"
DEFAULT_OUT_DIR = REPO / "reports" / "workspace_adapter_experiment_full388_20260715"
DEFAULT_FULL_ROOT = Path(
    "/home/zhoujun/.cache/huggingface/hub/"
    "datasets--Workspace-Bench--Workspace-Bench"
)
PINNED_FULL_SHA256 = (
    "2e3d8fd1f5a741b9e6b73ebab9ce23e26ce054527b4f3477de8fdd950aad9dbe"
)

ADAPTER_SPEC_SCHEMA = "workspace-adapter-spec-v1"
SIDECAR_SCHEMA = "workspace-adapter-reference-sidecar-v1"
MANIFEST_SCHEMA = "workspace-adapter-challenge-manifest-v1"
RESULT_SCHEMA = "workspace-adapter-experiment-result-v1"

VARIANTS = ("opaque_lattice", "opaque_shards", "opaque_capsule")

# These are canonical BenchmarkItem-facing fields.  Workspace-Bench does not
# contain choices/gold/aliases; they remain in the report with zero applicable
# rows rather than being silently treated as successful mappings.
CORE_FIELDS = (
    "item_id",
    "task",
    "context",
    "choices",
    "gold",
    "aliases",
    "output_contract",
    "evaluator",
    "metadata",
)
WORKSPACE_EXTENSION_FIELDS = (
    "output_files",
    "rubrics",
    "rubric_types",
    "file_dep_graph",
    "data_manifest",
    "input_files",
)

FORBIDDEN_ENVELOPE_KEYS = frozenset(
    {
        *CORE_FIELDS,
        *WORKSPACE_EXTENSION_FIELDS,
        "adapter_spec",
        "canonical_reference",
        "field_mapping",
        "mapping",
        "reference_sidecar",
        "source_field",
        "source_row_index",
    }
)
OPAQUE_KEY = re.compile(r"^x[0-9a-f]{10,20}$")
PATH_COMPONENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MISSING = object()


@dataclass(frozen=True)
class AdapterSpec:
    """Declarative mapping consumed by the adapter, never by challenge rows."""

    variant: str
    field_paths: dict[str, str]
    value_codecs: dict[str, dict[str, Any]]
    schema_version: str = ADAPTER_SPEC_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "variant": self.variant,
            "field_paths": dict(sorted(self.field_paths.items())),
            "value_codecs": copy.deepcopy(self.value_codecs),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AdapterSpec":
        if value.get("schema_version") != ADAPTER_SPEC_SCHEMA:
            raise ValueError(
                f"unsupported AdapterSpec schema: {value.get('schema_version')!r}"
            )
        variant = value.get("variant")
        paths = value.get("field_paths")
        codecs = value.get("value_codecs", {})
        if not isinstance(variant, str) or not variant:
            raise ValueError("AdapterSpec.variant must be a non-empty string")
        if not isinstance(paths, dict):
            raise ValueError("AdapterSpec.field_paths must be an object")
        if not isinstance(codecs, dict):
            raise ValueError("AdapterSpec.value_codecs must be an object")
        clean_paths: dict[str, str] = {}
        for field, path in paths.items():
            if not isinstance(field, str) or not field:
                raise ValueError("AdapterSpec field names must be non-empty strings")
            if not isinstance(path, str) or not path:
                raise ValueError(f"AdapterSpec path for {field!r} must be non-empty")
            _validate_path(path)
            clean_paths[field] = path
        clean_codecs: dict[str, dict[str, Any]] = {}
        for field, codec in codecs.items():
            if field not in clean_paths:
                raise ValueError(f"codec declared for unmapped field {field!r}")
            if not isinstance(codec, dict):
                raise ValueError(f"codec for {field!r} must be an object")
            kind = codec.get("kind")
            if kind != "xor_utf8_v1":
                raise ValueError(f"unsupported codec kind for {field!r}: {kind!r}")
            _codec_key(codec)
            clean_codecs[field] = copy.deepcopy(codec)
        return cls(
            variant=variant,
            field_paths=clean_paths,
            value_codecs=clean_codecs,
        )


@dataclass(frozen=True)
class AdaptationResult:
    values: dict[str, Any]
    abstentions: dict[str, str]
    errors: dict[str, str]


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_path(path: str) -> None:
    components = path.split(".")
    if not components or any(not PATH_COMPONENT.fullmatch(row) for row in components):
        raise ValueError(f"invalid AdapterSpec dotted path: {path!r}")


def _opaque_token(material: str, length: int = 12) -> str:
    return "x" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:length]


def _variant_path(variant: str, slot: int, seed: int) -> str:
    material = f"workspace-adapter-envelope:{seed}:{variant}:{slot}"
    tokens = [_opaque_token(f"{material}:{index}") for index in range(5)]
    if variant == "opaque_lattice":
        return ".".join((tokens[0], tokens[1], tokens[4]))
    if variant == "opaque_shards":
        depth = 3 + slot % 2
        return ".".join(tokens[:depth])
    if variant == "opaque_capsule":
        depth = 4 + slot % 2
        return ".".join(tokens[:depth])
    raise ValueError(f"unknown schema variant: {variant}")


def derive_adapter_spec(
    fields: Iterable[str], *, variant: str, seed: int,
) -> AdapterSpec:
    """Derive a deterministic opaque layout without embedding it in the data."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown schema variant: {variant}")
    ordered = sorted(
        set(fields),
        key=lambda field: hashlib.sha256(
            f"workspace-adapter-order:{seed}:{variant}:{field}".encode("utf-8")
        ).digest(),
    )
    paths = {
        field: _variant_path(variant, slot, seed)
        for slot, field in enumerate(ordered)
    }
    if len(set(paths.values())) != len(paths):
        raise RuntimeError("opaque path collision")
    _reject_prefix_collisions(paths.values())
    codec_key = hashlib.sha256(
        f"workspace-adapter-id-codec:{seed}:{variant}".encode("utf-8")
    ).digest()[:24]
    return AdapterSpec(
        variant=variant,
        field_paths=paths,
        value_codecs={
            "item_id": {
                "kind": "xor_utf8_v1",
                "key_b64": base64.urlsafe_b64encode(codec_key).decode("ascii"),
                "security_note": "reversible obfuscation, not encryption",
            }
        },
    )


def _reject_prefix_collisions(paths: Iterable[str]) -> None:
    ordered = sorted(path.split(".") for path in paths)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if len(left) <= len(right) and right[: len(left)] == left:
                raise ValueError(
                    f"AdapterSpec path prefix collision: {'.'.join(left)!r}"
                )


def _codec_key(codec: Mapping[str, Any]) -> bytes:
    encoded = codec.get("key_b64")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("xor_utf8_v1 codec requires key_b64")
    try:
        key = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid xor_utf8_v1 key_b64") from exc
    if not 16 <= len(key) <= 64:
        raise ValueError("xor_utf8_v1 key must contain 16..64 bytes")
    return key


def _encode_value(value: Any, codec: Mapping[str, Any] | None) -> Any:
    if codec is None:
        return copy.deepcopy(value)
    if codec.get("kind") != "xor_utf8_v1" or not isinstance(value, str):
        raise ValueError("xor_utf8_v1 accepts string values only")
    key = _codec_key(codec)
    payload = value.encode("utf-8")
    masked = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(payload))
    token = base64.urlsafe_b64encode(masked).decode("ascii").rstrip("=")
    return f"oid1_{token}"


def _decode_value(value: Any, codec: Mapping[str, Any] | None) -> Any:
    if codec is None:
        return copy.deepcopy(value)
    if codec.get("kind") != "xor_utf8_v1":
        raise ValueError(f"unsupported value codec: {codec.get('kind')!r}")
    if not isinstance(value, str) or not value.startswith("oid1_"):
        raise ValueError("opaque ID does not use the oid1_ encoding")
    encoded = value[5:]
    padding = "=" * (-len(encoded) % 4)
    try:
        payload = base64.b64decode(
            encoded + padding, altchars=b"-_", validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise ValueError("opaque ID contains invalid base64") from exc
    key = _codec_key(codec)
    raw = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(payload))
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("opaque ID cannot be decoded as UTF-8") from exc


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    components = path.split(".")
    current = target
    for component in components[:-1]:
        child = current.setdefault(component, {})
        if not isinstance(child, dict):
            raise ValueError(f"path collision at {component!r}")
        current = child
    leaf = components[-1]
    if leaf in current:
        raise ValueError(f"duplicate opaque path: {path!r}")
    current[leaf] = value


def _get_path(source: Mapping[str, Any], path: str) -> Any:
    current: Any = source
    for component in path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            return MISSING
        current = current[component]
    return current


def transform_row(row: Mapping[str, Any], spec: AdapterSpec, *, seed: int) -> dict[str, Any]:
    """Apply an AdapterSpec in the forward direction to create a challenge row."""
    transformed: dict[str, Any] = {}
    # Opaque decoys ensure the envelope is not merely one leaf per source field.
    decoy_root = _opaque_token(f"workspace-adapter-decoy:{seed}:{spec.variant}")
    _set_path(
        transformed,
        f"{decoy_root}.{_opaque_token(f'{spec.variant}:decoy:0')}",
        hashlib.sha256(f"{seed}:{spec.variant}".encode("utf-8")).hexdigest()[:20],
    )
    _set_path(
        transformed,
        f"{decoy_root}.{_opaque_token(f'{spec.variant}:decoy:1')}",
        [0, False, None],
    )
    for field, path in spec.field_paths.items():
        if field not in row:
            continue
        _set_path(
            transformed,
            path,
            _encode_value(row[field], spec.value_codecs.get(field)),
        )
    assert_no_envelope_mapping_leak(transformed, spec)
    return transformed


def assert_no_envelope_mapping_leak(row: Mapping[str, Any], spec: AdapterSpec) -> None:
    """Reject semantic or provenance keys outside mapped payload subtrees.

    Nested payloads such as the evaluator legitimately retain their internal
    schema.  They are treated as atomic values; only the challenge envelope is
    required to be opaque.
    """
    payload_paths = {tuple(path.split(".")) for path in spec.field_paths.values()}

    def visit(value: Any, prefix: tuple[str, ...]) -> None:
        if prefix in payload_paths:
            return
        if not isinstance(value, Mapping):
            return
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("challenge envelope keys must be strings")
            if key.casefold() in FORBIDDEN_ENVELOPE_KEYS:
                raise ValueError(f"mapping answer leaked through envelope key {key!r}")
            if not OPAQUE_KEY.fullmatch(key):
                raise ValueError(f"non-opaque challenge envelope key: {key!r}")
            visit(child, (*prefix, key))

    visit(row, ())


def adapt_row(row: Mapping[str, Any], spec: AdapterSpec) -> AdaptationResult:
    """Execute only the supplied spec; no reference data is consulted."""
    values: dict[str, Any] = {}
    abstentions: dict[str, str] = {}
    errors: dict[str, str] = {}
    for field, path in spec.field_paths.items():
        value = _get_path(row, path)
        if value is MISSING:
            abstentions[field] = "declared path is absent"
            continue
        try:
            values[field] = _decode_value(value, spec.value_codecs.get(field))
        except (TypeError, ValueError) as exc:
            errors[field] = str(exc)
    return AdaptationResult(values=values, abstentions=abstentions, errors=errors)


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(canonical_json(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_experiment_artifacts(
    rows: Sequence[dict[str, Any]],
    out_dir: Path,
    *,
    seed: int = 20260715,
    variants: Sequence[str] = VARIANTS,
    source_dataset: Path | None = None,
) -> dict[str, Any]:
    """Build opaque challenges and evaluator-only references for ``rows``."""
    if not rows:
        raise ValueError("cannot build an adapter experiment from zero rows")
    if len(set(variants)) != len(variants):
        raise ValueError("schema variants must be unique")
    unknown = set(variants) - set(VARIANTS)
    if unknown:
        raise ValueError("unknown schema variant(s): " + ", ".join(sorted(unknown)))
    fields = sorted(set().union(*(row.keys() for row in rows)))
    if "item_id" not in fields or "task" not in fields:
        raise ValueError("Workspace adapter references require item_id and task")
    if source_dataset is not None:
        source_dataset = source_dataset.expanduser().resolve()
        source_sha_start = file_sha256(source_dataset)
    else:
        source_sha_start = canonical_sha256(list(rows))
    implementation_start = implementation_manifest()

    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    variant_manifests: list[dict[str, Any]] = []
    for variant in variants:
        spec = derive_adapter_spec(fields, variant=variant, seed=seed)
        challenge_rows: list[dict[str, Any]] = []
        sidecar_rows: list[dict[str, Any]] = []
        for index, source in enumerate(rows):
            reference = copy.deepcopy(source)
            challenge = transform_row(source, spec, seed=seed)
            challenge_rows.append(challenge)
            sidecar_rows.append({
                "schema_version": SIDECAR_SCHEMA,
                "variant": variant,
                "row_index": index,
                "source_row_sha256": canonical_sha256(reference),
                "challenge_row_sha256": canonical_sha256(challenge),
                "canonical_reference": reference,
            })

        variant_dir = out_dir / variant
        challenge_path = variant_dir / "challenge.jsonl"
        sidecar_path = variant_dir / "reference_sidecar.jsonl"
        spec_path = variant_dir / "adapter_spec.json"
        _write_jsonl(challenge_path, challenge_rows)
        _write_jsonl(sidecar_path, sidecar_rows)
        _write_json(spec_path, spec.to_dict())
        variant_manifests.append({
            "variant": variant,
            "rows": len(challenge_rows),
            "challenge": str(challenge_path.relative_to(out_dir)),
            "reference_sidecar": str(sidecar_path.relative_to(out_dir)),
            "adapter_spec": str(spec_path.relative_to(out_dir)),
            "challenge_sha256": file_sha256(challenge_path),
            "reference_sidecar_sha256": file_sha256(sidecar_path),
            "adapter_spec_sha256": file_sha256(spec_path),
            "mapping_leak_check_passed": True,
            "opaque_item_id_codec": "xor_utf8_v1",
        })

    source_sha_end = (
        file_sha256(source_dataset)
        if source_dataset is not None else canonical_sha256(list(rows))
    )
    implementation_end = implementation_manifest()
    if implementation_start["sha256"] != implementation_end["sha256"]:
        raise RuntimeError(
            "adapter implementation changed while challenges were built"
        )
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "source_dataset": str(source_dataset) if source_dataset else None,
        "source_rows": len(rows),
        "source_fields": fields,
        "core_fields": list(CORE_FIELDS),
        "workspace_extension_fields": list(WORKSPACE_EXTENSION_FIELDS),
        "source_sha256_start": source_sha_start,
        "source_sha256_end": source_sha_end,
        "source_hash_end_check": {
            "passed": source_sha_start == source_sha_end,
            "expected": source_sha_start,
            "observed": source_sha_end,
        },
        "separation_policy": {
            "challenge_contains_mapping": False,
            "challenge_contains_reference": False,
            "adapter_receives_reference": False,
            "reference_is_evaluator_sidecar_only": True,
        },
        "variants": variant_manifests,
        "implementation": implementation_start,
        "implementation_hash_end_check": {
            "passed": True,
            "expected": implementation_start["sha256"],
            "observed": implementation_end["sha256"],
        },
    }
    if source_sha_start != source_sha_end:
        raise RuntimeError("source dataset changed while challenges were built")
    _write_json(out_dir / "manifest.json", manifest)
    return manifest


def load_adapter_spec(path: Path) -> AdapterSpec:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("AdapterSpec JSON root must be an object")
    return AdapterSpec.from_dict(value)


def load_variant_bundle(
    challenge_path: Path,
    sidecar_path: Path,
    spec_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], AdapterSpec]:
    challenge_rows = load_rows(challenge_path)
    sidecar_rows = load_rows(sidecar_path)
    spec = load_adapter_spec(spec_path)
    if len(challenge_rows) != len(sidecar_rows):
        raise ValueError(
            "challenge and reference sidecar row counts differ: "
            f"{len(challenge_rows)} != {len(sidecar_rows)}"
        )
    references: list[dict[str, Any]] = []
    for index, (challenge, sidecar) in enumerate(zip(challenge_rows, sidecar_rows)):
        if sidecar.get("schema_version") != SIDECAR_SCHEMA:
            raise ValueError(f"sidecar row {index} has an unsupported schema")
        if sidecar.get("variant") != spec.variant:
            raise ValueError(f"sidecar row {index} does not match AdapterSpec.variant")
        if sidecar.get("row_index") != index:
            raise ValueError(f"sidecar row {index} has an invalid row_index")
        observed = canonical_sha256(challenge)
        if sidecar.get("challenge_row_sha256") != observed:
            raise ValueError(f"challenge row {index} does not match its sidecar digest")
        reference = sidecar.get("canonical_reference")
        if not isinstance(reference, dict):
            raise ValueError(f"sidecar row {index} has no canonical reference object")
        if sidecar.get("source_row_sha256") != canonical_sha256(reference):
            raise ValueError(f"canonical reference row {index} failed its digest check")
        assert_no_envelope_mapping_leak(challenge, spec)
        references.append(reference)
    return challenge_rows, references, spec


def _workspace_mapping() -> FieldMapping:
    return FieldMapping(
        item_id="item_id",
        task="task",
        context=["context", "data_manifest", "file_dep_graph"],
        choices="choices",
        gold="gold",
        aliases="aliases",
        output_contract="output_contract",
        evaluator="evaluator",
        metadata=["metadata"],
        diagnostics={"source": "explicit", "experiment": "workspace_adapter"},
    )


def _semantic_violation_signature(violation: Violation) -> dict[str, Any]:
    value = asdict(violation)
    # These are source-container identities rather than finding semantics.  They
    # are evaluated separately by exact row recovery.
    value.pop("row_uid", None)
    value.pop("source_row_sha256", None)
    return value


def checker_finding_signature(
    row: dict[str, Any],
    *,
    source_index: int,
    allowed_roots: Sequence[Path],
) -> dict[str, Any]:
    """Run the real Workspace checker and return a deterministic signature."""
    try:
        item = build_items(
            [row], _workspace_mapping(), source_indices=[source_index],
        )[0]
        checker = WorkspaceArtifactInvariantChecker(allowed_roots=allowed_roots)
        violations = [
            _semantic_violation_signature(value)
            for value in checker.check(item)
        ]
        violations.sort(key=canonical_json)
        return {
            "ok": True,
            "sha256": canonical_sha256(violations),
            "count": len(violations),
            "violations": violations,
            "error": None,
        }
    except Exception as exc:  # fail closed and retain typed experiment evidence
        return {
            "ok": False,
            "sha256": None,
            "count": 0,
            "violations": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def checker_positive_control(row: Mapping[str, Any], *, source_index: int) -> dict[str, Any]:
    """Create a deterministic raw/canonical-rubric contradiction.

    Natural Full-388 currently has no deterministic invariant findings.  A
    positive-control projection is therefore needed to exercise preservation
    of non-empty finding signatures instead of reporting a vacuous equality of
    two empty lists.  The projection is applied independently, after adapter
    scoring, to both the evaluator reference and recovered row.
    """
    projected = copy.deepcopy(dict(row))
    evaluator = projected.get("evaluator")
    canonical_rubrics = (
        evaluator.get("rubrics") if isinstance(evaluator, dict) else None
    )
    if not isinstance(canonical_rubrics, list) or not canonical_rubrics:
        raise ValueError("positive control requires non-empty evaluator.rubrics")
    raw_rubrics = copy.deepcopy(canonical_rubrics)
    raw_rubrics[0] = (
        f"{raw_rubrics[0]} [adapter-positive-control-{source_index:08d}]"
    )
    projected["rubrics"] = raw_rubrics
    return projected


def mapping_sensitivity_controls(
    challenge_rows: Sequence[dict[str, Any]],
    references: Sequence[dict[str, Any]],
    spec: AdapterSpec,
) -> dict[str, Any]:
    """Verify that the scorer detects one abstention and one wrong-map control."""
    missing_paths = dict(spec.field_paths)
    missing_paths.pop("task", None)
    missing_spec = AdapterSpec(
        variant=f"{spec.variant}:missing_task_control",
        field_paths=missing_paths,
        value_codecs={
            field: copy.deepcopy(codec)
            for field, codec in spec.value_codecs.items()
            if field in missing_paths
        },
    )
    abstention_eligible = abstention_detected = 0
    for challenge, reference in zip(challenge_rows, references):
        if "task" not in reference:
            continue
        abstention_eligible += 1
        adapted = adapt_row(challenge, missing_spec)
        abstention_detected += int(
            "task" not in adapted.values and "task" not in adapted.errors
        )

    wrong_eligible = wrong_detected = 0
    persona_path = spec.field_paths.get("persona")
    task_path = spec.field_paths.get("task")
    if persona_path and task_path:
        wrong_paths = dict(spec.field_paths)
        wrong_paths["task"] = persona_path
        wrong_spec = AdapterSpec(
            variant=f"{spec.variant}:wrong_task_control",
            field_paths=wrong_paths,
            value_codecs=copy.deepcopy(spec.value_codecs),
        )
        for challenge, reference in zip(challenge_rows, references):
            if "task" not in reference or "persona" not in reference:
                continue
            if canonical_json(reference["task"]) == canonical_json(reference["persona"]):
                continue
            wrong_eligible += 1
            adapted = adapt_row(challenge, wrong_spec)
            wrong_detected += int(
                "task" in adapted.values
                and canonical_json(adapted.values["task"])
                != canonical_json(reference["task"])
            )

    return {
        "missing_task_abstention": _proportion(
            abstention_detected, abstention_eligible,
        ),
        "task_to_persona_wrong_mapping": _proportion(
            wrong_detected, wrong_eligible,
        ),
        "boundary": (
            "Controls validate scorer sensitivity only; they are not estimates "
            "of an automatic adapter's error distribution."
        ),
    }


def _wilson95(successes: int, total: int) -> list[float] | None:
    if total <= 0:
        return None
    if successes < 0 or successes > total:
        raise ValueError("invalid binomial counts")
    z = 1.959963984540054
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt(
        p * (1.0 - p) / total + z * z / (4.0 * total * total)
    ) / denominator
    low = max(0.0, centre - margin)
    high = min(1.0, centre + margin)
    if successes == 0:
        low = 0.0
    if successes == total:
        high = 1.0
    return [low, high]


def _proportion(successes: int, total: int) -> dict[str, Any]:
    return {
        "successes": successes,
        "total": total,
        "rate": successes / total if total else None,
        "wilson95": _wilson95(successes, total),
    }


def _empty_field_counts() -> dict[str, int]:
    return {
        "applicable": 0,
        "equivalent": 0,
        "abstained": 0,
        "mapping_error": 0,
        "adapter_error": 0,
    }


def _finish_field_counts(value: Mapping[str, int]) -> dict[str, Any]:
    result: dict[str, Any] = dict(value)
    applicable = int(value["applicable"])
    equivalent = int(value["equivalent"])
    result["equivalence_rate"] = equivalent / applicable if applicable else None
    result["equivalence_wilson95"] = _wilson95(equivalent, applicable)
    result["status"] = "measured" if applicable else "not_present_in_reference"
    return result


def evaluate_variant(
    challenge_rows: Sequence[dict[str, Any]],
    references: Sequence[dict[str, Any]],
    spec: AdapterSpec,
    *,
    allowed_roots: Sequence[Path] = (),
    workers: int = 1,
) -> dict[str, Any]:
    """Score one supplied AdapterSpec against evaluator-only references."""
    if len(challenge_rows) != len(references):
        raise ValueError("challenge/reference length mismatch")
    if not challenge_rows:
        raise ValueError("cannot evaluate an empty adapter challenge")

    adaptations = [adapt_row(row, spec) for row in challenge_rows]
    all_fields = sorted(set().union(*(row.keys() for row in references)))
    field_counts = {field: _empty_field_counts() for field in all_fields}
    for field in (*CORE_FIELDS, *WORKSPACE_EXTENSION_FIELDS):
        field_counts.setdefault(field, _empty_field_counts())

    row_equivalent = 0
    rows_with_abstention = 0
    rows_with_mapping_error = 0
    rows_with_adapter_error = 0
    unexpected_output_fields = 0
    row_diagnostics: list[dict[str, Any]] = []
    row_equivalence_failure_indices: list[int] = []
    recovered_rows: list[dict[str, Any]] = []

    for index, (adaptation, reference) in enumerate(zip(adaptations, references)):
        recovered = copy.deepcopy(adaptation.values)
        recovered_rows.append(recovered)
        absent: list[str] = []
        wrong: list[str] = []
        adapter_errors: list[str] = []
        for field, expected in reference.items():
            counts = field_counts.setdefault(field, _empty_field_counts())
            counts["applicable"] += 1
            if field in adaptation.errors:
                counts["adapter_error"] += 1
                adapter_errors.append(field)
            elif field not in recovered:
                counts["abstained"] += 1
                absent.append(field)
            elif canonical_json(recovered[field]) != canonical_json(expected):
                counts["mapping_error"] += 1
                wrong.append(field)
            else:
                counts["equivalent"] += 1
        unexpected = sorted(set(recovered) - set(reference))
        unexpected_output_fields += len(unexpected)
        exact = canonical_json(recovered) == canonical_json(reference)
        row_equivalent += int(exact)
        if not exact:
            row_equivalence_failure_indices.append(index)
        rows_with_abstention += int(bool(absent))
        rows_with_mapping_error += int(bool(wrong or unexpected))
        rows_with_adapter_error += int(bool(adapter_errors))
        if not exact and len(row_diagnostics) < 20:
            row_diagnostics.append({
                "row_index": index,
                "reference_sha256": canonical_sha256(reference),
                "recovered_sha256": canonical_sha256(recovered),
                "abstained_fields": absent,
                "mapping_error_fields": wrong,
                "adapter_error_fields": adapter_errors,
                "unexpected_output_fields": unexpected,
                "declared_path_abstentions": adaptation.abstentions,
                "adapter_errors": adaptation.errors,
            })

    roots = tuple(Path(value).expanduser().resolve() for value in allowed_roots)
    worker_count = max(1, int(workers))

    def signature_call(payload: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        index, row = payload
        return checker_finding_signature(
            row, source_index=index, allowed_roots=roots,
        )

    def positive_signature_call(payload: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        index, row = payload
        try:
            projected = checker_positive_control(row, source_index=index)
        except Exception as exc:
            return {
                "ok": False,
                "sha256": None,
                "count": 0,
                "violations": [],
                "error": f"positive_control:{type(exc).__name__}: {exc}",
            }
        return checker_finding_signature(
            projected, source_index=index, allowed_roots=roots,
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        baseline_signatures = list(executor.map(
            signature_call, enumerate(references),
        ))
        adapted_signatures = list(executor.map(
            signature_call, enumerate(recovered_rows),
        ))
        positive_baseline_signatures = list(executor.map(
            positive_signature_call, enumerate(references),
        ))
        positive_adapted_signatures = list(executor.map(
            positive_signature_call, enumerate(recovered_rows),
        ))

    finding_invariant = 0
    checker_errors = 0
    false_invariance_non_equivalent = 0
    finding_mismatches: list[dict[str, Any]] = []
    finding_failure_indices: list[int] = []
    baseline_finding_count = adapted_finding_count = 0
    for index, (baseline, adapted, reference, recovered) in enumerate(zip(
        baseline_signatures, adapted_signatures, references, recovered_rows,
    )):
        baseline_finding_count += int(baseline["count"])
        adapted_finding_count += int(adapted["count"])
        both_ok = bool(baseline["ok"] and adapted["ok"])
        invariant = both_ok and baseline["sha256"] == adapted["sha256"]
        finding_invariant += int(invariant)
        checker_errors += int(not both_ok)
        row_exact = canonical_json(reference) == canonical_json(recovered)
        false_invariance_non_equivalent += int(invariant and not row_exact)
        if not invariant:
            finding_failure_indices.append(index)
        if not invariant and len(finding_mismatches) < 20:
            finding_mismatches.append({
                "row_index": index,
                "baseline_sha256": baseline["sha256"],
                "adapted_sha256": adapted["sha256"],
                "baseline_count": baseline["count"],
                "adapted_count": adapted["count"],
                "baseline_error": baseline["error"],
                "adapted_error": adapted["error"],
            })

    positive_invariant = 0
    positive_checker_errors = 0
    positive_rows_without_finding = 0
    positive_baseline_finding_count = positive_adapted_finding_count = 0
    positive_failure_indices: list[int] = []
    positive_mismatches: list[dict[str, Any]] = []
    for index, (baseline, adapted) in enumerate(zip(
        positive_baseline_signatures, positive_adapted_signatures,
    )):
        positive_baseline_finding_count += int(baseline["count"])
        positive_adapted_finding_count += int(adapted["count"])
        both_ok = bool(baseline["ok"] and adapted["ok"])
        nonempty = int(baseline["count"]) > 0 and int(adapted["count"]) > 0
        invariant = both_ok and nonempty and baseline["sha256"] == adapted["sha256"]
        positive_invariant += int(invariant)
        positive_checker_errors += int(not both_ok)
        positive_rows_without_finding += int(both_ok and not nonempty)
        if not invariant:
            positive_failure_indices.append(index)
            if len(positive_mismatches) < 20:
                positive_mismatches.append({
                    "row_index": index,
                    "baseline_sha256": baseline["sha256"],
                    "adapted_sha256": adapted["sha256"],
                    "baseline_count": baseline["count"],
                    "adapted_count": adapted["count"],
                    "baseline_error": baseline["error"],
                    "adapted_error": adapted["error"],
                })

    completed_fields = {
        field: _finish_field_counts(counts)
        for field, counts in sorted(field_counts.items())
    }

    def group_metrics(fields: Sequence[str]) -> dict[str, Any]:
        applicable = sum(completed_fields[field]["applicable"] for field in fields)
        equivalent = sum(completed_fields[field]["equivalent"] for field in fields)
        return {
            "fields": {field: completed_fields[field] for field in fields},
            "micro_equivalence": _proportion(equivalent, applicable),
            "abstained": sum(completed_fields[field]["abstained"] for field in fields),
            "mapping_errors": sum(
                completed_fields[field]["mapping_error"] for field in fields
            ),
            "adapter_errors": sum(
                completed_fields[field]["adapter_error"] for field in fields
            ),
        }

    total = len(references)
    return {
        "variant": spec.variant,
        "rows": total,
        "adapter_spec_sha256": canonical_sha256(spec.to_dict()),
        "adapter_spec_fields": len(spec.field_paths),
        "duplicate_declared_paths": (
            len(spec.field_paths) - len(set(spec.field_paths.values()))
        ),
        "core_fields": group_metrics(CORE_FIELDS),
        "workspace_extension_fields": group_metrics(WORKSPACE_EXTENSION_FIELDS),
        "all_source_fields": {
            "fields": {field: completed_fields[field] for field in all_fields},
            "micro_equivalence": _proportion(
                sum(completed_fields[field]["equivalent"] for field in all_fields),
                sum(completed_fields[field]["applicable"] for field in all_fields),
            ),
        },
        "row_equivalence": _proportion(row_equivalent, total),
        "row_equivalence_failure_indices": row_equivalence_failure_indices,
        "rows_with_abstention": rows_with_abstention,
        "rows_with_mapping_error": rows_with_mapping_error,
        "rows_with_adapter_error": rows_with_adapter_error,
        "unexpected_output_fields": unexpected_output_fields,
        "row_mismatch_preview": row_diagnostics,
        "workspace_finding_signature_invariance": _proportion(
            finding_invariant, total,
        ),
        "workspace_finding_signature_failure_indices": finding_failure_indices,
        "checker_errors": checker_errors,
        "baseline_finding_count": baseline_finding_count,
        "adapted_finding_count": adapted_finding_count,
        "false_invariance_on_non_equivalent_rows": false_invariance_non_equivalent,
        "finding_mismatch_preview": finding_mismatches,
        "workspace_positive_control_finding_signature_invariance": _proportion(
            positive_invariant, total,
        ),
        "workspace_positive_control_failure_indices": positive_failure_indices,
        "positive_control_checker_errors": positive_checker_errors,
        "positive_control_rows_without_finding": positive_rows_without_finding,
        "positive_control_baseline_finding_count": positive_baseline_finding_count,
        "positive_control_adapted_finding_count": positive_adapted_finding_count,
        "positive_control_mismatch_preview": positive_mismatches,
        "scorer_sensitivity_controls": mapping_sensitivity_controls(
            challenge_rows, references, spec,
        ),
    }


def evaluate_manifest(
    out_dir: Path,
    *,
    allowed_roots: Sequence[Path],
    workers: int,
) -> dict[str, Any]:
    implementation_start = implementation_manifest()
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("unsupported adapter challenge manifest")
    started = time.monotonic()
    variants: list[dict[str, Any]] = []
    for entry in manifest.get("variants", []):
        if not isinstance(entry, dict):
            raise ValueError("manifest variant entries must be objects")
        challenge_path = _resolve_within(out_dir, str(entry.get("challenge") or ""))
        sidecar_path = _resolve_within(
            out_dir, str(entry.get("reference_sidecar") or ""),
        )
        spec_path = _resolve_within(out_dir, str(entry.get("adapter_spec") or ""))
        expected_hashes = {
            challenge_path: entry.get("challenge_sha256"),
            sidecar_path: entry.get("reference_sidecar_sha256"),
            spec_path: entry.get("adapter_spec_sha256"),
        }
        for path, expected in expected_hashes.items():
            if not path.is_file() or file_sha256(path) != expected:
                raise ValueError(f"manifest-bound artifact changed: {path}")
        challenge, references, spec = load_variant_bundle(
            challenge_path, sidecar_path, spec_path,
        )
        variants.append(evaluate_variant(
            challenge,
            references,
            spec,
            allowed_roots=allowed_roots,
            workers=workers,
        ))
    implementation_end = implementation_manifest()
    if implementation_start["sha256"] != implementation_end["sha256"]:
        raise RuntimeError("adapter implementation changed during evaluation")
    result = _finish_experiment_result(
        variants,
        source_manifest_sha256=file_sha256(manifest_path),
        allowed_roots=allowed_roots,
        workers=workers,
        elapsed_seconds=time.monotonic() - started,
    )
    result["implementation_hash_end_check"] = {
        "passed": True,
        "expected": implementation_start["sha256"],
        "observed": implementation_end["sha256"],
    }
    _write_json(out_dir / "results.json", result)
    _atomic_write(out_dir / "results.md", render_markdown(result))
    return result


def evaluate_explicit_bundle(
    challenge_path: Path,
    sidecar_path: Path,
    spec_path: Path,
    *,
    allowed_roots: Sequence[Path],
    workers: int,
) -> dict[str, Any]:
    implementation_start = implementation_manifest()
    started = time.monotonic()
    challenge, references, spec = load_variant_bundle(
        challenge_path, sidecar_path, spec_path,
    )
    variant = evaluate_variant(
        challenge,
        references,
        spec,
        allowed_roots=allowed_roots,
        workers=workers,
    )
    implementation_end = implementation_manifest()
    if implementation_start["sha256"] != implementation_end["sha256"]:
        raise RuntimeError("adapter implementation changed during evaluation")
    result = _finish_experiment_result(
        [variant],
        source_manifest_sha256=None,
        allowed_roots=allowed_roots,
        workers=workers,
        elapsed_seconds=time.monotonic() - started,
    )
    result["implementation_hash_end_check"] = {
        "passed": True,
        "expected": implementation_start["sha256"],
        "observed": implementation_end["sha256"],
    }
    return result


def _finish_experiment_result(
    variants: Sequence[dict[str, Any]],
    *,
    source_manifest_sha256: str | None,
    allowed_roots: Sequence[Path],
    workers: int,
    elapsed_seconds: float,
) -> dict[str, Any]:
    if not variants:
        raise ValueError("adapter result requires at least one evaluated variant")
    rows = sum(int(row["rows"]) for row in variants)
    row_successes = sum(
        int(row["row_equivalence"]["successes"]) for row in variants
    )
    finding_successes = sum(
        int(row["workspace_finding_signature_invariance"]["successes"])
        for row in variants
    )
    positive_finding_successes = sum(
        int(row["workspace_positive_control_finding_signature_invariance"]["successes"])
        for row in variants
    )
    core_total = sum(
        int(row["core_fields"]["micro_equivalence"]["total"])
        for row in variants
    )
    core_success = sum(
        int(row["core_fields"]["micro_equivalence"]["successes"])
        for row in variants
    )
    workspace_total = sum(
        int(row["workspace_extension_fields"]["micro_equivalence"]["total"])
        for row in variants
    )
    workspace_success = sum(
        int(row["workspace_extension_fields"]["micro_equivalence"]["successes"])
        for row in variants
    )
    aligned_source_rows = (
        int(variants[0]["rows"])
        if variants and len({int(row["rows"]) for row in variants}) == 1
        else 0
    )
    row_cluster_failures = {
        int(index)
        for row in variants
        for index in row["row_equivalence_failure_indices"]
    }
    finding_cluster_failures = {
        int(index)
        for row in variants
        for index in row["workspace_finding_signature_failure_indices"]
    }
    positive_cluster_failures = {
        int(index)
        for row in variants
        for index in row["workspace_positive_control_failure_indices"]
    }
    abstention_control_success = sum(
        int(row["scorer_sensitivity_controls"]["missing_task_abstention"]["successes"])
        for row in variants
    )
    abstention_control_total = sum(
        int(row["scorer_sensitivity_controls"]["missing_task_abstention"]["total"])
        for row in variants
    )
    wrong_control_success = sum(
        int(row["scorer_sensitivity_controls"]["task_to_persona_wrong_mapping"]["successes"])
        for row in variants
    )
    wrong_control_total = sum(
        int(row["scorer_sensitivity_controls"]["task_to_persona_wrong_mapping"]["total"])
        for row in variants
    )
    return {
        "schema_version": RESULT_SCHEMA,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_type": "given_adapter_spec_conformance",
        "source_manifest_sha256": source_manifest_sha256,
        "workers": max(1, int(workers)),
        "allowed_input_roots": [
            str(Path(value).expanduser().resolve()) for value in allowed_roots
        ],
        "elapsed_seconds": round(elapsed_seconds, 6),
        "variants": list(variants),
        "aggregate": {
            "variant_count": len(variants),
            "row_decisions": rows,
            "core_field_equivalence": _proportion(core_success, core_total),
            "workspace_extension_field_equivalence": _proportion(
                workspace_success, workspace_total,
            ),
            "row_equivalence": _proportion(row_successes, rows),
            "workspace_finding_signature_invariance": _proportion(
                finding_successes, rows,
            ),
            "workspace_positive_control_finding_signature_invariance": _proportion(
                positive_finding_successes, rows,
            ),
            "source_cluster_all_variants_row_equivalence": _proportion(
                aligned_source_rows - len(row_cluster_failures), aligned_source_rows,
            ),
            "source_cluster_all_variants_finding_invariance": _proportion(
                aligned_source_rows - len(finding_cluster_failures), aligned_source_rows,
            ),
            "source_cluster_all_variants_positive_control_invariance": _proportion(
                aligned_source_rows - len(positive_cluster_failures), aligned_source_rows,
            ),
            "scorer_abstention_control_detection": _proportion(
                abstention_control_success, abstention_control_total,
            ),
            "scorer_wrong_mapping_control_detection": _proportion(
                wrong_control_success, wrong_control_total,
            ),
            "rows_with_abstention": sum(
                int(row["rows_with_abstention"]) for row in variants
            ),
            "rows_with_mapping_error": sum(
                int(row["rows_with_mapping_error"]) for row in variants
            ),
            "rows_with_adapter_error": sum(
                int(row["rows_with_adapter_error"]) for row in variants
            ),
            "checker_errors": sum(int(row["checker_errors"]) for row in variants),
            "positive_control_checker_errors": sum(
                int(row["positive_control_checker_errors"]) for row in variants
            ),
            "positive_control_rows_without_finding": sum(
                int(row["positive_control_rows_without_finding"])
                for row in variants
            ),
            "positive_control_baseline_finding_count": sum(
                int(row["positive_control_baseline_finding_count"])
                for row in variants
            ),
            "positive_control_adapted_finding_count": sum(
                int(row["positive_control_adapted_finding_count"])
                for row in variants
            ),
            "false_invariance_on_non_equivalent_rows": sum(
                int(row["false_invariance_on_non_equivalent_rows"])
                for row in variants
            ),
        },
        "implementation": implementation_manifest(),
        "interpretation_boundary": [
            "The supplied AdapterSpecs are gold mappings generated outside challenge rows.",
            "These metrics validate adapter execution, not blind mapping discovery.",
            "The three schemas are controlled transformations of one benchmark export.",
            "Finding invariance covers WorkspaceArtifactInvariantChecker only.",
            "The natural Full-388 finding set is reported separately from a non-empty rubric-divergence positive control.",
            "Transformed-row Wilson intervals do not model dependence across variants; source-cluster all-variant metrics are the conservative companion estimate.",
        ],
    }


def _resolve_within(root: Path, relative: str) -> Path:
    if not relative:
        raise ValueError("manifest artifact path is empty")
    root = root.expanduser().resolve()
    path = (root / relative).resolve()
    if path != root and not path.is_relative_to(root):
        raise ValueError(f"manifest artifact escapes output directory: {relative!r}")
    return path


def _metric_text(value: Mapping[str, Any]) -> str:
    rate = value.get("rate")
    if rate is None:
        return "N/A"
    return f"{value['successes']}/{value['total']} ({rate:.3f})"


def render_markdown(result: Mapping[str, Any]) -> str:
    aggregate = result["aggregate"]
    lines = [
        "# WorkspaceBench opaque-schema adapter experiment",
        "",
        f"- Experiment: `{result['experiment_type']}`",
        f"- Variants: `{aggregate['variant_count']}`",
        f"- Transformed row decisions: `{aggregate['row_decisions']}`",
        f"- Elapsed seconds: `{result['elapsed_seconds']}`",
        "",
        "## Results",
        "",
        "| Variant | Rows | Core fields | Workspace fields | Exact rows | Natural signatures | Positive-control signatures | Abstain rows | Wrong-map rows |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["variants"]:
        lines.append(
            f"| `{row['variant']}` | {row['rows']} | "
            f"{_metric_text(row['core_fields']['micro_equivalence'])} | "
            f"{_metric_text(row['workspace_extension_fields']['micro_equivalence'])} | "
            f"{_metric_text(row['row_equivalence'])} | "
            f"{_metric_text(row['workspace_finding_signature_invariance'])} | "
            f"{_metric_text(row['workspace_positive_control_finding_signature_invariance'])} | "
            f"{row['rows_with_abstention']} | {row['rows_with_mapping_error']} |"
        )
    lines.extend([
        "",
        "## Aggregate",
        "",
        f"- Core-field equivalence: `{_metric_text(aggregate['core_field_equivalence'])}`",
        f"- Workspace-extension equivalence: `{_metric_text(aggregate['workspace_extension_field_equivalence'])}`",
        f"- Exact canonical rows: `{_metric_text(aggregate['row_equivalence'])}`",
        f"- Workspace finding-signature invariance: `{_metric_text(aggregate['workspace_finding_signature_invariance'])}`",
        f"- Non-empty positive-control signature invariance: `{_metric_text(aggregate['workspace_positive_control_finding_signature_invariance'])}`",
        f"- Source-cluster all-variant row equivalence: `{_metric_text(aggregate['source_cluster_all_variants_row_equivalence'])}`",
        f"- Source-cluster all-variant positive-control invariance: `{_metric_text(aggregate['source_cluster_all_variants_positive_control_invariance'])}`",
        f"- Abstention-control detection: `{_metric_text(aggregate['scorer_abstention_control_detection'])}`",
        f"- Wrong-mapping-control detection: `{_metric_text(aggregate['scorer_wrong_mapping_control_detection'])}`",
        f"- Rows with abstention: `{aggregate['rows_with_abstention']}`",
        f"- Rows with wrong mappings: `{aggregate['rows_with_mapping_error']}`",
        f"- Adapter execution errors: `{aggregate['rows_with_adapter_error']}`",
        f"- Checker execution errors: `{aggregate['checker_errors']}`",
        f"- Positive-control findings (reference/adapted): `{aggregate['positive_control_baseline_finding_count']}/{aggregate['positive_control_adapted_finding_count']}`",
        "",
        "## Interpretation boundary",
        "",
    ])
    lines.extend(f"- {line}" for line in result["interpretation_boundary"])
    lines.append("")
    return "\n".join(lines)


def implementation_manifest() -> dict[str, Any]:
    paths = [
        REPO / "scripts" / "build_or_run_workspace_adapter_experiment.py",
        REPO / "benchcore" / "loader.py",
        REPO / "benchcore" / "schema.py",
        REPO / "benchcore" / "workspace_invariants.py",
        REPO / "benchcore" / "promotion.py",
    ]
    files = {
        path.relative_to(REPO).as_posix(): file_sha256(path)
        for path in paths if path.is_file()
    }
    return {
        "schema_version": "workspace-adapter-implementation-manifest-v1",
        "files": files,
        "sha256": canonical_sha256(files),
        "git": _git_metadata(),
    }


def _git_metadata() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def _strict_passed(result: Mapping[str, Any]) -> bool:
    aggregate = result["aggregate"]
    required = (
        aggregate["core_field_equivalence"],
        aggregate["workspace_extension_field_equivalence"],
        aggregate["row_equivalence"],
        aggregate["workspace_finding_signature_invariance"],
        aggregate["workspace_positive_control_finding_signature_invariance"],
        aggregate["source_cluster_all_variants_row_equivalence"],
        aggregate["source_cluster_all_variants_positive_control_invariance"],
        aggregate["scorer_abstention_control_detection"],
        aggregate["scorer_wrong_mapping_control_detection"],
    )
    return (
        all(value.get("rate") == 1.0 for value in required)
        and aggregate["rows_with_abstention"] == 0
        and aggregate["rows_with_mapping_error"] == 0
        and aggregate["rows_with_adapter_error"] == 0
        and aggregate["checker_errors"] == 0
        and aggregate["positive_control_checker_errors"] == 0
        and aggregate["positive_control_rows_without_finding"] == 0
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("build", "run", "both"), default="both")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument(
        "--variant", action="append", choices=VARIANTS,
        help="Repeat to select variants; default: all three",
    )
    parser.add_argument("--expected-rows", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--allow-input-root", type=Path, action="append", default=[])
    parser.add_argument("--challenge", type=Path)
    parser.add_argument("--reference-sidecar", type=Path)
    parser.add_argument("--adapter-spec", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir.expanduser().resolve()
    dataset = args.dataset.expanduser().resolve()
    explicit_bundle = (args.challenge, args.reference_sidecar, args.adapter_spec)
    if any(explicit_bundle) and not all(explicit_bundle):
        raise ValueError(
            "--challenge, --reference-sidecar and --adapter-spec must be supplied together"
        )
    if any(explicit_bundle) and args.mode != "run":
        raise ValueError("explicit adapter bundles are supported only with --mode run")

    if args.mode in {"build", "both"}:
        if not dataset.is_file():
            raise FileNotFoundError(dataset)
        rows = load_rows(dataset)
        expected_rows = args.expected_rows
        if expected_rows is None and dataset == DEFAULT_DATASET.resolve():
            expected_rows = 388
        if expected_rows is not None and len(rows) != expected_rows:
            raise ValueError(
                f"expected {expected_rows} source rows, observed {len(rows)}"
            )
        manifest = build_experiment_artifacts(
            rows,
            out_dir,
            seed=args.seed,
            variants=tuple(args.variant or VARIANTS),
            source_dataset=dataset,
        )
        print(
            f"Built {len(manifest['variants'])} opaque schemas from "
            f"{manifest['source_rows']} source rows at {out_dir}",
            flush=True,
        )
        if args.mode == "build":
            return 0

    roots = [path.expanduser().resolve() for path in args.allow_input_root]
    if not roots and dataset.is_file() and file_sha256(dataset) == PINNED_FULL_SHA256:
        if DEFAULT_FULL_ROOT.is_dir():
            roots = [DEFAULT_FULL_ROOT.resolve()]
    if all(explicit_bundle):
        result = evaluate_explicit_bundle(
            args.challenge.expanduser().resolve(),
            args.reference_sidecar.expanduser().resolve(),
            args.adapter_spec.expanduser().resolve(),
            allowed_roots=roots,
            workers=max(1, args.workers),
        )
        _write_json(out_dir / "results.json", result)
        _atomic_write(out_dir / "results.md", render_markdown(result))
    else:
        result = evaluate_manifest(
            out_dir,
            allowed_roots=roots,
            workers=max(1, args.workers),
        )
    aggregate = result["aggregate"]
    print(
        "Adapter experiment: "
        f"rows={aggregate['row_equivalence']['successes']}/"
        f"{aggregate['row_equivalence']['total']} "
        f"workspace_findings={aggregate['workspace_finding_signature_invariance']['successes']}/"
        f"{aggregate['workspace_finding_signature_invariance']['total']} "
        f"abstain={aggregate['rows_with_abstention']} "
        f"wrong={aggregate['rows_with_mapping_error']} "
        f"errors={aggregate['rows_with_adapter_error']}",
        flush=True,
    )
    print(f"Wrote {out_dir}", flush=True)
    if args.strict and not _strict_passed(result):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
