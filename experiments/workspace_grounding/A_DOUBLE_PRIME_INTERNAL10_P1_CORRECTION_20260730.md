# Workspace grounding A″：internal10 P1 分母更正

日期：2026-07-30

协议：`workspace-a-double-prime-internal10-p1-correction-v1-20260730`

裁决：**FAIL 不变；旧 A 的历史基线从 0/7 更正为 6/7。**

## 1. 为什么需要更正

原始 internal10 报告使用 P0 盲审包定义 7 条 family positive。P0 的样本
构造部分包含旧 A 漏检、B-only 候选与对照，因此适合诊断这些案例，却不适合
估计旧 A 在同一集合上的 recall。其结果 `旧 A = 0/7` 带有选择条件，不能
作为公平的跨方法基线。

在 A″ 实验之前已经存在另一份独立的 P1 family reference：

- `reports/workspace_p1_family_reference_20260728/SEALED_MAPPING.json`;
- `reports/workspace_p1_family_reference_20260728/`
  `GEMINI_3_1_PRO_FAMILY_ANNOTATIONS.jsonl`.

本次更正只替换 family-positive 分母。它没有重新调用 API、没有重跑路由器、
没有更换 R2c+R2d、没有修改候选或原始实验产物。

## 2. 更正结果

| 方法 | Candidate | P0 family recall（原报告） | P1 family recall（更正） |
|---|---:|---:|---:|
| 旧 A | 118 | 0/7 = 0.0% | **6/7 = 85.7%** |
| A′ | 88 | 3/7 = 42.9% | **4/7 = 57.1%** |
| A″：R2c+R2d | 93 | 3/7 = 42.9% | **4/7 = 57.1%** |

两组 internal10 positive 各有 7 条，但交集为 **0**。这证明变化来自标签
分母，而不是候选或运行结果发生变化。

P1 口径下：

- 旧 A 命中 6/7；
- A′ 命中 4/7；
- R2c 与 R2d 对 P1 的 7 条 positive 均无新增命中；
- A″ 因而仍为 4/7，低于冻结门槛 6/7；
- 候选数、安全门、逻辑调用数和 operational 状态全部不变。

因此更正后的结论比原报告更明确：A″ 虽把候选从 118 降至 93，但相对旧 A
损失了 2 条 P1 family positive，并未取得 Pareto 改进。

## 3. 能说与不能说

可以说：

> 在预先存在的 P1 family reference 上，旧 A/A′/A″ 的 internal10 recall
> 分别为 6/7、4/7、4/7；A″ 没有补回 A′ 的 family 漏检，FAIL 裁决不变。

不能说：

- P0 的 0/7 是旧 A 的无偏 recall；
- P1 的 6/7 是 WorkspaceBench 全体缺陷的总体 recall；
- 此次更正产生了新实验数据或新 API 证据。

P1 reference 本身仍来自已审查候选集合，所以 6/7 也是条件 recall，而非
全量 benchmark recall。它只比 P0 更适合做当前三种方法的同集合比较。

## 4. 可复现性

机器结果：

`A_DOUBLE_PRIME_INTERNAL10_P1_CORRECTION_20260730.json`

重算器：

`scripts/recompute_workspace_a_double_prime_internal_p1.py`

关键冻结输入：

| 输入 | SHA-256 |
|---|---|
| 原始 internal10 analysis | `7a8d63a41990747bdafc91f31d712eb1c2dc72decf4a0638bd4ce2aac412aa18` |
| 原始 A″ observations | `9e827aafaf835fafa780455c5bb89b1201778ba2086d17166e9b862803e00edb` |
| P1 mapping | `3b24d271400355409ce9d5a61c808ebb8f5e9992d7e18ef572a5d54c90fabd6e` |
| P1 annotations | `cf88ac639d74d7b1bd98d350199b7de3335d8639086107b58aa9cd762c74e1c7` |

本次调用：

- LLM/API：**0**；
- 原始输出修改：**否**；
- 冻结工作点修改：**否**。

验证：

- 定向更正测试：**6 passed**（含原 internal10 gate 测试）；
- 全仓测试：**806 passed**；
- 两次独立重算产物逐字节一致；
- 更正 JSON SHA-256：
  `41a508c29a742ffa53f0bf0d5f0cbb3f8b5705e06979cfbb77774d938c810f4c`。
