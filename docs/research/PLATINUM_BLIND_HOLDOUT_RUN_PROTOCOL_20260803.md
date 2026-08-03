# Platinum 盲测运行协议：隔离物化、三次独立运行与零 API 预算门

> Freeze date: 2026-08-03  
> Status: **FROZEN_BEFORE_DRY_COUNT_AND_ANY_PAID_RUN**  
> Scope: 已冻结的 897-item Platinum holdout；本协议不解封真值、不改变选择结果  
> Paid-run authorization: 只有 §8 的零 API 门通过后才可启动

## 0. 目标与不可混淆的证据范围

本实验测量 BenchAudit 在**从未用于系统开发、阈值选择或 prompt 调整**的 Platinum
config 上的检测表现与运行间稳定性。它不主张这些题目对基础模型预训练不可见。

三层证据角色保持选择协议 V1–V3 的定义，并增加以下硬边界：

- Layer B 是唯一允许报告 `revised`（gold-error）recall 的层；
- Layer A 只有 3 条 revised，Layer C 为 0 条；A/C 只报告 revised support，**不得报告、
  推断或文字暗示 revised recall**；
- Layer A combined recall 主要由 22 条 rejected 决定，不得解释为 gold auditor 泛化；
- Layer C 仅为探索性；
- Platinum 检测表现与 MMLU 模型分数影响不是 item-level 闭环，不得写成“检出的这些
  缺陷导致了 MMLU 上的影响”。

## 1. 冻结输入

| Artifact | SHA-256 / immutable value |
|---|---|
| Code parent before this protocol | `18fdfcbd169336aef333f123593a91ba0bad8814` |
| Public selection manifest | `37637b8e4d19e66f002d9b766180b57c7076b31123b7139b28441ec6beaabe32` |
| Selection receipt | `e62acd45f95c0cac00582207d2f02e6618444bb2c3168e595ffc0317e4287f7c` |
| Selection V3 | `19ad4fcdaccd2a57e3f134fd149f6c611f92801ef1ae8e01f22c24c770a6d613` |
| Dataset repo | `madrylab/platinum-bench` |
| Dataset revision | `51920a33bfb4620c789729ace14141e87a14969b` |
| Public item-set SHA-256 | `d7c8294e6c8c80859e18bdc02de800138602d55ffeaf310ec41dddab30be79ad` |
| Sealed-truth commitment | `8e09ebc36684b24d291902e5942daa40a20bb69994d2a5cd2ad9e96a02ddfe0a` |
| Frozen item count | `897` (`442 + 300 + 155`) |

十个 config 的 parquet SHA-256 必须逐项等于已提交 availability receipt；物化器不得接受
调用方覆盖。任一哈希不符即 `SOURCE_ARTIFACT_MISMATCH`。

## 2. 检测输入隔离：公开 manifest 不进入 auditor 进程

公开 manifest 的 `counts` 和 item-level `layer` 对预注册透明度是必要的，但二者泄露了
精确标签构成。它们不得进入检测路径。

### 2.1 两阶段边界

1. 受信物化器读取公开 manifest，只用于按 `(config, opaque_id)` 定位冻结条目；
2. 物化器输出独立 canonical JSONL；
3. `benchcore.cli audit` 只接收该 JSONL，**不接收 public manifest、selection receipt、
   sealed-truth commitment 或 layer map 的路径**；
4. auditor 子进程的 argv、环境变量和可读输入清单须写入 receipt，机械证明上述文件不在
   输入面内。

不能仅靠 prompt 层“答应不使用”这些字段；它们必须在审计进程的数据结构中不存在。

### 2.2 物化字段白名单

每条 canonical row 只允许以下顶层键：

```text
id, task, gold, aliases, choices, output_contract, evaluator, metadata
```

其中：

- `id = opaque_id`；
- `task = platinum_prompt_no_cot`；
- `gold = original_target[0]`，`aliases = original_target[1:]`；空 target fail closed；
- `choices` 只在冻结源行有显式 list-valued `options` 时复制，否则为 null；不得从 truth
  或结果中反推；
- `platinum_parsing_strategy` 只用于机械导出 evaluator/output contract，不原样进入 metadata；
- `metadata` **只允许** `{"platinum_config": <config>}`。

`platinum_config` 是适配器与分层报告所需的已知协变量，允许进入检测路径并必须在结果中
披露。`layer`、`counts`、`cleaning_status`、`platinum_target`、`truth`、`binary_truth`、
`selection_seed`、`selection_rank`、`sealed_truth_sha256` 一律禁止。

物化时 parquet projection 必须在读取边界排除 `cleaning_status` 与 `platinum_target`；
物化器不得先读入再删除。identity 使用已冻结的 `row_identity()`，它不依赖这些字段。

### 2.3 evaluator 导出表

| Frozen parsing strategy | evaluator | output contract |
|---|---|---|
| `math` | `numeric_exact_match` | single numeric answer |
| `text` | `normalized_exact_match_with_aliases` | one short textual answer |
| `squad` | `normalized_exact_match_with_aliases` | one extractive textual answer |
| `bbh_multiple_choice` | `multiple_choice_exact_match` | one listed choice |
| `multiple_choice` | `multiple_choice_exact_match` | one listed choice |

未知 strategy、空 prompt、空 original target、opaque ID 无法唯一 join，均为
`NOT_IDENTIFIABLE_MATERIALIZATION`，不得临时加 adapter。

## 3. 冻结执行条件

| 项 | 值 |
|---|---|
| profile | `generic`（显式，不用 auto detection） |
| model | `deepseek-v4-flash` |
| base URL | `https://api.deepseek.com` |
| temperature | `0.0` |
| thinking | `disabled`（配置中必须显式出现） |
| max tokens / call | `5000` |
| votes | `1` |
| LLM auditors | `gold,question,quantity,event` |
| gold evidence mode | `cascade` |
| workers | `8`，必须进入 run metadata |
| repetitions | `3` |
| cache | 每跑各自全新、空、路径不同；禁止跨跑复用 |
| remote egress | 仅 §2.2 canonical row 可出站；需显式 `--allow-remote-data-egress` |

三跑不得因失败或结果不好看而增加第 4 跑。允许的结果是三跑完成，或按 §9 提前停止并
报告不完整；不存在“补跑取代失败跑”。

## 4. 冻结 method 集

三跑的 `methods_run` 必须与下列**有序列表逐项完全相同**：

```text
task_specification
context_attachment
expected_output
oracle_ground_truth
evaluator
task_integrity
contract_consistency
evaluator_replay
metamorphic_answer
evaluator_mutation
executable_evidence
differential_candidate
llm_gold_audit
llm_question_clarity
llm_quantity_consistency
llm_event_state
duplicate_conflict
schema_drift
choice_encoding_contract
```

集合或顺序任一不符即 `NOT_COMPARABLE_METHOD_SET`。不得把未知/不适用 method 静默删掉，
也不得因 config 不同启用不同 method。调用命令相同不替代结果里的逐项断言。

## 5. “检出”的唯一 item-level 口径

沿用 `SVAMP_REPLICATION_N5_PROTOCOL_20260802.md §2`：

> 一个 item 被 flag，当且仅当它至少有一条
> `defect_scope != "presentation"` 的 violation。

该定义在运行后不得变更。所有 primary recall、specificity/FPR 与稳定性 finding set 均从
此冻结谓词派生。presentation finding 单独报告但不使 item 成为预测阳性。

finding 身份键继续为：

```text
(item_id, detection_method, defect_type)
```

三跑间 item Jaccard、violation Jaccard、逐 method 复现率沿用 SVAMP n=5 口径；不新增
事后有利的身份键。

## 6. 分层计分边界

- Layer B primary：revised recall、rejected recall、balanced positive recall、specificity/FPR；
- Layer B 是唯一输出 revised recall 的层；
- Layer A：combined recall、specificity/FPR、empirical low-prevalence precision/F1，另仅列
  `revised support = 3`；
- Layer C：combined recall 与 specificity/FPR 仅探索性，另仅列 `revised support = 0`；
- A/C 的 scorer schema 中不得存在 `revised_recall` 键；不是填 `null` 或 `0`，而是拒绝
  生成该 metric；
- Layer B raw-sample precision/F1 不得作为 benchmark precision；标准化 PPV、权重、区间
  与三跑中位数完全沿用 Selection V3。

三跑每跑独立计分。每项头条为三跑中位数，三个原值、min–max 与 sample SD 全列；
union/intersection 只作 secondary。

## 7. 真值封存与提交顺序

1. 物化器、dry-count、run config、唯一 scorer 与 tests 先提交；
2. 零 API receipt 提交；
3. 每次 paid run 的 prediction/report 单独提交，三次 commit 均不得读取 sealed truth；
4. 三次 prediction commit 后提交 prediction-lock，绑定三个 prediction artifact SHA-256；
5. 只有 lock 提交后，唯一 scorer 才能解封/join truth；
6. scoring receipt 证明 scorer/config 是三个 prediction commits 的共同祖先。

run path 不得读取 public manifest 的 counts/layer；scorer 在 unseal 后可用 layer 与 truth。

## 8. 零 API dry-count 门

paid run 前必须运行确定性的 dry-count 工具。它可以物化 prompts，但不得构造
`LLMClient` 的联网实例、不得读取 API key、不得写模型缓存、不得生成模型响应。

receipt 至少记录：

- `api_attempts = 0`、`network_attempts = 0`、`model_responses_produced = false`；
- 897 条是否全部唯一物化；输入 JSONL SHA-256 与仅允许字段集；
- config 行数、prompt/gold/alias 非空计数和长度分布；不得记录 layer/truth 计数；
- 固定非 gold auditor 调用数：每个合格 item 各 question/quantity/event 一次；
- cascade gold 下界：blind + matcher + applicability = 3 calls/item；
- cascade gold 上界：再加 challenger + defender = 5 calls/item；
- 每跑与三跑总调用量上下界；
- exact serialized prompt character count 的下界和按冻结 stage schema 计算的上界；
- 使用的 token 估算方法、版本与误差边界；
- 以历史 SVAMP `664 calls / 100 items / ≈¥1.4` 只作经验校准，不当作 provider 账单证明。

冻结算术上界为：

- 每 item 6–8 calls；
- 每跑 `5,382–7,176` calls；
- 三跑 `16,146–21,528` calls。

只有同时满足下列条件才记 `DRY_COUNT_GO`：

1. 897/897 唯一物化且字段隔离通过；
2. 预期三跑花费 `<= ¥60`，硬预算仍为 `¥60`；
3. 三跑调用上界 `<= 21,528`；
4. 三跑 provider token 上界 `<= 50,000,000`；
5. frozen method list 可由当前 CLI 精确产生；
6. 无任何需要在见数据后新增的 adapter 分支。

任一不符即 `DRY_COUNT_NO_GO`，停止，不提高预算、不删 method、不减少层或 item。

## 9. Paid-run 停止条件

总预算：`<= ¥60`；总 provider tokens：`<= 50,000,000`；每跑 API attempts 硬上限按
dry-count 上界设为 `7,176`，不得运行后抬高。

出现任一条件立即停止剩余运行：

1. 任一跑 operational failure item 比例 `> 5%`；
2. 任一 LLM-derived finding 被提升到 `confirmed`；
3. `methods_run` 不等于 §4；
4. 任何 run 读到 layer/counts/truth commitment 或未白名单 metadata；
5. API、token 或人民币预算触顶；
6. 输入 JSONL、配置、代码或 prompt schema 在三跑间变化；
7. cache 在开跑前非空、在跑间复用，或出现不能解释的 cache hit。

## 10. 必须先通过的构造性测试

1. public manifest 含 counts/layer，但 materialized row 与 outbound payload 都不含；
2. 把 layer/counts/truth 字段注入 canonical row 时 fail closed；
3. parquet projection 请求 `cleaning_status` 或 `platinum_target` 时 fail closed；
4. config 保留且除此之外 metadata 为空；
5. 897 IDs 全部且仅一次 join，未知/重复 ID 拒绝；
6. 五种 parsing strategy 的 evaluator 映射逐项命中；未知 strategy 拒绝；
7. A/C scorer 尝试生成 revised recall 被拒；B 可以生成；
8. presentation-only item 不被 flag，任一非-presentation violation 被 flag；
9. 三跑 method 集有一个缺失、新增、调序均拒绝；
10. dry-count fake/network trap 证明 API key 与 socket 不被访问；
11. dry-count 6–8 calls/item 的边界在 constructed cascade paths 可达；
12. fresh clone 运行定向与全量测试；未提交文件不得参与通过声明。

## 11. 允许的下一步

本协议提交后，只允许实现并测试：物化器、显式 run config、dry-count、唯一 scorer 的
pre-unseal 部分及上述 gates。先产出并提交零 API receipt；只有 `DRY_COUNT_GO` 才可开始
第一次 paid run。
