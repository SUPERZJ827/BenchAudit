from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchcore.adaptation import (
    AdapterController,
    AdapterGatePolicy,
    AdapterRegistry,
    AdapterSpec,
    AdapterValidationError,
    StaticAdapterSynthesizer,
    adapt_rows,
    analyze_component_gaps,
    build_schema_profile,
    evaluate_adapter,
    schema_fingerprint,
)
from benchcore.adaptation.synthesis import (
    LLMAdapterSynthesizer,
    WORKSPACE_PLAN_SCHEMA_VERSION,
)
from benchcore.cli import main


def _nested_rows(count: int = 30) -> list[dict]:
    return [
        {
            "record": {"opaque": f"x-{index}"},
            "job": {"instruction": f"Solve task number {index}."},
            "assessment": {
                "criteria": [f"criterion {index}"],
                "kinds": ["Outcome Evaluation"],
            },
            "delivery": {"files": [f"answer-{index}.txt"]},
            "resources": {
                "manifest": [{"filename": f"input-{index}.txt"}],
                "dependencies": [{"from": f"input-{index}.txt", "to": f"answer-{index}.txt"}],
            },
            "stats": {"number": index},
        }
        for index in range(count)
    ]


def _nested_spec(rows: list[dict]) -> AdapterSpec:
    return AdapterSpec.from_dict({
        "schema_version": "benchcore-adapter-v1",
        "adapter_id": "nested_workspace_adapter",
        "version": 1,
        "family": "workspacebench",
        "schema_fingerprint": schema_fingerprint(rows),
        "description": "Nested Workspace schema test adapter.",
        "bindings": [
            {
                "target": "item_id",
                "template": {
                    "format": "workspacebench-{value}",
                    "path": ["record", "opaque"],
                    "transforms": ["stringify"],
                },
                "transforms": [],
                "required": True,
            },
            {
                "target": "task",
                "path": ["job", "instruction"],
                "transforms": ["strip"],
                "required": True,
            },
            {
                "target": "evaluator",
                "object": [
                    {
                        "key": "type",
                        "literal": "workspacebench_rubric",
                        "transforms": [],
                        "required": True,
                    },
                    {
                        "key": "rubrics",
                        "path": ["assessment", "criteria"],
                        "transforms": ["as_list"],
                        "required": True,
                    },
                    {
                        "key": "rubric_types",
                        "path": ["assessment", "kinds"],
                        "transforms": ["as_list"],
                        "required": True,
                    },
                ],
                "transforms": [],
                "required": True,
            },
            {
                "target": "output_contract",
                "object": [{
                    "key": "required_files",
                    "path": ["delivery", "files"],
                    "transforms": ["as_list"],
                    "required": True,
                }],
                "transforms": [],
                "required": True,
            },
            {
                "target": "context",
                "object": [
                    {
                        "key": "data_manifest",
                        "path": ["resources", "manifest"],
                        "transforms": ["as_list"],
                        "required": True,
                    },
                    {
                        "key": "file_dep_graph",
                        "path": ["resources", "dependencies"],
                        "transforms": ["as_list"],
                        "required": True,
                    },
                ],
                "transforms": [],
                "required": True,
            },
        ],
    })


def test_schema_fingerprint_ignores_values_order_and_row_count_but_detects_shape() -> None:
    rows = _nested_rows(30)
    changed_values = copy.deepcopy(list(reversed(rows[:20])))
    for row in changed_values:
        row["job"]["instruction"] = "Different content, same JSON type."
    assert schema_fingerprint(rows) == schema_fingerprint(changed_values)

    drifted = copy.deepcopy(rows)
    drifted[0]["new_component"] = {"x": True}
    assert schema_fingerprint(rows) != schema_fingerprint(drifted)


def test_adapter_dsl_rejects_code_provenance_and_role_misuse() -> None:
    rows = _nested_rows()
    base = _nested_spec(rows).to_dict()

    malicious = copy.deepcopy(base)
    malicious["bindings"][1]["transforms"] = ["exec_python"]
    with pytest.raises(AdapterValidationError, match="unsupported transforms"):
        AdapterSpec.from_dict(malicious)

    provenance = copy.deepcopy(base)
    provenance["bindings"][1]["path"] = ["_mutation_provenance", "task"]
    with pytest.raises(AdapterValidationError, match="reserved"):
        AdapterSpec.from_dict(provenance)

    role_misuse = copy.deepcopy(base)
    role_misuse["bindings"][1]["path"] = ["label"]
    with pytest.raises(AdapterValidationError, match="may only populate"):
        AdapterSpec.from_dict(role_misuse)

    classification = {
        "schema_version": "benchcore-adapter-v1",
        "adapter_id": "classification_label_adapter",
        "version": 1,
        "family": "generic",
        "schema_fingerprint": "0" * 64,
        "description": "Legitimate label to gold mapping.",
        "bindings": [
            {"target": "task", "path": ["text"], "transforms": [], "required": True},
            {"target": "gold", "path": ["label"], "transforms": [], "required": True},
        ],
    }
    assert AdapterSpec.from_dict(classification).binding_for("gold") is not None


def test_object_and_template_interpreter_and_fail_closed_drift() -> None:
    rows = _nested_rows()
    spec = _nested_spec(rows)
    result = adapt_rows(rows, spec, strict_rows=True)
    assert result.complete_rate == 1.0
    assert result.rows[0]["item_id"] == "workspacebench-x-0"
    assert result.rows[0]["evaluator"]["rubrics"] == ["criterion 0"]
    assert result.rows[0]["context"]["data_manifest"][0]["filename"] == "input-0.txt"

    drifted = copy.deepcopy(rows)
    drifted[0]["schema_v2"] = True
    with pytest.raises(AdapterValidationError, match="fingerprint mismatch"):
        adapt_rows(drifted, spec)


def test_component_gap_analysis_separates_dsl_from_trusted_plugins() -> None:
    rows = _nested_rows()
    spec = _nested_spec(rows)
    analysis = analyze_component_gaps(
        build_schema_profile(rows),
        family="workspacebench",
        spec=spec,
    )
    by_name = {component.component: component for component in analysis.components}
    assert by_name["canonical_task"].status == "resolved"
    assert by_name["dependency_graph"].status == "unresolved"
    assert by_name["candidate_materializer"].status == "requires_trusted_plugin"


def test_structural_only_is_shadow_and_exact_reference_is_verified() -> None:
    rows = _nested_rows()
    spec = _nested_spec(rows)
    adapted = adapt_rows(rows, spec, strict_rows=True)

    shadow = evaluate_adapter(spec, rows)
    assert shadow.accepted is True
    assert shadow.activation_mode == "active_shadow"
    assert shadow.reference is None

    verified = evaluate_adapter(spec, rows, references=list(adapted.rows))
    assert verified.accepted is True
    assert verified.activation_mode == "active_verified"
    assert verified.reference is not None
    assert verified.reference.target_coverage == 1.0
    assert set(verified.reference.expected_targets) == spec.targets
    assert verified.reference.field_accuracy == 1.0
    assert verified.reference.row_accuracy == 1.0

    wrong_reference = [dict(row) for row in adapted.rows]
    wrong_reference[0] = {**wrong_reference[0], "task": "wrong"}
    rejected = evaluate_adapter(spec, rows, references=wrong_reference)
    assert rejected.accepted is False
    assert rejected.activation_mode == "quarantined"


def test_verified_reference_contract_rejects_omitted_or_unregistered_targets() -> None:
    rows = _nested_rows()
    spec = _nested_spec(rows)
    references = [dict(row) for row in adapt_rows(rows, spec, strict_rows=True).rows]

    for index, reference in enumerate(references):
        reference["rubrics"] = [f"independent rubric {index}"]
    omitted = evaluate_adapter(spec, rows, references=references)
    assert omitted.accepted is False
    assert omitted.reference is None
    assert any(
        "omits targets declared by the external reference" in reason
        for reason in omitted.reasons
    )

    unknown_references = [
        {**row, "private_oracle_note": "must never be silently ignored"}
        for row in adapt_rows(rows, spec, strict_rows=True).rows
    ]
    unknown = evaluate_adapter(spec, rows, references=unknown_references)
    assert unknown.accepted is False
    assert unknown.reference is None
    assert any("unregistered targets" in reason for reason in unknown.reasons)


def test_reference_contract_error_is_a_closed_quarantine_run() -> None:
    rows = _nested_rows()
    spec = _nested_spec(rows)
    references = list(adapt_rows(rows, spec, strict_rows=True).rows)[:-1]
    run = AdapterController(
        StaticAdapterSynthesizer([spec]),
        max_rounds=1,
    ).run(
        rows,
        build_schema_profile(rows),
        family="workspacebench",
        references=references,
    )

    assert run.status == "quarantined"
    assert run.stop_reason == "sealed_reference_gate_failed"
    assert run.reference_attempts == 1
    assert run.lineage_closed is True
    assert run.final_evaluation is not None
    assert any(
        "reference row count must equal source row count" in reason
        for reason in run.final_evaluation.reasons
    )


class _TwoRoundSynthesizer:
    def __init__(self, bad: AdapterSpec, good: AdapterSpec) -> None:
        self.bad = bad
        self.good = good
        self.calls = 0
        self.feedback: list[list[dict]] = []

    def propose(self, profile, *, family, feedback, max_candidates):
        del profile, family, max_candidates
        self.feedback.append(copy.deepcopy(feedback))
        self.calls += 1
        return [self.bad if self.calls == 1 else self.good]


def test_controller_iterates_on_aggregate_gate_feedback_and_seals_reference() -> None:
    rows = _nested_rows()
    good = _nested_spec(rows)
    bad_payload = good.to_dict()
    for binding in bad_payload["bindings"]:
        if binding["target"] == "task":
            binding["path"] = ["stats", "number"]
            binding["transforms"] = []
    bad = AdapterSpec.from_dict(bad_payload)
    synthesizer = _TwoRoundSynthesizer(bad, good)
    references = list(adapt_rows(rows, good, strict_rows=True).rows)
    run = AdapterController(synthesizer, max_rounds=3).run(
        rows,
        build_schema_profile(rows),
        family="workspacebench",
        references=references,
    )
    assert synthesizer.calls == 2
    assert synthesizer.feedback[0][0]["trusted_contract"] == {
        "family": "workspacebench",
        "required_targets": [
            "context", "evaluator", "item_id", "output_contract", "task",
        ],
    }
    assert synthesizer.feedback[1]
    assert (
        "gate_reasons" in synthesizer.feedback[1][-1]
        or "trusted_evaluation_error" in synthesizer.feedback[1][-1]
    )
    assert run.status == "active_verified"
    assert run.reference_attempts == 1
    assert run.lineage_closed is True


class _PlanClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.prompts: list[tuple[str, str]] = []

    def chat_json(self, system: str, user: str) -> dict:
        self.prompts.append((system, user))
        return copy.deepcopy(self.response)


def test_workspace_llm_selects_compact_path_ids_and_trusted_compiler_builds_spec() -> None:
    rows = _nested_rows()
    profile = build_schema_profile(rows)
    path_ids = {entry.path: index for index, entry in enumerate(profile.paths)}
    client = _PlanClient({
        "schema_version": WORKSPACE_PLAN_SCHEMA_VERSION,
        "plans": [{
            "slots": {
                "item_id": path_ids[("record", "opaque")],
                "task": path_ids[("job", "instruction")],
                "rubrics": path_ids[("assessment", "criteria")],
                "rubric_types": path_ids[("assessment", "kinds")],
                "output_files": path_ids[("delivery", "files")],
                "data_manifest": path_ids[("resources", "manifest")],
                "file_dep_graph": path_ids[("resources", "dependencies")],
            },
        }],
    })
    specs = LLMAdapterSynthesizer(client).propose(
        profile,
        family="workspacebench",
        feedback=[],
        max_candidates=1,
    )

    assert len(specs) == 1
    spec = specs[0]
    assert {
        "item_id", "task", "rubrics", "rubric_types", "output_files",
        "data_manifest", "file_dep_graph", "context", "evaluator",
        "output_contract",
    } <= spec.targets
    adapted = adapt_rows(rows, spec, strict_rows=True)
    assert adapted.rows[0]["item_id"] == "workspacebench-x-0"
    assert adapted.rows[0]["evaluator"]["rubrics"] == ["criterion 0"]
    assert evaluate_adapter(spec, rows).activation_mode == "active_shadow"
    assert '"plans"' in client.prompts[0][1]
    assert "Solve task number" not in client.prompts[0][1]
    assert "criterion 0" not in client.prompts[0][1]


def test_workspace_compact_plan_rejects_unknown_ids_and_partial_metadata() -> None:
    rows = _nested_rows()
    profile = build_schema_profile(rows)
    path_ids = {entry.path: index for index, entry in enumerate(profile.paths)}
    bad_id = _PlanClient({
        "schema_version": WORKSPACE_PLAN_SCHEMA_VERSION,
        "plans": [{"slots": {"task": 999_999}}],
    })
    with pytest.raises(AdapterValidationError, match="unknown path ID"):
        LLMAdapterSynthesizer(bad_id).propose(
            profile, family="workspacebench", feedback=[], max_candidates=1,
        )

    partial_metadata = _PlanClient({
        "schema_version": WORKSPACE_PLAN_SCHEMA_VERSION,
        "plans": [{
            "slots": {
                "task": path_ids[("job", "instruction")],
                "metadata.language": path_ids[("record", "opaque")],
            },
        }],
    })
    with pytest.raises(AdapterValidationError, match="select all canonical roles"):
        LLMAdapterSynthesizer(partial_metadata).propose(
            profile, family="workspacebench", feedback=[], max_candidates=1,
        )


def test_registry_revalidates_gate_bundle_and_rejects_tampering(tmp_path: Path) -> None:
    rows = _nested_rows()
    spec = _nested_spec(rows)
    references = list(adapt_rows(rows, spec, strict_rows=True).rows)
    run = AdapterController(StaticAdapterSynthesizer([spec])).run(
        rows,
        build_schema_profile(rows),
        family="workspacebench",
        references=references,
    )
    registry = AdapterRegistry(tmp_path / "registry")
    activated = registry.activate(run)
    loaded, receipt = registry.resolve(
        family="workspacebench",
        schema_fingerprint=spec.schema_fingerprint,
    )
    assert loaded.sha256 == spec.sha256
    assert receipt["activation_mode"] == "active_verified"

    gate = tmp_path / "registry" / activated["receipt"]["gate_bundle_path"]
    payload = json.loads(gate.read_text(encoding="utf-8"))
    payload["status"] = "tampered"
    gate.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AdapterValidationError, match="gate bundle digest"):
        registry.resolve(
            family="workspacebench",
            schema_fingerprint=spec.schema_fingerprint,
        )


def test_registry_shadow_requires_explicit_resolution_opt_in(tmp_path: Path) -> None:
    rows = _nested_rows()
    spec = _nested_spec(rows)
    run = AdapterController(StaticAdapterSynthesizer([spec])).run(
        rows,
        build_schema_profile(rows),
        family="workspacebench",
    )
    registry = AdapterRegistry(tmp_path / "registry")
    registry.activate(run)
    with pytest.raises(AdapterValidationError, match="shadow opt-in"):
        registry.resolve(
            family="workspacebench",
            schema_fingerprint=spec.schema_fingerprint,
        )
    loaded, _ = registry.resolve(
        family="workspacebench",
        schema_fingerprint=spec.schema_fingerprint,
        allow_shadow=True,
    )
    assert loaded.sha256 == spec.sha256


def test_auto_adapt_cli_deterministic_workspace_reference_gate(tmp_path: Path) -> None:
    rows = []
    references = []
    for index in range(30):
        output_files = json.dumps([f"result-{index}.txt"])
        rubric_types = json.dumps(["Outcome Evaluation"])
        manifest = json.dumps([{"filename": f"input-{index}.txt"}])
        graph = json.dumps([{
            "from": f"input-{index}.txt",
            "to": f"result-{index}.txt",
        }])
        capabilities = json.dumps(["Workspace Exploration"])
        row = {
            "absolute_id": index,
            "task": f"Create result {index}.",
            "output_files": output_files,
            "rubrics": [f"Result {index} is correct."],
            "rubric_types": rubric_types,
            "file_dep_graph": graph,
            "data_manifest": manifest,
            "tested_capabilities": capabilities,
            "input_files": [f"/safe/input-{index}.txt"],
        }
        rows.append(row)
        references.append({
            "item_id": f"workspacebench-{index}",
            "task": f"Create result {index}.",
            "rubrics": [f"Result {index} is correct."],
            "rubric_types": rubric_types,
            "output_files": output_files,
            "input_files": [f"/safe/input-{index}.txt"],
            "data_manifest": manifest,
            "file_dep_graph": graph,
            "tested_capabilities": capabilities,
            "context": {
                "data_manifest": manifest,
                "file_dep_graph": graph,
                "input_files": [f"/safe/input-{index}.txt"],
            },
            "evaluator": {
                "type": "workspacebench_rubric",
                "rubrics": [f"Result {index} is correct."],
                "rubric_types": ["Outcome Evaluation"],
            },
            "output_contract": {"required_files": [f"result-{index}.txt"]},
        })
    input_path = tmp_path / "unknown.jsonl"
    reference_path = tmp_path / "reference.jsonl"
    input_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    reference_path.write_text(
        "".join(json.dumps(row) + "\n" for row in references), encoding="utf-8"
    )
    run_path = tmp_path / "run.json"
    spec_path = tmp_path / "adapter.json"
    adapted_path = tmp_path / "adapted.jsonl"
    registry_path = tmp_path / "registry"
    exit_code = main([
        "auto-adapt",
        str(input_path),
        "--family", "workspacebench",
        "--reference", str(reference_path),
        "--registry-dir", str(registry_path),
        "--activate",
        "--spec-out", str(spec_path),
        "--adapted-out", str(adapted_path),
        "--out", str(run_path),
        "--strict",
    ])
    assert exit_code == 0
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    assert payload["status"] == "active_verified"
    assert payload["reference_attempts"] == 1
    assert payload["final_evaluation"]["reference"]["field_accuracy"] == 1.0
    assert payload["final_evaluation"]["reference"]["row_accuracy"] == 1.0
    assert payload["activation"]["receipt"]["activation_mode"] == "active_verified"
    assert len(adapted_path.read_text(encoding="utf-8").splitlines()) == 30
