"""Code-execution verifier (tool-using executor).

For table-QA items, this checker parses the table into a pandas DataFrame, asks
an LLM to write code that computes the answer from the table, executes that code
through an explicitly configured command runner, and compares the computed
answer to the declared gold.  It refuses execution by default.

Unlike an LLM judging the table by eye, the answer is *computed*. This catches
table/computation gold errors and, crucially, is reproducible (the code and its
output are recorded) with no circularity (it computes, it does not look the
answer up).
"""
from __future__ import annotations

import io
import re
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Iterable

from .checkers import Checker
from .code_safety import UnsafeGeneratedCode, validate_generated_table_code
from .coverage import (
    AuditAbstained,
    AuditEligibility,
    AuditSecurityBlocked,
    AuditUnsupported,
)
from .execution import (
    CommandRunner,
    CommandSpec,
    ExecutionPolicy,
    ExecutionRefused,
)
from .llm_client import LLMClient
from .schema import BenchmarkItem, Violation

CODEGEN_PROMPT = """You are given a pandas DataFrame `df` already loaded from a table.
Write Python that computes the answer to the question using `df` and prints ONLY
the final answer (a number or short string) via print(). pandas is imported as pd
and numpy as np; `df` already exists (all columns are strings, coerce as needed).
Do not read files or the network.

Return ONLY JSON: {{"code": "<python statements that print the answer>"}}

DataFrame columns: {columns}
First rows:
{preview}

Question: {question}"""


def parse_markdown_table(md: str):
    lines = [ln for ln in md.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return None
    cells = lambda ln: [c.strip() for c in ln.strip().strip("|").split("|")]
    cols = cells(lines[0])
    rows = [cells(ln) for ln in lines[2:] if set(ln.strip()) - set("|-: ")]
    rows = [r for r in rows if len(r) == len(cols)]
    if not cols or not rows:
        return None
    return cols, rows


def _to_csv(cols, rows) -> str:
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    w.writerows(rows)
    return buf.getvalue()


def _normalize(ans) -> str:
    s = str(ans).strip().lower().replace(",", "")
    s = re.sub(r"[‒-―−]", "-", s)   # unify dash/minus variants
    s = re.sub(r"\s+", " ", s).strip().rstrip(".")
    s = re.sub(r"\b0+(\d)", r"\1", s)               # strip leading zeros (e.g. 05 -> 5)
    m = re.fullmatch(r"-?\d+\.?\d*", s)
    if m:
        f = float(s)
        return str(int(f)) if f == int(f) else f"{round(f, 4):g}"
    return s


def _table_markdown(item: BenchmarkItem) -> str | None:
    raw = item.raw or {}
    if isinstance(raw.get("table"), str) and "|" in raw["table"]:
        return raw["table"]
    ctx = item.context or {}
    vals = list(ctx.values()) if isinstance(ctx, dict) else [ctx]
    for v in vals:
        if isinstance(v, str) and "|" in v and "---" in v:
            return v
    return None


def _execute_code(
    csv_data: str,
    code: str,
    *,
    runner: CommandRunner | None,
    policy: ExecutionPolicy | None = None,
) -> tuple[str | None, str | None, dict[str, object]]:
    """Execute validated code only through an explicitly configured runner.

    AST validation is defense in depth, not a sandbox.  The default is
    therefore refusal.  Production callers should provide a ``ContainerRunner``;
    a ``LocalProcessRunner`` works only when its policy explicitly opts into
    trusted host execution and remains review-only at the CLI evidence ceiling.
    """
    try:
        validate_generated_table_code(code)
    except UnsafeGeneratedCode as exc:
        return None, f"unsafe_code: {exc}", {
            "executed": False,
            "isolation": "not_executed",
            "backend": "none",
        }
    if runner is None:
        return None, "execution_refused: no execution runner configured", {
            "executed": False,
            "isolation": "not_executed",
            "backend": "none",
        }
    wrapper = (
        "import io, sys\nimport pandas as pd\nimport numpy as np\n"
        f"df = pd.read_csv(io.StringIO({csv_data!r}), dtype=str).fillna('')\n"
        "df = df.apply(lambda c: c.str.strip())\n"
        "try:\n"
        + textwrap.indent(code, "    ")
        + "\nexcept Exception as e:\n    print('__ERR__:' + repr(e))\n"
    )
    with tempfile.TemporaryDirectory(prefix="benchcore-code-") as directory:
        path = Path(directory) / "compute.py"
        path.write_text(wrapper, encoding="utf-8")
        effective_policy = policy or ExecutionPolicy(
            timeout_seconds=12,
            max_output_chars=10_000,
            memory_mb=512,
            cpu_count=1.0,
            pids_limit=64,
            network_enabled=False,
            allow_local_process=False,
            allowed_environment=frozenset(),
        )
        try:
            result = runner.run(
                CommandSpec(
                    argv=(sys.executable, "-I", path.name),
                    cwd=Path(directory),
                ),
                effective_policy,
            )
        except ExecutionRefused as exc:
            return None, f"execution_refused: {exc}", {
                "executed": False,
                "isolation": "not_executed",
                "backend": "none",
            }
        except Exception as exc:  # runner/infrastructure failure is explicit
            return None, f"runner_failure: {type(exc).__name__}: {exc}", {
                "executed": False,
                "isolation": "unknown",
                "backend": type(runner).__name__,
            }
        metadata: dict[str, object] = {
            "executed": True,
            "isolation": result.isolation,
            "backend": result.backend,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "elapsed_seconds": result.elapsed_seconds,
            "network_enabled": effective_policy.network_enabled,
        }
        out = (result.stdout or "").strip()
        if result.timed_out:
            return None, "timeout", metadata
        if "__ERR__:" in out:
            return None, out.split("__ERR__:", 1)[1], metadata
        if not result.succeeded:
            return None, (result.stderr or "nonzero exit").strip()[:300], metadata
        return out, None, metadata


def _run_code(
    csv_data: str,
    code: str,
    timeout: int = 12,
    *,
    runner: CommandRunner | None = None,
    allow_unsafe_local: bool = False,
) -> tuple[str | None, str | None]:
    """Compatibility wrapper with a fail-closed default.

    ``allow_unsafe_local`` only affects an explicitly supplied local runner; it
    never selects a runner on the caller's behalf.
    """
    output, error, _ = _execute_code(
        csv_data,
        code,
        runner=runner,
        policy=ExecutionPolicy(
            timeout_seconds=timeout,
            max_output_chars=10_000,
            memory_mb=512,
            cpu_count=1.0,
            pids_limit=64,
            network_enabled=False,
            allow_local_process=allow_unsafe_local,
            allowed_environment=frozenset(),
        ),
    )
    return output, error


class CodeExecVerifier(Checker):
    """Verifies table-QA gold answers by computing them with executed code."""

    name = "code_exec_verifier"

    def __init__(
        self,
        client: LLMClient,
        confirm_threshold: float = 0.75,
        review_threshold: float = 0.45,
        *,
        runner: CommandRunner | None = None,
        policy: ExecutionPolicy | None = None,
        allow_unsafe_local: bool = False,
    ):
        self.client = client
        self.confirm_threshold = confirm_threshold
        self.review_threshold = review_threshold
        self.runner = runner
        self.policy = policy or ExecutionPolicy(
            timeout_seconds=12,
            max_output_chars=10_000,
            memory_mb=512,
            cpu_count=1.0,
            pids_limit=64,
            network_enabled=False,
            allow_local_process=allow_unsafe_local,
            allowed_environment=frozenset(),
        )
        self.allow_unsafe_local = allow_unsafe_local
        self.stats: dict[str, int] = {}

    def _bump(self, k: str) -> None:
        self.stats[k] = self.stats.get(k, 0) + 1

    def audit_eligibility(self, item, root=None) -> AuditEligibility:
        md = _table_markdown(item)
        if not md or item.gold in (None, ""):
            return AuditEligibility.not_applicable(
                "code execution requires a markdown table and declared gold"
            )
        if parse_markdown_table(md) is None:
            return AuditEligibility(
                False,
                "the table could not be parsed into a rectangular dataframe",
                "unsupported",
            )
        if self.runner is None:
            return AuditEligibility(
                False,
                "generated table code requires an explicitly configured isolated runner",
                "security_blocked",
            )
        return AuditEligibility.applicable(
            "a parseable table, gold answer, and explicit execution runner are available"
        )

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        md = _table_markdown(item)
        if not md or item.gold in (None, ""):
            return []
        parsed = parse_markdown_table(md)
        if not parsed:
            self._bump("no_table"); return []
        cols, rows = parsed
        csv_data = _to_csv(cols, rows)
        preview = _to_csv(cols, rows[:5])

        try:
            gen = self.client.chat_json(
                CODEGEN_PROMPT.format(columns=cols, preview=preview, question=item.task),
                f"Question: {item.task}",
            )
        except Exception as exc:
            self._bump("codegen_fail")
            raise AuditAbstained(
                f"table code generation failed: {type(exc).__name__}: {exc}"
            ) from exc
        code = (gen or {}).get("code", "")
        if not isinstance(code, str) or "print" not in code:
            self._bump("no_code")
            raise AuditAbstained(
                "table code generator did not return executable print-based code"
            )

        computed, err, execution = _execute_code(
            csv_data,
            code,
            runner=self.runner,
            policy=self.policy,
        )
        if computed is None:
            self._bump("exec_fail")
            details = {"execution": execution, "error": err or "unknown execution error"}
            if err and err.startswith("execution_refused:"):
                raise AuditSecurityBlocked(err, details=details)
            if err and (
                "ModuleNotFoundError" in err
                or "No module named" in err
                or "command not found" in err.casefold()
            ):
                raise AuditUnsupported(err, details=details)
            raise AuditAbstained(
                "generated computation did not produce a usable answer: "
                + (err or "unknown error"),
                details=details,
            )
        self._bump("verified")

        comp_n, gold_n = _normalize(computed), _normalize(item.gold)
        if comp_n == gold_n or comp_n in {_normalize(a) for a in (item.aliases or [])}:
            self._bump("agree"); return []  # gold corroborated by computation

        self._bump("disagree")
        return [Violation(
            item_id=item.item_id,
            artifact="oracle_ground_truth",
            mechanism="code_execution",
            defect_type="wrong_gold_answer",
            severity="review",
            confidence=0.6,
            message=(f"Executed table computation yields '{computed}' but gold is "
                     f"'{item.gold}'."),
            detection_method="code_exec_verifier",
            defect_scope="substantive",
            evidence={"computed": computed, "gold": item.gold, "code": code,
                      "columns": cols, "n_rows": len(rows),
                      "execution": execution},
            suggested_repair="Re-verify the gold against the table computation.",
            review_only=True,
        )]
