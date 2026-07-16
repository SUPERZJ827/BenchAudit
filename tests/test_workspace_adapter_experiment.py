import copy
import json
from pathlib import Path

import pytest

from benchcore.loader import load_rows
from scripts.build_or_run_workspace_adapter_experiment import (
    AdapterSpec,
    VARIANTS,
    adapt_row,
    assert_no_envelope_mapping_leak,
    build_experiment_artifacts,
    canonical_json,
    evaluate_manifest,
    evaluate_variant,
    load_adapter_spec,
    load_variant_bundle,
)


def workspace_row(input_path: Path, *, item_id: str = "workspacebench-test-1") -> dict:
    outputs = ["report.md"]
    rubrics = ["The final report.md contains the requested summary."]
    rubric_types = ["Basic Evaluation"]
    manifest = [{
        "filename": "source.txt",
        "stored_relpath": f"data/{input_path.name}",
    }]
    graph = [{"from": "source.txt", "to": "report.md"}]
    return {
        "absolute_id": 1,
        "context": {
            "data_manifest": manifest,
            "file_dep_graph": graph,
            "output_files": outputs,
        },
        "data_manifest": json.dumps(manifest),
        "evaluator": {
            "type": "workspacebench_rubric",
            "rubrics": rubrics,
            "rubric_types": rubric_types,
        },
        "file_dep_graph": json.dumps(graph),
        "input_files": [str(input_path)],
        "item_id": item_id,
        "language": "en",
        "metadata": {"suite": "unit-test"},
        "output_contract": {
            "type": "workspace_files",
            "required_files": outputs,
        },
        "output_files": json.dumps(outputs),
        "persona": "analyst",
        "rubric_types": json.dumps(rubric_types),
        "rubrics": json.dumps(rubrics),
        "task": "Read source.txt and write report.md.",
        "task_diff": "synthetic test task",
        "tested_capabilities": json.dumps(["file_read", "document_write"]),
    }


def _bundle_paths(out_dir: Path, variant: str) -> tuple[Path, Path, Path]:
    root = out_dir / variant
    return (
        root / "challenge.jsonl",
        root / "reference_sidecar.jsonl",
        root / "adapter_spec.json",
    )


def test_three_opaque_schemas_are_separated_reversible_and_invariant(tmp_path: Path):
    attachment = tmp_path / "0123456789abcdef_source.txt"
    attachment.write_text("grounded facts", encoding="utf-8")
    rows = [
        workspace_row(attachment, item_id="workspacebench-test-1"),
        {
            **workspace_row(attachment, item_id="workspacebench-test-2"),
            "absolute_id": 2,
        },
    ]
    out_dir = tmp_path / "experiment"

    manifest = build_experiment_artifacts(rows, out_dir, seed=41)

    assert manifest["source_rows"] == 2
    assert manifest["source_hash_end_check"]["passed"] is True
    assert [entry["variant"] for entry in manifest["variants"]] == list(VARIANTS)
    assert all(entry["mapping_leak_check_passed"] for entry in manifest["variants"])

    for variant in VARIANTS:
        challenge_path, sidecar_path, spec_path = _bundle_paths(out_dir, variant)
        challenge_rows, references, spec = load_variant_bundle(
            challenge_path, sidecar_path, spec_path,
        )
        assert references == rows
        for source, challenge in zip(rows, challenge_rows):
            assert_no_envelope_mapping_leak(challenge, spec)
            adapted = adapt_row(challenge, spec)
            assert adapted.errors == {}
            assert adapted.abstentions == {}
            assert adapted.values == source
            encoded_id = challenge
            for component in spec.field_paths["item_id"].split("."):
                encoded_id = encoded_id[component]
            assert encoded_id.startswith("oid1_")
            assert encoded_id != source["item_id"]
        challenge_text = challenge_path.read_text(encoding="utf-8")
        assert '"canonical_reference"' not in challenge_text
        assert '"field_paths"' not in challenge_text
        assert '"adapter_spec"' not in challenge_text

    result = evaluate_manifest(
        out_dir, allowed_roots=[tmp_path], workers=2,
    )
    aggregate = result["aggregate"]
    assert aggregate["variant_count"] == 3
    assert aggregate["row_equivalence"]["successes"] == 6
    assert aggregate["row_equivalence"]["rate"] == 1.0
    assert aggregate["core_field_equivalence"]["rate"] == 1.0
    assert aggregate["workspace_extension_field_equivalence"]["rate"] == 1.0
    assert aggregate["workspace_finding_signature_invariance"]["rate"] == 1.0
    assert aggregate[
        "workspace_positive_control_finding_signature_invariance"
    ]["rate"] == 1.0
    assert aggregate["positive_control_baseline_finding_count"] == 6
    assert aggregate["positive_control_adapted_finding_count"] == 6
    assert aggregate["positive_control_rows_without_finding"] == 0
    assert aggregate["scorer_abstention_control_detection"]["rate"] == 1.0
    assert aggregate["scorer_wrong_mapping_control_detection"]["rate"] == 1.0
    assert aggregate["source_cluster_all_variants_row_equivalence"]["total"] == 2
    assert aggregate["source_cluster_all_variants_row_equivalence"]["rate"] == 1.0
    assert aggregate["rows_with_abstention"] == 0
    assert aggregate["rows_with_mapping_error"] == 0
    assert aggregate["rows_with_adapter_error"] == 0
    assert aggregate["checker_errors"] == 0


def test_scorer_distinguishes_abstention_from_wrong_mapping(tmp_path: Path):
    attachment = tmp_path / "0123456789abcdef_source.txt"
    attachment.write_text("facts", encoding="utf-8")
    source = workspace_row(attachment)
    out_dir = tmp_path / "experiment"
    build_experiment_artifacts(
        [source], out_dir, seed=43, variants=("opaque_lattice",),
    )
    challenge_path, sidecar_path, spec_path = _bundle_paths(
        out_dir, "opaque_lattice",
    )
    challenge, references, correct = load_variant_bundle(
        challenge_path, sidecar_path, spec_path,
    )

    missing_data = correct.to_dict()
    missing_data["field_paths"].pop("task")
    missing = AdapterSpec.from_dict(missing_data)
    abstain_result = evaluate_variant(
        challenge, references, missing, allowed_roots=[tmp_path], workers=1,
    )

    assert abstain_result["rows_with_abstention"] == 1
    assert abstain_result["rows_with_mapping_error"] == 0
    assert abstain_result["core_fields"]["fields"]["task"]["abstained"] == 1
    assert abstain_result["row_equivalence"]["rate"] == 0.0

    wrong_data = correct.to_dict()
    wrong_data["field_paths"]["task"] = correct.field_paths["persona"]
    wrong = AdapterSpec.from_dict(wrong_data)
    wrong_result = evaluate_variant(
        challenge, references, wrong, allowed_roots=[tmp_path], workers=1,
    )

    assert wrong_result["duplicate_declared_paths"] == 1
    assert wrong_result["rows_with_abstention"] == 0
    assert wrong_result["rows_with_mapping_error"] == 1
    assert wrong_result["core_fields"]["fields"]["task"]["mapping_error"] == 1
    assert wrong_result["row_equivalence"]["rate"] == 0.0
    # The Workspace artifact checker does not consume task/persona.  This is a
    # useful guard against treating downstream invariance as row equivalence.
    assert wrong_result["workspace_finding_signature_invariance"]["rate"] == 1.0
    assert wrong_result["false_invariance_on_non_equivalent_rows"] == 1


def test_tampered_challenge_cannot_be_joined_to_reference_sidecar(tmp_path: Path):
    attachment = tmp_path / "0123456789abcdef_source.txt"
    attachment.write_text("facts", encoding="utf-8")
    out_dir = tmp_path / "experiment"
    build_experiment_artifacts(
        [workspace_row(attachment)],
        out_dir,
        seed=47,
        variants=("opaque_capsule",),
    )
    challenge_path, sidecar_path, spec_path = _bundle_paths(
        out_dir, "opaque_capsule",
    )
    rows = load_rows(challenge_path)
    spec = load_adapter_spec(spec_path)
    tampered = copy.deepcopy(rows[0])
    first_component = spec.field_paths["task"].split(".")[0]
    tampered[first_component] = {"x0000000000": "tampered"}
    challenge_path.write_text(canonical_json(tampered) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match its sidecar digest"):
        load_variant_bundle(challenge_path, sidecar_path, spec_path)


def test_adapter_spec_rejects_invalid_codec_material():
    with pytest.raises(ValueError, match="key_b64"):
        AdapterSpec.from_dict({
            "schema_version": "workspace-adapter-spec-v1",
            "variant": "candidate",
            "field_paths": {"item_id": "x0000000000"},
            "value_codecs": {
                "item_id": {"kind": "xor_utf8_v1", "key_b64": "%%%"},
            },
        })
