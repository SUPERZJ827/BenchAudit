# BenchAudit 夜间交付复核 + V2 工作指令

> 日期：2026-08-02
> 复核对象：分支 `chore/hygiene-and-adjudicator-protocol-20260802`，HEAD `ef2a4d0`
> 上游指令：`docs/research/BenchAudit_今夜工作指令_供GPT_20260802.md`
> 上游规划：`docs/research/BenchAudit_研究定位复核与可执行规划_20260801.md`
> 复核方式：**零 API、零外网**，全部依据 worktree 内已提交产物与主仓库代码
> 复核者角色：独立红队，不写生产代码

---

# 第一部分：复核结论

## 0. 裁决

**有条件通过。** 纪律执行满分，两处实质问题必须在实现前修正。

| 维度 | 裁决 |
|---|---|
| 纪律遵守 | ✅ 全部核验通过，无一项违反 |
| 任务 A（GDPVal 干净重跑） | ✅ 处理正确；差异是真实发现，不是失败 |
| 任务 B（manifest 版本控制） | ✅ 通过 |
| 任务 C（receipt reason_code） | ✅ 通过，且选了更严的那条路径 |
| 任务 D（裁决器协议） | ⚠️ **结论范围超出证据范围，必须收窄重冻**（F1、F2） |
| 任务 E（引用审计） | ✅ 正确跳过；脚本先冻结的顺序对 |
| 任务 F（P1 设计说明） | ✅ 通过 |

两处必修：

- **F1**：协议把一个只覆盖 in-memory 观测的论证，冻成了覆盖全部执行协议的结论。APPS（stdin/stdout）被误伤。
- **F2**：威胁模型隐含"拜占庭 harness"，但该模型从未被独立复核，且对 2022 年的公开 harness 可能标定过严。

另有两处非阻塞问题（F3、F4）。

---

## 1. 纪律核验（逐项，附我实际执行的核验）

| 声明 | 核验方式 | 结果 |
|---|---|---|
| 工作树干净 | `git status --short` | 空 ✅ |
| 未修改 `promotion.py` / `evaluator_execution.py` | `git diff --stat` vs merge-base | 未出现 ✅ |
| 未提交 dataset bytes | `git ls-files datasets/` | 0 条 ✅ |
| manifest 已纳入 | `git ls-files experiments/*.manifest.json` | 9 份 / 422,102 bytes ✅ |
| `.gitignore` 改动最小 | `git show fff4477 -- .gitignore` | 只加一行 `!experiments/*.manifest.json` ✅ |
| 原 external evidence receipt 未改 | `git log -- .../execution_receipt.json` | 只有 `e6476ec` 一个提交 ✅ |
| addendum 绑定原 receipt 哈希 | 比对 addendum 与 `diagnostic_addendum.json` | 均为 `a5c0edbfcc478…` ✅ |
| 决策未被重新归类 | addendum 内 `decision_changed: false` 等六个布尔 | 全部 false ✅ |
| 零 API | 晨报声明 + 无 cache 增量 | ✅ |
| 未 push main | 分支状态 | ✅ |
| 引用脚本先于结果冻结 | 提交序 `0ca45a7` 在无 receipt 产出前 | ✅ |

**没有发现任何纪律违规。** 尤其是任务 C：指令给了两条路径（改原文件 / 新增 addendum），GPT 选了更严的那条，理由正确（既有结果文档已绑定原 receipt 的 SHA-256，改原文件会打断哈希链）。

---

## 2. F1｜协议的结论范围超出了它的证据范围（阻塞，必修）

### 2.1 问题

`docs/TRUSTED_ADJUDICATOR_PROTOCOL_V1_20260802.md`（SHA-256 `9cbe5b1b…`）的 §3.4 与 §7.3 冻结了一个**不带限定词的**结论：

> **NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR**

但支撑它的论证（§2.4 末段、§3.3、§9.3）**只覆盖一种观测形态：in-memory Python 值**。§9.3 的可满足性框里三行判断全部是关于 DS-1000 的。

而协议**自己**在 §2.4 写了：

> For OS-visible protocols, a future trusted supervisor might capture stdout, exit status, or file artifacts directly. For DS-1000, the relevant Python values exist only inside the interpreter running the untrusted harness.

它明确区分了两类协议，却只对其中一类做了论证，然后把结论冻在了两类之上。

### 2.2 为什么这不是吹毛求疵

三个被禁用的证明族是**通用的**，不是 DS-1000 专用的：

```python
# benchcore/promotion.py:587
DISABLED_UNATTESTED_PROOFS = frozenset({
    ("execution_replay", "executed_harness", "gold_rejected_by_evaluator"),
    ("execution_differential", "executed_differential_confirmed", "overstrict_evaluator"),
    ("execution_kill_matrix", "executed_kill_matrix_confirmed", "evaluator_mutation_survived"),
})
```

**APPS 是 stdin/stdout 协议**（分支 `research/apps-official-survivor-confirmation-20260729`，`docs/experiments/APPS_STDIN_DIFFERENTIAL_ORACLE_PROTOCOL_20260729.md`）。而 stdout 的捕获**已经发生在 OS 边界**：

```python
# benchcore/execution.py:110-135
stdin=subprocess.PIPE if command.stdin is not None else subprocess.DEVNULL,
stdout=subprocess.PIPE,
...
stdout, stderr, timed_out = _communicate_bounded(...)
```

父进程通过管道读取的字节，子进程**只能是它实际写出去的**。这里没有"内存对象 → 调用方控制的序列化器 → 可能被篡改的字节"这一层——**观测本身就是字节流**。协议 §2.4 说的"a pipe from an untrusted child is not sufficient: a process can emit arbitrary bytes"在这里是对的但不相关：我们要断言的**恰恰就是"该进程写出了这些字节"**，而不是"该进程内存里有某个对象"。

因此：**一个笼统的 NOT_IDENTIFIABLE 把 APPS 一并关掉了**，而 APPS 恰恰是项目里已经跨协议迁移成功、19 次对抗全部降级为 review 的那条线。

### 2.3 GPT 自己已经看到了

晨报待决 #3：

> 是否另开一个仅面向 OS-visible stdout/file observation 的 V2，待独立复核后决定。

方向是对的。问题是**协议正文没有把结论收窄**，只把它记在了待决里。冻结的文档才是有效力的东西。

### 2.4 要求

V1 不用推翻，**收窄重冻**：

| 观测形态 | V1 应有的结论 |
|---|---|
| in-memory 语言级对象（DS-1000） | `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR_IN_MEMORY` —— 论证成立，保留 |
| OS-visible 字节流 / exit status / 文件产物（APPS 等） | **V1 未评估**，不得由 V1 的结论覆盖 |

这一条是我们自己反复批评别人的形态：**结论比证据宽**。必须自己先守住。

---

## 3. F2｜威胁模型标定（阻塞，必修）

### 3.1 问题

协议 §1.1 的"被保护声明"第 2 条：

> the comparison inputs are the observations actually produced by that execution

被当作一个需要**认证（authentication）** 才能成立的事实。这隐含了一个对手：**一个主动想伪造 confirmation 的 harness**——拜占庭模型。

问一句：**谁是这个对手？**

DS-1000 的 harness 是 2022 年发布的公开代码。写它的时候 BenchAudit 不存在。它不可能针对我们的裁决器构造 monkeypatch。这是**非自适应对手（non-adaptive adversary）**，不是拜占庭对手。

被禁用的真实理由（`evaluator_execution.py:29`）也不是"harness 想骗我们"，而是"harness 和数值裁决共用一个解释器，harness 代码**可能**覆盖比较器"——这是**意外干扰**的风险，不是恶意伪造。

### 3.2 现成的机械手段

"非自适应"不需要靠信念声明，我们有现成的机械证明手段：**external evidence policy 的 `pre_cutoff` 祖先关系**。

把 harness 的修订钉在一个早于 BenchAudit 相关工作的 cutoff 上，`git merge-base --is-ancestor` 就机械地确立了"该代码不可能是针对我们的裁决器写的"。这与时间戳不同——是 DAG 祖先关系，不可伪造（这正是我们在 external evidence V1→V2 里反复确立的原则）。

于是 §3.3 那句：

> A correct contract applied to forged values remains a forged proof.

退化成：

> A correct contract applied to values produced by code that provably predates, and therefore cannot target, the adjudicator.

配合两件已经能做到的事——**裁决进程不 import 任何 harness 对象** + **确定性重放**——足以支撑 `confirmed`。

### 3.3 代价必须写清楚

这不是白拿的。主张从：

> 对拜占庭 harness 可靠

降为：

> **对非自适应 harness 可靠，非自适应性由 pre-cutoff 祖先关系钉死**

这个假设**必须成为 confirmed 记录里的一个显式字段**（例如 `harness_adversary_model: "non_adaptive_pre_cutoff"` + 钉住的 cutoff commit），而不是隐含在协议正文里。第三方复核者必须一眼看到我们假设了什么。

同时**不覆盖**的情况要明说：如果某天审计一个在 BenchAudit 之后发布、且作者有动机让自己的 benchmark "看起来干净"的 harness，这个假设不成立，必须退回 review。

### 3.4 附带收益

这会让 external evidence 那条线——我在 07-31 批评它"5 轮 NOT_IDENTIFIABLE、零产出"的那条——**第一次有真实用途**：它的 `pre_cutoff` 关系推导成为执行类 confirmed 的信任前提之一。

### 3.5 我的责任

我在夜间指令 §5 只要求"正面回答循环依赖，答不了就写 NOT_IDENTIFIABLE"，**没有要求质询威胁模型本身**。这个 NOT_IDENTIFIABLE 有一部分是我的指令逼出来的，不是 GPT 的判断失误。

---

## 4. F3｜确定性门失败是设计问题，不是这次运行的问题（非阻塞）

两次 `audit.json` SHA-256 不同：

```
run 1: 0dba5fc79a4e812ee62f9e1b8002b6316fccb9d00a08f00b12fedcb6234ed7dc
run 2: 5a56797539a8e4980ac124b5518f40e462a43e0d601aad79eefe78a7a638b5bc
唯一差异：run_metadata.elapsed_seconds  8.818448 vs 4.504578
```

GPT 拒绝把它标成 pass，正确。

但根因要说清楚：**只要 `elapsed_seconds` 在被哈希的 payload 里，任何 GDPVal audit.json 都永远不可能逐字节确定。** 这不是这次运行的偶然，是 `report.py` 的设计问题，影响所有 benchmark 的所有报告。

**解法我们已经有了**，就在 external evidence 协议 §7 里：**stable-summary / raw-transcript 二分**——wall-clock、临时路径、PID、命令时长、DNS 应答、传输速率全部归入 raw transcript，不进 stable hash；stable summary 重复运行必须哈希相同。

把同一模式搬进 `report.py` 即可。详见任务 H。

---

## 5. F4｜报告字段有误导风险（非阻塞）

### 5.1 两个都叫 unknown

```
summary.unknown_count          = 0   ← findings 层：没有 unknown-tier 的 finding
summary.audit_coverage.unknown = 1   ← 覆盖层：有一个 check 未完成
```

markdown 里只印了前者（`report.py:158`："Unknown-tier findings: 0"）。快速阅读会得出"覆盖完整"的结论，而事实上有一个 item×checker 的洞。历史那次两个都是 0，所以这个坑一直没暴露。

### 5.2 `operational_affected_items` 名不副实

```python
# benchcore/report.py:42
"operational_affected_items": len({
    v.item_id for v in violations if v.defect_scope == "operational"
}),
```

它数的是**被发射为 violation 的 operational 缺陷**。本次的 artifact-not-cached 没有产生 violation，只产生了 ledger 里的 `operational_failed`，所以这个字段是 0——**按定义正确，但字段名读起来像"没有运行问题"**，而实际上 `audit_coverage.operational_failed = 1`。

### 5.3 需要说明的是：fail-closed 本身工作正常

```
audit_coverage: planned 880 / eligible 661 / attempted 661 / completed 660
                unknown 1 / operational_failed 1 / ineligible 219
ledger: item 83d10b06-26d1-4636-a32c-23f92c57f30b × gdpval_workbook_replay
        status=operational_failed, completed=false, coverage_unknown=True
```

**洞是可见的，没有被静默吞掉。** 系统行为正确，只是 markdown 摘要层把它藏起来了。

---

## 6. GDPVal 7 → 5：评估与"现在能守住的数字"

### 6.1 事实

| 运行 | Items | Violations | Confirmed | Review | Unknown(findings) |
|---|---:|---:|---:|---:|---:|
| 历史 2026-07-16（**dirty 工作树**） | 220 | 18 | **7** | 11 | 0 |
| 干净重跑 run 1 | 220 | 16 | **5** | 11 | 0 |
| 干净重跑 run 2 | 220 | 16 | **5** | 11 | 0 |

confirmed 构成：

| 缺陷类型 | 历史 | 干净重跑 |
|---|---:|---:|
| `task_artifact_contract_mismatch` | 4 | 3 |
| `rubric_artifact_contract_mismatch` | 2 | 1 |
| `rubric_reference_contract_mismatch` | 1 | 1 |

缺的两条都属于同一 item `83d10b06-26d1-4636-a32c-23f92c57f30b`，根因是：

```
gdpval_workbook_replay → GDPvalArtifactNotCached:
  reference_files/cc781e4dc0985c8eb327a53ec03b5900/Population v2.xlsx
```

### 6.2 真正的教训

**artifact cache 是证据链的一部分，但它从来没有被钉死。** 我们最强的 7 条结果里有 2 条依赖一份没有内容哈希、没进版本控制、不可重放的本地缓存文件。

这和 07-31 我提出的"`experiments/*.manifest.json` 不在版控"是同一类问题的两个实例：**冻结的东西没有被真正冻住。**

### 6.3 现在能守住的数字

> GDPVal 220 题，**5 条 confirmed**（3 task-artifact / 1 rubric-artifact / 1 rubric-reference），零 LLM，确定性重放，干净工作树 commit `a4d5fae`；
> 另有 **2 条 coverage unknown**，原因是一份 reference workbook 未在冻结缓存内，**不是 clean 判定**。

对外材料一律用这个版本，**不要再引用 7**。

### 6.4 待决问题的处置意见

**问题一：能否恢复 `Population v2.xlsx`？**

可以，但**顺序不能反**：

```
1. 先冻结 artifact manifest（相对路径 + 期望内容 SHA-256 + 数据集 revision）并提交
2. 再取文件
3. 校验实际内容 SHA-256 与 manifest 一致
4. 再重跑
5. 无论结果是 7 还是仍是 5，都如实记录
```

反过来做（先取到、跑出 7、再补 manifest）就是"补数据让计数对上"，禁止。

**问题二：`mmlu_redux_pilot1000.manifest.json` 缺 `source_sha256`，要不要补写？**

**不要补。** 现在补写等于用今天的数据给昨天的实验背书——我们无法证明今天算出来的哈希就是当时用的那份数据。正确做法：记为已知缺陷，写进 manifest schema 的改进项，**下次实验用新 schema**。历史 manifest 保持原样，附一行"该 manifest 无来源哈希，其对应实验的输入不可独立验证"。

---

# 第二部分：给 GPT 的 V2 工作指令

## 7. 绝对禁止（与夜间指令一致，另加两条）

1. 实现可信裁决器（V2 协议未经复核前）；
2. 修改 `benchcore/promotion.py`，尤其不得移除任何 `DISABLED_UNATTESTED_PROOFS` 条目；
3. 修改 `benchcore/evaluator_execution.py` 的判决逻辑；
4. external evidence V3 / Phase 2B / 任何出口策略放宽；
5. 重开 APPS input-contract V2（输入域证书，2.49% 预飞已关闭）——**注意与本指令的"APPS stdout 观测通道"不是一回事，后者是允许的**；
6. 调 A / A′ / A″；
7. 做 SVAMP bisect（Claude 负责）；
8. 花费 API 额度；
9. push main；
10. 把失败结果重新归类；
11. **【新】** 修改任何历史报告产物的内容或哈希（`reports/**` 下已提交的旧产物一律只读）；
12. **【新】** 先取数据再补 manifest（见 §6.4）。

---

## 8. 任务 G（最高优先）：V2 协议 —— 分协议重冻 + 威胁模型显式化

**只写协议。不写实现、不写测试、不跑任何东西。**

写到 `docs/TRUSTED_ADJUDICATOR_PROTOCOL_V2_20260802.md`，状态 `frozen before implementation; pending independent review`。

### G.1 与 V1 的关系

V1 **不作废、不修改、不重写**。V2 只做两件事：

1. 把 V1 的结论**收窄**为 `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR_IN_MEMORY`，并在 V2 §1 记录 V1 文档的 SHA-256 `9cbe5b1badf62540bd113b8822a1a584d8bcd3d9995a602fb14c7b7ad020cb0f` 作为不可变历史；
2. 对 V1 未评估的 **OS-visible 观测形态**单独做可识别性判断。

沿用 external evidence V1→V2 的先例：只 supersede 一条具体规则，不重解释父协议。

### G.2 必须新增的章节

**§A. 观测形态分类。** 明确定义并分开处理：

| 形态 | 观测是什么 | 捕获边界 | V2 是否评估 |
|---|---|---|---|
| in-memory 语言级对象 | Python 对象 | 无独立边界 | 否，沿用 V1 结论 |
| OS-visible 字节流 | stdout / stderr / exit status | 父进程管道（OS 内核） | **是** |
| OS-visible 文件产物 | 沙箱内落盘文件 | 容器挂载点 / 父进程读 | **是** |

**§B. OS-visible 观测的 provenance 论证。** 必须正面回答：

1. 父进程通过 `subprocess.PIPE`（`benchcore/execution.py:110-135`）读到的字节，是否**只能**是子进程实际写出的？列出可能的例外并逐条处理：
   - 子进程 fork 出的孙进程写同一 fd；
   - 容器 runtime 在中间做了转换（`execution.py:173-175` 的 `-i` 转发）；
   - 输出被截断（`_communicate_bounded`）——截断必须导致弃权，不能当作"输出就是这些"；
   - stderr / stdout 交织；
   - 非 UTF-8 字节、超长行、超时后的部分输出。
2. 谁执行捕获、谁不能干预捕获，用哪个进程边界表达。
3. 与 in-memory 情况的**关键差异**必须写成一句可复核的话（不要只说"更容易"）。

**§C. 威胁模型：显式的对手能力假设。** 这是 V1 缺的东西。必须写出：

1. **对手模型的名字与定义**：`non_adaptive_pre_cutoff` —— harness 代码的修订是某个钉住 cutoff 的祖先，因而不可能针对本裁决器构造。
2. **该假设如何被机械确立**：复用 external evidence policy 的 `git merge-base --is-ancestor` 关系推导（不用时间戳）。给出需要钉住的对象：benchmark 仓库 canonical remote、harness 修订 commit、cutoff commit。
3. **该假设不覆盖什么**：cutoff 之后发布的 harness、benchmark 作者有动机自证清白的场景、任何在我们发布方法之后修订过 evaluator 的 benchmark —— 这些一律退回 review。
4. **假设必须出现在 confirmed 记录里**：冻结字段名与取值域，例如
   `harness_adversary_model: "non_adaptive_pre_cutoff"` +
   `harness_revision_commit` + `cutoff_commit` + `ancestry_verified: true`。
   promotion 侧必须**重新推导**这个字段，不接受调用方填写（沿用 `derive_allowed_uses()` 的原则）。
5. **降级路径**：祖先关系不可验证 → 该 finding 最高 `review`，不是 `unknown`，也不是 confirmed。

**§D. 进程隔离要求（对 OS-visible 仍然必要）。** 裁决进程：

- 不 import 任何 harness / benchmark 代码；
- 只接收字节流 + 契约 ID + 契约参数（沿用 V1 §2.1 的白名单，去掉 in-memory 相关项）；
- 比较契约来自 code-owned manifest，不接受内联比较器（沿用 V1 §3.2）；
- 崩溃 / 超时 / 截断 / 解析失败 → 弃权，不得成为语义结论。

**§E. 正例可满足性冻结。** 按 V2 协议 §9 已确立的通用规则，在实现前记录：

- 目标：**APPS**，不是 DS-1000；
- 需要哪些确切对象（benchmark revision、harness 修订、cutoff commit、具体 item id、probe/mutant 哈希）；
- 这些对象**在冻结时就已存在**的证据（引用分支 `research/apps-official-survivor-confirmation-20260729` 上已提交的 receipt，给出文件路径与 SHA-256）；
- 若无法在不读取目标结果的前提下证明正例可满足 → 写 `NOT_IDENTIFIABLE`，**不要**为了让 V2 好看而放宽。

**§F. 冻结测试清单。** V1 §6 的 26 条中与 in-memory 无关的全部保留，另加：

- 子进程输出被截断 → 弃权，不得确认；
- 孙进程写同一 fd → 检测或弃权；
- 超时后的部分输出 → 不得当作完整观测；
- 祖先关系不可验证 → 降为 review；
- 祖先关系被伪造（fork 造祖先）→ 拒绝（复用 external evidence 已有的 fork-ancestry 攻击测试）；
- 调用方自填 `harness_adversary_model` → 被 promotion 侧忽略并重新推导。

**§G. 三种结局的充分条件**：`PASS_TRUSTED_ADJUDICATOR_OS_VISIBLE` / `FAIL` / `NOT_IDENTIFIABLE`。一次对抗逃逸即 FAIL。

**§H. 非激活边界**：与 V1 §8 相同，V2 同样不授权任何实现。

### G.3 明确不做

不写 `benchcore/` 代码、不写测试、不改 `promotion.py`、不跑 APPS。

### G.4 预算

≤3 小时。零 API。单独一个 `protocol/gate` 提交。

---

## 9. 任务 H：`report.py` 的 stable / raw 二分

### H.1 目标

让审计报告可以做确定性哈希比对（当前因 `run_metadata.elapsed_seconds` 永远做不到）。

### H.2 做法

沿用 external evidence 协议 §7 已确立的模式：

- **stable payload**：items、violations、summary、coverage_ledger、field_mapping、methods_run、source_identity —— 一切语义内容；
- **raw / run metadata**：`elapsed_seconds`、wall-clock 时间戳、临时路径、PID、主机名、任何随运行变化的量；
- 报告新增 `stable_payload_sha256` 字段，只对 stable payload 计算；
- 两次相同输入的运行，`stable_payload_sha256` 必须相同；`audit.json` 整体哈希允许不同。

### H.3 硬约束

1. **不得改变任何 violation 的数量、tier、severity、defect_type**——这是纯报告层改动。加一条测试断言改动前后在同一输入上的 violation 集合完全相同；
2. **不得回改历史报告**。`reports/**` 下已提交的旧产物一律只读；
3. schema 版本号递增，旧报告没有新字段是正常的，读取端要能容忍。

### H.4 验收

- 新增测试：同一输入两次运行 → `stable_payload_sha256` 相等；
- 新增测试：violation 集合在改动前后不变；
- 全量测试从 fresh clone 通过。

### H.5 预算

≤2 小时。零 API。

---

## 10. 任务 I：GDPVal artifact manifest 冻结 → 恢复 → 重跑

**严格按这个顺序，不许调换。**

### I.1 步骤

1. **先冻 manifest**（单独提交，此时不得访问缺失文件）：
   `experiments/gdpval_full220.artifact_manifest.json`，内含
   - 数据集 revision `11e7900cdcac61bc4daf59e65feb238acda98fbf`；
   - 输入 parquet 的 SHA-256 `f8422fab9b21…`；
   - **所有** `gdpval_workbook_replay` 会用到的 reference artifact 的相对路径 + 期望内容 SHA-256（若某份的期望哈希当前不可知，如实写 `expected_sha256: null` 并标 `unknown_at_freeze: true`——**这一条本身就是重要记录**）；
2. 提交 manifest；
3. 再获取缺失的 `reference_files/cc781e4dc0985c8eb327a53ec03b5900/Population v2.xlsx`（如果本地或合规冻结来源里有）；
4. 校验实际内容 SHA-256，写进 manifest 的 `observed_sha256`；
5. 重跑两次，出新 receipt；
6. 无论结果是 7、是 5、还是别的数，**如实记录**。

### I.2 停止条件

- 如果无法从合规来源获得该文件 → 记 `NOT_RECOVERABLE`，GDPVal 的结论永久停在 **5 confirmed + 2 coverage unknown**，这是可接受的最终结果；
- 如果取到文件后 confirmed 变成了 7 **但** artifact 的哈希在 manifest 冻结时是 `unknown_at_freeze: true` → 必须在报告里显著标注"该 2 条 confirmed 依赖一份其期望哈希在冻结时未知的 artifact"。

### I.3 预算

≤1 小时。零 API。

---

## 11. 任务 J：报告摘要的覆盖可见性（小）

`benchcore/report.py` 的 markdown 摘要：

1. 在 "Unknown-tier findings" 之外，**加印** `audit_coverage.unknown` 与 `audit_coverage.operational_failed`，并让两者非零时的措辞明确区别于 findings 层的 unknown；
2. `operational_affected_items` 保留（定义没错），但在其后加印 `audit_coverage.operational_failed`，避免"0 运行问题"的误读；
3. 不改任何计数逻辑，只改展示。

**验收**：用本次 GDPVal 的 `audit.json` 重新渲染 markdown，摘要里必须能一眼看到"1 个 check 因运行失败未完成"。

**预算**：≤30 分钟。

---

## 12. 顺序、提交纪律与交付

### 12.1 顺序

```
G（V2 协议）  ← 最高优先，决定后面走不走得动
  ↓ 我复核
H（stable/raw）、I（GDPVal artifact）、J（报告可见性）  ← 可并行，不依赖 G
```

如果时间不够，**砍 H/I/J，把时间给 G**。

### 12.2 提交

- 继续用分支 `chore/hygiene-and-adjudicator-protocol-20260802`，或新开 `protocol/trusted-adjudicator-v2-20260802`；
- 每个任务独立提交；协议提交必须与任何实现分离；
- 不动 main，不 force push。

### 12.3 交付格式

沿用晨报格式（逐任务结局表 / 只列数字不解读 / 待决 / 没做的事及原因 / 提交序 / 关键产物 SHA-256 / 纪律自查）。

纪律自查新增两项：

- [ ] 未修改任何历史报告产物
- [ ] GDPVal 任务未出现"先取数据后补 manifest"

---

# 第三部分：Claude 并行执行的部分

## 13. P2：SVAMP 回归定位 + 仪器稳定性表

由我独立执行，理由是"改动作者不应 bisect 自己引入的回归"。纯离线、零 API、只读缓存与旧 commit。

目标现象：

| 时间 / 版本 | candidate P | R | **F1** | FP |
|---|---:|---:|---:|---:|
| v5（历史，DeepSeek V3） | 0.860 | 0.974 | **0.914** | 6 |
| 主线 2026-07-30 重跑 | 0.660 | 0.868 | **0.750** | 17 |
| DeepSeek V4 Flash 2026-08-01 | 0.659 | 0.763 | **0.707** | 15 |

同期 MMLU-1000：0.663 → 0.657（几乎不动）。

要回答的问题：为什么同一份 100 题、同一套真值、无 prompt 改动的情况下，SVAMP 掉 0.21 F1 而 MMLU 纹丝不动。

如果定位不到单一 commit（是多个改动的交互），**如实写"多因，不可归约"**——那本身就是"审计器是不稳定测量仪器"这个论点的最强证据。

---

## 14. 一句话总结

夜间交付的**纪律无可挑剔**，GDPVal 的差异处理和 external evidence 的 addendum 路径选择都比我预期的更严。

唯一要修的是：**协议把一个只覆盖 in-memory 的论证冻成了覆盖全部执行协议的结论，顺带关掉了 APPS 这条已经跑通的路。** 收窄它，把威胁模型的对手假设显式写出来，P0 就从"被永久封死"变成"在 OS-visible 协议上可能立刻可做"。
