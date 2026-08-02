# Auto Benchmark Auditing：从原理、代码到研究表达的完整学习指南

> **学习版历史快照（2026-07-13）：** 原理章节仍可学习；最新实现、Workspace
> 复现实验、统计口径和“可以/不能对外说什么”请以
> [`BENCHAUDIT_NEAR_FINAL_WORKSPACEBENCH_EXPERIMENT_20260714_zh.md`](BENCHAUDIT_NEAR_FINAL_WORKSPACEBENCH_EXPERIMENT_20260714_zh.md)
> 为准。

> 更新日期：2026-07-13  
> 对应项目：`/home/zhoujun/llmdata/after623`  
> 阅读目标：真正理解“自动查 benchmark 的问题”在解决什么、为什么困难、BenchCore 当前怎样实现、实验说明了什么，以及如何用很短的话向别人讲清楚。  
> 研究范围：本文讨论的是 **benchmark auditing（审计评测工具本身）**，不是普通的“用 benchmark 测模型”。

---

## 阅读导航

- **第一次学习**：按顺序阅读第 0–6 节，先建立问题模型，再理解代码和实验。
- **补研究背景**：阅读第 7–8 节，每篇论文只记住“问题—方法—结论—启示”。
- **准备汇报/答辩**：直接阅读第 11–12 节，练习一句话、30 秒和三分钟版本。
- **检查是否真正掌握**：完成第 14 节自测题，再回看不会的代码模块。
- **规划后续开发**：阅读第 9–10 节，区分已经实现、尚未实现和下一优先级。

---

## 0. 先记住这五句话

如果暂时没有时间读全文，先记住下面五句：

1. **Benchmark 是测量 AI 能力的仪器；benchmark auditing 是在使用仪器前，先校准仪器。**
2. 一个 benchmark item 不只有题目和答案，还包括输入、输出契约、oracle、evaluator、环境和运行轨迹；这些部分任何一个出错，最终分数都可能失真。
3. 自动审计不能只问一次 LLM“这题有错吗”，而应组合静态规则、artifact 交叉检查、evaluator 重放、变形/反例测试、模型响应统计、执行轨迹和人工复核。
4. 系统必须区分 `confirmed`、`review`、`unsupported`：发现候选不等于证明缺陷，没有发现也不等于 benchmark 没问题。
5. BenchCore 当前已经做好了自动 family routing、结构检查、部分 evaluator/LLM/rubric 审计和合成缺陷回归；真正尚未完成的是任意 family 的安全环境重放、test coverage/over-strictness、trace analysis 和污染证据。

一句最短定义：

> **我们的工作，是自动检查“题目—输入—正确结果—评分器—执行环境”是否共同构成一个公平、可解、可重复的能力测量。**

---

## 1. 为什么需要审计 benchmark

### 1.1 Benchmark 不是数据表，而是测量系统

通常大家把 benchmark 想成：

```text
question + answer
```

但真实评测，尤其是 code/agent benchmark，更接近：

```text
任务说明 T
+ 上下文/附件 C
+ 环境与工具 H
+ 输出契约 O
+ 正确性依据/Oracle G
+ 评分器 E
+ 模型尝试与运行轨迹 R
--------------------------------
= 最终观测分数 S
```

可以把一个 item 抽象为：

\[
B_i = (T_i, C_i, H_i, O_i, G_i, E_i, R_i, P_i)
\]

其中 `P` 是 provenance/version，即数据来源、版本和时间信息。某个模型 `M` 的得分不是天然真理，而是：

\[
S_i = E_i(M(T_i,C_i,H_i), G_i, O_i)
\]

因此低分至少有两种完全不同的解释：

- 模型没有完成一个有效任务；
- 测量系统本身有问题，错误地拒绝了合理答案，或者错误地接受了不完整答案。

Benchmark auditing 的核心任务，就是尽量把第二类“测量误差”从第一类“能力不足”中分离出来。

### 1.2 四个直观例子

#### 例 1：错误 gold

题目是 `2 + 2 = ?`，选项中 `B=4`，但 gold 写成 `C`。模型回答正确仍会被判错。这是 oracle defect。

#### 例 2：测试过严

任务要求“实现功能 X”，模型实现功能正确，但隐藏测试强制某个题面没有要求的内部函数名。合理实现被拒绝，这是 overly strict evaluator。

#### 例 3：测试覆盖不足

任务要求完成 A、B、C，测试只检查 A。只做三分之一的错误解也能通过，这是 evaluator undercoverage。

#### 例 4：agent benchmark 没有标量答案

Workspace/Terminal 任务通常要求创建文件或改变环境状态，其 oracle 是 rubrics/tests/state verifier，而不是一条 `gold="..."`。如果通用规则看到没有 gold 就报错，错的是审计器对 family semantics 的理解。

这四个例子对应本项目最重要的认识：

> **不能脱离 benchmark family 和执行语义，机械检查字段是否存在。**

---

## 2. 到底要检查哪些问题

### 2.1 Artifact 视角

BenchCore 把 benchmark 拆成十类 artifact。前五类是当前 item 审计的主干，后五类是走向通用 agent auditing 必须补齐的部分。

| Artifact | 要回答的问题 | 常见缺陷 |
|---|---|---|
| Task specification | 到底要求做什么？ | 缺失、歧义、矛盾、隐含要求、截断 |
| Context / attachment | 解题所需信息是否存在且可访问？ | 丢文件、错版本、表格/PDF 损坏、引用不存在 |
| Expected output | 合法输出是什么？ | 格式不清、多文件契约冲突、选项重复 |
| Oracle / ground truth | 什么结果算正确？ | 错 gold、多正确答案、无正确答案、reference 错误 |
| Evaluator / tests / rubric | 如何把输出变成分数？ | 过严、覆盖不足、拒绝等价答案、错误 rubric target |
| Environment | 任务运行在什么状态？ | 依赖缺失、镜像错误、版本冲突、非确定性 |
| Tool/action space | agent 能做什么？ | 工具缺失、权限与任务不匹配、协议错误 |
| Interaction protocol | 如何交互和终止？ | 隐藏步骤、终止条件错误、状态不可达 |
| Trace/attempt | 模型在哪里以及为什么失败？ | 共同失败点、环境异常、评分器异常 |
| Provenance/version | 数据从哪里来、是否被污染？ | 版本漂移、重复、训练泄漏、来源不可追溯 |

### 2.2 五个质量性质

检查具体 defect 之前，可以先用五个更稳定的质量性质组织思考。

#### 完整性 Completeness

完成任务所必需的说明、输入、环境和评分规则是否齐全？

#### 一致性 Consistency

Task、context、output contract、gold 和 evaluator 是否彼此一致？

#### 可解性 Solvability

是否至少存在一个在给定信息和环境中能够满足要求的合理解？

#### 评分健全性 Evaluator soundness

明显错误或不完整的解是否会被 evaluator 拒绝？如果错误解通过，说明测试覆盖不足。

#### 评分完备性 Evaluator completeness

所有符合题意的合理替代解是否都能通过？如果合理解被拒绝，说明测试过严或输出契约过窄。

这里很容易混淆两个方向：

```text
合理解被拒绝  -> evaluator 太严 / 不完备
错误解被接受  -> evaluator 太松 / 不健全
```

这正是 evaluator audit 为什么必须同时构造正例和反例。

---

## 3. 为什么“让 LLM 看一遍”不够

### 3.1 LLM 能发现语义问题，但不是事实数据库

LLM 很适合：

- 理解 task 与 rubric 的自然语言关系；
- 提出可能的歧义、遗漏和合理替代解；
- 阅读代码、测试和运行轨迹，形成调查假设；
- 把不同 artifact 的矛盾组织成人可读证据。

但 LLM 也会：

- 把自己不懂的问题误判为题目错误；
- 在同一证据上多次给出不同结论；
- 多次稳定地产生同一种系统性误判；
- 在看到 gold 后产生锚定和事后合理化；
- 不知道真实 harness 的隐藏行为，却把猜测写得很确定。

因此本项目采用的原则不是“不要 LLM”，而是：

> **让 LLM 负责提出和组织语义假设，让静态事实、执行结果、原始附件、provenance 或人工专家负责确认。**

### 3.2 投票稳定不等于正确

如果同一个 LLM 连续 30 次都说某 rubric 有错，只能证明判断稳定，不能单独证明 rubric 真错。模型可能共享同一个误解。

本项目 Workspace 实验已经出现过这种现象：简单客观错误较稳定，难例位于决策边界；也存在非缺陷被模型稳定误判。正确做法是：

```text
多次独立判断
-> 看一致性与分歧
-> 回到原始文件/代码/测试找证据
-> 独立 verifier 复核
-> 仍依赖未知 harness 时保持 review/uncertain
```

---

## 4. 一个可靠自动审计系统应怎样工作

下面是 BenchCore 当前架构和理想架构的共同主线：

```text
Benchmark file / directory / repository
        |
        v
1. Package scan：发现文件并分类 artifact
        |
        v
2. Canonicalization：把不同字段归一成 BenchmarkItem
        |
        v
3. Family detection：识别 QA / SWE / Workspace / Terminal / unknown
        |
        v
4. Audit planning：根据 artifact、family、LLM/执行能力选择 checker DAG
        |
        v
5. Layered checks
   静态规则 -> 交叉一致性 -> replay/metamorphic/mutation
   -> LLM semantic audit -> trace/response statistics -> investigator
        |
        v
6. Evidence fusion：冲突降级、根因归类、confirmed/review/unknown
        |
        v
7. Calibration：人工标签、clean control、synthetic defects、ranking impact
```

最重要的不是 checker 数量，而是这条链上的三个闭环：

1. **选择闭环**：输入是什么，就选择适合它的检查；
2. **证据闭环**：一个候选要能回到具体 artifact 或执行证据；
3. **校准闭环**：系统必须知道自己能检出什么、会误报什么。

---

## 5. BenchCore 代码是怎样实现这条链的

### 5.1 输入归一化：先让不同 benchmark 说同一种语言

关键文件：

- `benchcore/loader.py`
- `benchcore/field_mapping.py`
- `benchcore/schema.py`
- `benchcore/adapter.py`

不同数据集可能使用 `question`、`prompt`、`instruction` 或 `problem_statement` 表示 task；使用 `answer`、`gold` 或 `patch` 表示 oracle。字段推断先把它们映射为统一的 `BenchmarkItem`：

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

为什么一定要 canonical schema？因为 checker 不应该为每个数据集重新写一套“读取字段”的逻辑。统一 schema 让检查算法与数据来源解耦。

边界也要说清楚：当前 loader 能直接加载 JSONL/JSON/CSV；package scanner 虽然能扫描任意目录，但还不能自动把任意 repository 解析成可审计 item。新 family 仍可能需要 adapter。

### 5.2 Package scan：把目录看成 artifact graph

关键文件：`benchcore/package_scan.py`

scanner 会递归 inventory 文件，记录：

- 相对路径、大小、media type、SHA-256；
- artifact kind；
- 文件之间推断出的关系；
- 超大文件、截断扫描和未知角色等 warning；
- canonical item 中内嵌的 task/context/oracle/evaluator 虚拟节点。

它的价值不只是“列文件”，而是防止下面这种错误结论：

> 报告没有发现问题，但其实测试目录、附件或环境文件根本没有被读取。

### 5.3 Family detection：理解“答案”在不同 benchmark 中是什么

关键文件：`benchcore/planning.py` 中的 `detect_benchmark_family()`。

当前 detection 同时看：

- 路径和文件名，如 tests、rubric、problem statement；
- record keys，如 `FAIL_TO_PASS`、`rubrics`、`task_toml`；
- evaluator type，如 `swebench_pytest`、`workspacebench_rubric`、`terminal_bench_verifier`；
- output contract，如 `git_patch`、`workspace_files`、`terminal_task`。

当前可路由：

| Family | Oracle 语义 | 特有检查 |
|---|---|---|
| generic | gold/answer/choices | 通用 task、context、gold、evaluator 方法 |
| swebench | reference patch + tests | 公共结构检查 + solution leakage |
| workspacebench | rubrics + output state | 关闭标量 gold 假设，支持 grounded rubric |
| terminalbench | verifier/tests + environment state | 关闭标量 gold 假设，保留 evaluator 检查 |

这里有一个很重要的工程修复：旧 SWE profile 会清空所有公共 checker，导致结构缺陷召回为 0；旧 generic profile 又会把所有 Workspace/Terminal item 误报为 missing oracle。现在 profile 是公共能力之上的增量/减量组合。

### 5.4 AuditPlan：不是写报告，而是真正决定运行什么

关键文件：`benchcore/planning.py`。

`CORE_CAPABILITIES` 给每种检查声明：

- 需要哪些 artifact；
- 适用哪些 family；
- 是否需要 LLM；
- 是否需要安全执行；
- evidence level 和 cost class。

planner 输出四类状态：

| 状态 | 含义 |
|---|---|
| selected | 条件满足，本次应执行 |
| executed | 已经实际执行完成 |
| skipped | 能做但本次没有启用，或 family 不适用 |
| unsupported | 缺少必要 artifact/能力，当前无法检查 |

这是通用系统的关键，因为 `unsupported` 不能被解释成“检查通过”。

自动 profile 还有一个成本安全规则：family detection 本身不会偷偷调用付费 LLM；只有用户显式启用 LLM 方法，或显式选择 Workspace 深审 profile，才会创建 LLM client。

### 5.5 第一层：低成本静态检查

关键文件：`benchcore/checkers.py`。

`DEFAULT_CHECKERS` 包括：

- `TaskSpecChecker`
- `ContextChecker`
- `OutputContractChecker`
- `OracleChecker`
- `EvaluatorChecker`

它们检查缺失字段、引用附件不存在、choice/gold 无法映射、重复选项、简单算术冲突、evaluator 缺失或格式风险等。

静态层的特点：

- 快、便宜、可重复；
- 对结构缺失通常有很强证据；
- 对“题目真正答案是什么”召回很低；
- 关键词规则容易在 unit、时间范围等问题上产生噪声。

因此静态层应该承担“高精度事实检查和低成本候选生成”，不能承担全部语义审计。

### 5.6 第二层：把 evaluator 当程序测试

关键文件：`benchcore/methods.py`。

#### Evaluator replay

把 evaluator 自己声明的 gold/alias 重新送入 evaluator。如果自己的正确答案都不能通过，评分器明显不一致。

#### Metamorphic testing

对答案做不改变语义的变换：

- `4.62` → `4.620`
- 选择题 `B` → 正确选项文本
- set answer 改变顺序
- 大小写、空格和允许的格式变化

如果等价变换后被拒绝，可能是 over-strict evaluator。

#### Mutation testing

构造明显错误或不完整的答案。如果错误答案仍然通过，可能是 evaluator undercoverage。

#### Differential candidate

从不同来源抽取 candidate answer，比较它们与 gold/evaluator 的一致性。

这套思想本质上来自软件测试：

> 不仅验证“标准解能通过”，还验证“合理替代解不会被错杀、错误解不会漏过”。

### 5.7 第三层：结构化 LLM gold audit

关键文件：`benchcore/llm_auditor.py`。

普通选择题不能直接把题目、选项和 gold 全给模型，再问“gold 对不对”，因为模型很容易被 gold 锚定。当前链路更接近：

```text
Blind solver：隐藏 choices/gold，独立求解
-> Answer-to-option matcher：把开放答案与选项做语义匹配
-> Option applicability：逐个判断选项是否可能正确
-> Accepted answer set：程序聚合合理正确答案集合
-> Challenger / defender：对风险样本做对抗复核
-> Root-cause classification
```

它试图区分：

- declared gold 错了；
- 根本没有正确选项；
- 有多个正确选项；
- 题面不充分；
- 只是展示/切分损坏。

当前实验说明它能发现语义 oracle issue，但 subtype 还不稳定：10 个 clean-source wrong-gold mutation 全部被发现，只有 7 个准确归类为 `wrong_gold_answer`，另外 3 个被分成 `no_correct_answer`。下一步要先推断正确答案集合，再判断 declared gold，避免根因混淆。

### 5.8 Workspace：rubric 不是天然正确的 oracle

关键文件：

- `benchcore/artifact_consistency.py`
- `benchcore/value_recompute.py`
- `benchcore/investigator.py`
- `benchcore/forensic.py`

Workspace 的审计对象是：

```text
task
<-> input files/context
<-> expected output files
<-> rubrics/evaluator
```

主要问题包括：

- rubric 要求了 task 没有要求的内容；
- rubric 依赖输入中根本不存在的数据；
- rubric 写死了错误数字；
- output contract 与 rubric 要求不同文件；
- rubric 没覆盖 task 的核心义务。

`investigator` 会进行多次独立调查、quorum 聚合和独立 evidence verifier。但只要结论依赖未知 harness 行为，就必须保持 review。

### 5.9 SWE：solution leakage 只是污染问题的一小部分

关键文件：`benchcore/swe_leak.py`。

当前主要检查 gold patch 是否直接出现在模型可见的 `problem_statement` 或 hints 中。这能发现明显的题面泄漏，但还不能覆盖：

- 语义改写后的 solution leak；
- 模型训练时见过公开 issue/commit；
- repo 历史和版本信息泄漏；
- benchmark-specific over-optimization。

因此 `solution_leak` checker 不能等价于完整 contamination audit。

### 5.10 Evidence fusion：为什么同一个 item 不能重复投票升级

关键文件：`benchcore/auditor.py`。

多个 LLM checker 可能使用相同 prompt 信息或同一基础模型，它们不是独立证据。系统需要：

- 合并同源 observation；
- 识别冲突；
- 在证据冲突时降级；
- 把 presentation 与 substantive defect 分开；
- 一个 item 允许多个 defect，但避免重复计数同一根因。

真正的独立证据通常来自不同机制，例如：

```text
LLM 提出 rubric 数字可疑
+ 原始 CSV 确定性重算不一致
+ evaluator replay 复现失败
= 可以显著提高确认等级
```

而“三次相同 LLM 都觉得可疑”通常只提高 review 优先级。

### 5.11 Synthetic defect injection：在缺人力时怎样测 recall

关键文件：`benchcore/defect_injection.py`。

系统从原 item 确定性生成带 provenance 的 mutation，例如：

- 删除 task/gold/context/evaluator；
- 替换为错误 gold；
- 制造重复选项。

每个 mutation 保存 source ID、seed、变更字段、前后 SHA-256 和 evidence grade。召回定义为：

\[
Recall_{synthetic}=\frac{\text{检出的注入缺陷}}{\text{全部有效注入缺陷}}
\]

这里必须区分：

- `structural`：删除 evaluator、重复选项等，缺陷由变换本身保证；
- `conditional`：wrong-gold 只有在原 gold 唯一正确时才成立。

Synthetic recall 很有价值，但只能证明 checker 能找到“已经定义的 mutation family”，不能证明能找到所有真实世界缺陷。

当前固定 fixture 已进入 pytest：structural exact recall 低于 100% 就会回归失败。

---

## 6. 怎样理解当前实验结果

### 6.1 静态规则是高精度筛选，不是完整查错

在有人工标签的小样本中：

| 数据集 | 静态候选 Precision | 静态 Recall |
|---|---:|---:|
| MMLU-Redux 200 | 1.000 | 0.060 |
| GSM8K 100 | 0.200 | 0.100 |
| SVAMP 100 | 1.000 | 0.079 |

正确解读是：

- MMLU/SVAMP 静态发现少但比较准；
- GSM8K 的 unit handling 关键词规则噪声大；
- 不应因为 precision 高就说系统已经能找全问题；
- 也不应因为 recall 低就删除静态层，它是便宜且可证实的第一层。

### 6.2 P0 修复证明了 auto routing 的必要性

| Family | 修复前结构召回 | 修复后 auto 结构召回 |
|---|---:|---:|
| SWE-bench profile | 0% | 100% |
| Workspace-Bench | 52.4% | 100% |
| Terminal-Bench | 52.9% | 100% |

同时在原始样本上：

- Workspace 的 20 个 `missing_oracle` 假阳性归零；
- Terminal 的 89 个 `missing_oracle` 假阳性归零；
- SWE 仍然只保留原来的 2 条 solution-leak review，没有增加候选。

这说明改进不是简单“多报警”，而是同时提高了 injected recall、降低了 family mismatch false positive。

### 6.3 LLM 能补 wrong-gold 盲区，但根因分类仍需改进

正式 MMLU clean-source mutation：

- item-level oracle issue：10/10；
- exact wrong-gold subtype：7/10；
- 3/10 错分为 no-correct-answer；
- 50 次 API 调用、95,628 tokens。

这表明 LLM 语义层有明显增益，也表明不能只报告“发现率”：还要报告 subtype accuracy、confirmed/review 分布、成本和失败模式。

### 6.4 Investigator 的价值是降噪，不是把候选自动变真

Workspace 单 item 初审产生 5 个 review candidates。多 pass investigator + verifier 后：

- 4 个有支持证据的 likely true；
- 1 个 false positive 被证据明确驳回；
- 其中 3 个文件字节目标有确定性不一致；
- 另一个 output contract 候选仍依赖 harness，应保持 review。

这里最重要的研究态度是：`likely_true` 不是作者确认，也不是总体 defect rate。

---

## 7. 相关研究：每篇只记“问题—方法—结论—对我们的启示”

> 注意：2026 年论文中多篇仍是 arXiv preprint。下面写的是论文/机构公开报告的结论，不等于已经被我们的实验独立复现。

### 7.1 OpenAI：Separating signal from noise in coding evaluations（2026）

论文/报告：[OpenAI 官方文章](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)

**问题**：SWE-Bench Pro 的低通过率到底代表模型能力不足，还是任务本身有问题？

**方法**：先结合 task metadata、模型 attempts 和 failure traces 自动筛选，再让 investigator agent 进入真实 repository/environment 检查代码和运行测试；候选由多次独立调查和五位有经验的软件工程师复核。

**公开结果**：731 个 public tasks 中，agent pipeline 标出 200 个 broken tasks，人工 campaign 标出 249 个；主要问题是 overly strict tests、underspecified prompts、low-coverage tests 和 misleading prompts。人工比 agent 更常给一个任务多个标签，尤其更容易发现 low coverage。

**对我们的启示**：

- trace 和多模型 attempts 是审计输入，不是附属日志；
- coding benchmark 必须进入真实 repo/environment；
- test coverage 不能靠静态阅读完全判断；
- investigator 是可扩展调查工具，最终证据仍需要执行或人工复核。

一句话记忆：

> **OpenAI 路线证明，代码 benchmark 审计必须从“读题”升级为“读题 + 看失败轨迹 + 进环境运行 + 专家复核”。**

### 7.2 Auto Benchmark Audit（ABA，2026）

论文：[Automated Benchmark Auditing for AI Agents and Large Language Models](https://arxiv.org/abs/2605.26079)

**问题**：能否用统一 agentic pipeline 跨很多 benchmark/domain 查 instruction、environment 和 evaluation 问题？

**方法**：收集 task 配置、文件和运行证据，让 auditor agent 使用 shell 检查 artifacts；同时比较 static mode 与带 trajectory 的 audit。

**论文报告**：覆盖九个领域的 168 个 benchmarks，报告在被审计任务中发现 25.7% 以上存在关键问题；过滤问题任务后，SWE-bench Verified 和 Terminal-Bench 2 的平均性能分别变化 9.9% 和 9.6%，并可能改变模型排序。

**对我们的启示**：

- taxonomy 至少要分 instruction、environment、evaluation 三条轴；
- 审计价值最终要用 ranking impact 衡量，而不只是 defect count；
- trajectory mode 比纯静态模式能发现更多 runtime issue；
- BenchCore 当前的 `ranking_impact.py`、package graph 和未来 harness/trace 层与这条路线高度一致。

一句话记忆：

> **ABA 把 benchmark auditing 从单数据集脚本推进到跨领域 agent pipeline，并强调缺陷会真实改变分数和排名。**

### 7.3 BenchGuard（2026）

论文：[BenchGuard: Who Guards the Benchmarks?](https://arxiv.org/abs/2604.24955)

**问题**：复杂 scientific agent benchmark 的 task、inputs、reference、grader 是否互相一致？

**方法**：用结构化 LLM protocol 交叉验证所有 benchmark artifacts，并可加入 agent solution 和 execution trace 作为额外证据。

**论文报告**：在 ScienceAgentBench 找到 12 个作者确认问题；在 BIXBench Verified-50 上匹配专家问题的 83.3%；论文还报告 50 个复杂 bioinformatics tasks 的完整审计成本低于 15 美元。

**对我们的启示**：

- benchmark 应被表示为 artifact graph，而不是一行 prompt；
- structured protocol 比单轮自由判断更可控；
- solution/trace 是诊断 evidence；
- LLM audit 可以大规模生成候选，但作者确认/专家证据仍然重要。

一句话记忆：

> **BenchGuard 的核心是“让所有 artifact 相互作证”，这正是 BenchCore package graph 和 cross-artifact checker 的研究依据。**

### 7.4 Item Response Theory benchmark auditing（2026）

论文：[Auditing LLM Benchmarks with Item Response Theory](https://arxiv.org/abs/2605.30504)

**问题**：没有足够人工标签时，能否从大量模型的答题模式发现疑似错标 item？

**方法**：使用 114 个模型的 response matrix 拟合 Item Response Theory。直觉上，如果一个 item 的表现模式与模型整体能力和题目难度关系极不协调，它可能不是普通难题，而是错标、歧义或特殊污染。

**论文报告**：在七个 preference/MCQ benchmarks 上，top 200 疑似问题达到 95% precision；发现的问题包括机械标注错误、从上游数据继承的错误和没有唯一合理标签的歧义 item。

**对我们的启示**：

- 当没有足够人力时，model panel 是一种 weak supervision；
- 单模型答错不能说明题错，多模型的结构化异常更有信息；
- IRT 只能给“高价值疑似样本”，仍需 artifact/专家证据确认；
- 未来可把 response matrix 作为 BenchCore 的新 evidence channel。

一句话记忆：

> **IRT 路线不是让最强模型当老师，而是利用很多模型的整体答题结构找异常 item。**

### 7.5 CheckList（ACL 2020）

论文：[Beyond Accuracy: Behavioral Testing of NLP Models with CheckList](https://aclanthology.org/2020.acl-main.442/)

**问题**：单一 held-out accuracy 不能告诉我们系统具体在哪些行为上失败。

**方法**：借鉴软件工程，把能力拆成 checklist，并使用 minimum functionality、invariance、directional expectation 等行为测试生成大量 case。

**论文结果**：论文在商业和当时先进 NLP 系统中发现关键问题；用户研究中，使用 CheckList 的实践者创建的测试约为两倍、发现的 bug 接近三倍。

**对我们的启示**：

- aggregate score 必须被 capability-specific tests 补充；
- metamorphic testing 是无需知道完整正确答案时的强工具；
- BenchCore 的 answer variants、mutation 和 capability registry 可以看作把行为测试思想反过来用于检查 benchmark/evaluator。

一句话记忆：

> **CheckList 教会我们：不要只盯总分，要把“应该保持不变”和“应该按方向变化”的行为写成测试。**

### 7.6 Sage：无人工 gold 检查 LLM judge（2025）

论文：[Are We on the Right Way to Assessing LLM-as-a-Judge?](https://arxiv.org/abs/2512.16041)

**问题**：如果 judge 本身也可能不可靠，又缺少足够人类 gold，怎样检查 judge？

**方法**：从理性选择公理出发，检查局部 pairwise preference 是否稳定，以及全局偏好关系是否满足传递性。

**论文报告**：即使表现最好的模型，在困难 case 中也有接近四分之一无法保持一致偏好；明确 rubric、panel judge 和 deeper reasoning 能改善一致性。

**对我们的启示**：

- judge consistency 是可测的，但 consistency 不等于 factual correctness；
- 多次投票要报告分布和不确定性，不能只给 majority label；
- BenchCore investigator 应继续加入顺序置换、对称性、传递性和 evidence-grounding 测试。

一句话记忆：

> **Sage 说明在没有人工 gold 时，可以先测 judge 是否自洽，但自洽只能证明“裁判稳定”，不能证明“裁判正确”。**

### 7.7 Contamination detection 的可靠性边界（2026）

论文：[The Reliability Gap in Benchmark Auditing](https://arxiv.org/abs/2606.03305)

**问题**：在理想实验上有效的训练数据污染检测，到了真实 benchmark 规模和 distribution shift 下是否仍可靠？

**方法**：跨 27 个模型、335 次评估检查 LLM Dataset Inference、Post-Hoc Dataset Inference 和 CoDeC 等方法。

**论文报告**：只有 199/335 个结果正确；distribution shift 会制造假阳性，benchmark-scale 数据量会让部分方法统计功效不足，CoDeC 更适合粗粒度 provenance，而难以确认具体 split。

**对我们的启示**：

- 统计污染信号应分成 risk，而不是自动 confirmed；
- provenance、版本 pin、canary 和直接 overlap 比单一统计分数更可解释；
- clean reference 与 suspect set 不同分布时，必须先排除 distribution shift。

一句话记忆：

> **污染统计检测可以排序风险，但目前不能替代透明的数据来源和直接证据。**

---

## 8. 把研究路线统一成一张方法地图

| 证据来源 | 能发现什么 | 强项 | 主要风险 | BenchCore 状态 |
|---|---|---|---|---|
| 静态规则 | 缺字段、重复、显式冲突 | 快、确定、便宜 | 语义 recall 低 | 已实现 |
| Artifact cross-check | task/rubric/context 矛盾 | 根因清楚 | 复杂语义依赖 LLM | 部分实现 |
| Replay/metamorphic | evaluator 拒绝等价解 | 可复现 | 需要正确 variant model | 已有基础 |
| Wrong-solution mutation | evaluator 漏过错误解 | 直接测 coverage | 自动生成强反例困难 | 已有基础 |
| LLM structured audit | wrong gold、歧义、隐含要求 | 语义覆盖广 | 幻觉、锚定、不稳定 | 已实现多种 auditor |
| Investigator + verifier | 深审高价值候选 | 能查复杂上下文 | 成本高，仍需事实证据 | 已有基础 |
| Response matrix / IRT | 多模型异常 item | 不依赖单一 judge | 需要大量模型响应 | 未实现 |
| Trace clustering | 共同失败点、环境问题 | 贴近真实运行 | 需要统一 trace schema | 未实现 |
| Full environment replay | 测试过严/不足、flakiness | 证据最强 | sandbox 与 adapter 成本高 | runner/harness 底座已有，未贯通 |
| Provenance/contamination | 泄漏、版本、重复 | 影响 benchmark 有效性 | 统计方法易误判 | 仅有局部 solution leak |

这张表表达了一个很关键的研究判断：

> **不存在一个万能 checker。通用性来自证据机制的组合、自动路由和诚实报告覆盖，而不是来自一个更长的 prompt。**

---

## 9. 当前系统已经做到什么、还没有做到什么

### 已经做到

- 扫描 benchmark file/directory，建立十类 artifact inventory；
- 将 JSONL/JSON/CSV 归一为统一 item schema；
- 根据 record semantics 自动识别 generic/SWE/Workspace/Terminal；
- AuditPlan 真正驱动 checker selection；
- 检查核心 task/context/output/oracle/evaluator 结构问题；
- 做基础 replay、metamorphic、mutation、dataset drift；
- 对 MCQ 做结构化 LLM gold/option audit；
- 对 Workspace 做 grounded rubric、contract、coverage 候选和 investigator；
- 对 SWE 做字面 solution leakage；
- 用 synthetic mutations 测 structural recall 并阻止回归；
- 报告 executed/skipped/unsupported 和 confirmed/review。

### 尚未做到

- 自动解析任意 repository 成完整可执行 BenchmarkItem；
- 为任意 benchmark 自动生成安全 harness adapter；
- 大规模重放 SWE/Terminal/Office environment；
- 系统生成“所有合理替代解”和“最小错误解”；
- mutation kill matrix 与 test coverage 分析；
- 多模型 attempt matrix、IRT 和 trace failure clustering；
- 完整 provenance/contamination audit；
- 在大量不同 family 上获得可靠的人类 precision/recall gold；
- 证明“没有发现的 item 就一定没问题”。

所以目前最准确的产品定位是：

> **一个已具备通用规划和多证据检查底座的 benchmark auditing 研究系统，而不是能够证明任意 benchmark 完全正确的万能验证器。**

---

## 10. 接下来最值得做的技术工作

### 优先级 1：修好语义根因和 evidence aggregation

- 先推断 accepted answer set，再判断 declared gold；
- blind solver 无法开放求解时，不应与两条强 option/challenger 证据同权；
- 两个高质量独立证据至少应进入 review；
- 对同源 LLM evidence 降低独立性权重。

### 优先级 2：Evaluator 正反例执行闭环

对每个 evaluator 构造：

```text
Gold / known-valid solution
Reasonable alternative solutions
Formatting/metamorphic equivalents
Minimal incomplete solutions
Plausible but wrong solutions
```

然后得到 kill matrix：每个 test 能杀死哪些错误解，会错杀哪些合理解。

### 优先级 3：Trace 与 response matrix

- 收集多模型、多次 attempt；
- 统一 failure stage、assertion、exception、environment event；
- 聚类共同失败点；
- 用 IRT/异常检测产生疑似错标 item；
- investigator 只深审高价值 cluster。

### 优先级 4：Ranking impact

最终不能只说“发现 N 个问题”，还要回答：

- 去掉/修复问题 item 后，模型分数变化多少？
- 排名是否翻转？
- 不同模型是否受缺陷不均匀影响？
- benchmark 的置信区间和有效样本量怎样变化？

---

## 11. 怎样向别人讲清楚

### 11.1 一句话版本

> 我们不是在用 benchmark 测模型，而是在自动审计 benchmark 这个测量工具：检查题目、输入、gold、rubric/tests 和环境是否一致，避免把 benchmark 的错误误算成模型的能力不足。

### 11.2 30 秒版本

> 一个 benchmark 不只是题目和答案，它实际上是一套测量系统，包括 task、附件、输出要求、oracle、评分器和执行环境。任何一个环节出错，模型分数都会失真。我们的系统先自动识别 benchmark 类型和 artifacts，再组合静态规则、交叉一致性、evaluator replay、变形/反例测试和 LLM investigator，输出 confirmed、review 和 unsupported。我们已经把 SWE、Workspace、Terminal 的结构缺陷召回修到 100%，同时消除了 agent benchmark 因没有标量 gold 产生的大量假阳性；下一步重点是环境重放、test coverage 和 trace/多模型响应分析。

### 11.3 三分钟版本

> 我把 benchmark 理解成 AI 能力的测量仪器。传统做法默认题目、标准答案和评分器是正确的，然后直接报告模型得分；但 code 和 agent benchmark 实际还包含附件、repository、环境、工具、hidden tests、rubrics 和运行状态。只要这些 artifact 不一致，就会出现两类测量错误：合理解被拒绝，或者错误解被接受。
>
> 所以我们的 auto benchmark auditing 分七步。第一，扫描文件或目录并建立 artifact graph；第二，把不同数据集映射成统一 item schema；第三，根据字段、evaluator 和 output contract 自动识别 generic、SWE、Workspace 或 Terminal；第四，AuditPlan 根据现有 artifact、LLM 和执行能力选择 checker；第五，分层运行静态规则、cross-artifact、一致性重放、metamorphic/mutation 和结构化 LLM audit；第六，融合证据并区分 confirmed、review、unsupported；第七，用人工标签、clean controls 和 synthetic defect injection 校准 precision/recall。
>
> 我们的实验说明了两个关键点。第一，family semantics 很重要：旧 SWE profile 的结构召回是 0%，Workspace/Terminal 又因为没有标量 gold 产生大量假阳性；auto routing 修复后，三类结构召回都是 100%，原始 agent 样本的 missing-oracle 假阳性归零。第二，LLM 能补静态规则找不到的 wrong-gold，但根因分类和置信度仍不稳定，所以 LLM 只能生成和调查候选，确认需要执行、原始文件或专家证据。
>
> 这和最新研究方向一致：OpenAI 用 attempts、failure traces、真实 repo 执行和工程师复核审计 SWE-Bench Pro；BenchGuard/ABA 做跨 artifact 的 agent 审计；IRT 用 114 个模型的响应模式找疑似错标；Sage 检查 LLM judge 自洽性。我们的最终目标不是承诺找出所有错误，而是最大化可验证缺陷召回、控制误报，并明确告诉用户哪些部分没有被检查。

### 11.4 技术答辩时的核心结构

如果对方问“你的创新点是什么”，可以按四层回答：

1. **问题建模**：把 benchmark 从 `(question, answer)` 提升为 artifact graph 和 measurement system；
2. **自动规划**：family detection + capability-aware AuditPlan，而不是手工为每个数据集跑脚本；
3. **多证据验证**：静态、执行、反事实、LLM、trace/statistical evidence 分层，明确证据等级；
4. **可校准性**：synthetic provenance、clean control、人类 gold 和 ranking impact，而不是只展示几个案例。

如果对方问“和让 GPT 看题有什么区别”，回答：

> GPT 只是其中一个语义候选生成器。我们的主体是 artifact schema、自动 checker planning、evaluator 正反例测试、证据融合和可复现实验；没有静态/执行/原始文件证据的 LLM 结论默认不会自动 confirmed。

如果对方问“能保证找出所有问题吗”，回答：

> 不能，也不应该这样承诺。未知领域、缺失环境、私有事实和不可判定的语义都造成 coverage 边界。我们的目标是对可定义缺陷测 recall，对确认层测 precision，对没有能力检查的部分明确 abstain，而不是把 unknown 当 clean。

---

## 12. 常见误区与正确说法

| 错误说法 | 正确说法 |
|---|---|
| LLM 多数投票通过，所以问题是真的 | 多数投票提高稳定性；仍需独立事实或执行证据确认 |
| 没有发现 violation，所以 benchmark 没问题 | 本次已执行的方法没有发现；还要看 unsupported/coverage |
| Synthetic recall 100%，说明真实 recall 100% | 只说明对已定义 structural mutation 的召回是 100% |
| Agent benchmark 没有 gold，所以缺 oracle | tests/rubrics/state verifier 本身可以是 oracle |
| Gold 能通过 tests，说明 tests 正确 | 还需验证合理替代解和错误解，分别检查过严与覆盖不足 |
| 模型都答错，说明题有问题 | 可能只是题难；需要异常模式、artifact 矛盾或执行证据 |
| 模型都答对，说明题质量高 | 可能有泄漏、测试太松或 shortcut |
| 污染分数高，说明一定训练过 | 统计信号可能受 distribution shift 和样本规模影响 |
| Profile 越专用，越应该关闭通用检查 | 专用 profile 应在公共结构检查上增删少量 family policy |

---

## 13. 学习顺序：用两小时真正吃透项目

### 第 1 阶段：20 分钟建立问题模型

读本文第 0–3 节，确保能解释：

- 为什么 benchmark 是测量系统；
- soundness 与 completeness 的区别；
- 为什么 LLM vote 不是 gold。

### 第 2 阶段：35 分钟跟一遍代码链路

依次阅读：

1. `benchcore/schema.py`
2. `benchcore/loader.py`、`field_mapping.py`
3. `benchcore/package_scan.py`
4. `benchcore/planning.py`
5. `benchcore/cli.py` 的 `run_audit()`
6. `benchcore/checkers.py`
7. `benchcore/methods.py`
8. `benchcore/auditor.py`

目标不是记住每个函数，而是能从输入追踪到 report。

### 第 3 阶段：30 分钟理解两条专项链路

- MCQ：读 `llm_auditor.py` 中 EvidenceGold 相关流程；
- Workspace：读 `artifact_consistency.py` 和 `investigator.py`。

问自己：哪些结果是事实，哪些只是 LLM observation？

### 第 4 阶段：20 分钟读实验

阅读：

- `reports/universal_audit_experiment_20260713/EXPERIMENT_ANALYSIS.md`
- `UNIVERSAL_BENCHMARK_AUDIT_OPTIMIZATION_ROADMAP_zh.md`

重点看失败实验为什么被排除，而不只是看最好数字。

### 第 5 阶段：15 分钟复述

不看文档，分别说一遍：

- 一句话版本；
- 30 秒版本；
- 三分钟版本；
- “当前还做不到什么”。

如果能准确说清这四段，就已经掌握了项目的主体。

---

## 14. 自测题与参考答案

### 问题 1

为什么 benchmark auditing 不是普通的数据清洗？

**答案**：因为它不仅检查 row/label，还检查 task、输入、输出契约、评分器、环境、轨迹和这些 artifact 的执行关系；目标是保证测量有效性，而不只是格式正确。

### 问题 2

合理解被测试拒绝和错误解被测试接受分别是什么问题？

**答案**：前者是 evaluator 过严/不完备，后者是 evaluator 覆盖不足/不健全。

### 问题 3

为什么 Workspace 没有 gold 不一定是缺陷？

**答案**：它的正确性由 rubrics、输出文件和最终 workspace state 定义，rubric/tests 就是 oracle。

### 问题 4

为什么自动 profile 是系统能力，而不是 CLI 便利功能？

**答案**：不同 family 的 oracle 和 evaluator 语义不同；选错 checker 会同时造成漏检和系统性误报。

### 问题 5

Metamorphic testing 不知道新答案的完整 gold，为什么仍能测试？

**答案**：它利用已知不变量或方向关系，例如数值尾零、集合顺序、选项 label 与文本等价；只需知道变换不应改变正确性。

### 问题 6

为什么 wrong-gold mutation 是 conditional，而 remove-evaluator 是 structural？

**答案**：wrong-gold 依赖原 gold 唯一正确；如果原题本来多解，替换未必制造缺陷。删除一个原本声明且必要的 evaluator 则由结构变化直接保证缺失。

### 问题 7

LLM 三次判断一致，证据变强了吗？

**答案**：稳定性证据变强，但如果调用同一模型、同一信息，它们高度相关，不等于三份独立事实证据。

### 问题 8

IRT 为什么比“最强模型答错就报警”更合理？

**答案**：IRT 利用大量模型能力、题目难度和整体响应模式，寻找不能被普通难度解释的异常，而不是依赖单一模型权威。

### 问题 9

为什么必须报告 unsupported？

**答案**：否则用户会把“由于缺环境根本没检查”误解为“检查过且没有问题”。

### 问题 10

项目下一步为什么应该先做 evaluator execution，而不是继续加 prompt？

**答案**：当前 prompt 已能产生语义候选，真正限制确认能力的是缺少合理替代解/错误解的真实执行、test coverage 和环境证据。

---

## 15. 术语速查

| 术语 | 最短解释 |
|---|---|
| Benchmark auditing | 检查评测工具本身是否有效 |
| Artifact | 构成 benchmark 的一个证据组件 |
| Oracle | 定义“什么是正确”的依据，不一定是标量 gold |
| Evaluator | 把候选输出与 oracle/规则比较并生成分数的机制 |
| Output contract | 合法输出的形态、文件、格式和约束 |
| Family semantics | 某类 benchmark 特有的任务和评分含义 |
| Replay | 用已知输入重新运行 evaluator/环境 |
| Metamorphic test | 对不应改变正确性的变换检查行为是否稳定 |
| Mutation test | 注入错误解或数据缺陷，检查系统能否杀死/发现 |
| Soundness | 错误解不能通过 |
| Completeness | 合理解不应被错杀 |
| Undercoverage | evaluator 没检查完整要求 |
| Over-strict | evaluator 强制题面未要求的细节 |
| Evidence fusion | 合并多方法证据并处理重复/冲突 |
| Investigator | 对高价值候选进行深入、多步调查的 agent |
| Provenance | 数据来源、版本、时间和变换历史 |
| Contamination | 评测内容进入训练数据或被特殊优化 |
| Abstention | 证据不足或能力缺失时明确说“不知道” |
| Ranking impact | 修复问题后模型分数/排序变化 |

---

## 16. 最终应该形成的认识

真正的 auto benchmark problem finding 不是：

```text
把数据发给一个大模型
-> 问有没有错
-> 汇总模型回答
```

而是：

```text
把 benchmark 建模成测量系统
-> 自动发现 artifact 和 family semantics
-> 为当前输入生成能力感知的 audit plan
-> 用静态、执行、反事实、统计和语义方法交叉取证
-> 对 evaluator 同时测试合理正例与错误反例
-> 用 trace/response matrix 找系统性异常
-> 用 provenance、执行和专家证据确认
-> 用 precision、recall、coverage、abstention、成本和 ranking impact 校准
```

最后再用一句话收束整个项目：

> **BenchCore 要做的不是让 AI 宣判 benchmark 对错，而是建立一套自动、可复现、证据分级的 benchmark 质量保障系统，让每个分数都能回答“测了什么、怎样测的、哪里可能不可信”。**
