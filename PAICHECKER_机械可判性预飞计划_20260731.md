# PAIChecker 机械可判性预飞：计划与预注册协议

> 日期：2026-07-31
> 状态：**计划草案。阶段 0/1 跑完必须先经独立复核，才允许进入阶段 2 写实现。**
> 全程 **零 LLM/API 调用**。

---

## 0. 这份计划从哪来

**论文**：PAIChecker: Uncovering and Checking PR-Issue Misalignment in SWE-Bench-Like Benchmarks
arXiv `2607.28587v1`（2026-07-30），Manyi Wang / Junjielong Xu / Pinjia He
代码与数据：`https://github.com/manyifire/PAIChecker`

**它做了什么**：SWE-bench 类 benchmark 把 issue 当问题陈述、PR patch 当 oracle，但这个配对经常错。系统研究 SWE-bench Verified，**13.6% 存在 PR-Issue 错配**，分 5 类模式 11 个细分场景。提出 PAIChecker，三阶段多 agent 系统，最高 **92.12% 二分类准确率**。

**它和我们是什么关系**：同一个缺陷家族的另一个化身。

| BenchAudit（Workspace） | PAIChecker（SWE-bench） |
|---|---|
| task ← rubric 是否被授权 | issue ← PR patch 是否对齐 |
| `task_rubric_mismatch` | PR-Issue misalignment |

**它停在哪**：三个阶段**全是 LLM**。其中名为 "Code Validation" 的第三阶段，论文明确是"又一次 LLM 调用 + 仓库文件检索"，不是确定性执行。消融数据佐证它的份量很轻：

```
完整 pipeline    92.12% BA / 84.66% EM
w/o Phase I      67.83%      (−24.29)   ← 活全在这
w/o Phase II     87.41%      (−4.71)
w/o Phase III    88.97%      (−3.15)    ← "code validation" 只值 3 个点
```

**所以确认合同这个位置仍然空着。**

---

## 1. 机会：它的分类法里有一部分是纯机械的

PAIChecker 的 11 个场景（括号内为 SWE-bench Verified 中的实例数）：

| 场景 | 定义 | 是否需要语义判断 |
|---|---|---|
| **SC-1**（12） | PR 解决多个 issue，只链接了一个 | ❌ **解析 PR 描述里的 issue 引用即可** |
| **UL-1**（1） | test patch 断言了 issue 里没有的精确字面量 | ❌ **字面量包含检查** |
| SC-4（6） | 夹带其他 issue 的补丁 | 部分（issue 引用） |
| SC-2（2）/ SC-3（2） | 超出 issue 范围加功能 / 捆绑修复 | 需语义 |
| DP-1（14）/ DP-2（16） | 引入新 bug / 修不完整，需后续 PR | 部分（**后续 PR 是否引用同一 issue，是图/元数据**） |
| FP-1（2）/ FP-2（1） | 本 PR 在补前一个 PR | 部分（同上） |
| IS-1（12）/ IS-2（6） | issue 细节在讨论区补充 / 后被重定义 | 部分（**断言内容只在评论不在正文** = 文本包含） |

**PAIChecker 对全部这些都用了 LLM agent，包括纯元数据的那几类。**

在 SC-1 和 UL-1 上，确定性检查器要么找到那个 issue 引用/字面量，要么找不到 —— **没有 92%，只有命中或弃权**。这就是 review 与 confirmed 的分界。

UL-1 的形状和我们已有的 `route_exact_constraints`（Exact router）完全一致：**规范里没出现的字面量，出现在了 oracle 里**。

---

## 2. 数据为什么重要

PAIChecker 声明公开全部标注数据：

```
SWE-Gym                  2,438 例   双标注  κ=0.91 (binary) / 0.86 (细粒度)
SWE-bench Multilingual     300 例   双标注
SWE-bench Verified         500 例   预研，单标注 + 二审
```

**这是第三方标注的、我们没有参与构造的外部参照。** 正好是路线图 Phase C 要的"自然存在的强 oracle"，也可能顶上 Phase A 在 DBCode 判 `NOT_IDENTIFIABLE_DATA_LINKAGE` 之后空出来的对象位。

---

# 阶段 0：数据可得性预检（零 API，先做，可能直接判死）

**不要先写检查器。** 先确认数据存在、且含我们需要的字段。

## 0.1 取数据

```bash
git clone https://github.com/manyifire/PAIChecker /tmp/paichecker
```

## 0.2 要统计的东西

只输出**聚合计数与哈希，不导出任何原文**：

1. 仓库是否存在、是否非空 —— **论文 07-30 才发，很可能还没传数据**；
2. 标注文件的行数、字段名、格式；
3. 每条是否含 `instance_id` 与 `label`（binary + 细粒度场景码）；
4. **是否含 issue 正文 / issue 讨论 / PR 描述 / PR patch / test patch** —— 还是只有 `instance_id`，需要回 SWE-Gym 取；
5. 各场景码的实际分布，与论文的 12/2/2/6/14/16/12/6/2/1 对照。

## 0.3 停止条件

- 仓库空、或只有代码没有标注数据 → 记 `NOT_IDENTIFIABLE_DATA`，**停**；
- 数据只有 `instance_id` 且拿不到 PR 描述与 test patch → 记 `NOT_IDENTIFIABLE_DATA`，**停**。

**不要去别处凑数据、不要手动补。** 停下来报告，这本身是结论。

## 0.4 产出

`docs/experiments/paichecker_data_receipt_20260731.json`：仓库 commit、文件列表与 SHA-256、行数、字段名、场景码分布、判定结果。

---

# 阶段 1：机械可判性预飞（零 API）

**只统计，不判断。** 回答一个问题：

> 在标注为错配的实例里，有多少条能机械抽出判定所需的字段？

## 1.1 三组（B 组是唯一通向 confirmed 的那组）

| 组 | 判定依据 | 需要的字段 | 最高证据层 |
|---|---|---|---|
| **B · 字面量差分执行**（**主线**） | 断言字面量 L 不在 issue 正文，且 production patch 引入同一 L，且变异 L 后测试失败 | test patch + issue 正文 + **production patch** + **可重放执行环境** | **confirmed** |
| A · issue 引用 | PR 描述中 `#N` 引用数 > 1，或与 benchmark 链接的 issue 不符 | PR 描述 | review |
| C · 讨论区补充 | 断言内容只出现在 issue 评论、不在正文 | issue 正文 + 评论 | review |

对每组报告**可抽取率**：多少条能拿到全部所需字段。**这一步不判定对错，只看字段够不够。**

B 组要额外报一个数：**多少实例能在钉住的容器里复现原始测试结果**（这是差分执行的前提，抽不出字段和跑不起来是两回事，要分开计）。

> 已知的好消息：`examples/dp_example.jsonl` 的字段结构里，`issue_body / issue_discussion / pr_description / production_patch / test_patch` **全部存在**。所以一旦作者发布逐实例标注，字段侧应该是够的 —— 卡点会在可执行复现，不在字段。

## 1.2 预注册门槛（写进协议，跑完不许改）

> **B 组**（字面量差分执行）的可抽取率 **≥ 20%**，且可抽取且**可容器复现**的实例数 **≥ 30**
> → 进入阶段 2。
>
> 否则记 `NOT_IDENTIFIABLE_PREFLIGHT`，**停**，把"v1 不可行"写成结论。

**门槛只看 B 组。** A、C 两组即使覆盖率很高也不放行 —— 它们产出不了 confirmed，做出来不改变这条线的立论。它们的统计只作报告，不参与 Go/No-Go。

覆盖率不够是**有价值的负结果**，不是失败。这个模式今年已经救过两次场（APPS V1 覆盖 2.49% 省掉一整轮；DBCode 完整链 0/0 省掉三周）。

## 1.3 产出

`docs/experiments/PAICHECKER_MECHANICAL_PREFLIGHT_RESULTS_20260731.md` + 对应 receipt json。

**跑完先停，交独立复核，通过才进阶段 2。**

---

# 阶段 2：实现 v1（仅在过门槛后）

## 2.0 先修正一个致命设计错误

本计划初稿把 R-UL 和 R-SC1 都写成了"文本包含检查 → candidate"。**这个设计产出不了任何 `confirmed`，因此立不住整个计划的立论。**

原因：

- **SC-1**：多个 `#N` 引用有太多良性解释 —— 引用笔误、多个 issue 共享同一根因、一个 PR 合法关闭多个 issue。论文自己就给了反例。**"引用数 > 1"不构成错配的证明。**
- **UL-1**：即使字面量不在 issue 正文里，它仍可能是**可机械推导的合法值**（issue 说"返回总和"，测试断言 42，而 42 正是所给输入之和）。而"证明某个值不可推导"在一般情况下做不到。

**两条都只能到 review，不能到 confirmed。** 而"我们能确认他们只能复核的东西"正是这条线的全部价值。所以 v1 必须改。

## 2.1 修正后的范围

### R-UL-EXEC：字面量差分执行证明（唯一的 confirmed 路径）

**思路转向**：不再试图证明"L 不可推导"（做不到），改为证明"**oracle 对 L 这个具体值敏感**"（可执行、可重放）。

SWE-bench 类有真实可执行测试，所以可以做：

```
1. 确认字面量 L 出现在 test patch 的断言中，且不出现在 issue 正文（归一化后）；
2. 确认 production patch 引入了同一个 L；
3. 对 production patch 做确定性变异：L → L'（同类型、同长度族的邻值）；
4. 在钉住的容器里重跑官方测试：
     - 变异后测试失败  → oracle 被钉死在 L 上
     - 变异后测试通过  → L 不是判定依据，NOT_IDENTIFIABLE
5. 若「测试对 L 敏感」且「L 不在 issue 正文」→ 规范从未规定该值，oracle 却强制它。
```

**这就是我们已经跑通两次的 MR-4 形状**（HumanEval/MBPP 函数调用 → APPS stdin/stdout），SWE-bench 只是第三个执行协议。证据可本地重放：变异体哈希 + 测试结果 + 独立签名 → 够得着 `confirmed`。

**弃权条件（任一命中即 `NOT_IDENTIFIABLE`）：**

- 抽不出断言字面量、patch 解析失败；
- production patch 未引入同一 L；
- 变异后测试仍通过（说明 oracle 不依赖 L）；
- 测试超时、报错、环境不可重放；
- 变异导致语法错误或无法编译。

### R-SC1：降级为 review-only 信号，不进 confirmed

保留实现，但**明确标注为 review**：

1. 从 PR 描述解析全部 `#N` / `fixes|closes|resolves #N` 引用；
2. 引用数 > 1 且 benchmark 只链接其中一个 → **review candidate**；
3. 解析不出引用 → `NOT_IDENTIFIABLE`；
4. **该规则永远不得升级为 confirmed**，`confirmation_eligible=False` 写死在数据结构里。

它的价值是给人工复核排序，不是证明。

## 2.2 新增的执行环境要求

R-UL-EXEC 需要可重放的执行环境，照搬 APPS 那一轮的做法：

- 容器镜像按 **registry digest** 钉住；
- 禁网、只读 root 文件系统、non-root UID/GID、dropped capabilities；
- 每测试用例超时、外层任务超时都要预先固定；
- 变异体源码哈希绑进执行 transcript；
- 独立 worker 签名，父进程钉住 worker 公钥并独立验签。

**若 SWE-Gym / SWE-bench Multilingual 的实例无法在钉住的容器里复现原始测试结果 → 记 `NOT_IDENTIFIABLE`，不得放宽。**

## 2.2 硬要求（照搬 A″ 那一套，逐条不许省）

1. **裁决必须抽成纯函数**，与文件无关，可零依赖测试；
2. **每条规则至少两条可达输出路径**（命中 / 弃权），各有构造性测试；
3. **走中央 promotion**，不自判 confirmed；
4. **控制集**：正例零漏、反例零触发、字段缺失记 `NOT_IDENTIFIABLE` 而非 clean；
5. **零 LLM 调用**；
6. **代码与测试中不得出现任何具体 instance_id**；
7. 任何"测试通过"的声明必须来自 `git clone` 到全新目录后的运行结果，**未提交的文件不得参与测试**。

> 第 2、7 条有来历：上一轮某自动化流程把裁决写死成常量、并用依赖未提交文件的测试宣称通过。这两条是机械可查的防线。

---

# 阶段 3：对照评估

在 PAIChecker 的标注上算：

| 指标 | 含义 |
|---|---|
| **confirmed 数** | 通过差分执行证明的实例数 —— **这是唯一的头条数字** |
| **覆盖率** | 我们能判的 / 全部标注错配 |
| **条件精度** | 我们判 candidate 的里有多少被他们标为错配 |
| **弃权率** | `NOT_IDENTIFIABLE` 占比 —— **这是特性，不是缺点** |
| 变异后测试仍通过的比例 | 说明 oracle 不依赖该字面量，属正常弃权，不是失败 |
| 对照 | PAIChecker 在同一子集上的表现（他们全部是 review 层） |

**如果 confirmed 数为 0，本轮记 NO_GO，不要用 review 层的覆盖率去粉饰。** 这条线要么产出机器可确认的证据，要么就是负结果。

## 叙事目标

**不是"我们准确率更高"** —— 大概率不会更高，覆盖率也一定更低。是：

> 在我们能判的那个子集上，结论**可由本地程序重放**，不依赖任何模型判断；
> PAIChecker 在同一子集上给出的是 92% 准确率的 LLM 共识。

覆盖率低 + 可重放，胜过覆盖率高 + 需人工复核 —— 这是整个项目的立论。

---

# 提交顺序（四步分开，不许合并）

```
1. 本协议 + 预注册门槛        → 单独提交
2. 扫描器 + 测试              → 单独提交
3. 运行（阶段 0、阶段 1）
4. receipt + 结果报告         → 单独提交
```

阶段 1 跑完**必须停下来交复核**，过门槛才允许写阶段 2 的实现。

---

# 明确不做的事

- 不用 LLM 做任何判定 —— 那是 PAIChecker 已经做过的，重复没有价值；
- 不为了提高覆盖率放宽 `NOT_IDENTIFIABLE` 的判据；
- 不在看过目标实例之后修改抽取语法；
- 阶段 0/1 未过门槛就不写实现；
- 不手动补数据。

---

# 附：要同步更新的两处文档

1. **路线图 Phase C 的 novelty boundary** —— 现在只提了 STING，必须补上 PAIChecker，并写明差异点：
   > PAIChecker 三个阶段全是 LLM（包括名为 "Code Validation" 的第三阶段，消融仅值 3.15 个点）；我们的主张是机器可重放确认。

2. **Phase A 的对象** —— DBCode 判 `NOT_IDENTIFIABLE_DATA_LINKAGE` 后 Phase A 无对象。若本预飞过门槛，SWE-bench 类是当前最合理的候补（有真实可执行测试 = 一个新执行协议，且现在有了外部标签集）。
