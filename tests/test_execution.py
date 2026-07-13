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
