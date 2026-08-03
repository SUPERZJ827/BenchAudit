# Platinum 盲测运行零 API 预飞结果：`DRY_COUNT_NO_GO`

> Result date: 2026-08-03  
> Final decision for this frozen run design: **DRY_COUNT_NO_GO — no paid run started**

## 1. 一句话结论

897 条 holdout 已全部在不读取 `cleaning_status` / `platinum_target` 的条件下唯一物化，
字段隔离、18-method 集和调用量门均通过；但冻结的 historical-max response 规划代理给出
三跑约 **79,782,468 tokens**，超过预注册的 50,000,000 token 门。因此本轮在第一个
付费请求前停止。

## 2. 绑定产物

| Artifact | Commit / SHA-256 |
|---|---|
| Run protocol V1 | `06fbc2e` / `ba09ef99cefc3f0fa63dbdc49171c1d31dd40a5da21db4200983e28073d57401` |
| Method registry preflight | `bcc336f` / `4de5bed31df4e8b9d8f00c49a14bf105a94ba4a7cb33f6ec5baabf6189cbb346` |
| Run protocol V2 | `b91351a` / `836021cad630dcb379e72152da02d4e452d4d9ad38bd31b1937c5c87e47e65c8` |
| Materializer/dry-count implementation | `a640212` / script `19dda6c799950ad17e0f1165ed899374ffba69900dab4362931873d3e0a49339` |
| Run config | `a640212` / `6aaf42b0fc798fca327ab2dc3b27930cd76bbd459e2df7a1cfbad7b5768ace4a` |
| Constructive tests | `cda001a` / `d33e7b3ec61f9e2b16a683f460814ee53424d14516e30091fd3d472f1116c6ab` |
| Dry-count receipt | `9603d81` / `dbfd2587215923f0fedc7db3647e9cb893ffd58364a13ef7b535afc2fad92a0c` |
| Local canonical audit input | not committed / `a4c07d132bbce9ed7774fdc17d7b63ef4c8e21ffda34a39cd370c9e5fbbdb61a` |

Canonical input 位于：

`/home/zhoujun/llmdata/datasets/platinum_blind_holdout_897/audit_input.jsonl`

它是由冻结 parquet 与 public manifest 确定性重建的派生产物；不含 truth、layer 或
selection counts。

## 3. 先发生的一次零成本协议更正

V1 抄用了历史 SVAMP 报告的 19-method 列表，其中包含当前 registry 已不存在的
`choice_encoding_contract`。在打开 holdout parquet 和运行 dry-count 之前，静态 registry
预飞得到：

- historical report: 19 methods；
- current frozen code: 18 methods；
- historical-only: `choice_encoding_contract`。

因此先记录 `V1_METHOD_SET_NOT_SATISFIABLE_BY_FROZEN_CODE`，再冻结 V2 的当前 18 项。
没有为了复制历史表而接回旧 checker，也没有看任何 holdout 结果后调 method 集。

## 4. 物化与隔离结果

| Gate | Result |
|---|---:|
| public selection rows | 897 |
| unique materialized rows | 897 |
| nonempty task / gold | 897 / 897 |
| duplicate or missing opaque ID | 0 / 0 |
| top-level output keys | 仅 `id/task/gold/aliases/choices/output_contract/evaluator/metadata` |
| metadata keys | 仅 `platinum_config` |
| parquet projection read `cleaning_status` | false |
| parquet projection read `platinum_target` | false |
| emitted layer / counts / truth commitment | false / false / false |
| public manifest passed to auditor | false |
| truth unsealed | false |

十个 config 的物化行数为：

| Config | Rows |
|---|---:|
| multiarith | 174 |
| singleop | 159 |
| singleq | 109 |
| drop | 100 |
| hotpotqa | 100 |
| squad | 100 |
| bbh_logical_deduction_three_objects | 35 |
| bbh_navigate | 35 |
| bbh_object_counting | 45 |
| winograd_wsc | 40 |

`platinum_config` 是已知协变量并被允许进入 detector；`layer` 与标签构成没有进入。

## 5. 调用量与预算

Gold cascade 每题为 3–5 次调用；question/quantity/event 各 1 次，因此：

| Quantity | One run | Three runs |
|---|---:|---:|
| minimum calls | 5,382 | 16,146 |
| maximum calls | 7,176 | 21,528 |
| SVAMP 6.64 calls/item empirical expectation | — | 17,868 |

经验调用成本校准给出：

- expected: `¥37.67`；
- call-count upper proxy: `¥45.39`；
- monetary cap: `¥60`。

这些数字不是 provider invoice，也不能覆盖任务文本更长、级联分支更深带来的 token 风险。

## 6. 唯一失败的门

Dry-count 使用冻结的 DeepSeek-v4-flash MMLU-1000 cache response JSON 字符分布：

- p95 response length: 1,645 chars；
- observed maximum response length: 5,510 chars；
- planning conversion: 4 chars/token；
- 每个 item 的 8-call historical-max-response prompt proxy：median 72,264 chars，
  p95 82,052 chars，max 94,212 chars；
- 三跑 prompt + completion planning proxy：**79,782,468 tokens**。

Gate table：

| Gate | Result |
|---|---:|
| 897/897 unique materialization | PASS |
| field isolation | PASS |
| current method set exact | PASS |
| calls ≤ 21,528 | PASS |
| estimated cost ≤ ¥60 | PASS |
| no new adapter branch | PASS |
| planning token proxy ≤ 50,000,000 | **FAIL** |

这只是保守规划代理，不证明真实运行一定会消费 79.8M tokens；但协议在看到该结果之前已把
它设为 paid-run gate。本轮不能用“实际可能更低”覆盖预注册失败。

## 7. 测试与可达路径

- 定向：`20 passed`（preflight + LLM client）；
- 当前工作树全量：`571 passed in 18.42s`；
- 从提交 `cda001a` 克隆到全新目录后全量：`571 passed in 19.00s`；
- fresh clone worktree clean；测试未依赖未提交文件或本机 canonical input。

构造测试覆盖：truth-bearing parquet 列不进入 projection、五种 evaluator mapping、未知
strategy/空 target fail-closed、18-method 精确匹配、dry-count 无网络/LLMClient 路径，
以及 `workers=8` 被写入 run metadata。

## 8. 没有发生的事

- API attempts: 0；
- network attempts: 0；
- API key reads: 0；
- model responses/cache: 0；
- paid runs: 0；
- truth unseal/scoring: 0；
- method 删除、样本缩减、预算上调或第 4 次运行：0。

## 9. 后续边界

当前 897×3 设计已按冻结门收口。若未来要运行，必须作为**新的实验设计**重新论证，而
不是给本轮改判；可讨论的科学选择包括减少重复数、预注册分层子样本或提高经费/令牌预算，
但它们都会改变估计精度或成本约束，不能事后冒充本轮继续执行。

本轮最有价值的产出不是一个模型分数，而是：在第一笔 API 支出前，确认了字段隔离与
跨任务适配可行，同时量化出三跑全量设计的真正调用/token 尺度并按预注册门停止。

