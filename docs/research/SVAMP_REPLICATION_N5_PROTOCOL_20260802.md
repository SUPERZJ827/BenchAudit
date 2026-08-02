# SVAMP 同代码重复运行协议（n=5）

> 日期：2026-08-02
> 状态：**frozen before any paid API request**
> 执行者：Claude（独立于实现方）
> 目的：把 `BenchAudit_审计器仪器稳定性_SVAMP双跑实验_20260802.md` 的 n=2 跨度变成可引用的分布
> 授权：用户已批准约 ¥7 的 API 支出

## 0. 待回答的问题

在代码、模型、配置、输入全部固定的条件下，BenchAudit 的 SVAMP 审计结果在重复运行之间的离散程度有多大？

具体输出三个量：

1. 候选层 P/R/F1 的 5 次分布（min / median / max / 极差）；
2. 逐条 finding 的两两复现率（10 个配对的 Jaccard）；
3. 逐 detection_method 的复现率（确定性方法应为 1.00）。

## 1. 冻结的执行条件

| 项 | 值 |
|---|---|
| 代码 | 分离 worktree，detached HEAD `d705f9b7dfaa679b3cd71d65553ead0c35e27432` |
| 与既有两次运行的代码关系 | `git diff 3b59ae1 d705f9b -- benchcore/` = **0 行**，故 07-30 与 08-01 两次运行可并入同一样本 |
| 输入 | `/home/zhoujun/llmdata/datasets/svamp_platinum/svamp_platinum_all.jsonl` |
| 输入 SHA-256 | `f27f8ebf56b33fbeea4b6430f63f24c66adb37bd38a1a8b2bbe62960f588063e` |
| 抽样 manifest | `experiments/svamp_platinum_pilot100.manifest.json` |
| manifest SHA-256 | `c4ef5ddfb590b210243c0114d7d9eed7a15c2c0a1cf14a98f763cb7d4992d861` |
| 模型 | `deepseek-v4-flash` |
| temperature | 0.0 |
| thinking | disabled |
| max_tokens | 5000 |
| 投票数 | 1（不启用 vote） |
| LLM auditors | `gold,question,quantity,event` |
| gold-evidence-mode | `cascade` |
| 重复次数 | **5** |
| 缓存 | **每次运行使用各自独立的空缓存**（保证样本独立；不得跨运行复用） |
| `--workers` | **8**（见 §1.1 修订记录） |
| `--allow-remote-data-egress` | 必须显式传入（CLI 的出口守卫会拦截；SVAMP 是公开 benchmark，07-30 与 08-01 两次已授权运行同样发送该数据） |

### 1.1 修订记录（发生在任何结果产出之前）

初版协议未指定 `--workers`，CLI 默认值为 1。首次试跑以 workers=1 运行约 7 分钟后，实测吞吐约 20 次调用/分钟，推算单次运行需约 33 分钟、5 次约 2.75 小时；而 07-30 那次的 run_metadata 显示 635 次调用耗时 111 秒（约 5.7 次/秒），说明既有两次运行都使用了并行。

因此修订为 `--workers 8`，理由有二：

1. 与既有 07-30 / 08-01 两次运行的执行形态一致，§5 的 n=7 合并才成立；
2. 把总耗时压到可控范围。

**该试跑被终止，其 160 条缓存被删除，从未产出任何 report，因此未观测到任何结果。** 这次修订是"见结果前修订"，不是"见结果后修订"；被丢弃的约 ¥0.3 计入总预算。

并行只影响 item 之间的调度；单个 item 内部的级联仍是顺序的，且 07-30 的 run_metadata 显示 `singleflight_shared_results: 0`，即并行未导致跨 item 共享调用结果。

命令模板（第 k 次）：

```bash
python -m benchcore.cli audit <input> \
  --manifest experiments/svamp_platinum_pilot100.manifest.json \
  --llm-audit --llm-auditors gold,question,quantity,event \
  --gold-evidence-mode cascade \
  --llm-config <frozen config> \
  --llm-cache <run_k 独立缓存> \
  --out <run_k/report.json> --md <run_k/report.md>
```

## 2. 冻结的度量口径

- 真值字段：`metadata.audit_label`；clean 值集合 `{clean}`；缺陷项 38 条；
- 预测项 = 至少有一条 `defect_scope != "presentation"` 的 violation 的 item；
- 候选层 P/R/F1 按 item 计；
- 逐条 finding 的身份键 = `(item_id, detection_method, defect_type)`；
- 复现率 = Jaccard = `|A∩B| / |A∪B|`；
- 逐方法复现率在所有 10 个配对上分别计算后取均值，同时报告 min/max。

**以上口径在运行前冻结，运行后不得更改，不得增删指标。**

## 3. 预算与硬性停止条件

| 项 | 上限 |
|---|---|
| 总 API 花费 | **≤ ¥15**（预期约 ¥7） |
| 总 provider token | ≤ 8,000,000 |
| 单次运行 API 尝试 | ≤ 700（沿用配置内 `max_api_attempts`） |

出现以下任一情况，**立即停止全部剩余运行并如实报告**：

1. 任何一次运行的 operational failure 比例 > 5%；
2. 出现任何 LLM 派生的 `confirmed`（review 天花板逃逸）——这将是比稳定性更严重的问题；
3. 累计 token 超过上限；
4. 传输层反复失败导致某次运行不完整。

**不允许**：因为结果不好看而追加运行、更换题目、更换模型、改阈值或改 prompt。

## 4. 预注册的解读规则

- 若 5 次的 F1 极差 **< 0.02**：说明 n=2 观察到的 0.043 落差不能代表常态，需重新审视 07-30/08-01 两次之间是否还有未识别的差异；
- 若极差 **≥ 0.02**：确认审计器输出在固定条件下具有实质性运行间波动，`n=1` 的跨版本对比不可归因这一结论成立；
- 无论哪种，**确定性方法（`static_rule`、`cross_artifact_consistency` 等）的复现率必须为 1.00**；若不是 1.00，那是一个比波动更严重的缺陷，必须单独报告。

上述三条在看到任何结果之前写定。

## 5. 与既有样本的合并规则

07-30 与 08-01 两次运行的 `benchcore` 与本协议使用的版本逐字节相同，输入哈希与 manifest 哈希也相同，因此**可以并入同一样本，总 n=7**。

但必须披露两点不对称：

1. 07-30 那次有 32 条缓存命中（来自更早的缓存），并非全新缓存；
2. 07-30、08-01 与本次 5 跑分布在三个不同日期，provider 侧服务是否变化不可从本地判断。

因此主结论以**本次 5 跑（同日、全新缓存、完全对称）**为准，n=7 仅作为补充参考。
