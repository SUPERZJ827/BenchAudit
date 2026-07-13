from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol

from .execution import CommandRunner, CommandSpec, ExecutionPolicy, RunResult


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    workspace: Path
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HarnessRun:
    candidate_id: str
    phase: str
    result: RunResult

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "phase": self.phase,
            "result": self.result.to_dict(),
        }


class HarnessAdapter(Protocol):
    def prepare(self) -> None: ...
    def reset(self) -> None: ...
    def run(self, candidate: Candidate) -> HarnessRun: ...
    def cleanup(self) -> None: ...


class CommandHarnessAdapter:
    """Reusable adapter for command/exit-code benchmark harnesses.

    Candidate materialization remains an explicit caller responsibility. The
    adapter never invokes a shell or weakens the supplied runner's isolation.
    """

    def __init__(
        self,
        *,
        runner: CommandRunner,
        argv: tuple[str, ...],
        policy: ExecutionPolicy | None = None,
        environment: Mapping[str, str] | None = None,
        phase: str = "evaluate",
    ) -> None:
        if not argv:
            raise ValueError("harness argv is required")
        self.runner = runner
        self.argv = argv
        self.policy = policy or ExecutionPolicy()
        self.environment = dict(environment or {})
        self.phase = phase
        self._prepared = False

    def prepare(self) -> None:
        self._prepared = True

    def reset(self) -> None:
        if not self._prepared:
            raise RuntimeError("prepare() must be called before reset()")

    def run(self, candidate: Candidate) -> HarnessRun:
        if not self._prepared:
            raise RuntimeError("prepare() must be called before run()")
        workspace = candidate.workspace.resolve()
        if not workspace.is_dir():
            raise FileNotFoundError(workspace)
        result = self.runner.run(
            CommandSpec(argv=self.argv, cwd=workspace, env=self.environment),
            self.policy,
        )
        return HarnessRun(candidate_id=candidate.candidate_id, phase=self.phase, result=result)

    def cleanup(self) -> None:
        self._prepared = False
