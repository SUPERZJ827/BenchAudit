# BenchAudit 静态审计完整逻辑（供 Claude 独立复核）

> 目的：让独立审阅者直接按照当前代码验证 BenchAudit 的静态审计路径，而不是根据历史报告或作者总结判断。
>
> 代码快照：分支 `fix/provenance-contract-20260727`，基准 commit `1860771`。
>
> 本机对应 worktree：`/tmp/benchaudit-released-results`。不要直接在其他旧分支上核查本文声明。
>
> 最近一次全量验证：`pytest -q` → **730 passed**；`python -m unittest discover tests/ -q` → **201 tests OK**。

---

## 0. 请 Claude 如何使用这份文档

这不是一份“实现正确性证明”，而是代码导航与待核查声明。请 Claude：

1. 逐项回到代码确认，不要因为本文写了“fail-closed”就默认它真的 fail-closed。
2. 优先构造陌生 schema、边界编码、空清单、部分数据、重复 ID、错误 mapping receipt 等反例。
3. 对每个 `confirmed` 场景同时检查：
   - detector 的前提是否成立；
   - evidence payload 是否可伪造；
   - validator 是否从 live item / live dataset 重新计算；
   - mapping 是否可能把语义不同的字段映射到同一 canonical slot。
4. 对每个“0 finding”场景检查 coverage ledger，不能把未执行、失败或不适用误称为 clean。
5. 将问题按以下等级报告：
   - P0：能够让错误 finding 进入 `confirmed`；
   - P1：系统性产生大量 review 假阳性，或静默漏掉整个 benchmark 家族；
   - P2：coverage、可复现性、提示信息或运维边界不准确。

建议先运行：

```bash
cd /tmp/benchaudit-released-results
git rev-parse HEAD
pytest -q
python -m unittest discover tests/ -q
```

关键代码入口：

- `benchcore/cli.py:875`：主 `audit` 命令。
- `benchcore/field_mapping.py:294`：字段推断。
- `benchcore/loader.py:404`：canonical item 和 mapping receipt。
- `benchcore/auditor.py:58`：item/dataset checker 执行和 coverage ledger。
- `benchcore/promotion.py:1320`：证据等级裁决。
- `benchcore/report.py:57`：最终报告。

---

## 1. 本文所说的“静态部分”是什么

### 1.1 纳入范围

“静态审计”指不调用远程 LLM、不生成候选程序、不启动 benchmark 执行环境，仅根据已经存在的下列材料进行检查：

- benchmark 记录字段；
- task、choices、gold、aliases；
- output contract、evaluator 声明；
- 本地附件路径、manifest、rubric 元数据；
- 数据集内其他记录；
- 已经随数据发布的安全算术表达式或 solver 结果。

它包括三种不同强度的能力：

1. **结构规则**：缺字段、重复 ID、路径不存在、schema drift。
2. **声明契约 replay**：用 BenchAudit 自己的 evaluator model 重放 gold、aliases 和变体。
3. **独立 live replay**：重新读取当前 item、当前完整数据集或固定文件字节验证证据。

### 1.2 不纳入静态主路径

以下模块即使与静态结果一起出现在报告中，也不是本文意义上的纯静态判断：

- 所有 `llm_*` auditor；
- `taskcontract` 输出文件名抽取；
- `ExecutionEvaluatorAuditChecker`；
- `CodeExecVerifier`；
- `ValueRecomputeChecker`；
- Workspace rubric grounding 的 LLM 路径；
- 任何主动运行 benchmark task/agent 的实验。

### 1.3 “零 API”不等于“confirmed”

下列信号可以完全离线计算，但中央策略仍只允许 `review`：

- 历史模型回答错误率；
- released results 的 evaluator disagreement；
- TraceBundle 中重复运行或 identical-output disagreement；
- pattern memory 匹配；
- 已发布 solver answer 与 gold 的差分；
- 没有独立 attestation 的历史执行 payload。

原因：它们是候选排序或观察性证据，不是对 benchmark 契约的独立证明。

---

## 2. 端到端数据流

主流程不是“正则扫 JSON”，而是：

```text
输入文件
  ↓
load_rows：严格读取 JSONL/JSON/CSV/TSV/Parquet
  ↓
infer_mapping / explicit mapping：原字段 → canonical slots
  ↓
build_items：BenchmarkItem + row_uid + source hash + mapping receipt
  ↓
scan_benchmark_package：识别 artifact 类型
  ↓
detect_benchmark_family / build_audit_plan
  ↓
组装 core item checkers
  ↓
组装 method item checkers（除非 --basic-only）
  ↓
组装 dataset checkers（除非 --basic-only）
  ↓
逐 item 执行，可多线程；每个 checker 单独记录 coverage
  ↓
dataset-level 执行与 target_row_uids 校验
  ↓
LLM evidence fusion（纯静态运行通常无新增结果）
  ↓
central promotion：confirmed / review / unknown
  ↓
choice-encoding dataset finding 合并
  ↓
report：findings 与 coverage ledger 分开输出
```

重要性质：

- 多线程只改变完成顺序，结果按原始 item 顺序重新合并。
- `item_id` 是 benchmark 数据，可能重复；内部 identity 使用 `row_uid`。
- 每行同时保存 `source_row_sha256`，防止 finding 被错误 join 到改变后的数据。
- checker 异常默认被隔离为 coverage failure，不应终止整批审计。
- 空 finding 只叫 `completed_no_finding`，不叫 clean。

---

## 3. 输入加载

实现：`benchcore/loader.py:83`。

支持：

- `.jsonl`
- `.json`
- `.csv`
- `.tsv`
- `.parquet`（需要可选 `pyarrow`）

关键规则：

- JSONL 每个非空行必须是 object。
- JSON list 内出现非 object 时整批报错，不静默丢行。
- JSON wrapper 只识别 `data/items/examples/rows` 等明确 list。
- 不支持的后缀直接失败。
- `--offset`、`--limit` 和 sample manifest 在 canonicalization 前保留原始 source index。

Claude 应检查：

- 空文件、混合 object/scalar、重复 source index；
- CSV 字符串类型对 mapping 类型判断的影响；
- JSON wrapper 中同时存在多个候选 list 时的选择是否可歧义。

---

## 4. 字段映射

实现：

- 候选字段与推断：`benchcore/field_mapping.py`
- canonical item 和 receipt：`benchcore/loader.py:404`

### 4.1 Canonical slots

每行被映射到：

| canonical 字段 | 常见源字段示例 |
|---|---|
| `item_id` | `item_id/id/instance_id/task_id/question_id/uid` |
| `task` | `question/prompt/instruction/task/problem/query/input` |
| `context` | `context/passage/files/attachments/schema/table/repo` |
| `choices` | `choices/options/answer_choices/candidates` |
| `gold` | `gold/answer/target/label/reference/gold_sql` |
| `aliases` | `aliases/accepted_answers/equivalent_outputs` |
| `output_contract` | `output_contract/expected_output/output_format/answer_type` |
| `evaluator` | `evaluator/metric/rubric/tests/checker/scoring` |
| `metadata` | `subject/domain/source/split/version/error_type/...` |

### 4.2 自动推断算法

`infer_mapping` 不是只看第一行：

1. 在所有行、最多四层嵌套路径中找同名候选。
2. 对每个候选统计：
   - 非空覆盖率；
   - 类型兼容率；
   - 原始候选优先级。
3. 按覆盖率、类型兼容率、候选优先级排序。
4. 如果高覆盖候选在重叠行上值不一致，标记 `ambiguous`。
5. 某行主字段为空时，inferred mapping 可以尝试同一 canonical 字段的备选路径，并记录 `fallback_used`。

### 4.3 Mapping receipt

每个 `BenchmarkItem.metadata["_mapping_provenance"]` 包含：

- receipt version；
- source：`inferred/explicit/generated_adapter`；
- trust domain；
- activation mode；
- exact field bindings；
- bindings SHA-256；
- live record schema SHA-256；
- 每个 canonical 字段的 row status、resolved key、mapping status。

这不是普通日志，而是 promotion 的前置条件。

### 4.4 映射信任域

中央 promotion 会区分：

- 用户显式 mapping；
- host programmatic mapping；
- inferred mapping；
- registry 已独立验证的 generated adapter；
- shadow / 自签名 generated adapter。

AI adapter 即使给自己写了正确 fingerprint，也不能自动获得 confirmation；必须回 registry authority 重放 receipt。

### 4.5 最高风险点

Claude 必须重点检查这些字段别名：

- retrieval 数据的 `candidates` 可能是文档池，不是答案 choices；
- `target` 可能是外部文档 ID，不是 choices namespace；
- `reference` 可能是 artifact，不是 scalar gold；
- `tests/rubric` 可能是 agent evaluator，而不是 scalar evaluator；
- `input` 可能是 task，也可能是上下文数据。

历史上 `candidates + target` 被误映射为 MCQ 并产生 confirmed 误报，因此这部分是最高优先级红队面。

---

## 5. Package scan、family detection 和 planner

实现：

- `benchcore/package_scan.py:105`
- `benchcore/planning.py:111`
- `benchcore/planning.py:317`

### 5.1 Family

当前 planner 识别：

- `generic`
- `swebench`
- `workspacebench`
- `terminalbench`
- 内部还使用 `code/rubric` capability 标签

信号来自：

- 文件名和 artifact kind；
- 前 100 个 canonical item 的 raw keys；
- evaluator/output contract 的类型文字；
- source code、rubric、test、workspace manifest 等结构。

### 5.2 Auto profile

`--profile auto`：

- 自动识别 family；
- 只执行 planner 选中的 checker；
- **不会因为自动识别出 WorkspaceBench 就自动打开付费 LLM**；
- 未提供 LLM/execution capability 时，对应方法标 `skipped`。

### 5.3 显式 profile

`--profile generic/swebench/workspacebench/terminalbench`：

- family confidence 设为 1；
- core checkers 仍保留，profile 是叠加策略，不是整套替换。

特别注意：

- Workspace/Terminal 不要求 scalar gold，因此删除 `OracleChecker`。
- Workspace/Terminal 的 `TaskSpecChecker` 关闭宽泛 ambiguity 规则。
- Workspace/Terminal 的 `ContextChecker` 关闭宽泛 version risk。
- Workspace 增加 `WorkspaceArtifactInvariantChecker`。
- SWE-bench 增加 `SolutionLeakChecker`。
- 显式 `--profile workspacebench` 当前还会打开 grounded rubric 和 rubric-contract LLM 路径，因此不等于纯静态运行。

### 5.4 `--basic-only`

只保留 core checkers 和 family 必要调整，不运行：

- method checkers；
- dataset checkers。

因此 basic-only 的“0 finding”不能与完整默认审计的“0 finding”比较。

---

## 6. Core item checkers

默认列表：`benchcore/checkers.py:674`。

### 6.1 `TaskSpecChecker`

实现：`benchcore/checkers.py:142`。

检查：

- task 缺失 → `missing_task`；
- task 提到 passage/figure/table/file/database，但 canonical context 无对应材料 → `missing_context`；
- task 使用 latest/current/best/most appropriate 等上下文敏感词，且无 source/version/date/domain → `ambiguous_goal` review。

防误报：

- 内嵌长 passage/table 可以视为已提供 context；
- Workspace/Terminal profile 关闭宽泛 ambiguity 检查。

### 6.2 `ContextChecker`

实现：`benchcore/checkers.py:197`。

检查：

- context value 看起来像文件路径且文件不存在 → `inaccessible_attachment`；
- task 有 as-of/version/latest/current 等版本词但 metadata 无版本信息 → `context_version_mismatch_risk` review。

边界：

- 只有字符串且符合路径外形才会访问文件系统；
- relative path 相对 `--root`；
- Workspace 使用更严格的 allowed-root containment，见第 9 节。

### 6.3 `OutputContractChecker`

实现：`benchcore/checkers.py:247`。

检查：

- 没有 output contract、choices、evaluator → `missing_output_contract` review；
- task 要 approximate/estimate，但 evaluator 被建模为 exact numeric → `output_format_overstrict_risk` review；
- 数值题提到单位，但 task 和 contract 都未明确单位输出规则 → `missing_accepted_alternatives` review。

已有降噪：

- “how many minutes / how much money / what is the area”等问题本身已指定单位，不重复报警；
- “约需要多少辆车/多少组”这类离散计数不自动当作 tolerance 缺失。

### 6.4 `OracleChecker`

实现：`benchcore/checkers.py:310`。

检查：

- scalar-answer profile 缺 gold → `missing_oracle`；
- choices 存在且 gold 无法映射 → `invalid_choice_gold`；
- choices 归一化后重复 → `duplicate_choices`；
- 严格算术形式语言与 gold 不符 → `wrong_gold_answer`。

#### Choice 映射

支持：

- A/B/C；
- `(C)`、`C.`、`C. option text`；
- choices dict 的 key/value；
- 选项全文；
- 甲乙丙丁；
- 0-based / 1-based 数字候选；
- multi-answer 逐组件判断；
- NFKC 全角归一化。

数字标签可能同时符合 0-based 和 1-based 时，视为 evaluator interpretation gap，不直接判 invalid。

#### 算术证明语言

只接受整句：

```text
What is <decimal arithmetic expression>?
Calculate <decimal arithmetic expression>
Compute <decimal arithmetic expression>
```

表达式只允许：

- 十进制数字；
- `+ - * / // % **`；
- 括号；
- 水平空白。

不接受：

- percent、power、divided by 等自然语言；
- 单位；
- 引用/例子；
- 跨行文本；
- 找错题；
- 分数/单位 gold；
- 只匹配 task 前缀。

这是为了避免把 “What is 15 percent of 200?” 截成 `15` 后自动 confirmed 的历史问题。

### 6.5 `EvaluatorChecker`

实现：`benchcore/checkers.py:410`。

检查：

- 有 gold/output contract 但 evaluator 缺失 → `missing_evaluator`；
- evaluator 拒绝明确声明的 aliases → `overstrict_evaluator`；
- exact evaluator 拒绝格式保持变体 → `output_format_overstrict_risk` review；
- evaluator、output contract、choices 都不足以定义成功 → `underconstrained_evaluator_risk` review。

Agent-style output contract 无 scalar gold 时，rubric/tests 是 oracle；缺 evaluator 被当作结构性 scoring gap。

---

## 7. 默认 method checkers

列表：`benchcore/methods.py:715`。`--basic-only` 时不运行。

### 7.1 `TaskIntegrityChecker`

实现：`benchcore/methods.py:219`。

只产生 review，检查：

- 时间范围缺失；
- 未命名 research/study/report；
- 缺 blank 或截断命令；
- mojibake、电子表格日期转换、截断指数等 presentation corruption。

### 7.2 `ContractConsistencyChecker`

实现：`benchcore/methods.py:168`。

仅处理 scalar/set answer contract，不把 Workspace JSON/PDF artifact 容器强行解释成 scalar evaluator。

检查：

- choices 与 numeric/free-text contract 冲突；
- JSON output contract 与 exact/numeric/choice evaluator 冲突；
- numeric output contract 与 choice evaluator 冲突。

注意：当前 proof basis 被标记为 `same_heuristic_replay`，上限是 review，不应 confirmed。

### 7.3 `EvaluatorReplayChecker`

实现：`benchcore/methods.py:32`。

将 gold 同时作为 prediction 和 gold，调用 BenchAudit 的声明 evaluator model：

- evaluator 连自己的 gold 都拒绝 → `gold_rejected_by_evaluator`。

它不是执行 benchmark 自带代码，而是重放 BenchAudit 的 evaluator abstraction。

### 7.4 `MetamorphicAnswerChecker`

实现：`benchcore/methods.py:65`。

生成语义保持变体：

- choice label/text/小写/标点；
- numeric `6/6.0/6.00/006`；
- normalized exact 的空格/大小写；
- set/compound 重排或规范形式；
- declared aliases。

若 evaluator 拒绝，产生 `metamorphic_inconsistency` review。

### 7.5 `EvaluatorMutationChecker`

实现：`benchcore/methods.py:110`。

生成明显错误候选：

- 非 gold choices；
- numeric `+1`、取负；
- unrelated sentinel；
- empty answer；
- gold 加矛盾 sentinel。

错误 mutation 被 evaluator 接受 → `evaluator_mutation_survived` review。

### 7.6 `ExecutableEvidenceChecker`

实现：`benchcore/methods.py:332`。

只读取记录中已经存在的：

- `executable_checks`
- `execution_checks`
- `oracle_checks`

且只执行受限 AST 的 `python_expr`：

- 常量；
- 安全算术运算；
- `abs/ceil/floor/round/min/max`。

检查：

- 表达式不能复现 expected → `invalid_executable_evidence`；
- embedded final answer 与 gold 冲突 → `executable_evidence_gold_conflict`。

这里不是运行任意 Python，不允许 attribute/import/file/network。

### 7.7 `DifferentialCandidateChecker`

实现：`benchcore/methods.py:405`。

读取记录内已有的：

- `math_solution_verification`
- `solver_result`
- `candidate_solution`

若已有候选答案与 gold 不同，产生 `solver_gold_disagreement` review。

候选 confidence 只改变 review 排序信号，不能成为 confirmed proof。

---

## 8. 默认 dataset checkers

列表：`benchcore/methods.py:725`。

### 8.1 `DuplicateConflictChecker`

实现：`benchcore/methods.py:461`。

两类索引：

1. `item_id` 分组：
   - 重复 ID → `duplicate_item_id`。
2. canonical signature 分组：
   - signature = normalized task + context + choices + output contract；
   - 相同 signature、不同 gold → `conflicting_duplicate_oracle`；
   - 相同 signature、相同 gold → `duplicate_task` review。

Dataset finding 必须声明 `target_row_uids`，不能只靠可能重复的 item ID。

### 8.2 `SchemaDriftChecker`

实现：`benchcore/methods.py:536`。

条件：

- 至少 5 条；
- 对每条形成 `(task, context, output/choices, gold, evaluator/choices)` presence pattern；
- 找 dominant pattern；
- minority 占比至少 2% 才产生 `schema_drift` review。

它只检查核心 artifact 可用性差异，不证明 minority 一定错误。

### 8.3 `ChoiceEncodingContractChecker`

实现：`benchcore/methods.py:577`。

目的：防止一种合法但未知的 gold 编码被放大成 N 条 item-level critical。

逻辑：

1. 按 declared label source、labels、choice count、schema keys 分组。
2. 若 gold 能映射到 choice，但不是 declared label → dataset-level encoding mismatch。
3. 若 gold 暂时不能映射：
   - 检查 gold token 基数是否与 choice count 一致；
   - 检查分布/namespace 是否形成稳定编码；
   - 必要时提取覆盖 95% 的 dominant namespace；
   - 将离群行排除后产生一条 dataset review。
4. 后处理删除被该 dataset finding 覆盖的逐条 `invalid_choice_gold` candidate。

已知边界：

- 结构双射不能发现“全表标签系统性循环移位”，那需要语义/verifier；
- 小样本、筛选子集、某个 choice position 从未出现都可能降低可识别性；
- `--limit/--offset` 会改变 dataset proof 的统计前提。

---

## 9. WorkspaceBench 静态专用检查

实现：`benchcore/workspace_invariants.py:525`。

仅在 Workspace schema 存在时启用。

### 9.1 路径 containment

- 所有 `input_files` 必须落在显式 allowed roots；
- existing symlink 先 resolve 再判断 containment；
- 越界路径是 security/coverage 问题，不应被当作已验证的 benchmark 缺陷；
- 文件过大或无法读取时保持保守。

### 9.2 Manifest replay

当 `data_manifest` 和 materialized input files 都存在时：

- 物理文件名；
- 去除 Workspace hash prefix 后的逻辑名；
- `stored_relpath`

三者交叉核对。manifest entry 找不到 materialized file → `artifact_data_gap`。

### 9.3 同名不同内容

若同一逻辑 filename 对应多个 contained materialized files：

- 读取字节；
- 比较 size + SHA-256；
- 内容不同 → `ambiguous_input_filename`。

这是 flat runner view 下必然 shadow/overwrite 的客观冲突。

### 9.4 Dependency graph

只在 benchmark 明确声明 `workspace_inventory_complete=true` 时检查 dangling endpoint。

原因：task-local `data_manifest` 不是完整 role workspace。若不要求 complete receipt，会把 workspace 中合法的共享文件误报为缺失。

### 9.5 重复元数据一致性

检查：

- raw `output_files` vs canonical output contract；
- raw rubrics vs canonical evaluator rubrics；
- `rubric_types` 数量 vs rubrics 数量。

### 9.6 Reference generator heuristic

扫描 agent-visible input package 中疑似生成 reference output 的脚本：

- 文件名命中 generator/gold/reference 模式；
- 文件体命中 output save / reference-generation 模式。

只产生 `solution_leak` review，因为静态命中没有证明：

- 与 hidden oracle 等价；
- agent 实际可见；
- 能改变得分。

即使 runner visibility transcript 匹配，也仍需 oracle equivalence 和 score impact 才能升级。

---

## 10. SWE-bench 静态 leak 检查

实现：`benchcore/swe_leak.py`。

静态阶段比较 problem statement / hints 与 reference patch/solution，寻找：

- reference-only identifier；
- patch token/代码片段重合；
- 过度具体、足以还原 solution 的提示。

静态命中保持 review。可选 LLM confirmation 仍属于 model judgment，不会自动 confirmed。

---

## 11. Terminal/Harbor 静态模块

实现：`benchcore/terminal_audit.py:69`。

这是单独的 task-directory 静态审计模块，不是主 `audit` 默认 checker。

它安全读取 task 目录内有限大小的文本文件，不跟随 symlink，检查：

- exact mutable system package pin；
- runtime network dependency；
- resource headroom 风险；
- overstrict directory/file tests；
- 隐含 input immutability；
- host CPU/environment leakage。

全部为 review。静态源码证据不能证明 task 在真实环境必然失败。

---

## 12. GDPval 客观 replay 模块

实现：`benchcore/gdpval_objective.py`。

它包含：

- record schema integrity；
- rubric representation；
- artifact manifest reference；
- duplicate rubric ID；
- rubric column/internal contradiction；
- task/rubric deliverable filename、格式；
- workbook header 与 pinned XLSX bytes replay；
- dataset-level duplicate rubric ID。

这一模块有一组精确注册的 promotion tuples，只有 live record 或 pinned workbook bytes 重放成功才可 confirmed。

注意：它不是 generic default checker；通常由 GDPval 专用脚本/adapter 构建 items 后运行。

---

## 13. Evaluator abstraction

实现：`benchcore/evaluators.py`。

静态 replay 支持：

- exact；
- normalized exact；
- numeric；
- choice；
- set；
- compound；
- ratio 等 answer contract。

### 13.1 文本规范化

- Unicode NFKC；
- trim；
- lower；
- whitespace collapse。

Loose normalize 还会去 punctuation 和 articles。

### 13.2 Choice 解析

不要把 `type=multiple_choice` 理解成“gold 必须是 A/B/C/D”：

- MCQ type 只证明任务家族；
- label namespace 必须来自明确 labels/index_base/format；
- 未声明 label namespace 时依赖 dataset leave-one-out 统计；
- choices dict、选项全文、本地化标签、多选必须保守处理。

### 13.3 这里没有运行 benchmark 原 evaluator

`evaluate_answer` 是 BenchAudit 根据声明建模的 evaluator，不是随意执行 benchmark-supplied code。

因此：

- model replay 可发现声明自相矛盾；
- 不能证明真实 harness 的全部行为；
- 没有独立执行 transcript 的结果不能冒充真实 harness proof。

---

## 14. Central promotion

实现：

- proof registry：`benchcore/promotion.py:908`
- dataset proof registry：`benchcore/promotion.py:942`
- decision：`benchcore/promotion.py:1320`

### 14.1 Severity 与 evidence tier 分离

Severity：

- critical
- major
- minor
- review

Evidence tier：

- confirmed
- review
- unknown

`critical` finding 可以只有 `review` 或 `unknown` evidence；严重性不能替代证据强度。

### 14.2 精确三元组授权

Confirmation 不是授予 checker class，而是授予：

```text
(detection_method, evidence_level, defect_type)
```

新增 checker 或新增 evidence level 默认没有 confirmed 权限。

### 14.3 裁决顺序

简化后的顺序：

1. operational scope → `unknown`；
2. mapping-sensitive finding 先检查 mapping receipt；
3. memory-derived → `review`；
4. released-result / historical-trace-derived → `review`；
5. LLM/model-derived → `review`；
6. originating checker 明确 `review_only` → `review`；
7. same-heuristic replay → `review`；
8. dataset validator 对完整 live items 重放；
9. unattested execution proof 保持 review；
10. objective validator 对 live item/bytes 重放；
11. 未注册 tuple → `review`。

任何 validator exception 都 fail closed，不保留 confirmed。

### 14.4 当前可 confirmed 的主要静态 tuple

按代码注册表，主要包括：

- canonical task 确实缺失；
- 严格算术形式语言 replay；
- declared aliases 被 evaluator 拒绝；
- gold 被声明 evaluator model 拒绝；
- Workspace manifest / dependency graph / filename collision / metadata replay；
- embedded safe expression replay；
- duplicate ID、conflicting duplicate oracle 的 live dataset replay；
- invalid choice gold 的 dataset namespace replay；
- GDPval record/artifact/rubric/workbook replay。

`ContractConsistencyChecker` 虽然有 validator，但因为 basis 是 same heuristic，保持 review。

### 14.5 Mapping fail-closed

对 mapping-sensitive artifact：

- live item 缺失 → 不信；
- provenance 缺失 → 不信；
- receipt version 错 → 不信；
- field binding hash 不符 → 不信；
- live schema hash 不符 → 不信；
- dependent field unresolved/ambiguous → 不信；
- generated adapter registry receipt 无法重放 → 不信。

结果降为 `unknown`，因为 finding 可能只是 mapping 错。

### 14.6 “完整 live dataset”的实际边界

Dataset proof validator 接收的是 `run_audit` 当前构造的 `items`，而 `items`
已经经过 `--manifest`、`--offset`、`--limit`。因此代码中的
`complete_live_record_set` 实际是“当前审计切片中的全部 live rows”，不必然是
源 benchmark 的全部记录。

这是需要 Claude 独立判断的风险点：

- 小切片是否仍有资格产生 dataset-level `confirmed`；
- 抽样是否会制造虚假的 choice namespace 一致性；
- duplicate/conflict proof 是否应该区分 `full_source` 与 `sampled_slice`；
- report 是否显式披露 dataset proof 使用的范围。

---

## 15. Coverage ledger

实现：`benchcore/auditor.py`、`benchcore/coverage.py`。

每个 item × checker 记录：

- planned；
- eligible；
- attempted；
- completed；
- finding count；
- substantive finding count；
- checker scope；
- terminal status；
- lifecycle；
- reason；
- row_uid。

状态包括：

- `completed_no_finding`
- `finding`
- `ineligible`
- `unsupported`
- `abstained`
- `operational_failed`
- `security_blocked`

原则：

```text
completed_no_finding != clean
ineligible != passed
operational_failed != no defect
security_blocked != inaccessible benchmark artifact defect
```

Dataset checker 会将一次全局执行投影到逐行 ledger，并依据 `target_row_uids` 关联 findings。

Post-checker fusion 若新增 finding，也必须补写 ledger，不能在 ledger 关闭后静默出现结果。

---

## 16. 后处理

### 16.1 LLM evidence fusion

实现：`benchcore/auditor.py:670`。

纯静态运行通常没有作用。混合运行时：

- 多 LLM auditor 一致只增加 corroboration metadata；
- `needs_expert` 强制 review；
- auditor 相互矛盾新增 operational `auditor_contradiction`；
- LLM finding 本身仍由 promotion 锁在 review。

### 16.2 Choice encoding consolidation

如果 dataset-level checker 识别出稳定的未知 encoding：

- 删除被它覆盖的 item-level `invalid_choice_gold` candidates；
- 保留一条 dataset-level `choice_encoding_contract_mismatch` review。

目的是避免“一种未知编码 → N 条 critical”。

---

## 17. 输出报告

最终报告至少包含：

- source/input identity；
- field mapping；
- methods run；
- benchmark package；
- audit plan；
- violations；
- evidence tier distribution；
- proof kind distribution；
- artifact/defect/method/scope/severity distribution；
- coverage ledger；
- runtime metadata；
- implementation source manifest；
- git commit 与 dirty 状态；
- LLM/execution/egress metadata（若启用）。

报告中的主要计数口径：

- `confirmed_count`
- `review_signal_count`
- `unknown_count`
- `affected_items`
- `affected_rows`
- `confirmed_affected_items`

Claude 应检查 duplicated item ID 下 item-level 和 row-level 统计是否一致。

---

## 18. 与静态主路径相邻、但不能混淆的离线模块

### 18.1 Response triage

`benchcore/response_triage.py:407`

- 按稳定 item ID join 多模型 per-item correct/incorrect；
- 拒绝重复 `(item_id, model_id)`；
- 计算 error rate、disagreement、心理测量候选信号；
- 所有输出 review-only。

### 18.2 TraceBundle

`benchcore/trace_bundle.py:750`

- 规范化历史 run、artifact、evaluation；
- 检查 repeated-run disagreement；
- identical bytes 被不一致评分；
- run/evaluator coverage；
- 不主动执行 task；
- 观察性 finding review-only；
- 每条候选强制发射
  `evidence_level=historical_trace_observation` 和稳定的
  `trace_bundle_candidate_id`，调用方无法覆盖；method 改名后中央 gate
  仍可识别。

### 18.3 Released results

`benchcore/released_results.py:460`

- 将公开 prediction/reference/verdict 映射到 TraceBundle；
- 检查 evaluator disagreement、diagnostic payload、历史排名影响；
- 可进行 SQL parser replay，但历史 verdict 本身不构成 proof；
- 每条候选 evidence 强制携带
  `evidence_level=released_result_observation` 和稳定的
  `released_result_candidate_id`；
- promotion 中有独立 historical-result hard ceiling；即使未来消费者修改
  detection method 名，只要携带实际候选 evidence，仍会被识别为
  `historical_result_observation` 并锁在 review。

### 18.3.1 Producer-to-promotion 通用护栏

- promotion 中当前有效的 provenance sentinel 使用显式集合注册；
- CI 用 memory、released-results、trace 的真实 producer 输出检查注册
  key 确实被发射；
- CI 将 method 改成 `objective_recompute` 等无关名称后重新执行中央
  promotion；
- 只手工往 finding 填一个 sentinel 的测试不算完整 contract test；
- 从未由 producer 发射的 5 个伪哨兵已删除，避免把不存在的防线计入
  纵深防御。

### 18.4 Pattern memory

- 只做 verifier routing / candidate prioritization；
- 不改变原 audit findings；
- raw schema-key fingerprint 默认关闭；
- 中央 promotion 根据 memory evidence key 识别来源，即使 method 被改名仍锁 review。

---

## 19. `taskcontract` 的准确边界

实现：`benchcore/task_contract.py`。

它不是静态 checker，而是 **LLM 抽取 + 静态 replay**：

1. 只向模型发送 `item_id` 和 `task`。
2. 模型只允许返回显式输出 filename/relative path。
3. 每个 path 必须：
   - 有 task 原文 exact evidence span；
   - path 本身出现在 evidence；
   - 是安全 relative path；
   - 不包含 absolute path、`..` 或控制字符。
4. 本地代码只把下列字段视为输出 inventory：
   - `output_files`
   - `outputs`
   - `expected_files`
   - `deliverables`
   - `output_manifest`
5. `reference_files` 默认属于输入附件，不作为输出清单；输入侧还识别
   `input_files`、`inputs`、`attachments`、`data_files`、
   `source_files` 和 `input_manifest`。
6. 若模型抽取的 path 明确位于输入 inventory、且不在输出 inventory，
   本地 replay 将它标为 input/output role ambiguous 并抑制，不把模型的
   角色分类错误转成 benchmark finding。
7. 无输出 inventory → 不报 benchmark defect。
8. 显式空 inventory → 视为已知缺失。
9. 非歧义 mismatch → 一条 severity=`review`、
   evidence tier=`review` 的 `task_artifact_contract_mismatch`。
10. 模型输出非法 → operational `llm_audit_failure` / unknown。

inventory 中一个对象若同时有 `path`、`relative_path`、`filename`、
`file`、`name`，按上述固定顺序取值，不能依赖 Python set/hash 的随机
迭代顺序。

对示例：

```text
请总结1.txt,2.txt,.....100.txt为123.txt
```

只提取：

```json
{"output_requirements": [{"path": "123.txt", "evidence": "123.txt"}]}
```

明确不做：

- 不展开 1–100；
- 不检查 100 个输入是否存在；
- 不判断输出是否总结了全部输入；
- 不判断总结质量。

必须保留的回归断言：

```text
input_files 只有 1.txt + output_files 是 123.txt → 0 finding
output_files 是 wrong.txt → 1 条 output filename mismatch review
模型把 input_files 中的 1.txt 抽成 output → 抑制并记录 role ambiguity
只有 reference_files=data.csv → 不视为 output inventory
多字段 manifest 在不同 PYTHONHASHSEED 下 → replay 完全一致
```

保守边界：若任务确实要求原地覆盖、输出复用输入文件名，但 output
inventory 没有显式声明该文件，本门禁会选择不报。这里用少量召回换取
陌生 schema 下不把输入附件系统性误报成缺失输出。

另有两条不可识别边界：

1. item 没有显式 input inventory 时，本地 replay 无法证明模型抽出的
   `1.txt` 是输入；若 output inventory 存在且不含它，仍可能产生
   review-only mismatch。不能把“缺少输入清单”直接等价为“它一定是输入”
   并全局抑制，否则会删除真实输出缺失的召回。
2. 输入 inventory 当前只从 `item.raw` 的显式 input-side 字段读取，不从
   `item.output_contract` 猜测。若新 benchmark 有独立的结构化输入契约，
   应由已验证 adapter/mapping receipt 显式声明，而不是让通用 checker
   猜测陌生 contract 的字段语义。

---

## 20. 当前已知能力边界

纯静态方法无法可靠完成：

- 自由文本 task 的深层语义正确性；
- gold factual correctness（除严格形式语言或已有 objective evidence 外）；
- rubric 是否合理、是否超纲的全部自然语言情形；
- output 是否真正满足每条 rubric；
- evaluator code 的真实 runtime behavior；
- 系统性但内部一致的 label permutation；
- 需要外部世界知识、专业规范或时间敏感知识的判断；
- agent 在真实环境中是否会成功。

正确策略不是让静态规则假装覆盖，而是：

- 静态层做低成本、可重放候选；
- LLM 层做语义候选，保持 review；
- 历史结果/轨迹做排序和交叉观察，保持 review；
- 可执行/verifier-rich 领域再尝试独立确认。

---

## 21. 建议 Claude 优先攻击的测试矩阵

### 21.1 Mapping

- retrieval：`query + candidates + target_id`；
- NLI：`premise + hypothesis + label`；
- summarization：`document + summary/reference`；
- code：`prompt + tests + canonical_solution`；
- tabular QA：`table + question + answer`；
- choices 为 dict；
- gold 为 list；
- 中英文/全角/希腊/圆圈标签；
- 同行存在多个高覆盖 task/gold 候选字段。

目标：合法陌生 schema 的 confirmed 必须为 0；不能靠全局降级破坏已注册真阳性。

### 21.2 Arithmetic

- `What is 15 percent of 200?`
- `Compute 100 minus 37.`
- `What is 2 to the power of 10?`
- `What is 12 divided by 4 plus 3?`
- `What is 1 / 2?` + gold 为 `one half`
- 引用中的算式；
- “找出错误算式”。

目标：全部不能进入 strict arithmetic proof。

### 21.3 Choice namespace

- A/B/C/D；
- `(C)`；
- `C. full choice text`；
- choice 全文；
- 0-based；
- 1-based；
- 甲乙丙丁；
- 全角 ABCD；
- 希腊标签；
- 圆圈数字；
- 多选 list；
- dict choices；
- 全数据集一种未知但一致编码；
- 59 行一致 + 1 行离群；
- 小样本 `<21`；
- 某一 position 从未作为答案。

目标：合法编码不产生 item-level confirmed；单个真实 outlier 仍能保留召回。

### 21.4 Mapping receipt

- provenance 缺失；
- receipt version 错；
- bindings hash 错；
- live row schema 改变；
- generated adapter 自签 receipt；
- shadow adapter 冒充 active；
- method 改名但保留 memory/historical evidence key。

目标：任何一条都不能绕过 central ceiling。

### 21.5 Workspace

- symlink 逃逸 allowed root；
- task-local manifest 缺 shared workspace file；
- `workspace_inventory_complete=false` 的 graph endpoint；
- 同逻辑名、相同 bytes；
- 同逻辑名、不同 bytes；
- raw/canonical outputs 顺序不同但集合相同；
- rubric_types 数量不一致；
- generator 文件名命中但 body 不命中；
- body 命中但文件不 agent-visible。

### 21.6 Coverage

- checker eligibility 抛异常；
- checker check 抛异常；
- dataset checker 部分 finding 后抛异常；
- 全部 ineligible；
- `completed_no_finding`；
- security blocked；
- duplicate item ID；
- 多线程完成乱序。

目标：coverage 状态必须准确，不能把失败计入 clean/executed。

### 21.7 Output filename LLM 辅助

- task 明确 `123.txt`，输出 `123.txt`；
- task 明确 `123.txt`，输出 `wrong.txt`；
- 输入缺失但输出正确；
- 无 output inventory；
- 显式空 output inventory；
- 模型虚构 evidence；
- 模型输出 absolute path / `../`；
- task 同时提到多个 input filenames 和一个 output filename。
- 模型把格式合法、原文可锚定的 input filename 错抽成 output；
- `reference_files` 仅表示输入附件；
- 一个 manifest 记录同时包含 `path/name/file`，跨多个
  `PYTHONHASHSEED` 结果一致；
- 原地覆盖、输入输出同名的保守弃权边界。

目标：只检查输出名，永远不把 input coverage 混进来；永远不 confirmed。

---

## 22. Claude 最终应回答的问题

请不要只给“整体架构不错”。需要给出：

1. 是否存在任何陌生 schema 能稳定制造 `confirmed` 假阳性？
2. 是否存在合法 MCQ encoding 被系统性误报？
3. 是否有 checker 的 detector 与 validator 共享同一个错误前提，却仍获 confirmed？
4. 是否能伪造 mapping/memory/history/execution provenance 绕过 ceiling？
5. 是否有 profile/auto planner 声称执行了实际未执行的方法？
6. 是否有 `completed_no_finding` 被报告层误解释为 clean？
7. Workspace 的完整 inventory、path containment、runner visibility 前提是否严密？
8. `taskcontract` 是否严格只处理输出文件名？
9. 哪些静态 finding 的默认 severity 与实际证据等级容易误导用户？
10. 修复建议是否会通过“把全部结果降级”为代价损害真实召回？

建议输出格式：

```text
问题：
复现输入：
当前输出：
期望输出：
根因：
是否影响 confirmed：
最小修复：
需要新增的回归测试：
```
