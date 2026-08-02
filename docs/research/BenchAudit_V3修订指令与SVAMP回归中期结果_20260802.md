# BenchAudit V3 修订指令 + SVAMP 回归中期结果

> 日期：2026-08-02
> 上游：`BenchAudit_夜间交付复核与V2工作指令_20260802.md`
> 复核对象：分支 `chore/hygiene-and-adjudicator-protocol-20260802`，HEAD `53c512f`
> 执行方式：零 API、零外网，全部依据已提交产物
> 本文包含三部分：V3 协议修订指令（供 GPT）、SVAMP 回归中期结果（Claude 执行）、对我自己早前结论的更正

---

# 第一部分：V2 交付复核结论

## 0. 裁决：通过

我独立核验的项：

| 核验项 | 方法 | 结果 |
|---|---|---|
| 任务 I 的 freeze→fetch 顺序 | `git log` 逐提交比对 | `9231580` 冻结（`observation_status: not_attempted_at_freeze`）→ `6f58d33` 绑定 → 发现第二份依赖后 `8ff05f8` 再冻结 → `af685b9` 再绑定。**两次都是先冻后取** ✅ |
| V1 协议未被改动 | `git log` + `sha256sum` | 仅 `4193ee2` 一个提交；实测 `9cbe5b1b…` 与 V2 §1.1 记录一致 ✅ |
| H 的 stable 白名单 | 读 `report.py` diff + 实际 `source_identity` | 只排除 `declared_input_path` / `audited_snapshot_path`；`input_sha256`、`audited_row_manifest_sha256` 全部保留；**用白名单不是黑名单**，未来新增易变字段不会漏进 ✅ |
| J 的渲染 | 读 `COVERAGE_VISIBILITY_REPLAY.md` | 输出了显式 **Coverage warning** 行，并把字段改名为 `Operationally affected items (finding records)` ✅ |
| 定向测试 | 我自己跑 `test_report_stability` + `test_audit_coverage` | 15 passed ✅ |

**未独立复核**：780 全量测试与 fresh clone 测试，我采信了交付方的报告，没有自己重跑。

有一处比指令要求更严，应当指出：artifact manifest 主动写了 `target_outcome_known_at_freeze: true` 与 "does not claim blindness or pre-outcome selection"。这是这次恢复的真实弱点，我没要求披露，主动披露是对的。

---

# 第二部分：V3 修订指令（供 GPT）

## 1. 定位

V2 协议（`docs/TRUSTED_ADJUDICATOR_PROTOCOL_V2_20260802.md`）**结构上是对的，可以作为实现基础**。V3 不推翻它，只做三处修订。

**V1 与 V2 均不修改、不重写。** V3 单独成文，在 §1 记录 V1 SHA-256 `9cbe5b1b…` 与 V2 的 SHA-256 作为不可变父协议。

---

## 2. R1（必须在实现前修）：§D.3 的密钥托管范围写错了

### 2.1 问题

V2 §D.3 要求私钥对以下各方均不可得：

> parent, harness, candidate, container, and report code

**对 parent 的隔离在本项目的执行环境里不可实现。** parent 与 supervisor 在同一台主机、同一 UID 下运行，parent 可以 ptrace supervisor 进程或直接读它的密钥文件。按字面实现，只有两种结局：做不出来，或者做出一个自己给自己签名的空壳。

### 2.2 而且它不必要

签名要防的**真实威胁**是 §1.2 列的第一条：harness monkeypatch 比较器。也就是要区分"这份观测来自 supervisor"还是"来自 harness"。

- 对 **harness / candidate / container** 的密钥隔离是可达的（不同进程；容器内读不到宿主文件系统；无共享内存）；
- 对 **parent** 的隔离既不可达，也不针对任何已列出的威胁。

### 2.3 更要紧的是：签名到底买到了什么

必须在协议里写清楚，否则会被误当成第三方证明：

> **我们持有签名密钥，因此签名对第三方不构成证明。** 它是我们系统内部的完整性边界，用于把 supervisor 的观测与 harness 的自述区分开。第三方的信任来自**确定性重放**——第三方在钉住的镜像里跑同样的 harness、同样的 probe，自己观察到同样的字节——而不是来自我们的签名。

这一点和整个项目的 `confirmed` 定义是一致的（fresh clone 可重放），不是新的让步。

### 2.4 要求

1. §D.3 的密钥不可得清单改为 **harness / candidate / container / benchmark-controlled code**；
2. 显式把 **parent 与 report 进程写进 TCB**，并说明理由；
3. 加一小节 `signature semantics`，写明上面 2.3 那段话：签名是内部完整性边界，不是第三方 attestation；
4. §G.1 `PASS` 条件里凡是依赖"parent 无法访问密钥"的，全部改为依赖"harness/container 无法访问密钥"；
5. 冻结测试里对应的那条（V2 §F.2 中关于 key 可达性的）相应改写。

---

## 3. R2（澄清，必改）：§E.3 的 equal-commit 让祖先检查不做任何工作

### 3.1 问题

V2 §E.3 冻的是：

```text
harness_revision_commit    = 21e74ddf8de1a21436da12e3e653065c5213e9d1
benchmark_cutoff_commit    = 21e74ddf8de1a21436da12e3e653065c5213e9d1
cutoff relation            = equal
```

一个 commit 永远是自己的祖先。**所以 APPS 侧的 Git 祖先关系在这个正例上恒真，不承担任何论证。**

真正承担"非自适应"论证的是 §C.2 里的另一条：

> `cutoff_binding_benchaudit_commit`, which must be an ancestor of the V2 protocol commit in the BenchAudit repository

也就是**我们自己仓库的提交顺序**——cutoff 是在 07-29（`d3a5233`）钉的，早于 V2 协议，所以我们无法事后挑一个有利的 revision。

### 3.2 为什么必须改

这条守卫本身很好（防事后挑选，我没要求，是你加的）。问题是**warrant 归属写反了**：协议读起来像是 APPS 侧的祖先关系在证明非自适应，实际上证明它的是 BenchAudit 侧的提交顺序。

不澄清的话，复核者和审稿人会以为祖先检查证明了它没证明的东西。这与我在 external-evidence V1 里指出过的"把分支覆盖当成语义正确性"是同一类错误。

### 3.3 要求

在 §C 或 §E.3 新增一小节，明确写：

1. 对 equal-commit 正例，Git 祖先检查是**恒真**的，它验证的是 revision 与内容确实来自钉住的 canonical remote，**不是**非自适应性；
2. 非自适应性的 warrant 来自 `cutoff_binding_benchaudit_commit` 早于本协议提交这一事实，属于 **BenchAudit 仓库的历史**，不是 benchmark 仓库的历史；
3. 因此该 warrant 覆盖的命题精确地是"harness 不可能针对本适配机制及其目标结果而被撰写或修订"，**不是**"harness 早于 BenchAudit 全部工作"；
4. 若将来正例改为严格祖先（`harness_revision` ≠ `cutoff`），祖先检查才开始承担实质论证，届时需要重新表述。

---

## 4. R3（建议）：正例全部压在一个 item 上

V2 §E.2 冻的三个候选（`arithmetic_operator:0` / `boolean_operator:0` / `condition_negation:0`）**全在 `apps/1402`**。

一个 item 的特异性——例如它的输出恰好对空白或数值格式敏感——就能同时带走三个候选，正例集合会一起失效。

### 要求

1. 检查冻结时已有的 `apps_stdin_differential_confirmation_detail.json` 里，**是否还有其他 item 具备同方向的 weak-pass / strong-fail 关系**；
2. 若有：再冻一个**独立 item** 作为第二正例，并在 §E.2 说明它是从冻结时已存在的记录中选的，不是 V2 之后产生的；
3. 若没有：在 §E.4 显式写明 `positive_witness_concentrated_on_single_item: true` 作为已知限制，并说明这对 `PASS` 的解释力意味着什么；
4. **不许**为了凑第二个正例去跑新的 APPS。

---

## 5. R4（新增，来自第三部分的发现）：缓存键变更必须留下可发现的记录

见第三部分 §8。发现是：`ac99446`（2026-07-16）往 `_cache_key` 里加了 `thinking` 字段，**使 07-16 之前的全部 LLM 缓存不可达**，而这件事在任何报告、任何 CHANGELOG 里都没有记录，是我这次逐字节比对缓存键才发现的。

后果：任何跨 07-16 的"同缓存重放"实验在方法上都不成立，而我们已经在规划里写过这样的实验。

### 要求（这一项是实现，不是协议）

1. 在 `benchcore/llm_client.py` 里给缓存键加一个**显式版本号** `CACHE_KEY_SCHEMA_VERSION`，并把它写进被哈希的 payload；
2. 缓存文件每行增加 `cache_key_schema_version` 字段（旧行没有该字段即视为 `v0`）；
3. 运行报告的 `run_metadata.llm` 增加 `cache_key_schema_version`；
4. 加一条测试：改变键组成而不递增版本号，测试失败；
5. **不要回改任何历史缓存文件**；只在新写入的行上带版本号。

这是十几行的改动，但它是唯一能让"同缓存重放"这类实验在方法上站得住的前提。

---

## 6. 禁止清单（与前两轮一致）

1. 实现可信裁决器（V3 复核通过前）；
2. 修改 `promotion.py`，尤其不得移除 `DISABLED_UNATTESTED_PROOFS` 任何条目；
3. 修改 `evaluator_execution.py` 的判决逻辑；
4. external evidence V3 / Phase 2B / 出口策略放宽；
5. 重开 APPS input-contract V2（输入域证书）——**注意与 stdout 观测通道不是一回事**；
6. 调 A / A′ / A″；
7. 做 SVAMP bisect（Claude 负责）；
8. 花费 API 额度；
9. push main；
10. 把失败结果重新归类；
11. 修改任何历史报告产物或历史缓存文件；
12. 先取数据后补 manifest。

## 7. 顺序与交付

```
R1、R2（协议修订，V3 单独成文）  ← 最高优先
R3（正例扩展，取决于冻结数据里有没有）
R4（缓存键版本号，实现 + 测试）  ← 可并行，与协议无关
```

提交纪律：协议提交与实现提交分离；沿用晨报格式交付。

---

# 第三部分：SVAMP 回归中期结果（Claude 执行）

## 8. 已经确定的事实

全部用已提交产物离线重算，零 API。

### 8.1 精确复现了两次运行

我用同一份真值（`svamp_platinum_all.jsonl` 的 `metadata.audit_label`，38 条缺陷）和同一套口径（排除 `presentation` scope）重算：

| 运行 | 提交产物 | 预测项 | TP | FP | FN | P | R | **F1** |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-07-07 recheck | `reports/svamp_recheck_20260707_report.json` | 42 | 36 | 6 | 2 | 0.857 | 0.947 | **0.900** |
| 2026-07-30 mainline | `reports/svamp_mainline0730_report.json` | 50 | 33 | 17 | 5 | 0.660 | 0.868 | **0.750** |

0730 的 33/17/5 与该次运行自带的 comparison JSON 完全一致，重算口径正确。

### 8.2 FP 增长集中在 LLM auditor，不在静态检查器

| 检出方法 | 0707 FP | 0730 FP | 变化 |
|---|---:|---:|---|
| `llm_quantity_consistency` | 4 | 9 | **+5** |
| `llm_question_clarity` | 2 | 7 | **+5** |
| `llm_quantity_consistency_nonmaterial` | 1 | 5 | **+4** |
| `llm_gold_audit` | 0 | 3 | **+3** |
| `llm_event_state` | 2 | 2 | 0 |
| `llm_event_state_nonmaterial` | 4 | 0 | **−4** |

**没有任何一个静态检查器贡献 FP。** 两次运行的 method 集合几乎相同（0730 多了 `choice_encoding_contract`，是 MCQ 检查器，在 SVAMP 上不产出）。

在 0730 的 17 个 FP item 中，只被单一方法命中的有 10 个：`llm_question_clarity` 3、`llm_quantity_consistency` 3、`llm_quantity_consistency_nonmaterial` 2、`llm_event_state` 2。也就是说**抑制 `*_nonmaterial` 单独触发可以直接消掉 2 个 FP item**——这与我在学弟指南里提的第一条改进方向一致，现在有了具体数字。

### 8.3 决定性的方法学发现：跨 07-16 的"同缓存重放"不可能

我原计划用"同一份缓存 + 不同代码版本"来做 bisect，把模型因素排除掉。这个方法**在 07-16 这条线上不成立**：

```
commit ac99446  (2026-07-16)  Add adaptive benchmark auditing and objective evidence replay
  → benchcore/llm_client.py 的 _cache_key() 增加了 "thinking": self.config.thinking
```

缓存键是整个 payload 的 SHA-256，新增字段使**07-16 之前写入的每一条缓存都不可达**。实测：

```
0707 缓存 648 条 | 0730 缓存 661 条 | 键交集 = 0
```

这个 0 交集**不能**用来推断模型或 prompt 变了——它被键组成变更完全解释。任何基于"老缓存重放"的跨 07-16 bisect 都无法执行。

### 8.4 0730 → 0801 之间确实有内容变化，但成因未定

这两次运行的配置**完全相同**：`deepseek-v4-flash`、temperature 0.0、`configured_votes: 1`、`thinking: disabled`、`max_tokens: 5000`、19 个 method 完全一致。键组成也相同（都在 07-16 之后）。

然而：

```
0730 缓存 661 条 | 0801 缓存 664 条 | 键交集 = 400  → 约 40% 的 prompt 不同
```

模型和配置都在键里且相同，所以差异只能来自 `system` 或 `user` 文本。两种可能，我**无法**从已提交产物中区分：

- (a) prompt 模板在 07-30 到 08-01 之间被改过；
- (b) 系统有答案依赖的级联（`response_triage` / `investigator` 一类），上游一个答案不同就会让下游一批 prompt 全部不同。

要区分需要（a）比对两个日期的 `llm_auditor.py` prompt 字符串，或（b）在代码里给 prompt 模板加哈希并记进 run_metadata——这正是 R4 要解决的同一类问题。

## 9. 尚未回答的问题

**为什么 SVAMP 掉 0.15 F1 而 MMLU 几乎不动（0.663 → 0.657）？** 还没有答案。已排除：静态检查器、method 集合变化。未排除：模型版本、prompt 变化、级联行为、`promotion.py` 引入后的分级变化。

下一步（我继续做，仍然零 API）：

1. 在 07-16 之后的提交里做真正的 bisect（这一段缓存键组成一致，可以复用 0730 缓存）；
2. 直接 diff 0730 与 0801 之间 `llm_auditor.py` 的 prompt 字符串，判定 §8.4 的 (a) 还是 (b)；
3. 把 17 个 FP 逐条读一遍，判断是"系统变差"还是"Platinum 漏标"——0707 时代的 6 个 FP 里有 4 个被判定为"真问题但 Platinum 没标"，这个比例如果保持，实际精度损失会小得多。

---

# 第四部分：对我自己早前结论的更正

## 10. 更正一：`BenchAudit_研究定位复核与可执行规划_20260801.md` §W8

我在那份文档里写了：

> **在没有任何 prompt 字符串改动的情况下**，我们自己的审计器在 SVAMP 上掉了 0.21 F1，假阳翻了近 3 倍。

**"没有任何 prompt 字符串改动"这一句我无法支持，应当撤回。** 我当时依据的是"`llm_auditor.py` prompt strings unchanged"这个更早的说法，没有独立验证。现在的证据是：0730 与 0801 在模型与配置完全相同的前提下仍有 40% 的 prompt 键不同（§8.4）。成因未定，但"无 prompt 改动"这个前提已经站不住。

正确的表述应改为：

> 同一份 100 题、同一套真值，我们自己的审计器在 2026-07-07 与 2026-07-30 两次运行间 F1 从 0.900 降到 0.750，FP 从 6 升到 17，全部增量来自 LLM auditor 而非静态检查器；成因尚未定位，且因缓存键在 07-16 变更，跨该日期的同缓存对照不可执行。

## 11. 更正二：基线数字

我在规划文档里用的 SVAMP 基线是 `RESULTS.md` 里的 **0.914（v5）**。但 v5 那次运行的完整报告 JSON 我没有找到；**可离线精确重算的最早产物是 0707 recheck 的 0.900**。

后续所有对比一律以 **0.900（0707）→ 0.750（0730）→ 0.707（0801）** 为准，不再引用 0.914，除非 v5 的原始报告能被定位并重算。

## 12. 这两条更正对规划的影响

**不影响"审计器是不稳定测量仪器"这个论点**——0.900 → 0.750 的落差、以及全部来自 LLM 层的事实，本身就是证据，而且现在是逐方法可归因的。

**影响的是这条线的做法**：原计划"纯缓存 bisect"只能在 07-16 之后的区间执行；07-16 之前那一段要么重新打 API（需要授权和预算），要么只能作为"不可复原的历史"如实记录。我倾向后者——**"我们自己的实验在四个月内变得不可复原"本身就是最该报告的发现**，而不是花钱把它买回来。
