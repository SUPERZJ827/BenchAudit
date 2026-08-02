# BenchAudit 简历项目描述更新建议

## 一、这个项目还没完全做完，能不能放在简历上？

可以放。

研究型和工程型项目很少存在“全部做完”的状态。简历真正要求的是：

- 写进去的功能已经实现，而不是仍在计划中；
- 写进去的实验已经实际运行，并且有报告或代码可以复现；
- 面试时能够解释设计、实验口径、失败案例和能力边界；
- 不声称已经解决“任意 benchmark 的所有问题”；
- 明确使用“持续迭代”“研究原型”或“至今”，避免暗示系统已经完全成熟。

你当前已经完成了代码实现、自动审计规划、多个数据集实验、合成缺陷回归和结果分析，因此具备写入简历的条件。

不过不建议把安全容器执行、完整 trace auditing、任意 benchmark adapter、完整 contamination detection 等尚未贯通的内容写成已完成能力。

---

## 二、推荐版本

这版保留必要的技术含量，但不会堆太多实现细节或夸大通用性。

```latex
\item \textbf{BenchAudit：LLM/Agent Benchmark 自动化质量审计框架}：
面向 LLM 与 Agent benchmark 的题目、上下文、输出契约、标准答案和评分器，构建分层数据质量审计流程，覆盖错误答案、题目歧义、选项冲突、上下文缺失及评分规则不一致等问题；
实现 benchmark artifact 统一建模、自动类型识别与审计计划，可根据 Generic QA、SWE-bench、Workspace-Bench 和 Terminal-Bench 的评分语义选择静态规则、evaluator replay、变形测试、缺陷注入及结构化 LLM 审计方法；
在 MMLU-Redux、SVAMP、GSM8K、SWE-bench、Workspace-Bench 等评测集上完成实验与回归验证，SVAMP-Platinum candidate F1 达 \textbf{0.914}；针对已定义的合成结构缺陷，在 9 个评测集上的召回率达到 \textbf{100\%}。
\githublink{https://github.com/SUPERZJ827/BenchAudit} \hfill 2026年6月--至今
```

### 为什么推荐这一版

- 第一行说明解决的问题，没有罗列过多 defect taxonomy；
- 第二行体现最新的 auto routing、AuditPlan 和多证据方法；
- 第三行只保留两个容易记住的指标；
- 对 100% recall 明确限定为“已定义的合成结构缺陷”，没有暗示真实缺陷召回率为 100%；
- 没有声称能够检查任意 benchmark 的所有错误。

---

## 三、更简短、更加保守的版本

如果简历空间有限，或者你担心面试时难以解释太多底层细节，建议使用这一版。

```latex
\item \textbf{BenchAudit：LLM Benchmark 数据质量审计工具}：
构建面向 LLM/Agent benchmark 的自动化质量审计原型，统一检查题目、上下文、标准答案、输出要求与评分器之间的缺失和不一致问题；
实现静态规则、evaluator replay、变形/缺陷注入测试及结构化 LLM 审计，并根据 QA、代码和 Agent benchmark 的不同评分语义自动选择检查方法；
在 MMLU-Redux、SVAMP、GSM8K、SWE-bench 等公开评测集上完成实验和回归测试，SVAMP-Platinum candidate F1 达 \textbf{0.914}。
\githublink{https://github.com/SUPERZJ827/BenchAudit} \hfill 2026年6月--至今
```

这版更适合：

- 实习申请；
- 简历只有一页；
- 面试岗位不专门研究 benchmark/evaluation；
- 目前还不想重点讲复杂 agent environment 和研究路线。

---

## 四、如果申请偏研究或算法岗位，可以使用的版本

```latex
\item \textbf{BenchAudit：面向 LLM/Agent Evaluation 的自动化 Benchmark Auditing}：
将 benchmark 建模为 task、context、output contract、oracle 与 evaluator 组成的 artifact 系统，研究错误 gold、语义歧义、评分器过严/覆盖不足等缺陷对模型能力测量的影响；
设计 capability-aware audit planning 与多证据审计流水线，组合静态检查、evaluator replay、metamorphic/mutation testing、结构化 LLM auditor 和证据分级，区分 confirmed、review 与 unsupported 结果；
完成 9 个公开评测集的静态与合成缺陷实验；在已定义的 structural mutations 上达到 \textbf{100\% recall}，并通过自动 family routing 消除 Workspace/Terminal 中由标量 gold 假设造成的系统性误报。
\githublink{https://github.com/SUPERZJ827/BenchAudit} \hfill 2026年6月--至今
```

这版技术表达更强，但只有在你能够解释下面这些概念时再使用：

- oracle 和 evaluator 的区别；
- evaluator soundness 与 completeness；
- metamorphic testing 与 mutation testing；
- 为什么 Agent benchmark 不一定有标量 gold；
- synthetic recall 为什么不等于真实缺陷 recall；
- `confirmed`、`review`、`unsupported` 的证据边界。

---

## 五、不建议写入简历的说法

下面这些表述目前过于夸张或难以证明：

```text
实现了任意 benchmark 的全自动错误检测
能够检测 benchmark 中的所有问题
实现了通用 Agent benchmark 执行审计
实现了完整的训练数据污染检测
自动确认 LLM benchmark 中的语义错误
真实 benchmark 缺陷召回率达到 100%
```

更准确的替换方式：

| 不建议 | 建议替换为 |
|---|---|
| 任意 benchmark 全自动检测 | 面向多类 LLM/Agent benchmark 的自动审计原型 |
| 检测所有问题 | 覆盖若干核心 artifact 和已定义缺陷类型 |
| 真实召回率 100% | 已定义合成结构缺陷 recall 100% |
| 自动确认语义错误 | 生成语义审计候选并进行证据分级 |
| 完整执行审计 | 已实现 execution/harness 底座，专项 adapter 持续迭代 |

---

## 六、简历数字的口径说明

### SVAMP-Platinum candidate F1 = 0.914

这是已有多审计器实验结果，不是最新静态规则单独运行的结果。面试时应说明：

- `candidate` 是面向人工复核的高召回候选层；
- 它不等同于自动确认缺陷的 precision；
- 该结果来自结构化多审计器流程，而不是单一 prompt。

### 9 个评测集 structural mutation recall = 100%

这是修复 auto routing 和 agent evaluator semantics 后，对固定 mutation 集的回归结果。

必须说明：

- 100% 仅针对已经定义的 structural mutation；
- 不包括需要真正解题的 conditional wrong-gold；
- 不能推出系统对所有真实缺陷的 recall 是 100%；
- 这一指标主要证明基础 checker 和 profile routing 没有结构性漏检回退。

### 为什么不建议同时放很多指标

原版本同时写了 SVAMP F1、GSM8K recall 和 MMLU F1。数字本身没有问题，但简历中连续出现三个不同数据集、不同指标和不同统计层级，容易让读者无法快速抓住贡献，也会增加面试解释成本。

建议只保留：

1. 一个有人工标签的代表性效果指标，例如 SVAMP candidate F1；
2. 一个体现最新工程改进的回归指标，例如 structural mutation recall。

---

## 七、考虑到目前主要借助 LLM 工作，应该选择哪一版？

建议优先使用“更简短、更加保守的版本”。

是否借助 LLM 并不是决定项目能否写进简历的唯一标准。真正需要考虑的是，你能否独立做到：

- 解释项目为什么要做；
- 解释完整输入到报告的流程；
- 说清楚一个核心 checker 的逻辑；
- 解释实验指标和适用边界；
- 运行测试并判断结果是否合理；
- 当 LLM 生成错误代码时，能够定位或至少通过实验发现问题。

如果目前还不能熟练解释 auto planning、evaluator replay 和实验口径，就不要使用偏研究版本。先使用保守版，同时根据以下文档补足理解：

- `AUTO_BENCHMARK_AUDITING_LEARNING_GUIDE_zh.md`
- `reports/universal_audit_experiment_20260713/EXPERIMENT_ANALYSIS.md`
- `PROJECT_SUMMARY_FOR_CLAUDE.md`

---

## 八、最终建议

当前最推荐放入简历的是“更简短、更加保守的版本”。

原因不是项目成果不够，而是简历的目标不是展示所有技术名词，而是让面试官快速理解：

```text
你发现了 benchmark 本身可能有错误
-> 设计并实现了自动审计原型
-> 在多个公开数据集上做了实验
-> 有可验证的效果提升
-> 清楚系统目前仍有哪些边界
```

这种写法比声称“解决任意 benchmark 自动查错”更可信，也更容易在面试中守住。

---

## 九、专门申请 LLM Evaluation 岗位的最终推荐版本

如果目标岗位明确是 LLM Evaluation、Benchmark、数据质量或模型评测，可以使用下面这版。它比通用实习版本技术性更强，但没有把尚未完成的执行审计写成成果。

```latex
\item \textbf{BenchAudit：LLM/Agent Benchmark 数据质量与评分器审计框架}：
将 benchmark 统一建模为 task、context、output contract、oracle 与 evaluator 等 artifacts，构建自动类型识别与审计计划，适配 QA、SWE-bench、Workspace-Bench 和 Terminal-Bench 的不同评分语义；
实现静态一致性检查、evaluator replay、metamorphic/mutation testing 与结构化 LLM auditor，并通过证据分级区分 confirmed、review 和 unsupported，支持可复现的合成缺陷注入与回归评估；
在 9 个公开评测集上完成实验与消融验证，SVAMP-Platinum candidate F1 达 \textbf{0.914}；针对已定义的 structural mutations，回归召回率达到 \textbf{100\%}，并修复 Agent benchmark 因标量 gold 假设导致的系统性误报。
\githublink{https://github.com/SUPERZJ827/BenchAudit} \hfill 2026年6月--至今
```

### 如果简历空间较紧，使用两行压缩版

```latex
\item \textbf{BenchAudit：LLM Benchmark 数据质量与 Evaluator 审计}：
构建 artifact-aware 自动审计框架，统一检查 task、context、oracle、output contract 与 evaluator，组合静态规则、evaluator replay、metamorphic/mutation testing 和结构化 LLM auditor，并适配 QA、SWE 与 Agent benchmark 的不同评分语义；
在 9 个公开评测集上完成验证，SVAMP-Platinum candidate F1 达 \textbf{0.914}，已定义合成结构缺陷的回归 recall 达 \textbf{100\%}。
\githublink{https://github.com/SUPERZJ827/BenchAudit} \hfill 2026年6月--至今
```

### 为什么这版适合 LLM Evaluation

它直接展示了该岗位通常关心的四类能力：

1. **Evaluation schema**：理解 task、oracle、evaluator 和 output contract 不是同一概念；
2. **Evaluator validation**：不仅验证 gold 能通过，也测试合理等价解和错误 mutation；
3. **Benchmark adaptation**：理解 QA、代码和 Agent benchmark 的评分语义不同；
4. **Evaluation methodology**：报告 candidate、synthetic recall、evidence grade 和 unsupported，而不是只展示一个最好看的数字。

### 面试时必须能够解释的六个问题

使用这版之前，至少要准备好回答：

1. 为什么 oracle 和 evaluator 必须分开建模？
2. evaluator replay、metamorphic testing 和 mutation testing 分别发现什么问题？
3. 为什么 Workspace/Terminal 没有标量 gold 不代表缺少 oracle？
4. `candidate F1=0.914` 的标签、样本和统计口径是什么？
5. 为什么 synthetic structural recall=100% 不等于真实缺陷 recall=100%？
6. 当前系统还有哪些 unsupported 能力，例如完整环境重放、trace clustering 和 contamination audit？

对于 LLM Evaluation 岗位，能够主动说明第 5、6 点通常比单纯展示“100%”更加分，因为这体现了对评测有效性和实验边界的理解。
