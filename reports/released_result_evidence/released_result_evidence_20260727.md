# Released-result evidence：零 API 真实结果审计

> 结论：已有模型输出和评测结果能够成为一个低成本、高召回的候选前端，但只能定位“值得独立重放”的位置，不能仅凭历史 verdict 自动确认 benchmark 缺陷。

## 数据覆盖

| 数据集 | 模型/系统 | 对齐后的 item | 历史 run |
|---|---:|---:|---:|
| SQL Dialect Translation | 8 | 556 | 4,448 |
| PortugueseSpider | 19 | 2,754 | 29,986 |
| DBCode | 14 | 365 | 1,413 |
| 合计 | — | 3,675 | 35,847 |

整个实验未调用 LLM API。输入 manifest 覆盖所有消费文件，并记录字节数和 SHA-256：
`4ebc7d465d4ff571619a53a604749b1fc068d82ad3da005a858a813e60c51d88`。

## 主要结果

### 1. SQL reference 污染可以被低成本、高精度地定位

- 65/556 个 reference 字段直接包含 SQL 解析器错误文本或 ANSI 诊断载荷；
- 发布侧 SQLGlot 判定 66/556 个 reference invalid，另有 14 个属于
  `unsupported_fallback`；
- 使用固定 SQLGlot 30.2.1 对 556 个 reference 重新执行，得到
  476 valid、66 invalid、14 unsupported，和发布 sidecar **0 个不一致**；
- 两次重放产物逐字节一致，稳定摘要哈希为
  `2253c3ce222ad1d959c1c3e7fecfb0b3a3db4d7d8023c5641a5c1e3552ac9d94`。

以“发布侧 reference parser failure”作为复现代理标签（不是语义真值）：

| 候选信号 | AUROC | P@20 | P@50 | P@66 / R@66 |
|---|---:|---:|---:|---:|
| 8 模型预测语法失败率 | 0.825 | 0.650 | 0.520 | 0.439 / 0.439 |
| reference 诊断载荷 | 0.992 | 1.000 | 1.000 | 0.985 / 0.985 |
| 诊断载荷 + 行为失败率 | 0.996 | 1.000 | 1.000 | 0.985 / 0.985 |
| 随机期望 | 0.500 | 0.119 | 0.119 | 0.119 / 0.119 |

因此，行为矩阵有筛选价值，但 reference 自身的确定性完整性检查更强；二者融合只带来很小的排序增益。这个结果支持“先便宜结构检查，再用行为信号补充”的流程，而不是让多模型行为替代 verifier。

### 2. PortugueseSpider 的 evaluator 选择会显著改变结论

29,986 个同一 `(reference, prediction)` 对的双评测结果：

| Structural match | Database execution | 数量 |
|---|---|---:|
| pass | pass | 14,436 |
| fail | fail | 9,074 |
| pass | fail | 4,855 |
| fail | pass | 1,621 |

总冲突为 6,476/29,986 = **21.60%**，95% Wilson CI 为
**21.13%–22.07%**。在 19 个系统中，8 个系统的排行榜位置发生变化；
忽略 tie 的 pairwise Kendall τ 为 **0.871**。

这证明“评测器选择”不是小噪声。但冲突本身无法说明 match 或 execution
哪一个错，所以全部保持 review，后续要对冲突子集进行任务级重放。

### 3. DBCode 揭示 full harness 与 function tests 的契约差异

有 316 个 run 同时具备两种 verdict：

| Full harness | Function tests | 数量 |
|---|---|---:|
| pass | pass | 53 |
| fail | fail | 203 |
| fail | pass | 60 |

冲突率为 60/316 = **18.99%**，95% Wilson CI 为 **15.05%–23.67%**。
四个具备双通道结果的系统没有发生名次交换，但绝对通过率被明显改变。
此外，`sqlite:json_valid` 与 `sqlite:substr` 在不同发布文件中使用了不同
reference 版本，应当先做版本对齐再重放。

## 本轮代码改进

1. 新增通用 released-result adapter，支持 JSON、JSONL、dict-of-records；
2. 字段推断歧义时 fail-closed，不按行号跨文件对齐；
3. 转换到现有 `TraceBundle`，没有新造一套平行结果 schema；
4. 输出内容用路径无关 SHA-256 比较，可发现相同输出 verdict 不一致；
5. 将 reference 诊断污染、reference evaluator failure、reference 版本漂移聚合为数据集级 finding，避免一次根因产生 N 条 critical；
6. promotion 中央硬门禁止 released-result/trace evidence 越级 confirmed；
7. 加入固定版本 SQLGlot 重放、随机对照、ranking sensitivity 和置信区间；
8. 结果在不同输出目录复跑得到相同稳定摘要：
   `e447721d92e9c038391037a8b8331e494c6a2fcd93e765e1b9ef4cfa8d4efb50`。

## 诚实边界与下一步

- SQLGlot 重放只证明发布标签可复现，不证明 SQL 语义等价，也不证明
  SQLGlot 完整支持目标 dialect。
- PortugueseSpider/DBCode 冲突是候选证据，不是缺陷真值。
- DBCode 缺少完整、冻结的 repository/container snapshot，目前不能独立重放。
- 65 个 SQL 诊断载荷是已见案例，不能把它同时当开发集和无偏测试集。

下一步优先级：

1. 对 65 个诊断 reference 和 1 个“干净文本但 parser invalid”的 reference
   做独立契约复核，区分数据污染与 parser coverage；
2. 从 PortugueseSpider 四象限分层抽样，重建 database 执行环境，估计哪一类
   evaluator failure 是真实问题；
3. 为 DBCode 收集 commit、依赖锁和测试命令；没有环境快照时不宣称 confirmed；
4. 在新的、冻结的结果集上评估候选排序，避免在已知 65 条上继续调参。
