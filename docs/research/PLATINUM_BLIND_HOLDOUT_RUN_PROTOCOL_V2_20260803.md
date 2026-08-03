# Platinum 盲测运行协议 V2：绑定当前可执行的 18-method 集

> Freeze date: 2026-08-03  
> Status: **FROZEN_BEFORE_DATA_DRY_COUNT_AND_ANY_PAID_RUN**  
> Supersedes: V1 §4 的 method 有序列表，以及依赖该列表的 §8(5)/§9(3)/§10(9)  
> V1 其余条款全部继承，不放宽

## 0. 为什么需要 V2

V1 在任何数据物化或付费请求前，把历史 SVAMP 报告的 19-method 集误当成当前代码的
registry，其中包含 `choice_encoding_contract`。协议提交后的静态 registry 预飞证明：

- 当前冻结代码只能产生 18 项；
- `choice_encoding_contract` 不存在于当前 checker registry；
- 强行保留 V1 列表会使每次运行必然得到 `NOT_COMPARABLE_METHOD_SET`；
- 为迁就历史报告重新接回旧 checker 会改变被测系统，且没有本实验的科学必要性。

本次更正发生在 0 个数据 dry-count、0 个 API request、0 个 prediction、0 个 truth unseal
之后；它不依赖任何 holdout 结果。

## 1. 绑定

| Artifact | Commit / SHA-256 |
|---|---|
| Run protocol V1 | commit `06fbc2e`, SHA `ba09ef99cefc3f0fa63dbdc49171c1d31dd40a5da21db4200983e28073d57401` |
| Method registry preflight | commit `bcc336f`, SHA `4de5bed31df4e8b9d8f00c49a14bf105a94ba4a7cb33f6ec5baabf6189cbb346` |
| Current `benchcore/checkers.py` | `24c303bc695c8e879ac990b0cbed758e2394c9a081efcc5ecf10ab3deb95955b` |
| Current `benchcore/methods.py` | `8d8b55f942a3db267c04dde1e2e4af1846691f22961661363e594e6da6e4cd5b` |
| Current `benchcore/cli.py` | `40700d90ea1ded61430e0f78b2e12e514ed1afac9158e99c6a20326c0efb06c5` |

预飞为纯 Python registry import：API/network 均为 0，未打开 parquet、public manifest 或
sealed truth。

## 2. V2 冻结 method 集

三跑 `methods_run` 必须与下列**有序 18 项逐项相同**：

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
```

集合或顺序任一不符即 `NOT_COMPARABLE_METHOD_SET`。三跑仍须完全相同。

## 3. 不主张什么

- V2 不声称与历史 19-method SVAMP 运行做跨 benchmark method-by-method 等价比较；
- V2 不把删除一个历史 method 解释成性能优化；
- V2 不允许运行后继续增删 method；
- V2 不改变 V1 的 flag 谓词、三跑规则、字段隔离、预算或停止条件。

本实验回答的是当前冻结 BenchAudit 在新 holdout 上的盲测表现和自身三跑稳定性；这两个
问题只要求本实验内部的三跑 method 集一致。

