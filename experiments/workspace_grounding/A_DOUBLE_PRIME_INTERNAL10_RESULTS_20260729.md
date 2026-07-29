# Workspace grounding A″：internal10 冻结结果

> **2026-07-30 口径更正：**本报告的 7 条 family positive 使用了 P0
> 盲审包。该包的抽样部分依赖旧路由器的漏检/B-only 案例，不适合估计旧 A
> 的 recall。原始预注册裁决仍为 FAIL，但跨方法比较应使用此前已存在的 P1
> family reference：旧 A、A′、A″ 分别为 **6/7、4/7、4/7**。详见
> `A_DOUBLE_PRIME_INTERNAL10_P1_CORRECTION_20260730.md`。下文保留原始
> P0 协议数字，作为不可改写的历史记录，不再作为公平基线。

协议：`workspace-grounding-a-double-prime-internal10-v1-20260729`

裁决：**FAIL。停止 A″ 路线，不创建第四份 holdout。**

## 1. 结果

固定工作点为 R2c+R2d，没有重新选择组合：

| 方法 | Candidate | Candidate rate | Family TP | Family recall | Reviewed P/R/F1 |
|---|---:|---:|---:|---:|---:|
| 旧 A | 118 | 57.8% | 0/7 | 0.0% | 0.700 / 0.778 / 0.737 |
| A′ | 88 | 43.1% | 3/7 | 42.9% | 未单独作为 gate |
| **A″：R2c+R2d** | **93** | **45.6%** | **3/7** | **42.9%** | **0.750 / 0.667 / 0.706** |

A″ 满足候选、安全和完整性门槛，但只命中 3/7，未达到预注册的 6/7：

| Gate | 结果 |
|---|---|
| family hits ≥ 6/7 | **FAIL：3/7** |
| candidates ≤ 118 | PASS：93 |
| candidate rate ≤ 57.843% | PASS：45.588% |
| logical calls ≤ 128 | PASS：103 |
| review ceiling escape = 0 | PASS |
| operational unknown = 0 | PASS |
| 固定 R2c+R2d | PASS |

唯一失败项是 family recall，但它是核心 gate，因此总裁决必须为 FAIL。

## 2. 规则迁移结果

- R2c 触发 0 次；
- R2d 触发 5 次；
- R2c/R2d 对 7 条 family positive 的直接命中均为 0；
- 5 条本地 residue 只增加候选，没有恢复新的已知 family positive；
- A″ 的 3 个 family hit 全部已经由 A′ 路由获得。

这与运行前预注册的脆弱性预期吻合：R2c 在 internal10 上为 0 次触发，
冻结工作点实际退化成 R2d 路由补充，而且没有带来目标召回。

开发集上的三项词表消融说明规则不是由窄词表挑中特定 item；internal10
进一步说明，**不是词表拟合并不等于机制能够跨 task 恢复目标 family**。
R2c 的真实数据支持仍只有 dev20 上的单个样本。

## 3. 成本

| 指标 | 数值 |
|---|---:|
| API attempts | 10 |
| API successes / failures | 10 / 0 |
| prompt tokens | 74,058 |
| completion tokens | 19,167 |
| total tokens | 93,225 |
| verifier API calls | 0 |
| A″ logical calls | 103 |
| 旧 A logical calls | 128 |
| 相对旧 A logical-call reduction | 19.5% |

实际 token 使用低于 200,000 停止线，没有重试、第二模型或第二视角。

## 4. 安全与可复现

- 10/10 task、204/204 rubric 完整；
- operational unknown：0；
- review ceiling escape：0；
- R2c+R2d 产生的 observation 均保持 review-only；
- 运行前 11 份冻结输入哈希全部通过；
- runtime contract 的 12 项检查全部通过。

H1 的 92 条诊断中仍有 53 条因 `input_text` 未传入而为 unknown；H1 不进入
候选集，且 R2b 未进入冻结工作点，因此该输入可见性边界不改变本次 gate，
但仍限制对输入来源拒绝理由的完整解释。

原始产物：

| 文件 | SHA256 |
|---|---|
| `grounding_item_structured_triage_items.jsonl` | `cab777f36735f38f182d7ace397e47fd276c1d2a729a6dfb38e5e88298837042` |
| `grounding_item_structured_triage_cache.jsonl` | `eda228758f22da1fa508dad07a655d3bdfa483221ed53f5e65ea8b3f80778eef` |
| `runtime.json` | `8a1e3b50c763d9e0eaa134a239eefa612708740015291dc83359fd260ec58885` |
| `provenance.json` | `42bfdf12009441a791222c9dc80cdef84d95002749f2255c36be622417325fd2` |
| `a_double_prime_analysis.json` | `7a8d63a41990747bdafc91f31d712eb1c2dc72decf4a0638bd4ce2aac412aa18` |
| `a_double_prime_observations.jsonl` | `9e827aafaf835fafa780455c5bb89b1201778ba2086d17166e9b862803e00edb` |
| `a_double_prime_h1_diagnostics.jsonl` | `9b2a75befb1da1f9cb21315e4c0f45822a243337c7bb9d03613ad5a3eaa19b9f` |

完整外部产物位于：

```text
/home/zhoujun/llmdata/after623/reports/
workspace_grounding_a_double_prime_internal10_20260729/
```

仓库内冻结分析：

`A_DOUBLE_PRIME_INTERNAL10_ANALYSIS_20260729.json`

## 5. 诚实结论

本实验支持两个结论：

1. A″ 可以在 internal10 上把候选从旧 A 的 118 降至 93，并保持安全和
   operational 完整；
2. 该成本下降伴随严重的已知 family recall 损失，3/7 远低于 6/7，
   因而不能作为默认路由器，也没有资格进入新 holdout。

不能根据本结果做的事：

- 切换到 calibration 上的 R2a+R2d 后重跑 internal10；
- 针对这 7 条增加词表或放宽 R2c 唯一性闸门；
- 把 45.6% candidate rate 单独宣传成优化成功；
- 创建第四份 holdout；
- 把 review-only residue 升级为 confirmed。

按照预注册停止纪律，A″ 路线到此保留为负结果。下一步应回到研究问题层面：
决定是否继续投入 Workspace grounding 路由，或把这一负结果用于说明
“开发集上恢复 recall 的静态 residue 规则难以迁移”，转向拥有可客观 replay
的缺陷确认任务。
