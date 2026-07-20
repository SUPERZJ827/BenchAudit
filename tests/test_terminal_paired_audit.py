from pathlib import Path

from scripts.run_terminal_bench_paired_audit import (
    classification_metrics,
    hypergeometric_tail,
    run_experiment,
)


def write_task(root: Path, name: str, *, pinned: bool = False, marker: str = "") -> None:
    task = root / name
    (task / "solution").mkdir(parents=True)
    (task / "instruction.md").write_text("Complete the task.\n", encoding="utf-8")
    (task / "task.toml").write_text(
        "[environment]\ncpus = 2\nmemory_mb = 8192\n", encoding="utf-8"
    )
    command = "apt-get install curl=1.2.3\n" if pinned else "apt-get install curl\n"
    (task / "solution" / "solve.sh").write_text(command + marker, encoding="utf-8")


def test_classification_metrics_uses_proxy_negative_name():
    result = classification_metrics({"a", "b"}, {"a", "c"}, {"a", "b", "c", "d"})

    assert result["tp"] == 1
    assert result["fp_proxy"] == 1
    assert result["fn"] == 1
    assert result["f1"] == 0.5


def test_hypergeometric_tail_extremes():
    assert hypergeometric_tail(population=10, positives=2, draws=2, overlap=0) == 1.0
    assert 0 < hypergeometric_tail(population=10, positives=2, draws=2, overlap=2) < 1


def test_paired_experiment_audits_versions_independently(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    write_task(old, "changed", pinned=True)
    write_task(new, "changed", pinned=False)
    write_task(old, "stable", pinned=False)
    write_task(new, "stable", pinned=False)

    result = run_experiment(old, new, 0.70)

    assert result["dataset"]["changed_tasks"] == 1
    assert result["old_release"]["metrics"]["tp_tasks"] == ["changed"]
    assert result["paired_effect"]["cleared_changed_tasks"] == ["changed"]
