"""B2 value-recompute checker (executes LLM-generated code).

For each rubric that ASSERTS a substantive numeric value, an LLM writes pandas
code that RE-COMPUTES that quantity from the selected input files; we execute
the code and check whether every asserted number is reproduced. This catches
wrong oracle values and values whose source data is absent, independently of
layout or wording.

SECURITY: generated code is untrusted.  Production callers must supply an
isolated :class:`~benchcore.execution.CommandRunner` (normally a
``ContainerRunner``).  Host subprocess execution is refused unless both the
runner policy and an explicit unsafe-local acknowledgement opt in.  Every
probe gets a new, otherwise-empty workspace containing only the generated
script and copied, explicitly selected inputs.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence

from .artifact_consistency import (
    context_path_candidate,
    context_pairs,
    extract_rubrics,
    is_structure_rubric,
    resolve_path,
    resolve_context_path_candidate,
)
from .checkers import Checker, _violation
from .coverage import AuditEligibility
from .execution import (
    CommandRunner,
    CommandSpec,
    ExecutionPolicy,
    ExecutionRefused,
    LocalProcessRunner,
    RunResult,
)
from .file_reader import read_file
from .llm_client import LLMClient
from .schema import BenchmarkItem, Violation

SYSTEM_PROMPT = """You recompute quantities from data files to verify a benchmark
rubric. You do not trust the rubric's numbers; you compute them independently.
Return only JSON."""

USER_PROMPT = """Write Python (pandas as pd) that RE-COMPUTES, from the input files,
the quantity the rubric asserts, and prints it as `label=value`.

Reading inputs (use only the sandbox paths given below; files may be hash-named with no
extension, so judge type from the preview, not the name):
- try pandas first: pd.read_csv(path) / pd.read_excel(path) (pandas reads by content).
- if a file is not tabular, call the preloaded helper `read_file(path, 20000)`, which
  returns the file's text (handles docx/pdf/pptx/txt/xml); parse the number from it.

Rules:
- Print the numeric VALUE itself, e.g. `count=84` or `total=58000`. NEVER print a
  boolean such as yes/no/true/false -- print the number you computed.
- Compute the FULL quantity the rubric asks about (e.g. a grand total across all
  rows/months/categories), not a single row or a partial subset.
- Do not trust the rubric's numbers; compute independently.
- Only if the data is genuinely absent from every input file, print
  `DATA_NOT_AVAILABLE` and nothing else.

Return ONLY JSON: {{"code": "<python that prints label=value lines>"}}

INPUT FILES (read-only paths inside the isolated /workspace + preview):
{inputs}

RUBRIC: {rubric}"""


def nums(s: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", s.replace(",", ""))]


def rubric_values(s: str) -> list[float]:
    """Extract only the SUBSTANTIVE numeric claims from a rubric, dropping the numbers
    that are identifiers / indices / years / filename digits / THRESHOLDS -- nums() treats
    those as 'expected values' and produces false B2 mismatches (Partner 3, item 14, PO
    #1013, SR-021, DES-06, year 2024, '4-financial-table.xlsx', the '50' in 'discount
    >=50%'). Keeps real counts/sums/figures."""
    t = s
    t = re.sub(r'\b[\w\-./]+\.(?:xlsx|xls|csv|txt|docx?|pdf|md|py|json|pptx?|png|html?)\b', ' ', t, flags=re.I)  # filenames
    # inequality / threshold numbers ('>=50%', 'at least 3', 'top 10%') are FILTER conditions,
    # not asserted results -- a recompute reproduces the asserted value, never the threshold.
    t = re.sub(r'(?:≥|≤|>=|<=|>|<|至少|至多|不少于|不超过|不低于|不高于|大于|小于|超过|低于|高于|'
               r'at least|at most|no (?:less|more) than|not (?:less|more) than|greater than|'
               r'less than|more than|over|above|below|up to|within|between)\s*[¥$]?\s*\d[\d,]*\.?\d*\s*%?',
               ' ', t, flags=re.I)
    t = re.sub(r'\b\d[\d,]*\.?\d*\s*%?\s*(?:-|to|~|–|—|至|到)\s*\d[\d,]*\.?\d*\s*%', ' ', t)  # ranges '35%-45%'
    # bare numeric ranges are labels/bins ('1-9 beds', '10-29', '30-49'), not asserted
    # single values -- a recompute reproduces one value, never a range bound.
    t = re.sub(r'\b\d[\d,]*\.?\d*\s*(?:-|–|—|~|至|到)\s*\d[\d,]*\.?\d*\b', ' ', t)
    t = re.sub(r'\b[A-Za-z]{1,}[-_]?\d[\w-]*', ' ', t)      # SR-021, DES-06, DEV-0108, PO-2024-019, W42, P4, A4
    t = re.sub(r'#\s*\d+', ' ', t)                          # #1013
    t = re.sub(r'\b(?:item|items|partner|chapter|page|pages|top|no|number|question|article|'
               r'figure|fig|table|slide|part|day|days|month|months|week|weeks|step|point|'
               r'grades?|level|priority|section|row|column|col|q|dev|proj)\.?\s*#?\s*\d+',
               ' ', t, flags=re.I)                          # ordinal/index words + number
    t = re.sub(r'第\s*\d+\s*(?:个|条|项|章|页|位|名|列|行|款|季度|周|天|月)?', ' ', t)
    t = re.sub(r'序号\s*\d+', ' ', t)
    # Chinese calendar tokens: '2024年' (the English \b year rule fails before 年, a word char),
    # month/day indices '1月' '01月' '15日' -- calendar references, never asserted results.
    # '12个月' (a duration) keeps its number: the 个 blocks the N月 match.
    t = re.sub(r'(?:19|20)\d{2}\s*年', ' ', t)
    t = re.sub(r'\d{1,2}\s*[月日号]', ' ', t)
    t = re.sub(r'\b(?:19|20)\d{2}\b', ' ', t)               # standalone years
    return nums(t)


def computed_values(output: str) -> list[float]:
    """Numbers from the VALUE side of `label=value` lines only. Labels such as
    'centers_10_29_beds' otherwise leak 10 and 29 into the comparison, both faking
    matches and hiding all-zero (failed) recomputes."""
    vals: list[float] = []
    for line in output.splitlines():
        if "=" not in line:
            continue
        rhs = line.rsplit("=", 1)[-1]
        vals.extend(nums(rhs))
    return vals


def reproduced(expected: list[float], computed_out: str) -> list[float]:
    """Each expected number must appear (within 0.5% or ±1) in the computed output."""
    got = computed_values(computed_out)
    miss = []
    for e in expected:
        if not any(abs(e - g) <= max(1, abs(e) * 0.005) for g in got):
            miss.append(e)
    return miss


def is_uninformative(computed: str, expected: list[float]) -> bool:
    """A recompute that produced no usable value -- not a rubric defect. Covers nan/None
    results and all-zero output while the rubric asserts non-zero values (the LLM code
    found/parsed nothing and emitted zeros instead of the DATA_NOT_AVAILABLE sentinel)."""
    low = computed.lower()
    if "nan" in low or "none" in low or "null" in low:
        return True
    got = computed_values(computed)
    if not got:
        return True
    if got and all(g == 0 for g in got) and any(e != 0 for e in expected):
        return True
    return False


_PRELUDE = r'''# Standalone probe prelude: never import BenchAudit or mount its repository.
import re
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

def read_file(path, max_chars=20000):
    """Small, dependency-light reader available to generated recompute code.

    Office Open XML formats are read directly from their ZIP/XML payload.  PDF
    extraction uses pypdf/PyPDF2 only when the selected container image ships
    it.  Missing optional dependencies fail explicitly instead of reaching
    back into the host BenchAudit checkout.
    """
    p = Path(path)
    limit = max(1, min(int(max_chars), 200000))
    suffix = p.suffix.lower()
    if suffix in {".docx", ".pptx", ".xlsx", ".xlsm"} or zipfile.is_zipfile(p):
        chunks = []
        with zipfile.ZipFile(p) as archive:
            for name in sorted(archive.namelist()):
                if not name.lower().endswith((".xml", ".rels")):
                    continue
                raw = archive.read(name)
                text = raw.decode("utf-8", errors="replace")
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    chunks.append(text)
                if sum(len(value) for value in chunks) >= limit:
                    break
        return "\n".join(chunks)[:limit]
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        chunks = []
        with p.open("rb") as handle:
            for page in PdfReader(handle).pages:
                chunks.append(page.extract_text() or "")
                if sum(len(value) for value in chunks) >= limit:
                    break
        return "\n".join(chunks)[:limit]
    return p.read_bytes()[: max(limit * 4, limit)].decode("utf-8", errors="replace")[:limit]
'''


@dataclass(frozen=True)
class SandboxInput:
    """One host input copied to a deterministic path in the probe workspace."""

    source: Path
    relative_path: Path

    @property
    def sandbox_path(self) -> str:
        return "/workspace/" + self.relative_path.as_posix()


@dataclass(frozen=True)
class RecomputeExecution:
    """Successful execution evidence. Failures raise ``RecomputeExecutionError``."""

    output: str
    backend: str
    isolation: str
    elapsed_seconds: float
    input_count: int
    script_sha256: str
    network_isolated: bool
    workspace_mount: str

    def to_evidence(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "isolation": self.isolation,
            "elapsed_seconds": self.elapsed_seconds,
            "input_count": self.input_count,
            "script_sha256": self.script_sha256,
            "network_policy_requested": "disabled",
            "network_isolated": self.network_isolated,
            "workspace_mount": self.workspace_mount,
        }


class RecomputeExecutionError(RuntimeError):
    """Operational probe failure; never evidence that the benchmark is clean."""

    def __init__(self, kind: str, message: str, *, run: RunResult | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.run = run


def sandbox_inputs(paths: Sequence[Path]) -> list[SandboxInput]:
    """Assign stable, non-secret paths without exposing host path components."""

    rows: list[SandboxInput] = []
    for index, source in enumerate(paths):
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", source.name).strip("._")
        name = (name or "input")[-120:]
        rows.append(SandboxInput(source.resolve(), Path("inputs") / f"{index:04d}_{name}"))
    return rows


def _effective_policy(
    policy: ExecutionPolicy | None,
    *,
    timeout: float,
    local: bool,
) -> ExecutionPolicy:
    base = policy or ExecutionPolicy(timeout_seconds=float(timeout))
    if base.network_enabled:
        raise ExecutionRefused("value recompute forbids network-enabled execution policies")
    if local and not base.allow_local_process:
        raise ExecutionRefused(
            "unsafe local value recompute also requires ExecutionPolicy(allow_local_process=True)"
        )
    return replace(
        base,
        timeout_seconds=min(float(timeout), base.timeout_seconds),
        network_enabled=False,
        allow_local_process=local,
        allowed_environment=frozenset(),
    )


def _copy_regular_file_bounded(source: Path, target: Path, max_bytes: int) -> int:
    """Copy one allowlisted regular file without following a last-hop symlink.

    The execution timeout starts after staging, so staging itself needs a byte
    bound and must not block on a FIFO/device accidentally substituted for an
    input.  ``O_NOFOLLOW`` closes the most common stat/copy symlink race.
    """

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(source, flags)
    copied = 0
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RecomputeExecutionError(
                "invalid_input", "an explicitly selected input is not a regular file"
            )
        if metadata.st_size > max_bytes:
            raise RecomputeExecutionError(
                "input_budget", "an input exceeds the remaining staging byte budget"
            )
        with (
            os.fdopen(descriptor, "rb", closefd=False) as source_handle,
            target.open("xb") as target_handle,
        ):
            while True:
                chunk = source_handle.read(min(1024 * 1024, max_bytes - copied + 1))
                if not chunk:
                    break
                copied += len(chunk)
                if copied > max_bytes:
                    raise RecomputeExecutionError(
                        "input_budget", "inputs grew beyond the staging byte budget"
                    )
                target_handle.write(chunk)
    finally:
        os.close(descriptor)
    target.chmod(0o400)
    return copied


def execute_code(
    code: str,
    timeout: float = 15,
    *,
    runner: CommandRunner | None = None,
    policy: ExecutionPolicy | None = None,
    input_paths: Sequence[Path] = (),
    allow_unsafe_local: bool = False,
    max_code_chars: int = 100_000,
    max_input_files: int = 64,
    max_total_input_bytes: int = 512 * 1024 * 1024,
) -> RecomputeExecution:
    """Execute generated code in an isolated, least-privilege workspace.

    ``runner=None`` is deliberately an error: a timeout-limited subprocess is
    not a sandbox.  A ``LocalProcessRunner`` needs two independent API-level
    opt-ins (``allow_unsafe_local`` and ``policy.allow_local_process``), mirroring
    the CLI's two acknowledgement flags.
    """

    if runner is None:
        raise ExecutionRefused(
            "value recompute execution refused: provide an isolated runner"
        )
    if timeout <= 0 or max_code_chars <= 0 or max_input_files <= 0 or max_total_input_bytes <= 0:
        raise ValueError("execution timeout and resource budgets must be positive")
    local = isinstance(runner, LocalProcessRunner)
    if local and not allow_unsafe_local:
        raise ExecutionRefused(
            "LocalProcessRunner requires allow_unsafe_local=True for value recompute"
        )
    if not isinstance(code, str) or not code.strip():
        raise RecomputeExecutionError("invalid_code", "generated code is empty")
    if "\x00" in code or len(code) > max_code_chars:
        raise RecomputeExecutionError(
            "invalid_code", f"generated code exceeds the {max_code_chars}-character safety budget"
        )
    if len(input_paths) > max_input_files:
        raise RecomputeExecutionError(
            "input_budget", f"input count exceeds the {max_input_files}-file safety budget"
        )

    bindings = sandbox_inputs(input_paths)
    total_bytes = 0
    for binding in bindings:
        if not binding.source.is_file():
            raise RecomputeExecutionError("missing_input", "an explicitly selected input is not a file")
        total_bytes += binding.source.stat().st_size
        if total_bytes > max_total_input_bytes:
            raise RecomputeExecutionError(
                "input_budget",
                f"inputs exceed the {max_total_input_bytes}-byte safety budget",
            )

    execution_policy = _effective_policy(policy, timeout=timeout, local=local)
    script_text = _PRELUDE + "\n" + code.rstrip() + "\n"
    script_sha256 = hashlib.sha256(script_text.encode("utf-8")).hexdigest()

    with tempfile.TemporaryDirectory(prefix="benchcore-value-recompute-") as directory:
        workspace = Path(directory)
        (workspace / "inputs").mkdir(mode=0o700)
        copied_bytes = 0
        for binding in bindings:
            target = workspace / binding.relative_path
            copied_bytes += _copy_regular_file_bounded(
                binding.source,
                target,
                max_total_input_bytes - copied_bytes,
            )

        # In the explicitly unsafe local mode, translate only the documented
        # sandbox prefix. This is a compatibility aid, not isolation: the user
        # has already acknowledged that local code can access the entire host.
        effective_script = script_text
        if local:
            effective_script = effective_script.replace("/workspace/", f"{workspace.as_posix()}/")
        script_path = workspace / "recompute_probe.py"
        script_path.write_text(effective_script, encoding="utf-8")
        script_path.chmod(0o400)

        try:
            result = runner.run(
                CommandSpec((sys.executable, script_path.name), cwd=workspace),
                execution_policy,
            )
        except ExecutionRefused:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize backend failures
            raise RecomputeExecutionError(
                "runner_error", f"execution backend failed: {type(exc).__name__}: {exc}"
            ) from exc

        if result.timed_out:
            raise RecomputeExecutionError("timeout", "recompute probe timed out", run=result)
        if result.exit_code != 0:
            detail = (result.stderr or result.stdout or "no diagnostic output").strip()[-500:]
            raise RecomputeExecutionError(
                "dependency_or_runtime_error",
                f"recompute probe exited with code {result.exit_code}: {detail}",
                run=result,
            )
        output = (result.stdout or "").strip()
        if "...[output truncated; original_chars=" in output:
            raise RecomputeExecutionError(
                "output_budget", "recompute output exceeded the configured capture budget", run=result
            )
        if not output:
            raise RecomputeExecutionError(
                "invalid_output", "recompute probe produced no stdout", run=result
            )
        return RecomputeExecution(
            output=output,
            backend=result.backend,
            isolation=result.isolation,
            elapsed_seconds=result.elapsed_seconds,
            input_count=len(bindings),
            script_sha256=script_sha256,
            # ExecutionPolicy expresses the desired network setting, but only
            # the container backend enforces it. LocalProcessRunner is plainly
            # labelled unsafe rather than claiming a sandbox it does not have.
            network_isolated=not local,
            workspace_mount="temporary_not_isolated" if local else "read_only",
        )


def run_code(
    code: str,
    timeout: float = 15,
    *,
    runner: CommandRunner | None = None,
    policy: ExecutionPolicy | None = None,
    input_paths: Sequence[Path] = (),
    allow_unsafe_local: bool = False,
) -> str:
    """Compatibility wrapper returning stdout while retaining fail-closed safety."""

    return execute_code(
        code,
        timeout,
        runner=runner,
        policy=policy,
        input_paths=input_paths,
        allow_unsafe_local=allow_unsafe_local,
    ).output


def _within_allowed_roots(path: Path, allowed_roots: Sequence[Path] | None) -> bool:
    if allowed_roots is None:
        return True
    resolved_roots = [candidate.expanduser().resolve() for candidate in allowed_roots]
    return any(path == candidate or path.is_relative_to(candidate) for candidate in resolved_roots)


def input_file_paths(
    item: BenchmarkItem,
    root: Path | None,
    *,
    allowed_roots: Sequence[Path] | None = None,
) -> list[Path]:
    """Resolved, existing input files. Tabular ones the recompute reads with pandas;
    the rest it reads via read_file, so the data a rubric needs is not starved just
    because it lives in a non-tabular input."""
    paths: list[Path] = []
    seen: set[str] = set()
    for _label, value in context_pairs(item):
        for entry in value if isinstance(value, list) else [value]:
            if not isinstance(entry, str):
                continue
            path = resolve_path(entry, root, allowed_roots=allowed_roots)
            if path is None or not path.exists():
                continue
            resolved = path.resolve()
            if not resolved.is_file() or not _within_allowed_roots(resolved, allowed_roots):
                continue
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            paths.append(resolved)
    return paths


def _blocked_input_paths(
    item: BenchmarkItem,
    root: Path | None,
    allowed_roots: Sequence[Path] | None,
) -> list[str]:
    """Return declared materialized paths rejected by realpath containment."""

    if allowed_roots is None:
        return []
    blocked: list[str] = []
    for _label, value in context_pairs(item):
        for entry in value if isinstance(value, list) else [value]:
            if not isinstance(entry, str):
                continue
            candidate = context_path_candidate(entry, root)
            if candidate is None:
                continue
            resolved, blocked_reason = resolve_context_path_candidate(
                candidate,
                root=root,
                allowed_roots=allowed_roots,
            )
            if blocked_reason is not None:
                # Do not echo the host path into LLM prompts or finding evidence.
                blocked.append(hashlib.sha256(str(candidate).encode("utf-8")).hexdigest()[:16])
                continue
            if resolved is None or not resolved.exists():
                continue
    return sorted(set(blocked))


def inputs_preview(paths: list[Path], per_file_chars: int) -> str:
    # read_file gives the LLM a content preview so it can tell tabular from text even
    # when files are hash-named; the generated code re-reads the real file for the compute.
    bindings = sandbox_inputs(paths)
    return "\n\n".join(
        f"路径: {binding.sandbox_path}\n{read_file(binding.source, per_file_chars)}"
        for binding in bindings
    )


class ValueRecomputeChecker(Checker):
    """Re-compute numeric rubric assertions from tabular inputs (executes LLM code)."""

    name = "value_recompute"

    def __init__(
        self,
        client: LLMClient,
        *,
        runner: CommandRunner | None = None,
        policy: ExecutionPolicy | None = None,
        allow_unsafe_local: bool = False,
        allowed_roots: Sequence[Path] | None = None,
        per_file_chars: int = 1200,
        max_inputs_chars: int = 8000,
        timeout: int = 15,
        max_input_files: int = 64,
        max_total_input_bytes: int = 512 * 1024 * 1024,
        confidence: float = 0.6,
    ) -> None:
        if per_file_chars <= 0 or max_inputs_chars <= 0:
            raise ValueError("preview character budgets must be positive")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_input_files <= 0 or max_total_input_bytes <= 0:
            raise ValueError("input execution budgets must be positive")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")
        self.client = client
        self.runner = runner
        self.policy = policy
        self.allow_unsafe_local = allow_unsafe_local
        self.allowed_roots = tuple(allowed_roots) if allowed_roots is not None else None
        self.per_file_chars = per_file_chars
        self.max_inputs_chars = max_inputs_chars
        self.timeout = timeout
        self.max_input_files = max_input_files
        self.max_total_input_bytes = max_total_input_bytes
        self.confidence = confidence

    def audit_eligibility(
        self,
        item: BenchmarkItem,
        root: Path | None = None,
    ) -> AuditEligibility:
        blocked = _blocked_input_paths(item, root, self.allowed_roots)
        if blocked:
            return AuditEligibility(
                False,
                f"{len(blocked)} materialized input path(s) escape the allowed roots",
                "security_blocked",
            )
        paths = input_file_paths(item, root, allowed_roots=self.allowed_roots)
        if not paths:
            return AuditEligibility.not_applicable(
                "value recompute requires at least one materialized input file"
            )
        rubrics = extract_rubrics(item)
        if not any(
            rubric_values(rubric) and not is_structure_rubric(rubric)
            for rubric in rubrics
        ):
            return AuditEligibility.not_applicable(
                "item has no substantive numeric rubric assertion"
            )
        if self.runner is None:
            return AuditEligibility(
                False,
                "generated code execution requires an isolated runner",
                "security_blocked",
            )
        if self.policy is not None and self.policy.network_enabled:
            return AuditEligibility(
                False,
                "value recompute forbids network-enabled execution policies",
                "security_blocked",
            )
        if isinstance(self.runner, LocalProcessRunner) and not (
            self.allow_unsafe_local
            and self.policy is not None
            and self.policy.allow_local_process
        ):
            return AuditEligibility(
                False,
                "LocalProcessRunner lacks both unsafe-local API acknowledgements",
                "security_blocked",
            )
        if len(paths) > self.max_input_files:
            return AuditEligibility(
                False,
                f"input count exceeds the configured {self.max_input_files}-file budget",
                "unsupported",
            )
        try:
            total_bytes = sum(path.stat().st_size for path in paths)
        except OSError as exc:
            return AuditEligibility(
                False,
                f"input metadata is unavailable: {type(exc).__name__}",
                "unsupported",
            )
        if total_bytes > self.max_total_input_bytes:
            return AuditEligibility(
                False,
                "input bytes exceed the configured execution budget",
                "unsupported",
            )
        return AuditEligibility.applicable(
            "materialized inputs, numeric rubric assertions, and an authorized execution backend are present"
        )

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        paths = input_file_paths(item, root, allowed_roots=self.allowed_roots)
        if not paths:
            return
        rubrics = extract_rubrics(item)
        # only rubrics that ASSERT a substantive numeric value are recomputable; rubric_values()
        # drops identifiers/thresholds/years/filenames so those never trigger a B2 recompute.
        numeric = {
            index
            for index, rubric in enumerate(rubrics)
            if rubric_values(rubric) and not is_structure_rubric(rubric)
        }
        if not numeric:
            return
        inputs = inputs_preview(paths, self.per_file_chars)[: self.max_inputs_chars]
        for index, rubric in enumerate(rubrics):
            if index not in numeric:
                continue
            yield from self._check_rubric(item, index, rubric, inputs, paths)

    def _check_rubric(
        self,
        item: BenchmarkItem,
        index: int,
        rubric: str,
        inputs: str,
        paths: list[Path],
    ) -> Iterable[Violation]:
        prompt = USER_PROMPT.format(inputs=inputs, rubric=rubric)
        try:
            generated = self.client.chat_json(SYSTEM_PROMPT, prompt)
        except Exception as exc:  # noqa: BLE001 - preserve row-level failure
            yield _violation(
                item,
                "llm_audit_failure",
                0.25,
                "Value-recompute code generation failed.",
                {"rubric_index": index, "rubric": rubric, "error": f"{type(exc).__name__}: {exc}"},
                severity="review",
                review_only=True,
                method="value_recompute",
                scope="operational",
            )
            return
        code = generated.get("code", "") if isinstance(generated, dict) else ""
        if not isinstance(code, str) or "print" not in code:
            yield self._operational_failure(
                item,
                index,
                rubric,
                "invalid_code",
                "Generated recompute code does not implement the required print protocol.",
            )
            return
        try:
            execution = execute_code(
                code,
                self.timeout,
                runner=self.runner,
                policy=self.policy,
                input_paths=paths,
                allow_unsafe_local=self.allow_unsafe_local,
                max_input_files=self.max_input_files,
                max_total_input_bytes=self.max_total_input_bytes,
            )
            computed = execution.output
        except (ExecutionRefused, RecomputeExecutionError) as exc:
            yield self._operational_failure(
                item,
                index,
                rubric,
                getattr(exc, "kind", "execution_refused"),
                str(exc),
            )
            return
        # This checker's only substantive signal is a concrete value mismatch.
        # Unrunnable or DATA_NOT_AVAILABLE results are explicit operational
        # unknowns: they affect coverage, but are never benchmark defects.
        expected = rubric_values(rubric)
        if "DATA_NOT_AVAILABLE" in computed or is_uninformative(computed, expected):
            yield self._operational_failure(
                item,
                index,
                rubric,
                "inconclusive_recompute",
                "Recompute produced no independently usable value.",
                execution=execution,
            )
            return
        missing = reproduced(expected, computed)
        if missing:
            yield _violation(
                item,
                "rubric_target_error",
                self.confidence,
                "Rubric's asserted target value(s) not reproduced by independent recompute from inputs.",
                {
                    "rubric_index": index,
                    "rubric": rubric,
                    "expected_values": expected,
                    "missing_values": missing,
                    "computed_output": computed[:200],
                    "code": code,
                    "execution": execution.to_evidence(),
                },
                severity="review",
                review_only=True,
                method="value_recompute",
            )

    @staticmethod
    def _operational_failure(
        item: BenchmarkItem,
        index: int,
        rubric: str,
        kind: str,
        message: str,
        *,
        execution: RecomputeExecution | None = None,
    ) -> Violation:
        evidence: dict[str, object] = {
            "rubric_index": index,
            "rubric": rubric,
            "failure_kind": kind,
            "audit_coverage_status": "operational_failed",
        }
        if execution is not None:
            evidence["execution"] = execution.to_evidence()
        return _violation(
            item,
            "llm_audit_failure",
            0.25,
            f"Value-recompute execution was inconclusive: {message[:500]}",
            evidence,
            severity="review",
            review_only=True,
            method="value_recompute",
            scope="operational",
        )
