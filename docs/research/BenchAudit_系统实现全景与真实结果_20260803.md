# BenchAudit 系统实现全景与真实实验结果

> 日期：2026-08-03
> 编写：Claude（独立红队），依据仓库代码与已提交产物逐项核对，非凭记忆
> 用途：把"系统到底怎么实现的"和"我们真正有什么结果"两件事一次讲清

---

# 第一部分：系统是什么

一句话：

> BenchAudit 把一个 benchmark 拆成 `任务 / 输入 / 参考答案 / 评分规则 / 执行环境 / 聚合规则` 六层，用多种互不相同的信号源找出可疑之处，然后由**一个中央策略**决定每条发现能站到哪个证据等级上——**只有能被独立本地程序重放的才叫 `confirmed`，模型判断一律封顶在 `review`，证据不足时记 `unknown` 而不是猜。**

它不是一个"检测器"，是一条**带证据天花板的流水线**。

---

# 第二部分：从头到尾的实现

## 层 0：加载与适配

```
原始 benchmark 文件（jsonl / parquet / 目录）
  → loader.py          读入行
  → field_mapping.py   把任意字段名映射到统一角色（question / gold / options / evaluator …）
  → adapter.py         协议族适配（可声明式，也可注册 adapter）
  → schema.py          统一成 BenchmarkItem
```

关键设计：**映射如果是"推断"出来的而不是显式声明的，后面 promotion 会因此把结论降级。** 见 `promotion.py:_mapping_is_trusted()`——推断映射有歧义时直接返回 `unknown`，理由是"这条发现可能只是字段映射猜错了"。

抽样用 `experiments/*.manifest.json` 冻结（含 `source_sha256`、`seed`、题目 ID 列表），保证同一实验可复现。

## 层 1：候选生成 —— 三条互不相同的信号源

### 1a. 确定性检查器（不调模型）

| 模块 | 检查器数 | 做什么 |
|---|---:|---|
| `checkers.py` | 6 | 通用结构：缺任务、选项域非法、重复 ID、schema 漂移 |
| `artifact_consistency.py` | 4 | 跨产物一致性、任务↔评分契约、grounded rubric |
| `workspace_invariants.py` | 1 | 文件清单重放、依赖图重放、元数据契约 |
| `value_recompute.py` | 1 | 把 rubric 里的数值重算一遍 |
| `swe_leak.py` / `code_verifier.py` | 各 1 | 代码类 benchmark 的解答泄漏 / 代码校验 |

这些的共同特点：**输出可以被第三方拿同样的输入重跑出完全一样的结果**。它们是唯一能走到 `confirmed` 的来源。

> **框架边界说明**：仓库里还有一组 benchmark 专用检查器（针对某个具体 benchmark 的 rubric/工作簿/文件名契约）。它们**不属于通用框架**，是单个 benchmark 的适配实例。本文的架构描述只覆盖通用层；专用层带来的结果在第三部分单独标注，不与通用能力混算。

### 1b. LLM 语义审计器（`llm_auditor.py`，10 个）

盲解、gold 审计、题面清晰度、选项集合、选项适用性、数量一致性、事件状态、呈现完整性等。

**内部有答案依赖的级联**：`build_gold_evidence_user_prompt(item, blind_solution, …)` 把上一次 LLM 的回答直接写进下一个 prompt；`blind_solution_is_risky()` / `defender_is_needed()` 这类门控函数决定**后续调用要不要发生**。这是覆盖率的来源，也是不稳定性的放大器（见第四部分）。

`llm_client.py` 负责调用、缓存、投票。缓存键 = `{cache_key_schema_version, model, base_url, temperature, max_tokens, dry_run, response_format, thinking, system, user}` 的 SHA-256。

### 1c. 执行证据层（`evaluator_execution.py` + `execution.py`）

这一层审的不是题目，是**评分器本身**：

```
LLM 只负责生成探针（等价实现 / 语义变异体），不做任何判断
  → 在隔离容器里用 benchmark 自己的测试输入真跑
  → 等价探针应当通过，变异体应当被杀死
  → 等价体被拒 → 评分器过严
  → 变异体存活 → 评分器覆盖不足
```

`execution.py` 的 `ContainerRunner` 走 `--network none`、只读根、非 root、能力裁剪。

## 层 2：覆盖账本（coverage ledger）

每一个 `item × checker` 组合都要留一条记录，状态取自闭集：
`planned / eligible / attempted / completed_no_finding / finding / operational_failed / ineligible / unsupported / security_blocked / abstained`。

**`completed_no_finding` 明确定义为"检查器正常返回且没发现问题"，不等于"这道题干净"。** 报告里会印出 `Coverage unknown` 与 `Operational failures`，让覆盖漏洞可见（2026-08-02 加强，此前只印 findings 层的 unknown，会误导）。

## 层 3：中央 promotion（`promotion.py`，848 行）—— 全项目的核心

每条 `Violation` 进来，按**固定顺序**过闸，先命中先返回：

| 顺序 | 条件 | 结果 |
|---:|---|---|
| 1 | 字段映射是推断的且有歧义 | `unknown` / `adapter_inference` |
| 2 | 是运行失败（`defect_scope == "operational"`） | `unknown` —— 运行失败描述的是覆盖，不是缺陷 |
| 3 | **检出方法是模型驱动的** | **`review` / `model_judgment`** —— 硬天花板 |
| 4 | 检查器自己声明 `review_only` | `review` |
| 5 | 属于数据集级证明族 | 拿**完整活数据**重放；过 → `confirmed`，否则 `review` |
| 6 | 属于 `DISABLED_UNATTESTED_PROOFS` | `review` —— 见下 |
| 7 | 属于对象级证明族 | 本地重放；过 → `confirmed`，否则 `review` |

三条铁律写死在代码里：

- **第 3 条不可绕过。** 任何模型判断、多模型共识、自洽投票，都到不了 `confirmed`；
- **重放抛异常 = 不确认，且不中断整场审计**（fail-closed）；
- **`DISABLED_UNATTESTED_PROOFS`** 目前封掉三个执行证明族：

```python
("execution_replay",      "executed_harness",                 "gold_rejected_by_evaluator")
("execution_differential","executed_differential_confirmed",  "overstrict_evaluator")
("execution_kill_matrix", "executed_kill_matrix_confirmed",   "evaluator_mutation_survived")
```

理由写在代码注释里：*"a caller-controlled trust-domain string and well-shaped hashes are not proof."* 执行器和数值裁决目前共用一个解释器，harness 能 monkeypatch 比较器，所以**执行类结论目前全部封在 `review`**。

当前 live 的证明族约 24 个。按来源拆开看很重要：

| 类别 | 证明族数 | 说明 |
|---|---:|---|
| **通用** | 约 11 | 静态规则重放、选项域重放、安全算术重放、工作区清单/依赖/元数据重放、可执行证据重放、跨产物契约、数据集重复 ID/矛盾 oracle |
| benchmark 专用适配 | 约 13 | 单个 benchmark 的 rubric/工作簿/文件名契约，不计入通用能力 |

**注册表里专用族比通用族还多**——这本身就是当前系统的真实画像：确认能力的覆盖面主要靠逐个 benchmark 手写扩出来的，而不是通用规则自然覆盖到的。

## 层 4：报告（`report.py`）

统一 JSON + Markdown。2026-08-02 起做了 **stable / raw 二分**：语义内容进 `stable_payload_sha256`，`elapsed_seconds`、本地路径这类易变字段留在 raw。**同输入两次运行的 stable hash 必须相同**——在此之前 `elapsed_seconds` 在被哈希的 payload 里，任何报告都不可能逐字节确定。

## 层 5：下游

- `ranking_impact.py`：剔除缺陷题后重算 leaderboard（Kendall τ、名次变动、per-subject 冠军变化），并带**随机删题对照**；
- `defect_injection.py` + `scripts/run_ds1000_defect_injection.py`：注入已知缺陷来测**检出召回**（这是"确认层的分母"，见第四部分）；
- 修复闭环：**尚未实现**。

## 层 6：还未接线的部分（Phase 2A，已实现但物理隔离）

`trusted_adjudicator.py`（649 行）：把观测捕获与数值裁决拆到不同信任域，只处理 **OS 可见字节流**（stdout / exit status），带完整性签名与 MR-4 差分裁决。

**当前完全非激活**：`production_manifest_ids()` 返回 `()`，模块外零引用，不产生 `Violation`，不进 promotion。要激活需要一个能跑生产 Git verifier 的执行环境——见第五部分。

---

# 第三部分：真实实验结果

## 3.0 先说一个必须摆在最前面的事实

**通用层在真实未修改数据上的 `confirmed` 数是 0。**

| 数据集 | 真实未修改数据上的 confirmed |
|---|---:|
| SVAMP-100 | **0** |
| MMLU-Redux-1000 | **0** |
| MMLU-Redux-200 | **0** |
| Workspace Lite-CN 100 | **0** |
| Workspace Full 388 | **0** |

唯一一批真实数据上的 confirmed（5 条）来自**某个 benchmark 的专用契约检查器**，属于适配实例而非通用能力，因此**不计入通用层战绩**。

这条事实决定了整个项目现在的定位：**通用确认通道已经建好、经过对抗测试、但还没有在真实数据上开过火。** 后面所有"正结果"都要在这个前提下读。

## 3.1 能守住的正结果

### DS-1000 执行证据层 —— 2 条真评分器缺陷（但只能记 review）

60 题 / 411 探针 → 141 等价体全部通过、190 变异体杀死 186、存活 4。人工核实后：

- **id=11**：harness 根本检测不到时区是否真被移除——而那正是这道题要测的属性；
- **id=300**：`assert_allclose` 的广播行为让它对形状不敏感；
- id=308 是方法级假阳（property-based 比较器忽略 `ans`，题目允许多解），已加自动降级。

**这两条是真缺陷，但因为第三部分说的裁决器问题，目前封在 `review`。**

### 注入缺陷验证 —— 确认层的召回下界

20 道干净题 × 3 类评分器缺陷：

| 注入缺陷 | 检出 |
|---|---:|
| `neutralize_comparator`（比较前直接返回通过） | **20/20** |
| `reject_gold`（断言取反） | **20/20** |
| `implementation_assert`（钉死 gold 特有写法） | **13/20 (65%)** |

65% 的漏检有明确机制解释：被钉住的 token 恰好是所有生成等价体都会用的自然写法。**这是可解释的召回下界，不是噪声。**

### APPS stdin/stdout 差分合同 —— 跨协议迁移

同一套确认合同从函数调用协议迁到 stdin/stdout 协议；135 对完成，7 条 weak-pass/strong-fail 跨 4 个 task（1402 ×3、1785、1849、4352 ×2）；19 次对抗攻击全部降级为 `review` 或不产出。

### 候选层监督指标 —— 当前模型（DeepSeek V4 Flash，2026-08-01 同批重跑）

SVAMP-100，四个系统在**同一天、同一模型、同一份题目 manifest** 下重跑：

| 系统 | pred | TP | FP | FN | P | R | **F1** |
|---|---:|---:|---:|---:|---:|---:|---:|
| Rules-Only（零 LLM） | 0 | 0 | 0 | 38 | 0.000 | 0.000 | **0.000** |
| Naive LLM（单次提问） | 32 | 24 | 8 | 14 | 0.750 | 0.632 | **0.686** |
| LLM + 分类法 | 40 | 25 | 15 | 13 | 0.625 | 0.658 | **0.641** |
| **BenchCore（结构化分解）** | 44 | 29 | 15 | 9 | 0.659 | **0.763** | **0.707** |

MMLU-Redux，当前模型：

| 数据集 | pred | TP | FP | FN | P | R | **F1** |
|---|---:|---:|---:|---:|---:|---:|---:|
| MMLU-1000 | 351 | 237 | 114 | 133 | 0.675 | 0.641 | **0.657** |
| MMLU-200（21-method） | 80 | 63 | 17 | 37 | 0.787 | 0.630 | **0.700** |
| MMLU-200（18-method） | 92 | 70 | 22 | 30 | 0.761 | 0.700 | **0.729** |

### ⚠ 一个必须说的退化：F1 上的优势已经掉进噪声里

在当前模型下，BenchCore 相对 Naive LLM 是 **+0.021 F1**（0.707 vs 0.686）。

而我们自己测出来的**同代码同配置 5 次重复的 F1 极差是 0.046**（见 3.4）。

> **+0.021 < 0.046 —— 所以在 SVAMP 上，"结构化分解的 F1 优于单次提问"这个主张在当前证据下不成立。** 两个臂都只跑了一次，差值落在噪声带内。

**召回上的优势看起来是真的**：0.763 vs 0.632，差 **+0.131**；而我们 5 次重复的召回全部落在 0.763–0.842 区间，naive 的 0.632 **低于全部五次**。所以可守住的表述是：

> 结构化分解**显著提高召回**（+0.13，超出重复运行区间）；**F1 上的优势不可归因**，需要每臂多次运行才能判定。

"分类法反而有害"这一条在当前模型下仍然成立（0.641 < 0.686），且方向与历史一致。

Rules-Only 在 SVAMP 上仍是 0.000——**说明 LLM 层不是可选项，而是这类语义缺陷的唯一来源**；但也正因如此，3.4 的不稳定性直接落在系统的主力路径上。

## 3.2 受控/合成条件下的结果（**不能当自然缺陷检出率读**）

### Workspace-Bench 结构不变式

| 套件 | 源任务 | 配对变异 | 精确召回 | 额外告警 |
|---|---:|---:|---:|---:|
| Full | 388 | 1,940 | **1,940/1,940 = 1.000** | 0 |
| Lite | 100 | 500 | **500/500 = 1.000** | 0 |

**这是五个自己设计的确定性算子的一致性/回归结果**，不是自然缺陷率、不是留出根因召回。

### Workspace 语义证书挑战

50 个真实任务 × 4 种客观干预 = 200 对：

| 判定层 | 变异召回 | 干净假阳 | 配对 |
|---|---:|---:|---:|
| 原始 LLM 扫描 | 1.000 | 0.170 | 0.830 |
| 引文接地（排除证书） | 0.570 | 0.050 | 0.540 |
| **客观证书** | **1.000** | **0.000** | **1.000** |

**但挑战生成器和判决器共用四条相同的原子语法**，所以这是证书一致性，不是改写泛化。

### 未修改的 Workspace 数据

| 套件 | confirmed | review | 
|---|---:|---:|
| Lite-CN 100 | **0** | 1 |
| Full 388 | **0** | 2 |

## 3.3 负结果（都是有价值的）

| 结局 | 内容 |
|---|---|
| `NOT_IDENTIFIABLE_PREFLIGHT_V1` | APPS 输入域证书：非目标预飞机械覆盖率 **33/1327 = 2.49%**，按预注册纪律终止，没有退化成 benchmark 专用 parser |
| `NOT_IDENTIFIABLE_DATA` | PAIChecker 复现：目标标签不可机械判定 |
| `NOT_IDENTIFIABLE_DATA_LINKAGE` | DBCode 适配成本曲线：task/candidate/reference/score 完整执行链 **0/0** |
| 5 × `NOT_IDENTIFIABLE` | external evidence Git verifier：策略层 + gate + 协议 V1/V2 + 实现 + 48 测试 + 2 次回放，**产出零条已验证外部证据** |
| `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR_IN_MEMORY` | DS-1000 的内存对象无法独立于不可信解释器认证 |
| `NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY` | Podman 3.4.4 与 Docker 29.4.1 双引擎都无法实例化冻结拓扑；**本宿主无直接出口** |
| A / A′ / A″ 路由 | 独立 holdout 上增量 reviewed TP = 0；A′ family recall 从 84.2% 降到 63.2%；全部关闭 |

## 3.4 最新、也最重要的结果：审计器自己是不稳定的测量仪器

### SVAMP-100，同代码同配置，同日 5 次重复（2026-08-02，¥7）

| run | pred | TP | FP | FN | F1 |
|---|---:|---:|---:|---:|---:|
| 1 | 44 | 29 | 15 | 9 | 0.707 |
| 2 | 47 | 32 | 15 | 6 | **0.753** |
| 3 | 46 | 30 | 16 | 8 | 0.714 |
| 4 | 44 | 29 | 15 | 9 | 0.707 |
| 5 | 44 | 29 | 15 | 9 | 0.707 |

**F1 极差 0.046，标准差 0.020。** 10 个配对：

| 层级 | 均值 | min |
|---|---:|---:|
| item Jaccard | 0.962 | 0.936 |
| **violation Jaccard** | **0.845** | 0.796 |

逐方法复现率——**分离是完全的**：

| 方法 | 复现率 |
|---|---:|
| `static_rule` / `cross_artifact_consistency` | **1.00** |
| `llm_event_state_nonmaterial` | 1.00 |
| `llm_quantity_consistency` | 0.90 |
| `llm_event_state` | 0.87 |
| `llm_quantity_consistency_nonmaterial` | 0.84 |
| `llm_question_clarity` | 0.73 |
| **`llm_gold_audit`** | **0.68** |

### MMLU-200 清洁复现对（2026-08-02）

| | Run 1 | Run 2 |
|---|---:|---:|
| TP / FP | 68 / 18 | 62 / 21 |
| F1 | 0.731 | 0.678 |

item Jaccard **0.811**、violation Jaccard **0.683**，**都低于 SVAMP 十对的最小值**；确定性方法仍是 **1.00**（第三次独立复制）。

裁决：`DOES_NOT_SUPPORT_MMLU_MORE_STABLE_FOR_THIS_PAIR`。

### 机制

温度 0 下 provider 并非逐位确定 → 盲解回答略有不同 → 被嵌进下游 prompt → 缓存键变、门控函数改变后续调用是否发生 → **约 40% 的 LLM 调用在两次运行中根本不是同一次调用**。

### 结论

> **聚合 F1 的稳定不等于仪器的稳定。** MMLU 跨版本 F1 只动 0.006（0.663→0.657），但它逐条 finding 的复现率比 SVAMP 更差。用单跑 F1 比较版本是**主动误导**的。

推论：**我们过去所有"某改动让 F1 变了 X"的单跑结论都要重标为不可归因**，除非该改动走确定性路径。

## 3.5 排名影响（MMLU-Redux，15 模型）

| 剔除依据 | 题数 | 全局 τ | 最大名次变动 | Top-1 变化 | per-subject 冠军易主 |
|---|---:|---:|---:|---|---|
| 第三方标注 | 181 | 0.981 | 1 | 否 | 2/28 |
| 我们审计器检出 | 318 | 0.981 | 1 | 否 | 9/28 |

审计器 vs 第三方标注：**precision 0.43 / recall 0.76 / F1 0.55**——不依赖第三方标注就能高召回定位已知缺陷，这一条站得住。

**但"9 个 subject 冠军易主"不能当影响证据**：随机删等量题的对照显示无统计差异（**p ≈ 0.32**），唯一稳健单点是 philosophy（随机翻转概率 1.8%）。

> 所以在 MCQ 上，"修好错题 → 排名变化"这条 so-what 很弱，且**是我们自己用随机对照证伪的**。

## 3.6 引用审计（2026-08-02）

对 GPT 那份 1107 行综述做机械核验，83 个唯一 URL：

| verdict | 数 |
|---|---:|
| resolved | 26 |
| title_mismatch | 55 |
| unreachable | 2 |
| **not_found** | **0** |

**主结论：没有一条是编造的链接。** 55 条 title_mismatch 经抽查主要是简称 vs 全名（`EvalPlus` ↔ "Is Your Code Generated by ChatGPT Really Correct?"、`TracIn` ↔ "Estimating Training Data Influence…"），**不是错误引用数**；其中 6 条实为 OpenReview 反爬页。

**仍未核**：约 20 篇 2026 年新论文是否确为所指，以及 12 个具体数值主张（84% Precision@50、95% top-200、57% Virology、4.2–9.0% resolved rate 等）。这些进人工 review，**机械层已按边界停止**。

---

# 第四部分：当前真实能力边界

| 能力 | 状态 | 最强证据 | 缺口 |
|---|---|---|---|
| 候选生成 | 成熟 | 召回显著优于单次提问（+0.13） | **F1 优势落在噪声内**；跨版本不可归因 |
| **通用层确定性确认** | **已建成，真实数据上尚未开火** | 对抗控制全部 fail-closed | **真实未修改数据 confirmed = 0** |
| 执行类确认 | **物理关闭** | DS-1000 两条真缺陷 | 缺可信裁决器 |
| 主动弃权 | 成熟 | review 天花板、fail-closed、`unknown` 分层 | — |
| 自动适配 | 初步 | 确认合同跨函数调用与 stdin/stdout 复用 | adapter 仍手写；DBCode A0 失败 |
| 修复闭环 | **不存在** | — | 从未跑通一次 |
| 排名后果 | 有工具、效应弱 | τ=0.981、随机对照 p≈0.32 | MCQ 上 so-what 不成立 |

**可以守住的项目主张**：

> BenchAudit 已经证明一套带证据天花板、fail-closed 与主动弃权的确认合同能跨执行协议复用并抵住对抗攻击；同时用同代码重复运行首次量化了**审计器自身作为测量仪器的不稳定性**，并证明确定性层与 LLM 层在复现性上完全分离（确定性 1.00，LLM 0.68–0.90）。
>
> **尚未证明**：通用层能在真实未修改数据上产出 confirmed（当前为 0）；任意 benchmark 的适配可以自动完成；结构化分解在 F1 上优于单次提问。**尚未完成**任何一次修复—回归闭环。

---

# 第五部分：现在卡在哪

```
北极星（新 benchmark 上产出可重放 confirmed 并完成修复闭环）
  └─ APPS 双正例
       └─ 可信裁决器激活
            └─ 生产 Git verifier
                 └─ 一台有直接出口的机器   ← 卡在这里
```

本宿主直连一律超时，只有 `127.0.0.1:17890` 代理可用；而冻结的 verifier 拓扑要求容器经受限 allowlist 代理出网，Podman 3.4.4 与 Docker 29.4.1 都无法同时满足"代理可达 + 直连不可达"。已按约定永久收口，不再迭代拓扑。

**瓶颈已经从"方法设计"转成"执行环境"。**

Phase A（适配成本曲线）死在 DBCode A0；Phase B（修复闭环）我建议的 DS-1000 id=300 目标同样挂在裁决器上。

## 没被卡住、且都便宜的下一步

1. 约 20 篇 2026 新论文 + 12 个数值主张的人工核验（引用审计已交界）；
2. 17 条假阳的盲审（需无历史上下文的复核者）；
3. SVAMP 三臂 × 三跑消融（主靶已收窄为 `llm_gold_audit`，启动前先做零 API 调用量预飞）；
4. 把注入算子从 DS-1000 专用脚本提升为协议无关组件，做出**协议 × 缺陷类的确认召回矩阵**——这是文献里没有的"确认层分母"。

---

# 附：读这份文档时要小心的三件事

1. **通用层在真实未修改数据上的 `confirmed` 是 0**；唯一那批真实 confirmed 来自单个 benchmark 的专用检查器，属适配实例，不能计入通用能力；
2. **Workspace 的 1940/1940 是自己设计的注入算子的一致性结果**，不是自然缺陷检出率，任何对外材料都不能简写成"召回 100%"；
3. **任何单跑得出的跨版本比较都不可归因**——这是我们自己测出来的（3.4），对内对外一视同仁。
