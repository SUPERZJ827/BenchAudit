import sys
import unittest
from pathlib import Path

from benchcore.execution import (
    CommandSpec,
    ContainerRunner,
    ExecutionPolicy,
    ExecutionRefused,
    LocalProcessRunner,
)


def test_local_runner_refuses_execution_by_default():
    with unittest.TestCase().assertRaises(ExecutionRefused):
        LocalProcessRunner().run(CommandSpec((sys.executable, "-c", "print('x')")))


def test_local_runner_runs_explicitly_trusted_command_without_shell(tmp_path: Path):
    result = LocalProcessRunner().run(
        CommandSpec((sys.executable, "-c", "print('safe')"), cwd=tmp_path),
        ExecutionPolicy(allow_local_process=True),
    )

    assert result.succeeded
    assert result.stdout.strip() == "safe"
    assert result.isolation == "trusted_local_process"


def test_local_runner_rejects_unapproved_environment_variable():
    with unittest.TestCase().assertRaisesRegex(ExecutionRefused, "SECRET"):
        LocalProcessRunner().run(
            CommandSpec((sys.executable, "-c", "pass"), env={"SECRET": "value"}),
            ExecutionPolicy(allow_local_process=True),
        )


def test_local_runner_streams_and_bounds_stdout_and_stderr():
    result = LocalProcessRunner().run(
        CommandSpec((
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.stdout.write('stdout-head-' + 'A' * 200000 + '-stdout-tail'); "
                "sys.stderr.write('stderr-head-' + 'B' * 200000 + '-stderr-tail')"
            ),
        )),
        ExecutionPolicy(allow_local_process=True, max_output_chars=1_000),
    )

    assert result.succeeded
    assert len(result.stdout) <= 1_000
    assert len(result.stderr) <= 1_000
    assert "stdout-head" in result.stdout and "stdout-tail" in result.stdout
    assert "stderr-head" in result.stderr and "stderr-tail" in result.stderr
    assert "output truncated" in result.stdout
    assert "output truncated" in result.stderr


def test_local_runner_timeout_preserves_bounded_partial_output():
    result = LocalProcessRunner().run(
        CommandSpec((
            sys.executable,
            "-c",
            "import time; print('started', flush=True); time.sleep(10)",
        )),
        ExecutionPolicy(
            allow_local_process=True,
            timeout_seconds=0.2,
            max_output_chars=1_000,
        ),
    )

    assert result.timed_out
    assert result.exit_code is None
    assert "started" in result.stdout


def test_local_runner_timeout_applies_after_child_closes_output_pipes():
    result = LocalProcessRunner().run(
        CommandSpec((
            sys.executable,
            "-c",
            "import os, time; os.close(1); os.close(2); time.sleep(10)",
        )),
        ExecutionPolicy(allow_local_process=True, timeout_seconds=0.2),
    )

    assert result.timed_out
    assert result.elapsed_seconds < 2.0


def test_local_runner_streams_stdin_without_pipe_deadlock():
    payload = "input-data-" * 100_000
    result = LocalProcessRunner().run(
        CommandSpec(
            (sys.executable, "-c", "import sys; print(len(sys.stdin.read()))"),
            stdin=payload,
        ),
        ExecutionPolicy(allow_local_process=True, timeout_seconds=5),
    )

    assert result.succeeded
    assert result.stdout.strip() == str(len(payload))


def test_container_command_has_security_controls(tmp_path: Path):
    runner = ContainerRunner("python:3.12-slim", engine="/usr/bin/docker")
    argv = runner.build_argv(
        CommandSpec(("python", "-c", "print(1)"), cwd=tmp_path),
        ExecutionPolicy(),
    )
    joined = " ".join(argv)

    assert "--network none" in joined
    assert "--read-only" in argv
    assert "--cap-drop=ALL" in argv
    assert "--security-opt=no-new-privileges" in argv
    assert "readonly" in joined
    assert "--pids-limit=128" in argv


def test_container_forwards_stdin_only_when_present(tmp_path: Path):
    runner = ContainerRunner("python:3.12-slim", engine="/usr/bin/docker")
    with_stdin = runner.build_argv(
        CommandSpec(("python", "-c", "print(1)"), cwd=tmp_path, stdin="payload"),
        ExecutionPolicy(),
    )
    without_stdin = runner.build_argv(
        CommandSpec(("python", "-c", "print(1)"), cwd=tmp_path),
        ExecutionPolicy(),
    )
    # -i must precede the image so the driver's stdin payload reaches the container.
    assert "-i" in with_stdin[: with_stdin.index("python:3.12-slim")]
    assert "-i" not in without_stdin


def test_container_replaces_host_python_with_image_python(tmp_path: Path):
    runner = ContainerRunner(
        "python:3.12-slim",
        engine="/usr/bin/docker",
        python_executable="python3",
    )
    argv = runner.build_argv(
        CommandSpec((sys.executable, "-c", "print(1)"), cwd=tmp_path),
        ExecutionPolicy(),
    )

    image_index = argv.index("python:3.12-slim")
    assert argv[image_index + 1] == "python3"
    assert sys.executable not in argv[image_index + 1:]
