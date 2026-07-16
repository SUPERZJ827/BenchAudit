"""Budgeted, fail-closed attachment extraction for benchmark auditing.

Untrusted attachments are part of the benchmark attack surface.  This module
therefore separates two parser classes:

* plain text and OOXML (xlsx/docx/pptx) use small, bounded readers implemented
  here; ZIP metadata and every decompressed byte are budgeted before text is
  exposed;
* formats requiring complex native parsers or external converters (PDF, legacy
  Office, OCR) are refused by default and can run only through an explicitly
  supplied isolated ``ContainerRunner``.  Unsafe local execution needs a
  separate acknowledgement.

The compatibility functions ``read_file`` and ``search_file`` still return the
historical string/dict shapes, but failures now carry an explicit status.  New
code can use ``read_file_result`` for typed coverage decisions.
"""
from __future__ import annotations

import codecs
import hashlib
import html
import json
import os
import re
import stat
import sys
import tempfile
import threading
import time
import zipfile
from collections import OrderedDict, namedtuple
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Sequence

from .execution import (
    CommandRunner,
    CommandSpec,
    ContainerRunner,
    ExecutionPolicy,
    ExecutionRefused,
    LocalProcessRunner,
)


PARSER_IMPLEMENTATION_VERSION = "benchcore-file-reader/3.0"
_CACHE_CAPACITY = 256


@dataclass(frozen=True)
class FileReadLimits:
    """All resource limits that can affect an extraction result."""

    max_file_bytes: int = 64 * 1024 * 1024
    max_total_uncompressed_bytes: int = 128 * 1024 * 1024
    max_member_uncompressed_bytes: int = 24 * 1024 * 1024
    max_archive_members: int = 2_048
    max_compression_ratio: float = 250.0
    max_pages: int = 64
    max_text_nodes: int = 250_000
    max_extracted_chars: int = 500_000
    timeout_seconds: float = 30.0
    memory_mb: int = 768
    cpu_count: float = 1.0
    pids_limit: int = 64

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_file_bytes,
            self.max_total_uncompressed_bytes,
            self.max_member_uncompressed_bytes,
            self.max_archive_members,
            self.max_pages,
            self.max_text_nodes,
            self.max_extracted_chars,
            self.memory_mb,
            self.pids_limit,
        )
        if any(value <= 0 for value in integer_limits):
            raise ValueError("file-reader integer limits must be positive")
        if self.max_compression_ratio <= 0 or self.timeout_seconds <= 0 or self.cpu_count <= 0:
            raise ValueError("file-reader ratio, timeout, and CPU limits must be positive")
        if self.max_member_uncompressed_bytes > self.max_total_uncompressed_bytes:
            raise ValueError("single-member budget cannot exceed total uncompressed budget")

    def fingerprint(self) -> tuple[Any, ...]:
        return (
            self.max_file_bytes,
            self.max_total_uncompressed_bytes,
            self.max_member_uncompressed_bytes,
            self.max_archive_members,
            self.max_compression_ratio,
            self.max_pages,
            self.max_text_nodes,
            self.max_extracted_chars,
            self.timeout_seconds,
            self.memory_mb,
            self.cpu_count,
            self.pids_limit,
        )


DEFAULT_LIMITS = FileReadLimits()

_PLAIN_EXTENSIONS = frozenset({
    ".csv", ".txt", ".md", ".json", ".jsonl", ".py", ".js", ".ts",
    ".java", ".xml", ".html", ".htm", ".yaml", ".yml", ".sql",
    ".toml", ".ini", ".properties", ".gradle", ".log", ".rst",
})


@dataclass(frozen=True)
class FileReadResult:
    status: str
    text: str
    parser: str
    content_sha256: str | None = None
    truncated: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status in {"ok", "truncated"}


class FileReadFailure(RuntimeError):
    """A typed non-finding outcome from attachment handling."""

    def __init__(
        self,
        status: str,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = dict(details or {})


@dataclass
class _Budget:
    limits: FileReadLimits
    deadline: float
    decompressed_bytes: int = 0

    @classmethod
    def start(cls, limits: FileReadLimits) -> "_Budget":
        return cls(limits, time.monotonic() + limits.timeout_seconds)

    def check_time(self) -> None:
        if time.monotonic() > self.deadline:
            raise FileReadFailure(
                "budget_exceeded",
                "time_budget",
                "attachment parsing exceeded its wall-time budget",
            )

    def consume_decompressed(self, amount: int) -> None:
        self.decompressed_bytes += amount
        if self.decompressed_bytes > self.limits.max_total_uncompressed_bytes:
            raise FileReadFailure(
                "budget_exceeded",
                "total_uncompressed_budget",
                "archive output exceeds the total uncompressed-byte budget",
            )
        self.check_time()


@dataclass(frozen=True)
class _Snapshot:
    workspace: Path
    path: Path
    content_sha256: str
    size: int
    extension: str


class _TextCollector:
    """Retain bounded head/tail text while consuming the complete allowed input."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.keep_each = max((limit + 1) // 2, 1)
        self.head = ""
        self.tail = ""
        self.total_chars = 0

    def add(self, value: str, *, separate: bool = True) -> None:
        if not value:
            return
        if self.total_chars and separate:
            value = "\n" + value
        self.total_chars += len(value)
        missing = max(self.keep_each - len(self.head), 0)
        if missing:
            self.head += value[:missing]
            value = value[missing:]
        if value:
            self.tail = (self.tail + value)[-self.keep_each:]

    @property
    def truncated(self) -> bool:
        return self.total_chars > self.limit

    def value(self) -> str:
        if not self.truncated:
            return (self.head + self.tail)[: self.total_chars]
        marker = f"\n...[middle truncated; total_chars={self.total_chars}]...\n"
        if len(marker) >= self.limit:
            return marker[: self.limit]
        available = self.limit - len(marker)
        head_chars = (available + 1) // 2
        tail_chars = available - head_chars
        return self.head[:head_chars] + marker + self.tail[-tail_chars:]


_CacheInfo = namedtuple("FileReaderCacheInfo", "hits misses maxsize currsize")
_cache_lock = threading.Lock()
_extraction_cache: "OrderedDict[tuple[Any, ...], FileReadResult]" = OrderedDict()
_cache_hits = 0
_cache_misses = 0


def clear_file_reader_cache() -> None:
    global _cache_hits, _cache_misses
    with _cache_lock:
        _extraction_cache.clear()
        _cache_hits = 0
        _cache_misses = 0


def file_reader_cache_info():
    with _cache_lock:
        return _CacheInfo(_cache_hits, _cache_misses, _CACHE_CAPACITY, len(_extraction_cache))


def _cache_get(key: tuple[Any, ...]) -> FileReadResult | None:
    global _cache_hits, _cache_misses
    with _cache_lock:
        value = _extraction_cache.get(key)
        if value is None:
            _cache_misses += 1
            return None
        _cache_hits += 1
        _extraction_cache.move_to_end(key)
        return replace(value, details=dict(value.details))


def _cache_put(key: tuple[Any, ...], value: FileReadResult) -> None:
    with _cache_lock:
        _extraction_cache[key] = replace(value, details=dict(value.details))
        _extraction_cache.move_to_end(key)
        while len(_extraction_cache) > _CACHE_CAPACITY:
            _extraction_cache.popitem(last=False)


def _safe_extension(path: Path) -> str:
    suffix = path.suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,12}", suffix) else ""


@contextmanager
def _snapshot_file(path: Path, limits: FileReadLimits, budget: _Budget) -> Iterator[_Snapshot]:
    """Copy a stable, bounded regular-file snapshot and hash the copied bytes."""

    try:
        resolved = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise FileReadFailure("missing", "file_missing", "declared attachment does not exist") from exc
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as exc:
        raise FileReadFailure(
            "security_blocked",
            "snapshot_open_failed",
            f"attachment could not be opened safely: {type(exc).__name__}",
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise FileReadFailure(
                "security_blocked",
                "not_regular_file",
                "attachment is not a regular file",
            )
        if metadata.st_size > limits.max_file_bytes:
            raise FileReadFailure(
                "budget_exceeded",
                "file_size_budget",
                f"attachment exceeds the {limits.max_file_bytes}-byte file budget",
            )
        with tempfile.TemporaryDirectory(prefix="benchcore-file-reader-") as directory:
            workspace = Path(directory)
            extension = _safe_extension(path)
            target = workspace / f"input{extension}"
            digest = hashlib.sha256()
            copied = 0
            with os.fdopen(descriptor, "rb", closefd=False) as source, target.open("xb") as output:
                while True:
                    budget.check_time()
                    chunk = source.read(min(1024 * 1024, limits.max_file_bytes - copied + 1))
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > limits.max_file_bytes:
                        raise FileReadFailure(
                            "budget_exceeded",
                            "file_size_budget",
                            "attachment grew beyond its file-size budget while being read",
                        )
                    digest.update(chunk)
                    output.write(chunk)
            target.chmod(0o400)
            yield _Snapshot(workspace, target, digest.hexdigest(), copied, extension)
    finally:
        os.close(descriptor)


def _runner_identity(runner: CommandRunner | None) -> str:
    if isinstance(runner, ContainerRunner):
        return f"container:{runner.image}"
    if isinstance(runner, LocalProcessRunner):
        return "unsafe-local"
    return "none" if runner is None else f"unrecognized:{type(runner).__name__}"


def _parser_name(extension: str) -> str:
    if extension == ".xlsx":
        return "bounded-ooxml-xlsx"
    if extension == ".docx":
        return "bounded-ooxml-docx"
    if extension == ".pptx":
        return "bounded-ooxml-pptx"
    if extension in {".pdf", ".xls", ".doc", ".ppt", ".png", ".jpg", ".jpeg", ".webp"}:
        return "isolated-rich-document"
    if extension in _PLAIN_EXTENSIONS:
        return "bounded-plain-text"
    return "unsupported-format"


def read_file_result(
    path: str | Path,
    *,
    limits: FileReadLimits | None = None,
    runner: CommandRunner | None = None,
    allow_unsafe_local: bool = False,
    max_pages: int | None = None,
) -> FileReadResult:
    """Return a typed extraction outcome without confusing failure with empty text."""

    chosen = limits or DEFAULT_LIMITS
    requested_pages = chosen.max_pages if max_pages is None else min(max(int(max_pages), 1), chosen.max_pages)
    source = Path(path)
    budget = _Budget.start(chosen)
    parser = _parser_name(_safe_extension(source))
    try:
        with _snapshot_file(source, chosen, budget) as snapshot:
            parser_identity = (
                f"{PARSER_IMPLEMENTATION_VERSION}:{parser}:"
                f"{_runner_identity(runner) if parser == 'isolated-rich-document' else 'host-bounded'}"
            )
            cache_key = (
                snapshot.content_sha256,
                parser_identity,
                chosen.fingerprint(),
                requested_pages,
            )
            cached = _cache_get(cache_key)
            if cached is not None:
                return cached
            text, truncated, details = _extract_snapshot(
                snapshot,
                chosen,
                budget,
                requested_pages,
                runner=runner,
                allow_unsafe_local=allow_unsafe_local,
            )
            result = FileReadResult(
                status="truncated" if truncated else "ok",
                text=text,
                parser=parser_identity,
                content_sha256=snapshot.content_sha256,
                truncated=truncated,
                details={"file_bytes": snapshot.size, **details},
            )
            _cache_put(cache_key, result)
            return result
    except FileReadFailure as exc:
        return FileReadResult(
            status=exc.status,
            text=str(exc),
            parser=f"{PARSER_IMPLEMENTATION_VERSION}:{parser}",
            details={"code": exc.code, **exc.details},
        )
    except Exception as exc:  # parser bugs are operational, never a clean signal
        return FileReadResult(
            status="operational_failed",
            text=f"attachment parser failed: {type(exc).__name__}: {str(exc)[:300]}",
            parser=f"{PARSER_IMPLEMENTATION_VERSION}:{parser}",
            details={"code": "unexpected_parser_failure", "exception_type": type(exc).__name__},
        )


def read_file(
    path: str | Path,
    max_chars: int = 3000,
    *,
    limits: FileReadLimits | None = None,
    runner: CommandRunner | None = None,
    allow_unsafe_local: bool = False,
) -> str:
    """Compatibility wrapper returning a compact profile with explicit status."""

    source = Path(path)
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    result = read_file_result(
        source,
        limits=limits,
        runner=runner,
        allow_unsafe_local=allow_unsafe_local,
    )
    extension = _safe_extension(source)
    header = f"FILE {source.name} [{extension}]"
    if not result.succeeded:
        code = str(result.details.get("code") or "unknown")
        return f"{header}\n[FILE_READER_STATUS={result.status}; code={code}] {result.text}"
    body = _head_tail(result.text, max_chars)
    status = "\n[FILE_READER_STATUS=truncated]" if result.truncated else ""
    return f"{header}{status}\n{body}"


def search_file(
    path: str | Path,
    terms: list[str],
    max_pages: int | None = None,
    *,
    limits: FileReadLimits | None = None,
    runner: CommandRunner | None = None,
    allow_unsafe_local: bool = False,
) -> dict[str, Any]:
    """Search bounded extracted text; incomplete absence is an explicit error."""

    result = read_file_result(
        path,
        limits=limits,
        runner=runner,
        allow_unsafe_local=allow_unsafe_local,
        max_pages=max_pages,
    )
    if not result.succeeded:
        return {
            "_error": result.text,
            "_status": result.status,
            "_code": result.details.get("code"),
        }
    text = result.text
    low = text.lower()
    output: dict[str, Any] = {}
    missing = False
    for term in terms:
        value = str(term)
        index = low.find(value.lower())
        if index < 0:
            output[value] = None
            missing = True
        else:
            output[value] = text[max(0, index - 40): index + 60].replace("\n", " ")
    if result.truncated and missing:
        output["_error"] = "search is incomplete because the extraction hit a page or output budget"
        output["_status"] = "truncated"
        output["_code"] = "incomplete_search_space"
    return output


def _extract_snapshot(
    snapshot: _Snapshot,
    limits: FileReadLimits,
    budget: _Budget,
    max_pages: int,
    *,
    runner: CommandRunner | None,
    allow_unsafe_local: bool,
) -> tuple[str, bool, dict[str, Any]]:
    extension = snapshot.extension
    if extension == ".xlsx":
        return _xlsx(snapshot.path, limits, budget, max_pages)
    if extension == ".docx":
        return _docx(snapshot.path, limits, budget)
    if extension == ".pptx":
        return _pptx(snapshot.path, limits, budget, max_pages)
    if extension in {".pdf", ".xls", ".doc", ".ppt", ".png", ".jpg", ".jpeg", ".webp"}:
        return _isolated_rich_document(
            snapshot,
            limits,
            budget,
            max_pages,
            runner=runner,
            allow_unsafe_local=allow_unsafe_local,
        )
    if extension in _PLAIN_EXTENSIONS:
        return _plain(snapshot.path, limits, budget)
    raise FileReadFailure(
        "unsupported",
        "unsupported_file_type",
        f"attachment type {extension or '(no extension)'} has no safe parser",
    )


@contextmanager
def _validated_archive(
    path: Path,
    limits: FileReadLimits,
    budget: _Budget,
) -> Iterator[zipfile.ZipFile]:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise FileReadFailure(
            "operational_failed",
            "invalid_ooxml_zip",
            "OOXML attachment is not a valid ZIP package",
        ) from exc
    try:
        infos = archive.infolist()
        if len(infos) > limits.max_archive_members:
            raise FileReadFailure(
                "budget_exceeded",
                "archive_member_budget",
                f"archive contains more than {limits.max_archive_members} members",
            )
        names: set[str] = set()
        declared_total = 0
        allowed_compression = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
        for info in infos:
            budget.check_time()
            name = info.filename.replace("\\", "/")
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts or "\x00" in name:
                raise FileReadFailure(
                    "security_blocked",
                    "unsafe_archive_member",
                    "archive contains an unsafe member path",
                )
            if name in names:
                raise FileReadFailure(
                    "security_blocked",
                    "duplicate_archive_member",
                    "archive contains duplicate member names",
                )
            names.add(name)
            if info.flag_bits & 0x1:
                raise FileReadFailure(
                    "unsupported",
                    "encrypted_archive_member",
                    "encrypted OOXML members are unsupported",
                )
            if info.compress_type not in allowed_compression:
                raise FileReadFailure(
                    "unsupported",
                    "archive_compression_method",
                    "archive uses an unsupported compression method",
                )
            if info.file_size > limits.max_member_uncompressed_bytes:
                raise FileReadFailure(
                    "budget_exceeded",
                    "archive_member_size_budget",
                    "archive member exceeds its uncompressed-byte budget",
                )
            declared_total += info.file_size
            if declared_total > limits.max_total_uncompressed_bytes:
                raise FileReadFailure(
                    "budget_exceeded",
                    "total_uncompressed_budget",
                    "archive declared size exceeds the total uncompressed-byte budget",
                )
            if info.file_size >= 4096:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > limits.max_compression_ratio:
                    raise FileReadFailure(
                        "security_blocked",
                        "archive_compression_ratio",
                        f"archive member compression ratio {ratio:.1f} exceeds the safety limit",
                    )
        yield archive
    finally:
        archive.close()


def _read_member(
    archive: zipfile.ZipFile,
    name: str,
    limits: FileReadLimits,
    budget: _Budget,
) -> bytes:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise FileReadFailure(
            "operational_failed",
            "missing_ooxml_member",
            f"required OOXML member is absent: {name}",
        ) from exc
    output = bytearray()
    try:
        with archive.open(info, "r") as stream:
            while True:
                budget.check_time()
                chunk = stream.read(
                    min(
                        256 * 1024,
                        limits.max_member_uncompressed_bytes - len(output) + 1,
                    )
                )
                if not chunk:
                    break
                output.extend(chunk)
                budget.consume_decompressed(len(chunk))
                if len(output) > limits.max_member_uncompressed_bytes:
                    raise FileReadFailure(
                        "budget_exceeded",
                        "archive_member_size_budget",
                        "archive member expanded beyond its byte budget",
                    )
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise FileReadFailure(
            "operational_failed",
            "archive_decompression_failed",
            f"archive member decompression failed: {type(exc).__name__}",
        ) from exc
    return bytes(output)


def _natural_member_key(name: str) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name))


def _xml_text_nodes(
    data: bytes,
    budget: _Budget,
    max_nodes: int,
    *,
    preserve_whitespace: bool = False,
) -> list[str]:
    text = data.decode("utf-8", errors="replace")
    values: list[str] = []
    pattern = re.compile(
        r"<(?:[A-Za-z_][\w.-]*:)?t(?:\s[^>]*)?>(.*?)</(?:[A-Za-z_][\w.-]*:)?t\s*>",
        re.DOTALL,
    )
    for index, match in enumerate(pattern.finditer(text), 1):
        if index > max_nodes:
            raise FileReadFailure(
                "budget_exceeded",
                "xml_text_node_budget",
                "OOXML text-node count exceeds the parser budget",
            )
        if index % 512 == 0:
            budget.check_time()
        value = re.sub(r"<[^>]+>", "", match.group(1))
        value = html.unescape(value)
        if not preserve_whitespace:
            value = value.strip()
        if value.strip():
            values.append(value)
    return values


def _xlsx_shared_strings(
    data: bytes,
    budget: _Budget,
    max_nodes: int,
) -> tuple[list[str], int]:
    """Return one shared-string entry per ``<si>``, joining rich-text runs."""

    xml = data.decode("utf-8", errors="replace")
    strings: list[str] = []
    text_nodes = 0
    for entry_index, entry in enumerate(
        re.finditer(r"<si(?:\s[^>]*)?>(.*?)</si\s*>", xml, re.DOTALL),
        1,
    ):
        if entry_index % 512 == 0:
            budget.check_time()
        values = _xml_text_nodes(
            entry.group(1).encode("utf-8"),
            budget,
            max_nodes - text_nodes,
            preserve_whitespace=True,
        )
        text_nodes += len(values)
        strings.append("".join(values).strip())
    return strings, text_nodes


def _docx(
    path: Path,
    limits: FileReadLimits,
    budget: _Budget,
) -> tuple[str, bool, dict[str, Any]]:
    collector = _TextCollector(limits.max_extracted_chars)
    with _validated_archive(path, limits, budget) as archive:
        names = {
            info.filename
            for info in archive.infolist()
            if re.fullmatch(r"word/(?:document|header\d+|footer\d+|footnotes|endnotes)\.xml", info.filename)
        }
        if "word/document.xml" not in names:
            raise FileReadFailure(
                "operational_failed", "missing_ooxml_member", "DOCX has no word/document.xml"
            )
        nodes = 0
        for name in sorted(names, key=_natural_member_key):
            values = _xml_text_nodes(
                _read_member(archive, name, limits, budget),
                budget,
                limits.max_text_nodes - nodes,
            )
            nodes += len(values)
            for value in values:
                collector.add(value)
    return collector.value(), collector.truncated, {"text_nodes": nodes}


def _page_selection(count: int, maximum: int) -> list[int]:
    if count <= maximum:
        return list(range(count))
    if maximum == 1:
        return [0]
    tail = min(2, maximum - 1)
    return list(range(maximum - tail)) + list(range(count - tail, count))


def _pptx(
    path: Path,
    limits: FileReadLimits,
    budget: _Budget,
    max_pages: int,
) -> tuple[str, bool, dict[str, Any]]:
    collector = _TextCollector(limits.max_extracted_chars)
    with _validated_archive(path, limits, budget) as archive:
        slides = sorted(
            (
                info.filename
                for info in archive.infolist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", info.filename)
            ),
            key=_natural_member_key,
        )
        selected = _page_selection(len(slides), max_pages)
        text_nodes = 0
        for index in selected:
            values = _xml_text_nodes(
                _read_member(archive, slides[index], limits, budget),
                budget,
                limits.max_text_nodes - text_nodes,
            )
            text_nodes += len(values)
            collector.add(f"[slide {index + 1}] " + " | ".join(values))
    page_truncated = len(slides) > len(selected)
    return (
        f"({len(slides)} slides, preview_slides={[index + 1 for index in selected]})\n"
        + collector.value(),
        collector.truncated or page_truncated,
        {"page_count": len(slides), "parsed_pages": len(selected), "text_nodes": text_nodes},
    )


def _xlsx(
    path: Path,
    limits: FileReadLimits,
    budget: _Budget,
    max_pages: int,
) -> tuple[str, bool, dict[str, Any]]:
    collector = _TextCollector(limits.max_extracted_chars)
    with _validated_archive(path, limits, budget) as archive:
        members = {info.filename for info in archive.infolist()}
        shared: list[str] = []
        text_nodes = 0
        if "xl/sharedStrings.xml" in members:
            shared, shared_nodes = _xlsx_shared_strings(
                _read_member(archive, "xl/sharedStrings.xml", limits, budget),
                budget,
                limits.max_text_nodes,
            )
            text_nodes += shared_nodes
        sheets = sorted(
            (
                name
                for name in members
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
            ),
            key=_natural_member_key,
        )
        if not sheets:
            raise FileReadFailure(
                "operational_failed", "missing_ooxml_member", "XLSX contains no worksheet XML"
            )
        sheet_names: list[str] = []
        if "xl/workbook.xml" in members:
            workbook = _read_member(archive, "xl/workbook.xml", limits, budget).decode(
                "utf-8", errors="replace"
            )
            sheet_names = [
                html.unescape(value)
                for value in re.findall(r"<sheet\b[^>]*\bname=[\"']([^\"']+)", workbook)
            ]
        selected = _page_selection(len(sheets), max_pages)
        collector.add(f"sheets={sheet_names or [Path(name).stem for name in sheets]}")
        rows_seen = 0
        for sheet_index in selected:
            label = sheet_names[sheet_index] if sheet_index < len(sheet_names) else Path(sheets[sheet_index]).stem
            collector.add(f"-- sheet '{label}' --")
            xml = _read_member(archive, sheets[sheet_index], limits, budget).decode(
                "utf-8", errors="replace"
            )
            for row_index, row_match in enumerate(
                re.finditer(r"<row\b[^>]*>(.*?)</row\s*>", xml, re.DOTALL),
                1,
            ):
                rows_seen += 1
                if rows_seen > limits.max_text_nodes:
                    raise FileReadFailure(
                        "budget_exceeded",
                        "xlsx_row_budget",
                        "worksheet row count exceeds the parser budget",
                    )
                if row_index % 512 == 0:
                    budget.check_time()
                cells: list[str] = []
                for cell in re.finditer(r"<c\b([^>]*)>(.*?)</c\s*>", row_match.group(1), re.DOTALL):
                    attrs, body = cell.groups()
                    cell_type_match = re.search(r"\bt=[\"']([^\"']+)", attrs)
                    cell_type = cell_type_match.group(1) if cell_type_match else ""
                    if cell_type == "inlineStr":
                        values = _xml_text_nodes(
                            body.encode("utf-8"),
                            budget,
                            limits.max_text_nodes - text_nodes,
                        )
                        if text_nodes + len(values) > limits.max_text_nodes:
                            raise FileReadFailure(
                                "budget_exceeded",
                                "xml_text_node_budget",
                                "XLSX text-node count exceeds the parser budget",
                            )
                        text_nodes += len(values)
                        value = " ".join(values)
                    else:
                        value_match = re.search(r"<v(?:\s[^>]*)?>(.*?)</v\s*>", body, re.DOTALL)
                        value = html.unescape(value_match.group(1).strip()) if value_match else ""
                        if cell_type == "s" and value:
                            try:
                                value = shared[int(value)]
                            except (ValueError, IndexError):
                                value = "[invalid shared-string index]"
                    if value:
                        cells.append(value)
                if cells:
                    collector.add("\t".join(cells))
    page_truncated = len(sheets) > len(selected)
    return (
        collector.value(),
        collector.truncated or page_truncated,
        {
            "sheet_count": len(sheets),
            "parsed_sheets": len(selected),
            "rows_seen": rows_seen,
            "text_nodes": text_nodes,
        },
    )


def _plain(
    path: Path,
    limits: FileReadLimits,
    budget: _Budget,
) -> tuple[str, bool, dict[str, Any]]:
    collector = _TextCollector(limits.max_extracted_chars)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    bytes_read = 0
    with path.open("rb") as stream:
        while True:
            budget.check_time()
            chunk = stream.read(256 * 1024)
            if not chunk:
                break
            bytes_read += len(chunk)
            collector.add(decoder.decode(chunk, final=False), separate=False)
        collector.add(decoder.decode(b"", final=True), separate=False)
    return collector.value(), collector.truncated, {"decoded_bytes": bytes_read}


_PDF_DRIVER = r'''
import json, sys
path, max_pages, max_chars = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader
reader = PdfReader(path)
parts = []
for index, page in enumerate(reader.pages[:max_pages]):
    parts.append(f"[page {index + 1}]\n{page.extract_text() or ''}")
text = "\n".join(parts)
body = f"({len(reader.pages)}-page PDF, parsed_pages={min(len(reader.pages), max_pages)})\n" + text
print("__BENCHCORE_FILE_READER_META__" + json.dumps({
    "source_count": len(reader.pages),
    "parsed_count": min(len(reader.pages), max_pages),
    "total_chars": len(body),
    "truncated": len(reader.pages) > max_pages or len(body) > max_chars,
}, sort_keys=True))
print(body[:max_chars])
'''


_XLS_DRIVER = r'''
import json, sys
import pandas as pd
path, max_sheets, max_chars = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
book = pd.ExcelFile(path)
parts = [f"sheets={book.sheet_names}"]
total_chars = sum(len(part) + 1 for part in parts)
stored_chars = total_chars
truncated = len(book.sheet_names) > max_sheets
for name in book.sheet_names[:max_sheets]:
    frame = book.parse(name, header=None).fillna("").astype(str)
    heading = f"-- sheet '{name}' shape={frame.shape} --"
    total_chars += len(heading) + 1
    if stored_chars < max_chars:
        parts.append(heading)
        stored_chars += len(heading) + 1
    for row in frame.itertuples(index=False, name=None):
        value = "\t".join(cell.strip() for cell in row if cell.strip())
        if value:
            total_chars += len(value) + 1
            if stored_chars < max_chars:
                parts.append(value)
                stored_chars += len(value) + 1
            else:
                truncated = True
body = "\n".join(parts)
print("__BENCHCORE_FILE_READER_META__" + json.dumps({
    "source_count": len(book.sheet_names),
    "parsed_count": min(len(book.sheet_names), max_sheets),
    "total_chars": total_chars,
    "truncated": truncated or total_chars > max_chars,
}, sort_keys=True))
print(body[:max_chars])
'''


_PPT_DRIVER = r'''
import html, json, re, subprocess, sys, tempfile, zipfile
from pathlib import Path
path, max_pages, max_chars = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    profile = root / "profile"
    result = subprocess.run(
        ["libreoffice", "--headless", f"-env:UserInstallation={profile.as_uri()}",
         "--convert-to", "pptx", "--outdir", str(root), str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False,
    )
    converted = root / (path.stem + ".pptx")
    if result.returncode != 0 or not converted.is_file():
        raise RuntimeError("LibreOffice conversion failed")
    with zipfile.ZipFile(converted) as archive:
        names = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=lambda value: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", value)],
        )
        parts = []
        for index, name in enumerate(names[:max_pages]):
            xml = archive.read(name).decode("utf-8", errors="replace")
            values = [html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
                      for value in re.findall(r"<a:t(?:\s[^>]*)?>(.*?)</a:t\s*>", xml, re.S)]
            parts.append(f"[slide {index + 1}] " + " | ".join(value for value in values if value))
        body = f"({len(names)} slides, parsed_slides={min(len(names), max_pages)})\n" + "\n".join(parts)
        print("__BENCHCORE_FILE_READER_META__" + json.dumps({
            "source_count": len(names),
            "parsed_count": min(len(names), max_pages),
            "total_chars": len(body),
            "truncated": len(names) > max_pages or len(body) > max_chars,
        }, sort_keys=True))
        print(body[:max_chars])
'''


def _isolated_rich_document(
    snapshot: _Snapshot,
    limits: FileReadLimits,
    budget: _Budget,
    max_pages: int,
    *,
    runner: CommandRunner | None,
    allow_unsafe_local: bool,
) -> tuple[str, bool, dict[str, Any]]:
    extension = snapshot.extension
    if runner is None:
        wording = (
            "legacy .doc parsing unavailable without an isolated runner"
            if extension == ".doc"
            else f"{extension or 'rich-document'} parsing requires an isolated runner"
        )
        raise FileReadFailure("security_blocked", "isolated_parser_required", wording)
    local = isinstance(runner, LocalProcessRunner)
    if local and not allow_unsafe_local:
        raise FileReadFailure(
            "security_blocked",
            "unsafe_local_parser_refused",
            "LocalProcessRunner requires allow_unsafe_local=True for attachment parsing",
        )
    if not local and not isinstance(runner, ContainerRunner):
        raise FileReadFailure(
            "security_blocked",
            "unrecognized_runner",
            "attachment parser accepts only ContainerRunner or explicitly unsafe local execution",
        )
    if extension == ".doc":
        argv = ("antiword", snapshot.path.name)
    elif extension in {".png", ".jpg", ".jpeg", ".webp"}:
        argv = ("tesseract", snapshot.path.name, "stdout", "-l", "eng", "--psm", "6")
    elif extension == ".pdf":
        argv = (
            sys.executable,
            "-c",
            _PDF_DRIVER,
            snapshot.path.name,
            str(max_pages),
            str(limits.max_extracted_chars),
        )
    elif extension == ".xls":
        argv = (
            sys.executable,
            "-c",
            _XLS_DRIVER,
            snapshot.path.name,
            str(max_pages),
            str(limits.max_extracted_chars),
        )
    elif extension == ".ppt":
        argv = (
            sys.executable,
            "-c",
            _PPT_DRIVER,
            snapshot.path.name,
            str(max_pages),
            str(limits.max_extracted_chars),
        )
    else:  # defensive: dispatch is closed above
        raise FileReadFailure("unsupported", "unsupported_rich_document", "unsupported rich document")
    budget.check_time()
    remaining_seconds = budget.deadline - time.monotonic()
    if remaining_seconds <= 0:
        raise FileReadFailure(
            "budget_exceeded", "time_budget", "no execution time remains after input staging"
        )
    policy = ExecutionPolicy(
        timeout_seconds=remaining_seconds,
        max_output_chars=limits.max_extracted_chars + 4_096,
        memory_mb=limits.memory_mb,
        cpu_count=limits.cpu_count,
        pids_limit=limits.pids_limit,
        network_enabled=False,
        allow_local_process=local,
        allowed_environment=frozenset(),
    )
    try:
        run = runner.run(CommandSpec(argv=argv, cwd=snapshot.workspace), policy)
    except (ExecutionRefused, OSError) as exc:
        raise FileReadFailure(
            "operational_failed",
            "external_parser_runner_error",
            f"isolated attachment parser could not start: {type(exc).__name__}",
        ) from exc
    if run.timed_out:
        raise FileReadFailure(
            "operational_failed",
            "external_parser_timeout",
            "isolated attachment parser exceeded its timeout",
            details={"backend": run.backend, "isolation": run.isolation},
        )
    if run.exit_code != 0:
        diagnostic = (run.stderr or run.stdout or "no diagnostic output").strip()[-300:]
        raise FileReadFailure(
            "operational_failed",
            "external_parser_failed",
            f"isolated attachment parser failed: {diagnostic}",
            details={"backend": run.backend, "isolation": run.isolation},
        )
    output = (run.stdout or "").strip()
    if not output:
        raise FileReadFailure(
            "operational_failed", "external_parser_empty", "isolated attachment parser returned no text"
        )
    if "...[output truncated; original_chars=" in output:
        raise FileReadFailure(
            "budget_exceeded",
            "external_output_budget",
            "isolated attachment parser exceeded its output budget",
        )
    metadata: dict[str, Any] = {}
    expects_metadata = extension in {".pdf", ".xls", ".ppt"}
    if expects_metadata:
        marker, separator, body = output.partition("\n")
        prefix = "__BENCHCORE_FILE_READER_META__"
        if not separator or not marker.startswith(prefix):
            raise FileReadFailure(
                "operational_failed",
                "external_parser_protocol",
                "isolated attachment parser omitted its truncation metadata",
            )
        try:
            metadata = json.loads(marker[len(prefix):])
        except (json.JSONDecodeError, TypeError) as exc:
            raise FileReadFailure(
                "operational_failed",
                "external_parser_protocol",
                "isolated attachment parser returned invalid truncation metadata",
            ) from exc
        required = {"source_count", "parsed_count", "total_chars", "truncated"}
        counts = [metadata.get(name) for name in ("source_count", "parsed_count", "total_chars")]
        if (
            not required.issubset(metadata)
            or not isinstance(metadata.get("truncated"), bool)
            or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts)
            or metadata.get("parsed_count", 0) > metadata.get("source_count", 0)
        ):
            raise FileReadFailure(
                "operational_failed",
                "external_parser_protocol",
                "isolated attachment parser metadata is incomplete",
            )
        output = body.strip()
    truncated = bool(metadata.get("truncated")) or len(output) > limits.max_extracted_chars
    return (
        _head_tail(output, limits.max_extracted_chars),
        truncated,
        {"backend": run.backend, "isolation": run.isolation, **metadata},
    )


def _head_tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 200:
        return text[:max_chars]
    marker = f"\n...[middle truncated; total_chars={len(text)}]...\n"
    if len(marker) >= max_chars:
        return marker[:max_chars]
    available = max_chars - len(marker)
    head = (available + 1) // 2
    tail = available - head
    return text[:head] + marker + text[-tail:]
