# DS-1000 执行审计 — 分诊后的人工复核队列

> 源:`reports/ds1000_exec_pilot200`;共 **4** 个待复核信号。按任务唯一性分诊排序:**priority**(无多解标记,真嫌疑,优先看) > **ambiguous**(弱多解如随机)> **by_design**(任务自己声明多解,大概率非缺陷)。

> 分布:priority **1** / ambiguous 1 / by_design 2。全部 review 级,无自动确认。


| # | id | 库 | 分诊 | 缺陷类型 | 任务多解证据 |
|---:|---:|---|---|---|---|
| 1 | 11 | Pandas | 🔴 priority | underconstrained_evaluator_risk | (无——输出应唯一) |
| 2 | 308 | Numpy | 🟡 ambiguous | underconstrained_evaluator_risk | `randomly` |
| 3 | 340 | Numpy | ⚪ by_design | underconstrained_evaluator_risk | `do not care about the order` |
| 4 | 348 | Numpy | ⚪ by_design | underconstrained_evaluator_risk | `one maximal` |

## 怎么用

- 🔴 **priority**:任务应有唯一输出、评测器却接受了不同输出 → 最可能是真过宽,优先人工确认。
- ⚪ **by_design**:任务 prompt 明确声明多解(见证据短语),存活变异是预期的,可快速跳过。
- 🟡 **ambiguous**:仅匹配到弱标记(如'random'),需看一眼确认是输出随机还是输入设置。