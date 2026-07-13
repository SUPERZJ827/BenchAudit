import unittest
from pathlib import Path

from benchcore.execution import CommandSpec, ExecutionPolicy, RunResult
from benchcore.harness import Candidate, CommandHarnessAdapter


class RecordingRunner:
    def __init__(self):
        self.calls: list[tuple[CommandSpec, ExecutionPolicy]] = []

    def run(self, command: CommandSpec, policy: ExecutionPolicy | None = None) -> RunResult:
        assert policy is not None
        self.calls.append((command, policy))
        return RunResult(
            argv=command.argv,
            exit_code=0,
            stdout="ok",
            stderr="",
            elapsed_seconds=0.01,
            timed_out=False,
            isolation="fake",
            backend="fake",
        )


def test_command_harness_requires_prepare(tmp_path: Path):
    adapter = CommandHarnessAdapter(runner=RecordingRunner(), argv=("pytest", "-q"))

    with unittest.TestCase().assertRaisesRegex(RuntimeError, "prepare"):
        adapter.run(Candidate("gold", tmp_path))


def test_command_harness_preserves_runner_policy_and_candidate_identity(tmp_path: Path):
    runner = RecordingRunner()
    policy = ExecutionPolicy(timeout_seconds=12)
    adapter = CommandHarnessAdapter(
        runner=runner,
        argv=("pytest", "-q"),
        policy=policy,
        environment={"TZ": "UTC"},
    )
    adapter.prepare()

    result = adapter.run(Candidate("gold", tmp_path))

    assert result.candidate_id == "gold"
    assert result.result.succeeded
    assert runner.calls[0][0].cwd == tmp_path.resolve()
    assert runner.calls[0][0].env == {"TZ": "UTC"}
    assert runner.calls[0][1] is policy
    adapter.cleanup()
    with unittest.TestCase().assertRaises(RuntimeError):
        adapter.reset()
