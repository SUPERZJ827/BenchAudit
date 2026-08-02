# A′ 独立红队复核

> 复核日期：2026-07-29
> 复核范围：`research/workspace-a-prime-rejection-20260729` 的 `449b6cb..72f7001`
> 全程零 API 调用。所有数字由本地代码、冻结产物和原始 cache 独立重算。

---

## 最终裁决

**有条件通过。**

主结论全部独立成立：

- calibration gate 确实 FAIL（family recall 0.632 < 0.90，candidate rate 0.464 > 0.40）；
- 五个预注册阈值确实给出同一候选集，且原因是真实的（被选中的 188 条最低置信度就是 0.90），不是重放口径错误；
- internal validation 确实没有偷跑；
- review-only 安全边界在代码层成立，A′ 路由无法单独产生语义 finding；
- 四个产物哈希逐字节匹配，`analysis.json` 独立重算后与交付版本完全一致。

发现 4 个问题，**没有一个改变已报告数字，也没有一个改变停止裁决**。其中 2 个（B1 索引类型、B2 Exact 诊断口径）应在合并前修掉或改写表述。

---

## 独立复现结果

### git / diff

```
72f7001 report Workspace A-prime calibration failure     (+130)
35c1714 add structured Workspace A-prime router          (+943)
449b6cb freeze Workspace A-prime development protocol    (+197)
45156a2 clarify Workspace holdout metric scope           (baseline)
```

`git diff --stat 45156a2..72f7001` → 11 files, **1270 insertions / 9 deletions**。
`git diff --check` 无空白问题。

安全扫描结论：

| 检查项 | 结果 |
|---|---|
| API key / token / `.env` | 无。唯一命中是 `"api_key_env": "DEEPSEEK_API_KEY"`（变量名，非密钥） |
| `/home/zhoujun` 写进主库逻辑 | 无。唯一命中在 `A_PRIME_CALIBRATION_RESULTS_20260729.md` 的产物路径锚点（文档，非代码） |
| 大型 cache / 原始响应 / artifact | 无。11 个文件全部是代码、测试、配置、manifest、报告 |
| 无关功能改动 | 无 |
| 修改第三份 holdout 结果或标签 | **无**。改动文件列表中不含任何 `third_holdout` 路径；diff 全文对 `third_holdout` 零引用 |

`§12.10` 的"943 行新增"核实为 `35c1714` 单个提交的插入数，属实。全阶段实际：Python 893 行（非测试 661 / 测试 232），其余 377 行为配置、manifest 与报告。

### 测试

```
pytest -q tests/test_workspace_grounding.py \
         tests/test_workspace_static_llm_ablation.py \
         tests/test_workspace_a_prime.py
→ 50 passed in 0.18s

pytest -q
→ 778 passed in 21.39s
```

零失败。与声称一致。

### 哈希

```
689fad58c3947109b3547561681d3fa258ecbc7ded9ec94cfb7751d2ec061c1a  ..._items.jsonl     ✓
53740726724c1a58e200245a3795ca243c2573ec49aa1ce838b1f7d7b39fc6e4  ..._cache.jsonl     ✓
8f307d1d906cc8729462405bb4667cada0f90236c9984c53ade213f182ceee63  runtime.json        ✓
fee5a065173851bb5597af5994e3beee9408bf40aaa0b9d62854d617d5434147  analysis.json       ✓
```

4/4 匹配。

### 指标

用文档给出的命令独立重跑 `analyze_workspace_a_prime.py`，输出与交付的 `analysis.json` **规范化后逐字段完全一致**。

| 方法 | Candidate rate | Family recall | Reviewed P | Reviewed R | Reviewed F1 | Logical calls |
|---|---:|---:|---:|---:|---:|---:|
| 旧 A | 211/405 = 52.10% | 16/19 = 84.21% | 0.850 | 0.8095 | 0.8293 | 231 |
| A′ | 188/405 = 46.42% | 12/19 = 63.16% | 0.8125 | 0.6190 | 0.7027 | 208 |

- family positives（calibration 分区）= 19 ✓
- reviewed universe = 28（21 positive + 7 negative）✓
- A′ reviewed TP/FP = 13/3 ✓
- logical-call reduction = 1 − 208/231 = **9.96%** ✓（"约 10.0%" 属实）
- 五阈值候选集：`0.50→188, 0.60→188, 0.70→188, 0.80→188, 0.90→188` ✓
- 置信度分布：`1.00:273, 0.95:40, 0.90:75, 0.80:17`（合计 405）✓

### API / token / verifier / finding

| 项目 | 声称 | 实测 |
|---|---:|---:|
| task | 20 | 20 |
| rubric | 405 | 405（`structured_rows` 亦为 405） |
| API attempts / success / failure | 20 / 20 / 0 | 20 / 20 / 0 |
| prompt / completion / total tokens | 126,647 / 35,971 / 162,618 | 一致 |
| verifier calls | 0 | 0（`verify_unsupported: false`） |
| findings | 0 | 0（jsonl 中 findings 数组全空） |
| operational unknown | 0 | 0（`operational_unknown_tasks: []`） |
| cache hits | — | 0（20 条全为新调用） |

---

## Claim-by-claim 核验表

| Claim | 核验结果 | 独立证据 |
|---|---|---|
| §4.2-1 必须覆盖每个 rubric index | ✅ | `set(indexed) != requested → None`；缺行实测 fail-closed |
| §4.2-2 缺行/重复/越界/未知 code/非法 confidence 全部使 view 失败 | ✅（含类型例外见 B1） | 16 个对抗构造 15 个 fail-closed，见下表 |
| §4.2-3 缺失行不当 do_not_route | ✅ | 缺行整体返回 None，走 operational failure 路径 |
| §4.2-4 route + 拒绝类 code → 本地强制拒绝 | ✅ **且真实生效** | 实跑中 `route_action_rejected_by_reason_code` 触发 **10 次**（action=route 198 条，policy 选中仅 188 条） |
| §4.2-5 模型不能只改 action 绕过 allowlist | ✅ | `do_not_route + unsupported_exact_constraint` → selected=False；`route + general_quality` → selected=False |
| §4.2-6 原始结果保留在 `scanner["structured_route"]` | ✅ | 确定性覆盖时 `model_action`/`model_reason_code` 保留原值 |
| §4.3 26 条 P1 grounding positive 上 0 条被确定性拒绝 | ✅ | 26/26 rubric 文本可取，`deterministic_structured_rejection` 全部返回 None |
| §4.3 dual-triage 30 task：general quality 13 / intrinsic validity 5 | ✅ | 609 条 rubric 全量离线重扫 → `{intrinsic_validity: 5, general_quality: 13}` |
| §4.4 A′ 路由无法直接产生 `task_rubric_mismatch` | ✅ | 合成 decision 探针：`routing_only=True + verifier=None + label=unsupported` → 发出 0 条 |
| §4.4 operational failure 不被静默当 clean | ✅ | 探针 → `llm_audit_failure` / `unknown` / review_only=True / scope=operational |
| §4.4 confirmed 永远不可达 | ✅ | `_assert_review_only` 对 substantive 强制 `evidence_tier == "review"`；探针中 verifier 路径亦为 review |
| §4.4 findings=0 由构造保证 | ⚠️ 见 B3 | 实测为 0，但不是结构性保证 |
| §五 旧 A 基线只计一次 router call | ✅ | `_task_router_calls` 按 task 布尔计数，与 view 数无关；baseline router_calls=20 |
| §五 objective resolver 全短路 task 不误计费 | ✅（本轮不适用） | 本分区短路 0 条，405 条 rubric 全部进入 router |
| §五 candidate 按 `(item_id, rubric_index)` 去重 | ✅ | 两侧均为 `set[tuple[str,int]]` |
| §五 分母一致 | ✅ | 旧 A 与 A′ 同用 `rubric_count = 405` |
| §五 candidate rate 只作为成本代理 | ✅ | 协议 §7 与报告 §3 均如此表述 |
| §六 20 API attempts | ✅ | runtime.json，另见 B4（配置上限口径） |
| §七 全部数字 | ✅ | 见上表 |
| §八 七条漏检 | ✅ 逐条确认 | 见下节 |
| §九 Exact 诊断 9 / +3 / 47.2% / 恢复 0/7 | ✅ 复现，但口径需修正 | 见 B2 |
| §十 未偷跑 internal validation | ✅ | 见下节 |
| §十一 50 / 778 passed | ✅ | 实跑一致 |
| 划分正确性（20+10、不重叠、分层 10/5） | ✅ | 交集为空；并集恰为 `DUAL_TRIAGE_HOLDOUT_30`；positive-bearing task 10 vs 5；family positives 19 vs 7（合计 26 ✓） |
| 第三份 holdout 不在 30 个开发 task 内 | ✅ | `THIRD_HOLDOUT_30_20260729.json` 与 dev30 交集 = 0 |

### Parser 对抗构造实测

| 构造 | 结果 |
|---|---|
| 完整合法 | 接受 |
| 少一行 | **fail-closed** |
| 重复 index | **fail-closed** |
| 多一行（越界 index） | **fail-closed** |
| `confidence: True` | **fail-closed** |
| `confidence: NaN` / `Inf` / 字符串 `"NaN"` | **fail-closed** |
| `confidence: -0.1` / `1.5` | **fail-closed** |
| 未知 reason_code | **fail-closed** |
| 未知 evidence_source | **fail-closed** |
| `decisions` 非 list / 行非 dict / 空 list | **fail-closed** |
| `operational_failure: true` | **fail-closed** |
| 大小写 + 空白变体（`" ROUTE "`, `" Unsupported_Exact_Constraint "`） | 接受（设计意图，正确） |
| `rubric_index: true` / `1.9` / `"1"` | ⚠️ **静默接受**，见 B1 |

---

## 发现的问题

### [中] B1 — `rubric_index` 类型校验不严格，可静默错位

- **最小复现**

```python
from benchcore.workspace_grounding import _indexed_structured_triage_decisions as P
row = lambda i: {"rubric_index": i, "action": "route",
                 "reason_code": "unsupported_exact_constraint",
                 "evidence_source": "task", "confidence": 1.0}
P({"decisions": [row(True), row(0), row(2)]}, {0, 1, 2})  # 被接受，True → index 1
P({"decisions": [row(1.9),  row(0), row(2)]}, {0, 1, 2})  # 被接受，1.9 → index 1
```

- **根因**：`index = int(value.get("rubric_index"))`。`confidence` 做了 `isinstance(..., bool)` 拒绝，`rubric_index` 没有做同样的检查，也没有拒绝浮点截断。`int(True) == 1`、`int(1.9) == 1`。
- **影响**：模型若省略 index 1 的真实行、改以 `true` 或 `1.9` 提交，覆盖性检查（`set(indexed) != requested`）仍会通过，该 rubric 的决定来自一行本该判为非法的输出。这正是 §12.5「索引对齐」攻击面上唯一真实存在的洞。
- **是否影响已报告数字**：**否**。原始 cache 的 405 个 decision 行 `rubric_index` 类型全部为严格 `int`（0 例非法）。
- **是否影响停止裁决**：否。
- **推荐修法**：与 `confidence` 同构处理。

```python
raw_index = value.get("rubric_index")
if isinstance(raw_index, bool) or not isinstance(raw_index, int):
    return None
index = raw_index
```

（若要继续容忍 `"1"` 这类字符串，应显式白名单 `str` 并要求 `.isdigit()`，而不是靠 `int()` 兜底。）

---

### [中] B2 — Exact 诊断的 9 / +3 / 47.2% 是"零输入证据"上界，不是操作值

文档 §九 自己提出了这个疑问。答案是：**结论方向安全，但报告的三个数字系统性高估了 Exact 的边际贡献。**

- **单调性证明**（代码层）：`route_exact_constraint` 中 `allowed_input_evidence` 只参与拼接 `visible`，而全部四个路由条件都是 `... not in visible` 形式（`unmatched literal`、`exact_count`、`ordering`、`language_requirement`）。因此扩大 `visible` **只能删除 reason，永不新增**。→ `allowed_input_evidence=""` 给出的是 Exact 路由的**最大集**。

- **实测**（零 API，仅本地重算）：

| 设定 | Exact 路由 | 相对 A′ 新增 | 并集 candidate rate | 恢复漏检 |
|---|---:|---:|---:|---:|
| `allowed_input_evidence=""`（报告口径） | 9 | 3 | 47.16% | **0 / 7** |
| 带真实 input inventory | 6 | **0** | 46.42% | **0 / 7** |

- **是否影响已报告数字**：不影响 A′ 主指标（A′ 的 188 / 46.4% / 63.2% 与 Exact 完全无关）。影响的是 §六 诊断段落的三个数字本身。
- **是否影响停止裁决**：**否**——"恢复 0/7" 在最大集下都成立，补上输入证据只会让 Exact 路由更少，结论 a fortiori 更强。
- **推荐修法**：不必删除该诊断，但把表述改成：*"在零输入证据（即 Exact 路由的上界）设定下 Exact 选 9 条、相对 A′ 新增 3 条、并集 47.2%；补上真实 input evidence 后降为 6 条、新增 0 条、并集 46.4%。两种设定下均恢复 0/7 漏检。"* 现在的写法会让读者以为 Exact 还能贡献 3 条候选，实际是 0 条。

---

### [低 / 说明] B3 — `--grounding-routing-only` 不结构性保证零 substantive finding

- **最小复现**（合成 decision 直接喂 checker）：

```
routing_only=True,  verifier=None                  → []                       ✓
routing_only=True,  verifier={"label":"unsupported"} → task_rubric_mismatch    （verifier 授权，符合设计）
routing_only=False, verifier=None, label=unsupported → task_rubric_mismatch    ← 这条
operational_failure=True                            → llm_audit_failure        ✓
```

- **根因**：`audit_item_two_stage` 中 objective resolver 短路路径写死 `"routing_only": False`。`check()` 的豁免门是 `routing_only is True and verifier is None`，短路路径不满足，于是若 resolver 判 `label="unsupported"` 就会直接发 `task_rubric_mismatch`——即便 `--grounding-routing-only` 开着、verifier 关着。
- **是否影响已报告数字**：**否**。本分区 405 条 rubric 的 objective resolver 短路数为 **0**，所以 findings=0 是实测事实。
- **是否影响停止裁决**：否。
- **对 review ceiling 的影响**：无。该路径产出的仍是 `evidence_tier="review"` / `review_only=True`，`_assert_review_only` 也会拦截任何越界，**confirmed 依然不可达**。
- **需要修正的是表述**：`§4.4` 的 "confirmed 永远不可达" 成立；但若把 "routing-only ⇒ findings=0" 当成构造保证则不成立。建议报告写成"本轮 objective resolver 短路 0 条，因此 findings 实测为 0"，或者在 runner 里对 routing-only 模式加一条断言，把短路路径的 substantive finding 也一并抑制。

---

### [低] B4 — 配置的 API 硬闸设在阶段二的值上

`configs/llm_deepseek_workspace_a_prime_dev.json` 的 `max_api_attempts: 35` 与 `observed_token_stop: 600000`，对应协议 §5 的**全阶段**上限；而阶段一（calibration）的预算是 **25 attempts / 400,000 tokens**。也就是说阶段一的预算没有机器强制，只有人工纪律。

- **是否影响已报告数字**：否。实跑 20 attempts / 162,618 tokens，两个口径下都远低于上限。
- **是否影响停止裁决**：否。
- **推荐修法**：阶段一单独一份 config（`max_api_attempts: 25`, `observed_token_stop: 400000`），或在 runner 中按 partition manifest 选预算。`RESULTS.md` 写的 "API attempts：20/25" 是按协议口径写的，与 config 不符，属同一问题的两面。

---

### [说明] B5 — 七条漏检的根因比报告写的更严重

报告 §5 的解释（"宽泛父任务被误当作精确设计的授权"）是对的，但漏掉了更关键的一层：**模型选的 `reason_code` 与它自己写的 `brief_reason` 在 7 例中有 3 例直接矛盾**。详见下节逐例裁决。这意味着 reason taxonomy 并没有真正约束模型的推理，只是给了它一个事后贴标签的字段。

这一点强化而不是削弱负结论：它说明失败不在 confidence 校准（§7-4 已指出），也不只在语义判断，而在**结构化 schema 本身没有形成约束力**。下一版若继续让模型自选 reason_code，同样的错误会以同样的方式复现。

### [说明] B6 — family recall 的分母同样受 reference selection bias 影响，但未同等声明

协议 §6 与报告都正确地把 reviewed precision 限定为"已有标签上的条件指标"。但 family recall 的分母来自同一条链路：

`SEALED_MAPPING.json` 30 行 → 全部 `reviewed_label = 较可信真问题` → 该标签来自 `WorkspaceBench_full388_Codex证据化逐条标注_20260720.md`，而该文件开头自述"是对前一份**筛选后问题清单**的逐条复核，不是人工作者真值集"，复核输入为 559 条候选。

即 family positive 集合 = "曾被更早一轮候选生成器捞出、且被两阶段复核判为可信真问题" 的 rubric。任何从未被任何路由器捞出的 grounding 缺陷，对 A 和 A′ 都不可见。

- **偏差程度可量化且不严重**：30 行中 `routed_hidden_constraint=True` 仅 24 行、`routed_union=True` 仅 26 行——说明该 universe 并非旧 A 候选集的子集，A 自己也漏了 6 条。所以这不是循环论证。
- **但 recall 84.2% / 63.2% 都是"在已知可发现正例上的条件 recall"**，不是全量 recall。建议在报告 §3 表格下方加一行与 reviewed P 同等强度的限定语。
- **不影响 A vs A′ 的比较有效性**：两者面对同一分母，且该分母的构造与 A′ 无关。

---

## 七条漏检逐例裁决

对每条回答文档 §八 的五个问题。**结论：7/7 全部确认为真漏检，family label 无误判，索引无错位。**

索引对齐前置验证：

- `SEALED_MAPPING` 的 30 行 `routed_hidden_constraint` / `routed_support_challenge` / `routed_union` 用原始 dual-triage jsonl 全部独立重算 → **0 处不一致**；
- A′ 运行与 A 基线运行的 405 条 rubric 文本**逐字节相同** → **0 处错位**。

| # | item / rubric | family label | A′ 决定 | 模型引用的证据 | 裁决 |
|---|---|---|---|---|---|
| 1 | wb-130 / 19<br>"合并后 PPT 的第一张幻灯片是否来自 panel A" | grounding ✓（primary，无 acceptable 备选） | `do_not_route` / `task_supported` / conf **0.8** | "merge the \`Suppl.Fig.2\` panel-related files" | **真漏检。** 引文只授权"合并"，完全未授权"第一张必须来自 A"。模型 brief 自述 "is **plausible**"——把"合理"当成"被授权"，字面暴露了根因 |
| 2 | wb-157 / 10<br>"改进建议章节是否汇总了至少十条来自用户的具体建议" | grounding ✓ | `do_not_route` / `input_supported` / conf 1.0 | 逐条列出了 10 条建议 | **真漏检，但七条中最可辩护的一条。** 输入确实存在 ≥10 条建议，模型的事实陈述不假；错在它回答的是"素材是否存在"，而 grounding 问的是"rubric 指定的汇总口径（恰好十条、须来自用户）是否被 task 授权"。属于问题错位而非事实错误 |
| 3 | wb-196 / 7<br>"改进报告结构是否包含核心问题总结、分维度改进、实施时间线、预期效果、结论、优先级排序六个完整章节" | grounding ✓ | `do_not_route` / **`general_quality`** / `evidence_source=intrinsic` / **evidence_quote 为空** | 无 | **真漏检，且是最严重的一例。** 六个具名章节的强制枚举被归类为 `general_quality`，证据来源标 `intrinsic`，引文为空——三项全错。模型 brief 自写 "Requires **specific sections**"，与它选的 code 直接矛盾。另注：确定性捷径在此**正确地**没有触发（rubric 含 `include`/`section` marker，`_EXACT_OR_CONTENT_MARKER_RE` 命中并禁用短路），所以这是纯模型错误 |
| 4 | wb-49 / 18<br>"是否基于表格中的约定采购量数据生成了柱状图" | grounding ✓ | `do_not_route` / `task_supported` / conf 1.0 | "also create a **visualization chart** inserted below the table" | **真漏检。** "可视化图表" ≠ "柱状图"。模型 brief 自述 "bar chart is a **reasonable choice**"——再次把"合理"当"授权" |
| 5 | wb-9 / 2<br>"HTML dashboard 是否包含 OKR 完成度柱状图、用户反馈问题分布饼图、问题解决进度环形图三张图" | grounding ✓（acceptable 含 `subjective_quality_review`） | `do_not_route` / `task_supported` / conf 1.0 | "generate a visual HTML dashboard" | **真漏检。** 引文完全未提及任何图表类型。brief 自述 "three specific chart types are a **legitimate design requirement**"——承认了是"设计要求"却仍标 `task_supported` |
| 6 | wb-9 / 8<br>"改进建议章节是否包含至少五条覆盖资源调整、问题重排序、决策复盘、里程碑监控、目标调整的建议" | grounding ✓（acceptable 含 `subjective_quality_review`） | `do_not_route` / `task_supported` / conf 1.0 | "provide recommendations" | **真漏检。** brief 自述 "five specific categories is a legitimate **general quality** requirement"——brief 说 general quality，code 却写 `task_supported`，两者互斥 |
| 7 | wb-9 / 9<br>"HTML 布局是否分为核心指标、OKR 完成度、用户反馈、决策评估、综合建议五个区块" | grounding ✓（acceptable 含 `subjective_quality_review`） | `do_not_route` / `task_supported` / conf 1.0 | "generate a visual HTML dashboard" | **真漏检。** 同 #5，同一条引文被用来授权五个具名区块 |

**关于 family label 是否可能判错**：#5 / #6 / #7 三条的 `acceptable_families` 含 `subjective_quality_review`，是七条里唯一有解释空间的一组，且恰好全部来自同一个 task（wb-9）。但它们的 `is_grounding_defect` 均为 `yes`、`primary_family` 均为 `workspace_rubric_grounding`，按分析器的判定规则计入正例是正确的。

**敏感性**：即使把这三条全部剔除，A′ 的 family recall 为 12/16 = 75.0%，仍低于 0.90 门槛；旧 A 为 16/16 = 100%，差距反而拉大。**calibration FAIL 的裁决对这个标签争议不敏感。**

**共同结构**：7 例中 5 例（#1/#4/#5/#6/#7）的 `evidence_quote` 是 rubric 精确要求的**严格上位概念**。这可以被一条本地策略机械捕获，无需模型自觉：*当 rubric 命中 exact/枚举 marker、而 `evidence_source=task` 且 `evidence_quote` 未包含该 marker 对应的字面量时，禁止 `task_supported` 拒绝。* 建议作为下一版的具体入口，而不是继续依赖模型自选 reason_code。

---

## Exact 临时诊断是否可保留

**可以保留，但必须改写表述。**

理由已在 B2 展开，核心是三点：

1. 该诊断零 API、不参与主指标、不改变 calibration FAIL——这一点属实；
2. `allowed_input_evidence=""` 产生的是 Exact 路由的**最大集**（代码层单调性可证），所以"恢复 0/7"这个**否定性结论在最保守方向上成立**，不需要补造；
3. 但 9 条 / 新增 3 条 / 47.2% 三个数字是上界，真实设定下为 6 条 / 新增 0 条 / 46.4%。按现在的写法，读者会认为 Exact 尚能贡献 3 条候选，实际贡献为 0。

因此**不建议删除**（文档 §九 给的第三个选项），建议按 B2 的措辞改写。

---

## Internal validation 未运行证明

| 检查 | 结果 |
|---|---|
| `find reports -maxdepth 2 \| grep -Ei 'a_prime\|internal_validation\|fourth_holdout'` | 仅命中 `workspace_grounding_a_prime_calibration_20260729/` 下的 6 个文件，全部属于 calibration |
| `reports/` 下是否存在 internal-validation 目录或第四份 holdout 目录 | 无 |
| 10 个 IV item id 在 calibration 产物目录中出现 | **0 次命中** |
| 10 个 IV item id 在 A′ 全部 diff 中出现 | 每个恰好 **2 次**，全部位于 `A_PRIME_DEV_SPLIT_20260729.json` 与 `A_PRIME_INTERNAL_VALIDATION_10_20260729.json` 两份 manifest。**无一出现在 prompt、reason code、regex、阈值或分析器中** |
| calibration ∩ internal validation | 空集 |
| calibration ∪ internal validation | 恰好等于 `DUAL_TRIAGE_HOLDOUT_30_20260728` 的 30 个 id |
| 分层是否符合协议 | positive-bearing task：calibration 10 / IV 5 ✓；family positives：19 / 7（合计 26）✓ |
| 第三份 holdout 泄漏（§12.9） | `THIRD_HOLDOUT_30_20260729.json` 与 dev30 交集 = 0；A′ diff 全文对 `third_holdout` **零引用**；改动文件列表不含任何第三份 holdout 产物。未发现按逐例结果拟合的痕迹 |
| 运行产物本身 | `runtime.json` 记录 20 个 task、20 次 API、cache 20 条；`items.jsonl` 20 行，item id 与 calibration manifest 完全一致 |

**结论：停止纪律成立。** 未发现任何偷跑迹象。

需要说明的方法论边界：以上只能证明"未对 IV 的 10 个 task 发起过 A′ 调用、未在代码中引用它们"。无法从产物证明"未曾在脑内看过第三份 holdout 的逐例结果再据此设计 reason taxonomy"——这类泄漏原则上不可由静态审计排除。但 reason taxonomy 是通用语义类别、五条 regex 也未针对任何具体 item，未见定向拟合特征。

---

## 是否允许合并

**允许合并，条件如下。**

合并前必做（2 项）：

1. **B1** — `rubric_index` 加严格类型校验。这是唯一一个能让非法输出被静默接受的路径，改动 3 行，且已有测试文件可直接补一条回归。
2. **B2** — 改写 `A_PRIME_CALIBRATION_RESULTS_20260729.md` §6 与 `RESULTS.md` 中 Exact 诊断的三个数字，标注为零证据上界并补上真实证据下的值（6 / 0 / 46.4%）。这是唯一一处会让读者得出错误推论的表述。

合并前建议（2 项，可延后）：

3. **B3** — 或在 runner 的 routing-only 模式加断言抑制 objective-resolver 短路路径的 substantive finding，或把报告表述从"构造保证"改为"本轮实测短路 0 条"。
4. **B6** — 在报告 §3 表格下补一行与 reviewed P 同等强度的 family recall 选择偏差限定语。

不阻断合并：

- **B4**（config 上限口径）与 **B5**（漏检根因描述可加强）。B5 建议在下一版协议中吸收，而不是改本轮报告的结论。

**对负结果本身的评价**：协议、分母、标签、成本口径和停止纪律五项均独立成立。冻结、预注册阈值集、事前 go gate、以及 gate 失败后真的停手——这几点在本次核验中都经受住了检验。B5 提供的额外证据（reason_code 与 brief_reason 自相矛盾）使这个负结论比原报告写的更有信息量：它定位到的不是"阈值没调好"，而是"让模型自选 reason code 这一结构本身不成立"。这是可以直接指导下一版设计的负结果。
