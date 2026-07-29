# BenchAudit 长期研究路线：从可信确认到自动适配与修复闭环

日期：2026-07-30

状态：**规划草案；任何实验执行前必须另行冻结协议并独立提交**

## 0. 一句话目标

BenchAudit 的长期目标不是“再堆一个能报很多问题的检查器”，而是：

> 对一个此前未接入的 benchmark，尽量自动建立任务、执行器和证据之间的
> 关系；高召回地产生候选；只把能由独立本地程序重放的缺陷升级为
> `confirmed`；证据不足时主动弃权；最后生成最小修复并证明缺陷消失且没有
> 引入回归。

北极星结果由两个事件组成：

1. 在一个没有人为它手写 item-level 证明器的新 benchmark 上产生至少一条
   可重放的 `confirmed` 缺陷；
2. 对至少一条 `confirmed` 缺陷完成“修复—重放—无回归”闭环。

缺少任一项，都不能声称实现了通用 benchmark 自动审计。

## 1. 当前真实能力边界

| 能力 | 当前状态 | 最强证据 | 主要缺口 |
|---|---|---|---|
| 候选生成 | 有静态规则、LLM 语义路由、多模型响应排序 | Workspace、SVAMP、MMLU 多轮消融 | 跨任务泛化不稳定，review 候选仍多 |
| 客观确认 | 当前最强 | EvalPlus 与 APPS stdin/stdout 的差分证明合同 | 协议适配仍依赖人工 |
| 主动弃权 | 成熟 | review-only ceiling、attestation、timeout/error fail-closed | 新证据源仍需防回归 |
| 自动适配 | 初步 | 通用核心能跨函数调用与 stdin/stdout 复用 | adapter 与输入域证书主要靠手写 |
| 自动修复 | 尚未形成闭环 | 有修复建议和 replay 基础设施 | 尚无“修复后 clean + 零回归”的完整结果 |

当前最可靠的项目主张应是：

> BenchAudit 已经证明一套带 attestation、方向约束和失败关闭策略的确认合同
> 能跨执行协议复用；尚未证明任意 benchmark 的适配可以自动完成，也尚未
> 完成系统化修复闭环。

## 2. 已经关闭的路线

以下路线保留结果，但近期不再投入：

- Workspace Exact router：独立 holdout 上增量 reviewed TP 为 0；
- A′：候选下降，但 family recall 从 84.2% 降至 63.2%；
- A″：internal10 上未达到冻结 recall 门槛；
- APPS input-contract V1：非目标覆盖率 33/1,327 = 2.49%，触发
  `NOT_IDENTIFIABLE_PREFLIGHT_V1`；
- APPS V2：明确禁止；
- 继续调整 A/A′/A″ 词表、阈值或组合：禁止；
- 用 LLM 或多模型共识把 review 直接升级为 confirmed：禁止。

### A″ 历史口径更正

2026-07-30 的零 API 重算发现，A″ 原报告使用的 P0 family-positive 包含
路由选择条件，不适合估计旧 A recall。预先存在的 P1 family reference 给出：

| 方法 | P0 原报告 | P1 更正口径 |
|---|---:|---:|
| 旧 A | 0/7 | **6/7** |
| A′ | 3/7 | **4/7** |
| A″ | 3/7 | **4/7** |

FAIL 裁决不变，而且结论更清楚：A″ 的候选下降伴随相对旧 A 的 recall
损失。修复分支为
`fix/workspace-a-double-prime-p1-denominator-20260730`，提交
`0a15f1d`。

## 3. 以后所有领域模型实验的共同前置门

APPS V1 的最高价值不是 2.49% 本身，而是一个通用实验模式：

> 在写完整领域适配器之前，先在非目标数据上测量机械覆盖率。

任何新的 parser、schema、certificate language 或 adapter family 必须先做：

1. 冻结目标集合但不读取目标内容；
2. 在非目标样本上运行 aggregate-only 预飞；
3. 冻结最低覆盖门槛；
4. 目标样本在解析前物理跳过；
5. 只提交聚合计数、输入哈希和扫描器哈希；
6. 未过门槛则终止，不开发目标感知的 V2。

协议门槛和扫描器必须在不同提交中依次落地：

1. `protocol/gate` 提交；
2. `scanner/tests` 提交；
3. 运行；
4. `receipt/results` 提交。

无人值守长跑只允许发生在第 1、2 步已经独立复核之后。

## 4. Phase A：适配成本曲线

周期：1–2 周。

### A0. 写协议前的数据可得性预检

在冻结 A1 协议之前，先做一次约十分钟、aggregate-only 的可得性检查。它只
读取目录结构、schema、行数和 item ID，不读取 task/candidate/reference
正文，也不执行数据库代码。

分别统计：

- task 行数与唯一 item ID 数；
- candidate/model output 行数与唯一 item ID 数；
- reference 行数与唯一 item ID 数；
- score/per-item status 行数与唯一 item ID 数；
- execution trace 行数与唯一 item ID 数；
- task ↔ candidate ↔ reference ↔ score ↔ trace 的两两和全链 join 覆盖率；
- 缺失、重复、冲突 ID 数；
- 是否存在稳定 evaluator/harness identity。

如果不存在稳定共享 ID，或可形成完整执行链的 item 少于 30 条，先记为
`NOT_IDENTIFIABLE_DATA_LINKAGE`，不要按猜测的数据形态写 A1 协议。可得性
receipt 必须先于协议提交。

### A1. 研究问题

通用确认核心已经跨函数调用和 stdin/stdout 复用，但尚不知道接入陌生协议
究竟需要多少人工工作。Phase A 同时要求两类结果：

1. 一张逐步骤适配成本表；
2. adapter 在该 benchmark 上实际产生至少一条可重放 confirmed，或给出
   有原则、可复核的 `NOT_IDENTIFIABLE`。

只有成本表而没有能力结局，只能记为“成本已测量，能力未验证”。

### A2. 首轮对象

优先选择本地已有真实结果、但 BenchAudit 尚无专用确认 adapter 的数据库执行
协议：

- `/data/expdata/BenchAudit/DBCode/SQLite_Function_Code_Generation`;
- `/data/expdata/BenchAudit/DBCode/PostgreSQL_Function_Code_Generation`.

SQLite 优先，因为执行环境更易本地重放，标为 `first-of-family`；
PostgreSQL 作为同族不同运行时的迁移检查，标为 `second-of-family`。两者
成本必须分别报告，不能把首个适配器的一次性协议学习成本算到第二个上。
SQLBench 目前主要是 README/sidecar，是否进入实验取决于能否获得冻结的逐题
输入、输出与 evaluator receipt。

### A3. 必须记录的步骤

每一步同时记录人工时间、人工代码行数和自动化级别：

| 步骤 | 要回答的问题 | 自动化级别 |
|---|---|---|
| 协议识别 | 系统能否识别 SQL function / query / stdin 等协议 | 自动 / 半自动 / 人工 |
| item 对齐 | task、candidate、reference、score 是否能按 ID 关联 | 自动 / 半自动 / 人工 |
| 输入物化 | 能否建立数据库状态、参数和依赖 | 自动 / 半自动 / 人工 |
| 执行沙箱 | timeout、error、transaction rollback 是否可区分 | 自动 / 半自动 / 人工 |
| 比较器 | 值、行集、顺序、浮点、异常如何比较 | 自动 / 半自动 / 人工 |
| 证明绑定 | driver、candidate、输入、环境是否有哈希与 attestation | 自动 / 半自动 / 人工 |
| 控制集 | canonical、identical、swapped、timeout、tamper 是否为零 | 自动 / 半自动 / 人工 |
| promotion | 是否复用中央确认合同，无 benchmark-specific 旁路 | 自动 / 半自动 / 人工 |

代码行数必须拆开报告：

- 通用核心新增 LOC；
- adapter-specific 生产 LOC；
- benchmark mapping/config LOC；
- tests/fixtures LOC；
- item-specific LOC（目标为 0）。

删除行与自动生成文件不能用来降低 LOC；格式化改动不计入。

### A4. 预注册判据

能力判据优先于成本判据：

- 产生 `≥1` 条可重放 confirmed 且所有安全硬门通过：能力得到验证；
- 没有 confirmed，但输出有原则的 `NOT_IDENTIFIABLE`，明确指出是缺少
  可执行 oracle、无可确认缺陷、证据链不完整还是环境不可冻结：有效负结果，
  但不推进北极星事件 1，也不进入 A2；
- 既没有 confirmed，也没有可复核的 `NOT_IDENTIFIABLE`：记为“成本已测量，
  能力未验证”，不得进入 A2。

成本判据以人工活跃时间与必须人工介入的步骤数为主，LOC 只作辅助：

- SQLite `first-of-family` 只建立首个成本点，不用 150/500 LOC 对它作
  Go/No-Go；
- PostgreSQL `second-of-family` 若人工活跃时间 `≤8 小时`、必须人工步骤
  `≤2`，且 adapter-specific 生产 LOC `<150`：自动适配值得继续；
- PostgreSQL `second-of-family` 若人工活跃时间 `>24 小时`、必须人工步骤
  `≥4`，且 adapter-specific 生产 LOC `>500`：当前架构不支持“任意
  benchmark”，停止自动生成叙事，先重构；
- 其余组合：报告完整成本曲线，不强行二分。

时间只统计主动分析、编码、调试和人工配置；等待测试或容器下载的 wall-clock
单独报告。人工步骤按“缺少该判断就无法继续”的独立决策点计数。

安全硬门：

- item-specific proof validator = 0；
- control escape = 0；
- timeout/error 被当作语义失败 = 0；
- 未 attested confirmed = 0；
- 运行时依赖缺失必须记 `NOT_IDENTIFIABLE`，不能按 clean 处理。

### A5. A2 的条件触发

只有新 benchmark 至少产出一条 confirmed、全部安全门通过，并且
second-of-family 成本显示瓶颈集中在 1–2 步时，才尝试自动化：

1. 自动识别协议族；
2. 从冻结模板选择 adapter skeleton；
3. 自动生成 mapping receipt；
4. 生成后运行控制集；
5. 控制不全通过时保持 shadow/review，不注册 adapter。

A2 的成功不是“代码能运行”，而是：

- 人工 adapter-specific LOC 至少下降 50%；
- 人工活跃时间至少下降 50%；
- 人工干预步骤减少；
- 控制集与手写 adapter 完全等价；
- confirmation 数量不能因放宽门槛增加。

## 5. Phase B：首个修复—回归闭环

周期：2–3 周，可与 Phase A 顺序执行，不建议在同一晚并行启动。

### B1. 单条闭环

首选候选：`workspacebench-351` 的输入文件名碰撞。

选择它的理由：

- 缺陷由确定性 manifest replay 确认；
- 不依赖 LLM；
- 两份同名文件内容哈希不同；
- promotion contract 已有测试。

但“碰撞存在”不自动决定“哪份文件应被改名或删除”。因此修复前必须先做
repair-identifiability gate：

1. 是否能从 task、manifest、文件内容或上游 mapping 唯一确定两份文件的
   语义角色；
2. 是否能生成不删除信息的唯一命名；
3. task 中所有文件引用能否同步机械更新；
4. 修复后是否仍能找到全部原始输入内容。

若任一项不唯一，结果必须是 `NOT_IDENTIFIABLE_REPAIR`，不得通过删掉一份
文件或直接移除 item 来制造 clean。

### B2. 修复成功合同

一次成功修复必须同时满足：

1. 修复前原 finding 可由原始 replay 重现为 confirmed；
2. patch 只修改责任 artifact；
3. 修复后同一 replay 为 clean；
4. 两份原内容均可由新 manifest 唯一寻址；
5. task/contract 引用无悬空；
6. 其余 Workspace invariants 不新增 finding；
7. 未受影响 item 的抽样回归不变；
8. patch、输入、checker 和 replay transcript 全部带 SHA-256；
9. 不允许靠 suppress/allowlist/降低 severity 消除 finding。

主要指标：

- repair success；
- regression count；
- new finding count；
- changed artifact count；
- changed bytes/lines；
- human intervention steps；
- repair replay determinism。

### B3. 缺陷族扩展

只有 B1 成功后，才选择一个至少有 3 条 confirmed 实例的同根因家族进行
批量修复。一次修复能消掉多条 finding 时按 one-fix 原则计一个 root cause。

若没有 3 条同族 confirmed，不为了凑数量降低证据标准。

### B4. 排名影响

当修复会改变 evaluator 接受/拒绝结果时，重算修复前后：

- model score；
- pairwise ranking；
- Kendall’s tau；
- Top-k 变化；
- bootstrap 置信区间。

若修复只是消除输入歧义但缺少模型输出，诚实记录
`ranking_impact_not_identifiable`，不要补造模型运行。

## 6. Phase C：自然存在的强 oracle

周期：机会型，约 1–2 周。

目的：把“构造弱测试前缀”的机制可迁移证据，推进为关于官方测试覆盖的
陈述。

优先对象：

- HumanEval ↔ HumanEval+；
- MBPP ↔ MBPP+；
- benchmark 官方 v1 ↔ 官方修订版；
- 有明确旧测试/增强测试 receipt 的公开执行 benchmark。

这条线必须避免退化成已有 mutation-guided test generation 的复刻。真正的
差异点只保留两项：

1. **机器可重放的确认合同**：中央 proof contract、evidence attestation、
   fail-closed promotion 和逐条本地 replay 是同一个技术贡献的组成部分，
   不拆成四项贡献；
2. **确认后的修复闭环**：从 confirmed 继续走到最小修复与回归证明。

adapter 成本曲线是 Phase A 对可扩展性的实证，不作为 Phase C 的独立新颖性
主张。

不再做：

- 自己随意截取测试形成“弱 oracle”后把差值解释成官方缺陷；
- 依赖 LLM 判断 mutant 是否等价；
- 在没有域合法性证书时把生成输入升级为 confirmed。

## 7. Phase D：论文级实验包

只有 A、B 至少各有一个正结果后才进入。

### D1. 建议主张

> Attested confirmation contracts can transfer across heterogeneous benchmark
> execution protocols, expose replayable evaluator defects while failing
> closed under incomplete evidence, and support regression-checked repair.

中文：

> 带证明绑定的确认合同可以跨异构执行协议迁移，在证据不足时主动弃权，
> 对可重放 evaluator 缺陷进行机器确认，并支持带回归证明的修复。

### D2. 最低实验组合

- 至少 3 种执行协议；
- 至少 2 个自然存在的强 oracle 对，其中至少 1 个必须来自 EvalPlus 之外的
  独立数据集、作者或修订机制；HumanEval+ 与 MBPP+ 不能被解释为两份独立
  方法学证据；
- 至少 1 个从未手写 item-level verifier 的新 benchmark；
- 至少 1 条完整修复闭环；
- 每个 confirmed 路径均有对抗控制；
- 至少一次跨 benchmark 或跨协议 holdout。

### D3. 主要指标

确认质量：

- confirmed precision（逐条 replay）；
- control escape rate；
- attestation tamper rejection；
- timeout/error confusion rate；
- abstention / not-identifiable rate。

适配能力：

- human intervention count；
- active human time；
- time-to-first-replay；
- adapter-specific LOC；
- shared-core reuse ratio；
- protocol-family holdout success。

修复能力：

- repair success rate；
- regression-free rate；
- new finding count；
- leaderboard/ranking impact；
- repair cost。

候选层指标只作为辅助：

- candidate recall；
- reviewed precision；
- calls/tokens per reviewed root cause；
- candidate rate。

## 8. 八周时间表

| 周 | 主要任务 | 必须产物 | 停止条件 |
|---|---|---|---|
| 1 | A0 数据关联预检 + A1 协议与 SQLite 预飞 | linkage receipt、输入 receipt、成本 schema | 共享 ID/执行链不可识别 |
| 2 | SQLite first-of-family adapter | 时间/步骤/LOC 表、能力结局、控制集 | 无 confirmed 且无原则性弃权 |
| 3 | PostgreSQL second-of-family 迁移 | 第二个成本点、迁移差异、能力结局 | 环境不可冻结或成本分散 |
| 4 | B1 repair-identifiability + 单条修复 | pre/post replay、patch、回归 | 修复意图不唯一 |
| 5 | B2 同族扩展或第二条闭环 | 批量结果或诚实 NOT_IDENTIFIABLE | confirmed 样本不足 |
| 6 | 自然 oracle 扩展 | 官方强 oracle 的重放结果 | 只能构造自有弱 oracle |
| 7 | 统一消融与安全攻击 | 跨协议表、控制矩阵 | 任一 confirmed escape |
| 8 | 论文整理与复现包 | 冻结 artifact、脚本、文档 | 主张超出证据 |

Phase A1 或 B1 失败时不补做更多同类小实验来“救结果”；按停止条件切换到
架构复盘。

## 9. 无人值守长跑政策

可以无人值守运行：

- 已冻结 mutation pool 的 kill matrix；
- 已冻结 official weak/strong oracle 的差分执行；
- 哈希校验、静态扫描和确定性 replay；
- 不含策略更新的 bootstrap / permutation；
- 完整测试与安全控制。

不能无人值守启动：

- 未复核 prompt 的 API 批量调用；
- 会根据中间结果动态改规则的 agent；
- 未冻结超时/沙箱/比较器的执行；
- 会改 benchmark 数据或推送 main 的修复；
- 失败后自动扩语法、扩词表或切换 holdout。

每个长跑必须提前固定：

- commit；
- 输入 SHA-256；
- 命令；
- 容器镜像的 registry digest；
- network-disabled 策略；
- read-only root filesystem 与可写临时目录边界；
- non-root UID/GID；
- dropped Linux capabilities 与进程数限制；
- 禁止 secret/API key mount；
- CPU/内存/超时；
- 最大任务数；
- 最大 API/token 成本；
- 中止条件；
- 输出目录；
- 两次确定性复跑要求。

## 10. 明天开始时的精确顺序

1. 合并或复核 A″ P1 分母更正 `0a15f1d`；
2. 对 DBCode 做十分钟 aggregate-only 数据可得性检查，生成 task/candidate/
   reference/score/trace 的 ID 覆盖表；
3. 只有 linkage 可识别，才单独提交 Phase A1 measurement protocol，暂不写
   adapter；
4. 对 DBCode/SQLite 做输入与执行器预飞；
5. 只有预飞通过才实现 adapter；
6. 另开 B1 repair protocol，先判断 workspacebench-351 的修复是否唯一；
7. B1 通过 identifiability gate 后才生成 patch；
8. 不启动 APPS V2，不回到 Workspace router 调参。

## 11. 对外汇报的简洁版本

目前最强的正结果：

> 通用确认合同已经从函数调用迁移到 stdin/stdout，并通过证据篡改、方向交换、
> timeout/error 和 attestation 缺失等对抗测试。

目前最重要的负结果：

> APPS 输入域 V1 在未读目标任务的非目标预飞中仅覆盖 2.49%，因此项目按
> 预注册纪律停止，没有把通用研究退化成 benchmark-specific parser。

接下来的两个决定性问题：

> 接入陌生执行协议到底需要多少人工工作？确认缺陷后能否完成带回归证明的
> 修复？

这两项比继续提高 review 候选召回更接近 BenchAudit 的最终目标。
