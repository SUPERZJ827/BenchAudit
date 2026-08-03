# MMLU holdout 污染清点结果

> 日期：2026-08-03
> 裁决：`NOT_IDENTIFIABLE_SCAN_COVERAGE`
> API / 网络调用：0 / 0
> 未生成 holdout manifest，未运行 auditor

## 0. 结论

污染清点应该先于 holdout 冻结；本轮也证明了它不是三个 manifest 的简单并集。
扫描覆盖了全部本地 Git refs 的可达历史 blob 与当前工作树（含 ignored、
untracked、hidden 文件和 ZIP 成员），且没有解析或输出 5,700 条候选题的题面、
gold、`verified_gold` 或 audit label。

精确 ID 层面的结果仍为：

- 已暴露：**1,087 / 5,700**；
- `repo-artifact-unseen` 候选：**4,613 / 5,700**；
- 已暴露集合与 `pilot1000 + pilot200 + diag8` 三份 manifest 的 ID 并集
  **逐项完全相同**，两边差集均为零。

这显著加强了“没有发现额外 exact-ID 暴露”的证据，但不能把 4,613 条称为
绝对干净 holdout。

## 1. 冻结执行链

| 对象 | 值 |
|---|---|
| 协议提交 | `b7c8fb0` |
| 协议 SHA-256 | `a825e0309c7bde2d5cecc26c695f098fe7896f04d81f43ca2bb41b563c0d27fe` |
| 扫描器提交 | `3d289e9` |
| 扫描器 SHA-256 | `c66ce9e1dfe7771492b6d8ec8e49df8c49b272f36841855f899cd7b92bbefeee` |
| `inventory.json` SHA-256 | `a416ea4a2e3dd41865d6f0f12db46df67db91b324a7a2b6273fa66c21b5d0f10` |
| `REPORT.md` SHA-256 | `f288107462361b3afffb8d7382540aea4e16d029ffa5aad4222c0eca833245f3` |
| `receipt.json` SHA-256 | `f13d046b2e4b3d17db01cd8a562c4f710b81ac38e2d41dc536d70f64d59f8961` |

两次独立临时目录重放与最终仓库产物三者逐字节相同。

## 2. 实际覆盖

| 表面 | 数量 |
|---|---:|
| 本地 Git refs | 58 |
| 唯一可达 Git blobs | 1,116 |
| 当前工作树 regular files | 3,654 |
| exact-ID exposed items | 1,087 |
| exact-ID unseen items | 4,613 |

数据集行使用锚定在行首的 byte-level `id` extractor；`dataset_rows_json_decoded`
为 false。工作树扫描不跟随 symlink，ZIP 从成员原始解压字节扫描；任何匹配只输出
item ID 与源路径/blob OID，不输出上下文。

## 3. 两个阻塞项

### 3.1 Digest-only caches

发现 **106 个** `{"key": <digest>, "response": ...}` 形状且无法按 item 反解的
cache 文件，共 **114,595 条**。这些缓存不含 prompt，只含 prompt-derived key 与
response；本轮协议禁止用候选题重建历史 prompt，所以不能证明某个候选 item
是否对应其中一条 key。

按路径名称作非裁决性诊断，明显与 MMLU/ranking-impact 相关的 7 个 cache 共
14,839 条；它们很可能由已有的 1,087 条实验项产生，但“很可能”不是证明。
在建立由冻结 report/manifest 到 cache key 的机械绑定以前，
`absolute_blindness_identifiable` 必须保持 false。

### 3.2 全工作树覆盖不足

冻结协议要求其他压缩格式 fail-closed。扫描遇到两份未支持的 LaTeX 同步文件：

- `IEEE-conference-template-062824/IEEE-conference-template-062824.synctex.gz`
- `IEEE-conference-template-062824/benchcore_paper.synctex.gz`

它们看起来与 MMLU 无关，但协议是在见结果前冻结的，不能事后排除。因此本轮正式
结局只能是 `NOT_IDENTIFIABLE_SCAN_COVERAGE`。没有删除文件、缩小根目录或把失败
改写成 PASS。

## 4. 后续边界

本轮允许做出的最强陈述是：

> 在 58 个本地 refs 的 1,116 个可达 blob 与当前工作树 3,654 个 regular file
> 中，发现 exact MMLU item ID 的集合恰好等于既有三个 manifest 的 1,087 条并集；
> 其余 4,613 条没有发现 exact-ID 暴露证据。

不得说“4,613 条从未被看过”或“缓存中没有这些题”。本轮也不允许直接从这
4,613 条生成 holdout。

若继续，应另冻 V2 清点协议，并在运行前解决两个独立问题：

1. 明确支持 gzip 解压扫描，不能仅按文件名排除；
2. 用冻结 run metadata / manifest 机械绑定 MMLU cache key 的来源集合，无法绑定的
   cache 继续保留为 unresolved，而不是按路径名称猜测。

只有 V2 清点得到可审计的 scoped pool 后，才进入分层抽样和 holdout manifest 冻结。
