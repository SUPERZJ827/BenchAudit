# MMLU-Redux 15模型响应矩阵：离线可行性实验预注册

## 目标

在不调用新 API、不重新执行 benchmark、不改动 BenchAudit 主流程的前提下，判断已有 `15 模型 × 1000 题` 行为矩阵能否为 Q&A benchmark 提供比简单模型分歧更有效的低成本候选排序。

## 数据安全约束

1. 15 个 JSONL 文件必须按 `id` join，禁止按行号堆叠。
2. 物理拆分 `features.json` 与 `labels.json`。
3. 排序阶段只能读取 features 和已有 BenchAudit 候选，禁止读取 `error_type`。
4. 评估阶段才按 `id` join labels。
5. 能力分数使用其余全部题的原始 correct/incorrect，不按任何 `error_type` 筛题。
6. 所有心理测量/行为统计信号的 promotion ceiling 固定为 `review`。

## 标签口径

### 主口径：objective-vs-ok

- 正例：`wrong_groundtruth` / `multiple_correct_answers` / `no_correct_answer`，预期 181 题。
- 负例：`ok`，预期 630 题。
- `bad_question_clarity` / `bad_options_clarity` / `expert` 不参与该口径。

### 补充口径：any-error-vs-ok

- 正例：任何 `error_type != ok`，预期 370 题。
- 负例：`ok`，预期 630 题。

## 预注册排序器

1. `random`：随机基线。
2. `at_least_one_wrong`：至少一个模型答错。
3. `error_rate`：15 模型错误率。
4. `answer_entropy`：A/B/C/D/缺失预测的归一化熵。
5. `global_item_total_anomaly`：负 corrected item-total correlation，当前题从总分排除。
6. `subject_item_total_anomaly`：subject 内 corrected item-total，小学科与 global 做 shrinkage。
7. `high_ability_disagreement`：当前题排除后，能力最高三分之一模型的错误率减全体错误率。
8. `majority_against_gold`：最大非 gold 答案数减 gold 答案数。
9. `psychometric_fusion`：等权融合 entropy、global/subject item-total anomaly、high-ability disagreement 和 majority-against-gold 的百分位排名，不使用标签。
10. `benchaudit_flag`：现有审计器 318 条答案/选项类候选。
11. `benchaudit_score`：现有审计候选的最大 confidence，未命中为 0。
12. `audit_psychometric_fusion`：`benchaudit_score` 与 `psychometric_fusion` 百分位等权融合，不做监督调参。

## 指标

- Average Precision (AP / ranking AUPRC)
- Precision@20/50/100
- Recall@50/100/200
- Lift over random prevalence
- Top-K 中各 error type 命中数
- 与现有 BenchAudit 的四象限互补性
- 5/8/10/15 模型子采样的 Top-50 Jaccard 和 P@50
- 候选分数与 error rate 的 Spearman 相关，用于检查是否只在找难题

P@K/R@K 对分数并列做固定种子随机 tie-breaking，报告均值与 95% 区间。

## 可行性裁决

- `promising`：在主口径上，`psychometric_fusion` 相对 `error_rate` 或 `audit_psychometric_fusion` 相对 `benchaudit_score` 的 AP 绝对提升至少 0.02，且 10 模型子采样 Top-50 Jaccard 中位数至少 0.40。
- `mixed`：有正增益或有现有 BenchAudit 漏检的新 objective 命中，但未同时达到上述效果与稳定性门槛。
- `not_justified`：不优于简单分歧基线，且对现有 BenchAudit 没有稳定的互补命中。

## 输出与边界

- 产物写入 `reports/mmlu_psychometric_feasibility_20260722/`。
- 不改动 `benchcore/`、主 CLI、promotion registry 或现有报告。
- 本实验只判断值不值得继续工程化，不将统计异常声称为 confirmed benchmark 缺陷。
