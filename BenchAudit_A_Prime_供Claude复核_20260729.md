# BenchAudit Workspace A′：供 Claude 独立红队复核

> 日期：2026-07-29  
> 目标：检查“结构化 A′ 拒绝路由”代码、实验协议与负结果是否真实可靠。  
> 复核原则：不要根据本报告替实现辩护；请从代码行为、冻结数据和原始产物
> 独立重算。  
> **禁止调用任何外部 API。** 本次复核只需要本地代码、缓存和结果文件。

---

## 一、请先给最终裁决

请在复核报告开头给出以下一种结论：

1. **通过**：代码安全边界、实验协议、指标和结论均成立；
2. **有条件通过**：主结论成立，但存在不改变结论的实现或表述问题；
3. **不通过**：发现会改变主要指标、停止裁决或 review-only 安全承诺的问题。

每个问题请标注：

- 严重程度：阻断 / 高 / 中 / 低 / 说明；
- 是否影响已报告数字；
- 是否影响“停止、不运行 internal validation”的裁决；
- 最小复现；
- 推荐修法。

---

# 二、代码位置与版本

工作树：

```text
/tmp/benchaudit-workspace-static-llm-20260728
```

分支：

```text
research/workspace-a-prime-rejection-20260729
```

A′ 阶段的三个提交：

```text
449b6cb freeze Workspace A-prime development protocol
35c1714 add structured Workspace A-prime router
72f7001 report Workspace A-prime calibration failure
```

本阶段开始前的基线提交：

```text
45156a2 clarify Workspace holdout metric scope
```

建议先检查：

```bash
cd /tmp/benchaudit-workspace-static-llm-20260728
git status --short --branch
git log --oneline -8
git diff --stat 45156a2..72f7001
git diff --check 45156a2..72f7001
```

请确认 A′ diff 中没有：

- API key、token、`.env`；
- `/home/zhoujun` 等本地路径写进主库逻辑；
- 大型 cache、原始模型响应、artifact 文件；
- 与本实验无关的功能改动；
- 修改第三份 holdout 的结果或标签。

---

# 三、研究问题和停止规则

第三份 task-disjoint holdout 发现旧 A（`hidden_constraint`）路由了
424/575 条 rubric，candidate rate 为 73.7%。这个数字只是逐候选 verifier
成本代理，不等同于真实端到端调用削减。

A′ 阶段只研究：

> 能否通过 reason code、证据来源、置信度和 `do_not_route`，在旧开发数据
> 上保持 grounding-family recall，同时降低 candidate rate？

本阶段明确不是新的泛化实验。

冻结协议：

```text
experiments/workspace_grounding/A_PRIME_DEV_PROTOCOL_20260729.md
```

冻结划分：

```text
experiments/workspace_grounding/A_PRIME_DEV_SPLIT_20260729.json
experiments/workspace_grounding/A_PRIME_CALIBRATION_20_20260729.json
experiments/workspace_grounding/A_PRIME_INTERNAL_VALIDATION_10_20260729.json
```

数据全部来自已经使用过的：

```text
experiments/workspace_grounding/DUAL_TRIAGE_HOLDOUT_30_20260728.json
```

划分方式：

- calibration：20 task，其中 10 个含 grounding positive；
- internal validation：10 task，其中 5 个含 grounding positive；
- 两部分 task 完全不重叠；
- 第三份 task-disjoint holdout 不属于这 30 个开发 task。

Calibration 的预注册 go gate：

- grounding-family recall ≥ 0.90；
- candidate rate ≤ 0.40；
- review ceiling escape = 0；
- operational unknown task = 0。

只允许从以下阈值选择工作点：

```text
0.50 / 0.60 / 0.70 / 0.80 / 0.90
```

未通过 calibration 时：

- 不运行 10 个 internal-validation task；
- 不生成第四份 holdout；
- 不追加第二模型、第二视角或 verifier；
- 不修改 reason taxonomy 后继续冒充同一次预注册实验。

---

# 四、A′ 具体实现

## 4.1 模型输出 schema

核心代码：

```text
benchcore/workspace_grounding.py
```

新增 prompt：

```python
ITEM_STRUCTURED_TRIAGE_PROMPT
```

模型必须为每条 rubric 返回：

```json
{
  "rubric_index": 0,
  "action": "route|do_not_route",
  "reason_code": "...",
  "evidence_source": "task|output_contract|input_inventory|input|intrinsic|none",
  "confidence": 0.0,
  "brief_reason": "...",
  "evidence_quote": "..."
}
```

允许路由的 reason code：

```text
unsupported_exact_constraint
task_rubric_contradiction
unsupported_prescriptive_content
input_evidence_contradiction
underdetermined_requirement
```

强制拒绝的 reason code：

```text
task_supported
output_contract_supported
input_supported
mechanically_derivable
intrinsic_validity
general_quality
artifact_satisfaction_only
uncertain_no_specific_gap
```

## 4.2 Fail-closed parser

函数：

```python
_indexed_structured_triage_decisions
```

声称的行为：

1. 必须覆盖请求中的每一个 rubric index；
2. 缺行、重复 index、越界 index、未知 code、非法 confidence 均使整个
   task 的 structured view 失败；
3. 缺失行不能被当作 `do_not_route`；
4. `action=route` 但 reason code 属拒绝类时，本地 policy 强制拒绝；
5. 模型不能只改 action 绕过 reason-code allowlist；
6. 原始结构化结果保留在
   `scanner["structured_route"]`，供离线阈值重放。

请重点构造对抗测试：

- 重复 index；
- 少一行；
- 多一行；
- `True` 作为 confidence；
- `NaN/Inf` confidence；
- 大小写和空白变体；
- 未知 reason code；
- `route + general_quality`；
- `do_not_route + unsupported_exact_constraint`；
- 模型输出合法但 evidence quote 伪造。

最后一项目前不应获得任何证明权限，因为 routing 本身始终 review-only。

## 4.3 窄确定性拒绝

函数：

```python
deterministic_structured_rejection
```

目前只处理：

- 纯 general quality；
- 纯 intrinsic file validity。

如果 rubric 包含引号、反引号、数字、exact/title/section/column/order/include
等具体内容 marker，则不得使用该捷径。

已报告的离线结果：

- 在 26 条 P1 grounding-family positive 上：0 条被确定性拒绝；
- 在 dual-triage 30 task 全部 rubric 上：
  - general quality：13；
  - intrinsic validity：5。

请独立重算，尤其检查：

- regex 是否会误拒混合 rubric；
- 中英文/全角标点是否形成漏网或误判；
- `include`、`contain` 等 marker 是否过宽；
- 一个 rubric 同时包含 general quality 和 hidden exact clause 时是否一定
  禁止短路。

## 4.4 Review-only 安全边界

策略名称：

```text
item-structured-triage
```

运行参数：

```text
--grounding-routing-only
--structured-min-confidence 0.0
```

重要逻辑：

- calibration 时使用阈值 0.0 保存所有 model-route 结果；
- 最终 0.5–0.9 阈值由离线分析器重放；
- verifier 关闭；
- routing decision 只保存用于测量；
- `WorkspaceRubricGroundingChecker.check()` 遇到
  `routing_only=True && verifier is None` 时不得发射 semantic finding；
- operational failure 可以发射 operational review finding；
- confirmed 永远不可达。

请尝试证明或推翻：

1. A′ 路由能否绕过 checker 直接产生 `task_rubric_mismatch`；
2. 改 strategy 名是否会影响 ceiling；
3. 合法 structured route 是否可能被误当 verifier verdict；
4. operational failure 是否会被静默当 clean；
5. future caller 打开 verifier 后，是否仍然只由 verifier 决定 substantive
   finding。

---

# 五、统一成本公式

冻结公式：

```text
logical_calls = task_router_calls + routed_candidate_verifier_calls
```

定义：

- 每个实际需要语义 router 的 task 计一次 router logical call；
- 每个 routed rubric 假设后接一次 isolated verifier；
- Exact 等确定性代码计 0 次 LLM logical call；
- provider retry 单独报告；
- cache hit 仍是 logical call，但 API attempt 为 0。

分析器：

```text
scripts/analyze_workspace_a_prime.py
```

请检查：

- dual-triage 的旧产物含两个 view，但旧 A 基线是否只计一次 A router call；
- objective resolver 全短路的 task 是否被错误计费；
- candidate 是否按唯一 `(item_id, rubric_index)` 去重；
- logical-call reduction 是否使用同一分母；
- candidate rate 是否只被表述为成本代理；
- reviewed TP 是否按 rubric 计数；
- task hit 与 rubric hit 是否混用。

---

# 六、真实 API 运行

配置：

```text
configs/llm_deepseek_workspace_a_prime_dev.json
```

运行产物：

```text
/home/zhoujun/llmdata/after623/reports/
workspace_grounding_a_prime_calibration_20260729/
```

本次真实运行声称：

| 项目 | 数值 |
|---|---:|
| task | 20 |
| rubric | 405 |
| API attempts | 20 |
| API success | 20 |
| API failure / retry | 0 |
| prompt tokens | 126,647 |
| completion tokens | 35,971 |
| total tokens | 162,618 |
| verifier calls | 0 |
| findings | 0 |
| operational unknown | 0 |

原始产物哈希：

```text
decisions
689fad58c3947109b3547561681d3fa258ecbc7ded9ec94cfb7751d2ec061c1a

cache
53740726724c1a58e200245a3795ca243c2573ec49aa1ce838b1f7d7b39fc6e4

runtime
8f307d1d906cc8729462405bb4667cada0f90236c9984c53ade213f182ceee63

analysis
fee5a065173851bb5597af5994e3beee9408bf40aaa0b9d62854d617d5434147
```

请执行：

```bash
sha256sum \
  /home/zhoujun/llmdata/after623/reports/workspace_grounding_a_prime_calibration_20260729/grounding_item_structured_triage_items.jsonl \
  /home/zhoujun/llmdata/after623/reports/workspace_grounding_a_prime_calibration_20260729/grounding_item_structured_triage_cache.jsonl \
  /home/zhoujun/llmdata/after623/reports/workspace_grounding_a_prime_calibration_20260729/runtime.json \
  /home/zhoujun/llmdata/after623/reports/workspace_grounding_a_prime_calibration_20260729/analysis.json
```

不要重新发 API。若要复跑分析，只运行本地 analyzer。

---

# 七、请独立重算的主要结果

已有 family label：

```text
/home/zhoujun/llmdata/after623/reports/workspace_p1_family_reference_20260728/
SEALED_MAPPING.json

/home/zhoujun/llmdata/after623/reports/workspace_p1_family_reference_20260728/
GEMINI_3_1_PRO_FAMILY_ANNOTATIONS.jsonl
```

既有 reviewed reference：

```text
/home/zhoujun/llmdata/after623/
WorkspaceBench_full388_Codex证据化逐条标注_20260720.md
```

旧 A baseline：

```text
/home/zhoujun/llmdata/after623/reports/
workspace_grounding_dual_triage_holdout30_20260728/
grounding_dual_triage_items.jsonl
```

本地重算命令：

```bash
cd /tmp/benchaudit-workspace-static-llm-20260728

python scripts/analyze_workspace_a_prime.py \
  --structured-results \
  /home/zhoujun/llmdata/after623/reports/workspace_grounding_a_prime_calibration_20260729/grounding_item_structured_triage_items.jsonl \
  --baseline-results \
  /home/zhoujun/llmdata/after623/reports/workspace_grounding_dual_triage_holdout30_20260728/grounding_dual_triage_items.jsonl \
  --partition-manifest \
  experiments/workspace_grounding/A_PRIME_CALIBRATION_20_20260729.json \
  --reviewed-reference \
  /home/zhoujun/llmdata/after623/WorkspaceBench_full388_Codex证据化逐条标注_20260720.md \
  --family-mapping \
  /home/zhoujun/llmdata/after623/reports/workspace_p1_family_reference_20260728/SEALED_MAPPING.json \
  --family-annotations \
  /home/zhoujun/llmdata/after623/reports/workspace_p1_family_reference_20260728/GEMINI_3_1_PRO_FAMILY_ANNOTATIONS.jsonl \
  --output /tmp/claude_a_prime_analysis.json
```

需要核验的数字：

| 方法 | Candidate rate | Family recall | Reviewed P | Reviewed R | Reviewed F1 | Logical calls |
|---|---:|---:|---:|---:|---:|---:|
| 旧 A | 52.1% | 84.2% | 0.850 | 0.810 | 0.829 | 231 |
| A′ | 46.4% | 63.2% | 0.812 | 0.619 | 0.703 | 208 |

具体计数：

- 旧 A candidates：211/405；
- A′ candidates：188/405；
- family positives：19；
- 旧 A family hits：16；
- A′ family hits：12；
- reviewed universe：28；
- A′ reviewed TP/FP：13/3；
- A′ logical-call reduction vs A：约 10.0%。

五个 threshold 的候选集声称完全一致：

```text
0.50 -> 188
0.60 -> 188
0.70 -> 188
0.80 -> 188
0.90 -> 188
```

置信度分布：

```text
1.00: 273
0.95: 40
0.90: 75
0.80: 17
```

因此 calibration gate 未通过。

---

# 八、七条漏检和核心解释

A′ 漏掉 7 条 family-grounding positive：

```text
workspacebench-130 / rubric 19
workspacebench-157 / rubric 10
workspacebench-196 / rubric 7
workspacebench-49  / rubric 18
workspacebench-9   / rubric 2
workspacebench-9   / rubric 8
workspacebench-9   / rubric 9
```

当前解释是：

> A′ 将“这种设计合理 / 输入中有相关素材”误认为“task 明确授权了 rubric
> 的精确设计或汇总口径”。

例子：

- “生成可视化图表”不等于指定 bar / pie / donut chart；
- “提供建议”不等于指定五类建议；
- “合并 panel 文件”不等于第一张必须来自 panel A；
- 输入中有十条意见，不等于 rubric 指定的汇总方式已被授权。

请逐条回到 task、rubric 和结构化 route 判断：

1. P1 family label 是否确实为 grounding positive；
2. A′ 是否确实 `do_not_route`；
3. 模型引用的 evidence 是否支持“精确要求”，还是只支持宽泛父任务；
4. 是否存在 family reference 本身判错的可能；
5. 是否存在 rubric index 对齐错误。

---

# 九、Exact 诊断的特殊说明

报告中还有一次**零 API、探索性** Exact 并集诊断：

- Exact 选 9 条；
- 相对 A′ 新增 3 条；
- A′ + Exact candidate rate 为 47.2%；
- 恢复 0/7 条 family-positive 漏检。

这不是预注册主指标，也没有改变 calibration FAIL。

该临时诊断调用 `route_exact_constraints` 时使用了 task + output contract，
`allowed_input_evidence=""`，没有重新构建完整 input evidence bundle。

请重点审查：

- 缺少 input evidence 是否可能使“恢复 0/7”的结论不成立；
- 对当前 Exact 算法而言，增加允许输入证据是否只会减少 unmatched literal，
  还是也可能新增 route；
- 如果该诊断不可解释，请要求从正式报告删除，而不是替它补造正结论。

无论 Exact 诊断是否成立，A′ 自身 calibration FAIL 都不依赖这项诊断。

---

# 十、请验证没有偷跑 internal validation

内部验证 manifest：

```text
experiments/workspace_grounding/A_PRIME_INTERNAL_VALIDATION_10_20260729.json
```

声称：

- 没有为这 10 个 task 发起 A′ API；
- 没有 internal-validation cache；
- 没有 internal-validation result；
- 没有根据这 10 个 task 修改 prompt、reason code 或阈值；
- 没有第四份 holdout。

请搜索：

```bash
find /home/zhoujun/llmdata/after623/reports \
  -maxdepth 2 -type f | rg 'a_prime|internal_validation|fourth_holdout'

rg -n 'workspacebench-(34|156|189|191|158|220|190|186|144|63)' \
  /home/zhoujun/llmdata/after623/reports/workspace_grounding_a_prime_calibration_20260729
```

第二条应无命中。

---

# 十一、测试

请独立运行：

```bash
cd /tmp/benchaudit-workspace-static-llm-20260728

pytest -q \
  tests/test_workspace_grounding.py \
  tests/test_workspace_static_llm_ablation.py \
  tests/test_workspace_a_prime.py

pytest -q
```

当前声称：

```text
定向测试：50 passed
全量测试：778 passed
```

请注意测试数量可能因其他分支更新变化；重点是零失败，不要只对数字。

---

# 十二、我希望 Claude 特别攻击的地方

1. **Parser 完整性**  
   是否真的能把缺行、重复行和未知 code 全部变成 operational unknown？

2. **拒绝权限是否过强**  
   LLM 的 `task_supported/input_supported` 是否被错误当成可靠 clean 证据？

3. **确定性规则是否真高精度**  
   regex 会不会在混合 rubric 上吞掉 hidden exact clause？

4. **阈值重放是否诚实**  
   calibration 使用 0.0 运行、离线使用 0.5–0.9 是否会产生口径错位？

5. **Family 标签对齐**  
   mapping、blind ID、item ID、rubric index 是否有一处错位？

6. **成本公式**  
   dual baseline 的两视角数据是否被错误计成一个或两个 A call？

7. **Reference selection bias**  
   reviewed precision 是否始终被限定为“已有标签上的条件指标”？

8. **停止纪律**  
   calibration FAIL 后是否真的没有偷跑 internal validation？

9. **第三份 holdout 泄漏**  
   A′ 实现、threshold 或 reason code 是否读取/拟合了第三份 holdout 的逐例
   结果，而不只是使用其聚合结论发现“候选率过高”？

10. **代码复杂度**  
    943 行新增是否过度；哪些结构可在不改变行为的情况下缩小？

---

# 十三、期望的 Claude 输出格式

```markdown
# A′ 独立红队复核

## 最终裁决
通过 / 有条件通过 / 不通过

## 独立复现结果
- git / diff
- tests
- hashes
- metrics
- API / token / verifier / finding counts

## Claim-by-claim 核验表
| Claim | 核验结果 | 独立证据 |

## 发现的问题
### [严重度] 问题名称
- 最小复现
- 根因
- 是否影响数字
- 是否影响停止裁决
- 推荐修法

## 七条漏检逐例裁决

## Exact 临时诊断是否可保留

## Internal validation 未运行证明

## 是否允许合并
```

请不要因为本轮结果是负数就降低审查强度。负结果只有在协议、分母、标签、
成本和停止纪律都成立时才有研究价值。
