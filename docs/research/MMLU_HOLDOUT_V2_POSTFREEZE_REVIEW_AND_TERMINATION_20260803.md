# MMLU holdout V2：冻结后复核、目标更正与终止记录

> Date: 2026-08-03  
> Status: **STOP_DETECTION_HOLDOUT_ZERO_POSITIVES**  
> Scope: aggregate-label audit only; no candidate text was inspected or emitted  
> Implementation started: **false**  
> Holdout manifest produced: **false**  
> API/network use: **zero**

## 0. 本记录的性质

本文件是冻结后的复核记录，不修改、覆盖或重解释已冻结的 V2 文档。
V2 与其 clarification 保持原样，作为一次在实现前被聚合真值闸门否决的
协议样本。

绑定对象：

| Artifact | Commit | SHA-256 |
|---|---|---|
| `MMLU_HOLDOUT_CONTAMINATION_PROTOCOL_V2_20260803.md` | `5aa4f760a6c82a3a357b7cc9b77eded0f4a08fff` | `a075213c0a2c3bb574ff0fdab2c1948d4e8842f42c26fc9272e072df7025695e` |
| `MMLU_HOLDOUT_CONTAMINATION_PROTOCOL_V2_CLARIFICATION_20260803.md` | `387845d9ef0d0fbbe241c4c863a16af4b649733d` | `e1d9dc81e28d6b1ecdd69df4733ea7519cd67a87133b293ccfc156dac43bba49` |
| V1 contamination inventory | `812ba0585449ba097456595d328fb6f51ac401fd` | `a416ea4a2e3dd41865d6f0f12db46df67db91b324a7a2b6273fa66c21b5d0f10` |
| Cache-binding A0 receipt | `cdc3ae1943443d178365c736d599ce8657126665` | `ee2b178132191c5c81eb72322a0ca6f2f304c0e2ed351841b3039769e5c46263` |

## 1. 阻塞发现

V2 的目标是从未进入开发暴露集的 4,613 条 MMLU-Redux item 中，按 subject
确定性抽取 500 条，并把它描述为 development holdout。协议禁止选择过程读取
逐题真值字段，这一隔离原则本身正确；但协议没有在选择前检查候选池的**聚合
阳性余额**。

冻结后、实现前的聚合审计发现：所有已标注缺陷均已被历史富集采样吸收到开发
暴露集，候选池中没有任何阳性。

| Dataset | Rows | Labeled defects | Defects in used/exposed set | Defects remaining outside used set |
|---|---:|---:|---:|---:|
| MMLU-Redux | 5,700 | 370 | 370 / 1,087 | **0 / 4,613** |
| SVAMP-Platinum | 300 | 38 | 38 / 100 | **0 / 200** |
| GSM8K-Platinum (`cleaning_status=revised`) | 1,209 | 10 | 10 / 100 and 10 / 110 | **0** under either frozen manifest |

MMLU-Redux 的 370 条由 `metadata.error_type != "ok"` 定义；分布为
`ok=5330`，其余六类合计 370。SVAMP 的 38 条由
`metadata.audit_label != "clean"` 定义。GSM8K 的 10 条由
`metadata.cleaning_status == "revised"` 定义。

本次只计算边际计数与集合交叉计数。没有输出 item-to-label 对应关系，没有读取
或输出候选 question、choices、gold、verified_gold 或模型响应。聚合计数审计不
参与候选排序或替换。

## 2. 为什么当前 V2 会错误 PASS

V2 §6 以“illustrative 10% defect prevalence”估算 500 条约含 50 个阳性，
但没有把阳性率作为可满足性前置条件。V2 §8 的 PASS 只要求：

1. 七个 forward bindings 与 A0 controls 可复现；
2. artifact scope 未漂移；
3. subject quotas 可填满；
4. 产出 500-ID manifest。

4,613 条候选可以满足以上全部条件，因此实现会诚实地返回
`PASS_RECORDED_DEVELOPMENT_HOLDOUT_500`，却交付一个阳性数为零的集合。
该集合的 recall 分母为零，不能支持 detection recall、precision 或 F1 主张。

这不是 contamination scanner 的实现缺陷，而是**评测目标与 PASS gate 不一致**。
因此不得通过给实现补一个事后检查来继续 V2；当前 V2 的 detection-performance
用途在实现前终止。

## 3. 4,613 条剩余 MMLU item 的合法用途

这 4,613 条不是 detection-performance holdout。它们可在另行冻结的协议下作为：

- **specificity / false-positive control holdout**：报告假阳数量、假阳率、
  specificity，并配套一个不能由“永不报 finding”轻易满足的独立阳性控制；
- **instrument reproducibility set**：不依赖缺陷标签地测 item/violation Jaccard、
  per-method reproducibility 与运行间 finding composition；
- **false-positive-side threshold calibration set**：只约束阈值的假阳侧。

它们不得用于：

- detection recall；
- detection precision/F1 头条；
- 自然缺陷检出能力的泛化主张；
- “model-unseen”或“全新 benchmark item”措辞。

允许的最强措辞是：`held out from recorded system development and threshold
selection, subject to the separately reported contamination audit boundary`。
本地无暴露记录不等于模型预训练未见。

## 4. 后续必须拆成两个协议

### 4.1 Specificity holdout

可继续使用 MMLU 剩余池，但必须重新冻结目的、指标和对照。该协议不设置自然
阳性率要求，也不得输出 recall/precision/F1。它必须显式规定“零假阳不能由永不
触发的系统满足”的注入阳性或可达性控制。

### 4.2 Detection holdout

必须换用一个开发期未接触、且保留自然标注阳性的来源。实现前先做**零 API 的
数据可得性预飞**，只回答：

1. 数据与不可变 revision 是否可得；
2. 是否存在 item-level defect labels；
3. 是否存在运行 detection evaluation 所需的模型作答/输出矩阵；
4. 聚合候选池阳性数与阳性率是否达到预注册下限；
5. 是否能在不泄露 item-label mapping 给选择器的条件下完成分层抽样。

可得性预飞应优先检查尚未接入的 Platinum Benchmark 数据集，但不得在冻结
source manifest 前下载后补 manifest，也不得用非官方镜像或手工重建缺失标签。
只有预飞通过，才允许冻结 detection-holdout selection protocol。

未来 detection holdout 的 PASS gate 必须包含一个由独立聚合器给出的
`positive_count >= pre_registered_minimum` 条件。聚合器只向选择器公开总数/分层
计数，不公开 item-label 对应；低于门槛时结局为
`INSUFFICIENT_POSITIVE_PREVALENCE`，且不产出 manifest。

## 5. 流程修正

以后任何用于 precision/recall/F1 的自然标签 holdout，在冻结选样协议前必须完成：

1. **聚合阳性余额预飞**：总阳性、已用阳性、候选阳性；
2. **用途—分母可定义性检查**：每个预注册指标的分母在候选池中必须非零；
3. **富集采样耗尽检查**：历史 defect-enriched manifests 是否已吸干标签预算；
4. **正例可满足性检查**：真实候选源必须能满足协议所需的阳性下限；
5. **RNG 环境绑定**：除 seed、bit generator 与算法外，记录 NumPy 版本。

聚合真值审计必须与逐题选择器隔离。聚合器可发布边际计数和 gate boolean；
不得把 item-label mapping、标签排序或替换依据交给选择器。

## 6. 输入绑定

| Input | SHA-256 |
|---|---|
| MMLU-Redux 5,700 | `0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4` |
| SVAMP-Platinum 300 | `f27f8ebf56b33fbeea4b6430f63f24c66adb37bd38a1a8b2bbe62960f588063e` |
| GSM8K-Platinum aligned 1,209 | `9ac7e9b626b3708022533c87ed8c90f82cc4f804ac52bb468d7bd5232ca87087` |
| SVAMP pilot100 manifest | `c4ef5ddfb590b210243c0114d7d9eed7a15c2c0a1cf14a98f763cb7d4992d861` |
| GSM8K pilot100 manifest | `7a635d0e568489d86d34af65c127c1c5ed91ed0a7c22e9d2abc768ebdd1a0fda` |
| GSM8K pilot110 manifest | `88cd0724b6892b62a6599502521f951fa49e7e18d342a70ad98e32bd00f3c3f8` |

## 7. 最终裁决

**STOP_DETECTION_HOLDOUT_ZERO_POSITIVES**

- 不实现当前 V2；
- 不产出 500-ID detection holdout manifest；
- 不修改冻结协议或 clarification；
- MMLU 剩余池仅保留为未来 specificity/reproducibility 协议的候选源；
- 下一项工作是先冻结并执行“未接触 Platinum 数据集的可得性与聚合阳性余额
  预飞”，不是直接抽样或运行审计器。

这次停止发生在实现前，因此没有 API 成本，也没有新增候选暴露。
