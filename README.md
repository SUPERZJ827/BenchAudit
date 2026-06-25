# BenchCore After623

这是一个从零开始的轻量 benchmark audit 原型，不依赖前面已有的 `benchaudit` 代码。

当前聚焦 5 个核心 benchmark artifact：

```text
Task Specification
Context / Attachments
Expected Output / Answer Contract
Oracle / Ground Truth
Evaluator / Rubric / Tests
```

暂时不把复杂 agent 环境、工具、交互、trace、provenance 作为第一阶段主线。

## 1. 输入格式

支持：

- `.jsonl`
- `.json`
- `.csv`

字段可以不完全统一，程序会自动推断常见字段：

| 标准含义 | 自动识别字段示例 |
|---|---|
| item id | `id`, `item_id`, `instance_id`, `task_id` |
| task | `question`, `prompt`, `instruction`, `problem_statement`, `query` |
| context | `context`, `passage`, `schema`, `files`, `attachments`, `repo` |
| choices | `choices`, `options`, `answer_choices` |
| gold | `answer`, `gold`, `correct_answer`, `final_answer`, `gold_sql` |
| aliases | `aliases`, `accepted_answers` |
| output contract | `output_format`, `expected_output`, `answer_type` |
| evaluator | `evaluator`, `metric`, `rubric`, `tests` |

如果自动推断不准，可以提供 mapping JSON。

## 2. 运行示例

在 `/home/zhoujun/llmdata/after623` 下运行：

### 推荐：一键运行 MMLU-Redux Pilot 200

当前推荐的开放式求解、答案选项等价匹配实验：

```bash
python scripts/run_mmlu_pilot.py
```

脚本默认使用：

```text
DeepSeek deepseek-v4-flash
Gold Auditor
cascade 模式
5 workers
Pilot 200 固定 manifest
```

它会自动完成 `audit` 和 `compare`，结果写入 `reports/`。

指定实验名称，避免覆盖已有结果：

```bash
python scripts/run_mmlu_pilot.py --tag open_match_v1
```

运行完整三 Auditor：

```bash
python scripts/run_mmlu_pilot.py \
  --tag open_match_full \
  --auditors all
```

`all` 包含：

```text
gold
question
option
presentation
```

其中 Presentation Auditor 会检查题干、上下文、选项、gold、输出合同和
evaluator/rubric 中需要模型静默修复才能理解的 OCR、编码、截断、切分及数学格式
问题。此类问题单独记为 `presentation` scope，即使不影响最终答案也会报告。

切换 OpenRouter：

```bash
python scripts/run_mmlu_pilot.py \
  --tag openrouter_open_match \
  --model openrouter
```

```bash
python -m benchcore.cli audit \
  examples/sample_core_benchmark.jsonl \
  --out reports/sample_audit_report.json \
  --md reports/sample_audit_report.md \
  --print-summary
```

查看自动字段映射：

```bash
python -m benchcore.cli infer-mapping examples/sample_core_benchmark.jsonl
```

把任意 benchmark 归一化为统一 canonical JSONL：

```bash
python -m benchcore.cli canonicalize \
  examples/sample_core_benchmark.jsonl \
  --out reports/sample_canonical.jsonl
```

抽样运行：

```bash
python -m benchcore.cli audit \
  /path/to/benchmark.jsonl \
  --limit 20 \
  --out reports/sample20_audit_report.json \
  --md reports/sample20_audit_report.md \
  --canonical-out reports/sample20_canonical.jsonl \
  --print-summary
```

其中 `canonical-out` 会输出统一字段：

```text
item_id
task
context
choices
gold
aliases
output_contract
evaluator
metadata
artifact_coverage
raw
```

## 2.1 可复现分层采样

通用 `sample` 命令支持：

- 任意嵌套分层字段；
- clean / defect 比例控制；
- 固定 seed；
- 排除开发样本或已有 manifest；
- 输出 sample JSONL 和 source-index manifest；
- source SHA-256 校验。

示例：

```bash
python -m benchcore.cli sample benchmark.jsonl \
  --size 200 \
  --seed 20260624 \
  --stratify-field metadata.subject \
  --stratify-field metadata.error_type \
  --label-field metadata.error_type \
  --clean-value ok \
  --defect-fraction 0.5 \
  --exclude-first 120 \
  --sample-out experiments/pilot200.jsonl \
  --manifest-out experiments/pilot200.manifest.json
```

使用 manifest 运行同一批记录：

```bash
python -m benchcore.cli audit benchmark.jsonl \
  --manifest experiments/pilot200.manifest.json \
  --progress-every 10 \
  --out reports/pilot200_report.json
```

`compare` 同样支持 `--manifest`，因此不再需要手工维护 `offset/limit`。

LLM 运行时默认每 10 条输出一次：

```text
[20/200 10.0%] item=... elapsed=2m10s eta=19m30s
```

可以调整：

```bash
--progress-every 5
```

完全关闭：

```bash
--progress-every 0
```

当前固定 pilot 及完整命令见：

[experiments/README.md](/home/zhoujun/llmdata/after623/experiments/README.md)

## 3. 当前能检测什么

默认 `audit` 会同时运行基础规则和多方法检查，包括：

- task 缺失；
- 题目引用 passage / figure / table / file / database 但上下文缺失；
- 附件路径不可访问；
- 输出格式缺失；
- gold answer 缺失；
- 单选 gold 无法映射到选项；
- 选项文本重复；
- 简单算术 gold answer 错误；
- evaluator 缺失；
- exact evaluator 过严风险；
- declared alias 被 evaluator 拒绝；
- 无 evaluator 且无 output contract 的 underconstrained 风险。

非 LLM 方法：

| 方法 | 主要覆盖问题 |
|---|---|
| `cross_artifact_consistency` | output contract、gold、choices、evaluator 类型不一致 |
| `evaluator_replay` | evaluator 拒绝自己的 gold |
| `metamorphic_testing` | 大小写、choice label/text、数字表示、declared alias 等等价变换被误拒 |
| `mutation_testing` | 明确错误答案仍被 evaluator 接受 |
| `dataset_duplicate_scan` | 重复 ID、重复任务、相同任务 gold 冲突 |
| `dataset_schema_profile` | 同一数据集核心 artifact 字段发生异常漂移 |
| `executable_arithmetic` | 简单算术题的 gold 与安全执行结果冲突 |
| `executable_evidence_replay` | 安全执行 `python_expr` evidence，核验 expected 和最终答案 |
| `differential_solver` | 比较独立 solver/candidate final answer 与 gold |
| `task_integrity` | 检查缺失时间范围、未指明来源、任务指令截断和明显展示损坏 |

如果只想运行最基础的静态规则：

```bash
python -m benchcore.cli audit input.jsonl --basic-only --out report.json
```

需要注意：

- 如果输入只声明了 evaluator 类型，没有提供真实 evaluator 代码，那么 replay/metamorphic/mutation 只能针对“声明的 evaluator 模型”运行。
- 这类证据在报告里会标记为 `declared_evaluator_model`，通常进入 review。
- 真实 test script、SQL executor、code runner 接入后，才能升级为 execution-backed confirmed evidence。

按方法单独计算监督指标：

```bash
python -m benchcore.cli compare benchmark.jsonl \
  --report reports/audit_report.json \
  --truth-field metadata.error_type \
  --clean-value ok \
  --include-method differential_solver \
  --out reports/differential_comparison.json \
  --md reports/differential_comparison.md \
  --print-summary
```

也可以使用 `--include-defect wrong_gold_answer` 按缺陷类型过滤。

## 3.1 通用 LLM 语义审计

对于需要“做题/审题”的 benchmark，可以打开通用 LLM semantic auditor。

它不是针对 MMLU 或某个数据集写死的，只读取 canonical 字段：

```text
task
context
choices
gold
aliases
output_contract
evaluator
metadata
```

默认拆成三个独立 auditor：

```text
EvidenceGoldLLMAuditor
QuestionClarityLLMAuditor
OptionSetLLMAuditor
```

分别检查：

- blind solve、gold defender、gold challenger 的结构化证据是否支持 gold；
- 题干是否存在 answer-changing ambiguity、missing condition/context；
- 每个选项的支持状态、是否多解、无解或选项表述不清。

增强版 Gold Auditor 第一次求解时既看不到 gold，也看不到 choices：

```text
Blind Solver（隐藏 choices 和 gold，输出开放式答案）
    ↓
Answer-to-Option Matcher（分别判断语义等价）
    ↓
程序统计等价选项集合
    ├─ 0 个：no_correct_answer
    ├─ 1 个：再与 gold 比较
    └─ 多个：multiple_correct_answers
             ↓
      可疑时启动 Challenger / Defender
```

在等价匹配之后，系统还会独立检查每个选项是否直接满足题干。这可以发现多个
彼此不等价、但分别正确的选项，例如“哪个数是质数”中的 `2` 和 `3`。只有所有
选项都完成独立判断后，程序才确认答案集合；漏评选项会进入 uncertain/review。

新增或修改 LLM 阶段后应使用新的实验 tag，避免把旧 prompt 缓存与新流程混用：

```bash
python scripts/run_mmlu_pilot.py \
  --tag option_applicability_v1 \
  --auditors all
```

聚合置信度由“支持同一缺陷的证据阶段数 / 有效阶段数”和各阶段置信度共同计算，
不直接采用某一次 LLM 自报的高置信度。依赖外部来源、未验证假设或专业约定的结论
只能进入 review。

Matcher 判断的是答案等价关系，不是性质蕴含关系。例如开放式答案为
`Abelian group` 时，`commutative semigroup` 是较弱性质，但不是等价答案，
因此不会被计为第二个正确选项。

Option Auditor 会分别输出：

```text
literal_truth
best_answer_status
literal_cardinality
best_answer_cardinality
equivalence_group
```

这样可以区分“字面上也成立的较弱选项”和“题目要求的唯一最佳答案”，避免把
best/most/primary 类题目机械地判为多解。同时，普通单选题中两个独立成立的选项
仍会被保留为候选缺陷。

证据融合规则：

- Question Clarity Auditor 的自然语言歧义判断默认只进入 `review`；
- 只有静态/执行检查提供同类独立证据时，题干问题才升级为 confirmed；
- 多个 LLM auditor 的结论互相冲突时，相关结论降为 `review`，并输出
  `auditor_contradiction` 运行信号；
- `auditor_contradiction` 和 `llm_audit_failure` 属于 operational scope，
  默认不作为 benchmark defect 计算 precision/recall。

运行：

```bash
python -m benchcore.cli audit \
  /home/zhoujun/llmdata/datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl \
  --limit 20 \
  --llm-audit \
  --llm-auditors gold,question,option \
  --llm-config configs/llm_deepseek.json \
  --llm-cache reports/mmlu_redux_llm_cache.jsonl \
  --workers 5 \
  --out reports/mmlu_redux_sample20_llm_audit_report.json \
  --md reports/mmlu_redux_sample20_llm_audit_report.md \
  --print-summary
```

默认 `gold` 使用按风险触发的结构化级联：

```bash
--llm-auditors gold,question,option \
--gold-evidence-mode cascade
```

正式召回实验可以强制每题都运行 defender/challenger：

```bash
--llm-auditors gold,question,option \
--gold-evidence-mode full
```

`cascade` 中正常题调用 Blind Solver、Matcher 和 Independent Option
Applicability 三次，发现缺陷或不确定匹配时再调用 Challenger 和 Defender。
`full` 强制运行全部阶段。
旧单次 Gold Auditor 保留为消融基线：

```bash
--llm-auditors gold-single,question,option
```

注意：同时启用 gold/question/option 时，`cascade` 模式每条产生 4 到 5 次
API 调用，`full` 固定最多 5 次；
只启用部分 auditor 可以降低成本：

```bash
--llm-auditors gold
--llm-auditors question,option
```

`llm_audit_failure` 是运行失败信号，不作为 benchmark defect 参与 comparison。

### MMLU-Redux Pilot 200 历史结果

以下结果来自引入新 Option schema、TaskIntegrityChecker 和证据门控之前的固定
100 clean + 100 defect 实验，仅用于记录迭代历史：

```text
Confirmed: precision=0.891 recall=0.490 F1=0.632
Candidate: precision=0.882 recall=0.600 F1=0.714
```

相比单一 gold prompt：

```text
Confirmed recall: 0.290 -> 0.490
Candidate recall: 0.390 -> 0.600
```

需要本地环境变量：

```bash
export FIN_API=...
```

只测试流程、不调用 API：

```bash
python -m benchcore.cli audit \
  examples/sample_core_benchmark.jsonl \
  --llm-audit \
  --llm-dry-run \
  --out reports/sample_llm_dryrun_report.json \
  --print-summary
```

### SVAMP-Platinum Pilot 100

SVAMP 实验包含 35 道人工拒绝坏题、3 道人工修订错答案和 62 道干净题。
`Quantity Consistency Auditor` 由 LLM 提取实体、数量、事件和约束，再由程序验证
数量关系；影响答案的矛盾进入 priority，非关键背景矛盾进入 exploratory review。

准备数据并运行：

```bash
python scripts/prepare_svamp_platinum.py
python scripts/run_svamp_pilot.py \
  --model deepseek \
  --workers 10 \
  --tag svamp_platinum_pilot100_v2_quantity
```

固定 Pilot 100 上的结果：

| 模式 | Precision | Recall | F1 |
|---|---:|---:|---:|
| Confirmed | 0.818 | 0.237 | 0.367 |
| Candidate | 0.842 | 0.842 | 0.842 |
| Priority candidate | 0.880 | 0.579 | 0.698 |

相较没有数量一致性审计的版本，Candidate F1 从 `0.676` 提升至 `0.842`，
Priority Recall 从 `0.158` 提升至 `0.579`。3 道人工修订错答案均进入候选集合。

## 4. 报告字段

JSON 报告包括：

```text
summary
field_mapping
violations
```

每条 violation 都有：

```json
{
  "item_id": "...",
  "artifact": "oracle_ground_truth",
  "mechanism": "incorrect",
  "defect_type": "invalid_choice_gold",
  "severity": "critical",
  "confidence": 0.98,
  "message": "...",
  "evidence": {},
  "suggested_repair": "...",
  "review_only": false
}
```

## 5. 当前定位

这个版本是 first-pass audit scaffold。

它不是最终论文系统，主要用于：

1. 快速接入不同 benchmark；
2. 统一核心 artifact schema；
3. 产生第一批 confirmed defects 和 review signals；
4. 后续继续加入 execution consistency、candidate replay、mutation testing。

## 6. 下一步建议

优先新增：

1. 真实 evaluator bridge：SQL executor、test script、numeric solver、rubric grader；
2. `ExecutionConsistencyAlternativeChecker`：检测合理替代解是否被 evaluator 误杀；
3. candidate solution generation：为 metamorphic/mutation 提供更多候选；
4. 多次 LLM / solver disagreement 和 assumption audit。
