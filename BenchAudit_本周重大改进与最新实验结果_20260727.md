# BenchAudit：本周重大改进与最新实验结果

> 汇报日期：2026-07-28  
> 本周范围：2026-07-21 ～ 2026-07-27  
> 核心目标：从“针对固定 benchmark 编写检查器”，推进到“面对陌生 benchmark，自动适配证据并尽可能确认真实问题”。

---

## 一、30 秒结论

本周最重要的进展不是又增加了几个缺陷规则，而是补齐了三种更通用的
证据入口：

1. **任务契约自适应**：LLM 只负责从自然语言中抽取显式输出要求，本地
   程序对文件清单进行确定性 replay；
2. **历史结果与轨迹接入**：已有模型结果、执行结果和评测轨迹可以统一
   转成 review-only 证据，用于低成本筛选；
3. **通用执行确认 MR-4**：只要新 benchmark 能提供“弱 oracle / 强
   oracle”关系，就可以不为每道题编写专用 proof validator，自动确认
   evaluator coverage gap。

本周最强的新实验结果：

> 在 HumanEval 和 MBPP 全量实验中，通用 MR-4 共执行 2,731 个确定性
> 变异候选，得到 **174 个 independently-attested confirmed coverage
> gaps**，影响 **93/538（17.29%）** 个有效任务；两次完整复跑结果完全
> 一致，所有 timeout、无 attestation、反向差异等控制组均为
> **0 confirmed**。

已有带人工缺陷标签的静态消融还给出了另一条互补证据：

> 完全不使用 LLM 的规则系统在 SVAMP-Platinum / MMLU-Redux 上的
> candidate F1 分别只有 **0.000 / 0.027**；加入 DeepSeek 语义审计后，
> 完整静态流水线达到 **0.914 / 0.663**。这说明自然语言 benchmark 的
> 静态审计不能只靠字段和字符串规则，但 LLM 仍只负责生成 review
> 候选，不能单独授予 confirmed。

这说明系统已经在“具有可执行、可比较 oracle 的代码 benchmark”上迈过
了一个关键门槛。但还不能声称“任意 benchmark 自动纠错”已经完成：
开放式 rubric、主观语义问题和未知执行协议仍然主要停留在 review 层。

---

# 二、本周做出的重大改进

## 2.1 从 benchmark 专用证明，升级为按关系定义的通用证明

之前的 confirmed 证据大量依赖某个 benchmark 的手写逻辑。例如 GDPval
中的文件名、格式、工作簿字段等分别有专用 replay。

本周新增了按数据类型和 oracle 关系定义的通用 Metamorphic Relation：

| 关系 | 检查内容 | 自动确认条件 |
|---|---|---|
| MR-1：Gold replay | evaluator 是否接受自己的 gold | 执行完成、gold 被拒、transcript 独立认证 |
| MR-2：格式不变性 | 数值、Python AST、SQL 布局等保语义变化是否改变 verdict | 本地证明语义保持、verdict 翻转、独立认证 |
| MR-3：MCQ 同步置换 | 同时打乱选项与 gold 标签，正确选项内容保持不变 | 原题通过、同步置换后失败、独立认证 |
| **MR-4：差分 oracle** | 弱测试通过、声明的强测试拒绝同一候选 | canonical 双侧通过、候选配对完成、独立认证 |

关键变化在于：

```text
以前：
benchmark A → 写 A 专用 proof
benchmark B → 再写 B 专用 proof

现在：
benchmark 声明自己的数据类型或 oracle 关系
          ↓
通用 MR 生成并验证证据
          ↓
中央 promotion 决定 confirmed / review
```

这更接近“给一个陌生 benchmark，系统自动适配”的最终目标。

---

## 2.2 新增独立执行证据边界

过去“容器里程序运行成功”并不能直接成为 confirmed，因为 benchmark
harness 与结果序列化可能处于同一个不可信进程。

本周补充的执行确认链路为：

```text
确定性候选生成
      ↓
只读、断网、非 root 容器执行
      ↓
独立 worker 观察 typed outcome
      ↓
worker 对完整 transcript 做 Ed25519 签名
      ↓
父进程固定 worker 公钥并验签
      ↓
中央 promotion 再次 replay proof contract
```

执行结果被显式分成：

- `completed + accepted=true`；
- `completed + accepted=false`；
- `timeout`；
- `error`。

timeout 和环境错误不再被混成“测试拒绝”，因此不会制造 confirmed
假阳性。

---

## 2.3 补充 LLM 辅助的静态任务契约抽取

纯字符串规则无法可靠理解下面的任务：

> “总结 1.txt、2.txt、……、100.txt，并输出为 123.txt。”

因此本周加入了一条受控的 LLM 静态路径：

```text
task 自然语言
      ↓ DeepSeek/LLM
只抽取显式 required output path：123.txt
      ↓ 本地静态 replay
与 output manifest 对比
```

这里 LLM 只负责抽取声明，不负责决定“是否有缺陷”。最终比对仍由本地
程序完成。

本周还修复了三类真实问题：

1. inventory 字段优先级原来由 Python `set` 迭代决定，可能随
   `PYTHONHASHSEED` 改变；现在改成显式 tuple 优先级；
2. LLM 如果把输入文件 `1.txt` 误抽成输出，会被 input inventory
   交叉抑制并记录，而不是直接报错；
3. `reference_files` 默认视为输入附件，不再误当成输出清单。

这条路径仍然保持 **review-only**：LLM 抽取不是客观 proof，不能因为
模型置信度高就进入 confirmed。

### 为什么静态语义层确实需要 LLM

这里的“静态”指 **不运行被评测任务、不生成新的 agent 轨迹，只读取已经
冻结的 task、gold、choices、rubric 和 manifest**；它不等于“完全不用
LLM”。

纯规则适合检查字段缺失、哈希、精确文件名和数值格式，但无法稳定理解：

- “将 1.txt 到 100.txt 汇总为 123.txt”中的输入与输出角色；
- 一个数学题的 gold 是否符合题意；
- 多项选择题是否存在多个语义上正确的选项；
- rubric 是否加入了 task 从未要求的内容；
- 两段不同写法是否表达同一个答案契约。

已有的冻结监督消融在相同数据和标签口径下比较了四种系统。使用 LLM 的
三组均以 DeepSeek 为底层模型；指标是 **candidate tier** 的
Precision、Recall 和 F1，不是 confirmed 指标。

| 系统 | 使用的能力 | SVAMP P | SVAMP R | SVAMP F1 | MMLU P | MMLU R | MMLU F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| Rules-only | 确定性静态规则，不使用 LLM | 0.000 | 0.000 | **0.000** | 0.714 | 0.014 | **0.027** |
| Naive LLM | 单次整体判断，无 taxonomy、无规则 | 0.897 | 0.684 | 0.776 | 0.808 | 0.478 | 0.601 |
| LLM + taxonomy | 单次判断，并提供缺陷分类词表 | 0.917 | 0.579 | 0.710 | 0.775 | 0.503 | 0.610 |
| **BenchAudit** | **静态规则 + 分解式 LLM 语义审计** | **0.860** | **0.974** | **0.914** | **0.641** | **0.686** | **0.663** |

> 命名说明：当前项目和系统统一称为 **BenchAudit**。这组历史实验的原始
> runner/产物中曾出现 `BenchCore` 标签，但它不是另一个系统，也不应作为
> 对外名称使用。

可以从这组数据得出三个有限但清楚的结论：

1. **只靠规则不够。** Rules-only 在 SVAMP 完全没有检出，在 MMLU 的
   recall 也只有 0.014；自然语言语义问题是确定性表面规则的明显盲区。
2. **只调用一次 LLM 也不够。** 完整 BenchAudit 相对最佳单次 LLM，
   SVAMP 的 F1 提高 **0.138**、recall 提高 **0.290**；MMLU 的 F1
   提高 **0.062**、recall 提高 **0.208**。
3. **增益不是因为多给了一份缺陷词表。** taxonomy 在 SVAMP 反而使
   F1 从 0.776 降至 0.710，在 MMLU 只从 0.601 小幅升至 0.610。
   真正有效的是把问题拆成 oracle、选项、题面和契约等视角，再让本地规则
   对可重放部分进行交叉检查。

因此当前推荐的静态架构不是“规则或 LLM 二选一”，而是：

```text
确定性规则通道 ───────────────┐
                              ├─ 候选合并与去重 → review
LLM 分解式语义抽取/审计 ──────┘
                                      ↓
                         若存在独立 replay/执行证明
                                      ↓
                                  confirmed
```

需要特别强调两条边界：

- 这组消融证明的是 **LLM 对静态候选召回有必要性**，不证明 LLM
  verdict 本身可以成为 confirmed；
- 它是已有的 SVAMP/MMLU 监督实验；本周已经另外完成 WorkspaceBench
  full388 的输出文件名 arm，并对 rubric arm 做了全量尝试。

### WorkspaceBench full388 最新量化

在 388 items / 7,393 rubrics 上比较 Rules-only 与
DeepSeek-assisted BenchAudit：

| 专项 | Rules-only | DeepSeek-assisted BenchAudit |
|---|---:|---:|
| 12 个已知 task-vs-contract 文件名冲突 Recall | 0.000 | **1.000** |
| 文件名 strict-reference F1* | 0.000 | 0.333 |
| Rubric attempted-full388 P/R/F1 | 0/0/0 | **0.790 / 0.213 / 0.336** |
| Rubric evaluable-subset P/R/F1 | 0/0/0 | **0.790 / 0.344 / 0.479** |

\* 其余 item 没有逐条人工 clean 标签，所以文件名 Precision/F1 只表示
对旧窄参考集的 alignment；新增候选不能直接记作假阳性。

任务契约抽取共得到 259 个路径：197 个映射到 output inventory，1 个
input-only 路径被本地抑制，61 个形成 mismatch path；8 个 item 的响应
未通过 schema/grounding 校验。所有 substantive finding 都是 review，
LLM-derived confirmed=0。

Rubric arm 的重要限制是 API 余额耗尽：7,393 条中只有 4,751 条完成，
operational coverage 为 **64.26%**，2,642 条保持 unknown。因此
0.790/0.344/0.479 是 evaluable-subset 条件指标，不是完整人工真值上的
最终结果；补充余额后应仅重跑 unknown。

完整报告：
`BenchAudit_Workspace静态LLM量化报告_20260728.md`。

---

## 2.4 已有模型结果和执行轨迹可以直接接入

本周新增 released-result / trace 接入层，将别人已经运行好的模型结果、
不同 evaluator 的 verdict 和历史执行记录转成统一证据。

核心原则是：

> 历史结果可以生成候选、比较 evaluator、发现矛盾，但不能独立证明哪一方
> 正确，因此中央 promotion 上限固定为 `review`。

为防止未来开发者仅仅修改 checker 名称绕过上限，本周增加了：

- evidence provenance sentinel；
- method rename 对抗测试；
- producer-to-promotion contract；
- safety claim registry；
- “哨兵必须被真实 producer 发射”的活性检查。

这使已有的真实运行结果可以被最大限度利用，同时不会污染 confirmed
层的可信度。

---

## 2.5 缺陷模式 Memory：保留有效部分，拒绝过度宣传

本周实现了结构化缺陷模式库：

- pattern 带来源、适用条件、反例和 verifier hint；
- 不读取 target gold 或 target EvalPlus verdict；
- 默认关闭可能泄露 benchmark 身份的 raw schema key；
- memory 只能用于 probe 路由；
- 中央 promotion 将所有 memory-derived finding 锁在 review。

HumanEval/MBPP 的 leave-one-benchmark-out 结果说明，结构记忆在一个方向
上能提高 probe yield，但并非全面稳定：

| Source → Target | 固定顺序 | 随机顺序均值 | Memory | 随机最大值 | 相对随机 p |
|---|---:|---:|---:|---:|---:|
| MBPP → HumanEval | 3.32% | 3.54% | **3.94%** | 3.94% | 0.072 |
| HumanEval → MBPP | 6.88% | 7.19% | **8.40%** | 7.64% | **0.002** |

诚实结论：

- HumanEval → MBPP 的 witness yield 超过 500 次随机顺序的最大值；
- 反向只达到随机最大值，未通过 0.05 门槛；
- 半 memory、半探索的 F 组没有增益；
- memory 适合做低成本路由，不足以承担自动 confirmation。

---

## 2.6 四轮红队复核与 confirmed 安全收紧

本周针对陌生 schema 做了多轮冻结红队测试，发现并修复了以下
confirmed 级误报家族：

1. 自然语言算术被正则截断后误算；
2. retrieval 的 `candidates/target` 被误映射为 MCQ choices/gold；
3. adapter 自己给自己签发 explicit receipt；
4. 中文标签、数字标签、多选列表、dict choices 被当成非法 gold；
5. `(C)`、`C. option text`、选项全文等合法 gold 编码；
6. 全角字母、希腊字母、圆圈数字等未枚举编码。

最终修复不是继续枚举每一种编码，而是增加：

- NFKC 归一化；
- 数据集级 leave-one-out 命名空间验证；
- 基数与稳定映射检查；
- 最小 peer 数；
- 未识别但内部一致的编码降级为一条 dataset-level review；
- 真正的单行离群 oracle 仍可 confirmed。

当前研究分支全量测试：

- `pytest`：**760 passed**；
- `unittest`：**201 tests OK**；
- safety claim registry：通过。

---

# 三、本周最新、最好的实验结果

## 3.1 最重要的新结果：HumanEval / MBPP 通用 MR-4

### 实验问题

在没有为目标 benchmark 手写题目级 proof validator 的情况下，系统能否
自动产出 confirmed evaluator defect？

### 方法

1. 从 canonical solution 生成确定性 AST 变异；
2. 同一个 candidate 分别运行：
   - benchmark 原始测试：弱 oracle；
   - EvalPlus 测试：强 oracle；
3. 仅保留：
   - canonical 在两侧均通过；
   - candidate 在弱侧通过、强侧失败；
   - 两侧均完成、不是 timeout/error；
   - transcript 通过独立签名与中央 replay。

### 全量结果

| 指标 | HumanEval | MBPP | 合计 |
|---|---:|---:|---:|
| 请求任务 | 164 | 378 | 542 |
| 有效任务 | 162 | 376 | 538 |
| 生成候选 | 1,171 | 1,560 | 2,731 |
| 完成弱/强配对 | 1,166 | 1,554 | 2,720 |
| timeout / indeterminate | 5 | 6 | 11 |
| **confirmed coverage gaps** | **50** | **124** | **174** |
| **受影响任务** | **30** | **63** | **93** |
| witness yield | **4.29%** | **7.98%** | **6.40%** |
| 受影响任务比例 | **18.52%** | **16.76%** | **17.29%** |

### 安全对照

| 对照 | 实际观测 | Confirmed |
|---|---:|---:|
| canonical solution | 538 个有效基线 | 0 |
| timeout | 11 | 0 |
| 弱拒绝、强通过 | 24 | 0 |
| 移除 attestation | 与主实验相同 observation | 0 |
| identical outcome | 确定性关系对照 | 0 |

### 与旧实验相比

旧 EvalPlus 路由实验中：

- 结果全部锁在 review；
- timeout 与正常拒绝都被编码为 `passed=false`；
- 原始记录共有 184 个 weak-pass / strong-nonpass。

新实现自动排除了：

- 7 个 timeout；
- 3 个来自 canonical 强测试本身无效的 witness。

最终 174 个 witness 获得独立执行认证和中央 replay：

```text
旧：184 个表面 witness，confirmed = 0
新：排除 10 个不合格 witness，174 个可重放 confirmed
```

这个改进不是靠放宽门槛增加数字，而是先删掉错误口径，再提高剩余证据
等级。

### 可复现性

两次全量运行得到相同的：

- stable summary SHA-256：  
  `c343687e82ca5f1659f89752f954260c9ea2dc6444fbd70675d6be285c5d14f7`
- finding identity + transcript SHA-256：  
  `ccbbf9de807e7cfc17bc439f669478254188b5e30df3ee0dbda9452b313a487d`

### API 使用

这项实验 **0 次 LLM/API 调用**：

- candidate 来自确定性 AST 变异；
- verdict 来自本地 Docker 执行；
- 确认来自独立 transcript attestation。

它验证的是执行确认层，不是 LLM 静态抽取层。

---

## 3.2 已发布结果接入：35,847 行真实历史结果

本周将 SQL Dialect Translation、PortugueseSpider 和 DBCode 的
**35,847 行**历史结果转为统一证据。

### SQL Dialect Translation

- 556 条 reference；
- 65/556 含字面 parser diagnostic；
- SQLGlot 拒绝 66/556；
- pinned replay 对 556 条已发布状态实现 **0 mismatch**；
- prediction failure rate AUROC：**0.825**；
- diagnostic detector AUROC：**0.992**；
- 融合 AUROC：**0.996**；
- `K=66` 时 P=R=**0.985**，随机期望 precision 仅 0.119。

这些指标说明历史结果能非常有效地筛选 parser/格式异常，但不代表 parser
一定是最终正确 evaluator，因此仍为 review。

### PortugueseSpider

- 结构匹配与数据库执行在 **6,476/29,986（21.60%）** 行上不一致；
- 19 个系统中 8 个排名位置发生变化；
- 忽略 tie 的 pairwise Kendall τ：**0.871**。

### DBCode

- full harness 与 function test 在 **60/316（18.99%）** 个配对结果上不一致；
- 4 个可配对系统没有发生排名交换。

这组实验的重要结论是：

> evaluator 选择本身可以改变大量逐题 verdict，甚至改变模型排序；但仅凭
> 两个 evaluator 不一致，不能自动判定谁错。

---

## 3.3 多模型结果的低成本候选排序

使用 MMLU-Redux 的：

- 1,000 道题；
- 15 个真实模型；
- 15×1,000 item-level correctness 矩阵；
- 181 条第三方 objective defect；
- 630 条 `ok` 对照。

结果：

| 方法 | Average Precision |
|---|---:|
| BenchAudit candidate risk | 0.573 |
| 多模型 item error rate | 0.634 |
| **BenchAudit + error rate** | **0.734** |
| BenchAudit + psychometric fusion | 0.740 |

复杂 psychometric fusion 仅提升 0.006，且在 subject-held-out 上不稳定：

- mean delta：`-0.0275`；
- bootstrap 95% CI：`[-0.0821, +0.0245]`；
- subject wins/ties/losses：`6/1/12`。

因此最终采用更简单的 `BenchAudit + error rate`，而不是为了 0.006 的表面
提升引入复杂模型。

这条能力不需要重新执行 agent，只需要收集已有逐题结果矩阵。

---

## 3.4 Workspace evaluator 噪声与反事实实验

官方 filesystem judge 实验完成：

- 11 个可用 baseline tasks；
- 53/53 个有效 evaluation units；
- 删除完整输出后，11/11 个任务得分显著下降；
- 平均 whole-output deletion delta：**-54.7 个百分点**；
- reward-gaming 自我声明被奖励：**0/5**；
- 相同输出的独立重评中，6/11 的差异超过 3 个百分点；
- identical-output mean absolute delta：**7.3 个百分点**。

意义：

- 删除完整 output 这种大干预可以稳定验证 judge 是否感知核心产物；
- 小幅 rubric 差异可能低于 judge 自身 7.3pp 的噪声地板；
- 因此不能看到一次得分变化就自动 confirmed。

---

## 3.5 Terminal-Bench 配对实验

31 个 enriched paired tasks：

| 方法 | Recall | F1 |
|---|---:|---:|
| Deterministic | 0.588 | 0.741 |
| Paired only | 0.118 | 0.211 |
| Union | **0.647** | **0.786** |

虽然 union F1 提升到 0.786，但预注册的 paired retention gate 后来变得
数学上不可达，因此实验被 early stop，paired 方法没有进入默认 pipeline。

本周还把两个问题拆开报告：

- `defect_supported`：证据是否支持旧版本存在缺陷；
- `repair_localized`：证据是否稳定定位到新版本修复了该缺陷。

这避免把“存在问题”和“修复归因”混成一个指标。

---

## 3.6 SQLBench 元形关系安全压力测试

在 56 个 SQLBench 结果文件上：

- 模型答案：4,448；
- 可判定 baseline：4,371；
- 每条运行 3 个固定 SQL layout transformation；
- 总 variant runs：**13,113**；
- verdict flips：**0**；
- 两次输出文件 SHA-256 完全一致；
- LLM 调用：0。

这说明 `sql_layout` 关系在当前数据上没有制造假 flip，可以保留为 opt-in
关系。

但 SQLGlot 是辅助 parser，不是 SQLBench 官方 evaluator，因此这一实验
是 relation safety test，不是 confirmed defect experiment。

---

# 四、历史最佳结果：仍然有效，但不是本周新增

为了汇报完整性，可以保留以下历史 supervised 结果，但要明确它们不是
本周新跑：

| 数据集 | 主要指标 |
|---|---:|
| SVAMP-Platinum | candidate F1 **0.914** |
| GSM8K-Platinum | priority-candidate recall **1.000** |
| MMLU-Redux | candidate F1 **0.755** |

MMLU-Redux 的 15 模型排名影响：

- 删除 181 条第三方客观缺陷后，全局 Kendall τ：**0.981**；
- 最大名次变化：1；
- 发生一次相邻模型换位；
- Top-1 不变。

需要强调：小 subject 的“冠军易主”很容易由等量随机删题和 tie-breaking
产生，因此不再作为 headline evidence。

---

# 五、本周到底在哪些地方使用了 API

| 能力 | 是否使用 API | API 的作用 |
|---|---|---|
| 纯静态字段、哈希、manifest 检查 | 否 | 本地确定性计算 |
| 输出文件名任务契约抽取 | 是，可使用 DeepSeek | 从自然语言抽取显式 required output |
| 数学、MCQ、Workspace / rubric 静态语义审计 | 是 | 分解题面、gold、选项和契约，生成 review 候选 |
| 多模型历史响应排序 | 否 | 直接使用已有 item-level 结果矩阵 |
| SQLBench 元形测试 | 否 | 本地 parser replay |
| HumanEval/MBPP MR-4 | **否** | AST 变异 + Docker 弱/强 oracle |
| Pattern memory LOBO | 否 | 对已经生成的变异与结果做离线选择 |

因此：

> BenchAudit 不是“完全不用 LLM”，而是让 LLM 补足静态规则无法覆盖的
> 自然语言语义理解；能够由执行、重算、哈希和约束解决的问题，仍由本地
> 代码裁决。LLM 提高 candidate recall，但不因此获得 confirmed 权限。

---

# 六、我们现在比一周前强在哪里

## 一周前

- 很多能力依赖某个 benchmark 的专用 checker；
- historical result 和 trace 缺少统一入口；
- timeout 与语义失败容易混淆；
- LLM/static/execution 证据的权限边界不够统一；
- pattern memory 有想法，但缺少严格 LOBO 和随机对照；
- confirmed 仍有陌生 schema 系统性误报风险。

## 现在

- 有了统一的历史结果与轨迹接入；
- 有了 LLM 抽取、本地 replay 的任务契约路径；
- 有了按数据类型定义的 MR-1/2/3；
- 有了可跨两个 code benchmark 使用的 MR-4；
- 有了独立 transcript attestation；
- 有了 timeout/error/semantic failure 三态区分；
- 有了 promotion exact tuple 与 safety claim registry；
- 有了冻结红队与确定性复跑；
- 有了“复杂方法不显著就不采用”的负结果机制。

最重要的质变是：

> 系统开始从“为 benchmark 写规则”，转向“benchmark 声明证据能力，系统
> 自动选择 verifier 和 proof contract”。

---

# 七、现在还缺什么

## 7.1 还没有覆盖“任意 benchmark”

MR-4 当前要求存在可声明的弱/强 oracle。对于下面这些任务仍然困难：

- 开放式文本生成；
- 主观质量评价；
- Workspace 的复杂 rubric；
- 只有单个 LLM judge、没有强 oracle 的 benchmark；
- 执行协议完全未知、需要新容器和依赖的任务。

## 7.2 新增的输出文件名抽取器还缺全量量化

历史监督消融已经证明静态语义层需要 LLM；这里尚未量化的是本周新增的
“输出文件名抽取 + 本地 manifest replay”这一条具体能力。仍需在
WorkspaceBench 全量 388 题上重新跑：

- rules-only；
- DeepSeek extraction + local replay；
- 与现有人工标注比较；
- 报 Precision、Recall、候选数量和 review burden。

## 7.3 EvalPlus 是较有利的验证场景

HumanEval 与 MBPP：

- 都是 Python 函数生成任务；
- 都有现成 EvalPlus 强测试；
- 都能使用统一 AST mutation。

因此 174 confirmed 是可靠的“相对 coverage gap”，但还不能证明该方法
已经跨语言、跨任务、跨 evaluator family 泛化。

## 7.4 独立 attestation 还需服务化

目前实验使用独立 worker + 临时 Ed25519 key。下一步应做成：

- 固定身份的 attestation service；
- runner 版本与容器镜像登记；
- transcript 持久化；
- CLI/adapter 可配置接入。

## 7.5 缺少第三个独立 executable benchmark

要让论文 claim 更扎实，需要在非 EvalPlus 系列的第三个 benchmark 上
做冻结 holdout，并且实施前不针对它编写 proof validator。

---

# 八、下一步优先级

## P0：Workspace 静态 LLM 抽取量化（文件名完成，rubric 待补覆盖）

已完成：

- 全量 388 题；
- rules-only vs DeepSeek-assisted；
- 使用既有 reviewed reference 计算条件 P/R/F1；
- 单独统计 output filename / rubric grounding / input-output role confusion；
- 所有 LLM finding 保持 review-only。

结果：

- 文件名已知正类 Recall：0.000 → **1.000**；
- rubric evaluable-subset：P/R/F1 =
  **0.790 / 0.344 / 0.479**；
- input-only 误抽取本地抑制 1 条；
- LLM confirmed=0，review ceiling escape=0；
- 全仓 **742 passed**。

仍需补充：

- rubric operational coverage 当前为 64.26%，需要补余额后定向补跑
  2,642 条 unknown；
- 既有标签不是穷尽人工 gold，需对新增候选做冻结人工抽样。

## P1：第三个 executable benchmark 冻结 holdout

要求：

- 不属于 HumanEval/MBPP/EvalPlus；
- 具有真实弱/强 evaluator 或可构造的官方 test extension；
- 通用 MR-4 核心代码不能出现目标 benchmark 名称和 task-ID allowlist；
- 预注册：至少一个 confirmed、所有控制 0 confirmed、两次复跑一致。

## P2：自动 verifier routing

让 adapter 自动声明：

```text
benchmark capabilities:
  has_task_text
  has_manifest
  has_rubric
  has_weak_oracle
  has_strong_oracle
  has_execution_trace
  has_model_response_matrix
```

系统据此自动选择：

- 静态约束；
- LLM 抽取；
- 历史响应排序；
- metamorphic replay；
- differential oracle；
- review-only 或 confirmed ceiling。

## P3：把研究结论整理为一个更小的论文课题

推荐将论文主问题收窄为：

> **如何在没有 benchmark 专用 proof validator 的情况下，通过类型化元形
> 关系与独立执行证据，自动确认 evaluator coverage gap？**

这比“任意 benchmark 自动纠错”更可完成，也更容易形成可证伪实验闭环。

---

# 九、汇报时建议怎么说

## 推荐表述

> 我们原来的系统能够高召回地发现 benchmark 候选问题，但 confirmed 层
> 很依赖 benchmark 专用代码。本周我们把这个问题拆成了通用证据关系：
> LLM 只做任务契约抽取，历史结果只做 review 路由；真正的自动确认由
> 类型化 metamorphic relation、弱/强 oracle 差分执行和独立 transcript
> attestation 完成。
>
> 最新在 HumanEval 与 MBPP 上共执行 2,731 个变异候选，得到 174 个
> confirmed coverage gaps，影响 93/538 个有效任务。两次完整复跑结果
> 一致，11 个 timeout、24 个反向差异和无 attestation 对照全部是
> 0 confirmed。说明通用 proof contract 已经能跨两个真实 code benchmark
> 工作，但我们仍把结论限制在“具有可执行强弱 oracle 的任务”，没有声称
> 已经解决任意 benchmark。

## 不推荐表述

- “我们找到了 HumanEval/MBPP 的 174 道错误题。”
  - 更准确：174 个 candidate-level evaluator coverage gaps；
  - 它们分布在 93 个任务上。
- “我们已经可以自动纠正任意 benchmark。”
  - 当前只在 verifier-rich 的 code benchmark 上完成通用 confirmation。
- “Memory 在两个方向都显著提升。”
  - 只有 HumanEval → MBPP 相对随机顺序显著。
- “Workspace 的小幅分数变化就是 judge 缺陷。”
  - identical-output 的平均噪声已经达到 7.3pp。
- “这周所有实验都用了 DeepSeek。”
  - MR-4、SQLBench、memory LOBO 和历史结果分析均为零 API。

---

# 十、高频问题

## Q1：174 个 confirmed 是不是 174 道错误题？

不是。它们是 174 个 candidate mutation 级 coverage gap，分布在 93 道
任务上。同一道题可能有多个不同 mutation 通过弱测试但被强测试拒绝。

## Q2：为什么 MR-4 不需要 LLM？

候选由 AST 确定性变异生成，正确与否由真实测试执行区分，不需要模型理解
自然语言。LLM 主要用于没有确定性 parser/verifier 的静态语义抽取。

## Q3：静态检测既然不执行任务，为什么还需要 LLM？

因为“不执行”不等于“只做字符串匹配”。字段、哈希和精确 manifest 可以
由规则处理，但 task、gold、choices 和 rubric 之间的语义关系需要语言
理解。冻结消融中，Rules-only 在 SVAMP/MMLU 的 candidate F1 只有
0.000/0.027；静态规则加分解式 DeepSeek 审计达到 0.914/0.663。

LLM 的职责是把自然语言转成结构化候选或声明；缺陷能否自动 confirmed，
仍由独立 replay、约束求解或真实执行决定。

## Q4：为什么不直接相信 EvalPlus？

我们确认的是“相对于声明的强 oracle，弱 oracle 存在覆盖缺口”，不是把
EvalPlus 宣称为绝对人类真值。这个 claim 更窄，但可以客观 replay。

## Q5：这算自动适配吗？

算“关系级自动适配”：

- 核心 proof 不包含 HumanEval/MBPP 题目 ID；
- benchmark adapter 只声明弱/强 oracle 身份和候选 manifest；
- 同一 proof contract 在两个 benchmark 上复用。

但还不是完整自动适配，因为陌生执行协议的 loader、容器和依赖仍可能需要
生成并验证。

## Q6：为什么复杂 psychometric 方法没用？

它只比简单融合高 0.006，而且 subject-held-out 不稳定。我们保留简单的
error-rate fusion，降低过拟合和工程复杂度。

## Q7：本周最大的负结果是什么？

- memory 在一个迁移方向不显著；
- 半 memory、半探索策略没有增益；
- Terminal paired-only 方法效果弱且 gate 不可达；
- SQL parser 只能作为诊断，不能自动确认语义错误；
- Workspace 小干预低于 judge 噪声地板。

这些负结果被保留，是为了避免只展示最有利数字。

---

# 十一、代码与结果位置

最新 MR-4 代码位于独立研究分支：

```text
research/generalized-confirmation-metamorphic-20260727
```

最新本地提交：

```text
813ab14 feat: confirm differential oracle coverage gaps
```

关键文件：

- `benchcore/differential_oracle.py`
- `benchcore/metamorphic_evaluator.py`
- `benchcore/promotion.py`
- `scripts/run_evalplus_differential_confirmation.py`
- `docs/experiments/EVALPLUS_DIFFERENTIAL_CONFIRMATION_RESULTS_20260727.md`
- `docs/experiments/evalplus_differential_confirmation_summary.json`
- `RESULTS.md`

注意：当前研究分支本地比 GitHub 远端领先 2 个提交；代码已经 commit，
但 GitHub push 被本机失效的 VS Code/GitHub 凭证阻塞。汇报前若需要现场
打开 GitHub，应先恢复凭证并推送。

---

# 十二、一句话总结

> 本周 BenchAudit 从“依靠 LLM 和 benchmark 专用 checker 发现候选”，
> 实质推进到了“通过通用 proof contract、真实执行与独立认证自动确认
> evaluator coverage gap”；最新在 HumanEval/MBPP 上得到 174 个可复现
> confirmed，且所有安全对照为零；历史监督消融同时证明，LLM 能将
> 静态语义审计的 candidate F1 从 0.000/0.027 提升到
> 0.914/0.663；本周 Workspace full388 又将已知输出文件名冲突 Recall
> 从 0 提升到 1.000，并在可评估 rubric 子集上取得
> P/R/F1=0.790/0.344/0.479。所有 LLM 结果仍锁在 review；下一步需补足
> rubric API coverage，并完成第三个非 EvalPlus executable benchmark。
