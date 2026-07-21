# 排名影响实验:benchmark 缺陷是否改变模型排名(MMLU-Redux)

> 数据:MMLU-Redux 1000 题(带 error_type 真值标注);15 个模型;zero-shot 单次作答。

> 口径:**full**=全 1000 题(含缺陷);**objective**=剔除 181 道 MMLU-Redux 人工标注的客观缺陷题(wrong_groundtruth/no_correct/multiple_correct,即我们审计器针对的类型;MCQ 上为 review 候选,不自动 confirmed);**strict**=只留 630 道 ok 题。


## 排名对照(按 full 排名)

| full名次 | 模型 | acc_full | acc_objective | objective名次 | 名次变化 |
|---:|---|---:|---:|---:|:--:|
| 1 | deepseek | 0.803 | 0.899 | 1 | — |
| 2 | google__gemini-2.5-flash | 0.770 | 0.855 | 2 | — |
| 3 | openai__gpt-4o | 0.745 | 0.830 | 3 | — |
| 4 | qwen__qwen-2.5-72b-instruct | 0.734 | 0.817 | 4 | — |
| 5 | openai__gpt-4.1-mini | 0.715 | 0.795 | 5 | — |
| 6 | amazon__nova-pro-v1 | 0.709 | 0.785 | 6 | — |
| 7 | microsoft__phi-4 | 0.705 | 0.778 | 7 | — |
| 8 | meta-llama__llama-3.1-70b-instruct | 0.697 | 0.773 | 8 | — |
| 9 | mistralai__mistral-small-24b-instruct-2501 | 0.692 | 0.772 | 9 | — |
| 10 | meta-llama__llama-3.3-70b-instruct | 0.689 | 0.768 | 10 | — |
| 11 | openai__gpt-4o-mini | 0.679 | 0.746 | 11 | — |
| 12 | cohere__command-r-08-2024 | 0.638 | 0.692 | 13 | ↓1 |
| 13 | qwen__qwen-2.5-7b-instruct | 0.634 | 0.697 | 12 | ↑1 |
| 14 | meta-llama__llama-3.1-8b-instruct | 0.593 | 0.650 | 14 | — |
| 15 | mistralai__mistral-nemo | 0.582 | 0.636 | 15 | — |

## 核心指标

- **Kendall's τ(full vs objective)= 0.981**(1.0=排名完全不变;越低=洗牌越厉害)
- Kendall's τ(full vs strict-ok)= 0.943
- **最大名次变动 = 1 位**
- **Top-1 是否换人:否**

## 解读

剔除的都是**客观错题**(标准答案本身错/无正确答案/多正确答案)——在这些题上,模型答案匹配错误 gold 才算「对」,所以 full 排名奖励了「和标注者犯同样错误」的模型。剔除后名次变动与 Top-1 变化,即为 benchmark 缺陷对排名的直接影响。

## 与审计系统的闭环

被剔除的 3 类正是本项目审计器**针对**的缺陷类型(wrong_gold / no_correct / multiple_correct)——在 MCQ 上这些是 **review 候选**(LLM 判断),不是自动 confirmed。本节量化第三方标注错题对排名的影响;审计器自身检出的闭环见 closed_loop_ranking.md,其 per-subject 结果须对照 random_deletion_control.md(见下方边界)。

## 诚实边界

- 仅 1000 题子集、15 个模型、zero-shot 单次、无投票;更大 leaderboard 变动可能不同。
- 真值用 MMLU-Redux 标注(第三方人工),非本项目审计器输出;闭环成立但两者是独立来源。
- 排名基于单次作答,存在采样噪声;方向性结论稳健,具体名次可能有 ±1 抖动。

## Per-subject 排名影响(缺陷集中处,文献效应所在)

在 16 个题数≥15、剔除≥3 道客观错题的 subject 中,**2 个的 Top-1 在剔除错题后换人**。洗牌最厉害的:

| subject | 题数 | 剔除客观错题 | Kendall τ | 最大名次变动 | Top-1 变化 |
|---|---:|---:|---:|---:|---|
| virology | 63 | 41 | 0.47 | 11 | ⚠️ command-r-08-2024 → qwen-2.5-72b-instruct |
| professional_law | 30 | 13 | 0.60 | 5 | 否 |
| professional_psychology | 19 | 3 | 0.62 | 5 | 否 |
| college_chemistry | 38 | 23 | 0.68 | 6 | ⚠️ nova-pro-v1 → gemini-2.5-flash |
| miscellaneous | 19 | 5 | 0.68 | 6 | 否 |
| logical_fallacies | 39 | 10 | 0.70 | 5 | 否 |
| global_facts | 21 | 9 | 0.71 | 5 | 否 |
| public_relations | 20 | 6 | 0.75 | 5 | 否 |
| formal_logic | 23 | 12 | 0.77 | 4 | 否 |
| human_sexuality | 27 | 5 | 0.81 | 3 | 否 |
| professional_accounting | 21 | 5 | 0.85 | 4 | 否 |
| international_law | 18 | 5 | 0.89 | 4 | 否 |

**结论**:全局 1000 题上排名仅轻微变动(τ=0.981,最大 1 位)——leaderboard 越密集,缺陷越能扰动全局名次(本实验 8 模型时 τ=1.0、15 模型时 τ=0.981);per-subject 层面表面上有 2/16 个 subject 冠军易主,**但这一表象经不起随机删题对照**(见 `random_deletion_control.md`):细分 subject 只有 8–27 题,剔除缺陷后常剩个位数、多个模型并列,'冠军'由 tie-break 决定;删**等量随机题**翻转的 subject 数与之无统计差异(p≈0.32)。**因此不能把 per-subject 冠军易主当作缺陷影响的证据。**真正站得住的是:全局名次随 leaderboard 加密而出现真实换位,以及个别单点(如 philosophy,随机翻转概率仅 1.8%)审计器精准命中了扭转排名的缺陷题。
