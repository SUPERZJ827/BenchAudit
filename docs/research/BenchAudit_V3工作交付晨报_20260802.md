# BenchAudit V3 工作交付晨报

> 日期：2026-08-02  
> 分支：`chore/hygiene-and-adjudicator-protocol-20260802`  
> V3 起点：`53c512f`  
> 本报告撰写前 HEAD：`f3e3bd177b046758446de613e3ff9aae51d88c6c`  
> 模型 API：0  
> 外网：0  
> main 推送：未执行

## 1. 逐任务结局

| 任务 | 结局 | 交付 |
|---|---|---|
| R1：密钥托管与签名语义 | `PROTOCOL_FROZEN_PENDING_INDEPENDENT_REVIEW` | V3 已修订；未实现、未激活 |
| R2：equal-commit warrant 澄清 | `PROTOCOL_FROZEN_PENDING_INDEPENDENT_REVIEW` | 已明确真正 warrant 来自 BenchAudit cutoff-binding 历史 |
| R3：独立 item 正例 | `SECOND_FROZEN_ITEM_AVAILABLE` | 从 V3 前冻结明细加入 `apps/4352 × numeric_constant:0`；未重跑 APPS |
| R4：缓存键版本化 | `PASS` | schema `v1`、新行带版本、旧行归为 `v0`、run metadata 带版本与指纹 |

## 2. V3 协议

### 2.1 冻结产物

- 文件：`docs/TRUSTED_ADJUDICATOR_PROTOCOL_V3_20260802.md`
- 提交：`388d2e3`
- SHA-256：`70ea07afeae0ec34673441eba882c5a2e0b94fa31ef2d825317eeacb51048e92`
- 状态：`frozen before implementation; pending independent review`

父协议未修改：

| 协议 | SHA-256 |
|---|---|
| V1 | `9cbe5b1badf62540bd113b8822a1a584d8bcd3d9995a602fb14c7b7ad020cb0f` |
| V2 | `57092a96c6b47d0ff23a9be4dad3f7829aade5a39e7f5f8e002deae4a570cd7e` |

### 2.2 R1：密钥托管范围

V3 冻结的密钥隔离对象为：

```text
harness / candidate / container / benchmark-controlled code
```

parent 与 report 进程显式进入 TCB，不再声称同 UID 下无法访问 supervisor 密钥。TCB 变更必须使既有 attestation 失效或重新签发。

签名语义被限定为：

- BenchAudit 内部完整性边界；
- 区分 supervisor 捕获结果与 harness 自述；
- 绑定 observation、execution、contract、runtime 与 session；
- 不构成第三方证明；
- 第三方信任来自钉住环境中的确定性重放，而不是持有 BenchAudit 私钥。

### 2.3 R2：equal-commit 的真实 warrant

APPS 冻结正例中：

```text
harness_revision_commit = benchmark_cutoff_commit
                         = 21e74ddf8de1a21436da12e3e653065c5213e9d1
```

该 benchmark-side ancestry 对 equal commit 恒真，只验证 canonical remote 中的 revision/content identity，不独立证明非自适应性。

非自适应 warrant 来自 BenchAudit 仓库：

```text
cutoff_binding_receipt = docs/experiments/apps_stdin_input_receipt_20260729.json
cutoff_binding_benchaudit_commit = d3a5233aaefd81cf1bcf89b22f572021f2698384
```

未来 verifier 必须证明该 commit 是 V3 与实现协议提交的祖先。由此支撑的精确命题是：APPS revision 与目标身份在本 adjudicator 适配及其目标结果检查前已被冻结；不是“harness 早于全部 BenchAudit 工作”。

### 2.4 R3：第二个独立 item

只读来源：

- 分支：`research/apps-official-survivor-confirmation-20260729`
- 文件：`docs/experiments/apps_stdin_differential_confirmation_detail.json`
- SHA-256：`646f6774a5a25d118c99a5f3f82b9dea64704a29689dfa31ab62f4ae03f4080b`
- 冻结记录：30 tasks；7 个 weak-pass/strong-fail candidates；4 个 affected tasks。

追加正例：

| Item | Candidate | Candidate source SHA-256 | Transcript SHA-256 | 冻结关系 |
|---|---|---|---|---|
| `apps/4352` | `numeric_constant:0` | `9151bcf04668e8c58c73a1cd410b38f09543a1dd987e4bf5ad2b65c889d5670c` | `ca591e3be47431f080f57eb4c8cf7ed078d7877f2d99840c9bd7fafb2d73d8ae` | canonical weak+strong pass；candidate weak pass、strong `output_mismatch` |

现在冻结正例覆盖两个 item：`apps/1402` 与 `apps/4352`。

边界：第二 item 是在 V2 复核后从结果已知的冻结明细中选择的，只用于避免实现正路径完全依赖 item 1402；它不是盲 holdout、无偏 yield 或跨 item 泛化证明。没有运行新 APPS，也没有在实现结果后换正例。

## 3. R4：LLM 缓存键 schema version

### 3.1 实现

- 文件：`benchcore/llm_client.py`
- 提交：`f3e3bd1`
- SHA-256：`3ee01eefb0ac4339a2663c32cf0c3234a39b409d427c4a104d81de4087d755da`
- `CACHE_KEY_SCHEMA_VERSION`：`v1`
- schema field-manifest fingerprint：`c5c875661725c62292b13598e8172456ccdc9f0db6d6d92bc4b61ee48ee31006`

`v1` 被写进 chat/vote cache-key 的哈希 payload。两类 payload 另有 `cache_key_kind`，vote payload 继续绑定 `vote_index`。

### 3.2 cache 文件行为

新写入行：

```json
{
  "cache_key_schema_version": "v1",
  "key": "<sha256>",
  "response": {}
}
```

旧行处理：

- 缺少 `cache_key_schema_version` 时机械归为 `v0`；
- `v0` 行保留为可审计历史记录；
- `v0` 不能满足 `v1` exact replay；
- cache-only 模式遇到 v0/current mismatch 时 fail-closed，不发起网络请求；
- 未修改任何历史 cache 文件。

### 3.3 schema 变更门

代码冻结 chat/vote 两类 field manifest，并为 `v1` 注册 manifest fingerprint。

- payload 字段与 manifest 不一致：失败；
- manifest 组成变化但 `CACHE_KEY_SCHEMA_VERSION` 未递增：失败；
- 未注册的新 schema version：失败。

测试通过注入一个未版本化的新 component，验证 key 生成以 `cache-key composition changed without incrementing CACHE_KEY_SCHEMA_VERSION` 拒绝。

### 3.4 运行元数据

`LLMClient.run_stats()` 现在输出：

- `cache_key_schema_version`；
- `cache_key_schema_fingerprint`；
- `cache_entries_by_schema_version`。

`collect_run_metadata()` 原样把这些字段写入 `run_metadata.llm`；新增测试直接断言了该路径。

## 4. 测试

| 范围 | 结果 |
|---|---:|
| R4 + report/coverage 定向 | 33 passed |
| 当前 worktree 全量 | 783 passed |
| 全新目录 clone，detached `f3e3bd1` 全量 | 783 passed |

全新 clone 测试不依赖未提交文件。

## 5. 提交序

```text
388d2e3 docs: freeze trusted adjudicator protocol v3
f3e3bd1 feat: version LLM cache key schema
```

协议提交与实现提交分离。

## 6. 待决

1. V3 需要独立复核；通过前不得实现或激活 trusted adjudicator；
2. `apps/4352` 是已知冻结结果中的工程正例，不替代新的独立 holdout；
3. 历史 v0 cache 不可按 v1 exact replay；没有追溯改写或购买 API 重建；
4. SVAMP 跨 2026-07-16 的缓存重放仍不可执行；本任务只保证今后的 schema 变化可发现；
5. SVAMP bisect 与 17 个 FP 的复核继续由独立复核者完成。

## 7. 明确未做

- 未实现 trusted supervisor、signer、provenance verifier 或 manifest registry；
- 未修改 `benchcore/promotion.py`；
- 未修改 `benchcore/evaluator_execution.py`；
- 未移除或放宽任何 `DISABLED_UNATTESTED_PROOFS`；
- 未运行 APPS；
- 未重开 APPS input-contract V2；
- 未启动 external evidence V3 / Phase 2B；
- 未调整 A / A′ / A″；
- 未执行 SVAMP bisect；
- 未调用 API 或访问外网；
- 未修改历史 cache、历史 report 或既有 manifest；
- 未 push main。

## 8. 纪律自查

- [x] V1、V2 文件与哈希未变；
- [x] V3 作为独立父协议修订提交；
- [x] R3 只读 V3 前已存在的 APPS 明细，没有新执行；
- [x] 第二正例的事后选择边界已披露；
- [x] R4 与协议分开提交；
- [x] 旧 cache 缺字段机械归为 v0，未原地补写；
- [x] `promotion.py` / `evaluator_execution.py` 相对 V3 起点零改动；
- [x] `reports/**` 与 `experiments/**` 相对 V3 起点零改动；
- [x] `git ls-files datasets/` 为 0；
- [x] 全新 clone 全量测试通过；
- [x] 用户原工作树中的未提交改动未被修改。
