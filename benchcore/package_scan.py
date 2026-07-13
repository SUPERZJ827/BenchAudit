from __future__ import annotations

import hashlib
import mimetypes
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from .schema import BenchmarkItem


SCHEMA_VERSION = "1.0"


class ArtifactKind(str, Enum):
    TASK_SPECIFICATION = "task_specification"
    CONTEXT = "context_attachment"
    ENVIRONMENT = "environment_initial_state"
    TOOL_PROTOCOL = "tool_action_space"
    INTERACTION_PROTOCOL = "interaction_protocol"
    OUTPUT_CONTRACT = "expected_output"
    ORACLE = "oracle_ground_truth"
    EVALUATOR = "evaluator_tests_rubric"
    TRACE = "trace_evidence"
    PROVENANCE = "provenance_versioning"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PackageArtifact:
    artifact_id: str
    kind: ArtifactKind
    relative_path: str
    media_type: str
    size_bytes: int
    sha256: str
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArtifactEdge:
    source_id: str
    target_id: str
    relation: str
    evidence: str


@dataclass
class BenchmarkPackage:
    root: str
    schema_version: str = SCHEMA_VERSION
    artifacts: list[PackageArtifact] = field(default_factory=list)
    edges: list[ArtifactEdge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    scan_metadata: dict[str, Any] = field(default_factory=dict)

    def kinds(self) -> set[ArtifactKind]:
        return {artifact.kind for artifact in self.artifacts}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "root": self.root,
            "artifacts": [
                {**asdict(artifact), "kind": artifact.kind.value}
                for artifact in self.artifacts
            ],
            "edges": [asdict(edge) for edge in self.edges],
            "warnings": list(self.warnings),
            "truncated": self.truncated,
            "scan_metadata": dict(self.scan_metadata),
        }


DEFAULT_IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "__pycache__", "node_modules", ".tox", ".venv", "venv", "dist", "build",
})

DATA_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv", ".parquet", ".arrow"}
CONTEXT_SUFFIXES = {
    ".txt", ".md", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".pptx",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".wav", ".mp3", ".mp4",
    ".sqlite", ".db", ".sql",
}
TRACE_TOKENS = {"trace", "trajectory", "attempt", "transcript", "stdout", "stderr", "run_log"}
ORACLE_TOKENS = {"gold", "reference", "answer", "solution", "target", "expected"}
EVALUATOR_TOKENS = {"test", "tests", "eval", "evaluator", "grader", "rubric", "checker", "metric"}
TASK_TOKENS = {"task", "tasks", "question", "questions", "prompt", "prompts", "instruction"}
OUTPUT_TOKENS = {"output", "submission", "deliverable", "answer_contract"}
PROVENANCE_NAMES = {
    "readme", "license", "citation", "dataset_card", "datasheet", "changelog",
    "pyproject.toml", "requirements.txt", "poetry.lock", "uv.lock", "package-lock.json",
}
ENVIRONMENT_NAMES = {
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "environment.yml", "environment.yaml", "conda.yml", "conda.yaml", "vagrantfile",
}


def scan_benchmark_package(
    source: Path,
    *,
    max_files: int = 10_000,
    max_file_bytes: int = 512 * 1024 * 1024,
    ignored_dirs: Iterable[str] = DEFAULT_IGNORED_DIRS,
) -> BenchmarkPackage:
    source = source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if max_files <= 0:
        raise ValueError("max_files must be positive")
    root = source if source.is_dir() else source.parent
    package = BenchmarkPackage(root=str(root))
    ignored = set(ignored_dirs)
    candidates = [source] if source.is_file() else _iter_files(source, ignored)
    skipped_large = 0
    for index, path in enumerate(candidates):
        if index >= max_files:
            package.truncated = True
            package.warnings.append(f"scan stopped after max_files={max_files}")
            break
        try:
            stat = path.stat()
        except OSError as exc:
            package.warnings.append(f"cannot stat {path}: {exc}")
            continue
        relative = path.relative_to(root).as_posix()
        kind, roles = classify_artifact(path, relative)
        if stat.st_size > max_file_bytes:
            skipped_large += 1
            package.warnings.append(
                f"skipped hashing oversized file {path.relative_to(root)} ({stat.st_size} bytes)"
            )
            identity = hashlib.sha256(f"{relative}\0unhashed\0{stat.st_size}".encode("utf-8")).hexdigest()
            package.artifacts.append(PackageArtifact(
                artifact_id=f"artifact:{identity[:16]}",
                kind=kind,
                relative_path=relative,
                media_type=media_type(path),
                size_bytes=stat.st_size,
                sha256="",
                roles=(*roles, "unhashed_oversized"),
            ))
            continue
        try:
            digest = sha256_file(path)
        except OSError as exc:
            package.warnings.append(f"cannot read {relative}: {exc}")
            continue
        identity = hashlib.sha256(f"{relative}\0{digest}".encode("utf-8")).hexdigest()
        package.artifacts.append(PackageArtifact(
            artifact_id=f"artifact:{identity[:16]}",
            kind=kind,
            relative_path=relative,
            media_type=media_type(path),
            size_bytes=stat.st_size,
            sha256=digest,
            roles=roles,
        ))
    package.artifacts.sort(key=lambda artifact: artifact.relative_path)
    package.edges = infer_artifact_edges(package.artifacts)
    package.scan_metadata = {
        "files_scanned": len(package.artifacts),
        "files_skipped_large": skipped_large,
        "max_files": max_files,
        "max_file_bytes": max_file_bytes,
        "ignored_directories": sorted(ignored),
    }
    return package


def add_canonical_item_artifacts(
    package: BenchmarkPackage,
    items: Iterable[BenchmarkItem],
) -> BenchmarkPackage:
    """Add virtual artifact nodes for fields embedded inside dataset records."""
    items = list(items)
    field_presence = {
        ArtifactKind.TASK_SPECIFICATION: any(item.task not in (None, "") for item in items),
        ArtifactKind.CONTEXT: any(bool(item.context) for item in items),
        ArtifactKind.OUTPUT_CONTRACT: any(item.output_contract not in (None, "", {}) for item in items),
        ArtifactKind.ORACLE: any(item.gold not in (None, "") for item in items),
        ArtifactKind.EVALUATOR: any(item.evaluator not in (None, "", {}) for item in items),
        ArtifactKind.TRACE: any(
            any(key in item.raw for key in ("trace", "trajectory", "attempt", "transcript"))
            for item in items
        ),
        ArtifactKind.PROVENANCE: any(
            any(key in item.metadata for key in ("source", "version", "split", "date", "commit"))
            for item in items
        ),
    }
    existing_kinds = package.kinds()
    for kind, present in field_presence.items():
        if not present or kind in existing_kinds:
            continue
        digest = hashlib.sha256(f"canonical:{kind.value}:{len(items)}".encode("utf-8")).hexdigest()
        package.artifacts.append(PackageArtifact(
            artifact_id=f"virtual:{digest[:16]}",
            kind=kind,
            relative_path=f"@canonical/{kind.value}",
            media_type="application/x-benchcore-canonical",
            size_bytes=0,
            sha256=digest,
            roles=("embedded_record_field",),
        ))
    package.artifacts.sort(key=lambda artifact: artifact.relative_path)
    package.edges = infer_artifact_edges(package.artifacts)
    return package


def _iter_files(root: Path, ignored: set[str]) -> Iterable[Path]:
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames[:] = sorted(
            name for name in dirnames
            if name not in ignored and not (Path(directory) / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if path.is_symlink() or not path.is_file():
                continue
            yield path


def classify_artifact(path: Path, relative_path: str | None = None) -> tuple[ArtifactKind, tuple[str, ...]]:
    relative = (relative_path or path.name).lower()
    name = path.name.lower()
    stem_tokens = set(_tokens(relative))
    suffix = path.suffix.lower()
    roles: list[str] = []

    if name in ENVIRONMENT_NAMES or name.startswith("dockerfile"):
        return ArtifactKind.ENVIRONMENT, ("environment_definition",)
    if name in PROVENANCE_NAMES or path.stem.lower() in PROVENANCE_NAMES:
        return ArtifactKind.PROVENANCE, ("documentation",)
    if stem_tokens & TRACE_TOKENS:
        return ArtifactKind.TRACE, ("attempt_or_trace",)
    if _is_test_path(relative) or stem_tokens & EVALUATOR_TOKENS:
        return ArtifactKind.EVALUATOR, ("test_or_evaluator",)
    if stem_tokens & ORACLE_TOKENS:
        return ArtifactKind.ORACLE, ("reference_or_gold",)
    if stem_tokens & OUTPUT_TOKENS:
        return ArtifactKind.OUTPUT_CONTRACT, ("output_contract",)
    if stem_tokens & TASK_TOKENS or suffix in DATA_SUFFIXES:
        roles.append("dataset_or_task_records" if suffix in DATA_SUFFIXES else "task_specification")
        return ArtifactKind.TASK_SPECIFICATION, tuple(roles)
    if suffix in {".sh", ".ps1", ".bat"}:
        return ArtifactKind.TOOL_PROTOCOL, ("command_or_tool_protocol",)
    if suffix in CONTEXT_SUFFIXES:
        return ArtifactKind.CONTEXT, ("input_or_attachment",)
    return ArtifactKind.UNKNOWN, ()


def infer_artifact_edges(artifacts: list[PackageArtifact]) -> list[ArtifactEdge]:
    edges: list[ArtifactEdge] = []
    task_artifacts = [a for a in artifacts if a.kind == ArtifactKind.TASK_SPECIFICATION]
    for artifact in artifacts:
        if artifact.kind == ArtifactKind.EVALUATOR:
            for task in _nearest_by_directory(artifact, task_artifacts):
                edges.append(ArtifactEdge(
                    source_id=artifact.artifact_id,
                    target_id=task.artifact_id,
                    relation="evaluates",
                    evidence="directory_and_role_heuristic",
                ))
        elif artifact.kind == ArtifactKind.ORACLE:
            for task in _nearest_by_directory(artifact, task_artifacts):
                edges.append(ArtifactEdge(
                    source_id=artifact.artifact_id,
                    target_id=task.artifact_id,
                    relation="answers_or_references",
                    evidence="directory_and_role_heuristic",
                ))
    return edges


def _nearest_by_directory(source: PackageArtifact, candidates: list[PackageArtifact]) -> list[PackageArtifact]:
    if not candidates:
        return []
    source_parent = Path(source.relative_path).parent
    ranked = sorted(
        candidates,
        key=lambda candidate: _directory_distance(source_parent, Path(candidate.relative_path).parent),
    )
    best_distance = _directory_distance(source_parent, Path(ranked[0].relative_path).parent)
    return [
        candidate for candidate in ranked
        if _directory_distance(source_parent, Path(candidate.relative_path).parent) == best_distance
    ][:3]


def _directory_distance(left: Path, right: Path) -> int:
    left_parts, right_parts = left.parts, right.parts
    shared = 0
    for a, b in zip(left_parts, right_parts):
        if a != b:
            break
        shared += 1
    return (len(left_parts) - shared) + (len(right_parts) - shared)


def _tokens(value: str) -> list[str]:
    normalized = value.replace("-", "_").replace(".", "_").replace("/", "_")
    return [token for token in normalized.split("_") if token]


def _is_test_path(relative: str) -> bool:
    parts = set(Path(relative).parts)
    name = Path(relative).name
    return "tests" in parts or "test" in parts or name.startswith("test_") or name.endswith("_test.py")


def media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
