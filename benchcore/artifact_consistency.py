from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .checkers import Checker, _violation
from .file_reader import read_file, search_file
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
verifiable. Use short natural-language phrases in the same language as the
rubric or task.

Prefer phrases that might actually appear in source files. Do not invent
normalized labels, snake_case identifiers, or artificial taxonomy names.

Do not include generic words such as count/total/number/data/name/status/file.
Return [] if the rubric checks output formatting, filename, sheet name,
transcription accuracy, or generated recommendation content rather than a source
data dimension.
Return [] if the rubric checks content the task explicitly asks the agent to
infer, define, design, assign, summarize, or recommend, such as role/permission
assignments, responsibility boundaries, validation checklists, summaries, or
recommendations. Those are generated output requirements, not missing input data.

Return ONLY JSON: {{"required":["..."]}}

TASK:
{task}

RUBRIC:
{rubric}
"""

DATA_GROUNDING_SYSTEM_PROMPT = """You verify whether a rubric's required source data
is present or derivable from the provided benchmark context. Return only JSON."""

DATA_GROUNDING_PROMPT = """A lexical search did not find exact matches for these
required source-data terms:
{missing}

Decide whether this is a real data gap. The lexical miss above is weak evidence
only. Before choosing not_in_inputs, actively check semantic equivalence:
- synonyms, paraphrases, abbreviations, morphology, and translation variants
  (e.g. aid vs assistance, dismissed vs dissolved);
- facts listed as an enumeration rather than restated as a count or summary;
- wording split across nearby sentences, filenames, headings, tables, or fields;
- values computable from provided records.

Verdicts:
- present_or_derivable: the data exists under different wording, in filenames, in
  another field, as an enumerated list, or is computable from provided data.
- generated_content: the rubric checks content the agent should produce from
  judgment or writing, so absence from input data is expected.
- unverified_due_to_read_limit: the relevant files are truncated, unreadable,
  encrypted, image-only, or otherwise not sufficiently searchable, so absence
  cannot be concluded from the visible preview.
- not_in_inputs: a source field/category/entity required by the rubric is absent
  from every provided artifact and cannot be derived after considering the
  targeted full-file search snippets.

Use generated_content when the task itself asks the agent to infer, design,
define, assign, summarize, or recommend the missing content (for example role
permissions, responsibility boundaries, checklists, conclusions, or suggestions).
Do not call that a data gap merely because the exact generated output wording is
not present in the input files.
Do not call not_in_inputs solely because the rubric uses a different word than
the source files. If the concept is semantically present, use present_or_derivable.

Return ONLY JSON:
{{"verdict":"present_or_derivable|generated_content|unverified_due_to_read_limit|not_in_inputs","reason":"one sentence","confidence":0.0}}

TASK:
{task}

CONTEXT / INPUT ARTIFACTS:
{context}

RUBRIC:
{rubric}
"""

STRUCTURE_SYSTEM_PROMPT = """You are the semantic confirmation stage for
candidate rubric/task mismatch findings. Return only JSON."""

STRICTNESS_SYSTEM_PROMPT = """You are the semantic confirmation stage for
candidate over-strict rubric findings. Return only JSON."""

STRICTNESS_PROMPT = """A cheap code filter selected this rubric as a POSSIBLE
over-strict or unsupported evaluator requirement.

Your job is semantic confirmation, not candidate generation. Most candidates
should be rejected.

Benchmark rubrics are allowed to operationalize a broad task into concrete,
objective checks. Do NOT flag:
- objective values, counts, totals, percentages, categories, or facts that are
  directly present in or computable from the inputs;
- specific names, labels, recommendations, categories, file contents, counts,
  or structural details when they are explicitly present in the input artifacts
  or can be inferred from them;
- normal checks that a generated report/manual/slide deck includes analysis,
  summaries, conclusions, tables, or evidence-backed content requested by the
  task;
- file type or output artifact requirements explicitly requested by the task or
  output contract.

Flag a problem only when the rubric imposes an evaluator requirement that a
reasonable correct output could fail despite satisfying the task, such as:
- unsupported_requirement: the rubric requires a specific conclusion, label,
  role/permission assignment, classification, recommendation, or content detail
  that is not given by the task and not derivable from the input data.
- multi_valid_outputs: the task admits many valid designs/analyses/plans, but
  the rubric hard-codes one arbitrary answer, wording, section, exact list, page,
  slide, order, chart type, or placement.
- over_constrained: the rubric pins an exact structure, title, page/slide number,
  worksheet name, format, or layout not required by the task/contract/context.
- task_mismatch: the rubric contradicts the task's requested scope or output.

Use none when the requirement is grounded in task text, output contract, or
provided context, or when the issue is merely a broad/subjective quality check.

Critical rule: "the task did not explicitly say this exact detail" is NOT enough
to flag over-strictness. If the detail is supported by input files, file names,
tables, headings, policies, meeting notes, screenshots, or can be computed or
reasonably inferred from them, return none. Only flag when the requirement lacks
support in BOTH the task/contract and the input/context, or when many equally
valid outputs would satisfy the task but the rubric accepts only one arbitrary
choice.

Examples that should usually be flagged if not grounded:
- the task asks for a PPT/report, but the rubric requires content on page/slide X;
- the task asks for a chart, but the rubric requires a horizontal bar chart;
- the task asks for recommendations, but the rubric accepts only one specific
  recommendation or exactly N recommendations;
- the task asks for a table/manual/report, but the rubric requires exact section
  titles, worksheet names, ordering, or wording.

Return ONLY JSON:
{{
  "defect":"none|unsupported_requirement|multi_valid_outputs|over_constrained|task_mismatch",
  "strictness_category":"none|unsupported_requirement|multi_valid_outputs|arbitrary_structure|task_mismatch",
  "evidence":"short quote/reason",
  "confidence":0.0,
  "todo":"short human-review instruction if defect is not none, otherwise empty"
}}

TASK:
{task}

OUTPUT CONTRACT:
{output_contract}

CONTEXT / INPUT ARTIFACTS:
{context}

RUBRIC:
{rubric}
"""

STRUCTURE_PROMPT = """A cheap code filter selected this rubric as a POSSIBLE
rubric/task mismatch because it mentions structure, naming, format, a title, a
directory, a file, a worksheet, or layout.

Your job is semantic confirmation, not candidate generation. Most candidates
should be rejected.

Important: in benchmark rubrics, it is normal for the rubric to operationalize
a broad task into concrete checks. Do NOT treat the following as over-constraint:
- checking whether a generated report contains an analysis, summary, conclusion,
  classification, table value, count, percentage, or extracted fact that can be
  derived from the inputs;
- checking whether the answer includes specific evidence-backed content, even
  if the task phrased the request broadly.
- checking a generated report's substantive section/content coverage when the
  task asks for a report, analysis, summary, manual, guide, or plan.

Verdicts:
- none: the task explicitly asks for this structure, or it is a harmless
  operationalization / normal oracle check.
- over_constrained: the task never asks for this exact structure, so a correct
  answer could fail only because of the rubric's extra arbitrary structure,
  naming, formatting, exact-title, or wording requirement.
- task_mismatch: the structure contradicts the task's scope or requested output.

Use over_constrained only when BOTH are true:
1. the requirement is arbitrary and not grounded in the task, output contract, or
   provided context; and
2. a reasonable correct output could be incorrectly rejected solely because of
   that extra structure/format/name/title requirement.

Return ONLY JSON:
{{"defect":"none|over_constrained|task_mismatch","evidence":"short quote/reason","confidence":0.0}}

TASK:
{task}

CONTEXT / INPUT ARTIFACTS:
{context}

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
    r"工作表|命名|文件名|格式|结构|包含名为|目录|标题|"
    r"\b(?:folder|filename|file name|worksheet|tab name|sheet\s+name|"
    r"section\s+(?:title|name)|titled|title|layout|format)\b",
    re.I,
)

CONTENT_ORACLE_RUBRIC_PATTERN = re.compile(
    r"\b("
    r"accurately|correctly|calculate|computed?|extract(?:ed)?|identify|list|mention|"
    r"state|show|include|contain|summari[sz]e|analy[sz]e|point out|classif(?:y|ication)|"
    r"count|total|rate|ratio|percentage|amount|value|metric|data|fact|conclusion|"
    r"analysis|summary|report section|chapter|part"
    r")\b|"
    r"准确|正确|计算|提取|识别|列出|提到|说明|指出|包含|总结|分析|分类|"
    r"数量|总数|比例|占比|金额|数值|指标|数据|事实|结论|章节|部分",
    re.I,
)

ARBITRARY_STRUCTURE_RUBRIC_PATTERN = re.compile(
    r"\b("
    r"file(?:name)?|file name|directory|folder|worksheet|tab name|sheet\s+name|"
    r"format|layout|markdown|xlsx?|docx?|pptx?|csv|json|html|"
    r"section\s+(?:title|name)|titled|title|header|column(?: name)?"
    r")\b|"
    r"文件名|目录|文件夹|工作表|表名|格式|布局|标题|列名|命名",
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

GENERATED_CONTENT_RUBRIC_PATTERN = re.compile(
    r"\b("
    r"classif(?:y|ies|ication)|categor(?:y|ize|ization)|risk classification|"
    r"analysis|analy[sz]e|conclusion|recommend(?:ation)?|suggestion|"
    r"checklist|phase|plan|strategy|work plan|implementation|workflow|"
    r"metric|performance metric|priority|p0|p1"
    r")\b|"
    r"分类|归类|分析|结论|建议|清单|阶段|计划|策略|工作计划|实施|流程|指标|优先级",
    re.I,
)

STRICTNESS_RUBRIC_PATTERN = re.compile(
    r"\b("
    r"slide|slides|page|pages|ppt|pptx|powerpoint|first slide|second slide|"
    r"chart type|pie chart|bar chart|line chart|placement|position|order|"
    r"exact(?:ly)?|specific(?:ally)?|specific recommendations?|such as|namely|"
    r"at least\s+\d+|exact title|title[d]?|section title|worksheet|sheet name|"
    r"role|roles|permission|permissions|responsibilit(?:y|ies)|access|"
    r"classif(?:y|ies|ication)|category|risk level|priority|p0|p1|"
    r"recommend(?:ation)?|suggestion|phase|stage|implementation plan|"
    r"strong department|weak department|best|most promising"
    r")\b|"
    r"第.{0,8}(页|张|个|部分|章节)|幻灯片|页面|页码|位置|顺序|"
    r"精确|具体|特定|例如|包括以下|分别为|名为|标题|工作表|表名|"
    r"角色|权限|职责|责任|访问|分类|归类|等级|级别|优先级|"
    r"建议|阶段|计划|指定|固定",
    re.I,
)

PRESENTATION_STRICTNESS_PATTERN = re.compile(
    r"\b(slide|slides|page|pages|ppt|pptx|powerpoint|chart type|"
    r"placement|position|order|exact(?:ly)?|specific recommendations?)\b|"
    r"第.{0,8}(页|张|个|部分|章节)|幻灯片|页面|页码|位置|顺序|"
    r"精确|具体|特定|固定",
    re.I,
)

OBJECTIVE_DATA_ORACLE_PATTERN = re.compile(
    r"\b("
    r"count|total|number|amount|rate|ratio|percentage|sum|average|"
    r"records?|orders?|items?|tasks?|participants?|employees?|hospitals?|"
    r"purchase orders?|inbound|outbound|variance|priority counts?|"
    r"state|show|list|identify|extract|calculate|computed?"
    r")\b|"
    r"数量|总数|金额|比例|占比|记录|订单|采购单|项目|任务|员工|医院|"
    r"入库|出库|差异|列出|识别|提取|计算|统计",
    re.I,
)

NON_OBJECTIVE_STRICTNESS_PATTERN = re.compile(
    r"\b("
    r"slide|slides|page|pages|ppt|pptx|chart type|placement|position|"
    r"title|worksheet|sheet name|format|layout|section|"
    r"role|permission|access|responsibilit(?:y|ies)|"
    r"classif(?:y|ies|ication)|risk level|priority|p0|p1|"
    r"recommend(?:ation)?|suggestion|phase|stage|plan|strategy|"
    r"exact wording|phrase|horizontal|vertical"
    r")\b|"
    r"幻灯片|页面|页码|位置|标题|工作表|表名|格式|布局|章节|"
    r"角色|权限|职责|责任|访问|分类|归类|等级|级别|优先级|"
    r"建议|阶段|计划|策略|措辞|水平|垂直",
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
            for violation in self._check_strictness_rubric(
                item,
                index,
                rubric,
                task,
                context_text,
                root,
            ):
                yield violation
            for violation in self._check_data_grounding(
                item,
                index,
                rubric,
                task,
                context_text,
                root,
            ):
                yield violation

    def _check_strictness_rubric(
        self,
        item: BenchmarkItem,
        index: int,
        rubric: str,
        task: str,
        context_text: str,
        root: Path | None,
    ) -> Iterable[Violation]:
        if not is_strictness_rubric(rubric) or len(normalize_space(task)) < 8:
            return []
        focused_context = append_targeted_search_context(
            item,
            root,
            context_text,
            strictness_grounding_terms(rubric),
            rubric,
            max_chars=5000,
        )
        prompt = STRICTNESS_PROMPT.format(
            task=preview(task, 1400),
            output_contract=preview(item.output_contract, 800) or "(no output contract)",
            context=preview(focused_context, 5200),
            rubric=preview(rubric, 1000),
        )
        result = call_json_single(
            self.client,
            STRICTNESS_SYSTEM_PROMPT,
            prompt,
            key="defect",
            default="none",
        )
        defect = result.get("majority")
        if defect not in {
            "unsupported_requirement",
            "multi_valid_outputs",
            "over_constrained",
            "task_mismatch",
        }:
            return []
        confidence = as_float(result.get("confidence"), 0.0)
        category = str(result.get("strictness_category") or strictness_category_for_defect(defect))
        if not keep_strictness_result(defect, category, rubric, result, self.review_threshold):
            return []
        todo = (
            result.get("todo")
            or "TODO: verify whether the rubric requirement is grounded in the task, output contract, or input data."
        )
        return [
            _violation(
                item,
                "task_rubric_mismatch",
                min(0.9, confidence),
                result.get("evidence")
                or "Rubric imposes an over-strict requirement not clearly supported by the task.",
                {
                    "rubric_index": index,
                    "rubric": rubric,
                    "grounding_check": "rubric_strictness_vs_task_context",
                    "defect": defect,
                    "strictness_category": category,
                    "todo": todo,
                    "human_review_todo": True,
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
        root: Path | None,
    ) -> Iterable[Violation]:
        if (
            is_structure_rubric(rubric)
            or is_presentation_strictness_rubric(rubric)
            or not looks_data_bearing(rubric)
        ):
            return []
        extract_prompt = REQUIRED_DATA_PROMPT.format(
            task=preview(task or "(missing task)", 900),
            rubric=preview(rubric, 1200),
        )
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
        if is_generated_content_requirement(task, rubric, required):
            return []

        focused_context = append_targeted_search_context(item, root, context_text, missing, rubric)
        verify_prompt = DATA_GROUNDING_PROMPT.format(
            missing=", ".join(missing),
            task=preview(task or "(missing task)", 1200),
            context=preview(focused_context, self.context_chars + 4000),
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
        reason = str(result.get("reason") or "")
        if data_gap_reason_is_not_aligned_with_rubric(reason, rubric):
            return []
        if targeted_search_refutes_data_gap(reason, focused_context, rubric):
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


def task_named_output_basenames(task: str) -> set[str]:
    """Basenames of files the task explicitly names as its output (create/generate/save as
    `foo.md`). Used to tell a save-location directory ('save it under `/x/`') from a directory
    that is itself the deliverable ('copy them into a new directory named `x`')."""
    names: set[str] = set()
    for match in BACKTICK_PATH_PATTERN.finditer(task):
        artifact = match.group(1).strip()
        if not artifact or not FILE_EXT_PATTERN.search(artifact):
            continue
        before = task[max(0, match.start() - 55): match.start()]
        if not OUTPUT_CUE_PATTERN.search(before):
            continue
        if re.search(r"\b(from|using|under)\s*$", before, re.I) and not re.search(r"\bsave\b", before, re.I):
            continue
        names.add(Path(artifact).name.lower())
    return names


def static_output_contract_issues(item: BenchmarkItem) -> list[dict[str, Any]]:
    required = contract_required_files(item.output_contract)
    if not required:
        return []
    required_norm = {p.strip("/").lower() for p in required}
    required_basenames = {Path(p).name.lower() for p in required}
    task = item.task or ""
    # When the contract's required file(s) are exactly what the task names as its output, a
    # directory the task mentions is only a save location, not a missing deliverable.
    contract_is_named_output = bool(required_basenames) and required_basenames <= task_named_output_basenames(task)
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
        elif DIR_CUE_PATTERN.search(window) and not contract_is_named_output:
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
    r"data preservation|visual content|image content|speech bubble|question mark|"
    r"icon content|picture content|visual elements?|file size|naming pattern|"
    r"color description|shape details?|content details?)\b|"
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
    if isinstance(output_contract, dict):
        contract_for_structure = {
            key: value
            for key, value in output_contract.items()
            if key not in {"required_files", "files"}
        }
    else:
        contract_for_structure = output_contract
    text = normalize_space(json.dumps(contract_for_structure, ensure_ascii=False, sort_keys=True))
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
    pairs = context_pairs(item)
    entry_count = sum(len(value) if isinstance(value, list) else 1 for _label, value in pairs)
    inventory_budget = max(0, max_chars // 5)
    per_entry_chars = max(
        250,
        (max_chars - inventory_budget) // max(entry_count, 1) - 180,
    )
    for label, value in pairs:
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
                        f"{read_file(path, per_entry_chars)}"
                    )
                    continue
            chunks.append(f"[{label}#{index}]\n{preview(entry, per_entry_chars)}")
    return preview("\n\n".join(chunks), max_chars)


def append_targeted_search_context(
    item: BenchmarkItem,
    root: Path | None,
    context_text: str,
    missing_terms: list[str],
    rubric: str = "",
    *,
    max_chars: int = 4000,
) -> str:
    snippets = targeted_search_context(item, root, missing_terms, rubric=rubric, max_chars=max_chars)
    if not snippets:
        return context_text
    return (
        context_text
        + "\n\n[TARGETED FULL-FILE SEARCH SNIPPETS]\n"
        + snippets
    )


def targeted_search_context(
    item: BenchmarkItem,
    root: Path | None,
    missing_terms: list[str],
    rubric: str = "",
    *,
    max_chars: int = 4000,
) -> str:
    terms = search_terms_from_required(missing_terms, rubric=rubric)
    if not terms:
        return ""
    chunks: list[str] = []
    for path in context_file_paths(item, root):
        results = search_file(path, terms)
        if results.get("_error"):
            chunks.append(f"FILE {path.name}\n- search_error: {results['_error']}")
            continue
        found = [(term, snippet) for term, snippet in results.items() if term != "_error" and snippet]
        if not found:
            continue
        lines = [f"FILE {path.name}"]
        for term, snippet in found[:12]:
            lines.append(f"- match `{term}`: {snippet}")
        chunks.append("\n".join(lines))
    return preview("\n\n".join(chunks), max_chars)


def context_file_paths(item: BenchmarkItem, root: Path | None) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for _label, value in context_pairs(item):
        values = value if isinstance(value, list) else [value]
        for entry in values:
            if not isinstance(entry, str):
                continue
            path = resolve_path(entry, root)
            if path is None or not path.exists():
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
    return paths


SEARCH_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "available",
    "before",
    "company",
    "correctly",
    "data",
    "does",
    "field",
    "file",
    "from",
    "have",
    "include",
    "includes",
    "input",
    "into",
    "list",
    "listed",
    "manual",
    "must",
    "output",
    "provided",
    "required",
    "rubric",
    "shall",
    "should",
    "source",
    "that",
    "the",
    "their",
    "these",
    "this",
    "those",
    "with",
}


def search_terms_from_required(
    required_terms: list[str],
    *,
    rubric: str = "",
    max_terms: int = 64,
) -> list[str]:
    terms: list[str] = []
    for raw in [*required_terms, rubric]:
        phrase = normalize_space(str(raw).replace("_", " ").replace("-", " "))
        if len(phrase) >= 3:
            terms.append(phrase)
        for number in re.findall(r"\b\d[\d,]*(?:\.\d+)?%?\b", phrase):
            terms.append(number)
            if number.endswith("%"):
                terms.append(number[:-1])
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]{3,}|[\u4e00-\u9fff]{2,}", phrase):
            low = token.lower()
            if low not in SEARCH_STOPWORDS:
                terms.append(token)
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
        if len(out) >= max_terms:
            break
    return out


def strictness_grounding_terms(rubric: str) -> list[str]:
    """Extract terms to search before confirming an over-strict rubric.

    A strictness finding is only credible after checking whether the allegedly
    arbitrary detail is grounded in the input artifacts. These terms feed
    targeted full-file search snippets into the LLM confirmation prompt.
    """
    text = normalize_space(rubric)
    terms: list[str] = []
    for quoted in re.findall(r"[`'\"]([^`'\"]{2,120})[`'\"]", text):
        terms.append(quoted)
    for number in re.findall(r"\b\d[\d,]*(?:\.\d+)?%?\b", text):
        terms.append(number)
        if number.endswith("%"):
            terms.append(number[:-1])
    for filename in re.findall(
        r"\b[\w./ -]+\.(?:md|txt|csv|tsv|xlsx|xls|docx|doc|pdf|pptx|ppt|json|html|htm|png|jpg|jpeg|svg|zip)\b",
        text,
        flags=re.I,
    ):
        value = filename.strip()
        terms.append(value)
        terms.append(Path(value).name)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{4,}|[\u4e00-\u9fff]{2,}", text):
        low = token.lower()
        if low not in SEARCH_STOPWORDS:
            terms.append(token)
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = normalize_for_presence(term)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(term)
        if len(out) >= 48:
            break
    return out


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
    text = rubric or ""
    if not STRUCTURE_RUBRIC_PATTERN.search(text):
        return False
    if ARBITRARY_STRUCTURE_RUBRIC_PATTERN.search(text):
        return True
    # Rubrics often use words like "section" while checking substantive report
    # content. In Workspace-style benchmarks that is normal oracle behavior, not
    # an output-structure over-constraint.
    if CONTENT_ORACLE_RUBRIC_PATTERN.search(text):
        return False
    return True


def is_strictness_rubric(rubric: str) -> bool:
    text = rubric or ""
    if is_objective_data_oracle_rubric(text):
        return False
    return bool(is_structure_rubric(text) or STRICTNESS_RUBRIC_PATTERN.search(text))


def is_objective_data_oracle_rubric(rubric: str) -> bool:
    text = rubric or ""
    if not OBJECTIVE_DATA_ORACLE_PATTERN.search(text):
        return False
    if NON_OBJECTIVE_STRICTNESS_PATTERN.search(text):
        return False
    return True


def is_presentation_strictness_rubric(rubric: str) -> bool:
    return bool(PRESENTATION_STRICTNESS_PATTERN.search(rubric or ""))


def strictness_category_for_defect(defect: Any) -> str:
    value = str(defect or "").strip()
    if value == "over_constrained":
        return "arbitrary_structure"
    if value in {"unsupported_requirement", "multi_valid_outputs", "task_mismatch"}:
        return value
    return "none"


STRONG_UNSUPPORTED_RUBRIC_PATTERN = re.compile(
    r"\b("
    r"exact(?:ly)?|at least\s+\d+|file size|bytes?|"
    r"role|roles|permission|permissions|access|responsibilit(?:y|ies)|"
    r"sensitive|classification level|level\s+\d+|"
    r"column names?|worksheet|sheet name|section title|exact title|"
    r"specific phrase|exact wording"
    r")\b|"
    r"精确|至少\s*\d+|文件大小|字节|角色|权限|职责|责任|访问|"
    r"敏感|等级|级别|列名|工作表|表名|章节标题|准确标题|具体措辞|固定措辞",
    re.I,
)


def keep_strictness_result(
    defect: Any,
    category: str,
    rubric: str,
    result: dict[str, Any],
    threshold: float,
) -> bool:
    """Favor precision for over-strict rubric findings.

    Unsupported-requirement is the noisiest label: it often means only "the task
    did not explicitly ask for this". Keep it only with stronger confidence and
    strong lexical evidence of exact/arbitrary constraints. Structure and
    multi-valid-output findings are closer to the desired failure mode.
    """
    confidence = as_float(result.get("confidence"), 0.0)
    if confidence < threshold:
        return False
    defect_s = str(defect or "")
    if defect_s == "unsupported_requirement" or category == "unsupported_requirement":
        if confidence < 0.8:
            return False
        return bool(STRONG_UNSUPPORTED_RUBRIC_PATTERN.search(rubric or ""))
    if category in {"multi_valid_outputs", "arbitrary_structure", "task_mismatch"}:
        return confidence >= max(threshold, 0.65)
    return defect_s in {"over_constrained", "task_mismatch"} and confidence >= max(threshold, 0.65)


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


def is_generated_content_requirement(task: str, rubric: str, required: list[str]) -> bool:
    """Generated analysis structures are not source-data gaps.

    If the task asks the agent to analyze/classify/plan/summarize and the rubric
    checks the resulting classification/checklist/plan/metrics, absence of that
    exact output structure from the input files is expected.
    """
    task_text = task or ""
    joined = " ".join([rubric, *required])
    if not GENERATIVE_TASK_PATTERN.search(task_text):
        return False
    if not GENERATED_CONTENT_RUBRIC_PATTERN.search(joined):
        return False
    # Keep concrete source-value checks alive: numbers often indicate a value the
    # rubric expects to be extracted or recomputed, not just a generated section.
    if re.search(r"\b\d[\d,]*(?:\.\d+)?%?\b", rubric):
        return False
    return True


GRADE_TERMS = re.compile(
    r"\b(tertiary|secondary|primary|grade classification|hospital grade)\b|"
    r"三级|二级|一级|等级",
    re.I,
)


def data_gap_reason_is_not_aligned_with_rubric(reason: str, rubric: str) -> bool:
    """Drop LLM reasons that clearly discuss a different rubric in the same item."""
    if not reason:
        return False
    # Common Workspace-Bench failure: the checker audits a simple total-count
    # rubric but explains a data gap for a different grade-breakdown rubric.
    return bool(GRADE_TERMS.search(reason) and not GRADE_TERMS.search(rubric or ""))


ABSENCE_REASON_PATTERN = re.compile(
    r"\b(not present|not found|absent|missing|not in|no .*?(?:given|found|provided)|"
    r"cannot be derived|no derivable)\b|不存在|缺失|未找到|没有|无法推导",
    re.I,
)


def targeted_search_refutes_data_gap(reason: str, focused_context: str, rubric: str) -> bool:
    """A data-gap claim is unsafe when full-file snippets show the allegedly missing value."""
    if not reason or not ABSENCE_REASON_PATTERN.search(reason):
        return False
    if "[TARGETED FULL-FILE SEARCH SNIPPETS]" not in focused_context:
        return False
    reason_norm = normalize_for_presence(reason)
    found_terms = {
        normalize_for_presence(term)
        for term in re.findall(r"- match `([^`]+)`:", focused_context)
    }
    for number in substantive_numeric_terms(rubric):
        norm = normalize_for_presence(number)
        if norm and norm in reason_norm and norm in found_terms:
            return True
    return False


def substantive_numeric_terms(text: str) -> list[str]:
    out: list[str] = []
    for number in re.findall(r"\b\d[\d,]*(?:\.\d+)?%?\b", text or ""):
        plain = number.rstrip("%").replace(",", "")
        try:
            value = float(plain)
        except ValueError:
            continue
        if number.endswith("%") or "." in number or "," in number or abs(value) >= 1000:
            out.append(number)
    return out


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


def call_json_single(
    client: LLMClient,
    system: str,
    user: str,
    *,
    key: str,
    default: str,
) -> dict[str, Any]:
    try:
        result = client.chat_json(system, user)
    except Exception as exc:  # noqa: BLE001 - convert to row-local uncertain result
        return {
            "majority": default,
            "votes": [],
            "results": [{"error": f"{type(exc).__name__}: {exc}"}],
            "confidence": 0.0,
        }
    if not isinstance(result, dict):
        return {"majority": default, "votes": [], "results": [], "confidence": 0.0}
    vote = str(result.get(key)).strip() if result.get(key) not in (None, "") else default
    merged = dict(result)
    merged["majority"] = vote
    merged["votes"] = [vote]
    merged["results"] = [result]
    return merged
