# Workspace grounding P0 独立盲审结果

日期：2026-07-28  
协议：`workspace-grounding-p0-adjudication-v1.1-20260728`  
独立模型：`google/gemini-3.1-pro-preview`

## 1. 执行与完整性

- 26 个 task 级独立请求，对应 37 条 rubric；
- 每个请求均为全新上下文，不共享历史；
- 26/26 一次通过，无格式重试；
- API 返回模型均为冻结模型；
- 37 个 blind id 完整、无重复；
- 所有 evidence quote 均通过本地逐字匹配；
- sealed mapping 在独立结果落盘并提交回执后才揭示；
- 输入 139,876 tokens，输出 38,504 tokens，总计 178,380 tokens；
- OpenRouter 实际记录费用：`$0.7418`；
- 标注 SHA256：
  `b091fae11b9ecbd2bffc826c4cf60615e15c39357b700abdf3c9510daa3b8e62`。

这是一份合格的跨模型独立盲审，但仍是 model-reviewed reference，不是人工
gold。

## 2. 37 条结果

| 来源分层 | n | 独立模型 yes | no | uncertain |
|---|---:|---:|---:|---:|
| B-only、原 verifier 判 unsupported | 13 | 6 | 6 | 1 |
| B-only、原 verifier 判 supported 的对照 | 10 | 1 | 9 | 0 |
| B-only、原 verifier 判 uncertain 的对照 | 10 | 4 | 6 | 0 |
| 两个 triage 均漏掉的既有 reviewed-positive | 4 | 3 | 1 | 0 |

### B-only unsupported 的真实含义

13 条是此前没有 reference label 的全部 B-only final-unsupported：

- 6/13 被独立模型判断为真实缺陷；
- 6/13 被判断为非缺陷；
- 1/13 证据不足；
- 若只看 yes/no，独立模型 positive rate 为 6/12 = 50.0%；
- 6 个 yes 中，5 个主归因于 `workspace_rubric_grounding`，1 个属于
  `task_contract`。

因此，第二视角 B 确实补到了旧标签未覆盖的潜在真问题，但原 verifier 对
intrinsic validity、通用质量要求和 task/input-derived 要求存在明显过判。
这不支持把全量 B 设为默认路由。

## 3. 调用成本与增量收益

全量双视角相对 A 增加 206 次逻辑调用：

- 按 6 个独立模型 positive 计：34.3 次新增调用/positive；
- 按两位审阅者一致的 2 个 positive 计：103 次新增调用/一致 positive。

这些 positive 仍然是 review 证据，不是 confirmed defect。因此最诚实的结论
是：

> 全量 B 有召回价值，但成本较高、精度不稳定，继续保留为实验上界，不进入
> 默认流程。

## 4. 四条“grounding 漏检”的责任边界

独立模型对四条旧 reviewed-positive 的判断：

| item | rubric | verdict | primary family |
|---|---:|---|---|
| workspacebench-74 | 8 | no | workspace_rubric_grounding |
| workspacebench-223 | 2 | yes | task_contract |
| workspacebench-186 | 21 | yes | task_contract |
| workspacebench-223 | 3 | yes | task_contract |

这验证了旧的 86.7% grounding routing recall 混入了其他 detector family：
四条中三条真实问题的主责任均是 `task_contract`，另一条被独立模型判为非
grounding defect。

因此，旧的 26/30 = 86.7% 不能继续作为 grounding router 的正式 recall。
本轮只重新标了四条漏检，没有重新标 26 条已路由 positive 的 detector family，
所以现在也不能诚实地给出 A、B 的完整 family-conditioned recall。

目前只能给两个边界事实：

1. 按 `primary_family`，四条旧漏检中没有 grounding-family positive；因此在
   已检查的漏检侧，A∪B 没有剩余的 primary-grounding FN。
2. 按更宽的 `acceptable_families`，`workspacebench-186/rubric-21` 仍允许
   grounding detector 发现，所以至少保留 1 个跨 family FN。若暂时假设 26
   条已路由 positive 均仍属于 grounding 可接受分母，A∪B 的条件性估计是
   26/27 = 96.3%；但这不是最终 P1 指标。

正式重评分必须在 P1 中给 30 条 reference 全部补齐
`primary_family + acceptable_families`，再分别计算 A、B 和 A∪B。这样不会用
“只重新标漏检、不重新标命中”的不对称口径虚增 recall。

## 5. 跨审阅者一致性

独立 Gemini 与非盲 Codex evidence review：

| 字段 | 一致率 |
|---|---:|
| grounding defect yes/no/uncertain | 26/37 = 70.3% |
| grounding class | 23/37 = 62.2% |
| evaluation objectivity | 30/37 = 81.1% |
| satisfaction checkability | 15/37 = 40.5% |
| primary detector family | 18/37 = 48.6% |

grounding verdict 的 Cohen's κ = 0.389。

在 13 条 B-only unsupported 中：

- 2 条两位审阅者一致为 yes；
- 5 条一致为 no；
- 5 条 verdict 冲突；
- 1 条一致为 uncertain。

这意味着不能把 6/13 直接写成硬 precision。更重要的发现是：判定契约在
“requirement 是否合理”“当前 artifact 如何检查”“由哪个 detector 负责”
三件事之间仍有明显语义漂移。

## 6. 本轮能站住的结论

1. **第二视角不是零增益。** 独立模型在 13 条新增 unsupported 中判断出
   6 条潜在真缺陷，其中 5 条属于 rubric grounding。
2. **全量第二视角仍不适合作为默认策略。** 独立模型同时否定 6 条，且每个
   跨审阅一致 positive 需要 103 次新增逻辑调用。
3. **旧 routing recall 的分母不干净。** 三个旧漏检主要属于
   `task_contract`；漏检侧重评分表明 86.7% 明显低估了 grounding 路由，
   但 30 条 reference 尚未全部补齐 family 标签，不能提前宣称最终提升值。
4. **真正瓶颈是 GroundingDecisionContract。** 低 κ、低 family/checkability
   一致率表明，继续堆第二个 prompt 不如先统一标签定义和责任转交规则。
5. **所有相关结果仍保持 review-only。** 本轮没有产生任何 confirmed
   promotion。

## 7. 下一步

P0 最小收尾是只人工复核关键未决项，而不是重审 37 条：

- 13 条 unsupported 中的 5 条 verdict 冲突和 1 条共同 uncertain；
- 4 条旧漏检中的 2 条 verdict 冲突；
- 共 8 条重点案例。

若暂时没有人工力量，则保留上下界和 conflict，不强造 gold。随后可以使用
一致案例建立 `GroundingDecisionContract v1`，明确：

1. grounding status；
2. requirement kind；
3. evaluation objectivity；
4. satisfaction checkability；
5. primary/acceptable detector families；
6. intrinsic/general/task-derived 的确定性短路；
7. task-contract 冲突的转交规则。

完成 contract 和回归集后，再实现可解释的 exact-constraint 静态 router，并
在第三份 task-disjoint holdout 上验证；不要继续在当前 30 题上调参并重复报告
提升。
