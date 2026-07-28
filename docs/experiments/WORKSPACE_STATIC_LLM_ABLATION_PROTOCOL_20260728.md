# WorkspaceBench 静态 LLM 配对消融协议

> 状态：在查看本轮 API 结果之前冻结  
> 数据集：WorkspaceBench full388  
> 项目名称：BenchAudit

## 研究问题

在不执行 WorkspaceBench 任务、不生成 agent 轨迹的条件下，DeepSeek
辅助的静态语义审计相对纯确定性规则带来什么增量？

## 两个实验臂

### A：Rules-only

- `static_output_contract_issues`：任务文本与发布 output contract 的确定性
  文件名检查；
- `collect_workspace_invariant_issues`：manifest、输入文件身份和 Workspace
  元数据的确定性检查；
- `resolve_objective_grounding_certificate`：对已进入形式语法的精确
  文件名、标题和清单关系做确定性 rubric replay；
- 不调用 LLM。

### B：DeepSeek-assisted BenchAudit

包含 A 的全部能力，并增加：

- `LLMTaskContractAuditor`：从 task 中抽取显式输出文件名，再由本地
  manifest replay；
- `WorkspaceRubricGroundingAuditor`：逐 rubric 判断其精确要求是否能从
  task、output contract 和允许的输入证据得到支持，并对 unsupported
  结论进行独立反驳式复核。

所有模型衍生 finding 必须满足：

- `review_only=true`；
- substantive candidate 的 `evidence_tier=review`；
- API/解析等 operational failure 只能是 `unknown` 或 `review`；
- `confirmed=0`。

## 运行前输入完整性修正（不改变指标或阈值）

首轮运行中发现，公开 Hugging Face snapshot 的 3,854 个附件均以 symlink
指向 content-addressed blob；安全身份层按设计拒绝 final-component
symlink，导致 rubric arm 测到的是“附件不可读”而非模型能力。该轮结果
废弃，不进入指标。

正式 full388 运行先建立 task-scoped 普通文件视图：

- 只解析数据集已经声明的 `input_files`；
- symlink 只在 staging 阶段解析一次，目标必须是 regular file；
- 同文件系统使用 hard link，跨文件系统才复制；
- auditor 仍执行原有 bounded hash、解析、citation gate 和 review-only
  ceiling；
- 原始数据、标签集合、prompt、阈值和评分代码均不改变。

该修正属于输入物化/安全适配，不是根据实验标签调参。symlink-blocked
试运行产物单独保留作诊断，不参与最终 P/R/F1。

同时修正一个共享底座口径：assisted auditor 本来就会调用
`resolve_objective_grounding_certificate`。正式计分前把同一 resolver
加入 rules-only，防止把确定性 certificate 的收益误记为 DeepSeek 收益。
该调整同样不读取任何标签，且两臂使用同一实现。

## 评价口径

### 1. 输出文件名

使用全库确定性复核中 `task_vs_contract_filename` 的 item-level 集合作为
已知正类参考。在全部 388 个 item 上计算严格 reference-convention 的
Precision、Recall、F1，但不得把未进入旧规则扫描参考集的新候选直接称为
人工证伪的 FP。已知正类 Recall 可直接解释；Precision/F1 只表示与该窄
参考集的 alignment，新增候选另列待复核差异。

### 2. Rubric grounding

现有
`WorkspaceBench_full388_Codex证据化逐条标注_20260720.md`
不是人工 gold，而是双阶段 LLM 证据化复核。只在其中有明确同向结论的
rubric 上计算条件指标：

- 正类：`较可信真问题`；
- 负类：`较可信非问题`；
- `证据不足/分歧` 不计入 P/R/F1；
- item-level confirmed collision 不属于 rubric-grounding 指标。

该指标必须写成 **reviewed-reference conditional P/R/F1**，不得写成
完整数据集人工真值 P/R/F1。

### 3. Input/output role confusion

对每个 LLM 抽取路径与发布 inventories 做机械分类：

- 命中 output inventory；
- 仅命中 input inventory，触发本地抑制；
- 两边均未命中，成为 output mismatch 候选。

报告抽取路径数、被抑制数、残余候选数；不把抑制项当 benchmark 缺陷。

## 必报差异

- A、B 各自候选数和涉及 item 数；
- 交集、B 新增、B 丢失；
- 总体与专项 P/R/F1；
- 全量 7,393 条 rubric 中的 review burden；
- API 请求、cache hit、token 和 operational failure；
- LLM-derived confirmed 数，预期必须为 0。

## 命名规则

本实验一律使用 **BenchAudit**。历史表格中的 `BenchCore` 仅是早期 runner
标签；若必须引用，应写成“历史 runner 名称，对应当时的 BenchAudit
完整流水线”，不得把它当作另一个系统。
