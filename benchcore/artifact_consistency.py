from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .checkers import Checker, _violation
from .file_reader import read_file
from .llm_client import LLMClient
from .schema import BenchmarkItem, Violation


SYSTEM_PROMPT = """You are a cross-artifact consistency auditor for benchmark quality.
You do not solve the task. You compare whether the provided benchmark artifacts
are mutually aligned and whether the evaluator/rubric/reference can be grounded
in the task and available context.

Return only JSON."""

USER_PROMPT = """Audit this benchmark item across artifacts.

Check:
1. SOLVABILITY / DATA GAP: can the task and rubric/evaluator be completed from
   the provided context? If a required source field/table/file/category is absent,
   report data_gap.
2. TASK AMBIGUITY: does the task omit answer-changing scope, convention, time,
   unit, output format, or source constraints?
3. TASK <-> RUBRIC/EVALUATOR CONSISTENCY: does the rubric/evaluator check
   something the task never asked for, or omit something central to the task?
4. TASK <-> REFERENCE CONSISTENCY: does the reference/gold solution address a
   different question, scope, file, behavior, or output contract?

Be conservative:
- Do not flag a rubric merely because it states an objective expected value.
- Do not flag preview truncation as a dataset defect.
- If evidence is weak or depends on professional judgment, use uncertain.
- Prefer concrete artifact-level evidence over broad impressions.

Return ONLY JSON:
{{
  "status": "consistent|data_gap|task_ambiguity|task_rubric_mismatch|task_context_mismatch|reference_mismatch|uncertain",
  "missing_data": ["required data/source absent from provided context"],
  "task_ambiguities": ["answer-changing underspecification"],
  "consistency_issues": [
    {{
      "type": "task_rubric|task_context|rubric_context|reference_task|evaluator_task|task_self",
      "detail": "specific mismatch",
      "material": true
    }}
  ],
  "severity": "high|medium|low|none",
  "confidence": 0.0,
  "summary": "one sentence"
}}

TASK:
{task}

CONTEXT / INPUT ARTIFACTS:
{context}

RUBRICS / EVALUATOR:
{rubrics}

REFERENCE / GOLD / SOLUTION:
{reference}

OUTPUT CONTRACT:
{output_contract}
"""

REQUIRED_DATA_SYSTEM_PROMPT = """You extract source-data requirements from benchmark rubrics.
Return only JSON."""

REQUIRED_DATA_PROMPT = """Name the core SOURCE DATA dimensions, categories, columns,
or fields this rubric needs to be present in the input/context artifacts to be
verifiable. Use short terms in the same language as the rubric.

Do not include generic words such as count/total/number/data/name/status/file.
Return [] if the rubric checks output formatting, filename, sheet name,
transcription accuracy, or generated recommendation content rather than a source
data dimension.

Return ONLY JSON: {{"required":["..."]}}

RUBRIC:
{rubric}
"""

DATA_GROUNDING_SYSTEM_PROMPT = """You verify whether a rubric's required source data
is present or derivable from the provided benchmark context. Return only JSON."""

DATA_GROUNDING_PROMPT = """A literal search did not find these required source-data terms:
{missing}

Decide whether this is a real data gap.

Verdicts:
- present_or_derivable: the data exists under different wording, in filenames, in
  another field, or is computable from provided data.
- generated_content: the rubric checks content the agent should produce from
  judgment or writing, so absence from input data is expected.
- not_in_inputs: a source field/category/entity required by the rubric is absent
  from every provided artifact and cannot be derived.

Return ONLY JSON:
{{"verdict":"present_or_derivable|generated_content|not_in_inputs","reason":"one sentence","confidence":0.0}}

TASK:
{task}

CONTEXT / INPUT ARTIFACTS:
{context}

RUBRIC:
{rubric}
"""

STRUCTURE_SYSTEM_PROMPT = """You verify whether an output-structure rubric is
grounded in the task. Return only JSON."""

STRUCTURE_PROMPT = """This rubric checks output structure, such as filename, sheet
name, format, section name, directory, or layout. Judge it against the task.

Verdicts:
- none: the task explicitly asks for this structure, or it is a harmless
  operationalization.
- over_constrained: the task never asks for this exact structure, so a correct
  answer could fail only because of the rubric's extra requirement.
- task_mismatch: the structure contradicts the task's scope or requested output.

Return ONLY JSON:
{{"defect":"none|over_constrained|task_mismatch","evidence":"short quote/reason","confidence":0.0}}

TASK:
{task}

RUBRIC:
{rubric}
"""

STRUCTURE_RUBRIC_PATTERN = re.compile(
    r"工作表|sheet|命名|文件名|格式|结构|包含名为|目录|folder|filename|file name|"
    r"worksheet|tab name|section|layout|format",
    re.I,
)

DATA_BEARING_PATTERN = re.compile(
    r"\d|等级|三级|二级|一级|字段|分布|总数|数量|金额|比例|占比|count|total|sum|"
    r"number|amount|rate|ratio|percentage|column|field|category|breakdown|"
    r"grade|level|tier|class|tertiary|secondary|primary",
    re.I,
)

GENERIC_GROUNDING_SUFFIXES = (
    "数量",
    "总数",
    "家数",
    "名称",
    "情况",
    "明细",
    "信息",
    "统计",
    "分布",
    "数据",
    "数",
    "表",
    "值",
    "count",
    "total",
    "number",
    "data",
    "field",
    "column",
)


class CrossArtifactConsistencyChecker(Checker):
    """LLM-assisted consistency audit over task, context, reference, and evaluator."""

    name = "cross_artifact_consistency"

    def __init__(
        self,
        client: LLMClient,
        *,
        review_threshold: float = 0.45,
        context_chars: int = 9000,
        rubric_chars: int = 3500,
        reference_chars: int = 2500,
    ) -> None:
        self.client = client
        self.review_threshold = review_threshold
        self.context_chars = context_chars
        self.rubric_chars = rubric_chars
        self.reference_chars = reference_chars

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if not has_enough_artifacts(item):
            return []
        prompt = USER_PROMPT.format(
            task=preview(item.task or "(missing task)", 1800),
            context=build_context_preview(item, root, self.context_chars),
            rubrics=preview(format_rubrics(item), self.rubric_chars) or "(no rubric/evaluator)",
            reference=preview(format_reference(item), self.reference_chars) or "(no reference)",
            output_contract=preview(item.output_contract, 1200) or "(no output contract)",
        )
        try:
            result = self.client.chat_json(SYSTEM_PROMPT, prompt)
        except Exception as exc:  # noqa: BLE001 - preserve row-level failure
            yield _violation(
                item,
                "llm_audit_failure",
                0.25,
                "Cross-artifact consistency audit failed.",
                {"error": f"{type(exc).__name__}: {exc}"},
                severity="review",
                review_only=True,
                method="llm_cross_artifact_consistency",
                scope="operational",
            )
            return

        for violation in consistency_violations(item, result, self.review_threshold):
            yield violation


class GroundedRubricConsistencyChecker(Checker):
    """Ground rubrics against task text and provided context artifacts.

    This migrates the stable parts of the older Workspace-Bench B1/B5 prototype:
    B1-style data availability checks and B5-style output-structure checks. It
    deliberately emits review signals by default; family-specific confirmation
    gates can later upgrade high-consensus results.
    """

    name = "grounded_rubric_consistency"

    def __init__(
        self,
        client: LLMClient,
        *,
        review_threshold: float = 0.45,
        context_chars: int = 12000,
    ) -> None:
        self.client = client
        self.review_threshold = review_threshold
        self.context_chars = context_chars

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        rubrics = extract_rubrics(item)
        if not rubrics:
            return []
        context_text = full_context_text(item, root, self.context_chars)
        if not context_text.strip():
            return []
        task = item.task or ""
        for index, rubric in enumerate(rubrics):
            for violation in self._check_structure_rubric(item, index, rubric, task):
                yield violation
            for violation in self._check_data_grounding(
                item,
                index,
                rubric,
                task,
                context_text,
            ):
                yield violation

    def _check_structure_rubric(
        self,
        item: BenchmarkItem,
        index: int,
        rubric: str,
        task: str,
    ) -> Iterable[Violation]:
        if not is_structure_rubric(rubric) or len(normalize_space(task)) < 8:
            return []
        prompt = STRUCTURE_PROMPT.format(
            task=preview(task, 1400),
            rubric=preview(rubric, 1000),
        )
        result = call_json_multi_majority(
            self.client,
            STRUCTURE_SYSTEM_PROMPT,
            prompt,
            key="defect",
            default="none",
        )
        defect = result.get("majority")
        if defect not in {"over_constrained", "task_mismatch"}:
            return []
        confidence = max(self.review_threshold, as_float(result.get("confidence"), 0.65))
        return [
            _violation(
                item,
                "task_rubric_mismatch",
                min(0.9, confidence),
                result.get("evidence")
                or "Rubric imposes output structure not clearly supported by the task.",
                {
                    "rubric_index": index,
                    "rubric": rubric,
                    "grounding_check": "output_structure_vs_task",
                    "defect": defect,
                    "votes": result.get("votes", []),
                    "llm_results": result.get("results", []),
                },
                severity="review",
                review_only=True,
                method="grounded_rubric_consistency",
            )
        ]

    def _check_data_grounding(
        self,
        item: BenchmarkItem,
        index: int,
        rubric: str,
        task: str,
        context_text: str,
    ) -> Iterable[Violation]:
        if is_structure_rubric(rubric) or not looks_data_bearing(rubric):
            return []
        extract_prompt = REQUIRED_DATA_PROMPT.format(rubric=preview(rubric, 1200))
        try:
            required_raw = self.client.chat_json(REQUIRED_DATA_SYSTEM_PROMPT, extract_prompt)
        except Exception as exc:  # noqa: BLE001 - preserve row-level failure
            return [
                _violation(
                    item,
                    "llm_audit_failure",
                    0.25,
                    "Grounded rubric data extraction failed.",
                    {
                        "rubric_index": index,
                        "rubric": rubric,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    severity="review",
                    review_only=True,
                    method="grounded_rubric_consistency",
                    scope="operational",
                )
            ]
        required = [
            str(term).strip()
            for term in required_raw.get("required", [])
            if isinstance(term, (str, int, float)) and len(str(term).strip()) >= 2
        ]
        if not required:
            return []
        context_norm = normalize_for_presence(context_text)
        missing = [
            term
            for term in required
            if normalize_for_presence(core_grounding_term(term)) not in context_norm
        ]
        if not missing:
            return []

        verify_prompt = DATA_GROUNDING_PROMPT.format(
            missing=", ".join(missing),
            task=preview(task or "(missing task)", 1200),
            context=preview(context_text, self.context_chars),
            rubric=preview(rubric, 1200),
        )
        result = call_json_multi_majority(
            self.client,
            DATA_GROUNDING_SYSTEM_PROMPT,
            verify_prompt,
            key="verdict",
            default="present_or_derivable",
        )
        if result.get("majority") != "not_in_inputs":
            return []
        confidence = max(self.review_threshold, as_float(result.get("confidence"), 0.7))
        return [
            _violation(
                item,
                "artifact_data_gap",
                min(0.9, confidence),
                result.get("reason")
                or "Rubric appears to require source data absent from the provided context.",
                {
                    "rubric_index": index,
                    "rubric": rubric,
                    "grounding_check": "required_data_in_context",
                    "required_terms": required,
                    "literal_missing_terms": missing,
                    "votes": result.get("votes", []),
                    "llm_results": result.get("results", []),
                },
                severity="major",
                review_only=True,
                method="grounded_rubric_consistency",
            )
        ]


def has_enough_artifacts(item: BenchmarkItem) -> bool:
    artifact_count = 0
    if item.task:
        artifact_count += 1
    if item.context or common_context_values(item.raw):
        artifact_count += 1
    if format_rubrics(item):
        artifact_count += 1
    if item.gold not in (None, "") or item.raw.get("patch") or item.raw.get("reference_solution"):
        artifact_count += 1
    return artifact_count >= 2


def consistency_violations(
    item: BenchmarkItem,
    result: dict[str, Any],
    review_threshold: float = 0.45,
) -> list[Violation]:
    confidence = as_float(result.get("confidence"), default=0.5)
    if confidence < review_threshold:
        return []
    status = str(result.get("status", "uncertain")).strip()
    severity = severity_from_result(result)
    evidence = {
        "llm_result": result,
        "status": status,
        "missing_data": result.get("missing_data", []),
        "task_ambiguities": result.get("task_ambiguities", []),
        "consistency_issues": result.get("consistency_issues", []),
    }
    common = {
        "confidence": min(0.95, max(review_threshold, confidence)),
        "message": result.get("summary") or "Cross-artifact consistency issue detected.",
        "evidence": evidence,
        "severity": severity,
        "review_only": True,
        "method": "llm_cross_artifact_consistency",
    }

    violations: list[Violation] = []
    if status == "data_gap" or result.get("missing_data"):
        violations.append(
            _violation(
                item,
                "artifact_data_gap",
                common["confidence"],
                common["message"],
                common["evidence"],
                severity=common["severity"],
                review_only=True,
                method=common["method"],
            )
        )
    if status == "task_ambiguity" or result.get("task_ambiguities"):
        violations.append(
            _violation(
                item,
                "ambiguous_goal",
                common["confidence"],
                common["message"],
                common["evidence"],
                severity="review",
                review_only=True,
                method=common["method"],
            )
        )

    for issue in normalized_issues(result):
        defect_type = issue_defect_type(issue)
        if not defect_type:
            continue
        issue_evidence = {
            **evidence,
            "issue": issue,
        }
        violations.append(
            _violation(
                item,
                defect_type,
                common["confidence"],
                issue.get("detail") or common["message"],
                issue_evidence,
                severity=common["severity"],
                review_only=True,
                method=common["method"],
            )
        )

    # Deduplicate when status and issue list point to the same finding.
    out: list[Violation] = []
    seen: set[tuple[str, str]] = set()
    for violation in violations:
        key = (violation.defect_type, violation.message)
        if key in seen:
            continue
        seen.add(key)
        out.append(violation)
    return out


def normalized_issues(result: dict[str, Any]) -> list[dict[str, Any]]:
    issues = result.get("consistency_issues", [])
    if not isinstance(issues, list):
        return []
    out = []
    for issue in issues:
        if isinstance(issue, dict):
            out.append(issue)
        elif isinstance(issue, str):
            out.append({"type": "task_self", "detail": issue, "material": True})
    return out


def issue_defect_type(issue: dict[str, Any]) -> str | None:
    kind = str(issue.get("type", "")).strip()
    if kind in {"task_rubric", "evaluator_task"}:
        return "task_rubric_mismatch"
    if kind in {"task_context", "rubric_context"}:
        return "artifact_data_gap"
    if kind == "reference_task":
        return "reference_task_mismatch"
    if kind == "task_self":
        return "ambiguous_goal"
    return None


def severity_from_result(result: dict[str, Any]) -> str:
    severity = str(result.get("severity", "medium")).lower()
    if severity == "high":
        return "major"
    if severity == "medium":
        return "review"
    return "review"


def build_context_preview(item: BenchmarkItem, root: Path | None, max_chars: int) -> str:
    chunks: list[str] = []
    for label, value in context_pairs(item):
        chunks.extend(render_context_value(label, value, root))
    if not chunks:
        return "(no context artifacts)"
    return preview("\n\n".join(chunks), max_chars)


def context_pairs(item: BenchmarkItem) -> list[tuple[str, Any]]:
    pairs: list[tuple[str, Any]] = []
    for key, value in item.context.items():
        if value not in (None, "", [], {}):
            pairs.append((key, value))
    for key, value in common_context_values(item.raw):
        if key not in item.context and value not in (None, "", [], {}):
            pairs.append((key, value))
    return pairs


def common_context_values(raw: dict[str, Any]) -> list[tuple[str, Any]]:
    keys = (
        "inputs",
        "input_files",
        "attachments",
        "files",
        "data_files",
        "data_manifest",
        "context",
        "passage",
        "table",
        "tables",
        "documents",
    )
    return [(key, raw.get(key)) for key in keys if key in raw]


def render_context_value(label: str, value: Any, root: Path | None) -> list[str]:
    values = value if isinstance(value, list) else [value]
    chunks: list[str] = []
    inventory = file_inventory(values, root)
    if inventory:
        chunks.append(f"[{label} inventory]\n{inventory}")
    for index, entry in enumerate(values, start=1):
        if isinstance(entry, dict):
            chunks.append(f"[{label}#{index}]\n{preview(entry, 1600)}")
            continue
        if isinstance(entry, str):
            path = resolve_path(entry, root)
            if path is not None and path.exists():
                chunks.append(
                    f"[{label}#{index}: {entry}]\n"
                    f"{file_metadata(path)}\n"
                    f"{read_file(path, 1600)}"
                )
            else:
                chunks.append(f"[{label}#{index}]\n{preview(entry, 1600)}")
            continue
        chunks.append(f"[{label}#{index}]\n{preview(entry, 1600)}")
    return chunks


def resolve_path(value: str, root: Path | None) -> Path | None:
    if "\n" in value or len(value) > 260:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    if root is not None:
        return root / path
    return path


def full_context_text(item: BenchmarkItem, root: Path | None, max_chars: int) -> str:
    chunks: list[str] = []
    per_file_chars = max(1600, max_chars // max(len(context_pairs(item)) or 1, 1))
    for label, value in context_pairs(item):
        values = value if isinstance(value, list) else [value]
        inventory = file_inventory(values, root)
        if inventory:
            chunks.append(f"[{label} inventory]\n{inventory}")
        for index, entry in enumerate(values, start=1):
            if isinstance(entry, str):
                path = resolve_path(entry, root)
                if path is not None and path.exists():
                    chunks.append(
                        f"[{label}#{index}: {entry}]\n"
                        f"{file_metadata(path)}\n"
                        f"{read_file(path, per_file_chars)}"
                    )
                    continue
            chunks.append(f"[{label}#{index}]\n{preview(entry, per_file_chars)}")
    return preview("\n\n".join(chunks), max_chars)


def file_inventory(values: list[Any], root: Path | None, max_entries: int = 300) -> str:
    lines: list[str] = []
    for entry in values[:max_entries]:
        if not isinstance(entry, str):
            continue
        path = resolve_path(entry, root)
        if path is None or not path.exists():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        suffix = f" size_bytes={size}" if size is not None else ""
        lines.append(f"- source={entry} name={path.name}{suffix}")
    if len(values) > max_entries:
        lines.append(f"... {len(values) - max_entries} more files omitted from inventory")
    return "\n".join(lines)


def file_metadata(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return f"FILE_META name={path.name}"
    return f"FILE_META name={path.name} size_bytes={stat.st_size}"


def format_rubrics(item: BenchmarkItem) -> str:
    rubrics = extract_rubrics(item)
    parts: list[str] = []
    if rubrics:
        parts.append("\n".join(f"- {rubric}" for rubric in rubrics))
    if item.evaluator not in (None, "", [], {}):
        parts.append("EVALUATOR:\n" + preview(item.evaluator, 1800))
    return "\n\n".join(parts)


def extract_rubrics(item: BenchmarkItem) -> list[str]:
    raw = item.raw or {}
    for key in ("rubrics", "rubric", "criteria", "grading_rubric"):
        if key in raw:
            parsed = parse_maybe_json(raw[key])
            if isinstance(parsed, list):
                return [str(x) for x in parsed if str(x).strip()]
            if isinstance(parsed, dict):
                return [json.dumps(parsed, ensure_ascii=False)]
            if isinstance(parsed, str) and parsed.strip():
                return [parsed]
    if isinstance(item.evaluator, dict):
        for key in ("rubrics", "rubric", "criteria"):
            if key in item.evaluator:
                parsed = parse_maybe_json(item.evaluator[key])
                if isinstance(parsed, list):
                    return [str(x) for x in parsed if str(x).strip()]
                if parsed:
                    return [str(parsed)]
    if isinstance(item.evaluator, list):
        return [str(x) for x in item.evaluator if str(x).strip()]
    return []


def parse_maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    if stripped.startswith(("[", "{")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value


def format_reference(item: BenchmarkItem) -> str:
    parts: list[str] = []
    if item.gold not in (None, ""):
        parts.append("GOLD / REFERENCE:\n" + preview(item.gold, 1800))
    raw = item.raw or {}
    for key in ("patch", "reference_solution", "solution", "gold_patch", "test_patch"):
        if key in raw and raw[key] not in (None, ""):
            parts.append(f"{key}:\n{preview(raw[key], 1200)}")
    return "\n\n".join(parts)


def preview(value: Any, max_chars: int) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            text = str(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_for_presence(value: Any) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").lower(), flags=re.UNICODE)


def is_structure_rubric(rubric: str) -> bool:
    return bool(STRUCTURE_RUBRIC_PATTERN.search(rubric or ""))


def looks_data_bearing(rubric: str) -> bool:
    return bool(DATA_BEARING_PATTERN.search(rubric or ""))


def core_grounding_term(term: str) -> str:
    text = normalize_space(term)
    lowered = text.lower()
    for suffix in GENERIC_GROUNDING_SUFFIXES:
        if lowered.endswith(suffix.lower()) and len(text) > len(suffix) + 1:
            return text[: -len(suffix)].strip()
    return text


def call_json_multi_majority(
    client: LLMClient,
    system: str,
    user: str,
    *,
    key: str,
    default: str,
) -> dict[str, Any]:
    try:
        if hasattr(client, "chat_json_multi"):
            results = client.chat_json_multi(system, user)
        else:
            results = [client.chat_json(system, user)]
    except Exception as exc:  # noqa: BLE001 - convert to row-local uncertain result
        return {
            "majority": default,
            "votes": [],
            "results": [{"error": f"{type(exc).__name__}: {exc}"}],
            "confidence": 0.0,
        }
    if not isinstance(results, list):
        results = [results]
    dict_results = [result for result in results if isinstance(result, dict)]
    votes = [
        str(result.get(key)).strip()
        for result in dict_results
        if result.get(key) not in (None, "")
    ]
    majority = Counter(votes).most_common(1)[0][0] if votes else default
    exemplar = next(
        (result for result in dict_results if str(result.get(key)).strip() == majority),
        dict_results[0] if dict_results else {},
    )
    merged = dict(exemplar)
    merged["majority"] = majority
    merged["votes"] = votes
    merged["results"] = dict_results
    return merged
