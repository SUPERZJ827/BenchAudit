# 端到端闭环:用我们审计器自己检出的题剔除,排名会变吗?

> 不依赖第三方标注——剔除的是**本项目审计器 `--llm-audit` 检出**的答案/选项类缺陷题。

> 15 模型;审计器用 DeepSeek(review 级信号,MCQ 上 LLM 判断不自动 confirmed)。


## 1. 审计器 vs 第三方标注(我们真找到那些改排名的题吗)

- 审计器检出客观缺陷题:**318** 道
- MMLU-Redux 客观错题(第三方标注):181 道
- 命中(交集 TP)= 138 → **precision=0.43, recall=0.76, F1=0.55**

## 2. 排名变化:用我们检出剔除 vs 用第三方标注剔除

| 剔除依据 | 剔除题数 | 全局 Kendall τ | 全局最大名次变动 | Per-subject 冠军易主 |
|---|---:|---:|---:|---:|
| **我们审计器检出** | 318 | 0.981 | 1 | 9/28 |
| 第三方 MMLU-Redux 标注 | 181 | 0.981 | 1 | 2/28 |

## 3. 用我们检出剔除后,冠军易主的 subject

| subject | 题数 | 我们剔除 | Top-1 变化 |
|---|---:|---:|---|
| virology | 63 | 52 | command-r-08-2024 → deepseek |
| college_chemistry | 38 | 23 | nova-pro-v1 → gemini-2.5-flash |
| business_ethics | 24 | 14 | llama-3.3-70b-instruct → gpt-4o |
| high_school_european_history | 26 | 10 | gpt-4o → deepseek |
| security_studies | 15 | 6 | qwen-2.5-7b-instruct → deepseek |
| high_school_psychology | 17 | 5 | gpt-4o → deepseek |
| astronomy | 19 | 4 | deepseek → gpt-4o |
| high_school_chemistry | 16 | 4 | gemini-2.5-flash → deepseek |
| philosophy | 17 | 3 | deepseek → gemini-2.5-flash |

## 结论(经随机删题对照修正)

审计器仅凭自己的检测,以 **recall=0.76 / precision=0.43** 找回了大量第三方人工标注的客观缺陷题——**这是站得住的硬结果**:系统不依赖第三方标注就能高召回地定位已知缺陷。

但**「用我们检出剔除→9 个 subject 冠军易主」不能作为影响证据**:细分 subject 仅 8–27 题,剔除后常剩个位数、多模型并列,'冠军'由 tie-break 决定;随机删题对照(`random_deletion_control.md`)显示,删**等量随机题**翻转的 subject 数与审计器删题无统计差异(p≈0.32)。故本实验应定位为**候选驱动的排名敏感性探针**,而非「自动纠错闭环」。

## 诚实边界

- 审计器检出为 **review 级候选**(高召回,含假阳性),非自动 confirmed;MCQ 语义缺陷本就不该自动 confirmed。
- 审计 recall=0.76 意味着仍漏检部分第三方标注错题;precision=0.43 表示部分检出未被第三方标注(可能是漏标或假阳,需人工复核)。
- per-subject 冠军易主经随机删题对照后**不显著**(见 random_deletion_control.md);唯一稳健的单点是 philosophy(随机翻转概率 1.8%)。
- 1000 题子集、DeepSeek 单模型审计、15 个作答模型、zero-shot 单次。