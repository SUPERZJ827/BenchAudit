# Workspace grounding A″：internal10 冻结协议

协议版本：`workspace-grounding-a-double-prime-internal10-v1-20260729`

## 0. 目的与纪律

本实验只回答：

> 在没有参与 R2a–R2d 设计、也没有运行过 A′ 的 10 个冻结 task 上，
> 固定工作点 R2c+R2d 能否恢复至少 6/7 条已知 grounding positive，
> 同时不超过旧 A 在同一批 task 上的候选成本？

本实验不重新选择规则，不修改 A′ prompt、reason taxonomy、词表、解析器、
阈值或 tie-break。internal10 的 item ID 只用于执行与计量，不得用于规则
开发。

允许的结局只有 PASS 或 FAIL。API、provider 或解析失败记为 operational
unknown；不得追加模型、重试实验、切换到 R2a+R2d，或据 internal10 结果
修改规则后再次声称同一批数据为验证集。

## 1. 冻结工作点

- A′ 本地阈值：`0.50`；
- A″ 规则并集：`R2c + R2d`；
- 不启用 R2a；
- 不启用 R2b；
- 不重新运行 15 组合 tie-break；
- 所有 residue observation 保持 `review_only=True` 且
  `confirmation_eligible=False`。

开发集选择 R2c+R2d 的提交与结果报告：

- 实现：`7bad3b2`；
- calibration 分析：
  `235a710fb5b3e62a1c86873f6ff6838f60f3f21ecd19d60e75d1c69383d8e7f1`；
- 修订后结果报告：
  `09fb2be5b0fecb5d7dda3572b170324691a578a16d53ef4eda8b2e49f83f3b21`。

## 2. 冻结输入

### 2.1 仓库输入

| 文件 | SHA256 |
|---|---|
| `experiments/workspace_grounding/A_PRIME_INTERNAL_VALIDATION_10_20260729.json` | `8af94ea6a23663654bec21e115928f6a7d5b30b86d1912e6992e9a5d24325515` |
| `configs/llm_deepseek_workspace_a_prime_internal_validation.json` | `f6542eb4dd7c326f22c5fe109575258b8ba48f57a75493a66ddc0861948bad86` |
| `benchcore/workspace_constraint_residue.py` | `aa0f09461a0414466259d9f37e5512c9226c5918578f5b167159dc84411c0b34` |
| `benchcore/workspace_grounding.py` | `0f64ce1d7050b16f0596c2e4cae2772b380b6ebb6337dd983d1b4c9fa126592a` |
| `scripts/run_workspace_static_llm_ablation.py` | `e941aa57953a693d94d9be12844a66fa45c6aa6bc753dc01ca17cc972b3566e2` |

### 2.2 外部 artifact-root 输入

`--artifact-root` 冻结为
`/home/zhoujun/llmdata/after623`。该绝对路径只属于实验记录，不得写入
库代码。

| 相对路径 | SHA256 |
|---|---|
| `datasets/workspacebench/full.jsonl` | `2e3d8fd1f5a741b9e6b73ebab9ce23e26ce054527b4f3477de8fdd950aad9dbe` |
| `reports/workspace_grounding_dual_triage_holdout30_20260728/grounding_dual_triage_items.jsonl` | `2562ca10533e8f1a0a87080eed306fcf19389039ed7172ac7f04c1c197f9a50e` |
| `WorkspaceBench_full388_Codex证据化逐条标注_20260720.md` | `fa8fbef8497ac2f8f39b21975e28dd88005a5d2541db07cbe162fb04558978cf` |
| `reports/workspace_p0_blind_adjudication_20260728/SEALED_MAPPING.json` | `18232ed0e0e65e9215dd51c857c34b560512d59be51d74b89b1c3efad4619ee9` |
| `reports/workspace_p0_blind_adjudication_20260728/GEMINI_3_1_PRO_INDEPENDENT_ANNOTATIONS.jsonl` | `b091fae11b9ecbd2bffc826c4cf60615e15c39357b700abdf3c9510daa3b8e62` |

缺文件或任一哈希不匹配必须在 API 调用前 fail-closed。

## 3. 运行与成本上限

只运行 A′ 的 task-level structured router，不运行 isolated verifier：

- 模型：`deepseek-v4-flash`；
- temperature：0；
- thinking：disabled；
- task router logical calls：10；
- API attempts 硬上限：10；
- observed-token 软停止线：200,000；
- workers：最多 4；
- provider retry：0；
- 第二模型/第二视角：禁止；
- verifier API calls：0。

calibration 的观察均值约为每个 task 8,131 total tokens，因此本轮预期约
81,000 total tokens；该值只用于成本预警，200,000 才是机器停止线。

输出目录固定为：

```text
/home/zhoujun/llmdata/after623/reports/
workspace_grounding_a_double_prime_internal10_20260729/
```

## 4. 运行前已冻结的旧 A 基线

旧 A 基线只从已经运行过的 dual-triage 结果中按 internal10 item ID 机械
切片，不读取 internal10 的 A′ 输出：

| 指标 | 冻结值 |
|---|---:|
| task | 10 |
| rubric | 204 |
| 候选 | 118 |
| candidate rate | 57.843% |
| 反事实 logical calls | 128 = 10 + 118 |
| 已知 grounding positive | 7 |
| reviewed universe | 14 |
| reviewed positive | 9 |

旧 A 对 7 条 family positive 的命中为 0；该值只作为历史描述，不降低
A″ 的固定 6/7 recall 门槛。

## 5. PASS/FAIL gate

必须同时满足：

1. family grounding hits ≥ 6/7（recall ≥ 85.7%）；
2. candidate count ≤ 118；
3. candidate rate ≤ 118/204（57.843%）；
4. logical calls ≤ 128；
5. review ceiling escape = 0；
6. operational unknown task = 0；
7. 输出完整覆盖 10 个 task 和 204 条 rubric；
8. 工作点严格为 R2c+R2d。

Reviewed precision/recall/F1、相对旧 A 的成本变化、R2c/R2d 各自触发数和
非目标触发数必须报告，但不构成额外硬门。

## 6. R2c 事前脆弱性预期

在运行前冻结：

- R2c 在 internal10 上预期触发 0–1 次；
- 若触发 0 次，工作点实际等价于 R2d 单独，family recall 很可能低于
  6/7；
- 该情况是正常负结果，不属于 operational failure；
- 不得因此切换组合、补词表、放宽唯一性闸门或再次调用 API。

## 7. 执行顺序

1. 提交并推送本协议；
2. 实现只读 internal10 分析器及测试，独立提交；
3. 在任何 API 调用前校验第 2 节全部哈希；
4. 运行 10 个 task 的 A′ routing-only arm；
5. 冻结原始 decisions/cache/runtime/provenance 哈希；
6. 使用固定 R2c+R2d 做本地 replay；
7. 输出逐项 gate、全部负结果和成本；
8. internal10 FAIL 则停止，不创建第四份 holdout。

