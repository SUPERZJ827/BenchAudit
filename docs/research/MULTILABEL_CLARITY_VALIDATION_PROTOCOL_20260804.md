# 多标签 clarity schema 效果验证协议

> 日期：2026-08-04
> 状态：**frozen before the paid comparison runs**
> 被测改动：commit `53f9aa7`（clarity 单一互斥状态 → 置信度排序列表，primary 计分）

## 0. 待检验的主张

> 单一互斥 `clarity_status` 结构性压制了缺陷类型：一道题同时有歧义和缺材料时，只能报其中一个。改成排序列表后，被压制的类型应当浮现。

盲测上的观察动机：clarity auditor 报 `ambiguous_goal` 161 次，`missing_context` 仅 2 次。

## 1. 预注册判据

| 结局 | 判据 |
|---|---|
| **压制成立且已缓解** | 新 schema 下 clarity 报出的**缺陷类型分布**较旧 schema 更分散（非 `ambiguous_goal` 类型占比上升），**且** 报出 >1 标签的响应比例 > 10% |
| **压制不成立** | >1 标签的响应比例 ≤ 10%，即模型本来就极少认为一题有多个问题；此时该改动只是 schema 整洁，不构成能力提升，**须如实记录** |

**代价门（任一触发即判定该改动有害）**：

- primary 计分下的候选层 **F1 中位数下降超过臂内跨度**；
- 逐条 violation-Jaccard **下降超过臂内跨度**。

## 2. 冻结的对照

| | 旧 schema | 新 schema |
|---|---|---|
| 产物 | 级联消融 `full` 臂 `full_1..5.json` | 本次 `run1..5.json` |
| 输入 SHA | `f27f8ebf56b33fbe…` | 同 |
| manifest | `svamp_platinum_pilot100`，`9b26031b62b7eabf…` | 同 |
| 模型/温度/votes/thinking | v4-flash / 0.0 / 1 / disabled | 同 |
| auditors | `gold,question,quantity,event`，cascade | 同 |
| methods | 18 | 同 |
| cascade_mode | full | full |

唯一差异是 clarity schema。两臂各 n=5，每次独立空缓存。

## 3. 必报指标

1. 候选层 P/R/F1，五跑各值 + 中位数；
2. item / violation Jaccard，每臂 10 个配对的均值与 min–max；
3. **clarity auditor 报出的缺陷类型分布**（两臂对比）；
4. **每条响应的标签数分布**，以及 >1 标签的比例；
5. token 与成本。

## 4. 预算与停止

| 项 | 值 |
|---|---|
| 增量成本上限 | **¥10**（已完成 656 条调用命中缓存，不重复计费） |
| 停止条件 | operational failure > 5%；出现 LLM 派生 confirmed；method 集不为 18；provider 持续 503 |

## 5. 已知中断

2026-08-04 09:39 首次尝试，run1 在 656/665 调用处被 provider 过载中断
（`HTTP 503 "Service is too busy"`，随后连最小请求也超时）。
已完成调用保留在缓存中，重跑复用。**这是外部故障，不构成结果。**
