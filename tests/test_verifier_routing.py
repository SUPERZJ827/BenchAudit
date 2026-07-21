from benchcore.planning import build_audit_plan
from benchcore.schema import BenchmarkItem
from benchcore.verifier_routing import route_verifier


def test_workspace_route_prefers_objective_certificate_over_agent_vote():
    item = BenchmarkItem(
        item_id="workspace", raw={"rubrics": ["x"]}, task="make a report",
        evaluator={"rubrics": ["x"]}, output_contract={"required_files": ["a.md"]},
    )
    route = route_verifier(item)
    assert route.route == "workspace_objective_certificate_then_grounded_review"
    assert route.status == "available"


def test_code_route_requires_external_attestation_to_confirm():
    route = route_verifier(BenchmarkItem(
        item_id="code", raw={}, task="sort", gold="result = sorted(x)",
        evaluator={"code_context": "def test_execution(solution): pass"},
    ))
    assert route.route == "executable_harness_with_external_transcript_attestation"
    assert route.status == "requires_external_attestation"
    assert "answer_contract_metamorphic_and_mutation_replay" in route.secondary_routes


def test_scalar_gold_gets_answer_counterexample_route():
    route = route_verifier(BenchmarkItem(
        item_id="answer", raw={}, task="What is 2 + 2?", gold="4",
        evaluator={"type": "numeric"},
    ))

    assert route.route == "answer_contract_counterexample_replay"
    assert route.status == "available"
    assert "declared answer contract" in route.required_evidence


def test_unknown_schema_fails_to_review_only_instead_of_inventing_verifier(tmp_path):
    item = BenchmarkItem(item_id="unknown", raw={}, task="Describe a landscape.")
    from benchcore.package_scan import scan_benchmark_package

    (tmp_path / "task.txt").write_text("describe", encoding="utf-8")
    plan = build_audit_plan(scan_benchmark_package(tmp_path), items=[item])
    assert plan.verifier_routes[0].status == "review_only"
