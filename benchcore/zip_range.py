"""Read selected members of a remote ZIP/ZIP64 archive with HTTP ranges.

This is intentionally extraction-free: member paths are never written to disk,
and CRC/size checks are mandatory.  It lets audit experiments verify visibility
inside very large immutable benchmark workspaces without downloading the whole
archive.
"""
from __future__ import annotations

import binascii
import hashlib
import re
import struct
import urllib.request
import zlib
from dataclasses import dataclass
from typing import Protocol


EOCD = b"PK\x05\x06"
ZIP64_EOCD = b"PK\x06\x06"
ZIP64_LOCATOR = b"PK\x06\x07"
CENTRAL_HEADER = b"PK\x01\x02"
LOCAL_HEADER = b"PK\x03\x04"
MAX32 = 0xFFFFFFFF
MAX16 = 0xFFFF


class RangeReadError(RuntimeError):
    pass


class RangeReader(Protocol):
    size: int

    def read(self, start: int, end: int) -> bytes:
        """Read the half-open byte range ``[start, end)`` exactly."""


class HTTPRangeReader:
    def __init__(self, url: str, *, timeout: float = 60.0) -> None:
        self.url = url
        self.timeout = timeout
        _, total = self._request("bytes=0-0")
        self.size = total

    def _request(self, value: str) -> tuple[bytes, int]:
        request = urllib.request.Request(self.url, headers={"Range": value})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = response.read()
            content_range = response.headers.get("Content-Range") or ""
            status = getattr(response, "status", None)
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
        if status != 206 or not match:
            raise RangeReadError(
                f"server did not honor byte range {value!r}: "
                f"status={status}, content-range={content_range!r}"
            )
        start, end, total = map(int, match.groups())
        if len(payload) != end - start + 1:
            raise RangeReadError("range response length does not match Content-Range")
        return payload, total

    def read(self, start: int, end: int) -> bytes:
        if not (0 <= start <= end <= self.size):
            raise ValueError(f"invalid range [{start}, {end}) for size {self.size}")
        if start == end:
            return b""
        payload, total = self._request(f"bytes={start}-{end - 1}")
        if total != self.size or len(payload) != end - start:
            raise RangeReadError("remote object changed or returned the wrong range")
        return payload


class BytesRangeReader:
    """In-memory reader used by tests and local callers."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.size = len(payload)

    def read(self, start: int, end: int) -> bytes:
        if not (0 <= start <= end <= self.size):
            raise ValueError("range outside payload")
        return self.payload[start:end]


@dataclass(frozen=True)
class RemoteZipEntry:
    name: str
    flags: int
    compression: int
    crc32: int
    compressed_size: int
    uncompressed_size: int
    local_header_offset: int


@dataclass(frozen=True)
class RemoteZipIndex:
    entries: tuple[RemoteZipEntry, ...]
    archive_size: int
    central_directory_offset: int
    central_directory_size: int
    central_directory_sha256: str

    def by_name(self, name: str) -> RemoteZipEntry | None:
        return next((entry for entry in self.entries if entry.name == name), None)


def read_zip_index(
    reader: RangeReader,
    *,
    max_central_directory_bytes: int = 128_000_000,
    max_entries: int = 1_000_000,
) -> RemoteZipIndex:
    tail_size = min(reader.size, 131_072)
    tail_start = reader.size - tail_size
    tail = reader.read(tail_start, reader.size)
    eocd_position = tail.rfind(EOCD)
    if eocd_position < 0 or eocd_position + 22 > len(tail):
        raise RangeReadError("ZIP end-of-central-directory record not found")
    _, disk, cd_disk, disk_entries, entries, cd_size, cd_offset, comment = struct.unpack_from(
        "<4s4H2LH", tail, eocd_position,
    )
    if eocd_position + 22 + comment != len(tail):
        # An EOCD signature inside a comment/member is not authoritative.
        raise RangeReadError("EOCD is not at the physical end of the archive")
    if disk or cd_disk:
        raise RangeReadError("multi-disk ZIP archives are unsupported")

    if entries == MAX16 or cd_size == MAX32 or cd_offset == MAX32:
        locator_position = eocd_position - 20
        if locator_position < 0 or tail[locator_position:locator_position + 4] != ZIP64_LOCATOR:
            raise RangeReadError("ZIP64 locator is missing")
        _, locator_disk, zip64_offset, total_disks = struct.unpack_from(
            "<4sLQL", tail, locator_position,
        )
        if locator_disk or total_disks != 1:
            raise RangeReadError("multi-disk ZIP64 archives are unsupported")
        record = reader.read(zip64_offset, min(reader.size, zip64_offset + 56))
        if len(record) < 56 or record[:4] != ZIP64_EOCD:
            raise RangeReadError("ZIP64 EOCD record is invalid")
        (
            _, record_size, _, _, zip_disk, zip_cd_disk, _, entries,
            cd_size, cd_offset,
        ) = struct.unpack_from("<4sQ2H2L4Q", record)
        if record_size < 44 or zip_disk or zip_cd_disk:
            raise RangeReadError("unsupported ZIP64 directory layout")
    if entries > max_entries:
        raise RangeReadError(f"central directory declares too many entries: {entries}")
    if cd_size > max_central_directory_bytes:
        raise RangeReadError(f"central directory exceeds byte budget: {cd_size}")
    if cd_offset + cd_size > reader.size:
        raise RangeReadError("central directory lies outside archive")

    payload = reader.read(cd_offset, cd_offset + cd_size)
    parsed: list[RemoteZipEntry] = []
    cursor = 0
    while cursor < len(payload):
        if cursor + 46 > len(payload) or payload[cursor:cursor + 4] != CENTRAL_HEADER:
            raise RangeReadError(f"invalid central header at offset {cursor}")
        values = struct.unpack_from("<4s6H3L5H2L", payload, cursor)
        flags, compression = values[3], values[4]
        crc32, compressed, uncompressed = values[7], values[8], values[9]
        name_len, extra_len, comment_len = values[10], values[11], values[12]
        disk_start, local_offset = values[13], values[16]
        end = cursor + 46 + name_len + extra_len + comment_len
        if end > len(payload):
            raise RangeReadError("truncated central directory entry")
        raw_name = payload[cursor + 46:cursor + 46 + name_len]
        extra = payload[
            cursor + 46 + name_len: cursor + 46 + name_len + extra_len
        ]
        encoding = "utf-8" if flags & 0x800 else "cp437"
        name = raw_name.decode(encoding)
        uncompressed, compressed, local_offset, disk_start = _resolve_zip64_extra(
            uncompressed, compressed, local_offset, disk_start, extra,
        )
        if disk_start:
            raise RangeReadError("entry is stored on another disk")
        parsed.append(RemoteZipEntry(
            name=name,
            flags=flags,
            compression=compression,
            crc32=crc32,
            compressed_size=compressed,
            uncompressed_size=uncompressed,
            local_header_offset=local_offset,
        ))
        cursor = end
    if len(parsed) != entries:
        raise RangeReadError(
            f"directory entry count mismatch: declared={entries}, parsed={len(parsed)}"
        )
    return RemoteZipIndex(
        entries=tuple(parsed),
        archive_size=reader.size,
        central_directory_offset=cd_offset,
        central_directory_size=cd_size,
        central_directory_sha256=hashlib.sha256(payload).hexdigest(),
    )


def _resolve_zip64_extra(
    uncompressed: int,
    compressed: int,
    local_offset: int,
    disk_start: int,
    extra: bytes,
) -> tuple[int, int, int, int]:
    zip64 = None
    cursor = 0
    while cursor + 4 <= len(extra):
        kind, size = struct.unpack_from("<HH", extra, cursor)
        end = cursor + 4 + size
        if end > len(extra):
            raise RangeReadError("truncated ZIP extra field")
        if kind == 0x0001:
            zip64 = extra[cursor + 4:end]
            break
        cursor = end
    values = [uncompressed, compressed, local_offset, disk_start]
    sentinels = [MAX32, MAX32, MAX32, MAX16]
    formats = ["<Q", "<Q", "<Q", "<L"]
    position = 0
    for index, (value, sentinel, fmt) in enumerate(zip(values, sentinels, formats)):
        if value != sentinel:
            continue
        if zip64 is None:
            raise RangeReadError("ZIP64 value is missing from extra field")
        size = struct.calcsize(fmt)
        if position + size > len(zip64):
            raise RangeReadError("truncated ZIP64 extra field")
        values[index] = struct.unpack_from(fmt, zip64, position)[0]
        position += size
    return tuple(values)  # type: ignore[return-value]


def read_zip_entry(
    reader: RangeReader,
    entry: RemoteZipEntry,
    *,
    max_uncompressed_bytes: int = 4_000_000,
) -> bytes:
    if entry.flags & 0x1:
        raise RangeReadError("encrypted ZIP members are unsupported")
    if entry.uncompressed_size > max_uncompressed_bytes:
        raise RangeReadError(
            f"member exceeds uncompressed byte budget: {entry.uncompressed_size}"
        )
    header = reader.read(entry.local_header_offset, entry.local_header_offset + 30)
    if len(header) != 30 or header[:4] != LOCAL_HEADER:
        raise RangeReadError("invalid local file header")
    values = struct.unpack("<4s5H3L2H", header)
    name_len, extra_len = values[-2], values[-1]
    data_start = entry.local_header_offset + 30 + name_len + extra_len
    compressed = reader.read(data_start, data_start + entry.compressed_size)
    if entry.compression == 0:
        output = compressed
    elif entry.compression == 8:
        try:
            output = zlib.decompress(compressed, -15)
        except zlib.error as exc:
            raise RangeReadError(f"deflate decompression failed: {exc}") from exc
    else:
        raise RangeReadError(f"unsupported compression method: {entry.compression}")
    if len(output) != entry.uncompressed_size:
        raise RangeReadError("uncompressed member length mismatch")
    if binascii.crc32(output) & 0xFFFFFFFF != entry.crc32:
        raise RangeReadError("ZIP member CRC mismatch")
    return output
