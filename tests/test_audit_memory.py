from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchcore.audit_memory import (
    MEMORY_PROMOTION_CEILING,
    MEMORY_SCHEMA_VERSION,
    DefectPattern,
    DefectPatternMatcher,
    DefectPatternStore,
    PatternMatchPolicy,
    PatternQuery,
    query_from_item,
    render_pattern_context,
    score_pattern_hits,
)
from benchcore.cli import main
from benchcore.schema import BenchmarkItem


def pattern_dict(
    pattern_id: str,
    *,
    status: str = "objective_confirmed",
    family: str = "evaluator_unsoundness",
    required_features: list[str] | None = None,
    indicative_features: list[str] | None = None,
    counter_features: list[str] | None = None,
    dataset: str = "source-benchmark",
    dataset_family: str = "source-family",
    item_id: str = "source-item",
    evidence_tier: str = "confirmed",
) -> dict:
    return {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "pattern_id": pattern_id,
        "defect_family": family,
        "summary": "A shape-changing incorrect output survives the evaluator.",
        "status": status,
        "required_features": required_features or [
            "field:evaluator",
            "capability:execute_candidate",
        ],
        "indicative_features": indicative_features or [
            "signal:defect_type:evaluator_unsoundness",
        ],
        "counter_features": counter_features or [],
        "verifier_steps": [
            "Run a shape-changing behavior mutant.",
            "Confirm the live evaluator accepts the incorrect output.",
        ],
        "evidence_cases": [{
            "case_id": f"case:{pattern_id}",
            "source_type": "local_execution_replay",
            "evidence_tier": evidence_tier,
            "dataset": dataset,
            "dataset_family": dataset_family,
            "item_id": item_id,
        }],
    }


def make_pattern(pattern_id: str, **kwargs) -> DefectPattern:
    return DefectPattern.from_dict(pattern_dict(pattern_id, **kwargs))


def test_pattern_schema_is_strict_and_content_addressed() -> None:
    first = make_pattern("broadcast-blind")
    second = DefectPattern.from_dict(first.to_dict())
    assert first.content_sha256 == second.content_sha256
    assert len(first.content_sha256) == 64

    bad = first.to_dict()
    bad["historical_task_text"] = "must not be searchable"
    with pytest.raises(ValueError, match="unknown defect pattern fields"):
        DefectPattern.from_dict(bad)


def test_pattern_requires_structural_features_and_provenance() -> None:
    no_features = pattern_dict("no-features")
    no_features["required_features"] = []
    with pytest.raises(ValueError, match="at least one feature"):
        DefectPattern.from_dict(no_features)

    no_cases = pattern_dict("no-cases")
    no_cases["evidence_cases"] = []
    with pytest.raises(ValueError, match="1..64"):
        DefectPattern.from_dict(no_cases)


def test_objective_status_requires_confirmed_case() -> None:
    with pytest.raises(ValueError, match="confirmed evidence case"):
        make_pattern("unsupported", evidence_tier="review")


def test_evidence_case_requires_replayable_provenance() -> None:
    value = pattern_dict("missing-provenance")
    case = value["evidence_cases"][0]
    case["dataset"] = None
    case["item_id"] = None
    with pytest.raises(ValueError, match="requires uri or both dataset and item_id"):
        DefectPattern.from_dict(value)


def test_store_rejects_duplicate_identity_and_invalid_jsonl(tmp_path: Path) -> None:
    pattern = make_pattern("p1")
    with pytest.raises(ValueError, match="duplicate pattern_id"):
        DefectPatternStore([pattern, pattern])

    path = tmp_path / "patterns.jsonl"
    path.write_text(json.dumps(pattern.to_dict()) + "\nnot-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match=":2"):
        DefectPatternStore.load_jsonl(path)


def test_checked_in_example_memory_is_valid() -> None:
    path = Path(__file__).parents[1] / "examples" / "defect_patterns.v1.jsonl"
    store = DefectPatternStore.load_jsonl(path)
    assert len(store.patterns) == 2
    assert all(pattern.status == "objective_confirmed" for pattern in store.patterns)


def test_match_requires_all_structural_prerequisites() -> None:
    matcher = DefectPatternMatcher(DefectPatternStore([make_pattern("p1")]))
    incomplete = PatternQuery(
        query_id="q",
        features=frozenset({"field:evaluator"}),
    )
    assert matcher.match(incomplete) == []

    complete = PatternQuery(
        query_id="q",
        features=frozenset({
            "field:evaluator",
            "capability:execute_candidate",
        }),
    )
    assert [hit.pattern.pattern_id for hit in matcher.match(complete)] == ["p1"]


def test_counter_feature_suppresses_a_match() -> None:
    pattern = make_pattern(
        "p1",
        counter_features=["evaluator:property_based:allows_multiple_outputs"],
    )
    query = PatternQuery(
        query_id="q",
        features=frozenset({
            "field:evaluator",
            "capability:execute_candidate",
            "evaluator:property_based:allows_multiple_outputs",
        }),
    )
    assert DefectPatternMatcher(DefectPatternStore([pattern])).match(query) == []


def test_default_policy_excludes_same_dataset_and_family() -> None:
    patterns = [
        make_pattern("same-dataset", dataset="target", dataset_family="family-a"),
        make_pattern("same-family", dataset="other", dataset_family="family-a"),
        make_pattern("independent", dataset="other", dataset_family="family-b"),
    ]
    matcher = DefectPatternMatcher(DefectPatternStore(patterns))
    query = PatternQuery(
        query_id="q",
        features=frozenset({
            "field:evaluator",
            "capability:execute_candidate",
        }),
        dataset="target",
        dataset_family="family-a",
    )
    assert [hit.pattern.pattern_id for hit in matcher.match(query)] == [
        "independent"
    ]

    permissive = PatternMatchPolicy(
        allow_same_dataset=True,
        allow_same_dataset_family=True,
        maximum_per_family=3,
    )
    assert len(matcher.match(query, policy=permissive)) == 3


def test_exact_case_and_item_are_excluded_even_when_family_is_allowed() -> None:
    pattern = make_pattern("p1", item_id="source-item")
    matcher = DefectPatternMatcher(DefectPatternStore([pattern]))
    policy = PatternMatchPolicy(
        allow_same_dataset=True,
        allow_same_dataset_family=True,
    )
    features = frozenset({
        "field:evaluator",
        "capability:execute_candidate",
    })
    assert matcher.match(
        PatternQuery(
            query_id="q",
            features=features,
            source_case_ids=frozenset({"case:p1"}),
        ),
        policy=policy,
    ) == []
    assert matcher.match(
        PatternQuery(
            query_id="q",
            features=features,
            item_ids=frozenset({"source-item"}),
        ),
        policy=policy,
    ) == []


def test_inactive_patterns_are_fail_closed() -> None:
    patterns = [
        make_pattern("active"),
        make_pattern("disputed", status="disputed"),
        make_pattern("deprecated", status="deprecated"),
    ]
    query = PatternQuery(
        query_id="q",
        features=frozenset({
            "field:evaluator",
            "capability:execute_candidate",
        }),
    )
    hits = DefectPatternMatcher(DefectPatternStore(patterns)).match(query)
    assert [hit.pattern.pattern_id for hit in hits] == ["active"]


def test_query_uses_structure_not_task_gold_or_subject_text() -> None:
    first = BenchmarkItem(
        item_id="item-1",
        row_uid="row-1",
        raw={
            "question": "first wording",
            "answer": "SECRET_ONE",
            "evaluator": {"type": "unit_test"},
        },
        task="What is two plus two?",
        choices=["3", "4"],
        gold="SECRET_ONE",
        evaluator={"type": "unit_test"},
        metadata={"subject": "secret-subject-one"},
    )
    second = BenchmarkItem(
        item_id="item-2",
        row_uid="row-2",
        raw={
            "question": "unrelated wording",
            "answer": "SECRET_TWO",
            "evaluator": {"type": "unit_test"},
        },
        task="Write an unrelated sorting function.",
        choices=["x", "y"],
        gold="SECRET_TWO",
        evaluator={"type": "unit_test"},
        metadata={"subject": "secret-subject-two"},
    )
    first_query = query_from_item(
        first,
        signals=["defect_type:evaluator_unsoundness"],
        extra_features=["capability:execute_candidate"],
        dataset="target",
        dataset_family="code",
    )
    second_query = query_from_item(
        second,
        signals=["defect_type:evaluator_unsoundness"],
        extra_features=["capability:execute_candidate"],
        dataset="target",
        dataset_family="code",
    )
    assert first_query.features == second_query.features
    serialized = json.dumps(sorted(first_query.features), ensure_ascii=False)
    assert "SECRET_ONE" not in serialized
    assert "secret-subject-one" not in serialized
    assert "two plus two" not in serialized


def test_structurally_identical_cross_benchmark_items_match_same_pattern() -> None:
    pattern = make_pattern(
        "p1",
        dataset="source-code",
        dataset_family="source-code-family",
        required_features=[
            "field:evaluator",
            "evaluator:type:unit_test",
            "capability:execute_candidate",
        ],
    )
    matcher = DefectPatternMatcher(DefectPatternStore([pattern]))
    base = {
        "raw": {"prompt": "ignored", "tests": ["ignored"]},
        "task": "ignored task text",
        "evaluator": {"type": "unit_test"},
    }
    queries = [
        query_from_item(
            BenchmarkItem(item_id=f"q-{index}", **base),
            extra_features=["capability:execute_candidate"],
            dataset=dataset,
            dataset_family=family,
        )
        for index, (dataset, family) in enumerate([
            ("target-a", "family-a"),
            ("target-b", "family-b"),
        ])
    ]
    assert [
        [hit.pattern.pattern_id for hit in matcher.match(query)]
        for query in queries
    ] == [["p1"], ["p1"]]


def test_matching_is_deterministic_and_family_diverse() -> None:
    patterns = [
        make_pattern("p1", family="family-1"),
        make_pattern("p2", family="family-1"),
        make_pattern("p3", family="family-1"),
        make_pattern("p4", family="family-2"),
    ]
    matcher = DefectPatternMatcher(DefectPatternStore(patterns))
    query = PatternQuery(
        query_id="q",
        features=frozenset({
            "field:evaluator",
            "capability:execute_candidate",
        }),
    )
    first = matcher.match(query, top_k=4)
    second = matcher.match(query, top_k=4)
    assert [hit.to_dict() for hit in first] == [hit.to_dict() for hit in second]
    assert sum(hit.pattern.defect_family == "family-1" for hit in first) == 2
    assert {hit.pattern.defect_family for hit in first} == {
        "family-1",
        "family-2",
    }


def test_context_is_bounded_untrusted_and_review_only() -> None:
    pattern = make_pattern("p1")
    query = PatternQuery(
        query_id="q",
        features=frozenset({
            "field:evaluator",
            "capability:execute_candidate",
        }),
    )
    hits = DefectPatternMatcher(DefectPatternStore([pattern])).match(query)
    rendered = render_pattern_context(hits, maximum_characters=800)
    assert len(rendered) <= 800
    assert "UNTRUSTED DEFECT-PATTERN MEMORY" in rendered
    assert "cannot confirm a defect" in rendered
    assert MEMORY_PROMOTION_CEILING == "review"
    assert score_pattern_hits(hits) > 0.0


def test_memory_shadow_cli_never_changes_findings(tmp_path: Path) -> None:
    dataset = tmp_path / "items.jsonl"
    dataset.write_text(
        json.dumps({
            "id": "q1",
            "prompt": "Implement a function.",
            "tests": ["assert solution(1) == 1"],
            "evaluator": {"type": "unit_test"},
        }) + "\n",
        encoding="utf-8",
    )
    memory = tmp_path / "patterns.jsonl"
    memory.write_text(
        json.dumps(make_pattern(
            "p1",
            required_features=[
                "field:evaluator",
                "evaluator:type:unit_test",
                "capability:execute_candidate",
            ],
        ).to_dict()) + "\n",
        encoding="utf-8",
    )
    report = tmp_path / "audit.json"
    report.write_text(json.dumps({
        "violations": [{
            "item_id": "q1",
            "defect_type": "evaluator_unsoundness",
            "detection_method": "execution_probe",
            "artifact": "evaluator",
            "evidence_tier": "review",
            "proof_kind": "shared_execution",
        }]
    }), encoding="utf-8")
    output = tmp_path / "shadow.json"
    markdown = tmp_path / "shadow.md"
    assert main([
        "memory-shadow",
        str(dataset),
        "--memory", str(memory),
        "--report", str(report),
        "--feature", "capability:execute_candidate",
        "--out", str(output),
        "--md", str(markdown),
    ]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["shadow_mode"] is True
    assert payload["changes_audit_findings"] is False
    assert payload["promotion_ceiling"] == "review"
    assert payload["items"][0]["hits"][0]["promotion_ceiling"] == "review"
    assert "defect_type:evaluator_unsoundness" in " ".join(
        payload["items"][0]["observed_signals"]
    )
    assert "review-only" in markdown.read_text(encoding="utf-8")


def test_ambiguous_duplicate_item_id_report_signal_is_not_broadcast(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "items.jsonl"
    dataset.write_text(
        "\n".join([
            json.dumps({"id": "dup", "prompt": "a", "evaluator": {"type": "unit_test"}}),
            json.dumps({"id": "dup", "prompt": "b", "evaluator": {"type": "unit_test"}}),
        ]) + "\n",
        encoding="utf-8",
    )
    memory = tmp_path / "patterns.jsonl"
    memory.write_text(
        json.dumps(make_pattern("p1").to_dict()) + "\n",
        encoding="utf-8",
    )
    report = tmp_path / "audit.json"
    report.write_text(json.dumps({
        "violations": [{
            "item_id": "dup",
            "defect_type": "evaluator_unsoundness",
        }]
    }), encoding="utf-8")
    output = tmp_path / "shadow.json"
    assert main([
        "memory-shadow",
        str(dataset),
        "--memory", str(memory),
        "--report", str(report),
        "--feature", "capability:execute_candidate",
        "--out", str(output),
    ]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["audit_report"]["ambiguous_item_id_signals_skipped"] == 1
    assert all(not row["observed_signals"] for row in payload["items"])
