from __future__ import annotations

import codecs
import os
import selectors
import shutil
import signal
import subprocess
import sys
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
        process = subprocess.Popen(
            list(command.argv),
            cwd=str(cwd) if cwd else None,
            env=env,
            stdin=subprocess.PIPE if command.stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=(os.name == "posix"),
        )
        try:
            stdout, stderr, timed_out = _communicate_bounded(
                process,
                stdin=command.stdin,
                timeout_seconds=policy.timeout_seconds,
                max_output_chars=policy.max_output_chars,
            )
        except BaseException:
            _kill_and_reap(process)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
            raise
        return RunResult(
            argv=command.argv,
            exit_code=None if timed_out else process.returncode,
            stdout=stdout,
            stderr=stderr,
            elapsed_seconds=round(time.monotonic() - started, 6),
            timed_out=timed_out,
            isolation="trusted_local_process",
            backend="local",
        )


class ContainerRunner:
    """Runs a command in an ephemeral Docker/Podman container."""

    def __init__(
        self,
        image: str,
        *,
        engine: str | None = None,
        python_executable: str = "python",
    ) -> None:
        if not image.strip():
            raise ValueError("container image is required")
        self.image = image
        self.engine = engine or find_container_engine()
        self.python_executable = python_executable.strip()
        if not self.python_executable:
            raise ValueError("container python executable is required")
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
            # Forward the host-provided stdin into the container; the audit driver
            # reads its payload from stdin, so without -i it sees an empty stream.
            *(["-i"] if command.stdin is not None else []),
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
        container_command = list(command.argv)
        if Path(container_command[0]).resolve() == Path(sys.executable).resolve():
            # Host interpreter paths (for example /usr/bin/python3.10) are not
            # meaningful inside an arbitrary image. The image owns its Python.
            container_command[0] = self.python_executable
        argv.extend(container_command)
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


class _BoundedTextCapture:
    """Continuously drains a stream while retaining only bounded head/tail text."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.keep_each = max((limit + 1) // 2, 1)
        self.head = ""
        self.tail = ""
        self.total_chars = 0
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def feed(self, value: bytes) -> None:
        self._append(self.decoder.decode(value, final=False))

    def finish(self) -> None:
        self._append(self.decoder.decode(b"", final=True))

    def _append(self, value: str) -> None:
        if not value:
            return
        self.total_chars += len(value)
        missing_head = max(self.keep_each - len(self.head), 0)
        if missing_head:
            self.head += value[:missing_head]
            value = value[missing_head:]
        if value:
            self.tail = (self.tail + value)[-self.keep_each:]

    def value(self) -> str:
        if self.total_chars <= self.limit:
            return (self.head + self.tail)[:self.total_chars]
        marker = f"\n...[output truncated; original_chars={self.total_chars}]...\n"
        if len(marker) >= self.limit:
            return marker[:self.limit]
        available = self.limit - len(marker)
        head_chars = (available + 1) // 2
        tail_chars = available - head_chars
        suffix = self.tail[-tail_chars:] if tail_chars else ""
        return self.head[:head_chars] + marker + suffix


def _communicate_bounded(
    process: subprocess.Popen[bytes],
    *,
    stdin: str | None,
    timeout_seconds: float,
    max_output_chars: int,
) -> tuple[str, str, bool]:
    """Drain a child with selector-based bounded capture and a hard deadline."""
    stdout_capture = _BoundedTextCapture(max_output_chars)
    stderr_capture = _BoundedTextCapture(max_output_chars)
    selector = selectors.DefaultSelector()
    streams: dict[int, tuple[str, object, _BoundedTextCapture | None]] = {}

    def register_read(stream: object, name: str, capture: _BoundedTextCapture) -> None:
        fd = stream.fileno()  # type: ignore[attr-defined]
        os.set_blocking(fd, False)
        selector.register(fd, selectors.EVENT_READ)
        streams[fd] = (name, stream, capture)

    assert process.stdout is not None and process.stderr is not None
    register_read(process.stdout, "stdout", stdout_capture)
    register_read(process.stderr, "stderr", stderr_capture)

    stdin_bytes = stdin.encode("utf-8") if stdin is not None else b""
    stdin_offset = 0
    if process.stdin is not None:
        fd = process.stdin.fileno()
        os.set_blocking(fd, False)
        selector.register(fd, selectors.EVENT_WRITE)
        streams[fd] = ("stdin", process.stdin, None)

    deadline = time.monotonic() + timeout_seconds
    kill_deadline: float | None = None
    timed_out = False
    try:
        while selector.get_map():
            now = time.monotonic()
            if not timed_out and now >= deadline:
                timed_out = True
                _kill_process_group(process)
                kill_deadline = now + 2.0
                for fd, (name, stream, _) in list(streams.items()):
                    if name == "stdin":
                        _unregister_and_close(selector, streams, fd, stream)

            if timed_out and kill_deadline is not None and now >= kill_deadline:
                # A descendant retaining an inherited pipe must not keep this
                # runner alive after the process group was killed.
                for fd, (_, stream, capture) in list(streams.items()):
                    if capture is not None:
                        capture.finish()
                    _unregister_and_close(selector, streams, fd, stream)
                break

            wait_until = kill_deadline if timed_out else deadline
            wait = max(min((wait_until or now) - now, 0.1), 0.0)
            for key, _ in selector.select(wait):
                fd = int(key.fd)
                name, stream, capture = streams.get(fd, ("", None, None))
                if name == "stdin":
                    try:
                        if stdin_offset < len(stdin_bytes):
                            written = os.write(fd, stdin_bytes[stdin_offset:stdin_offset + 65_536])
                            stdin_offset += written
                        if stdin_offset >= len(stdin_bytes):
                            _unregister_and_close(selector, streams, fd, stream)
                    except (BrokenPipeError, OSError):
                        _unregister_and_close(selector, streams, fd, stream)
                    continue
                try:
                    chunk = os.read(fd, 65_536)
                except BlockingIOError:
                    continue
                except OSError:
                    chunk = b""
                if chunk:
                    assert capture is not None
                    capture.feed(chunk)
                else:
                    assert capture is not None
                    capture.finish()
                    _unregister_and_close(selector, streams, fd, stream)
    finally:
        selector.close()

    if process.poll() is None and not timed_out:
        wait_timeout = max(deadline - time.monotonic(), 0.0)
        try:
            process.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
    if timed_out:
        _kill_and_reap(process)
    return stdout_capture.value(), stderr_capture.value(), timed_out


def _unregister_and_close(
    selector: selectors.BaseSelector,
    streams: dict[int, tuple[str, object, _BoundedTextCapture | None]],
    fd: int,
    stream: object,
) -> None:
    try:
        selector.unregister(fd)
    except (KeyError, ValueError):
        pass
    streams.pop(fd, None)
    try:
        stream.close()  # type: ignore[attr-defined]
    except (OSError, ValueError):
        pass


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            # The group can outlive its leader when a descendant inherited an
            # output pipe. Kill it even if the direct child already exited.
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


def _kill_and_reap(process: subprocess.Popen[bytes], timeout: float = 2.0) -> None:
    _kill_process_group(process)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # A platform-specific process-group operation may fail. Fall back to
        # the direct child and never use an unbounded wait in the runner.
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            pass
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass


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
