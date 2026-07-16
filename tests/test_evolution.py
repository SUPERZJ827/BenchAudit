from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchcore.auditor import audit_items_with_ledger
from benchcore.cli import main
from benchcore.evolution import (
    CorpusExample,
    DeclarativeRuleChecker,
    EvolutionController,
    EvolutionRegistry,
    GatePolicy,
    RuleSpec,
    RuleValidationError,
    StaticRuleSynthesizer,
    evaluate_rule,
)
from benchcore.evolution.corpus import synthesis_projection, validate_corpus
from benchcore.loader import build_items, load_mapping


def _rule(*, rule_id: str = "rubric_type_count_mismatch", family: str = "generic") -> RuleSpec:
    return RuleSpec.from_dict({
        "schema_version": "benchcore-declarative-rule-v1",
        "rule_id": rule_id,
        "version": 1,
        "family": family,
        "defect_type": "schema_drift",
        "description": "Rubric and rubric-type list lengths differ.",
        "message": "Rubric and rubric-type cardinalities differ.",
        "repair": "Provide exactly one type for every rubric.",
        "conditions": [{
            "left": {
                "source": "raw",
                "path": ["rubrics"],
                "transforms": ["parse_jsonish", "length"],
            },
            "operator": "ne",
            "right": {"operand": {
                "source": "raw",
                "path": ["rubric_types"],
                "transforms": ["parse_jsonish", "length"],
            }},
        }],
        "match": "all",
        "confidence": 0.85,
    })


def _always_match_rule() -> RuleSpec:
    return RuleSpec.from_dict({
        "schema_version": "benchcore-declarative-rule-v1",
        "rule_id": "flag_every_rubric_row",
        "version": 1,
        "family": "generic",
        "defect_type": "schema_drift",
        "description": "Bad reward-hacking candidate.",
        "message": "Always flags rows with rubrics.",
        "repair": "None.",
        "conditions": [{
            "left": {"source": "raw", "path": ["rubrics"], "transforms": []},
            "operator": "is_present",
        }],
        "confidence": 0.5,
    })


def _examples(groups_per_split: int = 3) -> list[CorpusExample]:
    examples: list[CorpusExample] = []
    for split_index, split in enumerate(("train", "dev", "holdout")):
        for group_index in range(groups_per_split):
            group = f"opaque-group-{split_index}-{group_index}"
            clean = {
                "item_id": f"opaque-{split_index}-{group_index}-a",
                "task": "Create the requested artifact.",
                "rubrics": ["file exists", "content is correct"],
                "rubric_types": ["basic", "outcome"],
            }
            mutant = {
                **clean,
                "item_id": f"opaque-{split_index}-{group_index}-b",
                "rubric_types": ["basic"],
            }
            examples.extend([
                CorpusExample(
                    example_id=f"example-{split_index}-{group_index}-a",
                    source_group=group,
                    split=split,
                    row=clean,
                    expected_defect_types=(),
                ),
                CorpusExample(
                    example_id=f"example-{split_index}-{group_index}-b",
                    source_group=group,
                    split=split,
                    row=mutant,
                    expected_defect_types=("schema_drift",),
                ),
            ])
    validate_corpus(examples)
    return examples


def _test_policy(groups: int = 3) -> GatePolicy:
    return GatePolicy(
        min_train_positives=groups,
        min_train_negatives=groups,
        min_dev_positives=groups,
        min_dev_negatives=groups,
        min_holdout_positives=groups,
        min_holdout_negatives=groups,
        min_dev_recall=1.0,
        min_holdout_recall=1.0,
        min_dev_paired_discrimination=1.0,
        min_holdout_paired_discrimination=1.0,
        max_dev_false_positive_rate=0.0,
        max_holdout_false_positive_rate=0.0,
        min_dev_recall_wilson_lower=0.0,
        min_holdout_recall_wilson_lower=0.0,
        max_dev_false_positive_wilson_upper=1.0,
        max_holdout_false_positive_wilson_upper=1.0,
    )


def test_rule_schema_rejects_label_leakage_and_executable_features():
    payload = _rule().to_dict()
    payload["rule_id"] = "cheat_by_mutation_id"
    payload["conditions"][0]["left"]["path"] = ["_injected_defect", "operator"]
    with pytest.raises(RuleValidationError, match="identity, split, or provenance"):
        RuleSpec.from_dict(payload)

    payload = _rule().to_dict()
    payload["conditions"][0]["operator"] = "python_eval"
    with pytest.raises(RuleValidationError, match="unsupported condition operator"):
        RuleSpec.from_dict(payload)

    payload = _rule().to_dict()
    payload["defect_type"] = "model_invented_new_taxonomy"
    with pytest.raises(RuleValidationError, match="registered defect types"):
        RuleSpec.from_dict(payload)


def test_rule_interpreter_matches_pair_and_abstains_on_unparseable_input():
    rows = [
        {"item_id": "clean", "task": "x", "rubrics": ["a"], "rubric_types": ["b"]},
        {"item_id": "mutant", "task": "x", "rubrics": ["a"], "rubric_types": []},
        {"item_id": "bad", "task": "x", "rubrics": "[", "rubric_types": "[]"},
    ]
    items = build_items(rows, load_mapping(None, rows))
    assert evaluate_rule(_rule(), items[0]).matched is False
    assert evaluate_rule(_rule(), items[1]).matched is True
    outcome = evaluate_rule(_rule(), items[2])
    assert outcome.status == "abstained"
    assert outcome.matched is None


def test_generated_checker_is_forced_to_review_and_uses_live_identity():
    rows = [{
        "item_id": "visible-id",
        "task": "x",
        "rubrics": ["a"],
        "rubric_types": [],
    }]
    item = build_items(rows, load_mapping(None, rows))[0]
    result = audit_items_with_ledger(
        [item],
        checkers=[DeclarativeRuleChecker(_rule(), registry_receipt="receipt-1")],
        dataset_checkers=[],
    )
    assert len(result.violations) == 1
    finding = result.violations[0]
    assert finding.item_id == item.item_id
    assert finding.row_uid == item.row_uid
    assert finding.detection_method == "learned_declarative_rule"
    assert finding.evidence_tier == "review"
    assert finding.review_only is True
    assert finding.evidence["automatic_confirmation_authority"] is False
    assert result.ledger[0].status == "finding"


def test_corpus_rejects_split_sibling_and_embedded_provenance():
    examples = _examples(1)
    leaked = list(examples)
    original = leaked[-1]
    leaked[-1] = CorpusExample(
        example_id=original.example_id,
        source_group=leaked[0].source_group,
        split="holdout",
        row=original.row,
        expected_defect_types=original.expected_defect_types,
    )
    with pytest.raises(RuleValidationError, match="cross train/dev/holdout"):
        validate_corpus(leaked)

    with pytest.raises(RuleValidationError, match="sidecar provenance"):
        CorpusExample.from_dict({
            "example_id": "x",
            "source_group": "g",
            "split": "train",
            "row": {"task": "x", "_injected_defect": {"operator": "remove_task"}},
            "expected_defect_types": ["missing_task"],
        })


def test_synthesis_projection_removes_identifiers_and_sidecar_metadata():
    projected = synthesis_projection(_examples(1))
    text = json.dumps(projected, ensure_ascii=False)
    assert "item_id" not in text
    assert "source_group" not in text
    assert "example_id" not in text
    assert "expected_defect_types" in text


def test_controller_iterates_on_dev_then_consumes_holdout_once():
    class TwoRoundSynthesizer:
        def __init__(self):
            self.calls = 0
            self.feedback = []

        def propose(self, train_examples, *, feedback, max_candidates):
            assert all(example.split == "train" for example in train_examples)
            self.calls += 1
            self.feedback.append(list(feedback))
            return [_always_match_rule()] if self.calls == 1 else [_rule()]

    synthesizer = TwoRoundSynthesizer()
    run = EvolutionController(
        synthesizer,
        policy=_test_policy(),
        max_rounds=3,
        max_candidates_per_round=1,
        max_total_candidates=3,
    ).run(_examples())
    assert synthesizer.calls == 2
    assert run.status == "accepted"
    assert run.holdout_attempts == 1
    assert run.lineage_closed is True
    assert run.final_evaluation is not None
    assert run.final_evaluation.holdout is not None
    assert run.final_evaluation.holdout.recall == 1.0
    assert run.final_evaluation.holdout.false_positive_rate == 0.0
    # Round feedback contains aggregate dev metrics, never holdout rows/results.
    assert "holdout" not in json.dumps(synthesizer.feedback)


def test_flag_all_reward_hack_never_reaches_holdout():
    run = EvolutionController(
        StaticRuleSynthesizer([_always_match_rule()]),
        policy=_test_policy(),
        max_rounds=2,
    ).run(_examples())
    assert run.status == "no_candidate"
    assert run.holdout_attempts == 0
    candidate = run.rounds[0]["candidates"][0]
    assert candidate["dev"]["false_positive_rate"] == 1.0
    assert candidate["dev_passed"] is False


def test_registry_activation_roundtrip_and_tamper_detection(tmp_path: Path):
    spec = _rule()
    run = EvolutionController(
        StaticRuleSynthesizer([spec]),
        policy=_test_policy(100),
    ).run(_examples(100))
    registry = EvolutionRegistry(tmp_path / "registry")
    activated = registry.activate(spec, run)
    assert activated["receipt"]["evidence_ceiling"] == "review"
    checkers = registry.load_active(family="generic")
    assert len(checkers) == 1
    assert checkers[0].spec.sha256 == spec.sha256

    rule_path = registry.root / activated["registry"]["active"][0]["rule_path"]
    payload = json.loads(rule_path.read_text(encoding="utf-8"))
    payload["message"] = "tampered"
    rule_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuleValidationError, match="digest"):
        registry.load_active(family="generic")


def test_registry_can_quarantine_external_representation_failure(tmp_path: Path):
    spec = _rule()
    run = EvolutionController(
        StaticRuleSynthesizer([spec]),
        policy=_test_policy(100),
    ).run(_examples(100))
    registry = EvolutionRegistry(tmp_path / "registry")
    registry.activate(spec, run)
    result = registry.deactivate(
        spec.rule_id,
        reason="deployment representation canary produced false positives",
    )
    assert result["registry"]["active"] == []
    assert registry.load_active(family="generic") == []
    events = [
        json.loads(line)
        for line in registry.events_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event"] for event in events] == ["activate", "deactivate"]


def test_evolve_cli_and_audit_registry_integration(tmp_path: Path):
    corpus = {
        "schema_version": "benchcore-evolution-corpus-v1",
        "examples": [example.to_dict() for example in _examples(100)],
    }
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(_rule().to_dict()), encoding="utf-8")
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(_test_policy(100).to_dict()), encoding="utf-8")
    run_path = tmp_path / "run.json"
    registry_path = tmp_path / "registry"
    assert main([
        "evolve-rules",
        str(corpus_path),
        "--proposal", str(proposal_path),
        "--gate-policy", str(policy_path),
        "--registry-dir", str(registry_path),
        "--activate",
        "--strict",
        "--out", str(run_path),
    ]) == 0
    assert json.loads(run_path.read_text())["status"] == "accepted"

    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(json.dumps({
        "item_id": "real-row",
        "task": "Create a file.",
        "rubrics": ["a", "b"],
        "rubric_types": ["basic"],
        "output_contract": {"type": "workspace_files"},
        "evaluator": {"type": "workspacebench_rubric"},
    }) + "\n", encoding="utf-8")
    report_path = tmp_path / "audit.json"
    assert main([
        "audit", str(dataset_path),
        "--profile", "generic",
        "--basic-only",
        "--evolution-registry", str(registry_path),
        "--out", str(report_path),
    ]) == 0
    report = json.loads(report_path.read_text())
    learned = [
        row for row in report["violations"]
        if row["detection_method"] == "learned_declarative_rule"
    ]
    assert len(learned) == 1
    assert learned[0]["evidence_tier"] == "review"
    assert report["run_metadata"]["evolution_registry"]["loaded_checker_count"] == 1
