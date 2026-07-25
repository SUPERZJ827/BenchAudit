# CodeContests 第三代码 Benchmark 冻结验证

日期：2026-07-25  
状态：**有方向一致、可复现的正向信号，但未通过预注册成功门槛**

## 1. 研究问题

前一轮在 HumanEval 与 MBPP 之间观察到：从源 benchmark 学到的高收益
mutation family，可以提高目标 benchmark 中 evaluator-unsoundness witness 的
发现效率。本实验检验该信号能否迁移到执行协议明显不同的第三个 benchmark：

- 源：HumanEval + MBPP，函数级单元测试协议；
- 目标：DeepMind CodeContests，标准输入/标准输出协议；
- 弱 evaluator：公开测试；
- 强 oracle：私有测试与生成测试，最多 50 例；
- witness：某个变异程序通过公开测试，但不能通过强 oracle。

实验只使用现成 benchmark 代码与测试，不调用 LLM API。模式记忆只参与探针
排序，promotion ceiling 固定为 `review`。

## 2. 冻结与防泄漏

- CodeContests 固定 revision：
  `802411c3010cb00d1b05bad57ca77365a3c699d6`
- HumanEval 固定 revision：
  `7dce6050a7d6d172f3cc5c32aa97f52fa1a2e544`
- HumanEvalPlus 固定 revision：
  `d32357cf319e50e9c8d8dab5ea876c72b0fd321b`
- MBPPPlus 固定 revision：
  `b2d74c91837c3f2a20c1299ae98133cbe7cfa077`
- 容器镜像：
  `sha256:9e30f4122a069ab7f626cdd70a3c11ddbbf44a9bd0cc4cc834136a2a2f08e995`
- 选择探针时不读取目标任务的 private/generated test 结果；
- A、D、F 三组对每个任务使用相同探针预算；
- 只有同时在 HumanEval 和 MBPP 中分别得到至少两个 witness task 的 family，
  才允许进入目标路由；
- 结果哈希只绑定语义 pass/fail，不绑定运行时间、对象内存地址或错误文案。

源端最终满足条件的三个 family 为：

1. `numeric_constant`
2. `return_default`
3. `comparison_boundary`

## 3. v1：test split，因执行抖动降级

v1 使用 CodeContests test split、每题 6 个探针、2 秒单例超时。

第一次运行得到：

| 指标 | A：固定通用顺序 | D：模式引导 | F：半引导半探索 |
|---|---:|---:|---:|
| 有效任务 | 102 | 102 | 102 |
| witnessable tasks | 27 | 27 | 27 |
| 探针数 | 605 | 605 | 605 |
| witness 数 | 27 | 29 | 25 |
| witness yield | 4.46% | 4.79% | 4.13% |
| task recall | 66.67% | 62.96% | 55.56% |

D 的 witness yield 高于 500 个随机 family order 的均值 3.94%，但 D-A 的
配对 bootstrap 95% CI 为 `[-0.66, +1.16]` 个百分点，包含 0。

复跑时稳定摘要哈希从 `9b15a15b...` 变为 `498407e3...`。根因是 2 秒超时
在并发容器负载下使两个目标任务的语义结果发生变化，而不是路由随机性。
因此 v1 **不能作为确认性结果**，只用于发现和修复执行可靠性问题。

## 4. v2：未触碰的 valid split，顺序确认

v2 在查看 valid split 的 mutation outcome 前冻结，改动如下：

- 使用 CodeContests valid split；
- 先按 v1 的预算敏感性分析冻结每题 4 个探针；
- 单例超时在执行 valid split 前从 2 秒提高到 10 秒；
- worker 固定为 4；
- 目标 evidence hash 改为语义哈希；
- valid split 中满足结构条件的候选实际只有 93 条，全部纳入；仍保留
  `minimum_valid_target_tasks >= 80` 的原成功门槛。

### 4.1 主要结果

93 个结构合格候选中，66 个参考实现同时通过弱、强 evaluator；其中 18 个任务
至少存在一个 evaluator-unsoundness witness。

| 指标 | A：固定通用顺序 | D：模式引导 | F：半引导半探索 |
|---|---:|---:|---:|
| 有效任务 | 66 | 66 | 66 |
| witnessable tasks | 18 | 18 | 18 |
| 探针数 | 264 | 264 | 264 |
| witness 数 | 12 | **17** | 11 |
| witness yield | 4.55% | **6.44%** | 4.17% |
| 检出的 witnessable tasks | 9 | **13** | 8 |
| task recall | 50.00% | **72.22%** | 44.44% |

相对 A，D 的点估计提升为：

- witness yield：`+1.89` 个百分点；
- task recall：`+22.22` 个百分点；
- 相同预算下多找到 5 个 witness；
- 多覆盖 4 个 witnessable task。

### 4.2 随机顺序对照

| 指标 | 随机顺序均值 | 随机顺序最大值 | D | D - 随机均值 | 经验单侧 p |
|---|---:|---:|---:|---:|---:|
| witness yield | 3.74% | 5.30% | **6.44%** | +2.70 pp | 0.001996 |
| task recall | 45.59% | 55.56% | **72.22%** | +26.63 pp | 0.001996 |

在 500 个随机 family order 中，没有一个达到 D 的 witness yield 或 task
recall。这里的 p 值是有限随机化集合上的经验值，不应解释成跨数据集总体效应。

### 4.3 配对不确定性

按任务配对 bootstrap：

- witness yield 的 D-A 95% CI：`[0.00, 4.17]` 个百分点；
- task recall 的 D-A 95% CI：`[0.00, 47.06]` 个百分点。

66 个有效任务中，60 个任务的 witness 数相同，D 在 5 个任务上检出而 A
未检出，A 在 1 个任务上检出而 D 未检出。改进集中在少量任务，导致区间下界
恰好为 0；这也是不能把点估计写成确认性结论的主要原因。

### 4.4 确定性复跑

v2 完整运行两次，以下内容逐项一致：

- 93 个任务的 manifest；
- HumanEval、MBPP 与 CodeContests 的逐任务、逐 mutant 语义 pass/fail；
- 有效任务数、witnessable task 数和所有指标；
- 稳定摘要 SHA256：
  `9f62170835d7a536954cc225d47f8c6e7ba6637e907c7a32d136ee55feffd47e`。

原始 JSON 不逐字节相同，因为诊断字段含运行耗时和错误文本；这些字段从不参与
选择、标签或结果哈希。

## 5. 预注册门槛裁决

| 门槛 | 结果 |
|---|---|
| 有效目标任务 ≥ 80 | **失败：66** |
| witnessable tasks ≥ 10 | 通过：18 |
| D witness yield 高于随机均值 | 通过 |
| 随机顺序经验 p ≤ 0.05 | 通过：0.001996 |
| D-A witness-yield CI 下界 > 0 | **失败：下界 = 0** |
| D task recall 不低于随机均值 | 通过 |
| D-A task-recall CI 下界 > 0 | **失败：下界 = 0** |
| 两次完整运行语义结果一致 | 通过 |

最终裁决：**未通过预注册成功门槛。**

可以支持的窄结论是：

> 在第三种 stdin/stdout 代码评测协议上，来自 HumanEval 与 MBPP 的 mutation
> family 优先级产生了方向一致、超过 500 个随机顺序最大值且可确定性复现的
> 效率提升点估计；但有效样本数不足，配对区间下界为 0，因此目前只能视为
> promising replication，而不是完成确认的跨 benchmark 迁移证据。

## 6. 失败样本诊断

93 个结构合格任务中有 27 个参考实现未通过双 evaluator：

- 13 个在公开测试和强 oracle 上都输出不匹配；
- 8 个出现运行时或输入协议错误；
- 5 个公开测试通过、强 oracle 失败；
- 1 个公开测试输出不匹配、但强 oracle 通过。

当前选择的是每题第一个 Python 3 参考实现。未来可以预注册“依次验证多个官方
Python 3 参考实现，选择首个双 evaluator 通过者”的候选恢复策略，以提高有效
任务数；但不能在已经查看本 split 结果后把它用于挽救 v2 的确认性裁决。

## 7. 工程改进

本实验同时留下了几项独立于正负结果、值得保留的工程改进：

1. 为 HumanEval/MBPP 数据加载固定 revision；
2. 修复实验脚本直接执行时找不到 `benchcore` 的路径问题；
3. 新增 stdin/stdout evaluator 执行协议；
4. manifest 绑定任务、参考实现、弱测试和强测试的哈希；
5. 语义 evidence hash 排除耗时与错误字符串噪声；
6. 固定容器镜像、worker、超时与环境变量；
7. 测试源 family 必须由两个源 benchmark 独立支持，而非合并计数；
8. 全部 memory 派生结果继续保持 `review-only`。

## 8. 下一步

在获得真实模型轨迹前，不继续针对 valid split 调参。更合适的工作是：

1. 把“多官方参考实现回退”作为新协议，在未触碰的新 benchmark/split 上冻结后
   再验证；
2. 接入一套新的公开 stdin/stdout benchmark，扩大有效任务数；
3. 完成真实轨迹的最小导入契约：任务、run、最终输出、evaluator verdict、
   artifact hash、事件时间与 provenance；
4. 对真实历史轨迹优先做零新增执行的矛盾挖掘：同输入异 verdict、同输出异分、
   evaluator 不读关键 artifact、失败日志与最终状态冲突；
5. 保留 A/D/F 等预算、随机顺序和冻结 holdout，不因本次正向点估计降低门槛。
