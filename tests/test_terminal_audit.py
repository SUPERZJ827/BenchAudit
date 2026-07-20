from pathlib import Path

from benchcore.terminal_audit import audit_terminal_task, parse_task_resources


def make_task(tmp_path: Path, *, instruction: str = "Do the task.") -> Path:
    task = tmp_path / "sample"
    (task / "solution").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "environment").mkdir()
    (task / "instruction.md").write_text(instruction, encoding="utf-8")
    (task / "task.toml").write_text(
        """
[environment]
cpus = 1
memory_mb = 2048
[agent]
timeout_sec = 900.0
[verifier]
timeout_sec = 600.0
""",
        encoding="utf-8",
    )
    return task


def finding_types(task: Path) -> set[str]:
    return {str(row["defect_type"]) for row in audit_terminal_task(task)}


def test_resource_parser_uses_tightest_repeated_limit():
    parsed = parse_task_resources(
        "memory_mb = 8192\n[verifier]\nmemory_mb = 4096\ntimeout_sec = 30.0\n"
    )

    assert parsed == {"memory_mb": 4096.0, "timeout_sec": 30.0}


def test_exact_apt_pin_is_flagged(tmp_path):
    task = make_task(tmp_path)
    (task / "solution" / "solve.sh").write_text(
        "apt-get install -y curl=8.5.0-1 ca-certificates\n", encoding="utf-8"
    )

    assert "fragile_exact_system_package_pin" in finding_types(task)


def test_unpinned_package_install_is_not_flagged_as_exact_pin(tmp_path):
    task = make_task(tmp_path)
    (task / "solution" / "solve.sh").write_text(
        "apt-get install -y curl ca-certificates\n", encoding="utf-8"
    )

    assert "fragile_exact_system_package_pin" not in finding_types(task)


def test_low_memory_heavy_stack_is_review_signal(tmp_path):
    task = make_task(tmp_path)
    (task / "tests" / "test.py").write_text("import torch\n", encoding="utf-8")

    assert "low_resource_headroom" in finding_types(task)


def test_exact_directory_listing_is_overstrict(tmp_path):
    task = make_task(tmp_path)
    (task / "tests" / "test.py").write_text(
        'assert os.listdir("/app/out") == ["answer.txt"]\n', encoding="utf-8"
    )

    assert "overstrict_directory_exactness" in finding_types(task)


def test_explicit_do_not_modify_suppresses_immutability_gap(tmp_path):
    task = make_task(tmp_path, instruction="Do not modify /app/data.db.")
    (task / "tests" / "test.py").write_text(
        "expected = sha256(path); assert sha256(path) == expected\n", encoding="utf-8"
    )

    assert "implicit_input_byte_immutability" not in finding_types(task)


def test_runtime_external_url_is_review_signal(tmp_path):
    task = make_task(tmp_path)
    (task / "solution" / "solve.sh").write_text(
        "wget https://example.org/data.bin\n", encoding="utf-8"
    )

    assert "runtime_external_dependency" in finding_types(task)
