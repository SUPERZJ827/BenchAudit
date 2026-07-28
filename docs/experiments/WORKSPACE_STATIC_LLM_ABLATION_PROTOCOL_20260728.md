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
- `evidence_tier=review`；
- `confirmed=0`。

## 评价口径

### 1. 输出文件名

使用全库确定性复核中 `task_vs_contract_filename` 的 item-level 集合作为
客观参考。在全部 388 个 item 上计算 Precision、Recall、F1。

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
