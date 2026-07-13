from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, Sequence


class ExecutionRefused(RuntimeError):
    """Raised when a requested command exceeds the configured trust boundary."""


@dataclass(frozen=True)
class ExecutionPolicy:
    timeout_seconds: float = 30.0
    max_output_chars: int = 100_000
    memory_mb: int = 512
    cpu_count: float = 1.0
    pids_limit: int = 128
    network_enabled: bool = False
    allow_local_process: bool = False
    allowed_environment: frozenset[str] = frozenset({"LANG", "LC_ALL", "TZ"})

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_output_chars <= 0:
            raise ValueError("max_output_chars must be positive")
        if self.memory_mb <= 0 or self.cpu_count <= 0 or self.pids_limit <= 0:
            raise ValueError("resource limits must be positive")


@dataclass(frozen=True)
class CommandSpec:
    argv: tuple[str, ...]
    cwd: Path | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    stdin: str | None = None

    def __post_init__(self) -> None:
        if not self.argv or not self.argv[0]:
            raise ValueError("argv must contain an executable")
        if any("\x00" in argument for argument in self.argv):
            raise ValueError("argv must not contain NUL bytes")


@dataclass(frozen=True)
class RunResult:
    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    elapsed_seconds: float
    timed_out: bool
    isolation: str
    backend: str

    @property
    def succeeded(self) -> bool:
        return not self.timed_out and self.exit_code == 0

    def to_dict(self) -> dict:
        return {
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "elapsed_seconds": self.elapsed_seconds,
            "timed_out": self.timed_out,
            "isolation": self.isolation,
            "backend": self.backend,
            "succeeded": self.succeeded,
        }


class CommandRunner(Protocol):
    def run(self, command: CommandSpec, policy: ExecutionPolicy | None = None) -> RunResult: ...


class LocalProcessRunner:
    """Runs trusted commands without a shell.

    This backend is intentionally opt-in. It constrains time, environment and
    output, but it is not an OS security sandbox and must never be presented as
    one.
    """

    def run(self, command: CommandSpec, policy: ExecutionPolicy | None = None) -> RunResult:
        policy = policy or ExecutionPolicy()
        if not policy.allow_local_process:
            raise ExecutionRefused(
                "local execution is disabled; use ContainerRunner or explicitly trust the command"
            )
        cwd = command.cwd.resolve() if command.cwd else None
        if cwd is not None and not cwd.is_dir():
            raise FileNotFoundError(cwd)
        env = _sanitized_environment(command.env, policy)
        started = time.monotonic()
        try:
            process = subprocess.run(
                list(command.argv),
                cwd=str(cwd) if cwd else None,
                env=env,
                input=command.stdin,
                capture_output=True,
                text=True,
                timeout=policy.timeout_seconds,
                shell=False,
                check=False,
            )
            return RunResult(
                argv=command.argv,
                exit_code=process.returncode,
                stdout=_truncate(process.stdout or "", policy.max_output_chars),
                stderr=_truncate(process.stderr or "", policy.max_output_chars),
                elapsed_seconds=round(time.monotonic() - started, 6),
                timed_out=False,
                isolation="trusted_local_process",
                backend="local",
            )
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                argv=command.argv,
                exit_code=None,
                stdout=_truncate(_as_text(exc.stdout), policy.max_output_chars),
                stderr=_truncate(_as_text(exc.stderr), policy.max_output_chars),
                elapsed_seconds=round(time.monotonic() - started, 6),
                timed_out=True,
                isolation="trusted_local_process",
                backend="local",
            )


class ContainerRunner:
    """Runs a command in an ephemeral Docker/Podman container."""

    def __init__(self, image: str, *, engine: str | None = None) -> None:
        if not image.strip():
            raise ValueError("container image is required")
        self.image = image
        self.engine = engine or find_container_engine()
        if not self.engine:
            raise ExecutionRefused("neither docker nor podman is available")

    def build_argv(self, command: CommandSpec, policy: ExecutionPolicy) -> tuple[str, ...]:
        if command.cwd is None:
            raise ValueError("container execution requires a workspace cwd")
        workspace = command.cwd.resolve()
        if not workspace.is_dir():
            raise FileNotFoundError(workspace)
        argv = [
            self.engine, "run", "--rm", "--init", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            f"--memory={policy.memory_mb}m", f"--cpus={policy.cpu_count}",
            f"--pids-limit={policy.pids_limit}",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--mount", f"type=bind,src={workspace},dst=/workspace,readonly",
            "--workdir", "/workspace",
        ]
        if not policy.network_enabled:
            argv.extend(["--network", "none"])
        for key, value in sorted(command.env.items()):
            if key not in policy.allowed_environment:
                raise ExecutionRefused(f"environment variable {key!r} is not allowed")
            argv.extend(["--env", f"{key}={value}"])
        argv.append(self.image)
        argv.extend(command.argv)
        return tuple(argv)

    def run(self, command: CommandSpec, policy: ExecutionPolicy | None = None) -> RunResult:
        policy = policy or ExecutionPolicy()
        container_argv = self.build_argv(command, policy)
        local_policy = ExecutionPolicy(
            timeout_seconds=policy.timeout_seconds,
            max_output_chars=policy.max_output_chars,
            memory_mb=policy.memory_mb,
            cpu_count=policy.cpu_count,
            pids_limit=policy.pids_limit,
            network_enabled=policy.network_enabled,
            allow_local_process=True,
            allowed_environment=frozenset(),
        )
        raw = LocalProcessRunner().run(
            CommandSpec(argv=container_argv, stdin=command.stdin),
            local_policy,
        )
        return RunResult(
            argv=command.argv,
            exit_code=raw.exit_code,
            stdout=raw.stdout,
            stderr=raw.stderr,
            elapsed_seconds=raw.elapsed_seconds,
            timed_out=raw.timed_out,
            isolation="ephemeral_container_readonly_workspace",
            backend=Path(self.engine).name,
        )


def find_container_engine() -> str | None:
    for name in ("podman", "docker"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _sanitized_environment(extra: Mapping[str, str], policy: ExecutionPolicy) -> dict[str, str]:
    disallowed = set(extra) - set(policy.allowed_environment)
    if disallowed:
        raise ExecutionRefused("disallowed environment variables: " + ", ".join(sorted(disallowed)))
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    for key in policy.allowed_environment:
        if key in os.environ:
            env[key] = os.environ[key]
    env.update({key: str(value) for key, value in extra.items()})
    return env


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker = f"\n...[output truncated; original_chars={len(value)}]...\n"
    side = max((limit - len(marker)) // 2, 0)
    return value[:side] + marker + value[-side:] if side else marker[:limit]


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
