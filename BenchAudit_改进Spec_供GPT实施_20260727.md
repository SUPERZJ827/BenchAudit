# BenchAudit 改进 Spec(供 GPT 实施)

作者:Claude(设计/复核角色)
日期:2026-07-27
基线 commit:main = `b450d4e`,待合 `fix/provenance-contract-20260727` = `1860771`

---

## 0. 这份 Spec 要解决的核心问题

对当前 `promotion.py` 的证明验证器做过统计:

```
可 confirmed 的证明验证器共 32 个,按家族:
 13  gdpval_objective              ← 只对 GDPval
  8  static_rule                   ← 通用
  5  workspace_artifact_invariants ← 只对 Workspace
  2  executable_evidence_replay    ← 通用
  2  dataset_duplicate_scan        ← 通用
  1  evaluator_replay              ← 通用
  1  cross_artifact_consistency    ← 通用

绑定到单一 benchmark 家族:18/32 = 56%
```

**结论:`confirmed` 层一半以上是逐 benchmark 手写的契约重放。**
换一个新 benchmark 就要再手写一批,这是随人力线性增长的手工艺,不是自动化。
所有通用机制(LLM 语义 / memory / trace / released results)都被正确地锁在 `review`。

**因此本 Spec 的唯一北极星指标(可证伪里程碑):**

> **在一个从未有人为它手写过任何证明验证器的 benchmark 上,产出 `confirmed` 缺陷。**

P1、P2 直接攻击这个指标;P3、P4 是卫生项。
**不要为了完成 P3/P4 而推迟 P1/P2。**

---

## P1(最高优先级):元形关系层 —— 第一个真正通用的 confirmed 机制

### 动机

现有唯一通用的"客观确认"机制是 `gold_rejected_by_evaluator`(32 个里的 1 个),严重欠开发。
元形关系(Metamorphic Relations, MR)可以在**不需要 gold 标注、不需要逐 benchmark 逻辑**的前提下,
产出客观可重放的 evaluator 缺陷证据。这条路线在 2026 年的元形测试+LLM 综述里已是主流方向
(见文末参考),而我们已有的 EvalPlus witness 机制本质上就是一个 MR 的特例。

**关键设计约束(必须严格遵守,否则会产生假 confirmed):**
MR 必须按**数据类型**设计,不能按 benchmark 设计。这正是它区别于手写证明的地方。
每条 MR 必须能形式化陈述"这个变换保语义"的理由;**无法形式化保语义的变换,一律不得进入 confirmed,只能 review。**

### 要实现的 MR(按可信度排序,建议按序实施)

**MR-1 `gold_self_consistency`(最高可信度,建议先做)**
- 陈述:benchmark 自己的 gold answer,必须被 benchmark 自己的 evaluator 判为通过。
- 违反 = `gold_rejected_by_evaluator`,**客观 confirmed**(evaluator 与 gold 至少有一个错)。
- 前置:evaluator 可执行。
- 已有部分实现,需要做的是**推广到所有具备可执行 evaluator 的数据集**,而不只是当前注册的那一个路径。

**MR-2 `evaluator_format_invariance`(最高价值,通用性最强)**
- 陈述:对候选答案施加**可证明保语义**的扰动后,evaluator 判定不得翻转。
- 判定翻转 = evaluator 脆弱 = **客观 confirmed 的 evaluator 缺陷**。
- **不需要 gold 是否正确,只需要 evaluator 可执行** —— 这是它通用性的来源。
- 按类型定义扰动,**每种类型必须单独论证保语义**:

  | 答案类型 | 保语义扰动 | 保语义论证 |
  |---|---|---|
  | 数值 | `0.5` ↔ `.5` ↔ `0.50` | 十进制表示等价 |
  | 数值 | 末尾无关空白 | 数值解析不受影响 |
  | 字符串/自由文本 | **仅**首尾空白 | 不改变内容 |
  | MCQ | `A` ↔ `A.` ↔ `(A)` | 选项标识等价(需 benchmark 声明允许) |
  | 代码 | **禁止空白扰动** | Python 缩进有语义,**不保语义** |
  | 代码 | 仅允许:注释增删、末尾换行 | 不改变 AST |

- **实现要求**:每条扰动规则必须带 `semantics_preserving_rationale` 字段;
  没有该字段的扰动**只能产出 review,不得 confirmed**。
- **反向也要检测**:扰动后从 fail 变 pass,说明 evaluator 过宽(`underspecified_evaluator`)。

**MR-3 `mcq_permutation_consistency`**
- 陈述:打乱 MCQ 选项顺序并同步置换 gold 索引后,evaluator 对同一实质答案的判定必须不变。
- 违反 = evaluator 依赖了选项位置 = 客观 confirmed。
- 注意:**必须同步置换 gold**,否则测的是别的东西。已有 choice encoding 处理逻辑要复用,不要重写。

**MR-4 `differential_oracle_witness`(已有,需泛化)**
- 陈述:变异体通过弱 evaluator 但挂在独立强 oracle 上 → 弱 evaluator 不完备。
- 这就是现有 EvalPlus witness。**需要做的是把它从实验脚本提升为正式能力**,
  并接受任意"弱/强 oracle 对",而不是硬编码 EvalPlus。

### 验收标准(预注册,不得事后放宽)

1. **不丢失**:在 GDPval / WorkspaceBench 上,MR 层不得使任何现有 confirmed finding 消失或降级。
2. **零假 confirmed**:注入 100 个"故意合法"的 evaluator(对上述所有保语义扰动都正确不变),
   MR 层必须产出 **0 个 confirmed**。这是精度硬门槛,不达标不得合并。
3. **北极星**:在**至少一个从未手写过证明验证器的 benchmark** 上产出 ≥1 个 confirmed 缺陷,
   且该缺陷经人工独立复核确认为真。
4. **确定性**:同一输入两次运行,稳定摘要哈希逐字节一致。
5. 若验收 3 失败,**保留负结果**,不得通过放宽"保语义"定义来凑数。

### 明确不要做

- 不要用 LLM 生成扰动(不可证明保语义,会污染 confirmed 层)。
- 不要对自由文本做同义改写(不保语义)。
- 不要因为某条 MR 在某 benchmark 上没命中就删掉它。

---

## P2(最高杠杆重构):把 13 个 GDPval 手写证明抽象成 1 个通用检测器

### 观察

逐条读过 13 个 `gdpval_objective` 证明,它们结构完全同构:

> benchmark 在字段 A 里声明了 X,在字段 B 里声明了 X′,A 与 B 按契约必须一致,但实际不一致。

例:`gdpval_task_deliverable_filename_replay` = 任务文本声明的交付文件名 vs rubric 声明的文件名。
`gdpval_rubric_column_replay`、`gdpval_rubric_deliverable_format_replay` 等等,全是同一形状。

**矛盾检测逻辑是 benchmark 无关的;benchmark 相关的只有"哪个字段扮演什么角色"。**
而"字段角色声明"我们已经有机制了 —— verified adapter / mapping receipt。

### 要做的重构

1. 新增**单一**通用检测器 `intra_record_contract_contradiction`。
2. 每个 benchmark 的契约用**声明式数据**表达(JSON/YAML),不是代码:
   ```
   contract_id: gdpval_task_vs_rubric_deliverable_filename
   role_a: {field: task, extractor: declared_filenames}
   role_b: {field: rubric, extractor: declared_filenames}
   relation: must_be_equal_set
   proof_kind: intra_record_contract_replay
   ```
3. 抽取器(`declared_filenames`、`declared_format`、`declared_columns` …)按**类型**实现,
   数量应远少于 13,且跨 benchmark 复用。

### 验收标准

1. **等价性(硬门槛)**:在 GDPval 全量上,通用机制必须复现 13 个手写证明产出的
   **完全相同的 finding 集合与完全相同的 tier**。逐条 diff,不允许"大体一致"。
2. 通过等价性后,**删除**那 13 个手写验证器(否则重构没有意义,只是加了一层)。
3. 把同一套机制应用到 WorkspaceBench 的 5 个手写证明,同样要求等价。
4. **北极星**:把契约声明写给一个**新** benchmark,在**不写任何新代码**的前提下产出 confirmed。
   这一条是判断重构成功与否的唯一标准。

### 风险提示

- 如果发现某些手写证明**无法**用声明式契约表达,**不要强行改造**——
  如实记录它们为"确实需要手写的特例",并统计比例。这个比例本身就是有价值的科研结论:
  它量化了"benchmark 缺陷检测中不可通用化的部分有多大"。

---

## P3(卫生,小改动):执行层区分 timeout 与语义失败

### 问题

`scripts/run_pattern_memory_codecontests_holdout.py:63-66`:

```python
except subprocess.TimeoutExpired:
    return {"passed": False, "error": f"case {index}: timeout", ...}
```

超时被记成 `passed=False`,与"语义判错"在 `passed` 布尔上**不可区分**。
唯一区分标记是 `error` 字符串,而它不进语义哈希。
后果:CodeContests v3 实验中一个慢参考解在并发负载下超时抖动,污染了稳定摘要哈希。

### 最小修复

1. 执行结果增加显式三态:`outcome ∈ {passed, failed, timeout}`,不要用布尔表示三种情况。
2. **评分路径遇到 timeout 必须 fail-loud**(抛出或标记 `indeterminate`),
   而不是静默当作 failed 参与选择或统计。
3. 稳定哈希绑定 `outcome` 三态;timeout 视为 `indeterminate`,该条目不参与语义哈希。

### 验收

- 人为注入一个必然超时的解,两次运行稳定摘要哈希必须一致。
- **不要**回头去救已经正确停放的 CodeContests v3 结论:它在配对 CI 门槛上是独立失败的,
  修确定性不改变那个裁决。这条修复只服务于**下一个** benchmark。

---

## P4(卫生,推广已有护栏):声称-强制执行契约

### 观察

这轮复核发现的 4 个问题**全部是同一类**:

| 声称位置 | 声称内容 | 实际 |
|---|---|---|
| docstring | "改名后仍可识别来源" | 只有一层,改名即绕过 |
| system prompt | "input 文件名不是 output" | 代码零约束,全靠模型自觉 |
| 文档 | "结果确定性" | set 迭代顺序,跨进程翻转 |
| gate 定义 | 10 个哨兵 key | 5 个从未被发射 |

`1860771` 的 producer-to-promotion 护栏封死了其中一个实例。**应当推广成通用规则。**

### 要做的

1. 在 `DESIGN.md` 建立**安全声称登记表**:凡 docstring/文档中出现
   "即使 X 仍然 Y"、"无法绕过"、"确定性"、"永不 Z" 这类断言,必须登记。
2. 每条登记的声称,必须有一个**会红的测试**:即变异测试——
   人为破坏该保证,测试必须失败。(`1860771` 已经做到,以它为模板。)
3. CI 增加检查:登记表中每条声称都能定位到对应测试。

### 验收

- 对每条已登记声称做一次变异测试,确认全部会红。
- 我已验证 `1860771` 的护栏满足此标准(注入 `never_emitted_fake_key` → 立即 FAIL,恢复 → 绿)。

---

## P5(不要做的事 —— 明确劝阻)

1. **不要继续在 CodeContests 的 test/valid/train 上调参**。三个 split 都已用于开发或验证。
2. **不要用多模型共识把 review 提升为 confirmed**。共识只能改善 review 的分诊优先级,
   不构成独立证明。文献里的 frontier-model-consensus 方法用于**发现**,不用于**确认**,不要混淆。
3. **不要扩大 pattern memory 的路由权重**。当前证据:non-code LOBO 家族交集为 0、
   CodeContests 未过配对 CI 门槛。在拿到真实轨迹做冻结 holdout 之前,memory 保持 review-only 建议角色。
4. **不要为了让 MR 层出结果而放宽"保语义"定义**。这是唯一会真正毁掉 confirmed 层可信度的操作。

---

## 实施顺序建议

```
1. P1 的 MR-1 + MR-2        ← 先做,单独提交,单独复核
2. P3(小,可与 P1 并行)
3. P1 的 MR-3 + MR-4
4. P2 重构(大,等价性 diff 是硬门槛)
5. P4 推广
```

每一步**独立提交、独立复核**,不要合并成一个大提交。
每一步的验收标准**在实施前冻结**,不在看到结果后调整。

---

## 参考(2026 年前后相关工作,供背景参考,不作为设计依据)

- Bidirectional Empowerment of Metamorphic Testing and Large Language Models: A Systematic Survey — arXiv 2605.13898
- Mutation-Guided LLM-based Test Generation at Meta — arXiv 2501.12862
- Are LLMs Better than Reported? Detecting Label Errors and Mitigating Their Effect — arXiv 2410.18889
- Automatic Detection of Errors in LLM Large Benchmarks Using Frontier Model Consensus — SpringerLink
- EvalPlus(我们已在用的强 oracle 增强思路)

**注意**:上述文献用于确认方向不孤立,**不要**直接照搬其方法论——
其中多数方法(LLM-as-judge、模型共识)在我们的体系里只能产出 `review`,不能产出 `confirmed`。
