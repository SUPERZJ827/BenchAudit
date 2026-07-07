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
Return [] if the rubric checks content the task explicitly asks the agent to
infer, define, design, assign, summarize, or recommend, such as role/permission
assignments, responsibility boundaries, validation checklists, summaries, or
recommendations. Those are generated output requirements, not missing input data.

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

Use generated_content when the task itself asks the agent to infer, design,
define, assign, summarize, or recommend the missing content (for example role
permissions, responsibility boundaries, checklists, conclusions, or suggestions).
Do not call that a data gap merely because the exact generated output wording is
not present in the input files.

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

CONTRACT_SYSTEM_PROMPT = """You verify consistency between a benchmark's output
contract and its rubric/evaluator. Return only JSON."""

CONTRACT_PROMPT = """Audit whether the rubric/evaluator is consistent with the
declared output contract.

Focus only on concrete output-contract issues:
- required output files, directories, top-level output names, or top-level formats
- evaluator/rubric requiring extra output artifacts not declared by the contract
- evaluator/rubric contradicting the declared file names, output type, or format

Be conservative:
- Do not flag ordinary content requirements inside a declared output file.
- Do not flag worksheet names, chart placement, sections, rows, columns, tables,
  or layout inside an already-declared output file unless the output contract
  itself explicitly declares those internal structures.
- Do not flag rubrics that check whether source/input files are accessible; that
  is not an output-contract mismatch.
- Do not flag a rubric simply because it checks quality, correctness, or completeness.
- If the output contract is intentionally broad, use uncertain unless the conflict is concrete.

Return ONLY JSON:
{{
  "status": "consistent|contract_mismatch|uncertain",
  "issues": [
    {{
      "rubric_index": 0,
      "type": "extra_output|missing_contract|format_conflict|file_name_conflict|layout_conflict",
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

OUTPUT CONTRACT:
{output_contract}

RUBRICS / EVALUATOR:
{rubrics}
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

GENERATIVE_TASK_PATTERN = re.compile(
    r"\b(infer|define|design|assign|analy[sz]e|generate|create|prepare|compile|"
    r"summarize|recommend|propose)\b|"
    r"推断|定义|设计|分配|分析|生成|创建|编制|整理|总结|建议|提出",
    re.I,
)

ROLE_PERMISSION_PATTERN = re.compile(
    r"\b(role|roles|permission|permissions|access|responsibilit(?:y|ies)|view|edit|"
    r"export|print|delete|sharing|authorization|authorized)\b|"
    r"角色|权限|职责|责任|查看|编辑|导出|打印|删除|共享|授权",
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
        if is_generated_role_permission_requirement(task, rubric, required):
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


class RubricOutputContractConsistencyChecker(Checker):
    """Check whether rubrics/evaluators are aligned with the output contract."""

    name = "rubric_output_contract_consistency"

    def __init__(
        self,
        client: LLMClient,
        *,
        review_threshold: float = 0.45,
        rubric_chars: int = 5000,
        contract_chars: int = 2200,
    ) -> None:
        self.client = client
        self.review_threshold = review_threshold
        self.rubric_chars = rubric_chars
        self.contract_chars = contract_chars

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        rubrics = format_rubrics(item)
        if item.output_contract in (None, "", [], {}) or not rubrics:
            return []
        static_issues = static_output_contract_issues(item)
        prompt = CONTRACT_PROMPT.format(
            task=preview(item.task or "(missing task)", 1600),
            output_contract=preview(item.output_contract, self.contract_chars),
            rubrics=preview(rubrics, self.rubric_chars),
        )
        result = call_json_multi_majority(
            self.client,
            CONTRACT_SYSTEM_PROMPT,
            prompt,
            key="status",
            default="uncertain",
        )
        if result.get("majority") != "contract_mismatch" and not static_issues:
            return []
        confidence = as_float(result.get("confidence"), 0.5)
        if confidence < self.review_threshold and not static_issues:
            return []
        issues = dedupe_contract_issues([*static_issues, *normalized_contract_issues(result)])
        if not issues:
            issues = [
                {
                    "type": "contract_mismatch",
                    "detail": result.get("summary")
                    or "Rubric/evaluator appears inconsistent with the output contract.",
                    "material": True,
                }
            ]
        severity = contract_severity(result)
        material_issues = [
            issue for issue in issues if is_material_output_contract_issue(issue, item.output_contract)
        ]
        if not material_issues:
            return []
        first = material_issues[0]
        message = (
            first.get("detail")
            or result.get("summary")
            or "Rubric/evaluator appears inconsistent with the output contract."
        )
        if len(material_issues) > 1:
            message = f"{message} (+{len(material_issues) - 1} related contract issue(s))"
        return [
            _violation(
                item,
                "output_evaluator_contract_mismatch",
                min(0.9, max(self.review_threshold, confidence)),
                message,
                {
                    "output_contract": item.output_contract,
                    "rubrics": extract_rubrics(item),
                    "contract_issue": first,
                    "contract_issues": material_issues,
                    "votes": result.get("votes", []),
                    "llm_results": result.get("results", []),
                },
                severity=severity,
                review_only=True,
                method="rubric_output_contract_consistency",
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


def normalized_contract_issues(result: dict[str, Any]) -> list[dict[str, Any]]:
    issues = result.get("issues", [])
    if not isinstance(issues, list):
        return []
    out = []
    for issue in issues:
        if isinstance(issue, dict):
            out.append(issue)
        elif isinstance(issue, str):
            out.append({"type": "contract_mismatch", "detail": issue, "material": True})
    return out


BACKTICK_PATH_PATTERN = re.compile(r"`([^`]+)`")
FILE_EXT_PATTERN = re.compile(
    r"\.(?:md|txt|csv|tsv|xlsx|xls|docx|doc|pdf|pptx|ppt|json|html|htm|png|jpg|jpeg|svg|zip)$",
    re.I,
)
DIR_CUE_PATTERN = re.compile(r"\b(directory|folder)\b|目录|文件夹", re.I)
OUTPUT_CUE_PATTERN = re.compile(
    r"\b(create|generate|build|prepare|produce|save|copy|output|new|named|called|title[d]?)\b|"
    r"生成|创建|构建|保存|输出|新的|命名|名为|标题",
    re.I,
)


def contract_required_files(output_contract: Any) -> list[str]:
    if isinstance(output_contract, dict):
        required = output_contract.get("required_files") or output_contract.get("files") or []
    else:
        required = []
    if not isinstance(required, list):
        return []
    return [str(path).strip() for path in required if str(path).strip()]


def raw_input_basenames(item: BenchmarkItem) -> set[str]:
    out: set[str] = set()
    for path in item.raw.get("input_files", []) or []:
        name = Path(str(path)).name
        if "_" in name:
            name = name.split("_", 1)[1]
        out.add(name)
    return out


def static_output_contract_issues(item: BenchmarkItem) -> list[dict[str, Any]]:
    required = contract_required_files(item.output_contract)
    if not required:
        return []
    required_norm = {p.strip("/").lower() for p in required}
    required_basenames = {Path(p).name.lower() for p in required}
    task = item.task or ""
    issues: list[dict[str, Any]] = []

    for match in BACKTICK_PATH_PATTERN.finditer(task):
        artifact = match.group(1).strip()
        if not artifact:
            continue
        artifact_norm = artifact.strip("/").lower()
        basename = Path(artifact).name.lower()
        before = task[max(0, match.start() - 55): match.start()]
        window = task[max(0, match.start() - 40): match.end() + 40]
        if not OUTPUT_CUE_PATTERN.search(before):
            continue
        if re.search(r"\b(from|using|under)\s*$", before, re.I) and not re.search(r"\bsave\b", before, re.I):
            continue
        if FILE_EXT_PATTERN.search(artifact):
            if basename not in required_basenames and artifact_norm not in required_norm:
                issues.append(
                    {
                        "rubric_index": -1,
                        "type": "file_name_conflict",
                        "detail": f"Task names required output file `{artifact}`, but output contract requires {required}.",
                        "material": True,
                        "source": "static_task_contract",
                    }
                )
        elif DIR_CUE_PATTERN.search(window):
            if not any(artifact_norm in path for path in required_norm):
                issues.append(
                    {
                        "rubric_index": -1,
                        "type": "extra_output",
                        "detail": f"Task names required output directory `{artifact}`, but output contract requires {required}.",
                        "material": True,
                        "source": "static_task_contract",
                    }
                )

    input_names = {name.lower() for name in raw_input_basenames(item)}
    if input_names and required and all(Path(path).name.lower() in input_names for path in required):
        if re.search(r"\b(generate|create|build|prepare)\b.*\b(report|file|dataset|form)\b|生成|创建|构建|报告|文件|表单", task, re.I):
            issues.append(
                {
                    "rubric_index": -1,
                    "type": "file_name_conflict",
                    "detail": f"Output contract requires input file(s) {required} instead of the generated output requested by the task.",
                    "material": True,
                    "source": "static_task_contract",
                }
            )
    return dedupe_contract_issues(issues)


def dedupe_contract_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (str(issue.get("type", "")), normalize_space(str(issue.get("detail", ""))).lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(issue)
    return out


INTERNAL_OUTPUT_CONTRACT_PATTERN = re.compile(
    r"\b(sheets?|worksheets?|tabs?|sections?|charts?|plots?|tables?|rows?|"
    r"columns?|cells?|layouts?|slides?|pages?|placement|value checks?|"
    r"data preservation)\b|"
    r"工作表|图表|章节|小节|表格|行|列|单元格|布局|版式|位置|页面|幻灯片",
    re.I,
)

FILE_OR_DIRECTORY_PATTERN = re.compile(
    r"\b[\w./ -]+\.(?:md|txt|csv|tsv|xlsx|xls|docx|doc|pdf|pptx|ppt|json|"
    r"html|htm|png|jpg|jpeg|svg|zip)\b|"
    r"\bdirector(?:y|ies)\b|\bfolders?\b|目录|文件夹",
    re.I,
)

SOURCE_FILE_ACCESS_PATTERN = re.compile(
    r"\b(source|input)\s+files?\b|"
    r"\b(source|input)\s+files?\b.*\b(located|accessible|available|present)\b|"
    r"\b(located|accessible|available|present)\b.*\b(source|input)\s+files?\b|"
    r"源文件|输入文件",
    re.I,
)


def contract_declares_internal_structure(output_contract: Any) -> bool:
    text = normalize_space(json.dumps(output_contract, ensure_ascii=False, sort_keys=True))
    return bool(INTERNAL_OUTPUT_CONTRACT_PATTERN.search(text))


def is_material_output_contract_issue(issue: dict[str, Any], output_contract: Any) -> bool:
    if issue.get("material") is False:
        return False
    kind = str(issue.get("type", "")).strip()
    detail = normalize_space(str(issue.get("detail", "")))
    internal_contract = contract_declares_internal_structure(output_contract)
    if issue.get("source") != "static_task_contract" and SOURCE_FILE_ACCESS_PATTERN.search(detail):
        return False
    if not internal_contract and INTERNAL_OUTPUT_CONTRACT_PATTERN.search(detail):
        return False
    if kind == "extra_output" and not FILE_OR_DIRECTORY_PATTERN.search(detail):
        return False
    return True


def contract_severity(result: dict[str, Any]) -> str:
    severity = str(result.get("severity", "medium")).lower()
    if severity == "high":
        return "major"
    return "review"


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


def is_generated_role_permission_requirement(
    task: str,
    rubric: str,
    required: list[str],
) -> bool:
    """Role/permission requirements are often output the agent must infer.

    Workspace-style tasks commonly ask the agent to infer responsibilities and
    access boundaries from business needs. In that case exact role/permission
    terms are generated output content, not source data that must literally
    exist in the input files.
    """
    task_text = task or ""
    joined = " ".join([rubric, *required])
    return bool(GENERATIVE_TASK_PATTERN.search(task_text) and ROLE_PERMISSION_PATTERN.search(joined))


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
