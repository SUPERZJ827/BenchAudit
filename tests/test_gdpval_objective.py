"""Regression contracts for the deterministic GDPval objective audit.

All examples are synthetic.  The tests exercise general predicates and never
key behavior on a published GDPval task ID, person, filename, or rubric text.
"""

from __future__ import annotations

import json
import uuid
from hashlib import sha256
from urllib.parse import quote

import pytest

from benchcore.promotion import enforce_promotion_policy
from benchcore.gdpval_objective import (
    GDPValDatasetIntegrityChecker,
    GDPValRecordIntegrityChecker,
    build_gdpval_items,
    extract_column_claims,
    parse_rubrics,
)
from benchcore.schema import BenchmarkItem, Violation


def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://example.invalid/{label}"))


def rubric_item(
    criterion: str,
    *,
    score: int = 1,
    label: str | None = None,
    include_form_content: bool = True,
) -> dict:
    row = {
        "score": score,
        "criterion": criterion,
        "required": None,
        "rubric_item_id": stable_uuid(label or criterion),
        "author_type": "human",
        "tags": ["true"],
        "read_only": None,
    }
    if include_form_content:
        row["form_content"] = None
    return row


def render_pretty(rubrics: list[dict]) -> str:
    return "\n".join(
        f"[{int(row['score']):+d}] {row['criterion']}" for row in rubrics
    )


def artifact_triplet(role: str, filename: str, *, label: str) -> tuple[str, str, str]:
    digest = sha256(label.encode("utf-8")).hexdigest()[:32]
    path = f"{role}_files/{digest}/{filename}"
    encoded = quote(path, safe="/")
    return (
        path,
        f"https://huggingface.co/datasets/openai/gdpval/resolve/main/{encoded}",
        f"hf://datasets/openai/gdpval@main/{encoded}",
    )


def make_row(
    *,
    prompt: str = "Use the attached source to prepare the requested report.",
    rubrics: list[dict] | None = None,
    references: tuple[str, ...] = ("source.xlsx",),
    deliverables: tuple[str, ...] = ("report.docx",),
    task_label: str = "clean-task",
) -> dict:
    rubrics = rubrics or [rubric_item("The report contains a clear summary.")]
    reference_triplets = [
        artifact_triplet("reference", name, label=f"{task_label}-ref-{index}")
        for index, name in enumerate(references)
    ]
    deliverable_triplets = [
        artifact_triplet("deliverable", name, label=f"{task_label}-gold-{index}")
        for index, name in enumerate(deliverables)
    ]
    return {
        "task_id": stable_uuid(task_label),
        "sector": "Synthetic Services",
        "occupation": "Synthetic Reviewer",
        "prompt": prompt,
        "reference_files": [row[0] for row in reference_triplets],
        "reference_file_urls": [row[1] for row in reference_triplets],
        "reference_file_hf_uris": [row[2] for row in reference_triplets],
        "deliverable_files": [row[0] for row in deliverable_triplets],
        "deliverable_file_urls": [row[1] for row in deliverable_triplets],
        "deliverable_file_hf_uris": [row[2] for row in deliverable_triplets],
        "rubric_pretty": render_pretty(rubrics),
        "rubric_json": json.dumps(rubrics, ensure_ascii=False),
    }


def item_for(row: dict) -> BenchmarkItem:
    return build_gdpval_items([row])[0]


def record_findings(row: dict) -> list[Violation]:
    return list(GDPValRecordIntegrityChecker().check(item_for(row)))


def dataset_findings(rows: list[dict]) -> list[Violation]:
    return list(GDPValDatasetIntegrityChecker().check(build_gdpval_items(rows)))


def atom(violation: Violation) -> dict:
    value = violation.evidence.get("atom")
    assert isinstance(value, dict), "objective findings must expose evidence.atom"
    assert isinstance(value.get("kind"), str) and value["kind"]
    return value


def findings_of_kind(
    violations: list[Violation], kind: str,
) -> list[tuple[Violation, dict]]:
    return [
        (violation, atom(violation))
        for violation in violations
        if atom(violation)["kind"] == kind
    ]


# ---------------------------------------------------------------------------
# Structured rubric parsing and readable/JSON representation replay


def test_parse_rubrics_is_lossless_and_preserves_order() -> None:
    source = [
        rubric_item("First requirement.", score=2, label="parse-first"),
        rubric_item(
            "Penalty requirement.", score=-5, label="parse-second",
            include_form_content=False,
        ),
    ]

    assert parse_rubrics(json.dumps(source)) == source


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        '{"criterion":"not a list"}',
        "[]",
        '[{"score": 1, "criterion": ""}]',
        '[{"score": "one", "criterion": "text"}]',
    ],
)
def test_parse_rubrics_fails_closed_on_invalid_json_or_shape(payload: str) -> None:
    with pytest.raises(ValueError, match="rubric_json"):
        parse_rubrics(payload)


def test_bad_rubric_json_is_reported_without_row_level_crash() -> None:
    row = make_row()
    row["rubric_json"] = "["

    matches = findings_of_kind(
        record_findings(row), "json_parse_or_shape_error",
    )

    assert len(matches) == 1
    violation, evidence = matches[0]
    assert violation.defect_type == "rubric_representation_mismatch"
    assert violation.evidence["evidence_level"] == (
        "gdpval_rubric_representation_replay"
    )
    assert evidence["error_type"] == "ValueError"


def test_unparseable_pretty_rubric_is_reported() -> None:
    row = make_row()
    row["rubric_pretty"] = "plain prose without score markers"

    matches = findings_of_kind(record_findings(row), "pretty_parse_error")

    assert len(matches) == 1
    assert matches[0][0].defect_type == "rubric_representation_mismatch"


def test_pretty_and_json_content_mismatch_identifies_first_index() -> None:
    rubrics = [
        rubric_item("First requirement.", label="pretty-first"),
        rubric_item("Second requirement.", score=2, label="pretty-second"),
    ]
    row = make_row(rubrics=rubrics)
    row["rubric_pretty"] = (
        "[+1] First requirement.\n[+2] A different second requirement."
    )

    matches = findings_of_kind(
        record_findings(row), "pretty_json_content_mismatch",
    )

    assert len(matches) == 1
    assert matches[0][1]["first_mismatch_index"] == 1
    assert matches[0][1]["pretty_item_count"] == 2
    assert matches[0][1]["json_item_count"] == 2


def test_pretty_whitespace_and_negative_scores_round_trip() -> None:
    rubrics = [rubric_item("A penalty condition.", score=-2)]
    row = make_row(rubrics=rubrics)
    row["rubric_pretty"] = "  [-2]   A penalty condition.  \n"

    assert record_findings(row) == []


# ---------------------------------------------------------------------------
# Three-view artifact manifest replay


def test_clean_and_empty_artifact_manifests_are_valid() -> None:
    assert record_findings(make_row()) == []
    assert record_findings(make_row(references=(), deliverables=())) == []


def test_manifest_cardinality_mismatch_records_role_fields_and_lengths() -> None:
    row = make_row(references=("one.pdf", "two.xlsx"))
    row["reference_file_urls"].pop()

    matches = findings_of_kind(record_findings(row), "artifact_triplet_mismatch")

    assert len(matches) == 1
    violation, evidence = matches[0]
    assert violation.defect_type == "artifact_reference_manifest_mismatch"
    assert evidence["artifact_role"] == "reference"
    assert evidence["source_fields"] == [
        "reference_files",
        "reference_file_urls",
        "reference_file_hf_uris",
    ]
    assert evidence["lengths"] == [2, 1, 2]
    assert evidence["mismatches"] == []


def test_manifest_decodes_percent_encoded_basenames_before_comparison() -> None:
    row = make_row(references=("source workbook (final).xlsx",))

    assert record_findings(row) == []


def test_manifest_basename_disagreement_is_localized_to_entry() -> None:
    row = make_row(references=("source workbook.xlsx",))
    row["reference_file_urls"][0] = row["reference_file_urls"][0].replace(
        "source%20workbook.xlsx", "different.xlsx",
    )

    matches = findings_of_kind(record_findings(row), "artifact_triplet_mismatch")

    assert len(matches) == 1
    mismatch = matches[0][1]["mismatches"]
    assert len(mismatch) == 1
    assert mismatch[0]["index"] == 0
    assert mismatch[0]["reasons"] == [
        "basename_disagreement",
        "https_artifact_path_disagreement",
    ]


def test_manifest_rejects_unsafe_paths_and_unexpected_origins() -> None:
    row = make_row(references=("source.pdf",))
    row["reference_files"][0] = "reference_files/../private/source.pdf"
    row["reference_file_urls"][0] = (
        "https://example.invalid/datasets/openai/gdpval/source.pdf"
    )

    matches = findings_of_kind(record_findings(row), "artifact_triplet_mismatch")

    assert len(matches) == 1
    reasons = set(matches[0][1]["mismatches"][0]["reasons"])
    assert reasons == {
        "hf_artifact_path_disagreement",
        "unexpected_https_dataset_path",
        "unexpected_https_url_origin",
        "unsafe_or_invalid_relative_path",
    }


def test_manifest_binds_full_openai_repo_path_and_revision() -> None:
    row = make_row(references=("source.pdf",))
    declared = row["reference_files"][0]
    row["reference_file_urls"][0] = (
        f"https://huggingface.co/datasets/evil/repo/resolve/deadbeef/{declared}"
    )
    row["reference_file_hf_uris"][0] = (
        f"hf://datasets/evil/repo@deadbeef/{declared}"
    )

    matches = findings_of_kind(record_findings(row), "artifact_triplet_mismatch")

    assert len(matches) == 1
    reasons = set(matches[0][1]["mismatches"][0]["reasons"])
    assert "unexpected_https_dataset_path" in reasons
    assert "unexpected_hf_dataset_path" in reasons


def test_malformed_manifest_url_becomes_finding_instead_of_crashing() -> None:
    row = make_row(references=("source.pdf",))
    row["reference_file_urls"][0] = "https://["

    matches = findings_of_kind(record_findings(row), "artifact_triplet_mismatch")

    assert len(matches) == 1
    assert "malformed_https_url" in matches[0][1]["mismatches"][0]["reasons"]


def test_missing_required_field_is_an_objective_schema_finding() -> None:
    row = make_row()
    row.pop("reference_file_urls")

    matches = findings_of_kind(
        record_findings(row), "gdpval_record_schema_mismatch",
    )

    assert len(matches) == 1
    violation, evidence = matches[0]
    assert violation.defect_type == "gdpval_schema_mismatch"
    assert violation.evidence_tier == "confirmed"
    assert evidence["missing_fields"] == ["reference_file_urls"]


# ---------------------------------------------------------------------------
# Duplicate rubric structure


def test_normalized_duplicate_criterion_is_review_only_with_scores_and_ids() -> None:
    rubrics = [
        rubric_item("The report contains a signed summary.", score=2, label="dup-a"),
        rubric_item("  THE REPORT contains a signed summary.  ", label="dup-b"),
    ]

    matches = findings_of_kind(
        record_findings(make_row(rubrics=rubrics)),
        "duplicate_rubric_criterion",
    )

    assert len(matches) == 1
    violation, evidence = matches[0]
    assert violation.defect_type == "duplicate_rubric_criterion"
    assert violation.review_only
    assert evidence["indices"] == [0, 1]
    assert evidence["rubric_item_ids"] == [stable_uuid("dup-a"), stable_uuid("dup-b")]
    assert evidence["scores"] == [2, 1]
    assert len(evidence["criterion_sha256"]) == 64


def test_templated_but_distinct_criteria_are_not_duplicates() -> None:
    row = make_row(rubrics=[
        rubric_item("The table reports the total for Carrier North.", label="north"),
        rubric_item("The table reports the total for Carrier South.", label="south"),
    ])

    assert findings_of_kind(
        record_findings(row), "duplicate_rubric_criterion",
    ) == []


def test_reused_rubric_id_inside_one_record_is_not_hidden_by_distinct_text() -> None:
    shared = stable_uuid("within-record-shared-id")
    first = rubric_item("First independent requirement.", label="within-a")
    second = rubric_item("Second independent requirement.", label="within-b")
    first["rubric_item_id"] = shared
    second["rubric_item_id"] = shared

    matches = findings_of_kind(
        record_findings(make_row(rubrics=[first, second])),
        "duplicate_rubric_item_id",
    )

    assert len(matches) == 1
    assert matches[0][1] == {
        "kind": "duplicate_rubric_item_id",
        "rubric_item_id": shared,
        "indices": [0, 1],
    }


# ---------------------------------------------------------------------------
# Deliberately narrow spreadsheet-column grammar


def test_extract_column_claims_parses_q2_q3_pair_and_scope() -> None:
    claims = extract_column_claims(
        "Q2 and Q3 data are stored in columns C and D.",
        source="task",
        source_path="prompt",
    )

    # Claim ordering is signature-stable rather than semantic-role ordering.
    assert {
        (claim["role"], claim["column"]) for claim in claims
    } == {("q2", "C"), ("q3", "D")}
    assert {claim["scope"] for claim in claims} == {"reference:population"}
    assert {claim["source_path"] for claim in claims} == {"prompt#fragment-0"}


def test_column_extractor_does_not_treat_prose_preposition_as_excel_column() -> None:
    claims = extract_column_claims(
        "Add a year-over-year variance column in both dollars and percentages.",
        source="task",
        source_path="prompt",
    )

    assert claims == []


def test_internal_column_role_conflict_requires_table_identity_review() -> None:
    row = make_row(rubrics=[
        rubric_item(
            "The variance is shown in column F on the first worksheet.",
            label="variance-f",
        ),
        rubric_item(
            "The variance is shown in column G on the first worksheet.",
            label="variance-g",
        ),
    ])

    matches = findings_of_kind(
        record_findings(row), "incompatible_column_role_claims",
    )

    assert len(matches) == 1
    violation, evidence = matches[0]
    assert violation.defect_type == "rubric_internal_contradiction"
    assert violation.review_only
    assert violation.evidence_tier == "review"
    assert evidence["claim_count"] == 2
    assert evidence["conflicts"][0]["kind"] == "one_role_multiple_columns"
    assert evidence["conflicts"][0]["role"] == "variance"
    assert evidence["conflicts"][0]["columns"] == ["F", "G"]


def test_one_column_cannot_have_two_unconditional_roles_in_same_scope() -> None:
    row = make_row(rubrics=[
        rubric_item(
            "Column H contains the variance on the first worksheet.",
            label="column-variance",
        ),
        rubric_item(
            "Sampled rows are marked in column H on the first worksheet.",
            label="column-sample",
        ),
    ])

    matches = findings_of_kind(
        record_findings(row), "incompatible_column_role_claims",
    )

    assert len(matches) == 1
    conflicts = matches[0][1]["conflicts"]
    assert any(
        conflict["kind"] == "one_column_multiple_roles"
        and conflict["column"] == "H"
        and conflict["roles"] == ["sample_flag", "variance"]
        for conflict in conflicts
    )


def test_conditional_or_different_scope_column_claims_do_not_confirm_conflict() -> None:
    conditional = make_row(rubrics=[
        rubric_item("The variance is shown in column F.", label="base-variance"),
        rubric_item("If needed, the variance is shown in column G.", label="conditional"),
    ])
    different_scope = make_row(rubrics=[
        rubric_item(
            "The variance is shown in column F on the first worksheet.",
            label="deliverable-scope",
        ),
        rubric_item(
            "The variance is shown in column G on the population reference sheet.",
            label="reference-scope",
        ),
    ])

    assert findings_of_kind(
        record_findings(conditional), "incompatible_column_role_claims",
    ) == []
    assert findings_of_kind(
        record_findings(different_scope), "incompatible_column_role_claims",
    ) == []


def test_named_worksheets_are_not_collapsed_into_one_scope() -> None:
    row = make_row(rubrics=[
        rubric_item(
            "Variance is in column F on the North worksheet.", label="north-var",
        ),
        rubric_item(
            "Variance is in column G on the South worksheet.", label="south-var",
        ),
    ])

    assert findings_of_kind(
        record_findings(row), "incompatible_column_role_claims",
    ) == []


def test_different_tables_on_first_sheet_do_not_self_confirm_a_conflict() -> None:
    row = make_row(rubrics=[
        rubric_item(
            "In the North table on the first worksheet, variance is in column F.",
            label="north-table-var",
        ),
        rubric_item(
            "In the South table on the first worksheet, variance is in column G.",
            label="south-table-var",
        ),
    ])

    matches = findings_of_kind(
        record_findings(row), "incompatible_column_role_claims",
    )
    assert len(matches) == 1
    assert matches[0][0].evidence_tier == "review"


def test_task_rubric_column_difference_stays_review_only() -> None:
    row = make_row(
        prompt="Capture the quarter-on-quarter variance in column F.",
        rubrics=[rubric_item(
            "The variance is shown in column G on the first worksheet."
        )],
    )

    matches = findings_of_kind(
        record_findings(row), "task_rubric_column_difference",
    )

    assert len(matches) == 1
    violation, evidence = matches[0]
    assert violation.defect_type == "task_rubric_mismatch"
    assert violation.review_only
    assert evidence["mismatches"] == [{
        "scope": "deliverable:first_sheet",
        "role": "variance",
        "task_columns": ["F"],
        "rubric_columns": ["G"],
    }]


# ---------------------------------------------------------------------------
# Explicit single-output filename and format contracts


def test_explicit_task_single_output_format_conflicts_with_gold_extension() -> None:
    row = make_row(
        prompt="Create the final policy as a Word document (.docx).",
        rubrics=[rubric_item("The policy contains an approval section.")],
        deliverables=("final_policy.pdf",),
    )

    matches = findings_of_kind(record_findings(row), "output_format_mismatch")

    assert len(matches) == 1
    violation, evidence = matches[0]
    assert violation.defect_type == "task_artifact_contract_mismatch"
    assert evidence["expected_extension"] == ".docx"
    assert evidence["observed_extension"] == ".pdf"
    assert evidence["claim"]["source"] == "task"


def test_explicit_rubric_single_output_format_conflicts_with_gold_extension() -> None:
    row = make_row(
        rubrics=[rubric_item("The deliverable is a Word document (.docx).")],
        deliverables=("final_policy.pdf",),
    )

    matches = findings_of_kind(record_findings(row), "output_format_mismatch")

    assert len(matches) == 1
    assert matches[0][0].defect_type == "rubric_artifact_contract_mismatch"
    assert matches[0][1]["claim"]["source"] == "rubric"


def test_input_extension_is_not_promoted_as_requested_output_format() -> None:
    row = make_row(
        prompt="Create a report using input.xlsx.",
        deliverables=("report.pdf",),
    )

    assert findings_of_kind(
        record_findings(row), "output_format_mismatch",
    ) == []


@pytest.mark.parametrize(
    "prompt",
    [
        "Create a negotiation strategy document in Word or PDF format.",
        "Create five PowerPoint slides summarizing the analysis.",
        "Create a PowerPoint presentation (as PDF) with labeled slides.",
    ],
)
def test_alternative_or_slide_language_does_not_require_pptx_or_pdf(
    prompt: str,
) -> None:
    row = make_row(prompt=prompt, deliverables=("slides.pdf",))

    assert findings_of_kind(
        record_findings(row), "output_format_mismatch",
    ) == []


def test_format_alternatives_or_multiple_gold_files_are_not_overclaimed() -> None:
    alternatives = make_row(
        prompt="Create the strategy in Word (.docx) or PDF (.pdf) format.",
        deliverables=("strategy.pdf",),
    )
    multiple_outputs = make_row(
        prompt="Create the report as a Word document (.docx).",
        deliverables=("report.docx", "appendix.pdf"),
    )

    assert findings_of_kind(
        record_findings(alternatives), "output_format_mismatch",
    ) == []
    assert findings_of_kind(
        record_findings(multiple_outputs), "output_format_mismatch",
    ) == []


def test_exact_task_filename_absent_from_gold_manifest_is_reported() -> None:
    expected = "Quote - Batch-7 (Client-A).xlsx"
    actual = "Quote Batch 7 Client A.xlsx"
    row = make_row(
        prompt=f'Save the workbook exactly as "{expected}".',
        deliverables=(actual,),
    )

    matches = findings_of_kind(record_findings(row), "exact_filename_absent")

    assert len(matches) == 1
    violation, evidence = matches[0]
    assert violation.defect_type == "task_artifact_contract_mismatch"
    assert evidence["artifact_role"] == "deliverable"
    assert evidence["expected_basename"] == expected
    assert evidence["observed_basenames"] == [actual]
    assert evidence["claim"]["source"] == "task"
    span = evidence["claim"]["raw_claim_span"]
    assert row["prompt"][span["start"]:span["end"]] == expected
    assert evidence["claim"]["raw_claim_sha256"] == sha256(
        expected.encode("utf-8")
    ).hexdigest()


def test_record_replay_rejects_a_mutated_dataset_revision() -> None:
    row = make_row(
        prompt="Create the final policy as a Word document (.docx).",
        deliverables=("final_policy.pdf",),
    )
    item = item_for(row)
    finding = list(GDPValRecordIntegrityChecker().check(item))[0]
    assert finding.evidence_tier == "confirmed"

    finding.evidence["dataset_revision"] = "0" * 40
    enforce_promotion_policy(finding, item)

    assert finding.evidence_tier == "review"


def test_exact_rubric_filename_match_and_missing_gold_do_not_false_alarm() -> None:
    expected = "approved_report.xlsx"
    matching = make_row(
        rubrics=[rubric_item(f'The filename exactly equals "{expected}".')],
        deliverables=(expected,),
    )
    no_gold = make_row(
        rubrics=[rubric_item(f'The filename exactly equals "{expected}".')],
        deliverables=(),
    )

    assert findings_of_kind(
        record_findings(matching), "exact_filename_absent",
    ) == []
    assert findings_of_kind(
        record_findings(no_gold), "exact_filename_absent",
    ) == []


def test_reference_double_extension_is_grounded_as_manifest_absence() -> None:
    row = make_row(
        rubrics=[rubric_item(
            "The reference sheet 'layout_guide.docx.docx' is used for formatting.",
            score=5,
        )],
        references=("layout_guide.docx",),
        deliverables=(),
    )

    matches = findings_of_kind(record_findings(row), "exact_filename_absent")

    assert len(matches) == 1
    violation, evidence = matches[0]
    assert violation.defect_type == "rubric_reference_contract_mismatch"
    assert evidence["artifact_role"] == "reference"
    assert evidence["expected_basename"] == "layout_guide.docx.docx"
    assert evidence["observed_basenames"] == ["layout_guide.docx"]
    assert evidence["claim"]["source"] == "rubric"


def test_quoted_filename_without_reference_or_output_cue_is_ignored() -> None:
    row = make_row(
        prompt='The phrase "unrelated_name.pdf" appears only as an example.',
        references=("source.xlsx",),
        deliverables=("report.docx",),
    )

    assert findings_of_kind(
        record_findings(row), "exact_filename_absent",
    ) == []


# ---------------------------------------------------------------------------
# Dataset-level rubric identifier registry and explicit mapping boundary


def test_global_duplicate_rubric_id_targets_each_physical_occurrence() -> None:
    shared = stable_uuid("global-shared-rubric-id")
    first_rubric = rubric_item("First requirement.", label="global-first")
    second_rubric = rubric_item("Second requirement.", label="global-second")
    first_rubric["rubric_item_id"] = shared
    second_rubric["rubric_item_id"] = shared
    rows = [
        make_row(rubrics=[first_rubric], task_label="global-row-a"),
        make_row(rubrics=[second_rubric], task_label="global-row-b"),
    ]

    matches = findings_of_kind(
        dataset_findings(rows), "global_duplicate_rubric_item_id",
    )

    assert len(matches) == 1
    violation, evidence = matches[0]
    assert violation.defect_type == "duplicate_rubric_item_id"
    assert violation.review_only
    assert evidence["rubric_item_id"] == shared
    assert evidence["occurrences"] == [
        {"row_uid": "source-row-00000000", "rubric_index": 0},
        {"row_uid": "source-row-00000001", "rubric_index": 0},
    ]
    assert violation.evidence["target_row_uids"] == [
        "source-row-00000000", "source-row-00000001",
    ]


def test_repeated_generic_criterion_across_rows_is_not_dataset_duplicate() -> None:
    shared_text = "Overall formatting and style of the deliverable."
    rows = [
        make_row(
            rubrics=[rubric_item(shared_text, label="generic-a")],
            task_label="generic-row-a",
        ),
        make_row(
            rubrics=[rubric_item(shared_text, label="generic-b")],
            task_label="generic-row-b",
        ),
    ]

    assert dataset_findings(rows) == []


def test_explicit_mapping_keeps_gold_inventory_separate_from_output_contract() -> None:
    item = item_for(make_row(deliverables=("expert_reference.pdf",)))

    assert item.gold == [
        next(iter(item.raw["deliverable_files"])),
    ]
    assert item.output_contract is None
    assert item.evaluator == item.raw["rubric_json"]
