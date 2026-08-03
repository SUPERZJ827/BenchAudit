# MMLU-Redux `ok` 盲裁定协议 V2：四格对照与机械优先分流

> Freeze date: 2026-08-03  
> Status: **FROZEN_BEFORE ITEM CONTENT INSPECTION, MECHANICAL PREFLIGHT, OR PACKAGE GENERATION**  
> Supersedes: V1 §3、§8 中的三臂设计；补充 V1 §4–§12  
> V1 其余盲化、锁定、证据措辞与 scorer 条款全部继承

## 0. V2 的两个原因

V1 漏掉了 `Redux explicit defect AND system substantive-review` 这一格。只用“Redux 缺陷、
系统未报”的困难正对照，会把裁定者对公认缺陷的敏感度估成下界，无法解释争议池的绝对
命中率。

其次，86 条争议项中可能存在无需语义裁定的机械缺陷。机械能判的必须先给本地可重放
证据；只有机械规则 abstain 的项目才进入盲裁定。

这两个变更在逐题内容检查、机械 verifier 运行和 package 生成之前冻结。

## 1. `expert` 不能混进“Redux 缺陷”

完整历史标签交叉表（把所有非-`ok` 都粗称“缺陷”）是：

| Redux coarse label | system review | system no-review |
|---|---:|---:|
| non-`ok` | 206 | 164 |
| `ok` | 86 | 544 |

但 `non-ok` 包含 32 条 `expert`：system review 10，system no-review 22。`expert` 表示需要
专家/无法直接裁定，不是 explicit defect。用于正对照的严格表为：

| Redux strict label | system review | system no-review |
|---|---:|---:|
| explicit defect | **196** | **142** |
| `expert` abstention | 10 | 22 |
| `ok` | 86 | 544 |

explicit defect 集仍为：

```text
wrong_groundtruth
bad_question_clarity
multiple_correct_answers
no_correct_answer
bad_options_clarity
```

32 条 `expert` 不进入任何裁定臂；报告中单列，不得为满足 40 条配额而使用。

## 2. 机械优先分流（在盲包之前）

### 2.1 输入域

机械 verifier 必须对全部 86 个 D item 运行。是否调用某条规则只允许由冻结 report 的
`defect_type` 决定，不得先看题面再挑规则。

### 2.2 Rule M-DUP-V1：规范化后完全重复的选项

Eligibility：该 item 至少有一个 substantive-review finding 属于：

```text
duplicate_choices
multiple_correct_answers
bad_options_clarity
```

Predicate：

1. source `choices` 是长度至少 2 的 list；
2. 对每个 choice 使用当前已提交 `normalize_choice_for_duplicate()`；
3. 存在两个不同 index 的非空规范化字符串完全相等。

命中只确认 `duplicate_choices` artifact defect；若系统原 claim 是
`multiple_correct_answers`，不得自动升级为“语义上多个正确答案”，报告为
`mechanical_duplicate_supports_option_defect_only`。

### 2.3 Rule M-GOLD-DOMAIN-V1：declared gold 不属于显式选择域

Eligibility：至少一个 substantive-review finding 属于：

```text
wrong_gold_answer
no_correct_answer
multiple_correct_answers
```

Predicate：

1. source `choices` 是长度至少 2 的 list；
2. declared gold 非空且按 `choice_label_to_index(gold, choices)` 无法映射；
3. 所有 declared aliases 也无法映射；
4. evaluator/output contract 明确是 single-choice；若 contract 不明，abstain。

命中确认 `declared_gold_outside_choice_domain`，不确认哪一个选项在语义上正确。

### 2.4 明确不支持的机械化

V2 不实现一般算术求解、事实检索、自然语言蕴含、隐含选项解析或“看起来类型不匹配”规则。
这些容易把语义判断伪装成机械证明。未知结构一律 abstain，不临时加规则。

### 2.5 三值输出与路由

每个 eligible rule 输出恰好一个：

```text
mechanically_confirmed
mechanically_not_triggered
not_applicable
```

只有 `mechanically_confirmed` 且 rule defect 与冻结 finding 兼容的 D item 才移出盲包。
`not_triggered` 不是 clean；它仍进入语义盲裁定。若同一 item 一条规则 confirmed、另一条
abstain，机械 confirmed 结果保留，其他 claim 的未决边界逐项披露。

机械 receipt 必须绑定 source/report/rule code SHA、item ID、输入字段哈希、规范化选项/
映射结果和兼容 finding key；不含 LLM 或网络证据。

## 3. V2 四臂设计

令 `M` 为 §2 真正 mechanically confirmed 的 D item 数。公开裁定包的唯一 item 数为：

```text
(86 - M) + 40 + 40 + 40 = 206 - M
```

裁定者不得获知 `M` 或各臂大小。

### D：语义争议项，census `n = 86 - M`

V1 的 86 条 D 中除去 mechanically confirmed 项，其余全部进入，不再抽样。

### P-agree：双方都报 explicit defect，n=40

母池 196：Redux explicit defect 且至少一个 substantive-review finding。它估计裁定者面对
较显著/双方一致缺陷时的识别率。

### P-missed：Redux 报 explicit defect、系统未报，n=40

母池 142：Redux explicit defect 且没有 substantive-review finding。它估计较隐蔽、系统
漏检缺陷的裁定敏感度。

### N-agree：双方都未报缺陷，n=40

母池 544：Redux=`ok` 且没有 substantive-review finding。它估计裁定者在共识 clean 项上
的过度判错率，同时保留“第三方和系统都可能漏掉”的诚实边界。

## 4. 四臂抽样

D 仍为 census。三个 40-item control arm 分别使用 V1 已冻结 seed，加 domain：

```text
"p_agree"
"p_missed"
"n_agree"
```

每臂独立按 D 的 subject 分布作 largest-remainder quota；不足重分配规则与 V1 完全相同。
组内 rank：

`SHA256(seed || domain || subject || item_id)`

三臂不得共享 item；不得用题面长度、finding confidence、错误类别或人工可读性挑题。
P-agree/P-missed 的 explicit Redux defect subtype 只在解盲后分层报告，不用于二次配额调整。

## 5. 裁定者的完整校准输出

分别报告：

- `S_agree`：P-agree 中判 material defect 的比例；
- `S_missed`：P-missed 中判 material defect 的比例；
- `C_agree`：N-agree 中判 clean 的比例；
- `R_dispute`：D 中判 material defect 的比例；
- `S_agree - S_missed`：公认缺陷与系统漏检缺陷的可见性差异，附 Newcombe interval；
- `R_dispute - (1 - C_agree)`：争议项缺陷率相对共识 clean overcall baseline 的差异。

V1 的可解释性门改为：

```text
S_agree >= 0.70
AND S_missed >= 0.60
AND C_agree >= 0.70
```

P-missed 门较低，是因为该臂按定义连系统也未报、预期更隐蔽。任一不达时仍记
`ADJUDICATOR_NOT_CALIBRATED`，不从三个对照里事后删除最差的一臂。

## 6. 盲化补强

四臂 public row schema 必须逐键、逐类型相同。裁定者不看 auditor 输出，也不得看到：

- 哪些题经过机械 verifier；
- D/P-agree/P-missed/N-agree；
- system reported/unreported；
- Redux label/subtype；
- 各臂数目或 source-pool 数目。

机械 confirmed 项不混入包冒充“容易正对照”；它们单独作为本地可重放硬证据报告。

## 7. Primary 结果分两层

### 7.1 Mechanical headline

`M / 86` 条 MMLU-Redux=`ok` candidates 有本地可重放机械证书。逐条给 rule、source hash、
finding compatibility 与 replay command。即使 `M=0` 也完整报告，不加 V3 规则。

### 7.2 Semantic adjudication headline

在 `86-M` 中，报告 system-aligned external confirmations。沿用 V1 的 evidence wording：
agent-only 只能 supported，不能 human-confirmed。

总的“系统找到的 Redux-`ok` 真缺陷”只能合并：

```text
mechanically confirmed
+ semantically adjudicated AND system-family-aligned AND evidence-tier-qualified
```

两者必须分栏，不能把 agent supported 与 mechanical confirmed 相加后统称 confirmed。

## 8. 新增构造性测试

除 V1 §12 外：

1. coarse 206/164 可复算，且严格拆成 196/142 + expert 10/22；
2. expert 无法进入 P-agree/P-missed；
3. M-DUP exact duplicate 命中、近似但不等同 abstain/not-triggered；
4. M-GOLD-DOMAIN invalid label 命中、合法 label/choice text 不命中；
5. 非 single-choice contract 无论 gold 如何都 abstain；
6. 两条规则各有 confirmed/not-triggered/not-applicable 可达路径；
7. verifier 对全部 86 运行，不能只挑某 method/confidence 的子集；
8. mechanically not-triggered item 仍进入 D；
9. mechanically confirmed 与冻结 finding 不兼容时不能移出 D；
10. 三个 control pools 精确为 196/142/544；
11. P-agree/P-missed/N-agree 各 40、互不重叠、subject quota 可复算；
12. 四臂 public schema 不泄露类别；
13. scorer 同时报两个正对照敏感度，不得合并成一个；
14. mechanical 与 semantic evidence tier 分栏，agent-only 不能混入 confirmed count；
15. fresh clone 测试不依赖密封 mapping、salt 或未提交文件。

## 9. 执行顺序

1. V2 提交；
2. mechanical verifier + tests 提交；
3. 对 86 条运行并提交 mechanical receipt；
4. package builder + tests 提交；
5. 根据冻结 `M` 生成 `(206-M)` 条 public blind package 与密封 mapping；
6. 交给无历史上下文裁定者。

机械结果出来后不得新增规则，也不得改变四臂配额。

