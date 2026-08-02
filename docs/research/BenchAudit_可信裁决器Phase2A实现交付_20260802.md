# BenchAudit 可信裁决器 Phase 2A 实现交付

> 日期：2026-08-02
> 分支：`chore/hygiene-and-adjudicator-protocol-20260802`
> 实现提交：`2ada09de90cb6bdd08b8baeaef32225fd0f78a06`
> 裁决：`IMPLEMENTED_NOT_ACTIVATED`

## 1. 本轮完成内容

### 1.1 仪器可复现性补强

- cache-key 金键同时钉住普通请求与 vote 请求的实际序列化结果；
- 改变字段取值方式会令金键测试失败，必须人工判断是否递增 schema version；
- audit 与 investigate 的 `run_metadata.workers` 现在记录实际并发数；
- 提交：`62c0845`；
- 定向测试：42 passed。

### 1.2 Trusted adjudicator core

实现文件：`benchcore/trusted_adjudicator.py`  
SHA-256：`aa85091fde4601a1533cfbcf16c565b6a98d661ae9271224e8446341076118f4`

已实现：

- 原始 stdout/stderr 字节捕获，不经过 UTF-8 replacement；
- timeout、stdout overflow、stderr overflow、EOF 与 exit status 分开记录；
- leader 已退出但 descendant 仍持有 pipe 时，继续按 process group 处理并弃权；
- equal-commit 与 strict-ancestor 的 `non_adaptive_pre_cutoff` 纯策略推导；
- equal-commit 必须额外具备 BenchAudit cutoff-binding ancestry；
- caller 自填 adversary model 无权威；
- APPS comparator 固定在 code-owned registry，在 raw hash 之后本地执行；
- 内部 HMAC-SHA256 transcript integrity；
- item、candidate、oracle、contract、stdin、runtime、nonce、raw hash 与 provenance 全部进入稳定 payload；
- wrong key、cross-item、cross-session、nonce replay 与 transcript tampering 拒绝；
- 四个独立观测执行 MR-4 方向判断：canonical weak+strong pass、candidate weak pass、strong fail 才能生成 proof candidate。

该模块只返回 `confirmed_relative_coverage_gap_candidate`，不构造 `Violation`，不进入 promotion。

## 2. 测试结果

| 范围 | 结果 |
|---|---:|
| trusted adjudicator 新测试 | 21 passed |
| execution / attestation / evaluator execution 定向 | 72 passed |
| 当前 worktree 全量 | 805 passed |
| 全新 clone，detached `2ada09d` 全量 | 805 passed |

新增攻击覆盖：

- 非 UTF-8 stdout/stderr；
- timeout 后部分输出；
- 输出溢出；
- descendant 保持 stdout fd；
- equal-commit 缺 BenchAudit cutoff binding；
- distinct commit 双向 ancestry；
- caller 伪造 adversary model；
- wrong key 与 cross-item replay；
- runtime 不具备 confirmation eligibility；
- provenance unverifiable；
- unknown manifest 与 stdin hash mismatch；
- comparator 的 whitespace、numeric tolerance、token multiset、mismatch 与 non-UTF-8 abstention；
- MR-4 正方向、all-pass control、nonce replay 与 attestation tamper。

## 3. 非激活证明

当前状态：

```text
production_manifest_ids() = ()
CLI references             = 0
promotion references       = 0
evaluator_execution refs   = 0
```

本轮没有：

- 修改 `benchcore/promotion.py`；
- 修改 `benchcore/evaluator_execution.py`；
- 移除任何 `DISABLED_UNATTESTED_PROOFS`；
- 注册生产 manifest；
- 接线 CLI、checker、producer 或 report；
- 运行 APPS；
- 修改任何历史 finding、report 或 cache。

因此该实现无法改变现有实验结论，也无法自行产出 confirmed finding。

## 4. 证据产物

- Receipt：`docs/experiments/trusted_adjudicator_phase2a_20260802/implementation_receipt.json`
- Receipt SHA-256：`249672e6b4385dc8489ef5df5af008bf70dc8085ec92bde8a83cc80f352f8a1f`
- 测试文件 SHA-256：`ad160ed2247a576a4aa20e27a02a5e4e6b2108f1af78409478f58bfd7d7ce900`

## 5. 尚不能声称的内容

本轮不能声称 `PASS_TRUSTED_ADJUDICATOR_OS_VISIBLE`，原因是：

1. 生产 code-owned runtime/APPS manifest 仍为空；
2. 尚未通过该 core 运行 digest-pinned container；
3. 生产 canonical-remote Git provenance verifier 尚未接入；
4. `apps/1402` 与 `apps/4352` 尚未在 V2/V3 下重新执行；
5. 本轮只实现 stream capture，尚未实现 OS-visible file-artifact capture；
6. 尚未经过实现级独立红队复核。

## 6. 下一步 gate

独立复核应先攻击：

1. raw capture 是否存在丢字节、假 EOF 或 descendant escape；
2. HMAC binding 是否能跨 item/session/contract 重放；
3. comparator 是否在 raw hashing 前发生有损处理；
4. equal-commit 是否可能绕过 BenchAudit cutoff-binding；
5. code-owned registry 是否能被调用方扩展；
6. MR-4 是否存在 timeout/error 被当作 strong semantic fail 的路径。

复核通过后，才可另开提交实现并冻结 production Git verifier、digest-pinned container manifest 与 APPS 双正例运行；promotion 激活仍须再做一次独立复核。
