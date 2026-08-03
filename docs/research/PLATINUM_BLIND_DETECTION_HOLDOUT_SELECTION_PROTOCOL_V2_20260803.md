# Platinum 盲测 Holdout 选择协议 V2：功效、三跑与 Truth-Unseal 顺序

> Freeze date: 2026-08-03  
> Status: **FROZEN_PENDING_INDEPENDENT_REVIEW**  
> This document supersedes only the clauses explicitly listed below  
> Selector/auditor implementation before review: forbidden

## 0. V1 绑定与修订原因

V1 保持不可变：

| Artifact | Commit | SHA-256 |
|---|---|---|
| `PLATINUM_BLIND_DETECTION_HOLDOUT_SELECTION_PROTOCOL_20260803.md` | `24c6e01` | `2ad4cc5c06039f9281e07b7d97372b3588fd20f104cefb0a9879425f19c105b1` |

冻结后、实现前的独立复核发现，V1 把统计功效最弱的算术层指定为 primary，且没有
把项目已经测得的 LLM 审计器运行间不稳定性用于 holdout 运行设计。V2 在没有运行
selector、auditor 或查看逐题 truth mapping 的前提下修订：

1. 证据层级由统计功效决定，而不是由与开发分布的距离决定；
2. Layer B 的 `revised/rejected` 阳性配额预先拆开；
3. 未来 holdout 评测必须三次独立运行；
4. truth unseal 必须晚于预测产物 Git commit，并可由祖先关系复算。

V1 中未被 V2 明确覆盖的来源绑定、VQA/TabFact 排除、identity 定义、总样本范围、
禁止 raw pooled F1、停止结局与诚实边界继续有效。

## 1. 功效预飞与证据层级（覆盖 V1 §0、§2、§3、§6）

### 1.1 规划口径

以真实 recall `p=0.80` 作为**规划例**，不是结果预测。Wilson 95% interval：

| Layer | Natural-positive support | Approx. Wilson 95% CI | Width | Permitted role |
|---|---:|---:|---:|---|
| A arithmetic | 25 | `[0.609, 0.911]` | 0.303 | descriptive / existence only |
| B text QA | 170 | `[0.734, 0.853]` | 0.120 | primary inferential result |
| C reasoning/coreference | 15 | `[0.548, 0.930]` | 0.381 | exploratory only |

Layer A 已经是 442 条 census，Layer C 已纳入全部 15 个自然阳性；无法通过增加同源
样本缩窄阳性 recall 区间。不得在结果后通过合并层、注入阳性或换 config 放大分母。

### 1.2 新的证据层级

#### Primary：Layer B text QA

Layer B 是唯一有足够自然阳性支持区间估计的层，承载论文的 blind detection
performance 主结果。允许的主张限于冻结的 DROP/HotpotQA/SQuAD 范围以及“跨任务、
同文本模态”层级，不外推到任意 QA 或任意 benchmark。

#### Descriptive：Layer A arithmetic

Layer A 回答同族未接触数据上是否仍存在可检出信号，并报告 census 下的自然
prevalence、recall、specificity、precision/F1 与区间。由于 positive `n=25`，只允许
描述性或存在性表述，例如“仍检出若干/多数人工标注缺陷”。

禁止用 Layer A 支持：

- 优于某基线或优于另一 layer；
- 与开发集性能等价；
- 性能下降/提升不超过某阈值；
- 任务内泛化已经被精确估计。

#### Exploratory：Layer C reasoning/coreference

Layer C 只作探索性附录或独立小节，不进主结果表，不用于摘要或头条比较。必须同时
展示两个零阳性 BBH config 的 negative-control 结果，不能只报存在阳性的两个
config。

### 1.3 禁止跨层 raw headline

三层不得合成未经设计加权的 overall precision/F1/recall。若实现 design-weighted
估计，其结果仍为 secondary，不得覆盖 Layer B primary。

## 2. Layer B truth-stratified 配额（覆盖 V1 §2.2、§5.2）

V1 的 Layer B 总数保持 300、每 config 总数保持 100，但 positive stratum 从 binary
拆成确切的 `revised` 与 `rejected`：

| Config | Revised | Rejected | Negative control | Total |
|---|---:|---:|---:|---:|
| `drop` | 40 | 30 | 30 | 100 |
| `hotpotqa` | 25 | 25 | 50 | 100 |
| `squad` | 20 | 30 | 50 | 100 |
| **Layer B** | **85** | **85** | **130** | **300** |

所有格子均在冻结 availability 聚合计数内可满足。选择 rank 的 stratum token 改为：

- `revised`
- `rejected`
- `negative`（`consensus` 与 `verified` 合并）

其余 rank 公式、seed、tie-break 与不可人工替换规则继承 V1。

Layer B 必须分别报告：

- revised recall，support 85；
- rejected recall，support 85；
- combined positive recall，support 170；
- negative specificity/FPR，support 130。

这两个 positive stratum 对应不同问题：`revised` 主要是原 target 需改正；`rejected`
主要是 item 因歧义、不可用或其他质量问题被排除。不得只报 combined recall 来掩盖
两类能力差异。

### 2.1 Layer A/C 不拆 positive subtype

Layer A 的真实分布为 `revised=3, rejected=22`，不是近似均衡；Layer C 的 15 个阳性
全部来自 rejected。两层 subtype 区间不具解释力，因此：

- Layer A 只报 combined positive recall；
- Layer C 只报 combined exploratory recall；
- subtype 计数作为 support disclosure 保留，但不计算或比较 subtype performance。

该口径现在冻结，不能根据结果决定是否拆分。

## 3. 三次独立 holdout 运行（覆盖 V1 §7）

Selection PASS 仍不直接授权 API。后续 run protocol 必须预注册并执行恰好 **3 次**
独立运行；少于 3 次时不得发布 primary detection performance。

三次运行必须：

1. 使用同一冻结 897-item manifest、同一代码 commit、同一 methods 列表与同一模型
   config；
2. 每次使用新的、开始时为空的 cache；禁止跨运行读取或写入另一运行 cache；
3. 显式固定 workers、temperature、votes、thinking、max tokens；
4. 各自记录 API attempts、token、成本、operational failures 与 coverage；
5. 不因某一运行更好而把它指定为代表运行；三次全部进入结果；
6. 任何一次触发冻结 stop gate 时保留该次失败，并由 run protocol 决定是否停止后续
   运行；不得无声明重跑替换；
7. 允许的重跑次数必须在 run protocol 中固定，默认 **0**。

预估仅用于预算：按 SVAMP-100 的既有调用量外推，897 条单次约 ¥13，三次约 ¥40。
真实预算须由零 API dry-count 预飞重新计算后，在运行前冻结；本数字不授权开跑。

## 4. 三跑报告口径

每一运行独立报告 V1/V2 规定的 layer/config 指标与 Wilson interval。不得把三次对同一
item 的观测当作 3 倍独立样本来收窄 Wilson CI。

跨运行另报：

- 每项 primary metric 的三个点值、median、min–max、sample SD；
- 3 个 pairwise item-level Jaccard；
- 3 个 pairwise violation-level Jaccard；
- per-method reproducibility；
- finding count 与 coverage 的三跑分布；
- deterministic methods 与 LLM-derived methods 分层稳定性。

Layer B primary 必须把“层内抽样不确定性（Wilson CI）”和“仪器运行间不确定性
（三跑散布）”并列展示。二者不得合成一个未经论证的单一 CI。

如果三次的 operational method sets 不完全相同，primary comparison fail closed；
只能报告 `NOT_COMPARABLE_METHOD_SET`，不得对交集 methods 事后重算来抢救头条。

## 5. Git 顺序证明与 Truth Unseal（覆盖 V1 §4）

### 5.1 Selection commit

Selector 阶段提交：

- public manifest；
- sealed truth artifact 的 SHA-256 commitment；
- selector/code/input/receipt hashes；
- `truth_unsealed=false`。

sealed truth 本体不得进入 runner 可读路径，也不得进入该提交的公开产物。V1 的诚实
边界继续成立：这不防拥有源数据权限的拜占庭操作者，只控制正常流程与意外泄露。

### 5.2 Prediction commits

每次运行完成后，先提交一个 prediction commit，至少包含：

- raw/stable prediction artifact SHA-256；
- run cache SHA-256 与 entry count；
- code/config/method-set/manifest hash；
- operational/coverage counters；
- `truth_read=false`、`scoring_performed=false`。

第三次完成后再提交一个 prediction-lock commit，列出三个 prediction commit 与全部
产物哈希。该 commit 形成不可变的 pre-truth prediction set。

### 5.3 Unseal 与 scoring commit

scorer 只有在以下条件全部满足时才可读取 truth：

1. prediction-lock commit 存在且工作树干净；
2. 三个 prediction commit 都是 prediction-lock 的祖先；
3. public manifest、sealed-truth commitment 与三套 prediction hashes 全部匹配；
4. 三次 method sets 完全相同；
5. 当前 scoring code commit 是三个 prediction commits 的共同祖先，因而在任何
   holdout 预测之前已经冻结；
6. scorer 的 unseal 操作写入独立 receipt。

scoring commit 必须以 prediction-lock 为祖先，并记录：

- `git merge-base --is-ancestor <prediction-lock> <scoring-commit>` 可复算为 true；
- truth artifact hash 与 selection commitment 相同；
- exact unseal receipt hash；
- predictions 未被修改。

任何 prediction artifact 在 unseal 后改变，整个结果为
`CONTAMINATED_POST_UNSEAL_PREDICTION_MUTATION`，不得通过重算 hash 修复。

这条 Git 顺序证明可以机械证明“已发布预测早于评分提交”，但不能证明操作者没有从
仓库外提前读取源标签；这一残余边界必须保留。

## 6. 新增/覆盖测试

在 V1 §9 测试之外，至少增加：

1. Layer B 配额精确为 revised 85 / rejected 85 / negative 130；
2. 每个 config 的三格配额逐项匹配 §2；
3. Layer A support 精确为 revised 3 / rejected 22，且 subtype metric 被拒；
4. Layer C subtype metric 被拒；
5. Layer B combined 与 split recall 都可达；
6. reporter 拒绝把 Layer A/C 标为 primary；
7. reporter 拒绝把 Layer C 放进 main table；
8. run count 1 或 2 时 primary publication gate fail closed；
9. 三个 cache 初始非空或 hash 相同即拒绝；
10. 三次 method set 任一不同返回 `NOT_COMPARABLE_METHOD_SET`；
11. 三跑 metric 不被错误合并为 3n Wilson interval；
12. prediction-lock 缺失时 scorer 拒绝读取 truth；
13. prediction commit 不是 lock 祖先时拒绝；
14. scoring code 不是三个 prediction commits 的共同祖先时拒绝；
15. prediction-lock 是 scoring commit 祖先的正例；
16. unseal 后改一字节 prediction，返回 contamination；
17. truth hash 与 selection commitment 不同，拒绝 scoring；
18. toy history 证明 predictions → lock → scoring 的唯一正路径可达。

## 7. 更新后的阶段结局

Selection 阶段沿用 V1 结局，但 PASS 名称保持
`PASS_BLIND_HOLDOUT_MANIFEST_897`，不因证据层级变化而改样本总数。

Run/scoring 阶段必须至少支持：

- `PASS_THREE_RUN_BLIND_EVALUATION`
- `INSUFFICIENT_RUN_REPLICATION`
- `NOT_COMPARABLE_METHOD_SET`
- `OPERATIONAL_STOP_GATE_TRIGGERED`
- `CONTAMINATED_TRUTH_UNSEAL`
- `CONTAMINATED_POST_UNSEAL_PREDICTION_MUTATION`
- `NOT_IDENTIFIABLE_GIT_ORDER_PROOF`
- `NO_DETECTION_SIGNAL`

## 8. 当前许可

V2 仍只是一份待独立复核的冻结协议。复核通过前：

- 不实现 selector/sealing/scorer；
- 不生成 manifest/truth；
- 不启动三次运行；
- 不读取 item-level truth mapping；
- 不修改 V1 或 V2。

复核通过后，selector 实现必须按 V1 的提交顺序进行；run protocol 仍需在任何 API
调用之前另行冻结，并绑定实际 dry-count 与预算。
