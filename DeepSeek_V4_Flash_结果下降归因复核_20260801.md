# DeepSeek V4 Flash 结果下降归因复核

日期：2026-08-01

## 裁决

“所有下降主要由代码修改造成”不成立；“所有下降主要由模型服务漂移造成”
同样过强。当前证据支持按实验拆分：

- SVAMP100：代码回归被排除；差异来自相同请求下的新鲜模型响应变化。
- Workspace A-prime 与第三 holdout：当前后处理代码回归被排除；相同 cache
  key 下的模型响应发生变化。
- MMLU1000：旧新实验合同不一致，代码、请求合同和模型响应无法分离；该组
  差值不得用于单因归因。

## 机械证据

### SVAMP100

- 历史报告代码：`3b59ae163b97f0f115601edf37a2c607ac16bb9e`。
- 新报告代码：`39e0c62f1bfa169a20af1a73156b54618770b128`。
- 两提交之间 `benchcore/` 与 `scripts/` 的 diff 文件数：0。
- 历史 cache SHA-256：
  `117906a173198190d8360bfb360bc1e8afd4788a1c61dd3dde6035b88d96d32a`。
- 旧 cache 在当前代码上回放：0 API，得到 50 candidates、33 TP、17 FP、
  5 FN、F1 0.750，与历史完全一致。
- 新鲜运行：44 candidates、29 TP、15 FP、9 FN、F1 0.707。
- 历史与新 cache 有 400 个相同 request key；400 个 response 全部不同。

结论：0.750→0.707 不是代码修改造成。

### Workspace A-prime calibration20

- 历史 cache SHA-256：
  `53740726724c1a58e200245a3795ca243c2573ec49aa1ce838b1f7d7b39fc6e4`。
- 旧 cache 在当前代码上回放：20/20 cache hits、0 API。
- 回放 `analysis.json` SHA-256：
  `fee5a065173851bb5597af5994e3beee9408bf40aaa0b9d62854d617d5434147`，
  与历史 `analysis.json` 逐字节相同。
- 指标完全复现：188/405 candidates、12/19 family hits、reviewed
  TP/FP/FN=13/3/8、F1 0.703。
- 历史与新运行有 19 个相同 request key，19 个 response 全部不同。

结论：A-prime 的下降不是当前本地 policy/analyzer 造成。

### Workspace 第三 holdout30

- 历史 cache SHA-256：
  `e512ea47624f32ace41f7c6d276c46d09ebf6d517e3fcaa5149932964625c9ca`。
- 旧 cache 在当前代码上回放：30/30 cache hits、0 API。
- 核心指标完全复现：424 hidden candidates、TP/FP/FN=26/13/6、
  P/R/F1=0.667/0.812/0.732。
- 历史与新运行的 30 个相同 request key 中，13 个 response 相同、17 个不同。

结论：候选增加与小幅 F1 变化来自响应变化，不是后处理代码变化。

### MMLU1000

- 旧运行输入：独立冻结文件 `experiments/mmlu_redux_pilot1000.jsonl`，输入
  SHA-256 `70cc9ee1...`；git commit `2b3ce354...`，dirty=true；
  `thinking=null`。
- 新运行输入：全量 5700 文件 + manifest；`thinking=disabled`。
- 新 manifest 与旧文件的 item ID 及原始 JSON 内容 1000/1000 一致。
- 但旧 cache 在当前代码和旧原始输入上仍然 0/3000 request hits；严格
  cache-only 回放全部 fail closed 为 operational unknown。
- 从旧快照到当前快照，`llm_auditor.py`、`llm_client.py`、`promotion.py`、
  `taxonomy.py`、`cli.py` 的实现哈希均变化；`report.py` 与
  `comparison.py` 未变。

结论：MMLU 差值混入请求构造/序列化、thinking 设置、promotion 和模型响应
等多重变化，现有产物不足以确定主因。若要真正归因，必须预注册并运行 2×2：
旧代码×当前模型、当前代码×当前模型，并固定同一输入与 thinking；历史 cache
不能替代这项实验。

## 新发现的实现缺陷

`LLMConfig` 定义了 `cache_only`，`LLMClient` 也会在 miss 时拒绝 HTTP；但普通
CLI 使用的 `load_llm_config()` 没有把 JSON 中的 `cache_only` 传给
`LLMConfig`。因此仅在配置文件写 `"cache_only": true` 并不能阻止 CLI 发起
网络请求。Workspace runner 通过运行时赋值绕过了这个缺口，所以 Workspace
归因结果不受影响。

本次 MMLU 首次诊断因此在人工中断前追加了 123 条新响应。原历史 cache 未被
修改；被污染的只是诊断副本。这 123 条响应不进入任何指标，保守估计额外成本
不超过约 0.6 元。

## 下一步

1. 单独修复 `load_llm_config(cache_only=...)`，加入“cache miss 时 API attempts
   必须为 0、cache 文件不得增长”的回归测试。
2. 保留 SVAMP/Workspace 当前结论，不再追加 API。
3. 撤回 MMLU 的“严格可比”措辞；只有确实需要回答模型升级效应时，才冻结
   同一代码、输入、thinking 后做小规模 2×2 canary，再决定是否花钱跑 1000。

