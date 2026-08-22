# SVAMP 改进 B 离线反事实决策说明

- 更新日期：2026-08-20
- 目标：检查 quantity LLM 响应内部自洽性，并按 claim 作用域使不可信证据失效
- 执行约束：全程离线；零 LLM API；不修改 prompt、标签或冻结报告；checker 不读取 gold、`audit_label` 或 TP/FP 状态
- 实现状态：原型和测试已移植到最新主线基线，代码提交为 `dd3023b`

## 1. 核心结论

改进 B 包含两个需要分开评价的部分：

1. **claim-scoped 失效策略有效**：当响应明确 `INCONSISTENT` 时，只阻止依赖 `derived_answers` 的 `wrong_gold_answer`，保留由 `checks`、reference issues 或题面结构独立支撑的 claim。五跑合计消除 13 次 FP candidate，TP 和 FN 不变。
2. **当前 extractor 覆盖率不足**：498 份真实 quantity 响应中有 406 份 `NOT_IDENTIFIABLE`，总体 NI 为 81.5%；即使只看 solved 响应，NI 仍为 78.0%。因此收益只能解释为**可识别响应子集上的稳定收益**，不能外推为对大多数 quantity 响应普遍有效。

学长已选择接受方案 1：保留 D 方案，并将 18.5% 明确判定覆盖率作为已知限制与收益并列写入主线文档。当前不继续调整 extractor、协议或 prompt。

## 2. 完整 cache 与映射验证

使用材料：

- `handoff_svamp_fp_n5/handoff_svamp_fp_n5/runs/full_1..5.json`
- `改进B_交付_20260815/改进B_交付/caches/full_1..5_cache.jsonl`
- `五跑quantity响应按题号索引_20260816/quantity_cache_index_pkg/`
- `scripts/analyze_svamp_quantity_full_cache_counterfactual.py`

验证结果：

- 索引包 SHA256 全部通过；
- 100 个 item ID 和 100 个 cache key 一一对应且 key 全部唯一；
- 五跑成功索引 99、100、99、100、100 份响应；
- 498/498 份索引响应与原始 cache 逐字段完全一致；
- `full_1/chal-513`、`full_3/chal-58` 当跑没有 quantity 调用，按无响应处理，不计入分母。

此前使用当前代码重建 cache key 得到 `0/100`，原因已确认：历史 commit `5824cd9f` 使用默认 JSON 分隔符，当前代码增加了紧凑 `separators=(",", ":")`。这是 key 公式变化，不是 cache、payload 或映射错误。

## 3. 完整状态分布

checker 判定阶段仅使用原题 `task` 和原始 quantity 响应，并显式令 `gold=None`。全部状态固定后才加载 manifest 标签进行离线计分。

| run | 响应数 | solved | CONSISTENT | INCONSISTENT | NOT_IDENTIFIABLE | NI 比例 |
|---|---:|---:|---:|---:|---:|---:|
| `full_1` | 99 | 83 | 11 | 6 | 82 | 82.8% |
| `full_2` | 100 | 84 | 11 | 7 | 82 | 82.0% |
| `full_3` | 99 | 84 | 13 | 6 | 80 | 80.8% |
| `full_4` | 100 | 84 | 12 | 5 | 83 | 83.0% |
| `full_5` | 100 | 84 | 14 | 7 | 79 | 79.0% |
| **合计** | **498** | **419** | **61** | **31** | **406** | **81.5%** |

NI 构成：

- 79 份响应因 `solution_status != solved` 按协议直接不可判定；
- 327 份 solved 响应仍不可判定，solved-only NI 为 `327/419=78.0%`；
- 当前 extractor 只明确判定了 `92/498=18.5%` 的响应；
- 大多数 solved NI 的原因是 `rationale_final_claim_missing`，说明常见终结措辞未命中当前保守规则。

## 4. D 方案全量反事实

D 方案规则：

- `INCONSISTENT` 时只使 `wrong_gold_answer` 失效；
- 独立证据 claim 和其他 auditor findings 保留；
- 不为原报告中的 no-finding 响应新增 candidate；
- 标签只用于 checker 完成后的 TP/FP/FN 计分。

| run | 基线 TP/FP/FN | INCONSISTENT | 其中 no-finding | D 方案 TP/FP/FN | ΔTP/ΔFP/ΔFN |
|---|---:|---:|---:|---:|---:|
| `full_1` | 31 / 17 / 7 | 6 | 1 | 31 / 14 / 7 | 0 / -3 / 0 |
| `full_2` | 29 / 17 / 9 | 7 | 2 | 29 / 14 / 9 | 0 / -3 / 0 |
| `full_3` | 31 / 17 / 7 | 6 | 1 | 31 / 15 / 7 | 0 / -2 / 0 |
| `full_4` | 29 / 16 / 9 | 5 | 1 | 29 / 15 / 9 | 0 / -1 / 0 |
| `full_5` | 30 / 18 / 8 | 7 | 1 | 30 / 14 / 8 | 0 / -4 / 0 |
| **合计** | **150 / 85 / 40** | **31** | **6** | **150 / 72 / 40** | **0 / -13 / 0** |

需要明确：

- 13 是 **item-run candidate 消除次数**，不是 13 个不同 item；
- 新发现的 no-finding `INCONSISTENT` 为 `chal-747`（5/5）和 `chal-693`（仅 `full_2`）；
- 这 6 次响应没有产生原始 quantity finding，因此只改变覆盖率统计，不改变 TP/FP/FN；
- D 的收益来自限制证据失效范围，不来自标签、item ID 特判或为了指标收窄 checker。

## 5. `chal-591`

当前本地保存过一份 `derived_answers=93887`、rationale 最终结论为 `93899` 的响应。现有 parser 只解析并缓存 provider 返回的 JSON，不会重算或改写 `derived_answers`，因此该案例记录为 **LLM structured-output inconsistency**，不继续分析数字来源。

五跑完整 cache 中，`chal-591` 的真实响应均为：

- `solution_status=solved`；
- `derived_answers=["93899"]`；
- rationale 表达 `403 * 233 = 93899`；
- checker 返回 `NOT_IDENTIFIABLE`，原因为 `rationale_final_claim_missing`；
- 没有触发 D 失效，TP 损失为 0/5。

因此，本地 TP 损失不是五跑稳定现象；同时，`multiply ... to get 93899` 未被识别也再次说明当前 extractor 覆盖有限。本轮不据此修改规则或为 `chal-591` 添加特判。

## 6. 决策边界

已经确认：

- checker 对同一冻结响应的判定是确定性的；
- checker 不读取 gold 或标签即可识别部分内部冲突；
- claim-scoped D 方案解决了“整条响应作废”导致的过度失效；
- 当前只确认 `wrong_gold_answer` 依赖 `derived_answers`；
- 五跑实现 `ΔTP=0`、`ΔFP=-13`、`ΔFN=0`。

不能声称：

- extractor 覆盖大多数 quantity 响应；
- 13 次 FP 消除可以外推到全部响应；
- 任意评估口径下都绝不会损失 TP；
- `INCONSISTENT` 是题目的固定属性，而不是具体响应的属性。

禁止通过以下方式改善指标：

- checker 读取 gold、`audit_label` 或 TP/FP 状态；
- 为 `chal-513`、`chal-591` 等 item ID 增加特判；
- 因 NI 或指标不理想而临时修改提取口径；
- 把 operational unknown 计作 substantive candidate。

## 7. 实现与验证状态

- claim-scoped 原型已接入 `quantity_consistency_violations()`；
- 已覆盖 derived-dependent claim 失效、`chal-513` 独立 check 存活、nonmaterial reference claim 存活等 fixture；
- 完整 cache 分析脚本：`scripts/analyze_svamp_quantity_full_cache_counterfactual.py`；
- quantity 定向测试：`12 passed, 8 subtests passed`；
- 原开发基线完整测试：`714 passed, 8 subtests passed`；
- 最新主线同步分支的全部本地可运行测试：`932 passed, 23 skipped, 12 deselected, 8 subtests passed`；12 个 deselected 节点及另 2 个未收集模块依赖未随 Git 提供的外部实验资产、学长机器路径或当前环境未安装的 `scipy`；
- 最新主线代码下五跑反事实仍为 `NOT_IDENTIFIABLE=81.5%`、`ΔTP=0`、`ΔFP=-13`、`ΔFN=0`；
- Python 编译检查及 `git diff --check` 通过；
- 全程未调用 LLM API；原实现提交 `c461d29` 已在最新主线基线上重放为 `dd3023b`。

复现命令：

```bash
.venv/bin/python scripts/analyze_svamp_quantity_full_cache_counterfactual.py
```

## 8. 已确认决策与后续

已确认采用“低覆盖、但可识别子集稳定减少 FP”的改进 B：

- 对外同时报告 `92/498=18.5%` 明确判定覆盖率与 `ΔTP=0、ΔFP=-13、ΔFN=0`；
- 不把子集收益外推为对全部 quantity 响应普遍有效；
- 不为提高覆盖率而继续放宽当前措辞规则；
- 将提交 `dd3023b` 及本文档结论合入主线；
- 最新主线适配和五跑离线反事实已完成；在可运行测试范围内未发现回归，主线证据语义变化未改变本方案结论。

本轮仍不改 prompt、不扩展 claim 依赖集合、不调用 API、不开始改进 A/C。若以后提高覆盖率，应另开迭代并优先研究可程序化验证的算式重算。
