import hashlib
import json
from pathlib import Path

from benchcore.auditor import audit_items_with_ledger
from benchcore.file_reader import DEFAULT_LIMITS
from benchcore.schema import BenchmarkItem
from benchcore.workspace_grounding import (
    WorkspaceRubricGroundingAuditor,
    WorkspaceRubricGroundingChecker,
    build_workspace_evidence_bundle,
    resolve_objective_grounding_certificate,
    rubric_search_terms,
    validate_grounding_citations,
)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def chat_json(self, system, prompt):
        self.prompts.append((system, prompt))
        return self.responses.pop(0)


def make_item(paths, rubric="Does the report use the exact title `Secret Heading`?"):
    return BenchmarkItem(
        item_id="workspacebench-1",
        raw={"input_files": [str(path) for path in paths], "rubrics": [rubric]},
        task="Read the source and create report.md.",
        context={},
        output_contract={"type": "workspace_files", "required_files": ["report.md"]},
        evaluator={"type": "workspacebench_rubric", "rubrics": [rubric]},
    )


def declare_complete_inventory(item, input_names):
    values = [*input_names, "report.md"]
    item.raw["workspace_inventory"] = values
    item.raw["workspace_inventory_complete"] = True
    return item


def test_evidence_bundle_masks_reference_generators(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("independent facts", encoding="utf-8")
    generator = tmp_path / "generate_report.py"
    generator.write_text("secret answer", encoding="utf-8")

    bundle = build_workspace_evidence_bundle(
        make_item([source, generator]), allowed_roots=[tmp_path],
    )

    assert bundle.indexed_files == ["source.txt"]
    assert bundle.excluded_files == ["generate_report.py"]
    assert "secret answer" not in bundle.text


def test_search_terms_keep_numbers_filenames_and_quoted_literals():
    terms = rubric_search_terms(
        'Does report.md contain exactly 43 rows and the title "Annual Review"?'
    )

    assert "43" in terms
    assert any("report.md" in term for term in terms)
    assert "Annual Review" in terms


def test_adversarial_verifier_can_confirm_unsupported(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("ordinary source", encoding="utf-8")
    client = FakeClient([
        {
            "label": "unsupported", "confidence": 0.91,
            "requirement_type": "presentation", "atomic_requirement": "exact hidden title",
            "reason": "The task does not specify this title.", "evidence": [],
            "missing_assumption": "A visible style specification.",
        },
        {"label": "unsupported", "confidence": 0.87, "reason": "No independent support."},
    ])
    auditor = WorkspaceRubricGroundingAuditor(client, allowed_roots=[tmp_path])
    item = declare_complete_inventory(make_item([source]), [source.name])

    decision = auditor.audit_item(item)[0]

    assert decision.label == "unsupported"
    assert decision.confidence == 0.87
    assert decision.verifier is not None


def test_verifier_refutation_prevents_false_positive(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("The mandatory title is Secret Heading.", encoding="utf-8")
    client = FakeClient([
        {"label": "unsupported", "confidence": 0.8, "reason": "No support", "evidence": []},
        {
            "label": "supported", "confidence": 0.94,
            "reason": "Input explicitly states it.",
            "decisive_evidence": {
                "source": "input:source.txt",
                "quote": "The mandatory title is Secret Heading.",
            },
        },
    ])
    auditor = WorkspaceRubricGroundingAuditor(client, allowed_roots=[tmp_path])

    decision = auditor.audit_item(make_item([source]))[0]

    assert decision.label == "supported"
    assert decision.confidence == 0.94


def test_checker_emits_only_verified_unsupported_as_review(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("ordinary source", encoding="utf-8")
    client = FakeClient([
        {"label": "unsupported", "confidence": 0.9, "reason": "Hidden title", "evidence": []},
        {"label": "unsupported", "confidence": 0.85, "reason": "Confirmed"},
    ])
    checker = WorkspaceRubricGroundingChecker(
        WorkspaceRubricGroundingAuditor(client, allowed_roots=[tmp_path])
    )
    item = declare_complete_inventory(make_item([source]), [source.name])

    violations = list(checker.check(item))

    assert [row.defect_type for row in violations] == ["task_rubric_mismatch"]
    assert violations[0].review_only
    assert violations[0].evidence["evidence_level"] == "llm_grounded_with_adversarial_verifier"


def test_checker_declares_applicability_and_partial_model_failure_is_operational(
    tmp_path: Path,
):
    source = tmp_path / "source.txt"
    source.write_text("ordinary source", encoding="utf-8")
    rubrics = ["Use a hidden blue background.", "Use a hidden serif font."]
    item = make_item([source], rubrics[0])
    item.raw["rubrics"] = rubrics
    item.evaluator["rubrics"] = rubrics
    item = declare_complete_inventory(item, [source.name])
    client = FakeClient([
        {
            "label": "unsupported", "confidence": 0.9,
            "requirement_type": "presentation", "reason": "Hidden choice",
            "evidence": [],
        },
        {
            "label": "unsupported", "confidence": 0.85,
            "reason": "Complete view confirms no support",
        },
        {"reason": "JSON object omitted label and confidence"},
    ])
    checker = WorkspaceRubricGroundingChecker(
        WorkspaceRubricGroundingAuditor(client, allowed_roots=[tmp_path]),
    )

    eligibility = checker.audit_eligibility(item)
    assert eligibility.eligible is True
    result = audit_items_with_ledger([item], checkers=[checker])

    assert [row.defect_type for row in result.violations] == [
        "task_rubric_mismatch", "llm_audit_failure",
    ]
    failure = result.violations[1]
    assert failure.defect_scope == "operational"
    assert failure.evidence["coverage_granularity"] == "rubric"
    assert failure.evidence["audit_coverage_status"] == "operational_failed"
    assert result.ledger[0].status == "operational_failed"
    assert not result.ledger[0].completed

    non_workspace = BenchmarkItem(item_id="plain", raw={}, evaluator={})
    assert checker.audit_eligibility(non_workspace).eligible is False


def test_batched_audit_keeps_rubric_indices_and_verifies_candidates(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("The report must contain 7 rows.", encoding="utf-8")
    rubrics = ["Use the title Secret.", "Does the report contain 7 rows?"]
    item = make_item([source], rubrics[0])
    item.raw["rubrics"] = rubrics
    item.evaluator["rubrics"] = rubrics
    item = declare_complete_inventory(item, [source.name])
    client = FakeClient([
        {
            "decisions": [
                {
                    "rubric_index": 0, "label": "unsupported", "confidence": 0.9,
                    "reason": "Hidden title", "evidence": [],
                },
                    {
                        "rubric_index": 1, "label": "supported", "confidence": 0.95,
                        "reason": "Input states 7", "evidence": [{
                            "source": "input:source.txt",
                            "quote": "The report must contain 7 rows.",
                            "relation": "supports",
                        }],
                },
            ],
        },
        {
            "decisions": [
                {
                    "rubric_index": 0, "label": "unsupported", "confidence": 0.85,
                    "reason": "No source supports the title",
                },
            ],
        },
    ])
    auditor = WorkspaceRubricGroundingAuditor(client, allowed_roots=[tmp_path])

    decisions = auditor.audit_item_batched(item, batch_size=4)

    assert [(row.rubric_index, row.label) for row in decisions] == [
        (0, "unsupported"), (1, "supported"),
    ]
    assert decisions[0].verifier["rubric_index"] == 0
    assert len(client.prompts) == 2


def test_batched_audit_downgrades_missing_or_duplicate_index(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("ordinary source", encoding="utf-8")
    rubrics = ["First requirement", "Second requirement"]
    item = make_item([source], rubrics[0])
    item.raw["rubrics"] = rubrics
    item.evaluator["rubrics"] = rubrics
    duplicate = {
        "rubric_index": 0, "label": "supported", "confidence": 0.99,
        "reason": "ambiguous duplicate",
    }
    client = FakeClient([{"decisions": [duplicate, duplicate]}])
    auditor = WorkspaceRubricGroundingAuditor(client, allowed_roots=[tmp_path])

    decisions = auditor.audit_item_batched(item, batch_size=4)

    assert [row.label for row in decisions] == ["uncertain", "uncertain"]
    assert all(row.scanner["operational_failure"] for row in decisions)


def test_evidence_bundle_never_reads_path_outside_allowed_root(tmp_path: Path):
    package = tmp_path / "package"
    package.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("PRIVATE_TOKEN_DO_NOT_SEND", encoding="utf-8")

    bundle = build_workspace_evidence_bundle(
        make_item([secret]), package, allowed_roots=[package],
    )

    assert bundle.indexed_files == []
    assert bundle.blocked_files[0]["resolved"] == str(secret.resolve())
    assert "PRIVATE_TOKEN_DO_NOT_SEND" not in bundle.text


def test_hallucinated_supported_quote_forces_uncertain(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("The source contains only ordinary facts.", encoding="utf-8")
    client = FakeClient([{
        "label": "supported",
        "confidence": 0.99,
        "requirement_type": "input_fact",
        "reason": "Invented evidence",
        "evidence": [{
            "source": "input:source.txt",
            "quote": "A sentence that is not actually present",
            "relation": "supports",
        }],
    }])

    decision = WorkspaceRubricGroundingAuditor(
        client, allowed_roots=[tmp_path],
    ).audit_item(
        make_item([source]),
    )[0]

    assert decision.label == "uncertain"
    assert not decision.citation_validation["all_claimed_valid"]
    assert decision.citation_validation["gate_reason"].startswith("one_or_more")


def test_low_information_quote_pseudo_intrinsic_and_incomplete_absence_fail_closed(
    tmp_path: Path,
):
    source = tmp_path / "source.txt"
    source.write_text("7 ordinary source facts", encoding="utf-8")
    item = make_item([source], "Use an arbitrary hidden layout.")
    bundle = build_workspace_evidence_bundle(item, allowed_roots=[tmp_path])
    citation = validate_grounding_citations(item, bundle, [{
        "source": "input:source.txt",
        "quote": "7",
        "relation": "supports",
    }])
    assert not citation["all_claimed_valid"]
    assert citation["claims"][0]["reason"] == "low_information_quote"

    intrinsic_client = FakeClient([{
        "label": "supported",
        "confidence": 0.99,
        "requirement_type": "intrinsic",
        "reason": "The model merely called an arbitrary layout intrinsic.",
        "evidence": [],
    }])
    intrinsic = WorkspaceRubricGroundingAuditor(
        intrinsic_client, allowed_roots=[tmp_path],
    ).audit_item(item)[0]
    assert intrinsic.label == "uncertain"
    assert intrinsic.citation_validation["gate_reason"] == (
        "pseudo_intrinsic_has_no_objective_certificate"
    )

    absence_client = FakeClient([
        {
            "label": "unsupported", "confidence": 0.9,
            "requirement_type": "presentation", "reason": "No support",
            "evidence": [],
        },
        {"label": "unsupported", "confidence": 0.9, "reason": "Still absent"},
    ])
    absence = WorkspaceRubricGroundingAuditor(
        absence_client, allowed_roots=[tmp_path],
    ).audit_item(item)[0]
    assert not bundle.actor_view_complete
    assert absence.label == "uncertain"
    assert absence.citation_validation["gate_reason"] == (
        "incomplete_actor_view_cannot_confirm_uncited_absence"
    )


def test_objective_resolver_rejects_negation_secondary_substrings_and_delegation(
    tmp_path: Path,
):
    source = tmp_path / "source.txt"
    source.write_text("ordinary source", encoding="utf-8")
    title_rubric = (
        'Does the primary requested artifact use the exact title "Primary Title"?'
    )

    secondary = make_item([source], title_rubric)
    secondary.task = (
        'Use the exact title "Primary Title" for the secondary requested artifact.'
    )
    secondary_bundle = build_workspace_evidence_bundle(
        secondary, allowed_roots=[tmp_path],
    )
    secondary_cert = resolve_objective_grounding_certificate(
        secondary, secondary_bundle, title_rubric,
    )
    assert secondary_cert["applicable"]
    assert not secondary_cert["eligible"]
    assert secondary_cert["label"] is None

    negated = make_item([source], title_rubric)
    negated.task = (
        'Do not use the exact title "Primary Title" for the primary requested artifact.'
    )
    negated_cert = resolve_objective_grounding_certificate(
        negated,
        build_workspace_evidence_bundle(negated, allowed_roots=[tmp_path]),
        title_rubric,
    )
    assert not negated_cert["eligible"]
    assert negated_cert["label"] is None

    companion_rubric = "Was the required companion file `target.md` created?"
    substring = make_item([source], companion_rubric)
    substring.output_contract = {
        "type": "workspace_files",
        "required_files": ["old_target.md"],
    }
    substring_cert = resolve_objective_grounding_certificate(
        substring,
        build_workspace_evidence_bundle(substring, allowed_roots=[tmp_path]),
        companion_rubric,
    )
    assert not substring_cert["eligible"]
    assert substring_cert["label"] is None

    negated_companion = make_item([source], companion_rubric)
    negated_companion.output_contract = {
        "type": "workspace_files",
        "required_files": ["target.md"],
        "required_files_complete": True,
    }
    negated_companion.task = "Do not create the companion file `target.md`."
    negated_companion_cert = resolve_objective_grounding_certificate(
        negated_companion,
        build_workspace_evidence_bundle(
            negated_companion, allowed_roots=[tmp_path],
        ),
        companion_rubric,
    )
    assert not negated_companion_cert["eligible"]
    assert negated_companion_cert["label"] is None
    assert negated_companion_cert["certificate_type"] == "required_file_conflict"

    delegated = make_item([source], companion_rubric)
    delegated.task = (
        "Use the companion filename specified in the attached source document."
    )
    delegated.output_contract = {
        "type": "workspace_files",
        "required_files": ["report.md"],
        "required_files_complete": True,
    }
    delegated_cert = resolve_objective_grounding_certificate(
        delegated,
        build_workspace_evidence_bundle(delegated, allowed_roots=[tmp_path]),
        companion_rubric,
    )
    assert delegated_cert["facts"]["delegated_naming"]
    assert not delegated_cert["eligible"]
    assert delegated_cert["label"] is None

    beyond_prefix = make_item([source], companion_rubric)
    beyond_prefix.output_contract = {
        "type": "workspace_files",
        "required_files": [
            f"artifact_{index}_{'x' * 60}.md" for index in range(80)
        ] + ["target.md"],
        "required_files_complete": True,
    }
    beyond_bundle = build_workspace_evidence_bundle(
        beyond_prefix, allowed_roots=[tmp_path],
    )
    beyond_cert = resolve_objective_grounding_certificate(
        beyond_prefix, beyond_bundle, companion_rubric,
    )
    canonical_contract = json.dumps(
        {
            "required_files": beyond_prefix.output_contract["required_files"],
            "declared": beyond_prefix.output_contract,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    assert beyond_cert["eligible"]
    assert beyond_cert["label"] == "supported"
    assert beyond_cert["source_sha256"] == hashlib.sha256(
        canonical_contract.encode("utf-8")
    ).hexdigest()


def test_complete_inventory_is_citable_without_requiring_content_parse(tmp_path: Path):
    # Rich-document parsing is refused without an isolated runner, but a
    # contained complete manifest still proves the exact filename and
    # actor-visible input count independently of content extraction.
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7\nsynthetic attachment")
    item = declare_complete_inventory(make_item([source]), [source.name])

    bundle = build_workspace_evidence_bundle(item, allowed_roots=[tmp_path])
    validation = validate_grounding_citations(item, bundle, [
        {
            "source": "input_inventory",
            "quote": "file_count=1",
            "relation": "supports",
        },
        {
            "source": "input_inventory",
            "quote": "logical=source.pdf",
            "relation": "supports",
        },
    ])

    assert bundle.input_inventory_complete
    assert bundle.inventory_absence_is_confirmation_eligible
    assert not bundle.actor_view_complete
    assert validation["all_claimed_valid"]
    assert validation["valid_support_count"] == 2
    assert all(
        len(claim["source_sha256"]) == 64
        for claim in validation["claims"]
    )
    assert all(claim["resolved_excerpt"] for claim in validation["claims"])


def test_citation_binding_uses_only_prompt_visible_prefixes_and_hashed_sources(
    tmp_path: Path,
):
    source = tmp_path / "source.txt"
    source.write_text("machine-bound attachment sentence", encoding="utf-8")
    item = make_item([source])
    item.task = "A" * 4_050 + " invisible task tail"
    item.output_contract["required_files"] = [
        f"artifact_{index}_{'x' * 60}.md" for index in range(80)
    ] + ["invisible_contract_tail.md"]
    bundle = build_workspace_evidence_bundle(item, allowed_roots=[tmp_path])

    validation = validate_grounding_citations(item, bundle, [
        {
            "source": "task",
            "quote": "invisible task tail",
            "relation": "supports",
        },
        {
            "source": "output_contract",
            "quote": "invisible_contract_tail.md",
            "relation": "supports",
        },
        {
            "source": "input:source.txt",
            "quote": "machine-bound attachment sentence",
            "relation": "supports",
        },
    ])

    task_claim, contract_claim, input_claim = validation["claims"]
    assert not task_claim["valid"]
    assert not contract_claim["valid"]
    assert input_claim["valid"]
    assert len(input_claim["source_sha256"]) == 64
    assert "machine-bound attachment sentence" in input_claim["resolved_excerpt"]


def test_inventory_citation_rejects_invented_count(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("ordinary source", encoding="utf-8")
    item = declare_complete_inventory(make_item([source]), [source.name])
    bundle = build_workspace_evidence_bundle(item, allowed_roots=[tmp_path])

    validation = validate_grounding_citations(item, bundle, [{
        "source": "input_inventory",
        "quote": "file_count=2",
        "relation": "supports",
    }])

    assert bundle.input_inventory_complete
    assert not validation["all_claimed_valid"]
    assert validation["claims"][0]["reason"] == (
        "quote_not_in_complete_rendered_inventory"
    )


def test_inventory_is_not_complete_when_declared_actor_view_does_not_reconcile(
    tmp_path: Path,
):
    source = tmp_path / "source.txt"
    source.write_text("ordinary source", encoding="utf-8")
    item = declare_complete_inventory(
        make_item([source]), [source.name, "unmaterialized.dat"],
    )

    bundle = build_workspace_evidence_bundle(item, allowed_roots=[tmp_path])
    count_validation = validate_grounding_citations(item, bundle, [{
        "source": "input_inventory",
        "quote": "file_count=1",
        "relation": "supports",
    }])

    assert not bundle.input_inventory_complete
    assert not bundle.inventory_absence_is_confirmation_eligible
    assert not count_validation["all_claimed_valid"]
    assert count_validation["claims"][0]["reason"] == (
        "inventory_count_requires_complete_actor_view"
    )


def test_large_symlinked_and_globally_truncated_inputs_fail_closed(tmp_path: Path):
    large = tmp_path / "too_large.txt"
    with large.open("wb") as handle:
        handle.truncate(DEFAULT_LIMITS.max_file_bytes + 1)
    large_item = declare_complete_inventory(make_item([large]), [large.name])
    large_bundle = build_workspace_evidence_bundle(
        large_item, allowed_roots=[tmp_path],
    )
    assert large_bundle.parse_failures == [large.name]
    assert not large_bundle.actor_view_complete
    assert large_bundle.artifact_identity_failures[0]["status"] == "budget_exceeded"
    assert large_bundle.content_sha256_by_path == {}

    target = tmp_path / "target.txt"
    target.write_text("stable target", encoding="utf-8")
    link = tmp_path / "contained-link.txt"
    link.symlink_to(target.name)
    link_item = declare_complete_inventory(make_item([link]), [link.name])
    link_bundle = build_workspace_evidence_bundle(
        link_item, allowed_roots=[tmp_path],
    )
    assert link_bundle.parse_failures == [link.name]
    assert link_bundle.artifact_identity_failures[0]["code"] == (
        "identity_symlink_refused"
    )
    assert not link_bundle.actor_view_complete

    text = tmp_path / "bounded.txt"
    text.write_text("visible phrase " + "x" * 1_000, encoding="utf-8")
    truncated_item = declare_complete_inventory(make_item([text]), [text.name])
    truncated_bundle = build_workspace_evidence_bundle(
        truncated_item, max_chars=300, allowed_roots=[tmp_path],
    )
    validation = validate_grounding_citations(truncated_item, truncated_bundle, [{
        "source": "input:bounded.txt",
        "quote": "visible phrase",
        "relation": "supports",
    }])
    assert truncated_bundle.input_inventory_complete
    assert truncated_bundle.bundle_truncated
    assert not truncated_bundle.actor_view_complete
    assert not validation["all_claimed_valid"]
    assert validation["claims"][0]["reason"] == (
        "bundle_truncation_prevents_input_citation_confirmation"
    )
