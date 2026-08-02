# Phase 2A 实现复核 + V4 修订指令

> 日期：2026-08-02
> 复核对象：分支 `chore/hygiene-and-adjudicator-protocol-20260802`，HEAD `fd6377d`
> 复核方式：零 API、零外网；独立读码、独立跑测试、独立核验非激活
> 复核者：Claude（独立红队，不写生产代码）
> 上游：`BenchAudit_夜间交付复核与V2工作指令_20260802.md` → `BenchAudit_V3修订指令与SVAMP回归中期结果_20260802.md`

---

# 第一部分：Phase 2A 复核结论

## 0. 裁决

**通过，可以继续开发。** 实现质量高、非激活状态属实、fail-closed 设计正确。

**但有一处冻结协议偏离未被披露（F1），在补上之前不得声称 `PASS_TRUSTED_ADJUDICATOR_OS_VISIBLE`。** 交付方已正确地没有声称。

## 1. 我独立核验的项

| 核验项 | 我用的方法 | 结果 |
|---|---|---|
| 非激活：模块外引用 | `grep -rn "trusted_adjudicator" benchcore/ --include=*.py`，排除模块自身 | **0 处** ✅ |
| 非激活：生产 manifest | 直接 import 并调用 `production_manifest_ids()` | 返回 `()` ✅ |
| `cli.py` 那 7 行是否为激活路径 | 逐行读 diff | 全部是 `workers` 元数据（我上轮建议项），带拒绝 `bool` 的 `isinstance` 守卫；无裁决器引用 ✅ |
| 裁决器测试 | 我自己跑 `pytest tests/test_trusted_adjudicator.py -q` | **21 passed** ✅ |
| descendant 持有 pipe | 读测试源码 + 读捕获主循环 | 测试真的 spawn 了持有 stdout 的子孙进程且 leader 先退出；结果 `timed_out=True` → `complete=False` → 无法确认 ✅ |
| 完整性判据 | 读 `RawProcessCapture.complete` | 严格合取（无 timeout / 无 overflow / 双 EOF / exit_code 非空），任一不满足即 `capture_incomplete` → 弃权 ✅ |
| MR-4 方向 | 读 `adjudicate_weak_strong_pair` | 见 §2 ✅ |
| V1/V2/V3 未被改动 | `sha256sum` 三份协议 | V1 `9cbe5b1b…`、V2 `57092a96…`、V3 `70ea07af…`，均与各自冻结时一致 ✅ |

**未独立复核**：805 全量测试与 fresh-clone 测试，采信交付方报告（我只跑了裁决器与缓存两个定向套件）。

## 2. 做得对的地方（值得保留的设计）

- `capture_raw_process` 用 `start_new_session=True` 建独立进程组，超时/溢出时整组 kill；非阻塞 selector 读取；stdout/stderr 各自独立字节上限与 overflow 标志；EOF 与 exit status 分开记录。
- `complete` 是**严格合取**而不是"尽力而为"，把 timeout / overflow / 缺 EOF / 缺 exit 全部推向弃权。
- MR-4 裁决顺序正确且层层 fail-closed：先验四份 attestation → 四个互异 session nonce（防重放）→ 单一 item → canonical 与 candidate 身份不得碰撞 → weak/strong oracle 绑定必须互异且跨 canonical/candidate 一致 → 单一比较契约。
- **canonical 控制未双过时返回 `no_finding` 而不是 `review`**——控制失败就不该产生任何主张，这个区分是对的。
- 终端命名克制：`confirmed_relative_coverage_gap_candidate`，docstring 明写 "returns a proof candidate, never a BenchAudit `Violation`"。

---

# 第二部分：V4 修订指令

## 3. F1（必须）：签名方案偏离冻结协议，且未披露

### 3.1 事实

冻结协议链的要求：

| 位置 | 原文 |
|---|---|
| V1 §4.1 | "Use an **asymmetric** signature scheme with a project-approved implementation, such as **Ed25519**." |
| V1 §4.1 | "Generate the **private key** outside the parent, harness, candidate, and report processes." |
| V2 §D.3 | "The supervisor/adjudicator **private key** is unavailable to …" |
| V3 §2.4 | "key identifier and signature-scheme version, but **never key material**" |

V3 §2.1 只 supersede 了 V2 D.3 中"密钥必须对 parent 与 report 不可得"这一句，**从未触及签名方案**。

实现：

```python
SIGNATURE_SCHEME = "hmac-sha256-internal-integrity-v1"
```

对称。而 `implementation_receipt.json` 的 `known_unimplemented_or_unverified_boundaries` 六条**全部是"尚未实现"类**，没有任何一条记录这处偏离；交付文档只把 HMAC 当作特性列出。

### 3.2 为什么这不是措辞问题

1. HMAC 下**验证密钥即签名密钥**（`verify_supervisor_attestation(..., verification_key=...)`）。**凡能验证者皆能伪造。**
2. V3 §5.2 把这一条明列为 FAIL：*"a generic parent-supplied byte string can be signed as if supervisor-captured"*。HMAC 下 parent 恰好能做到——不是靠攻击，是由构造决定。**当前实现与它自己的 go/no-go 条款相冲突。**
3. V3 §2.2 确实已把 parent 放进 TCB 并承认同 UID 下密钥可及。但两者性质不同：Ed25519 下**一个行为正确的 parent 在结构上无法伪造**，必须主动扒内存；HMAC 下"无法伪造"在任何实现里都不可达。
4. 它廉价地断掉一个未来选项：Ed25519 下外部复核者仅用公钥即可验证 transcript；HMAC 下必须交出验证密钥，性质彻底消失。

### 3.3 推荐路径

**推荐 (a)：保留 HMAC，修订协议并重新冻结。** 理由：Python 标准库无 Ed25519，替代方案是新依赖，CLAUDE.md §8 要求不轻易引入；而 V3 §2.3 已确立第三方信任来自确定性重放而非签名。**问题从来不是选了 HMAC，是静默偏离了冻结协议。**

路径 (b)（换 Ed25519）只在以下条件同时成立时才做：Phase 2B 明确需要外部方仅凭公钥验证，且愿意接受新依赖。今夜不要做。

### 3.4 V4 必须包含的内容

新建 `docs/TRUSTED_ADJUDICATOR_PROTOCOL_V4_20260802.md`，状态 `frozen`。V1/V2/V3 **一律不修改**，在 §1 记录三者 SHA-256 作为不可变父协议：

```
V1  9cbe5b1badf62540bd113b8822a1a584d8bcd3d9995a602fb14c7b7ad020cb0f
V2  57092a96c6b47d0ff23a9be4dad3f7829aade5a39e7f5f8e002deae4a570cd7e
V3  70ea07afeae0ec34673441eba882c5a2e0b94fa31ef2d825317eeacb51048e92
```

必须写清：

1. **偏离声明**：V1 §4.1 的 asymmetric/Ed25519 要求被 V4 supersede，仅限签名方案一项，其余不变；
2. **理由**：标准库无 Ed25519；新依赖违反项目依赖政策；第三方信任由 V3 §2.3 的确定性重放承担；
3. **精确损失**（不许模糊）：
   - 验证能力蕴含伪造能力；
   - 无法在结构上把 parent 排除在伪造能力之外，只能靠 TCB 纪律；
   - 该 attestation 在任何情况下都不可作为对外证明；
4. **修订 V3 §5.2 的 FAIL 措辞**，使"parent 可签任意字节"这一条明确限定为"**harness / candidate / container / benchmark-controlled code** 可签任意字节"，否则实现违反自己的 go/no-go；
5. **新增机器可读的自我限定字段**（这一条是新要求，不只是文字）：attestation 必须携带
   ```
   attestation_class = "internal_integrity_symmetric"
   verification_implies_forgery_capability = true
   ```
   并加测试断言任何消费方看到 `attestation_class != "third_party_verifiable"` 时不得把它当作对外证明。**让限制随数据走，而不是只写在文档里。**
6. **重新冻结**：V4 单独一个 `protocol` 提交，与任何实现改动分离。

### 3.5 顺带确立一条通用规则（写进 V4 末节）

这次的问题是可复用的教训，应当和 V2 §9 的"正例可满足性冻结规则"并列：

> **偏离声明规则**：任何实现若在冻结协议的某项要求上做出不同选择，必须在其 implementation receipt 中以专门字段 `protocol_deviations` 声明，每条包含：被偏离的协议与条款编号、实际选择、理由、**精确损失的性质**、以及"是否已通过新协议重新冻结"。
>
> `known_unimplemented_or_unverified_boundaries` 记录的是"还没做的事"，**不能用来承载"做了但和协议不一样的事"**——两者混在一起，偏离就会隐形。

同时要求：把本次的 HMAC 偏离补进 `implementation_receipt.json` 的新 `protocol_deviations` 字段。**不要修改已提交 receipt 的其他字段**；若协议规定 receipt 不可变，则新增 hash-bound addendum（沿用 external evidence 那次的做法）。

---

## 4. F2（小，必须）：`key_id` 泄漏密钥的哈希

```python
self.key_id = _sha256(self.__key)     # benchcore/trusted_adjudicator.py
```

key ID 是密钥本身的 SHA-256，且随 attestation 流出。对 ≥32 字节随机密钥不具实际可利用性，但它交出了一个**离线校验密钥猜测的 oracle**，与 V3 §2.4 "never key material" 的精神相悖。

修法（一行，二选一）：

- 域分离：`key_id = sha256(b"benchaudit-adjudicator-keyid-v1" + key)`；
- 或改用与密钥无代数关系的不透明标识符，绑定在 code-owned manifest 里。

加一条测试：`key_id != sha256(key)`。

---

## 5. F3（小，必须）：descendant 情形丢了诊断

V2 §B.3 要求"子孙进程持有 pipe"这一类**单独标记**。当前实现走的是超时分支，transcript 上只留 `timeout`。

行为正确（弃权），但记录不对。**这正是我们已经付过学费的同一个错误**：external evidence 的 `execution_receipt.json` 里 `reason` 为空、真实 `reason_code` 只存在于不可采信的 diagnostic addendum 中，为此多走了一轮。同一原则——**可采信的记录必须自带真实原因**。

修法：在超时分支判断

```python
process.poll() is not None and not (stdout_eof and stderr_eof)
```

命中即写入独立 reason（如 `descendant_retained_pipe`），与普通 `timeout` 区分。行为不变，仍然弃权。

加一条测试：现有的 descendant 测试断言该 reason，而普通超时（leader 未退出）断言 `timeout`。

---

## 6. 禁止清单（延续前三轮）

1. 激活裁决器：不得注册任何生产 manifest、不得接入 CLI / checker / producer / report；
2. 修改 `promotion.py`，尤其不得移除 `DISABLED_UNATTESTED_PROOFS` 任何条目；
3. 修改 `evaluator_execution.py` 的判决逻辑；
4. 修改 V1 / V2 / V3 协议正文；
5. 修改任何历史报告或历史缓存；
6. external evidence V3 / Phase 2B / 出口策略放宽；
7. 重开 APPS input-contract V2（输入域证书）；
8. 调 A / A′ / A″；
9. 做 SVAMP 相关分析（Claude 负责）；
10. **跑 APPS 双正例**——那要等生产 Git verifier 与 digest-pinned container manifest 各自冻结之后；
11. 花费 API 额度；
12. push main；
13. 把失败结果重新归类；
14. 声称 `PASS_TRUSTED_ADJUDICATOR_OS_VISIBLE`。

## 7. 顺序与交付

```
F1（V4 协议 + attestation_class 字段 + receipt 的 protocol_deviations）  ← 最高优先
F2（key_id 域分离）   ┐
F3（descendant reason）┘  可与 F1 并行，各自独立提交
```

提交纪律：协议提交与实现提交分离；`protocol` 提交先于对应的 `impl/tests` 提交。

晨报沿用既有格式，纪律自查新增两项：

- [ ] 未声称 PASS
- [ ] 所有对冻结协议的偏离均已在 `protocol_deviations` 中声明

## 8. F1–F3 完成之后的下一步（不要今夜做）

按交付方自己的排序，我同意：

1. 冻结**生产 Git verifier** 协议（用于机械推导 `non_adaptive_pre_cutoff`）；
2. 冻结 **digest-pinned container manifest**；
3. 才是运行 **APPS 双正例**（`apps/1402` 与 `apps/4352`，两者必须各自独立执行、独立 nonce、独立 attestation，不得共用）。

注意第 1 步会再次撞上 external evidence 那条线的出口问题——**那是环境问题不是研究问题**，不要用协议工作去解决管道问题（这是 07-31 已经确立的结论）。真回放需要一台能直连的机器。
