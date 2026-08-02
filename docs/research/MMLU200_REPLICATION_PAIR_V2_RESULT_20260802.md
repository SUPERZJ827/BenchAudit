# MMLU-200 完整复现对 V2 结果

> 日期：2026-08-02  
> 裁决：**DOES_NOT_SUPPORT_MMLU_MORE_STABLE_FOR_THIS_PAIR**  
> 两次完整性门：PASS / PASS  
> confirmed：0 / 0

## 1. 核心结果

| 指标 | run 1 | run 2 | 差异 |
|---|---:|---:|---:|
| candidates | 86 | 83 | −3 |
| TP | 68 | 62 | −6 |
| FP | 18 | 21 | +3 |
| FN | 32 | 38 | +6 |
| precision | 0.791 | 0.747 | −0.044 |
| recall | 0.680 | 0.620 | −0.060 |
| F1 | 0.731 | 0.678 | **−0.0536** |

复现集合：

- item Jaccard：`0.8105`；
- violation Jaccard：`0.6834`；
- F1 绝对差：`0.0536`。

预注册参照为 SVAMP violation-Jaccard `0.845` 与 F1 极差 `0.046`。本次 MMLU 两项都更差，因此不是 mixed result，直接落入：

```text
DOES_NOT_SUPPORT_MMLU_MORE_STABLE_FOR_THIS_PAIR
```

这回答了原问题：当前证据不支持“MMLU 天然比 SVAMP 稳”。

## 2. 这次确实是完整运行

| 完整性项 | run 1 | run 2 |
|---|---:|---:|
| methods | 18/18 | 18/18 |
| items | 200/200 | 200/200 |
| attempts / cap | 1256/1600 | 1257/1600 |
| operational failure | 3/3054 = 0.098% | 2/3050 = 0.066% |
| cache hits | 0 | 0 |
| provider failures | 0 | 0 |
| provider tokens | 2,913,971 | 2,911,572 |
| LLM-derived confirmed | 0 | 0 |

因此 V2 没有 V1 与历史 21-method mmlu200 的 cap 截断问题。两个 cache 各自从空文件开始，严格串行，未复用 V1 缓存。

## 3. 波动来自哪里

| detection method | Jaccard |
|---|---:|
| `static_rule` | **1.000** |
| `task_integrity_rule` | **1.000** |
| `llm_question_clarity` | 0.938 |
| `llm_evidence_fusion` | 0.677 |
| `llm_gold_audit` | 0.655 |
| `llm_option_set` | 0.633 |
| `llm_option_applicability` | 0.000 |

两个确定性方法逐条一致，符合 SVAMP n=5 的同一规律。主要波动位于 gold、option 与派生 fusion 层。`llm_option_applicability=0` 是小样本敏感项，不能单独解释为整体最差方法；其两次 finding 集没有交集。

`llm_question_clarity=0.938` 表明“LLM 方法必然都不稳定”也不准确：触发结构与任务分布仍然重要。

## 4. 对下一步的含义

1. 单跑的 MMLU/SVAMP 跨版本 F1 差不能归因给代码或模型版本；运行噪声本身足以造成约 0.05 的摆动。
2. 三臂消融坚持每臂 n=3 是必要的；用一跑比较 current/tightened/vote 会落入这次已经测到的噪声量级。
3. 收紧策略应优先针对 gold/option 的不稳定触发与 fusion 级联，而不是笼统压制全部 LLM auditor。
4. 历史 21-method mmlu200 必须继续带 `1400/1400、8.58% operational failure、1067 coverage unknown` 的截断披露。

## 5. 边界与产物

这只是同日、固定 MMLU-200 样本上的一个 pair，不是 MMLU 总体方差估计，也不能替代 n≥3 的分布。

原始 cache/report/comparison 保存在：

```text
/home/zhoujun/llmdata/after623_worktrees/mmlu200-replication-pair-v2-20260802/
  reports/mmlu200_replication_pair_v2_20260802/
```

机器汇总：[mmlu200_replication_pair_v2_summary_20260802.json](../experiments/mmlu200_replication_pair_v2_summary_20260802.json)。原始 runner summary SHA-256：`32f3a198f41d51cfecafea7695fa51a3dd77366e844e4ed79f430c19e43e12cc`。
