from benchcore.auditor import audit_items
from benchcore.checkers import TaskSpecChecker, _violation
from benchcore.field_mapping import infer_mapping, mapping_from_dict
from benchcore.loader import build_items
from benchcore.promotion import enforce_all
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
