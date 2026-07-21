from benchcore.auditor import audit_items
from benchcore.checkers import OracleChecker, TaskSpecChecker, _violation
from benchcore.field_mapping import infer_mapping, mapping_from_dict
from benchcore.loader import (
    build_items,
    explicit_mapping_provenance,
    mapping_bindings_sha256,
    record_schema_sha256,
)
from benchcore.promotion import (
    DATASET_PROOF_VALIDATORS,
    OBJECTIVE_PROOF_VALIDATORS,
    PROOF_SPECS,
    enforce_all,
)
from benchcore.schema import BenchmarkItem


def test_sparse_high_priority_field_does_not_override_dense_task_field():
    rows = [
        {"id": index, "task": f"task {index}", **({"question": "sparse"} if index == 0 else {})}
        for index in range(100)
    ]

    mapping = infer_mapping(rows)

    assert mapping.task == "task"
    assert mapping.diagnostics["fields"]["task"]["coverage"] == 1.0


def test_conflicting_dense_candidates_make_mapping_dependent_finding_unknown():
    rows = [
        {"id": index, "question": f"question {index}", "prompt": f"different {index}"}
        for index in range(4)
    ]
    mapping = infer_mapping(rows)
    assert mapping.diagnostics["fields"]["task"]["status"] == "ambiguous"
    items = build_items(rows, mapping)

    # Simulate a task-derived deterministic checker finding.  Because the
    # adapter cannot prove which dense field is the actual task, it must not be
    # automatically confirmed.
    finding = _violation(
        items[0], "missing_condition", 1.0, "task-derived contradiction",
        method="static_rule",
    )

    assert finding.evidence_tier == "unknown"
    assert finding.review_only
    assert finding.proof_kind == "adapter_inference"


def test_unresolved_inferred_task_never_confirms_missing_task():
    mapping = infer_mapping([{"id": "one", "answer": 4}])
    item = build_items([{"id": "one", "answer": 4}], mapping)[0]

    findings = audit_items([item], checkers=[TaskSpecChecker()])

    assert len(findings) == 1
    assert findings[0].defect_type == "missing_task"
    assert findings[0].evidence_tier == "unknown"


def test_explicit_mapping_can_confirm_a_missing_required_task_field():
    mapping = mapping_from_dict({"item_id": "id", "task": "question"})
    item = build_items([{"id": "one"}], mapping)[0]

    findings = audit_items([item], checkers=[TaskSpecChecker()])

    assert findings[0].evidence_tier == "confirmed"


def test_retrieval_candidates_do_not_confirm_invalid_choice_gold():
    rows = [
        {
            "id": f"r{index}",
            "query": "capital of France",
            "candidates": ["docA", "docB", "docC"],
            "target": "doc_17",
        }
        for index in range(5)
    ]
    items = build_items(rows, infer_mapping(rows))

    findings = audit_items(items, checkers=[OracleChecker()])

    assert len(findings) == 5
    assert {finding.defect_type for finding in findings} == {"invalid_choice_gold"}
    assert all(finding.evidence_tier == "review" for finding in findings)
    assert all(
        finding.evidence["choice_namespace_replay"]["peer_records"] == 4
        for finding in findings
    )


def test_large_homogeneous_choice_namespace_can_confirm_one_invalid_gold():
    rows = [
        {
            "id": f"q{index}",
            "question": "Pick one.",
            "choices": ["alpha", "beta", "gamma", "delta"],
            "answer": "A",
        }
        for index in range(100)
    ]
    rows.append({
        "id": "bad",
        "question": "Pick one.",
        "choices": ["alpha", "beta", "gamma", "delta"],
        "answer": "E",
    })
    items = build_items(rows, infer_mapping(rows))

    findings = audit_items(items, checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].item_id == "bad"
    assert findings[0].evidence_tier == "confirmed"
    replay = findings[0].evidence["choice_namespace_replay"]
    assert replay["peer_records"] == 100
    assert replay["mappable_peer_records"] == 100
    assert replay["wilson_lower_95"] >= 0.95


def test_small_inferred_choice_sample_stays_review_only():
    rows = [
        {
            "id": f"q{index}",
            "question": "Pick one.",
            "choices": ["alpha", "beta"],
            "answer": "A",
        }
        for index in range(20)
    ]
    rows.append({
        "id": "bad",
        "question": "Pick one.",
        "choices": ["alpha", "beta"],
        "answer": "C",
    })
    items = build_items(rows, infer_mapping(rows))

    findings = audit_items(items, checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].evidence_tier == "review"


def test_explicit_choice_evaluator_can_confirm_without_large_dataset():
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "evaluator": "evaluator",
    })
    item = build_items([{
        "id": "bad",
        "question": "Pick one.",
        "choices": ["alpha", "beta"],
        "answer": "C",
        "evaluator": {"type": "multiple_choice", "labels": ["A", "B"]},
    }], mapping)[0]

    findings = audit_items([item], checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].evidence_tier == "confirmed"


def test_explicit_choice_output_contract_can_confirm_without_evaluator():
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "output_contract": "output_contract",
    })
    item = build_items([{
        "id": "bad",
        "question": "Pick one.",
        "choices": ["alpha", "beta"],
        "answer": "C",
        "output_contract": {"type": "multiple_choice", "labels": ["A", "B"]},
    }], mapping)[0]

    findings = audit_items([item], checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].evidence_tier == "confirmed"
    assert findings[0].evidence["choice_contract_source"] == "output_contract"


def test_content_task_type_does_not_fragment_choice_namespace_proof():
    rows = [{
        "id": f"q{index}",
        "question": "Pick one.",
        "choices": ["alpha", "beta"],
        "answer": "A",
        "task_type": f"subject-{index % 4}",
    } for index in range(100)]
    rows.append({
        "id": "bad",
        "question": "Pick one.",
        "choices": ["alpha", "beta"],
        "answer": "C",
        "task_type": "subject-0",
    })
    items = build_items(rows, infer_mapping(rows))

    findings = audit_items(items, checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].evidence_tier == "confirmed"
    assert findings[0].evidence["choice_namespace_replay"]["peer_records"] == 100


def test_programmatic_item_without_mapping_receipt_cannot_confirm():
    item = BenchmarkItem(
        item_id="math",
        raw={},
        task="What is 2 + 2?",
        gold="5",
    )

    findings = audit_items([item], checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].defect_type == "wrong_gold_answer"
    assert findings[0].evidence_tier == "unknown"
    assert findings[0].proof_kind == "adapter_inference"


def test_explicit_mapping_keeps_strict_arithmetic_confirmation():
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "gold": "answer",
    })
    item = build_items([{
        "id": "math",
        "question": "What is (2 + 2) * 3?",
        "answer": "11",
    }], mapping)[0]

    findings = audit_items([item], checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].defect_type == "wrong_gold_answer"
    assert findings[0].evidence_tier == "confirmed"


def test_incomplete_explicit_mapping_receipt_cannot_confirm():
    item = BenchmarkItem(
        item_id="math",
        raw={},
        task="What is 2 + 2?",
        gold="5",
        metadata={"_mapping_provenance": {"source": "explicit"}},
    )

    findings = audit_items([item], checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].evidence_tier == "unknown"
    assert "missing adapter_id" in findings[0].promotion_reason


def test_shadow_adapter_cannot_self_sign_a_confirmed_mapping_receipt():
    raw = {"question": "What is 2 + 2?", "answer": "5"}
    bindings = {
        "item_id": None,
        "task": "question",
        "choices": None,
        "gold": "answer",
        "aliases": None,
        "output_contract": None,
        "evaluator": None,
        "context": [],
        "metadata": [],
    }
    item = BenchmarkItem(
        item_id="math",
        raw=raw,
        task=raw["question"],
        gold=raw["answer"],
        metadata={"_mapping_provenance": {
            "receipt_version": "1",
            "source": "generated_adapter",
            "trust_domain": "adapter_shadow_v1",
            "activation_mode": "active_shadow",
            "adapter_id": "self-signed",
            "adapter_version": "1",
            "adapter_sha256": "a" * 64,
            "receipt_id": "self-issued",
            "schema_fingerprint": "b" * 64,
            "mapping_bindings": bindings,
            "mapping_bindings_sha256": mapping_bindings_sha256(bindings),
            "record_schema_sha256": record_schema_sha256(raw),
            "fields": {
                "task": {"selected": "question", "resolved_key": "question", "row_status": "resolved"},
                "gold": {"selected": "answer", "resolved_key": "answer", "row_status": "resolved"},
            },
        }},
    )

    findings = audit_items([item], checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].evidence_tier == "unknown"
    assert "verified registry receipt" in findings[0].promotion_reason


def test_active_verified_string_without_registry_authority_cannot_confirm():
    raw = {"question": "What is 2 + 2?", "answer": "5"}
    provenance = explicit_mapping_provenance(
        adapter_id="self-signed",
        adapter_version="1",
        raw=raw,
        field_bindings={"task": "question", "gold": "answer"},
    )
    provenance.update({
        "source": "generated_adapter",
        "trust_domain": "adapter_registry_verified_v1",
        "activation_mode": "active_verified",
        "adapter_sha256": "a" * 64,
        "adapter_family": "generic",
        "receipt_id": "self-issued",
    })
    item = BenchmarkItem(
        item_id="math",
        raw=raw,
        task=raw["question"],
        gold=raw["answer"],
        metadata={"_mapping_provenance": provenance},
    )

    findings = audit_items([item], checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].evidence_tier == "unknown"
    assert "verified registry receipt" in findings[0].promotion_reason


def test_programmatic_receipt_is_bound_to_the_live_record_schema():
    raw = {"question": "What is 2 + 2?", "answer": "5"}
    provenance = explicit_mapping_provenance(
        adapter_id="host-fixture",
        adapter_version="1",
        raw=raw,
        field_bindings={"task": "question", "gold": "answer"},
    )
    item = BenchmarkItem(
        item_id="math",
        raw={**raw, "unexpected": True},
        task=raw["question"],
        gold=raw["answer"],
        metadata={"_mapping_provenance": provenance},
    )

    findings = audit_items([item], checkers=[OracleChecker()])

    assert len(findings) == 1
    assert findings[0].evidence_tier == "unknown"
    assert "live record schema" in findings[0].promotion_reason


def test_every_confirmation_validator_declares_scope_basis_and_prerequisites():
    registered = set(OBJECTIVE_PROOF_VALIDATORS) | set(DATASET_PROOF_VALIDATORS)

    assert set(PROOF_SPECS) == registered
    assert all(spec.scope in {"item", "dataset"} for spec in PROOF_SPECS.values())
    assert all(
        spec.evidence_basis in {
            "independent_source_replay",
            "decidable_predicate",
            "same_heuristic_replay",
        }
        for spec in PROOF_SPECS.values()
    )
    assert all(spec.prerequisites for spec in PROOF_SPECS.values())


def test_same_heuristic_contract_replay_cannot_confirm():
    mapping = mapping_from_dict({
        "item_id": "id",
        "task": "question",
        "choices": "choices",
        "gold": "answer",
        "output_contract": "output_contract",
        "evaluator": "evaluator",
    })
    item = build_items([{
        "id": "contract",
        "question": "Pick one.",
        "choices": ["alpha", "beta"],
        "answer": "A",
        "output_contract": "Return a numeric answer",
        "evaluator": {"type": "multiple_choice"},
    }], mapping)[0]
    finding = _violation(
        item,
        "output_evaluator_contract_mismatch",
        1.0,
        "choice evaluator conflicts with numeric contract",
        {
            "output_contract": item.output_contract,
            "evaluator": item.evaluator,
            "inferred_evaluator": "choice",
            "evidence_level": "answer_contract_static_consistency",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="cross_artifact_consistency",
    )

    assert finding.evidence_tier == "review"
    assert "heuristic assumptions" in finding.promotion_reason


def test_llm_confidence_and_votes_cannot_self_confirm():
    item = BenchmarkItem(item_id="x", raw={}, task="question")

    finding = _violation(
        item,
        "wrong_gold_answer",
        1.0,
        "three model votes agree",
        {"llm_result": {"confidence": 1.0}, "votes": ["bad", "bad", "bad"]},
        review_only=False,
        method="llm_gold_audit",
    )

    assert finding.evidence_tier == "review"
    assert finding.review_only
    assert finding.proof_kind == "model_judgment"


def test_self_reported_executed_proof_cannot_confirm():
    item = BenchmarkItem(
        item_id="x",
        raw={},
        task="question",
        gold="reference code",
        evaluator={"code_context": "def test_execution(solution): pass"},
    )

    finding = _violation(
        item,
        "gold_rejected_by_evaluator",
        1.0,
        "official harness rejects gold",
        {
            "evidence_level": "executed_harness",
            "proof_schema_version": "1.0",
            "harness": {"pass": False},
            "driver_sha256": "a" * 64,
            "reference_code_sha256": "b" * 64,
            "code_context_sha256": "c" * 64,
            "adjudicator_trust_domain": "separate_process_v1",
        },
        review_only=False,
        method="execution_replay",
    )

    assert finding.evidence_tier == "review"
    assert finding.review_only
    assert finding.proof_kind == "isolated_execution"
    assert "independently verifiable" in finding.promotion_reason


def test_method_name_alone_never_grants_confirmation():
    item = BenchmarkItem(item_id="x", raw={}, task="question")

    finding = _violation(
        item,
        "wrong_gold_answer",
        1.0,
        "unregistered heuristic disguised as a static rule",
        {},
        review_only=False,
        method="static_rule",
    )

    assert finding.evidence_tier == "review"
    assert finding.review_only


def test_registered_proof_with_malformed_payload_fails_closed():
    item = BenchmarkItem(item_id="x", raw={}, task="question")

    finding = _violation(
        item,
        "gold_rejected_by_evaluator",
        1.0,
        "claims an execution proof without replay hashes",
        {
            "evidence_level": "executed_harness",
            "proof_schema_version": "1.0",
            "harness": {"pass": False},
        },
        review_only=False,
        method="execution_replay",
    )

    assert finding.evidence_tier == "review"
    assert "independently verifiable" in finding.promotion_reason


def test_workspace_evidence_shape_without_live_replay_cannot_confirm():
    item = BenchmarkItem(
        item_id="workspace-clean", raw={"data_manifest": []}, task="Create report.md",
        context={"data_manifest": []},
        output_contract={"required_files": ["report.md"]},
        evaluator={"type": "workspacebench_rubric", "rubrics": ["Create it"]},
    )

    finding = _violation(
        item,
        "artifact_data_gap",
        1.0,
        "forged unresolved manifest payload",
        {
            "unresolved_manifest_entries": [{"filename": "ghost.txt"}],
            "evidence_level": "filesystem_manifest_replay",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="workspace_artifact_invariants",
    )

    assert finding.evidence_tier == "review"
    assert "failed validation" in finding.promotion_reason


def test_workspace_file_replay_without_runtime_trust_roots_cannot_confirm():
    item = BenchmarkItem(
        item_id="workspace-host-path",
        raw={
            "input_files": ["/etc/passwd"],
            "data_manifest": [
                {"filename": "ghost.txt", "stored_relpath": "data/ghost.txt"},
            ],
        },
        task="Create report.md",
        context={
            "data_manifest": [
                {"filename": "ghost.txt", "stored_relpath": "data/ghost.txt"},
            ],
        },
        output_contract={"required_files": ["report.md"]},
        evaluator={"type": "workspacebench_rubric", "rubrics": ["Create it"]},
    )

    finding = _violation(
        item,
        "artifact_data_gap",
        1.0,
        "forged replay over an untrusted host path",
        {
            "unresolved_manifest_entries": [
                {"filename": "ghost.txt", "stored_relpath": "data/ghost.txt"},
            ],
            "evidence_level": "filesystem_manifest_replay",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="workspace_artifact_invariants",
    )

    assert finding.evidence_tier == "review"


def test_forged_arithmetic_replay_is_independently_recomputed():
    item = BenchmarkItem(item_id="math", raw={}, task="What is 2 + 2?", gold="5")

    finding = _violation(
        item,
        "wrong_gold_answer",
        1.0,
        "forged arithmetic replay",
        {
            "gold": "5",
            "task": item.task,
            "computed_value": 99,
            "safe_expression_replayed": True,
            "evidence_level": "safe_arithmetic_replay",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="static_rule",
    )

    assert finding.evidence_tier == "review"


def test_forged_evaluator_rejection_is_independently_replayed():
    item = BenchmarkItem(
        item_id="evaluator",
        raw={},
        task="Return 4.",
        gold="4",
        evaluator={"type": "exact"},
    )

    finding = _violation(
        item,
        "gold_rejected_by_evaluator",
        1.0,
        "forged rejection",
        {
            "gold": item.gold,
            "choices": item.choices,
            "evaluator": item.evaluator,
            "evidence_level": "declared_evaluator_replay",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="evaluator_replay",
    )

    assert finding.evidence_tier == "review"


def test_forged_contract_mismatch_is_independently_recomputed():
    item = BenchmarkItem(
        item_id="contract",
        raw={},
        task="Return the answer.",
        gold="answer",
        output_contract={"type": "text"},
        evaluator={"type": "exact"},
    )

    finding = _violation(
        item,
        "output_evaluator_contract_mismatch",
        1.0,
        "forged mismatch",
        {
            "output_contract": item.output_contract,
            "evaluator": item.evaluator,
            "inferred_evaluator": "exact",
            "evidence_level": "answer_contract_static_consistency",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="cross_artifact_consistency",
    )

    assert finding.evidence_tier == "review"


def test_forged_executable_check_is_recomputed_from_live_raw_record():
    check = {"kind": "python_expr", "expr": "2 + 2", "expected": 4}
    item = BenchmarkItem(
        item_id="executable",
        raw={"executable_checks": [check]},
        task="Compute the result.",
        gold="4",
    )

    finding = _violation(
        item,
        "invalid_executable_evidence",
        1.0,
        "forged failed check",
        {
            "source_path": "executable_checks",
            "check": check,
            "computed": 9,
            "evidence_level": "safe_expression_replay",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="executable_evidence_replay",
    )

    assert finding.evidence_tier == "review"


def test_forged_duplicate_payload_cannot_confirm_against_unique_live_rows():
    items = [
        BenchmarkItem(item_id="a", raw={}, task="first", row_uid="row-a"),
        BenchmarkItem(item_id="b", raw={}, task="second", row_uid="row-b"),
    ]
    finding = _violation(
        items[0],
        "duplicate_item_id",
        1.0,
        "forged duplicate group",
        {
            "item_id": "a",
            "count": 2,
            "target_row_uids": ["row-a", "row-b"],
            "evidence_level": "dataset_identifier_collision",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="dataset_duplicate_scan",
    )

    enforce_all([finding], items)

    assert finding.evidence_tier == "review"
    assert "complete live records" in finding.promotion_reason


def test_forged_conflicting_oracle_group_cannot_confirm():
    items = [
        BenchmarkItem(
            item_id="a", raw={}, task="first", gold="1", row_uid="row-a",
        ),
        BenchmarkItem(
            item_id="b", raw={}, task="different", gold="2", row_uid="row-b",
        ),
    ]
    finding = _violation(
        items[0],
        "conflicting_duplicate_oracle",
        1.0,
        "forged oracle conflict",
        {
            "item_ids": ["a", "b"],
            "target_row_uids": ["row-a", "row-b"],
            "gold_values": ["1", "2"],
            "evidence_level": "canonical_record_oracle_conflict",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="dataset_duplicate_scan",
    )

    enforce_all([finding], items)

    assert finding.evidence_tier == "review"


def test_multifield_mapping_dependency_blocks_workspace_visibility_promotion():
    item = BenchmarkItem(
        item_id="workspace", raw={}, task="task",
        evaluator={"type": "workspacebench_rubric"},
        metadata={
            "_mapping_provenance": {
                "source": "inferred",
                "fields": {
                    "context": {
                        "row_status": "resolved", "mapping_status": "ambiguous",
                    },
                    "evaluator": {
                        "row_status": "resolved", "mapping_status": "resolved",
                    },
                },
            }
        },
    )

    finding = _violation(
        item, "solution_leak", 1.0, "visibility replay",
        {
            "evidence_level": "workspace_runner_visibility_replay",
            "proof_schema_version": "1.0",
        },
        review_only=False,
        method="workspace_artifact_invariants",
    )

    assert finding.evidence_tier == "unknown"
    assert finding.proof_kind == "adapter_inference"
