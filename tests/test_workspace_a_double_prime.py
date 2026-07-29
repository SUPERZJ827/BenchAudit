import json
from pathlib import Path

import pytest

from benchcore.workspace_constraint_residue import (
    DerivationCertificate,
    extract_noun_phrases,
    normalize_text,
    route_constraint_residue,
)
from scripts import analyze_workspace_a_double_prime as analysis
from scripts.run_workspace_static_llm_ablation import POSITIVE_REVIEW_LABEL


def _route(
    *,
    reason="task_supported",
    source="task",
    quote="",
    action="do_not_route",
):
    return {
        "action": action,
        "reason_code": reason,
        "evidence_source": source,
        "evidence_quote": quote,
        "confidence": 1.0,
        "policy_selected_before_threshold": action == "route",
    }


def _observe(
    rubric,
    *,
    task="Create a report.",
    contract=None,
    route=None,
    inventory="",
    certificates=None,
):
    return route_constraint_residue(
        item_id="synthetic-item",
        rubric_index=0,
        rubric=rubric,
        route=route or _route(),
        task=task,
        output_contract=contract or {"required_files": ["report.md"]},
        input_inventory=inventory,
        derivation_certificates=certificates,
    )


def _reasons(observation):
    return {
        (hit.rule_id, hit.reason)
        for hit in (() if observation is None else observation.hits)
    }


def test_normalization_is_nfkc_casefold_and_punctuation_insensitive():
    assert normalize_text("Ａ—B.\nC") == "a b c"
    phrases = extract_noun_phrases("A BAR chart and text.")
    assert phrases[0]["span"].text == "BAR chart"
    assert phrases[0]["span"].start == 2


def test_h1_distinguishes_positive_support_from_other_empty_quotes():
    _, positive = _observe(
        "Is the report complete?",
        task="Create a complete report.",
        route=_route(reason="task_supported", quote=""),
    )
    _, general = _observe(
        "Is the report clear?",
        route=_route(reason="general_quality", source="intrinsic", quote=""),
    )
    assert positive["status"] == "invalid"
    assert positive["reason"] == "empty_quote"
    assert general is None


def test_h1_validates_quote_against_declared_source():
    _, valid = _observe(
        "Is the report complete?",
        task="Create a Complete report.",
        route=_route(reason="task_supported", quote="complete report"),
    )
    _, invalid = _observe(
        "Is the report complete?",
        task="Create a concise report.",
        route=_route(reason="task_supported", quote="complete report"),
    )
    assert valid["status"] == "valid"
    assert invalid["status"] == "invalid"


def test_r2a_requires_relation_and_anchor_and_respects_direct_support():
    observation, _ = _observe(
        "Does the first slide come from panel Q?",
        task="Merge the supplied panels into one deck.",
    )
    missing_anchor, _ = _observe(
        "Does the deck use the correct ordering?",
        task="Merge the supplied panels into one deck.",
    )
    supported, _ = _observe(
        "Does the first slide come from panel Q?",
        task="The first slide must come from panel Q.",
    )
    assert ("R2a", "unsupported_order_or_position") in _reasons(observation)
    assert missing_anchor is None
    assert supported is None


def test_r2b_direct_certificate_delegation_4a_and_4b_paths():
    direct, _ = _observe(
        "Does the report contain exactly five sections?",
        task="Create a report with exactly five sections.",
    )
    certificate, _ = _observe(
        "Does the report cover exactly twelve months?",
        task="Summarize the full calendar year.",
    )
    delegated, _ = _observe(
        "Does the summary include exactly three records?",
        task="Include every record in the summary.",
        inventory="three records",
        route=_route(source="input", quote="three records"),
    )
    absent, _ = _observe(
        "Does the report contain exactly seven charts?",
    )
    descriptive, _ = _observe(
        "Does the report contain at least ten specific improvement suggestions?",
        route=_route(
            reason="input_supported",
            source="input",
            quote=(
                "Alpha idea, Beta idea, Gamma idea, Delta idea, Epsilon idea, "
                "Zeta idea, Eta idea, Theta idea, Iota idea, Kappa idea"
            ),
        ),
    )
    assert direct is None
    assert certificate is None
    assert delegated is None
    assert ("R2b", "unsupported_quantity_without_source") in _reasons(absent)
    assert (
        "R2b",
        "descriptive_input_not_normative_obligation",
    ) in _reasons(descriptive)


def test_r2b_conflicting_normative_value_routes_under_4a():
    observation, _ = _observe(
        "Does the report contain at least five suggestions?",
        task="Provide at least three suggestions.",
    )
    hit = next(hit for hit in observation.hits if hit.rule_id == "R2b")
    assert hit.reason == "unsupported_quantity_without_source"
    assert hit.details["conflicting_normative_atoms"][0]["count"] == 3


def test_r2b_partial_certificate_only_exempts_covered_atom():
    certificate = DerivationCertificate(
        derivation_id="year-months-v1",
        object_head="month",
        count=12,
    )
    observation, _ = _observe(
        "Does the report contain exactly twelve months and exactly five charts?",
        certificates=(certificate,),
    )
    hits = [hit for hit in observation.hits if hit.rule_id == "R2b"]
    assert len(hits) == 1
    assert hits[0].details["atom"]["object_head"] == "chart"


def test_r2b_and_r2d_union_preserves_both_reasons():
    observation, _ = _observe(
        "Does the report include five sections: Alpha, Beta, Gamma, Delta, and Epsilon?",
    )
    assert observation.rule_ids == ("R2b", "R2d")
    assert len(observation.hits) == 2


def test_r2b_treats_named_list_without_explicit_number_as_closed_set():
    observation, _ = _observe(
        "Does the report include sections for Alpha, Beta, and Gamma?",
    )
    hit = next(hit for hit in observation.hits if hit.rule_id == "R2b")
    assert hit.details["atom"]["count"] == 3
    assert hit.details["atom"]["closed_members"] == ("Alpha", "Beta", "Gamma")


def test_r2c_parses_shared_head_modifier_and_rejects_supported_modifier():
    observation, _ = _observe(
        "Was a bar chart generated?",
        task="Create a visualization chart.",
    )
    supported, _ = _observe(
        "Was a bar chart generated?",
        task="Create a bar chart.",
    )
    hit = next(hit for hit in observation.hits if hit.rule_id == "R2c")
    assert hit.details["rubric_head"] == "chart"
    assert hit.details["residual_modifiers"] == ["bar"]
    assert supported is None


def test_r2c_does_not_use_same_word_outside_np_or_multiple_heads():
    unrelated, _ = _observe(
        "Was a bar chart generated?",
        task="Put a bar beside the chart title.",
    )
    competing, _ = _observe(
        "Were a bar chart and a pie chart generated?",
        task="Create a visualization chart.",
    )
    assert unrelated is None
    assert competing is None


def test_r2c_abstains_for_entirely_new_object_head_without_fallback():
    observation, _ = _observe(
        "Does the dashboard contain three bar charts?",
        task="Create a visual dashboard.",
    )
    assert observation is not None
    assert "R2b" in observation.rule_ids
    assert "R2c" not in observation.rule_ids


def test_r2d_named_structure_general_quality_and_direct_support():
    route = _route(reason="general_quality", source="intrinsic")
    observation, _ = _observe(
        "Does the report include sections for Alpha plan, Beta plan, and Gamma plan?",
        route=route,
    )
    supported, _ = _observe(
        "Does the report include sections for Alpha plan, Beta plan, and Gamma plan?",
        task="Use sections for Alpha plan, Beta plan, and Gamma plan.",
        route=route,
    )
    assert ("R2d", "unsupported_named_structure") in _reasons(observation)
    assert supported is None


def test_observation_is_review_only_and_route_rows_are_not_reclassified():
    observation, _ = _observe(
        "Does the report contain exactly seven charts?",
    )
    routed, _ = _observe(
        "Does the report contain exactly seven charts?",
        route=_route(
            reason="unsupported_exact_constraint",
            source="none",
            action="route",
        ),
    )
    assert observation.review_only is True
    assert observation.confirmation_eligible is False
    assert routed is None


def test_candidate_id_and_rule_order_are_deterministic():
    first, _ = _observe(
        "Does the report include five sections: Alpha, Beta, Gamma, Delta, and Epsilon?",
    )
    second, _ = _observe(
        "Does the report include five sections: Alpha, Beta, Gamma, Delta, and Epsilon?",
    )
    assert first.candidate_id == second.candidate_id
    assert first.rule_ids == tuple(sorted(first.rule_ids))
    assert first.to_dict() == second.to_dict()


def test_frozen_input_gate_requires_root_and_rejects_missing_or_changed(
    tmp_path: Path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    artifact = tmp_path / "artifact"
    repo.mkdir()
    artifact.mkdir()
    repo_file = repo / "protocol.md"
    artifact_file = artifact / "result.json"
    repo_file.write_text("protocol", encoding="utf-8")
    artifact_file.write_text("result", encoding="utf-8")
    monkeypatch.setattr(
        analysis,
        "FROZEN_REPO_INPUTS",
        {"protocol.md": analysis.sha256_file(repo_file)},
    )
    monkeypatch.setattr(
        analysis,
        "FROZEN_ARTIFACT_INPUTS",
        {"result.json": analysis.sha256_file(artifact_file)},
    )
    with pytest.raises(ValueError, match="artifact-root"):
        analysis.verify_frozen_inputs(repo_root=repo, artifact_root=None)
    assert analysis.verify_frozen_inputs(
        repo_root=repo, artifact_root=artifact,
    )
    artifact_file.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        analysis.verify_frozen_inputs(repo_root=repo, artifact_root=artifact)
    artifact_file.unlink()
    with pytest.raises(ValueError, match="missing"):
        analysis.verify_frozen_inputs(repo_root=repo, artifact_root=artifact)


def test_missing_structured_route_is_operational_unknown_not_clean():
    rows = {
        "synthetic-item": {
            "decisions": [{"rubric_index": 0, "scanner": {}}],
        },
    }
    candidates, count, unknown = analysis._a_prime_candidates(rows)
    assert candidates == set()
    assert count == 1
    assert unknown == ["synthetic-item"]


def test_reviewed_metrics_are_conditioned_on_calibration_tasks():
    metrics = analysis._reviewed_metrics(
        {("task-a", 0)},
        {
            ("task-a", 0): POSITIVE_REVIEW_LABEL,
            ("task-b", 0): POSITIVE_REVIEW_LABEL,
        },
        {"task-a"},
    )
    assert metrics["universe"] == 1
    assert metrics["positives"] == 1
    assert metrics["tp"] == 1


def test_rule_combinations_and_tie_break_are_deterministic():
    combinations = analysis.rule_id_combinations()
    assert len(combinations) == 15
    rows = [
        {
            "rule_ids": ["R2b", "R2d"],
            "candidates": 200,
            "family_hits": 17,
            "pass": True,
        },
        {
            "rule_ids": ["R2a"],
            "candidates": 200,
            "family_hits": 17,
            "pass": True,
        },
        {
            "rule_ids": ["R2b"],
            "candidates": 200,
            "family_hits": 17,
            "pass": True,
        },
    ]
    assert analysis.choose_working_point(rows)["rule_ids"] == ["R2a"]
