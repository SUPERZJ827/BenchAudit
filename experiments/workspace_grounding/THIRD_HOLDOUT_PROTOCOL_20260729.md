# Workspace grounding 第三份 task-disjoint holdout 协议

协议版本：`workspace-grounding-third-holdout-v1-20260729`

## 1. 目标

在 `GroundingDecisionContract v1` 和 exact-constraint router 代码冻结后，
测试：

1. A（单 LLM hidden-constraint router）的路由表现；
2. A + exact deterministic router 是否产生新增 TP；
3. 新增候选量和 reviewed-reference precision；
4. 是否能以零额外 LLM 路由调用改善 recall。

当前 P0/P1、cost pilot 和 dual-triage holdout 已全部视为开发数据。

## 2. 样本选择

从 WorkspaceBench 388 个 task 中排除：

- `COST_PILOT_30_20260728.json` 的 30 个 task；
- `DUAL_TRIAGE_HOLDOUT_30_20260728.json` 的 30 个 task。

使用固定种子：

`workspace-grounding-third-holdout-v1-20260729`

从剩余 task 中选择：

- 20 个至少含 1 条既有 reviewed-positive 的 task；
- 10 个不含 reviewed-positive、但至少含 1 条 reviewed-negative 的 task。

这是一份为 routing recall/precision 富集的评价集，不用于估计 WorkspaceBench
自然缺陷 prevalence。

选择过程不得读取 exact router 输出或 A 路由输出。

## 3. 冻结系统

- Git code commit：生成 manifest 时记录；
- contract：
  `workspace-grounding-decision-contract-v1-20260729`；
- exact router：`benchcore/exact_constraint_router.py`；
- A router：`ITEM_TRIAGE_PROMPT`；
- 模型：`deepseek-v4-flash`；
- 温度：0；
- verifier：关闭。

`A + exact` 只对候选集合做并集，不产生 semantic verdict，不产生 finding，
更不能产生 confirmed。

## 4. API 硬预算

只允许每 task 一次 A 路由：

- 30 个逻辑调用；
- 最多 40 次实际 attempts；
- provider-reported total tokens 软停止上限：600,000；
- 不运行 isolated verifier；
- exact router 的额外 API 调用必须为 0。

如果已有缓存与冻结 prompt、model、task evidence 的 cache key 完全一致，可以
复用；否则不能用旧 prompt 的缓存冒充本轮结果。

## 5. 指标

在 reviewed reference universe 内报告：

1. A candidate precision/recall/F1；
2. exact-only candidate precision/recall/F1；
3. A + exact precision/recall/F1；
4. exact 相对 A 的 incremental candidates / TP / FP；
5. incremental calls / incremental TP；
6. exact reason-code 分布和逐例列表；
7. unlabeled candidate 数量，不能自动计为 TP 或 FP。

若后续进行独立 family review，再补：

- primary-grounding recall；
- acceptable-grounding recall。

## 6. 预注册 gate

- review/confirmation ceiling escapes = 0；
- exact 新增 LLM routing calls = 0；
- A + exact reviewed-positive recall 不低于 A；
- exact 相对 A 至少新增 1 个 reviewed TP；
- 在有 reviewed label 的 exact 增量候选中 precision ≥ 0.50；
- exact routed rubric rate ≤ 15%。

未通过时保留负结果，不在此 holdout 调规则后重新声称提升。

