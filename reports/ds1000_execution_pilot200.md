# DS-1000 执行审计 200 题试点 — 可行性判定(2026-07-18)

> 目的:判断"把排名影响实验/闭环搬到 DS-1000 这类有客观执行验证器的领域"是否值得投入。
> 结论:**执行 grounding 本身在自然数据上仍无法自动确认评测器缺陷**,与 MMLU 一样只能产出 review 候选;不建议作为"自动确认闭环"投入,但过程中修复了一个使容器执行层从未真正可用的 bug。

## 环境(版本保真的可信执行)

- 数据:DS-1000 全 1000 题的前 Pandas 100 + Numpy 100 = **200 题**。
- 执行:**digest-pinned 容器**(自建 `pandas==1.5.3 + numpy==1.24.4`,DS-1000 时代版本,推本地 registry 取 `@sha256:` digest),`docker run --read-only --network none --cap-drop=ALL`。
- 探针:DeepSeek 单模型生成等价/变异探针,执行差分裁决(非对称比较器)。

## 结果(全 200 题)

| 指标 | 值 | 解读 |
|---|---:|---|
| **自动 confirmed 违规** | **0** | 全部 review。零假确认,红线守住。 |
| llm_audit_failure | 75 (37%) | **单模型探针生成失败**,该题未达 comparison-valid 覆盖 → 无审计信号。最大覆盖缺口。 |
| output_format_overstrict_risk | 26 | DS-1000 故意的 `test_string` 表面约束拒绝行为等价解(多半 by-design)。 |
| underconstrained_evaluator_risk | 7(4 题) | "评测器接受了与参考不同的输出"——生存变异信号。 |

## 生存变异信号的人工三分诊(精度 ≈ 25%)

4 个出现生存变异的题(id=11 / 308 / 340 / 348),逐一读原始任务后:

| id | 任务 | 生存变异 | 判定 |
|---|---|---|---|
| **11** | "移除时区" | 不移除 tz 的解仍通过 | ✅ **真评测器盲点**(`assert_frame_equal(check_dtype=False)` 视 tz-aware≡tz-naive) |
| 308 | 属性式验证(不用 ans) | 与 gold 不同的解通过 | ❌ 属性式任务,多解合法 |
| 340 | prompt 明说 **"I do not care about the order"** | 列序展平通过 | ❌ 任务允许任意顺序 |
| 348 | 求**一个**极大线性无关组 | 另一组合法解通过 | ❌ 任务本就多解 |

(id=376 生存变异被 test_string 守卫抑制;id=300 本轮因探针非确定性未复现。)

**关键**:4 个信号里只有 1 个是真缺陷。DS-1000 充满**多解/顺序无关/随机**任务,"评测器接受了不同输出"在这些题上**是正确行为、不是 bug**。

## 判定:不建议把 DS-1000 执行审计当"自动确认闭环"投入

1. **自然数据上自动 confirmed = 0**。"评测器过宽(bug)"与"任务本就多解(非 bug)"的区分,需要判断**任务输出是否唯一**——这本身是语义/领域判断。系统正确地把所有生存变异只标为 `underconstrained_evaluator_risk` / review,不自动确认。这是诚实的,但意味着**和 MMLU 一样需要人工三诊**。
2. **生存变异信号精度低**(~25%),被 DS-1000 的多解任务稀释。
3. **37% 的题没有任何信号**(单模型探针生成失败)。
4. 真实评测器缺陷密度很低(~id=11 一类,约 1–2/200)。

这反而印证了"**多候选 + 分领域独立验证器 + 全局裁决**"的架构判断:执行 grounding 给出高召回的**嫌疑**,但最终"是否缺陷"的裁决仍需一个**任务唯一性 oracle**(prompt 是否说"任意顺序/随机/其中一个"),而那又回到语义判断。

## 过程副产品(真 bug 修复,已提交)

发现并修复 `ContainerRunner.build_argv` **缺 `-i`**:审计 driver 经 stdin 收 payload,但 `docker run` 不加 `-i` 时 stdin 不入容器 → 容器内 `json.load(sys.stdin)` 读空流 → 每题致命失败。原 60 题结果用的是宿主 `LocalProcessRunner`(stdin 正常);**trust-split 引入的容器路径此前从未端到端跑通**。加 `-i`(仅当有 stdin)后容器执行层首次真正可用(本试点即在此路径上完成)。附回归测试 `test_container_forwards_stdin_only_when_present`。

## 落地:任务唯一性分类器(2026-07-18,已实现)

按上面的杠杆做了 **`benchcore/task_uniqueness.py`**:确定性词法分类器,判断任务是否声明多解(顺序无关/随机/求其一/显式多解),把 `underconstrained_evaluator_risk` 的 review 队列分诊——**by_design**(高置信多解→降级)/ **ambiguous**(低置信如随机)/ **priority**(无多解标记→真嫌疑,优先人工)。接入执行层 emit(纯证据增强,**不碰 confirmed 门、不改 severity**,红线不动);每个降级都附匹配短语供人工一眼推翻。

在本试点实际 flag 的 5 个 item 上验证:

| id | 分诊 | 匹配证据 | 真实 |
|---|---|---|---|
| **11** | **priority** | (无) | ✅ 真缺陷 |
| 340 | by_design | "do not care about...order" | ❌ 顺序无关 |
| 348 | by_design | "one maximal" | ❌ 多解 |
| 376 | ambiguous | "random" | ❌ 随机 |
| 308 | ambiguous | "randomly" | ❌ 属性式 |

**唯一被标 priority 的就是唯一的真缺陷** → "优先桶"精度 25%→100%(此样本)。这正是"多候选+分领域验证器+全局裁决"架构里缺的**任务唯一性 oracle** 的第一版:执行给高召回嫌疑,分类器把语义判断显式化+附证据,让人工三诊更快更准。测试 `tests/test_task_uniqueness.py`(6 例,用真实 DS-1000 措辞)。
