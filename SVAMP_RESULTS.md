# SVAMP-Platinum 固定 100 题结果

## 核心指标

- Items：100
- Known defects：38
- 单次 LLM Flagged：43
- BenchAudit candidate Flagged：50

| 方法 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| 单次 LLM | 28 | 15 | 10 | 0.651 | 0.737 | 0.691 |
| BenchAudit | 32 | 18 | 6 | 0.640 | 0.842 | 0.727 |
| 差值（BenchAudit−单次 LLM） | +4 | +3 | -4 | -0.011 | +0.105 | +0.036 |

## 解读

1. BenchAudit Recall 从 0.737 提高到 0.842，提高 +0.105。
2. BenchAudit F1 从 0.691 提高到 0.727，提高 +0.036。
3. 净 TP 从 28 增至 32，多找到 4 个真实缺陷。集合层面，BenchAudit 新增找出 8 个 TP，同时漏掉 4 个单次 LLM 已找到的 TP，因此净增 4。
4. FP 从 15 增至 18，增加 3；Precision 因而从 0.651 小幅降至 0.640。

## 与历史参考结果对照

| 方法 | 版本 | TP | FP | FN | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| 单次 LLM | 本次 | 28 | 15 | 10 | 0.651 | 0.737 | 0.691 |
| 单次 LLM | 历史参考 | 26 | 3 | 12 | 0.897 | 0.684 | 0.776 |
| BenchAudit | 本次 | 32 | 18 | 6 | 0.640 | 0.842 | 0.727 |
| BenchAudit | 历史参考 | 37 | 6 | 1 | 0.860 | 0.974 | 0.914 |

本次两种方法都比历史参考产生更多 FP；BenchAudit 本次 Recall/F1 也低于历史参考。可能原因包括模型服务已切换到 `deepseek-v4-flash`、API 服务行为变化、非确定性、thinking 设置、提示词/聚合实现和 Git commit 不同。历史数字仅用于定位差异，不能替代本次固定 manifest 的实测结果。

> 口径说明：以上 BenchAudit 数字是 **candidate/review 候选检测能力**，不是系统自动 confirmed 的错误数量。本次报告的 confirmed 层为 0；候选仍需人工复核。
