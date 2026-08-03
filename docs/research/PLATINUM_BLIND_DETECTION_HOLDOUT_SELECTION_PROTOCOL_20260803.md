# Platinum 未接触数据：盲测 Detection Holdout 选择协议

> Freeze date: 2026-08-03  
> Status: **FROZEN_PENDING_INDEPENDENT_REVIEW**  
> Auditor/LLM execution before manifest commit: forbidden  
> Item-level truth inspection by runner or analyst before prediction commit: forbidden  
> This protocol does not authorize model-output reruns

## 0. 研究问题与三条不可混淆的轴

本协议构造一个 held out from recorded BenchAudit development and threshold
selection 的自然标签评测集，用于回答：

1. **同族盲测**：在未参与开发的算术题上，现有审计器能否检出自然缺陷；
2. **跨任务族泛化**：在文本 QA 与更远的推理/指代任务上，性能如何变化；
3. **仪器稳定性**：同一冻结方法在这些层上的 finding composition 是否可复现。

它不回答：

- 模型在预训练阶段是否见过这些题；
- VQA/视觉模态上的检测能力；
- 这些 Platinum item 的缺陷给模型分数造成了多大影响；
- confirmed 缺陷的执行级召回；
- 任意 benchmark 上的普遍泛化。

检测与影响当前落在两套不同数据上：

- blind detection performance：本协议的 Platinum holdout；
- score/ranking impact：MMLU-Redux 的 15-model panel。

论文必须把两者作为**互补但非 item-level 闭环**的证据报告。不得写成“本协议检出
的 Platinum 缺陷导致了 MMLU 中观察到的分数变化”，也不得把 MMLU 的开发数据
影响分析描述为 blind impact evaluation。

## 1. 上游绑定与许可

本协议只继承下列冻结来源与可得性结果：

| Artifact | Commit / revision | SHA-256 |
|---|---|---|
| Availability protocol | `83bd325` | `cbe0e5cd145f1cf23481f508464501ff1f12deeca992ee9391148bf9918a0450` |
| Availability result commit | `bb48a96e53c211a8e552b783f942b28293c21809` | — |
| `availability.json` | `bb48a96e53c211a8e552b783f942b28293c21809` | `2a1b1164f1e9831e5554abfcac14df44cf78963957cce219ecc9381f2d3e7f77` |
| `receipt.json` | `bb48a96e53c211a8e552b783f942b28293c21809` | `d0a587a8bd83b1169e3a8328d097218d5d6a0645eb5f3548774c9b2e3e5545de` |
| Platinum dataset | `51920a33bfb4620c789729ace14141e87a14969b` | per-config hashes in availability result |

上游结论为：11 个 identity 合格 config，791 个自然阳性、1,443 个阴性对照；
其中 8 个 config 同时含正负样本。模型作答轴为
`NOT_IDENTIFIABLE_MODEL_OUTPUT_LINKAGE`，本协议不得绕过该结局。

## 2. Config 分层与预注册排除

### 2.1 Layer A：同族算术，主结果

- `multiarith`
- `singleop`
- `singleq`

选择全部 **442** 条，构成 census：25 natural positives + 417 negative controls。
不抽样、不替换、不丢弃任何一条。该层最接近 SVAMP/GSM8K 的开发任务形态，且
输入短、答案契约简单，是本研究的主要 blind-detection 结果，也是未来若另冻模型
作答协议时优先考虑的低成本 cohort。

### 2.2 Layer B：邻族文本 QA，次要泛化结果

- `drop`
- `hotpotqa`
- `squad`

按 config × binary truth stratum 做冻结配额抽样：

| Config | Natural positive | Negative control | Total |
|---|---:|---:|---:|
| `drop` | 70 | 30 | 100 |
| `hotpotqa` | 50 | 50 | 100 |
| `squad` | 50 | 50 | 100 |
| **Layer B** | **170** | **130** | **300** |

### 2.3 Layer C：远族推理/指代，探索性泛化结果

- `bbh_logical_deduction_three_objects`
- `bbh_navigate`
- `bbh_object_counting`
- `winograd_wsc`

两个 BBH config 没有自然阳性，必须保留为纯阴性对照，不得从层内统计分母中
静默删除：

| Config | Natural positive | Negative control | Total |
|---|---:|---:|---:|
| `bbh_logical_deduction_three_objects` | 0 | 35 | 35 |
| `bbh_navigate` | 0 | 35 | 35 |
| `bbh_object_counting` | 10（census） | 35 | 45 |
| `winograd_wsc` | 5（census） | 35 | 40 |
| **Layer C** | **15** | **140** | **155** |

### 2.4 Layer X：模态外，仅可得性记录

`vqa` 预注册排除于选择与所有检测指标之外。理由在看到任何 BenchAudit 结果前已
固定：当前系统没有视觉输入通道，数据中的图像资产也未被本协议物化。将 VQA
并入指标只会把“模态不可执行”误写成“缺陷检测失败”。

VQA 的 242 positive-only rows 继续留在 availability 报告中；不得从上游总数中
抹去，也不得作为 recall 失败计入 Layer A/B/C。

### 2.5 Identity 不可识别排除

`tab_fact` 的原生 `id` 有 17 个重复，冻结 availability gate 已将其记为
`NOT_IDENTIFIABLE_ITEM_IDENTITY`。本协议不设计 composite ID 来换取纳入；未来如
要支持，须另冻 identity protocol。

## 3. 总样本与阳性分母

| Layer | Items | Natural positives | Negative controls | Use |
|---|---:|---:|---:|---|
| A arithmetic | 442 | 25 | 417 | primary |
| B text QA | 300 | 170 | 130 | secondary |
| C reasoning/coreference | 155 | 15 | 140 | exploratory |
| **Total executed holdout** | **897** | **210** | **687** | no unweighted pooled headline |

每层 positive 分母均在选择前由聚合器证明非零。Layer A/C 的阳性数低是总体数据
性质，分别采用阳性 census；不得在结果后换 config、补注入阳性或把层合并来放大
分母。

## 4. Truth 定义与隔离

冻结二元真值：

- positive: `cleaning_status in {revised, rejected}`
- negative: `cleaning_status in {consensus, verified}`

它表示 Platinum 作者的人工清洗结局，不表示 BenchAudit confirmed，也不表示所有
positive 都属于同一种可机械判定缺陷。

选择器与 runner 必须分离：

1. selector 是唯一允许读取 `cleaning_status` 的组件；
2. selector 输出 public run manifest（opaque item identity、config、layer、source
   row locator），不含 status、gold、target、题面或抽样 rank；
3. selector 另输出 sealed truth artifact，含 item identity → binary truth/status；
4. sealed truth 的 SHA-256 在任何 auditor 运行前提交；
5. runner 只能读取 public manifest 与运行所需 item 内容，不能读取 sealed truth；
6. auditor 原始结果、配置、代码 commit、cache hash 与 completion marker 提交后，
   才允许 scorer 读取 sealed truth；
7. scorer 不得把逐题 truth 回写进 auditor cache 或下一轮 prompt。

本轮的 blind 是**系统开发与阈值选择隔离**，不是对拥有源数据文件的恶意操作者的
密码学不可见保证。该限制必须披露。任何人工提前查看 item↔status mapping 的事件
都使结果降为 `CONTAMINATED_TRUTH_UNSEAL`。

## 5. 确定性选择

### 5.1 Census strata

Layer A 全量纳入；Layer C 的 positive strata 全量纳入。census 不调用 RNG。

### 5.2 Sampled strata

对 Layer B 的每个 config×truth 和 Layer C 的每个 negative stratum：

1. 使用 availability 中的 opaque identity；
2. 计算 `rank = SHA256(seed || "\0" || config || "\0" || binary_stratum || "\0" || opaque_id)`；
3. 按 `(rank, opaque_id)` 升序取冻结配额；
4. 不允许人工替换；identity collision、配额不足或未知 status 均 fail closed。

冻结 seed（ASCII）：

`benchaudit-platinum-blind-holdout-v1-20260803`

这里使用 cryptographic hash ranking，不实例化 NumPy RNG；receipt 仍须记录 Python、
hashlib/OpenSSL 与 NumPy 版本，并断言 `numpy_rng_instantiated=false`。

## 6. 指标与汇总纪律

### 6.1 必报

逐 config、逐 layer 报告：

- positive/negative support；
- recall、specificity、false-positive rate；
- precision 与 F1（仅在该层 predicted-positive 分母非零时）；
- Wilson 95% CI；
- item-level 与 violation-level run-to-run Jaccard（若执行复跑）；
- abstention/coverage；
- confirmed/review/unknown 分层计数。

Layer A 是 primary；Layer B secondary；Layer C exploratory。不得看到结果后交换层级。

### 6.2 禁止的汇总

897 条的 raw pooled precision/F1 不得作为头条，因为 Layer B/C 是标签分层抽样，
raw prevalence 被设计改变。

若报告跨层总体，只允许：

1. 逐层并列，不合并；或
2. 使用已冻结 inclusion probability 的 Horvitz–Thompson/design-weighted 估计，
   报告权重、有效样本量与 bootstrap CI。

任何 design-weighted 实现必须在 truth unseal 前提交并有构造测试；否则不报总体。

Layer A 为 census，可直接报告其自然 prevalence 下的 precision/F1。

### 6.3 “永不报 finding”控制

specificity/FPR 不能单独构成 PASS。主结果至少同时满足：

- Layer A natural-positive recall 可定义；
- 至少一个预注册 positive control 使 detection path 可达；
- 若全部层 predicted findings=0，结局为 `NO_DETECTION_SIGNAL`，不得以零 FP 宣称成功。

positive control 只能验证管道可达性，不进入自然缺陷召回分子或分母。

## 7. 运行预算与未来模型重跑

本协议只授权生成 897-item manifest，不授权 LLM/auditor 运行。运行协议须另行冻结：

- methods 列表、模型、温度、votes、thinking、workers；
- API attempt/token/cost 上限；
- operational failure 与 coverage stop gate；
- cache schema/version 与两个全新运行 cache；
- 至少两次运行或明确的单跑限制。

若未来要在 Platinum 上补 model-score impact，必须另冻模型作答协议。优先 cohort 是
Layer A 的 442-item arithmetic census，因为其短答案与确定性解析使成本和 evaluator
风险最低。不得因为未来成本考虑而修改本协议已冻结的 detection 选样。

## 8. 选择阶段结局

- `PASS_BLIND_HOLDOUT_MANIFEST_897`：所有冻结配额满足，public manifest 与 sealed
  truth 均生成并哈希绑定，runner 未获得 truth；
- `NOT_IDENTIFIABLE_SOURCE_DRIFT`：revision/blob/availability hash 漂移；
- `NOT_IDENTIFIABLE_ITEM_IDENTITY`：任何纳入 stratum identity 缺失/碰撞；
- `INSUFFICIENT_LAYER_POSITIVES`：任何预注册非零 positive stratum 无法满足配额；
- `INSUFFICIENT_LAYER_NEGATIVES`：任何 negative 配额无法满足；
- `CONTAMINATED_TRUTH_UNSEAL`：预测 commit 前发生 item-level truth 暴露；
- `NOT_IDENTIFIABLE_SEALING`：truth artifact 无法在 runner 权限边界外保存；
- `SCOPE_DRIFT`：config、层、配额、seed 或 truth 定义发生变化。

非 PASS 不得发布 partial manifest，也不得用可用 config 临时补齐。

## 9. 实现前测试

至少包括：

1. 三层与两个排除 config 精确匹配本协议；
2. Layer A census 442/25/417；
3. Layer B 配额逐格匹配，任一不足 fail closed；
4. Layer C 两个零阳性 config 仍进入 negative controls；
5. VQA 永不进入 public manifest；
6. tab_fact 永不进入 public manifest；
7. public manifest 不含 truth/status/target/prompt/question；
8. sealed truth 与 public identity 集完全相等；
9. 改一个 seed byte 会改变 sampled strata，但不改变 census；
10. 重复运行逐字节一致；
11. runner 尝试读取 truth path 时被拒；
12. prediction completion marker 缺失时 scorer 拒绝 unseal；
13. pooled raw F1 被报告器拒绝；
14. design weight 在 toy fixture 上复算正确；
15. 零 finding 对照返回 `NO_DETECTION_SIGNAL`，不能 PASS；
16. NumPy RNG 未实例化且版本被记录。

## 10. 当前许可

本提交只冻结 selection protocol。独立复核通过前：

- 不实现 selector；
- 不生成 manifest/truth artifact；
- 不运行任何 auditor/LLM；
- 不查看未接触 config 的 item-level label mapping；
- 不修改阈值或 methods。

协议通过后，提交顺序必须为：selector → tests → fresh-clone tests → manifest/sealed
truth receipt。运行协议与检测结果属于后续独立提交。
