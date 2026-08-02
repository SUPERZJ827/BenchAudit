# BenchAudit 简历面试冲刺指南

> 更新时间：2026-07-23  
> 适用场景：普通技术面试、LLM Evaluation / Benchmark / 数据质量岗位  
> 项目目录：`/home/zhoujun/llmdata/after623`  
> 目标：明天下午面试时，能够讲清项目、守住数字、回答技术追问，并诚实说明本人工作方式和系统边界。

---

## 0. 时间紧张时怎么使用本文

如果今晚只有 2～3 小时，按下面顺序准备：

1. 背熟第 1 节的一句话、30 秒和 2 分钟介绍；
2. 能独立画出第 3 节的数据流；
3. 吃透第 4 节的三个核心设计；
4. 熟记第 6 节五组最重要实验，但不要只背数字；
5. 逐题回答第 9 节高频追问；
6. 看第 11 节“哪些话不能说”；
7. 明天面试前用第 14 节做一次 30 分钟模拟。

不需要把仓库所有代码背下来。优先掌握两条主线：

- `audit`：未知 benchmark 如何被解析、规划、检查和证据分级；
- `triage-responses`：如何利用已有模型运行结果，低成本缩小需要复核的题目范围。

---

## 1. 项目介绍：三个长度版本

### 1.1 一句话版本

> BenchAudit 是一个审计 benchmark 本身是否可靠的框架：它检查题目、标准答案、输出约束和评分器之间是否一致，并把静态规则、历史模型响应、LLM 语义判断和真实执行证据分层，避免把模型低分直接误认为模型能力差。

### 1.2 30 秒版本

> 我做的项目叫 BenchAudit，目标是自动发现 LLM 和 Agent benchmark 里的题目、gold answer、rubric 和 evaluator 问题。系统先把不同数据集统一表示为 task、context、output contract、oracle 和 evaluator，再识别 QA、SWE-bench、WorkspaceBench 或 TerminalBench 等类型，选择对应检查器。它最重要的设计是证据分级：LLM 和统计异常只进入 review，只有可以重算、重放或执行验证的证据才可能 confirmed。最近我又加入了历史响应分诊，在 MMLU-Redux 的 15 个模型、1000 道题上，把候选排序 AP 从 0.573 提高到 0.734，而且不需要重新调用模型完成题目。

### 1.3 两分钟版本

> 这个项目来自一个很实际的问题：benchmark 分数不只取决于模型能力，还取决于题目有没有歧义、gold 是否正确、输出格式是否合理，以及 evaluator 有没有过严或漏检。如果这些地方有问题，排行榜测到的可能是评测噪声，而不是模型能力。
>
> 我的第一步是把 benchmark 建模为五个核心 artifact：task、context、output contract、oracle 和 evaluator。输入经过字段映射后形成统一 `BenchmarkItem`，系统再扫描数据和附件，识别 benchmark family，并生成 capability-aware audit plan。这样没有 LLM、没有容器或缺少 evaluator 时，系统会明确写 `unsupported`，而不是把“没检查”写成“没有问题”。
>
> 检测层分为三类。第一类是便宜的确定性检查，例如字段、重复、answer contract、文件和 rubric 一致性。第二类是结构化 LLM 检查，用于语义歧义、错答案或 rubric 不一致，但始终保持 review。第三类是 replay、metamorphic、mutation 和容器执行，用来验证 evaluator 是否拒绝合理解、接受错误解。
>
> 最近的改进是复用已有模型运行轨迹。MMLU-Redux 已有 15 个模型对 1000 题的逐题结果，我把静态审计分数与题目错误率融合，AP 从 0.573 提高到 0.734。复杂心理测量融合整体只再提高 0.006，而且跨 subject 不稳定，所以最后选择了更简单、可解释的 error-rate 方案。所有行为信号都是 review-only，不能直接证明 benchmark 有错。
>
> 项目现在已经能在多种 benchmark 上自动规划并生成高召回候选，也能对部分确定性和可执行问题给出强证据；距离“任意 benchmark 自动纠错”仍缺统一轨迹接入、更多领域 verifier、真正跨数据集 holdout，以及把研究分支完整集成。

### 1.4 五分钟版本的组织方式

不要连续讲五分钟代码。按以下顺序展开：

1. **问题**：benchmark 是测量系统，本身也会错；
2. **抽象**：五类 artifact；
3. **系统**：自动 mapping、family detection、audit plan；
4. **方法**：规则、LLM、行为信号、执行 verifier；
5. **安全原则**：confidence 不等于 proof，默认 fail-closed；
6. **代表实验**：MMLU 响应分诊、Workspace 反事实、DS-1000 执行；
7. **负结果**：复杂 psychometric 和语义 gate 没有稳定增益；
8. **边界与下一步**：TraceBundle 和领域 verifier。

---

## 2. 面试官首先要听懂的问题定义

### 2.1 Benchmark 不是一个普通数据表

可以写成：

```text
模型输出 = Model(task, context, environment)

最终得分 = Evaluator(
    model_output,
    oracle,
    output_contract,
    rubric/tests
)
```

模型低分可能来自：

- task 含糊；
- 缺少必要 context；
- gold answer 写错；
- 合理答案没有被 evaluator 接受；
- 错误答案没有被 evaluator 拒绝；
- rubric 超出任务要求；
- 环境、parser 或 harness 出错；
- judge 自身不稳定。

因此项目不是“再做一个答题模型”，而是在检查整个测量链。

### 2.2 五个必须分清的 artifact

| Artifact | 含义 | 例子 |
|---|---|---|
| Task | 要模型完成什么 | 回答问题、修改仓库、制作 PPT |
| Context | 完成任务需要的信息 | passage、表格、输入文件、代码仓库 |
| Output contract | 合法输出长什么样 | A/B/C/D、数字、patch、文件集合 |
| Oracle | 什么结果算正确 | gold、reference patch、rubric、目标状态 |
| Evaluator | 如何把输出变成分数 | exact match、tests、rubric judge、脚本 |

最重要的区分：

> Oracle 定义正确性，evaluator 实现正确性判断。Oracle 可以是对的但 evaluator 写错；evaluator 也可以正常执行，但 oracle 本身错误。

WorkspaceBench 没有单个标量 gold，不代表没有 oracle。它的 oracle 更接近 rubric 集合、输出文件约束和最终 workspace 状态。

### 2.3 Evaluator 的 soundness 与 completeness

| 现象 | 问题 |
|---|---|
| 错误解也能通过 | evaluator 不够 sound，存在漏检 |
| 合理等价解被拒绝 | evaluator 不够 complete，过于严格 |

这正是 mutation testing 与 metamorphic testing 分别要探索的方向。

---

## 3. 必须能独立画出的系统流程

```text
未知 benchmark 文件 / 目录 / repository
                  |
                  v
        load_rows + infer_mapping
                  |
                  v
             BenchmarkItem
       task/context/gold/evaluator/...
                  |
                  v
       package scan + artifact inventory
                  |
                  v
   detect_benchmark_family + build_audit_plan
                  |
          +-------+---------+
          |                 |
          v                 v
 确定性/数据集检查       LLM/执行能力检查
          |                 |
          +-------+---------+
                  v
              Violation
                  |
                  v
       central promotion policy
       confirmed/review/unknown
                  |
                  v
         JSON / Markdown report

已有逐题模型响应（可选）
                  |
                  v
     ID join + coverage/diversity gates
                  |
                  v
  audit risk + response error rate 融合
                  |
                  v
        review-only 候选排序
```

### 3.1 代码阅读顺序

| 顺序 | 文件 | 需要会讲什么 |
|---:|---|---|
| 1 | `benchcore/schema.py` | `BenchmarkItem`、`Violation`、证据等级 |
| 2 | `benchcore/field_mapping.py` | 陌生字段怎样映射到统一槽位 |
| 3 | `benchcore/loader.py` | 输入怎样变成稳定 item |
| 4 | `benchcore/package_scan.py` | 文件、附件和环境 artifact 扫描 |
| 5 | `benchcore/planning.py` | family detection 与 capability-aware plan |
| 6 | `benchcore/checkers.py` | item-level 和 dataset-level 检查 |
| 7 | `benchcore/auditor.py` | 检查执行、ledger 和证据融合 |
| 8 | `benchcore/promotion.py` | 为什么某条 finding 能或不能 confirmed |
| 9 | `benchcore/evaluator_execution.py` | 等价探针、错误 mutation 和执行结果 |
| 10 | `benchcore/response_triage.py` | 历史响应矩阵与候选排序 |
| 11 | `benchcore/cli.py` | 用户真正怎样调用整套能力 |

---

## 4. 三个最值得讲的技术设计

### 4.1 设计一：Artifact-aware 自动适配

#### 解决什么问题

不同 benchmark 的字段、正确性语义和运行方式不同：

- MMLU：question、choices、gold label；
- DS-1000：代码上下文、reference solution、可执行 harness；
- SWE-bench：issue、repository、patch、tests；
- WorkspaceBench：task、输入文件、输出文件、多个 rubric；
- TerminalBench：instruction、environment、terminal trajectory、tests。

如果假设所有数据集都有一个标量 gold，就会在 Agent benchmark 上产生系统性误报。

#### 当前做法

1. 自动推断常见字段；
2. 统一到 `BenchmarkItem`；
3. 扫描目录和附件，建立 artifact inventory；
4. 根据 schema、文件名、evaluator 和 output contract 判断 family；
5. `AuditPlan` 为每项检查标出 selected、skipped、unsupported；
6. 只有显式 profile 才开启某些付费或高风险能力。

#### 为什么不是“真正任意 benchmark”

当前自动适配主要覆盖：

- 非可执行 schema 映射；
- 已知 family 的 checker 组合；
- 受限、可验证的 declarative adapter。

对全新执行协议，系统仍不知道：

- 应该启动什么容器；
- 如何安装依赖；
- 怎样提交输出；
- 怎样解析 evaluator；
- 什么算一次完整 trajectory。

所以正确说法是：

> 已实现 schema 和审计策略层的自动适配；全新执行协议的通用接入还没有完成。

### 4.2 设计二：Fail-closed 证据分级

`Violation.confidence` 与 `evidence_tier` 是两件事：

- confidence：检测器有多相信自己的判断；
- evidence tier：证据是否足以免人工确认。

当前三档：

| Tier | 含义 | 典型来源 |
|---|---|---|
| confirmed | 可重算、可重放、前提明确 | 确定性矛盾、可信执行、live artifact replay |
| review | 值得优先看，但仍可能是难题或语义争议 | LLM、响应异常、统计分歧 |
| unknown | 缺数据、映射或能力，不能下结论 | 缺 evaluator、adapter 未验证、执行不可用 |

核心原则：

> Confidence is not proof。即使 LLM 置信度 0.99、多模型一致投票，也不能自动变成 confirmed。

为什么要中央 promotion policy：

- checker 只负责产生 observation；
- `promotion.py` 统一检查 detection method、evidence level、defect type 和 proof 前提；
- 未注册组合默认降级；
- 避免某个新 checker 自己给自己授予 confirmed 权限。

这是项目最有工程价值的部分之一。

### 4.3 设计三：历史响应先分诊，昂贵验证后置

#### 背景

完整让多个模型重新执行 benchmark 很贵，而且不同代码/Agent benchmark 还需要专用容器。现实中经常已经存在 leaderboard responses、trial logs 或 evaluator traces。

#### 最新实现

`benchcore/response_triage.py` 和 CLI `triage-responses` 支持：

- 每题一个 `model -> correct` 字典；
- `(item_id, model_id, correct)` 长表；
- 一个模型一个 JSONL 文件的目录。

安全与数据质量门禁：

- 永远按 `item_id` join，不按文件行号堆叠；
- 重复 `(item_id, model_id)` 直接报错；
- `correct` 只接受 JSON boolean 或 0/1；
- 检查最少模型数、题目响应数和模型覆盖率；
- 唯一 correctness pattern 太少时关闭融合；
- 区分独立模型、单模型多提示、重复运行和来源未知；
- 输出 Wilson 95% 区间；
- 所有结果固定 `review_only=true`。

#### 为什么错误率能帮助找错

如果很多本来能力较高、来源不同的模型都在同一道题上异常失败，该题可能：

- 非常困难；
- 表述含糊；
- gold 错；
- evaluator 不接受等价表达；
- 依赖缺失信息。

错误率不能区分这些原因，所以只能决定“先看哪一道题”，不能证明题目有错。

#### 为什么最后选择简单融合

在 MMLU-Redux 上：

- BenchAudit AP：0.573；
- error rate AP：0.634；
- 简单融合 AP：0.734；
- 复杂 psychometric fusion：0.740。

复杂方法整体只提高 0.006，而且逐 subject 平均反而低 0.0275，置信区间跨 0，因此没有把 tetrachoric/Rasch 工程化。这个选择体现的是：

> 优先选择跨切分稳定、可解释、容易维护的方法，而不是只选择整体表中最高的数字。

---

## 5. 四类 benchmark 分别怎样审计

### 5.1 普通 QA / MCQ

主要检查：

- gold 是否落在合法答案空间；
- 多个选项是否重复或都可成立；
- 数值、单位、ratio、set/compound answer 是否等价；
- 题目是否缺上下文或含歧义；
- 多模型响应是否出现异常高错误率。

重要边界：

- MCQ 的“答案错”通常需要语义判断；
- LLM 认为 gold 错时只能 review；
- 陌生标签编码不能被误判成坏 gold；
- 数据集内部一致但系统不认识的编码属于覆盖盲区，而不是 benchmark 缺陷。

### 5.2 代码 benchmark / DS-1000

三种探针思路：

1. `P0 gold replay`：参考答案是否能通过自己的 harness；
2. `P1 equivalent implementation`：行为等价实现是否被拒绝；
3. `P2 behavioral mutant`：行为不同的错误实现是否仍通过。

关键思想：

> LLM 只提出探针，真实执行负责裁决。

但当前仍有信任域边界：如果探针执行和最终差异裁决处于同一个不可信 driver，benchmark 代码可能 monkeypatch 比较器。因此最新安全口径是把 `shared_untrusted_driver` 保持 review，不能把历史结果继续称为自动 confirmed。

### 5.3 WorkspaceBench

它不是“一个答案和一个 gold”，而是：

- 多个输入文件；
- 一个或多个输出文件；
- 多条 rubric；
- 文件系统中的实际内容；
- LLM judge 或确定性 verifier。

适合的方法：

- 文件名、文件数量、可读性和格式检查；
- rubric 与 task/output contract 对齐；
- 删除文件或局部内容的反事实实验；
- identical-output 独立复评，估计 judge 噪声；
- AB/BA 顺序平衡，避免位置偏差。

不适合的方法：

- 看到没有标量 gold 就报 `missing_oracle`；
- 仅凭单次 LLM judge 的分数变化确认缺陷；
- 把输出文件本身不符合隐藏 rubric，直接当成 benchmark 设计错误。

### 5.4 TerminalBench

主要证据来自：

- task 定义；
- environment 和 tests；
- 版本差异；
- 历史 execution transcript；
- 具体 claim 在旧版和新版中的支持情况。

必须拆分：

- `defect_supported`：这个 claim 本身是否有证据；
- `repair_localized`：新版是否真的修复了该 claim。

真实缺陷可能在两个版本都存在，因此“旧版有、新版没有”只能证明修复定位，不能作为缺陷存在的唯一定义。

---

## 6. 必须会解释的最新量化结果

### 6.1 结果总表

| 实验 | 数据与规模 | 主要结果 | 正确结论 |
|---|---|---|---|
| SVAMP 监督缺陷检测 | Pilot 100，38 个已知缺陷 | Candidate P/R/F1 = 0.860/0.974/0.914 | 高召回 review queue 有效；不是 confirmed F1 |
| MMLU 历史响应分诊 | 1000 题，15 模型，181 objective defects + 630 ok | Audit AP 0.573；error 0.634；融合 0.734 | 历史响应能低成本改善排序 |
| MMLU 复杂融合稳健性 | 57 subjects，19 个可比较 subject | psych 比 error：整体 +0.006；subject 均值 -0.0275，CI [-0.0821, 0.0245] | 不采用复杂 psychometric |
| MMLU 排名影响 | 1000 题，15 模型，剔除 181 客观缺陷 | Kendall τ=0.981；最大变化 1 位 | 缺陷可造成真实相邻换位，但全局影响较小 |
| SVAMP 单模型多提示 | Full 300，8 个 DeepSeek views | error AP 0.554；融合 AP 0.528 | 同模型视角有信号，但不能替代独立多模型 |
| SVAMP 行为→语义级联 | 行为 Top100/300 送 DeepSeek | AP 0.589→0.581；P@20 0.700→0.750 | LLM 解释有用，但不应自动重排 |
| Workspace 官方反事实 | 11 有效任务，53 judge 单元 | 整文件删除 11/11；平均 -54.7pp；identical mismatch 6/11 | 明显破坏可检测；细粒度单次 judge 噪声较大 |
| Terminal 配对试点 | 31 题子集，150 trials，131 valid | deterministic F1 0.741；union 0.786；paired 0.211 | 联合数值提高，但预注册主门槛失败 |
| DS-1000 最新执行 | 60 题，609 probes | 224 equivalent；235 mutant；226 killed；7 survived | 探针层可运行，但当前信任域下保持 review |

### 6.2 怎样解释 SVAMP F1=0.914

必须完整说：

- 样本：SVAMP-Platinum 固定 pilot 100；
- 已知缺陷：38；
- Candidate precision：0.860；
- Candidate recall：0.974；
- Candidate F1：0.914；
- 找回：37/38 个已知缺陷；
- candidate 是高召回候选层，不是自动确认；
- 该数字来自特定运行，LLM 即使 temperature=0 也可能有波动；
- 更稳妥的口头说法是“约 0.90 candidate F1”。

F1 公式：

```text
F1 = 2 * Precision * Recall / (Precision + Recall)
```

### 6.3 怎样解释 MMLU AP=0.734

主评估只比较：

- 181 条第三方标注的客观缺陷；
- 630 条 `ok`；
- 其他主观或专家标签不混入主指标。

15 个模型文件各有 1000 题，但文件行顺序不同，所以必须按 `item_id` join。

```text
BenchAudit 静态/语义风险 AP = 0.573
题目多模型错误率 AP       = 0.634
两者简单融合 AP           = 0.734
```

AP 是 Average Precision，适合正负样本不均衡的候选排序：

- 排名靠前的真缺陷越多，AP 越高；
- 它综合了不同阈值下的 precision-recall；
- 不是准确率，也不是“73.4% 的题判断正确”。

### 6.4 为什么不采用最高的 0.740

复杂 psychometric fusion 整体 AP=0.740，比简单方案高 0.006，但：

- 逐 subject 平均差为 -0.0275；
- Bootstrap 95% CI 为 `[-0.0821, +0.0245]`；
- 19 个 subject 胜/平/负为 6/1/12；
- 5 个 fold 只有 3 个为正。

所以不能仅凭整体最高值选择复杂方法。

这是非常好的面试回答：

> 我把模型选择标准从“单表最好”改成“跨 subject 稳定且成本合理”。复杂方法没有证明稳定增益，所以生产实现采用简单融合。

### 6.5 怎样解释排行榜变化

剔除 MMLU-Redux 的 181 条客观缺陷后：

- 15 模型全局 Kendall τ：0.981；
- 最大名次变化：1；
- 第 12/13 名发生相邻换位；
- Top-1 不变。

Kendall τ：

- 1：排序完全一致；
- 0：没有单调一致性；
- -1：排序完全相反。

可以说：

> 缺陷没有颠覆整个榜单，但在密集 leaderboard 上足以造成真实相邻换位。

不能说：

> 多个学科冠军易主证明缺陷显著改变排名。

因为等量随机删题对照显示，细分 subject 的冠军翻转没有统计显著性，很多来自小样本和 tie-break。保留下来的稳健结论是全局相邻换位和个别敏感单点，而不是“9 个学科被颠覆”。

### 6.6 Workspace 结果怎样讲

官方文件系统 judge 实验：

- 11 个有效 baseline 任务；
- 53/53 judge 单元成功；
- 删除整个输出：11/11 显著降分；
- 平均下降 54.7 个百分点；
- gaming 自我声明：0/5 被错误奖励；
- 完全相同产物独立复评：6/11 的总分差超过 3 个百分点；
- identical 平均绝对变化：7.3 个百分点。

结论：

> Judge 对明显缺失非常敏感，但细粒度内容变动的信号小于自身复评噪声。因此必须加入 identical control 和定向 rubric 反事实，不能只看一次总分。

### 6.7 Terminal 负结果怎样讲

31 题富集子集：

- deterministic F1：0.741；
- paired-only F1：0.211；
- union F1：0.786；
- identical verdict mismatch：0/70；
- 150 trial 中 131 valid、19 invalid。

虽然 union 数字更高，预注册的“保留旧 LLM 增量 TP”门槛已经数学上不可达，所以实验被判失败并早停。

正确说法：

> 我们没有因为 union F1 好看就宣布成功。配对协议能过滤噪声，但 recall 损失过大，所以没有进入默认流水线。

### 6.8 DS-1000 结果怎样讲

最新 60 题执行：

- 60 个脚本完成，59 个环境完整；
- 609 个 probes；
- 224 个 validated equivalent；
- 235 个 validated mutant；
- 226 个 mutant killed；
- 7 个 survived。

历史人工复核发现过：

- id=11：评测器对 timezone 核心属性不敏感；
- id=300：scalar 与 length-1 array 因 broadcasting 被认为相等。

但当前面试必须使用更新后的安全口径：

> 这些是有价值的执行候选和人工复核案例；由于旧协议中执行与裁决共享不可信 driver，不能继续宣传为当前系统自动 confirmed 的结果。

---

## 7. 最新代码主线：`triage-responses`

这是明天最值得深入准备的代码，因为它是当前 checkout 的最新正式提交。

### 7.1 输入

三种响应格式：

```json
{"id": "q1", "correct": {"model-a": true, "model-b": false}}
```

```json
{"item_id": "q1", "model_id": "model-a", "correct": true}
```

```text
answers/
  model-a.jsonl
  model-b.jsonl
```

### 7.2 为什么一定按 ID join

MMLU 的 15 个模型文件虽然都有相同 1000 个 ID，但行顺序并不一致。

错误实现：

```python
matrix = np.stack([file_a_correct, file_b_correct])
```

这会静默把不同题目的答案对齐，程序不报错，但统计完全错误。

正确实现：

```python
responses[item_id][model_id] = correct
```

这也是一个很好的数据工程面试案例：最危险的不一定是 crash，而是“结果看起来正常的 silent corruption”。

### 7.3 为什么严格解析 boolean

Python 中：

```python
bool("false") is True
```

如果直接 `bool(value)`，字符串 `"false"` 会被当作正确答案。代码只接受：

- JSON `true/false`；
- 整数 `0/1`。

其他值直接失败。

### 7.4 为什么拒绝重复 pair

同一个 `(item_id, model_id)` 出现两次，即使值相同也拒绝，因为：

- 可能是重复导出；
- 可能让某个模型被重复加权；
- 无法确定应该覆盖、平均还是保留；
- 静默处理会污染 error rate。

Fail fast 比猜测用户意图更安全。

### 7.5 为什么检查 pattern diversity

如果所有“模型列”其实是同一个模型复制八次，它们不会提供八份独立证据。

系统检查每题 correctness pattern 的多样性，并要求调用者声明：

- `independent-models`；
- `single-model-views`；
- `repeated-runs`；
- `unspecified`。

多样性不足时关闭融合，而不是继续输出一个虚假的高置信度分数。

### 7.6 为什么输出 Wilson interval

5 个模型中 4 个答错，与 100 个模型中 80 个答错，点估计都是 0.8，但不确定性完全不同。

Wilson 区间比简单的正态近似更适合：

- 二项分布；
- 样本较小；
- 比例接近 0 或 1。

它提醒下游用户：错误率只是有限样本估计。

### 7.7 生产 CLI 示例

```bash
PYTHONPATH=. python -m benchcore.cli triage-responses \
  reports/ranking_impact/answers \
  --report reports/ranking_impact/audit_full1000.json \
  --panel-kind independent-models \
  --minimum-models 5 \
  --audit-score-mode priority-risk \
  --out reports/triage.json \
  --md reports/triage.md \
  --print-summary
```

### 7.8 面试官让你现场扩展时

可选的小需求：

- 新增 `latency_ms` 或 token cost；
- 增加模型组织字段，避免同组织模型被当成完全独立；
- 输出 Top-K 候选的响应 pattern；
- 加入 per-subject 分层错误率；
- 对缺失响应做更严格的 missingness 诊断。

回答时先写测试，再改 loader 或 fusion。

---

## 8. 实验方法论：项目真正的亮点

### 8.1 预注册与冻结协议

在看结果前固定：

- 数据和 sample manifest；
- 主指标；
- 对照方法；
- 成功门槛；
- 早停规则；
- label 读取阶段；
- protocol 和输入 SHA-256。

目的不是形式主义，而是防止：

- 看到结果后换指标；
- 只报告最好的一次；
- 改采样直到显著；
- 把 exploratory 结果冒充 confirmatory 结果。

### 8.2 标签与特征物理隔离

MMLU 响应排序时：

- feature 阶段只读取模型 correct/incorrect 和审计 finding；
- `error_type` 标签只在评估阶段读取；
- 能力或错误率估计不能用标签过滤题目。

这样避免 target leakage。

### 8.3 对照的重要性

项目中最典型的三个对照：

1. 排名变化需要等量随机删题；
2. Workspace 变体需要 identical-output 复评噪声；
3. Terminal A/B 判断需要 AB/BA 顺序平衡。

没有对照时，“有变化”并不能说明变化来自 benchmark 缺陷。

### 8.4 保留负结果

仓库中值得主动讲的负结果：

- 同一模型增加温度采样降低探针召回；
- 多提示视角不能替代真正独立模型；
- psychometric fusion 没有跨 subject 稳定胜过 error rate；
- DeepSeek 语义 gate 提高 P@20，但 AP 下降；
- Terminal 强模型配对过滤噪声，却损失太多 recall；
- DS-1000 一次要求生成更多探针，反而降低有效覆盖。

面试价值：

> 说明你不是只挑最好看的数字，而是会用门槛、对照和失败分析做研究决策。

---

## 9. 高频追问与参考回答

### Q1：你这个项目到底解决了什么？

> 它解决的是 benchmark 自身质量不可见的问题。传统评测默认题目、gold 和 evaluator 都正确，我把这些假设显式拆成 artifact 并分别审计，最终输出可确认问题、待复核候选和未覆盖能力。

### Q2：为什么不用一个强 LLM 逐题判断？

> 第一，成本高；第二，LLM 判断不稳定；第三，它可能和 benchmark 有相同知识盲区；第四，多次一致不等于正确。因此 LLM 只生成语义候选，确定性重算、执行 replay 或外部证据才负责确认。

### Q3：你说可以适配任意 benchmark，是真的吗？

> 不能这样说。当前可以自动扫描陌生 schema、映射字段、识别已知 family 并生成 audit plan；对于全新执行协议，容器、依赖、提交方式和 evaluator parser 仍需要新 adapter。我的目标是逐步扩大可自动适配的 artifact 和 verifier，而不是声称已经覆盖任意 benchmark。

### Q4：错误率高为什么说明题目有问题？

> 它不说明题目一定有问题。错误率也可能代表题目难，所以它只能是 review ranking signal。它的价值是把 1000 题缩到 Top-K，再交给语义审计或客观 verifier。

### Q5：为什么 fusion 能从 0.573 提高到 0.734？

> 两个信号互补。BenchAudit 看到题面、gold、选项和契约的结构/语义风险；response error rate 看到模型群体的行为异常。一个题可能在文本上看不出问题，但很多高能力模型异常失败；也可能模型都猜对了，但静态契约已经矛盾。融合提高了排序质量。

### Q6：为什么不用 Rasch 或 tetrachoric correlation？

> 我做了离线对照。复杂融合整体 AP 只比简单 error-rate fusion 高 0.006，逐 subject 平均反而低 0.0275，bootstrap CI 跨 0。因此复杂度没有换来稳定增益，当前选择简单方案。

### Q7：`confirmed` 如何保证没有 LLM 越级？

> 通过中央 promotion policy。LLM 方法、LLM evidence key 或未注册三元组默认上限是 review；validator 还需要验证 proof schema 和前置条件。confidence 与 tier 分离，投票数也不直接参与升级。

### Q8：什么是 metamorphic testing？

> 没有额外 gold 时，构造一个应保持答案或行为不变的变换。例如数值答案 `0.5` 与 `1/2`、等价代码实现。若 evaluator 对等价变换不保持结果，可能过严。前提是等价关系本身必须可靠。

### Q9：什么是 mutation testing？

> 主动构造一个应当错误的实现或输出，看 evaluator 是否能杀死它。错误 mutant 仍通过，说明 evaluator 可能覆盖不足。它检查 soundness，但必须先证明 mutant 的行为真的不同。

### Q10：DS-1000 为什么不能直接 confirmed？

> 早期协议中探针执行和最终差异裁决共享不可信 driver，benchmark harness 可能影响比较函数。因此执行本身是真的，但信任域没有完全拆开。当前把这类结果降为 review，下一步需要独立 attestation 或不可伪造 transcript。

### Q11：WorkspaceBench 为什么难？

> 因为正确性由多个 rubric 和真实文件内容共同决定，不是一个标量 gold。LLM judge 还存在随机波动。我们的实验显示整文件删除非常稳定，但局部删除平均变化只有 2.4pp，而 identical 复评平均波动 7.3pp，所以细粒度结论必须做噪声对照。

### Q12：排行榜实验说明什么？

> 剔除 181 条客观缺陷后，15 模型 Kendall τ 是 0.981，并发生一组相邻模型换位。说明缺陷可影响密集榜单，但没有颠覆 Top-1。细分 subject 冠军变化经随机删题对照后不显著，所以我不会用它作为主结论。

### Q13：项目怎样控制 API 成本？

> 先跑零成本规则和历史响应，只有 Top-K 进入 LLM；使用 cache 和冻结 manifest；执行前做 smoke test；失败时记录 attempts 和 missing observation；主门槛数学上不可达时早停。最近 SVAMP 级联只发送 100/300 给 DeepSeek。

### Q14：为什么单模型多提示不能算多模型？

> 它们共享模型参数、训练数据和系统性偏差，响应高度相关。SVAMP 八个视角两两 correctness agreement 为 0.956，所以只能标注为 `single-model-views` 的降级信号，不能冒充独立证据。

### Q15：当前最大的工程问题是什么？

> 第一，历史轨迹还没有统一 TraceBundle；第二，代码、数学、表格和开放任务需要不同 verifier；第三，研究成果分散在研究分支，尚未完整合并；第四，需要真正冻结的跨数据集 holdout，而不仅是同一数据集内的 subject 切分。

### Q16：下一步具体做什么？

> 先将 Workspace 和 Terminal 的历史 trial、rubric score、artifact hash、evaluator log 统一成 TraceBundle，再做不调用 API 的确定性矛盾检查，例如相同输出不同分数、rubric 子分和总分不一致、parser log 与最终 verdict 冲突。LLM 只解释 Top20～50，所有统计异常继续 review-only。

### Q17：如果有一个完全没见过的数据集，你怎么处理？

> 先扫描文件和 schema，推断五类核心 artifact；然后生成审计计划，标出能执行、缺 artifact 和缺 verifier 的能力；先跑结构、重复、契约和历史响应检查；再对高风险候选调用领域 verifier。不能自动接入的执行协议明确记 unsupported，并生成需要实现的 adapter contract。

### Q18：你如何保证实验可复现？

> 固定 sample manifest、seed、protocol 和输入 hash；缓存原始 LLM 响应；保存模型名和配置；按 ID join；将 invalid trial 与错误答案分开；主结果和 post-hoc 诊断分开；对执行环境使用 digest-pinned container。

### Q19：为什么 pytest 一开始全报 import error？

> 当前仓库没有安装成 editable package，直接 `pytest` 时项目根目录不一定进入 import path。使用仓库既有方式 `PYTHONPATH=. pytest -q` 后得到 516 passed。collection import error 与业务断言失败不同，但这也说明 packaging 仍应改善，例如增加标准 `pyproject.toml` 安装和 CI 入口。

### Q20：你本人主要做了什么？

建议诚实回答：

> 我大量使用 LLM 辅助代码实现、测试生成和文献整理，但不是直接接受生成结果。我的主要工作是确定问题抽象、设计证据等级和实验协议、选择指标与对照、运行真实数据、分析负结果，并通过回归和红队用例决定代码能否保留。我能沿着输入、checker、promotion 和实验产物解释代码，也能说明哪些结论被否定。LLM 提高了实现速度，但实验裁决和结果责任由我承担。

不要说“这些代码完全都是我手写的”，也不要贬低自己说“我只是让 LLM 写”。面试官关心的是你能否理解、验证、维护和继续迭代。

---

## 10. 可能出现的现场代码题

### 10.1 题目一：安全合并多个模型回答

需要想到：

- 按 item ID，不按行；
- pair 唯一；
- strict boolean；
- 缺失响应；
- 模型覆盖率；
- 错误信息包含文件和行号。

### 10.2 题目二：实现 P@K

```python
def precision_at_k(labels, scores, k):
    if k <= 0:
        raise ValueError("k must be positive")
    ranked = sorted(
        zip(scores, labels),
        key=lambda pair: pair[0],
        reverse=True,
    )
    top = ranked[: min(k, len(ranked))]
    return sum(label for _, label in top) / len(top) if top else 0.0
```

追问时主动说：

- 并列分数怎样处理；
- K 大于样本数怎么办；
- labels 是否严格布尔；
- 如果用 item ID 打破并列，会引入任意顺序；
- 正式实验可报告 tie-aware 期望。

### 10.3 题目三：给新 checker 写测试

至少包括：

1. 一个真阳性；
2. 一个正常负例；
3. 陌生合法 schema；
4. 缺字段；
5. 重复或边界编码；
6. finding tier 断言；
7. 防止“为了零误报全降级”而加入召回对照。

### 10.4 题目四：设计一个 evaluator 检查

回答模板：

1. 明确要测 soundness 还是 completeness；
2. 定义可执行输入；
3. 构造 gold、等价实现或错误 mutant；
4. 独立验证探针前提；
5. 隔离不可信代码；
6. 保存 transcript、hash、环境；
7. 失败时 review，只有完整 proof chain 才 confirmed。

### 10.5 题目五：设计陌生 benchmark adapter

不要直接生成任意 Python 并执行。优先：

- 受限声明式 schema；
- 明确字段来源；
- schema fingerprint；
- shadow mode；
- holdout gate；
- 未验证 adapter 的证据天花板；
- registry 签发者与 adapter 生成者分离。

---

## 11. 面试中“能说”和“不能说”

### 11.1 可以说

- “SVAMP pilot 的 candidate F1 为 0.914，candidate 是 review 层。”
- “MMLU 15 模型历史响应融合将 AP 从 0.573 提高到 0.734。”
- “复杂 psychometric 没有稳定胜过简单 error rate，所以没有采用。”
- “MMLU 清洗后全局 Kendall τ 为 0.981，并出现相邻换位。”
- “Workspace 整文件删除 11/11 被显著检测，但 identical judge 有较大波动。”
- “系统对未知 schema 可以生成计划和 unsupported 清单。”
- “当前目标是尽可能自动化，不声称已经解决任意 benchmark。”

### 11.2 不能说

- “系统已经能自动检测任意 benchmark 的所有错误。”
- “LLM 多次一致就可以 confirmed。”
- “错误率高就证明题目错了。”
- “SVAMP 0.914 是自动确认缺陷的 F1。”
- “9 个学科冠军易主证明缺陷显著影响排行榜。”
- “DS-1000 的 id=11/300 是当前系统自动 confirmed。”
- “Terminal union F1=0.786，所以新方法成功。”
- “当前 GitHub main 已经集成所有最新研究代码。”
- “641 个测试是当前 checkout 的测试数。”

### 11.3 当前真实分支状态

截至 2026-07-23：

- 当前分支：`research/ranking-impact-mmlu-redux-20260718`
- 当前 HEAD：`12a6e2c Add review-only historical response triage`
- 远端同名分支已包含该提交；
- Workspace/Terminal 证据加固位于：
  `research/terminalbench-paired-audit-20260720`
  的 `5ec273e`；
- `5ec273e` 不是当前 HEAD 的祖先；
- `origin/main` 仍停在较早的 `ac99446`；
- 当前 checkout 的正确测试命令：

```bash
PYTHONPATH=. pytest -q
# 516 passed
```

如果面试官问为什么没合并：

> 这些研究实验在不同冻结分支上推进，为避免在实验中改变基线，没有直接合并。现在已经形成需要集成的工程债务；下一步应先做 clean integration branch、处理冲突、统一回归测试，再更新 main。

这比假装所有功能已经在同一 HEAD 更可信。

---

## 12. 常用英文和指标速查

| 术语 | 中文解释 | 面试中的一句话 |
|---|---|---|
| Benchmark auditing | 评测基准审计 | 检查 benchmark 本身是否可靠 |
| Oracle | 正确性依据 | 定义什么结果算对 |
| Evaluator / harness | 评分实现 | 把输出转换成分数 |
| Output contract | 输出契约 | 合法答案的结构与格式 |
| Replay | 重放 | 用相同 artifact 重新执行判定 |
| Metamorphic testing | 变形测试 | 检查应保持不变的关系是否保持 |
| Mutation testing | 变异测试 | 检查 evaluator 能否拒绝主动构造的错误 |
| Soundness | 健全性 | 错误解不应通过 |
| Completeness | 完备性 | 合理解不应被拒绝 |
| Triage | 分诊 | 排序哪些候选先复核 |
| Review-only | 仅供复核 | 不允许自动确认 |
| Fail-closed | 失败时保守关闭 | 缺证据就降级，不猜测通过 |
| Provenance | 来源记录 | 数据、代码、模型和环境来自哪里 |
| Grounding | 证据落地 | claim 能追溯到具体文本、文件或执行 |
| Counterfactual | 反事实 | 改变一个因素观察评分是否合理变化 |
| Ablation | 消融 | 去掉组件看增益来自哪里 |
| Holdout | 留出集 | 不参与方法设计的测试数据 |
| AP | 平均精度 | 衡量不平衡候选排序质量 |
| P@K | Top-K 精度 | 前 K 个候选里真问题比例 |
| Recall@K | Top-K 召回 | 前 K 个找回全部问题的比例 |
| F1 | P/R 调和平均 | 平衡 precision 与 recall |
| Kendall τ | 排名相关系数 | 衡量两份排行榜顺序变化 |
| Wilson interval | 二项比例区间 | 小样本错误率的不确定性区间 |
| Label leakage | 标签泄漏 | 特征阶段偷看了评估真值 |
| Silent corruption | 静默数据污染 | 不报错但结果已经错位 |

---

## 13. 当前不足与下一步

### 13.1 当前不足

1. **跨分支集成不足**：最新 response triage 和 Workspace/Terminal hardening 未在同一主线。
2. **轨迹 schema 不统一**：QA 有 correctness matrix，Agent 数据仍各自保存 transcript。
3. **领域 verifier 不够广**：代码可执行，数学 Lean/SMT、表格约束和开放任务仍不完整。
4. **真正跨数据集 holdout 不足**：subject split 不能等价于全新 benchmark。
5. **执行信任域仍需加强**：执行和裁决需要独立 attestation。
6. **LLM review 稳定性有限**：Workspace finding-level Jaccard 只有 0.465。
7. **Packaging 仍可改善**：直接 `pytest` 无法导入，应统一安装和 CI 命令。

### 13.2 推荐下一步：TraceBundle v1

轻量记录：

```text
task_id / run_id / model_id
overall_score
rubric_id -> pass/fail/score
execution_events
output_artifacts + hashes
evaluator_logs
environment/version
```

先适配已有 Workspace 和 Terminal 历史结果，不重新执行任务，然后做：

- 相同输出、不同分数；
- 不同输出、相同 rubric 判断；
- rubric 子分与总分矛盾；
- parser/evaluator 日志与最终 verdict 矛盾；
- rubric 永远通过或永远失败；
- evaluator/environment 版本变化后的系统性漂移。

这些异常先全部 review-only。只有能回到日志、文件或可重放 evaluator 的，才尝试 confirmed。

### 13.3 项目最终目标的合理表达

不要说：

> 随便给一个 benchmark，自动找到全部错误。

推荐说：

> 最终希望构建一个 evidence-aware benchmark auditor：对未知 benchmark 自动识别 artifact 和能力缺口，先用低成本结构与历史轨迹产生高召回候选，再按领域路由到可验证的 verifier；能客观确认的自动确认，不能确认的明确保留 review 或 unknown。

---

## 14. 明天面试前的冲刺计划

### 今晚第一小时

- 朗读 30 秒和 2 分钟介绍各 3 次；
- 不看文档画一遍系统数据流；
- 讲清五个 artifact；
- 讲清 confirmed/review/unknown；
- 讲清 error rate 为什么只能 review。

### 今晚第二小时

重点背五组数字：

```text
SVAMP: P/R/F1 = .860/.974/.914
MMLU triage: AP .573 -> .734
MMLU ranking: tau .981, max 1 place
Workspace: delete 11/11, -54.7pp; identical mismatch 6/11
Terminal subset: .741 / .211 / .786，但主门槛失败
```

随后逐题回答 Q1～Q20，任何答不顺的题重新组织成：

```text
问题 -> 方法 -> 数字 -> 边界 -> 下一步
```

### 今晚第三小时

阅读并能解释：

- `benchcore/schema.py`
- `benchcore/planning.py`
- `benchcore/promotion.py`
- `benchcore/response_triage.py`

至少能够回答：

- 为什么按 ID join；
- 为什么 strict bool；
- 为什么重复 pair 失败；
- 为什么 confidence 不等于 tier；
- 为什么 behavior fusion 永远 review-only。

### 明天面试前 30 分钟

1. 用手机录一遍两分钟介绍；
2. 看第 11 节，避免过度声称；
3. 看第 12 节英文；
4. 记住当前测试：

```text
PYTHONPATH=. pytest -q
516 passed in 21.45s
```

5. 记住当前分支和 HEAD，不要把跨分支成果说成已合并。

---

## 15. 自测题

如果下面 15 题能脱稿回答，准备基本足够：

1. 为什么 benchmark 是测量系统？
2. Oracle 和 evaluator 有什么区别？
3. WorkspaceBench 为什么不能套用标量 gold？
4. 自动适配目前做到哪一层？
5. `unsupported` 和 clean 有什么区别？
6. 什么证据才能 confirmed？
7. Metamorphic 与 mutation 分别测什么？
8. 为什么多模型错误率只能用于排序？
9. 为什么 MMLU 必须按 ID join？
10. 为什么采用 AP 而不是 accuracy？
11. 为什么没有采用 AP=0.740 的复杂方法？
12. 排行榜 τ=0.981 应该怎样解释？
13. Workspace identical control 揭示了什么？
14. Terminal 的 union F1 更高，为什么实验仍失败？
15. 如果明天拿到全新 benchmark，前三步做什么？

---

## 16. 面试官要看证据时打开哪里

| 内容 | 仓库内证据 |
|---|---|
| 面试可直接展示的真实问题案例与完整索引 | [`BenchAudit_面试可展示真实问题清单_20260724.md`](BenchAudit_面试可展示真实问题清单_20260724.md) |
| 最新历史响应分诊实现与总结果 | [`reports/response_triage_implementation_20260723/summary.md`](reports/response_triage_implementation_20260723/summary.md) |
| MMLU subject 稳健性 | [`reports/mmlu_subject_grouped_robustness_20260723/report.md`](reports/mmlu_subject_grouped_robustness_20260723/report.md) |
| MMLU 排名影响 | [`reports/ranking_impact/ranking_impact.md`](reports/ranking_impact/ranking_impact.md) |
| 审计器闭环与随机对照边界 | [`reports/ranking_impact/closed_loop_ranking.md`](reports/ranking_impact/closed_loop_ranking.md) 与 [`reports/ranking_impact/random_deletion_control.md`](reports/ranking_impact/random_deletion_control.md) |
| SVAMP 单模型多视角 | [`reports/svamp_deepseek_view_triage_20260723/report.md`](reports/svamp_deepseek_view_triage_20260723/report.md) |
| SVAMP 行为→语义级联 | [`reports/svamp_response_semantic_cascade_20260723/report.md`](reports/svamp_response_semantic_cascade_20260723/report.md) |
| Workspace 官方文件系统实验 | [`WorkspaceBench_官方全量真实输出实验_20260721.md`](WorkspaceBench_官方全量真实输出实验_20260721.md) |
| Terminal 配对试点 | [`TerminalBench_GPT55噪声控制配对试点_20260721.md`](TerminalBench_GPT55噪声控制配对试点_20260721.md) |
| 最新代码关键重跑 | [`最新代码关键实验重跑报告_20260721.md`](最新代码关键实验重跑报告_20260721.md) |
| 历史完整学习指南 | [`LLM_EVALUATION_INTERVIEW_PREPARATION_GUIDE_zh.md`](LLM_EVALUATION_INTERVIEW_PREPARATION_GUIDE_zh.md) |

如果面试现场只打开两个文件，优先打开：

1. `benchcore/response_triage.py`：展示最新数据工程、门禁和 review-only 设计；
2. `benchcore/promotion.py`：展示证据分层的核心思想。

注意：查看 `promotion.py` 时要说明当前 checkout 与 `5ec273e` 加固分支的区别，不把跨分支实现混为同一个 HEAD。

---

## 17. 最后可以背下来的收尾

> 我认为这个项目最重要的不是又加了多少 checker，而是建立了一个证据纪律：先区分 benchmark 的 task、context、oracle、contract 和 evaluator，再区分候选信号与可确认事实。历史模型响应、LLM 判断和统计异常可以帮我们把复核范围缩小，但不能替代证明；真正的自动确认必须来自重算、重放、执行或领域 verifier。现在系统已经证明这种分层在 QA、代码和 Agent benchmark 上有价值，但统一轨迹接入和跨领域验证仍是下一阶段工作。
