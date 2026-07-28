# Workspace grounding A′ 拒绝能力开发协议

协议版本：`workspace-grounding-a-prime-dev-v1-20260729`

## 1. 研究问题

现有 A（`hidden_constraint`）在第三份 holdout 上路由 424/575 条 rubric，
candidate rate 为 73.7%。该值只是 verifier 成本代理，但足以说明 A 尚未
形成有效拒绝。

本阶段只回答：

> 结构化 A′ 能否在旧开发数据上保持 grounding-family recall，同时显著
> 降低 candidate rate？

本阶段不产生新的泛化结论。

## 2. 数据纪律

只使用已运行过的
`DUAL_TRIAGE_HOLDOUT_30_20260728.json`。该数据已经参与模型、prompt 和
指标分析，因此从现在起整体降级为开发数据。

使用固定种子 `workspace-grounding-a-prime-dev-v1-20260729`，按是否包含
P1 独立 family review 确认的 grounding positive task 分层：

- calibration：10 个 positive-bearing task + 10 个其余 task；
- internal validation：剩余 5 个 positive-bearing task + 5 个其余 task。

calibration 可用于选择 confidence threshold；internal validation 在运行前
冻结，不能用于调 prompt、reason taxonomy、拒绝策略或阈值。

第三份 holdout 不读取、不重算、不调参。第四份 holdout 暂不生成。

## 3. A′ 输出 contract

每条 rubric 必须输出且只输出一个结构化决定：

- `action`: `route | do_not_route`
- `reason_code`
- `evidence_source`
- `confidence`
- `brief_reason`
- `evidence_quote`

允许路由的 reason code：

- `unsupported_exact_constraint`
- `task_rubric_contradiction`
- `unsupported_prescriptive_content`
- `input_evidence_contradiction`
- `underdetermined_requirement`

强制拒绝的 reason code：

- `task_supported`
- `output_contract_supported`
- `input_supported`
- `mechanically_derivable`
- `intrinsic_validity`
- `general_quality`
- `artifact_satisfaction_only`
- `uncertain_no_specific_gap`

本地 policy fail-closed：

1. `action=route` 但 reason code 不在允许列表，强制 `do_not_route`；
2. reason code 属拒绝列表时，模型无法用 action 绕过；
3. 缺行、重复 index、未知 code、非法 confidence 导致整个 task
   operational unknown，不把遗漏当 clean；
4. router 永远 review-only；只有独立 verifier 才能产生语义 finding。

## 4. 统一成本定义

主口径：

`logical_calls = task_router_calls + routed_candidate_verifier_calls`

其中：

- task-level A/A′ 每处理一个未被 objective resolver 全短路的 task 计 1；
- 每个 routed rubric 假设后接一次 isolated verifier，计 1；
- Exact 等确定性规则计 0 次 LLM logical call；
- provider retry 单列为 `operational_retry_attempts`，不混入语义调用；
- cache hit 仍计 logical call，但 API attempts 为 0。

报告：

- candidate rate；
- logical calls；
- 相对旧 A 的逻辑调用削减；
- logical calls / reviewed-positive rubric hit；
- logical calls / reviewed-positive task hit；
- operational unknown。

## 5. API 预算

模型：`deepseek-v4-flash`，temperature 0，thinking disabled，verifier off。

阶段一：

- calibration 20 次逻辑调用；
- 最多 25 API attempts；
- 软 token 上限 400,000。

只有 calibration 存在满足门槛的 Pareto 工作点，才运行 internal validation：

- 再增加 10 次逻辑调用；
- 全阶段最多 35 API attempts；
- 全阶段软 token 上限 600,000。

不得为了得到正结果调用第二模型或第二视角。

## 6. Pareto 与门槛

只允许在 calibration 上，从预先固定阈值集合
`{0.50, 0.60, 0.70, 0.80, 0.90}` 选择工作点。

calibration go：

- grounding-family routing recall ≥ 0.90；
- candidate rate ≤ 0.40；
- review ceiling escape = 0；
- operational unknown task = 0。

若多个点通过，选择 candidate rate 最低者；并列时选择 recall 最高者；
再并列选择 threshold 最高者。

internal validation gate：

- grounding-family routing recall ≥ 0.85；
- candidate rate ≤ 0.40；
- 相对旧 A 统一逻辑调用削减 ≥ 0.20；
- reviewed precision 与 F1 必须报告，但由于 reference selection bias，
  不作为单独硬门；
- review ceiling escape = 0；
- operational unknown task = 0。

未通过则停止，不生成第四份 holdout。通过也只表示形成了值得外测的冻结
A′，不表示已经泛化。

## 7. 禁止项

- 不读取第三份 holdout 的漏检来改 A′；
- 不在 internal validation 上选阈值；
- 不把 candidate rate 称为已实现的最终成本下降；
- 不把 reviewed precision 称为全量 precision；
- 不因 gate 失败而扩 reason code、放宽 recall 分母或追加模型投票。
