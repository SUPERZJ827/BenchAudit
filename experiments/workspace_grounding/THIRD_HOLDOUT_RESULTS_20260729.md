# Workspace grounding 第三份 holdout：冻结结果

协议：`workspace-grounding-third-holdout-v1-20260729`

本次在代码、contract、exact router 和 30 个 task 均冻结后运行。30 个
task 与前两批共 60 个开发 task 完全不重叠。实验只测候选路由，不运行
isolated verifier，也不把路由结果作为缺陷 finding。

## 1. 结果

评价集包含 575 条 rubric，其中既有 reviewed-reference 覆盖 48 条：
32 条 positive、16 条 negative。该 reference 来自历史候选复核，存在
selection bias，因此 P/R/F1 只能解释为条件指标，不能代表 WorkspaceBench
全量自然分布。

| 路由 | P | R | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| A：DeepSeek 单视角 | 0.667 | 0.812 | 0.732 | 26 | 13 | 6 |
| Exact：零 API | 1.000 | 0.094 | 0.171 | 3 | 0 | 29 |
| A + Exact | 0.667 | 0.812 | 0.732 | 26 | 13 | 6 |

Exact 在全部 575 条 rubric 中路由 20 条，其中 18 条已被 A 路由。剩余
2 条增量候选均不在已有 reviewed-reference 中，因此不能算 TP 或 FP。
Exact 命中的 3 条已复核 TP 全部已被 A 覆盖，A + Exact 对已知正例没有
新增召回。

全部 rubric 的候选量：

| A | Exact | 交集 | 并集 | Exact 相对 A 新增 |
|---:|---:|---:|---:|---:|
| 424 | 20 | 18 | 426 | 2 |

A 的候选率为 424/575 = 73.7%。如果后接逐候选 verifier，它仍会带来
很高成本，因此本轮不仅没有证明 Exact 的增量价值，也暴露出 A 本身
缺少足够分诊能力。

## 2. API 与安全

- DeepSeek `deepseek-v4-flash`，temperature 0，thinking disabled；
- 30 次逻辑调用，实际 attempts 30，成功 30，失败/重试 0；
- prompt tokens 182,295，completion tokens 1,028，总计 183,323；
- verifier 调用 0；
- findings 0；
- confirmed 或 review-ceiling escape 0；
- Exact 额外 API 调用 0。

相较预注册上限，attempts 使用 30/40，tokens 使用
183,323/600,000（30.6%）。

## 3. 预注册裁决

通过：

- review ceiling escape = 0；
- verifier call = 0；
- attempts 与 token 预算内；
- A + Exact recall 不低于 A；
- Exact 路由率不超过 15%。

未通过：

- Exact 相对 A 没有新增 reviewed TP；
- 2 条增量候选均未标注，无法满足已标注增量 precision ≥ 0.50。

最终裁决：**FAIL，Exact router 不进入默认路径。**

这是保留的负结果。不得在本 holdout 上调整规则后重新宣称泛化提升。
两个未标注增量候选可以作为探索性人工复核对象，但任何后验判断都不改变
本次预注册裁决。

## 4. 下一步含义

不建议继续增加第二个 LLM 视角，也不建议立即重调 Exact。优先问题变成：

1. 将 A 从“几乎全选”的高召回提示词，改造成真正有拒绝能力的分诊器；
2. 在开发集上同时优化 routing recall 和 candidate rate，而非只追 recall；
3. 继续保持 router review-only，最终缺陷仍需独立 verifier；
4. 新版本冻结后，必须换第四份 task-disjoint holdout 评价。

## 5. 复现锚

- 执行代码提交：`ab2de93f325801915c646c1c46c1cf286052daac`
- raw decisions SHA256：
  `cb8110f33982ebacd92c6ea84913cc9229d6b74cd19d8dafd6951fae2c2e1a98`
- cache SHA256：
  `e512ea47624f32ace41f7c6d276c46d09ebf6d517e3fcaa5149932964625c9ca`
- runtime SHA256：
  `e483534cf7b6339a89f5c28b0fb1a10a0f5d35d4abca58f5a1ddc5969d23a0b9`
- analysis SHA256：
  `0cef0c5c1a3c73a179a91d7f1edbf53c0b0a434ba366adf8b2f5073225523743`

完整未提交运行产物位于：

`/home/zhoujun/llmdata/after623/reports/workspace_grounding_third_holdout_20260729/`
