# MR-4 / EvalPlus 差分 Oracle 确认实验

日期：2026-07-27  
结论：**通过本阶段的窄北极星门槛，但尚未实现“任意 benchmark 自动纠错”。**

## 1. 这次实际证明了什么

系统没有为 HumanEval 或 MBPP 编写题目级证明器，而是使用同一个通用
MR-4 关系：

> 同一个候选程序通过原 benchmark 的弱测试，但被声明为更强的 EvalPlus
> 测试拒绝，则原测试存在一个“相对于强测试的覆盖缺口”。

只有同时满足以下条件才允许 `confirmed`：

- canonical solution 在弱、强 oracle 上均完成且通过；
- candidate 在弱、强 oracle 上均完成；
- 弱 oracle 通过、强 oracle 拒绝；
- timeout、环境错误和损坏输出全部视为 indeterminate；
- candidate 清单、代码哈希、oracle 身份和数据版本均被 transcript 绑定；
- 独立 worker 只为自己实际运行得到的 transcript 进行 Ed25519 签名；
- 父进程固定 worker 公钥并验签；
- 中央 promotion 再次重放 proof contract。

这里的 `confirmed` 是“相对于声明强 oracle 的测试覆盖缺口”，不是声称
EvalPlus 的每个测试都等价于无争议的人类意图。

## 2. 全量实验设置

| 项目 | 配置 |
|---|---:|
| HumanEval | 164 题 |
| MBPP | 378 题 |
| AST 变异 | 每个 family 最多 2 个 |
| 并发 | 8 workers |
| 单 probe timeout | 10 秒 |
| 单任务外层 timeout | 90 秒 |
| 容器 | 只读、无网络、cap-drop、非 root |
| LLM/API 调用 | **0** |
| 完整复跑 | 2 次 |

容器镜像：
`sha256:9e30f4122a069ab7f626cdd70a3c11ddbbf44a9bd0cc4cc834136a2a2f08e995`

## 3. 最新量化结果

| 指标 | HumanEval | MBPP | 合计 |
|---|---:|---:|---:|
| 请求任务 | 164 | 378 | 542 |
| 有效任务 | 162 | 376 | 538 |
| 生成候选 | 1,171 | 1,560 | 2,731 |
| 完成的弱/强配对 | 1,166 | 1,554 | 2,720 |
| timeout / indeterminate | 5 | 6 | 11 |
| confirmed coverage gaps | **50** | **124** | **174** |
| 受影响任务 | **30** | **63** | **93** |
| witness yield | **4.29%** | **7.98%** | **6.40%** |
| 受影响任务比例 | **18.52%** | **16.76%** | **17.29%** |

变异 family 分布：

| Family | Confirmed 数 |
|---|---:|
| numeric constant | 73 |
| return default | 35 |
| comparison boundary | 29 |
| arithmetic operator | 17 |
| range boundary | 5 |
| boolean operator | 5 |
| slice boundary | 4 |
| drop wrapper call | 4 |
| condition negation | 2 |

## 4. 安全对照

| 对照 | Confirmed |
|---|---:|
| canonical solution | 0 |
| identical outcome | 0 |
| timeout 被当成强 oracle 拒绝 | 0 |
| 反向差异：弱拒绝、强通过 | 0 |
| 移除 attestation | 0 |

实际观测到 11 个 timeout 和 24 个反向差异；它们全部没有进入
`confirmed`。

## 5. 相比旧实验，具体改进在哪里

旧的 EvalPlus memory-routing 实验人为将所有结果锁在 `review`，而且执行
驱动把 timeout 与正常测试拒绝都编码为 `passed=false`。

| 口径 | 旧实现 | 新实现 |
|---|---:|---:|
| 可进入 confirmed | 0 | **174** |
| 原始 weak-pass / strong-nonpass | 184 | — |
| 被识别并排除的 timeout | 0 | **7 个旧 witness** |
| 因 canonical 强测试失败而排除 | 0 | **3 个旧 witness** |
| 最终可确认集合 | review-only | **174 confirmed** |

集合级复核表明：新集合正好保留旧结果中 174 个“非 timeout 且 canonical
有效”的 witness；被删除的 10 个由 7 个 timeout 与 HumanEval/32 上的
3 个候选组成。也就是说，这次不是通过放宽门槛增加数字，而是先修正
旧口径，再为剩余证据建立独立执行与 promotion replay。

## 6. 可复现性

两次完整运行得到相同的：

- stable summary SHA-256：  
  `c343687e82ca5f1659f89752f954260c9ea2dc6444fbd70675d6be285c5d14f7`
- finding identity + transcript 集合 SHA-256：  
  `ccbbf9de807e7cfc17bc439f669478254188b5e30df3ee0dbda9452b313a487d`

每次 worker 使用新的签名密钥，因此原始 JSON 的签名字段和运行耗时不同；
这不影响 verdict、transcript hash 或稳定摘要。

## 7. 是否达到预期

### 已达到

- 在两个未为其编写题目级 proof validator 的 benchmark 上得到真实
  `confirmed`；
- 同一个按“弱/强 oracle 关系”定义的通用 validator 跨 HumanEval 和
  MBPP 复用；
- confirmation 不依赖 LLM、多模型投票或人工逐题判断；
- timeout、canonical 失败、无 attestation 等情况均 fail-closed；
- 两次全量结果完全复现；
- 全仓测试 `760 passed`，`unittest 201 OK`，安全登记表通过。

### 尚未达到

- HumanEval 与 MBPP 都属于 Python 函数生成，且强 oracle 都来自
  EvalPlus；这证明了“跨 benchmark 复用”，还没有证明“跨领域复用”；
- 系统仍需要 loader 声明弱/强 oracle 的身份和关系，尚未自动发现所有
  新 benchmark 的执行协议；
- 结果是相对 coverage gap，不是所有题目语义错误的完整真值；
- 本实验没有更新 WorkspaceBench、TerminalBench、排行榜变化或以人工
  标签计算的 precision/recall；
- 两个任务因容器 OOM 退出，两个 canonical control 不满足，均被明确
  排除而非静默计作无缺陷。

因此，最准确的判断是：

> **MR-4 已经把“56% confirmed proof 依赖 benchmark 手工实现”的问题向前
> 推进了一大步，并首次在两个真实 code benchmark 上完成无题目级验证器
> 的自动确认；但它只覆盖具有可声明弱/强 oracle 的可执行任务，不能据此
> 宣称任意 benchmark 自动纠错已经完成。**

## 8. 下一步

1. 在第三个、非 EvalPlus 系列的可执行 benchmark 上冻结 holdout，检验
   相同 proof contract 是否仍成立；
2. 将实验内独立 worker 提升为可部署的 attestation service，而不是脚本
   内部实现；
3. 为 oracle-pair 自动发现建立 fail-closed adapter：只生成候选 contract，
   未通过 registry receipt 时保持 review；
4. 做 clean negative / defect injection 配对实验，报告 coverage-gap
   检测的 precision、recall 与成本；
5. 再扩展到 rubric/artifact 关系；没有确定性 verifier 时仍坚持
   review-only。

