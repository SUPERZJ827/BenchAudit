# BenchAudit / LLM Evaluation 简历面试准备指南

> 适用项目：`/home/zhoujun/llmdata/after623`  
> 适用简历版本：`简历_BenchAudit_项目描述更新建议.md` 第九节“专门申请 LLM Evaluation 岗位的最终推荐版本”  
> 目标：不是背诵一套包装话术，而是确保简历上的每个名词、数字和设计选择都能由仓库中的代码、测试与实验结果支撑。  
> 范围：本文只围绕当前 BenchAudit/BenchCore 仓库，不要求额外学习其他项目。

---

## 0. 你最终要达到什么状态

准备完成后，你应该能够做到：

1. 用 30 秒、2 分钟和 8 分钟三个版本介绍项目；
2. 不看文档画出从输入文件到 audit report 的完整流程；
3. 解释 task、context、output contract、oracle、evaluator 的区别；
4. 解释 replay、metamorphic testing、mutation testing 分别检查什么；
5. 现场沿着一个 item 讲清楚 checker 如何产生 `Violation`；
6. 解释为什么 QA、SWE、Workspace 和 Terminal 不能共用同一个 gold 假设；
7. 准确解释 `candidate F1=0.914` 和 `structural recall=100%` 的统计口径；
8. 主动说明当前系统还不能完成哪些审计；
9. 如实说明 LLM 在开发中的作用，同时证明自己能验证和维护结果；
10. 在 30–45 分钟内完成一个小 checker、测试或实验设计题。

判断是否准备好的标准不是“代码都背下来了”，而是：

> 面试官随机选择简历中的一句话，你都能给出“问题背景—设计选择—代码位置—实验依据—能力边界”五层回答。

---

## 1. 先把最终简历内容拆成可验证声明

你的最终版本大意是：

```latex
\item \textbf{BenchAudit：LLM/Agent Benchmark 数据质量与评分器审计框架}：
将 benchmark 统一建模为 task、context、output contract、oracle 与 evaluator 等 artifacts，构建自动类型识别与审计计划，适配 QA、SWE-bench、Workspace-Bench 和 Terminal-Bench 的不同评分语义；
实现静态一致性检查、evaluator replay、metamorphic/mutation testing 与结构化 LLM auditor，并通过证据分级区分 confirmed、review 和 unsupported，支持可复现的合成缺陷注入与回归评估；
在 9 个公开评测集上完成实验与消融验证，SVAMP-Platinum candidate F1 达 \textbf{0.914}；针对已定义的 structural mutations，回归召回率达到 \textbf{100\%}，并修复 Agent benchmark 因标量 gold 假设导致的系统性误报。
```

不要把它当一段话背。它实际上包含九个需要独立证明的声明。

| 简历声明 | 必须能解释什么 | 主要代码/证据 |
|---|---|---|
| artifact 统一建模 | 为什么 benchmark 不只是 question/answer | `schema.py`、`package_scan.py` |
| 自动类型识别 | family detection 看什么信号 | `planning.py:detect_benchmark_family` |
| 自动审计计划 | selected/skipped/unsupported 怎样产生 | `planning.py:build_audit_plan` |
| 适配四类 family | 四类 oracle/evaluator 语义差异 | `planning.py`、`cli.py:run_audit` |
| 静态一致性检查 | 五个默认 checker 的职责 | `checkers.py` |
| replay/metamorphic/mutation | 正例、等价正例、错误反例 | `methods.py` |
| 结构化 LLM auditor | 为什么不直接把 gold 给模型判断 | `llm_auditor.py:EvidenceGoldLLMAuditor` |
| 证据分级 | confirmed/review/unsupported 的区别 | `schema.py`、`auditor.py`、`report.py` |
| 两个实验指标 | 样本、标签、分母、限制条件 | `RESULTS.md`、`reports/universal_audit_experiment_20260713/EXPERIMENT_ANALYSIS.md` |

准备时始终用这张表检查自己。任何一项解释不清楚，都应该回到对应代码，而不是继续背更多术语。

---

## 2. 面试必懂的基础概念

### 2.1 Benchmark 是测量系统

最重要的认识：

```text
模型低分
不一定等于
模型能力不足
```

也可能是：

- task 说不清楚；
- 必需 context 不存在；
- output contract 与 evaluator 不一致；
- gold 写错；
- tests 拒绝合理实现；
- tests 没覆盖完整要求；
- environment 本身无法运行。

可以用下面的抽象回答：

```text
模型输出 = M(task, context, environment)
观测分数 = evaluator(模型输出, oracle, output_contract)
```

BenchAudit 检查的是上面这个测量链，而不只是检查数据行格式。

### 2.2 五个核心 artifact

#### Task

模型需要完成的目标和约束。

#### Context

完成 task 所需的 passage、表格、PDF、代码仓库、文件或状态。

#### Output contract

合法输出应该长什么样，例如：

- 单个选项；
- 数字；
- set/compound answer；
- git patch；
- 一组 workspace files。

#### Oracle

“什么算正确”的依据。它可能是：

- MCQ gold label；
- 数值答案；
- reference patch；
- rubric 集合；
- 最终环境状态。

#### Evaluator

把候选输出和正确性依据转换成 pass/fail 或 score 的程序、规则或 tests。

必须能回答：

> Oracle 定义正确性，evaluator 实现判定过程；oracle 可能正确而 evaluator 写错，也可能 evaluator 正常但 oracle 本身错。

### 2.3 Evaluator soundness 与 completeness

这是 LLM Evaluation 面试最值得掌握的一对概念。

```text
错误解通过 -> evaluator 不够 sound / coverage 不足
合理解失败 -> evaluator 不够 complete / 过于严格
```

例子：

- 任务允许任意正确排序算法，测试却要求必须调用 `sorted()`：过严；
- 任务要求同时处理空输入和重复值，测试只检查普通输入：覆盖不足。

### 2.4 Candidate、confirmed、review、unsupported

#### Candidate

系统认为值得调查的缺陷候选，通常追求较高 recall。

#### Confirmed

有足够强的静态、执行或可复现证据；不能只因为 LLM 很自信就自动确认。

#### Review

有信号但还需要人工、专家或环境证据。

#### Unsupported

当前缺 artifact、执行环境或 adapter，无法完成这类检查。

必须说清楚：

> `unsupported` 不等于 clean；没有发现 violation 也不等于 benchmark 没问题。

---

## 3. 你必须能画出的代码执行链

不看代码，练习在纸上画：

```text
JSONL / JSON / CSV
        |
        v
load_rows + infer_mapping
        |
        v
build_items -> BenchmarkItem
        |
        +----------------------+
        |                      |
        v                      v
scan_benchmark_package    add canonical artifacts
        |                      |
        +----------+-----------+
                   v
        detect_benchmark_family
                   |
                   v
          build_audit_plan
                   |
                   v
       profile/family policy composition
                   |
                   v
        build checker + dataset checker list
                   |
                   v
             audit_items
                   |
                   v
          fuse_llm_evidence
                   |
                   v
        build_report -> JSON / Markdown
```

### 对应代码阅读顺序

1. `benchcore/schema.py`
2. `benchcore/field_mapping.py`
3. `benchcore/loader.py`
4. `benchcore/package_scan.py`
5. `benchcore/planning.py`
6. `benchcore/cli.py` 的 `run_audit()`
7. `benchcore/checkers.py`
8. `benchcore/methods.py`
9. `benchcore/auditor.py`
10. `benchcore/report.py`

不要一开始通读两千多行的 `llm_auditor.py`。先把不依赖 LLM 的主链讲清楚，再学习专项链路。

---

## 4. 第一条代码主线：输入如何变成 BenchmarkItem

### 必读文件

- `benchcore/schema.py`
- `benchcore/field_mapping.py`
- `benchcore/loader.py`

### 你应该掌握

`FieldMapping` 记录源字段到 canonical 字段的映射；`BenchmarkItem` 是 checker 使用的统一输入；`Violation` 是统一输出。

不同 benchmark 可能写：

```text
question / prompt / instruction / problem_statement
answer / gold / correct_answer / patch
rubric / evaluator / tests
```

统一 schema 的意义：

- checker 不需要为每个数据集重新解析字段；
- 相同检查逻辑可以跨数据集复用；
- report 和 comparison 有稳定结构；
- family adapter 只负责转换，不负责重复实现审计逻辑。

### 高频追问

#### 为什么还保留 `raw`？

因为 canonical schema 不可能提前覆盖所有 family-specific 字段，例如 SWE 的 `FAIL_TO_PASS`、Workspace 的 `rubrics`、Terminal 的 `task_toml`。`raw` 保留原始证据和扩展能力。

#### 自动字段映射错了怎么办？

CLI 支持显式 mapping JSON；自动推断是便利入口，不应该被当成永远正确的 schema inference。

#### 为什么 metadata 不能传人工 truth label 给 LLM？

会造成 label leakage。人工 truth 只能在 audit 完成后用于 `compare`，不能进入检测 prompt。

### 实操任务

自己创建一个包含以下字段的 JSONL：

```json
{"qid":"1","prompt":"2+2?","options":["3","4"],"label":"B","metric":"choice_match"}
```

然后：

1. 运行 `infer-mapping`；
2. 检查哪些字段没有正确映射；
3. 写一个 mapping JSON；
4. 运行 `canonicalize`；
5. 解释输出中每个字段。

---

## 5. 第二条代码主线：Package scan 与 artifact graph

### 必读文件

- `benchcore/package_scan.py`
- `tests/test_package_scan.py`

### 你应该掌握

`ArtifactKind` 当前覆盖：

- task specification；
- context；
- environment；
- tool protocol；
- interaction protocol；
- output contract；
- oracle；
- evaluator；
- trace；
- provenance；
- unknown。

scanner 记录路径、大小、media type、SHA-256、roles 和推断关系，同时：

- 不跟随 symlink；
- 忽略 `.git`、虚拟环境、cache 等目录；
- 对扫描文件数和单文件大小设上限；
- 对无法解析或超限内容产生 warning；
- 把 item 中内嵌的 artifact 添加为 canonical virtual artifacts。

### 高频追问

#### 为什么需要 SHA-256？

用于 reproducibility、manifest/provenance、变更追踪和防止“同名但内容不同”的实验漂移。

#### 为什么 scanner 不能直接解决任意目录审计？

发现文件角色不等于理解 benchmark execution semantics。scanner 可以 inventory repository，但仍需要 adapter 把 task、environment、tests 和 harness 转换为可执行审计对象。

#### 为什么要报告 unknown？

unknown 是 coverage 信息。如果系统无法识别某文件的作用，就不能暗示该 artifact 已经被检查。

### 现场设计题

如果加入 SQL benchmark，你会如何扩展？

回答框架：

1. scanner 识别 schema、database、query、gold SQL、execution evaluator；
2. adapter 建立 task/context/output/oracle/evaluator；
3. plan 声明需要 DB environment 与执行能力；
4. replay gold SQL；
5. 生成语义等价 SQL 做 completeness test；
6. 生成错误 SQL 做 soundness/coverage test；
7. 在隔离数据库中执行，并记录 query result 和 trace。

---

## 6. 第三条代码主线：Auto family routing 与 AuditPlan

### 必读文件

- `benchcore/planning.py`
- `tests/test_planning.py`
- `benchcore/cli.py:run_audit()`
- `tests/test_universal_cli.py`

### Family detection 看什么

当前综合使用：

- 文件路径和命名；
- record key；
- evaluator type；
- output contract；
- canonical artifact presence。

举例：

| Family | 典型信号 |
|---|---|
| SWE | `problem_statement`、`patch`、`FAIL_TO_PASS`、`swebench_pytest`、`git_patch` |
| Workspace | `rubrics`、`rubric_types`、`file_dep_graph`、`workspace_files` |
| Terminal | `task_toml`、`instruction`、`has_environment`、`terminal_bench_verifier` |

### AuditPlan 的 capability model

每个 `CheckerCapability` 声明：

- `requires_any`；
- `requires_all`；
- `families`；
- `needs_llm`；
- `needs_execution`；
- `evidence_level`；
- `cost_class`。

planner 根据当前 package 和运行能力输出：

```text
selected
skipped
unsupported
```

审计完成后，再把实际运行的方法标记为 `executed`。

### 最重要的历史 bug

旧实现：

- `swebench` profile 清空公共 checker，只运行 solution leak；
- `generic` profile 在 Workspace/Terminal 上要求传统 scalar gold。

后果：

- SWE structural recall = 0%；
- Workspace structural recall = 52.4%；
- Terminal structural recall = 52.9%；
- 原始 Workspace 20/20 和 Terminal 89/89 被错误报告 missing oracle。

修复：

- profile 改为公共 checker 上的 additive/subtractive policy；
- SWE 保留结构检查，再增加 solution leak；
- Workspace/Terminal 只关闭不适用的 scalar gold 假设；
- evaluator/tests/rubric 被视为 agent benchmark 的 oracle 实现；
- auto plan 真正过滤 checker，而不只是写进报告。

结果：

- 三类 family 的已定义 structural mutation recall 均为 100%；
- 原始 Workspace/Terminal 的 missing-oracle 系统性误报归零；
- SWE 原始 20 条仍只有原来的 2 条 solution-leak review，没有新增候选。

### 高频追问

#### 为什么不是把所有 checker 全跑一遍？

因为不适用的语义假设会制造系统性误报；LLM/执行 checker 还有成本和安全约束。正确做法是公共结构检查 + family policy + capability negotiation。

#### Auto 是不是已经支持任意 benchmark？

不是。当前只对四类 family 有明确 routing；未知 family 会回退到 generic/coverage reporting，而不是自动理解所有执行语义。

#### 为什么 auto detection 不自动调用 LLM？

避免静默产生费用和数据外发。LLM 使用必须由显式 flag 或明确 profile 触发。

---

## 7. 第四条代码主线：静态 Checker

### 必读文件

- `benchcore/checkers.py`
- `tests/test_checkers.py`
- `tests/test_answer_contracts.py`

### 五个默认 Checker

#### TaskSpecChecker

检查 task 缺失、截断和部分歧义风险。

#### ContextChecker

检查题目引用 passage/table/file 等 context，但 context 缺失或附件不可访问。

#### OutputContractChecker

检查输出格式、单位和 evaluator/output contract 的显式冲突。

#### OracleChecker

检查 gold 缺失、choice gold 无法映射、重复选项、简单可执行算术与 gold 冲突。

#### EvaluatorChecker

检查 evaluator 缺失、alias 被拒绝、等价格式被 exact evaluator 拒绝等问题。

### 你应该能逐行解释的改进

`EvaluatorChecker` 中：

```text
有 output contract
+ 没有 scalar gold
+ evaluator 缺失
```

对于 agent-style task 仍然是结构性 `missing_evaluator`，因为没有 tests/rubric 就无法判断任务是否成功。

### 为什么静态规则不能包打天下

从最新静态实验可见：

| 数据集 | Precision | Recall |
|---|---:|---:|
| MMLU-Redux 200 | 1.000 | 0.060 |
| GSM8K 100 | 0.200 | 0.100 |
| SVAMP 100 | 1.000 | 0.079 |

这说明：

- 静态规则对可观察结构错误可能很准；
- 对真正的 wrong gold、数学语义和专业知识 recall 很低；
- 关键词规则可能产生噪声，例如 GSM8K unit handling；
- 静态层适合作为便宜、可解释的第一层，而不是全部审计。

### 现场编码练习

实现一个 `EmptyChoiceChecker`：

- 如果 choices 中存在空字符串，产生 `empty_choice` review；
- 如果 gold 指向空选项，提高严重度；
- 写三个测试：正常、空 distractor、gold 指向空选项；
- 思考 defect type 是否已有 taxonomy，如何避免直接 KeyError。

---

## 8. 第五条代码主线：Evaluator replay、metamorphic 与 mutation

### 必读文件

- `benchcore/methods.py`
- `benchcore/evaluators.py`
- `tests/test_multimethod.py`
- `tests/test_integrity_and_fusion.py`

### Evaluator replay

把 evaluator 声明为正确的 gold/alias 重新送入 evaluator。

目标：检查 evaluator 是否至少接受自己的标准答案。

### Metamorphic answer testing

构造语义不变的答案变体：

- `4.62` → `4.620`；
- choice label `B` → 对应 choice text；
- set answer 改变顺序；
- 允许的大小写、空格、格式变化。

目标：发现 evaluator 过严、normalization 不完整。

### Evaluator mutation testing

构造错误答案：

- 改选项；
- 数值扰动；
- 删除 compound answer 的一部分；
- 使用 plausible wrong candidate。

目标：错误答案如果仍通过，说明 evaluator coverage 可能不足。

### 面试时最好使用的解释

```text
Replay 测标准正例；
Metamorphic 测合理等价正例；
Mutation 测错误反例。

三者组合，分别覆盖 evaluator 的基本一致性、completeness 和 soundness。
```

### 高频追问

#### Metamorphic variant 本身生成错了怎么办？

这是该方法的主要风险。variant 必须由 answer contract 约束，只生成语义保持的变换；不确定时降级 review，不能把生成器假设当事实。

#### Gold 能通过 evaluator，为什么还不够？

因为 evaluator 可能只为 gold 特化：它仍可能错杀其他合理解，或放过错误解。

#### Mutation survived 一定说明 evaluator 有 bug 吗？

不一定。mutation 可能没有真正改变语义，或 output contract 允许该形式。需要记录 mutation provenance 并验证它确实是错误解。

### 现场实验设计题

给一个代码 patch benchmark，如何测试 hidden tests 是否过严或覆盖不足？

回答：

1. 重放 gold patch；
2. 生成不同实现方式但功能等价的 alternative patches；
3. 生成只完成部分要求的 minimal incomplete patches；
4. 分别运行 tests；
5. 合理解失败是 over-strict candidate；
6. 不完整解通过是 undercoverage candidate；
7. 检查测试失败 assertion、repo conventions 和 task wording；
8. 在独立环境重复，排除 flakiness。

---

## 9. 第六条代码主线：结构化 LLM Auditor

### 必读范围

不要通读整个文件，先读：

- `EvidenceGoldLLMAuditor`
- `build_blind_user_prompt`
- `build_option_match_user_prompt`
- `build_option_applicability_user_prompt`
- `aggregate_gold_evidence`
- `infer_defect_from_answers`
- `gold_violations`

文件：`benchcore/llm_auditor.py`。

### 为什么不能直接问“gold 对不对”

如果把题目、choices 和 gold 一起展示，模型容易：

- 被 gold 锚定；
- 事后合理化；
- 把选项格式问题误当知识问题；
- 给出不可验证的自由文本判断。

当前 structured pipeline：

```text
Blind solver：隐藏 choices/gold 独立求解
-> answer-to-option matcher
-> option applicability
-> accepted answer set aggregation
-> risk-triggered challenger/defender
-> programmatic defect classification
```

### 它试图区分什么

- `wrong_gold_answer`；
- `no_correct_answer`；
- `multiple_correct_answers`；
- `ambiguous_goal`；
- option/presentation 问题。

### 当前已知失败模式

MMLU clean-source wrong-gold experiment：

- item-level oracle issue：10/10；
- exact wrong-gold subtype：7/10；
- 3/10 被错分为 `no_correct_answer`；
- 50 API calls；
- 95,628 tokens。

根因：accepted answer set 推断与 declared gold 归因混在一起；option applicability 漏认正确选项时，会把 wrong gold 错归为 no correct answer。

### 高频追问

#### 为什么多 auditor 比单次 LLM 更好？

不同 auditor 分解不同任务，例如独立求解、选项匹配、数量关系和展示问题，降低单 prompt 同时处理太多目标的负担。SVAMP/MMLU ablation 显示 structured decomposition 提高 recall。

#### 多 auditor 是否就是独立证据？

不是。相同基础模型、相同输入和相关 prompt 产生的结果高度相关。需要去重 observation、识别冲突，并用执行或原始数据证据确认。

#### 为什么不直接提高 LLM confidence？

confidence 是模型输出或聚合量，不是校准后的事实概率。应使用有标签 validation、reliability analysis 和 evidence quality 进行校准。

#### 下一步怎样修 wrong-gold subtype？

先独立估计 accepted answer set，再比较 declared gold 是否属于该集合；把“答案集合缺陷”和“声明 gold 缺陷”分层，而不是一次投票直接选 defect type。

---

## 10. 第七条代码主线：Workspace、SWE 与 Investigator

### Workspace 必读文件

- `benchcore/artifact_consistency.py`
- `benchcore/investigator.py`
- `benchcore/forensic.py`
- `benchcore/gold_study.py`

### Workspace 的检查关系

```text
task
<-> input files/context
<-> expected output files
<-> rubrics/evaluator
```

可能的问题：

- rubric 要求 task 未要求的内容；
- rubric 所需数据在输入中不存在；
- rubric 写死错误数字；
- output contract 与 rubric 的文件要求冲突；
- rubric 没覆盖 task 的核心义务。

### Investigator 为什么需要多 pass + verifier

初始 LLM auditor 负责高召回发现；investigator 深入查看原始附件和候选证据；独立 verifier 检查引用证据是否真的支持结论。

但是：

- 多 pass 一致只说明稳定；
- 不等于作者确认；
- 依赖未知 harness 行为时必须保持 uncertain/review。

### 一个你应该会讲的 Workspace case

`workspacebench-7` 中 rubric 声明三个文件的目标字节数：

| 文件 | Rubric | 实际 |
|---|---:|---:|
| meeting minutes A | 4,000 | 4,760 |
| meeting minutes B | 4,586 | 5,582 |
| requirements document | 5,613 | 6,511 |

如果任务要求复制当前输入文件，而 rubric 强制错误字节数，则正确复制也无法满足 rubric。这应更准确归为 `rubric_target_error`，而不是泛化的 task-rubric mismatch。

同时有一个 false positive 被 investigator 驳回：task 说“复制文件”本身就隐含内容应与源文件一致，不能因为 task 没逐字写“内容相同”就判 rubric 过严。

### SWE 必读文件

- `benchcore/swe_leak.py`
- `tests/test_swe_leak_checker.py`

当前主要做 gold patch 与 problem statement/hints 的字面泄漏检查。必须主动说明它还不等于完整 contamination audit。

---

## 11. 两个简历数字必须怎样解释

## 11.1 SVAMP-Platinum candidate F1 = 0.914

### 数字来源

`RESULTS.md`：

```text
dataset: SVAMP-Platinum
N: 100
truth defects: 38
BenchCore candidate precision: 0.860
BenchCore candidate recall: 0.974
BenchCore candidate F1: 0.914
best single-pass LLM F1: 0.776
```

对应含义：

- 系统发现约 37/38 个 truth defects；
- candidate 层有一定 false positives；
- structured multi-checker 比单轮 LLM 主要提升 recall；
- 这是 candidate tier，不是 confirmed tier。

### F1 公式

\[
Precision = \frac{TP}{TP+FP}
\]

\[
Recall = \frac{TP}{TP+FN}
\]

\[
F1 = \frac{2PR}{P+R}
\]

### 面试回答模板

> SVAMP-Platinum 实验使用 100 个 item，其中 38 个有人类缺陷标签。BenchCore candidate 层 precision/recall/F1 分别是 0.860、0.974、0.914，主要增益来自 quantity 和 event-state 等结构化 auditor 提高了 recall。这里的 candidate 是送人工复核的高召回层，不代表系统自动确认缺陷的 F1；confirmed tier 更保守。

### 面试官可能继续问

#### 为什么选择 candidate F1，不选择 confirmed？

因为 benchmark audit 的第一目标之一是减少漏检并建立人工复核队列；candidate tier 衡量该队列质量。必须同时报告 confirmed tier，不能把 candidate 当自动确认。

#### n=100 是否太小？

是，置信区间和跨数据集泛化仍有限。因此仓库还做了 MMLU n=200/n=1000、GSM8K 等实验；简历选 SVAMP 是因为它有平衡的代表性结果，不表示所有 family 都达到同样效果。

#### 为什么复现实验是 0.889 而不是 0.914？

LLM audit 存在运行波动；`RESULTS.md` 记录 repro candidate F1=0.889。应该主动承认稳定性问题，并使用 cache、固定配置、多次运行和置信区间管理。

## 11.2 已定义 structural mutations recall = 100%

### 数据范围

9 个评测集：

1. MMLU-Redux；
2. GSM8K；
3. SVAMP；
4. ARC；
5. WikiTableQuestions；
6. ASDiv；
7. SWE-bench；
8. Workspace-Bench；
9. Terminal-Bench。

### Mutation operators

- remove task；
- remove gold；
- wrong gold；
- duplicate choice；
- remove context；
- remove evaluator。

### 为什么区分 structural 和 conditional

`remove_evaluator` 等变换可以由结构直接保证缺陷成立。

`wrong_gold` 依赖原题确实有唯一正确 gold；如果原题本身多解或有错，替换 gold 未必形成单一新缺陷，所以属于 conditional。

### 正确解释

> 修复 auto routing 和 agent evaluator semantics 后，系统对本次定义的 structural mutations 达到 100% recall。这个指标主要用于防止 checker/profile 结构性回归，不代表系统能够找到全部真实语义缺陷；conditional wrong-gold 仍需要 LLM、执行或专家证据。

本轮对应的 structural exact score 是 `3691/3691`。面试中可以报告这个分子/分母，但必须同时说明它来自预先定义的 mutation operators。

### 绝对不能说

```text
BenchAudit 的真实缺陷召回率是 100%。
系统可以发现任意 benchmark 的全部错误。
```

### 为什么 synthetic test 仍然有价值

- 有确定 provenance；
- 分母明确；
- 能自动进入 CI；
- 能精准定位某种 checker/profile 回归；
- 在没有大量人工标注时提供最低 recall guarantee。

### 它不能证明什么

- 未定义 defect family 的 recall；
- 真实数据分布上的 precision；
- 语义 wrong-gold 能力；
- execution environment、trace、contamination 等未覆盖能力。

---

## 12. 仓库 Demo：面试前必须亲手跑通

建议准备一个 3–5 分钟、完全不调用付费 LLM 的 demo。

### 12.1 环境与测试

```bash
cd /home/zhoujun/llmdata/after623
/home/zhoujun/llmdata/.venv/bin/python -m pytest -q
python -m unittest discover tests -q
```

当前预期：

```text
174 passed
73 tests, OK
```

### 12.2 生成 audit plan

```bash
/home/zhoujun/llmdata/.venv/bin/python -m benchcore.cli plan \
  examples/sample_core_benchmark.jsonl \
  --out /tmp/bench_plan.json \
  --md /tmp/bench_plan.md
```

解释：

- family 被识别为 generic；
- plan 显示 selected/skipped/unsupported；
- 没有执行不等于没有选择；
- package coverage 会显示有哪些 artifact。

### 12.3 运行 auto audit

```bash
/home/zhoujun/llmdata/.venv/bin/python -m benchcore.cli audit \
  examples/sample_core_benchmark.jsonl \
  --profile auto \
  --basic-only \
  --progress-every 0 \
  --out /tmp/bench_audit.json \
  --md /tmp/bench_audit.md \
  --print-summary
```

当前 sample 预期：

```text
items: 5
violations: 5
wrong_gold_answer: 1
invalid_choice_gold: 1
missing_context: 1
overstrict_evaluator: 1
inaccessible_attachment: 1
```

### 12.4 Demo 时怎样讲

1. 先展示输入中的五个故意缺陷；
2. 展示 plan，说明为什么只运行当前可支持的 checker；
3. 展示 JSON report 的 `methods_run`；
4. 展示一个 violation 的 artifact、defect_type、confidence、evidence；
5. 展示 unsupported，强调 coverage honesty；
6. 最后说明付费 LLM audit 是显式开启，不会由 auto 静默调用。

### 12.5 Demo 不要做什么

- 不要现场调用真实付费 API；
- 不要使用需要下载的大数据集；
- 不要展示含密钥的 config；
- 不要打开 `reports/` 中未经筛选的大量历史文件；
- 不要把一个 review candidate 说成 confirmed defect。

---

## 13. 面试开场表达

### 13.1 30 秒版本

> BenchAudit 是一个检查 benchmark 本身质量的框架。它把 benchmark 统一表示成 task、context、output contract、oracle 和 evaluator，先自动识别 QA、SWE 或 Agent family，再选择静态规则、evaluator replay、metamorphic/mutation testing 和结构化 LLM auditor。系统强调证据分级，不把 LLM 判断直接当事实。在有标签的 SVAMP pilot 上 candidate F1 是 0.914；在 9 个评测集的已定义结构缺陷回归上达到 100% recall，但这个 100% 不包含真实语义缺陷。

### 13.2 两分钟版本

> 我做这个项目的出发点是：模型低分不一定都是模型能力问题，也可能是 benchmark 的题目、gold、评分器或环境有问题。尤其 code 和 agent benchmark 不再是简单的 question-answer 数据，而是一整套测量系统。
>
> 系统首先把不同数据集映射到统一 BenchmarkItem，同时扫描文件和目录形成 artifact inventory。然后根据字段、evaluator type 和 output contract 自动识别 generic QA、SWE、Workspace 或 Terminal family，AuditPlan 根据已有 artifacts、LLM 和执行能力选择 checker。检查层包括静态一致性、evaluator replay、答案等价变形、错误 mutation 和结构化 LLM audit。最后统一输出 confirmed、review、unsupported，避免把没检查过的部分当成 clean。
>
> 一个代表性改进是，旧 SWE profile 会清空公共 checker，而 Workspace/Terminal 又被错误要求 scalar gold，导致结构漏检和系统误报。改成 additive family policy 后，三个 family 的已定义 structural mutations recall 都恢复到 100%，原始 Agent 样本的 missing-oracle 误报归零。语义层在 SVAMP 上 candidate F1 是 0.914，但复现有波动，且 candidate 不是自动确认层。
>
> 当前最大边界是完整 environment replay、test coverage/over-strictness、trace clustering 和 contamination audit 还没有贯通，所以我把它定位为多证据 benchmark auditing 原型，而不是声称能检查任意 benchmark 的所有问题。

### 13.3 八分钟深讲结构

按下面顺序讲，不要从文件列表开始：

1. 真实问题：benchmark 是测量系统；
2. 一个具体失败例子：Agent 没 scalar gold 不等于没 oracle；
3. artifact schema；
4. auto family routing + AuditPlan；
5. replay/metamorphic/mutation；
6. structured LLM auditor；
7. 两个实验指标及限制；
8. 一个失败实验和你学到什么；
9. 当前边界与下一步。

---

## 14. 高频项目追问与回答要点

### Q1：这个项目和普通数据清洗有什么区别？

数据清洗多关注缺失值、格式、重复；BenchAudit 还检查 task、oracle、evaluator 和 environment 之间的测量有效性，以及合理输出是否被公平评分。

### Q2：为什么需要 LLM？规则不够吗？

规则适合结构事实，但 wrong gold、歧义、rubric 与 task 的语义关系需要推理。SVAMP rules-only recall 接近零，而 structured LLM decomposition 提高了 recall。但 LLM 输出默认是候选证据。

### Q3：为什么不用一个最强模型一次判断？

单 prompt 容易锚定、任务混杂和自由文本不可控。当前分解独立求解、选项匹配、option applicability、数量和状态检查，再程序聚合。

### Q4：为什么 multi-agent/multi-pass 不能直接 confirmed？

它们可能共享模型和信息，错误相关；一致性只是稳定性证据。confirmed 需要静态、执行、原始附件或专家证据。

### Q5：怎样防止人工 truth 泄漏给 auditor？

truth label 只在 audit 完成后由 comparison 使用；prompt payload 会过滤 verified metadata 和注入 provenance 等字段。

### Q6：为什么要保留 output contract？

同一个语义答案可能有多种合法表示。output contract 决定单值、集合、compound、文件或 patch 等输出空间，是 evaluator normalization 的前提。

### Q7：为什么 Agent benchmark 不一定有 gold？

它的 oracle 可能是 rubrics、tests 或最终 state；强行要求 scalar gold 会误报。缺 evaluator 仍然是问题，因为没有判定任务成功的机制。

### Q8：Auto detection 错了怎么办？

允许显式 `--profile` 和 mapping override；report 记录 family confidence 和原因。未知 family 应回退并报告 unsupported，而不是假装理解。

### Q9：怎样衡量 benchmark audit 系统？

至少包括：confirmed precision、candidate recall、coverage、abstention quality、reproducibility、cost/time per item 和 ranking impact。

### Q10：为什么 synthetic mutation 不能代替人工标签？

它只覆盖定义好的变换，且分布可能比真实错误简单。人工标签用于真实 precision/recall；synthetic 更适合回归和已知能力下界。

### Q11：你最大的工程改进是什么？

把 planner 从报告元数据变成真正的 checker selection，并把 profile 从整组替换改为公共 checker 上的 family policy，解决 SWE 漏检和 Agent missing-oracle 误报。

### Q12：你最大的研究发现是什么？

LLM 能提高语义缺陷 recall，但稳定投票不等于正确；必须把 candidate generation、evidence verification 和 confirmation 分开。

### Q13：最明显的失败实验是什么？

wrong-gold 第一版 mutation 改变了 label 表示形式；第二版 sample 又混入原本有缺陷的 item，违反 one-defect premise。这两轮被排除，最终只使用人工 clean source 和 label-preserving mutation。

### Q14：为什么主动讲失败实验？

Evaluation 岗位最关心实验有效性。识别 mutation invalidity、sample contamination 和 label leakage，比只展示最好数字更能证明能力。

### Q15：下一步你会做什么？

优先做 evaluator execution：合理替代解、最小错误解、mutation kill matrix；然后统一 trace schema 和多模型 response matrix。不会继续无目的增加 prompt。

---

## 15. LLM Evaluation 通用技术题，但只用本仓库回答

### 15.1 如何设计一个可靠 eval？

回答框架：

1. 明确 capability 与 target population；
2. 定义 task、context、output contract、oracle、evaluator；
3. 避免 contamination 和 annotation artifacts；
4. 验证 gold 正确；
5. 用合理替代解检查 evaluator completeness；
6. 用错误解检查 soundness/coverage；
7. 做多模型、多次运行和稳定性分析；
8. 报告置信区间、coverage、成本和失败类别；
9. 做 human review 与 ranking impact；
10. 固定版本、环境和 provenance。

### 15.2 LLM-as-a-Judge 有哪些风险？

结合仓库回答：

- gold anchoring；
- prompt/order sensitivity；
- 同源 auditor evidence correlation；
- 难例重复运行翻转；
- 稳定系统性误判；
- confidence 未校准；
- task/rubric/harness 信息不完整；
- judge 可能看见 truth metadata。

缓解：blind stage、structured outputs、cache、重复运行、evidence verifier、原始 artifact grounding、人工 controls、abstention。

### 15.3 Exact match 为什么常有问题？

它可能拒绝：

- 数值等价；
- 单位表达；
- ratio；
- set 顺序变化；
- compound answer 格式；
- choice label 与文本等价；
- 合法 explanatory text。

仓库中的 `evaluators.py`、answer contract 和 metamorphic variants 就是为此设计。

### 15.4 怎样检查 benchmark contamination？

当前仓库只能回答局部方案：

- SWE gold patch/problem statement 字面 overlap；
- provenance/version/hash；
- duplicate/near-duplicate 可扩展。

必须主动说明尚未实现完整训练数据 membership inference、网页/代码历史搜索和时间切分审计。

### 15.5 如何处理多正确答案？

先估计 accepted answer set，再检查 declared gold 是否属于集合；evaluator 应使用 set/denotation semantics，而不是把集合成员误当 aliases。

### 15.6 如何估计没有人工标签时的 recall？

不能直接准确估计。可以：

- synthetic defects 测已定义类型；
- 分层随机抽取 unflagged controls；
- model response matrix 找异常；
- 双人/专家标注；
- capture-recapture 等估计作为研究信号；
- 明确置信区间和假设。

仓库已有 `gold_study.py` 用 flagged + random unflagged controls 建立更合理的人工审查集。

---

## 16. 现场编码与系统设计准备

### 16.1 你至少要亲手完成的四个小改动

#### 练习 A：新增静态 checker

要求：检查 choices 中的空选项。

准备点：

- `Checker` interface；
- `_violation()`；
- taxonomy 注册；
- unit tests；
- severity/review_only 选择。

#### 练习 B：新增 mutation operator

要求：把 output contract 删除。

准备点：

- `_can_apply()`；
- deterministic RNG；
- before/after hash；
- expected defect type；
- structural/conditional grade；
- score exact matching。

#### 练习 C：新增 family hint

要求：通过 `sql_schema`、`gold_sql`、`execution_match` 识别 SQL family。

准备点：

- score-based detection；
- confidence；
- reason；
- explicit override；
- unknown fallback；
- false-positive tests。

#### 练习 D：实现 precision/recall comparison

输入：truth item IDs 与 report violations。

要求：

- 定义 item-level positive；
- TP/FP/FN；
- zero denominator；
- include-method/include-defect filter；
- 输出 confusion examples。

### 16.2 系统设计题：设计任意新 benchmark adapter

统一回答模板：

```text
1. Inventory artifacts
2. Define canonical mapping
3. Identify family semantics
4. Register checker capabilities
5. Build safe execution adapter
6. Replay known-valid solution
7. Generate equivalent valid alternatives
8. Generate invalid/incomplete mutations
9. Collect trace and evidence
10. Calibrate with labels + controls
11. Report coverage/unknown
```

### 16.3 代码质量可能被问到的点

- 为什么 dataclass 而不是任意 dict；
- 如何保证 injection deterministic；
- 为什么不 follow symlink；
- 如何限制文件和执行资源；
- LLM cache 如何保证可复现；
- workers 并发如何保持 item-level isolation；
- 为什么 local runner 默认拒绝；
- AST gate 为什么仍不等于安全 sandbox；
- 如何避免在报告中重复计算同源 observation。

---

## 17. 如何诚实说明“主要借助 LLM 开发”

不要说：

```text
代码基本都是 AI 写的，我不太清楚。
```

也不要假装：

```text
所有代码都是我从零独立手写的。
```

推荐表达：

> 我在实现过程中大量使用了 LLM 辅助代码生成、测试补全和文档整理，但需求分解、实验设计、结果验证和是否接受修改由我负责。这个项目也让我意识到 LLM 生成内容本身需要审计：例如早期 wrong-gold mutation 改变了标签表示、sample 混入已有缺陷，都是通过实验检查而不是相信生成结果发现的。目前我正在加强对核心执行链、evaluator 逻辑和实验统计的独立理解。

如果面试官追问“哪些部分你能独立完成”：

> 我可以独立运行和解释主 CLI 流程、修改基础 checker/mutation、补测试、分析 P/R/F1 和 synthetic recall，并能说明 family routing 的 bug 与修复。复杂 LLM evidence aggregation 和 Workspace 深度 checker 我目前需要结合代码阅读和工具辅助，这是我仍在补强的部分。

这比夸大能力更可信。关键是面试前真的完成第 16 节的四个练习，而不只是背这段回答。

---

## 18. 七天高强度准备计划

每天建议 4–6 小时。每一天都必须包含“读代码、亲手运行、口头复述”三部分。

### Day 1：问题模型与简历数字

阅读：

- 本文第 1、2、11 节；
- `RESULTS.md`；
- `reports/universal_audit_experiment_20260713/EXPERIMENT_ANALYSIS.md` 第 1–4、10 节。

任务：

- 手算一次 P/R/F1；
- 写出 0.914 的 N、truth defects、P/R；
- 写出 synthetic 100% 的分母与不覆盖范围；
- 录制 30 秒介绍三遍。

验收：不看资料解释两个数字，不说错 candidate/confirmed。

### Day 2：Schema、loader 与 checker

阅读：

- `schema.py`；
- `field_mapping.py`；
- `loader.py`；
- `checkers.py`。

任务：

- 手动画 `BenchmarkItem`；
- 跑 mapping/canonicalize；
- 完成 EmptyChoiceChecker 练习；
- 为它写测试。

验收：能从 JSON row 追踪到 Violation。

### Day 3：Package scan、planning 与 CLI

阅读：

- `package_scan.py`；
- `planning.py`；
- `cli.py:run_audit()`；
- 对应 tests。

任务：

- 跑第 12 节 demo；
- 画执行链；
- 给一个 synthetic SQL item 设计 family hint；
- 解释旧 profile bug。

验收：能在 5 分钟内不看代码讲清 auto routing。

### Day 4：Evaluator methods

阅读：

- `evaluators.py`；
- `methods.py`；
- `test_answer_contracts.py`；
- `test_multimethod.py`。

任务：

- 为 numeric、choice、set、compound 各写一个 variant；
- 设计三个 wrong mutations；
- 回答 soundness/completeness；
- 完成“删除 output contract” mutation 练习。

验收：能用一个例子区分 replay/metamorphic/mutation。

### Day 5：LLM auditor 与 evidence

阅读：

- 第 9 节列出的 `llm_auditor.py` 函数；
- `auditor.py`；
- MMLU clean10 report/score。

任务：

- 画 structured gold pipeline；
- 找出 wrong-gold 被分为 no-correct-answer 的链路；
- 写一个两阶段 root-cause 修复方案；
- 解释为什么 vote 不等于 independent evidence。

验收：能回答 LLM-as-a-Judge 风险。

### Day 6：Workspace/SWE 与失败分析

阅读：

- `artifact_consistency.py` 的四个 checker class；
- `investigator.py` 主流程；
- `swe_leak.py`；
- Workspace item7 分析。

任务：

- 讲清字节数 case；
- 讲清被 verifier 驳回的 false positive；
- 列出 SWE checker 的 coverage 和 blind spots；
- 准备一个失败实验 STAR 故事。

验收：不把 likely_true 说成 author-confirmed。

### Day 7：完整模拟面试

上午：

- 从干净终端跑 demo；
- 检查 GitHub README 和公开链接；
- 运行全量测试；
- 准备一页架构图。

下午：

- 30 秒自我介绍；
- 2 分钟项目介绍；
- 8 分钟深讲；
- 随机回答第 14、15 节问题；
- 限时 30 分钟完成一个 checker + tests。

晚上：

- 回看录音；
- 删除自己解释不了的简历词；
- 最终确认所有指标口径。

---

## 19. 十四天稳健准备计划

如果时间允许，把七天计划拆成两周：

| Day | 主题 | 交付物 |
|---:|---|---|
| 1 | Benchmark measurement model | 一页概念图 |
| 2 | 指标与实验口径 | 数字证据卡 |
| 3 | Schema/loader | 自建 mapping demo |
| 4 | Static checker | 新 checker + tests |
| 5 | Package scan | artifact inventory 讲解 |
| 6 | Planning/CLI | 执行链图 |
| 7 | 第一轮模拟 | 问题清单 |
| 8 | Evaluators/answer contract | 四类 answer 示例 |
| 9 | Replay/metamorphic/mutation | 正反例矩阵 |
| 10 | LLM auditor | evidence pipeline 图 |
| 11 | Workspace/SWE | 两个 case study |
| 12 | 代码题/系统设计 | 两道限时练习 |
| 13 | 完整 mock interview | 录音与复盘 |
| 14 | GitHub/demo/简历检查 | 最终面试包 |

---

## 20. 面试前 GitHub 与仓库检查

简历既然放 GitHub 链接，面试官可能在面试前打开仓库。

### 必查

- 使用未登录浏览器确认仓库链接可访问；
- README 第一屏能解释项目是什么；
- 默认分支包含最新 commit；
- 安装和最小 demo 命令可运行；
- 不包含 API key、cache、用户数据和公司材料；
- `reports/`、`datasets/` 和大附件没有进入 Git；
- GitHub 上的项目名 BenchAudit 与代码包名 BenchCore 的关系能解释；
- commit history 不应只有难以理解的临时信息；
- issue/roadmap 不声称未实现能力已经完成。

### 当前核心 commit

```text
6e189b8 Add artifact-aware automatic benchmark auditing
```

### 建议 README 第一屏包含

1. 一句话定位；
2. 支持的 artifacts/families；
3. 一个无 API demo；
4. 当前实验口径；
5. limitations；
6. tests badge 或测试命令。

---

## 21. 面试中绝对不要犯的错误

### 错误 1：把 synthetic 100% 说成真实 recall

正确说法：已定义 structural mutation regression recall。

### 错误 2：把 candidate 当 confirmed

正确说法：candidate 是高召回人工复核队列。

### 错误 3：把 investigator-supported 当作者确认

正确说法：有证据支持的 review candidate，尚未获得 benchmark 作者确认。

### 错误 4：声称已经完整支持任意 benchmark

正确说法：已有 package/planning 底座和四类 routing，新 family 仍需 adapter。

### 错误 5：隐藏复现波动

正确说法：SVAMP 主实验 0.914、repro 0.889；LLM 稳定性是已知问题。

### 错误 6：无法解释为什么使用 LLM

正确说法：LLM 补语义 recall，但不直接作为最终事实来源。

### 错误 7：只讲最好结果，不讲误报

至少准备 GSM8K unit rule 的 4/5 clean false positives 和对应改进方向。

### 错误 8：现场暴露密钥或私有数据

只使用 basic-only demo 和公开 sample。

---

## 22. 最终自测清单

每项给自己打分：

- 0：不会；
- 1：看资料能说；
- 2：不看资料能说；
- 3：能应对连续追问或现场修改。

| 能力 | 目标分 |
|---|---:|
| 解释 benchmark auditing 的意义 | 3 |
| 区分五个核心 artifact | 3 |
| 画完整执行链 | 3 |
| 解释 auto family routing | 3 |
| 解释 selected/skipped/unsupported | 3 |
| 解释五个默认 checker | 2 |
| 解释 replay/metamorphic/mutation | 3 |
| 解释 structured gold auditor | 2 |
| 解释 Workspace oracle semantics | 3 |
| 解释 SVAMP 0.914 | 3 |
| 解释 structural 100% | 3 |
| 解释一次失败实验 | 3 |
| 完成一个 checker + tests | 2 |
| 完成一个 mutation + tests | 2 |
| 运行无 API demo | 3 |
| 说明当前 limitations | 3 |
| 诚实说明 LLM 开发方式 | 3 |

建议总分达到 43/51，并且两个实验数字相关项目必须全部为 3，再正式使用当前技术版简历。

如果不足 35 分，先把简历换成较保守版本；不是因为项目不能写，而是当前描述会触发超出准备程度的追问。

---

## 23. 最终复习卡：面试当天只看这一页

### 项目一句话

> 自动审计 benchmark 这个测量系统，而不是默认题目、gold 和 evaluator 都正确。

### 五个 artifact

```text
task / context / output contract / oracle / evaluator
```

### 三类 evaluator tests

```text
replay = 标准正例
metamorphic = 等价正例
mutation = 错误反例
```

### Auto 的核心

```text
artifact scan
-> family detection
-> capability-aware plan
-> additive/subtractive profile policy
-> executed/skipped/unsupported coverage
```

### 两个数字

```text
SVAMP n=100, truth defects=38
candidate P/R/F1 = 0.860 / 0.974 / 0.914

9 datasets
defined structural mutations recall = 100%
not real-world total recall
```

### 一个成功修复

```text
SWE profile structural 0% -> 100%
Workspace 52.4% -> 100%
Terminal 52.9% -> 100%
Agent missing-oracle systematic FP -> 0
```

### 一个失败实验

```text
invalid gold representation mutation
+ sample already contained defects
-> pilots excluded
-> clean source + label-preserving mutation
```

### 当前边界

```text
full environment replay
test kill matrix / coverage
trace clustering
response matrix / IRT
complete contamination audit
arbitrary family adapters
```

### 最后一句

> 我追求的不是让 LLM 宣判 benchmark 对错，而是让每个 finding 都有证据等级，让每个没有检查的部分都被明确报告。
