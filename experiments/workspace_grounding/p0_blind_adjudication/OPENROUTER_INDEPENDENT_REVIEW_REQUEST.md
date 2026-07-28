# Workspace P0：OpenRouter 独立模型盲审任务

执行时必须同时遵守：

1. `PROTOCOL_20260728.md`
2. `PROTOCOL_AMENDMENT_INDEPENDENT_MODEL_20260728.md`

冻结模型：

`google/gemini-3.1-pro-preview`

只允许向模型发送以下三个盲包文件中的内容：

1. `BLIND_TASKS.jsonl`
2. `BLIND_CANDIDATES.jsonl`
3. `ANNOTATION_TEMPLATE.jsonl`

不得读取或发送：

- `SEALED_MAPPING.json`
- 双 triage 原始结果；
- 既有 Codex/Claude/Gemini 标注；
- analyzer summary/report；
- 任何 A/B、prior verdict、reviewed label 或 source stratum。

输出到：

`/home/zhoujun/llmdata/after623/reports/workspace_p0_blind_adjudication_20260728/GEMINI_3_1_PRO_INDEPENDENT_ANNOTATIONS.jsonl`

回执写入：

`/home/zhoujun/llmdata/after623/reports/workspace_p0_blind_adjudication_20260728/GEMINI_3_1_PRO_INDEPENDENT_RECEIPT.json`

只有在以下条件全部满足时，`blinding_compromised` 才可为 `false`：

- API 返回的模型身份与冻结模型一致；
- 37 个 blind id 完整且无重复；
- 所有枚举和字段通过校验；
- 每条 evidence quote 均逐字存在于对应 task、output contract 或允许输入证据；
- 脚本没有读取任何禁止文件；
- 每个 task 使用全新的无历史请求。

