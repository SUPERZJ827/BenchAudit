# 排名影响实验:benchmark 缺陷是否改变模型排名(MMLU-Redux)

> 数据:MMLU-Redux 1000 题(带 error_type 真值标注);15 个模型;zero-shot 单次作答。

> 口径:**full**=全 1000 题(含缺陷);**objective**=剔除 181 道客观缺陷题(wrong_groundtruth/no_correct/multiple_correct,即我们审计器能 confirmed 的类型);**strict**=只留 630 道 ok 题。


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

被剔除的 3 类正是本项目审计器能**客观 confirmed** 的缺陷类型(wrong_gold / no_correct / multiple_correct)。因此这个排名变化不是假想:它量化了「我们能自动检出的缺陷」若不修正会造成多大的排名失真。

## 诚实边界

- 仅 1000 题子集、15 个模型、zero-shot 单次、无投票;更大 leaderboard 变动可能不同。
- 真值用 MMLU-Redux 标注(第三方人工),非本项目审计器输出;闭环成立但两者是独立来源。
- 排名基于单次作答,存在采样噪声;方向性结论稳健,具体名次可能有 ±1 抖动。

## Per-subject 排名影响(缺陷集中处,文献效应所在)

在 16 个题数≥15、剔除≥3 道客观错题的 subject 中,**5 个的 Top-1 在剔除错题后换人**。洗牌最厉害的:

| subject | 题数 | 剔除客观错题 | Kendall τ | 最大名次变动 | Top-1 变化 |
|---|---:|---:|---:|---:|---|
| global_facts | 21 | 9 | 0.58 | 6 | ⚠️ gpt-4o → qwen-2.5-72b-instruct |
| college_chemistry | 38 | 23 | 0.60 | 7 | ⚠️ nova-pro-v1 → gemini-2.5-flash |
| virology | 63 | 41 | 0.60 | 6 | ⚠️ command-r-08-2024 → qwen-2.5-72b-instruct |
| professional_law | 30 | 13 | 0.62 | 6 | ⚠️ gemini-2.5-flash → llama-3.3-70b-instruct |
| professional_accounting | 21 | 5 | 0.66 | 8 | 否 |
| logical_fallacies | 39 | 10 | 0.70 | 7 | 否 |
| public_relations | 20 | 6 | 0.70 | 6 | 否 |
| human_sexuality | 27 | 5 | 0.70 | 6 | 否 |
| professional_psychology | 19 | 3 | 0.73 | 4 | ⚠️ gpt-4o-mini → deepseek |
| miscellaneous | 19 | 5 | 0.75 | 5 | 否 |
| abstract_algebra | 24 | 8 | 0.75 | 4 | 否 |
| machine_learning | 23 | 3 | 0.79 | 5 | 否 |

**结论**:全局 1000 题上排名仅轻微变动(τ=0.981,最大 1 位)——leaderboard 越密集,缺陷越能扰动全局名次(本实验 8 模型时 τ=1.0、15 模型时 τ=0.981);但在缺陷集中的 subject 上,排名剧烈洗牌——5/16 个 subject 的冠军易主。**benchmark 缺陷对排名的影响是 subject-局部但可颠覆性的**,与文献一致(MMLU-Redux virology 上模型名次大幅重排)。这说明用含缺陷的细分 benchmark 给模型下结论是危险的,且 leaderboard 越密集风险越高。
