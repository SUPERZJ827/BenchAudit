import copy
import json
import re
from pathlib import Path

import pytest

from benchcore.loader import build_items, load_mapping
from benchcore.workspace_semantic_challenge import (
    CONTRACT_REQUESTED_VS_HIDDEN_COMPANION_FILE,
    INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL,
    INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME,
    TASK_EXPLICIT_VS_HIDDEN_TITLE,
    WORKSPACE_SEMANTIC_OPERATORS,
    audit_semantic_phase,
    build_workspace_semantic_challenge,
    model_signature,
    prompt_signature,
    rows_contain_semantic_provenance,
    score_workspace_semantic_challenge,
    select_workspace_source_rows,
    semantic_run_signature,
    workspace_snapshot_signature,
)
from benchcore.workspace_grounding import (
    build_workspace_evidence_bundle,
    resolve_objective_grounding_certificate,
)
from scripts.run_workspace_semantic_challenge import (
    materialize_attachment_snapshot,
    portable_attachment_manifest_signature,
    prepare_exact_cache_reuse,
    preflight_challenge_views,
)


def workspace_row(tmp_path: Path, item_id: str = "workspacebench-17") -> dict:
    source = tmp_path / f"0123456789abcdef_{item_id}_source.txt"
    source.write_text("independent facts\n", encoding="utf-8")
    generator = tmp_path / f"generate_{item_id}_report.py"
    generator.write_text("reference output", encoding="utf-8")
    logical_source = f"{item_id}_source.txt"
    outputs = ["report.md"]
    rubrics = ["Was report.md created?", "Does it summarize the source?"]
    rubric_types = ["Basic Evaluation", "Outcome Evaluation"]
    manifest = [
        {
            "filename": logical_source,
            "stored_relpath": f"data/{source.name}",
        },
        {
            "filename": generator.name,
            "stored_relpath": f"data/{generator.name}",
        },
    ]
    return {
        "item_id": item_id,
        "absolute_id": 17,
        "task": "Read the provided source and create report.md.",
        "output_files": json.dumps(outputs),
        "rubrics": json.dumps(rubrics),
        "rubric_types": json.dumps(rubric_types),
        "data_manifest": json.dumps(manifest),
        "output_contract": {
            "type": "workspace_files",
            "required_files": outputs,
        },
        "evaluator": {
            "type": "workspacebench_rubric",
            "rubrics": rubrics,
            "rubric_types": rubric_types,
        },
        "context": {
            "output_files": outputs,
            "data_manifest": manifest,
        },
        "input_files": [str(source), str(generator)],
    }


class PromptAwareClient:
    """Behavior-identical fake: labels come only from visible prompt evidence."""

    def __init__(self, phase: str, events: list[tuple[str, str, str]] | None = None):
        self.phase = phase
        self.events = events if events is not None else []
        self.prompts: list[tuple[str, str]] = []

    def chat_json(self, system: str, prompt: str) -> dict:
        self.prompts.append((system, prompt))
        self.events.append((self.phase, system, prompt))
        label, requirement_type, source, quote, rubric = self._classify(prompt)
        if "adversarial evidence verifier" in system:
            return {
                "label": label,
                "confidence": 0.93,
                "reason": "The exact visible evidence determines this requirement.",
                "decisive_evidence": {
                    "source": source,
                    "quote": quote,
                },
            }
        return {
            "label": label,
            "confidence": 0.95,
            "requirement_type": requirement_type,
            "atomic_requirement": rubric,
            "reason": "The exact target was compared with its visible evidence source.",
            "evidence": [{
                "source": source,
                "quote": quote,
                "relation": "supports" if label == "supported" else "contradicts",
            }],
            "missing_assumption": "" if label == "supported" else "exact target support",
        }

    @staticmethod
    def _between(value: str, start: str, end: str) -> str:
        assert start in value and end in value
        return value.split(start, 1)[1].split(end, 1)[0].strip()

    @classmethod
    def _classify(cls, prompt: str) -> tuple[str, str, str, str, str]:
        task = cls._between(prompt, "TASK:\n", "\n\nOUTPUT CONTRACT:")
        contract = cls._between(prompt, "OUTPUT CONTRACT:\n", "\n\nRUBRIC")
        if "\nRUBRIC INDEX 0:\n" in prompt:
            rubric = cls._between(
                prompt,
                "\nRUBRIC INDEX 0:\n",
                "\n\nALLOWED INPUT EVIDENCE:",
            )
        else:
            rubric = cls._between(
                prompt,
                "\nRUBRIC:\n",
                "\n\nSCANNER DECISION:",
            )
        evidence = cls._between(
            prompt,
            "ALLOWED INPUT EVIDENCE:\n",
            "\n\nTARGETED FULL-FILE SEARCH:",
        )
        inventory = evidence.split("\n\n", 1)[0].strip()

        title = re.search(r'exact title "([^"]+)"', rubric, flags=re.I)
        if title:
            target = title.group(1)
            supported = target in task
            requested = re.search(r'"(Orchid Review [^"]+)"', task)
            quote = target if supported else requested.group(1) if requested else ""
            return (
                "supported" if supported else "unsupported",
                "task",
                "task",
                quote,
                rubric,
            )

        companion = re.search(r"companion file `([^`]+)`", rubric, flags=re.I)
        if companion:
            target = companion.group(1)
            supported = target in contract
            requested = re.search(r"supporting_notes_[a-f0-9]+\.md", contract, flags=re.I)
            quote = target if supported else requested.group(0) if requested else ""
            return (
                "supported" if supported else "unsupported",
                "contract",
                "output_contract",
                quote,
                rubric,
            )

        count = re.search(
            r"exactly\s+(\d+)\s+allowed visible input source files",
            rubric,
            flags=re.I,
        )
        if count:
            desired = int(count.group(1))
            actual_match = re.search(r"^file_count=(\d+)$", inventory, flags=re.M)
            assert actual_match
            actual = int(actual_match.group(1))
            scope_count = re.search(
                r"^scope=complete_actor_view\nfile_count=\d+$",
                inventory,
                flags=re.M,
            )
            assert scope_count
            return (
                "supported" if desired == actual else "unsupported",
                "input_fact",
                "input_inventory",
                scope_count.group(0),
                rubric,
            )

        filename = re.search(r"identify `([^`]+)`", rubric, flags=re.I)
        if filename:
            target = filename.group(1)
            logical_lines = [
                line for line in inventory.splitlines()
                if line.startswith("- logical=")
            ]
            supported_line = next(
                (line for line in logical_lines if line.startswith(f"- logical={target} |")),
                None,
            )
            if supported_line is not None:
                quote = supported_line
                label = "supported"
            else:
                # A complete scope plus the complete contiguous inventory is
                # objective negative evidence for a non-existent logical name.
                quote = "\n".join(inventory.splitlines()[1:])
                label = "unsupported"
            return label, "input_fact", "input_inventory", quote, rubric

        raise AssertionError(f"unrecognized semantic challenge rubric: {rubric}")


class NoCallClient:
    def chat_json(self, system: str, prompt: str) -> dict:  # pragma: no cover
        raise AssertionError("a complete resumable phase must not call the model")


class FlakyThenSupportedClient:
    def __init__(self):
        self.calls = 0

    def chat_json(self, system: str, prompt: str) -> dict:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient transport failure")
        task_quote = prompt.split("TASK:\n", 1)[1].split(
            "\n\nOUTPUT CONTRACT:", 1,
        )[0].strip().split("\n\n")[-1]
        return {
            "label": "supported",
            "confidence": 0.9,
            "requirement_type": "task",
            "reason": "visible",
            "evidence": [{
                "source": "task",
                "quote": task_quote,
                "relation": "supports",
            }],
        }


class UntrustedParaphraseClient:
    """A deliberately wrong model whose free-form citation never validates."""

    def __init__(self):
        self.calls = 0

    def chat_json(self, system: str, prompt: str) -> dict:
        self.calls += 1
        return {
            "label": "supported",
            "confidence": 1.0,
            "requirement_type": "other",
            "atomic_requirement": "model-generated inversion",
            "reason": "This verdict and citation are deliberately untrusted.",
            "evidence": [{
                "source": "task",
                "quote": "invented paraphrase that is absent from the task",
                "relation": "supports",
            }],
            "missing_assumption": "",
        }


def decision(
    item_id: str,
    label: str,
    rubric: str = "synthetic requirement",
    *,
    operational: bool = False,
    inventory_eligible: bool = True,
) -> dict:
    scanner = {"label": label, "confidence": 0.9}
    if operational:
        scanner["operational_failure"] = True
    return {
        "item_id": item_id,
        "rubric_index": 0,
        "rubric": rubric,
        "label": label,
        "scanner": scanner,
        "verifier": None,
        "evidence_bundle_sha256": "bundle-sha",
        "artifact_manifest_sha256": "artifact-sha",
        "input_inventory_complete": inventory_eligible,
        "inventory_absence_is_confirmation_eligible": inventory_eligible,
        "citation_validation": {
            "all_claimed_valid": True,
            "inventory_absence_is_confirmation_eligible": inventory_eligible,
        },
    }


def test_builds_four_objective_pairs_with_sidecar_only_provenance(tmp_path: Path):
    source = workspace_row(tmp_path)
    untouched = copy.deepcopy(source)

    first = build_workspace_semantic_challenge(
        [source], seed=37, allowed_roots=[tmp_path],
    )
    second = build_workspace_semantic_challenge(
        [source], seed=37, allowed_roots=[tmp_path],
    )

    assert source == untouched
    assert first.clean_rows == second.clean_rows
    assert first.mutant_rows == second.mutant_rows
    assert first.manifest() == second.manifest()
    assert len(first.clean_rows) == len(first.mutant_rows) == 4
    assert len(first.provenance) == 4
    assert {row.operator for row in first.provenance} == set(WORKSPACE_SEMANTIC_OPERATORS)
    assert not first.skipped
    assert not rows_contain_semantic_provenance(first.clean_rows)
    assert not rows_contain_semantic_provenance(first.mutant_rows)

    all_rows = first.clean_rows + first.mutant_rows
    for row in all_rows:
        assert len(row["evaluator"]["rubrics"]) == 1
        assert len(json.loads(row["rubrics"])) == 1
        assert "Does it summarize the source?" not in json.dumps(row)
        assert source["item_id"] not in row["item_id"]
        assert "clean" not in row["item_id"]
        assert "mutant" not in row["item_id"]
        assert all(operator not in row["item_id"] for operator in WORKSPACE_SEMANTIC_OPERATORS)
        assert row["workspace_inventory_complete"] is True
        assert row["context"]["workspace_inventory_complete"] is True

    clean_by_id = {row["item_id"]: row for row in first.clean_rows}
    mutant_by_id = {row["item_id"]: row for row in first.mutant_rows}
    by_operator = {row.operator: row for row in first.provenance}

    title = by_operator[TASK_EXPLICIT_VS_HIDDEN_TITLE]
    assert "Orchid Review" in clean_by_id[title.clean_item_id]["task"]
    assert clean_by_id[title.clean_item_id]["task"] == mutant_by_id[title.mutant_item_id]["task"]
    assert "Orchid Review" in title.clean_requirement
    assert "Cobalt Digest" in title.mutant_requirement

    companion = by_operator[CONTRACT_REQUESTED_VS_HIDDEN_COMPANION_FILE]
    clean_outputs = clean_by_id[companion.clean_item_id]["output_contract"]["required_files"]
    mutant_outputs = mutant_by_id[companion.mutant_item_id]["output_contract"]["required_files"]
    assert clean_outputs == mutant_outputs
    assert any(name.startswith("supporting_notes_") for name in clean_outputs)
    assert "supporting_notes_" in companion.clean_requirement
    assert "review_appendix_" in companion.mutant_requirement

    # Apart from opaque item IDs, every pair has the same visible task and
    # contract; only the exact rubric target changes.
    for provenance in first.provenance:
        clean_row = clean_by_id[provenance.clean_item_id]
        mutant_row = mutant_by_id[provenance.mutant_item_id]
        assert clean_row["task"] == mutant_row["task"]
        assert clean_row["output_contract"] == mutant_row["output_contract"]
        clean_control = copy.deepcopy(clean_row)
        mutant_control = copy.deepcopy(mutant_row)
        clean_control["item_id"] = mutant_control["item_id"] = "opaque-control"
        clean_control["rubrics"] = mutant_control["rubrics"] = "[\"controlled\"]"
        clean_control["evaluator"]["rubrics"] = ["controlled"]
        mutant_control["evaluator"]["rubrics"] = ["controlled"]
        assert clean_control == mutant_control

    count = by_operator[INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL]
    assert "exactly 1 allowed visible input" in count.clean_requirement
    assert "exactly 2 allowed visible input" in count.mutant_requirement

    filename = by_operator[INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME]
    assert "workspacebench-17_source.txt" in filename.clean_requirement
    assert "source_register_" in filename.mutant_requirement
    assert filename.source_item_id == source["item_id"]


def test_stable_source_selection_is_order_independent_and_requires_visible_inputs(
    tmp_path: Path,
):
    rows = [workspace_row(tmp_path, f"workspacebench-{index}") for index in range(4)]
    first = select_workspace_source_rows(
        rows, sample_size=2, seed=41, allowed_roots=[tmp_path],
    )
    second = select_workspace_source_rows(
        list(reversed(rows)), sample_size=2, seed=41,
        allowed_roots=[tmp_path],
    )

    assert [row["item_id"] for row in first] == [row["item_id"] for row in second]

    missing = copy.deepcopy(rows[0])
    missing["item_id"] = "missing"
    missing["input_files"] = [str(tmp_path / "absent.txt")]
    with pytest.raises(ValueError, match="only 0 are eligible"):
        select_workspace_source_rows(
            [missing], sample_size=1, seed=41, allowed_roots=[tmp_path],
        )

    isolated_root = tmp_path / "isolated"
    isolated_root.mkdir()
    with pytest.raises(ValueError, match="only 0 are eligible"):
        select_workspace_source_rows(
            [rows[0]],
            sample_size=1,
            seed=41,
            allowed_roots=[isolated_root],
        )


def test_control_support_survives_production_task_and_contract_prefix_caps(
    tmp_path: Path,
):
    source = workspace_row(tmp_path)
    source["task"] = "original task payload " * 500
    long_outputs = [f"artifact_{index}_{'x' * 60}.md" for index in range(80)]
    source["output_contract"]["required_files"] = long_outputs
    challenge = build_workspace_semantic_challenge(
        [source], seed=41, allowed_roots=[tmp_path],
    )
    clean_by_id = {row["item_id"]: row for row in challenge.clean_rows}
    by_operator = {row.operator: row for row in challenge.provenance}

    title = by_operator[TASK_EXPLICIT_VS_HIDDEN_TITLE]
    assert "Orchid Review" in clean_by_id[title.clean_item_id]["task"][:4000]

    count = by_operator[INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL]
    assert "Also include an accurate count" in (
        clean_by_id[count.clean_item_id]["task"][:4000]
    )

    filename = by_operator[INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME]
    assert "Also identify the allowed visible input source files" in (
        clean_by_id[filename.clean_item_id]["task"][:4000]
    )

    companion = by_operator[CONTRACT_REQUESTED_VS_HIDDEN_COMPANION_FILE]
    companion_row = clean_by_id[companion.clean_item_id]
    visible_contract = json.dumps({
        "required_files": companion_row["output_contract"]["required_files"],
        "declared": companion_row["output_contract"],
    })[:2500]
    requested = re.search(r"`([^`]+)`", companion.clean_requirement)
    assert requested and requested.group(1) in visible_contract


def test_attachment_snapshot_is_contained_regular_and_resume_stable(tmp_path: Path):
    source = workspace_row(tmp_path)
    # Reproduce the Hugging Face layout: the declared, logically named file is
    # a relative symlink into a content-addressed blob directory.
    declared_source = Path(source["input_files"][0])
    payload = declared_source.read_bytes()
    blob = tmp_path / "blobs" / "content-addressed-source"
    blob.parent.mkdir()
    blob.write_bytes(payload)
    declared_source.unlink()
    declared_source.symlink_to(blob.relative_to(declared_source.parent))
    snapshot_root = tmp_path / "snapshot"

    first_rows, first_manifest = materialize_attachment_snapshot(
        [source],
        dataset_root=tmp_path,
        allowed_roots=(tmp_path,),
        snapshot_root=snapshot_root,
    )
    second_rows, second_manifest = materialize_attachment_snapshot(
        [source],
        dataset_root=tmp_path,
        allowed_roots=(tmp_path,),
        snapshot_root=snapshot_root,
    )

    assert first_rows == second_rows
    assert first_manifest == second_manifest
    portable_signature = portable_attachment_manifest_signature(first_manifest)
    diagnostics_variant = copy.deepcopy(first_manifest)
    diagnostics_variant["snapshot_root"] = "/different/machine/output"
    diagnostics_variant["source_allowed_roots"] = ["/different/cache"]
    diagnostics_variant["artifacts"][0]["resolved_source"] = "/different/blob"
    diagnostics_variant["artifacts"][0]["declared_path"] = "/different/source"
    diagnostics_variant["artifacts"][0]["materialization"] = "copy"
    assert portable_attachment_manifest_signature(diagnostics_variant) == (
        portable_signature
    )
    assert all(not Path(value).is_absolute() for value in first_rows[0]["input_files"])
    assert all((snapshot_root / value).is_file() for value in first_rows[0]["input_files"])
    frozen_source = snapshot_root / first_rows[0]["input_files"][0]
    assert not frozen_source.is_symlink()
    assert frozen_source.read_bytes() == payload
    challenge = build_workspace_semantic_challenge(
        first_rows,
        root=snapshot_root,
        allowed_roots=[snapshot_root],
        seed=42,
    )
    assert len(challenge.provenance) == 4
    assert not challenge.skipped
    preflight = preflight_challenge_views(
        challenge,
        root=snapshot_root,
        allowed_roots=(snapshot_root,),
        workers=2,
        evidence_chars=16_000,
    )
    assert preflight["source_tasks"] == 1
    assert preflight["evidence_views"] == 2  # base and companion-file contracts
    assert preflight["indexed_files"] == 1
    assert preflight["input_inventory_complete_tasks"] == 1
    assert preflight["inventory_confirmation_eligible_tasks"] == 1
    assert preflight["synthetic_gold_mismatches"] == 0


def test_exact_response_cache_reuse_is_staged_with_explicit_provenance(
    tmp_path: Path,
):
    source_dir = tmp_path / "invalid-source-run"
    destination = tmp_path / "fresh-run"
    source_dir.mkdir()
    destination.mkdir()
    for phase in ("clean", "mutant"):
        cache_rows = [
            {"key": f"{phase}-key-{index}", "response": {"label": "supported"}}
            for index in range(2)
        ]
        (source_dir / f"{phase}_llm_cache.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in cache_rows),
            encoding="utf-8",
        )
        (source_dir / f"{phase}_phase_summary.json").write_text(
            json.dumps({"client": {"api_successes": 2}}), encoding="utf-8",
        )
    (source_dir / "run_manifest.json").write_text(
        json.dumps({"run_signature": "invalid-old-run"}), encoding="utf-8",
    )
    (source_dir / "source_hash_end_check.json").write_text(
        json.dumps({"passed": False}), encoding="utf-8",
    )

    provenance = prepare_exact_cache_reuse(source_dir, destination)

    assert provenance["source_status"] == "invalid_source_drift_responses_only"
    assert provenance["source_run_signature"] == "invalid-old-run"
    assert provenance["source_end_check"] == {"passed": False}
    assert provenance["staged_caches"]["clean"]["entries"] == 2
    assert provenance["staged_caches"]["mutant"]["entries"] == 2
    assert (destination / "clean_llm_cache.jsonl").is_file()
    assert json.loads((destination / "cache_provenance.json").read_text()) == (
        provenance
    )


def test_phase_runner_is_single_rubric_phase_separated_and_scores_perfectly(
    tmp_path: Path,
):
    challenge = build_workspace_semantic_challenge(
        [workspace_row(tmp_path)], seed=43, allowed_roots=[tmp_path],
    )
    events: list[tuple[str, str, str]] = []

    clean = audit_semantic_phase(
        challenge,
        "clean",
        PromptAwareClient("clean", events),
        tmp_path / "clean_decisions.jsonl",
        run_signature="fixed-run",
        root=tmp_path,
        allowed_roots=[tmp_path],
        workers=4,
    )
    mutant = audit_semantic_phase(
        challenge,
        "mutant",
        PromptAwareClient("mutant", events),
        tmp_path / "mutant_decisions.jsonl",
        run_signature="fixed-run",
        root=tmp_path,
        allowed_roots=[tmp_path],
        workers=4,
    )

    assert clean["complete"] and mutant["complete"]
    assert clean["new_attempts"] == mutant["new_attempts"] == 4
    assert [event[0] for event in events[:4]] == ["clean"] * 4
    assert all(event[0] == "mutant" for event in events[4:])
    # Every row still gets one isolated scanner call.  A machine-grounded
    # objective certificate makes an additional semantic verifier redundant.
    assert len(events) == 8
    assert not any("adversarial evidence verifier" in event[1] for event in events)
    for _, system, prompt in events:
        if "adversarial evidence verifier" in system:
            assert prompt.count("\nRUBRIC:\n") == 1
        else:
            assert prompt.count("RUBRIC INDEX 0:") == 1
        assert "RUBRICS (JSON" not in prompt
        assert all(row.pair_id not in prompt for row in challenge.provenance)
        assert all(row.pair_id[:12] not in prompt for row in challenge.provenance)
        assert all(operator not in prompt for operator in WORKSPACE_SEMANTIC_OPERATORS)

    score = score_workspace_semantic_challenge(
        challenge.provenance,
        clean["decisions"],
        mutant["decisions"],
    )
    assert score["pairs"] == 4
    assert score["mutant_unsupported_hits"] == 4
    assert score["mutant_unsupported_recall"] == 1.0
    assert score["clean_nonunsupported"] == 4
    assert score["paired_discriminated"] == 4
    assert score["strict_paired_discriminated"] == 4
    assert score["clean_false_alarms"] == 0
    assert score["uncertain_decisions"] == 0
    assert score["operational_failure_decisions"] == 0
    assert score["extra_decision_count"] == 0
    assert score["duplicate_decision_count"] == 0
    assert score["source_tasks"] == 1
    assert score["source_complete_paired"] == 1
    assert score["source_cluster_bootstrap95"]["paired_discrimination"] == [1.0, 1.0]
    assert all(
        row["citation_validation"]["valid_support_count"] >= 1
        for row in clean["decisions"]
    )
    assert all(
        row["citation_validation"]["all_claimed_valid"]
        for row in mutant["decisions"]
    )
    assert {
        row["evidence"][0]["source"] for row in clean["decisions"]
    } == {"task", "output_contract", "input_inventory"}
    assert sum(
        row["evidence"][0]["source"] == "input_inventory"
        for row in clean["decisions"]
    ) == 2
    assert all(row["actor_view_complete"] for row in clean["decisions"])
    assert all(row["actor_view_complete"] for row in mutant["decisions"])
    assert all(row["input_inventory_complete"] for row in clean["decisions"])
    assert all(
        row["inventory_absence_is_confirmation_eligible"]
        for row in mutant["decisions"]
    )
    # The phase tag is diagnostics-only: replaying a clean prompt through a
    # differently named fake produces the same behavior-derived label.
    replay = PromptAwareClient("arbitrary").chat_json(
        events[0][1], events[0][2],
    )
    assert replay["label"] == "supported"

    mismatched_mutants = copy.deepcopy(mutant["decisions"])
    mismatched_mutants[0]["evidence_bundle_sha256"] = "stale-evidence-view"
    mismatch_score = score_workspace_semantic_challenge(
        challenge.provenance,
        clean["decisions"],
        mismatched_mutants,
    )
    assert mismatch_score["paired_discriminated"] == 3
    assert mismatch_score["integrity_failure_pairs"] == 1
    assert all(
        row["paired_discrimination"] == 1.0
        for row in score["per_operator"].values()
    )


def test_objective_certificates_override_wrong_model_and_invalid_self_reported_quotes(
    tmp_path: Path,
):
    challenge = build_workspace_semantic_challenge(
        [workspace_row(tmp_path)], seed=45, allowed_roots=[tmp_path],
    )
    client = UntrustedParaphraseClient()

    clean = audit_semantic_phase(
        challenge,
        "clean",
        client,
        tmp_path / "cert_clean.jsonl",
        run_signature="objective-certificates",
        root=tmp_path,
        allowed_roots=[tmp_path],
        workers=2,
    )
    mutant = audit_semantic_phase(
        challenge,
        "mutant",
        client,
        tmp_path / "cert_mutant.jsonl",
        run_signature="objective-certificates",
        root=tmp_path,
        allowed_roots=[tmp_path],
        workers=2,
    )

    assert client.calls == 8  # scanner only; model never proposes unsupported
    assert {row["label"] for row in clean["decisions"]} == {"supported"}
    assert {row["label"] for row in mutant["decisions"]} == {"unsupported"}
    for row in clean["decisions"] + mutant["decisions"]:
        validation = row["citation_validation"]
        assert not validation["all_claimed_valid"]
        assert validation["gate_reason"] == "objective_certificate"
        certificate = validation["objective_certificate"]
        assert certificate["applicable"] and certificate["eligible"]
        assert certificate["label"] == row["label"]
        assert len(certificate["source_sha256"]) == 64
        assert certificate["target"]
        serialized_certificate = json.dumps(certificate, ensure_ascii=False)
        assert "pair_id" not in serialized_certificate
        assert "source_item_id" not in serialized_certificate
        assert "operator" not in serialized_certificate
        assert "expected_label" not in serialized_certificate
        assert "_workspace_semantic_challenge" not in serialized_certificate

    score = score_workspace_semantic_challenge(
        challenge.provenance,
        clean["decisions"],
        mutant["decisions"],
    )
    assert score["mutant_unsupported_hits"] == 4
    assert score["strict_paired_discriminated"] == 4
    assert score["objective_certified_pairs"] == 4
    assert score["objective_certified_pair_rate"] == 1.0
    # The deliberately wrong scanner says "supported" for every row.  The
    # report must therefore keep raw, citation-grounded, and objectively
    # certified performance visibly separate.
    assert score["raw_mutant_unsupported_hits"] == 0
    assert score["raw_paired_discriminated"] == 0
    assert score["grounded_mutant_unsupported_hits"] == 0
    assert score["grounded_paired_discriminated"] == 0
    assert score["grounded_uncertain_decisions"] == 8


def test_objective_certificate_grammar_and_inventory_absence_fail_closed(
    tmp_path: Path,
):
    challenge = build_workspace_semantic_challenge(
        [workspace_row(tmp_path)],
        operators=[INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME],
        allowed_roots=[tmp_path],
        seed=46,
    )
    mutant_row = copy.deepcopy(challenge.mutant_rows[0])
    item = build_items([mutant_row], load_mapping(None, [mutant_row]))[0]
    rubric = mutant_row["evaluator"]["rubrics"][0]
    bundle = build_workspace_evidence_bundle(item, allowed_roots=[tmp_path])

    compound = resolve_objective_grounding_certificate(
        item,
        bundle,
        rubric + " Also require an unrelated visual style.",
    )
    assert not compound["applicable"]
    assert not compound["eligible"]
    assert compound["label"] is None

    mutant_row["workspace_inventory_complete"] = False
    mutant_row["context"]["workspace_inventory_complete"] = False
    incomplete_item = build_items(
        [mutant_row], load_mapping(None, [mutant_row]),
    )[0]
    incomplete_bundle = build_workspace_evidence_bundle(
        incomplete_item, allowed_roots=[tmp_path],
    )
    unresolved = resolve_objective_grounding_certificate(
        incomplete_item,
        incomplete_bundle,
        rubric,
    )
    assert unresolved["applicable"]
    assert not unresolved["eligible"]
    assert unresolved["label"] is None
    assert not incomplete_bundle.inventory_absence_is_confirmation_eligible


def test_phase_is_resumable_and_atomic_retry_does_not_create_duplicate_decision(
    tmp_path: Path,
):
    challenge = build_workspace_semantic_challenge(
        [workspace_row(tmp_path)],
        operators=[TASK_EXPLICIT_VS_HIDDEN_TITLE],
        allowed_roots=[tmp_path],
        seed=47,
    )
    path = tmp_path / "clean.jsonl"
    flaky = FlakyThenSupportedClient()

    first = audit_semantic_phase(
        challenge,
        "clean",
        flaky,
        path,
        run_signature="resume-run",
        root=tmp_path,
        allowed_roots=[tmp_path],
        workers=1,
        operational_passes=2,
    )

    assert flaky.calls == 2
    assert first["complete"]
    assert first["new_attempts"] == 2
    assert first["retried_attempts"] == 1
    assert len(first["decisions"]) == 1
    assert first["decisions"][0]["label"] == "supported"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    resumed = audit_semantic_phase(
        challenge,
        "clean",
        NoCallClient(),
        path,
        run_signature="resume-run",
        root=tmp_path,
        allowed_roots=[tmp_path],
        workers=1,
    )
    assert resumed["complete"]
    assert resumed["new_attempts"] == 0
    assert resumed["resumed_valid_items"] == 1

    part = next(path.with_name(path.name + ".parts").glob("*.json"))
    stale = json.loads(part.read_text(encoding="utf-8"))
    stale["evidence_bundle_sha256"] = "old-extractor-view"
    part.write_text(json.dumps(stale), encoding="utf-8")
    refreshed = audit_semantic_phase(
        challenge,
        "clean",
        PromptAwareClient("clean"),
        path,
        run_signature="resume-run",
        root=tmp_path,
        allowed_roots=[tmp_path],
        workers=1,
    )
    assert refreshed["complete"]
    assert refreshed["stale_decision_items_seen"] == 1
    assert refreshed["new_attempts"] == 1


def test_scoring_exposes_uncertainty_operational_failures_extras_and_duplicates(
    tmp_path: Path,
):
    challenge = build_workspace_semantic_challenge(
        [workspace_row(tmp_path)], seed=53, allowed_roots=[tmp_path],
    )
    pairs = challenge.provenance
    clean = [
        decision(pairs[0].clean_item_id, "supported", pairs[0].clean_requirement),
        decision(pairs[0].clean_item_id, "supported", pairs[0].clean_requirement),
        decision(pairs[1].clean_item_id, "uncertain", pairs[1].clean_requirement),
        decision(
            pairs[2].clean_item_id,
            "uncertain",
            pairs[2].clean_requirement,
            operational=True,
        ),
        decision(pairs[3].clean_item_id, "unsupported", pairs[3].clean_requirement),
        decision("unexpected-clean-id", "unsupported"),
    ]
    mutant = [
        decision(pair.mutant_item_id, "unsupported", pair.mutant_requirement)
        for pair in pairs
    ] + [decision("unexpected-mutant-id", "supported")]

    score = score_workspace_semantic_challenge(pairs, clean, mutant)

    assert score["pairs"] == 4
    assert score["mutant_unsupported_hits"] == 4
    assert score["clean_evaluable"] == 2  # uncertain and false-positive clean rows
    assert score["clean_nonunsupported"] == 1
    assert score["clean_false_alarms"] == 1
    assert score["clean_false_alarm_rate"] == 0.5
    assert score["paired_discriminated"] == 1
    assert score["strict_paired_discriminated"] == 0
    assert score["uncertain_decisions"] == 1
    assert score["operational_failure_decisions"] == 1
    assert score["integrity_failure_pairs"] == 1
    assert score["extra_decision_count"] == 2
    assert score["duplicate_decision_count"] == 1


def test_inventory_mutant_hits_fail_closed_without_inventory_absence_eligibility(
    tmp_path: Path,
):
    challenge = build_workspace_semantic_challenge(
        [workspace_row(tmp_path)], seed=57, allowed_roots=[tmp_path],
    )
    clean = [
        decision(pair.clean_item_id, "supported", pair.clean_requirement)
        for pair in challenge.provenance
    ]
    mutant = [
        decision(
            pair.mutant_item_id,
            "unsupported",
            pair.mutant_requirement,
            inventory_eligible=pair.operator not in {
                INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL,
                INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME,
            },
        )
        for pair in challenge.provenance
    ]

    score = score_workspace_semantic_challenge(
        challenge.provenance,
        clean,
        mutant,
    )

    assert score["mutant_unsupported_hits"] == 2
    assert score["paired_discriminated"] == 2
    assert score["strict_paired_discriminated"] == 2
    assert score["inventory_absence_required_pairs"] == 2
    assert score["inventory_confirmation_eligible_pairs"] == 0
    assert score["inventory_confirmation_eligibility_rate"] == 0.0
    by_operator = {row["operator"]: row for row in score["details"]}
    assert by_operator[TASK_EXPLICIT_VS_HIDDEN_TITLE]["mutant_unsupported_hit"]
    assert by_operator[CONTRACT_REQUESTED_VS_HIDDEN_COMPANION_FILE][
        "mutant_unsupported_hit"
    ]
    for operator in {
        INPUT_FILE_COUNT_CORRECT_VS_WRONG_LITERAL,
        INPUT_GROUNDED_VISIBLE_SOURCE_NAME_VS_NONEXISTENT_NAME,
    }:
        assert by_operator[operator]["inventory_absence_required"]
        assert not by_operator[operator][
            "inventory_absence_is_confirmation_eligible"
        ]
        assert not by_operator[operator]["mutant_unsupported_hit"]


def test_signatures_pin_prompts_model_snapshot_and_challenge(tmp_path: Path):
    row = workspace_row(tmp_path)
    challenge = build_workspace_semantic_challenge(
        [row], seed=59, allowed_roots=[tmp_path],
    )
    config = {
        "model": "fake-model",
        "base_url": "https://example.invalid/v1/",
        "temperature": 0.0,
        "max_tokens": 1200,
        "timeout": 30,
        "max_retries": 2,
    }

    prompt_sha = prompt_signature()
    model_sha = model_signature(config)
    snapshot_before = workspace_snapshot_signature([row], allowed_roots=[tmp_path])
    run_sha = semantic_run_signature(
        workspace_snapshot_sha256=snapshot_before,
        challenge_manifest=challenge.manifest(),
        model_sha256=model_sha,
        prompt_sha256=prompt_sha,
    )

    assert len(prompt_sha) == len(model_sha) == len(snapshot_before) == len(run_sha) == 64
    assert model_signature(config) == model_sha
    assert model_signature({**config, "model": "different-model"}) != model_sha
    assert semantic_run_signature(
        workspace_snapshot_sha256=snapshot_before,
        challenge_manifest=challenge.manifest(),
        model_sha256=model_sha,
        prompt_sha256=prompt_sha,
    ) == run_sha

    Path(row["input_files"][0]).write_text("changed bytes", encoding="utf-8")
    assert workspace_snapshot_signature([row], allowed_roots=[tmp_path]) != snapshot_before

    missing = score_workspace_semantic_challenge(challenge.provenance, [], [])
    assert missing["clean_evaluable"] == 0
    assert missing["clean_false_alarm_wilson95"] == [None, None]
