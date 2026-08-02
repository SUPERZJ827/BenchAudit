# MMLU-200 复现对停止结果

> 日期：2026-08-02  
> 裁决：**STOP_AFTER_RUN1_OPERATIONAL_FAILURE_GATE**  
> 协议：`MMLU200_REPLICATION_PAIR_PROTOCOL_20260802.md`  
> 机器回执：`docs/experiments/mmlu200_replication_pair_stop_receipt_20260802.json`

## 1. 结论

第一跑完成 200/200，但未通过预注册完整性门；第二跑因此没有启动，复现对的 Jaccard 与 F1 差异没有产生。

唯一失败项是：

```text
operational_failed / attempted = 303 / 3645 = 8.31% > 5%
```

这不是 DeepSeek 传输或 provider 故障。1400 次实际 API 调用全部成功，缓存命中为 0，模型派生 confirmed 为 0。303 条 operational failure 的逐条错误均为：

```text
LLM API-attempt budget exhausted before provider call (1400/1400)
```

因此准确归因是：**冻结的 1400 次单跑 API attempt 上限不足以完成当前 21-method / all-auditor 计划**。不能把这份不完整报告用于回答“MMLU 是否比 SVAMP 稳定”。

## 2. 冻结条件核验

| 项 | 结果 |
|---|---:|
| detached execution commit | `94b1e66b91ad2c5cc4a2c3e44d0a617ec6a27960` |
| items | 200 / 200 |
| methods | 与冻结的 21 项逐项相同 |
| workers | 8 |
| model | `deepseek-v4-flash` |
| thinking | disabled |
| votes | 1 |
| cache hits | 0 |
| API attempts / successes / failures | 1400 / 1400 / 0 |
| provider tokens | 2,992,586 |
| LLM-derived confirmed | 0 |
| elapsed | 399.554 s |

## 3. operational failure 分布

全部 303 条都由同一个 attempt-budget 原因产生：

| detection method | 数量 |
|---|---:|
| `llm_event_state` | 52 |
| `llm_gold_audit` | 48 |
| `llm_option_set` | 50 |
| `llm_presentation_integrity` | 52 |
| `llm_quantity_consistency` | 52 |
| `llm_question_clarity` | 49 |
| **合计** | **303** |

这也说明失败并非某一 auditor 的解析异常，而是并行调度到达全局 attempt 上限后，尚未开始的多个检查统一 fail-closed。

## 4. 未做的事

- 没有启动 run 2；
- 没有运行 compare；
- 没有计算 pair 指标；
- 没有提高 1400 上限；
- 没有放宽 5% gate；
- 没有复用 run 1 cache；
- 没有追加第三跑。

若以后要重开，必须先根据完整 audit plan 另冻一个足够的 attempt/token/费用上限；不能把本次 1400 条缓存当成“独立空缓存”的替代物，也不能把本次不完整结果与未来完整结果组成复现对。

## 5. 本地产物哈希

原始产物保存在独立 clone 的：

```text
/home/zhoujun/llmdata/after623_worktrees/mmlu200-replication-pair-20260802/
  reports/mmlu200_replication_pair_20260802/
```

| Artifact | SHA-256 |
|---|---|
| execution receipt | `5fa8acca2e5e5286ff6dff878a12685e668c517fafc2e4667213fd1c84a90270` |
| run1 cache | `a916f01848b29876c78beebc5d8cfbb6df38a52d47e2167cd5a2018bfb643b57` |
| run1 report JSON | `fd1f92329b1d9a9db6888c81379e833eedb402a908222d2e34ba5e7a795e7111` |
| run1 report Markdown | `2f5896c10b12f1faf7c0ff467f8dcf7d7939ce32cd6bcbf09be4b4dd0c8efcfe` |
| run1 integrity gate | `bf66a19f572bfa98fc41b5ad7b9484007330efc4f795093015ac95f5d560c2b2` |
