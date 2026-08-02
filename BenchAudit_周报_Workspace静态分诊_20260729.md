# BenchAudit 周报：Workspace 静态 LLM 分诊的两次负结果

> 日期：2026-07-29
> 分支：`research/workspace-a-prime-rejection-20260729` @ `429c3ee`（已推送，local == origin）
> 全量测试：781 passed

---

## 证据分层说明（请先读这一段）

本文所有数字按可信度分三层标注，**不要混用**：

| 层 | 含义 | 标记 |
|---|---|---|
| **层 1｜冻结正式结果** | 预注册协议下真实运行，产物有 SHA256，已被独立复核逐项重算 | 🟢 |
| **层 2｜红队离线重放** | 规则有精确定义，在冻结 cache 上离线重放，未调用 API，但未纳入正式协议 | 🟡 |
| **层 3｜探索性探针** | 红队为可行性评估临时构造，**无代码、无哈希、无测试、未提交**，只用于判断方向 | 🔴 |

层 3 的数字**不得作为实验结论引用**，只用于说明"这条路当前的量级"。

---

## 一句话总结

> 本周重点优化 WorkspaceBench 的静态 LLM 分诊：尝试用零 API 精确规则（Exact router）和结构化拒绝策略（A′）降低调用成本。两种方案都没有形成召回—成本的 Pareto 改进，因此按预注册门槛停止；同时完成了 fail-closed 解析、review-only 天花板、索引校验和早停防护等工程加固，并把下一步的瓶颈定位到"新增约束的类型与证据角色识别"。

---

# 一、🟢 第三份独立 holdout：Exact router 无增量价值

**协议**：`workspace-grounding-third-holdout-v1-20260729`　**任务数**：30　**rubric**：575
**成本**：30 API attempts（上限 40）／183,323 tokens（prompt 182,295 + completion 1,028）／verifier calls 0

## 路由指标（reviewed-reference 条件口径，universe = 48，32 正 / 16 负）

| 路由 | P | R | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| A：DeepSeek 单视角 | 0.667 | 0.812 | 0.732 | 26 | 13 | 6 |
| Exact：零 API | **1.000** | 0.094 | 0.171 | 3 | 0 | 29 |
| A + Exact | 0.667 | 0.812 | 0.732 | 26 | 13 | 6 |

## Exact 相对 A 的增量

| 项目 | 值 |
|---|---:|
| 候选数（A / Exact / 交集 / 并集） | 424 / 20 / 18 / 426 |
| 相对 A 新增候选 | **2**（两条**均无人工标注**） |
| 新增 reviewed TP / FP | 0 / 0 |
| 额外 LLM 调用 | 0 |

**结论**：Exact 找到的 3 条 TP 全部已被 A 覆盖；新增的 2 条落在无标注区，**无法证明增量收益，也不能断言无价值**。预注册 gate 8 项中 2 项 FAIL（`incremental_reviewed_tp_at_least_1`、`incremental_labeled_precision_at_least_0_50`），总裁决 **FAIL**，因此不并入默认流程，Exact 仅保留为诊断/回归探针。

> ⚠️ 必须主动说明：Exact 的 **P=1.000 是已有标签上的条件结果**，不能描述成"全数据集 100% 精确"。

---

# 二、🟢 A′ 结构化拒绝：省约 10% 调用，但召回崩塌

**协议**：`workspace-grounding-a-prime-dev-v1-20260729`　**calibration**：20 task / 405 rubric
**成本**：20 API attempts（上限 25）／162,618 tokens／verifier calls 0／findings 0／operational unknown 0

| 方法 | Candidate rate | Family recall | Reviewed P | Reviewed R | Reviewed F1 | 反事实 logical calls |
|---|---:|---:|---:|---:|---:|---:|
| 旧 A | 211/405 = **52.1%** | 16/19 = **84.2%** | 0.850 | 0.810 | 0.829 | 231 |
| A′ | 188/405 = **46.4%** | 12/19 = **63.2%** | 0.812 | 0.619 | 0.703 | 208 |

- 候选率下降 5.7 个百分点，反事实逻辑调用减少 **9.96%**；
- 但 family recall 下降 **21.0 个百分点**，F1 从 0.829 降到 0.703；
- **不是 Pareto 改进 → 预注册 calibration gate 判定 FAIL**；
- 未运行 10 个 internal-validation task，未生成第四份 holdout。

## 置信度阈值完全失效

五个预注册阈值 `0.50 / 0.60 / 0.70 / 0.80 / 0.90` 给出**完全相同的 188 条候选**。原因不是重放口径错误 —— 被选中的 188 条中最低置信度就是 0.90：

```
全部 405 条：1.00→273  0.95→40  0.90→75  0.80→17
被选中 188 条：1.00→89  0.95→40  0.90→59   (最低 0.90)
```

**模型自报 confidence 高度饱和，不能作为 Pareto 控制量。**

## 结构化 reason 分解（旧 A 无此能力）

| Reason code | 数量 | reviewed TP | reviewed 负例 | 空 quote |
|---|---:|---:|---:|---:|
| unsupported_exact_constraint | 178 | 12 | 2 | 127 |
| input_supported | 75 | 1 | 2 | 1 |
| general_quality | 51 | 1 | 1 | 42 |
| task_supported | 47 | 6 | 0 | 8 |
| artifact_satisfaction_only | 29 | 0 | 1 | 29 |
| output_contract_supported | 11 | 0 | 0 | 0 |
| unsupported_prescriptive_content | 9 | 1 | 1 | 9 |
| intrinsic_validity | 3 | 0 | 0 | 2 |
| mechanically_derivable | 1 | 0 | 0 | 0 |
| input_evidence_contradiction | 1 | 0 | 0 | 0 |

本地 fail-closed policy 在实跑中**真实触发**：模型输出 `action=route` 共 198 条，policy 只接受 188 条 —— 10 条 `route + 拒绝类 reason code` 被强制拒绝。另有确定性窄规则拒绝 10 条（general quality 7 + intrinsic validity 3），在全部 26 条 P1 grounding positive 上离线扫描 **0 误拒**。

> ⚠️ 旧 A 的 response schema 只存 `candidate_indices`，**没有 reason code、evidence source、evidence quote**。因此上表无法对旧 A 生成，也不能声称"分解了旧 A 的 424 条路由原因"。

---

# 三、🟢 七条漏检的根因

A′ 漏掉的 7 条 family-grounding positive：

| item / rubric | A′ 判定 | 模型引用的证据 | 问题 |
|---|---|---|---|
| wb-130 / 19　合并后 PPT 第一张是否来自 panel A | `task_supported` (0.8) | "merge the \`Suppl.Fig.2\` panel-related files" | 只授权"合并"，未授权顺序 |
| wb-157 / 10　是否汇总至少十条用户建议 | `input_supported` (1.0) | 逐条列出 10 条建议 | 素材存在 ≠ 汇总口径被授权 |
| wb-196 / 7　报告是否含六个具名章节 | **`general_quality`** / `intrinsic` / **引文为空** | 无 | 具名枚举被判通用质量 |
| wb-49 / 18　是否生成柱状图 | `task_supported` (1.0) | "create a **visualization chart**" | 上位概念 ≠ 柱状图 |
| wb-9 / 2　是否含柱状/饼/环形三图 | `task_supported` (1.0) | "generate a visual HTML dashboard" | 未提任何图表类型 |
| wb-9 / 8　是否含五类指定建议 | `task_supported` (1.0) | "provide recommendations" | 未提类别 |
| wb-9 / 9　布局是否分五个指定区块 | `task_supported` (1.0) | "generate a visual HTML dashboard" | 未提区块 |

**根因不止一层：**

1. **表层**：模型把"某种设计合理 / 输入中存在素材"误当作"task 授权了 rubric 的精确设计"。
2. **深层（红队发现）**：7 条中 **3 条的 `brief_reason` 与 `reason_code` 直接矛盾** —— 例如 wb-196/7 的 brief 自己写着 "Requires **specific sections**"，却选了 `general_quality`、证据来源标 `intrinsic`、引文留空；wb-9/8 的 brief 写 "general quality requirement"，code 却是 `task_supported`。

> **让 LLM 自行选择 reason code 的结构本身没有形成可靠约束。** 这不是调 confidence threshold 能解决的校准问题。

**敏感性**：wb-9 的三条 `acceptable_families` 含 `subjective_quality_review`，是唯一有解释空间的一组。即使全部剔除，A′ recall 为 12/16 = 75.0%，仍低于 0.90 门槛；旧 A 为 16/16 = 100%，差距反而拉大。**FAIL 裁决对标签争议不敏感。**

---

# 四、🟢 Exact 诊断探针（零 API，不改变裁决）

将冻结 Exact router 与 A′ 在 dev20 上做离线并集：

| Evidence 设定 | Exact 路由 | 相对 A′ 新增 | 并集 candidate rate | 恢复漏检 |
|---|---:|---:|---:|---:|
| 空 input evidence（**路由上界**） | 9 | 3 | 47.2% | **0/7** |
| 真实 input evidence | 6 | **0** | 46.4% | **0/7** |

Exact 的所有条件都是"目标是否**不在** visible evidence 中"，因此扩大 input evidence 只能删除路由原因、不会新增 —— 空 evidence 给出的是**上界**。两种设定下均恢复 0/7。

**结论**：这 7 条漏检不是现有 exact-literal 探针可补的形式缺口，而是"宽泛任务是否授权精确设计"的语义判断错误。

---

# 五、🟡🔴 本地证据一致性规则：能召回，但成本不可接受

**层级说明**：规则一为 🟡（定义精确，离线重放）；规则二为 🔴（红队临时正则，**无代码/哈希/测试，未提交**）。

| 方案 | 层 | 候选 | 候选率 | Family recall | 新增候选 | 新增 reviewed 负例 |
|---|:-:|---:|---:|---:|---:|---:|
| 旧 A | 🟢 | 211 | 52.1% | 16/19 = 84.2% | — | — |
| A′ | 🟢 | 188 | 46.4% | 12/19 = 63.2% | 0 | 0 |
| A′ + 规则一 | 🟡 | 270 | 66.7% | 13/19 = 68.4% | 82 | 2 |
| A′ + 规则二(ANY) | 🔴 | 286 | 70.6% | 17/19 = 89.5% | 98 | 1 |
| A′ + 规则二(ALL) | 🔴 | 305 | 75.3% | 18/19 = 94.7% | 117 | 2 |
| A′ + 规则一+二 | 🔴 | 327 | 80.7% | 18/19 = 94.7% | 139 | 2 |

**🔴 探索性探针中，六条漏检可被纯本地规则召回，但候选率被推到 80.7% —— 比旧 A 的 52.1% 还差 28 个百分点。**

## 两个必须说清的方法论点

**1. reviewed FP 会把成本低估约 70 倍。**
上表"新增 reviewed 负例"只有 +2，看似几乎免费；真实成本是 **+139 条候选**。原因是 reviewed universe 只有 28/405（7%），93% 的新增候选落在无标注区，在 reviewed FP 上完全不显形。
→ **主成本指标必须是 candidate rate / 预计 verifier workload，reviewed FP 只能作次要诊断。**

**2. 空 evidence_quote 不是异常，是常态。**
`artifact_satisfaction_only` 29/29 空、`general_quality` 42/51 空、`unsupported_exact_constraint` 127/178 空。用"空 quote"质疑拒绝等于质疑模型的默认行为 —— 这就是规则一 +82 条只换回 1 条漏检的原因。
→ 规则一**降级为卫生检查**，收窄为「声称正面支持（`task_supported`/`input_supported`/`output_contract_supported`）却给不出引文」，共 **9 条**。它不再承担召回任务。

## 换聚合算子救不了

宽词法路线的边际成本与匹配方式无关：

| 变体 | 新增候选 | 恢复 | 边际成本 |
|---|---:|---:|---:|
| ANY marker 未覆盖（🔴） | 98 | 5/7 | **19.6** |
| ALL marker 须覆盖（🔴） | 117 | 6/7（含 wb-49/18） | **19.5** |

`wb-49/18` 的例子说明了为什么：rubric "bar chart" 与证据 "visualization chart" **共享核心词 chart**，缺的是限制性修饰语 `bar`。问题不在关键词命中与否，而在**是否在已支持的概念上增加了新修饰语**。堆关键词或改聚合逻辑都到不了目标。

---

# 六、🟢 A″ 的定量约束（由 gate 反推）

把 P3 门槛换算成一个可执行的数：

```
候选率 ≤ 52.1%  →  405 × 52.1% = 211 条上限，A′ 已用 188  →  预算仅 23 条
recall ≥ 84.2%  →  16/19，A′ 已有 12               →  须再恢复 4 条
─────────────────────────────────────────────────────────────
必须达到：边际成本 ≤ 23 / 4 = 5.75 候选 / 恢复
🔴 探索性宽规则：          约 19.6                 →  差 3.4 倍
```

> 说明：边际成本的分母只计已知 positive，而 93% 的新增候选无标注，其中可能含真缺陷。因此 🔴 19.6 是探索性探针下的**成本上界 / 收益下界**；但候选率上限是硬约束，不受影响。

## A″ 的四类预注册窄规则（待冻结）

| 规则 | 目标 | 目标漏检 |
|---|---|---|
| **R2a** 未授权顺序约束 | first/last/before/after/排序，仅当 task/contract 明确给出顺序时才可拒绝 | wb-130/19 |
| **R2b** 未授权数量/封闭枚举 | "至少十条""五类" —— input 中存在十个对象不能授权"必须包含十个" | wb-157/10 |
| **R2c** 未授权子类型修饰语 | 共享核心 head + rubric 增加 modifier + modifier 不在 task/contract | wb-49/18, wb-9/2 |
| **R2d** 未授权具名结构 | "生成报告/提供建议"不能授权具体章节与类别清单 | wb-196/7, wb-9/8, wb-9/9 |

配套的 **evidence-role** 定义（本轮最重要的概念产出）：

| 证据来源 | 能证明 | **不能**自动证明 |
|---|---|---|
| task | 输出义务、格式、目标 | 未写出的额外细节 |
| output contract | 文件类型、交付格式 | 内容细节 |
| input | 某事实/数值**存在** | 输出**必须采用**该内容/顺序/数量 |
| artifact | 当前输出是否满足 | rubric 本身是否合法 |
| intrinsic | 通用合法要求 | 当前 artifact 已满足 |

wb-157/10 是典型：**"输入中有十条建议"是描述性证据，"输出必须汇总十条"是规范性义务** —— 两者混淆正是 `input_supported` 误拒的来源。

另需第七类关系 **`derivable_specific`**：rubric 字面更具体但可由 task + input 机械推导（如 task "统计 2024 年全年" / rubric "包含 12 个月份"），**不得判超纲**。纯双向蕴含四分类会漏掉这一类并产生假阳性。

**纪律**：不得针对这 7 条逐个写特例（`if "bar chart"`），那会得到漂亮的 7/7 但没有研究价值。必须先冻结四类规则，再统一运行，不根据结果加例外。

---

# 七、🟢 工程与可复现性加固

| 项目 | 状态 |
|---|---|
| 全量测试 | **781 passed** |
| review ceiling escape | 0 |
| verifier calls | 0（两轮均为 routing-only） |
| operational unknown | 0 |
| 实验产物哈希 | 修复前后**逐字节未变** |
| 独立重算 | 红队重跑 analyzer，输出与原始 `analysis.json` **完全一致** |

## 红队复核发现并已修复的 4 个问题

| # | 问题 | 影响已报告数字？ | 修复 |
|---|---|:-:|---|
| B1 | `rubric_index` 类型不严格，`int()` 静默接受 `true`/`1.9`/`"1"`，可造成索引错位 | 否（cache 中 405/405 均为严格 int） | 只接受字面 JSON integer；对抗构造全部 fail-closed |
| B2 | Exact 诊断的 9/+3/47.2% 是零证据**上界**，被当作操作值 | 否（不涉 A′ 主指标） | 改为双行表，补真实证据下的 6/+0/46.4% |
| B3 | `--grounding-routing-only` 不结构性保证零 substantive finding（objective resolver 短路路径可绕过） | 否（本轮短路 0 条） | verifier 关闭时结构性禁止全部 substantive finding |
| B4 | 配置硬闸设在阶段二的 35/600k，阶段一 25/400k 只靠人工纪律 | 否（实跑 20/162,618） | 拆分阶段专用配置：25/400k 与 10/200k |

## 当前双重防线

1. `verify_unsupported` 未开启时，**禁止一切 substantive finding**（含 objective resolver 短路），operational failure 仍正常上报；
2. routing-only 决定在 verifier 缺席时禁止升级为实质结论（为未来预算早停/部分验证预留）。

所有 LLM 路由结果仍只能是 **review**，`confirmed` 结构性不可达。

---

# 八、🟢 本周的研究认识

1. **继续扩大候选解决不了问题。** 双视角与 Exact router 都没有带来增量已知 TP。
2. **简单压缩候选也不行。** A′ 省约 10% 调用，却错误拒绝了 1/3 的已知真问题。
3. **瓶颈不在 confidence 阈值。** 五个阈值给出完全相同的 188 条候选，模型自报置信度高度饱和。
4. **瓶颈在结构化判断本身。** 7 条漏检中 3 条出现 `brief_reason` 与 `reason_code` 自相矛盾 —— 结构化 JSON ≠ 结构化推理。
5. **本地规则能找到漏检，但当前形式代价过高。** 🔴 探索性探针中 6/7 可召回，代价是候选率 46.4% → 80.7%；且换聚合算子无效（19.6 vs 19.5）。
6. **更合理的分工是"LLM 提出语义关系，程序独立核验并交叉检查"** —— 注意**不是**"程序完成全部裁决"，蕴含方向本身仍是模型判断，只能保持 review。这与输出文件名检测的成功设计一致：LLM 提取语义对象，本地代码负责可重放比较。

---

# 九、必须主动说明的边界

上台时主动说出，避免被追问时被动：

- **Candidate rate 只是 verifier 成本代理**，不是已实现的端到端费用下降；本轮为离线重放，未产生额外 verifier API 调用，但进入默认 pipeline 后将成为预计负担。
- **Reviewed P/R/F1 只在已有标注子集上计算**（dev20 为 28/405，第三份 holdout 为 48/575），不代表完整 388 题的绝对性能。
- **Family recall 同样是条件 recall。** 分母来自 dev30 中被前一轮 Codex 复核标为"较可信真问题"的 30 条，而该复核的输入是更早一轮的 559 条候选清单。偏差可量化且不严重（30 条中旧 A 只路由了 24 条，说明 universe 不是旧 A 候选的子集），但仍不能外推为全库 recall。
- **A′ 是负结果，但属于有效负结果**：协议先冻结、阈值集预注册、gate 失败后真的停手，没有继续在 holdout 上调参，没有追加第二模型或第二视角。
- **今晚不追加 API 实验**，避免未经复核的临时结果进入汇报。
- **第四份 holdout 未生成是有意停止，不是遗漏。**

---

# 十、8 页汇报提纲

| 页 | 内容 | 核心数字 |
|---|---|---|
| 1 | 最终目标与本周具体问题 | 目标须重述为可实现版本（见附录 A） |
| 2 | Workspace 静态 LLM 分诊流程 | 路由 → 隔离验证 → 分级裁决 |
| 3 | 本周实现：Exact router 与 A′ | 零 API 精确规则 + 结构化拒绝 schema |
| 4 | 第三份 holdout 结果 | A 0.667/0.812/0.732；Exact 增量 TP = 0 |
| 5 | **A′ 成本—召回结果（最重要一张表）** | 52.1%→46.4% vs 84.2%→63.2%，−9.96% 调用 |
| 6 | 独立红队复核与工程加固 | 781 tests，4 个问题已修，哈希未变 |
| 7 | 本周研究认识 | reason_code 与 brief_reason 自相矛盾 |
| 8 | 下一步 A″：约束残差 × 证据角色 | **🟢 允许值 ≤5.75；🔴 探索性探针约 19.6** |

---

# 十一、高频问答准备

**Q：候选率到底是 52.1% 还是 73.7%？**
A：同一个旧 A，在 dev20 上 52.1%，在第三份 holdout 上 73.7% —— 不同任务集。73.7% 正是启动 A′ 的动机。两张表分母不同，不可直接相比。

**Q：Exact 的 P=1.000 是不是说明它很准？**
A：只在已有标签上成立，且 R 仅 0.094。它找到的 3 条 TP 全部已被 A 覆盖，新增的 2 条无人标注。所以是"无法证明增量收益"，不是"证明了无价值"。

**Q：A′ 失败了，这周是不是白做了？**
A：排除了两个看似合理的方向，并把瓶颈定位到具体机制（reason code 与证据无强制一致性）。同时产出了旧 A 不具备的结构化可观测性 —— 上面那张 reason 分解表在旧 schema 下根本无法生成。

**Q：为什么不多调一个模型投票？**
A：协议第 7 条明确禁止"为了得到正结果追加模型投票"。且根因是判断结构问题，不是采样方差。

**Q：那 6/7 恢复是不是好消息？**
A：召回是好消息，成本不是。🔴 探索性探针的候选率为 80.7%，比基线 52.1% 还差；这不是冻结实验结果。

**Q：双重防线拦住过什么？**
A：**都没有触发过**，这是设计意图。第二道在当前代码路径下不可达，是为将来加预算早停时预留的。

**Q：怎么保证没有偷跑 internal validation？**
A：10 个 IV item id 在全部 diff 中只出现在两份 manifest，calibration 产物目录零命中，第三份 holdout 在 A′ diff 中零引用，产物哈希可复核。

---

# 十二、已核实的论文引用

| 论文 | 核实状态 | 可用表述 |
|---|---|---|
| [Fantastic Bugs in AI Benchmarks](https://arxiv.org/abs/2511.16842) | ✅ 已核实正文 | "在审查排名前 50 个候选的设置下，专家确认的 Precision@50 最高为 84%（GSM8K）"；论文明确定位为**辅助专家复核**，非自动确认 |
| [RULERS / From Rubrics to Reliable Scores](https://arxiv.org/abs/2601.08654) | ✅ 已核实 | 将 rubric 编译为 locked specifications，结构化 checklist + evidence grounding。**预印本**，结论谨慎看待 |
| [LGMT](https://arxiv.org/abs/2605.23965) | ✅ 已核实 | 由一阶逻辑等价关系导出 metamorphic relations，以跨样本一致性代替绝对 oracle |
| [OpenAI SWE-Bench Pro audit](https://openai.com/index/separating-signal-from-noise-coding-evaluations/) | ✅ 已核实 | 自动管线标记 200/731 = 27.4%，人工识别 249/731 = 34.1%，类别重合 74%，每题五名工程师独立复核 |
| [Judging LLM-as-a-Judge](https://openreview.net/pdf?id=jBcsGPKNeV) | ✅ PDF 可读 | 仅用 rubric 文本即可高于随机地预测 judge label，部分设置超过 0.8 → rubric 文本可能携带 shortcut signal。**2026 ACL ARR 匿名投稿，不可称已接收** |
| Auditing by Re-Solving | ⚠️ **待核** | OpenReview 条目存在，但当前未完成全文独立核验。**今晚不展示任何具体数字**；即便其结论成立，也只支持"不要让 auditor 重新求解复杂任务"，不能证明"抽取—裁决分离一定更好" |

---

# 附录 A：最终目标的现实化表述

"任意 benchmark 全自动修好所有错误"在存在主观 rubric、歧义和不可观测意图时不可实现。更可行也足够强的目标是：

> 给定任意 benchmark 的 task、data、rubric/evaluator 和已有运行结果，自动建立组件与证据关系；高召回生成缺陷候选；对可重放缺陷自动确认；对主观或证据不足的问题**主动弃权**；生成修复建议，并在存在 verifier 时自动完成回归验证。

当前已完成该目标的大部分工程骨架。下一次真正可能带来方法进步的，不是多调用一个模型，而是把"自然语言要求是否被支持"从一个整体 LLM 判断，变成**可引用、可比较、可测试的关系契约**。

---

# 附录 B：产物哈希

**A′ calibration**（`reports/workspace_grounding_a_prime_calibration_20260729/`）

```
689fad58c3947109b3547561681d3fa258ecbc7ded9ec94cfb7751d2ec061c1a  ..._items.jsonl
53740726724c1a58e200245a3795ca243c2573ec49aa1ce838b1f7d7b39fc6e4  ..._cache.jsonl
8f307d1d906cc8729462405bb4667cada0f90236c9984c53ade213f182ceee63  runtime.json
fee5a065173851bb5597af5994e3beee9408bf40aaa0b9d62854d617d5434147  analysis.json
```

**第三份 holdout**（`reports/workspace_grounding_third_holdout_20260729/`）

```
cb8110f33982ebacd92c6ea84913cc9229d6b74cd19d8dafd6951fae2c2e1a98  ..._items.jsonl
0cef0c5c1a3c73a179a91d7f1edbf53c0b0a434ba366adf8b2f5073225523743  analysis.json
```

**代码**：`research/workspace-a-prime-rejection-20260729` @ `429c3ee`（已推送，local == origin，0 ahead / 0 behind）

---

# 附录 C：今晚可直接使用的结论段

> 🟢 冻结结果显示，A′ 相比旧 A 将候选率从 52.1% 降至 46.4%，但 family recall 从 84.2% 降至 63.2%。由正式 gate 可推导：若要同时不劣于旧 A，每恢复一条已知漏检最多只能增加 5.75 条候选。🔴 红队探索性探针进一步显示，宽词法规则可重新召回七条已知漏检中的六条，但候选率会升至 80.7%，观察到的边际成本约为 19.6；将匹配聚合方式由 ANY 改为 ALL 后仍约为 19.5。该探针没有代码、哈希和测试，只用于说明宽词法路线目前距离正式 gate 约差 3.4 倍。下一步将把约束拆成顺序、数量、子类型和具名结构四类预注册规则，只接受候选率与召回同时不劣于旧 A 的方案。

（引用时请注明：80.7% / 19.6 / 19.5 属于红队探索性探针 🔴，非冻结实验结果。）
