# BenchAudit V2 工作交付晨报

> 日期：2026-08-02  
> 分支：`chore/hygiene-and-adjudicator-protocol-20260802`  
> 起点：`ef2a4d0`  
> 本报告撰写前 HEAD：`6b8ac8cc9630194e45ade7a6f021dbf8d99fe195`  
> 模型 API：0  
> 主线推送：未执行

## 1. 逐任务结局

| 任务 | 结局 | 交付 |
|---|---|---|
| G：可信裁决器 V2 协议 | `PROTOCOL_FROZEN_PENDING_INDEPENDENT_REVIEW` | 已完成；仅协议，无实现、无测试、无激活 |
| H：报告 stable/raw 二分 | `PASS` | 已实现并测试；真实 GDPVal 双跑 stable hash 相同 |
| I：GDPVal artifact 恢复 | `RECOVERED_WITH_UNKNOWN_AT_FREEZE_ARTIFACTS` | 已按 manifest-before-fetch 顺序完成；对外结论仍为 5 confirmed + 2 coverage unknown |
| J：覆盖可见性 | `PASS` | Markdown 摘要能直接显示 1 个检查因 operational failure 未完成 |

## 2. 任务 G：可信裁决器 V2 协议

### 2.1 冻结状态

- 文档：`docs/TRUSTED_ADJUDICATOR_PROTOCOL_V2_20260802.md`
- 提交：`c628e02`
- SHA-256：`57092a96c6b47d0ff23a9be4dad3f7829aade5a39e7f5f8e002deae4a570cd7e`
- 状态：`frozen before implementation; pending independent review`

V1 未修改：

- 文档：`docs/TRUSTED_ADJUDICATOR_PROTOCOL_V1_20260802.md`
- SHA-256：`9cbe5b1badf62540bd113b8822a1a584d8bcd3d9995a602fb14c7b7ad020cb0f`

### 2.2 结论范围

| 观测形态 | 协议结论 |
|---|---|
| in-memory 语言级对象 | 沿用并收窄为 `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR_IN_MEMORY` |
| OS-visible stdout/stderr/exit status | V2 单独评估，不受 V1 的 in-memory 结论覆盖 |
| OS-visible 文件产物 | V2 单独评估；要求密封输出边界与路径安全 |

V2 冻结的威胁模型为 `non_adaptive_pre_cutoff`。祖先关系不可验证时，确认上限为 `review`。

### 2.3 关键安全约束

- trusted supervisor 持有内核 pipe 的父端并捕获原始字节；不使用 UTF-8 replacement 作为证明输入；
- 子进程执行组包含后代进程；无法判定同一 fd 写入来源时弃权；
- 截断、超时后部分输出、解析失败、边界不完整均不得确认；
- 容器 runtime 属于 TCB，必须钉住 engine、version、image digest 与策略；
- 文件产物要求 sealed output boundary，并检查 symlink、hardlink、路径逃逸与运行后变更；
- 调用方自填 adversary model 不被信任，必须从 canonical remote Git ancestry 重新推导；
- 本协议不授权实现，不激活任何 disabled proof tuple。

### 2.4 冻结正例材料

协议只引用预先存在的 APPS 产物，未运行 APPS：

- dataset revision：`21e74ddf8de1a21436da12e3e653065c5213e9d1`
- dataset SHA-256：`5b003a1530968015cff1d1458169890a9328051913aa3cd178583466a04e760c`
- input receipt SHA-256：`9d4096bbc01b772a7a7db4be059b32a4a43d67dd81b240bfce93f8a0a3d028e6`
- pair JSONL SHA-256：`7b2190b7348923d82c0659a97c8cf73800e0afc99f2b1cfcda19e5b69e0a5420`
- detail JSON SHA-256：`646f67ec8321435941912442561cb4f2dc8d5cb4fb38c81a46e39567404d080b`
- stable summary SHA-256：`3a85290bd6488976233ee3a6fd9c51abf3a6135f5730afc23279dccaf8e3c734`

## 3. 任务 H：报告 stable/raw 二分

### 3.1 实现

- 代码：`benchcore/report.py`
- SHA-256：`acee6fb9c9b97033aaabb2dff719edda484a1f76d012496b51f42d8b45533825`
- schema：`benchcore-audit-report-v2`
- stable payload schema：`benchcore-audit-stable-payload-v1`
- 提交：`5c0a575`、`2598232`

stable payload 包含语义输入身份、summary、field mapping、methods、violations、coverage ledger、benchmark package 与 audit plan。`elapsed_seconds`、本地路径及其他运行元数据不进入 stable hash。

### 3.2 真实 GDPVal 双跑

| 字段 | run 1 | run 2 |
|---|---|---|
| items | 220 | 220 |
| violations | 18 | 18 |
| confirmed | 7 | 7 |
| review | 11 | 11 |
| coverage unknown | 0 | 0 |
| operational failed | 0 | 0 |
| raw audit SHA-256 | `66df8e414adfc766e18f60728536f14b05561bb36005b67c5a3dbaffbfa4641c` | `858b1b6e230f137831ae4c5290631d9ecaed753febc28ad33acfde1b7cec8962` |
| stable payload SHA-256 | `1ef7d44c197ba73de8a0bcfb4844ee33356ce74dc89575c1f906bf47fe268815` | `1ef7d44c197ba73de8a0bcfb4844ee33356ce74dc89575c1f906bf47fe268815` |

两次 violation payload 与 coverage ledger 逐项相等。raw hash 的差异来自运行元数据，stable hash 相同。

## 4. 任务 I：GDPVal artifact 恢复

### 4.1 manifest-before-fetch 提交序

| 阶段 | 提交 | manifest SHA-256 | 是否在取对应文件前冻结 |
|---|---|---|---|
| 任何恢复前 | `9231580` | `c364ca15d935c2bbf8bfcf2577d00767cae4d885e5bbee2523890a49c0808fbe` | 是 |
| reference observed | `6f58d33` | `2016d99ba5dfa1f17f6267fbdfe581a4193cdbf27448782100568c123c386c53` | 对 reference：是 |
| masked deliverable 发现后、取文件前 | `8ff05f8` | `ab513e40c2b24c4e167f74c1c7ea10354585bf8172ede80a8b2863f3b29b2397` | 对 deliverable：是 |
| 两份 observed artifact 绑定后 | `af685b9` | `286053be53f0dd7ca6033b0bd1a6c0e4900ac05bb51402b13c475f727ab752dd` | 是 |

最终 manifest：`experiments/gdpval_full220.artifact_manifest.json`。

### 4.2 恢复材料

| 角色 | 相对路径 | expected hash at freeze | observed SHA-256 | bytes |
|---|---|---|---|---:|
| reference | `reference_files/cc781e4dc0985c8eb327a53ec03b5900/Population v2.xlsx` | `null`；`unknown_at_freeze=true` | `e64a9d3ba60bbaecef0e6685a57b618e9b321bcd813c79e4460be36bf8c79fb7` | 61,470 |
| deliverable | `deliverable_files/2837faa0a7a6a95f40dfbe45bf66c7fb/Sample v2.xlsx` | `null`；`unknown_at_freeze=true` | `72b74484e2eeb6bd1a5b5391220a6dea142f3b7fbd6c218490b1aa633dbafcbb` | 79,328 |

两份文件均来自 dataset revision `11e7900cdcac61bc4daf59e65feb238acda98fbf` 的精确路径。没有外部独立 digest，因此 authenticity 状态保持 `unverified_without_external_digest`。

第二份 deliverable 依赖只在恢复 reference 后才暴露；在获取该 deliverable 前，先以 `unknown_at_freeze=true` 追加冻结 manifest。

### 4.3 结果与声明边界

恢复后 checker 观察：

- 220 items；
- 18 violations；
- 7 confirmed；
- 11 review；
- 0 coverage unknown；
- 0 operational failed。

confirmed 构成：

- `task_artifact_contract_mismatch`: 4；
- `rubric_artifact_contract_mismatch`: 2；
- `rubric_reference_contract_mismatch`: 1。

**对外可报告结论保持：`GDPVal 220: 5 confirmed + 2 coverage unknown`。**

恢复后的 7 仅作为受限 recovery observation：新增恢复的两条记录依赖冻结时 expected SHA-256 未知的 artifact，且第二份依赖是在第一次恢复后才暴露。历史 dirty 结果没有被重新确认为可独立复现的 7。

### 4.4 新产物

- receipt：`reports/gdpval_objective_full220_20260802_recovered/recovery_receipt.json`
  - SHA-256：`15d38e6eef50a42179a53e13bd484f39b9fe7787b78857da6c0a354aef83c6ea`
- result：`reports/gdpval_objective_full220_20260802_recovered/RECOVERY_RESULT.md`
  - SHA-256：`6a990ab8480e73df7c3f58f98e0aaecfc9957aa56e31b81bd3df972d1dc63c6e`

## 5. 任务 J：覆盖可见性

### 5.1 展示调整

Markdown 摘要现在并列显示：

- `Unknown-tier findings`；
- `Operationally affected items (finding records)`；
- `Coverage-unknown item×checker checks`；
- `Item×checker checks incomplete due operational failure`。

operational failure 非零时增加明确警告：coverage unknown 不是 clean result，也不是 unknown-tier finding。

### 5.2 GDPVal 5+2 可见性重放

新产物：`reports/gdpval_objective_full220_20260802_recovered/COVERAGE_VISIBILITY_REPLAY.md`

- SHA-256：`a9a595bb8160b3a1749bd6c4368742ead727f5706175b5d1e999b1e9599cecb2`
- Unknown-tier findings：0；
- Operationally affected items (finding records)：0；
- Coverage-unknown item×checker checks：1；
- Item×checker checks incomplete due operational failure：1。

提交：`6b8ac8c`。

## 6. 测试

| 范围 | 结果 |
|---|---:|
| H/J 定向测试 | 15 passed |
| 当前 worktree 全量 | 780 passed |
| 全新目录 clone，detached `6b8ac8c` 全量 | 780 passed |

全新 clone 测试不依赖未提交文件。

## 7. 提交序

```text
c628e02 docs: freeze OS-visible adjudicator protocol v2
5c0a575 feat: add stable semantic hashes to audit reports
9231580 exp: freeze GDPVal artifact recovery manifest
6f58d33 exp: bind recovered GDPVal workbook bytes
2598232 fix: exclude local source paths from stable report hash
8ff05f8 exp: freeze masked GDPVal deliverable dependency
af685b9 exp: bind recovered GDPVal deliverable bytes
e9bd133 exp: record bounded GDPVal artifact recovery
6b8ac8c fix: distinguish finding tiers from coverage gaps
```

## 8. 待决

1. V2 协议需要独立复核；复核前不实现、不激活；
2. GDPVal 两份恢复 artifact 缺少冻结时的 expected hash 与外部独立 digest；对外继续使用 5 confirmed + 2 coverage unknown；
3. SVAMP bisect 由独立复核者执行，本分支未触碰；
4. V2 实现、APPS stdout 实跑均未启动。

## 9. 明确未做

- 未调用任何模型 API；
- 未修改 `benchcore/promotion.py`；
- 未修改 `benchcore/evaluator_execution.py`；
- 未移除或放宽任何 `DISABLED_UNATTESTED_PROOFS`；
- 未重开 APPS input-contract V2；
- 未启动 external evidence V3 / Phase 2B；
- 未调整 A / A′ / A″；
- 未做 SVAMP bisect；
- 未 push main；
- 未把恢复观察重新包装为无保留的 7 confirmed。

## 10. 纪律自查

- [x] V1 不变，V2 协议单独提交；
- [x] 协议提交与实现分离；
- [x] `promotion.py` / `evaluator_execution.py` 相对 `ef2a4d0` 零改动；
- [x] `git ls-files datasets/` 为 0；
- [x] 未修改任何已提交的历史报告产物；只新增 `reports/gdpval_objective_full220_20260802_recovered/`；
- [x] GDPVal reference 在 `9231580` manifest 提交后获取；
- [x] 后暴露的 deliverable 在 `8ff05f8` manifest 提交后获取；
- [x] expected hash 未知时保留 `null` 与 `unknown_at_freeze=true`；
- [x] 两次最终 GDPVal 重跑发生在干净提交 `af685b919342818d6a10817bb978014b83d0b26d`；
- [x] stable hash 相同，raw hash 差异如实保留；
- [x] 全新 clone 全量测试通过；
- [x] 未修改用户原工作树中的既有未提交改动。
