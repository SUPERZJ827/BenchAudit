from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
import warnings
import zipfile
from pathlib import Path

import pytest

import benchcore.ooxml_cells as ooxml_cells
from benchcore.ooxml_cells import (
    XLSXSnapshotError,
    XLSXSnapshotLimits,
    snapshot_xlsx,
)


SPREADSHEET_NS = (
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
)
STRICT_SPREADSHEET_NS = "http://purl.oclc.org/ooxml/spreadsheetml/main"
OFFICE_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
STRICT_OFFICE_REL_NS = (
    "http://purl.oclc.org/ooxml/officeDocument/relationships"
)
PACKAGE_REL_NS = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
WORKBOOK_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet.main+xml"
)
WORKSHEET_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.worksheet+xml"
)
SHARED_STRINGS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sharedStrings+xml"
)


def _minimal_parts() -> dict[str, bytes]:
    return {
        "[Content_Types].xml": f"""\
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="{WORKBOOK_CONTENT_TYPE}"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""".encode(),
        "_rels/.rels": f"""\
<Relationships xmlns="{PACKAGE_REL_NS}">
  <Relationship Id="rId1" Type="{OFFICE_REL_NS}/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""".encode(),
        "xl/workbook.xml": f"""\
<workbook xmlns="{SPREADSHEET_NS}" xmlns:r="{OFFICE_REL_NS}">
  <sheets><sheet name="Sheet One" sheetId="1" r:id="rId1"/></sheets>
</workbook>""".encode(),
        "xl/_rels/workbook.xml.rels": f"""\
<Relationships xmlns="{PACKAGE_REL_NS}">
  <Relationship Id="rId1" Type="{OFFICE_REL_NS}/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="{OFFICE_REL_NS}/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>""".encode(),
        "xl/sharedStrings.xml": f"""\
<sst xmlns="{SPREADSHEET_NS}" count="2" uniqueCount="2">
  <si><t>Header</t></si>
  <si><r><t>rich</t></r><r><t xml:space="preserve"> text</t></r></si>
</sst>""".encode(),
        "xl/worksheets/sheet1.xml": f"""\
<worksheet xmlns="{SPREADSHEET_NS}"><sheetData>
  <row r="2">
    <c r="C2"><f>SUM(A2,1)</f><v>43</v></c>
    <c r="B2" t="b"><v>1</v></c>
    <c r="A2"><v>42</v></c>
  </row>
  <row r="1">
    <c r="B1" t="inlineStr"><is><r><t>in</t></r><r><t>line</t></r></is></c>
    <c r="A1" t="s"><v>0</v></c>
  </row>
  <row r="3"><c r="A3" t="s"><v>1</v></c></row>
</sheetData></worksheet>""".encode(),
    }


def _write_xlsx(
    path: Path,
    *,
    overrides: dict[str, bytes | str] | None = None,
    extras: dict[str, bytes | str] | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> dict[str, bytes]:
    parts = _minimal_parts()
    for name, value in (overrides or {}).items():
        parts[name] = value.encode() if isinstance(value, str) else value
    for name, value in (extras or {}).items():
        parts[name] = value.encode() if isinstance(value, str) else value
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
    return parts


def _assert_error(
    path: Path,
    code: str,
    *,
    limits: XLSXSnapshotLimits | None = None,
) -> XLSXSnapshotError:
    with pytest.raises(XLSXSnapshotError) as caught:
        snapshot_xlsx(path, limits=limits)
    assert caught.value.code == code
    assert caught.value.status in {
        "invalid",
        "security_blocked",
        "budget_exceeded",
        "unsupported",
    }
    assert caught.value.to_dict()["message"]
    return caught.value


def _zip_flag_offsets(data: bytes) -> tuple[int, ...]:
    """Locate general-purpose flag fields in a small, non-ZIP64 fixture."""

    offsets: list[int] = []
    cursor = 0
    while cursor + 10 <= len(data):
        signature = data[cursor : cursor + 4]
        if signature == b"PK\x03\x04":
            offsets.append(cursor + 6)
            if cursor + 30 > len(data):
                break
            name_length, extra_length = struct.unpack_from("<HH", data, cursor + 26)
            compressed_size = struct.unpack_from("<I", data, cursor + 18)[0]
            cursor += 30 + name_length + extra_length + compressed_size
        elif signature == b"PK\x01\x02":
            offsets.append(cursor + 8)
            if cursor + 46 > len(data):
                break
            name_length, extra_length, comment_length = struct.unpack_from(
                "<HHH", data, cursor + 28
            )
            cursor += 46 + name_length + extra_length + comment_length
        else:
            cursor += 1
    return tuple(offsets)


def test_snapshot_is_deterministic_and_preserves_lexical_cell_evidence(
    tmp_path: Path,
):
    path = tmp_path / "evidence.xlsx"
    _write_xlsx(path)

    first = snapshot_xlsx(path)
    second = snapshot_xlsx(path)

    assert first == second
    assert first.file_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert first.file_size_bytes == path.stat().st_size
    assert first.sheet_names == ("Sheet One",)
    assert first.cell_count == 6
    assert first.sheets[0].part_name == "xl/worksheets/sheet1.xml"
    assert [cell.coordinate for cell in first.sheets[0].cells] == [
        "A1",
        "B1",
        "A2",
        "B2",
        "C2",
        "A3",
    ]
    cells = {cell.coordinate: cell for cell in first.sheets[0].cells}
    assert cells["A1"].value == "Header"
    assert cells["B1"].value == "inline"
    assert cells["A2"].value == "42"
    assert cells["A2"].data_type == "number"
    assert cells["B2"].value == "1"
    assert cells["C2"].formula == "SUM(A2,1)"
    assert cells["C2"].value == "43"
    assert cells["A3"].value == "rich text"
    assert json.loads(json.dumps(first.to_dict()))["cell_count"] == 6


def test_strict_spreadsheetml_namespace_dialect_is_supported(tmp_path: Path):
    path = tmp_path / "strict.xlsx"
    strict_parts = {
        name: value.replace(
            SPREADSHEET_NS.encode(), STRICT_SPREADSHEET_NS.encode()
        ).replace(OFFICE_REL_NS.encode(), STRICT_OFFICE_REL_NS.encode())
        for name, value in _minimal_parts().items()
    }
    _write_xlsx(path, overrides=strict_parts)

    snapshot = snapshot_xlsx(path)

    assert snapshot.parser_version == "benchcore-ooxml-cells/1.1"
    assert snapshot.sheet_names == ("Sheet One",)
    assert snapshot.cell_count == 6
    assert snapshot.sheets[0].cells[0].value == "Header"


@pytest.mark.parametrize(
    ("part_name", "expected_code"),
    [
        ("xl/workbook.xml", "unexpected_workbook_namespace"),
        ("xl/sharedStrings.xml", "unexpected_shared_strings_namespace"),
        ("xl/worksheets/sheet1.xml", "unexpected_worksheet_namespace"),
    ],
)
def test_custom_spreadsheetml_root_namespaces_fail_closed(
    tmp_path: Path,
    part_name: str,
    expected_code: str,
):
    path = tmp_path / f"custom-{Path(part_name).name}.xlsx"
    original = _minimal_parts()[part_name]
    malicious = original.replace(SPREADSHEET_NS.encode(), b"urn:attacker:sheet")
    _write_xlsx(path, overrides={part_name: malicious})

    error = _assert_error(path, expected_code)

    assert error.status == "security_blocked"


@pytest.mark.parametrize(
    "part_name",
    ["_rels/.rels", "xl/_rels/workbook.xml.rels"],
)
def test_custom_opc_relationship_namespaces_fail_closed(
    tmp_path: Path,
    part_name: str,
):
    path = tmp_path / f"custom-rel-{Path(part_name).name}.xlsx"
    malicious = _minimal_parts()[part_name].replace(
        PACKAGE_REL_NS.encode(), b"urn:attacker:relationships"
    )
    _write_xlsx(path, overrides={part_name: malicious})

    error = _assert_error(path, "unexpected_relationships_namespace")

    assert error.status == "security_blocked"


def test_custom_opc_content_types_namespace_fails_closed(tmp_path: Path):
    path = tmp_path / "custom-content-types.xlsx"
    malicious = _minimal_parts()["[Content_Types].xml"].replace(
        b"http://schemas.openxmlformats.org/package/2006/content-types",
        b"urn:attacker:content-types",
    )
    _write_xlsx(path, overrides={"[Content_Types].xml": malicious})

    error = _assert_error(path, "unexpected_content_types_namespace")

    assert error.status == "security_blocked"


def test_custom_namespace_cannot_inject_cell_shaped_elements(tmp_path: Path):
    path = tmp_path / "custom-cell-namespace.xlsx"
    malicious_sheet = f"""\
<worksheet xmlns="{SPREADSHEET_NS}" xmlns:evil="urn:attacker:sheet">
  <sheetData><row r="1"><evil:c r="A1"><evil:v>forged</evil:v></evil:c></row></sheetData>
</worksheet>"""
    _write_xlsx(
        path,
        overrides={"xl/worksheets/sheet1.xml": malicious_sheet},
    )

    error = _assert_error(path, "unexpected_spreadsheet_namespace")

    assert error.status == "security_blocked"


@pytest.mark.parametrize(
    ("declared_type", "replacement", "expected_code"),
    [
        (
            WORKSHEET_CONTENT_TYPE,
            "application/xml",
            "worksheet_content_type_mismatch",
        ),
        (
            SHARED_STRINGS_CONTENT_TYPE,
            "application/xml",
            "shared_strings_content_type_mismatch",
        ),
    ],
)
def test_relationship_parts_require_exact_content_type_overrides(
    tmp_path: Path,
    declared_type: str,
    replacement: str,
    expected_code: str,
):
    path = tmp_path / f"bad-{expected_code}.xlsx"
    content_types = _minimal_parts()["[Content_Types].xml"].replace(
        declared_type.encode(), replacement.encode()
    )
    _write_xlsx(path, overrides={"[Content_Types].xml": content_types})

    error = _assert_error(path, expected_code)

    assert error.status == "security_blocked"


def test_mixed_strict_and_transitional_relationship_types_fail_closed(
    tmp_path: Path,
):
    path = tmp_path / "mixed-dialect.xlsx"
    strict_parts = {
        name: value.replace(
            SPREADSHEET_NS.encode(), STRICT_SPREADSHEET_NS.encode()
        ).replace(OFFICE_REL_NS.encode(), STRICT_OFFICE_REL_NS.encode())
        for name, value in _minimal_parts().items()
    }
    strict_parts["xl/_rels/workbook.xml.rels"] = strict_parts[
        "xl/_rels/workbook.xml.rels"
    ].replace(
        f'{STRICT_OFFICE_REL_NS}/worksheet'.encode(),
        f'{OFFICE_REL_NS}/worksheet'.encode(),
    )
    _write_xlsx(path, overrides=strict_parts)

    error = _assert_error(path, "mixed_ooxml_dialect")

    assert error.status == "security_blocked"


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="requires O_NOFOLLOW")
def test_source_symlink_and_symlinked_ancestor_are_refused(tmp_path: Path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    workbook = real_dir / "book.xlsx"
    _write_xlsx(workbook)

    file_link = tmp_path / "book-link.xlsx"
    file_link.symlink_to(workbook)
    _assert_error(file_link, "source_open_refused")

    directory_link = tmp_path / "directory-link"
    directory_link.symlink_to(real_dir, target_is_directory=True)
    _assert_error(
        directory_link / "book.xlsx", "source_path_component_refused"
    )


def test_source_metadata_change_is_detected_after_same_descriptor_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "race.xlsx"
    _write_xlsx(path)
    monkeypatch.setattr(ooxml_cells, "_same_file_state", lambda _a, _b: False)

    error = _assert_error(path, "source_changed_during_snapshot")

    assert error.status == "security_blocked"


@pytest.mark.parametrize("unsafe_name", ["../escape.xml", "/absolute.xml", "a\\b.xml"])
def test_unsafe_zip_member_paths_are_rejected(tmp_path: Path, unsafe_name: str):
    path = tmp_path / "traversal.xlsx"
    _write_xlsx(path, extras={unsafe_name: b"ignored"})

    error = _assert_error(path, "unsafe_archive_member")

    assert error.status == "security_blocked"


def test_duplicate_and_casefold_ambiguous_zip_members_are_rejected(tmp_path: Path):
    duplicate = tmp_path / "duplicate.xlsx"
    _write_xlsx(duplicate)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(duplicate, "a") as archive:
            archive.writestr("[Content_Types].xml", b"<duplicate/>")
    _assert_error(duplicate, "duplicate_archive_member")

    ambiguous = tmp_path / "ambiguous.xlsx"
    _write_xlsx(ambiguous, extras={"XL/WORKBOOK.XML": b"<ambiguous/>"})
    _assert_error(ambiguous, "duplicate_archive_member")


def test_archive_symlink_member_is_rejected(tmp_path: Path):
    path = tmp_path / "member-link.xlsx"
    parts = _minimal_parts()
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
        link = zipfile.ZipInfo("xl/linked.xml")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"workbook.xml")

    _assert_error(path, "archive_symlink_member")


def test_encrypted_member_flag_is_rejected_before_decompression(tmp_path: Path):
    path = tmp_path / "encrypted-flag.xlsx"
    _write_xlsx(path)
    data = bytearray(path.read_bytes())
    offsets = _zip_flag_offsets(data)
    assert offsets
    for offset in offsets:
        flags = struct.unpack_from("<H", data, offset)[0]
        struct.pack_into("<H", data, offset, flags | 0x1)
    path.write_bytes(data)

    error = _assert_error(path, "encrypted_archive_member")

    assert error.status == "security_blocked"


def test_high_compression_ratio_is_rejected_from_declared_metadata(tmp_path: Path):
    path = tmp_path / "bomb.xlsx"
    _write_xlsx(path, extras={"xl/bomb.bin": b"A" * 200_000})
    limits = XLSXSnapshotLimits(max_compression_ratio=10)

    error = _assert_error(path, "archive_compression_ratio", limits=limits)

    assert error.status == "security_blocked"


def test_xml_entities_are_forbidden_even_when_declared_in_a_required_part(
    tmp_path: Path,
):
    path = tmp_path / "entity.xlsx"
    malicious_workbook = f"""\
<!DOCTYPE workbook [<!ENTITY secret SYSTEM "file:///etc/passwd">]>
<workbook xmlns="{SPREADSHEET_NS}" xmlns:r="{OFFICE_REL_NS}">
  <sheets><sheet name="&secret;" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    _write_xlsx(path, overrides={"xl/workbook.xml": malicious_workbook})

    error = _assert_error(path, "forbidden_xml_declaration")

    assert error.status == "security_blocked"


@pytest.mark.parametrize("target", ["../worksheets/sheet1.xml", "%2e%2e/secret.xml"])
def test_relationship_traversal_is_rejected_before_member_lookup(
    tmp_path: Path, target: str
):
    path = tmp_path / "relationship-traversal.xlsx"
    relationships = f"""\
<Relationships xmlns="{PACKAGE_REL_NS}">
  <Relationship Id="rId1" Type="{OFFICE_REL_NS}/worksheet" Target="{target}"/>
</Relationships>"""
    _write_xlsx(
        path, overrides={"xl/_rels/workbook.xml.rels": relationships}
    )

    error = _assert_error(path, "relationship_path_traversal")

    assert error.status == "security_blocked"


def test_external_worksheet_relationship_is_never_fetched(tmp_path: Path):
    path = tmp_path / "external.xlsx"
    relationships = f"""\
<Relationships xmlns="{PACKAGE_REL_NS}">
  <Relationship Id="rId1" Type="{OFFICE_REL_NS}/worksheet" Target="https://example.invalid/sheet.xml" TargetMode="External"/>
</Relationships>"""
    _write_xlsx(
        path, overrides={"xl/_rels/workbook.xml.rels": relationships}
    )

    error = _assert_error(path, "external_worksheet_relationship")

    assert error.status == "security_blocked"


def test_workbook_part_must_match_content_type_declaration(tmp_path: Path):
    path = tmp_path / "mismatch.xlsx"
    content_types = _minimal_parts()["[Content_Types].xml"].decode().replace(
        '/xl/workbook.xml" ContentType=',
        '/xl/other-workbook.xml" ContentType=',
    )
    _write_xlsx(path, overrides={"[Content_Types].xml": content_types})

    error = _assert_error(path, "workbook_part_mismatch")

    assert error.status == "security_blocked"


def test_macro_enabled_workbook_content_type_is_unsupported(tmp_path: Path):
    path = tmp_path / "macro.xlsm"
    content_types = _minimal_parts()["[Content_Types].xml"].decode().replace(
        WORKBOOK_CONTENT_TYPE,
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
    )
    _write_xlsx(path, overrides={"[Content_Types].xml": content_types})

    error = _assert_error(path, "macro_enabled_workbook")

    assert error.status == "unsupported"


def test_duplicate_cells_and_invalid_shared_string_indexes_fail_closed(
    tmp_path: Path,
):
    duplicate = tmp_path / "duplicate-cell.xlsx"
    duplicate_sheet = f"""\
<worksheet xmlns="{SPREADSHEET_NS}"><sheetData><row r="1">
  <c r="A1"><v>1</v></c><c r="a1"><v>2</v></c>
</row></sheetData></worksheet>"""
    _write_xlsx(
        duplicate, overrides={"xl/worksheets/sheet1.xml": duplicate_sheet}
    )
    _assert_error(duplicate, "duplicate_cell_coordinate")

    bad_index = tmp_path / "bad-index.xlsx"
    invalid_index_sheet = f"""\
<worksheet xmlns="{SPREADSHEET_NS}"><sheetData><row r="1">
  <c r="A1" t="s"><v>999</v></c>
</row></sheetData></worksheet>"""
    _write_xlsx(
        bad_index, overrides={"xl/worksheets/sheet1.xml": invalid_index_sheet}
    )
    _assert_error(bad_index, "invalid_shared_string_index")


def test_cell_and_xml_resource_budgets_are_explicit(tmp_path: Path):
    path = tmp_path / "budget.xlsx"
    _write_xlsx(path)

    cell_error = _assert_error(
        path,
        "cell_count_budget",
        limits=XLSXSnapshotLimits(max_cells=2),
    )
    assert cell_error.status == "budget_exceeded"

    element_error = _assert_error(
        path,
        "xml_element_budget",
        limits=XLSXSnapshotLimits(max_xml_elements=2),
    )
    assert element_error.status == "budget_exceeded"


def test_limit_configuration_rejects_invalid_or_incoherent_values():
    with pytest.raises(ValueError):
        XLSXSnapshotLimits(max_cells=0)
    with pytest.raises(ValueError):
        XLSXSnapshotLimits(max_compression_ratio=float("inf"))
    with pytest.raises(ValueError):
        XLSXSnapshotLimits(
            max_member_uncompressed_bytes=2_000,
            max_total_uncompressed_bytes=1_000,
        )
