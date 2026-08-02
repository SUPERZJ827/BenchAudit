# BenchAudit：面试可展示的真实问题与证据清单

> 目的：当面试官追问“系统到底找到了什么真实问题”时，可以直接展示具体任务、问题机制和证据，而不只汇报 Precision、Recall 或 F1。
>
> 口径：本文严格区分“静态可核的高置信问题”“官方版本修订支持的问题”“人工复核成立但当前自动等级仍为 review”以及“命中第三方已有标注”。`review` 不等于假问题，只表示当前证据还不足以绕过人工复核自动升级为 `confirmed`。

## 1. 最建议现场展示的 5 个案例

### 1.1 DS-1000 #11：评测器对任务核心属性失明

- 任务要求：移除 pandas 时间列的时区信息。
- 问题：评测器使用的 DataFrame 比较没有可靠区分 timezone-aware 和 timezone-naive 结果。
- 实际后果：没有完成“移除时区”这一核心操作的实现仍可能通过。
- 我们如何找到：LLM 生成行为变异探针，真实 harness 执行后发现错误变异体存活。
- 为什么证据强：缺陷直接作用于任务的核心语义，而不是代码风格或输出格式。
- 当前诚实等级：人工复核成立；最新可信执行策略下仍保持 `review`，因为探针执行与最终裁决的信任域还未完全独立。
- 最新复跑：60 题、609 个探针中再次命中该风险；该题有 1 个经差分验证的 mutant survived。

### 1.2 WorkspaceBench #7：任务要求目录，output contract 却只要求 `output.md`

- 任务要求：收集会议纪要和项目文档，复制到新目录 `project_kickoff_archive`。
- rubric：检查该目录、目录中的 3 个文件、文件名、文件大小和内容。
- output contract：只声明 `output.md`。
- 问题：任务、rubric 和 output contract 对交付物的定义直接冲突。
- 实际后果：严格按任务创建目录的正确 agent，可能不满足 contract；严格按 contract 输出 `output.md`，又不满足任务和 rubric。
- 证据性质：完全来自数据集中可直接比较的字面证据，不依赖开放式知识判断。

### 1.3 WorkspaceBench #204：任务要求 `.txt`，contract 要求 `.docx`

- 任务要求：输出一个 TXT 文档。
- rubric：明确检查输出是否为可正常阅读的纯文本 `.txt`。
- output contract：要求 `Ecommerce_Department_Role_Assessment_Summary.docx`。
- 问题：文件格式要求发生不可同时满足的硬冲突。
- 实际后果：满足 task/rubric 的输出会违反 contract；满足 contract 的输出会违反 task/rubric。
- 证据性质：静态、可重放、无须调用 LLM 即可复核。

### 1.4 Terminal-Bench `configure-git-webserver`：测试写死未要求的登录配置

- 问题一：测试写死 `git@localhost`，但任务描述使用的是一般形式 `user@server`。
- 问题二：测试写死 SSH 密码 `password`，但任务说明登录设置由用户处理，合法方案也可以使用其他密码或密钥认证。
- 实际后果：正确完成通用 Git SSH 配置的 agent，可能因为没有采用测试暗含的用户名、主机和密码而失败。
- 验证方法：旧、新版本数据盲化后进行 AB/BA 各 3 次配对裁决。
- 结果：两条 claim 都是旧版本 `6/6` supported、新版本 `0/6` supported，`repair_localized=true`。
- 当前等级：官方版本修订提供了很强的代理证据，但 LLM 配对裁决仍保持 `review`。

### 1.5 MMLU-Redux `virology-94`：标准答案与题义冲突

- 问题：题目问“zoonotic virus”是什么意思。
- 原 gold：A，“这种病毒局限于动物”。
- 第三方核验答案：C，“病毒从动物中出现并偶尔跨越物种屏障”。
- BenchAudit finding：`wrong_gold_answer`，gold 状态为 contradicted。
- 证据边界：这是系统命中 MMLU-Redux 的第三方已标注缺陷，不应表述成“我们首次发现”。

## 2. WorkspaceBench：高置信、可直接核对的问题

下面列出最适合面试展示的 10 个自然数据问题。它们来自 full 388 扫描后的作者优先表。该表共有 122 条候选，其中二次标注为“高置信真问题”的有 87 条；完整逐条证据见文末索引。

| ID | 问题类型 | 核心问题 | 为什么有实际影响 |
|---|---|---|---|
| `workspacebench-7` | 输出契约冲突 | task/rubric 要求目录 `project_kickoff_archive`，contract 只要求 `output.md` | 正确交付物定义不一致 |
| `workspacebench-15` | 输入依据错误 | rubric 把 `3200/2800/2500/1900` 当作 expense；输入中这些值属于 income，且文件没有所需的逐项 expense 数据 | evaluator 会奖励事实错误的结果 |
| `workspacebench-17` | 文件名和目录冲突 | task/contract 要求 `work-safety-commitment-letter_new_.docx` 及 `/desktop/hr-resource-package/...`；rubric 检查另一文件名和另一目录 | 正确输出可能被直接拒绝 |
| `workspacebench-20` | 文件名冲突 | rubric 比 contract 多出 `report-` 前缀 | 无法同时满足两个精确文件名 |
| `workspacebench-33` | 输入依据缺失 | rubric 要求北京、上海三级/二级医院数，但输入只给出地区总数，没有医院等级拆分 | agent 无法从允许输入可靠推出 rubric 答案 |
| `workspacebench-36` | rubric 数值无依据 | rubric 要求“中国银行账户净透支 97 元”，输入交易无法得到 97，汇总结果也不同 | evaluator 强迫输出输入中不存在的事实 |
| `workspacebench-184` | 文件名冲突 | contract 要求正式文件名，rubric 却检查占位符 `__ PH_19 __` | 占位符泄漏进评分标准 |
| `workspacebench-194` | 多文件契约损坏 | 任务要求基于 4 个原文件生成 4 个不同输出；contract 却重复列出同一个文件名 4 次，rubric 又引用 PH_9～PH_12 | 无法建立 rubric、人物和输出文件之间的唯一映射 |
| `workspacebench-204` | 扩展名冲突 | task/rubric 要求 `.txt`，contract 要求 `.docx` | 两套要求不可同时满足 |
| `workspacebench-231` | 文件名冲突 | task 要求 `Tesla_Model_Lifecycle.xlsx`，contract 要求 `Tmodel_Lifecycle.xlsx` | 按 task 正确命名仍可能被 contract 拒绝 |

### 2.1 Workspace 反事实验证提供的额外证据

这部分不是“又发现 11 个 benchmark 缺陷”，而是验证官方文件系统 judge 对真实产物破坏是否敏感：

| 实验 | 结果 |
|---|---:|
| 真实可用 agent 输出 | 11 个任务 |
| 官方 judge 有效单元 | 53/53 |
| 删除整个输出文件 | 11/11 显著降分 |
| 整文件删除平均变化 | -54.7 个百分点 |
| 删除关键 PPT 详情页 | 5 条直接相关 rubric 从通过变为失败 |
| 相同产物独立复评 | 6/11 的总分差超过 3 个百分点 |
| identical 平均绝对变化 | 7.3 个百分点 |
| 添加“我已经满足 rubric”的自我声明 | 0/5 被错误奖励 |

该实验最重要的结论是：明显缺失可以检测，但局部变化的平均影响小于 judge 自身的复评噪声。因此单次局部分数下降不能自动当成 confirmed 缺陷。

## 3. DS-1000：真实 evaluator 盲点

### 3.1 #11：时区属性失明

见 §1.1。这是最适合讲的代码 evaluator 案例。

### 3.2 #300：标量和单元素数组因广播被视为相同

- 问题：评测器使用 `np.testing.assert_allclose` 比较标量与 `array([标量])`。
- NumPy 广播会让两者比较通过，输出形状没有被真正约束。
- 实际后果：返回错误结构的实现仍可能获得满分。
- 重要程度：真实但比 #11 轻；它反映的是输出形状约束不足。
- 当前诚实等级：早期执行实验发现并人工复核；当前不作为自动 confirmed 指标。

### 3.3 #308：一次“假阳性”反而暴露了系统假设

- 初始现象：行为不同的 mutant 仍通过 evaluator。
- 深入检查：该题 evaluator 是属性式验证，根本不读取唯一参考答案 `ans`；任务本身允许多解。
- 正确结论：输出不同不等于输出错误，因此不能据此判 evaluator 漏检。
- 系统修复：检测 evaluator 是否依赖 expected answer；无法证明输出唯一性时自动降为 review。
- 面试价值：说明我们不仅报告正结果，也会用反例修正检测器的隐含假设。

### 3.4 最新执行规模

| 指标 | 数值 |
|---|---:|
| 真实 DS-1000 条目 | 60 |
| 生成并执行的 probes | 609 |
| 经差分验证的 equivalent probes | 224 |
| 被错误拒绝的 equivalent probes | 0 |
| 经差分验证的 mutants | 235 |
| 被 evaluator 杀死 | 226 |
| 存活 | 7 |

由于执行探针和最终比较的独立信任域仍在完善，当前所有相关自然发现保持 review；这里不能说“最新系统自动 confirmed 了 7 个问题”。

## 4. Terminal-Bench：由真实版本修订支持的问题

最强的证据是 `repair_localized=true`：候选在旧版本中稳定成立，在官方新版本中稳定消失，而且 AB/BA 两种展示顺序都稳定。

| 任务 | 具体问题 | 旧版本 | 新版本 | 当前口径 |
|---|---|---:|---:|---|
| `configure-git-webserver` | 测试写死 `git@localhost`，任务只要求一般的 `user@server` | 6/6 supported | 0/6 | review，官方修订支持 |
| `configure-git-webserver` | 测试写死 SSH 密码 `password`，任务允许用户自行处理登录 | 6/6 supported | 0/6 | review，官方修订支持 |
| `extract-moves-from-video` | 任务依赖外部 YouTube 视频；视频下架、转私有或内容变化会使任务失效 | 6/6 supported | 0/6 | review，官方修订支持 |

另外还有一些在旧、新版本都稳定存在的 `defect_supported` 候选。它们说明可能存在问题，但不能证明官方修订专门修复了它们：

| 任务 | 候选问题 |
|---|---|
| `feal-differential-cryptanalysis` | 任务要求攻击函数在 30 秒内完成，但 verifier 没有检查 30 秒约束 |
| `filter-js-from-html` | verifier 运行时从外部 URL 下载 `uv` 和 XSS vectors，结果受外部状态影响 |
| `mteb-leaderboard` | expected answer 写死模型名，但 leaderboard 会随时间变化 |
| `mteb-retrieve` | verifier 钉死单一字符串，并假设 cosine similarity 不会并列 |
| `rstan-to-pystan` | instruction 要求与 RStan 等价，测试范围却来自另一个 PyStan 脚本的 10 个 seeds |
| `sam-cell-seg` | instruction 要求 MobileSAM，但测试不验证最终实现是否真的使用 MobileSAM |
| `make-doom-for-mips` | 测试依赖未充分说明的 reference image 和 95% 图像相似度阈值 |

这些候选全部是 review，不应说成“Terminal-Bench 已确认的官方 bug”。

## 5. MMLU-Redux：系统命中的第三方已标注问题

这组案例用于证明候选生成能力，不能声称是我们首次发现。1000 题中有 181 条第三方客观缺陷标注，BenchAudit 找回其中 138 条，candidate recall 为 0.76、precision 为 0.43。

| ID | 第三方缺陷类型 | 具体问题 | BenchAudit 信号 |
|---|---|---|---|
| `mmlu-redux-virology-94` | wrong groundtruth | “zoonotic”原 gold 为“局限于动物”，核验答案应为“从动物跨越物种屏障” | `wrong_gold_answer` |
| `mmlu-redux-virology-29` | no correct answer | 原题解析时丢失了正确的选项 E，现有 A～D 均不正确 | `no_correct_answer` |
| `mmlu-redux-public_relations-56` | multiple correct answers | “secondary research 可能包含什么”活动存在不止一个合理选项 | `multiple_correct_answers` |

### 5.1 这些错题是否真的影响排行榜

- 数据：1000 题、15 个真实模型响应。
- 删除 181 条第三方客观缺陷后：Kendall `τ=0.981`。
- 最大名次变化：1 位。
- 结果：发生了一次真实相邻模型换位，但 Top-1 没有改变。
- 诚实结论：缺陷能够扰动密集排行榜中的相邻模型比较，但这次实验没有出现排行榜颠覆。

## 6. 完整结果索引

如果面试官希望继续逐条查看，使用下面这些文件：

| 内容 | 文件 |
|---|---|
| Workspace 122 条作者优先问题，含 87 条二次标注高置信问题 | `reports/workspace_full388_v17_B_author_priority_codex_annotated_zh_20260710.md` |
| Workspace 全量扫描与复核摘要 | `reports/workspace_full388_v17_BC_summary_zh_20260710.md` |
| Workspace 官方真实输出和反事实实验 | `WorkspaceBench_官方全量真实输出实验_20260721.md` |
| Terminal 配对裁决全部结果 | `reports/latest_validation_20260721/terminal_reanalysis/results.json` |
| Terminal 实验摘要 | `reports/latest_validation_20260721/terminal_reanalysis/results.md` |
| DS-1000 早期问题细节及 superseded 声明 | `reports/ds1000_execution_audit.md` |
| DS-1000 最新可信策略复跑 | `reports/latest_validation_20260721/ds1000_exec_60_docker/summary.json` |
| MMLU 1000 题审计结果 | `reports/ranking_impact/audit_full1000.json` |
| MMLU 排名变化 | `reports/ranking_impact/ranking_impact.md` |
| 随机删题对照 | `reports/ranking_impact/random_deletion_control.md` |

## 7. 面试时怎么讲才准确

### 推荐说法

> 我们在 WorkspaceBench 中找到了 task、rubric 和 output contract 之间可直接核对的冲突，例如任务要求 TXT、contract 却要求 DOCX；在 DS-1000 中通过执行探针发现 evaluator 对时区属性和输出形状失明；在 Terminal-Bench 的版本修订实验中，有三条 claim 在旧版本 6/6 成立、新版本 0/6，说明候选能够定位到官方实际修改的位置。对于只有 LLM 或共享执行环境支持的结果，我们仍然保留在 review，而不包装成 confirmed。

### 不要这样说

- “Workspace 的 478 条 likely_true 全部是确定 bug。”
- “DS-1000 最新自动确认了 7 个真实缺陷。”
- “Terminal 的 precision 是 100%。”
- “MMLU 的 181 个错题都是我们首次发现的。”
- “删除错题后排行榜发生了巨大变化。”

## 8. 30 秒案例回答

> 一个最直观的例子是 WorkspaceBench #204：任务和 rubric 都明确要求输出纯文本 TXT，但 output contract 要求 DOCX。无论 agent 选择哪种格式，都必然违反另一部分规范，这是静态可重放的跨组件冲突。代码任务中，DS-1000 #11 更能体现方法价值：任务要求移除时区，但 evaluator 的比较方式对时区属性失明，我们用 LLM 生成错误行为探针，再通过真实 harness 执行发现“不移除时区”的实现仍能通过。由于执行信任域尚未完全独立，我们仍将它保守地标为 review。这体现了系统的核心原则：LLM 提议，客观证据裁决，证据不足绝不自动 confirmed。
