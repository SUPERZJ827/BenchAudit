# 研究综述引用审计：显式代理结果

> 日期：2026-08-02  
> 状态：**PASS_COMPLETENESS_WITH_MANUAL_REVIEW_QUEUE**  
> 输入：83 个机械抽取的唯一 URL  
> 模型/API：0

## 1. 结果

| 终态 | 数量 | 解释 |
|---|---:|---|
| resolved | 26 | URL 可达，且可抽取 title 时通过冻结 title rule |
| title_mismatch | 55 | 进入人工复核；不能直接称为错误引用 |
| not_found | 0 | 没有 404/410 |
| unreachable | 2 | 两个 URL 返回 403 |
| blocked_by_anti_bot | 0 | 冻结的 exact signature 未命中 |
| **合计** | **83** | 与抽取数严格相等 |

完整性门全部通过：83 行、83 个唯一 cite key、83 个唯一 URL；schema、survey SHA、transport 与 proxy URL 全部单值且正确。

## 2. 代理修正带来的信息增量

旧 direct-only 路径在本宿主上无法访问外部 HTTPS，因而没有生成一条完整 receipt。本轮使用显式 `http://127.0.0.1:17890`，81/83 URL 得到 HTTP 200，另 2 条得到 HTTP 403。

这证明原 `skipped_no_network` 不是来源不可用，而是 `direct_egress_unavailable_proxy_path_not_used`。代理只改变 transport；目标 URL、重定向、TLS 校验、正文与标题判据没有放宽。

## 3. 不能把 55 个 title mismatch 当成 55 条错误

机械规则故意保守，并把短链接标签视为未匹配。例如 `STING`、`EvalPlus`、`Data Shapley` 这类别名会与论文全标题不匹配；“LLM”与“Large Language Model”之类标题变体也可能低于冻结 token-Jaccard 门槛。因此：

```text
26 resolved = 已机械核实下界
55 title_mismatch ≠ 55 错误引用
```

55 条是人工 title 对照队列，不能用于计算引用准确率。

## 4. anti-bot 规则的诚实负结果

6 条 OpenReview 响应的可抽取 title 是：

```text
Verifying your browser | OpenReview
```

结果前冻结的规则要求 normalized title **精确等于** `verifying your browser`，因此 6 条均未命中 `blocked_by_anti_bot`，仍为 `title_mismatch`。本轮没有在看到结果后把规则加宽为 contains/prefix。

这 6 条应在人工复核时优先标为站点中间页，但该人工判断是结果解释，不回写机器 receipt。若未来要机械识别该变体，必须另冻协议并在新数据上验证。

## 5. unreachable

两条 HTTP 403：

1. Nottingham repository 的 metamorphic testing review；
2. ACM DOI `10.1145/3287560.3287596`。

403 只表示本轮无法验证，不是 not_found。

## 6. 产物

| Artifact | SHA-256 |
|---|---|
| protocol | `4b12bab8f7217f4e490510276dc9f978467c0fdbfd2b2e688580edd5086fd48e` |
| script | `39f37190d37905d390a88392623bb49065d4d17226187b3ffc80aac00a725663` |
| receipts JSONL | `0527d9fb8827bc85623d7dc8ec17ae7cc7de39954442391f1f01c73f33ea4367` |

机器汇总见 `docs/experiments/citation_audit_proxy_summary_20260802.json`。
