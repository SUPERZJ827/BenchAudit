# BenchAudit 研究定位复核与可执行规划

> 日期：2026-08-01
> 复核对象：`docs/research/BenchAudit_自动化Benchmark审计领域系统调研_20260731.md`（GPT 撰写，1107 行）
> 复核方式：**零 API、零外网**。全部依据本仓库已提交的实验产物、代码与 git 历史。
> 作者角色：独立红队复核 + 规划，不写生产代码。

---

## 0. 一句话总判断

综述的**领域框架是对的，研究空白清单是错的方向不多但优先级几乎全错，而且它对我们自己已有的资产一无所知**——它是一份"从零开始的领域地图"，不是一份"我们该做什么"的规划。

三个最关键的事实，综述一个都没有：

1. **我们在真实未修改数据上已经有 7 条 `confirmed`**（GDPVal 220 题，确定性重放，零 LLM）。综述把"产生第一条可重放 confirmed"写成北极星——**这个北极星我们 7 月 16 日就已经越过了**，所以它作为目标已经失效。
2. **执行类 benchmark 的 confirmed 通道当前是物理关闭的**。`benchcore/promotion.py:587` 的 `DISABLED_UNATTESTED_PROOFS` 把三个执行证明族全部禁用，理由是"caller-controlled trust-domain 字符串和形状正确的哈希不是证明"。DS-1000 的两条真缺陷因此只能停在 `review`。**这是全项目唯一的关键路径瓶颈**，综述和我们自己的路线图都没有把它放在第一位。
3. **我们自己的排名影响实验已经自证 so-what 很弱**：MMLU-Redux 全局 Kendall τ=0.981、最大名次变动 1 位、Top-1 不变；per-subject 冠军易主经随机删题对照后**不显著（p≈0.32）**。综述 §10、§14-G7 仍把"排名影响"当作可期待的收益，这与我们自己的数据相反。

因此本文的规划不是综述的补充，而是**替换它的第 14–18 章**。

---

## 1. 复核的证据口径

我能验的和不能验的必须分开写，否则这份复核本身就违反了我们自己的证据纪律。

| 复核维度 | 本次能否验证 | 依据 |
|---|---|---|
| 综述的内部逻辑一致性 | ✅ 能 | 通读全文 |
| 综述结论 vs 我们仓库的真实产物 | ✅ 能 | `reports/`、`benchcore/`、git 历史 |
| 综述引用的论文是否真实存在 | ❌ **不能** | 本机无外网出口（DNS 可解析，TCP 443 超时） |
| 综述引用的具体数字是否与原文一致 | ❌ **不能**（除少数几条） | 同上 |

**已经在此前会话中被独立核实过的引用只有两条**：Fantastic Bugs（arXiv 2511.16842，Precision@50 最高 84%，GSM8K）——综述 §4.2 第 221 行的描述**正确**；PAIChecker（arXiv 2607.28587）——综述 §7.3 表格里"主要是自动审查/人工验证，不是统一 proof contract"的定位**正确**。

这两条对上了，说明综述不是凭空编的。但**其余 78 条引用与全部数字，按我们自己的标准只能是 `review` 级**：它们是 LLM 生成的断言，没有绑定可重放的来源。见 §5。

---

## 2. 综述中正确、应当保留的部分

这些是真的好，直接进论文的 related work 骨架：

| 位置 | 内容 | 为什么对 |
|---|---|---|
| §1.2 | 把 item / evaluator / judge / contamination / construct / leaderboard 拆成六个**不同的审计对象**，各自需要不同证据 | 这是全文最有价值的一段。绝大多数"评测可靠性"论文的硬伤就是混用这六个单位 |
| §2.1 | E0–E5 五级证据阶梯 | 比我们现在的 confirmed/review/unknown 三级更完整，往上补了 E4 修复、E5 后果两级。**建议直接采用**，把我们的三级映射成 E1/E3/unknown |
| §6.4 | "judge verdict flip 是 evaluator relation violation，不自动说明哪一次 verdict 错" | 完全正确。这一句能杀掉半数 judge 审计论文的主张 |
| §7.2 | 变异体存活 ≠ 测试缺口，需要 `∃x: P(x)≠P'(x)` 且 x 是域内合法输入 | 正确，而且和我们 DS-1000 的实际教训一致（id=308 就是 property-based 比较器导致的方法级假阳） |
| §9.2 | 通用 provenance（PROV/in-toto/SLSA）只答"从哪来"，不答"这份证据允许证明什么" | 正确，这正是我们 external-evidence gate 做的事 |
| §12 | 横向比较表，明确"不存在同时高语义覆盖 + 高确定性 + 低成本的方法" | 正确，是分层架构的正当性论证 |
| §15.1 | 反事实 judge 审计**不应**和 BenchAudit 合成一篇 | 正确。两者 target claim 不同，合并会两边都不硬 |
| §17.1 | 划分必须按 benchmark family 隔离，不能按 candidate 行随机切 | 正确，是最常见的泄漏陷阱 |
| §18.2 | "不应声称"清单 | 全部正确，逐条都该贴在论文写作时的显示器边上 |

---

## 3. 需要修正的部分

### W1｜北极星已经失效，必须重新定义（最重要）

综述 §21 和我们自己 7-30 的路线图都写：

> 在**没有为单个 item 手写证明器**的新 benchmark 上产生至少一条可重放的 confirmed 缺陷。

**这个条件已经被满足了。** `reports/gdpval_objective_full220_20260716/audit.md`：

```
Items: 220   Violations: 18   Confirmed: 7   Review: 11   Unknown: 0
Methods: gdpval_objective, gdpval_workbook_replay, gdpval_dataset_objective, duplicate_conflict
Elapsed: 7.15s
```

7 条 confirmed 的构成（从 `audit.json` 重算）：

| 缺陷类型 | confirmed 数 |
|---|---:|
| `task_artifact_contract_mismatch` | 4 |
| `rubric_artifact_contract_mismatch` | 2 |
| `rubric_reference_contract_mismatch` | 1 |

零 LLM、零 item-level verifier、7 秒跑完 220 题、OpenAI 官方 benchmark 的未修改数据。**这是全项目最强的一条真实结果，而综述和路线图都没提。**

问题在于："没有 item-level 证明器"这个门槛太低——它几乎是免费的。真正贵的是 `benchcore/gdpval_objective.py` + `gdpval_artifacts.py` 这一整套 **benchmark-specific 生产代码**。所以正确的北极星应该往上抬一级：

> **修订后的北极星（可证伪）**
>
> 对一个此前从未接入、但属于**已注册协议族**的 benchmark，在**新增 benchmark-specific 生产代码 = 0 行**（只允许声明式 mapping/config）的前提下：
> 1. 产出 ≥1 条可由第三方 fresh clone 重放的 `confirmed`；
> 2. 在同一次运行的合法对照集上 `confirmed` 假阳 = 0；
> 3. 在注入缺陷集上 `confirmed` 召回 ≥ 预注册阈值。
>
> 三条缺一不可。只有 (1) 是存在性证明，不是结果。

这个版本才是真正没做到、且做到了有分量的。

### W2｜执行类 confirmed 通道是关闭的，这是唯一的关键路径

`benchcore/promotion.py:587`：

```python
DISABLED_UNATTESTED_PROOFS = frozenset({
    ("execution_replay", "executed_harness", "gold_rejected_by_evaluator"),
    ("execution_differential", "executed_differential_confirmed", "overstrict_evaluator"),
    ("execution_kill_matrix", "executed_kill_matrix_confirmed", "evaluator_mutation_survived"),
})
```

`promotion.py:317/339/365` 的三个谓词其实**已经写好了**接受条件，包括 `adjudicator_trust_domain == "separate_process_v1"`。但整族被禁用，因为 `evaluator_execution.py:29` 承认当前实际值是 `shared_untrusted_driver`——harness 代码和数值裁决共用一个解释器，harness 可以 monkeypatch 比较器。

**后果链条**：

- DS-1000 的 id=11（时区盲）、id=300（`assert_allclose` 广播盲）是**真缺陷**，但只能记 `review`；
- APPS stdin/stdout 差分合同的迁移成果，同样落在 review；
- 路线图 Phase A 的 A4 判据写着"产生 ≥1 条可重放 confirmed"——**在当前代码下这个判据在执行类 benchmark 上不可能被满足**，Phase A 无论怎么跑都只能返回"成本已测量，能力未验证"；
- 论文的"确认"支柱在执行协议上目前是空的。

所以：**在做任何新 adapter、任何新 benchmark、任何 external evidence 之前，先做 trusted adjudicator。** 这是唯一一件做完之后所有下游都解锁的事。综述没提（它不知道），路线图把它排在 Phase A 之后（顺序错了）。

### W3｜G3（域内合法区分输入证书）我们已经预飞失败了

综述 §14-G3 和 §15 第四推荐都在推这条路。但我们自己的记录：

> APPS input-contract V1：非目标覆盖率 **33/1,327 = 2.49%**，触发 `NOT_IDENTIFIABLE_PREFLIGHT_V1`。
> —— `docs/research/CONFIRMATION_CONTRACT_LONG_TERM_ROADMAP_20260730_zh.md` §2

综述在不知情的情况下推荐了一条我们已经按预注册纪律关闭的路线。**不要重开**。综述 §15 第四推荐里那句"必须先做非目标数据 preflight，未过门槛即停止"恰恰是我们已经执行并且没过的流程。

### W4｜G5（适配成本）是评估维度，不是研究空白

"接入新协议要多少人工"是一张好表，但它不是可发表的新颖性——综述自己在 §15 也承认这点（"adapter 成本曲线不作为独立新颖性主张"），却又把它列成 G5 空白，自相矛盾。而且我们的 Phase A 已经在 A0 就卡住了（DBCode 数据关联完整链 0/0）。

**处理**：降级为主线论文的一张成本表，不作为独立方向。

### W5｜"生死门槛 #1" 可以被空系统满足

综述 §17.5 第 1 条："合法 benchmark control 上 confirmed 假阳必须为 0"。

一个**永不 confirm 任何东西的系统**完美满足这一条。这个门槛必须和一个下界配对：

> #1a：合法对照集上 confirmed FP = 0；**且**
> #1b：注入缺陷集上 confirmed 召回 ≥ 预注册阈值（按缺陷类分别报告）。

我们已经有做 1b 的机器（见 §4-W7）。综述漏了这个配对，是清单里最实质的一个漏洞。

### W6｜排名影响这条 so-what，我们自己的数据已经打脸

`reports/ranking_impact/ranking_impact.md` + `closed_loop_ranking.md` + `random_deletion_control.md`：

| 剔除依据 | 剔除题数 | 全局 τ | 最大名次变动 | Top-1 变化 | per-subject 冠军易主 |
|---|---:|---:|---:|---|---|
| 第三方 MMLU-Redux 标注 | 181 | 0.981 | 1 | 否 | 2/28 |
| **我们审计器自己检出** | 318 | 0.981 | 1 | 否 | 9/28，**随机对照后不显著 p≈0.32** |

唯一稳健的单点是 philosophy（随机翻转概率 1.8%）。

**结论**：在 MCQ 类 benchmark 上，"修好错题 → 排名变化"这条 so-what 是弱的，而且我们已经用随机删题对照亲手把它证伪了。综述 §10.3 建议报告的七个排名指标当然都对，但**指标丰富不能救效应量为零**。

**正确的替代路线**：把后果指标从"删题改排名"换成"**修 evaluator 改 accept/reject**"。理由：

- 删一道错题只是把 15 个模型的分母同步缩小，几乎不改变相对序（这就是 τ=0.981 的来源）；
- 修一个 evaluator（比如 DS-1000 id=300 的形状盲比较器）会让**特定模型的特定输出从 pass 翻成 fail**，这是非同步的、有方向的扰动，效应量天然大得多。

这直接决定了下面 W8 的目标切换。

### W7｜Phase B 的修复目标选错了

路线图 B1 选 `workspacebench-351` 的文件名碰撞。它确实证明容易（确定性 manifest replay），但它**没有模型输出**，所以路线图自己也预写了 `ranking_impact_not_identifiable`。也就是说：**做完 B1 拿不到任何后果证据**。

**建议改为**：首个修复闭环目标改为 **DS-1000 id=300 / id=11 的 evaluator 修复**。

| 维度 | workspacebench-351 | DS-1000 id=300 |
|---|---|---|
| 缺陷确认难度 | 低（已 confirmed 通道） | 中（依赖 W2 的 adjudicator） |
| 修复意图唯一性 | **不唯一**（哪份文件改名？路线图自己列了 4 项 identifiability gate） | 唯一（比较器必须检查 shape，这是任务本身要测的属性） |
| 有无模型输出可重评分 | **无** | **有**（DS-1000 有公开模型提交） |
| 能否产出 E5 后果证据 | 否 | **能** |
| 一次修复覆盖的 item 数 | 1 | 一族（所有用同一比较器模式的题） |

代价是它被 W2 卡着。这恰好再次说明：**adjudicator 是关键路径**。

### W8｜综述完全没写"审计器本身是否可复现"

这是它最大的遗漏，而我们手上有全领域最硬的证据。

**SVAMP 同一份 100 题、同一套真值标注，我们自己的系统在三个时间点：**

| 时间 / 版本 | candidate P | R | **F1** | FP | 来源 |
|---|---:|---:|---:|---:|---|
| v5（历史，DeepSeek V3） | 0.860 | 0.974 | **0.914** | 6 | `RESULTS.md` |
| 主线 2026-07-30 重跑 | 0.660 | 0.868 | **0.750** | 17 | `reports/svamp_mainline0730_comparison.md` |
| DeepSeek V4 Flash 2026-08-01 | 0.659 | 0.763 | **0.707** | 15 | `reports/deepseek_v4_flash_rerun_20260801/svamp100_comparison.md` |

同期 MMLU-1000 却稳定：0.663 → 0.657。

**也就是：在没有任何 prompt 字符串改动的情况下，我们自己的审计器在 SVAMP 上掉了 0.21 F1，假阳翻了近 3 倍，而在 MMLU 上纹丝不动。** 原因至今未定位（嫌疑集中在 `promotion.py`（07-08 时还不存在，现 848 行）和 `report.py`）。分支 `research/svamp-fp-regression-bisect-20260731` 已开但未收口。

配合此前记录的 B2 codegen **temperature=0 下 40% verdict 翻转**、以及 probe 生成多样性对召回的影响，可以形成一个领域里**没人报告过**的结论：

> **自动 benchmark 审计器本身是一个不稳定的测量仪器。** 文献普遍报告 top-k precision，但从不报告同一系统在同一数据上跨版本 / 跨温度 / 跨模型的 run-to-run 稳定性。

这条既是我们的诚实义务，也是一个便宜且独立的贡献点（缓存都在，几乎零 API 成本）。

### W9｜没有预算上限和止损开关——这是本项目已经发生过的最大浪费

综述 §15 排了五个推荐方向，没有任何一个带成本上限或终止条件。而我们的实际教训是血的：

**external-evidence 这条线的实际消耗**：policy 层 + promotion gate + 18 测试 + APPS fixture + V1 协议 + V1 预飞 + V2 协议 + 实现 + 48 测试 + 2 次回放尝试。
**产出**：**连续 5 次 `NOT_IDENTIFIABLE`，零条已验证外部证据，对 BenchAudit 的审计能力零改变。**

其中 #1–#4 是有价值的负结果（数据不匹配 / 协议冻错，后者还产出了可复用的"正例可满足性冻结规则"）。**#5 完全没有产生知识**——它是一个网络出口问题穿着研究结论的外衣。

同期，路线图自己的北极星 Phase A / Phase B 从 07-30 起**一行没动**。

**任何新方向必须自带**：预注册的最大人工时长、最大 API 成本、以及"出现什么现象就停"的止损条件。见 §7。

---

## 4. 综述遗漏的三个真空白（我们能填，别人不方便填）

### 空白 A｜confirmation 层没有分母

全领域（包括综述覆盖的 80 篇）报告的都是 **precision@k**。没人报告 **confirmation recall**，因为真实缺陷总体未知。

**但我们有一个合法的分母：注入 evaluator 缺陷。** `scripts/run_ds1000_defect_injection.py` 已经实现了三类算子：

| 注入缺陷 | 语义 | DS-1000 检出率 |
|---|---|---:|
| `neutralize_comparator` | exec_test 在比较前直接返回 1 | **20/20 (100%)** |
| `reject_gold` | harness 断言取反 | **20/20 (100%)** |
| `implementation_assert` | 断言一个 gold 特有的实现 token | **13/20 (65%)** |

`implementation_assert` 的漏检有明确机制解释：被钉住的 token 恰好是所有生成等价体都会用的自然写法——**这是一个可解释的召回下界，不是噪声**。

**要做的事**：把这三个算子从 DS-1000 专用脚本提升为 `benchcore` 里协议无关的组件，在 ≥3 个执行协议上跑，得到一张 **协议 × 缺陷类 的 confirmation recall 矩阵**。这是文献里没有的东西，而且代码 80% 已存在。

### 空白 B｜审计器的仪器稳定性（见 W8）

指标建议：同输入同版本重跑的 finding 集合 Jaccard；跨温度的 verdict 翻转率；跨底层模型的 finding 集合重叠；跨自身代码版本的 F1 漂移。全部可用现有缓存离线算。

### 空白 C｜"证据允许证明什么"的策略化 provenance

综述 §9.2 把它识别为空白，判断正确——**而且我们已经把它实现了**（`external_evidence.py` 的 `_ROLE_CAPABILITIES` / `_RELATION_CAPABILITIES`、policy 重算 `allowed_uses`、cutoff 祖先关系而非时间戳、post-cutoff 拒收未使用的 blob hash）。

**定位必须诚实**：这是**基础设施贡献**，是论文的一个 section，不是论文的主张，也不该再投入任何工程时间（见 W9）。当前状态冻结在 `PASS_VERIFIER_NOT_ACTIVATED` 未达成、Phase 2B 禁止。**不冻 V3。**

---

## 5. 这份综述本身要过我们自己的证据关

一个尴尬但必要的观察：**这份综述是 LLM 生成的，按我们自己的策略，它整体是 `review` 级。** 它断言了约 80 条引用和至少 12 个具体数字（3.3% 标签错误、57% Virology、84% Precision@50、95% top-200 precision、77% SWE-bench Verified 实例、4.2–9.0% resolved rate 下降、419 对、144 unit tests、18,000 次模拟、2,636 个 mutant、93 项研究、445 个 benchmark……）。

其中只有 2 条经过独立核实。**风险集中在 2026 年的引用**：`aclanthology.org/2026.acl-long.1162/`、`2026.acl-long.719/`、`2026.findings-eacl.89/`、`openreview.net/pdf?id=...` 这类精确 ID 正是幻觉高发形态。

**要求 GPT 做一次引用 receipt 审计**（在有外网的机器上，一次性脚本，约 1 小时）：

对每条引用产出一行 receipt：

```json
{"cite_id": "...", "url": "...", "http_status": 200,
 "resolved_title": "...", "title_match": true,
 "venue_claimed": "ACL 2026", "venue_observed": "...",
 "numbers_claimed": ["84% Precision@50"], "numbers_verified": null,
 "verdict": "resolved | title_mismatch | not_found | unreachable"}
```

规则：
- `not_found` 的引用**直接从综述删除**，不改写、不替换成"相似的真论文"；
- `title_mismatch` 降级为 `unverified`，正文里不得再承载任何具体数字；
- 数字核验单独一轮，只对进入论文 related work 的 ≤15 条做，人工读原文；
- receipt 文件与综述一起提交，SHA-256 写进综述头部。

**在这份 receipt 出来之前，综述不得被任何对外材料（论文、周报、简历、给学弟的资料）引用其具体数字。**

---

## 6. 我们真实的资产盘点

规划必须从这里开始，而不是从领域地图开始。

| 资产 | 状态 | 最硬的数字 | 出处 |
|---|---|---|---|
| **GDPVal 客观契约确认** | ✅ 真实数据上的 confirmed | 220 题 / 18 findings / **7 confirmed** / 0 unknown / 7.15s / 零 LLM | `reports/gdpval_objective_full220_20260716/` |
| Workspace 结构不变式 | ✅ 受控召回满分 | Full 388: 1940/1940 精确召回，0 额外告警；未修改数据 confirmed=0 | `RESULTS.md` |
| Workspace 语义证书 | ✅ 但是同语法一致性 | 200 对 certificate-aware 1.000；**生成器与判决器共享 4 条原子语法**，非泛化 | `RESULTS.md` |
| DS-1000 执行差分 | ⚠️ 被 W2 卡住 | 60 题 411 probes → 2 条真 evaluator 缺陷；注入检出 100/100/65% | `reports/ds1000_execution_audit.md` |
| APPS stdin/stdout 迁移 | ⚠️ 同上 | 差分合同跨协议复用；19 次对抗全部降级为 review | `research/apps-...` 分支 |
| MCQ/数学候选检测 | ✅ 但在退化 | MMLU-1000 F1 0.663→0.657 稳定；**SVAMP 0.914→0.750→0.707 未解释** | `RESULTS.md`、`reports/deepseek_v4_flash_rerun_20260801/` |
| 排名影响 | ✅ 但效应弱 | τ=0.981，per-subject 随机对照后 p≈0.32 不显著 | `reports/ranking_impact/` |
| 缺陷注入机器 | ✅ 但 DS-1000 专用 | 3 个算子，在 `scripts/` 不在 `benchcore/` | `scripts/run_ds1000_defect_injection.py` |
| external evidence gate | ⏸ 冻结 | 5×`NOT_IDENTIFIABLE`，零已验证外部证据 | `feature/external-evidence-...` 分支（**未推送**） |
| 修复闭环 | ❌ 不存在 | — | — |

**两条必须立刻处理的卫生问题**：

1. GDPVal 那次运行的 git commit 记录是 `6e189b8 **dirty**`——工作树脏，严格说不可精确重放。**7 条 confirmed 是我们最强的结果，必须在干净树上重跑一次并重新出 receipt。** 这是十几分钟的事，但不做的话论文里最强的一张表站不住。
2. `experiments/*.manifest.json` 与 `datasets/` 被 gitignore，冻结 manifest 不在版本控制里。同样必须修。

---

## 7. 规划：四个支柱 + 明确的止损

### 7.1 论文主张（可守住的版本）

> **确认合同（confirmation contract），而不是检测器，才是 benchmark 审计中可迁移的单位。**
> 我们给出：(a) 同一套带证据绑定与主动弃权的确认合同跨 ≥3 种异构执行协议复用；(b) 用 evaluator 缺陷注入首次为"确认"层建立**召回分母**；(c) 全部确认路径在对抗控制下逃逸率为 0；(d) 至少一条 confirmed → 最小修复 → 同一证明变 clean → 零回归 → 模型分数变化的完整闭环。
> 同时我们报告一个负面但重要的发现：**自动审计器自身是不稳定的测量仪器**。

四个支柱对应四段实验，缺哪段就削哪段主张，不用别的东西补。

### 7.2 P0：可信裁决器（关键路径，一切的前提）

**问题**：执行 harness 与数值裁决共用解释器，harness 可 monkeypatch 比较器 → 三个执行证明族全部禁用。

**要做**：把裁决拆到独立信任域。`promotion.py` 已经在等 `adjudicator_trust_domain == "separate_process_v1"`，接口是现成的。

最小设计（供 GPT 实施，需先冻协议）：
1. 裁决进程与 harness 进程分离，裁决进程**不导入任何 benchmark 数据或 harness 代码**；
2. harness 只输出序列化的观测（typed values + 哈希），不输出判断；
3. 裁决进程独立签署 transcript，父进程只钉住公钥、不持有私钥（沿用我们已有的 attestation 模式）；
4. 从 `DISABLED_UNATTESTED_PROOFS` 移除三个族，改为由签名有效性 fail-closed。

**验收（预注册）**：
- 对抗集：harness 内 monkeypatch 比较器 / 伪造 trust-domain 字符串 / 重放他 item 的 transcript / 篡改签名 —— 逃逸必须为 0；
- DS-1000 id=11 与 id=300 从 `review` 升到 `confirmed`，且 id=308（已知方法级 FP）**仍不得** confirmed；
- 全量测试从 fresh clone 通过。

**止损**：若在预算内无法做到裁决进程完全不接触 harness 代码，记 `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR` 并**公开写进论文的限制章节**，主张从"机器确认"降级为"带完整对抗审计的 review 层"。不许用放宽门槛的方式过关。

**预算**：人工活跃 ≤3 天。API 成本 0（纯本地执行）。

### 7.3 P1：确认层的召回分母（便宜、独有、直接补空白 A）

1. 把三个注入算子从 `scripts/run_ds1000_defect_injection.py` 提升进 `benchcore`，做成协议无关；
2. 在 DS-1000（函数调用）、APPS（stdin/stdout）、+ 一个新协议上各跑一遍；
3. 产出 **协议 × 缺陷类的 confirmation recall 矩阵**，每格附合法对照集上的 confirmed FP（必须为 0）。

**验收**：合法对照 FP=0 **且** 每个协议至少两类缺陷召回 ≥0.9。达不到就如实报告并给机制解释（像 `implementation_assert` 的 65% 那样——**可解释的低召回比修饰过的高召回有价值**）。

**依赖**：P0。**预算**：人工 ≤4 天，API ≤¥100（探针生成）。

### 7.4 P2：仪器稳定性（可与 P0/P1 并行，几乎零成本）

两件事：

**(a) 收口 SVAMP 0.914→0.707 回归的定位。** 分支已开。用 git bisect 在 `promotion.py` / `report.py` 之间定位，每个候选 commit 用**同一份缓存**重跑（不打新 API）。产出一句能写进论文的因果解释。

**(b) 出一张仪器稳定性表**，全部离线用现有缓存算：

| 扰动轴 | 指标 | 现有素材 |
|---|---|---|
| 同版本同输入重跑 | finding 集合 Jaccard | 各 `*_cache.jsonl` |
| temperature 0 重复采样 | verdict 翻转率 | B2 codegen 已测 40% |
| 底层模型更换 | finding 重叠 / F1 漂移 | V3 vs V4 Flash 双份报告 |
| 自身代码版本 | F1 漂移 | SVAMP 三点 + MMLU 三点 |

**这张表本身就是一个发现**：同一系统在 SVAMP 漂 0.21 而在 MMLU 漂 0.006，说明不稳定性是**数据集依赖**的，不是全局噪声。文献里没人报这个。

**预算**：人工 ≤2 天，API ≈0。

### 7.5 P3：修复闭环（目标已按 W7 切换）

目标：**DS-1000 id=300（`assert_allclose` 形状盲）**，退路 id=11。

链条：
```
confirmed（依赖 P0）
  → 最小 patch：比较器补 shape 断言，不动任何其他行为
  → 同一 proof 重放变 clean
  → 该题的等价探针仍全部通过（不引入过严）
  → 全 taxonomy 回归无新 finding
  → 用 DS-1000 公开模型输出重新评分
  → 报告 pass 率变化 + bootstrap 置信区间
```

**这是唯一能给我们真实 E5 后果证据的路径**（因为它非同步地翻转特定输出，不像删题那样同步缩小分母）。

**止损**：若重新评分后分数变化落在 bootstrap 区间内，如实报告"修复正确但后果不显著"，**不换 benchmark 去凑一个好看的数字**——我们在 MMLU 排名影响上已经因为诚实处理了随机对照而变强，这里同理。

**预算**：人工 ≤5 天。

### 7.6 明确不做的事（全部有理由）

| 不做 | 理由 |
|---|---|
| external evidence V3 / Phase 2B | 5×NOT_IDENTIFIABLE，零产出；V2 协议是对的，坏的是这台机器的出口。冻结现状，论文里当基础设施写一节 |
| APPS 输入域证书 V2 / 综述 G3 | 非目标预飞 2.49%，已按预注册纪律关闭 |
| A / A′ / A″ 词表、阈值、组合的任何再调 | 已关闭；A″ 在 P1 口径下相对旧 A 是 recall 净损失 |
| 综述 G9（多 judge 误差依赖）、G11（动态 benchmark 版本可比）、G12（构念效度↔item proof） | 都需要大模型池 + 人工标签；G11 还被综述自己引的"Can We Trust IRT"打脸 |
| 反事实 judge 审计并入主线 | 综述 §15.1 判断正确，target claim 不同 |
| 把适配成本当独立方向 | 降级为主线的一张成本表 |
| 用排名变化当主要 so-what | 我们自己的随机对照已证伪（p≈0.32） |

### 7.7 顺序与门

```
P0 可信裁决器  ──┬─→ P1 召回分母 ──→ P3 修复闭环 ──→ 后果重评分
                 └─→ （P0 失败则三者全部降级为 review 层主张）
P2 仪器稳定性 ────────────────（独立，随时可做，最便宜）
卫生：GDPVal 干净树重跑 + manifest 纳入版本控制（今天就能做完）
```

**门 1**（P0 后）：执行证明族解禁且对抗逃逸=0 → 继续。否则改写主张，跳到 P2+P3-lite。
**门 2**（P1 后）：≥2 协议 × ≥2 缺陷类召回达标且对照 FP=0 → 继续。否则只报单协议结果。
**门 3**（P3 后）：修复后同一 proof clean 且零回归 → 完整主张。否则只报确认层。

---

## 8. 最可能的失败模式（按概率排序）

1. **P0 做不出真正的信任域分离**（概率中等）。裁决进程要判断"输出是否等价"，就需要知道任务语义，而语义又来自 benchmark 数据。这里可能存在一个本质的循环。**提前想好的答案**：裁决进程只接收**序列化的类型化值 + 契约 ID**，契约本身来自受信 manifest（复用 external evidence 的 manifest 信任根——这样那条线的投入至少回收了一部分）。若这条也不成立，就是真 `NOT_IDENTIFIABLE`。
2. **SVAMP 回归定位不到单一 commit**（概率中等）。若是多个改动的交互，就如实写"多因，不可归约"——**这本身就是空白 B 的最强证据**。
3. **修复后后果不显著**（概率中等）。已在 7.5 写好处理方式。
4. **引用 receipt 打掉大量 2026 年文献**（概率不低）。综述的领域框架不依赖具体哪篇，删掉后骨架仍在；但"2026 趋势"那一节可能要大幅缩水。
5. **又一次把流程当产品**（概率高，历史已发生）。这是所有失败模式里最贵的。§7 每一项的预算上限就是防它的。

---

## 9. 立刻可执行的下一步（给 GPT 的任务，按顺序）

1. **今天**：GDPVal 干净树重跑 + 出 receipt；把 `experiments/*.manifest.json` 纳入版本控制。（~30 分钟，解锁我们最强的一张表）
2. **今天**：`execution_receipt.json` 补上 `reason_code`（当前 `"reason": "verifier replay 1 failed: \n"` 是空的，真实原因只存在于不可采信的 diagnostic addendum 里）。然后 external evidence 这条线**收口不再动**。
3. **本周**：冻结 trusted adjudicator 协议（四提交纪律：协议 → 实现+测试 → 运行 → 结果），再实现。
4. **本周并行**：SVAMP 回归 bisect（纯缓存，零 API）+ 仪器稳定性表。
5. **有外网的机器上**：引用 receipt 审计脚本，出 `citation_receipts.jsonl`。
6. **P0 通过后**：P1 注入算子上移 + 三协议召回矩阵。

---

## 10. 给这份复核本身的边界声明

- 我没有外网，**没有核实综述的任何一条引用是否真实存在**（除此前已独立核实的 2 条）。§5 给出的是核实方案，不是核实结果。
- 本文引用的所有我方数字都来自仓库已提交产物，路径已逐条给出，可离线重放核对。
- §7 的预算数字是我的估计，不是测量值。
- "GDPVal 7 条 confirmed"是从 `audit.json` 现场重算的，与 `audit.md` 表头一致；但该次运行的工作树是 dirty，严格意义上尚不可精确重放——这正是 §9 第 1 项的原因。
