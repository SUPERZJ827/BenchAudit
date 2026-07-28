# Workspace grounding P0：独立模型替代协议修订

修订版本：`workspace-grounding-p0-adjudication-v1.1-20260728`

修订时间：2026-07-28（揭示 sealed mapping 之前）

## 修订原因

原协议指定 Claude Opus 为第一位独立盲审者，但当前无法使用 Claude API。
模型品牌不是本实验的科学变量；关键约束是：

1. 审阅模型与候选生成模型属于不同模型家族；
2. 每次请求使用全新、无对话历史的上下文；
3. 审阅模型只能看到冻结协议和三个盲包文件；
4. 审阅过程不得读取 source stratum、既有 verdict、reviewed label 或 sealed
   mapping；
5. 模型身份、输入哈希、输出哈希、token 用量和失败重试必须写入回执。

因此，本轮将第一位独立盲审者替换为：

`google/gemini-3.1-pro-preview`（通过 OpenRouter 调用）

该模型在执行前冻结，属于不同于 DeepSeek 候选生成器和 Codex 非盲证据审阅者
的模型家族。

## 不变部分

本修订不改变：

- 37 条 blind id；
- task、rubric、output contract 或允许输入证据；
- 标签空间和判定边界；
- 重点/对照的构成；
- sealed mapping；
- 后续一致率和分层指标定义。

原协议除“Claude/Opus”品牌限制外全部继续生效。

## 执行方式

- 按 `task_blind_id` 分组，共 26 个独立 API 请求；
- 同一 task 的多个 rubric 在同一请求中审阅，避免重复发送长输入；
- 不在请求之间传递消息或历史；
- 失败重试只允许携带同一盲包内容和格式/证据校验错误；
- 输出必须通过枚举、blind-id 覆盖和逐字证据锚校验；
- 原始响应和最终标注仅保存在 git worktree 之外，权限限制为当前用户。

## 证据等级

合格输出记为：

`independent_cross_model_blind_review`

它可以替代原协议中的第一位独立模型审阅者，但仍不是 human gold。与 Codex
结果一致时只记为 `reviewed_agreement`；分歧保持
`adjudication_conflict`，不通过多数票强行生成硬真值。

