# BenchAudit / BenchCore 新对话交接报告

更新时间：2026-06-26  
工作目录：`/home/zhoujun/llmdata/after623`  
当前定位：从零实现的通用 benchmark audit 原型，不依赖旧版 `benchaudit`。

## 1. 项目目标

我们要做的是一个面向 LLM / Agent benchmark 的自动化数据质量审计系统。核心目标不是“让 LLM 多次投票判断题目对不对”，而是把 benchmark 拆成若干 artifact，然后针对每个 artifact 做结构化、可解释、可排序的缺陷检测。

第一阶段聚焦 5 类核心 artifact：

1. `Task Specification`：题干、任务目标、约束条件是否清楚。
2. `Context / Attachments`：上下文、passage、表格、图片、文件、数据库等是否完整。
3. `Expected Output / Answer Contract`：输出格式、答案类型、精确/近似要求是否合理。
4. `Oracle / Ground Truth`：gold answer、reference answer、accepted alternatives 是否正确。
5. `Evaluator / Rubric / Tests`：评分器、rubric、测试逻辑是否过严、过松或与任务不一致。

暂时不把复杂 agent 环境、工具调用、交互 trace、provenance 作为主线，因为这部分会把问题扩展到环境复现和执行系统，不适合当前阶段。

## 2. 当前代码结构

核心代码在：

- `benchcore/adapter.py`：把不同 benchmark 输入转为统一 canonical item。
- `benchcore/field_mapping.py`：自动识别字段，例如 question、choices、gold、context、evaluator。
- `benchcore/checkers.py`：静态规则、完整性规则、简单 evaluator / output contract 检查。
- `benchcore/llm_auditor.py`：主要 LLM 审计器，包括 gold、question、option、quantity、event 等。
- `benchcore/auditor.py`：调度所有 checker / auditor。
- `benchcore/comparison.py`：与人工标签对比，计算 confirmed / candidate / priority 指标。
- `benchcore/report.py`：输出 JSON 和 Markdown 报告。
- `benchcore/cli.py`：命令行入口。
- `scripts/run_mmlu_pilot.py`：一键跑 MMLU-Redux pilot。
- `scripts/run_svamp_pilot.py`：一键跑 SVAMP-Platinum pilot。
- `scripts/prepare_svamp_platinum.py`：准备 SVAMP-Platinum 数据。

最近一次本地提交：

```text
b5345a4 Add event-state constraint auditing
```

如果要同步到 GitHub，通常需要：

```bash
cd /home/zhoujun/llmdata/after623
git push origin main
```

## 3. 已实现的检测模块

### 3.1 静态规则

已覆盖：

- task 缺失；
- context / passage / figure / table / file / database 被引用但缺失；
- 附件路径不可访问；
- output format 缺失；
- gold 缺失；
- 单选 gold 无法映射到选项；
- 选项文本重复；
- 近似题目却使用 exact numeric evaluator 的过严风险；
- 一些简单算术 gold answer 错误。

### 3.2 Gold Auditor

位置：`benchcore/llm_auditor.py`

作用：

- 独立求解题目；
- 判断 gold 是否正确；
- 判断是否 `wrong_gold_answer`、`no_correct_answer`、`multiple_correct_answers`；
- 对单选题采用“先求出答案，再与每个选项做等价匹配”的思路；
- 避免把非 gold 的低质量干扰项直接当作 benchmark 缺陷。

重要原则：

> 非 gold 的非法、较弱、低质量干扰项，只要不影响唯一正确答案和评分，不应直接算 confirmed defect；最多进入 review。

### 3.3 Question Clarity Auditor

作用：

- 检查题干是否缺少必要条件；
- 是否存在 `ambiguous_goal`；
- 是否缺失关键上下文；
- 是否存在时间、地区、法律辖区、专业语境等缺失。

最近修改：

- 题干清晰性审计不再把 gold / aliases / evaluator 暴露给 LLM，减少答案锚定。

### 3.4 Option Auditor / Option Applicability

作用：

- 检查选项是否重复；
- 检查选项集合是否导致多个合理答案；
- 检查每个选项是否符合题干要求；
- 区分“影响唯一答案的选项问题”和“不影响 gold 的干扰项问题”。

目前仍是 MMLU 类选择题召回的主要短板之一，因为很多人工标注的 `multiple_correct_answers` 依赖专业知识或隐性考试惯例。

### 3.5 Presentation / Formatting Auditor

作用：

- 检查题干、选项、context、gold、rubric 中的 OCR、编码、截断、公式损坏、明显排版错误；
- 即使不影响最终答案，也可以作为 `presentation` scope 单独报告。

### 3.6 Quantity Consistency Auditor

位置：`QuantityConsistencyLLMAuditor`

作用：

- 让 LLM 抽取机器可检查的数字约束；
- 程序验证数值关系，而不是直接相信 LLM 判断；
- 检查数量、总量、比例、剩余量、容量等是否自洽；
- 区分 `material_to_answer` 和 non-material contradiction。

这一步显著提升了 SVAMP/GSM8K 类数学文字题的候选召回。

### 3.7 Event-State Auditor

位置：`EventStateLLMAuditor`

作用：

- 抽取实体状态、初始值、事件变化、最终值、需求限制；
- 程序检查：
  - 移除量超过已有量；
  - 推导出的初始状态为负；
  - 最终状态与事件不一致；
  - 状态超过需求限制；
  - 语义角色冲突，例如 price / profit / cost 混用。

这一步是最近最重要的新增模块，主要解决 SVAMP-Platinum 中大量 story math 的状态转移错误。

## 4. 指标定义

当前报告中最重要的三层指标：

### Confirmed

系统认为“可以确认是缺陷”的结果。

特点：

- precision 高；
- recall 通常偏低；
- 适合作为论文中的 high-confidence 自动修复/报告集合。

### Candidate

系统认为“值得人工看”的候选集合，包括 confirmed 和 review signals。

特点：

- 更符合 benchmark audit 的真实使用场景；
- 目标是高召回，并显著减少人工审查规模；
- 当前实验里最应该重点看的指标是 `candidate_precision`、`candidate_recall`、`review_budget`。

### Priority Candidate

candidate 中更值得优先人工看的子集。

特点：

- 排序预算更小；
- 用于回答“只看前 5% / 10% / 20% 样本能找到多少问题”。

## 5. 当前主要实验结果

### 5.1 MMLU-Redux Pilot 200

数据：

- 输入：`/home/zhoujun/llmdata/datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl`
- manifest：`experiments/mmlu_redux_pilot200.manifest.json`
- 人工标签字段：`metadata.error_type`
- clean value：`ok`
- 这批 pilot 中 truth defect 数量为 100。

最近比较重要的一次结果：`option_applicability_v1`

```text
confirmed:
  prediction_items = 24
  true_positive = 21
  false_positive = 3
  precision = 0.875
  recall = 0.210
  f1 = 0.339

candidate:
  prediction_items = 104
  true_positive = 77
  false_positive = 27
  precision = 0.740
  recall = 0.770
  f1 = 0.755
```

解读：

- candidate 结果已经有实用价值：看 104 个候选能覆盖 77 个已知问题；
- confirmed 很保守，precision 高但 recall 低；
- MMLU-Redux 的难点在于专业知识、教材语境、考试惯例，很多漏检不是简单 prompt 能解决。

### 5.2 GSM8K / Platinum

GSM8K 类任务更确定，但仍有一个问题：如果不让 LLM / solver 做数学推理，纯静态规则基本找不到错误。

之前结果：

```text
candidate recall 可以做到 1.0
confirmed recall 一度较低
```

这说明数学类 benchmark 需要结合可执行证据、程序化约束、或更强求解器，而不是只靠题面静态规则。

### 5.3 SVAMP-Platinum Pilot 100

这是当前最好的实验结果，建议作为近期汇报重点。

数据构成：

- 35 个 rejected bad_question；
- 3 个 revised wrong_gold；
- 62 个 clean；
- 共 100 条。

最新推荐结果：`svamp_platinum_pilot100_v5_event_state`

```text
confirmed:
  precision = 0.900
  recall = 0.474
  f1 = 0.621

candidate:
  precision = 0.860
  recall = 0.974
  f1 = 0.914

priority candidate:
  precision = 0.897
  recall = 0.684
  f1 = 0.776

known defects:
  38 个已知缺陷中覆盖 37 个
  3 个 wrong_gold 全部覆盖
```

从版本演进看：

```text
v1 baseline candidate F1       0.676
v2 quantity candidate F1       0.767
v3 blind semantic candidate F1 0.842
v5 event-state candidate F1    0.914
```

解读：

- 这说明“结构化证据抽取 + 程序化约束验证”比单纯 LLM judge 更有效；
- SVAMP 是当前最能支撑论文方法有效性的实验；
- 但还需要跨数据集验证，避免看起来只对 SVAMP 有效。

## 6. 常用运行命令

请使用项目虚拟环境：

```bash
cd /home/zhoujun/llmdata/after623
source ~/.bashrc
/home/zhoujun/llmdata/.venv/bin/python -m pytest
```

### 6.1 跑 SVAMP 当前最佳实验

```bash
cd /home/zhoujun/llmdata/after623
source ~/.bashrc
/home/zhoujun/llmdata/.venv/bin/python scripts/run_svamp_pilot.py \
  --model deepseek \
  --workers 10 \
  --progress-every 20 \
  --tag svamp_platinum_pilot100_v5_event_state
```

结果看：

```text
reports/svamp_platinum_pilot100_v5_event_state_comparison.md
reports/svamp_platinum_pilot100_v5_event_state_report.md
```

### 6.2 跑 MMLU-Redux Pilot 200

```bash
cd /home/zhoujun/llmdata/after623
source ~/.bashrc
/home/zhoujun/llmdata/.venv/bin/python scripts/run_mmlu_pilot.py \
  --tag mmlu_pilot200_current \
  --auditors all \
  --workers 5 \
  --progress-every 10
```

### 6.3 手动 audit + compare 模板

```bash
/home/zhoujun/llmdata/.venv/bin/python -m benchcore.cli audit \
  /path/to/benchmark.jsonl \
  --manifest experiments/xxx.manifest.json \
  --llm-audit \
  --llm-config configs/llm_deepseek.json \
  --llm-cache reports/xxx_cache.jsonl \
  --workers 5 \
  --progress-every 10 \
  --out reports/xxx_report.json \
  --md reports/xxx_report.md \
  --print-summary
```

```bash
/home/zhoujun/llmdata/.venv/bin/python -m benchcore.cli compare \
  /path/to/benchmark.jsonl \
  --report reports/xxx_report.json \
  --truth-field metadata.error_type \
  --clean-value ok \
  --manifest experiments/xxx.manifest.json \
  --out reports/xxx_comparison.json \
  --md reports/xxx_comparison.md \
  --print-summary
```

## 7. 当前技术创新口径

建议汇报时这样讲：

1. **Artifact-centered benchmark audit**
   - 不把 benchmark 当作一坨数据，而是拆成 task spec、context、output contract、oracle、evaluator 等 artifact。

2. **LLM is evidence extractor, not final judge**
   - LLM 负责抽取候选证据、语义角色、数量关系、事件状态；
   - 程序化规则负责验证约束和归因；
   - 这比直接问 LLM “这题有没有错”更稳定、更可解释。

3. **Candidate-first audit**
   - benchmark 审计真实目标不是全自动替代专家，而是用较小人工预算覆盖尽可能多的问题；
   - 因此 candidate recall / review budget 比单纯 confirmed recall 更重要。

4. **Material vs non-material defect separation**
   - 区分影响答案/评分的核心缺陷和不影响答案但影响数据质量的缺陷；
   - 这可以解释为什么部分 Platinum clean label 仍被系统标记为数据质量问题。

5. **Constraint family extensibility**
   - 已经有 static、gold solving、option applicability、quantity consistency、event-state consistency；
   - 后续可以继续扩展 SQL execution consistency、code test consistency、rubric consistency、agent trace consistency。

## 8. 当前问题与短板

### 8.1 MMLU 类专业知识问题

MMLU-Redux 的很多错误依赖：

- 专业教材；
- 医学/法律/社科语境；
- 定义流派；
- source evidence；
- 人工专家共识。

这类问题单靠通用 LLM 很难稳定解决。后续如果要提升，需要：

- RAG / source evidence；
- 专业知识库；
- 多模型交叉验证；
- 或只把这类标为 expert-needed review。

### 8.2 Multiple Correct Answers 仍然难

现在系统能做 option applicability，但多个正确答案仍然难，因为它经常要求：

- 判断“最精确答案”还是“任意成立答案”；
- 判断选项之间是合理层级关系还是真实多解；
- 判断考试惯例。

不能简单把“弱选项也成立”全部判错，否则会大量误报。

### 8.3 Dataset label 本身可能不完整

SVAMP-Platinum 中有些 clean label 实际也存在非 material 的数据质量问题，例如：

- 人物钱不够但题目问总花费；
- 前提故事有状态矛盾但最终答案仍可算；
- wording 有轻微冲突。

所以论文中应区分：

- supervised defect label metrics；
- independent data-quality findings。

### 8.4 Confirmed recall 仍偏低

Confirmed 是高置信输出，目前保守。实际系统价值更体现在 candidate：

- MMLU candidate recall 约 0.77；
- SVAMP candidate recall 约 0.974。

如果论文要强调全自动 confirmed，需要继续提高 confirmed recall；如果定位为 audit assistant，则 candidate + review budget 更合理。

## 9. 下一步建议

最建议按这个顺序做：

1. **先不要继续针对 SVAMP 单点调 prompt**
   - 当前 SVAMP 已经很强；
   - 继续调可能过拟合。

2. **做跨 benchmark 验证**
   - 找另一个确定答案、人工标注明确、专业知识依赖较少的数据集；
   - 优先数学 / 常识推理 / 结构化 QA，而不是医学法律类 MMLU。

3. **补 review budget 曲线和案例分析**
   - 强调“审 20% 样本覆盖多少问题”；
   - 比单纯 precision / recall 更符合 benchmark audit 场景。

4. **把 SVAMP 的 false positives 分成两类**
   - Platinum label clean 但确实存在数据质量问题；
   - 真误报。
   这能体现系统发现了人工标注之外的问题。

5. **形成论文实验主线**
   - RQ1：能否用少量人工审查覆盖 benchmark 缺陷？
   - RQ2：结构化约束比 direct LLM auditor 好多少？
   - RQ3：不同 artifact / defect type 的表现如何？
   - RQ4：跨 benchmark 泛化如何？

## 10. 给新对话的直接任务提示

可以把下面这段直接发给新模型：

```text
我们在 /home/zhoujun/llmdata/after623 做 BenchCore，一个通用 benchmark audit 原型。
请先阅读 NEW_CHAT_HANDOFF_zh.md、README.md、benchcore/llm_auditor.py、benchcore/comparison.py、scripts/run_svamp_pilot.py。
当前最好的结果是 SVAMP-Platinum pilot100：candidate precision 0.860、candidate recall 0.974、candidate F1 0.914。
请不要重新从旧版 benchaudit 开始，也不要只做直接 LLM judge。
当前路线是 artifact-centered audit + LLM evidence extraction + programmatic constraint validation + candidate review ranking。
下一步优先做跨 benchmark 验证，找确定答案且人工标注明确的数据集，避免过度依赖 MMLU 专业知识。
```

