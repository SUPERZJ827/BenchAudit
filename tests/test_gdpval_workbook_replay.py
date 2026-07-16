"""Execution-style regression tests for GDPval XLSX header replay.

The workbooks are generated locally and the resolver is a cache-only fake.  No
test depends on a public GDPval artifact, network access, or a task-specific
identifier.
"""

from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
from xml.sax.saxutils import escape

import pytest

from benchcore.gdpval_objective import (
    GDPValWorkbookReplayChecker,
    build_gdpval_items,
    replay_workbook_fact,
)
from benchcore.auditor import audit_items_with_ledger
from benchcore.schema import BenchmarkItem, Violation


REVISION = "a" * 40
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
WORKBOOK_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet.main+xml"
)


def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://example.invalid/{label}"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_workbook(path: Path, headers: dict[str, str]) -> Path:
    cells = "\n".join(
        f'<c r="{escape(coordinate)}" t="inlineStr"><is><t>'
        f"{escape(value)}</t></is></c>"
        for coordinate, value in sorted(headers.items())
    )
    parts = {
        "[Content_Types].xml": f"""\
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="{WORKBOOK_CONTENT_TYPE}"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        "_rels/.rels": f"""\
<Relationships xmlns="{PACKAGE_REL_NS}">
  <Relationship Id="rId1" Type="{OFFICE_REL_NS}/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        "xl/workbook.xml": f"""\
<workbook xmlns="{SPREADSHEET_NS}" xmlns:r="{OFFICE_REL_NS}">
  <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        "xl/_rels/workbook.xml.rels": f"""\
<Relationships xmlns="{PACKAGE_REL_NS}">
  <Relationship Id="rId1" Type="{OFFICE_REL_NS}/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        "xl/worksheets/sheet1.xml": f"""\
<worksheet xmlns="{SPREADSHEET_NS}"><sheetData>
  <row r="1">{cells}</row>
</sheetData></worksheet>""",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value.encode("utf-8"))
    return path


@dataclass(frozen=True)
class FakeResolvedArtifact:
    revision: str
    declared_path: str
    sha256: str
    size_bytes: int
    materialized_path: Path

    def to_evidence(self) -> dict[str, Any]:
        return {"resolver_schema_version": "synthetic-local-resolver/v1"}


class FakeResolver:
    """Immutable declared-path bindings with an intentionally simple receipt."""

    def __init__(self, bindings: dict[str, Path], *, revision: str = REVISION) -> None:
        self.revision = revision
        self.calls: list[tuple[str, bool]] = []
        self._resolved = {
            declared: FakeResolvedArtifact(
                revision=revision,
                declared_path=declared,
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
                materialized_path=path,
            )
            for declared, path in bindings.items()
        }

    def resolve(
        self,
        declared_path: str,
        *,
        allow_download: bool = False,
    ) -> FakeResolvedArtifact:
        self.calls.append((declared_path, allow_download))
        if allow_download:
            raise AssertionError("synthetic workbook replay must remain cache-only")
        try:
            return self._resolved[declared_path]
        except KeyError as exc:
            raise AssertionError(f"undeclared fake artifact: {declared_path}") from exc


def rubric_item(criterion: str, *, label: str) -> dict[str, Any]:
    return {
        "score": 1,
        "criterion": criterion,
        "required": None,
        "rubric_item_id": stable_uuid(label),
        "author_type": "human",
        "tags": ["true"],
        "read_only": None,
    }


def artifact_columns(paths: tuple[str, ...]) -> tuple[list[str], list[str], list[str]]:
    urls = []
    hf_uris = []
    for path in paths:
        encoded = quote(path, safe="/")
        urls.append(
            f"https://huggingface.co/datasets/openai/gdpval/resolve/main/{encoded}"
        )
        hf_uris.append(f"hf://datasets/openai/gdpval@main/{encoded}")
    return list(paths), urls, hf_uris


def make_row(
    *,
    prompt: str,
    rubrics: list[dict[str, Any]],
    reference_paths: tuple[str, ...] = (),
    deliverable_paths: tuple[str, ...] = (),
    label: str = "workbook-task",
) -> dict[str, Any]:
    references, reference_urls, reference_hf = artifact_columns(reference_paths)
    deliverables, deliverable_urls, deliverable_hf = artifact_columns(
        deliverable_paths
    )
    return {
        "task_id": stable_uuid(label),
        "sector": "Synthetic Services",
        "occupation": "Synthetic Analyst",
        "prompt": prompt,
        "reference_files": references,
        "reference_file_urls": reference_urls,
        "reference_file_hf_uris": reference_hf,
        "deliverable_files": deliverables,
        "deliverable_file_urls": deliverable_urls,
        "deliverable_file_hf_uris": deliverable_hf,
        "rubric_pretty": "\n".join(
            f"[{int(item['score']):+d}] {item['criterion']}" for item in rubrics
        ),
        "rubric_json": json.dumps(rubrics),
    }


def make_item(row: dict[str, Any]) -> BenchmarkItem:
    return build_gdpval_items([row])[0]


def run_checker(
    item: BenchmarkItem,
    resolver: FakeResolver,
) -> list[Violation]:
    return list(GDPValWorkbookReplayChecker(resolver).check(item))


def evidence_atom(violation: Violation) -> dict[str, Any]:
    atom = violation.evidence.get("atom")
    assert isinstance(atom, dict)
    return atom


def test_clean_workbook_headers_emit_no_finding(tmp_path: Path) -> None:
    reference_declared = "reference_files/synthetic/population.xlsx"
    deliverable_declared = "deliverable_files/synthetic/sample.xlsx"
    reference = write_workbook(
        tmp_path / "population.xlsx",
        {"C1": "Q2", "D1": "Q3"},
    )
    deliverable = write_workbook(
        tmp_path / "sample.xlsx",
        {"F1": "Variance", "G1": "Sample Selected"},
    )
    row = make_row(
        prompt="Q2 and Q3 data are stored in columns C and D.",
        rubrics=[
            rubric_item(
                "The variance is shown in column F on the first worksheet.",
                label="clean-var",
            ),
            rubric_item(
                "Sampled rows are marked in column G on the first worksheet.",
                label="clean-sample",
            ),
        ],
        reference_paths=(reference_declared,),
        deliverable_paths=(deliverable_declared,),
    )
    resolver = FakeResolver({
        reference_declared: reference,
        deliverable_declared: deliverable,
    })

    assert run_checker(make_item(row), resolver) == []
    assert resolver.calls == [
        (reference_declared, False),
        (deliverable_declared, False),
    ]


def test_task_and_rubric_column_mismatches_are_separate_facts(
    tmp_path: Path,
) -> None:
    reference_declared = "reference_files/synthetic/population.xlsx"
    deliverable_declared = "deliverable_files/synthetic/sample.xlsx"
    reference = write_workbook(
        tmp_path / "population.xlsx",
        {"C1": "Q2", "D1": "Q3"},
    )
    deliverable = write_workbook(
        tmp_path / "sample.xlsx",
        {"F1": "Variance", "G1": "Sample Selected"},
    )
    row = make_row(
        prompt="Q2 and Q3 data are stored in columns D and E.",
        rubrics=[
            rubric_item(
                "The variance is shown in column H on the first worksheet.",
                label="wrong-var",
            ),
            rubric_item(
                "Sampled rows are marked in column G on the first worksheet.",
                label="right-sample",
            ),
        ],
        reference_paths=(reference_declared,),
        deliverable_paths=(deliverable_declared,),
    )
    resolver = FakeResolver({
        reference_declared: reference,
        deliverable_declared: deliverable,
    })

    findings = run_checker(make_item(row), resolver)

    assert {finding.defect_type for finding in findings} == {
        "task_artifact_contract_mismatch",
        "rubric_artifact_contract_mismatch",
    }
    by_source = {
        evidence_atom(finding)["claim_source"]: evidence_atom(finding)
        for finding in findings
    }
    assert {
        (row["role"], row["expected_column"], tuple(row["observed_columns"]))
        for row in by_source["task"]["mismatches"]
    } == {
        ("q2", "D", ("C",)),
        ("q3", "E", ("D",)),
    }
    assert [
        (
            mismatch["role"],
            mismatch["expected_column"],
            mismatch["observed_columns"],
        )
        for mismatch in by_source["rubric"]["mismatches"]
    ] == [("variance", "H", ["F"])]


def test_promotion_replays_the_real_local_workbook_fact(tmp_path: Path) -> None:
    declared = "reference_files/synthetic/population.xlsx"
    workbook = write_workbook(
        tmp_path / "population.xlsx",
        {"C1": "Q2", "D1": "Q3"},
    )
    row = make_row(
        prompt="Q2 and Q3 data are stored in columns D and E.",
        rubrics=[rubric_item("The report contains a summary.", label="summary")],
        reference_paths=(declared,),
    )
    item = make_item(row)
    resolver = FakeResolver({declared: workbook})

    findings = run_checker(item, resolver)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.evidence_tier == "confirmed"
    assert not finding.review_only
    assert finding.proof_kind == "deterministic_replay"
    assert "exact versioned" in finding.promotion_reason
    # One read creates the fact; the second is the promotion validator's
    # independent cache-only replay.
    assert resolver.calls == [(declared, False), (declared, False)]
    assert replay_workbook_fact(finding, item)
    assert resolver.calls == [
        (declared, False),
        (declared, False),
        (declared, False),
    ]
    assert finding.evidence["artifacts"][0]["artifact_sha256"] == sha256_file(
        workbook
    )


def test_title_row_is_not_used_as_the_header_ground_truth(tmp_path: Path) -> None:
    declared = "reference_files/synthetic/population.xlsx"
    workbook = write_workbook(
        tmp_path / "population.xlsx",
        {
            "A1": "Q2 overview",
            "B1": "Q3 overview",
            "H3": "Q2 2024 KRI",
            "I3": "Q3 2024 KRI",
        },
    )
    row = make_row(
        prompt="Q2 and Q3 data are stored in columns H and I.",
        rubrics=[rubric_item("The report contains a summary.", label="title")],
        reference_paths=(declared,),
    )
    resolver = FakeResolver({declared: workbook})

    assert run_checker(make_item(row), resolver) == []


def test_artifact_sha_tampering_fails_closed_before_finding(
    tmp_path: Path,
) -> None:
    declared = "reference_files/synthetic/population.xlsx"
    workbook = write_workbook(
        tmp_path / "population.xlsx",
        {"C1": "Q2", "D1": "Q3"},
    )
    resolver = FakeResolver({declared: workbook})
    # The resolver receipt is now bound. Re-saving different bytes simulates a
    # cache/view mutation after receipt creation.
    write_workbook(workbook, {"E1": "Q2", "F1": "Q3"})
    row = make_row(
        prompt="Q2 and Q3 data are stored in columns C and D.",
        rubrics=[rubric_item("The report contains a summary.", label="tamper")],
        reference_paths=(declared,),
    )

    with pytest.raises(ValueError, match="digest differs from resolver receipt"):
        run_checker(make_item(row), resolver)

    assert resolver.calls == [(declared, False)]


def test_multiple_xlsx_artifacts_do_not_trigger_role_guessing(
    tmp_path: Path,
) -> None:
    first_declared = "reference_files/synthetic/first.xlsx"
    second_declared = "reference_files/synthetic/second.xlsx"
    first = write_workbook(tmp_path / "first.xlsx", {"C1": "Q2", "D1": "Q3"})
    second = write_workbook(tmp_path / "second.xlsx", {"E1": "Q2", "F1": "Q3"})
    row = make_row(
        prompt="Q2 and Q3 data are stored in columns A and B.",
        rubrics=[rubric_item("The report contains a summary.", label="multi")],
        reference_paths=(first_declared, second_declared),
    )
    resolver = FakeResolver({first_declared: first, second_declared: second})

    item = make_item(row)
    checker = GDPValWorkbookReplayChecker(resolver)
    result = audit_items_with_ledger([item], checkers=[checker])

    assert result.violations == []
    assert len(result.ledger) == 1
    assert result.ledger[0].status == "unsupported"
    assert result.ledger[0].completed is False
    assert resolver.calls == []
