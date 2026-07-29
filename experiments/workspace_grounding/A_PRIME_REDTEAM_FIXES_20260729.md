# Workspace A′ Claude 红队问题闭环

依据：

`/home/zhoujun/llmdata/after623/BenchAudit_A_Prime_Claude独立红队复核报告_20260729.md`

全程零 API，没有重跑 calibration，也没有接触 internal validation。

## B1：rubric index 类型

已修复。`_indexed_structured_triage_decisions` 现在只接受 literal JSON
integer：

- `true`：拒绝；
- `1.0/1.9`：拒绝；
- `"1"`：拒绝；
- `1`：接受。

缺行/重复/覆盖检查保持不变。

## B2：Exact 诊断口径

已改写：

| Evidence | Exact | 相对 A′ 增量 | 并集 rate | 恢复漏检 |
|---|---:|---:|---:|---:|
| 空 input evidence（上界） | 9 | 3 | 47.2% | 0/7 |
| 真实 input evidence | 6 | 0 | 46.4% | 0/7 |

主 calibration FAIL 不依赖 Exact。

## B3：routing-only substantive finding

已结构性收紧。当 `auditor.verify_unsupported=False` 时：

- semantic/objective decisions 仍保存用于测量；
- checker 不发 substantive finding；
- operational failure 仍发 operational review finding。

新增 objective-title mismatch 回归测试，覆盖
`routing_only=False + verifier=None + objective unsupported`。

## B4：阶段预算

新增机器可执行的阶段配置：

- calibration：25 attempts / 400,000 tokens；
- internal validation：10 attempts / 200,000 tokens；
- 合计：35 attempts / 600,000 tokens。

历史运行仍如实记录其原始 combined config 和实际
20 attempts / 162,618 tokens，不 retroactively 修改 provenance。

## B5/B6：解释边界

报告已补充：

- 7 条漏检中 3 条 `brief_reason` 与 `reason_code` 自相矛盾；
- family recall 也是历史已知正例上的条件 recall，不能外推为全库 recall。

## 不变项

- 原始 decisions/cache/runtime/analysis 未修改；
- calibration 主数字未修改；
- calibration FAIL 未修改；
- internal validation 仍未运行；
- A′ 仍不进入默认路径。
