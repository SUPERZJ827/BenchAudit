"""Safe, bounded, read-only cell snapshots for XLSX workbooks.

This module deliberately does not use a full spreadsheet engine.  An XLSX file
is an untrusted ZIP/XML package, so the reader first takes a stable byte
snapshot through a no-symlink file-descriptor walk, validates the complete ZIP
directory, and then parses only the workbook parts needed to recover worksheet
names and cell values.  XML is parsed with :mod:`defusedxml`; formulas are never
evaluated and relationships are never fetched.

The returned values are lexical OOXML values.  This avoids locale, floating
point, date-system, and formula-recalculation ambiguity in audit evidence.
Both ISO/IEC 29500 Strict and Transitional SpreadsheetML namespaces are
accepted, but their application and relationship namespaces may not be mixed.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import posixpath
import re
import stat
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterator, Literal, Mapping
from urllib.parse import unquote, urlsplit

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException


SNAPSHOT_SCHEMA_VERSION = "benchcore-ooxml-cell-snapshot-v1"
PARSER_VERSION = "benchcore-ooxml-cells/1.1"

SnapshotStatus = Literal[
    "invalid", "security_blocked", "budget_exceeded", "unsupported"
]


class XLSXSnapshotError(ValueError):
    """Fail-closed XLSX snapshot error with a stable machine-readable code."""

    def __init__(self, status: SnapshotStatus, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status, "code": self.code, "message": str(self)}


@dataclass(frozen=True)
class XLSXSnapshotLimits:
    """Resource ceilings that affect whether a snapshot is admitted."""

    max_file_bytes: int = 64 * 1024 * 1024
    max_archive_members: int = 2_048
    max_member_uncompressed_bytes: int = 24 * 1024 * 1024
    max_total_uncompressed_bytes: int = 128 * 1024 * 1024
    max_compression_ratio: float = 250.0
    max_xml_elements: int = 500_000
    max_sheets: int = 256
    max_cells: int = 250_000
    max_shared_strings: int = 250_000
    max_shared_string_chars: int = 8 * 1024 * 1024
    max_total_cell_chars: int = 16 * 1024 * 1024
    max_cell_value_chars: int = 32_767
    max_formula_chars: int = 32_767

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_file_bytes,
            self.max_archive_members,
            self.max_member_uncompressed_bytes,
            self.max_total_uncompressed_bytes,
            self.max_xml_elements,
            self.max_sheets,
            self.max_cells,
            self.max_shared_strings,
            self.max_shared_string_chars,
            self.max_total_cell_chars,
            self.max_cell_value_chars,
            self.max_formula_chars,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in integer_limits
        ):
            raise ValueError("XLSX snapshot integer limits must be positive integers")
        if (
            not isinstance(self.max_compression_ratio, (int, float))
            or isinstance(self.max_compression_ratio, bool)
            or not math.isfinite(float(self.max_compression_ratio))
            or self.max_compression_ratio <= 0
        ):
            raise ValueError("max_compression_ratio must be finite and positive")
        if self.max_member_uncompressed_bytes > self.max_total_uncompressed_bytes:
            raise ValueError(
                "max_member_uncompressed_bytes cannot exceed the total budget"
            )


DEFAULT_LIMITS = XLSXSnapshotLimits()


@dataclass(frozen=True)
class CellSnapshot:
    coordinate: str
    value: str
    data_type: str
    formula: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SheetSnapshot:
    name: str
    part_name: str
    cells: tuple[CellSnapshot, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "part_name": self.part_name,
            "cells": [cell.to_dict() for cell in self.cells],
        }


@dataclass(frozen=True)
class XLSXSnapshot:
    schema_version: str
    parser_version: str
    file_sha256: str
    file_size_bytes: int
    sheet_names: tuple[str, ...]
    sheets: tuple[SheetSnapshot, ...]
    cell_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "parser_version": self.parser_version,
            "file_sha256": self.file_sha256,
            "file_size_bytes": self.file_size_bytes,
            "sheet_names": list(self.sheet_names),
            "sheets": [sheet.to_dict() for sheet in self.sheets],
            "cell_count": self.cell_count,
        }


@dataclass
class _RuntimeBudget:
    limits: XLSXSnapshotLimits
    decompressed_bytes: int = 0
    xml_elements: int = 0
    cells: int = 0
    shared_strings: int = 0
    shared_string_chars: int = 0
    cell_chars: int = 0

    def consume_decompressed(self, amount: int) -> None:
        self.decompressed_bytes += amount
        if self.decompressed_bytes > self.limits.max_total_uncompressed_bytes:
            _fail(
                "budget_exceeded",
                "total_uncompressed_budget",
                "XLSX members exceeded the aggregate decompression budget",
            )

    def consume_element(self) -> None:
        self.xml_elements += 1
        if self.xml_elements > self.limits.max_xml_elements:
            _fail(
                "budget_exceeded",
                "xml_element_budget",
                "XLSX XML element count exceeded the parser budget",
            )

    def consume_shared_string(self, value: str) -> None:
        self.shared_strings += 1
        self.shared_string_chars += len(value)
        if self.shared_strings > self.limits.max_shared_strings:
            _fail(
                "budget_exceeded",
                "shared_string_count_budget",
                "XLSX shared-string count exceeded the parser budget",
            )
        if self.shared_string_chars > self.limits.max_shared_string_chars:
            _fail(
                "budget_exceeded",
                "shared_string_char_budget",
                "XLSX shared strings exceeded the character budget",
            )

    def consume_cell(self, value: str, formula: str | None) -> None:
        self.cells += 1
        self.cell_chars += len(value) + (len(formula) if formula else 0)
        if self.cells > self.limits.max_cells:
            _fail(
                "budget_exceeded",
                "cell_count_budget",
                "XLSX cell count exceeded the snapshot budget",
            )
        if self.cell_chars > self.limits.max_total_cell_chars:
            _fail(
                "budget_exceeded",
                "cell_char_budget",
                "XLSX cell values exceeded the aggregate character budget",
            )


@dataclass(frozen=True)
class _Relationship:
    relationship_id: str
    relationship_type: str
    target: str
    external: bool


@dataclass(frozen=True)
class _OOXMLDialect:
    name: str
    spreadsheet_namespace: str
    relationship_namespace: str

    def relationship_type(self, kind: str) -> str:
        return f"{self.relationship_namespace}/{kind}"


@dataclass(frozen=True)
class _ContentTypeManifest:
    workbook_part: str
    overrides: Mapping[str, str]


_CELL_REFERENCE = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})\Z")
_DRIVE_PREFIX = re.compile(r"[A-Za-z]:")
_XML_DECLARATION_ATTACK = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.I)
_ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
# OPC container namespaces and part MIME types are shared by Strict and
# Transitional packages.  SpreadsheetML element namespaces and officeDocument
# relationship-type namespaces are dialect-specific and are bound below.
_OPC_CONTENT_TYPES_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/content-types"
)
_OPC_RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
_TRANSITIONAL_DIALECT = _OOXMLDialect(
    name="transitional",
    spreadsheet_namespace=(
        "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ),
    relationship_namespace=(
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ),
)
_STRICT_DIALECT = _OOXMLDialect(
    name="strict",
    spreadsheet_namespace="http://purl.oclc.org/ooxml/spreadsheetml/main",
    relationship_namespace=(
        "http://purl.oclc.org/ooxml/officeDocument/relationships"
    ),
)
_OOXML_DIALECTS = (_TRANSITIONAL_DIALECT, _STRICT_DIALECT)
_XLSX_WORKBOOK_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet.main+xml"
)
_XLSX_WORKSHEET_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.worksheet+xml"
)
_XLSX_SHARED_STRINGS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sharedStrings+xml"
)
_CELL_TYPES = frozenset({"", "n", "s", "str", "inlineStr", "b", "e", "d"})
_WORKBOOK_CORE_CHILDREN: Mapping[str, frozenset[str]] = {
    "sheets": frozenset({"sheet"}),
}
_SHARED_STRING_CORE_CHILDREN: Mapping[str, frozenset[str]] = {
    "sst": frozenset({"si"}),
    "si": frozenset({"r", "t"}),
    "r": frozenset({"t"}),
}
_WORKSHEET_CORE_CHILDREN: Mapping[str, frozenset[str]] = {
    "sheetData": frozenset({"row"}),
    "row": frozenset({"c"}),
    "c": frozenset({"f", "v", "is"}),
    "is": frozenset({"r", "t"}),
    "r": frozenset({"t"}),
}


def snapshot_xlsx(
    path: str | os.PathLike[str],
    *,
    limits: XLSXSnapshotLimits | None = None,
) -> XLSXSnapshot:
    """Return a deterministic, read-only snapshot of XLSX sheet cells.

    No formula is evaluated, no relationship is fetched, and no source path is
    followed through a symlink.  Any unsupported or ambiguous package feature
    fails closed with :class:`XLSXSnapshotError`.
    """

    active_limits = limits or DEFAULT_LIMITS
    data, digest = _read_stable_regular_file(path, active_limits.max_file_bytes)
    budget = _RuntimeBudget(active_limits)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data), "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise XLSXSnapshotError(
            "invalid", "invalid_xlsx_zip", "input is not a valid XLSX ZIP package"
        ) from exc

    with archive:
        members = _validate_archive(archive, active_limits)
        required = {"[Content_Types].xml", "_rels/.rels"}
        missing = required - set(members)
        if missing:
            _fail(
                "invalid",
                "missing_package_member",
                "XLSX package is missing required OPC metadata",
            )

        content_types = _read_member(
            archive, members["[Content_Types].xml"], budget
        )
        content_type_manifest = _validate_content_types(content_types, budget)

        root_relationships = _parse_relationships(
            _read_member(archive, members["_rels/.rels"], budget), budget
        )
        office = [
            (relationship, dialect)
            for relationship in root_relationships
            if (
                dialect := _relationship_dialect(
                    relationship, "officeDocument"
                )
            )
            is not None
        ]
        if len(office) != 1 or office[0][0].external:
            _fail(
                "invalid",
                "office_document_relationship",
                "XLSX must contain exactly one internal officeDocument relationship",
            )
        office_relationship, dialect = office[0]
        workbook_part = _resolve_relationship_target(
            "", office_relationship.target
        )
        if workbook_part != content_type_manifest.workbook_part:
            _fail(
                "security_blocked",
                "workbook_part_mismatch",
                "the root relationship and content types disagree on the workbook part",
            )
        if workbook_part not in members or members[workbook_part].is_dir():
            _fail(
                "invalid",
                "missing_workbook_part",
                "the workbook relationship does not resolve to a package member",
            )

        workbook_rels_part = _relationships_part_name(workbook_part)
        if workbook_rels_part not in members:
            _fail(
                "invalid",
                "missing_workbook_relationships",
                "XLSX workbook relationship metadata is missing",
            )
        workbook_relationships = _parse_relationships(
            _read_member(archive, members[workbook_rels_part], budget), budget
        )
        relationships_by_id: dict[str, _Relationship] = {}
        for relationship in workbook_relationships:
            if relationship.relationship_id in relationships_by_id:
                _fail(
                    "security_blocked",
                    "duplicate_relationship_id",
                    "workbook relationships contain a duplicate identifier",
                )
            relationships_by_id[relationship.relationship_id] = relationship
        _reject_mixed_relationship_dialect(
            workbook_relationships,
            kind="worksheet",
            dialect=dialect,
        )

        workbook_sheets = _parse_workbook(
            _read_member(archive, members[workbook_part], budget),
            budget,
            dialect,
        )
        if not workbook_sheets:
            _fail("invalid", "missing_worksheets", "XLSX workbook has no sheets")
        if len(workbook_sheets) > active_limits.max_sheets:
            _fail(
                "budget_exceeded",
                "sheet_count_budget",
                "XLSX sheet count exceeded the snapshot budget",
            )

        shared_strings: tuple[str, ...] = ()
        shared_relationships = [
            relationship
            for relationship in workbook_relationships
            if _relationship_is(relationship, "sharedStrings", dialect)
        ]
        _reject_mixed_relationship_dialect(
            workbook_relationships,
            kind="sharedStrings",
            dialect=dialect,
        )
        if len(shared_relationships) > 1:
            _fail(
                "invalid",
                "multiple_shared_string_parts",
                "XLSX declares multiple shared-string relationships",
            )
        if shared_relationships:
            relationship = shared_relationships[0]
            if relationship.external:
                _fail(
                    "security_blocked",
                    "external_shared_strings",
                    "external shared-string relationships are forbidden",
                )
            shared_part = _resolve_relationship_target(
                workbook_part, relationship.target
            )
            if shared_part not in members:
                _fail(
                    "invalid",
                    "missing_shared_strings",
                    "declared shared-string member is absent",
                )
            _require_part_content_type(
                content_type_manifest,
                shared_part,
                _XLSX_SHARED_STRINGS_CONTENT_TYPE,
                code="shared_strings_content_type_mismatch",
                label="shared-string",
            )
            shared_strings = _parse_shared_strings(
                _read_member(archive, members[shared_part], budget),
                budget,
                dialect.spreadsheet_namespace,
            )

        sheet_snapshots: list[SheetSnapshot] = []
        used_parts: set[str] = set()
        used_names: set[str] = set()
        for name, relationship_id in workbook_sheets:
            normalized_name = unicodedata.normalize("NFC", name).casefold()
            if normalized_name in used_names:
                _fail(
                    "invalid",
                    "duplicate_sheet_name",
                    "workbook contains duplicate or normalization-conflicting "
                    "sheet names",
                )
            used_names.add(normalized_name)
            relationship = relationships_by_id.get(relationship_id)
            if relationship is None:
                _fail(
                    "invalid",
                    "missing_sheet_relationship",
                    "a workbook sheet has no matching relationship",
                )
            if relationship.external:
                _fail(
                    "security_blocked",
                    "external_worksheet_relationship",
                    "external worksheet relationships are forbidden",
                )
            if not _relationship_is(relationship, "worksheet", dialect):
                foreign_dialect = _relationship_dialect(
                    relationship, "worksheet"
                )
                if foreign_dialect is not None:
                    _fail(
                        "security_blocked",
                        "mixed_ooxml_dialect",
                        "worksheet relationships do not match the workbook dialect",
                    )
                _fail(
                    "unsupported",
                    "unsupported_sheet_type",
                    "only worksheet cell sheets can be snapshotted",
                )
            part_name = _resolve_relationship_target(
                workbook_part, relationship.target
            )
            if part_name in used_parts:
                _fail(
                    "invalid",
                    "duplicate_sheet_part",
                    "multiple workbook sheets resolve to the same worksheet member",
                )
            used_parts.add(part_name)
            if part_name not in members or members[part_name].is_dir():
                _fail(
                    "invalid",
                    "missing_worksheet_part",
                    "a worksheet relationship resolves to a missing member",
                )
            _require_part_content_type(
                content_type_manifest,
                part_name,
                _XLSX_WORKSHEET_CONTENT_TYPE,
                code="worksheet_content_type_mismatch",
                label="worksheet",
            )
            cells = _parse_worksheet(
                _read_member(archive, members[part_name], budget),
                shared_strings,
                budget,
                dialect.spreadsheet_namespace,
            )
            sheet_snapshots.append(
                SheetSnapshot(name=name, part_name=part_name, cells=cells)
            )

    return XLSXSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        parser_version=PARSER_VERSION,
        file_sha256=digest,
        file_size_bytes=len(data),
        sheet_names=tuple(sheet.name for sheet in sheet_snapshots),
        sheets=tuple(sheet_snapshots),
        cell_count=sum(len(sheet.cells) for sheet in sheet_snapshots),
    )


def _fail(status: SnapshotStatus, code: str, message: str) -> None:
    raise XLSXSnapshotError(status, code, message)


def _read_stable_regular_file(
    path: str | os.PathLike[str], max_bytes: int
) -> tuple[bytes, str]:
    descriptor = _open_without_symlinks(path)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            _fail(
                "security_blocked",
                "not_regular_file",
                "XLSX input must be a regular file",
            )
        if before.st_size > max_bytes:
            _fail(
                "budget_exceeded",
                "file_size_budget",
                "XLSX input exceeds the file-size budget",
            )
        chunks: list[bytes] = []
        total = 0
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                _fail(
                    "budget_exceeded",
                    "file_size_budget",
                    "XLSX input grew beyond its byte budget while being read",
                )
            chunks.append(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        if total != before.st_size or not _same_file_state(before, after):
            _fail(
                "security_blocked",
                "source_changed_during_snapshot",
                "XLSX input changed while its stable snapshot was being read",
            )
        return b"".join(chunks), digest.hexdigest()
    finally:
        os.close(descriptor)


def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
    return all(
        getattr(left, field, None) == getattr(right, field, None)
        for field in fields
    )


def _open_without_symlinks(path: str | os.PathLike[str]) -> int:
    """Open every path component through anchored directory descriptors."""

    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        _fail(
            "unsupported",
            "nofollow_unavailable",
            "this platform cannot provide no-symlink file opening",
        )
    raw = os.path.expanduser(os.fspath(path))
    if not raw or "\x00" in raw:
        _fail("invalid", "invalid_source_path", "XLSX source path is invalid")
    absolute = os.path.abspath(raw)
    components = Path(absolute).parts
    if len(components) < 2 or components[0] != os.path.sep:
        _fail("invalid", "invalid_source_path", "XLSX source path is invalid")

    directory_flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    directory_fd = os.open(os.path.sep, directory_flags)
    try:
        for component in components[1:-1]:
            try:
                next_fd = os.open(
                    component, directory_flags, dir_fd=directory_fd
                )
            except OSError as exc:
                raise XLSXSnapshotError(
                    "security_blocked",
                    "source_path_component_refused",
                    "XLSX source path contains a missing, non-directory, "
                    "or symlink component",
                ) from exc
            os.close(directory_fd)
            directory_fd = next_fd
        try:
            return os.open(components[-1], file_flags, dir_fd=directory_fd)
        except OSError as exc:
            raise XLSXSnapshotError(
                "security_blocked",
                "source_open_refused",
                "XLSX source is missing, inaccessible, or a symlink",
            ) from exc
    finally:
        os.close(directory_fd)


def _validate_archive(
    archive: zipfile.ZipFile, limits: XLSXSnapshotLimits
) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > limits.max_archive_members:
        _fail(
            "budget_exceeded",
            "archive_member_budget",
            "XLSX archive contains too many members",
        )
    members: dict[str, zipfile.ZipInfo] = {}
    identity_names: set[str] = set()
    declared_total = 0
    for info in infos:
        name = _validate_member_name(info.filename, is_directory=info.is_dir())
        identity = unicodedata.normalize("NFC", name).casefold()
        if name in members or identity in identity_names:
            _fail(
                "security_blocked",
                "duplicate_archive_member",
                "XLSX archive contains duplicate or ambiguous member names",
            )
        members[name] = info
        identity_names.add(identity)
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            _fail(
                "security_blocked",
                "archive_symlink_member",
                "XLSX archive contains a symlink member",
            )
        if info.flag_bits & (0x1 | 0x40):
            _fail(
                "security_blocked",
                "encrypted_archive_member",
                "encrypted XLSX archive members are forbidden",
            )
        if info.compress_type not in _ALLOWED_COMPRESSION:
            _fail(
                "unsupported",
                "archive_compression_method",
                "XLSX archive uses an unsupported compression method",
            )
        if info.file_size < 0 or info.compress_size < 0:
            _fail(
                "invalid",
                "invalid_archive_member_size",
                "XLSX archive contains invalid member size metadata",
            )
        if info.file_size > limits.max_member_uncompressed_bytes:
            _fail(
                "budget_exceeded",
                "archive_member_size_budget",
                "an XLSX member exceeds its uncompressed-byte budget",
            )
        declared_total += info.file_size
        if declared_total > limits.max_total_uncompressed_bytes:
            _fail(
                "budget_exceeded",
                "total_uncompressed_budget",
                "XLSX declared size exceeds the aggregate decompression budget",
            )
        if info.file_size >= 4_096:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > limits.max_compression_ratio:
                _fail(
                    "security_blocked",
                    "archive_compression_ratio",
                    "an XLSX member exceeds the compression-ratio safety limit",
                )
    return members


def _validate_member_name(raw_name: str, *, is_directory: bool) -> str:
    if not isinstance(raw_name, str) or not raw_name or "\x00" in raw_name:
        _fail("security_blocked", "unsafe_archive_member", "unsafe ZIP member name")
    if "\\" in raw_name or raw_name.startswith("/") or _DRIVE_PREFIX.match(raw_name):
        _fail("security_blocked", "unsafe_archive_member", "unsafe ZIP member path")
    name = raw_name[:-1] if is_directory and raw_name.endswith("/") else raw_name
    pure = PurePosixPath(name)
    if (
        not name
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or posixpath.normpath(name) != name
        or "//" in name
    ):
        _fail("security_blocked", "unsafe_archive_member", "unsafe ZIP member path")
    return raw_name if is_directory else name


def _read_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    budget: _RuntimeBudget,
) -> bytes:
    output = bytearray()
    try:
        with archive.open(info, "r") as stream:
            while True:
                chunk = stream.read(
                    min(
                        256 * 1024,
                        budget.limits.max_member_uncompressed_bytes
                        - len(output)
                        + 1,
                    )
                )
                if not chunk:
                    break
                output.extend(chunk)
                budget.consume_decompressed(len(chunk))
                if len(output) > budget.limits.max_member_uncompressed_bytes:
                    _fail(
                        "budget_exceeded",
                        "archive_member_size_budget",
                        "an XLSX member expanded beyond its byte budget",
                    )
    except XLSXSnapshotError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise XLSXSnapshotError(
            "invalid",
            "archive_member_read_failed",
            "an XLSX archive member could not be read safely",
        ) from exc
    if len(output) != info.file_size:
        _fail(
            "invalid",
            "archive_member_size_mismatch",
            "an XLSX member disagrees with its declared uncompressed size",
        )
    return bytes(output)


def _iter_xml(data: bytes, budget: _RuntimeBudget) -> Iterator[tuple[str, Any]]:
    if _XML_DECLARATION_ATTACK.search(data):
        _fail(
            "security_blocked",
            "forbidden_xml_declaration",
            "OOXML DTD and entity declarations are forbidden",
        )
    try:
        iterator = DefusedET.iterparse(
            io.BytesIO(data),
            events=("start", "end"),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
        for event, element in iterator:
            if event == "start":
                budget.consume_element()
            yield event, element
    except XLSXSnapshotError:
        raise
    except (DefusedXmlException, DefusedET.ParseError, ValueError) as exc:
        raise XLSXSnapshotError(
            "security_blocked" if isinstance(exc, DefusedXmlException) else "invalid",
            "unsafe_or_invalid_xml",
            "OOXML contains forbidden or malformed XML",
        ) from exc


def _iter_xml_with_parent(
    data: bytes,
    budget: _RuntimeBudget,
) -> Iterator[tuple[str, Any, Any | None]]:
    """Yield defused parse events plus the structural parent element."""

    stack: list[Any] = []
    for event, element in _iter_xml(data, budget):
        if event == "start":
            parent = stack[-1] if stack else None
            stack.append(element)
            yield event, element, parent
            continue
        if not stack or stack[-1] is not element:
            _fail(
                "invalid",
                "invalid_xml_event_nesting",
                "OOXML parser observed inconsistent element nesting",
            )
        parent = stack[-2] if len(stack) > 1 else None
        yield event, element, parent
        stack.pop()


def _qname_parts(tag: Any) -> tuple[str, str]:
    text = str(tag)
    if text.startswith("{"):
        namespace, separator, local = text[1:].partition("}")
        if separator:
            return namespace, local
    return "", text


def _require_root_qname(
    element: Any,
    *,
    namespace: str,
    local_name: str,
    code: str,
    label: str,
) -> None:
    if _qname_parts(element.tag) != (namespace, local_name):
        _fail(
            "security_blocked",
            code,
            f"{label} root element uses an unexpected namespace or name",
        )


def _is_qname(element: Any, namespace: str, local_name: str) -> bool:
    return _qname_parts(element.tag) == (namespace, local_name)


def _reject_core_child_namespace(
    element: Any,
    *,
    parent: Any | None,
    namespace: str,
    child_rules: Mapping[str, frozenset[str]],
    code: str,
    label: str,
) -> None:
    if parent is None:
        return
    parent_namespace, parent_name = _qname_parts(parent.tag)
    expected_children = child_rules.get(parent_name)
    if parent_namespace != namespace or expected_children is None:
        return
    observed_namespace, local_name = _qname_parts(element.tag)
    if local_name in expected_children and observed_namespace != namespace:
        _fail(
            "security_blocked",
            code,
            f"a core {label} child element uses an unexpected namespace",
        )


def _parse_relationships(
    data: bytes, budget: _RuntimeBudget
) -> tuple[_Relationship, ...]:
    relationships: list[_Relationship] = []
    seen: set[str] = set()
    root_seen = False
    for event, element in _iter_xml(data, budget):
        if not root_seen and event == "start":
            _require_root_qname(
                element,
                namespace=_OPC_RELATIONSHIPS_NAMESPACE,
                local_name="Relationships",
                code="unexpected_relationships_namespace",
                label="OPC relationships",
            )
            root_seen = True
        if event != "end":
            continue
        namespace, local_name = _qname_parts(element.tag)
        if local_name == "Relationship" and (
            namespace != _OPC_RELATIONSHIPS_NAMESPACE
        ):
            _fail(
                "security_blocked",
                "unexpected_relationships_namespace",
                "an OPC Relationship element uses an unexpected namespace",
            )
        if (namespace, local_name) != (
            _OPC_RELATIONSHIPS_NAMESPACE,
            "Relationship",
        ):
            continue
        relationship_id = str(element.attrib.get("Id") or "")
        relationship_type = str(element.attrib.get("Type") or "")
        target = str(element.attrib.get("Target") or "")
        target_mode = str(element.attrib.get("TargetMode") or "Internal")
        if not relationship_id or not relationship_type or not target:
            _fail(
                "invalid",
                "invalid_relationship",
                "OOXML relationship is missing Id, Type, or Target",
            )
        if relationship_id in seen:
            _fail(
                "security_blocked",
                "duplicate_relationship_id",
                "OOXML relationships contain a duplicate identifier",
            )
        seen.add(relationship_id)
        if target_mode.casefold() not in {"internal", "external"}:
            _fail(
                "invalid",
                "invalid_relationship_mode",
                "OOXML relationship uses an unknown target mode",
            )
        relationships.append(
            _Relationship(
                relationship_id=relationship_id,
                relationship_type=relationship_type,
                target=target,
                external=target_mode.casefold() == "external",
            )
        )
        element.clear()
    if not root_seen:
        _fail("invalid", "missing_xml_root", "OPC relationships XML is empty")
    return tuple(relationships)


def _validate_content_types(
    data: bytes,
    budget: _RuntimeBudget,
) -> _ContentTypeManifest:
    workbook_types: list[str] = []
    overrides: dict[str, str] = {}
    root_seen = False
    for event, element in _iter_xml(data, budget):
        if not root_seen and event == "start":
            _require_root_qname(
                element,
                namespace=_OPC_CONTENT_TYPES_NAMESPACE,
                local_name="Types",
                code="unexpected_content_types_namespace",
                label="OPC content-types",
            )
            root_seen = True
        if event != "end":
            continue
        namespace, local_name = _qname_parts(element.tag)
        if local_name in {"Default", "Override"} and (
            namespace != _OPC_CONTENT_TYPES_NAMESPACE
        ):
            _fail(
                "security_blocked",
                "unexpected_content_types_namespace",
                "an OPC content-type declaration uses an unexpected namespace",
            )
        if (namespace, local_name) == (
            _OPC_CONTENT_TYPES_NAMESPACE,
            "Override",
        ):
            content_type = str(element.attrib.get("ContentType") or "")
            part_name = str(element.attrib.get("PartName") or "")
            if not content_type or not part_name:
                _fail(
                    "invalid",
                    "invalid_content_type_declaration",
                    "an OPC Override is missing PartName or ContentType",
                )
            normalized_part = _resolve_relationship_target("", part_name)
            if normalized_part in overrides:
                _fail(
                    "security_blocked",
                    "duplicate_content_type_override",
                    "OPC content types contain a duplicate part override",
                )
            overrides[normalized_part] = content_type
            folded_content_type = content_type.casefold()
            if content_type == _XLSX_WORKBOOK_CONTENT_TYPE:
                workbook_types.append(normalized_part)
            if (
                "macroenabled" in folded_content_type
                or "vbaproject" in folded_content_type
            ):
                _fail(
                    "unsupported",
                    "macro_enabled_workbook",
                    "macro-enabled spreadsheet packages are unsupported",
                )
        elif (namespace, local_name) == (
            _OPC_CONTENT_TYPES_NAMESPACE,
            "Default",
        ):
            content_type = str(element.attrib.get("ContentType") or "")
            extension = str(element.attrib.get("Extension") or "")
            if not content_type or not extension:
                _fail(
                    "invalid",
                    "invalid_content_type_declaration",
                    "an OPC Default is missing Extension or ContentType",
                )
            folded_content_type = content_type.casefold()
            if (
                "macroenabled" in folded_content_type
                or "vbaproject" in folded_content_type
            ):
                _fail(
                    "unsupported",
                    "macro_enabled_workbook",
                    "macro-enabled spreadsheet packages are unsupported",
                )
        element.clear()
    if not root_seen:
        _fail("invalid", "missing_xml_root", "OPC content-types XML is empty")
    if len(workbook_types) != 1:
        _fail(
            "invalid",
            "workbook_content_type",
            "XLSX content types must declare exactly one workbook main part",
        )
    return _ContentTypeManifest(
        workbook_part=workbook_types[0],
        overrides=overrides,
    )


def _require_part_content_type(
    manifest: _ContentTypeManifest,
    part_name: str,
    expected: str,
    *,
    code: str,
    label: str,
) -> None:
    if manifest.overrides.get(part_name) != expected:
        _fail(
            "security_blocked",
            code,
            f"the {label} relationship and ContentType declaration disagree",
        )


def _relationship_dialect(
    relationship: _Relationship,
    kind: str,
) -> _OOXMLDialect | None:
    return next(
        (
            dialect
            for dialect in _OOXML_DIALECTS
            if relationship.relationship_type == dialect.relationship_type(kind)
        ),
        None,
    )


def _relationship_is(
    relationship: _Relationship,
    kind: str,
    dialect: _OOXMLDialect,
) -> bool:
    return relationship.relationship_type == dialect.relationship_type(kind)


def _reject_mixed_relationship_dialect(
    relationships: tuple[_Relationship, ...],
    *,
    kind: str,
    dialect: _OOXMLDialect,
) -> None:
    if any(
        (candidate := _relationship_dialect(relationship, kind)) is not None
        and candidate != dialect
        for relationship in relationships
    ):
        _fail(
            "security_blocked",
            "mixed_ooxml_dialect",
            f"{kind} relationships do not match the workbook dialect",
        )


def _parse_workbook(
    data: bytes,
    budget: _RuntimeBudget,
    dialect: _OOXMLDialect,
) -> tuple[tuple[str, str], ...]:
    sheets: list[tuple[str, str]] = []
    root_seen = False
    for event, element, parent in _iter_xml_with_parent(data, budget):
        if not root_seen and event == "start":
            _require_root_qname(
                element,
                namespace=dialect.spreadsheet_namespace,
                local_name="workbook",
                code="unexpected_workbook_namespace",
                label=f"{dialect.name} SpreadsheetML workbook",
            )
            root_seen = True
        if event == "start":
            _reject_core_child_namespace(
                element,
                parent=parent,
                namespace=dialect.spreadsheet_namespace,
                child_rules=_WORKBOOK_CORE_CHILDREN,
                code="unexpected_spreadsheet_namespace",
                label="SpreadsheetML workbook",
            )
        if event != "end":
            continue
        namespace, local_name = _qname_parts(element.tag)
        if local_name == "sheet" and namespace != dialect.spreadsheet_namespace:
            _fail(
                "security_blocked",
                "unexpected_spreadsheet_namespace",
                "a workbook sheet declaration uses an unexpected namespace",
            )
        if (namespace, local_name) != (
            dialect.spreadsheet_namespace,
            "sheet",
        ):
            continue
        name = str(element.attrib.get("name") or "")
        relationship_id = ""
        for attribute, value in element.attrib.items():
            if _qname_parts(attribute) == (
                dialect.relationship_namespace,
                "id",
            ):
                relationship_id = str(value)
                break
        if not name or not relationship_id:
            _fail(
                "invalid",
                "invalid_sheet_declaration",
                "workbook sheet is missing its name or relationship identifier",
            )
        if len(name) > 255 or any(ord(character) < 32 for character in name):
            _fail(
                "invalid",
                "invalid_sheet_name",
                "workbook contains an invalid or excessively long sheet name",
            )
        sheets.append((name, relationship_id))
        element.clear()
    if not root_seen:
        _fail("invalid", "missing_xml_root", "SpreadsheetML workbook XML is empty")
    return tuple(sheets)


def _parse_shared_strings(
    data: bytes,
    budget: _RuntimeBudget,
    spreadsheet_namespace: str,
) -> tuple[str, ...]:
    strings: list[str] = []
    root_seen = False
    for event, element, parent in _iter_xml_with_parent(data, budget):
        if not root_seen and event == "start":
            _require_root_qname(
                element,
                namespace=spreadsheet_namespace,
                local_name="sst",
                code="unexpected_shared_strings_namespace",
                label="SpreadsheetML shared-string table",
            )
            root_seen = True
        if event == "start":
            _reject_core_child_namespace(
                element,
                parent=parent,
                namespace=spreadsheet_namespace,
                child_rules=_SHARED_STRING_CORE_CHILDREN,
                code="unexpected_spreadsheet_namespace",
                label="SpreadsheetML shared-string",
            )
        if event != "end" or not _is_qname(
            element, spreadsheet_namespace, "si"
        ):
            continue
        value = "".join(
            child.text or ""
            for child in element.iter()
            if _is_qname(child, spreadsheet_namespace, "t")
        )
        if len(value) > budget.limits.max_cell_value_chars:
            _fail(
                "budget_exceeded",
                "cell_value_budget",
                "an XLSX shared string exceeds the per-cell character budget",
            )
        budget.consume_shared_string(value)
        strings.append(value)
        element.clear()
    if not root_seen:
        _fail(
            "invalid",
            "missing_xml_root",
            "SpreadsheetML shared-string XML is empty",
        )
    return tuple(strings)


def _parse_worksheet(
    data: bytes,
    shared_strings: tuple[str, ...],
    budget: _RuntimeBudget,
    spreadsheet_namespace: str,
) -> tuple[CellSnapshot, ...]:
    cells: list[CellSnapshot] = []
    coordinates: set[str] = set()
    root_seen = False
    for event, element, parent in _iter_xml_with_parent(data, budget):
        if not root_seen and event == "start":
            _require_root_qname(
                element,
                namespace=spreadsheet_namespace,
                local_name="worksheet",
                code="unexpected_worksheet_namespace",
                label="SpreadsheetML worksheet",
            )
            root_seen = True
        if event == "start":
            _reject_core_child_namespace(
                element,
                parent=parent,
                namespace=spreadsheet_namespace,
                child_rules=_WORKSHEET_CORE_CHILDREN,
                code="unexpected_spreadsheet_namespace",
                label="SpreadsheetML worksheet",
            )
        if event != "end":
            continue
        if _is_qname(element, spreadsheet_namespace, "c"):
            coordinate = str(element.attrib.get("r") or "").upper()
            _validate_coordinate(coordinate)
            if coordinate in coordinates:
                _fail(
                    "invalid",
                    "duplicate_cell_coordinate",
                    "worksheet contains a duplicate cell coordinate",
                )
            coordinates.add(coordinate)
            data_type = str(element.attrib.get("t") or "")
            if data_type not in _CELL_TYPES:
                _fail(
                    "unsupported",
                    "unsupported_cell_type",
                    "worksheet uses an unsupported cell value type",
                )
            formula_element = next(
                (
                    child
                    for child in element
                    if _is_qname(child, spreadsheet_namespace, "f")
                ),
                None,
            )
            formula = (
                "".join(formula_element.itertext())
                if formula_element is not None
                else None
            )
            if formula is not None and len(formula) > budget.limits.max_formula_chars:
                _fail(
                    "budget_exceeded",
                    "formula_char_budget",
                    "an XLSX formula exceeds the character budget",
                )
            value = _cell_value(
                element,
                data_type,
                shared_strings,
                spreadsheet_namespace,
            )
            if len(value) > budget.limits.max_cell_value_chars:
                _fail(
                    "budget_exceeded",
                    "cell_value_budget",
                    "an XLSX cell value exceeds the character budget",
                )
            budget.consume_cell(value, formula)
            cells.append(
                CellSnapshot(
                    coordinate=coordinate,
                    value=value,
                    data_type=data_type or "number",
                    formula=formula,
                )
            )
            element.clear()
        elif _is_qname(element, spreadsheet_namespace, "row"):
            element.clear()
    if not root_seen:
        _fail("invalid", "missing_xml_root", "SpreadsheetML worksheet XML is empty")
    cells.sort(key=lambda cell: _coordinate_key(cell.coordinate))
    return tuple(cells)


def _cell_value(
    element: Any,
    data_type: str,
    shared_strings: tuple[str, ...],
    spreadsheet_namespace: str,
) -> str:
    if data_type == "inlineStr":
        return "".join(
            child.text or ""
            for child in element.iter()
            if _is_qname(child, spreadsheet_namespace, "t")
        )
    value_element = next(
        (
            child
            for child in element
            if _is_qname(child, spreadsheet_namespace, "v")
        ),
        None,
    )
    value = "" if value_element is None else "".join(value_element.itertext())
    if data_type == "s":
        try:
            index = int(value)
        except (TypeError, ValueError) as exc:
            raise XLSXSnapshotError(
                "invalid",
                "invalid_shared_string_index",
                "shared-string cell contains an invalid index",
            ) from exc
        if index < 0 or index >= len(shared_strings):
            _fail(
                "invalid",
                "invalid_shared_string_index",
                "shared-string cell index is outside the declared table",
            )
        return shared_strings[index]
    if data_type == "b" and value not in {"0", "1"}:
        _fail("invalid", "invalid_boolean_cell", "boolean cell must contain 0 or 1")
    return value


def _validate_coordinate(coordinate: str) -> None:
    match = _CELL_REFERENCE.fullmatch(coordinate)
    if match is None:
        _fail(
            "invalid",
            "invalid_cell_coordinate",
            "worksheet cell is missing a valid absolute coordinate",
        )
    column, row_text = match.groups()
    column_number = 0
    for character in column:
        column_number = column_number * 26 + ord(character) - ord("A") + 1
    if column_number > 16_384 or int(row_text) > 1_048_576:
        _fail(
            "invalid",
            "invalid_cell_coordinate",
            "worksheet cell coordinate exceeds XLSX bounds",
        )


def _coordinate_key(coordinate: str) -> tuple[int, int]:
    match = _CELL_REFERENCE.fullmatch(coordinate)
    assert match is not None
    column, row_text = match.groups()
    column_number = 0
    for character in column:
        column_number = column_number * 26 + ord(character) - ord("A") + 1
    return int(row_text), column_number


def _relationships_part_name(part_name: str) -> str:
    directory = posixpath.dirname(part_name)
    basename = posixpath.basename(part_name)
    return posixpath.join(directory, "_rels", basename + ".rels")


def _resolve_relationship_target(source_part: str, target: str) -> str:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        _fail(
            "security_blocked",
            "unsafe_relationship_target",
            "OOXML relationship target is not an internal package path",
        )
    try:
        decoded = unquote(parsed.path, errors="strict")
    except UnicodeError as exc:
        raise XLSXSnapshotError(
            "invalid", "invalid_relationship_target", "relationship target is invalid"
        ) from exc
    if not decoded or "\x00" in decoded or "\\" in decoded:
        _fail(
            "security_blocked",
            "unsafe_relationship_target",
            "OOXML relationship target contains an unsafe path",
        )
    decoded_parts = PurePosixPath(decoded.lstrip("/")).parts
    if any(part in {".", ".."} for part in decoded_parts):
        _fail(
            "security_blocked",
            "relationship_path_traversal",
            "OOXML relationship target contains a traversal component",
        )
    if decoded.startswith("/"):
        candidate = decoded.lstrip("/")
    else:
        candidate = posixpath.join(posixpath.dirname(source_part), decoded)
    normalized = posixpath.normpath(candidate)
    if (
        not normalized
        or normalized == "."
        or normalized.startswith("../")
        or normalized == ".."
        or normalized.startswith("/")
        or _DRIVE_PREFIX.match(normalized)
    ):
        _fail(
            "security_blocked",
            "relationship_path_traversal",
            "OOXML relationship escapes the package root",
        )
    _validate_member_name(normalized, is_directory=False)
    return normalized
