"""B2 value-recompute checker (executes LLM-generated code).

For each rubric that ASSERTS a substantive numeric value, an LLM writes pandas
code that RE-COMPUTES that quantity from the real tabular input files; we execute
the code and check whether every asserted number is reproduced. This catches
wrong oracle values and values whose source data is absent, independently of
layout or wording.

SECURITY: this checker runs code the LLM generates, in a subprocess with no
sandbox. It is opt-in (`--value-recompute-audit`) and must only be pointed at
trusted benchmark data.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from .artifact_consistency import (
    context_pairs,
    extract_rubrics,
    is_structure_rubric,
    resolve_path,
)
from .checkers import Checker, _violation
from .file_reader import read_file
from .llm_client import LLMClient
from .schema import BenchmarkItem, Violation

REPO_ROOT = str(Path(__file__).resolve().parents[1])

SYSTEM_PROMPT = """You recompute quantities from data files to verify a benchmark
rubric. You do not trust the rubric's numbers; you compute them independently.
Return only JSON."""

USER_PROMPT = """Write Python (pandas as pd) that RE-COMPUTES, from the input files,
the quantity the rubric asserts, and prints it as `label=value`.

Reading inputs (use the absolute paths given below; files may be hash-named with no
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

INPUT FILES (absolute paths + preview):
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
        rhs = line.rsplit("=", 1)[-1] if "=" in line else line
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
    if got and all(g == 0 for g in got) and any(e != 0 for e in expected):
        return True
    return False


_PRELUDE = (
    "import sys\n"
    f"sys.path.insert(0, {REPO_ROOT!r})\n"
    "import pandas as pd, numpy as np, warnings\n"
    "warnings.filterwarnings('ignore')\n"
    # read_file handles xlsx/docx/pptx/pdf/text, so generated code can pull numbers
    # from non-tabular inputs, not just the csv/xlsx pandas reads natively.
    "from benchcore.file_reader import read_file\n"
)


def run_code(code: str, timeout: int = 15) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(_PRELUDE + code)
        p = f.name
    try:
        r = subprocess.run([sys.executable, p], capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip() or (r.stderr or "")[-200:]
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    finally:
        Path(p).unlink(missing_ok=True)


def input_file_paths(item: BenchmarkItem, root: Path | None) -> list[Path]:
    """Resolved, existing input files. Tabular ones the recompute reads with pandas;
    the rest it reads via read_file, so the data a rubric needs is not starved just
    because it lives in a non-tabular input."""
    paths: list[Path] = []
    seen: set[str] = set()
    for _label, value in context_pairs(item):
        for entry in value if isinstance(value, list) else [value]:
            if not isinstance(entry, str):
                continue
            path = resolve_path(entry, root)
            if path is None or not path.exists():
                continue
            resolved = path.resolve()
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            paths.append(resolved)
    return paths


def inputs_preview(paths: list[Path], per_file_chars: int) -> str:
    # read_file gives the LLM a content preview so it can tell tabular from text even
    # when files are hash-named; the generated code re-reads the real file for the compute.
    return "\n\n".join(f"路径: {path}\n{read_file(path, per_file_chars)}" for path in paths)


class ValueRecomputeChecker(Checker):
    """Re-compute numeric rubric assertions from tabular inputs (executes LLM code)."""

    name = "value_recompute"

    def __init__(
        self,
        client: LLMClient,
        *,
        per_file_chars: int = 1200,
        max_inputs_chars: int = 8000,
        timeout: int = 15,
        confidence: float = 0.6,
    ) -> None:
        self.client = client
        self.per_file_chars = per_file_chars
        self.max_inputs_chars = max_inputs_chars
        self.timeout = timeout
        self.confidence = confidence

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        paths = input_file_paths(item, root)
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
            yield from self._check_rubric(item, index, rubric, inputs)

    def _check_rubric(
        self,
        item: BenchmarkItem,
        index: int,
        rubric: str,
        inputs: str,
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
        computed = run_code(code, self.timeout) if "print" in code else ""
        # This checker's only reliable signal is a concrete value MISMATCH. A recompute that
        # is un-runnable (empty/error/timeout) or reports DATA_NOT_AVAILABLE is an inconclusive
        # non-result -- often because the needed data lives in a non-tabular input the recompute
        # never saw -- so we stay silent. Data-gap detection is owned by GroundedRubricConsistencyChecker,
        # which distinguishes generated content from a true gap; emitting it here would only
        # duplicate and over-flag it.
        expected = rubric_values(rubric)
        if (
            not computed
            or "DATA_NOT_AVAILABLE" in computed
            or any(m in computed for m in ("Error", "Traceback", "TIMEOUT"))
            or is_uninformative(computed, expected)
        ):
            return
        missing = reproduced(expected, computed)
        if missing:
            yield _violation(
                item,
                "wrong_gold_answer",
                self.confidence,
                "Rubric's asserted value(s) not reproduced by independent recompute from inputs.",
                {
                    "rubric_index": index,
                    "rubric": rubric,
                    "expected_values": expected,
                    "missing_values": missing,
                    "computed_output": computed[:200],
                    "code": code,
                },
                severity="review",
                review_only=True,
                method="value_recompute",
            )
