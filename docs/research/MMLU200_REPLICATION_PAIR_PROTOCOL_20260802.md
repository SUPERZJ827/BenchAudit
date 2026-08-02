# MMLU-200 同配置独立复现对协议

> 日期：2026-08-02  
> 状态：**frozen before any paid API request**  
> 目的：回答 MMLU-Redux 的 LLM 审计输出是否比同日 SVAMP 重复运行更稳定  
> 授权：用户已批准使用最新 `deepseek-v4-flash` 重跑重要实验；本对预期约 ¥6，硬预算 ¥10

## 0. 待回答的问题与边界

在代码、输入、抽样、方法集、模型、提示、配置和并发度全部固定时，两次独立 MMLU-200 审计的 item、finding 与候选层指标有多大差异？

本实验只测量仪器重复性，不比较模型优劣，不定位单条 benchmark 缺陷，不把一次运行的输出当作另一运行的缓存，也不把旧的 `mmlu200` 与 `mmlu200_comparable` 合并为复现对。旧两份报告的方法集分别为 21 与 18，因而不可比。

## 1. 冻结输入与实现

| 项 | 冻结值 |
|---|---|
| 代码基线 | `39c962022079cc28ac5e0ce7a93ef4ea47d24649` |
| 数据 | `/home/zhoujun/llmdata/datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl` |
| 数据 SHA-256 | `0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4` |
| manifest | `experiments/mmlu_redux_pilot200.manifest.json` |
| manifest SHA-256 | `f60757deeb3f8ba6a682575fd7a87573999b8f0004894729f4904c189f6d77e1` |
| 样本 | 200 条；100 clean、100 defect；seed `20260624` |
| 模型配置 | `configs/llm_deepseek_mmlu200_replication_20260802.json` |
| 配置 SHA-256 | `0bb50a1316370c39541e2d3e7d9cffd21bddc2eaab4bfc48de905a8f64695e6c` |
| 模型 | `deepseek-v4-flash` |
| temperature | `0.0` |
| thinking | `disabled` |
| max_tokens | `5000` |
| votes | `1` |
| gold evidence | `cascade` |
| workers | **8，必须写入 run_metadata** |
| 运行数 | **2，严格串行** |
| 缓存 | 每次各自一个运行前不存在的空缓存；禁止跨运行复用 |
| 远端传输 | 显式 `--allow-remote-data-egress`；通过 `http://127.0.0.1:17890` CONNECT 到 `api.deepseek.com:443` |

代理只改变传输路径，不进入 LLM cache key。配置在运行前已通过无模型调用的连接预飞：TLS CONNECT 后请求 `/` 得到 HTTP 401；该结果只证明连通性，不是模型输出。

## 2. 冻结方法集

运行前 dry-run 在上述数据和 manifest 上导出以下 **21 个方法**。两次报告的 `methods_run` 必须与该列表逐项、逐序相同；仅“同一条命令”不构成充分保证。

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
16. `llm_presentation_integrity`
17. `llm_quantity_consistency`
18. `llm_event_state`
19. `duplicate_conflict`
20. `schema_drift`
21. `choice_encoding_contract`

任一运行的方法集不符即停止，不以删方法、补跑或事后取交集修正。

## 3. 执行与完整性门

每次运行均直接调用 `python -m benchcore.cli audit`，参数固定为：

```text
--manifest experiments/mmlu_redux_pilot200.manifest.json
--llm-audit --llm-auditors all
--gold-evidence-mode cascade
--llm-config configs/llm_deepseek_mmlu200_replication_20260802.json
--workers 8 --progress-every 10
--allow-remote-data-egress --print-summary
```

随后以 `metadata.error_type` 为真值字段、`ok` 为 clean 值运行 `benchcore.cli compare`。

运行器必须在每次启动前确认相应 report、comparison 与 cache 均不存在；运行后确认：

- `methods_run` 精确等于 §2；
- `run_metadata.workers == 8`；
- 模型、temperature、thinking、max_tokens、votes 与 §1 相同；
- cache 起始为空，本次不允许使用前一运行的 cache；
- API attempts 与 token 使用被记录；
- 未出现 LLM 派生 confirmed。

第一次未通过完整性门时，不启动第二次。

## 4. 冻结度量口径

本节复用 `SVAMP_REPLICATION_N5_PROTOCOL_20260802.md` §2 的口径，不在运行后增删指标：

1. 预测 item：至少有一条 `defect_scope != "presentation"` 的 violation；
2. finding 身份键：`(item_id, detection_method, defect_type)`，并排除 presentation；
3. item Jaccard：两次预测 item 集的 `|A∩B| / |A∪B|`；
4. violation Jaccard：两次 finding 键集合的 Jaccard；
5. 逐 method 复现率：按 detection method 分组的 finding 集 Jaccard，报告每个方法以及 min/median/max；
6. 候选层 P/R/F1：读取 comparison 的 `substantive_only.candidate`，分别报告两次值及绝对差。

空集与空集的 Jaccard 定义为 `1.0`；仅一侧为空定义为 `0.0`。

## 5. 预算与停止条件

| 项 | 预期 / 上限 |
|---|---|
| 单次费用 | 约 ¥3 |
| 总费用 | 约 ¥6；硬上限 ¥10 |
| 单次 API attempts | ≤ 1400 |
| 单次 provider tokens | ≤ 4,000,000 |
| 两次 provider tokens | ≤ 8,000,000 |

出现任一情况立即停止剩余运行并报告，不调整参数重试实验：

1. operational failure 比例 > 5%；
2. 出现任何 LLM 派生 confirmed；
3. 单次或累计 token 超过上述上限；
4. 方法集、输入哈希、manifest 哈希、配置哈希或 workers 不符；
5. 传输层持续故障导致结果不完整。

## 6. 预注册解释

同日 SVAMP n=5 的已观测噪声基准为 violation-Jaccard 中心值约 `0.845`、F1 极差 `0.046`。本实验只有一个 pair，因此结论限定为：

- MMLU violation Jaccard **> 0.845** 且 F1 绝对差 **< 0.046**：本复现对支持“MMLU 在本条件下比 SVAMP 基准更稳定”；
- 两项均反向：不支持该判断；
- 一项更好、一项更差或恰等于阈值：`INCONCLUSIVE_MIXED_METRICS`。

无论结果如何，不追加第三次，不切到 MMLU-1000；如需扩大样本或运行数，必须另冻协议。

## 7. 提交与运行纪律

1. 本协议先提交；
2. 运行器及其构造测试后提交；
3. 在固定运行器提交的全新独立目录中执行，运行期间该目录保持 detached HEAD；
4. 两次运行严格串行；
5. 原始 report、comparison、cache 与汇总全部保留并哈希；
6. 不修改历史报告，不复用旧缓存，不用结果反向修改本协议。
