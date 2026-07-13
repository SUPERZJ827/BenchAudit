# BenchCore 设计说明

## 1. 目标

本目录是一次从零开始的新实现，不依赖之前的 `benchaudit` 包。

目标是支持：

```text
任意给一个 benchmark 文件 -> 自动识别核心字段 -> 检查主要 benchmark artifact 缺陷 -> 输出统一报告
```

第一阶段只关注核心组件：

```text
Task Specification
Context / Attachments
Expected Output / Answer Contract
Oracle / Ground Truth
Evaluator / Rubric / Tests
```

## 2. 代码结构

```text
benchcore/
  adapter.py         通用 canonical adapter
  cli.py             命令行入口
  loader.py          JSONL / JSON / CSV 加载
  llm_client.py      OpenAI-compatible LLM API client
  llm_auditor.py     通用 LLM semantic auditor
  artifact_consistency.py 通用 task/context/reference/evaluator 一致性与 grounded rubric 审计器
  auditor.py         checker 调度、并行执行和跨审计器证据融合
  methods.py         replay / metamorphic / mutation / dataset checks
  field_mapping.py   自动字段映射
  schema.py          BenchmarkItem / Violation 数据结构
  taxonomy.py        artifact + mechanism + defect_type 分类
  evaluators.py      简单 evaluator 和 answer normalization
  checkers.py        核心 artifact 检查器
  swe_leak.py        代码 benchmark 的 solution leakage 审计器
  auditor.py         运行所有 checker
  report.py          JSON / Markdown 报告输出
```

## 3. 当前 checker

当前默认启用：

```text
TaskSpecChecker
ContextChecker
OutputContractChecker
OracleChecker
EvaluatorChecker
ContractConsistencyChecker
EvaluatorReplayChecker
MetamorphicAnswerChecker
EvaluatorMutationChecker
ExecutableEvidenceChecker
DifferentialCandidateChecker
DuplicateConflictChecker
SchemaDriftChecker
TaskIntegrityChecker
SolutionLeakChecker（可选，面向含 patch/problem_statement 的代码 benchmark）
CrossArtifactConsistencyChecker（可选，LLM 二级审计 task/context/reference/evaluator 是否互相一致）
```

它们现在主要做高泛化、低成本的检查：

- 任务说明缺失；
- 题面引用 passage / figure / table / file / database 但上下文缺失；
- 附件路径不存在；
- 输出合同缺失；
- gold answer 缺失；
- choice gold 无法映射到选项；
- 选项文本重复；
- 简单算术 gold answer 错误；
- evaluator 缺失；
- declared alias 被 evaluator 拒绝；
- exact match 过严风险；
- evaluator 过弱风险。
- 缺失时间范围；
- 引用未指明的研究、报告或比较来源；
- 明显截断的任务指令；
- mojibake、电子表格日期转换等展示损坏。
- gold patch 新增修复代码是否泄漏到可见 problem_statement（SWE-bench / 代码 benchmark 专项）。
- task、context/input、reference/gold、rubric/evaluator 之间是否存在数据缺口、任务-rubric 不一致、reference-task 不一致（可选 LLM 二级审计）。

## 3.1 通用 Adapter 原则

当前 adapter 不是针对某个 benchmark 写死的。它做的是：

1. 从 JSONL / JSON / CSV 自动推断常见字段；
2. 将输入统一成 canonical task package；
3. 保留原始 raw record，避免信息丢失；
4. 将嵌套 `metadata` 展开到统一 metadata 字段；
5. 不使用人工标签、verified gold、error type 作为检测依据。

如果自动字段推断不准，可以通过 mapping JSON 覆盖。

## 3.2 多方法证据等级

```text
static evidence
declared evaluator replay
declared evaluator model mutation/metamorphic evidence
executable evidence
LLM semantic evidence
human/expert evidence
```

其中：

- 静态字段冲突和可安全执行的算术证据可以直接 confirmed；
- 只基于 evaluator 类型模拟出的 mutation/metamorphic 结果默认进入 review；
- 真实 evaluator/test script/SQL execution 的结果才属于 execution-backed evidence；
- LLM 语义判断需要结合阈值、review routing 或其他方法交叉验证。

## 3.3 LLM 职责分解与证据门控

三个 LLM auditor 使用相同 canonical task package，但分别完成不同判断：

```text
EvidenceGoldLLMAuditor     盲解、gold 辩护、gold 挑战和程序化聚合
QuestionClarityLLMAuditor  检查 answer-changing 的缺失条件、上下文和歧义
OptionSetLLMAuditor        逐项判断字面真值、最佳答案资格和等价关系
PresentationLLMAuditor     检查模型理解过程中发生的隐式 OCR/格式修复
```

Gold 验证采用风险级联：

1. Blind Solver 同时看不到 choices 和 gold，只输出开放式精确答案；
2. Matcher 分别判断开放答案与每个选项是否语义等价；
3. Independent Option Applicability 对每个选项直接检查是否满足题干；
4. 较弱性质、上位概念、下位概念和相关事实不算身份型问题的等价答案；
5. 属性型问题中，彼此不等价但分别满足题干的选项都会加入答案集合；
6. 漏评任何选项都会使答案集合进入 uncertain；
7. 程序根据合并后的答案集合判断无正确答案、多正确答案或唯一答案；
8. 只有唯一答案时，才将它与 gold 比较；
9. 不一致、多解、无解、低置信或不确定匹配时启动 Challenger/Defender；
10. 代码根据有效阶段的缺陷票数和平均置信度计算最终置信度；
11. 外部来源、未验证假设和专业约定不会自动 confirmed；
12. `gold-single` 保留为单次 LLM 判断的消融基线。

Option Auditor 不把“字面为真”等同于“应被接受为最佳答案”。这用于处理
最完整、最精确、最合适等常见选择题语义，同时继续检测普通单选中的真正多解。

Presentation Auditor 不要求格式问题改变答案。只要模型必须把原始 artifact 从
`raw_text` 修复为不同的 `interpreted_text` 才能理解，例如补回指数符号、合并被
错误切开的选项或修复乱码，就输出 `presentation_corruption`。单纯的小数与百分数
表示差异、语法风格或事实错误不属于该类。

证据门控采用以下原则：

1. 题干歧义的单次 LLM 判断默认是 review signal；
2. 静态规则或执行检查提供同类证据后才升级 confirmed；
3. 审计器结论冲突时不强行投票，相关发现降级为 review；
4. 冲突和 API 失败属于 operational scope，不计入默认缺陷评估；
5. substantive 与 presentation scope 可以通过 `compare --include-scope` 分开评估。

人工审核标签用于实验评估，而不是检测输入。人工标签也可能有遗漏或争议，因此
报告应保留“多个独立审计器一致、但与人工标签冲突”的案例供二次复核，不能通过
针对具体样本的硬编码直接删除。

## 4. 运行命令

```bash
python -m benchcore.cli audit \
  examples/sample_core_benchmark.jsonl \
  --out reports/sample_audit_report.json \
  --md reports/sample_audit_report.md \
  --print-summary
```

字段映射：

```bash
python -m benchcore.cli infer-mapping examples/sample_core_benchmark.jsonl
```

LLM 语义审计：

```bash
python -m benchcore.cli audit \
  /path/to/benchmark.jsonl \
  --limit 20 \
  --llm-audit \
  --llm-config configs/llm_deepseek.json \
  --llm-cache reports/llm_cache.jsonl \
  --out reports/llm_audit_report.json \
  --md reports/llm_audit_report.md \
  --print-summary
```

代码 benchmark solution leakage 审计：

```bash
python scripts/export_swebench_jsonl.py \
  --suite both \
  --out-dir datasets/swebench

python -m benchcore.cli audit \
  datasets/swebench/lite.jsonl \
  --profile swebench \
  --out reports/swe_leak_audit.json \
  --md reports/swe_leak_audit.md \
  --print-summary
```

带 LLM 二级确认：

```bash
python -m benchcore.cli audit \
  datasets/swebench/lite.jsonl \
  --profile swebench \
  --swe-leak-llm-confirm \
  --llm-config configs/llm_deepseek.json \
  --llm-cache reports/llm_cache.jsonl \
  --out reports/swe_leak_audit_confirmed.json \
  --md reports/swe_leak_audit_confirmed.md \
  --print-summary
```

通用 cross-artifact consistency 审计：

```bash
python -m benchcore.cli audit \
  /path/to/benchmark.jsonl \
  --cross-artifact-audit \
  --llm-config configs/llm_deepseek.json \
  --llm-cache reports/cross_artifact_cache.jsonl \
  --out reports/cross_artifact_audit.json \
  --md reports/cross_artifact_audit.md \
  --print-summary
```

### Workspace-Bench 组件 profile 与审计器分工

Workspace-Bench 是 agentic benchmark，**没有传统 gold answer / reference output**。每个 item 的组件是：

- `task`：自然语言任务
- `input_files`：真实输入文件（`data/` 目录，多为 docx/pdf/xlsx/csv/md）
- `output_files` / `output_contract`：agent 应**创建**的文件名与产出契约（无内容）
- `rubrics` / `evaluator`（type=`workspacebench_rubric`）：一组 yes/no 评分条件——**oracle 是这组条件，不是某一条标准答案**

因此在 Workspace-Bench 上查的是「rubric 里的 oracle 是否有问题」，而不是「模型答案是否等于 gold」。缺陷类型应表述为：

- `task_rubric_mismatch`（rubric overconstraint / rubric-task mismatch）：rubric 要求了 task 未要求的结构/格式/命名/布局
- `artifact_data_gap`（rubric ungrounded）：rubric 需要的字段/数据/文件在输入中不存在
- `output_evaluator_contract_mismatch`（rubric-contract mismatch）：rubric/evaluator 要求了 output contract 未声明或相冲突的输出文件、格式、目录、sheet、布局
- `rubric_target_error`：rubric 写死的数字/事实与从输入独立重算的结果不符

**主线**是 grounded-rubric / rubric-contract / cross-artifact 审计；**`value_recompute` 只作为少数高置信辅助**，仅对明确能从输入重算的 rubric 有效——Workspace-Bench 的数值 rubric 多在断言**输出文档内容**（"manual 列出 6 项检查"），并非输入可重算，故它在此数据集上 precision 低、不作主 auditor（默认关闭）。

Workspace-Bench 主线审计：

```bash
python -m benchcore.cli audit \
  /path/to/benchmark.jsonl \
  --profile workspacebench \
  --basic-only \
  --llm-config configs/llm_deepseek.json \
  --llm-cache reports/grounded_rubric_cache.jsonl \
  --out reports/grounded_rubric_audit.json \
  --md reports/grounded_rubric_audit.md \
  --print-summary
```

`--profile workspacebench` 默认启用两个 LLM-assisted review checker：

- `GroundedRubricConsistencyChecker`：逐条检查 rubric 是否被 task/context 支撑。数据型 rubric 检查其所需 source data 是否存在于输入/context 中；结构型 rubric 检查文件名、sheet 名、章节、格式等要求是否被 task 明确支持。
- `RubricOutputContractConsistencyChecker`：检查 rubric/evaluator 是否和 `output_contract` 冲突，例如要求额外文件、额外目录、额外 sheet、不同文件名或不同格式。

generic profile 下也可以显式传 `--grounded-rubric-audit` / `--rubric-contract-audit` 单独启用。

Rubric coverage / under-checking 审计（对应 OpenAI low-coverage tests）：

```bash
python -m benchcore.cli audit \
  /path/to/benchmark.jsonl \
  --profile workspacebench \
  --basic-only \
  --rubric-coverage-audit \
  --llm-config configs/llm_deepseek.json \
  --llm-cache reports/rubric_coverage_cache.jsonl \
  --out reports/rubric_coverage_audit.json \
  --md reports/rubric_coverage_audit.md \
  --print-summary
```

`RubricCoverageChecker` 从 task 中抽取中心要求，并检查 rubric/evaluator 是否覆盖这些要求。它只标记 `underconstrained_evaluator_risk`，用于发现 evaluator/rubric **过松或漏测**的问题，例如任务要求多个交付物/多个分析维度/失败分支处理，但 rubric 只检查其中一部分。它默认关闭，因为这类判断比 contract mismatch 更主观，建议先小样本验证后再扩全量。

Investigator 证据复核（OpenAI-style flagged subset deep review）：

```bash
python -m benchcore.cli investigate \
  /path/to/benchmark.jsonl \
  --report reports/grounded_rubric_audit.json \
  --llm-config configs/llm_deepseek.json \
  --llm-cache reports/investigator_cache.jsonl \
  --out reports/investigation.json \
  --md reports/investigation.md \
  --print-summary
```

`investigate` 不再产生新候选，而是对已有 audit report 里的每条 candidate 做证据复核：重新读取 task、output contract、rubric/evaluator、输入文件 preview，并对 candidate finding 中的关键词、数字、文件名做 targeted full-file search。输出 `likely_true / false_positive / uncertain`、任务证据、输入证据、rubric 证据、contract 证据、反证和建议动作。

这一步用于把高召回 scanner 的原始队列压成更可信的 review queue。它显式执行几个 Workspace-Bench 规则：输入中存在或可推出的细节不算 over-strict；语义等价不算 data gap；保存路径目录不能直接当成额外输出；rubric 写出可计算答案值本身不是缺陷。

默认使用严谨复核模式：每个候选运行 3 次带独立 cache slot 的 investigator pass，严格多数聚合后再运行 evidence verifier。Evidence verifier 把 investigator 的引用当作不可信 claim，重新核对 task/input/rubric/contract；共识结论和证据结论不一致时自动降为 `uncertain`。保存目录是否漏测依赖 harness 行为，若没有证据证明错误目录也能通过 evaluator，则只能标为 `harness_dependent` / `uncertain`。

快速消融可以关闭这些质量门：

```bash
python -m benchcore.cli investigate ... \
  --investigator-passes 1 \
  --no-evidence-verifier
```

严谨模式报告额外保存：每次独立原始响应、verdict votes、agreement、证据验证结果、模型配置、API/cache 调用数、token、耗时和 git commit。可以据此计算准确率-成本曲线，而不是只比较最终候选数量。

构建正式 gold study 时必须同时抽取 scanner 未标记任务，否则只能估计 precision、无法估计 false-negative rate 和 recall：

```bash
python -m benchcore.cli gold-study \
  datasets/workspacebench/full.jsonl \
  --report reports/workspace_full388_v17_scanner_audit.json \
  --investigation reports/workspace_full388_v17_investigation_full.json \
  --flagged-size 60 \
  --unflagged-size 60 \
  --seed 20260710 \
  --out reports/workspace_gold120.jsonl \
  --md reports/workspace_gold120.md
```

输出保存 source/report/investigation SHA-256、sampling stratum 和空白人工标签。标注员必须打开原始输入文件；不能只复述 investigator evidence。

Forensic evidence bundle（人工/agent 深审证据包）：

```bash
python -m benchcore.cli forensic \
  /path/to/benchmark.jsonl \
  --item-id workspacebench-7 \
  --report reports/grounded_rubric_audit.json \
  --investigation reports/investigation.json \
  --out reports/forensic_workspacebench_7.json \
  --md reports/forensic_workspacebench_7.md
```

`forensic` 不调用 LLM，也不改变判断。它把单个任务的 task、output contract、rubrics、scanner candidates、investigator verdicts、targeted full-file search 证据打包，方便人工复核或后续 tool-using agent 深审。用途是把 OpenAI-style investigator review 的“可查证证据包”固化下来，尤其适合 `uncertain`、`需人工核输入` 和争议较大的 data-gap case。

Ranking impact（问题任务对榜单的影响）：

```bash
python scripts/ranking_impact.py \
  --trials /path/to/per_task_trials.jsonl \
  --exclude-investigation reports/investigation.json \
  --investigation-verdict likely_true \
  --investigation-category contract_mismatch \
  --investigation-category data_gap \
  --investigation-min-confidence 0.9 \
  --out-json reports/ranking_impact_cleaned.json \
  --out-csv reports/ranking_impact_cleaned.csv
```

`ranking_impact.py` 可以直接从 investigation report 中抽取需要剔除/清洗的问题任务，重新计算每个 system 的平均分、rank delta、score delta、pairwise flips、Kendall tau 和 Spearman rho。这样可以把“发现 benchmark 问题”推进到“这些问题是否改变模型/agent 排名”的量化分析。

B2 数值重算审计（`--value-recompute-audit`）：

```bash
python -m benchcore.cli audit \
  /path/to/benchmark.jsonl \
  --profile workspacebench \
  --basic-only \
  --value-recompute-audit \
  --llm-config configs/llm_deepseek.json \
  --llm-cache reports/value_recompute_cache.jsonl \
  --out reports/value_recompute_audit.json \
  --md reports/value_recompute_audit.md \
  --print-summary
```

对每条**断言了实质数值**的 rubric（`rubric_values()` 过滤掉标识符/阈值/年份/文件名/月份序号后仍有数值），让 LLM 写 pandas 代码从表格输入（`.xlsx/.xls/.csv`）**独立重算**该值，执行后比对。只有当重算成功且与断言不符时才发 `rubric_target_error`（review signal，非 gold-answer 判定）；重算不可运行或报 `DATA_NOT_AVAILABLE`（所需数据常在非表格输入里）一律静默，data-gap 检测交给 grounded-rubric checker。

⚠️ **安全**：该 checker 会用 `subprocess` **执行 LLM 生成的代码**、无沙箱，因此默认关闭、须显式 `--value-recompute-audit`，且**只应对可信数据启用**。

Workspace-Bench HuggingFace 导出：

```bash
python scripts/export_workspacebench_jsonl.py \
  --suite lite \
  --limit 5 \
  --download-inputs \
  --out-dir datasets/workspacebench
```

`--download-inputs` 会下载每个任务的真实 `data/` 目录，并把完整文件清单、`size_bytes` 和可读文件内容交给 grounded-rubric checker；没有这个证据，data-gap 类候选容易被截断 context 误导。

## 5. 后续扩展点

优先扩展：

1. benchmark-family adapters：SWE-bench、Workspace-Bench、MMLU-Redux、GSM8K-Platinum、ELT-Bench、LiveSQLBench/BIRD；
2. execution consistency：验证合理替代解是否被 evaluator 误杀；
3. mutation testing：验证 evaluator 是否过松；
4. benchmark-family grounding strategies：继续把 Workspace-Bench 的 B2、代码 benchmark 的 task/patch/test consistency 接到统一输出；
5. supervised comparison：如果输入里有人类 defect label，计算 precision/recall。
