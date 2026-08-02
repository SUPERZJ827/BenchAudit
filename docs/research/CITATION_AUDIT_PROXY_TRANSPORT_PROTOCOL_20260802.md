# 研究综述引用审计：显式代理传输协议

> 日期：2026-08-02  
> 状态：**frozen before proxy audit output exists**  
> API/LLM：0  
> 目的：在不改变内容判据和 TLS 验证的前提下，修正本机 direct egress 不可达造成的空审计

## 0. 原因更正与旧产物边界

旧晨报的 `skipped_no_network` 已由 hash-bound addendum 更正为：

```text
direct_egress_unavailable_proxy_path_not_used
```

宿主直连 `13.35.202.121:443` 在 6.0 秒后超时，而通过 `http://127.0.0.1:17890` 请求 HTTPS 正文可返回 HTTP 200。旧脚本显式使用 `ProxyHandler({})`，因此 26 条全 unreachable 的半成品只测了 direct transport，已作废且不得作为本轮输入。

旧晨报、旧脚本与旧半成品均不修改。本轮另产 v2 receipt。

## 1. 冻结输入

| 项 | 值 |
|---|---|
| survey | `/home/zhoujun/llmdata/after623/docs/research/BenchAudit_自动化Benchmark审计领域系统调研_20260731.md` |
| survey SHA-256 | `659f8bf22bf3c0d7068f476fd56c9c3c016ebaa19cc7a38bb75d5df6d195b1a7` |
| extraction rule | `LINK_RE` + first-seen URL de-duplication，未修改 |
| mechanically extracted unique URLs | **83** |
| old script SHA-256 | `19df29e2384d38793c70b0fc5a8ada5e441ccd22a4bbfcde4d6ce1635306da65` |
| proxy-capable script SHA-256 | `39f37190d37905d390a88392623bb49065d4d17226187b3ffc80aac00a725663` |
| proxy | `http://127.0.0.1:17890`，无 credentials |
| output | `docs/experiments/citation_receipts_proxy_20260802.jsonl`，运行前必须不存在 |

先前口头估计为 80 条；对冻结 survey 运行未联网 extraction 实际得到 83 个唯一 URL。本轮完整性门以**冻结输入机械导出的 83**为准，不删除三条来迎合估计值。该计数发生在任何 proxy 审计结果产生前。

## 2. 唯一允许的实现偏离

相对旧脚本，只有以下变化允许：

1. transport 从显式 direct 改为显式 proxy；
2. 每条 receipt 新增 `transport` 与 `proxy_url`；
3. 加入已在结果前预登记的 `blocked_by_anti_bot` 终态；
4. 输出文件用 exclusive create，防止覆盖旧结果；
5. 结束时机械检查终态互斥完备。

代理通过标准 HTTPS CONNECT 转发。URL、HTTP request、redirect、响应正文、证书验证、title extraction、title matching、404/410 与 unreachable 规则均不放宽；TLS 仍由 Python default context 对目标站点端到端验证。不得搜索替代来源、改 URL、关闭证书验证或调用模型。

## 3. 五个互斥终态

每个 citation 必须恰好进入一个状态：

1. `resolved`
2. `title_mismatch`
3. `not_found`
4. `unreachable`
5. `blocked_by_anti_bot`

`blocked_by_anti_bot` 的冻结条件：

```text
http_status == 200
AND normalize(resolved_title) == "verifying your browser"
```

normalize = Unicode NFKC、HTML unescape、casefold、保留 word token、单空格连接。该状态优先于 resolved/title_mismatch，计入 unverified，永不得计入 not_found 或 resolved。

运行后不得增加新的 anti-bot signature。其他未识别 interstitial 只能按现有规则落入 title_mismatch/unreachable，并在报告边界中披露。

## 4. 完整性门

- output 行数必须等于 83；
- 83 个 `cite_key` 与 URL 均唯一；
- 每行 `receipt_schema == benchaudit-citation-resolution-v2`；
- 每行 `survey_sha256` 等于 §1；
- 每行 `transport == proxy` 且 `proxy_url == http://127.0.0.1:17890`；
- 五种 terminal count 合计严格等于 83；
- 不存在其他 verdict；
- 脚本 SHA 与 survey SHA 不符时 fail-closed。

## 5. 解释边界

- `resolved` 只证明 URL 可达，以及在有可抽取 title 时通过冻结 title rule；不验证论文中的数值主张；
- `title_mismatch` 可能包含未预登记的反爬/登录/JavaScript interstitial，必须人工看，不自动称为错误引用；
- `blocked_by_anti_bot`、`unreachable` 均是 unverified，不是 not_found；
- 本轮 transport 修正不允许把任何未验证引用提升为已核实研究结论。

## 6. 提交顺序

1. 本协议、proxy-capable script 与测试先提交；
2. 从固定提交运行一次；实验级补跑次数为 0；
3. 运行结果、summary 与哈希另提交；
4. 不修改旧晨报或 causal addendum。
