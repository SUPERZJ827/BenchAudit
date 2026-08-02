# SVAMP 三臂 × 三跑消融协议

> 日期：2026-08-02  
> 状态：**design frozen; no arm run has started**  
> 目的：在已测运行噪声下，比较当前实现、结构性收紧与三票聚合  
> 执行状态：因准确成本预估高于原先的 ¥13，本协议冻结后等待单独预算确认

## 0. 问题与选择偏差声明

已知同代码同配置的 SVAMP n=5 运行仍有实质波动：violation-Jaccard 中心值约 `0.845`，F1 极差 `0.046`。因此单跑三臂不可归因；每臂必须有 3 次独立运行并报告分布。

本协议比较：

1. 当前实现；
2. 对 `llm_gold_audit` 与 `llm_question_clarity` 施加同 item 独立方法佐证门；
3. 保持当前触发逻辑但把每次 LLM 判断改为 3 票。

不采用“抑制仅 `*_nonmaterial` 触发的 item”作为收紧臂，因为该规则是在观察 2026-07-30 数据中“删 2 FP、零 TP 损失”后提出，若直接用于本样本会有结果驱动的选择偏差。该观察可作为未来独立 holdout 协议的假设，不能在当前 SVAMP-100 上当作未拟合消融。

## 1. 冻结公共条件

| 项 | 值 |
|---|---|
| 输入 | `/home/zhoujun/llmdata/datasets/svamp_platinum/svamp_platinum_all.jsonl` |
| 输入 SHA-256 | `f27f8ebf56b33fbeea4b6430f63f24c66adb37bd38a1a8b2bbe62960f588063e` |
| manifest | `experiments/svamp_platinum_pilot100.manifest.json` |
| manifest SHA-256 | `c4ef5ddfb590b210243c0114d7d9eed7a15c2c0a1cf14a98f763cb7d4992d861` |
| 样本 | 100 条；真值 `metadata.audit_label`，clean 值 `clean`，已知 positive 38 条 |
| 模型 | `deepseek-v4-flash` |
| temperature | `0.0` |
| thinking | `disabled` |
| max_tokens | `5000` |
| auditors | `gold,question,quantity,event` |
| gold evidence | `cascade` |
| workers | `8`，必须进入 run_metadata |
| 每臂运行数 | `3` |
| 总运行数 | `9`，全部串行 |
| 实验级补跑 | **0 次**；失败槽位保留为失败，不另开缓存替换 |
| 缓存 | 9 个各自独立、运行前不存在的空缓存；禁止跨运行复用 |
| 远端传输 | 显式授权，使用已测试的 HTTPS CONNECT transport |

任何 arm-specific 代码、配置与 runner 必须在首个付费调用前另行提交，运行时使用固定 detached commit；本协议不预先声称尚未实现的 arm 已可运行。

## 2. 三臂的可执行定义

### Arm C：current

- `n_votes = 1`；
- 当前 raw violation 与 candidate 生成逻辑不变；
- 不额外过滤 `llm_gold_audit`、`llm_question_clarity`。

### Arm T：tightened-by-independent-corroboration

- LLM 调用配置与 Arm C 相同，`n_votes = 1`；
- raw report 必须完整保留，不删除 finding；
- 仅在形成 candidate item 集时增加以下确定性 overlay：
  - `llm_gold_audit` finding 只有在同一 item 还存在至少一个**不同 primary family** 的 substantive finding 时，才能独立贡献 candidate；
  - `llm_question_clarity` 同理；
  - 若 item 还有不受本门影响的 substantive finding，该 item 仍是 candidate。

primary family 由 detection method 的闭集映射得到：

| detection method | family | 可作佐证 |
|---|---|---|
| `llm_gold_audit` | `gold` | 是，但不能佐证自身 |
| `llm_question_clarity` | `question` | 是，但不能佐证自身 |
| `llm_quantity_consistency` | `quantity_material` | 是 |
| `llm_event_state` | `event_material` | 是 |
| `cross_artifact_consistency` | `cross_artifact` | 是 |
| `static_rule` | `static` | 是 |

下列方法明确**不能**作佐证：

- `llm_quantity_consistency_nonmaterial`；
- `llm_event_state_nonmaterial`；
- `llm_evidence_fusion`（它由其他 finding 派生，不独立）；
- operational / presentation finding；
- 未列入上表的方法。未知方法 fail-closed 为“不可佐证”，不得在运行后扩表。

若同一 item 同时有 `gold` 与 `question`，二者可互为不同 primary family 的佐证。这一规则只检查 method family 与 item identity，不读取 confidence、真值标签或 item ID 特例。

### Arm V：vote-3

- candidate 逻辑与 Arm C 相同；
- `n_votes = 3`；
- `vote_temperature = 0.3`；
- 每个 vote 的 cache key 必须含 vote index；
- 三票的现有聚合代码不修改，不对单个 auditor 另设票数。

## 3. 顺序与独立性

为降低时间漂移与固定顺序的混淆，9 次运行按以下 Latin-style 顺序串行：

1. round 1：C → T → V
2. round 2：T → V → C
3. round 3：V → C → T

每次均使用新缓存。不得因为某一臂结果异常而交换后续次序、补跑或复用别臂缓存。传输失败可按客户端冻结的**单请求 retry** 策略处理；超出 retry 后该 run 记 operational failure，不私下重开同一槽位。实验级允许重跑次数严格为 0，因此不存在“多跑一次再挑一份”的自由度。

## 4. 冻结指标

完全沿用 `SVAMP_REPLICATION_N5_PROTOCOL_20260802.md` §2：

1. 预测 item = 至少一条 `defect_scope != "presentation"` 的 eligible violation；Arm T 的 eligible 按 §2 overlay 计算；
2. finding 键 = `(item_id, detection_method, defect_type)`；
3. 每臂三次的候选 TP / FP / FN / precision / recall / F1 分布：逐值、min、median、max、极差；
4. 每臂 3 个内部 pair 的 item Jaccard 与 violation Jaccard；
5. 每臂逐 detection method 的 3 个 pair Jaccard，并报 min/mean/max；
6. 每 round 的 T−C、V−C 差值：TP、FP、FN、F1；
7. API attempts、provider tokens、cache hits、operational failure、elapsed time。

不得运行后增加仅对某一臂有利的新指标或改 finding identity。

## 5. 预注册解释规则

把已观测同配置 F1 极差 `0.046` 当作保守噪声带，而不是显著性检验：

- 某实验臂相对 C 被称为“实际改善”，必须同时满足：
  1. median F1 增益 **> 0.046**；
  2. median FP 至少减少 3；
  3. median TP 相对 C 最多减少 1；
- 若只改善其中一部分，写 `INCONCLUSIVE_TRADEOFF`；
- 若 median F1 增益不超过 `0.046`，不得声称胜过已测运行噪声；
- 稳定性改善单独报告，不与准确率改善混为一项：只有内部 pair 的 median violation-Jaccard 高于 C 才能称为更稳定。

n=3 只提供开发诊断，不构成一般化证据，不做显著性检验。

## 6. 成本重算与启动门

旧 SVAMP 单票运行约 635 API attempts、约 ¥1.4。Arm C 与 T 各 3 跑约等于 6 个单票运行；Arm V 的 3 跑、每跑 3 票，约等于 9 个单票运行。总负载约等于 **15 个单票运行**：

- 预期费用约 `15 × ¥1.4 = ¥21`；
- 建议硬预算 ¥30；
- 预期 API attempts 约 `9,525`。

因此先前“9 次 ≈ ¥13”的估算没有计入 vote-3 的三倍调用，不能作为授权依据。**本协议冻结不等于授权开跑**；只有用户明确接受修正后的约 ¥21 预期 / ¥30 上限后才能启动。

如果预算不能提高，不得把 vote-3 静默改为 vote-2、只给部分 auditor 投票或减少重复数；应另冻低预算协议。

## 7. 硬停止条件

1. 任一 run operational failure > 5%；
2. 任一 run 出现 LLM 派生 confirmed；
3. 方法集、workers、模型语义配置或缓存独立性不符；
4. 累计费用达到授权硬上限，或 provider tokens 达预注册上限；
5. Arm T 实现使用真值标签、item ID、confidence threshold、未列入的 supporter 或修改 raw finding；
6. Arm V 实际票数不为 3 或 cache key 未区分 vote index。

停止后保留已完成运行，不补齐成看起来对称的数据。

## 8. 完成线

只有以下全部满足才算实验完成：

- 协议先于所有付费调用；
- 三臂实现有构造性测试，特别覆盖 T 的“无佐证过滤 / 有佐证保留 / 非目标 finding 不受影响 / nonmaterial 不可佐证”；
- 9 个独立缓存、9 份 report、9 份 comparison 与 1 份汇总均有 SHA-256；
- 指标严格来自 §4；
- 结论按 §5，不用单次最好值代替分布；
- 报告明确披露本协议在同一 SVAMP-100 开发样本上评估，不是新 holdout。
