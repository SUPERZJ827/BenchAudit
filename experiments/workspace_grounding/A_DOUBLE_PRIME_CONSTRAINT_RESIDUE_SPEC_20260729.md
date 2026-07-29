# Workspace grounding A″：约束残差与证据角色冻结 Spec

协议版本：`workspace-grounding-a-double-prime-residue-v1-20260729`

基线提交：`429c3ee`
研究分支：`research/workspace-a-double-prime-constraint-residue-20260729`

状态：**Spec 冻结候选；Claude 一致性复核通过前禁止写实现。**

---

## 0. 最重要的选择偏差声明

R2a–R2d 四个规则族是在研究者已经查看 A′ 的 7 条已知漏检后提出的：

- R2a 对应未授权的顺序或位置；
- R2b 对应未授权的数量或封闭枚举；
- R2c 对应未授权的子类型修饰语；
- R2d 对应未授权的具名结构。

因此：

1. 四个规则族本身已经使用了 dev20 漏检信息；
2. dev20 上的恢复数、candidate rate、边际成本都只能称为**开发诊断**；
3. 即使 dev20 达到 16/19，也不能声称泛化改进；
4. 只有未参与规则选择的冻结 internal10 才能提供内部验证证据；
5. 只有 internal10 通过后创建的 task-disjoint 新 holdout 才能提供外部泛化证据。

禁止在得到好看的 dev20 数字后补写本声明。

---

## 1. 本阶段只回答什么

本阶段只回答：

> 在不增加 LLM 调用、只使用 A′ 已缓存的结构化理由和证据锚时，四类预注册的约束残差规则能否把 A′ 恢复到至少不劣于旧 A 的 candidate–recall 工作点？

本阶段不回答：

- R2a–R2d 是否跨 task 或跨 benchmark 泛化；
- 新增的未标注候选是否是真缺陷；
- A″ 是否提高完整 388 题的 precision/recall；
- A″ 是否可以产生 confirmed finding；
- 新 schema 或第二次 LLM 调用是否有价值。

本阶段 **0 API 调用**。只允许读取冻结的 A′ calibration 产物，以及生成
这些产物时使用、按 SHA256 冻结且不含评审标签的 WorkspaceBench 源数据。

---

## 2. 冻结输入与来源

### 2.1 代码和协议

| 文件 | SHA256 |
|---|---|
| `experiments/workspace_grounding/A_PRIME_DEV_PROTOCOL_20260729.md` | `e7402f26bb46714687454ec368ee6e7e068a99a09a764a4f57a8708f618aabd4` |
| `experiments/workspace_grounding/A_PRIME_CALIBRATION_20_20260729.json` | `d17f47f5d74507878f63df16291952b8e33167f1941d20af64ce020f6bbe1d76` |
| `experiments/workspace_grounding/A_PRIME_INTERNAL_VALIDATION_10_20260729.json` | `8af94ea6a23663654bec21e115928f6a7d5b30b86d1912e6992e9a5d24325515` |
| `experiments/workspace_grounding/A_PRIME_CALIBRATION_RESULTS_20260729.md` | `ff22fd7069afaef524532c06bd20883d5e4d51d2eb337bee6af9b37cacc0fe17` |

### 2.2 本地冻结运行产物

以下产物不随本 Spec 提交，且位于被 `.gitignore` 排除的 `reports/` 下。
本轮冻结产物根目录为：

```text
/home/zhoujun/llmdata/after623
```

该绝对路径只属于本轮实验的冻结记录，不得硬编码进库代码。分析器必须要求
显式传入 `--artifact-root`，再解析下表中的相对路径；文件缺失或哈希不匹配
必须 fail-closed。

| `--artifact-root` 下相对路径 | SHA256 |
|---|---|
| `reports/workspace_grounding_a_prime_calibration_20260729/grounding_item_structured_triage_items.jsonl` | `689fad58c3947109b3547561681d3fa258ecbc7ded9ec94cfb7751d2ec061c1a` |
| `reports/workspace_grounding_a_prime_calibration_20260729/grounding_item_structured_triage_cache.jsonl` | `53740726724c1a58e200245a3795ca243c2573ec49aa1ce838b1f7d7b39fc6e4` |
| `reports/workspace_grounding_a_prime_calibration_20260729/analysis.json` | `fee5a065173851bb5597af5994e3beee9408bf40aaa0b9d62854d617d5434147` |
| `datasets/workspacebench/full.jsonl` | `2e3d8fd1f5a741b9e6b73ebab9ce23e26ce054527b4f3477de8fdd950aad9dbe` |

源数据只用于恢复 task、output contract 和 input inventory 的可见文本，
以机械校验 A′ evidence quote 及 constraint residue；不得读取其中不存在的
缺陷标签，也不得用 calibration manifest 之外的行调规则。

### 2.3 禁止读取

实现和 calibration 分析不得读取：

- `A_PRIME_INTERNAL_VALIDATION_10_20260729.json` 中 item 对应的运行结果；
- 第三份 holdout 的逐题漏检或标签来选择、删除或修改规则；
- 第四份 holdout（尚不存在）；
- Claude 探索性 ANY/ALL 正则的代码——该探针没有冻结代码、哈希或测试；
- 任何根据 7 个具体 item ID 编写的特例表。

internal10 manifest 的哈希可校验，但不得解析其中 item ID 来调规则。

---

## 3. 已冻结的基线与硬预算

在 dev20 / 405 rubric 上：

| 方法 | Candidate | Candidate rate | Family TP | Family recall |
|---|---:|---:|---:|---:|
| 旧 A | 211 | 52.1% | 16/19 | 84.2% |
| A′ | 188 | 46.4% | 12/19 | 63.2% |

若 A″ 是在 A′ 候选集上增加本地规则候选，则：

```text
候选预算 = 211 - 188 = 23
必须恢复 = 16 - 12 = 4
最大边际成本 = 23 / 4 = 5.75 新增候选 / 新增已知 positive
```

主验收指标按优先级排序：

1. `candidate_count` / `candidate_rate`；
2. `family_tp` / `family_recall`；
3. `marginal_candidates_per_recovered_positive`；
4. review ceiling escape 与 operational unknown；
5. reviewed P/R/F1 和 reviewed FP（仅次要诊断）。

Reviewed universe 仅覆盖 28/405；不得用“新增 reviewed FP 很少”替代
candidate-rate 成本。

---

## 4. 数据可观测性边界

### 4.1 旧 A

旧 A 只保存 `candidate_indices`，不保存：

- `reason_code`；
- `evidence_source`；
- `evidence_quote`；
- `structured_route`；
- 有意义的模型 confidence。

旧 A scanner 中的 `confidence=1.0` 是本地路由代码常量，不是模型自报。

因此禁止声称：

> 分解旧 A 的 424 条路由原因。

旧 A 只能用于候选集合和指标基线；若以后分析第三份 holdout 的 424 条，
只能做 rubric 词法特征等外生分析。

### 4.2 A′

A1a 对 A′ 的全部 405 条生成 reason breakdown：

- action；
- reason code；
- evidence source；
- evidence quote 是否为空及是否为允许材料中的逐字子串；
- policy override；
- route/do_not_route；
- reviewed 标签（若存在）。

重点拒绝类别必须包含：

- `task_supported`；
- `input_supported`；
- `output_contract_supported`；
- `general_quality`。

不能删除 `general_quality`；R2d 的一个已知开发样本位于该类别。

其他 reason code 仍进入完整分解表，但不自动进入 R2 candidate union。

---

## 5. 共同术语和证据角色

### 5.1 文本归一化

所有确定性文本操作统一：

1. Unicode NFKC；
2. `casefold()`；
3. 连续空白压成一个空格；
4. 保留原始字符 offset，报告必须能回指原文；
5. 不因标点差异制造新 constraint residue。

### 5.2 证据角色

| evidence source | 可以证明 | 不能单独证明 |
|---|---|---|
| `task` | 输出义务、目标、格式、明确顺序和覆盖要求 | 未写出的额外设计细节 |
| `output_contract` | 交付物、格式、文件名、结构化输出契约 | 未声明的内容选择 |
| `input` / `input_inventory` | 某个值、实体或事实存在 | 输出必须采用该值、顺序、数量或布局 |
| `intrinsic` | 某 requirement 属通用合法质量/有效性要求 | 当前 artifact 已满足，也不能授权具名内容 |
| artifact observation | 当前输出是否满足合法 rubric | rubric 本身有无 task/input 依据 |
| `none` | 无正面支持 | 不能作为 confirmed 缺陷证明 |

核心纪律：

> 描述性证据存在，不等于规范性输出义务成立。

输入中存在十个对象，不能单独授权“输出必须包含至少十个”；只有 task 或
output contract 明确要求全部覆盖，或存在确定性推导证书时才能拒绝路由。

### 5.3 关系状态

A″ 报告允许以下七种关系状态；这是分析词汇，不是 confirmed proof：

1. `equivalent`；
2. `source_stronger`；
3. `derivable_specific`；
4. `unsupported_specific`；
5. `intrinsic_or_general_quality`；
6. `unrelated_or_conflicting`；
7. `unknown`。

R2 规则只为机械可观察的 `unsupported_specific` 生成 review-routing
候选。无法机械区分时必须 `unknown`，不得强判。

---

## 6. Derivation certificate：R2b 的优先边界

`derivable_specific` 必须由本地、版本化、可重放的证书建立，不能由以下
内容建立：

- LLM 的 `brief_reason`；
- input 恰好含有 N 个对象；
- 常识性“看起来可以算”；
- 模糊的语义蕴含。

证书最小结构：

```json
{
  "derivation_id": "calendar_year_to_month_count_v1",
  "premise_spans": ["2024 年全年"],
  "input_facts": [],
  "derived_constraint": "12 months",
  "proof_basis": "closed_calendar_definition",
  "version": "v1"
}
```

约束必须按原子处理。若证书只覆盖一部分新增约束，已覆盖原子保持
`derivable_specific`，未覆盖残差继续执行下面的 4a/4b，不能让部分证书
为整条 rubric 免责。

v1 若没有可重放证书，不得采信 LLM 自报的 `mechanically_derivable`，也
不得临时用 LLM 补证书。未被证书覆盖的残差继续走 4a/4b；若两者均不
满足，则归为 `unknown` 并弃权。

R2b 的判定优先级固定为：

```text
task/output_contract 直接支持相同数量或封闭集合
    → supported，不路由
确定性 derivation certificate 覆盖一个或多个新增约束原子
    → 被覆盖原子 derivable_specific，不路由；未覆盖残差继续判断
task/contract 明确委托“覆盖 input 中全部/每个对象”，且 input 可完整枚举
    → delegated_derivation，不路由
4a. task/output_contract/input 中不存在支持该约束的量值或闭集；
    包括存在相同对象但量值/闭集与 rubric 要求不一致
    → unsupported quantity candidate
       reason=unsupported_quantity_without_source
4b. 仅 input 中存在 N 个对象或封闭集合，task/output_contract 无覆盖义务
    → unsupported quantity candidate
       reason=descriptive_input_not_normative_obligation
其他情况
    → unknown，不由 R2b 路由
```

这个优先级用于避免：

- 把“全年→12个月”等机械推导误报为超纲；
- 把“输入里刚好有十条→输出必须写十条”误判为已支持；
- 漏掉“任何规范性来源都没有，rubric 自行要求恰好七项”的凭空数量；
- 让部分 derivation certificate 为未覆盖的其他约束免责；
- 在 supported 与 unsupported 之间留下依赖分支顺序的空隙。

4a 优先处理可机械观察的量值/闭集冲突，不因 LLM 将该行自报为
`unrelated_or_conflicting` 而弃权。

---

## 7. H1：正面支持但无引文（卫生检查，不进候选集）

H1 仅在以下 reason code 上检查：

- `task_supported`；
- `input_supported`；
- `output_contract_supported`。

若 `evidence_quote` 为空，或不是其声明 evidence source 的逐字子串，则记录：

```text
explanation_inconsistent:positive_support_without_valid_quote
```

H1：

- 输出到独立 diagnostic ledger；
- 不进入 A″ candidate union；
- 不调用 verifier；
- 不生成 grounding finding；
- 不改变旧 A/A′ 指标；
- 可用于未来 prompt/schema 卫生回归。

当前冻结数据中，空 quote 分支预计命中 9 条，只用于完整性校验，不作为
recall 结果；非空 quote 的“不是声明来源逐字子串”分支尚未预估，不得把
9 写成 H1 总触发数。

---

## 8. R2a：未授权的顺序或位置

### 8.1 适用范围

只检查 A′ 的 `do_not_route` 行，且 reason code 属：

- `task_supported`；
- `input_supported`；
- `output_contract_supported`；
- `general_quality`。

### 8.2 必要条件

同时满足：

1. rubric 含明确的顺序/位置关系：
   - first/last/before/after；
   - 第一个/最后一个/之前/之后；
   - slide/page/section/row/column 等位置锚；
2. 该关系的两个必要组成部分可抽取：
   - `relation`；
   - `anchor` 或被排序对象；
3. task/output contract 没有相同的规范性关系；
4. 若关系只在 input 中出现，task/output contract 没有“保留输入顺序”
   或同等委托；
5. 没有确定性 derivation certificate。

### 8.3 输出

```json
{
  "rule_id": "R2a",
  "relation": "first",
  "anchor": "panel A",
  "rubric_span": "...",
  "support_spans": [],
  "evidence_role": "task",
  "candidate": true
}
```

缺少 relation 或 anchor 时弃权。只见 `order` 等孤立关键词不能路由。

---

## 9. R2b：未授权的数量或封闭枚举

### 9.1 适用范围

与 R2a 相同，并额外允许 `mechanically_derivable` 进入诊断，但证书校验
通过时必须保持拒绝，不能成为候选。若没有有效证书，LLM 自报的
`mechanically_derivable` 不提供任何豁免；未覆盖约束残差必须继续执行
第 6 节 4a/4b，只有两条均不满足时才归为 `unknown`。

### 9.2 必要条件

rubric 至少包含一种可结构化的 obligation：

- exact/at least/at most N；
- 明确“全部/每个”；
- 一个封闭的、可数的具名列表；
- 数量 + 对象 head，例如 `three charts`、`five sections`。

必须抽取：

```text
quantifier
count（若有）
object_head
closed_members（若有）
rubric_span
```

之后严格执行第 6 节优先级。Input 中存在相同数量对象只属于描述性证据；
没有 task/contract 覆盖义务时不能证明 rubric 已支持。

### 9.3 与 R2d 的边界

- R2b 负责“数量/闭集规模是否被授权”；
- R2d 负责“成员名称/章节名称是否被授权”；
- 同一 rubric 可以同时触发，candidate union 只计一次；
- 报告必须同时保留两个 reason，不能依赖先执行哪个规则。

---

## 10. R2c：未授权的子类型修饰语

### 10.1 禁止退化成关键词匹配

R2c 不能实现为：

```text
rubric 命中任一 marker 且 quote 没命中 → route
```

Claude 的探索探针已经表明 ANY/ALL 聚合的边际成本约 19.6/19.5；该代码
未冻结，只用于禁止继续在相同设计空间调聚合算子。

### 10.2 必须产生 head–modifier 结构

R2c v1 的解析器必须输出：

```json
{
  "rubric_head": "chart",
  "support_head": "chart",
  "rubric_modifiers": ["bar"],
  "support_modifiers": ["visualization"],
  "residual_modifiers": ["bar"],
  "rubric_span": "bar chart",
  "support_span": "visualization chart"
}
```

只有同时满足以下条件才可成为候选：

1. rubric 与 evidence quote/task/output contract 中存在可对齐的同一
   semantic head；
2. head 的对齐是显式的、可回放的，不是仅凭 embedding 相似；
3. rubric noun phrase 中存在 content-bearing modifier；
4. modifier 不在规范性 task/output-contract span 中；
5. modifier 不是格式无关的停用修饰语；
6. input 中出现 modifier 但 task 未授权采用该 subtype 时，仍不能证明
   输出义务；
7. 解析出多个竞争 head、无法唯一对齐时弃权。

### 10.3 v1 范围边界

R2c v1 只处理“同一 semantic head 下新增 subtype modifier”的情形。
若 rubric 引入的对象 head 在全部规范性 task/output-contract span 中均
不存在，R2c 必须弃权，不能退化为“全新对象”关键词检测。这一类可能由
R2b 的未授权数量/闭集规则或 R2d 的具名结构规则独立捕获，但不属于
R2c v1 的主张。

因此，`wb-9/2` 在 R2c 上预期弃权：支持 span 的 head 是 `dashboard`，
rubric 新增的是 `chart`，不存在共享 head；其 `three charts` 数量残差
由 R2b 4a 评估。`wb-49/18` 才是 R2c 的目标形态：`visualization chart`
与 `bar chart` 共享 `chart`，残差为 `bar`。

### 10.4 v1 可实现性约束

为避免暗中退化为 marker regex，v1 实现必须：

- 先抽取名词短语 span，再解析 head 与 modifier；
- 保存字符 offset；
- head 对齐和 modifier 残差分别报告；
- 至少有一个测试证明：
  - 共享 head、缺 modifier 时触发；
  - 同 modifier 已被 task 支持时不触发；
  - 只有相同关键词、但不是同一 noun phrase 时不触发；
  - 多个竞争 head 时 fail-closed；
- 测试不得包含 7 个真实 item ID 或逐字复制它们的完整文本。

允许 v1 只支持冻结的英语 noun-phrase grammar；非支持语言必须弃权，
不得用更宽的关键词 fallback。

如果无法实现稳定 head–modifier 输出，R2c 应判为技术不可行并停止，
不能退回 ANY/ALL marker。

---

## 11. R2d：未授权的具名结构

### 11.1 适用范围

必须包含 `general_quality`，同时检查：

- `task_supported`；
- `input_supported`；
- `output_contract_supported`。

### 11.2 必要条件

rubric 中必须能抽取：

- governing head：section/category/part/chapter/slide/heading 等；
- 至少两个具名 member，或一个明确要求的精确名称；
- 每个 member 的原文 span。

只有当 task/output contract：

- 逐项包含同一 member；或
- 明确委托使用 input/template 中的完整具名结构；

才可视为 supported。

仅有“生成报告”“提供建议”“制作 dashboard”等上位义务，不授权具体
章节、类别或栏目。

`general_quality` 的 brief 声称“specific sections”但 evidence source 为
intrinsic、引文为空时，R2d 可以生成 candidate；判断依据是抽出的具名
结构，不是 brief 中的单词。

### 11.3 七条已知漏检的实现前推演

下表在实现前冻结，用于检查四条规则的必要条件是否自洽。它是
dev20 上的开发期预期，不是逐 item 测试 oracle，也不是泛化证据。实现和
测试禁止读取 item ID 写特例；若通用规则的实际结果与表不同，必须报告
原因，不得事后修改表来迎合结果。

| 已知漏检 | R2a | R2b | R2c | R2d | 实现前预期 |
|---|---|---|---|---|---|
| `wb-130/19` | trigger | abstain | abstain | abstain | 未授权顺序/位置由 R2a 恢复 |
| `wb-157/10` | abstain | trigger 4b | abstain | abstain | input 描述性数量不构成输出义务 |
| `wb-196/7` | abstain | trigger 4a | abstain | trigger | 未授权闭集规模与具名章节可同时触发 |
| `wb-49/18` | abstain | abstain | trigger | abstain | 共享 `chart` head，新增 `bar` modifier |
| `wb-9/2` | abstain | trigger 4a | explicit abstain | abstain | `three charts` 无规范性来源；R2c 因无共享 head 弃权 |
| `wb-9/8` | abstain | trigger 4a | abstain | trigger | 未授权闭集规模与具名类别可同时触发 |
| `wb-9/9` | abstain | trigger 4a | abstain | trigger | 未授权闭集规模与具名类别可同时触发 |

这张表只证明规则设计覆盖了已知开发案例。Calibration 的真实结果仍以
统一运行、全量 candidate rate 和 19 条 family-positive 集合为准。

---

## 12. 共同 candidate contract

R2a–R2d 只能输出 review-routing observation：

```json
{
  "candidate_id": "stable hash",
  "item_id": "...",
  "rubric_index": 0,
  "rule_ids": ["R2b", "R2d"],
  "rubric_spans": [],
  "support_spans": [],
  "evidence_roles": [],
  "derivation_certificate": null,
  "review_only": true,
  "confirmation_eligible": false,
  "spec_version": "workspace-grounding-a-double-prime-residue-v1-20260729"
}
```

规则：

- 同一 `(item_id, rubric_index)` 只计一个新增候选；
- 所有触发 rule IDs 必须保留；
- observation 不修改原 A′ cache；
- 不进入 promotion confirmed 路径；
- 即使 method 改名，producer 也必须携带 `review_only=true` 和
  `confirmation_eligible=false`；
- 若未来接入主 checker，中央 promotion 必须有 provenance ceiling 测试；
- 本轮仅生成独立离线报告，不接主 CLI。

---

## 13. 分析与组合协议

### 13.1 单规则

R2a、R2b、R2c、R2d 分别报告：

- raw trigger count；
- 相对 A′ 新增 candidate；
- candidate rate；
- 恢复的已知 family positives；
- `incremental_candidates / recovered_known_positive`；
- 触发的 A′ reason-code 分布；
- 与其他规则的交集；
- reviewed TP/FP（次要）。

### 13.2 组合

四条规则共 15 个非空组合。分析器可以机械枚举全部组合；不得根据结果
增加第 5 条规则、修改文本 grammar 或删除不利 case。

每个组合以 A′ 188 条为基础取 union。

### 13.3 Calibration Go/No-Go

只有同时满足以下条件的组合才 PASS：

- `candidate_count <= 211`；
- `family_tp >= 16/19`；
- `candidate_rate <= 211/405`；
- `review_ceiling_escape == 0`；
- `operational_unknown == 0`；
- 不包含 item-ID 特例；
- R2c 没有退化为 marker ANY/ALL。

`marginal_candidates_per_recovered_positive <= 5.75` 由
`candidate_count <= 211` 和 `family_tp >= 16/19` 数学派生，只作为开发期
效率诊断报告，不构成第三个独立放行门槛。

若多个组合通过：

1. candidate count 最少；
2. family TP 最多；
3. rule 数最少；
4. 按规则 ID 字典序确定性打破并列。

若没有组合通过，裁决为 STOP：

- 不改 prompt；
- 不调用 API；
- 不运行 internal10；
- 不生成第四份 holdout；
- 保存负结果。

Reviewed F1 可以报告，但不参与单独放行。

---

## 14. 测试要求

实现提交至少包含：

1. NFKC/casefold/offset 回归；
2. H1 正面支持无引文与其他空引文类别的区分；
3. R2a relation + anchor 双必要条件；
4. R2b 直接支持、derivation certificate、delegated all-input、
   无来源数量 4a、只有 input 数量 4b 五条路径；
5. R2b 部分证书只豁免被覆盖原子，未覆盖残差继续进入 4a/4b；
6. R2b/R2d 同时触发时 union 去重且 reasons 保留；
7. R2c head–modifier 正例、supported modifier 反例、同词异短语反例、
   多 head fail-closed；
8. R2c 对全新 object head 明确弃权，不启用 marker fallback；
9. R2d 具名结构、通用质量和 task 明确授权反例；
10. observation 永远 review-only；
11. candidate ID 和输出排序确定性；
12. `--artifact-root` 缺失、源数据/产物缺失或任一输入哈希不匹配均
    fail-closed；
13. 旧 A 缺 reason schema 时不伪造 breakdown；
14. 15 个组合枚举及 tie-break 确定性。

测试 fixture 不得包含真实 7 个 item ID，也不得用测试判断字符串中特定
benchmark ID。

---

## 15. 产物和提交顺序

### 提交 1：本 Spec

只包含本文件。推送后由 Claude 检查：

- 选择偏差声明是否充分；
- R2b 与 `derivable_specific` 是否有重叠或空隙；
- R2c 是否可实现而非关键词换名；
- `general_quality` 是否包含在 R2d；
- candidate rate 是否为主成本；
- 是否错误使用旧 A reason data。

### 提交 2：实现与测试

Claude 通过 Spec 后才能开始。不得包含实验结果。

### 提交 3：离线分析与报告

只使用冻结 calibration cache，0 API。报告全部单规则与 15 个组合，包括
负结果。

### 后续

只有提交 3 通过 calibration gate，才单独申请：

- Claude 对抗测试与独立重算；
- internal10 API 预算；
- token/cost 双重上限；
- 是否创建新真实 holdout。

---

## 16. 预注册预期与停止纪律

开发假设：

> 证据角色 + 结构化 constraint residue 可能比宽 marker 规则更高效，但
> 现有证据不足以预言它能达到 5.75。

允许的结果：

- PASS：存在组合在 dev20 达到旧 A 的 candidate–recall 工作点；
- FAIL：规则可恢复漏检但成本仍超过 5.75；
- NOT IMPLEMENTABLE：R2c 无法在不退化为关键词匹配的条件下稳定解析；
- NOT IDENTIFIABLE：冻结 cache 缺少计算某项关系所需的可见文本。

不得为得到 PASS：

- 使用 internal10 或第三份 holdout 调规则；
- 加入逐 item 特例；
- 把 input 内容存在当作输出义务；
- 用 LLM 补 derivation certificate；
- 将 reviewed FP 替代 candidate rate；
- 采用 Claude 未冻结的 ANY/ALL 探针作为正式实现；
- 放宽 211、16/19 或 5.75 的门槛。
