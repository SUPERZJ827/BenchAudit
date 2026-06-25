# BenchCore After623 技术交接说明

## 1. 我们要做什么

目标是构建一个通用 benchmark audit 系统：

```text
任意 benchmark
→ 自动适配核心字段
→ 检查题目、上下文、选项、gold、输出合同、evaluator/rubric
→ 输出 confirmed defects 和 human-review candidates
→ 将缺陷归因到具体 benchmark artifact
```

第一阶段暂不重点处理 agent 环境、工具调用、执行轨迹和 provenance，主要覆盖：

```text
Task Specification
Context / Attachments
Choices / Expected Output
Oracle / Ground Truth
Evaluator / Rubric / Tests
```

系统定位不是直接自动删除所有可疑题，而是：

1. 用高精度 `confirmed` 支持自动修复或强提醒；
2. 用高召回 `candidate/review` 缩小人工审核范围；
3. 保留可重放的静态、执行、变异和 LLM 证据。

## 2. 代码位置

项目目录：

```text
/home/zhoujun/llmdata/after623
```

主要文件：

| 文件 | 作用 |
|---|---|
| `benchcore/adapter.py` | Canonical benchmark adapter |
| `benchcore/field_mapping.py` | 自动识别不同数据集字段 |
| `benchcore/checkers.py` | 基础静态检查 |
| `benchcore/methods.py` | replay、metamorphic、mutation、dataset checks |
| `benchcore/llm_auditor.py` | 所有 LLM 审计阶段 |
| `benchcore/auditor.py` | Checker 调度和跨审计器证据融合 |
| `benchcore/llm_client.py` | OpenAI-compatible API、缓存、重试 |
| `benchcore/taxonomy.py` | 缺陷 taxonomy |
| `benchcore/comparison.py` | 与人工标签比较 |
| `benchcore/report.py` | JSON/Markdown 报告 |
| `scripts/run_mmlu_pilot.py` | MMLU-Redux 一键实验脚本 |

## 3. Canonical 输入

任意 JSONL、JSON 或 CSV 会被统一为：

```text
item_id
task
context
choices
gold
aliases
output_contract
evaluator
metadata
raw
```

人工审核字段如 `error_type`、`verified_gold`、`source_evidence` 不会传给 LLM，
只用于实验结束后的监督评估。

## 4. 已实现的非 LLM 检测

### 基础静态检查

- task 缺失；
- 引用 passage、figure、table、file、database 但上下文缺失；
- 附件路径不可访问；
- 输出格式缺失；
- gold 缺失或无法映射到 choice；
- 重复选项；
- 简单算术与 gold 冲突；
- evaluator 缺失、过严或过松风险；
- alias 被 evaluator 拒绝。

### 多方法检查

- `EvaluatorReplayChecker`
- `MetamorphicAnswerChecker`
- `EvaluatorMutationChecker`
- `ContractConsistencyChecker`
- `TaskIntegrityChecker`
- `ExecutableEvidenceChecker`
- `DifferentialCandidateChecker`
- `DuplicateConflictChecker`
- `SchemaDriftChecker`

`TaskIntegrityChecker` 当前覆盖：

- 时间范围缺失；
- 来源未指定；
- 指令或 blank 截断；
- mojibake；
- Excel 日期转换；
- 少量静态数学格式损坏。

## 5. 当前 LLM 审计链

### 5.1 Structured Gold Audit

当前推荐流程不是直接让模型看 choices 和 gold 做题：

```text
Blind Solver
  隐藏 choices 和 gold，输出开放式答案
        ↓
Answer-to-Option Matcher
  将开放答案与每个选项做语义等价匹配
        ↓
Independent Option Applicability
  独立检查每个选项是否满足题干
        ↓
Programmatic Accepted Answer Set
        ↓
0 个答案      → no_correct_answer
1 个答案      → 与 gold 比较
多个答案      → multiple_correct_answers
不确定选项    → review candidate
        ↓
可疑时启动 Gold Challenger / Gold Defender
```

关键原则：

- “阿贝尔群”和“交换半群”不是等价答案；
- 弱性质、上位类、下位类和相关事实不算 identity answer；
- 但属性型问题中，`2` 和 `3` 可分别满足“哪个数是质数”，即使二者不等价；
- 漏评任何选项时，答案集合进入 uncertain；
- 低置信 option rejection 不直接排除选项；
- Challenger/Defender 不允许删除 Applicability 已发现的 candidate，只决定是否
  能升级为 confirmed。

### 5.2 Question Clarity Auditor

检查：

- answer-changing ambiguity；
- missing condition；
- missing context。

单独的自然语言歧义判断默认进入 review，避免过度确认。

### 5.3 Option Set Auditor

一次检查完整选项集合，输出：

```text
literal_truth
best_answer_status
clarity
equivalence_group
literal_cardinality
best_answer_cardinality
```

用于区分：

- 字面成立但不是最佳答案；
- 真正的多正确答案；
- 无正确答案；
- 选项不清楚。

非 gold 的错误或低质量干扰项，只要不影响答案集合和评分，不应算 substantive
benchmark defect。

### 5.4 Presentation Auditor

检查模型理解过程中发生的隐式修复：

- OCR corruption；
- encoding corruption；
- lost math markup；
- truncation；
- option segmentation；
- format conversion。

即使不影响最终答案也会上报，但单独记为：

```text
defect_type: presentation_corruption
scope: presentation
```

真实验证案例：

```text
1.5 x 1017 meters
→ 模型实际解释为
1.5 × 10^17 meters
```

Presentation Auditor 成功报告缺失指数标记。另一方面，`0.025` 与 `2.5%` 都是
明确数字表示，不应算格式错误。

## 6. Candidate 与 Confirmed

### Confirmed

证据足够强、可自动确认：

- 高置信；
- 不依赖未验证来源或专家约定；
- 不存在相关审计器冲突；
- 或有静态/执行证据。

适合自动修复或强提醒。

### Candidate / Review

值得人工检查但证据不足：

- 单一 LLM 判断；
- 低置信；
- 专业知识或来源依赖；
- Auditor 冲突；
- 不确定选项；
- presentation issue。

当前系统的主要目标应看 candidate 指标，confirmed 作为辅助指标。

## 7. MMLU-Redux Pilot 200

固定实验集：

```text
200 items
100 clean
100 human-labeled defects
```

人工缺陷分布：

```text
bad_question_clarity       30
wrong_groundtruth          24
no_correct_answer          13
bad_options_clarity        12
multiple_correct_answers   12
expert                      9
```

Manifest：

```text
experiments/mmlu_redux_pilot200.manifest.json
```

## 8. 最新实验

实验：

```text
reports/option_applicability_v1_report.json
reports/option_applicability_v1_comparison.json
```

使用：

```text
gold
question
option
presentation
Independent Option Applicability
```

总体结果：

```text
Confirmed:
precision = 0.875
recall    = 0.210
F1        = 0.339

Candidate:
precision = 0.740
recall    = 0.770
F1        = 0.755
```

上一版 `open_match_full`：

```text
Candidate precision = 0.843
Candidate recall    = 0.700
Candidate F1        = 0.765
```

新版变化：

```text
candidate recall:    70% → 77%
candidate precision: 84% → 74%
confirmed recall:    14% → 21%
confirmed precision: 保持 87.5%
```

### 分类型 Candidate Recall

```text
wrong_groundtruth          21/24 = 87.5%
no_correct_answer          12/13 = 92.3%
expert                       8/9 = 88.9%
multiple_correct_answers    9/12 = 75.0%
bad_options_clarity         8/12 = 66.7%
bad_question_clarity       19/30 = 63.3%
```

选项相关缺陷相较上一版明显提升：

```text
multiple_correct_answers: 41.7% → 75.0%
bad_options_clarity:      25.0% → 66.7%
no_correct_answer:        84.6% → 92.3%
```

## 9. 当前主要问题

### 9.1 Applicability 噪声

`llm_option_applicability` 单独结果：

```text
candidate items = 22
TP = 12
FP = 10
precision = 54.5%
```

它提高了选项缺陷召回，但不应和其他 candidate 等权排序。

建议分级：

```text
high-priority candidate:
- Applicability 与 Gold/Option Auditor 相互支持；
- 两个以上选项高置信 acceptable；
- 没有冲突；

exploratory candidate:
- 只有 Applicability 报警；
- uncertain option；
- 依赖严格术语解释或专业约定。
```

### 9.2 Presentation 标签与人工标签不完全对齐

Presentation Auditor 会发现人工标签未标注的真实格式问题，因此默认 item-level
compare 会将部分 presentation finding 计为 false positive。

应分别报告：

```text
substantive metrics
presentation discovery results
```

当前 substantive-only 结果：

```text
Candidate precision = 0.768
Candidate recall    = 0.730
Candidate F1        = 0.749
```

### 9.3 Item-level 不是 Typed Evaluation

当前 compare 只判断：

```text
系统是否认为该题有任意缺陷
vs.
人工是否标注该题非 ok
```

例如人工标注 `bad_question_clarity`，系统预测 `no_correct_answer`，仍算 item-level
命中。

下一步需要实现：

- typed precision/recall/F1；
- defect confusion matrix；
- artifact-level metrics；
- candidate ranking；
- Recall@5%、10%、20% review budget。

### 9.4 Auditor Contradictions

多个 Auditor 对同一题的答案集合判断可能冲突。当前会生成：

```text
auditor_contradiction
scope: operational
```

冲突不会计入 substantive benchmark defect，但会影响 confirmed 升级。

## 10. 已验证案例

### 多正确答案

`mmlu-redux-conceptual_physics-37`

```text
A. steadily in one direction
B. in one direction
```

Independent Option Applicability 判定：

```text
A acceptable
B acceptable
valid_answers = [A, B]
```

最终报告：

```text
multiple_correct_answers
method = llm_option_applicability
review_only = true
```

报告：

```text
reports/conceptual_physics37_applicability_v3_report.md
```

### Presentation corruption

`mmlu-redux-astronomy-33`

```text
1.5 x 1017 meters
```

模型做题时自动理解成：

```text
1.5 × 10^17 meters
```

Presentation Auditor 成功报告四个 lost exponent issues。

报告：

```text
reports/astronomy33_presentation_report.md
```

## 11. 测试状态

当前：

```text
23 tests passed
```

测试覆盖：

- 静态 task integrity；
- presentation corruption；
- 答案等价而非弱蕴含；
- 非等价但独立正确的多个选项；
- 低置信 option rejection；
- 漏评选项；
- Applicability candidate 不被后续角色吞掉；
- LLM null response 重试；
- evidence fusion。

运行：

```bash
python -m unittest discover -s tests -v
```

## 12. 一键运行

当前推荐：

```bash
cd /home/zhoujun/llmdata/after623

python scripts/run_mmlu_pilot.py \
  --tag option_applicability_v2 \
  --auditors all
```

必须使用新 tag，因为 LLM prompt 或检测阶段变化后不能复用旧缓存。

默认模型配置：

```text
configs/llm_deepseek.json
model = deepseek-v4-flash
api_key_env = DEEPSEEK_API_KEY
```

脚本自动运行 audit 和 compare，并生成：

```text
reports/<tag>_cache.jsonl
reports/<tag>_report.json
reports/<tag>_report.md
reports/<tag>_comparison.json
reports/<tag>_comparison.md
```

## 13. 建议 Claude 下一步优先做什么

优先级 1：

```text
实现 typed comparison 和 confusion matrix
```

否则无法准确判断系统预测的缺陷类型是否正确。

优先级 2：

```text
实现 candidate risk score 和 review-budget metrics
```

建议按以下证据加权：

- 多方法同类支持；
- 证据阶段一致率；
- Applicability 中 acceptable 数量；
- uncertain 数量；
- needs_expert；
- source-sensitive；
- auditor contradiction；
- presentation/substantive scope。

优先级 3：

```text
降低 Applicability-only 的 10 个 false positives
```

不要简单删除该模块，因为它显著提高了多答案和选项缺陷召回。应将单模块信号降级
或排序靠后。

优先级 4：

```text
将 presentation scope 从 substantive 指标中默认分离
```

Presentation 问题可单独做 discovery evaluation 或人工抽样验证。

优先级 5：

```text
在其他有人类缺陷标签的 benchmark 上验证通用性
```

不要为 MMLU-Redux 写样本级或学科级硬编码规则。

## 14. 不应破坏的设计原则

1. 不向 LLM 传人工审核标签或 verified gold；
2. 不针对具体题目和知识点硬编码；
3. 非 gold 的坏干扰项若不影响答案集合，不算 substantive defect；
4. Presentation corruption 即使不影响答案，也应单独上报；
5. identity equivalence 与 independent applicability 必须分开；
6. Challenger/Defender 不能删除早期发现的 review candidate；
7. API failure 和 auditor contradiction 属于 operational scope；
8. 论文主结果应同时报告 confirmed、candidate、typed 和 review-budget 指标。
