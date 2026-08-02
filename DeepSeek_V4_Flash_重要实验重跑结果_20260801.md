# DeepSeek V4 Flash 重要实验重跑结果

日期：2026-08-01

## 总结

当前 `deepseek-v4-flash` 服务**不值得替换 7 月最佳参考结果**，也没有足够
证据继续支付约 69 元运行 Workspace full388。

本轮显式固定 thinking disabled、temperature 0、全新 cache；累计 9,806 次
API attempts，保守总成本不超过 **24.679 元**。所有 LLM finding 仍为
review-only，confirmed escape 为 0。

注意：若干 7 月产物本身已经使用 `deepseek-v4-flash`。后续零 API 归因复核
证明，SVAMP 与两组 Workspace 差异主要发生在模型响应层；MMLU 的旧新实验
合同不一致，不能归因给模型服务或代码中的任何单一因素。

## 2026-08-01 归因更正

不能把所有下降统称为“当前服务退化”，也不能统称为“代码回归”。零 API
旧响应回放给出的结论如下：

| 实验 | 旧响应 + 当前代码 | 归因结论 |
|---|---|---|
| SVAMP100 | 33/17/5、F1 0.750，与历史逐项一致 | 当前审计代码未造成 0.750→0.707；新鲜模型响应不同 |
| Workspace A-prime | `analysis.json` SHA-256 与历史完全相同；188、12/19、F1 0.703 | 当前后处理代码未造成下降 |
| Workspace 第三 holdout | 424、26/13/6、F1 0.732 全部复现 | 当前后处理代码未造成差异 |
| MMLU1000 | 历史 cache 对当前请求 0 命中 | 旧新合同不可比，无法单因归因 |

MMLU 旧报告使用独立冻结的 1000 题文件、`thinking=null`，且记录为 dirty
worktree；新报告使用全量源文件加 manifest、显式 `thinking=disabled`。虽然
两批 item ID 与原始 JSON 1000/1000 一致，但代码演化改变了实际请求键，旧
cache 无法在当前流水线上重放。因此下文 MMLU 差值只能作为“两个系统快照的
观测差”，不得再称为严格可比的模型质量差。

归因复核还发现：普通 CLI 的 `load_llm_config()` 未读取 JSON 中的
`cache_only` 字段。诊断时在发现 cache 增长后立即中断，但已产生 123 次额外
调用；这些响应未用于任何结论。按本轮平均成本保守估计额外成本不超过约
0.6 元。该问题应作为独立实现缺陷修复和测试，而不是混入模型效果结论。

## 主要结果

### SVAMP100

| 系统 | P | R | F1 | TP/FP/FN |
|---|---:|---:|---:|---:|
| Rules-only | 0.000 | 0.000 | 0.000 | 0/0/38 |
| Naive LLM | 0.750 | 0.632 | 0.686 | 24/8/14 |
| LLM + taxonomy | 0.625 | 0.658 | 0.641 | 25/15/13 |
| BenchAudit 分解式审计 | 0.659 | 0.763 | 0.707 | 29/15/9 |

BenchAudit 仍优于单次判断基线，但相对 7 月 30 日同一 manifest 的主线结果，
F1 从 0.750 降至 0.707，recall 从 0.868 降至 0.763。

### MMLU-Redux

纠正后的 pilot200 为 P/R/F1 = 0.761/0.700/0.729，通过运营和成本门控。

| full1000 | P | R | F1 | TP/FP/FN |
|---|---:|---:|---:|---:|
| 7 月原始报告、同版 compare 重算 | 0.696 | 0.749 | 0.721 | 277/121/93 |
| 2026-08-01 当前服务 | 0.675 | 0.641 | 0.657 | 237/114/133 |

观测差值为 F1 -0.064，主要是 recall -0.108；由于输入运行合同、thinking
设置和请求键不一致，这不是严格可比差值。MMLU1000 成本约 15.709 元，比旧
token 结构按当前价格估算低约 17%，但本轮不能据此判断模型质量是否提升。

排名影响离线重算中，全局 Kendall tau 仍为 0.981；审计器对第三方
objective labels 的 F1 从 0.553 降到 0.508。

### Workspace A-prime calibration20

| 指标 | 7 月 | 本轮 |
|---|---:|---:|
| candidates | 188/405 | 96/405 |
| family recall | 12/19 | 10/19 |
| reviewed P/R/F1 | 0.812/0.619/0.703 | 0.714/0.476/0.571 |

候选量减少不是 Pareto 改进：召回和 F1 同时下降，并出现 1 个 operational
unknown task，`calibration_go=false`。

### Workspace 第三 holdout30

| 指标 | 7 月 | 本轮 |
|---|---:|---:|
| reviewed P/R/F1 | 0.667/0.812/0.732 | 0.651/0.875/0.747 |
| A candidates | 424/575 | 470/575 |
| Exact incremental reviewed TP | 0 | 0 |

这是唯一小幅 F1 增量（+0.015），但以 46 条额外候选为代价；Exact 的核心
预注册门仍 FAIL，因此不足以放行 full388。

## 成本与停止裁决

| 实验组 | 保守成本 |
|---|---:|
| canary + SVAMP + 两个直接基线 | ≤1.994 元 |
| MMLU200 配置错误臂 + 可比臂 | 6.600 元 |
| MMLU1000 | 15.709 元 |
| Workspace 20 + 30 | 0.376 元 |
| **原重跑总计** | **≤24.679 元** |
| 归因诊断误触发的 123 次调用 | **估计 ≤0.600 元** |
| **含归因诊断的总计** | **估计 ≤25.279 元** |

full388 按预注册 Gate 4 停止，避免继续花约 69 元。静态 replay、execution
proof、APPS confirmation contract、trace 与 released-result gate 是模型无关
能力，没有重复调用 API。

## 版本与产物

- 主实验分支：`research/deepseek-v4-flash-rerun-20260801`，HEAD `d705f9b`；
- Workspace 分支：`research/deepseek-v4-flash-workspace-rerun-20260801`，HEAD `1dc42fc`；
- 主原始产物：`/home/zhoujun/llmdata/after623/reports/deepseek_v4_flash_rerun_20260801/`；
- Workspace 原始产物：`/home/zhoujun/llmdata/after623/reports/deepseek_v4_flash_workspace_rerun_20260801/`。

完整版本化报告位于主实验分支：
`docs/DEEPSEEK_V4_FLASH_IMPORTANT_RERUN_RESULTS_20260801.md`。

GitHub 推送因当前环境缺少有效凭据而失败；两个本地分支和提交均保留，
工作树干净。原始大报告/cache 未提交进 Git，但完整 SHA-256 已记录在版本化
报告中。
