# 级联切断消融协议（full vs normalized，各 n=5）

> 日期：2026-08-03
> 状态：**frozen before any paid API request**
> 执行：Claude
> 授权预算：用户批准 ¥20 上限；本实验预计 ¥12.8

## 0. 待检验的因果主张

> 审计器逐条 finding 的不可复现性，其放大机制是**答案依赖的 prompt 级联**：盲解的自由文本被嵌入下游 prompt，温度 0 下的措辞漂移因此扇出成不同的下游调用。

**干预**：`normalized` 模式只把门控真正读取的结构字段嵌入下游，并把 confidence 桶化到门的哪一侧，剥除 `rationale` / `claims` / `required_assumptions`。

## 1. 预注册预测（运行前写定）

| 结局 | 判据 |
|---|---|
| **机制成立** | `normalized` 的 violation-Jaccard 均值 **高于** `full`，且差值 **超出** 两臂各自的臂内跨度 |
| **机制不成立** | 差值落在臂内跨度之内，或方向相反 |

**若不成立，本项目的因果主张即被证伪，须如实记录，不得改口径重算。**

## 2. 冻结的执行条件

| 项 | 值 |
|---|---|
| 代码 | commit `67ce836`，工作树须干净 |
| 输入 | `/home/zhoujun/llmdata/datasets/svamp_platinum/svamp_platinum_all.jsonl` |
| 输入 SHA-256 | `f27f8ebf56b33fbeea4b6430f63f24c66adb37bd38a1a8b2bbe62960f588063e` |
| manifest | `experiments/svamp_platinum_pilot100.manifest.json`，SHA-256 `c4ef5ddfb590b210243c0114d7d9eed7a15c2c0a1cf14a98f763cb7d4992d861` |
| 模型 / 温度 / votes / thinking / max_tokens | `deepseek-v4-flash` / 0.0 / 1 / disabled / 5000 |
| `--workers` | 8 |
| auditors | `gold,question,quantity,event`，`--gold-evidence-mode cascade` |
| 臂 | `--cascade-mode full` ×5，`--cascade-mode normalized` ×5 |
| 缓存 | **每次运行各自独立空缓存**，共 10 个 |

两臂**调用次数结构相同**（只改 prompt 内容不改分支），因此无需控预算即可比较。

## 3. 冻结的度量口径

沿用 `SVAMP_REPLICATION_N5_PROTOCOL_20260803.md` §2，不新造：

- 预测项 = 至少一条 `defect_scope != "presentation"` 的 violation 的 item；
- finding 身份键 = `(item_id, detection_method, defect_type)`；
- 复现率 = Jaccard；每臂 10 个配对，报均值与 min–max；
- 逐 detection_method 复现率；
- **代价指标**：两臂的候选层 P/R/F1（对 `metadata.audit_label`）——切断级联可能同时削掉覆盖，**这个代价必须报告，不得只报复现率**。

## 4. 预算与停止条件

| 项 | 上限 |
|---|---|
| 总花费 | **¥20**（预计 ¥12.8） |
| 总 token | 12,000,000 |

任一情况立即停止并如实报告：

1. 任一运行 operational failure > 5%；
2. 出现任何 LLM 派生的 `confirmed`（review 天花板逃逸）；
3. 累计 token 超限；
4. 两臂的 `decision_policy.sha256` 不是预期的 `8ca41956…`（full）/ `ada0b5cb…`（normalized）。

**不允许**：因结果不理想而追加运行、换数据集、改模式定义、调阈值。

## 5. 边界

- SVAMP-100 是开发数据，本实验测的是**仪器属性**（复现性），不是泛化性能，因此不受 blind-holdout 约束；
- n=5 给跨度不给总体方差；
- 只覆盖内容扇出，**不覆盖门控扇出**（`ungated` 臂未做，成本 3 倍且倍数未测）。
