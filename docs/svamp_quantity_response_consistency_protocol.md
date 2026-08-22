# SVAMP 改进 B：quantity 响应自洽性与 claim-scoped 失效协议

- 协议版本：V2 草案
- 制定日期：2026-08-11
- 修订日期：2026-08-20
- 对应方案：《SVAMP 实验复盘与迭代方案（定稿 2026-07-31）》第 5.2 节
- 修订依据：`改进B_降级作用域_复核与建议_20260813.md`、当前真实 extractor 五跑精确复算及五跑完整 quantity cache 覆盖率验证
- 适用模块：`llm_quantity_consistency`
- 开发基线：原型基于 `c6f62ce` 系列代码完成；合入当前主线前须重新验证证据语义和完整测试
- 实现提交：`dd3023b`（由原提交 `c461d29` 移植到最新主线基线）

## 1. 目标

阻止内部不自洽的 `derived_answers` 支撑正式检测候选，同时保留同一响应中由 `checks`、reference issues 或题面结构独立支撑的 claim。

本协议只处理以下已确认问题：

> 同一次 quantity 响应的结构化最终答案 `derived_answers` 与该响应 rationale 中明确给出的最终计算结论不一致。

V2 不处理一般算术错误、数量关系建模错误、题面语义误读或 nonmaterial 证据过滤。V2 只限定失效证据的作用域，不把单个字段的不可信扩大为整条响应无效。

## 2. 固定约束

1. 不修改 quantity prompt，确保现有缓存可复用。
2. 不调用新的 LLM，不调用外部服务。
3. 不使用 gold 判断响应是否内部自洽。
4. 不修改置信度阈值、审计聚合规则或其他 auditor。
5. V2 不重试；重试只允许在第一阶段收益验证通过后另行设计。
6. 内部不自洽时，只阻止依赖 `derived_answers` 的 claim；具有独立证据来源的 claim 不受影响。
7. 无法确定 rationale 最终结论时不得猜测。
8. claim 失效范围只依据证据依赖关系，不依据 gold、`audit_label`、TP/FP 状态或 item ID。

## 3. 输入

判定函数接收 quantity auditor 单次解析后的 `llm_result`，仅使用：

- `solution_status`
- `derived_answers`
- `rationale`
- `checks`（只作为同一响应内部的辅助证据）
- 原题 `task`（只用于确认 rationale 所指的是题目要求的目标数量）

禁止读取：

- `item.gold`
- 数据集 `audit_label`
- 其他 auditor 的判断
- 历史人工裁决标签

## 4. 输出状态

判定函数只允许返回以下三种状态：

| 状态 | 含义 | 后续行为 |
|---|---|---|
| `CONSISTENT` | 成功提取一个 rationale 最终结论，且与唯一 `derived_answers` 数值一致 | 正常进入现有 quantity 检查和 gold 比较流程 |
| `INCONSISTENT` | 成功提取一个 rationale 最终结论，但与唯一 `derived_answers` 数值不一致 | `derived_answers` 字段失效；只阻止依赖该字段的 claim，继续处理独立证据 claim |
| `NOT_IDENTIFIABLE` | 无法唯一、可靠地取得双方数值 | V2 不猜测、不据此使任何 claim 失效，保持现有处理流程 |

`NOT_IDENTIFIABLE` 不代表响应正确，只表示 V2 没有足够的确定性证据证明内部冲突。

## 5. 前置条件

只有同时满足以下条件才尝试比较：

1. `solution_status == "solved"`；
2. `derived_answers` 是列表；
3. `derived_answers` 中恰好能解析出一个唯一、有限的数值；
4. `rationale` 是非空字符串。

任一条件不满足时返回 `NOT_IDENTIFIABLE`。

数值解析复用现有 `parse_number` 语义；比较容差复用当前 gold 数值比较口径 `1e-9`，不得另设可调阈值。

## 6. rationale 最终结论提取规则

### 6.1 允许作为最终结论的证据

V2 只接受与题目所问目标数量明确关联的终结性表述：

1. 明确答案声明：
   - `answer is <number>`
   - `answer should be <number>`
   - `correct/final/derived answer is <number>`
2. 明确自我纠正：
   - `not <old>, ... answer is <new>`
   - `correction ... answer is <new>`
   - 后出现的明确纠正覆盖同一 rationale 中较早的旧答案声明。
3. 明确题目目标声明：
   - `the question/task asks ... which is <number>`
   - `asked difference ... = <number>`
   - 与题目最终疑问目标同名的数量赋值，例如 `disappeared = ... = 4`。
4. 明确最终算式：
   - 表述同时说明这是题目所问的量，并给出只含有限数值和 `+ - * /`、括号的可安全求值算式；
   - 算式结果必须与声明数值一致，否则该表述自身无效，不能用于降级。

### 6.2 不允许作为最终结论的证据

以下内容不得单独用于提取 rationale 最终答案：

1. rationale 中最后出现的任意数字；
2. 未与题目目标关联的中间变量；
3. `checks` 中一般性的库存、可行性或恒等式数值；
4. 只说明正负、大小关系但没有声明最终答案的数值；
5. 含未替换变量、无法安全求值或语义指向不明的表达式；
6. 多个互相冲突、且不存在明确后续纠正关系的答案声明；
7. 需要常识猜测、语义补全或再次调用 LLM 才能解释的表述。

### 6.3 唯一性规则

提取完成后：

- 没有有效最终结论：`NOT_IDENTIFIABLE`；
- 存在多个不同结论且无法由明确纠正顺序消解：`NOT_IDENTIFIABLE`；
- 明确纠正后的最终有效结论唯一：进入数值比较。

## 7. 数值比较

设：

- `D` 为唯一解析后的 `derived_answers` 数值；
- `R` 为唯一提取的 rationale 最终结论数值。

判定：

```text
abs(D - R) <= 1e-9  => CONSISTENT
abs(D - R) >  1e-9  => INCONSISTENT
```

比较不读取 gold。即使 `D` 与 `R` 一致但二者都算错，也必须返回 `CONSISTENT`，让现有 wrong-gold 检查正常保留该候选。

## 8. `INCONSISTENT` 的 claim-scoped 失效行为

当状态为 `INCONSISTENT`：

1. 只将当前响应的 `derived_answers` 标记为不可信，不将整条 quantity 响应标记为无效；
2. 禁止生成证据依赖 `derived_answers` 的 claim；
3. V2 当前确认的依赖映射仅为：

   ```python
   DERIVED_ANSWER_CLAIMS = {"wrong_gold_answer"}
   ```

4. 继续执行并保留由 `checks`、reference issues 或题面结构独立支撑的 claim，包括符合现有逻辑的 material 与 nonmaterial candidate；
5. 未列入 `DERIVED_ANSWER_CLAIMS` 的 claim 默认不受影响。只有在后续取得明确证据依赖关系后，才允许扩展该清单；
6. 在 quantity observation/诊断信息中保留：
   - 原始解析后响应；
   - `derived_value`；
   - `rationale_final_value`；
   - 命中的提取规则；
   - 字段失效原因 `quantity_response_internal_inconsistency`；
   - 被阻止的 claim 类型；
7. 字段失效诊断不得伪装成 clean，也不得取代仍然有效的独立证据 candidate；
8. 其他 auditor 对同一题的结果完全不变。

V2 不进行第二次请求，不自动修正 `derived_answers`，也不把 rationale 数值写回 structured output。

## 9. `NOT_IDENTIFIABLE` 的行为

当状态为 `NOT_IDENTIFIABLE`：

1. 不猜测 rationale 最终答案；
2. 不自动改写 `derived_answers`；
3. 不因“无法验证自洽”而删除现有候选；
4. 保持现有 quantity 处理逻辑；
5. 可记录不影响候选的诊断原因，用于统计 V2 覆盖率。

### 9.1 五跑完整 cache 的实测覆盖率

2026-08-20 使用历史 commit 重建的题号索引，对五跑 498 份真实 quantity 响应执行当前 checker：

| run | 响应数 | solved | CONSISTENT | INCONSISTENT | NOT_IDENTIFIABLE | NI 比例 |
|---|---:|---:|---:|---:|---:|---:|
| `full_1` | 99 | 83 | 11 | 6 | 82 | 82.8% |
| `full_2` | 100 | 84 | 11 | 7 | 82 | 82.0% |
| `full_3` | 99 | 84 | 13 | 6 | 80 | 80.8% |
| `full_4` | 100 | 84 | 12 | 5 | 83 | 83.0% |
| `full_5` | 100 | 84 | 14 | 7 | 79 | 79.0% |
| **合计** | **498** | **419** | **61** | **31** | **406** | **81.5%** |

其中 79 份响应因 `solution_status != solved` 按前置条件直接返回 NI；另有 327/419 份 solved 响应返回 NI，solved-only NI 为 78.0%。当前明确判定覆盖率只有 `92/498=18.5%`。

该结果不改变第 6 节提取规则和第 9 节保守行为，但形成以下解释边界：

- V2 当前是低覆盖、保守的字段自洽性检查，不是覆盖大多数 quantity rationale 的通用解析器；
- 后续收益只能描述为发生在可识别响应子集上；
- 不得因为 NI 比例高而在本轮放宽提取规则、猜测最终答案或修改 prompt；
- 是否接受该覆盖率由人工决策，不用 gold、标签或样本 ID 反向优化判定。

## 10. 回归 fixture

### 10.1 必须使 derived-dependent claim 失效的正向 fixture

使用 `reports/junior_svamp_benchaudit_report.json` 中现有解析响应固化：

| 样本 | `derived_answers` | rationale 最终结论 | 预期 |
|---|---:|---:|---|
| `chal-162` | 15 | 4 | `INCONSISTENT`；不得生成 derived-vs-gold 的 `wrong_gold_answer` |
| `chal-599` | 44 | 21 | `INCONSISTENT`；不得生成 derived-vs-gold 的 `wrong_gold_answer` |
| `chal-687` | 4085 | 8265 | `INCONSISTENT`；不得生成 derived-vs-gold 的 `wrong_gold_answer` |
| `chal-934` | 4 | 1 | `INCONSISTENT`；不得生成 derived-vs-gold 的 `wrong_gold_answer` |
| `chal-974` | 86 | 3 | `INCONSISTENT`；不得生成 derived-vs-gold 的 `wrong_gold_answer` |

fixture 必须保存必要的 `llm_result` 字段，不重新调用模型。

### 10.2 必须保留候选的控制 fixture

1. rationale 和 `derived_answers` 一起算错且数值一致：返回 `CONSISTENT`，继续现有 gold 比较。
   - handoff `chal-599` 的第 1–4 次运行；
   - handoff `chal-157` 的第 4 次运行；
   - handoff `chal-58` 的第 4–5 次运行。
2. rationale 无唯一最终答案：返回 `NOT_IDENTIFIABLE`，保持现有逻辑。
3. `solution_status=ambiguous/contradictory/uncertain`：返回 `NOT_IDENTIFIABLE`。
4. `derived_answers` 为空、多个不同值或不可解析：返回 `NOT_IDENTIFIABLE`。

### 10.3 独立证据存活 fixture

必须增加 `chal-513`：

- `derived_answers=132`，rationale 最终答案声明为 20，因此状态为 `INCONSISTENT`；
- derived-vs-gold 的 `wrong_gold_answer` 必须被阻止；
- `checks` 中独立成立的 `38 - 56 = -18` 非负约束违反必须继续生成原有 `ambiguous_goal` candidate；
- 测试不得读取 gold、`audit_label` 或对 `chal-513` 做 item ID 特判。

### 10.4 语义争议控制 fixture

`chal-275`、`chal-501`、`chal-697` 属于语义和语境理解争议，不是 V2 自洽性规则的直接修复目标。测试必须证明 V2 不会仅因题目存在复杂措辞而使独立证据 claim 失效。特别是 `chal-275`：即使同一响应的 `wrong_gold_answer` 被阻止，由题面结构独立支撑的 `ambiguous_goal` 仍须保留。

## 11. 实施顺序

严格按方案第 5.2.3 节：

1. 实现纯确定性的响应自洽性判定函数；
2. 先添加 fixture 单元测试，再接入 quantity auditor；
3. 第一阶段仅实现 `INCONSISTENT -> derived-dependent claim invalid`，不加重试；
4. 复用现有缓存运行 100 题验证，并报告完整三状态分布及 NI 比例；
5. 检查 API 调用次数必须为 0；非 0 立即停止；
6. 第一阶段收益达标后，才另行讨论重试逻辑。

## 12. 验收标准

必须同时满足：

1. `chal-162/599/687/934/974` 的不自洽 fixture 不再由无效 `derived_answers` 生成 `wrong_gold_answer`；
2. rationale 与 `derived_answers` 一起算错的控制 fixture 仍进入原 gold 比较流程；
3. 无法唯一提取最终结论的响应不被猜测性降级；
4. `chal-513` 中 derived-dependent claim 消失，但由独立 `checks` 支撑的 candidate 存活；
5. `chal-275` 中由题面结构独立支撑的争议 candidate 不因 `derived_answers` 失效而消失；
6. 其他 auditor 结果不变；
7. 100 题缓存验证 API 调用次数为 0；
8. 对比报告同时输出 TP、FP、FN；
9. 不得损失任何证据未被本规则作废的 TP；
10. handoff 五跑 findings 反事实使用真实 extractor 时，必须复现 `ΔTP=0`、`ΔFN=0`、`ΔFP=-4–-1`；
11. `confirmed=0` 顶层约束不变；
12. 不修改数据集标签、置信度阈值或 prompt；
13. 完整 cache 验证必须将未产生 quantity 调用的 item-run 排除分母，并同时报告总体 NI 与 solved-only NI；
14. 若 NI 高于 40%，必须明确披露外推限制，不得只报告 TP/FP/FN 收益。

基准参考：当前方案口径为 TP=32、FP=18。最终验收以同一代码基线、同一 manifest、同一缓存条件下的改造前后对比为准。

### 12.1 当前验证记录（更新至 2026-08-20）

- targeted pytest（quantity、event-state、audit-coverage）：`30 passed, 8 subtests passed`；
- 项目完整 pytest：`714 passed, 8 subtests passed`；
- Python 编译检查通过；
- `git diff --check` 通过；
- handoff 五跑实现级离线反事实复现 `ΔTP=0`、`ΔFN=0`、`ΔFP=-4–-1`；
- 五跑题号索引包 SHA256 全部通过，498/498 份响应与原始 cache 完全一致；
- 完整 cache 三状态为 `CONSISTENT=61`、`INCONSISTENT=31`、`NOT_IDENTIFIABLE=406`；
- 总体 NI 为 81.5%，solved-only NI 为 78.0%，当前结果不支持“覆盖大多数响应”的表述；
- 完整 D 方案五跑合计 `TP/FP/FN: 150/85/40 -> 150/72/40`，即 `0/-13/0`；
- no-finding 新增 `INCONSISTENT` 为 `chal-747`（5/5）和 `chal-693`（仅 `full_2`），均不改变冻结 candidate；
- `chal-591` 五跑均为 `derived_answers=93899` 且返回 NI，本地 TP 损失未复现；
- 完整 cache 分析脚本 targeted pytest：`12 passed, 8 subtests passed`；
- 最新主线同步分支的全部本地可运行测试：`932 passed, 23 skipped, 12 deselected, 8 subtests passed`；未运行部分依赖外部实验资产、学长机器路径或当前环境未安装的 `scipy`；
- 最新主线代码下五跑反事实完整复现 `NOT_IDENTIFIABLE=81.5%` 及 `ΔTP=0`、`ΔFP=-13`、`ΔFN=0`；
- 上述验证均未调用 LLM API；原实现提交 `c461d29` 已在最新主线基线上重放为 `dd3023b`。

## 13. 非目标

V2 明确不包含：

- 重试 LLM 请求；
- 修改 quantity prompt 或输出 schema；
- 自动修正模型答案；
- 整条 quantity 响应作废；
- 统一过滤 nonmaterial；
- 修复一般算术能力；
- 修复语义和语境理解问题；
- 新增 auditor；
- 开始改进 C；
- 同步主线。
