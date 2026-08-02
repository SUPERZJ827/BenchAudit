# BenchAudit Trusted Adjudicator V4 修订交付晨报

> 日期：2026-08-02
>
> 分支：`chore/hygiene-and-adjudicator-protocol-20260802`
>
> 裁决：`IMPLEMENTED_NOT_ACTIVATED`
>
> API：0
>
> 网络：0

## 1. 结论

Phase 2A 复核提出的 F1–F3 已按冻结顺序完成：先冻结 V4，再修改实现与测试，最后用 hash-bound addendum 补录历史 receipt 中遗漏的协议偏离。

本轮没有、也不得声称 `PASS_TRUSTED_ADJUDICATOR_OS_VISIBLE`。生产 Git verifier、digest-pinned container manifest、APPS 双正例和 promotion 激活均未执行。

## 2. 提交顺序

| 顺序 | 提交 | 内容 |
|---:|---|---|
| 1 | `75edb37f8ae8061631503b17465129c449972a09` | 冻结 V4 协议；只有协议文件 |
| 2 | `62a2b49dc91c960ef985ab5125db9f0055a5b5e0` | 实现 F1–F3 并补测试 |
| 3 | `cf119f898288880a25bb91f65ce611da02515beb` | 新增 hash-bound protocol-deviation addendum |

协议提交先于实现提交。V1、V2、V3 未被修改。

## 3. F1：对称 attestation 偏离已显式重冻

V4 只 supersede V1 §4.1 的 asymmetric/Ed25519 签名方案要求，其他父协议要求不变。选择保留 HMAC-SHA256，原因与损失均已写死：

- Python 标准库没有 Ed25519；本阶段不新增密码学依赖；
- V3 的第三方信任来自冻结输入与代码的确定性重放，而不是签名；
- 验证能力蕴含伪造能力；
- parent 无法在结构上排除于伪造能力之外，只能依赖 TCB 纪律；
- attestation 永远不能作为外部或第三方可验证证明。

实现新增并签名绑定：

```text
attestation_class = internal_integrity_symmetric
verification_implies_forgery_capability = true
```

两个字段任一被篡改，验证均失败。外部证明类别 code-owned registry 仍为空；当前 attestation 及伪造的 `third_party_verifiable` 标签都不能通过外部证明 eligibility。

V3 §5.2 的 generic-signing FAIL 仅被澄清为 harness、candidate、container 或 benchmark-controlled code 能让任意 bytes 被签名；parent 仍属于显式 TCB 限制，不被虚假描述为结构隔离。

## 4. F2：key ID 已做域分离

旧实现：

```text
key_id = SHA256(key)
```

V4 实现：

```text
key_id = SHA256(b"benchaudit-adjudicator-keyid-v1" + key)
```

测试同时断言 emitted key ID 与 bare key hash 不等，并与冻结域分离公式一致。该修正移除了 bare-key hash oracle，但不改变对称信任模型，也不把 key ID 宣称为不透明标识符。

## 5. F3：descendant retained pipe 已独立分类

稳定 raw observation 新增 `incomplete_reason`：

| 场景 | reason | 完整性 | confirmation eligibility |
|---|---|---:|---:|
| leader 尚未退出即到 deadline | `timeout` | false | false |
| leader 已退出、descendant 仍持有 stdout/stderr pipe | `descendant_retained_pipe` | false | false |
| stdout 超限 | `stdout_overflow` | false | false |
| stderr 超限 | `stderr_overflow` | false | false |
| 正常完成 | `null` | true | 仍由其余 gate 决定 |

更精确的 reason 只改善可诊断性，不改变 fail-closed 行为。该字段进入 transcript 稳定 payload，并由 attestation 完整性绑定。

## 6. Receipt 偏离补录

原 receipt 保持逐字节不变：

```text
docs/experiments/trusted_adjudicator_phase2a_20260802/implementation_receipt.json
SHA-256 249672e6b4385dc8489ef5df5af008bf70dc8085ec92bde8a83cc80f352f8a1f
```

新增 addendum：

```text
docs/experiments/trusted_adjudicator_phase2a_20260802/
  implementation_receipt_protocol_deviation_addendum.json
SHA-256 8cc10102aca6929b49fb918dbee2914f0b289a10a96dd0deb546ce3339e1b584
```

Addendum 的 4 个文件绑定全部独立校验通过：原 receipt、V4 协议、修订实现、修订测试。`protocol_deviations` 逐项包含协议与条款、原要求、实际选择、理由、精确损失和 V4 重新冻结状态。

`known_unimplemented_or_unverified_boundaries` 未被拿来冒充偏离声明，历史 receipt 的 decision、测试数与实验结果均未重写。

## 7. 哈希

| 文件 | SHA-256 |
|---|---|
| V1 protocol | `9cbe5b1badf62540bd113b8822a1a584d8bcd3d9995a602fb14c7b7ad020cb0f` |
| V2 protocol | `57092a96c6b47d0ff23a9be4dad3f7829aade5a39e7f5f8e002deae4a570cd7e` |
| V3 protocol | `70ea07afeae0ec34673441eba882c5a2e0b94fa31ef2d825317eeacb51048e92` |
| V4 protocol | `cae85f5a62155217129b6e4e25c4a7fe1e30fc473a8c6431d57dbf2f1a3fea74` |
| implementation | `c4e69b5ec5332cc7fced103120f4708716c2d0f97dbcf1390531f4ec55e9e230` |
| tests | `7c77cc7e03c2b1a985da088b947b9667c56a0570fb3416847dd6800dcd83a84d` |
| original receipt | `249672e6b4385dc8489ef5df5af008bf70dc8085ec92bde8a83cc80f352f8a1f` |
| deviation addendum | `8cc10102aca6929b49fb918dbee2914f0b289a10a96dd0deb546ce3339e1b584` |

## 8. 验证结果

| 范围 | 结果 |
|---|---:|
| V4 trusted-adjudicator 定向 | 23 passed |
| 当前 worktree 全量 | 807 passed |
| fresh clone，提交 `cf119f8` 全量 | 807 passed |
| addendum hash bindings | 4/4 |
| `production_manifest_ids()` | `()` |
| `benchcore/` 中模块外 trusted-adjudicator 引用 | 0 |
| 受保护文件变化 | 0 |

fresh-clone 首次包装命令因包含临时目录清理而被环境安全策略拒绝，测试未启动；去掉清理步骤后，在新目录克隆提交 `cf119f8` 并完成 807/807。该 operational 事件不计为测试失败，也未被隐藏。

## 9. 纪律自查

- [x] 未声称 PASS；
- [x] 所有已知冻结协议偏离均在 `protocol_deviations` 中声明；
- [x] V4 协议提交早于实现提交；
- [x] V1/V2/V3 未修改；
- [x] 原 receipt、历史报告与历史缓存未修改；
- [x] `benchcore/promotion.py` 未修改；
- [x] `benchcore/evaluator_execution.py` 未修改；
- [x] 未修改 `DISABLED_UNATTESTED_PROOFS`；
- [x] 未注册生产 manifest；
- [x] 未接入 CLI、checker、producer、report 或 promotion；
- [x] 未运行 APPS 双正例；
- [x] 未运行 SVAMP；
- [x] 未使用 API 或网络；
- [x] 未 push main。

## 10. 下一步边界

本轮到此停止。后续若继续，必须另行冻结并独立复核：

1. 生产 canonical-remote Git provenance verifier；
2. digest-pinned container manifest；
3. 两者通过后，才允许分别运行 `apps/1402` 与 `apps/4352` 的双正例；
4. promotion 激活仍是更后的独立 gate。

这些事项不属于 V4 修订交付，也不能用本轮 807 项测试替代。
