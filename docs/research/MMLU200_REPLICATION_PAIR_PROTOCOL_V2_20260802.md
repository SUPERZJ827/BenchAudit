# MMLU-200 同配置独立复现对协议 V2

> 日期：2026-08-02  
> 状态：**frozen before any V2 paid API request**  
> V1 结局：`STOP_AFTER_RUN1_OPERATIONAL_FAILURE_GATE`，保留且不改写  
> V2 变更：使用已证明能在预算内完整执行的 18-method 配置；API attempt 上限 1600

## 0. V2 为什么重开

V1 的第一跑在 200/200 item 后停止：1400 次 provider 调用全部成功，但全局 attempt cap 被打满，后续 303 个 checker invocation 在 provider 调用前 fail-closed，形成 `303/3645 = 8.31%` operational failure。第二跑按协议没有启动。

独立检查又发现 2026-08-01 的历史 21-method `mmlu200` 同样打满 `1400/1400`，有 `312/3637 = 8.58%` operational failure；本次 V1 实际复现了历史截断，而不是 MMLU 稳定性。

稳定性实验要求两跑完整且方法集一致，不要求方法集最大。历史 `mmlu200_comparable` 的 18-method 配置使用 1263/1400 attempts、operational failure `2/3057 = 0.07%`，因此 V2 选择该方法集，并把 cap 设为 1600 留出约 27% 头寸。

这不是把 V1 门槛调到通过：

- V1 结果与回执保持原样；
- operational failure 5% 门不变；
- 只减少三种非必要 auditor（presentation、quantity、event），且在任何 V2 结果产生前冻结；
- 两跑仍用各自全新空缓存，不复用 V1 的 1400 条结果。

## 1. 冻结输入与配置

| 项 | 值 |
|---|---|
| 数据 | `/home/zhoujun/llmdata/datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl` |
| 数据 SHA-256 | `0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4` |
| manifest | `experiments/mmlu_redux_pilot200.manifest.json` |
| manifest SHA-256 | `f60757deeb3f8ba6a682575fd7a87573999b8f0004894729f4904c189f6d77e1` |
| 配置 | `configs/llm_deepseek_mmlu200_replication_v2_20260802.json` |
| 配置 SHA-256 | `9b8c0d774e527c470d3854dc5d0f02512056daa3f01755aa3d17312ac3482e52` |
| model | `deepseek-v4-flash` |
| temperature | `0.0` |
| thinking | `disabled` |
| max_tokens | `5000` |
| votes | `1` |
| vote_temperature | `0.3`（votes=1 时不参与采样） |
| max_api_attempts | `1600` |
| observed_token_stop | `4,000,000` / run |
| workers | `8`，必须进入 run_metadata |
| auditors | **`gold,question,option`** |
| gold evidence | `cascade` |
| 运行 | 2 次，严格串行 |
| cache | 两个运行前不存在的空缓存；禁止跨运行和跨协议复用 |
| transport | 显式 HTTPS CONNECT `127.0.0.1:17890` → `api.deepseek.com:443`，TLS 端到端校验不变 |

## 2. 冻结的 18-method 集

V2 配置已在零 API `--llm-dry-run` 上机械导出以下列表。两次 `methods_run` 必须逐项、逐序完全相同：

1. `task_specification`
2. `context_attachment`
3. `expected_output`
4. `oracle_ground_truth`
5. `evaluator`
6. `task_integrity`
7. `contract_consistency`
8. `evaluator_replay`
9. `metamorphic_answer`
10. `evaluator_mutation`
11. `executable_evidence`
12. `differential_candidate`
13. `llm_gold_audit`
14. `llm_question_clarity`
15. `llm_option_set`
16. `duplicate_conflict`
17. `schema_drift`
18. `choice_encoding_contract`

V2 明确不运行：`llm_presentation_integrity`、`llm_quantity_consistency`、`llm_event_state`。不得在运行后补回或再删除方法。

## 3. 运行命令与门

每次 audit 的冻结参数：

```text
--manifest experiments/mmlu_redux_pilot200.manifest.json
--llm-audit --llm-auditors gold,question,option
--gold-evidence-mode cascade
--llm-config configs/llm_deepseek_mmlu200_replication_v2_20260802.json
--workers 8 --progress-every 10
--allow-remote-data-egress --print-summary
```

随后 compare 使用 `metadata.error_type` 与 clean 值 `ok`。

每跑必须满足：

- 18-method 精确相等；
- workers=8；
- cache hits=0，且两个 cache 路径不同；
- API attempts ≤1600、tokens ≤4,000,000；
- operational failure ≤5%；
- LLM-derived confirmed=0；
- 200 个 manifest item 均进入报告。

run 1 失败则 run 2 不启动。run 2 失败则不产生 pair 解释。

## 4. 冻结指标与解释

与 V1 §4、§6 完全相同：

- substantive item Jaccard；
- finding key `(item_id, detection_method, defect_type)` 的 violation Jaccard；
- 逐 method Jaccard；
- 两次 `substantive_only.candidate` P/R/F1 及绝对差。

解释仍以同日 SVAMP 的 violation-Jaccard `0.845` 与 F1 极差 `0.046` 为参照：

- Jaccard >0.845 且 F1 差 <0.046：支持“本 MMLU pair 更稳定”；
- 两项均反向：不支持；
- 一好一坏或等于边界：`INCONCLUSIVE_MIXED_METRICS`。

不得追加第三跑，不得把 V1 不完整 run 并入 V2。

## 5. 预算

历史 18-method 完整运行使用 1263 attempts、约 2.92M tokens。V2 预期两次约 ¥7：

| 项 | 上限 |
|---|---:|
| 单跑 attempts | 1600 |
| 单跑 tokens | 4,000,000 |
| 两跑 tokens | 8,000,000 |
| 两跑费用 | 预期约 ¥7，硬上限 ¥12 |
| 实验级补跑 | **0 次** |

传输层 retry 只允许配置内单请求 retry；一个实验槽位失败后不得重新开一份 cache 充当同一 run。

## 6. 提交纪律

1. V2 协议与配置先提交；
2. V2 runner 与构造测试另提交；
3. 在固定 runner commit 的全新 detached clone 执行；
4. 不修改 V1 protocol、V1 stop receipt、历史 mmlu200 report 或 comparison；
5. 全部新产物进入独立 `mmlu200_replication_pair_v2_20260802` 目录并哈希。
