# BenchAudit 非代码缺陷模式 Memory：隔离探索结论

日期：2026-07-25

分支：`research/pattern-memory-noncode-lobo-20260725`

状态：**探索完成，暂不合并、不推送**

## 结论

这轮没有得到足以接入正式系统的正结果。

最重要的发现是：当前两个有独立 confirmed 证据的非代码 benchmark，
其可用缺陷家族完全不重叠。把源 benchmark 的高频家族静态搬到新
benchmark，会发生明显负迁移；让系统在目标 benchmark 内根据已经执行的
探针反馈在线学习，能得到小幅点估计提升，但确认样本太少，随机题序区间
覆盖零，尚不能排除随机波动。

因此当前正确决策是：

1. pattern memory 保持 **review-only**；
2. 不让 memory 直接控制正式探针路由；
3. 优先收集跨 benchmark 的真实 confirmed 缺陷和运行轨迹；
4. 等出现独立、冻结的新 benchmark 后再做确认性实验。

## 数据与证据边界

| 数据集 | 题数 | 严格 confirmed 证据 | 本轮用途 |
|---|---:|---:|---|
| WorkspaceBench | 388 | 5 findings / 5 items，均为 `placeholder_leak` | labelled target/source |
| GDPval | 220 | 7 findings / 5 items，分属 6 个家族 | labelled target/source |
| JobBench | 65 | 无独立缺陷标注 | 只做未见数据结构检查，不当作 clean label |

GDPval 的 7 个 confirmed finding 包括：

- `task_output_filename`：2
- `task_output_format`：1
- `rubric_output_filename`：1
- `rubric_reference_filename`：1
- `rubric_column_conflict`：1
- `task_rubric_column_difference`：1

WorkspaceBench 只使用重新标注中有确定性证据、且不依赖
`output_files` 为 gold contract 的 5 个 placeholder finding。遵循既定边界：
WorkspaceBench 的最终输出由 rubric 评分，不能把 `output_files` 当作可信
交付清单。

两者的 confirmed family 交集：

```text
WorkspaceBench ∩ GDPval = ∅
```

这使得“缺陷家族能否跨 benchmark 迁移”在现有自然数据上不可识别，而不是
简单的模型效果差。

## 被否决的漂亮结果

早期规则实验曾出现很大的正向点估计，但复核发现它错误地把
WorkspaceBench `output_files` 当作 gold manifest。撤销这一假设后，增益
消失。该结果已否决，没有进入最终脚本、报告结论或 GitHub。

JobBench 初次扫描还出现过 1 个文件名冲突候选。逐条回放发现任务要求两个
输出文件，而 rubric 只检查其中一个，属于合法子集检查，不是矛盾。加入
“双方都只能声明一个交付文件”前置条件后，候选归零。

这两个反例共同说明：结构规则的结果不能因为可重复，就自动叫
“objective ground truth”；前置条件和独立证据必须分开。

## 在线自适应实验

### 协议

- 零 LLM/API 调用；
- 每题预算分别为 1、2、3 个 probe；
- 2,000 个随机题序；
- 所有策略逐题花费完全相同；
- task/rubric 文本值、当前和未来 target 标签都不参与选择；
- 当前题的全部 probe 选完后，才揭示本题反馈；
- memory 只作为弱先验，promotion ceiling 固定为 `review`。

比较策略：

- `A_frozen_generic`：固定通用顺序；
- `R_random_static`：每轮随机一次，整轮固定；
- `R_random_per_item`：每题重新随机；
- `D_source_memory`：按源 benchmark confirmed yield 静态排序；
- `H_online_ucb1`：只根据目标 benchmark 过去反馈在线更新；
- `I_memory_seeded_ucb1`：memory 弱先验 + 同一在线更新。

### 预算为 3 时的主要结果

| source → target | 随机逐题 recall | 静态 memory | 在线 UCB1 | memory + 在线 | 在线减随机 |
|---|---:|---:|---:|---:|---:|
| GDPval → WorkspaceBench | 0.4365 | 0.0000 | 0.4495 | 0.4475 | +0.0130 |
| WorkspaceBench → GDPval | 0.4035 | 0.2000 | 0.4512 | 0.4460 | +0.0477 |

在线 UCB1 相对随机逐题的随机题序中央 90% 差值区间，在两个方向均为：

```text
[-0.4, +0.6]
```

这个区间是 2,000 个随机题序的经验区间，不是总体置信区间。只有 5 个
confirmed target item，因此不能把 +1.3 或 +4.8 个百分点写成可靠提升。

### 三档预算的 recall

| source → target | budget | 随机逐题 | 静态 memory | 在线 UCB1 | memory + 在线 |
|---|---:|---:|---:|---:|---:|
| GDPval → WorkspaceBench | 1 | 0.1484 | 0.0000 | 0.1436 | 0.1436 |
| GDPval → WorkspaceBench | 2 | 0.2938 | 0.0000 | 0.2999 | 0.3052 |
| GDPval → WorkspaceBench | 3 | 0.4365 | 0.0000 | 0.4495 | 0.4475 |
| WorkspaceBench → GDPval | 1 | 0.1439 | 0.0000 | 0.1545 | 0.1622 |
| WorkspaceBench → GDPval | 2 | 0.2815 | 0.0000 | 0.3067 | 0.3037 |
| WorkspaceBench → GDPval | 3 | 0.4035 | 0.2000 | 0.4512 | 0.4460 |

静态 memory 的失败与 family 交集为零完全一致。memory 弱先验没有稳定优于
纯目标内学习，说明历史频率目前不应获得路由控制权。

### 参数敏感性

在 WorkspaceBench 上，把 UCB 探索常数从标准的 `sqrt(2)` 降到 `0.1`，
budget=3 的 recall 从 0.4495 上升到 0.6997。但 5 个缺陷全部属于同一个
family，低探索常数会在首次命中后快速集中到该 family；该参数又是在开发
数据上看到结果后分析的，因此只能解释机制，不能作为确认性结果。

GDPval 的 7 个 finding 分散在 6 个 family，参数变化不能带来相似增益。
这说明在线利用只在“同类缺陷会重复出现”时有明显价值。

## 代码与复现检查

- 新增 5 个针对未来标签泄漏、等预算、证据过滤和 applicability 的测试；
- 全仓测试：`700 passed in 22.25s`；
- 两次完整复跑稳定摘要 SHA256：
  `e9af9b527494962e5b8a36eea3a7383e240198d0e402a26c28c82b86b835079a`；
- 两份结果 JSON 文件 SHA256：
  `00eecb49e652fdaedd38dc29f1e430e610bfd898620557363cc714aa6802f96a`；
- 两份 JSON 逐字节一致；
- 无 LLM/API 调用；
- 无 target 文本值或未来 outcome 泄漏；
- 所有 memory 派生信号仍为 review-only。

## 为什么暂不推送

代码机制通过测试，但研究结论没有达到产品化门槛：

1. 只有 10 个 labelled target item（两个方向各 5 个）；
2. 两个 benchmark 的 confirmed family 交集为零；
3. 第三个真实 holdout 没有独立 defect label；
4. 在线增益的经验区间覆盖零；
5. 最显著的参数结果来自单一重复 family，且属于事后敏感性分析。

把这版直接接入正式 CLI，会把“可运行的探索代码”误写成“已验证的自适应
能力”。因此分支保留本地，不污染 `main` 和 GitHub。

## 下一步需要收集什么

最终 aggregate score 不够。为了最大限度找错，最好为每次真实运行保留：

- benchmark 名称、版本、task ID；
- 模型/agent、配置、seed、run ID；
- 原始最终输出；
- 每条 rubric / test / evaluator 的逐项 verdict 与分数；
- evaluator 输入、输出、错误和版本；
- 工具调用与关键 trajectory event；
- 执行 transcript、日志及其 SHA256；
- 生成的 artifact 路径、类型、大小和 hash；
- 运行状态、异常、耗时和成本；
- 同题多模型/多次运行的对应关系。

仓库已有 `TraceBundle v1`，不需要再造一套大型 schema。新数据优先转换为该
格式，再做：

1. run-level contradiction；
2. identical control；
3. 多模型响应异常；
4. evaluator 与 artifact 不一致；
5. 排名影响重算。

下一次确认性 memory 实验至少应满足：

- 有一个从未用于开发的冻结 target benchmark；
- 至少两个 source benchmark 独立支持同一 defect family；
- target 中存在多个已独立确认的同 family witness；
- memory、随机、静态规则、目标内在线学习严格等预算；
- 报告随机顺序对照和负结果；
- memory 信号仍不能直接升级为 confirmed。

## 最终判断

“缺陷模式库”方向仍有价值，但当前证据只支持把它作为低风险先验和解释
工具，不支持把它作为自动路由器。眼下最大的瓶颈不是再写一个算法，而是
缺少跨 benchmark、带逐项 verifier 结果和独立 confirmed 标签的真实运行
资料。
