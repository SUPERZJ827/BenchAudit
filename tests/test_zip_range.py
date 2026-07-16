import io
import zipfile

import pytest

from benchcore.zip_range import (
    BytesRangeReader,
    RangeReadError,
    read_zip_entry,
    read_zip_index,
)


def make_zip() -> bytes:
    handle = io.BytesIO()
    with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("role/work/data/generate_answer.py", b"print('reference')\n")
        archive.writestr("role/work/data/source.txt", b"facts\n")
    return handle.getvalue()


def test_range_index_and_member_read_validate_archive():
    reader = BytesRangeReader(make_zip())

    index = read_zip_index(reader)
    entry = index.by_name("role/work/data/generate_answer.py")

    assert len(index.entries) == 2
    assert len(index.central_directory_sha256) == 64
    assert read_zip_entry(reader, entry) == b"print('reference')\n"


def test_member_byte_budget_is_fail_closed():
    reader = BytesRangeReader(make_zip())
    entry = read_zip_index(reader).by_name("role/work/data/generate_answer.py")

    with pytest.raises(RangeReadError, match="byte budget"):
        read_zip_entry(reader, entry, max_uncompressed_bytes=2)


def test_corrupted_member_fails_crc_or_decompression():
    payload = bytearray(make_zip())
    index = read_zip_index(BytesRangeReader(bytes(payload)))
    entry = index.by_name("role/work/data/source.txt")
    # Flip a byte in the member's compressed region while keeping its central
    # directory untouched.
    start = entry.local_header_offset + 30
    name_len = int.from_bytes(payload[start - 4:start - 2], "little")
    extra_len = int.from_bytes(payload[start - 2:start], "little")
    payload[start + name_len + extra_len] ^= 0x01

    with pytest.raises(RangeReadError):
        read_zip_entry(BytesRangeReader(bytes(payload)), entry)
