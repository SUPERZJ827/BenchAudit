# 第一批 Benchmark 抽样实验选择建议

更新时间：2026-06-23

## 1. 结论

先做小规模、多 benchmark、核心 artifact 覆盖实验是合理的。

当前建议聚焦 5 个核心组件：

```text
Task Specification
Context / Attachments
Expected Output / Answer Contract
Oracle / Ground Truth
Evaluator / Rubric / Tests
```

暂时弱化或不做：

```text
Environment
Tools
Interaction
Trace
Provenance
```

原因是第一阶段目标不是构建完整 agent harness，而是验证：

1. 这些核心 artifact 是否足以覆盖多数 benchmark 质量问题；
2. 我们的 taxonomy 是否能跨 benchmark 工作；
3. 哪些缺陷能靠规则/执行/一致性检测发现；
4. 哪些缺陷只能进入 review；
5. 是否能比直接 LLM audit 或随机抽检更有效。

## 2. 第一批实验的选择原则

优先选择满足下面条件的数据集：

1. **有公开数据或容易本地准备**；
2. **有人工修订、verified subset 或已知缺陷标签**，方便算 precision / recall；
3. **覆盖不同任务形态**，不能只做选择题；
4. **不强依赖复杂 GUI/OS/浏览器环境**；
5. **能映射到 5 个核心 artifact**；
6. **每个 benchmark 先 sample，不急着全量跑**。

## 3. 推荐第一批 Benchmark

## 3.1 强推荐：MMLU-Redux

来源：

- Paper: https://arxiv.org/abs/2406.04127
- Dataset: https://huggingface.co/datasets/edinburgh-dawg/mmlu-redux-2.0

任务类型：

```text
多学科选择题
```

核心 artifact：

| 组件 | 对应字段 |
|---|---|
| Task Specification | question, subject |
| Context | 通常为空，部分题目含题干背景 |
| Expected Output | 单选 A/B/C/D |
| Oracle | original gold, verified gold, error type |
| Evaluator | exact match / normalized choice matching |

适合检测的问题：

- `wrong_gold_answer`
- `multiple_correct_answers`
- `no_correct_answer`
- `ambiguous_goal`
- `missing_condition`
- `option_ambiguity`
- `hidden_assumption`

为什么适合第一批：

- 有 5,700 条人工重标注问题；
- 有明确错误类型；
- 覆盖 57 个 subject；
- 之前已有本地代码基础；
- 非常适合验证 taxonomy 和指标。

建议抽样：

```text
stratified-570: 每个 subject 10 条
stratified-1140: 每个 subject 20 条
targeted-error-sample: 每种人工 error type 至少抽 30 条
```

建议实验目标：

- 先跑 stratified-570；
- 再跑 targeted-error-sample；
- 对比 random sampling、direct LLM auditor、checklist LLM auditor。

## 3.2 强推荐：GSM8K-Platinum / PlatinumBench 数学修订样本

来源：

- PlatinumBench project: https://platinum-bench.csail.mit.edu/
- GitHub: https://github.com/MadryLab/platinum-benchmarks
- Hugging Face: https://huggingface.co/datasets/madrylab/platinum-bench

任务类型：

```text
小学数学 word problem / short-answer reasoning
```

核心 artifact：

| 组件 | 对应字段 |
|---|---|
| Task Specification | math word problem |
| Context | 通常为空 |
| Expected Output | final numeric answer |
| Oracle | original answer, revised/platinum answer |
| Evaluator | numeric exact match / normalized answer matching |

适合检测的问题：

- `wrong_gold_answer`
- `output_format_overstrict`
- `missing_accepted_alternatives`
- `unit_or_scale_ambiguity`
- `evaluator_defect`

为什么适合第一批：

- 数学题相对少受学科流派影响；
- 可用 executable evidence / symbolic calculation；
- 适合验证 oracle checker；
- 比 MMLU 更容易形成硬证据。

建议抽样：

```text
platinum-revised-100: 从 revised/error 样本中抽 100
platinum-clean-100: 从 aligned/clean 样本中抽 100
```

建议实验目标：

- 检查系统是否能发现 gold answer defect；
- 检查是否误报 clean 样本；
- 对比强模型、多采样、python/sympy 辅助验证。

## 3.3 强推荐：ELT-Bench / ELT-Bench-Verified

来源：

- ELT-Bench-Verified: https://arxiv.org/abs/2603.29399
- Original benchmark: https://github.com/uiuc-kang-lab/ELT-Bench

任务类型：

```text
data transformation / extraction-loading-transformation tasks
```

核心 artifact：

| 组件 | 对应字段 |
|---|---|
| Task Specification | data transformation instruction |
| Context | input files / tables |
| Expected Output | transformed output |
| Oracle | expected output / verified correction |
| Evaluator | scripts / exact output / transformation tests |

适合检测的问题：

- `overstrict_evaluator`
- `wrong_gold_answer`
- `ambiguous_goal`
- `test_spec_mismatch`
- `missing_accepted_alternatives`
- `output_format_overstrict`

为什么适合第一批：

- 它天然就是 benchmark quality issue 研究对象；
- 很适合验证 evaluator 过严/过松；
- 比纯选择题更接近数据管理和 DB 顶会口味；
- 仍然不需要复杂 GUI/OS 环境。

建议抽样：

```text
verified-error-100: 从 verified 修订问题中抽 100
clean-or-uncertain-100: 从未修订或人工认为 ok 的样本中抽 100
```

建议实验目标：

- 重点测试 evaluator/rubric/test 类缺陷；
- 尝试 execution consistency 和 accepted alternative 检测；
- 对比 original evaluator 与 verified evaluator。

## 3.4 推荐：LiveSQLBench / BIRD 类 Text-to-SQL

来源：

- LiveSQLBench: https://livesqlbench.ai/
- BIRD benchmark: https://bird-bench.github.io/
- BIRD-INTERACT: https://arxiv.org/abs/2510.05318

任务类型：

```text
Text-to-SQL / database question answering / DB agent
```

核心 artifact：

| 组件 | 对应字段 |
|---|---|
| Task Specification | natural language query |
| Context | database schema, tables, HKB / metadata |
| Expected Output | SQL or query result |
| Oracle | gold SQL / expected result |
| Evaluator | SQL execution / test cases / result comparison |

适合检测的问题：

- `gold_sql_error`
- `context_oracle_conflict`
- `missing_condition`
- `ambiguous_goal`
- `missing_accepted_alternatives`
- `overstrict_evaluator`
- `underconstrained_evaluator`
- `context_version_mismatch`

为什么适合第一批：

- 非常贴合 DB 方向；
- 有天然 execution evidence；
- 可以借鉴 execution consistency；
- SQL 等价问题正好对应 accepted alternatives。

建议抽样：

```text
sql-dev-100: 从 dev/public split 抽 100
sql-hard-100: 从复杂 SQL / multi-table / HKB 任务抽 100
```

注意：

- 如果没有人工 defect labels，第一阶段可作为 discovery/case study；
- 如果能找到官方 verified / hidden test 或修订记录，则优先使用。

建议实验目标：

- 先跑 schema/context/oracle/evaluator consistency；
- 再跑 SQL execution consistency；
- 检查 gold SQL 与自然语言、HKB、执行结果是否一致。

## 3.5 推荐：SWE-bench Verified / SWE-bench Lite

来源：

- SWE-bench: https://www.swebench.com/
- SWE-bench Verified: https://www.swebench.com/verified.html
- Dataset: https://huggingface.co/datasets/SWE-bench/SWE-bench

任务类型：

```text
GitHub issue -> code patch
```

核心 artifact：

| 组件 | 对应字段 |
|---|---|
| Task Specification | problem_statement, issue |
| Context | repository, base commit, files |
| Expected Output | patch |
| Oracle | reference patch, test_patch, FAIL_TO_PASS / PASS_TO_PASS |
| Evaluator | unit tests |

适合检测的问题：

- `test_spec_mismatch`
- `overstrict_evaluator`
- `underconstrained_evaluator`
- `missing_accepted_alternatives`
- `invalid_reference_solution`
- `underspecified_success_criteria`

为什么适合第一批：

- 代表代码类 benchmark；
- Verified subset 有人工验证；
- 任务结构很标准；
- 但完整执行环境较重。

建议抽样：

```text
verified-metadata-100: 先只做 metadata/spec/oracle/evaluator 静态审计
lite-executable-20: 选择可快速运行的 20 条做 execution replay
```

注意：

- 如果当前阶段不做 environment，就不要把 SWE-bench 放在主指标里；
- 可以作为“代码类核心 artifact”案例，而不是第一阶段主战场。

## 3.6 可选：GAIA Dev

来源：

- Dataset: https://huggingface.co/datasets/gaia-benchmark/GAIA

任务类型：

```text
tool-augmented QA with files / browsing / multimodal attachments
```

核心 artifact：

| 组件 | 对应字段 |
|---|---|
| Task Specification | Question |
| Context | attachments / files |
| Expected Output | final answer |
| Oracle | final answer |
| Evaluator | normalized exact answer |

适合检测的问题：

- `missing_context`
- `inaccessible_attachment`
- `output_format_overstrict`
- `stale_external_context`
- `gold_requires_hidden_knowledge`

为什么作为可选：

- 很适合 context / attachment 审计；
- 但缺少公开的 benchmark defect labels；
- 很多问题依赖外部搜索和多模态能力。

建议抽样：

```text
gaia-dev-50: 只做 attachment/context/output contract discovery
```

## 3.7 暂不推荐第一批：GDPval / APEX / EnterpriseClawBench / PaperBench

这些 benchmark 很重要，但不适合作为第一批主实验。

原因：

- rubric / deliverable 复杂；
- gold deliverable 和专家评分可能不完全公开；
- 自动评价依赖 LLM judge 或专家；
- 很难快速算 precision / recall；
- 更适合第二阶段做 case study。

可作为第二阶段：

```text
rubric-prompt coverage
deliverable contract audit
judge bias probe
evidence sufficiency audit
```

## 4. 第一批推荐组合

## 4.1 最稳组合

```text
MMLU-Redux
GSM8K-Platinum / PlatinumBench
ELT-Bench-Verified
LiveSQLBench or BIRD dev
SWE-bench Verified metadata subset
```

覆盖关系：

| Benchmark | Task | Context | Output | Oracle | Evaluator | 有无人工标签 |
|---|---|---|---|---|---|---|
| MMLU-Redux | 强 | 弱 | 强 | 强 | 简单 | 强 |
| GSM8K-Platinum | 强 | 弱 | 强 | 强 | 简单/可执行 | 强 |
| ELT-Bench-Verified | 强 | 强 | 强 | 强 | 强 | 强 |
| LiveSQLBench / BIRD | 强 | 强 | 强 | 强 | 强 | 弱/视数据而定 |
| SWE-bench Verified | 强 | 强 | 强 | 中 | 强 | verified，但不是完整缺陷标签 |

这个组合的好处：

- 有选择题、数学、数据转换、SQL、代码；
- 有至少 3 个可以算指标的数据源；
- 有 DB/data management 方向；
- 不完全依赖 LLM；
- 可以测试 accepted alternatives / execution consistency。

## 4.2 更偏 DB / AI 顶会的组合

```text
MMLU-Redux
ELT-Bench-Verified
LiveSQLBench
BIRD / BIRD-INTERACT public split
GSM8K-Platinum
```

这个组合更强调：

- benchmark 数据质量；
- SQL / DB / data transformation；
- evaluator / oracle / context consistency；
- execution-backed evidence。

## 5. 建议抽样规模

第一阶段不要全量。

建议：

| 阶段 | 每个 benchmark 数量 | 目的 |
|---|---|---|
| smoke | 20-50 | 看字段适配、输出格式、明显 bug |
| pilot | 100-200 | 初步指标、案例分析 |
| stratified | 500-1000 | 稳定比较、论文表格 |
| targeted | 每类错误 30-50 | 分析不同 defect type 的召回和误报 |

推荐启动顺序：

```text
1. MMLU-Redux 200
2. GSM8K-Platinum revised/clean 各 100
3. ELT-Bench-Verified 100
4. LiveSQLBench/BIRD 100
5. SWE-bench Verified metadata 100 + executable 20
```

## 6. 每个样本统一跑哪些检查

围绕 5 个核心 artifact，建议每条样本输出同一种 audit record。

```json
{
  "item_id": "...",
  "benchmark": "...",
  "task_type": "...",
  "artifact_coverage": {
    "task_specification": true,
    "context_attachment": true,
    "expected_output": true,
    "oracle_ground_truth": true,
    "evaluator": true
  },
  "violations": [],
  "review_signals": [],
  "candidate_alternatives": [],
  "execution_evidence": {},
  "needs_expert": false
}
```

基础检查：

1. `TaskSpecChecker`
   - 是否目标清楚；
   - 是否缺少 answer-changing condition；
   - 是否存在互相冲突的约束。

2. `ContextChecker`
   - 引用的 passage/table/image/file/db 是否存在；
   - context 与 oracle 是否冲突；
   - schema/HKB/gold 是否一致。

3. `OutputContractChecker`
   - 输出格式是否明确；
   - evaluator 是否过度依赖表面格式；
   - 是否有 accepted alternatives。

4. `OracleChecker`
   - gold 是否被 task/context 支持；
   - 是否存在多个正确答案；
   - 是否没有正确答案。

5. `EvaluatorChecker`
   - evaluator 是否过严；
   - evaluator 是否过松；
   - 是否和 task success criteria 对齐；
   - 是否能接受 execution-consistent alternatives。

## 7. 第一批应该报告哪些指标

对于有人工标签的数据：

```text
item precision
item recall
typed precision
typed recall
candidate recall
candidate precision
candidate recall @ budget
by defect type recall
```

对于没有人工标签的数据：

```text
candidate rate
confirmed defect count
manual validation precision
defect distribution
artifact distribution
case study
```

还建议新增：

```text
artifact coverage
execution-evidence ratio
LLM-only vs execution-backed defect ratio
review-required ratio
```

## 8. 是否存在问题

这个实验设计本身没有大问题，但有三个风险要提前控制。

## 8.1 不同 benchmark 的 ground truth 不同

MMLU-Redux 有人工缺陷标签；LiveSQLBench/BIRD 可能没有 benchmark defect labels；SWE-bench Verified 是 verified subset，不等于完整错误标签。

解决：

```text
把实验分成 supervised evaluation 和 discovery evaluation。
```

## 8.2 不同 benchmark 的 evaluator 差异很大

选择题 exact match、数学 numeric match、SQL execution、代码 unit tests 完全不同。

解决：

```text
统一 audit record，不强行统一 evaluator 实现。
```

## 8.3 不做环境会限制 agent benchmark 覆盖

SWE-bench、WebArena、Terminal-Bench 的很多问题来自环境。

解决：

```text
第一阶段明确只做 core artifact audit。
环境作为 extended artifact，后续扩展。
```

## 9. 最终建议

第一批最推荐先做：

```text
MMLU-Redux
GSM8K-Platinum
ELT-Bench-Verified
LiveSQLBench / BIRD
SWE-bench Verified metadata subset
```

其中：

- MMLU-Redux 用来验证分类题/专业题；
- GSM8K-Platinum 用来验证数学 oracle；
- ELT-Bench-Verified 用来验证 evaluator 和 output contract；
- LiveSQLBench/BIRD 用来验证 DB / SQL execution consistency；
- SWE-bench Verified 用来证明框架能映射到代码 benchmark，但第一阶段不深做环境。

如果时间有限，最小可行组合是：

```text
MMLU-Redux + GSM8K-Platinum + ELT-Bench-Verified + LiveSQLBench/BIRD
```

这四个已经足够覆盖大多数核心 benchmark artifact。

## 10. 参考来源

- MMLU-Redux / Are We Done with MMLU?: https://arxiv.org/abs/2406.04127
- MMLU-Redux dataset: https://huggingface.co/datasets/edinburgh-dawg/mmlu-redux-2.0
- PlatinumBench: https://platinum-bench.csail.mit.edu/
- PlatinumBench GitHub: https://github.com/MadryLab/platinum-benchmarks
- ELT-Bench-Verified: https://arxiv.org/abs/2603.29399
- ELT-Bench GitHub: https://github.com/uiuc-kang-lab/ELT-Bench
- LiveSQLBench / Data Intelligence Index: https://livesqlbench.ai/
- BIRD benchmark: https://bird-bench.github.io/
- BIRD-INTERACT: https://arxiv.org/abs/2510.05318
- SWE-bench: https://www.swebench.com/
- SWE-bench Verified: https://www.swebench.com/verified.html
- SWE-bench dataset: https://huggingface.co/datasets/SWE-bench/SWE-bench

