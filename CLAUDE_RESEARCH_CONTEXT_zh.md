# BenchCore 研究背景、问题定义与实验路线

本文面向后续参与本项目的 Claude 或其他研究协作者，说明：

1. 为什么要做 benchmark audit；
2. 我们要审计 benchmark 的哪些部分；
3. 完整缺陷空间是什么；
4. 哪些检测方法已经成熟；
5. 哪些问题仍有研究创新空间；
6. 为什么选择当前数据集；
7. 下一阶段应该做哪些实验。

当前代码实现请同时阅读：

```text
CLAUDE_HANDOFF_zh.md
DESIGN.md
README.md
```

前期详细调研原文：

```text
/home/zhoujun/llmdata/explore/agent_benchmark_components_survey.md
/home/zhoujun/llmdata/explore/benchmark_defect_taxonomy_by_artifact.md
/home/zhoujun/llmdata/explore/benchmark_defect_detection_methods.md
/home/zhoujun/llmdata/after623/first_batch_benchmark_sampling_plan.md
```

## 1. 研究动机

LLM/Agent benchmark 已经从：

```text
question + gold answer + exact match
```

发展为：

```text
task specification
+ context / files / database / repository
+ environment and initial state
+ tools and interaction protocol
+ expected deliverable
+ oracle / target state
+ evaluator / tests / rubric
+ trace and provenance
```

一个模型得分错误，不一定来自模型能力不足，也可能来自：

- 题目缺条件；
- 上下文或附件损坏；
- gold 错误；
- 多个合理答案未被接受；
- evaluator 误杀正确解；
- rubric 与 prompt 不一致；
- 环境或工具不可用；
- benchmark 版本漂移；
- 证据不足以支撑最终分数。

因此，本项目要解决的不是：

> 再构建一个模型能力 benchmark。

而是：

> 自动审计 benchmark 自身的任务、答案、评分和数据 artifact，发现会导致评测失真的缺陷，并将缺陷归因到最可能的根因组件。

## 2. 主研究问题

建议将论文问题表述为四个核心 Research Questions。

### RQ1：统一表示

能否把不同类型 benchmark 统一表示为一个 canonical task package，使选择题、数学、
SQL、代码修复和开放式工作任务能够共享审计框架？

### RQ2：多方法缺陷检测

能否组合：

```text
静态规则
执行验证
metamorphic testing
mutation testing
差分求解
结构化 LLM audit
```

比直接让一个 LLM 判断“这道题有没有问题”取得更好的 precision、recall 和审核效率？

### RQ3：答案空间验证

当 benchmark 可能存在：

- wrong gold；
- no correct answer；
- multiple correct answers；
- missing accepted alternatives；

时，如何验证“正确解空间”，而不是只检查单个 gold？

### RQ4：证据与缺陷归因

如何把一个可疑信号分成：

```text
confirmed defect
human-review candidate
presentation defect
operational failure
```

并将它归因到 task、context、oracle、evaluator 等具体 artifact？

## 3. Benchmark 的统一组成

前期调研总结出 10 类完整 artifact。

| Artifact | 内容 |
|---|---|
| Task Specification | 用户目标、问题、issue、约束和成功标准 |
| Context / Attachments | passage、图片、PDF、表格、数据库、repo、知识库 |
| Environment / Initial State | Docker、VM、数据库快照、base commit、app state |
| Tools / Action Space | API、shell、browser、SQL、office tools |
| Interaction Protocol | 多轮规则、澄清、user simulator、step/time budget |
| Expected Output | 短答案、SQL、patch、文件、报告、目标状态 |
| Oracle / Ground Truth | gold、reference solution、target state、accepted alternatives |
| Evaluator / Tests / Rubric | exact match、执行测试、state check、rubric、LLM judge |
| Trace / Evidence | tool log、stdout、截图、state diff、cost/runtime |
| Provenance / Versioning | 数据来源、版本、split、验证状态、污染与许可 |

## 4. 当前研究范围

第一阶段集中在绝大多数 benchmark 都具备的五个核心组件：

```text
Task Specification
Context / Attachments
Expected Output / Choices
Oracle / Ground Truth
Evaluator / Rubric / Tests
```

暂时不作为主线：

```text
Environment
Tools
Interaction
Trace
Provenance
```

理由不是这些部分不重要，而是它们通常需要完整 agent harness、容器、GUI、数据库或
多轮用户模拟器。第一阶段先验证核心 artifact audit 是否能跨 benchmark 工作。

后续论文可以将环境审计作为扩展，而不是一开始就承担完整 agent infrastructure。

## 5. 缺陷分类原则

### 5.1 根因优先

同一问题可能产生多个症状，但主标签应指向最早、最可修复的根因。

例如：

```text
缺失图片导致 gold 看起来错误
→ 主标签应为 missing_context
→ 不应同时把 wrong_gold_answer 当作主根因
```

### 5.2 单主标签 + 辅助信号

真实缺陷不是天然完全互斥，因此采用：

```text
primary defect：一个根因标签
secondary signals：多个症状或下游影响
```

### 5.3 Benchmark 缺陷不等于模型失败

模型不会做题不是 benchmark defect。

只有 benchmark artifact 存在错误、缺失、不一致、不可复现或评分不合理时，才属于
审计目标。

### 5.4 Substantive 与 Presentation 分离

```text
substantive defect：
影响答案集合、任务可解性、gold 或评分正确性

presentation defect：
OCR、编码、数学格式、切分或转换损坏
```

Presentation 即使不影响强模型做题，也应报告，但不能混入 substantive 主指标。

## 6. 第一阶段核心缺陷体系

### 6.1 Task Specification

- `missing_task`
- `ambiguous_goal`
- `missing_condition`
- `false_premise`
- `hidden_assumption`
- `incomplete_task_instruction`
- `temporal_scope_missing`
- `source_reference_missing`

### 6.2 Context / Attachments

- `missing_context`
- `inaccessible_attachment`
- `corrupted_or_low_quality_context`
- `context_version_mismatch`
- `context_oracle_conflict`
- `stale_external_context`

### 6.3 Expected Output / Choices

- `missing_output_contract`
- `output_format_overstrict`
- `missing_accepted_alternatives`
- `unit_or_scale_ambiguity`
- `bad_options_clarity`
- `duplicate_choices`
- `presentation_corruption`

### 6.4 Oracle / Ground Truth

- `wrong_gold_answer`
- `multiple_correct_answers`
- `no_correct_answer`
- `stale_gold`
- `invalid_reference_solution`
- `oracle_context_mismatch`
- `gold_requires_hidden_knowledge`

### 6.5 Evaluator / Tests / Rubric

- `missing_evaluator`
- `overstrict_evaluator`
- `underconstrained_evaluator`
- `wrong_test_logic`
- `test_spec_mismatch`
- `rubric_ambiguity`
- `rubric_prompt_mismatch`
- `llm_judge_bias`
- `nondeterministic_grader`
- `reward_hackable_evaluator`

完整 10 artifact taxonomy 见前期调研原文。

## 7. 哪些方法已经相对成熟

这些部分主要是工程集成，但必须成为可靠底座。

| 方法 | 可检测问题 |
|---|---|
| Schema validation | 字段缺失、类型错误、合同错误 |
| Attachment integrity | 文件不存在、路径错误、checksum、格式不可读 |
| Static consistency | task、gold、choice、evaluator 字段冲突 |
| Reference replay | reference solution、环境和 evaluator 是否一致 |
| Evaluator replay | evaluator 是否接受自己的 gold |
| Metamorphic testing | 格式、别名、单位或等价转换是否被误拒 |
| Mutation testing | 明显错误答案是否仍能通过 |
| Differential execution | 多个 solver、SQL、patch 或程序输出是否冲突 |
| Duplicate scan | duplicate ID、重复任务、冲突 gold |
| Version/provenance checks | 数据版本、split 和来源记录 |

这些方法通常 precision 较高，创新主要来自统一集成和跨 artifact 证据归因。

## 8. 真正困难且值得研究的问题

### 8.1 Missing Condition / Hidden Assumption

难点：

- 需要知道完成任务真正依赖哪些条件；
- 不是所有未声明条件都会改变答案；
- 医学、法律、教材和行业惯例依赖来源。

可能方案：

```text
assumption extraction
+ alternative interpretation generation
+ answer-changing verification
+ source retrieval / expert routing
```

### 8.2 Accepted Alternatives / Correct Solution Space

难点：

- SQL、代码、Agent 任务通常有多条正确路径；
- 单一 gold 无法代表完整解空间；
- evaluator 可能误杀合理替代解。

可能方案：

```text
candidate solution mining
+ semantic equivalence
+ execution consistency
+ metamorphic generation
+ evaluator replay
```

Text-to-SQL 中可借鉴 execution consistency：不同 SQL 文本只要在充分测试数据库或
多个扰动实例上产生一致结果，就可能属于同一正确解空间。

### 8.3 Multiple Correct Answers

需要区分两种情况：

```text
答案等价：
两个选项表达同一答案

独立适用：
两个不等价选项分别满足题干
```

当前实现采用：

```text
open-ended blind solve
+ answer-option equivalence matcher
+ independent option applicability
```

这比只将 gold 与其他选项做字符串或语义匹配更完整。

### 8.4 Rubric / Prompt / Deliverable Alignment

对 GDPval、APEX、PaperBench 等开放式任务：

- prompt 可能要求多个交付内容；
- rubric 可能漏掉硬要求；
- rubric 也可能检查 prompt 未要求的内容；
- LLM judge 可能偏好长度、风格或格式。

可能方案：

```text
prompt requirement extraction
+ rubric criterion extraction
+ coverage matrix
+ counterfactual rubric probes
+ human calibration
```

### 8.5 Evidence-Supported Scoring

Agent benchmark 不能只报告 pass/fail，还应判断：

- 测试是否实际执行；
- target state 是否完整；
- trace 是否支持最终分数；
- 是否存在 collateral damage；
- score、log 和 artifact 是否一致。

这一部分是后续扩展到 agent benchmark 时的重要创新方向。

## 9. LLM 在系统中的合理角色

LLM 适合：

- 语义理解；
- 条件和假设抽取；
- 开放式求解；
- 候选答案生成；
- option applicability；
- prompt-rubric 对齐；
- 缺陷解释和人工 review 路由。

LLM 不应单独负责：

- 数值和符号执行；
- 文件存在性；
- 环境复现；
- SQL、代码、state 的最终执行判断；
- evaluator 覆盖；
- 污染证明；
- 最终 confirmed 决策。

核心方法口径：

> LLM 产生结构化假设、候选和语义证据，程序、执行器及跨 artifact 约束负责验证、
> 聚合和缺陷归因。

## 10. 代表性 Benchmark 调研

### 静态 QA / 选择题

- MMLU / MMLU-Redux
- TruthfulQA
- GAIA
- GoldenSwag 类人工审计数据

常见组件：

```text
question
context
choices
gold
exact/normalized evaluator
```

### 数学

- GSM8K
- GSM8K-Platinum / PlatinumBench

优势：

- 可执行；
- 学科流派争议少；
- 可验证 wrong gold；
- 可测试数值 evaluator。

### Text-to-SQL / DB

- LiveSQLBench
- BIRD / BIRD-INTERACT
- ELT-Bench / ELT-Bench-Verified

常见组件：

```text
natural language request
schema / database
knowledge base
gold SQL / expected result
test cases
execution evaluator
```

关键研究问题：

- SQL 等价；
- accepted alternatives；
- context-oracle conflict；
- evaluator 过严或过松；
- schema/version drift。

### Code / Terminal

- SWE-bench / SWE-bench Verified
- Terminal-Bench
- TerminalWorld

常见组件：

```text
issue/instruction
repo/container
base state
reference patch/solution
tests
FAIL_TO_PASS / PASS_TO_PASS
```

### Web / OS / App Agent

- WebArena
- OSWorld
- AppWorld
- tau-bench / tau2-bench

核心 oracle 通常不是唯一轨迹，而是：

```text
target environment state
+ state-based tests
+ side-effect constraints
```

### Workplace / Research

- GDPval
- APEX-Agents
- PaperBench
- MLE-bench
- ScienceAgentBench

常见组件：

```text
work assignment
files/context
deliverable contract
expert reference
rubric
human or LLM judge
```

## 11. 第一批实验数据集

### 11.1 MMLU-Redux

用途：

- 检验选择题 defect taxonomy；
- 有人工 error type；
- 可计算监督指标；
- 覆盖 57 个 subject。

重点缺陷：

- wrong gold；
- no correct answer；
- multiple correct answers；
- bad question clarity；
- bad option clarity；
- expert review。

当前 Pilot 200：

```text
100 clean
100 human-labeled defects
```

### 11.2 GSM8K-Platinum

用途：

- 可执行数学验证；
- 测试 wrong gold；
- 减少专业流派影响；
- 验证 differential solver 和 executable evidence。

### 11.3 ELT-Bench-Verified

用途：

- evaluator 过严/过松；
- transformation output；
- accepted alternatives；
- test-spec mismatch；
- 更接近数据管理方向。

### 11.4 LiveSQLBench / BIRD

用途：

- DB 顶会方向；
- execution consistency；
- SQL equivalent solution space；
- schema、HKB、gold SQL、test case 一致性。

如果缺少公开 defect labels，可作为 discovery study，而不是主监督指标。

### 11.5 SWE-bench Verified

用途：

- 代码类 benchmark；
- reference patch 与 tests；
- evaluator adequacy；
- accepted alternative patches。

执行环境较重，第一阶段可先做 metadata/static sample，再做少量 executable subset。

## 12. 当前 MMLU-Redux 实验结论

当前最新实现包括：

```text
Gold
Question
Option
Presentation
Independent Option Applicability
```

最新实验：

```text
reports/option_applicability_v1_report.json
reports/option_applicability_v1_comparison.json
```

结果：

```text
Confirmed:
precision = 87.5%
recall    = 21.0%

Candidate:
precision = 74.0%
recall    = 77.0%
F1        = 75.5%
```

分类型 candidate recall：

```text
wrong_groundtruth          87.5%
no_correct_answer          92.3%
multiple_correct_answers   75.0%
bad_options_clarity        66.7%
bad_question_clarity       63.3%
expert                     88.9%
```

说明：

- answer-space 检测明显改善；
- Applicability 增加 recall，也带来 review 噪声；
- Presentation 发现的人类未标注格式问题会被 item-level comparison 当成 FP；
- 当前最重要的是 typed evaluation 和候选排序，而不是继续盲目增加 candidate。

## 13. 实验指标应该怎么报告

不能只报告一个 item-level precision/recall。

### 必须报告

```text
confirmed precision / recall / F1
candidate precision / recall / F1
typed precision / recall / F1
per-defect recall
confusion matrix
substantive-only metrics
presentation discovery statistics
operational failure rate
```

### 审核预算指标

```text
Recall@top 5% reviewed
Recall@top 10% reviewed
Recall@top 20% reviewed
```

这比无排序的 candidate recall 更符合真实 benchmark audit 使用方式。

### 成本指标

```text
API calls/item
tokens/item
latency
cost
cache hit rate
```

## 14. Baseline 设计

至少包含：

```text
Random sampling
Single direct LLM audit
Checklist LLM audit
Single Gold Auditor
Blind solve only
Blind + equivalence matcher
Blind + matcher + option applicability
Full structured evidence system
```

如果接入可执行 benchmark，还应加入：

```text
execution-only
metamorphic-only
mutation-only
LLM-only
hybrid system
```

关键实验不是证明强模型会做题，而是：

> 在同一个基础模型下，BenchCore 的结构化证据和多方法框架是否优于直接 LLM audit。

## 15. Ablation 设计

建议消融：

1. 移除 blind solve；
2. 向 solver 暴露 gold；
3. 移除 equivalence matcher；
4. 移除 independent option applicability；
5. 移除 Challenger/Defender；
6. 移除静态规则；
7. 移除 presentation auditor；
8. 不做 contradiction gate；
9. 不区分 confirmed/review；
10. 不区分 substantive/presentation。

## 16. 下一步任务清单

### P0：指标完善

- typed comparison；
- confusion matrix；
- artifact-level metrics；
- review-budget ranking。

### P1：候选排序

建立 risk score：

```text
多方法支持
+ 同类证据一致率
+ accepted option 数
+ uncertain option 数
+ source sensitivity
+ needs_expert
+ contradiction
+ substantive/presentation scope
```

Applicability-only 信号应进入 exploratory review，而不是和多方法支持信号等权。

### P2：跨 benchmark

依次建议：

```text
GSM8K-Platinum
ELT-Bench-Verified
LiveSQLBench/BIRD sample
SWE-bench Verified sample
```

### P3：Accepted Alternatives

优先在 SQL 或 transformation benchmark 上实现：

```text
candidate solution generation
+ execution consistency
+ metamorphic database/input perturbation
+ evaluator replay
```

### P4：Rubric Audit

为 GDPval/APEX/PaperBench 类任务实现：

```text
prompt requirement extraction
rubric criterion extraction
coverage matrix
counterfactual rubric tests
```

### P5：Agent Extension

在核心系统稳定后再增加：

- environment smoke test；
- reference replay；
- tool schema audit；
- state diff；
- trace-score consistency；
- reward-hacking mutation。

## 17. 预期论文贡献

较合理的贡献口径：

1. 一个跨 benchmark 的 canonical artifact schema；
2. 一个 artifact-oriented、根因优先的缺陷 taxonomy；
3. 一个结合规则、执行、metamorphic、mutation 和结构化 LLM evidence 的审计框架；
4. 一个 accepted answer/solution space 验证方法；
5. confirmed、candidate、presentation、operational 的证据分层；
6. 跨数据集监督实验和真实新缺陷 discovery；
7. benchmark artifact graph 上的缺陷归因与修复建议。

不应把贡献表述为：

```text
让 LLM 多问几次，然后多数投票
```

核心应是：

> 把 benchmark audit 建模为跨 artifact 的约束验证、正确解空间检查、证据融合与根因归因。

## 18. 与代码交接文档的关系

Claude 开始协作前，建议依次阅读：

```text
1. CLAUDE_RESEARCH_CONTEXT_zh.md
   理解研究目标、taxonomy、数据集和论文路线

2. CLAUDE_HANDOFF_zh.md
   理解当前代码、实验结果和已知问题

3. DESIGN.md
   理解当前实现的具体设计原则

4. README.md
   获取运行命令
```

在修改代码前应先确认：

- 修改服务于哪一个研究问题；
- 属于哪一个 artifact 和 defect type；
- 产生的是 confirmed、candidate、presentation 还是 operational signal；
- 是否需要新缓存 tag；
- 是否有对应的 baseline、ablation 和监督指标。
