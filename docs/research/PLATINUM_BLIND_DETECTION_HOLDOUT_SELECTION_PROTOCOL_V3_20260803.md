# Platinum Holdout Selection Protocol V3：Prevalence、三跑头条与唯一评分入口

> Freeze date: 2026-08-03  
> Status: **FROZEN_PENDING_INDEPENDENT_REVIEW**  
> Supersedes only the clauses explicitly listed here  
> Selector/auditor/scorer implementation before review: forbidden

## 0. 绑定

| Artifact | Commit | SHA-256 |
|---|---|---|
| Selection V1 | `24c6e01` | `2ad4cc5c06039f9281e07b7d97372b3588fd20f104cefb0a9879425f19c105b1` |
| Selection V2 | `d6a9cc3` | `6aec64799c1ee833b0c426a4673ca3424f6bb9786fd6986d09449cb43137ef1c` |
| Strata receipt protocol | `21f84a4` | `6202fe3d37a1b92f29010ff5b544b45d82159445ded9210546f401efe0d66091` |
| Strata receipt | `daa486f` | `c14921699fd3db461fb424f50c1befac9e233b493f5e7ef4caca03e6399f9ce9` |
| Strata summary | `daa486f` | `4baa7a08667c23d769e76f2ff7a431d65dfeab6f0611a42544843c2d3955080e` |

Receipt 仅由已提交的 aggregate-only availability JSON 派生；没有重新打开数据集、
网络、API、auditor 或 item↔label mapping。

## 1. Prevalence 更正与精度边界（覆盖 V1 §6、V2 §1/§2）

### 1.1 三个不同的 prevalence，不得混称“自然值”

| Population / design | Positive | Negative | Prevalence |
|---|---:|---:|---:|
| Layer A source census | 25 | 417 | `25/442 = 5.656%` |
| Layer B source population | 509 | 241 | `509/750 = 67.867%` |
| Layer B frozen sample | 170 | 130 | `170/300 = 56.667%` |
| MMLU-Redux reference population | 370 | 5,330 | `370/5700 = 6.491%` |

因此，Layer B 抽样没有相对 Layer B 自身自然分布“把阳性率提高十倍”；它把源层
prevalence 从 67.9% 降到 56.7%。但 Layer B sample prevalence 确实约为 MMLU
reference prevalence 的 8.7 倍，raw sample precision 不能外推到低缺陷率 benchmark。

### 1.2 Primary endpoints

Layer B primary endpoints 改为对 prevalence 不敏感的：

1. revised recall（85 support）；
2. rejected recall（85 support）；
3. balanced positive recall：`(R_revised + R_rejected) / 2`；
4. specificity / false-positive rate（130 negative support）。

每项逐跑评分；三跑头条聚合见 §3。

Layer B raw-sample precision/F1 不得作为头条，也不得命名为 benchmark precision。

### 1.3 Precision 的唯一合法报告

令：

- `R_rev,c`、`R_rej,c` 为 config c 内对应 subtype recall；
- `FPR_c` 为 config c 内 negative-control FPR；
- Layer B source counts：
  - revised: drop/hotpotqa/squad = `179/88/43`，合计 310；
  - rejected: `41/69/89`，合计 199；
  - negative: `30/93/118`，合计 241。

按 frozen source composition 计算：

`R_B = (179 R_rev,drop + 88 R_rev,hotpot + 43 R_rev,squad
       + 41 R_rej,drop + 69 R_rej,hotpot + 89 R_rej,squad) / 509`

`FPR_B = (30 FPR_drop + 93 FPR_hotpot + 118 FPR_squad) / 241`

对指定 prevalence `π`：

`PPV_B(π) = π R_B / [π R_B + (1-π) FPR_B]`

若分母为零，PPV 为 undefined，不得填 0 或 1。

必须逐跑报告：

- `PPV_B(509/750)`：Layer B source-composition estimate；
- `PPV_B(370/5700)`：**标准化低-prevalence 情景**，仅用于与 MMLU 6.5%
  环境对照；
- sensitivity curve at `π ∈ {0.01, 0.025, 0.05, 370/5700, 0.10, 0.25,
  0.50, 509/750}`。

`PPV_B(370/5700)` 不得称为 Platinum 的真实 precision，也不得暗示 Layer B 与 MMLU
具有相同任务/缺陷组成。它依赖把冻结的 Layer B conditional sensitivity/FPR transport
到给定 prevalence 的显式假设。

Layer A 是 census，可直接报告其 `π=25/442` 下的 empirical precision/F1 与区间；
这是“真实低 prevalence 下的 precision”证据。Layer B 提供“有阳性功效的
recall/FPR”证据。两者互补，不得用一个替代另一个。

### 1.4 Design weighting 与区间

Layer B source-composition estimates 使用冻结 stratum inclusion probabilities；不得
从 raw `170/300` contingency table 直接计算 source precision。实现必须在 truth
unseal 前冻结 Horvitz–Thompson/等价分层估计代码与 toy-fixture tests。

固定 holdout 上的 85/85/130 empirical endpoints 可报告 Wilson interval；source-
composition weighted estimates 另报 stratified bootstrap CI。两种区间不得混称。

## 2. Layer A 解读约束（覆盖 V2 §1.2/§2.1）

专门 receipt 已确认 Layer A positive composition：

- revised = 3；
- rejected = 22。

因此 Layer A combined recall 主要测 rejected item（歧义、不可用或其他质量问题）的
检出，不足以评估 gold-auditor 对 revised/gold-error 的同族泛化。

必须伴随 Layer A 结果出现的限制语句：

> Layer A contains only three revised-label items and twenty-two rejected items;
> its combined recall predominantly reflects rejected-item detection and cannot
> establish generalization of the gold-error auditor.

禁止把 Layer A 低 recall 解读为整体算术审计失败，也禁止把高 recall 解读为 gold
auditor 泛化成功。revised 子类型只报 support，不报性能。

## 3. 三跑唯一头条规则（覆盖 V2 §3/§4）

每次运行独立评分，产生三个 primary endpoint 值。对每一个 Layer B primary endpoint：

- **headline = 三个独立运行点值的中位数**；
- 三个原始值按 run ID 全部列出；
- 同列报告 min–max 与 sample SD；
- 每跑自己的 Wilson interval 并列；不得对 median 伪造 Wilson interval；
- 不允许选择最优、最后一次或最接近开发集的一次作为代表。

Layer A/C 也使用三跑中位数作描述性汇总，但不得提升其证据层级。

### 3.1 Union / intersection

三跑 finding union 与 intersection 只允许作为 secondary stability analysis：

- union 不得作为主召回或主 finding count；
- intersection 不得作为主 precision/specificity；
- 两者必须标注其结构性方向：union 倾向提高召回/FP，intersection 倾向提高精度/
  降低召回；
- 禁止根据哪个更好而选择 union/intersection 作为系统输出。

Primary 永远是三次**独立逐跑评分的中位数**。

## 4. Strata receipt 与配额门（补强 V2 §2）

Selection implementation 必须先验证专门 receipt：

- input receipt SHA-256 =
  `c14921699fd3db461fb424f50c1befac9e233b493f5e7ef4caca03e6399f9ce9`；
- outcome = `PASS_SELECTION_STRATA_AVAILABLE`；
- Layer A revised/rejected = `3/22`；
- Layer B source revised/rejected/negative = `310/199/241`；
- Layer B frozen sample quota = `85/85/130`；
- 每个 config×status cell `headroom >= 0`；
- item IDs/mapping emitted = false；dataset/network/API/auditor access = zero。

任一不符即 `AGGREGATE_RECEIPT_MISMATCH`，不得打开 parquet 重算来现场补救。

## 5. VQA 排除的双重理由（补强 V1 §2.4）

VQA 继续预注册排除，理由同时为：

1. 当前系统没有视觉输入通道、图像资产未物化；
2. VQA availability 是 `242 positive / 0 negative`，precision、specificity 与 FPR
   分母不完整，不能支持与 Layer A/B/C 对称的检测性能评测。

两条理由都在任何 auditor 结果前固定。VQA 仍保留在 availability disclosure。

## 6. 唯一评分入口与配置哈希（补强 V2 §5）

Git common-ancestor proof 之外，再冻结唯一允许读取 sealed truth 的入口：

- module/CLI: `scripts/score_platinum_blind_holdout.py::main`
- config: `configs/platinum_blind_scoring_v1.json`
- truth-loader allowlist: 仅上述 scorer module

scorer 与 config 必须在第一次 prediction commit 前提交；run protocol 记录二者 SHA。
三个 prediction commits、prediction-lock 与 scoring receipt 必须重复绑定相同 SHA。

Scoring config 必须完整包含：

- primary/secondary/exploratory layer roles；
- Layer B 85/85/130 quota；
- source stratum counts与 inclusion probabilities；
- prevalence grid 与 exact rational values `25/442`、`370/5700`、`509/750`；
- PPV 公式版本；
- median-of-three headline rule；
- union/intersection secondary-only rule；
- CI/bootstrap method、seed 与 library versions；
- metric schema fingerprint。

禁止 CLI 覆盖 prevalence、layer role、formula、run aggregation 或 metric list。未知 config
字段、未知 schema version 或 hash mismatch fail closed。

静态测试必须扫描生产路径：除 allowlisted scorer 外，任何模块读取 sealed truth、
`cleaning_status` truth artifact 或调用 truth loader 均失败。存在多个预写评分入口时返回
`MULTIPLE_SCORING_ENTRYPOINTS`，不得在结果后挑选。

这仍不能排除恶意操作者自行编写仓库外 scorer；它机械固定的是可发布生产路径。

## 7. 新增测试

在 V1/V2 tests 之外：

1. prevalence 四个 exact fractions 与 decimal display 可复算；
2. raw Layer B sample precision 被拒为 headline；
3. `PPV_B(π)` toy fixture 与手算相同；
4. FPR=0/R=0 导致 PPV denominator zero 时返回 undefined；
5. source-composition weights精确为 revised `179/88/43`、rejected `41/69/89`、
   negative `30/93/118`；
6. `π=370/5700` 输出标为 standardized scenario；
7. Layer A revised performance metric 被拒，只保留 support；
8. Layer A 报告必须含 §2 限制语句；
9. 三跑 `[x,y,z]` headline 精确为 median，且三值全保留；
10. best-of-three/last-run aggregation 被拒；
11. union/intersection 不能进入 primary metric slots；
12. strata receipt hash/outcome/headroom 任一变异 fail closed；
13. VQA exclusion 同时记录 modality 与 zero-negative 原因；
14. scorer/config SHA 在三个 prediction commits 中完全相同；
15. CLI 尝试覆盖 prevalence/formula/role 被拒；
16. 第二个 truth-reading scorer 被静态 gate 捕获；
17. scorer/config 不是 prediction commits 的共同祖先时拒绝；
18. design-weighted source precision 与 stratified bootstrap 在 toy population 上复算。

## 8. 当前许可

V3 通过独立复核后才允许实现 selector。即便 selector PASS，三跑 auditor 仍需另冻 run
protocol、零 API dry-count、成本与 stop gates。

复核前不得实现 selector/scorer、生成 manifest/truth、运行 auditor 或读取 item-level
truth mapping。V1/V2/V3 与 strata receipt 均保持不可变。
