# Workspace P0：给独立 Claude 审阅者的盲审任务

请先完整阅读：

`/tmp/benchaudit-workspace-static-llm-20260728/experiments/workspace_grounding/p0_blind_adjudication/PROTOCOL_20260728.md`

只允许使用以下三个盲包文件：

1. `/home/zhoujun/llmdata/after623/reports/workspace_p0_blind_adjudication_20260728/blind_package/BLIND_TASKS.jsonl`
2. `/home/zhoujun/llmdata/after623/reports/workspace_p0_blind_adjudication_20260728/blind_package/BLIND_CANDIDATES.jsonl`
3. `/home/zhoujun/llmdata/after623/reports/workspace_p0_blind_adjudication_20260728/blind_package/ANNOTATION_TEMPLATE.jsonl`

请勿读取：

- `SEALED_MAPPING.json`
- 双 triage 原始结果
- 既有 Codex/Claude WorkspaceBench 标注
- analyzer summary/report
- 任何包含 A/B、prior verdict、reviewed label 或 source stratum 的文件

这不是让你判断 candidate output 是否满足 rubric，而是判断：

> 该 rubric requirement 对只看到 task、output contract 和允许输入证据的
> agent 来说，是否是合理且有依据的评分要求？

请逐条填写模板中的全部字段。`evidence` 必须是以下结构的数组：

```json
[
  {
    "source": "task|output_contract|input:<filename>|none",
    "quote": "exact quote",
    "relation": "supports|contradicts|insufficient"
  }
]
```

只允许以下枚举：

- `grounding_class`：
  - `hidden_exact_constraint`
  - `intrinsic_validity`
  - `general_quality`
  - `task_or_input_derived`
  - `task_contract_conflict`
  - `insufficient_evidence`
- `is_grounding_defect`：`yes|no|uncertain`
- `evaluation_objectivity`：`objective|subjective|mixed|uncertain`
- `satisfaction_checkability`：
  `static|artifact_execution|llm_judge|human_review|mixed|uncertain`

`primary_family` 和 `acceptable_families` 使用 detector family 名称，例如：

- `workspace_rubric_grounding`
- `task_contract`
- `artifact_execution`
- `input_recomputation`
- `subjective_quality_review`
- `unknown`

输出到：

`/home/zhoujun/llmdata/after623/reports/workspace_p0_blind_adjudication_20260728/CLAUDE_BLIND_ANNOTATIONS.jsonl`

要求：

1. 保持 37 行，与模板 blind id 一一对应；
2. 不新增或删除 blind id；
3. 不改变输入文件；
4. 完成后报告输出文件 SHA256；
5. 明确说明过程中是否意外看到了任何禁止信息；如果看到，整轮标记为
   `blinding_compromised`，不要隐瞒。
