# 文献调研范围指南(给学弟)

> 用途:入门本方向的第一步——用 1~2 周做文献调研,建立"benchmark 质量 / 自动查错"的领域认知。
> 先读《AutoDebugging_入门_给学弟.md》建立概念,再按本指南调研。
> **重要**:下面点到的**具体论文标题/作者/年份,请你自己检索核实**(我可能记错);
> 真正可靠、供你直接用的是每个主题的**关键词、要回答的问题、以及和我们工作的关联**。

---

## 目标(调研完成后你应能回答)

1. 这个领域在解决什么问题?主流做法有哪几类?
2. 别人怎么**自动**发现 benchmark 的缺陷?用了什么信号(客观 vs 主观)?
3. 我们的工作(auto-debugging + "只有客观可 grounding 才自动确认")在这张图里处于什么位置、有什么区别?
4. 还有哪些开放问题值得我们做?

---

## 怎么调研(方法,先看这段)

- **检索平台**:Google Scholar、Semantic Scholar、arXiv、ACL Anthology、OpenReview。
- **滚雪球**:先找每个主题里 1~2 篇近两年的高引 / survey,再看它的 related work(往前)和"引用它的论文"(往后)。
- **每篇记五点**:①解决什么问题 ②方法/信号 ③用了哪些数据集 ④主要结论 ⑤局限 + **和我们的关系**。
- **管理工具**:Zotero / Notion 建一个表,按主题归档。
- **带着问题读**,不要只做摘要——每篇都问一句"这对我们的方法有什么启发,或我们和它的区别是什么"。

---

## 调研主题(5 个范围,可按兴趣先做 2~3 个)

### 主题 1 · Benchmark 标注错误 / 数据质量
- **关键词**:benchmark label errors, dataset quality, annotation errors, noisy test sets, benchmark reliability
- **锚点(自行核实)**:Northcutt 等关于测试集普遍标注错误的工作(confident learning / cleanlab 方向);MMLU 的重标注工作(MMLU-Redux / "Are we done with MMLU");MadryLab 的 Platinum Benchmarks(清理到"零标注错误")。
- **要回答**:标注错误有多普遍?怎么**自动**检测?错误对模型排名的影响有多大?
- **和我们的关系**:这是我们 B1/B2(数据缺失/值错)的上游领域。注意区分"标注错误"(答案错)和我们更广的"评分标准本身有缺陷"。

### 主题 2 · 代码 benchmark(SWE-bench)的质量与泄漏
- **关键词**:SWE-bench, solution leakage, benchmark contamination (code), test adequacy, patch evaluation
- **锚点(自行核实)**:SWE-bench 原始论文;SWE-bench Verified(人工筛选高质量子集);社区对 SWE-bench 泄漏 / 测试不充分 / 环境不可复现的批评性讨论。
- **要回答**:SWE-bench 已知有哪些质量问题?社区怎么应对?"题目里泄漏答案"这类被研究过吗、怎么量化的?
- **和我们的关系**:**直接对应你的第一个练习任务**(problem_statement 泄漏检测)。看别人是否做过、我们能否做得更系统。

### 主题 3 · 数据污染 / Contamination detection
- **关键词**:data contamination, test set contamination, benchmark leakage into pretraining, memorization, membership inference
- **要回答**:训练数据污染 benchmark 怎么检测(n-gram 重叠 / 记忆探测 / 时间切分)?
- **和我们的关系**:注意概念区别——"污染"是**训练数据**见过测试题;我们查的是**题目文本内部**泄漏了答案。两者信号不同,别混。

### 主题 4 · LLM-as-a-judge 的可靠性
- **关键词**:LLM-as-a-judge, evaluation reliability, judge bias, self-consistency, position/verbosity bias, evaluator agreement
- **要回答**:用 LLM 当评判者有哪些系统性偏差和不可复现性?怎么缓解?
- **和我们的关系**:**直接对应我们的核心发现**(LLM 审计判定在边界上不可复现、稳定≠正确)。看别人怎么刻画和度量这种不可靠性,对比我们的"决策边界 / P̂ 置信区间"做法。

### 主题 5 · Agentic benchmark 的评测问题
- **关键词**:agent benchmark evaluation, rubric-based grading, LLM agent benchmark, task-based evaluation reliability
- **要回答**:agent / 多步任务 benchmark 怎么评分?rubric 打分有什么固有问题(过约束、主观)?
- **和我们的关系**:对应 Workspace-Bench 这条线(主观 rubric 为什么难自动确认)。

---

## 代表性文献(起点清单)

> 三档可靠度:**⭐ 联网核实过**(带 arXiv 号,可放心引用);**[ABA引]** 出自 ABA 论文的参考文献
> (真实存在,但确切标题/作者/年份请到 arXiv / Scholar 核实);**[经典]** 我记忆中的经典工作(真实、核实细节)。
> **引用前一律自己核对。** —— 本清单由联网检索 ABA 及其引用整理,比纯凭记忆可靠得多。

### ⭐ 最直接的同行:自动 benchmark 审计(必读,已联网核实)
> 这三篇和你们做的是同一件事——benchmark auditing 是正在成型的新子领域,你们**不是孤立的**。精读,想清楚差异化。
- **ABA — Auto Benchmark Audit.** arXiv:2605.26079(Duke / Together AI / Stanford, 2026)。agentic 框架审计 **168 个** benchmark,**25.7%** 任务有问题(隐藏环境依赖 / 规格缺口 / 评分逻辑弱 / 错误 ground truth);过滤后 SWE-bench Verified、Terminal-Bench 2 排名与性能变 **+9.9% / +9.6%**。站点 autobenchaudit.com,代码 github.com/IsThatYou/auto-bench-audit。
- **BenchGuard — Who Guards the Benchmarks?** arXiv:2604.24955(Xinming Tu 等, 2026)。用 frontier LLM cross-verify benchmark artifacts;ScienceAgentBench 查出 12 个(含致命)问题,BIXBench 匹配 **83.3%** 专家缺陷,审计 50 任务 <$15。
- **BenchJack — Do Androids Dream of Breaking the Game?** arXiv:2605.12673(Hao Wang, Alvin Cheung, Koushik Sen, Dawn Song 等 / Berkeley, 2026)。**红队 / reward-hacking 视角**:自动找漏洞让 agent 不解题也能拿高分;**219 个漏洞 / 8 类**,Agent-Eval Checklist;审计 WebArena、OSWorld 等 10 个。

### ① Benchmark 质量 / 标注错误
- **[ABA引] ⚠ 与你练习撞题** aleithan2024 — *SWE-bench+*:报 SWE-bench **32.7% 解题泄漏(solution leakage)**。**必读对照**——别人怎么定义/度量泄漏,想清楚我们(problem_statement 逐字+语义两级)的差异和补充点。
- **[ABA引]** yu2025 — *UTBoost*:SWE-bench 测试不充分。
- **[ABA引]** garg2025 — 用 mutation 检测 over-fitting(saving SWE-bench)。
- **[ABA引]** gema2024 — MMLU 重标注,**6.49%** 错误率(即 MMLU-Redux,我们项目在用)。
- **[ABA引]** vendrow2025 — platinum benchmarks(清理到近零错误再测可靠性)。
- **[ABA引]** reuel2024 — *BetterBench*,46 条 benchmark 最佳实践。
- **[ABA引]** zhu2025 — agentic benchmark 效度威胁 / checklist。
- **[ABA引/经典]** gururangan2018 — SNLI/MNLI 的 annotation artifacts。
- **[经典]** Northcutt et al. *Pervasive Label Errors in Test Sets.* NeurIPS 2021 — 测试集标注错误奠基工作(cleanlab)。

### ② SWE-bench / agent benchmark 本体
- **[ABA引]** jimenez2024 — SWE-bench;openai2024 — SWE-bench Verified;merrill2026 — Terminal-Bench 2;xie2024 — OSWorld。

### ③ 数据污染
- **[ABA引]** jain2024 — *LiveCodeBench*(持续更新、抗污染);huang2026 — *DeepFact*(audit-then-score)。
- 概念区别:"污染"=训练数据见过测试题;我们查的是"题目文本内泄漏答案"。

### ④ LLM-as-a-judge 可靠性
- **[ABA引]** zheng2023 — MT-Bench / Chatbot Arena(judge 一致性)。
- **[ABA引]** feuer2025 — LLM judge 的 position / verbosity / rubric-order 偏差。**和你们"判定不可复现、稳定≠正确"直接呼应。**

### ⑤ 起点建议
从 ⭐ 三篇同行入手,顺它们的 related work 滚雪球——它们已把领域引用网梳理好,是最高效的入口。

---

## 产出(1~2 周后)

1. **一份调研笔记**:按 5 个主题组织,每个主题 3~5 篇核心 + 一段小综述(150 字左右)。
2. **一页"领域地图 + 我们的位置"**:画出主要做法分类,标出我们工作的坐标和差异点。
3. **一次组会分享(~15 分钟)**:讲清"领域在做什么、我们做什么不同、我发现哪些值得做的开放问题"。

---

## 给你的两个提醒

- **我给的具体论文可能有记错,务必自己检索核实**;主题、关键词、问题是可靠的框架。
- 调研不是终点。读完主题 2 后,直接上手第一个练习(SWE-bench 泄漏检测),**边读边做**——这是"以练代学"的意思。
