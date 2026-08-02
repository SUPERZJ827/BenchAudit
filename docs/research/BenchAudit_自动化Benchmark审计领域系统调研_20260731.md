# 自动化 AI/LLM Benchmark 审计：系统性研究综述、技术地图与研究空白

> 版本：2026-07-31
> 本地交付目录：`/home/zhoujun/llmdata/after623/docs/research/`
> 面向课题：BenchAudit——从候选发现到可重放确认、修复与排名影响
> 调研范围：benchmark 数据缺陷、污染与动态评测、LLM-as-a-Judge 元评测、测试充分性、元形/变异测试、证据溯源、选择性评测、修复与 leaderboard 影响
> 文献规模：正文重点讨论 60 余项工作，文末索引覆盖 80 余项论文、规范与官方资源

## 摘要

AI benchmark 已不再只是一个静态数据集，而是由任务描述、输入资产、参考答案、rubric、执行环境、测试套件、评分程序、聚合规则和 leaderboard 共同组成的测量系统。任何一层的错误，都可能让“模型能力差异”被错误地解释为模型进步或退步。

过去几年的研究已经形成六条相对独立的路线：

1. 用模型响应模式、训练动态、IRT 或 LLM 发现疑似错标和歧义题；
2. 用人工复核、专家重标或 benchmark 修订确认并修复缺陷；
3. 用污染检测、动态出题和私有测试减轻训练—测试泄漏；
4. 用 LLM judge 元评测、受控扰动和选择性评测分析 evaluator 可靠性；
5. 用 mutation testing、metamorphic testing 和增强测试检验代码/agent benchmark 的 oracle 强度；
6. 用 datasheet、provenance 和可复现实验记录说明数据从哪里来、运行了什么。

但这些路线之间存在一个明显断层：**大多数方法擅长发现候选，少数方法能通过人工确认，极少方法能把某个具体 finding 自动提升为可由第三方本地重放的 confirmed 缺陷；更少工作完成“确认—修复—回归—排名影响”的闭环。**

因此，对 BenchAudit 最有价值的研究定位不是再做一个高召回 LLM 审稿器，而是建立一套分层系统：

```text
大规模候选发现
    ↓
关系/契约级证据抽取
    ↓
协议相关的机械 proof contract
    ↓
fail-closed promotion 与主动弃权
    ↓
最小修复、确定性回归、排名影响
```

这一路线与现有工作的关键差异是：**候选生成可以依赖 LLM，但 confirmed 结论不能仅由 LLM、多模型共识或自洽投票产生；它必须绑定可验证输入、版本、执行环境、比较器和证明重放。**

---

## 0. 调研方法与阅读说明

### 0.1 检索方法

本次调研以 2026-07-31 为资料截止点，围绕下列关键词簇交叉检索：

- benchmark audit、benchmark defect、label error、ground-truth error；
- LLM-as-a-Judge、meta-evaluation、judge bias、rubric reliability；
- benchmark contamination、dynamic benchmark、decontamination；
- metamorphic testing、mutation testing、test adequacy、equivalent mutant；
- evaluator provenance、dataset documentation、attestation、reproducibility；
- benchmark repair、leaderboard instability、construct validity。

来源优先级为：正式会议/期刊页面和论文正文 > OpenReview 正式接收页面 > arXiv 原论文 > 官方规范/项目文档 > 综述。搜索结果页、博客转述和无法核实的二手数字不作为关键结论依据。综述用于发现分类和相关工作，具体数字尽量回到原论文核验。

### 0.2 纳入标准

文献满足至少一个条件：

1. 直接发现、验证或修复 benchmark/evaluator 缺陷；
2. 提供可迁移的候选排序、关系测试、差分执行或证据机制；
3. 解释 benchmark 分数的测量效度、污染、排名稳定性；
4. 为数据/代码/执行 provenance 提供可验证标准；
5. 是 2025–2026 年直接改变该领域技术趋势的最新工作。

### 0.3 发表状态标记

本文将正式会议/期刊工作与预印本同时纳入，因为 2026 年 judge audit、agent benchmark audit 和 mutation-guided evaluation 发展很快。但二者证据成熟度不同：文末明确标为 `preprint` 的工作应视为最新研究信号，不应写成已由顶会同行评审确认。OpenReview workshop、withdrawn submission 与正式 ICLR/ICML/ACL 论文也不等价。

### 0.4 本综述的边界

- 不是穷尽式系统综述，没有声称覆盖所有语言、视觉、公平性和安全 benchmark；
- 重点是“审计测量系统”，而不是一般 LLM evaluation survey；
- 对近期论文只采用其公开实验结论，不把作者声称自动升级为 BenchAudit 的已验证事实；
- 文中提出的研究空白是基于所覆盖文献的综合判断，需要在正式投稿前再做一次 venue-specific related-work 检索。

---

## 1. 本综述回答什么问题

### 1.1 核心研究问题

本综述围绕五个问题组织：

1. benchmark 为什么会错，错误发生在哪些层？
2. 现有工作怎样发现、确认和修复这些错误？
3. LLM judge、元形测试和变异测试分别能提供什么证据，不能提供什么证据？
4. “高准确率候选检测”与“可机器确认缺陷”之间还缺什么？
5. BenchAudit 应把创新集中在哪些尚未被解决、同时可量化的空白上？

### 1.2 不把哪些问题混在一起

以下对象经常被统称为“评测可靠性”，但研究问题不同：

| 对象 | 典型问题 | 审计单位 | 需要的证据 |
|---|---|---|---|
| benchmark item | gold 错、题意歧义、输入缺失 | 题目/样本 | task、input、gold、reference |
| evaluator/test suite | 错误答案仍通过、正确答案被拒 | 评分器/测试 | 对照程序、执行结果、差分输入 |
| LLM judge | 位置、长度、措辞使 verdict 翻转 | 单次 verdict | 受控反事实、人工标签或关系约束 |
| dataset/model contamination | 模型训练见过测试数据 | 模型—数据对 | 训练来源、行为统计、时间/版本证据 |
| benchmark construct | 分数没有测到宣称的能力 | 整体测量设计 | 构念定义、任务抽样、评分效度 |
| leaderboard | 小改动导致模型排序变化 | 模型集合 | 全量输出、重评分、排名不确定性 |

这一区分非常重要。比如，“judge 对格式改写不稳定”证明 evaluator 存在关系违例，却不自动证明原 verdict 错；“变异体通过测试”说明测试可能不足，也不自动证明变异体语义错误，因为存在 equivalent mutant 问题。

---

## 2. 一个统一的 benchmark 测量模型

把一个 benchmark item 表示为：

\[
B_i=(T_i, I_i, O_i, R_i, E_i, A_i)
\]

其中：

- \(T_i\)：任务规范或 issue；
- \(I_i\)：输入及依赖资产；
- \(O_i\)：参考输出、gold 或声明行为；
- \(R_i\)：rubric、测试套件或评分规则；
- \(E_i\)：执行环境与依赖版本；
- \(A_i\)：聚合、过滤和 leaderboard 规则。

模型 \(M\) 产生输出 \(y_i\)，evaluator \(J\) 给出观测分数：

\[
s_i=J(T_i,I_i,y_i;R_i,E_i)
\]

benchmark 报告的模型分数通常是：

\[
S(M)=A(s_1,\ldots,s_n)
\]

因此，最终排序变化可能来自至少六个来源：模型输出变化、任务抽样变化、gold/rubric 变化、执行环境变化、judge 变化、聚合规则变化。[The Benchmark Lottery](https://arxiv.org/abs/2107.07002) 和 [When Benchmarks are Targets](https://aclanthology.org/2024.acl-long.744/) 分别从任务选择和细微评测配置说明了排名的脆弱性；后者报告 MCQ 选项顺序或答案抽取方式等小改动可使排名变化最多八位。

### 2.1 五级证据阶梯

本文建议用下列证据等级统一比较不同文献：

| 等级 | 名称 | 结论 | 典型方法 |
|---|---|---|---|
| E0 | heuristic signal | “值得看” | 长度、困惑度、关键词、单模型判断 |
| E1 | reviewed candidate | “自动方法认为可疑” | LLM/IRT/训练动态/多模型分歧 |
| E2 | externally adjudicated | “人工或专家确认” | 双人标注、专家复核、官方 errata |
| E3 | replay-confirmed | “机械证据可重放” | 确定性 replay、差分 oracle、proof contract |
| E4 | repaired and regression-tested | “缺陷已修复且无回归” | 最小补丁、全量回归、旧 finding 消失 |
| E5 | consequentially validated | “修复改变了实际结论” | 重新评测、排名/效应量/决策变化 |

这个阶梯不是说人工证据一定弱于程序证据；专家判断可能是语义问题的最佳证据。它强调的是：**不要把 E1 的候选准确率写成 E3 的机器确认率，也不要把 E3 的单条证明写成 E5 的整体影响。**

---

## 3. Benchmark 缺陷的系统分类

### 3.1 数据与标签层

- gold label 错误；
- 多个答案都合理，但只接受一个；
- 问题本身不可解或缺少必要上下文；
- 重复、近重复、数据泄漏；
- 上游数据错误被下游 benchmark 继承；
- 标注政策漂移、版本之间 label 不一致。

[Pervasive Label Errors in Test Sets](https://arxiv.org/abs/2103.14749) 在十个常用数据集上估计平均至少 3.3% 的测试集错误，并展示清洗后模型排序可能变化；[MMLU-Redux](https://aclanthology.org/2025.naacl-long.262/) 对 5,700 个 MMLU 题目重标，发现分析过的 Virology 子集中 57% 有问题，并报告清洗前后性能和排名存在显著差异；[Platinum Benchmarks](https://openreview.net/pdf?id=XSeN6xZtZ9) 则利用多模型行为优先排序，再由人工清洗多个推理 benchmark。

### 3.2 规范与契约层

- task 没授权 rubric 中的额外要求；
- issue 与 patch 实际解决的问题不一致；
- input manifest、task、reference、rubric 相互矛盾；
- 文件名、schema、字段角色不一致；
- 隐含依赖或环境要求未声明。

2026 年的 [PAIChecker](https://arxiv.org/abs/2607.28587) 系统研究 SWE-bench 类 benchmark 的 issue—PR 错配；[Auto Benchmark Audit, ABA](https://arxiv.org/abs/2605.26079) 用 agent 审计多领域 benchmark 的隐含依赖、规范缺口和评分逻辑；[ELT-Bench-Verified](https://arxiv.org/abs/2603.29399) 发现数据工程 agent 的部分失败来自刚性 evaluator、歧义规范和错误 ground truth。

### 3.3 Evaluator 与执行层

- 正确输出被格式解析器拒绝；
- 错误输出通过不充分测试；
- timeout 被误当作语义失败；
- 依赖、镜像或随机种子漂移；
- 同一行为因 judge/prompt 版本变化得到不同结论；
- evaluator 派生信息泄漏给被评系统，导致选择偏差。

[EvalPlus](https://arxiv.org/abs/2305.01210) 通过显著增强 HumanEval/MBPP 测试发现原测试通过的错误程序；[STING](https://arxiv.org/abs/2604.01518) 和 [SWE-Mutation](https://arxiv.org/abs/2605.22175) 把焦点进一步转向 SWE-bench/agent 场景中的测试充分性。

### 3.4 聚合与 leaderboard 层

- 平均分掩盖 worst-task 风险；
- 缺失分数、过滤规则和 tie-breaking 改变排名；
- 修复少数高杠杆题目导致局部冠军更替；
- evaluator 配置与被测方法内部选择通道耦合。

[The Benchmark Lottery](https://arxiv.org/abs/2107.07002)、[The Validity of Evaluation Results](https://aclanthology.org/2023.conll-1.19/) 和 [AuditRepairBench](https://arxiv.org/abs/2605.04624) 分别从 benchmark 选择、同构念 benchmark 间排序不一致、evaluator-channel coupling 说明“排行榜”本身也是审计对象。

---

## 4. 研究路线一：错标发现、数据质量与 item prioritization

### 4.1 从监督式数据清洗到 benchmark 审计

早期数据质量方法的目标通常是从训练集中找噪声样本：

- [Data Shapley](https://arxiv.org/abs/1904.02868) 用 Shapley value 衡量训练样本对模型效用的贡献；
- [Efficient Data Valuation](https://arxiv.org/abs/1902.10275) 探索更可扩展的 Shapley 近似；
- [TracIn](https://arxiv.org/abs/2002.08484) 用训练轨迹估计训练样本对预测的影响；
- [Dataset Cartography](https://arxiv.org/abs/2009.10795) 用训练动态划分 easy、ambiguous、hard 样本，hard 区域常含错标；
- [Confident Learning / Pervasive Label Errors](https://arxiv.org/abs/2103.14749) 用模型预测与噪声标签统计优先发现测试集错误。

这类方法的共同结构是：**用模型行为排序候选，再由人工确认。** 它们能把人工预算集中在高风险 item 上，但模型一致不等于 gold 错，模型分歧也可能来自题目真正困难。

### 4.2 LLM 时代的候选发现

近年出现四种主流信号：

1. **多模型共识/分歧**：若大量强模型给出同一非 gold 答案，题目可能错；Platinum Benchmarks、MMLU-Redux 的自动 prioritization 都属于这类。
2. **LLM 语义审计**：直接让模型分析问题、答案、rubric；[Fantastic Bugs](https://arxiv.org/abs/2511.16842) 先用自动模式发现再专家复核，在九个 benchmark 上报告最高 84% 的 Precision@50。
3. **统计测量模型**：[Auditing LLM Benchmarks with IRT](https://arxiv.org/abs/2605.30504) 利用 114 个模型的响应拟合 item 指标，在七个 benchmark 的 top-200 候选上报告 95% precision。
4. **agentic audit**：[ABA](https://arxiv.org/abs/2605.26079) 让 agent 读取规范、环境与 evaluator，覆盖复杂 agent benchmark。

需要同时注意反证。[Can We Trust IRT for AI Evaluation?](https://arxiv.org/abs/2607.15190) 用 18,000 个模拟实验指出：当模型样本少、分布偏离假设时，IRT 的 item 与排名推断可能不可靠；[Rethinking Data Shapley for Data Selection](https://arxiv.org/abs/2405.03875) 也说明数据价值方法在缺少合适效用假设时可能不优于随机选择。

### 4.3 这条路线已解决什么

- 能在大 benchmark 上显著缩小人工审查范围；
- 能识别系统性错标、歧义和上游继承错误；
- 能量化候选 precision、review yield 和清洗后 score shift。

### 4.4 尚未解决什么

- 候选分数很少自带可重放的证明；
- 多模型共识可能是共同偏差或共同污染；
- top-k precision 不代表全量 recall；
- 统计方法依赖模型池，模型池变化会改变 audit 结果；
- 大多数论文在人工确认处结束，未形成修复回归合同。

---

## 5. 研究路线二：污染、泄漏与动态 benchmark

### 5.1 污染不是一种现象

至少要区分：

- exact contamination：测试文本原样进入训练；
- paraphrase/semantic contamination：语义等价变体进入训练；
- label contamination：答案或标签泄漏；
- evaluation-protocol leakage：模型或 agent 知道测试器细节；
- generator—judge preference leakage：生成器和 evaluator 同源导致偏好污染。

[Benchmark Data Contamination Survey](https://arxiv.org/abs/2406.04244) 和 2025 年的 [Static-to-Dynamic Evaluation Survey](https://aclanthology.org/2025.emnlp-main.511/) 提供了较完整分类；后者特别指出动态 benchmark 本身尚缺标准化评价准则。

### 5.2 检测方法

| 方法族 | 代表工作 | 信号 | 主要限制 |
|---|---|---|---|
| 训练语料检索 | [Investigating Data Contamination](https://aclanthology.org/2024.naacl-long.482/) | benchmark 与 corpus 重叠 | 闭源模型不可用，语义泄漏难查 |
| 行为/记忆探针 | 同上 TS-Guessing、[CDD](https://aclanthology.org/2024.findings-acl.716/) | 模型补全、输出分布异常 | 强模型推理与记忆难分 |
| paired significance | [PaCoST](https://aclanthology.org/2024.findings-emnlp.97/) | 原题比同分布 counterpart 更自信 | counterpart 质量决定结论 |
| perplexity/n-gram | [Benchmarking Benchmark Leakage](https://arxiv.org/abs/2404.18824) | token 预测异常 | 受 tokenizer、能力与校准影响 |
| 多层风险建模 | [DCR](https://aclanthology.org/2025.emnlp-main.1173/) | 语义、信息、数据、标签风险 | 风险因子不是训练来源证明 |
| 语义扰动 | [SSA](https://aclanthology.org/2025.emnlp-main.744/) | entity shift 后敏感性 | 变换保语义/保标签需验证 |

[Does Data Contamination Detection Work?](https://aclanthology.org/2025.findings-naacl.291/) 系统评估了 50 篇污染检测论文的底层假设，提醒很多常用假设并未被严格验证；[Oracle Challenges](https://aclanthology.org/2025.coling-main.338/) 也发现不同方法之间可能不一致。

### 5.3 缓解方法

- [CLEAN-EVAL](https://arxiv.org/abs/2311.09154)：用释义和回译生成表面不同、语义相似的新题；
- [LiveBench](https://arxiv.org/abs/2406.19314)：使用近期来源、客观答案和持续更新；
- [MMLU-CF](https://aclanthology.org/2025.acl-long.656/)：公开 validation、保密 test，并从大规模网页来源重新构造；
- [C2LEVA](https://aclanthology.org/2025.findings-acl.116/)：自动更新测试数据并控制发布；
- [Dynabench](https://aclanthology.org/2021.naacl-main.324/)：人—模型循环生成模型当前失败的样本；
- [PALOMA](https://arxiv.org/abs/2312.10523)：强调细粒度语言模型评测和去污染协议。

### 5.4 对 BenchAudit 的启示

污染检测通常只能输出“suspected contaminated”，很难对闭源模型给出 E3 级确认。更合适的集成方式是：

- 把污染信号作为 candidate/routing，不自动进入 confirmed；
- 对可验证的 exact overlap、release/cutoff 关系建立版本化 receipt；
- 把污染修复前后分数与排名变化独立报告；
- 区分“来源关系已证明”和“模型确因记忆而答对”，两者不是同一命题。

---

## 6. 研究路线三：LLM-as-a-Judge 与元评测

### 6.1 从可扩展评测到 judge 本身成为被测对象

[Judging LLM-as-a-Judge / MT-Bench](https://arxiv.org/abs/2306.05685) 推动了 LLM judge 的普及，同时明确展示位置偏差、冗长偏好和自增强偏差；[G-Eval](https://arxiv.org/abs/2303.16634) 用 CoT 和表单式评分提升与人工相关性；[Prometheus](https://arxiv.org/abs/2310.08491) 训练开放 rubric-following evaluator。

随后研究重心从“相关性多高”转向“什么时候会失败”：

- [LLMBar](https://arxiv.org/abs/2310.07641) 构造 419 对对抗式 instruction-following 响应；
- [JudgeBench](https://arxiv.org/abs/2410.12784) 用客观正确性响应对测试 judge，在困难样本上强模型也接近随机；
- [Judging the Judges: Position Bias](https://aclanthology.org/2025.ijcnlp-long.18/) 在约 15 万个 judgment 上分解位置一致性与公平性；
- [The Progress Illusion](https://aclanthology.org/2025.findings-emnlp.1036/) 指出当被比较系统能力接近时，judge 与人工相关性显著降低；
- [GroUSE](https://aclanthology.org/2025.coling-main.304/) 用 144 个 unit tests 检查 grounded QA evaluator 的七种失败模式；
- [TrustJudge](https://iclr.cc/virtual/2026/poster/10011516) 研究评分—比较不一致和偏好传递性；
- [BiasScope](https://openreview.net/pdf?id=QGOw6AU8Lp) 自动发现未知 bias，并构造 JudgeBench-Pro；
- [Preference Leakage](https://openreview.net/pdf?id=grIvSXVJ65) 发现 generator 与 judge 的同模型、继承或同家族关系会污染偏好；
- [MM-JudgeBias](https://aclanthology.org/2026.acl-long.1162/) 对 query、image、response 做组合扰动，覆盖 29 个来源 benchmark 和 26 个多模态 judge；
- [Policy Invariance](https://arxiv.org/abs/2605.06161) 区分语义等价 rubric 改写、阈值改变和真正歧义；
- [BITE](https://openreview.net/forum?id=7g23tYAIDC) 将风格偏差转成黑盒 bandit 攻击，在保语义编辑下抬高 judge 分数。

### 6.2 平均相关性为什么不够

一个 judge 可能同时满足：

- 全局 Spearman 相关性很高；
- 在相近模型之间几乎无法区分；
- 对某些 task、语言或格式极不稳定；
- 在同一 generator family 上有系统偏好；
- 单次 verdict 的置信度没有校准。

因此需要至少四层元评测：

1. **aggregate agreement**：与人工总体相关；
2. **slice reliability**：按任务、难度、模型家族、语言分层；
3. **relational consistency**：不变量、单调性、传递性、局部性；
4. **instance-level risk**：当前 verdict 是否应接受或升级。

2026 年的 [Diagnosing LLM Judge Reliability](https://openreview.net/forum?id=FbDuesI6tD) 把 conformal prediction set 与传递违例结合，代表了从总体指标向逐实例诊断的趋势；[Trust or Escalate](https://arxiv.org/abs/2407.18370) 则用 selective evaluation 在覆盖率与人工一致性之间建立风险保证。

### 6.3 Rubric 也是测量程序

judge 的问题不只来自 base model，也来自 rubric：

- [What Makes the Whole?](https://openreview.net/forum?id=xd9qriSZQh) 研究多属性 compositionality；
- [RULERS](https://arxiv.org/abs/2601.08654) 将自然语言 rubric 编译成版本化规范，使用结构化证据和后处理校准；
- [PReMISE](https://arxiv.org/abs/2605.30803) 从结构充分性、可靠性、偏好拟合和对抗鲁棒性审计 rubric；
- [Can LLMs Write Reliable Rubrics?](https://arxiv.org/abs/2607.12835) 在实验复现任务上元评测自动 rubric；
- [Reliable to Expressive](https://arxiv.org/abs/2606.09165) 表明直接混合动态 rubric 可能增加跨 rubric 方差，需要课程式训练。

这与 BenchAudit 的 task—rubric grounding 问题直接相连：rubric 可以合法却难以客观评分，也可以客观但未被 task 授权。二者必须分开。

### 6.4 现有 judge 审计与“可确认 benchmark 缺陷”的差异

受控反事实非常适合证明：

\[
J(T(z)) \neq J(z)
\]

但若 \(T\) 声称保语义，仍需证明 \(q(T(z))=q(z)\)。因此：

- 格式变化、选项交换、确定性 AST 变换更接近可证关系；
- LLM paraphrase、风格改写通常只能作为 review 信号，除非有独立等价性合同；
- judge verdict flip 是 evaluator relation violation，不自动说明原 verdict 或变换后 verdict 哪一个错误；
- 多次投票降低方差，但不能消除共享系统偏差。

---

## 7. 研究路线四：元形测试、变异测试与 oracle problem

### 7.1 为什么它们适合 benchmark 审计

当无法直接知道正确输出时，元形测试不要求绝对 oracle，而要求输入—输出之间满足关系：

\[
R_I(x,x') \Rightarrow R_O(f(x),f(x'))
\]

[Metamorphic Testing: A Review](https://nottingham-repository.worktribe.com/output/925152/metamorphic-testing-a-review-of-challenges-and-opportunities) 系统总结了该范式；[DeepXplore](https://arxiv.org/abs/1705.06640) 用差分 oracle 和 coverage 测 DNN；[DeepTest](https://arxiv.org/abs/1708.08559) 用图像变换测试自动驾驶模型。

LLM 场景中，[LGMT](https://arxiv.org/abs/2605.23965) 从一阶逻辑等价关系导出 reasoning metamorphic relations；2026 年综述 [Bidirectional Empowerment of MT and LLMs](https://arxiv.org/abs/2605.13898) 整理了 93 项研究，区分“用 MT 测 LLM”和“用 LLM 生成 MT”。

### 7.2 Mutation testing 的基本逻辑

给定正确程序 \(P\)、测试集 \(S\) 与语义改变的变异体 \(P'\)：

\[
S(P)=pass \land S(P')=pass
\]

只说明 \(P'\) survived。要把它解释为测试缺口，还需证明：

\[
\exists x\in D: P(x) \neq P'(x)
\]

且 \(x\) 是任务域内合法输入。否则 \(P'\) 可能是 equivalent mutant 或只在非法输入上不同。[An Empirical Evaluation of Manually Created Equivalent Mutants](https://arxiv.org/abs/2404.09241) 发现人类创建的 mutant 中少于 10% 等价，但开发者判断等价性仍不可靠；这恰恰说明“比例不高”不能替代逐个语义非等价证明。

### 7.3 最新代码/agent benchmark 工作

| 工作 | 方法 | 强结果 | 证据边界 |
|---|---|---|---|
| [EvalPlus](https://arxiv.org/abs/2305.01210) | 大规模增强测试 | HumanEval+ 约 80 倍测试，发现原 suite 漏检 | 增强测试质量仍需验证 |
| [STING](https://arxiv.org/abs/2604.01518) | surviving variants 引导新测试 | 77% SWE-bench Verified 实例有 survivor；211 实例生成 1,014 测试 | 依赖变异语义和新测试有效性 |
| [SWE-Mutation](https://arxiv.org/abs/2605.22175) | 2,636 个 agentic mutant | 暴露 LLM 生成 test suite 判别力不足 | benchmark 测的是测试生成能力 |
| [PAIChecker](https://arxiv.org/abs/2607.28587) | 多 agent 检查 issue—PR 对齐 | 揭示 SWE-bench-like 配对问题 | 主要是自动审查/人工验证，不是统一 proof contract |
| [PyCraft](https://arxiv.org/abs/2402.07138) | LLM 生成代码变换与测试 | 展示生成多样性，也显示高错误率需过滤 | LLM 生成不等于语义正确 |

### 7.4 对 BenchAudit 最关键的技术抽象：差分证明合同

若有弱 oracle \(W\) 和强 oracle \(S\)，以及 canonical \(c\) 与候选 \(m\)，可以定义：

```text
canonical 通过 W 和 S
candidate 通过 W
candidate 失败于 S
W、S、driver、输入、代码、环境全部哈希绑定
```

这能确认“W 相对 S 存在 coverage gap”。但若 \(S\) 是研究者自己构造的前缀扩展，结论必须写成“相对于该构造强 oracle”；若 \(S\) 是官方完整测试或自然存在的 plus suite，主张才更强。

进一步确认“官方测试接受语义错误 mutant”，还需合法区分输入与参考行为共识。这个缺口——**domain-valid distinguishing input certificate**——是现有 mutation-guided benchmark 审计中仍很薄弱、但很有研究价值的一点。

---

## 8. 研究路线五：测量效度、可靠性与选择性评测

### 8.1 分数不是能力本身

[ECBD](https://aclanthology.org/2024.acl-long.861/) 将教育测量中的 evidence-centered design 引入 NLP benchmark，把能力主张、任务、证据和评分拆成模块；[MetricEval](https://aclanthology.org/2023.emnlp-main.676/) 用测量理论分析 NLG 指标的可靠性和效度；2025 年系统综述 [Measuring What Matters](https://arxiv.org/abs/2511.04703) 由 29 位专家审查 445 个 LLM benchmark，发现构念、任务和评分之间存在系统性效度问题。

同一构念的不同 benchmark 也未必给出相同排序。[The Validity of Evaluation Results](https://aclanthology.org/2023.conll-1.19/) 在 compositional generalization 上发现数据来源比声称的构念定义更能预测模型排名一致性；[The Benchmarking Epistemology](https://arxiv.org/abs/2510.23191) 则明确区分“对这个数据集的性能”与“对理论能力的科学推断”。

### 8.2 可靠性、效度和后果效度

- **reliability**：重复测量是否稳定；
- **construct validity**：评分是否测到了声称能力；
- **criterion validity**：与外部可信标准是否一致；
- **consequential validity**：依据该分数做出的模型选择是否会改变。

BenchAudit 的 replay-confirmed finding 主要加强评分器/任务的局部可靠性与内容效度；修复后重排名则进入 consequential validity。

### 8.3 Selective prediction 是自然的系统接口

对于无法统一机械证明的 item，正确目标不是强迫二分类，而是三动作：

```text
confirm / accept
review / acquire more evidence
abstain / not identifiable
```

[Trust or Escalate](https://arxiv.org/abs/2407.18370) 说明 judge 可以在覆盖率与人工一致性之间作带保证选择；conformal prediction 为集合式结论提供统计覆盖保证。但这些统计保证仍依赖校准分布，不能替代 proof contract。最佳组合是：

- 统计不确定性决定是否升级；
- 机械 proof 决定能否 confirmed；
- 无法验证时 fail closed，而不是让置信度越过证据天花板。

---

## 9. 研究路线六：文档、溯源、可复现与证据供应链

### 9.1 已有工作解决的是“从哪里来”

- [Datasheets for Datasets](https://arxiv.org/abs/1803.09010)：记录动机、组成、收集过程和推荐用途；
- [Data Statements](https://aclanthology.org/Q18-1041/)：明确语言数据适用人群和泛化边界；
- [Model Cards](https://dl.acm.org/doi/10.1145/3287560.3287596)：报告模型用途、指标和限制；
- [Data Cards](https://arxiv.org/abs/2204.01075)：面向不同 stakeholder 记录数据生命周期；
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)：用 Entity、Activity、Agent 及其关系表达可交换 provenance；
- [in-toto](https://in-toto.io/docs/what-is-in-toto/)：记录供应链步骤、执行者、材料和产物，并验证流程完整性；
- [SLSA Provenance](https://slsa.dev/spec/v1.0/provenance)：规定构建产物来源与不可伪造 provenance 的安全等级。

### 9.2 Benchmark 审计还缺“这份证据允许证明什么”

通用 provenance 标准能说明：

- 文件来自哪个 commit；
- 谁在什么环境运行了哪个步骤；
- 输出是否被篡改；
- 数据如何由上游产物生成。

但它们通常不直接回答：

- 这是规范性材料、元数据，还是已知缺陷结论？
- 它是在 benchmark cutoff 前还是 cutoff 后产生？
- 它可以参与 routing、detection、validation，还是 confirmation？
- 一个 post-cutoff erratum 是否污染了“独立发现”？

因此一个新的研究空白是 **semantic admissibility provenance**：不仅绑定来源和哈希，还由中央策略重新推导证据允许用途，生产者不能自填权限。它可借鉴 W3C PROV/in-toto 的完整性模型，但服务于 benchmark audit 的证据等级与时间切分。

### 9.3 推荐的证据 receipt 最小字段

```yaml
source_identity:
  official_remote: ...
  source_commit_or_release: ...
  path_or_blob: ...
  content_sha256: ...
benchmark_cutoff:
  immutable_ref: ...
relation_proof:
  host_specific_ancestry_or_release_relation: ...
source_role:
  normative | metadata | correction | execution_environment
role_binding:
  trusted_manifest_sha256: ...
allowed_uses:
  derived_by_policy_version: ...
```

关键不是 schema 漂亮，而是：关系必须在 pinned source 上重放、role 必须由受信 manifest 绑定、unknown host 必须弃权、allowed uses 必须由中央策略重算。

---

## 10. 研究路线七：修复、回归与排名影响

### 10.1 现有修复工作通常怎么做

1. 标记或删除坏题；
2. 重标 gold；
3. 修改 task/rubric；
4. 增强测试；
5. 重新运行模型并比较分数/排名。

代表性证据包括：

- MMLU-Redux：人工重标后模型 performance/rank 发生变化；
- [MMLU-CF](https://aclanthology.org/2025.acl-long.656/)：新 contamination-free 测试使多模型得分下降且排序显著改变；
- STING：增强测试使 top-10 repair agent resolved rate 降低 4.2–9.0%；
- ELT-Bench-Verified：修正 evaluator 和 ground truth 后，agent 结果显著改善；
- [BenchMarker](https://aclanthology.org/2026.acl-long.719/)：修复目标缺陷可能同时引入新的 distractor/多正确答案问题，说明 repair 也需要审计；
- [Garbage In, Reasoning Out?](https://aclanthology.org/2026.findings-eacl.89/)：审计 social reasoning benchmark 后，表面分数并不能稳定反映推理能力。

### 10.2 修复闭环的最低要求

```text
confirmed finding
  → responsibility localization
  → minimal repair candidate
  → same proof replay becomes clean
  → unrelated invariants remain unchanged
  → full regression has no new finding
  → model outputs are rescored
  → rank/effect-size change is reported with uncertainty
```

“删除问题让 finding 消失”不算修复，除非删除本身有明确治理政策；“分数提高”也不等于修复正确，因为可能放宽 evaluator。修复必须由原 proof 的反事实对照约束。

### 10.3 排名影响指标

建议至少报告：

- score delta 与置信区间；
- Kendall \(\tau\)、Spearman \(\rho\)；
- top-k membership change；
- winner change / per-domain winner change；
- pairwise rank flip count；
- worst-task 和 worst-defect-family risk；
- 修复题目数占比与排名位移的杠杆率。

---

## 11. 2018–2026 技术演进时间线

| 阶段 | 代表工作 | 主要变化 |
|---|---|---|
| 2018–2020 文档化与数据诊断 | Datasheets、Data Statements、Data Shapley、TracIn、Dataset Cartography | 数据来源、价值和噪声成为独立研究对象 |
| 2021–2022 benchmark 脆弱性 | Pervasive Label Errors、Benchmark Lottery、Dynabench、Data Cards | 错标会改变排序；静态 benchmark 会饱和和过拟合 |
| 2023 LLM judge 与增强测试 | G-Eval、MT-Bench、Prometheus、EvalPlus、MetricEval | LLM 开始承担评测，judge 与 test suite 自身需元评测 |
| 2024 污染与 judge 对抗 | LLMBar、JudgeBench、CLEAN-EVAL、PaCoST、MMLU-Redux、ECBD | 从总体相关性转向对抗样本、污染和构念效度 |
| 2025 系统综述与细粒度元评测 | Progress Illusion、GroUSE、MMLU-CF、污染检测假设审查、Fantastic Bugs | 更关注相近模型、unit test、候选发现与清洗后排名 |
| 2026 agent benchmark 与证据关系 | TrustJudge、BiasScope、RULERS、STING、SWE-Mutation、IRT Audit、ABA、PAIChecker、MM-JudgeBias | 审计对象扩展为完整执行协议；受控扰动、变异、证据锚定和逐实例可靠性成为主流 |

总体趋势可以概括为：

```text
静态准确率
→ 数据质量
→ evaluator reliability
→ protocol-level audit
→ replayable evidence
→ repair and consequences
```

但最后两步仍明显落后于前三步。

---

## 12. 现有方法横向比较

| 方法族 | 可扩展性 | 语义覆盖 | 确定性 | 可到 confirmed？ | 主要风险 |
|---|---:|---:|---:|---:|---|
| 静态规则/manifest replay | 高 | 低—中 | 高 | 可，若契约明确 | schema 适配、漏报 |
| 多模型响应统计 | 高 | 中 | 中 | 通常不可 | 共同偏差、污染、模型池依赖 |
| 单/多 LLM 审计 | 高 | 高 | 低—中 | 不应单独确认 | prompt/model 漂移、幻觉 |
| IRT/心理测量 | 高 | 中 | 中 | 通常需人工 | 假设失配、样本模型分布 |
| 人工/专家复核 | 低 | 高 | 中 | 可作为人工金标 | 成本、分歧、不可自动重放 |
| metamorphic relation | 中—高 | 取决于 MR | 中—高 | 关系可证时可 | 变换不保语义 |
| mutation testing | 中 | 高（代码） | 高 | 需非等价证明 | equivalent mutant |
| 差分执行 proof | 中 | 中 | 高 | 可 | 环境、domain-valid input |
| provenance/attestation | 高 | 不判断语义 | 高 | 只提供前提 | 来源可信不等于结论正确 |
| selective evaluation | 高 | 高 | 统计性 | 不能替代 proof | 校准分布漂移 |

不存在一个方法同时具备高语义覆盖、高确定性、低成本和跨 benchmark 零适配。合理系统必须分层组合，而不是寻找万能 checker。

---

## 13. 2026 年前沿技术趋势

### 趋势 1：从“judge 与人相关”转向“judge 在什么条件下可靠”

相近系统区分、跨 rubric 稳定性、位置/风格/家族偏差、run-to-run 方差、传递性和逐实例风险正在替代单一 Spearman 相关性。[The Progress Illusion](https://aclanthology.org/2025.findings-emnlp.1036/)、TrustJudge、Policy Invariance、MM-JudgeBias 和 conformal judge diagnosis 都属于这一转向。

### 趋势 2：从预定义偏差到自动发现未知偏差

BiasScope、BITE 和 automated concept discovery 试图让系统自动寻找 judge 的脆弱方向，而不是只测 position/verbosity。但自动发现的 bias 仍需语义保持验证，否则很容易把质量真实变化误判为 bias。

### 趋势 3：rubric 编译与 evidence anchoring

RULERS、PReMISE、ATOM 等工作不再把 rubric 当纯 prompt，而把它拆成原子标准、证据位置和结构化评分。这与 benchmark task-contract audit 合流：未来 evaluator 更像编译器和执行器，而不是自由文本裁判。

### 趋势 4：测试套件本身成为 benchmark 的被测对象

EvalPlus、STING、SWE-Mutation 和 PAIChecker 说明 agent/coding benchmark 的瓶颈不是只有模型能力，也包括 test adequacy 与 issue-oracle alignment。

### 趋势 5：从静态 benchmark 转向生命周期治理

LiveBench、Dynabench、MMLU-CF、C2LEVA 通过时间更新、隐藏测试或模型在环降低污染；MMLU-Redux、ELT-Bench-Verified 则说明 benchmark 需要正式的修订、版本和重新计分流程。

### 趋势 6：从确定标签转向集合结论与主动弃权

conformal set、selective evaluation、NOT_IDENTIFIABLE 结局共同承认：证据不足时最可信的自动化不是猜对，而是停止。

### 趋势 7：审计证据逐渐接近软件供应链

数据集 revision、代码 commit、镜像 digest、driver hash、raw output 与 stable summary 被绑定到同一证据链。研究空白不再只是 provenance 记录，而是 provenance 的语义使用权限。

---

## 14. 关键研究空白

### G1. 候选发现与机器确认之间没有通用桥梁

现状：LLM/IRT 能找到候选，人工能确认；跨 benchmark 的自动 proof contract 很少。
机会：定义可注册的 proof family、evidence schema、promotion ceiling 与 replay API。
可证伪目标：在没有 item-level 手写 verifier 的新 benchmark 上产生至少一条 replay-confirmed 缺陷。

### G2. 元形关系缺少“关系本身”的证书

现状：大量工作用 paraphrase、格式编辑或图像扰动，但变换是否保语义常靠人工或另一个 LLM。
机会：将 MR 分为 deterministic、certificate-backed、LLM-proposed 三层；只有前两层可升 confirmed。
指标：invalid transformation rate、relation coverage、confirmed yield、abstention rate。

### G3. Equivalent mutant 与合法区分输入没有被系统解决

现状：surviving mutant 被广泛用作弱测试证据，但语义非等价通常要人工判断。
机会：生成带任务域合法性证书的 distinguishing input，并用多个声明参考实现或形式规范重放。
难点：输入语法只是结构合法，不能保证所有语义前置条件。

### G4. 外部证据 provenance 没有“用途控制”

现状：Datasheet/W3C PROV/in-toto 证明来源和完整性，却不判断 post-cutoff errata 能否参与独立发现。
机会：role-aware、cutoff-aware、policy-derived allowed-use receipt。
攻击面：调用方伪造 role/allowed use、本地 fork 伪造 ancestry、正确 commit 配错误 blob。

### G5. 自动适配成本没有被当作研究指标

现状：每篇论文在少数 benchmark 上写 adapter，却很少报告接入新协议需要多少人工决策和代码。
机会：跨函数调用、stdin/stdout、文件产物、SQL、notebook、shell 协议测量 first-of-family 与 second-of-family 成本。
指标：人工活跃时间、必须人工步骤、adapter LOC、通用核心复用率、NOT_IDENTIFIABLE 原因。

### G6. 修复闭环远少于缺陷发现

现状：许多论文修订数据集，但很少由原 finding 自动约束最小修复，并证明无回归。
机会：proof-guided repair；修复前 proof 命中，修复后 clean，其他 invariants 不变。
指标：repair success、regression escape、new-finding rate、人工编辑量。

### G7. 排名后果通常只报平均值

现状：MMLU-Redux、STING 等证明排名/成功率会变，但一般缺 worst-slice、uncertainty 和 leverage 分析。
机会：把 item-level defect posterior/confirmation 传播到 set-valued leaderboard。
指标：rank interval、winner stability、per-domain flips、修复一题带来的最大位移。

### G8. Judge 关系违例与 verdict 错误预测尚未真正统一

现状：反事实工作报告 flip rate，selective work报告风险，但“哪次 verdict 错”仍需要标签。
机会：用多种 hold-out relation violation、margin、方差和证据缺失训练可靠性估计器，并在 judge-family holdout 上评估。
边界：它输出错误概率和 defer 决策，不能单独输出 confirmed benchmark defect。

### G9. 多 judge 系统缺少误差依赖建模

现状：投票常假设独立，Preference Leakage 和 multi-agent bias 说明同家族 judge 错误高度相关。
机会：按 provider、训练谱系、generator relatedness 建模相关错误；报告有效独立 judge 数而非名义模型数。

### G10. Benchmark repair 可能引入新缺陷

现状：BenchMarker 发现一些 targeted repair 会带来不自然 distractor 或多正确答案。
机会：修复后必须重新运行全 taxonomy audit，而非只验证原缺陷消失。

### G11. 动态 benchmark 的版本可比性不足

现状：持续更新能减污染，却使不同日期的分数不再直接可比。
机会：anchor items、equating、IRT linking、版本间桥接样本与 score provenance。
风险：IRT linking 本身受模型池和分布假设限制。

### G12. 构念效度与 item-level proof 仍然脱节

现状：ECBD/测量理论讨论“是否测到能力”，proof contract 讨论“某题是否被正确评分”。
机会：把 item proof 映射到构念证据图，量化某类缺陷对特定 capability claim 的影响，而不是只修总分。

---

## 15. 最值得做的研究方向排序

### 第一推荐：跨协议可重放确认合同

**问题**：能否在新 benchmark 上不写 item-level verifier，只声明协议角色，就自动确认至少一条缺陷？

**方法**：

1. 建立 proof registry：inventory replay、differential oracle、mutation survivor + non-equivalence、rubric literal grounding、external evidence provenance；
2. LLM 只抽取角色、关系和候选；
3. 本地 verifier 重算证据；
4. promotion 根据 proof type 和 attestation 决定 review/confirmed；
5. benchmark-family holdout 测迁移。

**创新性**：从“自动发现”推进到“自动确认”，与 Fantastic Bugs、ABA、PAIChecker 的人工/agent review 形成清晰差异；与 STING 的 test augmentation 相邻，但主张是统一证据合同与跨协议迁移。

### 第二推荐：Proof-guided benchmark repair

**问题**：能否由 confirmed proof 生成最小修复，并用同一 proof 自动验证修复和回归？

**方法**：从文件名碰撞、manifest mismatch、错误 gold、test underconstraint 中选 2–3 类；模板化产生 repair；运行原 proof + 全 taxonomy 回归；重新计分。

**创新性**：补齐现有工作最弱的 repair lifecycle；结果可以直接回答“系统修好了什么”。

### 第三推荐：关系监督的 judge 选择性评测

**问题**：关系违例能否预测逐次 judge verdict 错误，并在预算下优于 margin、self-consistency 和多 judge disagreement？

**方法**：确定性 invariance + controlled degradation + locality probes；训练 risk estimator；按 accept/probe/defer 决策；task/judge/transform 三重 holdout。

**注意**：这是 evaluator reliability 论文，不应混成 benchmark confirmed 主线。其输出是风险估计与选择性覆盖。

### 第四推荐：合法区分输入证书

**问题**：对官方测试中存活的 mutant，能否自动构造域内合法输入证明其与声明参考行为不同？

**方法**：受限 grammar、全题面语义约束排除、symbolic/concolic 生成、多个 AST-distinct reference 共识、容器重放。

**风险**：领域模型覆盖率可能很低；必须先做非目标数据 preflight，未过门槛即停止。

### 第五推荐：证据用途的可验证 provenance

**问题**：如何让 benchmark README、issue、errata、版本、PR 元数据既能辅助审计，又不污染独立发现？

**方法**：immutable cutoff、host-specific ancestry、blob hash、normative/metadata/correction role、policy-derived allowed uses。

**定位**：更偏基础设施/系统安全贡献，适合作为 confirmed 主线的关键可信基座，而非单独以 accuracy 竞争。

### 15.1 “反事实 Judge 审计”与“BenchAudit”应不应该合成一篇

不建议在主论文里把两者写成同一个目标。它们共享关系测试思想，但 target claim 不同：

| 轴 | 反事实 Judge 审计 | BenchAudit 确认合同 |
|---|---|---|
| 被测对象 | LLM evaluator 的单次 verdict | benchmark item/evaluator/protocol |
| 主要输出 | verdict error risk、accept/defer | review/confirmed/repair |
| 监督 | 人工 verdict 标签 + 关系违例 | proof contract + replay evidence |
| 核心指标 | risk-coverage、AUROC、selective accuracy | confirmed yield、escape、repair/regression |
| 关键边界 | 关系违例不自动说明哪次 verdict 错 | proof 覆盖低时必须弃权 |
| 最近竞争 | Policy Invariance、TrustJudge、BiasScope、MM-JudgeBias | ABA、Fantastic Bugs、STING、PAIChecker |

更合理的关系是：反事实 judge estimator 作为 BenchAudit 的候选 prioritizer 或 review-cost reducer，但它没有权限越过 confirmation ceiling。这样可以共享 transformation library、evidence receipt 和预算选择器，却不混淆论文主张。

如果投 ICLR、且实验资源集中在 judge 数据上，可单独做“关系监督的选择性 evaluator”；如果已有多协议 replay、confirmed 和 repair 资产，则更有差异化的主线是“可重放 benchmark audit”。以当前文献拥挤度看，后者竞争者更少，但工程和证明责任更重。

---

## 16. 推荐的整体系统架构

```text
                 ┌────────────────────────────┐
                 │ Frozen benchmark snapshot │
                 └──────────────┬─────────────┘
                                │
       ┌────────────────────────┼─────────────────────────┐
       │                        │                         │
 static contract         LLM semantic extraction   behavior/statistics
 inventory/schema        task/rubric roles         response patterns/IRT
       │                        │                         │
       └────────────────────────┴──────────────┬──────────┘
                                               ▼
                                      Review candidate pool
                                               │
                                    proof-family applicability
                                               │
                         ┌─────────────────────┴─────────────────────┐
                         │                                           │
                  replayable proof                            not identifiable
                         │                                           │
                  central promotion                              review/defer
                         │
                    confirmed defect
                         │
                  proof-guided repair
                         │
              regression + leaderboard impact
```

### 16.1 LLM 应该放在哪里

适合 LLM：

- 从 task/rubric 中抽取显式约束；
- 生成候选关系、mutant、repair suggestion；
- 解释复杂语义并帮助排序人工审查；
- 识别 protocol family 的初始候选。

不应由 LLM 单独完成：

- 判断哈希、文件是否存在、测试是否通过；
- 决定某 receipt 是否在 cutoff 前；
- 把自己的高置信度提升为 confirmed；
- 证明 LLM 自己生成的 paraphrase 保语义；
- 证明 mutant 非等价或 repair 无回归。

### 16.2 静态规则与 LLM 的正确分工

纯静态规则无法理解“请把 1.txt 到 100.txt 总结为 123.txt”中的输出角色；LLM 可抽取 `123.txt` 是显式要求的输出文件名。但最终是否缺少 `123.txt`，应由本地 manifest replay 决定。也就是：

```text
LLM：语义抽取声明
程序：验证声明、比对 inventory、发射 review evidence
proof：若存在确定性契约，再决定是否可 confirmed
```

这比“LLM 直接判断 benchmark 有错”更容易复核，也比纯 regex 有更高语义覆盖。

---

## 17. 实验设计蓝图

### 17.1 数据分层

至少覆盖三类协议：

1. 静态 QA/MCQ：SVAMP、MMLU-Redux；
2. artifact/workspace：文件、spreadsheet、rubric、manifest；
3. executable/code/agent：HumanEval+/MBPP+、APPS、SWE-bench-like。

划分必须按 task 或 benchmark family 隔离，不能按 candidate 行随机切分。建议：

- development benchmarks：允许设计规则；
- transformation holdout：新关系类型；
- benchmark-family holdout：新协议同族；
- protocol-family holdout：完全不同执行协议；
- temporal holdout：cutoff 后新版本，只用于最终验证。

### 17.2 三层指标

#### 候选发现层

- candidate recall / reviewed precision / F1；
- candidate rate；
- logical calls、tokens、人民币成本；
- incremental calls / incremental reviewed TP；
- family-conditioned recall。

#### 确认层

- replay-confirmed count；
- confirmed precision（对独立复核子集）；
- proof coverage；
- NOT_IDENTIFIABLE rate；
- adversarial ceiling escape；
- invalid proof / unattested proof escape；
- deterministic replay equality。

#### 修复与后果层

- repair success rate；
- original proof clean rate；
- regression/new-finding rate；
- score delta、rank flips、Kendall \(\tau\)；
- 每个 confirmed root cause 的人工时间和计算成本。

### 17.3 必须有的基线

- rules-only；
- naive single-pass LLM；
- LLM + taxonomy；
- multi-judge vote；
- response-pattern/IRT prioritization；
- static + decomposed LLM extraction；
- proposed system without proof promotion；
- full proof-contract system；
- human/expert review upper reference。

### 17.4 关键消融

- 去掉 provenance gate；
- 去掉 semantic extraction，只留静态；
- 去掉 deterministic short-circuit；
- 不同 proof family 单独贡献；
- benchmark-specific vs datatype-specific adapter；
- LLM family holdout；
- relation/transform holdout；
- 不同 evidence ceiling；
- 不报告弃权、强制二分类的代价。

### 17.5 生死门槛

建议预注册：

1. 合法 benchmark control 上 confirmed false positive 必须为 0；
2. 至少一个新 benchmark、无 item-level verifier，产出 ≥1 confirmed；
3. confirmation 必须可 fresh clone 重放；
4. 所有 LLM-only finding 保持 review-only；
5. 修复至少让一条 confirmed finding 变 clean，且无新 finding；
6. 若 proof coverage 低于预注册阈值，结论写 NOT_IDENTIFIABLE，不事后放宽语法。

---

## 18. 论文叙事与可守住的主张

### 18.1 最强但可守住的主张

> 我们把 benchmark auditing 从“模型认为样本可疑”的候选排序问题，扩展为一个分层的证据系统：LLM 与统计方法负责发现，协议相关但 item-agnostic 的 proof contract 负责本地重放确认，中央 promotion 负责 fail-closed 证据天花板，修复阶段用同一证明执行回归。该系统在未为单个 item 手写 verifier 的新 benchmark 上确认缺陷，并量化修复对最终评测的影响。

### 18.2 不应声称

- “自动发现的所有问题都是真的”；
- “多模型一致即可 confirmed”；
- “surviving mutant 一定是错误程序”；
- “反事实 flip 说明原 verdict 错”；
- “高 precision 等于高 recall”；
- “某 benchmark 有错误，所以整个 leaderboard 无效”；
- “一个 adapter 成功就实现任意 benchmark 自动适配”。

### 18.3 与最近工作的差异一句话版

- 相比 Fantastic Bugs / IRT Audit / ABA：它们擅长候选发现或专家验证，我们强调机器可重放确认和修复回归；
- 相比 PAIChecker：它聚焦 issue—PR alignment 的 LLM/agent checking，我们要求 confirmation 不依赖 LLM 共识；
- 相比 STING / SWE-Mutation：它们用 mutant 诊断/增强测试，我们进一步要求非等价或关系合法性证书以及中央 proof promotion；
- 相比 RULERS / judge invariance：它们提高或审计 evaluator，我们审计完整 benchmark 证据链并区分 review 与 confirmed；
- 相比 Datasheets/W3C PROV/in-toto：它们记录来源和完整性，我们增加证据语义角色、cutoff 与 allowed-use 策略。

---

## 19. 推荐阅读路线

### 第一阶段：建立 benchmark 不是“真理”的认识

1. [The Benchmark Lottery](https://arxiv.org/abs/2107.07002)
2. [Pervasive Label Errors](https://arxiv.org/abs/2103.14749)
3. [Are We Done with MMLU?](https://aclanthology.org/2025.naacl-long.262/)
4. [ECBD](https://aclanthology.org/2024.acl-long.861/)
5. [Measuring What Matters](https://arxiv.org/abs/2511.04703)

### 第二阶段：理解自动候选发现

6. [Platinum Benchmarks](https://openreview.net/pdf?id=XSeN6xZtZ9)
7. [Fantastic Bugs](https://arxiv.org/abs/2511.16842)
8. [IRT Audit](https://arxiv.org/abs/2605.30504)
9. [Can We Trust IRT?](https://arxiv.org/abs/2607.15190)
10. [ABA](https://arxiv.org/abs/2605.26079)

### 第三阶段：理解 evaluator 元评测

11. [Judging LLM-as-a-Judge](https://arxiv.org/abs/2306.05685)
12. [JudgeBench](https://arxiv.org/abs/2410.12784)
13. [The Progress Illusion](https://aclanthology.org/2025.findings-emnlp.1036/)
14. [TrustJudge](https://iclr.cc/virtual/2026/poster/10011516)
15. [Policy Invariance](https://arxiv.org/abs/2605.06161)
16. [RULERS](https://arxiv.org/abs/2601.08654)

### 第四阶段：理解可重放确认

17. [Metamorphic Testing Review](https://nottingham-repository.worktribe.com/output/925152/metamorphic-testing-a-review-of-challenges-and-opportunities)
18. [EvalPlus](https://arxiv.org/abs/2305.01210)
19. [STING](https://arxiv.org/abs/2604.01518)
20. [SWE-Mutation](https://arxiv.org/abs/2605.22175)
21. [Equivalent Mutants](https://arxiv.org/abs/2404.09241)
22. [PAIChecker](https://arxiv.org/abs/2607.28587)

### 第五阶段：理解证据生命周期

23. [Datasheets](https://arxiv.org/abs/1803.09010)
24. [W3C PROV-O](https://www.w3.org/TR/prov-o/)
25. [in-toto](https://in-toto.io/docs/what-is-in-toto/)
26. [Dynabench](https://aclanthology.org/2021.naacl-main.324/)
27. [LiveBench](https://arxiv.org/abs/2406.19314)
28. [BenchMarker](https://aclanthology.org/2026.acl-long.719/)

---

## 20. 扩展文献索引

### A. Benchmark 缺陷、重标与自动审计

1. Northcutt et al. [Pervasive Label Errors in Test Sets Destabilize Machine Learning Benchmarks](https://arxiv.org/abs/2103.14749), 2021.
2. Gema et al. [Are We Done with MMLU? / MMLU-Redux](https://aclanthology.org/2025.naacl-long.262/), NAACL 2025.
3. MadryLab. [Do Large Language Model Benchmarks Test Reliability? / Platinum Benchmarks](https://openreview.net/pdf?id=XSeN6xZtZ9), 2024.
4. Nahum et al. [Are LLMs Better than Reported? Detecting Label Errors](https://arxiv.org/abs/2410.18889), 2024.
5. Zhou et al. [Fantastic Bugs and Where to Find Them in AI Benchmarks](https://arxiv.org/abs/2511.16842), 2025 preprint.
6. Land & Bikel. [Auditing LLM Benchmarks with Item Response Theory](https://arxiv.org/abs/2605.30504), 2026 preprint.
7. Wang et al. [Automated Benchmark Auditing for AI Agents and LLMs](https://arxiv.org/abs/2605.26079), 2026 preprint.
8. Wang et al. [PAIChecker](https://arxiv.org/abs/2607.28587), 2026 preprint.
9. Zanoli et al. [ELT-Bench-Verified](https://arxiv.org/abs/2603.29399), 2026 preprint.
10. Balepur et al. [BenchMarker](https://aclanthology.org/2026.acl-long.719/), ACL 2026.
11. Mousavi et al. [Garbage In, Reasoning Out?](https://aclanthology.org/2026.findings-eacl.89/), Findings EACL 2026.

### B. 数据质量、模型行为与测量

12. Ghorbani & Zou. [Data Shapley](https://arxiv.org/abs/1904.02868), ICML 2019.
13. Jia et al. [Efficient Task-Specific Data Valuation](https://arxiv.org/abs/1902.10275), AISTATS 2019.
14. Pruthi et al. [TracIn](https://arxiv.org/abs/2002.08484), NeurIPS 2020.
15. Swayamdipta et al. [Dataset Cartography](https://arxiv.org/abs/2009.10795), EMNLP 2020.
16. Dehghani et al. [The Benchmark Lottery](https://arxiv.org/abs/2107.07002), 2021.
17. Sun et al. [The Validity of Evaluation Results](https://aclanthology.org/2023.conll-1.19/), CoNLL 2023.
18. Liu et al. [ECBD](https://aclanthology.org/2024.acl-long.861/), ACL 2024.
19. Xiao et al. [MetricEval](https://aclanthology.org/2023.emnlp-main.676/), EMNLP 2023.
20. Bean et al. [Measuring What Matters](https://arxiv.org/abs/2511.04703), 2025 preprint.
21. Freiesleben & Zezulka. [The Benchmarking Epistemology](https://arxiv.org/abs/2510.23191), 2025 preprint.
22. Kearns. [Quantifying Construct Validity in LLM Evaluations](https://arxiv.org/abs/2602.15532), 2026.
23. Dwork et al. [Generalization in Adaptive Data Analysis and Holdout Reuse](https://arxiv.org/abs/1506.02629), NeurIPS 2015.

### C. 污染与动态评测

24. Sainz et al. [Benchmark Data Contamination of LLMs: A Survey](https://arxiv.org/abs/2406.04244), 2024.
25. Deng et al. [Investigating Data Contamination in Modern Benchmarks](https://aclanthology.org/2024.naacl-long.482/), NAACL 2024.
26. Zhang et al. [PaCoST](https://aclanthology.org/2024.findings-emnlp.97/), Findings EMNLP 2024.
27. Xu et al. [Benchmarking Benchmark Leakage](https://arxiv.org/abs/2404.18824), 2024.
28. Fu et al. [Does Data Contamination Detection Work?](https://aclanthology.org/2025.findings-naacl.291/), Findings NAACL 2025.
29. Samuel et al. [Limitations, Inconsistencies, and Oracle Challenges](https://aclanthology.org/2025.coling-main.338/), COLING 2025.
30. Zhu et al. [CLEAN-EVAL](https://arxiv.org/abs/2311.09154), 2023.
31. White et al. [LiveBench](https://arxiv.org/abs/2406.19314), 2024.
32. Zhao et al. [MMLU-CF](https://aclanthology.org/2025.acl-long.656/), ACL 2025.
33. Li et al. [C2LEVA](https://aclanthology.org/2025.findings-acl.116/), Findings ACL 2025.
34. Kiela et al. [Dynabench](https://aclanthology.org/2021.naacl-main.324/), NAACL 2021.
35. Magnusson et al. [PALOMA](https://arxiv.org/abs/2312.10523), 2023.
36. Chen et al. [Static to Dynamic Evaluation Survey](https://aclanthology.org/2025.emnlp-main.511/), EMNLP 2025.

### D. LLM-as-a-Judge 与 rubric 元评测

37. Zheng et al. [Judging LLM-as-a-Judge / MT-Bench](https://arxiv.org/abs/2306.05685), NeurIPS D&B 2023.
38. Liu et al. [G-Eval](https://arxiv.org/abs/2303.16634), EMNLP 2023.
39. Kim et al. [Prometheus](https://arxiv.org/abs/2310.08491), 2023.
40. Zeng et al. [LLMBar](https://arxiv.org/abs/2310.07641), ICLR 2024.
41. Tan et al. [JudgeBench](https://arxiv.org/abs/2410.12784), 2024.
42. Shi et al. [Judging the Judges: Position Bias](https://aclanthology.org/2025.ijcnlp-long.18/), IJCNLP-AACL 2025.
43. Xu et al. [The Progress Illusion](https://aclanthology.org/2025.findings-emnlp.1036/), Findings EMNLP 2025.
44. Muller et al. [GroUSE](https://aclanthology.org/2025.coling-main.304/), COLING 2025.
45. TrustJudge. [Inconsistencies of LLM-as-a-Judge](https://iclr.cc/virtual/2026/poster/10011516), ICLR 2026.
46. Lai et al. [BiasScope](https://openreview.net/pdf?id=QGOw6AU8Lp), ICLR 2026.
47. Li et al. [Preference Leakage](https://openreview.net/pdf?id=grIvSXVJ65), ICLR 2026.
48. Lee et al. [MM-JudgeBias](https://aclanthology.org/2026.acl-long.1162/), ACL 2026.
49. Weng et al. [Policy Invariance](https://arxiv.org/abs/2605.06161), 2026 preprint.
50. Yang et al. [BITE](https://openreview.net/forum?id=7g23tYAIDC), ICML 2026.
51. Hong et al. [RULERS](https://arxiv.org/abs/2601.08654), 2026 preprint.
52. [What Makes the Whole? Attribute Compositionality](https://openreview.net/forum?id=xd9qriSZQh), 2026.
53. Jung et al. [Trust or Escalate](https://arxiv.org/abs/2407.18370), 2024.
54. [Diagnosing LLM Judge Reliability](https://openreview.net/forum?id=FbDuesI6tD), ICML workshop 2026.
55. Hong et al. [PReMISE](https://arxiv.org/abs/2605.30803), 2026 preprint.
56. [Can LLMs Write Reliable Rubrics?](https://arxiv.org/abs/2607.12835), 2026 preprint.
57. Xu et al. [ATOM: Beyond Ranking](https://aclanthology.org/2026.acl-long.932/), ACL 2026.

### E. 元形、变异与测试充分性

58. Chen et al. [Metamorphic Testing: A Review](https://nottingham-repository.worktribe.com/output/925152/metamorphic-testing-a-review-of-challenges-and-opportunities), ACM CSUR 2018.
59. Pei et al. [DeepXplore](https://arxiv.org/abs/1705.06640), SOSP 2017.
60. Tian et al. [DeepTest](https://arxiv.org/abs/1708.08559), ICSE 2018.
61. Liu et al. [LGMT](https://arxiv.org/abs/2605.23965), 2026 preprint.
62. [Bidirectional Empowerment of Metamorphic Testing and LLMs](https://arxiv.org/abs/2605.13898), 2026 survey.
63. Liu et al. [EvalPlus](https://arxiv.org/abs/2305.01210), NeurIPS 2023.
64. Li et al. [STING](https://arxiv.org/abs/2604.01518), 2026 preprint.
65. Sun et al. [SWE-Mutation](https://arxiv.org/abs/2605.22175), 2026 preprint.
66. Straubinger et al. [Equivalent Mutants](https://arxiv.org/abs/2404.09241), 2024.
67. Gulwani et al. [PyCraft](https://arxiv.org/abs/2402.07138), FSE 2024.

### F. 文档、provenance 与可复现

68. Gebru et al. [Datasheets for Datasets](https://arxiv.org/abs/1803.09010), CACM 2021 / preprint 2018.
69. Bender & Friedman. [Data Statements](https://aclanthology.org/Q18-1041/), TACL 2018.
70. Mitchell et al. [Model Cards for Model Reporting](https://dl.acm.org/doi/10.1145/3287560.3287596), FAT* 2019.
71. Pushkarna et al. [Data Cards](https://arxiv.org/abs/2204.01075), FAccT 2022.
72. W3C. [PROV-O](https://www.w3.org/TR/prov-o/), Recommendation 2013.
73. Torres-Arias et al. [in-toto: Providing Farm-to-Table Guarantees for Bits and Bytes](https://ssl.engineering.nyu.edu/papers/torres-toto-usenix19.pdf), USENIX Security 2019.
74. OpenSSF. [SLSA Provenance](https://slsa.dev/spec/v1.0/provenance), official specification.

---

## 21. 最终判断

这个领域不是“再找一些 benchmark 错误”这么简单，而是在形成一个新的评测基础设施问题：**如何审计负责测量 AI 的测量系统本身。**

现有文献已经充分证明：

- benchmark 错误普遍存在；
- 错误会改变模型得分和排名；
- LLM/统计方法可以高效发现候选；
- judge、rubric、测试套件和执行环境都可能成为失真来源；
- 动态 benchmark 和增强测试能缓解部分问题。

但仍未被系统解决的是：

1. 如何把候选转成可重放确认；
2. 如何跨执行协议复用确认合同；
3. 如何证明变换保语义、mutant 非等价、输入合法；
4. 如何让外部证据既可用又不污染；
5. 如何从 confirmed finding 走到最小修复、无回归和排名影响。

因此，BenchAudit 最合理的长期北极星不是追求“自动检测器在所有缺陷上的最高 F1”，而是：

> 在此前没有为单个 item 手写证明器的新 benchmark 上，自动产生可由第三方本地重放的 confirmed 缺陷；随后生成最小修复，证明原缺陷消失且没有新回归，并量化修复对最终评测结论的影响。

如果这条链真正走通，它与候选审计、LLM judge、mutation testing、provenance 和 benchmark repair 都相连，但又不等同于其中任何一条已有路线。这正是目前最清楚、也最有可能形成独立研究贡献的空白。
