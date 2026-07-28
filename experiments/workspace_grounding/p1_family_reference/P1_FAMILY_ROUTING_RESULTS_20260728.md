# Workspace grounding P1：完整 family-conditioned routing 结果

日期：2026-07-28  
协议：`workspace-grounding-p1-family-reference-v1-20260728`  
模型：`google/gemini-3.1-pro-preview`

## 1. 执行完整性

- 对冻结 holdout 中全部 30 条既有 reviewed-positive 对称重标；
- 18 个 task 级独立上下文；
- blind package 不包含 item id、reviewed label、A/B/union 状态或 verifier
  verdict；
- 30 个 blind id 和 evidence quote 全部通过本地校验；
- sealed mapping 在标注结果与回执提交后才揭示；
- 18 个逻辑 task 请求，因首轮严格格式失败共有 29 次实际 API 请求；
- 输入 145,799 tokens，输出 47,320 tokens，总计 193,119 tokens；
- OpenRouter 实际费用：`$0.859438`；
- 标注 SHA256：
  `cf88ac639d74d7b1bd98d350199b7de3335d8639086107b58aa9cd762c74e1c7`。

格式失败没有被静默放行。执行器增加了 evidence source JSON Schema 和断点续跑，
16 个已校验 task 直接复用，只重新调用 2 个失败 task。

## 2. 30 条 reference 的重新判定

| 独立 verdict | 数量 |
|---|---:|
| yes | 28 |
| no | 1 |
| uncertain | 1 |

独立模型支持 28/30 个旧 reviewed-positive。两个排除项：

- `workspacebench-74 / rubric 8`：输入文件已经明确给出 Chapter 3 及对应审批、
  补贴和责任内容，因此判为 `task_or_input_derived / no`；
- `workspacebench-198 / rubric 7`：允许证据中相关 PPT 页面被截断、图片无法解析，
  无法判断要求是否有来源，因此保留 `insufficient_evidence / uncertain`。

28 个 yes 的主责任：

| primary family | 数量 |
|---|---:|
| workspace_rubric_grounding | 26 |
| task_contract | 2 |

## 3. 正式 family-conditioned routing recall

本轮 `primary_grounding` 与 `acceptable_grounding` 的分母恰好相同，均为 26。

| 路由 | 旧混合口径（30） | family-conditioned（26） | 变化 |
|---|---:|---:|---:|
| A：hidden constraint | 24/30 = 80.0% | 22/26 = 84.6% | +4.6 pp |
| B：support challenge | 25/30 = 83.3% | 23/26 = 88.5% | +5.1 pp |
| A∪B | 26/30 = 86.7% | 24/26 = 92.3% | +5.6 pp |

结论比 P0 的漏检侧推断更保守，也更可信：

- 清理 detector-family 分母后，三种路由 recall 都提高；
- 但 A∪B 仍只有 92.3%，没有达到预注册的 95% gate；
- 因此不能声称双视角已经解决 grounding routing recall。

## 4. 剩余漏检

A∪B 剩余两个 item-rubric FN：

- `workspacebench-223 / rubric 2`
- `workspacebench-223 / rubric 3`

两条属于同一个 root cause：rubric 强制使用精确中文列名，而 task 只指定对应
英文列名。item-rubric 口径是 2 个 FN；one-fix/root-cause 口径是 1 个漏检
家族。

这正好支持下一步的可解释 exact-constraint router：

- quoted/exact column header；
- task 与 rubric 的 literal mismatch；
- section/filename/count/order 等窄约束。

但该规则是在看过这份 holdout 后提出的，所以只能把当前 30 题当开发数据。
实现后必须在第三份 task-disjoint holdout 上验证，不能在本数据上补到 100%
再声称泛化提升。

## 5. P0→P1 重复一致性

四条 P0 漏检案例在 P1 被重新独立请求：

| 字段 | 一致 |
|---|---:|
| is_grounding_defect | 4/4 |
| grounding_class | 4/4 |
| evaluation_objectivity | 4/4 |
| satisfaction_checkability | 3/4 |
| primary_family | 2/4 |

两条 `workspacebench-223` 的 defect verdict 和
`hidden_exact_constraint` 类别完全稳定，但 primary family 从 P0 的
`task_contract` 变为 P1 的 `workspace_rubric_grounding`。

这说明：

1. “是否存在隐藏精确约束”比“由哪个 detector 负责”稳定；
2. family assignment 仍受 prompt/context 影响；
3. 需要 GroundingDecisionContract 明确：
   - 缺少 rubric literal 来源 → grounding；
   - task/output contract 自相矛盾 → task_contract；
   - 当前 artifact 是否满足 → artifact_execution；
   - 多 family 只在同一根因确实可由多个 detector 合法发现时使用。

## 6. 能站住的结论

1. 旧的 86.7% 确实混入了其他 family 和一条非缺陷、一条不确定案例；
2. 对称重标后的 A∪B grounding recall 是 **92.3%**，较旧口径提高
   **5.6 个百分点**；
3. 92.3% 仍未达到 95% gate，结果是“有改进但未达标”；
4. 剩余两个 FN 集中在一个精确字面约束根因，为 cheap exact router 提供了
   明确设计目标；
5. family 标签自身不够稳定，P2 GroundingDecisionContract 必须先于第三份
   holdout；
6. 本轮全部输出仍是 review-only，不会产生 confirmed promotion。

## 7. 下一步顺序

1. 用 P0/P1 一致案例和冲突案例冻结 `GroundingDecisionContract v1`；
2. 实现输出触发原因的 exact-constraint router：
   `quoted_literal / filename / column_header / section_name / exact_count /
   ordering / literal_mismatch`；
3. 只在当前数据上做单元测试和开发，不报告新性能；
4. 冻结 contract、规则和指标；
5. 生成第三份 task-disjoint holdout；
6. 比较 A、A+exact、A∪B，并报告 recall、precision、增量调用/TP 和
   review-only 安全门。

