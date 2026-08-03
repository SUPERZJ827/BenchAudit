# MMLU-Redux `ok` 项盲裁定协议：验证 BenchAudit 是否发现重标数据遗漏的真缺陷

> Freeze date: 2026-08-03  
> Status: **FROZEN_BEFORE_PACKAGE_GENERATION_OR_ITEM-LEVEL ADJUDICATION**  
> API budget: 0 for package construction；裁定者类型与成本另行记录  
> Primary purpose: 回答“BenchAudit 到底发现了哪些第三方重标仍未标出的真问题”

## 0. 研究问题与优先级

本实验不优化运行成本，也不把成本作为方法贡献。它直接检验：

> 在 MMLU-Redux 标为 `ok` 的题目中，BenchAudit 的 substantive review candidates
> 有多少能被不知道来源类别的独立裁定者再次识别为 material defect？

这条证据优先于开发集上的 P/R/F1。Platinum blind holdout 仍是外部性能支撑；SVAMP/MMLU
重复运行仍是仪器稳定性证据。三者不得混写成同一个实验。

## 1. 冻结来源

| Artifact | SHA-256 |
|---|---|
| `experiments/mmlu_redux_pilot1000.jsonl` | `70cc9ee184db4017b323bda03061f7c3d56e57ad1ab4b1a3415263fd664072b8` |
| `reports/ranking_impact/audit_full1000.json` | `8fc5fa57330b704faa48f7007f228a7ae3f44d02beaa30c1e96970ba9aa88cc6` |

Frozen audit characteristics：

- items = 1,000；
- report methods = 17；本实验不重跑、不补 method；
- report 是历史冻结产物，不得修改；
- Redux label field = `metadata.error_type`；`ok` 是本实验的第三方 clean label；
- explicit defect labels = `{wrong_groundtruth, bad_question_clarity,
  multiple_correct_answers, no_correct_answer, bad_options_clarity}`；
- `expert` 是 abstention/需专家类，不当作正对照或 clean 对照。

在论文声称“人工标注员漏掉”之前，必须另行核验 MMLU-Redux 对这些 item 的 annotation
provenance。仅凭本地字段，本实验最多写“items labeled `ok` by MMLU-Redux”。

## 2. 三个历史口径必须同时披露

独立复算得到：

| Predicate | All flagged | Redux non-`ok` | Redux `ok` |
|---|---:|---:|---:|
| 任一 `defect_scope != presentation` | 400 | 279 | 121 |
| 任一 `defect_scope == substantive` | 396 | 277 | 119 |
| 任一 `substantive AND evidence_tier == review` | 292 | 206 | **86** |

相应 Redux=`ok` ID-set SHA-256（sorted IDs + trailing newline）：

| Set | SHA-256 |
|---|---|
| 121 legacy non-presentation | `9966f5b6a6fd0d966bda34f926d8e19566c008dd16aaa3311c82f70bc96467fb` |
| 119 substantive | `efbb3fbdc568ba98ec55d9dcb2fcb7b87b67721e89a0d4df4a9565105d9c179a` |
| 86 substantive-review | `4ddb19f6c1cdff3d68f5e6c3a95d75b80d9268c420895bfbe88180122c479e1b` |

`121` 中有 2 条仅含 operational `llm_audit_failure`，不能称为检测到缺陷。`119` 中有
33 条只有 unknown evidence tier，不能与候选层混称 review。故本实验的主争议池固定为
**86 条**，不是 121 条。121/119 只作口径审计。

## 3. 三类盲裁定源与固定规模

### 3.1 D：争议项，全部纳入（n=86）

同时满足：

```text
metadata.error_type == "ok"
AND exists violation:
    defect_scope == "substantive"
    evidence_tier == "review"
```

不抽样，86 条 census 全部进入裁定包。

### 3.2 P：正对照（n=40）

候选池：

```text
metadata.error_type in explicit defect labels
AND no substantive-review violation
```

冻结候选池大小为 142。按 D 的 subject 分布用 largest-remainder 分配 40 个配额；某 subject
无足够候选时，缺额按 `(remaining D subject weight desc, subject asc)` 重分配。组内按
`SHA256(seed || "positive" || item_id)` 排序取前。不得人工挑“明显错误”的题。

### 3.3 N：负对照（n=40）

候选池：

```text
metadata.error_type == "ok"
AND no substantive-review violation
```

冻结候选池大小为 544。使用与 P 完全相同的 subject quota/fallback 算法，rank domain 改为
`"negative"`。

### 3.4 `expert` 项

32 条 Redux=`expert` 全部排除。它们既不是确定正例，也不是 clean 对照；不得为凑配额
临时纳入。

最终唯一 item 数为 `86 + 40 + 40 = 166`。

## 4. 盲化：裁定者看不到系统 finding

第一阶段裁定包每条只含：

```text
blind_id
question/task
choices
declared_gold
evaluator/output contract（若冻结输入提供）
```

严格禁止：

- D/P/N 类别、Redux `error_type`、subject、原 item ID 与原顺序；
- BenchAudit finding、defect type、method、confidence、rationale、evidence tier；
- “系统是否 flag”、总体类比例、86/40/40 数字；
- MMLU-Redux correction、verified gold、source evidence、potential reason；
- 本协议正文或仓库路径。

原因：若只给 D 展示 auditor 输出，而 N 没有输出，类别会立即泄露；即使三类都给文本，
系统理由也会锚定裁定者。第一阶段必须是**独立解题与独立缺陷判断**。

## 5. Package builder 与密封映射

冻结 seed：

`benchaudit-mmlu-redux-ok-blind-adjudication-v1-20260803`

builder 在 package 生成时创建 32-byte random salt：

- `blind_id = HMAC-SHA256(salt, "id\0" || item_id)`；
- 顺序键 = `HMAC-SHA256(salt, "order\0" || item_id)`；
- source mapping（blind_id → item_id/class/Redux label/frozen findings）写到仓库外 mode 0600；
- repo 内只提交 mapping SHA-256、salt SHA-256 commitment 与 public package；
- adjudication lock 提交前不得公开 salt、mapping 或 class counts；
- lock 后才允许 reveal 并评分。

builder 可以读取 labels/findings 以选择和封装，但不得做 item-level judgement。裁定者不得是
package builder，也不得拥有本对话或仓库历史。

## 6. 裁定规则

每个 item 必须先独立求解，再输出一个结构化 verdict：

```text
material_status:
  clean
  material_defect
  presentation_only
  needs_domain_expert
  insufficient_evidence

defect_family (仅 material_defect):
  wrong_gold
  no_correct_answer
  multiple_correct_answers
  missing_condition_or_context
  materially_ambiguous_question
  defective_options
  evaluator_contract_error
  other_material

derived_answer_or_answer_set
confidence: low | medium | high
item_internal_evidence
external_source_used: true | false
external_source_citation (若使用)
short_rationale
```

裁定定义：

- `wrong_gold`：按题面与选项可唯一推出答案，且不等于 declared gold；
- `no_correct_answer`：没有选项/declared answer 满足题目；
- `multiple_correct_answers`：至少两个答案在相同合理解释下成立；
- missing/ambiguous：缺失条件或歧义会实质改变正确答案，不含纯措辞偏好；
- defective options：重复、互相包含、粒度不一致或选项集合使正确作答不可定义；
- presentation-only 不算 material defect；
- 仅“不喜欢题目”“知识陈旧但题面给定时间下仍可答”不算缺陷；
- 无法自行验证专业事实时必须 abstain，不得凭感觉判 defect。

允许查阅权威的一般知识来源，但禁止搜索完整题干、item ID、MMLU errata、MMLU-Redux
item discussion 或 BenchAudit 输出。所有外部来源逐条记录；搜索不是 confirmation 本身。

## 7. 裁定者与证据层级

理想执行为两个相互独立、均无历史上下文的裁定者；全 166 条分别完成后才交换结果。
分歧项交第三裁定者。若只有一个裁定者，结果必须标为 single-adjudicator exploratory。

证据措辞按裁定者类型分层：

| Evidence | 允许措辞 |
|---|---|
| 单个 LLM/agent | `blind-agent-supported`，不得称 confirmed 或 human-verified |
| 两个独立 LLM/agent 一致 | `independent-agent consensus`，仍不得称 human-confirmed |
| 一名独立人类专家 + 可复算机械/权威证据 | `externally confirmed` |
| 两名独立人类专家一致 | `human-adjudicated confirmed` |

因此，新会话 agent 可以高召回筛选和校准设计，但论文头条“人工重标漏掉的真缺陷”必须由
最后两行之一支撑。

## 8. 裁定者质量与对照解释

P/N 不是绝对无误 gold；它们用于解释裁定者的行为：

- P defect recognition rate：40 个 Redux explicit-defect control 中判 material defect 的比例；
- N clean rate：40 个 Redux `ok`、系统未报 review candidate 的 control 中判 clean 的比例；
- D defect rate：86 个争议项中判 material defect 的比例。

预注册可解释性门：

```text
P defect recognition >= 0.70
AND N clean rate >= 0.70
```

任一未达时结果记 `ADJUDICATOR_NOT_CALIBRATED`：仍完整报告，但 D rate 不得作主张。
这不是在宣称 Redux controls 完美，而是在要求裁定者至少与第三方标签有基本一致性；
P/N 的分歧本身另列为潜在新遗漏或过度判错，不能静默丢弃。

若有两个裁定者，同时报告 material-status agreement、defect-family agreement 与 Cohen's
kappa；不得只报最终仲裁后的一致率。

## 9. Commit-before-unblind

顺序固定：

1. 本协议提交；
2. builder + tests 提交；
3. public package、mapping/salt commitments 与 generation receipt 提交；
4. 每名裁定者输出分别提交，记录原始字节 SHA-256；
5. adjudication lock 提交，绑定全部裁定输出；
6. lock 后 reveal salt/mapping，运行唯一 scorer；
7. scoring receipt 与报告提交。

任何在第 5 步前读到 class、Redux label 或 BenchAudit finding 的裁定输出作废，不得用
“没有利用”补救。

## 10. 解盲后的系统归因

一个 D item 只有同时满足以下条件才计为“BenchAudit 找到的 Redux-`ok` material defect”：

1. 盲裁定结果为 `material_defect`；
2. 裁定 defect family 与该 item 在冻结 report 中至少一个 substantive-review finding
   同族或存在预注册兼容映射；
3. 裁定者证据层满足所使用措辞的最低层级；
4. finding 在 package 生成前已经存在，未根据裁定结果补写。

若裁定者发现真缺陷但与 BenchAudit claim 不同，单列 `independent_other_defect`，不计系统
成功。若 BenchAudit family 对但理由错，单列 `family_match_reason_mismatch`。

## 11. Primary / secondary outputs

Primary：

- D 中 system-aligned externally confirmed count / 86；
- D material-defect rate 与 95% Wilson interval；
- P recognition、N clean rate 与质量门；
- D defect rate − N defect rate，附 Newcombe/Wilson interval；
- 按 evidence wording tier 分层，绝不把 agent consensus 冒充 human confirmation。

Secondary：

- 按 frozen detection method/defect family 的确认率；
- Redux label 与裁定结果的 P/N disagreement；
- adjudicator agreement；
- 86 个 D item 的完整匿名 verdict table；
- 最强的 5–10 条 source-backed case studies。

禁止：只展示成功案例、按结果删裁定者、把 abstention 算 clean 或 defect、把 166 当随机
总体样本外推到全部 5,700 题。

## 12. Package builder 必须测试的攻击面

1. 121/119/86 三层计数与三个 ID-set SHA 可复算；
2. 两个 operational-only `ok` item 不进入 D；
3. unknown-only item 不进入 D；
4. `expert` 不进入 P/N；
5. D=86 census，P/N 各 40 且来源池不重叠；
6. subject quota 与不足重分配完全确定；
7. 相同 salt 逐字节重放，相异 salt 改变 blind IDs/order但不改变集合；
8. public row 无 class、label、subject、source ID、finding 或 rationale；
9. 三类 public schema 逐键相同，无法由字段存在性识别类别；
10. mapping/salt 不在 public package 或 Git diff；
11. malformed/duplicate/missing adjudication row fail closed；
12. lock 之前 scorer 拒绝 reveal；
13. agent-only verdict 无法进入 human-confirmed metric；
14. defect-family 不匹配不能计 system-aligned success；
15. fresh clone 测试不依赖未提交 mapping 或 salt。

## 13. 完成线

本阶段首先完成 package 与 commitments，不在当前有历史上下文的会话中执行裁定。裁定包
交给至少一个无历史上下文的新会话；若目标是论文头条，随后必须有人类专家确认层。

