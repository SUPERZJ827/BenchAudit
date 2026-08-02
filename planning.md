  ## 一、补充内容的准确定位

  输入：

  BenchmarkItem
  + 多模型 prediction
  + evaluator verdict
  + match/exec/compile/test 结果
  + 运行配置与版本

  输出：

  异常候选 → review
  客观 replay 成功 → confirmed
  修正/删除后 → 分数与排名影响

  关键红线：

  - 多模型共识、错误率和评分分歧只能生成 review；
  - 结果证据不能直接获得 confirmed 权限；
  - 只有数据库执行、PDF 来源证据、确定性重算等独立证据才能 confirmed；
  - 不新增一套 promotion 逻辑，继续复用现有证据分级。

  ## 二、最小代码设计

  只增加三个通用对象：

  ResultBundle
  - benchmark_id
  - item_id
  - model/system
  - prediction
  - run_id

  EvaluationRecord
  - verdict
  - score
  - evaluator
  - execution_output

  RunProvenance
  - dataset version
  - evaluator version
  - model/version
  - seed/config
  - artifact hashes

  新增四类通用能力：

  1. 自动字段映射与逐题对齐；
  2. provenance 和版本一致性检查；
  3. 多模型/多 evaluator 异常候选；
  4. 把候选送回现有 replay、promotion 和 ranking-impact。

  不会写 MoDoraChecker、SpiderChecker 这样的硬编码主逻辑；数据集差异由 adapter 和 verifier capability 描述。

  ## 三、四套数据的分工

  ### SQL Dialect：reference 完整性

  验证：

  - 异常日志是否写进 reference；
  - reference 是否为空、截断或含控制字符；
  - reference 是否符合目标 dialect；
  - reference 损坏是否造成模型系统性失败。

  已有64条损坏 reference 作为真实案例和回归集，但不能再冒充未知测试集。

  ### PortugueseSpider：evaluator soundness

  从6,476个 match/exec 分歧中聚类：

  - literal；
  - ordering；
  - NULL；
  - duplicate/bag semantics；
  - aggregation；
  - 合法等价 SQL；
  - 测试数据库覆盖不足。

  用数据库重放和反事实数据确认根因。

  ### MMDA：版本漂移与来源证据

  检查：

  - 当前 benchmark 与旧结果版本不一致；
  - 新 gold 与旧 verdict 冲突；
  - 公开 PDF 是否支持 gold；
  - 修正后模型分数和排名变化。

  ### DBCode：评分范围敏感性

  分析完整 harness 与函数专项测试的60个分歧。没有源码和容器时只做 review；环境补齐后才 replay。

  Agent 轨迹不作为主输入，只辅助解释少量失败根因。

  ## 四、冻结实验设计

  严格比较五组：

   组别    内容
  ━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   A       当前 BenchAudit
  ──────  ──────────────────────────────────
   B       简单行为信号：错误率、分歧、共识
  ──────  ──────────────────────────────────
   C       BenchAudit + 运行结果证据
  ──────  ──────────────────────────────────
   D       C + 客观 replay
  ──────  ──────────────────────────────────
   E       随机候选对照

  这样可以区分：

  - 是 BenchAudit 真正融合有效；
  - 还是简单错误率已经足够；
  - replay 是否提高 confirmed yield；
  - 是否只因为多看了更多候选。

  ## 五、量化指标

  ### 自动适配

  - 字段映射准确率；
  - item alignment rate；
  - provenance coverage；
  - silent drop rate；
  - 接入新格式所需人工配置量。

  ### 检测效果

  - Precision、Recall、F1；
  - Precision@20/50/100；
  - Recall@50/100/200；
  - lift over random；
  - confirmed yield；
  - 同等 Recall 下 review 数量下降比例。

  ### 根因聚合

  - affected items；
  - unique root causes；
  - one-fix groups；
  - 聚合前后人工审查量。

  ### 实际影响

  - 修正后模型准确率变化；
  - Kendall’s τ；
  - pairwise ranking swaps；
  - Top-k 变化；
  - 与等量随机删题对照。

  所有主要数字报告 bootstrap 置信区间，不只报点估计。

  ## 六、防止实验自证循环

  已经看到的64条 SQL reference 污染，只能用于：

  - 真实案例；
  - 开发；
  - 回归测试。

  不能同时拿来调 detector 又报告无偏 Precision。

  正式评估采用：

  - 冻结未参与规则设计的 item；
  - PortugueseSpider 的客观 replay 标签；
  - MMDA 的版本差异和 PDF 证据；
  - 预注册的干净负例；
  - 多种缺陷形态的注入对照；
  - 按根因划分 train/dev/test，防止同一生成 bug 泄漏到测试集。

  ## 七、合入主线的门槛

  只有满足以下条件才合并：

  1. item 对齐率至少99%，静默丢失为0；
  2. 行为信号不能绕过 review；
  3. 冻结负例上 confirmed 误报为0；
  4. C 相比 A/B，在至少两个独立数据集上提高 Precision@K，或在相同 Recall 下减少至少20%的 review；
  5. replay 提高 confirmed yield；
  6. 所有结果有数据/evaluator/transcript 哈希；
  7. 排名影响必须有等量随机删除对照。

  如果融合没有稳定增益，就保留为 shadow/实验功能，不进入默认 pipeline。

  ## 八、执行顺序

  1. 新建独立分支，检查现有接入点；
  2. 冻结四套数据和 SHA256；
  3. 实现最小 ResultBundle 接口；
  4. 先跑零 API SQL reference 审计；
  5. 接入 PortugueseSpider 配对分歧；
  6. 做数据库反事实 replay；
  7. 接入 MMDA 版本与 PDF 证据；
  8. DBCode 只做离线分析，环境齐备后再执行；
  9. 跑 A–E 消融；
  10. 计算检测、成本和排名指标；
  11. 红队测试；
  12. 达标才提交和合并。

  预期最稳妥的成果不是“又找出很多候选”，而是：

  > 证明发布的逐题运行结果能否在不重新调用模型的情况下，提高 BenchAudit 的候选精度、confirmed 产出和排名影响分析能力。