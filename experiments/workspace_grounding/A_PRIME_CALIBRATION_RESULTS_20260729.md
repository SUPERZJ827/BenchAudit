# Workspace grounding A′ calibration：冻结负结果

协议：`workspace-grounding-a-prime-dev-v1-20260729`

## 1. 裁决

**Calibration FAIL。未运行 10 个 internal-validation task，未生成第四份
holdout。**

本实验只使用已经污染的 dual-triage 开发数据，不构成泛化证据。

## 2. 数据与成本

- 20 个 calibration task；
- 405 条 rubric；
- family-reviewed grounding positive：19；
- reviewed-reference：21 positive + 7 negative；
- DeepSeek 请求 20，成功 20，失败/重试 0；
- prompt tokens 126,647；
- completion tokens 35,971；
- total tokens 162,618；
- verifier 调用 0；
- finding / review-ceiling escape 0。

## 3. A 与 A′

| 方法 | Candidate rate | Family recall | Reviewed P | Reviewed R | Reviewed F1 | 反事实 logical calls |
|---|---:|---:|---:|---:|---:|---:|
| 旧 A | 211/405 = 52.1% | 16/19 = 84.2% | 0.850 | 0.810 | 0.829 | 231 |
| A′ | 188/405 = 46.4% | 12/19 = 63.2% | 0.812 | 0.619 | 0.703 | 208 |

A′ 只将 candidate rate 降低 5.7 个百分点，反事实逻辑调用降低 10.0%，
但 family recall 同时下降 21.0 个百分点。它没有形成有效 Pareto 改进。

Family-positive 分母同样来自历史候选的独立复核，而非全量人工 gold；
因此 84.2%/63.2% 都是**在已知可发现正例上的条件 recall**。该 universe
不是旧 A 候选的子集（旧 A 本身也漏检），但仍不能外推为全库 recall。

阈值 `0.50/0.60/0.70/0.80/0.90` 的候选集完全相同。405 个置信度中：

- 273 个为 1.0；
- 40 个为 0.95；
- 75 个为 0.9；
- 17 个为 0.8。

因此本模型的该字段高度饱和，不能作为有效 Pareto 控制量。

## 4. 结构化原因分解

| Reason code | 数量 |
|---|---:|
| unsupported_exact_constraint | 178 |
| input_supported | 75 |
| general_quality | 51 |
| task_supported | 47 |
| artifact_satisfaction_only | 29 |
| output_contract_supported | 11 |
| unsupported_prescriptive_content | 9 |
| intrinsic_validity | 3 |
| mechanically_derivable | 1 |
| input_evidence_contradiction | 1 |

本地窄规则强制拒绝 7 条 general-quality 和 3 条 intrinsic-validity rubric。
它在全部 26 条 P1 grounding positive 上离线扫描为 0 误拒，但规模太小，
不足以解决 A 的主体候选膨胀。

旧 A 只能离线分解为 candidate / verifier outcome，因为其 response schema
只存 `candidate_indices`，没有 reason code。A′ 证明结构化可观测性已经补上，
但不代表拒绝判断本身可靠。

## 5. 七条 family-positive 漏检的共同根因

A′ 将以下要求错误视为已被宽泛任务支持：

- “合并面板”被解释为支持“第一张必须来自 panel A”；
- “生成可视化图表”被解释为支持指定 bar/pie/donut chart；
- “提供建议”被解释为支持五个指定建议类别；
- “生成 dashboard/report”被解释为支持指定分区与章节；
- 输入中存在十条意见，被解释为支持 rubric 指定的汇总口径。

它混淆了：

> 某种设计是合理的 / 输入中存在相关信息

与：

> rubric 指定的精确设计或汇总口径是 task 唯一授权的要求。

这是语义错误，不是调 confidence threshold 能解决的校准问题。

红队进一步发现，7 条漏检中有 3 条的 `brief_reason` 与 `reason_code`
直接矛盾。例如 rubric 明确要求六个具名章节，模型的 brief 写
“Requires specific sections”，却选择 `general_quality`、把证据来源标为
`intrinsic` 且不给引文。因此问题不只是 confidence 未校准：让模型自行选择
reason code 的结构本身没有形成可靠约束。

## 6. Exact 诊断探针

在不调用 API、不改变 calibration 裁决的前提下，将冻结 Exact router
与 A′ 做离线并集：

| Evidence 设定 | Exact 路由 | 相对 A′ 新增 | 并集 candidate rate | 恢复漏检 |
|---|---:|---:|---:|---:|
| 空 input evidence（路由上界） | 9 | 3 | 47.2% | 0/7 |
| 真实 input evidence | 6 | 0 | 46.4% | 0/7 |

Exact 的条件只会检查目标是否“不在 visible evidence 中”；扩大 input
evidence 只能删除路由原因、不会新增。因此空 evidence 的 9/+3/47.2%
只是上界，不是操作值。真实证据设定下 Exact 对 A′ 没有新增候选。

因此这些漏检不是现有 exact-literal 探针可补的形式缺口，而是对“宽泛任务
是否授权精确设计”的语义判断错误。Exact 继续只保留为诊断/回归探针。

## 7. 下一步

1. 不把当前 A′ 接入默认流程；
2. 不运行 internal validation，不追加第二模型或第二视角；
3. 保留结构化 reason/evidence 输出作为诊断基础；
4. 下一版不应依赖 LLM 自报 confidence；
5. 只有可机械验证的“明确支持证书”才允许确定性拒绝；LLM 的
   `task_supported/input_supported` 不能单独作为拒绝依据；
6. 新方案必须另立协议，继续只用 calibration 开发；未使用的 10 个
   internal-validation task 保持未运行。

## 8. 复现锚

- 实现提交：`35c1714e6a12249399d909daadfcf77ebef9caeb`
- decisions SHA256：
  `689fad58c3947109b3547561681d3fa258ecbc7ded9ec94cfb7751d2ec061c1a`
- cache SHA256：
  `53740726724c1a58e200245a3795ca243c2573ec49aa1ce838b1f7d7b39fc6e4`
- runtime SHA256：
  `8f307d1d906cc8729462405bb4667cada0f90236c9984c53ade213f182ceee63`
- analysis SHA256：
  `fee5a065173851bb5597af5994e3beee9408bf40aaa0b9d62854d617d5434147`

完整运行产物：

`/home/zhoujun/llmdata/after623/reports/workspace_grounding_a_prime_calibration_20260729/`
