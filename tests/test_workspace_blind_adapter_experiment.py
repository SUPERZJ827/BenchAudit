import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import scripts.run_workspace_blind_adapter_experiment as experiment

from benchcore.adaptation import (
    AdapterController,
    AdapterSpec,
    StaticAdapterSynthesizer,
    adapt_rows,
    build_schema_profile,
    evaluate_adapter,
)
from benchcore.adaptation.synthesis import deterministic_adapter_candidate
from benchcore.adaptation.synthesis import (
    LLMAdapterSynthesizer,
    WORKSPACE_PLAN_SCHEMA_VERSION,
)
from benchcore.loader import load_rows
from scripts.run_workspace_blind_adapter_experiment import (
    DEFAULT_SCHEMA_VARIANT,
    INAPPLICABLE_CORE_TARGETS,
    PUBLIC_CHALLENGE_KEYS,
    PUBLIC_CHALLENGE_ROOTS,
    REFERENCE_TARGETS,
    assert_public_schema_is_blind,
    build_experiment,
    canonical_json,
    load_experiment,
    oracle_adapter_spec,
    run_live,
    run_offline,
    score_passed,
    score_run,
)


def source_row(index: int, attachment: Path) -> dict:
    output_files = [f"report-{index}.md"]
    rubrics = [f"Report {index} contains the requested evidence."]
    rubric_types = ["Outcome Evaluation"]
    manifest = [{
        "filename": "source.txt",
        "stored_relpath": f"data/{attachment.name}",
    }]
    graph = [{"from": "source.txt", "to": output_files[0]}]
    return {
        "absolute_id": index,
        "task": f"Read source.txt and create report {index}.",
        "rubrics": rubrics,
        "rubric_types": json.dumps(rubric_types),
        "output_files": json.dumps(output_files),
        "input_files": [str(attachment)],
        "data_manifest": json.dumps(manifest),
        "file_dep_graph": json.dumps(graph),
        "tested_capabilities": json.dumps(["Workspace Exploration"]),
        "language": "en",
        "persona": "Research analyst",
        "task_diff": "medium",
        "item_id": f"workspacebench-{index}",
        # The builder must ignore these already-derived source fields.
        "context": {"do_not_copy": True},
        "output_contract": {"do_not_copy": True},
        "evaluator": {"do_not_copy": True},
        "metadata": {"do_not_copy": True},
    }


def build_fixture(
    tmp_path: Path,
    count: int = 20,
    *,
    schema_variant: str = DEFAULT_SCHEMA_VARIANT,
    out_name: str = "blind",
) -> tuple[Path, Path, Path]:
    attachment = tmp_path / "0123456789abcdef_source.txt"
    attachment.write_text("facts", encoding="utf-8")
    source_path = tmp_path / "full.jsonl"
    rows = [source_row(index + 1, attachment) for index in range(count)]
    source_path.write_text(
        "".join(canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    out_dir = tmp_path / out_name
    build_experiment(
        source_path,
        out_dir,
        expected_rows=count,
        schema_variant=schema_variant,
    )
    return source_path, out_dir, attachment


def test_builder_removes_canonical_fields_and_defeats_alias_inference(tmp_path: Path):
    _, out_dir, _ = build_fixture(tmp_path)

    public_rows, references, manifest = load_experiment(out_dir)
    profile = build_schema_profile(public_rows)

    assert len(public_rows) == len(references) == 20
    assert deterministic_adapter_candidate(
        public_rows, profile, family="workspacebench",
    ) is None
    assert manifest["public_challenge"]["deterministic_alias_candidate"] is False
    assert manifest["sealed_reference"]["llm_visible"] is False
    assert manifest["sealed_reference"]["targets"] == sorted(REFERENCE_TARGETS)
    assert manifest["sealed_reference"]["inapplicable_core_targets"] == sorted(
        INAPPLICABLE_CORE_TARGETS
    )

    forbidden = {
        "item_id", "task", "context", "output_contract", "evaluator",
        "metadata", "input_files", "rubrics", "rubric_types", "output_files",
    }
    for public, reference in zip(public_rows, references):
        assert_public_schema_is_blind(public)
        assert not (forbidden & set(public))
        assert set(reference) == REFERENCE_TARGETS
    public_text = (out_dir / "public_challenge" / "challenge.jsonl").read_text(
        encoding="utf-8"
    )
    assert '"canonical_reference"' not in public_text
    assert '"adapter_answer"' not in public_text

    spec = oracle_adapter_spec(public_rows)
    assert isinstance(spec, AdapterSpec)
    assert spec.targets == REFERENCE_TARGETS
    adapted = adapt_rows(public_rows, spec, strict_rows=True)
    assert list(adapted.rows) == references
    verified = evaluate_adapter(spec, public_rows, references=references)
    assert verified.accepted is True
    assert verified.activation_mode == "active_verified"
    assert verified.reference.field_accuracy == 1.0
    assert verified.reference.row_accuracy == 1.0


def test_offline_oracle_regression_scores_every_target_and_checker_path(tmp_path: Path):
    _, out_dir, attachment = build_fixture(tmp_path)

    run, score = run_offline(
        out_dir, allowed_roots=[tmp_path], workers=2,
    )

    assert run["synthesis"]["blind_discovery_claim_eligible"] is False
    assert score["experiment_type"] == "offline_oracle_interpreter_regression"
    assert score["blind_discovery_claim_eligible"] is False
    assert score_passed(score) is True
    assert score["attempts"]["first_candidate_verified_success"] is True
    assert score["attempts"]["verified_within_budget"] is True
    assert score["attempts"]["candidates_evaluated"] == 1
    assert score["sealed_reference"]["reference_attempts"] == 1
    assert score["target_coverage_complete"] is True
    assert score["reference_exactness"]["equal_fields"] == 20 * len(
        REFERENCE_TARGETS
    )
    assert score["reference_exactness"]["field_accuracy"] == 1.0
    assert score["reference_exactness"]["equal_rows"] == 20
    assert score["reference_exactness"]["row_accuracy"] == 1.0
    assert score["adaptation"]["abstained_rows"] == 0
    assert score["adaptation"]["errors"] == []
    assert score["component_gaps"]["summary"] == {
        "resolved": 7,
        "unresolved": 0,
        "requires_trusted_plugin": 5,
    }
    assert score["workspace_checker_parity"]["natural"]["parity"]["rate"] == 1.0
    positive = score["workspace_checker_parity"][
        "rubric_divergence_positive_control"
    ]
    assert positive["parity"]["rate"] == 1.0
    assert positive["reference_findings"] == positive["adapted_findings"] == 20
    assert attachment.is_file()


def test_semantic_v2_is_a_disjoint_fingerprinted_holdout(tmp_path: Path):
    source_path, v1_dir, attachment = build_fixture(tmp_path, count=20)
    v2_dir = tmp_path / "blind-v2"
    build_experiment(
        source_path,
        v2_dir,
        expected_rows=20,
        schema_variant="semantic_v2",
    )

    v1_public, v1_references, v1_manifest = load_experiment(v1_dir)
    v2_public, v2_references, v2_manifest = load_experiment(v2_dir)

    assert v1_manifest["schema_variant"] == "semantic_v1"
    assert v2_manifest["schema_variant"] == "semantic_v2"
    assert v1_manifest["holdout_fingerprint"] != v2_manifest["holdout_fingerprint"]
    assert (
        v1_manifest["public_challenge"]["schema_fingerprint"]
        != v2_manifest["public_challenge"]["schema_fingerprint"]
    )
    assert v1_dir.resolve() != v2_dir.resolve()
    assert PUBLIC_CHALLENGE_ROOTS["semantic_v1"].isdisjoint(
        PUBLIC_CHALLENGE_ROOTS["semantic_v2"]
    )
    assert PUBLIC_CHALLENGE_KEYS["semantic_v1"].isdisjoint(
        PUBLIC_CHALLENGE_KEYS["semantic_v2"]
    )
    assert set(v2_public[0]) == PUBLIC_CHALLENGE_ROOTS["semantic_v2"]
    assert v1_references == v2_references
    for row in v2_public:
        assert_public_schema_is_blind(row, schema_variant="semantic_v2")

    profile = build_schema_profile(v2_public)
    assert deterministic_adapter_candidate(
        v2_public, profile, family="workspacebench",
    ) is None
    spec = oracle_adapter_spec(v2_public, schema_variant="semantic_v2")
    adapted = adapt_rows(v2_public, spec, strict_rows=True)
    assert list(adapted.rows) == v2_references
    assert set(adapted.rows[0]["metadata"]) == {
        "absolute_id", "language", "persona", "task_diff",
    }
    assert not (
        {"language_tag", "actor_role", "difficulty_band"}
        & set(adapted.rows[0]["metadata"])
    )

    run, score = run_offline(
        v2_dir, allowed_roots=[tmp_path], workers=2,
    )
    assert run["synthesis"]["schema_variant"] == "semantic_v2"
    assert score["schema_variant"] == "semantic_v2"
    assert score["experiment_type"] == "offline_oracle_interpreter_regression"
    assert score["blind_discovery_claim_eligible"] is False
    assert score["holdout_fingerprint"] == v2_manifest["holdout_fingerprint"]
    assert score_passed(score) is True
    assert score["reference_exactness"]["equal_fields"] == 20 * len(
        REFERENCE_TARGETS
    )
    assert score["reference_exactness"]["field_accuracy"] == 1.0
    assert score["reference_exactness"]["row_accuracy"] == 1.0
    assert attachment.is_file()

    with pytest.raises(ValueError, match="different schema variant"):
        build_experiment(
            source_path,
            v1_dir,
            expected_rows=20,
            schema_variant="semantic_v2",
        )


def test_semantic_v2_compact_plan_compiler_can_express_all_reference_targets(
    tmp_path: Path,
):
    """Offline expressivity regression; this is deliberately not a blind claim."""

    _, out_dir, _ = build_fixture(
        tmp_path,
        count=20,
        schema_variant="semantic_v2",
    )
    public_rows, references, _ = load_experiment(out_dir)
    profile = build_schema_profile(public_rows)
    path_ids = {entry.path: index for index, entry in enumerate(profile.paths)}
    slots = {
        "item_id": path_ids[("unit_identity", "serial_index")],
        "task": path_ids[("work_request", "objective_text")],
        "rubrics": path_ids[("evaluation_rules", "check_items")],
        "rubric_types": path_ids[("evaluation_rules", "check_categories")],
        "output_files": path_ids[("deliverables", "expected_artifacts")],
        "data_manifest": path_ids[("evidence_bundle", "asset_inventory")],
        "file_dep_graph": path_ids[("evidence_bundle", "lineage_edges")],
        "input_files": path_ids[("evidence_bundle", "resolved_asset_paths")],
        "tested_capabilities": path_ids[("capability_declaration", "features")],
        "metadata.absolute_id": path_ids[("unit_identity", "serial_index")],
        "metadata.language": path_ids[("record_attributes", "language_tag")],
        "metadata.persona": path_ids[("record_attributes", "actor_role")],
        "metadata.task_diff": path_ids[("record_attributes", "difficulty_band")],
    }

    class PlanClient:
        def chat_json(self, system, user):
            del system, user
            return {
                "schema_version": WORKSPACE_PLAN_SCHEMA_VERSION,
                "plans": [{"slots": slots}],
            }

    spec = LLMAdapterSynthesizer(PlanClient()).propose(
        profile,
        family="workspacebench",
        feedback=[{
            "trusted_contract": {
                "family": "workspacebench",
                "required_targets": sorted(REFERENCE_TARGETS),
            },
        }],
        max_candidates=1,
    )[0]
    adapted = adapt_rows(public_rows, spec, strict_rows=True)

    assert spec.targets == REFERENCE_TARGETS
    assert list(adapted.rows) == references
    verified = evaluate_adapter(spec, public_rows, references=references)
    assert verified.accepted is True
    assert verified.reference.field_accuracy == 1.0
    assert verified.reference.row_accuracy == 1.0


def test_wrong_semantic_mapping_passes_shape_but_fails_sealed_reference(tmp_path: Path):
    _, out_dir, _ = build_fixture(tmp_path)
    public_rows, references, _ = load_experiment(out_dir)
    good = oracle_adapter_spec(public_rows)
    payload = good.to_dict()
    for binding in payload["bindings"]:
        if binding["target"] == "task":
            binding["path"] = ["benchmark_annotations", "role_description"]
            binding["transforms"] = ["strip"]
    bad = AdapterSpec.from_dict(payload)
    run = AdapterController(
        StaticAdapterSynthesizer([bad]),
        max_rounds=1,
        max_candidates_per_round=1,
        max_total_candidates=1,
    ).run(
        public_rows,
        build_schema_profile(public_rows),
        family="workspacebench",
        references=references,
    )
    assert run.rounds[0]["candidates"][0]["structural_passed"] is True
    assert run.status == "quarantined"
    assert run.reference_attempts == 1

    result_dir = out_dir / "wrong_control"
    run_path = result_dir / "run.json"
    result_dir.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        json.dumps(run.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    score = score_run(
        out_dir,
        run_path,
        result_dir=result_dir,
        allowed_roots=[tmp_path],
        workers=2,
    )

    assert score_passed(score) is False
    assert score["attempts"]["first_candidate_verified_success"] is False
    assert score["reference_exactness"]["per_target"]["task"]["accuracy"] == 0.0
    assert score["reference_exactness"]["field_accuracy"] < 1.0
    assert score["reference_exactness"]["row_accuracy"] == 0.0
    # The checker does not consume task text, so parity can remain perfect.
    # Exact external references are therefore a necessary independent metric.
    assert score["workspace_checker_parity"]["natural"]["parity"]["rate"] == 1.0


def test_tamper_and_unapproved_live_egress_fail_closed(tmp_path: Path):
    _, out_dir, _ = build_fixture(tmp_path)
    challenge_path = out_dir / "public_challenge" / "challenge.jsonl"
    rows = load_rows(challenge_path)
    tampered = copy.deepcopy(rows[0])
    tampered["unexpected"] = True
    challenge_path.write_text(
        canonical_json(tampered) + "\n" + "".join(
            canonical_json(row) + "\n" for row in rows[1:]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="manifest-bound artifact changed"):
        load_experiment(out_dir)

    # Rebuild before testing the remote-consent guard; no API call is made.
    source_path = tmp_path / "full.jsonl"
    build_experiment(source_path, out_dir, expected_rows=20)
    with pytest.raises(ValueError, match="allow-remote-data-egress"):
        run_live(
            out_dir,
            llm_config=tmp_path / "unused.json",
            llm_cache=None,
            allow_remote_data_egress=False,
            max_rounds=1,
            max_candidates_per_round=1,
            max_total_candidates=1,
            live_dir=out_dir / "live",
            allowed_roots=[tmp_path],
            workers=1,
        )


def test_live_attempt_is_consumed_before_synthesis_and_blocks_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        experiment,
        "LIVE_CONSUMPTION_REGISTRY",
        tmp_path / "fingerprint-registry",
    )
    source_path, out_dir, _ = build_fixture(tmp_path)
    config_path = tmp_path / "llm.json"
    config_path.write_text('{"provider":"test"}\n', encoding="utf-8")
    calls = 0

    def fail_after_claim(args: list[str]) -> int:
        nonlocal calls
        calls += 1
        raise RuntimeError("synthetic pre-egress failure")

    monkeypatch.setattr(experiment, "benchcore_main", fail_after_claim)
    live_dir = out_dir / "live-first"
    with pytest.raises(RuntimeError, match="synthetic pre-egress failure"):
        experiment.run_live(
            out_dir,
            llm_config=config_path,
            llm_cache=None,
            allow_remote_data_egress=True,
            max_rounds=1,
            max_candidates_per_round=1,
            max_total_candidates=1,
            live_dir=live_dir,
            allowed_roots=[tmp_path],
            workers=1,
        )
    receipt_path = out_dir / "sealed_reference" / "live_consumption" / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert calls == 1
    assert receipt["state"] == "attempt_failed"
    assert receipt["failure_counts_as_consumed"] is True
    assert receipt["blind_discovery_claim_eligible"] is True
    assert receipt["error_type"] == "RuntimeError"

    with pytest.raises(RuntimeError, match="already consumed"):
        experiment.run_live(
            out_dir,
            llm_config=config_path,
            llm_cache=None,
            allow_remote_data_egress=True,
            max_rounds=1,
            max_candidates_per_round=1,
            max_total_candidates=1,
            live_dir=out_dir / "live-second",
            allowed_roots=[tmp_path],
            workers=1,
        )
    assert calls == 1
    with pytest.raises(RuntimeError, match="refusing to rebuild a consumed"):
        build_experiment(source_path, out_dir, expected_rows=20)
    with pytest.raises(RuntimeError, match="fingerprint.*already been consumed"):
        build_experiment(
            source_path,
            tmp_path / "duplicate-holdout-directory",
            expected_rows=20,
        )


def test_direct_script_invocation_exposes_schema_variant_cli():
    script_path = Path(experiment.__file__).resolve()
    completed = subprocess.run(
        [sys.executable, str(script_path), "all-offline", "--help"],
        cwd=script_path.parents[1],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--schema-variant" in completed.stdout
    assert "semantic_v2" in completed.stdout
