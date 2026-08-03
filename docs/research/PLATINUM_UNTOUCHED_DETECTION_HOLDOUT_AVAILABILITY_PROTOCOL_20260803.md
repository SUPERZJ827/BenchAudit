# 未接触 Platinum 数据集：Detection Holdout 可得性预飞协议

> Freeze date: 2026-08-03  
> Phase: availability and aggregate-prevalence preflight only  
> LLM/API execution: forbidden  
> BenchAudit auditor execution: forbidden  
> Item text inspection/emission: forbidden  
> Detection-holdout manifest generation: forbidden

## 0. 目的与边界

本预飞只回答：在历史已使用的 MMLU-Redux、SVAMP-Platinum、
GSM8K-Platinum 之外，官方 Platinum Benchmarks 是否提供一个可用于后续真盲测的
数据源，其中同时存在：

1. item-level 缺陷状态；
2. 足够的自然阳性与合法对照；
3. 可机械 join 的 item identity；
4. 可选的官方论文模型作答缓存，可用于后续影响分析。

本轮不抽 holdout、不运行 BenchAudit、不读取题面、不计算检测指标，也不把任何
item-label mapping 写入产物。可得性 PASS 只允许下一轮另冻 selection protocol；
不构成检测性能结果。

允许的最终措辞是 `held out from recorded BenchAudit development and threshold
selection`，不得写 `model-unseen` 或声称模型预训练未见。

## 1. 冻结来源

只允许以下 code-owned source manifest，调用者不得增加或替换 remote：

| Role | Canonical remote | Frozen revision |
|---|---|---|
| dataset | `https://huggingface.co/datasets/madrylab/platinum-bench` | `51920a33bfb4620c789729ace14141e87a14969b` |
| paper inference cache | `https://huggingface.co/datasets/madrylab/platinum-bench-paper-cache` | `0012c118c69ea73597d731cd10af9fb2c87727cb` |
| official evaluation code | `https://github.com/MadryLab/platinum-benchmarks.git` | `8fd2f82e63c49ea1cca4266f4dded82b7ddbcb55` |

Revision 必须通过官方 remote 的 exact-object fetch/resolve 得到；`main` 只作为人类
可读来源名，不参与执行。未知 host、对象不存在、revision 漂移或 unofficial mirror
均 fail closed。

### 1.1 冻结前已读信息披露

为决定本协议是否值得冻结，撰写者在冻结前只读了官方公开的聚合/结构信息：

- dataset card 的 config 名、字段 schema、每个 config 的总行数及
  `consensus/revised/verified/rejected` 聚合计数；
- official README 对 15 个 benchmark 与 paper cache 的说明；
- pinned code revision 中 `scripts/download_paper_cache.sh` 暴露的官方 cache repo 名；
- pinned `scripts/get_paper_results.sh` 的模型列表。

没有读取任何未接触 config 的 item text、item ID、label mapping、模型响应或逐题
结果。聚合可得性信息被允许用于功效与预算规划，但必须在结果中继续披露。

## 2. 冻结 config 范围

排除所有已经进入本项目开发、阈值选择或实验叙事的 benchmark family：

- `gsm8k`
- `svamp`
- `mmlu_math`（即使其 Platinum 子集与 MMLU-Redux 不完全相同，也保守排除）

仅检查以下 12 个预注册 config：

1. `bbh_logical_deduction_three_objects`
2. `bbh_navigate`
3. `bbh_object_counting`
4. `drop`
5. `hotpotqa`
6. `multiarith`
7. `singleop`
8. `singleq`
9. `squad`
10. `tab_fact`
11. `vqa`
12. `winograd_wsc`

不得根据预飞结果增删 config。VQA 若因官方图像资产不在冻结 dataset revision 内而
不可执行，仍保留在 availability 表中并记为 `missing_required_asset`，不得悄悄从
分母删除。

## 3. 标签语义与仅聚合计数

只允许读取统一字段 `cleaning_status`，其冻结状态集合为：

- negative controls: `consensus`, `verified`
- natural positives: `revised`, `rejected`
- unknown: 任何其他值或缺失值

这里的 positive 表示 Platinum 作者认定原标签需修订，或 item 因歧义/质量问题被
剔除；它不等价于 BenchAudit 能机械 confirmed 的缺陷。

聚合器可在内存中读取逐题 `cleaning_status` 与机械 identity 字段，但稳定产物只准
包含每 config 的四状态计数、总计、缺失/重复 ID 计数和不可逆集合摘要哈希。
不得输出逐题 ID、题面、gold、platinum target、原 target 或 item-label mapping。

## 4. Identity 与数据完整性预飞

每个 config 必须：

1. 从 frozen dataset revision 读取，不得使用本地旧 cache 冒充；
2. 记录 parquet/blob path、blob object/OID、字节数与 SHA-256；
3. 使用 config 原生稳定 ID；若无显式 ID，只允许
   `sha256(config_name || canonical_original_row_bytes)` 作为 opaque identity；
4. 检查 identity 缺失数与重复数；
5. 记录 `cleaning_status` 完整分布；
6. 证明 stable output 不含 identity 值本身，只含集合摘要；
7. 不调用任何 prompt builder 或 evaluator。

若 canonical row bytes 因 parquet decoder/version 不稳定而无法定义，必须记
`NOT_IDENTIFIABLE_ITEM_IDENTITY`，不得以 source row index 冒充跨产物 identity。

## 5. Paper-cache 可得性与 join 预飞

先只读取 frozen cache repo 的 tree/file metadata，记录文件名、blob/OID、大小、
格式与总下载量。随后：

- 若总量不超过 **5 GiB**，允许下载到隔离临时目录并做只读解析；
- 超过 5 GiB 时不下载，记 `CACHE_OVER_PREFLIGHT_BUDGET`；
- pickle 只允许使用受限 opcode 静态检查或在 network-disabled、read-only、non-root
  隔离容器内解析；不得在宿主 Python 中直接 `pickle.load` 不可信文件；
- 不执行 cache 中携带的任何代码；
- 只导出 schema、模型名、config 名、记录数以及 join 覆盖率聚合，不导出响应。

对每个 config 计算每模型：

`join_coverage = cache_rows_joined_to_dataset / dataset_rows_expected_for_that_cache`

若 cache identity 只能靠题面文本 join，则 impact-matrix 轴记
`NOT_IDENTIFIABLE_MODEL_OUTPUT_LINKAGE`；不得把模糊文本匹配当作 exact join。

## 6. 两条相互独立的 GO/NO-GO 轴

### 6.1 Detection-holdout availability

`PASS_DETECTION_HOLDOUT_SOURCE_AVAILABLE` 当且仅当：

1. 12 个预注册 config 均进入一个互斥终态；
2. 至少 **3 个** config 同时含自然 positive 与 negative control；
3. 所有可用 config 合计自然 positives 至少 **100**；
4. 至少 **300** 条 negative controls 可用；
5. 至少 3 个合格 config 的 identity 缺失与重复均为 0；
6. 不存在未知 `cleaning_status`；
7. 未读取或输出 item content/item-label mapping。

否则：

- 标签/字段缺失：`NOT_IDENTIFIABLE_DEFECT_LABELS`
- positive <100 或 mixed config <3：`INSUFFICIENT_POSITIVE_PREVALENCE`
- negative <300：`INSUFFICIENT_NEGATIVE_CONTROLS`
- identity 不可用：`NOT_IDENTIFIABLE_ITEM_IDENTITY`
- source/revision 不可用：`NOT_IDENTIFIABLE_DATA_AVAILABILITY`

### 6.2 Downstream-impact matrix availability

该轴不影响 detection-source PASS。只有以下条件全部满足才记
`PASS_MODEL_OUTPUT_MATRIX_AVAILABLE`：

1. 至少 5 个官方 paper 模型；
2. 至少 3 个 mixed-label config；
3. 每个计入模型/config pair 的 exact join coverage ≥95%；
4. 至少 1,500 个 model×item exact joins；
5. parser/evaluator version 能绑定到 frozen code revision。

否则使用一个明确的非 PASS 终态：`CACHE_OVER_PREFLIGHT_BUDGET`、
`NOT_IDENTIFIABLE_CACHE_FORMAT`、`NOT_IDENTIFIABLE_MODEL_OUTPUT_LINKAGE`、
`INSUFFICIENT_MODEL_OUTPUT_COVERAGE` 或 `NOT_IDENTIFIABLE_EVALUATOR_BINDING`。

不得因 impact matrix 失败而把 detection source 错记为失败，也不得因 detection
source PASS 而声称影响分析可做。

## 7. 产物与确定性

仅允许生成：

1. `availability.json`：聚合计数、互斥终态、集合摘要哈希；
2. `receipt.json`：全部输入 revision/blob/code hash、工具版本、零 API 声明；
3. `REPORT.md`：人类可读结论与诚实边界。

Stable JSON 使用 UTF-8、sorted keys、compact separators、末尾单换行。
两次离线聚合必须逐字节一致。记录 Python、PyArrow/Datasets（若使用）以及 NumPy
版本；任何 RNG 即使本轮不应使用，也必须断言未实例化。

Raw-only 字段（时间、临时路径、PID、网络耗时、下载速率、stderr）不得进入 stable
hash payload。

## 8. 禁止事项与停止纪律

- 不运行 BenchAudit 或任何 LLM；
- 不生成 detection/specificity holdout manifest；
- 不打印、提交或人工查看未接触 config 的 item text/ID/label mapping；
- 不从 unofficial mirror、论文附录手抄或网页表格重建缺失 item labels；
- 不在结果后调整 positive/negative 定义、100/300 门槛或 config 范围；
- 不因某 config 失败而换入第 13 个 config；
- 不执行不可信 pickle；
- 不提交数据集或大 cache；receipt 只记录不可变 revision、blob 与 SHA-256；
- 不把 aggregate availability PASS 写成检测性能 PASS。

任一安全边界无法证明时 fail closed，并保留 detection/impact 两轴各自真实终态。

## 9. 下一阶段许可

只有 `PASS_DETECTION_HOLDOUT_SOURCE_AVAILABLE` 才允许另冻 selection protocol。
下一协议必须：

- 按 config/defect status 预注册样本预算；
- 由隔离聚合器证明 positive 下限，但不把逐题标签交给 selector；
- 预注册替换顺序；
- 绑定 seed、bit generator、NumPy 版本与选择算法；
- 明确 development-holdout 污染边界；
- 在任何 auditor 运行前提交。

本协议的 PASS 本身不授权抽样、LLM 调用或阈值修改。
