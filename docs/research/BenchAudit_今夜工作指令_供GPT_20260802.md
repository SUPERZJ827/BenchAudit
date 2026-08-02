# BenchAudit 今夜工作指令（供 GPT 执行）

> 日期：2026-08-02
> 上游依据：`docs/research/BenchAudit_研究定位复核与可执行规划_20260801.md`（Claude 独立复核 + 规划）
> 执行模式：**无人值守**。因此本指令只包含"不需要中途做架构判断"的任务。
> 天亮后由 Claude 复核，复核通过才进入实现阶段。

---

## 0. 今夜的定位

规划把关键路径定在 **P0：可信裁决器**（`promotion.py:587` 的 `DISABLED_UNATTESTED_PROOFS` 关闭了全部三个执行证明族，导致执行类 benchmark 的 confirmed 通道物理关闭）。

但按项目纪律，协议必须先冻结、先独立复核，才能实现：

```
1. protocol/gate 提交   ← 今夜只做到这一步
2. scanner/tests 提交   ← 复核通过后才做
3. 运行
4. receipt/results 提交
```

所以**今夜的目标不是让裁决器跑起来，而是让明天可以安全地开始写它**。今夜的产物全部是：可复核的文档、确定性的重跑 receipt、机械核实的结果。

一句话：**今夜不写任何 P0 生产代码。**

---

## 1. 绝对禁止（先读这一节，任何一条触发就停）

以下任何一项都不得在今夜发生，即使你认为它显然有益：

1. **实现 P0 可信裁决器**（协议未经复核）；
2. 修改 `benchcore/promotion.py`（尤其不得从 `DISABLED_UNATTESTED_PROOFS` 中移除任何条目）；
3. 修改 `benchcore/evaluator_execution.py` 的判决逻辑；
4. 启动 external evidence **V3 协议**、**Phase 2B**，或任何形式的 host 出口策略放宽；
5. 重开 **APPS input-contract V2**（V1 非目标预飞 2.49%，已按预注册纪律关闭）；
6. 调整 **A / A′ / A″** 的词表、阈值或组合（已关闭）；
7. 做 **SVAMP F1 回归的 bisect** —— 这一项由 Claude 独立执行，理由是"改动作者不应 bisect 自己引入的回归"；
8. 任何**花费 API 额度**的调用（本指令全部任务都不需要打模型）；
9. `push` 到 `main`，或修改 `main` 上的任何文件；
10. 把一次失败结果**重新归类**为其他结局（`NOT_IDENTIFIABLE` 不许改写成 `PASS`，diagnostic 不许升格为 admissible evidence）。

**遇到任何需要做架构判断的岔路：停下，把岔路写进晨报的"待决"一节，不要自己选。** 项目在 external evidence 那条线上已经因为"没人叫停"连续消耗了 5 轮零产出，不要重演。

---

## 2. 任务 A（最高优先，先做）：GDPVal 干净树重跑

### 背景

`reports/gdpval_objective_full220_20260716/audit.md` 是全项目最强的一条真实数据结果：

```
Items: 220   Violations: 18   Confirmed: 7   Review: 11   Unknown: 0
Methods: gdpval_objective, gdpval_workbook_replay, gdpval_dataset_objective, duplicate_conflict
Elapsed: 7.15s
Git commit: 6e189b821df3e76b9b477cefbc8c620621cfbe9c dirty
```

7 条 confirmed 的构成：`task_artifact_contract_mismatch` ×4、`rubric_artifact_contract_mismatch` ×2、`rubric_reference_contract_mismatch` ×1。零 LLM、零 item-level verifier、7 秒跑完。

**问题：`dirty`。** 工作树是脏的，这次运行严格意义上不可精确重放。我们最强的一张表目前站不住。

### 要做的事

1. 从**干净工作树**（`git status` 必须为空）的一个明确 commit 重跑同一次审计；
2. 输入必须是同一份数据。报告目录里有 `source-f8422fab9b21d90c0ee5f0659842ab666d418cb8940842918f9f4b0df7ae0202.parquet`——用它，并在 receipt 里记录该文件的 SHA-256（文件名里的哈希要**独立重算验证**，不要直接信文件名）；
3. 输出写到**新目录** `reports/gdpval_objective_full220_20260802_clean/`，**不要覆盖 07-16 的历史产物**；
4. 连跑两次，验证确定性。

### 必须产出的 receipt

`reports/gdpval_objective_full220_20260802_clean/rerun_receipt.json`：

```json
{
  "receipt_schema": "benchaudit-gdpval-clean-rerun-v1",
  "git_commit": "<40-hex>",
  "git_worktree_clean": true,
  "input_path": "...",
  "input_sha256": "<独立重算>",
  "input_sha256_matches_filename": true,
  "python_version": "...",
  "run_1": {"items": 220, "violations": N, "confirmed": N, "review": N, "unknown": N,
            "audit_json_sha256": "..."},
  "run_2": {"...同上..."},
  "deterministic": true,
  "confirmed_breakdown": {"task_artifact_contract_mismatch": N, "...": N},
  "matches_20260716_report": true
}
```

### 验收

- `git_worktree_clean = true`；
- 两次运行的 `audit.json` SHA-256 **完全一致**（若不一致，先定位不确定性来源，写进晨报，**不要**只报其中一次）；
- confirmed 数与类型分布与 07-16 一致。

### 停止条件

如果重跑结果与 07-16 **不一致**（confirmed 数变了、类型分布变了、或两次自身不一致）：

**这是重要发现，不是失败。** 立刻停止本任务，把差异写成 `DISCREPANCY.md` 放在同目录，记录两边的完整计数与差异项，然后继续做任务 B。**不要**去调代码让它对上 07-16 的数字。

### 预算

≤1 小时。零 API。

---

## 3. 任务 B：把冻结 manifest 纳入版本控制

`experiments/*.manifest.json` 和 `datasets/` 当前在 `.gitignore` 里。后果是**定义实验范围的冻结 manifest 不在版本控制中**，任何"冻结的 100 条"都无法被第三方核对。

要做的事：

1. 列出当前所有被忽略的 `experiments/*.manifest.json`（`git status --ignored` 或 `git check-ignore -v`）；
2. 调整 `.gitignore`，使 **manifest 文件本身进入版本控制**，同时**继续排除数据集字节**（`datasets/` 下的原始数据不得提交——这是既有硬约束）；
3. 提交这些 manifest，commit message 里说明每份 manifest 对应哪个实验；
4. 如果某份 manifest 里内嵌了数据集内容（而不只是 ID/哈希/路径），**不要提交它**，在晨报里单独列出。

### 验收

- `git ls-files experiments/ | grep manifest` 非空；
- `git ls-files datasets/` 仍为空（或仍只含 README 一类的说明文件）；
- 仓库体积增量 < 1 MB。

### 预算

≤30 分钟。

---

## 4. 任务 C：execution receipt 补 reason_code，然后这条线收口

`docs/experiments/apps_external_evidence_git_verifier_v2_20260801/execution_receipt.json` 当前是：

```json
{
  "decision": "NOT_IDENTIFIABLE_PRODUCTION_VERIFIER",
  "reason": "verifier replay 1 failed: \n",
  "receipt_schema": "benchaudit-external-evidence-git-verifier-v2-runs"
}
```

`reason` 是空的。真实原因 `pinned_allowlist_proxy_cannot_reach_environment_egress` 只存在于 `diagnostic_addendum.json` 里——而那份文件按协议是**不可采信的诊断材料**。也就是说：唯一可采信的 receipt 没有记录失败原因。

### 要做的事

1. 在 `execution_receipt.json` 中补 `reason_code` 字段（值用规范化的 `pinned_allowlist_proxy_cannot_reach_environment_egress`），并让 `reason` 携带非空的可读文本；
2. **决策本身不变**，仍是 `NOT_IDENTIFIABLE_PRODUCTION_VERIFIER`；
3. 这是对 receipt 的**追加修订**，必须在新提交里做，并说明"只补充失败原因的可采信记录，不改变结局、不改变协议、不引入新证据"；
4. 如果协议规定 receipt 一经产出即不可修改，则**不要改原文件**，改为新增一份 `execution_receipt_reason_addendum.json`，内含原 receipt 的 SHA-256 + reason_code，并在晨报里说明走了哪条路径。

### 然后：这条线今夜之后不再动

补完 reason_code，external evidence 线**冻结**：

- 不冻 V3；
- 不做 Phase 2B；
- 不再尝试任何回放；
- 论文里它的定位是"基础设施章节"，不是主张。

真实回放需要一台有直连出口的机器，这是环境问题不是研究问题。**不要用协议工作去解决管道问题。**

### 附带

`feature/external-evidence-provenance-gate-20260731` 分支本地领先 10+ 提交，push 因凭据过期被阻。今夜**不要**尝试重新认证或换 remote。在晨报里记一行"待用户处理凭据"即可。

### 预算

≤30 分钟。

---

## 5. 任务 D（今夜的主要智力产出）：冻结 P0 可信裁决器协议

**只写协议。不写实现。不写测试。不跑任何东西。**

### 要解决的问题

`benchcore/evaluator_execution.py:29` 承认当前实际状态是 `adjudicator_trust_domain = "shared_untrusted_driver"`——harness 代码与数值裁决共用一个解释器，harness 可以 monkeypatch 比较器。

而 `benchcore/promotion.py:317 / :339 / :365` 三个谓词已经写好了接受条件，包括：

```python
and evidence.get("adjudicator_trust_domain") == "separate_process_v1"
```

**注意这个洞**：这个值是**调用方自己填进 evidence 的字符串**。代码看起来在强制一个信任域，实际上任何能构造 evidence 的路径都能自称 `separate_process_v1`。`DISABLED_UNATTESTED_PROOFS`（`promotion.py:587`）的注释已经准确指出了这一点：

> a caller-controlled trust-domain string and well-shaped hashes are not proof.

所以协议必须回答的是：**怎样让"裁决发生在独立信任域"这件事，成为一个 promotion 层能独立验证的事实，而不是一个自称。**

### 协议文档必须包含的章节

写到 `docs/TRUSTED_ADJUDICATOR_PROTOCOL_V1_20260802.md`，状态标注 **frozen before implementation**。

**§0 问题陈述** —— 一句话，说明当前 confirmed 通道为何关闭。

**§1 威胁模型。** 至少必须显式列出并给出拒绝方式：

- harness 代码 monkeypatch 比较器 / 覆盖 `numpy.allclose` 一类的判定函数；
- harness 代码直接构造并返回一份"看起来合格"的裁决 transcript；
- **调用方自填 `adjudicator_trust_domain = "separate_process_v1"`（当前真实存在的洞）**；
- 跨 item 重放他人的裁决 transcript；
- 裁决进程被喂入被篡改的观测；
- 裁决进程本身崩溃/超时，被当作语义结论；
- 探针生成用的 LLM 输出被当作判断而不是候选。

**§2 信任域切分。** 明确回答：

- 裁决进程**能看到什么**（建议：序列化的类型化值 + 契约 ID + 契约参数）；
- 裁决进程**绝对看不到什么**（建议：benchmark 原始数据、harness 代码、reference solution 源码、probe 源码）；
- 观测如何从 harness 进程传到裁决进程，序列化格式是什么，如何防止在传输格式里夹带可执行内容。

**§3 —— 必须正面回答的核心难题：循环依赖。**

裁决"两个输出是否等价"需要任务语义；而任务语义来自 benchmark 数据；但裁决进程又不允许看 benchmark 数据。**这可能是一个本质循环。**

协议必须选择并论证一条路径：

- (a) 契约来自**受信 manifest**（复用 external evidence 已有的 manifest 信任根：code-owned allowlist + payload SHA-256），裁决进程只按契约 ID 取一个**预先注册的比较语义**（如"精确类型相等"、"含 shape 的数值近似"、"行集无序相等"），不做任何 ad-hoc 语义推断；
- (b) 其他方案，需给出等价强度的论证。

**如果论证下来两条都不成立，协议的正确结局是写 `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR` 并说明理由——不要为了让 P0 看起来可行而放宽定义。** 一个诚实的负结果比一个自称的信任域有价值得多。

**§4 attestation。** 裁决 transcript 如何被独立验证。要求：签名由裁决侧产生，父进程只钉住公钥、不持有私钥（沿用项目已有的 attestation 模式）。明确说明密钥从哪来、谁生成、谁不能访问。

**§5 promotion 侧的验证条件。** 精确写出 `promotion.py` 将来要检查什么。**`adjudicator_trust_domain` 字符串本身不得再作为任何充分条件的一部分**——它最多是一个标签，真正的条件必须是签名验证 + transcript 绑定。

**§6 冻结的测试清单。** 只列，不实现。§1 每条威胁至少对应一条 fail-closed 测试。另加：

- DS-1000 **id=11**（时区盲）与 **id=300**（`assert_allclose` 广播盲）必须能升到 `confirmed`；
- DS-1000 **id=308** 是已知的方法级假阳（property-based 比较器忽略 `ans`，任务本身允许多种输出）——**必须仍然不得 confirmed**。这条是防止"为了解锁而放宽"的关键对照。

**§7 go / no-go。** 明确 `PASS` / `FAIL` / `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR` 三种结局各自的充分条件。对抗逃逸 > 0 一律 `FAIL`。

**§8 非激活边界。** 本协议只覆盖裁决器本身。不得顺带激活任何 CLI、report、producer 路径。

**§9 正例可满足性冻结。** 按 V2 协议 §9 已确立的通用规则：在实现前记录本协议的正例（id=11 / id=300 升到 confirmed）所需要的确切对象标识与关系，并说明为什么它在实现前就已知可满足。

### 明确不做

- 不写任何 `benchcore/` 代码；
- 不写测试；
- 不改 `promotion.py`；
- 不跑 DS-1000。

### 提交

协议单独一个提交（`protocol/gate` 提交），message 里写明"frozen before implementation, pending independent review"。

### 预算

≤3 小时。零 API。

---

## 6. 任务 E（需要外网；没有外网就跳过并记录）：综述引用 receipt 审计

对象：`docs/research/BenchAudit_自动化Benchmark审计领域系统调研_20260731.md`，约 80 条引用。

当前状态：其中只有 2 条被独立核实过（Fantastic Bugs arXiv 2511.16842 的 "Precision@50 最高 84%"、PAIChecker arXiv 2607.28587 的定位）。**其余全部是未核实的 LLM 断言**，按项目证据策略只能是 `review` 级。风险最高的是 2026 年的精确 ID（`aclanthology.org/2026.acl-long.1162/`、`2026.acl-long.719/`、`2026.findings-eacl.89/`、`openreview.net/pdf?id=...` 这类形态）。

### 关键的执行顺序要求

**脚本必须在看到任何一条核实结果之前写完并提交。** 先提交脚本，再跑，再提交 receipt。否则"根据结果调整核实标准"就无法排除。

### 每条引用产出一行

`docs/research/citation_receipts_20260802.jsonl`：

```json
{"cite_key": "...", "url": "...", "http_status": 200,
 "resolved_title": "...", "claimed_title": "...", "title_match": true,
 "claimed_venue": "ACL 2026", "observed_venue": "...",
 "numbers_claimed_in_survey": ["84% Precision@50"],
 "numbers_verified": null,
 "verdict": "resolved | title_mismatch | not_found | unreachable"}
```

### 处置规则（不许变通）

- `not_found` → **该引用及其承载的所有数字从综述中删除**。**不许**替换成"一篇相似的真论文"，不许改写成模糊表述；
- `title_mismatch` → 降级为 `unverified`，正文中不得再承载任何具体数字；
- `unreachable`（网络原因）→ 保持 `unverified`，**不算通过**，在晨报里单列；
- `numbers_verified` 今夜一律填 `null`。数字核验是单独一轮、只对进入论文 related work 的 ≤15 条做、必须人工读原文——**今夜不做**。

### 综述的修改方式

今夜**不要直接删改综述正文**。改为产出一份 `docs/research/citation_audit_findings_20260802.md`，列出：

- 各 verdict 的计数；
- 全部 `not_found` 的清单，以及它们在综述里承载了哪些结论/数字；
- 如果删掉它们，综述哪些章节会受影响。

正文改动等复核后再做。

### 没有外网时

不要尝试代理、不要换 host、不要用缓存页面。写一行到晨报：`任务 E: 跳过，无外网出口`，然后结束。

### 预算

≤2 小时。零 API（HTTP 抓取不算模型调用）。

---

## 7. 任务 F（有余力才做）：P1 注入算子上移的设计说明

**只写设计说明，不写代码。**

现状：evaluator 缺陷注入的三个算子在 `scripts/run_ds1000_defect_injection.py`，是 DS-1000 专用的：

| 算子 | 语义 | DS-1000 检出率 |
|---|---|---:|
| `neutralize_comparator` | exec_test 在比较前直接返回 1 | 20/20 |
| `reject_gold` | harness 断言取反 | 20/20 |
| `implementation_assert` | 断言一个 gold 特有的实现 token | 13/20 |

目标（规划里的空白 A）：把它们提升为 `benchcore` 里协议无关的组件，在 ≥3 个执行协议上跑出 **协议 × 缺陷类的 confirmation recall 矩阵**——这是文献里没有的"确认层分母"。

写到 `docs/research/P1_injection_operator_generalization_notes_20260802.md`，回答：

1. 三个算子中哪些真的协议无关，哪些依赖 DS-1000 的 harness 形态？逐个说明；
2. 要变成协议无关，`benchcore` 需要什么抽象？（尽量复用已有的 `execution.py` / `evaluator_execution.py` 结构，**不要**为一个实现造接口）；
3. 每个协议上"合法对照集"如何构造，才能让 `confirmed FP = 0` 这个判据不是靠"什么都不 confirm"换来的？
4. `implementation_assert` 在 DS-1000 上 65% 的漏检有明确机制解释（被钉住的 token 恰是所有等价体都会用的自然写法）。这个机制在其他协议上是否同样存在？

**不要在这份说明里预测数字。**

### 预算

≤1 小时。

---

## 8. 提交纪律

- 每个任务独立提交，不要合并；
- 分支：新开 `chore/hygiene-and-adjudicator-protocol-20260802`，**不要动 main**；
- 协议文档的提交必须与任何实现分离（今夜本来也没有实现）；
- 不要 force push，不要 rebase 已有分支；
- commit message 用英文，说明做了什么和为什么。

---

## 9. 晨报格式（写到 `docs/research/晨报_20260802.md`）

请严格按这个结构，方便快速复核：

```markdown
## 逐任务结局
| 任务 | 结局 | 关键产物路径 | 用时 |
|---|---|---|---|
| A GDPVal 干净重跑 | done / discrepancy / blocked | | |
| B manifest 版本控制 | | | |
| C receipt reason_code | | | |
| D 裁决器协议冻结 | | | |
| E 引用 receipt | done / skipped_no_network | | |
| F P1 设计说明 | done / not_started | | |

## 数字（不要解读，只列）
- GDPVal 重跑：items / violations / confirmed / review / unknown，两次是否一致
- 引用核实：resolved / title_mismatch / not_found / unreachable 各几条

## 待决（我停下来没有自己选的岔路）
- ...

## 我没做的事，以及为什么
- ...

## 纪律自查
- [ ] 未实现 P0
- [ ] 未修改 promotion.py
- [ ] 未启动 external evidence V3 / Phase 2B
- [ ] 未重开 APPS V2
- [ ] 未调 A/A′/A″
- [ ] 未做 SVAMP bisect
- [ ] 零 API 调用
- [ ] 未 push main
- [ ] 未把任何失败结果重新归类
```

---

## 10. 最后一句

今夜真正重要的只有一件事：**让明天可以安全地开始写可信裁决器。**

任务 A/B/C 是清掉挡路的卫生问题，E/F 是不占关键路径的并行工作。**任务 D 的协议质量决定了后面三周走得动走不动**——如果时间不够，砍 E 和 F，把时间给 D。

如果 D 论证下来发现信任域切分在本项目的约束下做不到，**写 `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR` 并说清楚为什么**。这是一个完全可接受的结局，而且比一个自称的 `separate_process_v1` 有价值得多——后者正是我们今天要修的洞。
