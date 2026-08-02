# BenchAudit：WorkspaceBench full388 静态 LLM 量化报告

> 日期：2026-07-28  
> 数据：WorkspaceBench 全量 388 items / 7,393 rubrics  
> 对照：Rules-only vs DeepSeek-assisted BenchAudit  
> 运行方式：不执行 Workspace 任务、不生成 agent 轨迹，只读取冻结的
> task、rubric、output contract、manifest 和输入附件  
> 模型：`deepseek-v4-flash`，temperature=0

## 一、结论

这次实验给出了一个明确但需要分层解释的结果：

1. **输出文件名抽取有明显增量。** 对旧全库扫描确认的 12 个
   task-vs-contract 文件名冲突，rules-only 命中 0 个，加入 DeepSeek
   后命中 12/12，已知正类 Recall 从 **0.000 提升到 1.000**。
2. **rubric 语义审计能找出 rules-only 覆盖不到的问题。** 在 API
   真正完成的既有正/负复核子集上，DeepSeek-assisted 的
   P/R/F1 为 **0.790 / 0.344 / 0.479**；rules-only 为 0。
3. **本轮 rubric arm 不能冒充 100% 完整实验。** DeepSeek 余额在运行中
   耗尽，7,393 条 rubric 中 4,751 条完成，operational coverage 为
   **64.26%**；其余 2,642 条保持 unknown。
4. **安全边界成立。** 734 条 substantive LLM finding 全部为 review；
   2,650 条运行失败为 unknown；`confirmed=0`、越权数=0。

因此最稳妥的结论是：

> LLM 对 Workspace 静态语义候选生成确实有增量，尤其能把自然语言中的
> 输出文件名要求转成结构化声明，再由本地 manifest replay；但 rubric
> 指标仍受 API 覆盖率和非人工穷尽标签限制，不能写成“full388 人工真值
> 上的最终 F1”。

---

## 二、名称必须统一

项目和系统统一称为 **BenchAudit**。

- `benchcore/` 是仓库中的 Python 包名；
- 历史实验产物曾使用 `BenchCore` 作为 runner 标签；
- 它们不是两个系统；
- 当前实验、报告、简历和对外汇报均应写 **BenchAudit**。

历史 SVAMP/MMLU 表格中的完整流水线，应写成：

> **BenchAudit（原实验产物标签：BenchCore）**

而不能让读者误以为 BenchCore 是另一个对比方法。

---

## 三、实验到底比较了什么

### 3.1 Rules-only

不调用 LLM，使用相同的确定性底座：

- output contract 与 task 中可由规则直接识别的文件名关系；
- manifest、输入附件身份和 Workspace 元数据检查；
- 形式语法覆盖到的 objective grounding certificate。

### 3.2 DeepSeek-assisted BenchAudit

包含 Rules-only 的全部能力，另外增加两条 review-only 语义前端：

1. task 自然语言 → 显式输出路径 → 本地 output inventory replay；
2. task / contract / 输入附件 → 逐 rubric grounding scanner →
   对 unsupported 结论做独立反驳式 verifier。

LLM 只生成结构化声明或候选，不能直接确认缺陷。

```text
自然语言 task / rubric
        ↓ DeepSeek 抽取或分解
结构化 requirement / citation
        ↓ 本地 schema、路径、manifest、citation replay
review candidate
        ↓ 只有另有独立客观 proof 才可能继续
confirmed
```

本实验没有后面的客观 proof，所以所有 LLM substantive finding 均停在
review。

---

## 四、参考标签的真实性质

本实验使用两份已有复核文件，但它们**不是完整人工 gold**。

### 输出文件名参考

旧的全库确定性扫描给出 12 个已知
`task_vs_contract_filename` 正类。它是已知正类集合，但其余 376 题没有
逐条人工 clean 标签。

因此：

- Recall 可以解释为对 12 个已知正类的覆盖；
- 表中 Precision/F1 只是与窄参考集的 strict alignment；
- “FP”只表示没有进入旧参考集，不表示已经人工证伪。

### Rubric grounding 参考

既有证据化复核中共有：

- 300 条“较可信真问题”；
- 100 条“较可信非问题”；
- 159 条“证据不足/分歧”。

P/R/F1 只在前 400 条明确正/负结论上计算，159 条分歧项排除。由于这套
参考本身由旧候选触发并经过双阶段 LLM 复核，存在 selection bias，必须
写成 **reviewed-reference conditional metrics**。

---

## 五、输出文件名结果

| 系统 | 候选 item | TP | 未进入旧参考 | FN | P* | Recall | F1* |
|---|---:|---:|---:|---:|---:|---:|---:|
| Rules-only | 5 | 0 | 5 | 12 | 0.000 | 0.000 | 0.000 |
| DeepSeek-assisted BenchAudit | 60 | 12 | 48 | 0 | 0.200 | **1.000** | 0.333 |

\* P/F1 是对窄参考集的 alignment，不是完整人工 precision。

差异：

- LLM task-contract 自身提出 57 个 item；
- 与 rules 合并后共有 60 个 item；
- 相对 rules 新增 55 个，丢失 0 个；
- 12 个旧文件名正类全部命中；
- 还命中 6/17 个旧扫描确认的 task-level placeholder leak；
- 其余新增项单独列为待复核差异，不自动算错。

典型真命中包括：

- `Shandong.pptx` vs `Shandong.pptx.pptx`；
- `Tesla_Model_3.xlsx` vs `Tesla_Model3.xlsx`；
- `bug_report.txt` vs `bug report.txt`；
- `.doc` vs `.docx`；
- `.xls` vs `.xlsx`；
- task 与 contract 使用整体不同的报告或程序文件名。

完整 60 项差异已写入：

`WorkspaceBench_full388_输出文件名差异清单_20260728.md`

---

## 六、Rubric grounding 结果

### 6.1 Attempted-full388 保守口径

把 operational unknown 计为未检出：

| 系统 | TP | FP | FN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Rules-only | 0 | 0 | 300 | 0.000 | 0.000 | 0.000 |
| DeepSeek-assisted BenchAudit | 64 | 17 | 236 | **0.790** | **0.213** | **0.336** |

该口径衡量这次实际运行最终交付的命中，不是排除 API 故障后的纯模型能力。

### 6.2 Evaluable-subset 条件口径

只保留 scanner/verifier 真正完成的既有正/负复核项：

- 可评估：254/400；
- 正类：186；
- 负类：68；
- 覆盖率：63.50%。

| 系统 | TP | FP | FN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Rules-only | 0 | 0 | 186 | 0.000 | 0.000 | 0.000 |
| DeepSeek-assisted BenchAudit | 64 | 17 | 122 | **0.790** | **0.344** | **0.479** |

这个结果支持：

> 在可完成的复核子集上，DeepSeek 静态语义层以较高 precision 补充了
> rules-only 完全没有覆盖到的 rubric 候选；但 recall 仍然偏低，说明
> 当前 adversarial verifier 与 citation gate 比较保守。

不能据此声称：

- 对全部 7,393 rubrics 的完整 recall 是 0.344；
- 677 个候选都是真缺陷；
- rules-only 对 Workspace 的所有确定性缺陷都为 0。

### 6.3 全量候选和复核负担

| 指标 | 数值 |
|---|---:|
| LLM rubric candidates | 677 |
| 涉及 item | 222/388 |
| 全部 rubrics 上的 review burden | 9.16% |
| operational-evaluable rubrics 上的 review burden | 14.25% |
| 无既有明确标签的候选 | 569 |

569 条未标注候选没有被记作 FP，也没有被宣称为 TP。

---

## 七、Input/output role confusion

| 指标 | 数量 |
|---|---:|
| 通过 schema/证据校验的抽取路径 | 259 |
| 映射到发布 output inventory | 197 |
| 仅命中 input inventory，被本地抑制 | 1 |
| input/output 均未命中，形成 mismatch path | 61 |
| 抽取响应被 schema/grounding 拒绝的 item | 8 |

真实例子是 `workspacebench-246`：DeepSeek 同时抽取了两个输出文件和一个
输入 CSV；本地 input inventory 将该 CSV 识别为输入角色并抑制，因此没有
把它报告成 benchmark 输出缺陷。

这证明 LLM 与静态 replay 的分工是必要的：

- 只靠规则难以从自然语言中找出输出角色；
- 只相信 LLM 又会出现 input/output 混淆；
- LLM 抽取 + 本地 inventory replay 能同时获得语义覆盖和安全约束。

---

## 八、安全和工程验证

| 指标 | 数量 |
|---|---:|
| substantive review findings | 734 |
| operational unknown findings | 2,650 |
| LLM-derived confirmed | **0** |
| 越过 review ceiling | **0** |
| 全仓测试 | **742 passed** |

本轮还修复了几类会直接污染实验的工程问题：

1. LLM HTTP client 原来没有正确使用 `HTTPS_PROXY`；
2. Workspace `output_files` 的 JSON 字符串和 `required_files` 没有统一
   进入 replay；
3. `/desktop/report.docx` 等安全 save path 没有投影到 basename namespace；
4. operational failure 原来会被错误要求必须是 review，而不是允许 unknown；
5. Hugging Face snapshot 的 symlink 被安全身份层拒绝，现已建立
   task-scoped 普通文件视图；
6. rules-only 与 assisted arm 现在共享同一个确定性 objective resolver；
7. 未标注新增项不再被报告文字偷换成假阳性。

附件物化统计：

- 3,854 个输入附件；
- 1.78 GiB；
- 3,854 个同文件系统 hard links；
- 0 次内容复制；
- 原始数据未修改。

---

## 九、API 与未完成边界

### 文件名 arm

- 388/388 item 均有精确 prompt cache；
- 最终重放使用缓存，因此 runtime 中本轮 API request 显示为 0；
- 这不表示该能力没有使用 LLM。

### Rubric arm

| 指标 | 数值 |
|---|---:|
| API attempts | 10,763 |
| API successes | 7,857 |
| API failures | 2,906 |
| 成功响应报告的 prompt tokens | 31,306,958 |
| completion tokens | 6,599,068 |
| total tokens | 37,906,026 |
| wall time | 3,697.75 秒（约 61.6 分钟） |

失败诊断：

- 2,631 条 finding 明确包含 `402 Insufficient Balance`；
- 另有少量输出截断/JSON 校验失败；
- DeepSeek 直连与当前 OpenRouter key 最终都返回余额不足。

所以本轮的诚实状态是：

> full388 全部尝试并保留 unknown，但 rubric arm 只有 64.26%
> operational coverage；文件名 arm 已完整，rubric arm 尚待补余额后定向补跑。

---

## 十、下一步

补充 API 余额后，不需要重跑全部成功调用：

1. 保留现有精确 prompt cache；
2. 只重新生成包含 operational failure 的 item 结果；
3. 成功 prompt 自动 cache hit；
4. 只请求缺失的 scanner/verifier；
5. 覆盖率达到预设门槛后重新计算同一冻结指标；
6. 不修改标签、prompt、阈值或参考集合。

完成标准建议设为：

- all-rubric operational coverage ≥ 95%；
- reviewed-reference coverage ≥ 95%；
- LLM-derived confirmed = 0；
- review ceiling escape = 0；
- 单独报告新候选的人工抽样 precision，而不是把未标注项当 FP。

---

## 十一、可以对外说的一句话

> 在 WorkspaceBench 全量 388 题上，BenchAudit 的 DeepSeek 静态任务契约
> 抽取将 12 个已知输出文件名冲突的召回从 0 提升到 100%，并通过本地
> inventory replay 抑制 input/output 角色混淆；rubric 语义层在已完成的
> 既有正负复核子集上达到 P=0.790、R=0.344、F1=0.479。所有 LLM 发现
> 均保持 review-only、confirmed=0；rubric 全量指标仍需在补足 API 余额、
> 将 operational coverage 从 64.26% 提升后最终确认。
