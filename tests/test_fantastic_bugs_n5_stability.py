from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preflight = load_script("preflight_fantastic_bugs_n5_replication.py")
score = load_script("score_fantastic_bugs_n5_stability.py")


def test_frozen_source_config_methods_and_old_runs_still_match() -> None:
    frozen = preflight.validate_frozen_inputs()
    assert frozen["implementation"]["sha256"] == preflight.EXPECTED_HASHES["implementation"]
    assert frozen["config"]["model"] == "deepseek-v4-flash"
    assert frozen["config"]["temperature"] == 0.0
    assert frozen["config"]["n_votes"] == 1
    assert len(preflight.EXPECTED_METHODS) == 20


def test_run_commands_use_three_distinct_fresh_caches_and_fixed_workers() -> None:
    commands = {run: preflight.command_for_run(run) for run in (3, 4, 5)}
    rendered = {run: " ".join(command) for run, command in commands.items()}
    assert len(set(rendered.values())) == 3
    for run, command in commands.items():
        assert command[command.index("--llm-cache") + 1].endswith(
            f"complete_run{run}/cache.jsonl"
        )
        assert command[command.index("--workers") + 1] == "8"
        assert command[command.index("--llm-auditors") + 1] == "gold,question,quantity,event"
        assert "--allow-remote-data-egress" in command
        assert "--no-benchmark-profile" in command


def test_preflight_does_not_read_truth_contents(monkeypatch: pytest.MonkeyPatch) -> None:
    original = Path.read_text
    truth_path = preflight.OLD_ROOT / "materialized/sealed_truth.jsonl"

    def guarded_read_text(path: Path, *args, **kwargs):
        if path.resolve() == truth_path.resolve():
            raise AssertionError("preflight must not read sealed truth")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    preflight.validate_frozen_inputs()


def test_rank_correlations_handle_ties_without_item_id_ordering() -> None:
    left = [0.0, 0.0, 1.0, 2.0]
    same = [0.0, 0.0, 1.0, 2.0]
    reversed_values = [2.0, 2.0, 1.0, 0.0]
    assert score.spearman_tie_aware(left, same) == pytest.approx(1.0)
    assert score.kendall_tau_b(left, same) == pytest.approx(1.0)
    assert score.spearman_tie_aware(left, reversed_values) == pytest.approx(-1.0)
    assert score.kendall_tau_b(left, reversed_values) == pytest.approx(-1.0)


def test_prospective_decision_uses_only_runs_3_to_5_and_frozen_three_item_range() -> None:
    assert score.prospective_decision(
        [{"top50_tp": 14}, {"top50_tp": 15}, {"top50_tp": 16}]
    )["status"] == "NO_BROAD_STABILITY_CLAIM_FROM_THIS_PILOT"
    assert score.prospective_decision(
        [{"top50_tp": 12}, {"top50_tp": 15}, {"top50_tp": 14}]
    )["status"] == "REPLICATION_SUPPORTS_MATERIAL_TOP50_VARIABILITY"


def test_existing_runs_reproduce_published_p_at_50_and_pairwise_jaccards() -> None:
    truth_path = preflight.OLD_ROOT / "materialized/sealed_truth.jsonl"
    truth_rows = [
        json.loads(line)
        for line in truth_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    all_ids = sorted(str(row["id"]) for row in truth_rows)
    truth = {str(row["id"]) for row in truth_rows if row["platinum_label"] == "invalid"}
    reports = [
        json.loads(
            (preflight.OLD_ROOT / f"complete_run{run}/report.json").read_text(
                encoding="utf-8"
            )
        )
        for run in (1, 2)
    ]
    summaries = [
        score.summarize_run(report, all_ids, truth, run)
        for run, report in zip((1, 2), reports)
    ]
    assert [row["top50_tp"] for row in summaries] == [16, 12]
    assert [row["precision_at_50"] for row in summaries] == [pytest.approx(0.32), pytest.approx(0.24)]
    maps = [score.semantic_map(report) for report in reports]
    assert score.jaccard(set(maps[0]), set(maps[1])) == pytest.approx(0.9448924731)
    assert score.jaccard(
        score.semantic_finding_keys(maps[0]), score.semantic_finding_keys(maps[1])
    ) == pytest.approx(0.7841079460)


def test_wilson_interval_is_conditional_and_contains_observed_fraction() -> None:
    lower, upper = score.wilson_interval(16, 50)
    assert lower < 0.32 < upper
    assert lower == pytest.approx(0.2076, abs=0.001)
    assert upper == pytest.approx(0.4581, abs=0.001)
